import io
import json
import random
import tempfile
import uuid
import wave
from itertools import product
from html.parser import HTMLParser
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from django.core.management import call_command, CommandError
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings, Client
from django.db import OperationalError
from django.urls import reverse
from django.utils import timezone
from learning import authoring, review, work
from learning.models import Deck, Card, Presentation, Attempt, ExamplePair, GenerationJob, ScoredReview
from learning.providers import StageError, PROMPT_VERSIONS
from learning.rendering import render, recall_budget

GENERIC = {"question": "What is two plus two?", "answer": "four", "explanation": "Two pairs make four."}
VOCAB = {"word": "misunderstanding", "explanation": "A problem caused by people understanding each other incorrectly.",
         "target_language": "English", "native_language": "Chinese"}
PAIR = {"target_sentence": "A small misunderstanding stopped the conversation.", "target_highlight": "misunderstanding",
        "native_sentence": "一个小小的误会打断了谈话。", "native_highlight": "误会"}


def audio_bytes():
    b = io.BytesIO()
    with wave.open(b, "wb") as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000); wav.writeframes(b"\0\0"*4000)
    return b.getvalue()


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class LearningTests(TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.override = override_settings(AUDIO_DIR=Path(self.folder.name))
        self.override.enable(); self.addCleanup(self.override.disable)
        self.user = get_user_model().objects.create_user("learner", password="test-password")
        self.other = get_user_model().objects.create_user("other", password="test-password")
        self.deck = Deck.objects.create(owner=self.user, name="Everyday ideas")
        self.client.force_login(self.user)

    def generic(self, **overrides):
        return authoring.save_card(self.deck, "generic", {**GENERIC, **overrides})

    def vocabulary(self, **overrides):
        return authoring.save_card(self.deck, "vocabulary", {**VOCAB, **overrides})

    def ready(self, card):
        job = card.generation_jobs.get(mode="initial")
        job.state = "processing"; job.started_at=timezone.now(); job.deadline=job.started_at+timedelta(seconds=300); job.save()
        work.save_pair(job.pk, job.claim, PAIR, {"model": "test"})
        card.refresh_from_db()
        return card

    def present(self, card=None):
        if card:
            Card.objects.filter(pk=card.pk).update(due=timezone.now()-timedelta(seconds=1),deferred_until=None)
        return review.next_question(self.user,self.deck)

    def spoken(self, p, duration=2):
        path = Path(self.folder.name)/(uuid.uuid4().hex+".audio")
        path.write_bytes(audio_bytes())
        a = review.submit(p, "speak", duration, path.name)
        a.state = "processing"; a.save(update_fields=["state"])
        return a

    def score(self, card, grade="E", duration=2):
        card.due = timezone.now()-timedelta(seconds=1); card.save(update_fields=["due"])
        p = self.present(card)
        a = self.spoken(p, duration)
        return review.commit_grade(a.pk, a.claim, grade, [], "Controlled application fixture.")

    def test_csv_duplicate_and_independent_atomic_rollback(self):
        """ENTRY-CSV-DEDUP / ENTRY-CSV-ROLLBACK: absent valid rows precede an invalid row."""
        content = Path("docs/examples/vocabulary-cards.csv").read_bytes()
        created, skipped = authoring.import_csv(self.deck, "vocabulary", b"\xef\xbb\xbf"+content)
        jobs = GenerationJob.objects.count()
        self.assertEqual((created, skipped), (3, 0))
        self.assertEqual(authoring.import_csv(self.deck, "vocabulary", content), (0, 3))
        self.assertEqual(GenerationJob.objects.count(), jobs)
        independent = Deck.objects.create(owner=self.user, name="Atomic")
        z = authoring.save_card(independent, "generic", GENERIC)
        bad = b"word,explanation,native_language,target_language\nnew-a,meaning,Chinese,English\nnew-b,meaning,Spanish,English\nbad,meaning,Spanish,Spanish\n"
        with self.assertRaisesMessage(ValidationError, "record 4"):
            authoring.import_csv(independent, "vocabulary", bad)
        self.assertEqual(list(independent.cards.values_list("pk", flat=True)), [z.pk])
        self.assertEqual(GenerationJob.objects.count(), jobs)

    def test_csv_multiline_schema_and_same_language_validation(self):
        csv = b'explanation,answer,question\n"**Bold**\n<u>note</u>",four,"Two plus two?"\n'
        self.assertEqual(authoring.import_csv(self.deck, "generic", csv), (1, 0))
        self.assertIn("\n", self.deck.cards.get().explanation)
        for invalid in [b"question,answer,answer\na,b,c", b"question,answer,explanation\na,b", b"invalid\xff"]:
            with self.assertRaises(ValidationError):
                authoring.import_csv(self.deck, "generic", invalid)
        with self.assertRaises(ValidationError):
            self.vocabulary(target_language="Spanish", native_language="Spanish")
        for target,native in authoring.LANGUAGE_PAIRS:
            self.vocabulary(word=target+native, target_language=target, native_language=native)
        self.assertEqual(Card.objects.filter(kind="vocabulary").count(), 3)

    def test_safe_markdown_exact_units_and_identity(self):
        text = Path("docs/specs/v1.md").read_text()
        fixture = text.split("F-MD is this exact",1)[1].split("~~~~markdown\n",1)[1].split("\n~~~~",1)[0]
        output = render(fixture, "alpha; beta", True)
        self.assertEqual(output.blanks, 2)
        class Blanks(HTMLParser):
            ids = []
            def handle_starttag(self, tag, attrs):
                a = dict(attrs)
                if tag == "span" and a.get("class") == "cloze-blank": self.ids.append(a["data-blank"])
        parser = Blanks(); parser.feed(output.html)
        self.assertEqual(parser.ids, ["1", "2"])
        self.assertNotIn('<span class="cloze-blank" data-blank="99">', output.html)
        for raw in ['<script>alert(1)</script>', '<u onclick="bad()">text</u>', '<img src=x onerror=bad()>', '[x](javascript:alert(1))']:
            html = render(raw).html
            self.assertNotIn("<script>", html); self.assertNotIn("<img", html); self.assertNotIn("<u ", html)
            self.assertNotIn('href="javascript:', html)
        a = render('A {{blank}}.', 'answer', True)
        b = render('A **{{blank}}**.', 'answer', True)
        self.assertEqual((a.identity,a.reading_count),(b.identity,b.reading_count))
        self.assertNotEqual(render('`same`').identity, render('same').identity)
        self.assertEqual(render('{{blank}}').blanks, 0)
        self.assertEqual(recall_budget(1, 17, 'four'), 12)

    def test_first_preparation_failure_keeps_source_out_of_queue(self):
        """PREP-INITIAL / GEN-UNSTARTED."""
        card = self.vocabulary(); job = card.generation_jobs.get()
        self.assertFalse(card.ready); self.assertFalse(review.available(self.user).exists())
        self.assertIsNone(job.started_at);self.assertIsNone(job.deadline)
        later=timezone.now()+timedelta(days=1)
        with patch("learning.work.timezone.now",return_value=later):
            response=self.client.get(reverse("card",args=[card.pk]))
            job.refresh_from_db();self.assertEqual(job.state,"queued")
            self.assertContains(response,"Queued")
            claimed=work.claim_work()
        job.refresh_from_db()
        self.assertEqual(claimed,("generation",job.pk,job.claim,later+timedelta(seconds=300)))
        self.assertEqual(job.started_at,later)
        with patch("learning.work.timezone.now",return_value=job.deadline):
            self.client.get(reverse("card", args=[card.pk]))
        job.refresh_from_db(); self.assertEqual(job.state,"failed")
        self.assertNotEqual(job.claim,claimed[2])
        retried = work.retry_generation(job)
        self.assertEqual(retried.execution,2)
        self.assertIsNone(retried.started_at);self.assertIsNone(retried.deadline)
        self.assertEqual(Card.objects.count(),1)
        self.ready(card)
        self.assertEqual(review.available(self.user).count(),1)

    def test_bulk_generation_waits_for_capacity_without_spending_execution_budget(self):
        content="word,explanation,native_language,target_language\n"+"".join(
            f"word-{i},One intended meaning.,Chinese,English\n" for i in range(1201))
        self.assertEqual(authoring.import_csv(self.deck,"vocabulary",content.encode()),(1201,0))
        now=timezone.now()+timedelta(hours=2)
        with patch("learning.work.timezone.now",return_value=now):
            work.expire_generations()
            self.assertEqual(GenerationJob.objects.filter(state="queued",deadline__isnull=True).count(),1201)
            receipts=[work.claim_work(),work.claim_work()]
        self.assertEqual(GenerationJob.objects.filter(state="queued").count(),1199)
        self.assertEqual(GenerationJob.objects.filter(state="processing",started_at=now).count(),2)
        for receipt in receipts:self.assertEqual(receipt[3],now+timedelta(seconds=300))
        with patch("learning.work.timezone.now",return_value=now+timedelta(seconds=299)):
            self.assertIsNotNone(work.save_pair(receipts[0][1],receipts[0][2],PAIR,{}))
        with patch("learning.work.timezone.now",return_value=now+timedelta(seconds=301)):
            work.expire_generations()
            self.assertIsNone(work.save_pair(receipts[1][1],receipts[1][2],PAIR,{}))
            next_job=work.claim_work()
        self.assertEqual(GenerationJob.objects.filter(state="failed").count(),1)
        self.assertEqual(Card.objects.filter(ready=True).count(),1)
        self.assertEqual(next_job[3],now+timedelta(seconds=601))
        self.assertEqual(GenerationJob.objects.filter(state="queued",deadline__isnull=True).count(),1198)

    def test_assessment_keeps_submission_deadline_and_queue_priority(self):
        self.vocabulary()
        self.generic();a=review.submit(self.present(),"speak",1,"unused")
        deadline=a.deadline
        with patch("learning.work.timezone.now",return_value=a.submitted_at+timedelta(seconds=100)):
            receipt=work.claim_work()
        self.assertEqual(receipt,("assessment",a.pk,a.claim,deadline))
        self.assertEqual(GenerationJob.objects.get().state,"queued")
        self.assertEqual(deadline,a.submitted_at+timedelta(seconds=300))

    def test_explicit_preparation_requeue_is_scoped_and_idempotent(self):
        def failed(card):
            job=card.generation_jobs.get()
            job.state="failed";job.error_category="timeout";job.provenance={"model":"previous-dispatch"};job.save()
            return job
        first=failed(self.vocabulary())
        duplicate=failed(self.vocabulary(word="duplicate"))
        newest=authoring.new_generation(duplicate.card);newest.state="failed";newest.save()
        busy=failed(self.vocabulary(word="already-waiting"));authoring.new_generation(busy.card)
        changed=self.vocabulary(word="revised");old=failed(changed)
        authoring.save_card(self.deck,"vocabulary",{**VOCAB,"word":"revised","explanation":"A new sense."},changed)
        archived=failed(self.vocabulary(word="archived"));Card.objects.filter(pk=archived.card_id).update(archived=True)
        foreign_deck=Deck.objects.create(owner=self.other,name="Private")
        foreign=failed(authoring.save_card(foreign_deck,"vocabulary",VOCAB))
        ready=self.ready(self.vocabulary(word="ready"));self.score(ready,"E")
        before_cards=list(Card.objects.order_by("pk").values())
        before_reviews=list(ScoredReview.objects.values())
        output=io.StringIO()
        with patch("learning.providers.generate") as provider:
            call_command("requeue_preparation",self.user.username,dry_run=True,stdout=output)
            self.assertIn("Eligible failed initial tasks: 2",output.getvalue())
            first.refresh_from_db();self.assertEqual(first.state,"failed")
            call_command("requeue_preparation",self.user.username,stdout=output)
            provider.assert_not_called()
        for job in [first,newest]:
            job.refresh_from_db();self.assertEqual(job.state,"queued")
            self.assertEqual(job.execution,2);self.assertIsNone(job.started_at);self.assertIsNone(job.deadline)
            self.assertEqual(job.provenance,{})
        for job in [duplicate,busy,archived,foreign]:
            job.refresh_from_db();self.assertEqual(job.state,"failed")
        old.refresh_from_db();self.assertEqual(old.state,"cancelled")
        output=io.StringIO();call_command("requeue_preparation",self.user.username,stdout=output)
        self.assertIn("Requeued 0 tasks",output.getvalue())
        self.assertEqual(list(Card.objects.order_by("pk").values()),before_cards)
        self.assertEqual(list(ScoredReview.objects.values()),before_reviews)
        with self.assertRaises(CommandError):call_command("requeue_preparation","missing-user",stdout=output)

    def test_cancelled_generation_does_not_dispatch_or_commit(self):
        card=self.vocabulary();receipt=work.claim_work()
        from learning.providers import Profile
        def cancel(*args):
            authoring.archive_card(card,True)
            return Profile("GENERATOR","https://provider.test","selected","placeholder-only",120)
        with patch("learning.work.bounded_profile",side_effect=cancel),patch("learning.providers.generate") as generate:
            work.process_generation(receipt[1],receipt[2])
        generate.assert_not_called()
        self.assertIsNone(work.save_pair(receipt[1],receipt[2],PAIR,{}))
        self.assertFalse(ExamplePair.objects.exists())

    def test_generation_retry_waits_then_starts_a_fresh_execution(self):
        card=self.vocabulary();receipt=work.claim_work();job=card.generation_jobs.get()
        GenerationJob.objects.filter(pk=job.pk).update(provenance={"model":"old"})
        with patch("learning.work.timezone.now",return_value=job.deadline):
            job=work.retry_generation(job)
        self.assertEqual(job.state,"queued")
        self.assertIsNone(job.started_at);self.assertIsNone(job.deadline);self.assertEqual(job.provenance,{})
        later=timezone.now()+timedelta(days=2)
        with patch("learning.work.timezone.now",return_value=later):
            fresh=work.claim_work()
        self.assertEqual(fresh[3],later+timedelta(seconds=300))
        self.assertNotEqual(receipt[2],fresh[2])
        self.assertIsNone(work.save_pair(receipt[1],receipt[2],PAIR,{}))
        with patch("learning.work.timezone.now",return_value=later+timedelta(seconds=1)):
            self.assertIsNotNone(work.save_pair(fresh[1],fresh[2],PAIR,{}))

    def test_generation_claim_crash_replay_and_old_source(self):
        """GEN-CLAIMED / GEN-COMMITTED / GEN-STALE."""
        card = self.vocabulary(); work.claim_work();job=card.generation_jobs.get();old=job.claim
        job.deadline=timezone.now()-timedelta(seconds=1); job.save()
        job=work.retry_generation(job);work.claim_work();job.refresh_from_db()
        self.assertIsNone(work.save_pair(job.pk,old,PAIR,{}))
        pair=work.save_pair(job.pk,job.claim,PAIR,{})
        self.assertEqual(work.save_pair(job.pk,job.claim,PAIR,{}).pk,pair.pk)
        self.assertEqual(ExamplePair.objects.count(),1)
        card=authoring.save_card(self.deck,"vocabulary",{**VOCAB,"explanation":"Another intended meaning."},card)
        self.assertFalse(card.ready)
        self.assertEqual(work.save_pair(job.pk,old,PAIR,{}).pk,pair.pk)
        card.refresh_from_db(); self.assertFalse(card.ready); self.assertIsNone(card.active_pair_id)

    def test_actions_are_unique_and_voice_is_required(self):
        """FLOW-ACTIONS / GENERIC-WHOLE / EXIT-ACK."""
        card=self.generic(); p=self.present(card)
        self.assertEqual(p.snapshot["units"],1)
        a=review.submit(p,"skip")
        self.assertEqual(review.submit(p,"forgot").pk,a.pk)
        self.assertEqual(ScoredReview.objects.count(),0)
        card.refresh_from_db(); self.assertEqual(card.collection,"Normal")
        p=self.present(card); result=self.client.post(reverse("action",args=[p.pk]),{"action":"speak","transcript":"four","duration":"1"})
        self.assertEqual(result.status_code,400)
        self.assertFalse(Attempt.objects.filter(presentation=p).exists())
        a=review.submit(p,"forgot")
        self.assertEqual((a.grade,a.state),("A","assessed"))
        self.assertEqual(review.exit_attempt(a).grade,"A")

    def test_front_does_not_leak_reference_or_hidden_pair(self):
        card=self.ready(self.vocabulary())
        card.direction_block=["production","recognition"]; card.save()
        p=self.present(card)
        response=self.client.get(reverse("presentation",args=[p.pk]))
        self.assertNotContains(response,"misunderstanding")
        self.assertNotContains(response,PAIR["target_sentence"])
        a=review.submit(p,"skip")
        response=self.client.get(reverse("status",args=[p.pk]))
        self.assertIn("misunderstanding",response.json()["back_html"])
        self.assertEqual(a.presentation.snapshot["language"],"English")

    def test_vocabulary_back_uses_authored_target_and_explanation_for_legacy_and_new_reviews(self):
        card=self.ready(self.vocabulary())
        card.direction_block=["recognition","production"];card.save()
        p=self.present(card)
        self.assertEqual(p.snapshot["reference"],card.word)
        self.assertNotIn("gloss",p.snapshot)
        self.assertEqual(p.budget,recall_budget(1,p.snapshot["reading_count"],PAIR["native_highlight"]))
        # Display old frozen reviews consistently without rewriting their historical input.
        p.snapshot.update(reference="A legacy generated native definition",gloss="A legacy generated native definition")
        p.save(update_fields=["snapshot"])
        review.submit(p,"skip")
        html=self.client.get(reverse("status",args=[p.pk])).json()["back_html"]
        self.assertIn('<h2 class="answer">misunderstanding</h2>',html)
        self.assertIn(card.explanation,html)
        self.assertNotIn("A legacy generated native definition",html)
        p.refresh_from_db();self.assertEqual(p.snapshot["gloss"],"A legacy generated native definition")

    def test_example_correction_preserves_held_question_then_replaces_retained_cue(self):
        card=self.ready(self.vocabulary());self.score(card,"E");card.refresh_from_db()
        p=self.present(card);card.refresh_from_db()
        frozen=p.snapshot.copy()
        before={key:getattr(card,key) for key in ["fsrs","due","deferred_until","collection","streak",
            "review_count","source_version","progress_version","direction_block","direction_index","cue_direction"]}
        job=card.generation_jobs.get(mode="rotation",state="queued")
        job.state="processing";job.started_at=timezone.now();job.deadline=job.started_at+timedelta(seconds=300);job.save()
        pair=work.save_corrected_pair(card.pk,card.source_version,card.active_pair_id,
            {**PAIR,"native_sentence":"那次误会很小。"},{"prompt_version":PROMPT_VERSIONS["GENERATOR"]})
        card.refresh_from_db()
        self.assertEqual({key:getattr(card,key) for key in before},before)
        self.assertEqual(card.active_pair_id,pair.pk)
        self.assertEqual(card.cue_pair_id,frozen["pair_id"])
        self.assertTrue(review.valid_presentation(p))
        self.assertEqual(review.next_question(self.user,self.deck).pk,p.pk)
        self.assertIsNone(work.save_pair(job.pk,job.claim,PAIR,{}))
        job.refresh_from_db();self.assertEqual(job.state,"cancelled")
        self.assertIsNone(card.rotation_token)
        self.assertEqual(ScoredReview.objects.count(),1)
        pair=work.save_corrected_pair(card.pk,card.source_version,pair.pk,
            {**PAIR,"native_sentence":"他们有个误会。"},{"prompt_version":PROMPT_VERSIONS["GENERATOR"]})
        review.submit(p,"skip")
        p.refresh_from_db();self.assertEqual(p.snapshot,frozen)
        with patch("learning.review.timezone.now",return_value=timezone.now()+timedelta(minutes=31)):
            fresh=self.present()
        self.assertEqual(fresh.snapshot["pair_id"],pair.pk)
        self.assertEqual(fresh.snapshot["direction"],frozen["direction"])
        self.assertEqual(card.pairs.count(),3)

    def test_example_correction_is_source_fenced_and_keeps_submissions_in_other_scopes(self):
        card=self.ready(self.vocabulary());p=review.next_question(self.user)
        a=self.spoken(p);frozen=p.snapshot.copy()
        card.refresh_from_db();old_pair=card.active_pair_id
        pair=work.save_corrected_pair(card.pk,card.source_version,old_pair,PAIR,{})
        self.assertIsNotNone(pair)
        self.assertIsNone(work.save_corrected_pair(card.pk,card.source_version,old_pair,PAIR,{}))
        self.assertIsNone(work.save_corrected_pair(card.pk,card.source_version+1,pair.pk,PAIR,{}))
        card.refresh_from_db();self.assertEqual(card.cue_pair_id,old_pair)
        a.refresh_from_db();self.assertEqual(a.state,"processing")
        self.assertTrue(review.valid_presentation(p))
        result=review.commit_grade(a.pk,a.claim,"D",[],"Still assess the frozen question.")
        self.assertEqual(result.state,"assessed")
        self.assertEqual(ScoredReview.objects.get().snapshot,frozen)
        next_p=self.present(card);self.assertEqual(next_p.snapshot["pair_id"],pair.pk)

    def test_refresh_command_scopes_ready_cards_and_retries_only_remaining_failures(self):
        ready=self.ready(self.vocabulary())
        second=self.ready(self.vocabulary(word="another"))
        self.vocabulary(word="not-ready")
        foreign_deck=Deck.objects.create(owner=self.other,name="Private")
        foreign=self.ready(authoring.save_card(foreign_deck,"vocabulary",VOCAB))
        output=io.StringIO()
        with patch("learning.providers.generate") as generate:
            call_command("refresh_examples",self.user.username,dry_run=True,stdout=output)
        generate.assert_not_called()
        self.assertIn("Examples needing correction: 2",output.getvalue())

        def generate(source,profile):
            if source["word"]=="another":raise StageError("GENERATOR","Temporary provider failure")
            return PAIR,{"prompt_version":PROMPT_VERSIONS["GENERATOR"]}
        with patch("learning.providers.profile"),patch("learning.providers.generate",side_effect=generate):
            with self.assertRaises(CommandError):
                call_command("refresh_examples",self.user.username,stdout=output,stderr=io.StringIO())
        ready.refresh_from_db();second.refresh_from_db();foreign.refresh_from_db()
        self.assertEqual(ready.pairs.count(),2)
        self.assertEqual(second.pairs.count(),1)
        self.assertEqual(foreign.pairs.count(),1)
        with patch("learning.providers.profile"),patch("learning.providers.generate",
                return_value=(PAIR,{"prompt_version":PROMPT_VERSIONS["GENERATOR"]})) as generate:
            call_command("refresh_examples",self.user.username,stdout=output)
        self.assertEqual(generate.call_count,1)
        second.refresh_from_db();self.assertEqual(second.pairs.count(),2)
        with patch("learning.providers.profile") as profile:
            call_command("refresh_examples",self.user.username,stdout=output)
        profile.assert_not_called()

    def test_judgment_precedence_and_time_boundary(self):
        """GENERIC-MULTI / VOCAB-GRADING / UNIT-IDENTITY / CLOCK-BOUNDARY."""
        for duration, expected in [(11.99,"E"),(12,"E"),(12.01,"D")]:
            self.assertEqual(review.grade_units([{"outcome":"complete"}],duration,12),expected)
        for duration in [2,60]:
            self.assertEqual(review.grade_units([{"outcome":"partial"},{"outcome":"complete"}],duration,12),"C")
            self.assertEqual(review.grade_units([{"outcome":"partial"},{"outcome":"incorrect"}],duration,12),"B")
        self.generic(question="I had to **{{blank}}** because I was <u>{{blank}}</u>.",answer="call off; feeling unwell")
        p=self.present(); self.assertEqual(p.snapshot["units"],2)
        a=self.spoken(p); before=Card.objects.get(pk=p.card_id).fsrs
        with patch("learning.providers.transcribe",return_value=("cancel, feeling unwell",{})),patch("learning.providers.assess",side_effect=StageError("JUDGE","Missing unit")):
            try: work.process_assessment(a.pk,a.claim)
            except StageError as e: work.fail("assessment",a.pk,a.claim,e)
        a.refresh_from_db(); self.assertEqual(a.state,"failed"); self.assertEqual(a.transcript,"cancel, feeling unwell")
        self.assertEqual(Card.objects.get(pk=p.card_id).fsrs,before)

    def test_pipeline_normalizes_reuses_transcript_and_cleans_on_commit(self):
        """AUDIO-NORMALIZE / AUDIO-COMMIT / RESTORE-TRANSCRIPT."""
        self.generic(); a=self.spoken(self.present())
        units=[{"id":1,"outcome":"complete","reason":"The reference content was recalled."}]
        with patch("learning.providers.transcribe",return_value=("four",{"model":"fake-asr"})) as asr,patch("learning.providers.assess",side_effect=StageError("JUDGE","Temporary failure")):
            with self.assertRaises(StageError): work.process_assessment(a.pk,a.claim)
        a.refresh_from_db(); self.assertEqual(a.transcript,"four")
        self.assertTrue((Path(self.folder.name)/a.audio_name).exists())
        with wave.open(str(Path(self.folder.name)/(a.audio_name+".wav")),"rb") as normalized:
            self.assertEqual((normalized.getnchannels(),normalized.getframerate(),normalized.getsampwidth()),(1,16000,2))
        work.fail("assessment",a.pk,a.claim,StageError("JUDGE","Temporary"))
        a=review.retry_attempt(a); a.state="processing"; a.save()
        with patch("learning.providers.transcribe") as asr,patch("learning.providers.assess",return_value=(units,{"model":"fake-judge"})):
            work.process_assessment(a.pk,a.claim)
            asr.assert_not_called()
        a.refresh_from_db(); self.assertEqual((a.state,a.grade),("assessed","E"))
        self.assertFalse((Path(self.folder.name)/a.audio_name).exists())
        self.assertEqual(ScoredReview.objects.count(),1)

    def test_exit_first_and_grade_first_are_atomic_terminal_winners(self):
        """EXIT-FIRST / GRADE-FIRST / RESTORE-COMMITTED."""
        card=self.generic(); a=self.spoken(self.present()); old=a.claim
        exited=review.exit_attempt(a)
        self.assertEqual(review.commit_grade(a.pk,old,"E",[],"late").state,"closed_unassessed")
        self.assertEqual(review.retry_attempt(exited).state,"closed_unassessed")
        self.assertFalse(ScoredReview.objects.exists())
        a=self.score(card)
        self.assertEqual(review.exit_attempt(a).grade,"E")
        self.assertEqual(review.commit_grade(a.pk,a.claim,"B",[],"duplicate").grade,"E")
        self.assertEqual(ScoredReview.objects.count(),1)

    def test_unconfirmed_upload_can_close_before_a_late_submission(self):
        self.generic();p=self.present()
        response=self.client.post(reverse("attempt_exit",args=[p.pk]))
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()["state"],"closed_unassessed")
        late=review.submit(p,"speak",2,"late.audio")
        self.assertEqual(late.state,"closed_unassessed")
        self.assertFalse(ScoredReview.objects.exists())
        self.assertEqual(Attempt.objects.count(),1)

    def test_never_started_and_expired_execution_fencing(self):
        """NEVER-STARTED / EXPIRED-EXECUTION / AUDIO-TTL."""
        self.generic(); p=self.present(); a=review.submit(p,"speak",2,"missing.audio"); old=a.claim
        a.deadline=timezone.now()-timedelta(seconds=1); a.save()
        self.client.get(reverse("status",args=[p.pk])); a.refresh_from_db()
        self.assertEqual(a.state,"failed")
        self.assertNotEqual(a.claim,old)
        expiry=a.audio_expires_at; submitted=a.submitted_at
        (Path(self.folder.name)/a.audio_name).write_bytes(audio_bytes())
        a=review.retry_attempt(a)
        self.assertEqual((a.audio_expires_at,a.submitted_at),(expiry,submitted))
        self.assertEqual(review.commit_grade(a.pk,old,"E",[],"late").grade,"")
        a.state="failed"; a.audio_expires_at=timezone.now()-timedelta(seconds=1); a.save()
        self.assertEqual(review.retry_attempt(a).state,"failed")
        a.transcript="four"; a.save()
        self.assertEqual(review.retry_attempt(a).state,"submitted")

    def test_distinct_attempts_and_source_edit_fence(self):
        """TWO-ATTEMPTS / SOURCE-EDIT."""
        card=self.generic(); p1=self.present(); p2=review.next_question(self.user)
        a1=self.spoken(p1); a2=self.spoken(p2)
        review.commit_grade(a2.pk,a2.claim,"E",[],"winner")
        self.assertEqual(review.commit_grade(a1.pk,a1.claim,"E",[],"late").state,"closed_unassessed")
        self.assertEqual(ScoredReview.objects.count(),1)
        card.due=timezone.now()-timedelta(seconds=1); card.save(update_fields=["due"])
        p=self.present(); a=self.spoken(p)
        card=authoring.save_card(self.deck,"generic",{**GENERIC,"question":"Two plus three?","answer":"five"},card)
        review.commit_grade(a.pk,a.claim,"E",[],"old source")
        card.refresh_from_db(); self.assertEqual(card.fsrs,{})
        self.assertEqual(ScoredReview.objects.count(),1)

    def test_pipeline_closes_stale_attempt_before_more_paid_work(self):
        self.generic(); first=self.spoken(self.present()); second=self.spoken(review.next_question(self.user))
        review.commit_grade(first.pk,first.claim,"E",[],"First committed")
        with patch("learning.providers.transcribe") as asr,patch("learning.providers.assess") as judge:
            work.process_assessment(second.pk,second.claim)
        second.refresh_from_db()
        self.assertEqual(second.state,"closed_unassessed")
        asr.assert_not_called();judge.assert_not_called()
        self.assertEqual(ScoredReview.objects.count(),1)

    def test_profile_dispatch_snapshot_retry_and_cached_asr_provenance(self):
        import os
        self.generic();a=self.spoken(self.present());a.transcript="four";a.asr_provenance={"model":"original-asr"};a.save()
        seen=[]
        def interrupted(profile,*args):
            seen.append(profile.model)
            os.environ["JUDGE_MODEL"]="judge-next"
            raise StageError("JUDGE","Controlled interruption","transport")
        with patch.dict(os.environ,{"JUDGE_MODEL":"judge-dispatched","MINIMAX_API_KEY":"placeholder-only"}),patch("learning.providers.chat",side_effect=interrupted):
            with self.assertRaises(StageError):work.process_assessment(a.pk,a.claim)
        a.refresh_from_db();self.assertEqual(a.judge_provenance["model"],"judge-dispatched")
        self.assertEqual(seen,["judge-dispatched"])
        work.fail("assessment",a.pk,a.claim,StageError("JUDGE","Temporary","transport"))
        a=review.retry_attempt(a);a.state="processing";a.save()
        units={"units":[{"id":1,"outcome":"complete","reason":"Complete fixture"}]}
        with patch.dict(os.environ,{"JUDGE_MODEL":"judge-retry","MINIMAX_API_KEY":"placeholder-only"}),patch("learning.providers.chat",return_value=units),patch("learning.providers.transcribe") as asr:
            work.process_assessment(a.pk,a.claim)
        a.refresh_from_db();self.assertEqual(a.judge_provenance["model"],"judge-retry")
        self.assertEqual(a.asr_provenance,{"model":"original-asr"});asr.assert_not_called()

    def test_forgot_timeline_and_preserved_scheduler_memory(self):
        """SRS-TIMELINE / DELAY-ANCHOR / NEXT-REVIEW."""
        card=self.generic(); a=self.score(card,"B")
        card.refresh_from_db(); self.assertEqual((card.collection,card.streak),("Forgot",0))
        self.assertEqual(card.due,a.submitted_at+timedelta(minutes=1))
        with patch("learning.review.random.randint") as jitter:
            for streak,grade in [(1,"D"),(2,"E"),(3,"D")]:
                a=self.score(card,grade); card.refresh_from_db()
                self.assertEqual(card.streak,streak)
                self.assertTrue(card.fsrs["stability"]>0)
                if streak<3: self.assertEqual(card.due,a.submitted_at+timedelta(days=1))
            jitter.assert_not_called()
        self.assertEqual(card.collection,"Normal")
        self.score(card,"C"); card.refresh_from_db(); self.assertEqual(card.collection,"Normal")
        self.score(card,"B"); self.score(card,"E"); self.score(card,"C"); card.refresh_from_db()
        self.assertEqual((card.collection,card.streak),("Forgot",0))
        self.assertEqual(review.relative_due(timezone.now()-timedelta(seconds=1)),"Due now")

    def test_learning_d_uses_one_to_three_days_and_preserves_memory_and_replay(self):
        from fsrs import Card as MemoryCard,Rating,Scheduler,State
        for days in [1,2,3]:
            card=self.ready(self.vocabulary()) if days==2 else self.generic(question=f"First D fixture {days}?")
            with patch("learning.review.Scheduler",return_value=Scheduler(enable_fuzzing=False)),patch(
                    "learning.review.random.randint",return_value=days) as jitter:
                a=self.score(card,"D",duration=90)
                replay=review.commit_grade(a.pk,a.claim,"D",[],"Duplicate receipt")
                jitter.assert_called_once_with(1,3)
            card.refresh_from_db();event=ScoredReview.objects.get(attempt=a)
            expected,log=Scheduler(enable_fuzzing=False).review_card(
                MemoryCard(card_id=card.pk,due=a.submitted_at),Rating.Good,review_datetime=a.submitted_at)
            self.assertEqual(expected.due,a.submitted_at+timedelta(minutes=10))
            expected.due=a.submitted_at+timedelta(days=days)
            self.assertEqual(card.fsrs,json.loads(expected.to_json()))
            self.assertEqual(event.fsrs_log,json.loads(log.to_json()))
            self.assertEqual((card.due,a.next_due,event.next_due,replay.next_due),(expected.due,)*4)
            self.assertEqual((card.collection,card.review_count,card.progress_version),("Normal",1,1))
            self.assertEqual((card.fsrs["state"],card.fsrs["step"]),(State.Learning.value,1))
            self.assertEqual(ScoredReview.objects.filter(card=card).count(),1)

    def test_learning_d_after_c_changes_only_d_and_keeps_e_history_adaptive(self):
        from fsrs import Scheduler
        for grade,expected_days in [("D",2),("E",1)]:
            card=self.generic(question=f"Partial then {grade} fixture?")
            with patch("learning.review.Scheduler",return_value=Scheduler(enable_fuzzing=False)):
                first=self.score(card,"C")
                self.assertEqual(first.next_due,first.submitted_at+timedelta(minutes=1))
                with patch("learning.review.timezone.now",return_value=first.next_due),patch(
                        "learning.review.random.randint",return_value=2) as jitter:
                    result=self.score(card,grade,duration=90 if grade=="D" else 2)
                self.assertEqual(jitter.call_count,1 if grade=="D" else 0)
            self.assertEqual(result.next_due,result.submitted_at+timedelta(days=expected_days))
            first.refresh_from_db()
            self.assertEqual(first.next_due,first.submitted_at+timedelta(minutes=1))

    def test_mature_d_and_all_e_keep_native_fsrs_schedule(self):
        from datetime import datetime,timezone as tz
        from fsrs import Card as MemoryCard,Rating,Scheduler
        anchor=datetime(2030,1,20,12,tzinfo=tz.utc)
        for mature,grade in [(False,"E"),(True,"D"),(True,"E")]:
            card=self.generic(question=f"Native FSRS {mature}/{grade} fixture?")
            with patch("learning.review.Scheduler",return_value=Scheduler(enable_fuzzing=False)):
                if mature:
                    with patch("learning.review.timezone.now",return_value=anchor-timedelta(days=10)):
                        self.score(card,"E")
                    card.refresh_from_db();memory=MemoryCard.from_dict(card.fsrs)
                else:memory=MemoryCard(card_id=card.pk,due=anchor)
                expected,_=Scheduler(enable_fuzzing=False).review_card(memory,
                    Rating.Good if grade=="D" else Rating.Easy,review_datetime=anchor)
                with patch("learning.review.timezone.now",return_value=anchor),patch("learning.review.random.randint") as jitter:
                    result=self.score(card,grade,duration=90 if grade=="D" else 2)
                jitter.assert_not_called()
            card.refresh_from_db()
            self.assertEqual(result.next_due,expected.due)
            self.assertEqual(card.fsrs,json.loads(expected.to_json()))
            if mature:self.assertGreater(result.next_due-anchor,timedelta(days=3))
            else:self.assertEqual(result.next_due-anchor,timedelta(days=8))

    def test_actual_due_clock_all_eight_graduation_routes(self):
        from datetime import datetime, timezone as tz
        start=datetime(2030,1,1,12,tzinfo=tz.utc)
        for route in product("DE",repeat=3):
            card=self.generic(question="What is two plus two? Timeline fixture "+"".join(route))
            clock=start
            for index,grade in enumerate(["B",*route]):
                with patch("learning.review.timezone.now",return_value=clock):
                    p=self.present()
                    self.assertEqual(p.card_id,card.pk)
                    a=self.spoken(p)
                    result=review.commit_grade(a.pk,a.claim,grade,[],"Controlled timeline outcome")
                card.refresh_from_db()
                self.assertEqual(card.fsrs["last_review"],clock.isoformat())
                if index<3:
                    self.assertEqual(card.due,clock+(timedelta(minutes=1) if index==0 else timedelta(days=1)))
                else:
                    self.assertEqual(card.collection,"Normal")
                    self.assertEqual(card.streak,3)
                    self.assertEqual(card.fsrs["state"],2)
                clock=card.due

    def test_language_pairs_directions_and_actions_are_separate_dimensions(self):
        for target,native in authoring.LANGUAGE_PAIRS:
            for direction,action in product(["recognition","production"],["skip","forgot","speak"]):
                with self.subTest(target=target,native=native,direction=direction,action=action):
                    deck=Deck.objects.create(owner=self.user,name=f"{target}/{native}/{direction}/{action}")
                    card=authoring.save_card(deck,"vocabulary",{**VOCAB,"target_language":target,"native_language":native,
                        "word":"misunderstanding" if target=="English" else "malentendido"})
                    job=card.generation_jobs.get();job.state="processing";job.started_at=timezone.now();job.deadline=job.started_at+timedelta(seconds=300);job.save()
                    data={**PAIR}
                    if target=="Spanish": data.update(target_sentence="Un malentendido interrumpió la conversación.",target_highlight="malentendido")
                    if native=="Spanish": data.update(native_sentence="Un malentendido interrumpió la conversación.",native_highlight="malentendido")
                    work.save_pair(job.pk,job.claim,data,{"fixture":"controlled pair"});card.refresh_from_db()
                    card.direction_block=[direction,"production" if direction=="recognition" else "recognition"];card.save()
                    p=review.next_question(self.user,deck)
                    self.assertEqual(p.snapshot["language"],native if direction=="recognition" else target)
                    self.assertEqual(p.snapshot["direction"],direction)
                    if action=="speak":
                        a=self.spoken(p);a=review.commit_grade(a.pk,a.claim,"E",[],"Complete controlled fixture")
                    else:a=review.submit(p,action)
                    card.refresh_from_db()
                    self.assertEqual(card.direction_index,0 if action=="skip" else 1)
                    self.assertEqual(a.grade,"" if action=="skip" else "A" if action=="forgot" else "E")

    def test_short_sentence_and_invalid_audio_remain_whole_tasks(self):
        card=self.generic(question="Why did you postpone the meeting?",answer="To give everyone more time to prepare.")
        p=self.present();self.assertEqual(p.snapshot["units"],1)
        a=self.spoken(p)
        with patch("learning.providers.transcribe",return_value=(card.answer,{})),patch("learning.providers.assess",return_value=([{"id":1,"outcome":"complete","reason":"Complete sentence"}],{})):
            work.process_assessment(a.pk,a.claim)
        a.refresh_from_db();self.assertEqual(a.grade,"E")
        path=Path(self.folder.name)/"invalid.audio";path.write_bytes(b"This is not an audio file")
        with self.assertRaises(StageError): work.normalize(path,timezone.now()+timedelta(seconds=10))
        for seconds in [500,501]:
            sample=Path(self.folder.name)/f"duration-{seconds}.audio"
            with wave.open(str(sample),"wb") as wav:
                wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(1000);wav.writeframes(b"\0\0"*(1000*seconds))
            if seconds==500:
                output=work.normalize(sample,timezone.now()+timedelta(seconds=20))
                with wave.open(str(output),"rb") as wav:self.assertEqual(wav.getnframes()/wav.getframerate(),500)
            else:
                with self.assertRaises(StageError):work.normalize(sample,timezone.now()+timedelta(seconds=20))
        path.write_bytes(b"")
        with path.open("wb") as output: output.truncate(50*1024*1024+1)
        with self.assertRaises(StageError): work.normalize(path,timezone.now()+timedelta(seconds=10))

    def test_skip_defers_for_thirty_minutes_without_changing_learning_progress(self):
        from datetime import datetime, timezone as tz
        start=datetime(2030,1,1,12,tzinfo=tz.utc)
        with patch("learning.review.timezone.now",return_value=start):
            card=self.ready(self.vocabulary())
            p=self.present()
            before=(card.due,card.fsrs,card.progress_version,card.collection,card.streak,card.direction_index)
            result=review.submit(p,"skip")
            card.refresh_from_db()
            self.assertEqual(card.deferred_until,start+timedelta(minutes=30))
            self.assertEqual((card.due,card.fsrs,card.progress_version,card.collection,card.streak,card.direction_index),before)
            self.assertIsNone(review.next_question(self.user,self.deck))
            self.assertIsNone(review.next_question(self.user))
            self.assertEqual(review.submit(p,"forgot").pk,result.pk)
            self.assertEqual(ScoredReview.objects.count(),0)
            self.client.force_login(self.user)
            response=self.client.get(reverse("status",args=[p.pk]))
            self.assertIn("30 minutes",response.json()["back_html"])
        with patch("learning.review.timezone.now",return_value=start+timedelta(minutes=29,seconds=59)):
            self.assertFalse(review.queue(self.user,self.deck).exists())
        with patch("learning.review.timezone.now",return_value=start+timedelta(minutes=30)):
            next_p=review.next_question(self.user,self.deck)
            self.assertNotEqual(next_p.pk,p.pk)
            self.assertEqual((next_p.card_id,next_p.snapshot["direction"],next_p.snapshot["pair_id"]),
                (p.card_id,p.snapshot["direction"],p.snapshot["pair_id"]))
            card.refresh_from_db()
            self.assertEqual(card.deferred_until,start+timedelta(minutes=30))

    def test_new_cards_are_random_and_only_displayed_question_is_fixed(self):
        state=random.getstate();self.addCleanup(random.setstate,state);random.seed(17)
        cards=[self.generic(question=f"Imported card {index}") for index in range(12)]
        imported=[card.pk for card in cards]
        before=list(self.deck.cards.values("pk","due","fsrs","review_count","progress_version"))
        orders=[list(review.queue(self.user,self.deck).values_list("pk",flat=True)) for _ in range(3)]
        for order in orders:self.assertCountEqual(order,imported)
        self.assertNotEqual(orders[0],orders[1])
        self.assertNotEqual(orders[0],imported)
        p=self.present()
        for _ in range(3):self.assertEqual(self.present().pk,p.pk)
        self.assertEqual(list(self.deck.cards.values("pk","due","fsrs","review_count","progress_version")),before)

    def test_queue_preserves_review_due_order_and_candidate_scope(self):
        now=timezone.now()
        forgot=[self.generic(question=f"Forgot {index}") for index in range(3)]
        reviewed=[self.generic(question=f"Reviewed {index}") for index in range(3)]
        for cards,collection in [(forgot,"Forgot"),(reviewed,"Normal")]:
            for card,minutes in zip(cards,[1,2,2]):
                Card.objects.filter(pk=card.pk).update(collection=collection,review_count=1,due=now-timedelta(minutes=minutes))
        unseen=[self.generic(question=f"New {index}") for index in range(5)]
        future=self.generic(question="Future Normal")
        future_forgot=self.generic(question="Future Forgot")
        paused=self.generic(question="Paused card")
        Card.objects.filter(pk__in=[future.pk,future_forgot.pk]).update(due=now+timedelta(days=1))
        Card.objects.filter(pk=future_forgot.pk).update(collection="Forgot",review_count=1)
        Card.objects.filter(pk=paused.pk).update(deferred_until=now+timedelta(minutes=30))
        self.vocabulary()
        archived=self.generic(question="Archived card");authoring.archive_card(archived,True)
        other_deck=Deck.objects.create(owner=self.user,name="Another active deck")
        other_card=authoring.save_card(other_deck,"generic",GENERIC)
        private_deck=Deck.objects.create(owner=self.other,name="Private")
        private_card=authoring.save_card(private_deck,"generic",GENERIC)
        archived_deck=Deck.objects.create(owner=self.user,name="Archived deck",archived=True)
        Card.objects.create(deck=archived_deck,kind="generic",identity="archived-deck-fixture",ready=True,**GENERIC)
        ids=list(review.queue(self.user,self.deck).values_list("pk",flat=True))
        expected=[cards[index].pk for cards in [forgot,reviewed] for index in [1,2,0]]
        self.assertEqual(ids[:6],expected)
        self.assertCountEqual(ids[6:],[card.pk for card in unseen])
        all_ids=list(review.queue(self.user).values_list("pk",flat=True))
        self.assertCountEqual(all_ids,ids+[other_card.pk])
        self.assertNotIn(private_card.pk,all_ids)

    def test_new_ready_cards_join_without_changing_displayed_question(self):
        for index in range(6): self.generic(question=f"Ready card {index}")
        waiting=self.vocabulary()
        before=list(review.queue(self.user,self.deck).values_list("pk",flat=True))
        self.assertNotIn(waiting.pk,before)
        p=self.present();frozen=(p.pk,p.snapshot,p.budget,p.created_at)
        self.client.get(reverse("presentation",args=[p.pk]))
        self.ready(waiting)
        self.assertCountEqual(list(review.queue(self.user,self.deck).values_list("pk",flat=True)),before+[waiting.pk])
        resumed=self.present()
        self.assertEqual((resumed.pk,resumed.snapshot,resumed.budget,resumed.created_at),frozen)
        self.assertTrue(resumed.clock_claimed)
        self.assertEqual(Presentation.objects.count(),1)

    def test_empty_practice_rechecks_ready_cards_and_snoozed_availability(self):
        waiting=self.vocabulary()
        url=reverse("practice")+f"?deck={self.deck.pk}"
        response=self.client.get(url)
        self.assertContains(response,"Nothing to practice right now.")
        self.ready(waiting)
        response=self.client.get(url)
        p=self.present()
        self.assertRedirects(response,reverse("presentation",args=[p.pk]))
        review.submit(p,"skip")
        response=self.client.get(url)
        self.assertContains(response,"Nothing to practice right now.")
        self.assertEqual(response.context["due_count"],0)
        self.assertIn("min",response.context["next_review"])
        response=self.client.get(reverse("dashboard"))
        self.assertNotContains(response,"Start a new run")
        self.assertNotContains(response,"Finished this run")
        self.assertRedirects(self.client.get(f"/runs/{uuid.uuid4()}/"),reverse("dashboard"))
        self.assertEqual(self.client.get(reverse("practice")+"?deck=invalid").status_code,404)

    def test_unassessed_exit_is_idempotent_and_stale_work_cannot_snooze_new_progress(self):
        card=self.generic()
        first=self.spoken(self.present())
        other=self.spoken(review.next_question(self.user))
        reviewed=review.commit_grade(first.pk,first.claim,"B",[],"Wrong fixture")
        card.refresh_from_db();self.assertIsNone(card.deferred_until)
        review.exit_attempt(other)
        card.refresh_from_db();self.assertIsNone(card.deferred_until)
        self.assertEqual(card.due,reviewed.next_due)
        Card.objects.filter(pk=card.pk).update(due=timezone.now()-timedelta(seconds=1))
        current=self.spoken(self.present())
        self.assertEqual(review.next_question(self.user,self.deck).pk,current.presentation_id)
        review.exit_attempt(current);card.refresh_from_db();deadline=card.deferred_until
        self.assertIsNotNone(deadline)
        review.exit_attempt(current);card.refresh_from_db()
        self.assertEqual(card.deferred_until,deadline)
        self.assertEqual(ScoredReview.objects.count(),1)

    def test_direction_slots_and_pair_lock_race(self):
        """DIRECTION-BLOCK / PAIR-ROTATION / PAIR-LOCK-RACE."""
        card=self.ready(self.vocabulary()); original=card.active_pair_id
        self.score(card,"E"); card.refresh_from_db()
        job=card.generation_jobs.get(mode="rotation",state="queued")
        p=self.present(card); frozen=p.snapshot.copy(); version=card.progress_version
        review.submit(p,"skip")
        job.state="processing"; job.started_at=timezone.now(); job.deadline=job.started_at+timedelta(seconds=300); job.save()
        candidate=work.save_pair(job.pk,job.claim,{**PAIR,"target_sentence":"Another misunderstanding arose."},{})
        card.refresh_from_db(); self.assertEqual((card.active_pair_id,card.progress_version),(original,version))
        with patch("learning.review.timezone.now",return_value=timezone.now()+timedelta(minutes=30)):
            p=self.present(); self.assertEqual(p.snapshot["pair_id"],original); self.assertEqual(p.snapshot["direction"],frozen["direction"])
            a=self.spoken(p); result=review.commit_grade(a.pk,a.claim,"D",[],"Valid old question")
        self.assertEqual(result.grade,"D")
        card.refresh_from_db(); self.assertIsNone(card.rotation_token)
        self.assertNotEqual(candidate.pk,card.active_pair_id)
        self.assertEqual(card.direction_index,2)

    def test_pair_activation_before_question_preserves_progress(self):
        card=self.ready(self.vocabulary()); self.score(card,"E"); card.refresh_from_db()
        job=card.generation_jobs.get(mode="rotation",state="queued"); job.state="processing"; job.started_at=timezone.now(); job.deadline=job.started_at+timedelta(seconds=300); job.save()
        pair=work.save_pair(job.pk,job.claim,{**PAIR,"target_sentence":"Another misunderstanding arose."},{})
        before=(card.fsrs,card.progress_version,card.collection,card.streak,card.direction_index,ScoredReview.objects.count())
        card.due=timezone.now()-timedelta(seconds=1); card.save(update_fields=["due"])
        p=self.present(); card.refresh_from_db()
        self.assertEqual(p.snapshot["pair_id"],pair.pk)
        self.assertEqual((card.fsrs,card.progress_version,card.collection,card.streak,card.direction_index,ScoredReview.objects.count()),before)

    def test_forgot_rotation_third_d_vs_e(self):
        for last in ["D","E"]:
            card=self.ready(self.vocabulary(word="word-"+last)); self.score(card,"B")
            for grade in ["E","E",last]:
                self.score(card,grade); card.refresh_from_db()
                self.assertEqual(bool(card.rotation_token),card.collection=="Normal" and grade=="E")

    def test_independent_same_word_cards_preserve_other_progress(self):
        first=self.ready(self.vocabulary(word="bank",explanation="Land beside a river"))
        second=self.ready(self.vocabulary(word="bank",explanation="A financial institution"))
        p=self.present()
        untouched=second if p.card_id==first.pk else first
        before=(untouched.fsrs,untouched.due,untouched.active_pair_id,untouched.deferred_until)
        a=self.spoken(p);review.commit_grade(a.pk,a.claim,"E",[],"Complete fixture")
        untouched.refresh_from_db()
        self.assertEqual((untouched.fsrs,untouched.due,untouched.active_pair_id,untouched.deferred_until),before)

    def test_format_only_edits_preserve_progress(self):
        generic=self.generic(question="A {{blank}}.",answer="target");self.score(generic)
        generic.refresh_from_db();before=(generic.source_version,generic.progress_version,generic.fsrs)
        generic=authoring.save_card(self.deck,"generic",{**GENERIC,"question":"A **{{blank}}**.","answer":"target"},generic)
        self.assertEqual((generic.source_version,generic.progress_version,generic.fsrs),before)

    def test_archive_restore_does_not_revive_old_execution(self):
        card=self.generic(); a=self.spoken(self.present()); due=card.due
        authoring.archive_card(card,True); card.refresh_from_db()
        authoring.archive_card(card,False); card.refresh_from_db()
        self.assertEqual(card.due,due)
        self.assertEqual(review.commit_grade(a.pk,a.claim,"E",[],"old").state,"closed_unassessed")
        self.assertEqual(ScoredReview.objects.count(),0)

    def test_restore_without_audio_and_with_saved_transcript(self):
        """RESTORE-NO-AUDIO / RESTORE-TRANSCRIPT logical states; real backup drill is separate."""
        self.generic(); a=self.spoken(self.present()); work.cleanup_attempt_audio(a)
        with self.assertRaises(StageError): work.process_assessment(a.pk,a.claim)
        work.fail("assessment",a.pk,a.claim,StageError("audio","Missing recording"))
        self.assertEqual(review.retry_attempt(a).state,"failed")
        a.refresh_from_db(); a.transcript="four"; a.save()
        self.assertEqual(review.retry_attempt(a).state,"submitted")

    def test_timing_frozen_through_retry_and_schedule_uses_receipt(self):
        self.generic(); a=self.spoken(self.present(),11); anchor=a.submitted_at
        work.fail("assessment",a.pk,a.claim,StageError("JUDGE","temporary"))
        a=review.retry_attempt(a)
        self.assertEqual((a.duration,a.submitted_at),(11,anchor))
        result=review.commit_grade(a.pk,a.claim,"B",[],"wrong")
        self.assertEqual(result.next_due,anchor+timedelta(minutes=1))

    def test_database_only_retry_reuses_judgment_and_fuzzed_candidate(self):
        original=Card.save
        from fsrs import Scheduler
        units=[{"id":1,"outcome":"complete","reason":"Complete fixture"}]
        for index,(grade,duration) in enumerate([("E",2),("D",90)],1):
            self.generic(question=f"Database retry {grade} fixture?");a=self.spoken(self.present(),duration)
            a.transcript="four";a.save();calls=[]
            def save(card,*args,**kwargs):
                calls.append(card.pk)
                if len(calls)==1:raise OperationalError("database is locked")
                return original(card,*args,**kwargs)
            with patch("learning.providers.assess",return_value=(units,{})) as judge,patch.object(Card,"save",save),patch(
                    "learning.review.Scheduler",wraps=Scheduler) as schedule,patch("learning.review.random.randint",return_value=2) as jitter:
                work.process_assessment(a.pk,a.claim)
            self.assertEqual(judge.call_count,1);self.assertEqual(schedule.call_count,1)
            self.assertEqual(jitter.call_count,1 if grade=="D" else 0)
            a.refresh_from_db();self.assertEqual((a.state,a.grade),("assessed",grade))
            if grade=="D":self.assertEqual(a.next_due,a.submitted_at+timedelta(days=2))
            self.assertEqual(ScoredReview.objects.count(),index)

    def test_ownership_all_surfaces_and_post_csrf(self):
        card=self.generic(); p=self.present(); job=self.vocabulary().generation_jobs.get()
        self.client.force_login(self.other)
        for name,args in [("deck",[self.deck.pk]),("card",[card.pk]),("presentation",[p.pk]),("status",[p.pk]),
                          ("deck_edit",[self.deck.pk]),("csv_import",[self.deck.pk])]:
            self.assertEqual(self.client.get(reverse(name,args=args)).status_code,404,name)
        for name,args in [("card_archive",[card.pk]),("deck_archive",[self.deck.pk]),("generation_retry",[job.pk]),
                          ("action",[p.pk]),("attempt_exit",[p.pk]),("attempt_retry",[p.pk]),("restart_question",[p.pk])]:
            self.assertEqual(self.client.post(reverse(name,args=args)).status_code,404,name)
        secured=Client(enforce_csrf_checks=True); secured.force_login(self.user)
        self.assertEqual(secured.post(reverse("action",args=[p.pk]),{"action":"forgot"}).status_code,403)

    def test_metrics_history_and_all_pages_render(self):
        """ACCOUNT-METRICS / MARKDOWN-UI supporting-page rendering."""
        card=self.generic(); self.score(card,"E"); self.score(card,"B")
        p=self.present(card); review.submit(p,"skip")
        authoring.archive_card(card,True)
        response=self.client.get(reverse("statistics")+"?window=all")
        self.assertEqual((response.context["distinct"],response.context["total"],response.context["accuracy"]),(1,2,50))
        self.assertEqual(response.context["due_count"],0)
        for name,args in [("dashboard",[]),("library",[]),("deck",[self.deck.pk]),("card",[card.pk]),
                          ("card_create",[self.deck.pk]),("csv_import",[self.deck.pk]),("statistics",[])]:
            self.assertEqual(self.client.get(reverse(name,args=args)).status_code,200,name)
        self.client.logout(); self.assertEqual(self.client.get(reverse("login")).status_code,200)
