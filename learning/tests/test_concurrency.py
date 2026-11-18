import json
import os
import sqlite3
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import httpx
from django.contrib.auth import get_user_model
from django.db import connection, connections
from django.db.models.query import QuerySet
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from learning import authoring, providers, review, views, work
from learning.models import Card, Deck, Attempt, ScoredReview, Presentation, GenerationJob
from learning.worker import run_worker
from .test_learning import GENERIC, VOCAB, PAIR, audio_bytes


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user("concurrency")
        self.deck=Deck.objects.create(owner=self.user,name="Concurrent")
        self.card=authoring.save_card(self.deck,"generic",GENERIC)

    def presentation(self, deck=None):
        return review.next_question(self.user,deck or self.deck)

    def test_concurrent_practice_entries_reuse_one_current_question(self):
        barrier=threading.Barrier(2)
        def enter(_):
            try:
                barrier.wait()
                return review.next_question(self.user,self.deck).pk
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            questions=list(pool.map(enter,range(2)))
        self.assertEqual(questions[0],questions[1])
        self.assertEqual(Presentation.objects.count(),1)

    def test_deck_progress_stays_coherent_across_committed_restore_and_archive(self):
        card=authoring.save_card(self.deck,"generic",{**GENERIC,"answer":"four things"})
        for _ in range(2):
            attempt=review.submit(self.presentation(),"speak",2)
            self.assertEqual(review.commit_grade(attempt.pk,attempt.claim,"D",[],"Progress fixture.").state,"assessed")
        authoring.archive_card(card,True)
        fetch_all=QuerySet._fetch_all
        for archived,before_total,after_total in [(False,1,2),(True,2,1)]:
            with self.subTest(archived=archived):
                changed=False

                def change_membership():
                    try:
                        authoring.archive_card(card,archived)
                    finally:
                        connections.close_all()

                def change_after_read(queryset):
                    nonlocal changed
                    fetch_all(queryset)
                    if not changed and queryset.model is Card and queryset.query.group_by:
                        changed=True
                        # Commit on an independent connection after the first aggregate has fully read its snapshot.
                        with ThreadPoolExecutor(max_workers=1) as pool:
                            pool.submit(change_membership).result(timeout=5)

                with patch.object(QuerySet,"_fetch_all",change_after_read):
                    row=views.deck_progress(self.user,[self.deck])[self.deck.pk]
                self.assertTrue(changed)
                self.assertEqual(row,{"total":before_total,"qualified":before_total,"percent":100})
                self.assertTrue(0 <= row["qualified"] <= row["total"])
                self.assertEqual(views.deck_progress(self.user,[self.deck])[self.deck.pk],
                    {"total":after_total,"qualified":after_total,"percent":100})

    def test_two_real_connections_cannot_both_score_same_progress(self):
        first=review.submit(self.presentation(),"speak",1,"unused")
        second=review.submit(review.next_question(self.user),"speak",1,"unused")
        barrier=threading.Barrier(2)
        def complete(a):
            try:
                barrier.wait()
                return review.commit_grade(a.pk,a.claim,"E",[],"Concurrent complete").state
            finally: connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(complete,[first,second]))
        self.assertEqual(sorted(results),["assessed","closed_unassessed"])
        self.assertEqual(ScoredReview.objects.count(),1)
        self.card.refresh_from_db(); self.assertEqual(self.card.progress_version,1)

    def test_concurrent_generation_claims_are_distinct(self):
        for word in ["first","second"]:
            authoring.save_card(self.deck,"vocabulary",{**VOCAB,"word":word})
        barrier=threading.Barrier(2)
        def claim(_):
            try:
                barrier.wait()
                return work.claim_work()
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            receipts=list(pool.map(claim,range(2)))
        self.assertEqual(len({r[1] for r in receipts}),2)
        self.assertEqual(GenerationJob.objects.filter(state="processing",started_at__isnull=False,deadline__isnull=False).count(),2)

    def test_concurrent_manual_regeneration_requests_coalesce_into_one_job(self):
        card=authoring.save_card(self.deck,"vocabulary",{**VOCAB,"word":"manual-regen"})
        job=card.generation_jobs.get(mode="initial")
        job.state="processing";job.started_at=timezone.now();job.deadline=job.started_at+timedelta(seconds=300);job.save()
        work.save_pair(job.pk,job.claim,PAIR,{"model":"test"})
        card.refresh_from_db()
        barrier=threading.Barrier(2)
        def request(_):
            try:
                barrier.wait()
                return authoring.request_example_regeneration(card,expected_source_version=card.source_version,
                    expected_pair_id=card.active_pair_id).pk
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            job_ids=list(pool.map(request,range(2)))
        self.assertEqual(job_ids[0],job_ids[1])
        self.assertEqual(card.generation_jobs.filter(mode="manual",state="queued").count(),1)
        self.assertIsNone(card.rotation_token)  # automatic intent untouched by the manual request
        self.assertFalse(card.generation_jobs.filter(mode="rotation").exists())

    @override_settings(GENERATION_TIMEOUT_SECONDS=5,WORKER_CLEANUP_GRACE_SECONDS=1,WORKER_CONCURRENCY=2)
    def test_aged_generation_queue_executes_after_all_slots_recover(self):
        stop=threading.Event();lock=threading.Lock();requests=[];running=peak=0
        class Handler(BaseHTTPRequestHandler):
            def do_POST(inner):
                nonlocal running,peak
                body=json.loads(inner.rfile.read(int(inner.headers["Content-Length"])))
                source=json.loads(body["messages"][1]["content"])
                reviewing="candidate" in source
                with lock:
                    requests.append((source["word"],reviewing));running+=1;peak=max(peak,running)
                try:
                    inner.send_response(200);inner.send_header("Content-Type","application/json");inner.end_headers()
                    stall=(not reviewing and source["word"].startswith("stall")) or (reviewing and source["word"]=="review-stall")
                    if stall:
                        while not stop.wait(.02):inner.wfile.write(b" ");inner.wfile.flush()
                    elif reviewing:
                        inner.wfile.write(json.dumps({"choices":[{"finish_reason":"stop","message":{"content":json.dumps(
                            {"verdict":"accept","issues":[],"pair":source["candidate"]})}}]}).encode())
                    else:
                        time.sleep(1)
                        pair={"target_sentence":"A <focus>healthy</focus> example.","native_sentence":"一个<focus>健康的</focus>例子。"}
                        inner.wfile.write(json.dumps({"choices":[{"finish_reason":"stop","message":{"content":json.dumps(pair)}}]}).encode())
                except (BrokenPipeError,ConnectionResetError):pass
                finally:
                    with lock:running-=1
            def log_message(inner,*args):pass
        server=ThreadingHTTPServer(("127.0.0.1",0),Handler);server.daemon_threads=True
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        cards=[];old=timezone.now()-timedelta(hours=2)
        for index,word in enumerate(["stall-a","stall-b","review-stall","healthy"]):
            card=authoring.save_card(self.deck,"vocabulary",{**VOCAB,"word":word});cards.append(card)
            card.generation_jobs.update(requested_at=old+timedelta(seconds=index))
        started=time.monotonic();anchor=timezone.now()
        try:
            endpoint=f"http://127.0.0.1:{server.server_port}/generate"
            with patch.dict(os.environ,{"GENERATOR_ENDPOINT":endpoint,"GENERATOR_API_KEY":"test-only",
                    "EXAMPLE_REVIEWER_ENDPOINT":endpoint,"EXAMPLE_REVIEWER_API_KEY":"test-only","ALLOW_INSECURE_PROVIDER_HTTP":"1"}):
                run_worker(once=True,concurrency=2)
            elapsed=time.monotonic()-started
            self.assertEqual(GenerationJob.objects.filter(state="done").count(),1)
            self.assertEqual(GenerationJob.objects.filter(state="failed").count(),3)
            cards[3].refresh_from_db();self.assertTrue(cards[3].ready)
            stalled=GenerationJob.objects.get(card=cards[2])
            self.assertEqual((stalled.state,stalled.error_category),( "failed","timeout"))
            self.assertEqual(sorted(requests),[("healthy",False),("healthy",True),("review-stall",False),
                                               ("review-stall",True),("stall-a",False),("stall-b",False)])
            self.assertLessEqual(peak,2)
            self.assertLess(elapsed,12)
            for job in GenerationJob.objects.all():
                self.assertGreaterEqual(job.started_at,anchor)
                self.assertEqual(job.deadline-job.started_at,timedelta(seconds=5))
            self.assertEqual(ScoredReview.objects.count(),0)
            print(f"GENERATION-CAPACITY: aged queue recovered after stalls incl. a stalled review; healthy completion in {elapsed:.3f}s.",flush=True)
        finally:
            stop.set();server.shutdown();server.server_close();thread.join(timeout=2)

    def test_exit_and_grade_compete_on_separate_connections(self):
        a=review.submit(self.presentation(),"speak",1,"unused")
        barrier=threading.Barrier(2)
        def compete(action):
            try:
                barrier.wait()
                return (review.exit_attempt(a) if action=="exit" else review.commit_grade(a.pk,a.claim,"E",[],"Complete")).state
            finally: connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(compete,["exit","grade"]))
        self.assertEqual(len(set(results)),1)
        self.assertIn(results[0],["assessed","closed_unassessed"])
        self.assertEqual(ScoredReview.objects.count(),int(results[0]=="assessed"))

    @override_settings(ASSESSMENT_TIMEOUT_SECONDS=15)
    def test_provenance_transaction_wait_consumes_the_inference_allowance(self):
        self.provenance_wait_scenario(simulated=True)

    @override_settings(ASSESSMENT_TIMEOUT_SECONDS=15)
    def test_provenance_wait_and_encoding_exhaust_the_real_deadline(self):
        self.provenance_wait_scenario(simulated=False)

    def provenance_wait_scenario(self, simulated):
        """A real provenance-write wait plus encoding must exhaust the original deadline before HTTP."""
        self.assertEqual(connection.vendor,"sqlite")
        self.assertFalse(connection.is_in_memory_db(),"This test requires file-backed SQLite.")
        requests=[]
        def handler(request):
            requests.append(request)
            result={"units":[{"id":1,"outcome":"complete","reason":"Matches."}]}
            return httpx.Response(200,json={"choices":[{"finish_reason":"stop","message":{"content":json.dumps(result)}}]})
        folder=tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        audio_dir=Path(folder.name)
        name=uuid.uuid4().hex+".audio"
        (audio_dir/name).write_bytes(audio_bytes())
        (audio_dir/(name+".wav")).write_bytes(audio_bytes())
        env={"PATH":os.environ.get("PATH",os.defpath),"AUDIO_ASSESS_PROVIDER":"qwen",
            "AUDIO_ASSESS_ENDPOINT":"http://127.0.0.1:9/assessment","AUDIO_ASSESS_API_KEY":"test-only",
            "AUDIO_ASSESS_MODEL":"fake-qwen","AUDIO_ASSESS_TIMEOUT_SECONDS":"60","ALLOW_INSECURE_PROVIDER_HTTP":"1",
            "AUDIO_ASSESS_API_MODE":"chat_completions"}
        with override_settings(AUDIO_DIR=audio_dir), patch.dict(os.environ,env,clear=True):
            a=review.submit(self.presentation(),"speak",1,name)
            kind,claimed_pk,claimed_claim,_=work.claim_work()
            self.assertEqual((kind,claimed_pk),("assessment",a.pk))
            clock={"wall":timezone.now(),"monotonic":0.0}
            wall_now=(lambda:clock["wall"]) if simulated else timezone.now
            monotonic=(lambda:clock["monotonic"]) if simulated else time.monotonic
            deadline=wall_now()+timedelta(seconds=14 if simulated else 8)
            Attempt.objects.filter(pk=claimed_pk).update(deadline=deadline)
            progress=Card.objects.filter(pk=self.card.pk).values("due","fsrs","review_count","progress_version").get()

            selected=threading.Event(); locked=threading.Event(); begin=threading.Event()
            begin_returned=threading.Event(); encoding=threading.Event(); observed={}
            original_profile=work.bounded_profile
            original_encode=providers.transcode_mp3
            original_client=httpx.AsyncClient
            def select_profile(task,absolute_deadline):
                p=original_profile(task,absolute_deadline)
                observed["profile"]=p
                selected.set()
                if not locked.wait(5):
                    raise AssertionError("The test did not acquire the writer lock.")
                return p
            def slow_encode(path,budget):
                observed["encoding_start"]=wall_now(); observed["encoding_budget"]=budget
                started=monotonic()
                encoding.set()
                data=original_encode(path,budget)
                observed["encoded_bytes"]=len(data)
                if simulated:
                    # Model a slow encode without making the test depend on host scheduling.
                    clock["wall"]+=timedelta(seconds=7); clock["monotonic"]+=7
                else:
                    # Hold the real encoding result past the wall-clock deadline.
                    time.sleep(max(0,(deadline-wall_now()).total_seconds())+0.2)
                observed["encoding_end"]=wall_now(); observed["encoding_elapsed"]=monotonic()-started
                return data
            def process():
                try:
                    db=connections["default"]
                    db.ensure_connection()
                    def trace(sql):
                        if sql.upper()=="BEGIN IMMEDIATE" and selected.is_set() and not begin_returned.is_set():
                            begin.set()  # SQLite has entered the provenance transaction.
                    def measure(execute,sql,params,many,context):
                        if sql.upper()=="BEGIN IMMEDIATE" and selected.is_set() and not begin_returned.is_set():
                            started=time.monotonic()
                            try:return execute(sql,params,many,context)
                            finally:
                                observed["write_wait"]=time.monotonic()-started
                                begin_returned.set()
                        return execute(sql,params,many,context)
                    db.connection.set_trace_callback(trace)
                    with db.execute_wrapper(measure):
                        return work.process_assessment(claimed_pk,claimed_claim)
                finally:
                    connections.close_all()

            writer=sqlite3.connect(connection.settings_dict["NAME"],uri=True,timeout=5,isolation_level=None)
            error=None
            try:
                with patch("learning.work.timezone",SimpleNamespace(now=wall_now)), \
                        patch("learning.providers.time",SimpleNamespace(monotonic=monotonic)), \
                        patch("learning.work.bounded_profile",side_effect=select_profile), \
                        patch("learning.providers.transcode_mp3",side_effect=slow_encode), \
                        patch("learning.providers.request",wraps=providers.request) as model_request, \
                        patch("learning.providers.httpx.AsyncClient",
                            side_effect=lambda **kw: original_client(transport=httpx.MockTransport(handler),**kw)):
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        future=pool.submit(process)
                        try:
                            self.assertTrue(selected.wait(5),"Profile selection was not reached.")
                            writer.execute("BEGIN IMMEDIATE")
                            locked.set()
                            self.assertTrue(begin.wait(5),"SQLite did not enter the provenance write.")
                            self.assertFalse(begin_returned.wait(.2 if simulated else 2),"The provenance write did not wait for the lock.")
                            self.assertFalse(encoding.is_set())
                            if simulated:
                                # Advance both clocks only after the real transaction is blocked.
                                clock["wall"]+=timedelta(seconds=8); clock["monotonic"]+=8
                        finally:
                            if writer.in_transaction:writer.rollback()
                            locked.set()
                        try:future.result(timeout=10)
                        except providers.StageError as exc:error=exc
            finally:
                writer.close()
        self.assertEqual(len(requests),0,"No model request may start after the deadline.")
        model_request.assert_not_called()
        self.assertIsNotNone(error)
        self.assertEqual((error.stage,error.category),("AUDIO_ASSESS","timeout"))
        self.assertTrue(begin_returned.is_set())
        self.assertGreaterEqual(observed["write_wait"],0.2 if simulated else 1.9)
        self.assertTrue(encoding.is_set())
        self.assertGreater(observed["encoded_bytes"],0)
        self.assertEqual(observed["profile"].protocol,"qwen")
        if simulated:
            self.assertEqual((observed["profile"].timeout,observed["encoding_budget"]),(14,6))
        else:
            self.assertGreater(observed["profile"].timeout-observed["encoding_budget"],1.9)
        self.assertLess(observed["encoding_start"],deadline)
        self.assertGreaterEqual(observed["encoding_end"],deadline)
        self.assertGreater(observed["encoding_elapsed"],observed["encoding_budget"])
        self.assertLess(observed["encoding_elapsed"],observed["profile"].timeout)
        work.fail("assessment",claimed_pk,claimed_claim,error)
        a.refresh_from_db()
        self.assertEqual((a.state,a.error_stage,a.error_category,a.retryable,a.grade,a.transcript),
            ("failed","AUDIO_ASSESS","timeout",True,"",""))
        self.assertNotEqual(a.claim,claimed_claim)
        self.assertEqual(a.judge_provenance,observed["profile"].metadata())
        self.assertEqual(Card.objects.filter(pk=self.card.pk).values("due","fsrs","review_count","progress_version").get(),progress)
        self.assertEqual(ScoredReview.objects.count(),0)

    @override_settings(ASSESSMENT_TIMEOUT_SECONDS=5,WORKER_CLEANUP_GRACE_SECONDS=1,WORKER_CONCURRENCY=1)
    def capacity_scenario(self, conversion=False):
        """WORKER-CAPACITY: occupy the only slot, then enqueue healthy work at second 4."""
        stop=threading.Event(); requests=[]
        class Handler(BaseHTTPRequestHandler):
            def do_POST(inner):
                body=json.loads(inner.rfile.read(int(inner.headers["Content-Length"])))
                requests.append(body)
                text=next(part["text"] for part in body["messages"][1]["content"] if part["type"]=="text")
                inner.send_response(200); inner.send_header("Content-Type","application/json"); inner.end_headers()
                if "Stall fixture" in text:
                    try:
                        while not stop.wait(.04): inner.wfile.write(b" "); inner.wfile.flush()
                    except (BrokenPipeError,ConnectionResetError): pass
                else:
                    time.sleep(1)
                    inner.wfile.write(json.dumps({"choices":[{"finish_reason":"stop","message":{"content":json.dumps(
                        {"units":[{"id":1,"outcome":"complete","reason":"Complete fixture"}]})}}]}).encode())
            def log_message(inner,*args): pass
        server=ThreadingHTTPServer(("127.0.0.1",0),Handler); server.daemon_threads=True
        thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        Card.objects.filter(pk=self.card.pk).update(question="Stall fixture?")
        a=review.submit(self.presentation(),"speak",1,"missing")
        folder=tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        audio_dir=Path(folder.name)
        a.audio_name="fault.audio"
        (audio_dir/a.audio_name).write_bytes(audio_bytes())
        a.save()
        binary=audio_dir/"ffmpeg"
        pidfile=audio_dir/"child.pid"
        binary.write_text("#!/usr/bin/python3\nimport os,sys,time\nfrom pathlib import Path\n"
            "if sys.argv[-1]=='pipe:1':\n    sys.stdout.buffer.write(b'fake-mp3')\n"
            "else:\n    Path("+repr(str(pidfile))+").write_text(str(os.getpid()))\n    time.sleep(300)\n")
        binary.chmod(0o700)
        deck=Deck.objects.create(owner=self.user,name="Healthy")
        authoring.save_card(deck,"generic",GENERIC)
        p=self.presentation(deck)
        created=[]
        def enqueue():
            try:
                time.sleep(4)
                name=uuid.uuid4().hex+".audio"
                (audio_dir/name).write_bytes(audio_bytes())
                (audio_dir/(name+".wav")).write_bytes(audio_bytes())  # normalized derivative ready; conversion variant needs no ffmpeg here
                b=review.submit(p,"speak",1,name); created.append(b.pk)
            finally: connections.close_all()
        enqueuer=threading.Thread(target=enqueue)
        started=time.monotonic(); enqueuer.start()
        try:
            with patch.dict(os.environ,{"AUDIO_ASSESS_ENDPOINT":f"http://127.0.0.1:{server.server_port}/judge","AUDIO_ASSESS_API_KEY":"test-only", "ALLOW_INSECURE_PROVIDER_HTTP":"1",
                           "AUDIO_ASSESS_API_MODE":"chat_completions",
                           "PATH":str(audio_dir)+os.pathsep+os.environ["PATH"] if conversion else os.environ["PATH"]}),override_settings(AUDIO_DIR=audio_dir):
                run_worker(once=True,concurrency=1)
            enqueuer.join(timeout=2)
            self.assertEqual(Attempt.objects.get(pk=created[0]).state,"assessed")
            self.assertEqual(Attempt.objects.get(pk=a.pk).state,"failed")
            elapsed=time.monotonic()-started
            self.assertLess(elapsed,7, "The sole slot must recover in time for the one-second healthy job.")
            self.assertEqual(len(requests),1 if conversion else 2)
            if conversion:
                self.assertTrue(pidfile.exists())
                self.assertFalse(Path("/proc/"+pidfile.read_text()).exists(), "Conversion child must be killed and reaped.")
            print(f"WORKER-CAPACITY {'conversion' if conversion else 'provider'}: healthy completion at {elapsed:.3f}s; one slot, 5s deadline, 1s healthy job",flush=True)
        finally:
            stop.set(); server.shutdown(); server.server_close(); thread.join(timeout=2)

    def test_worker_recovers_actual_capacity_after_stalled_provider(self):
        self.capacity_scenario()

    def test_worker_kills_and_reaps_stalled_conversion_child(self):
        self.capacity_scenario(conversion=True)
