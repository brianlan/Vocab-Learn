"""Contract tests for the INT8 ComfyUI adapter in ops/illustration-renderer.py (issue #29).

A fake loopback ComfyUI stands in for the real runtime and models the upstream's distinct
lifetimes: /prompt enqueues under the caller-supplied id (possibly only after a delay), one job
runs at a time and writes a real temp file on completion, /queue deletes pending ids, /interrupt
with a prompt id cancels the running job, and a history delete forgets only the in-memory entry —
files outlive it, exactly as in ComfyUI v0.46.0. The adapter must submit the pinned graph
byte-for-byte except for the prompt text and noise seed, reject unauthenticated, mismatched and
malformed requests before any inference is queued, admit one render at a time, bound the whole
round trip — streamed reads included — by one deadline, cancel its owned job and remove its owned
files on every exit path, gate new inference behind unfinished recovery, reconcile a submission
that was never acknowledged, and keep serving verified TLS clients while an idle connection
lingers.
"""
import contextlib
import importlib.util
import io
import json
import os
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image

OPS = Path(__file__).resolve().parents[2] / "ops"


def renderer_module():
    spec = importlib.util.spec_from_file_location("illustration_renderer", OPS / "illustration-renderer.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def scene_png(width=768, height=576):
    image = Image.new("RGB", (width, height), (140, 150, 110))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class FakeComfyUI:
    """A loopback ComfyUI stand-in with real job, history and temp-file lifetimes."""

    def __init__(self, job_duration=0.15):
        self._temp = tempfile.TemporaryDirectory(prefix="fake-comfy-temp-")
        self.temp_dir = self._temp.name
        self.job_duration = job_duration
        self.enqueue_delay = 0.0
        self.submission_delay = 0.0
        self.submission_hang = False  # enqueue the job, then never answer (lost acknowledgement)
        self.history_delay = 0.0
        self.view_delay = 0.0
        self.trickle_view = False
        self.hold_jobs = threading.Event()  # clear to keep jobs out of the running slot
        self.hold_jobs.set()
        self.hang_cancellation = False
        self.fail_jobs = False  # completed jobs report an error instead of writing a file
        self.overlapped = False  # set when a graph is submitted while another job is queued or running
        self.jobs_pending, self.jobs_running = [], []
        self.history = {}
        self.counter = 0
        self.requests = []
        self.lock = threading.Lock()
        self.stopping = threading.Event()
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.server = server
        return f"http://127.0.0.1:{server.server_address[1]}"

    def stop(self):
        self.stopping.set()
        self.hold_jobs.set()
        self.thread.join(timeout=5)
        self.server.shutdown()
        self.server.server_close()
        self._temp.cleanup()

    def settle(self):
        """Wait until no job is pending or running."""
        for _ in range(200):
            with self.lock:
                if not self.jobs_pending and not self.jobs_running:
                    return
            time.sleep(0.05)

    def temp_files(self):
        return sorted(os.listdir(self.temp_dir))

    def submitted_ids(self):
        return [request["body"]["prompt_id"] for request in self.requests
                if request["path"] == "/prompt" and isinstance(request["body"], dict)]

    def _run(self):
        while not self.stopping.is_set():
            job = None
            with self.lock:
                if self.jobs_pending and self.hold_jobs.is_set():
                    job = self.jobs_pending.pop(0)
                    self.jobs_running.append(job)
            if job is None:
                time.sleep(0.01)
                continue
            cancelled = job["cancel"].wait(self.job_duration)
            with self.lock:
                self.jobs_running.remove(job)
                if cancelled or self.fail_jobs:
                    self.history[job["prompt_id"]] = {"status": {"completed": True, "status_str": "error"},
                                                      "outputs": {}}
                else:
                    self.counter += 1
                    filename = f"ComfyUI_temp_{self.counter:05d}_.png"
                    with open(os.path.join(self.temp_dir, filename), "wb") as handle:
                        handle.write(scene_png())
                    self.history[job["prompt_id"]] = {
                        "status": {"completed": True, "status_str": "success"},
                        "outputs": {"12": {"images": [{"filename": filename, "subfolder": "", "type": "temp"}]}}}

    def _handler(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length)) if length else {}
                self._record(body)
                if self.path == "/prompt":
                    time.sleep(outer.enqueue_delay)  # the runtime delays before the graph is queued
                    with outer.lock:
                        if outer.jobs_pending or outer.jobs_running:
                            outer.overlapped = True
                        outer.jobs_pending.append({"prompt_id": body.get("prompt_id"),
                                                   "cancel": threading.Event()})
                    if outer.submission_hang:
                        time.sleep(30)  # the acknowledgement never arrives; the job exists
                        return
                    time.sleep(outer.submission_delay)
                    return self._json({"prompt_id": body.get("prompt_id")})
                if self.path == "/queue":
                    if outer.hang_cancellation:
                        time.sleep(30)
                    for prompt_id in body.get("delete", []):
                        with outer.lock:
                            outer.jobs_pending = [job for job in outer.jobs_pending
                                                  if job["prompt_id"] != prompt_id]
                    return self._empty()
                if self.path == "/interrupt":
                    if outer.hang_cancellation:
                        time.sleep(30)
                    with outer.lock:
                        for job in outer.jobs_running:
                            if job["prompt_id"] == body.get("prompt_id"):
                                job["cancel"].set()
                    return self._empty()
                if self.path == "/history":
                    if outer.hang_cancellation:
                        time.sleep(30)
                    with outer.lock:
                        for prompt_id in body.get("delete", []):
                            outer.history.pop(prompt_id, None)  # the real delete forgets only this
                    return self._empty()
                self.send_error(404)

            def do_GET(self):
                self._record(None)
                if self.path.startswith("/history/"):
                    time.sleep(outer.history_delay)
                    prompt_id = self.path.rsplit("/", 1)[1]
                    with outer.lock:
                        entry = outer.history.get(prompt_id)
                    return self._json({prompt_id: entry} if entry else {})
                if self.path.startswith("/queue"):
                    with outer.lock:
                        payload = {"queue_running": [[0, job["prompt_id"]] for job in outer.jobs_running],
                                   "queue_pending": [[0, job["prompt_id"]] for job in outer.jobs_pending]}
                    return self._json(payload)
                if self.path.startswith("/view"):
                    time.sleep(outer.view_delay)
                    query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                    with open(os.path.join(outer.temp_dir, query["filename"][0]), "rb") as handle:
                        payload = handle.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    if outer.trickle_view:  # valid bytes, but the stream outlasts any small budget
                        for index in range(0, len(payload), 512):
                            self.wfile.write(payload[index:index + 512])
                            self.wfile.flush()
                            time.sleep(0.05)
                        return
                    self.wfile.write(payload)
                    return
                self.send_error(404)

            def _record(self, body):
                with outer.lock:
                    outer.requests.append({"path": self.path, "body": body})

            def _json(self, payload):
                self._send(200, "application/json", json.dumps(payload).encode())

            def _empty(self):
                self._send(200, "application/json", b"")

            def _send(self, status, content_type, payload):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        return Handler


class RendererContractTests(unittest.TestCase):
    """Drive the real adapter Handler against the fake upstream over HTTP."""

    def setUp(self):
        self.renderer = renderer_module()
        self.renderer.CLEANUP_SECONDS = 0.8  # bounded cleanup window, kept small for the tests
        self.comfyui = FakeComfyUI()
        self.upstream = self.comfyui.start()
        self.reparse()
        self.renderer.Handler.abandoned = {}
        self.renderer.Handler.workflow = self.renderer.load_workflow(OPS / "illustration-workflow.json")
        self.server = self.renderer.Server(("127.0.0.1", 0), self.renderer.Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.endpoint = f"http://127.0.0.1:{self.server.server_address[1]}/render"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.comfyui.stop()

    def reparse(self, timeout=2.0, comfyui=None):
        self.renderer.Handler.arguments = self.renderer.build_parser().parse_args(
            ["--api-key", "scene-key", "--comfyui", comfyui or self.upstream, "--temp-dir", self.comfyui.temp_dir,
             "--revision", "int8-test@cafe", "--host", "127.0.0.1", "--port", "0", "--timeout", str(timeout)])

    def render_request(self, body=None, authorization="Bearer scene-key", timeout=30, raw=None):
        payload = raw if raw is not None else json.dumps(
            {"model": "black-forest-labs/flux-3-image-klein", "prompt": "A test scene.", "seed": 424242}
            if body is None else body).encode()
        headers = {"Content-Type": "application/json"}
        if authorization is not None:
            headers["Authorization"] = authorization
        request = urllib.request.Request(self.endpoint, data=payload, method="POST", headers=headers)
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, dict(response.headers), response.read(), time.monotonic() - started
        except urllib.error.HTTPError as error:
            return error.code, dict(error.headers), error.read(), time.monotonic() - started

    def upstream_requests(self):
        return [request["path"].split("?")[0] for request in self.comfyui.requests]

    def assert_no_inference(self):
        self.assertEqual(self.upstream_requests(), [])

    def test_submits_the_pinned_graph_with_only_prompt_and_seed_substituted(self):
        status, _, _, _ = self.render_request(
            body={"model": "black-forest-labs/flux-3-image-klein",
                  "prompt": "A hand-painted kitchen scene.", "seed": 987654})
        self.assertEqual(status, 200)
        [submitted] = [request["body"] for request in self.comfyui.requests if request["path"] == "/prompt"]
        pinned = json.loads((OPS / "illustration-workflow.json").read_text())["prompt"]
        self.assertEqual(submitted["prompt"]["4"]["inputs"]["text"], "A hand-painted kitchen scene.")
        self.assertEqual(submitted["prompt"]["6"]["inputs"]["noise_seed"], 987654)
        del submitted["prompt"]["4"], submitted["prompt"]["6"]
        del pinned["4"], pinned["6"]
        self.assertEqual(submitted["prompt"], pinned)  # loaders, latent size, sigmas: all pinned
        graph_id = submitted["prompt_id"]
        self.comfyui.settle()  # the job the adapter owned by this id is gone from queue and history
        with self.comfyui.lock:
            self.assertNotIn(graph_id, self.comfyui.history)
            self.assertFalse(self.comfyui.jobs_pending + self.comfyui.jobs_running)

    def test_success_returns_a_decodable_bounded_webp_with_the_revision(self):
        status, headers, image, _ = self.render_request()
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "image/webp")
        self.assertEqual(headers["X-Illustration-Revision"], "int8-test@cafe")
        self.assertLessEqual(len(image), 128 * 1024)
        with Image.open(io.BytesIO(image)) as decoded:
            self.assertEqual(decoded.format, "WEBP")
            self.assertEqual(decoded.size, (512, 384))

    def test_a_successful_render_removes_its_temp_file_and_history_entry(self):
        self.render_request()
        self.comfyui.settle()
        self.assertEqual(self.comfyui.temp_files(), [])  # the real temporary file is gone
        with self.comfyui.lock:
            self.assertEqual(self.comfyui.history, {})
            self.assertFalse(self.comfyui.jobs_pending + self.comfyui.jobs_running)

    def test_authentication_is_required_before_any_inference_is_queued(self):
        for authorization in (None, "Bearer wrong", "bearer scene-key"):
            with self.subTest(authorization=authorization):
                status, _, _, _ = self.render_request(authorization=authorization)
                self.assertEqual(status, 401)
        self.assert_no_inference()

    def test_a_model_mismatch_is_rejected_before_any_inference_is_queued(self):
        status, _, _, _ = self.render_request(body={"model": "someone-else", "prompt": "x", "seed": 1})
        self.assertEqual(status, 400)
        self.assert_no_inference()

    def test_malformed_requests_are_rejected_before_any_inference_is_queued(self):
        model = "black-forest-labs/flux-3-image-klein"
        documents = [json.dumps(body).encode() for body in (
            {}, {"model": model}, {model: model},
            {"model": model, "prompt": "   ", "seed": 1},
            {"model": model, "prompt": "x", "seed": 2**32},
            {"model": model, "prompt": "x", "seed": True},
            {"model": model, "prompt": "x", "seed": "7"},
            {"model": model, "prompt": "x"})] + [b"[]", b"null", b""]
        for payload in documents:
            with self.subTest(payload=payload):
                status, _, _, _ = self.render_request(raw=payload)
                self.assertEqual(status, 400)
        self.assert_no_inference()
        self.assertEqual(self.comfyui.temp_files(), [])  # nothing was ever written

    def test_an_oversized_body_is_rejected(self):
        request = urllib.request.Request(self.endpoint, data=b"x" * (65 * 1024), method="POST",
                                         headers={"Authorization": "Bearer scene-key"})
        try:
            urllib.request.urlopen(request, timeout=10)
            self.fail("the oversized body must be rejected")
        except urllib.error.HTTPError as error:
            self.assertEqual(error.code, 413)
        self.assert_no_inference()

    def test_renders_are_admitted_one_at_a_time(self):
        results = []

        def worker():
            results.append(self.render_request(timeout=30)[0])

        threads = [threading.Thread(target=worker) for _ in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(results), [200, 200, 200])
        self.assertFalse(self.comfyui.overlapped)  # no graph was ever submitted beside another

    def test_admission_and_the_round_trip_stay_within_the_request_budget(self):
        self.comfyui.job_duration = 1.2
        self.reparse(timeout=0.6)
        results = {}

        def first_request():
            results["A"] = self.render_request(timeout=30)[0]

        first = threading.Thread(target=first_request)
        first.start()
        time.sleep(0.3)  # the first request holds the renderer
        status, _, _, elapsed = self.render_request(timeout=30)
        self.assertEqual(status, 504)  # bounded admission: the queued wait consumed the budget
        self.assertLess(elapsed, 1.6)  # arrival + budget + bounded cleanup, never unbounded queuing
        first.join()
        self.assertEqual(results["A"], 504)  # the slow first render hit its own budget
        self.comfyui.settle()
        self.reparse(timeout=2.0)
        status, _, _, _ = self.render_request()
        self.assertEqual(status, 200)  # a subsequent request succeeds once the renderer is healthy
        self.assertEqual(self.comfyui.temp_files(), [])

    def test_a_timed_out_running_render_is_interrupted_and_cleaned_up(self):
        self.comfyui.job_duration = 3.0
        self.reparse(timeout=0.6)
        started = time.monotonic()
        status, _, _, _ = self.render_request(timeout=30)
        self.assertEqual(status, 504)
        self.assertLess(time.monotonic() - started, 2.5)  # bounded cancellation, not a hang
        self.comfyui.settle()
        self.assertEqual(self.comfyui.temp_files(), [])  # the owned file was never published or is removed
        with self.comfyui.lock:
            self.assertEqual(self.comfyui.history, {})
            self.assertFalse(self.comfyui.jobs_pending + self.comfyui.jobs_running)

    def test_a_timed_out_pending_render_is_dequeued(self):
        self.comfyui.hold_jobs.clear()  # nothing runs; the job would wait in the queue forever
        self.reparse(timeout=0.5)
        status, _, _, _ = self.render_request(timeout=30)
        self.assertEqual(status, 504)
        self.comfyui.settle()
        with self.comfyui.lock:
            self.assertFalse(self.comfyui.jobs_pending + self.comfyui.jobs_running)
            self.assertEqual(self.comfyui.history, {})
        self.assertEqual(self.comfyui.temp_files(), [])
        self.comfyui.hold_jobs.set()

    def test_a_lost_submission_acknowledgement_is_still_cancelled(self):
        self.comfyui.submission_hang = True  # the job is enqueued, but the adapter never learns the id back
        self.reparse(timeout=0.6)
        status, _, _, elapsed = self.render_request(timeout=30)
        self.assertEqual(status, 504)
        self.assertLess(elapsed, 2.0)
        self.comfyui.settle()
        self.assertEqual(self.comfyui.temp_files(), [])
        with self.comfyui.lock:
            self.assertEqual(self.comfyui.history, {})
            self.assertFalse(self.comfyui.jobs_pending + self.comfyui.jobs_running)

    def test_a_late_completion_is_not_served_past_the_deadline(self):
        self.comfyui.job_duration = 0.05
        self.comfyui.history_delay = 0.6  # the result arrives only after the budget has expired
        self.reparse(timeout=0.3)
        status, _, _, _ = self.render_request(timeout=30)
        self.assertEqual(status, 504)
        self.comfyui.settle()
        self.assertEqual(self.comfyui.temp_files(), [])  # the completed-but-late render is cleaned up

    def test_a_failed_render_is_rejected_and_cleaned_up(self):
        self.comfyui.fail_jobs = True
        status, _, _, _ = self.render_request(timeout=30)
        self.assertEqual(status, 502)
        self.comfyui.settle()
        self.assertEqual(self.comfyui.temp_files(), [])
        with self.comfyui.lock:
            self.assertEqual(self.comfyui.history, {})

    def test_an_unreachable_comfyui_reports_a_clean_failure(self):
        self.reparse(comfyui="http://127.0.0.1:1")  # nothing listens there
        status, _, _, _ = self.render_request(timeout=30)
        self.assertEqual(status, 502)

    def test_a_cleanup_that_cannot_complete_is_retried_by_the_next_request(self):
        self.comfyui.job_duration = 3.0
        self.comfyui.hang_cancellation = True
        self.reparse(timeout=0.5)
        status, _, _, _ = self.render_request(timeout=30)  # timeout; the cancellation calls stall
        self.assertEqual(status, 504)
        self.assertTrue(self.renderer.Handler.abandoned)  # the unfinished cleanup is not forgotten
        self.comfyui.hang_cancellation = False
        self.comfyui.settle()  # the abandoned job eventually finishes and writes its file
        self.assertEqual(len(self.comfyui.temp_files()), 1)
        self.comfyui.job_duration = 0.15  # the next healthy render is quick again
        self.reparse(timeout=2.0)
        status, _, _, _ = self.render_request(timeout=30)  # the next healthy render
        self.assertEqual(status, 200)
        self.assertEqual(self.comfyui.temp_files(), [])  # the abandoned file is removed with the new one

    def test_recovery_failure_blocks_new_renders_until_resolved(self):
        foreign = os.path.join(self.comfyui.temp_dir, "unrelated.png")
        with open(foreign, "wb") as handle:
            handle.write(scene_png(16, 16))
        self.comfyui.job_duration = 3.0
        self.comfyui.hang_cancellation = True
        self.reparse(timeout=0.5)
        self.assertEqual(self.render_request(timeout=30)[0], 504)  # abandoned: cancellation hung
        status, _, _, elapsed = self.render_request(timeout=30)
        self.assertEqual(status, 503)  # no new inference while an owned job is unresolved
        self.assertLess(elapsed, 2.5)  # the recovery attempt itself stays bounded
        self.assertEqual(len(self.comfyui.submitted_ids()), 1)  # nothing new was submitted
        self.comfyui.hang_cancellation = False
        self.comfyui.job_duration = 0.15
        self.reparse(timeout=2.0)
        status, _, _, _ = self.render_request(timeout=30)  # recovery first, then a fresh render
        self.assertEqual(status, 200)
        self.comfyui.settle()
        self.assertEqual(self.comfyui.temp_files(), ["unrelated.png"])  # only our own files were touched
        with self.comfyui.lock:
            self.assertEqual(self.comfyui.history, {})

    def test_a_transient_file_removal_failure_keeps_ownership(self):
        self.comfyui.hang_cancellation = True
        self.reparse(timeout=0.5)
        self.assertEqual(self.render_request(timeout=30)[0], 200)  # the image rendered; cleanup hangs
        self.assertTrue(self.renderer.Handler.abandoned)  # and the file cleanup did not complete
        self.comfyui.hang_cancellation = False
        self.comfyui.settle()  # the abandoned job finishes and writes its file
        [owned] = self.comfyui.temp_files()
        [submitted_id] = self.comfyui.submitted_ids()
        os.chmod(self.comfyui.temp_dir, 0o500)  # unlink now fails with PermissionError
        try:
            status, _, _, _ = self.render_request(timeout=30)
            self.assertEqual(status, 503)  # recovery did not complete: no new inference
            with self.comfyui.lock:
                self.assertIn(submitted_id, self.comfyui.history)  # the ownership record is kept
            self.assertTrue(os.path.exists(os.path.join(self.comfyui.temp_dir, owned)))
        finally:
            os.chmod(self.comfyui.temp_dir, 0o700)
        status, _, _, _ = self.render_request(timeout=30)
        self.assertEqual(status, 200)  # recovery completes once deletion becomes possible
        self.assertEqual(self.comfyui.temp_files(), [])
        with self.comfyui.lock:
            self.assertNotIn(submitted_id, self.comfyui.history)

    def test_a_submission_that_was_never_acknowledged_is_reconciled(self):
        self.comfyui.enqueue_delay = 0.4  # the runtime delays before the graph is queued
        self.comfyui.submission_hang = True  # and the acknowledgement never arrives
        self.comfyui.job_duration = 3.0
        self.reparse(timeout=0.15)
        status, _, _, _ = self.render_request(timeout=30)
        self.assertEqual(status, 504)
        self.assertTrue(self.renderer.Handler.abandoned)  # the unknown submission is retained
        status, _, _, _ = self.render_request(timeout=30)  # while the retention window holds
        self.assertEqual(status, 503)  # unresolved owned work blocks new inference
        self.assertEqual(len(self.comfyui.submitted_ids()), 1)
        time.sleep(0.5)  # the delayed submission queues its job after the fact
        self.comfyui.enqueue_delay = 0.0
        self.comfyui.submission_hang = False  # the next submission is answered normally
        self.comfyui.job_duration = 0.15  # only for the fresh render; the old job keeps its wait
        self.reparse(timeout=2.0)
        status, _, _, _ = self.render_request(timeout=30)
        self.assertEqual(status, 200)  # recovery reconciles and cancels the late job, then renders
        self.comfyui.settle()
        self.assertEqual(self.comfyui.temp_files(), [])
        with self.comfyui.lock:
            self.assertEqual(self.comfyui.history, {})
            self.assertFalse(self.comfyui.jobs_pending + self.comfyui.jobs_running)

    def test_an_unacknowledged_submission_is_reconciled_after_a_bounded_window(self):
        self.comfyui.enqueue_delay = 30.0  # far beyond the retention window: the graph never queues
        self.comfyui.submission_hang = True
        self.reparse(timeout=0.15)
        self.renderer.RECONCILE_SECONDS = 0.5
        self.assertEqual(self.render_request(timeout=30)[0], 504)
        self.assertEqual(self.render_request(timeout=30)[0], 503)  # retained while the window holds
        time.sleep(0.7)  # the bounded retention expires with nothing ever having appeared
        self.comfyui.enqueue_delay = 0.0
        self.comfyui.submission_hang = False
        self.reparse(timeout=2.0)
        status, _, _, _ = self.render_request(timeout=30)
        self.assertEqual(status, 200)  # the unknown id is dropped and the renderer serves again
        self.assertEqual(self.renderer.Handler.abandoned, {})

    def test_a_trickling_body_cannot_outlast_the_deadline(self):
        self.comfyui.trickle_view = True  # valid bytes, streamed slower than the budget
        self.reparse(timeout=0.3)
        status, _, _, elapsed = self.render_request(timeout=30)
        self.assertEqual(status, 504)  # the streamed read is cut by the absolute deadline
        self.assertLess(elapsed, 1.5)
        self.comfyui.settle()
        self.assertEqual(self.comfyui.temp_files(), [])  # the fetched-then-abandoned output is cleaned

    def test_the_timeout_must_be_positive_and_finite(self):
        for value in ("0", "-1", "nan", "inf"):
            with self.subTest(value=value):
                with contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        self.renderer.require_bounded_timeout(self.renderer.build_parser().parse_args(
                            ["--temp-dir", "/tmp/x", "--timeout", value]))
        self.renderer.require_bounded_timeout(self.renderer.build_parser().parse_args(
            ["--temp-dir", "/tmp/x", "--timeout", "0.5"]))  # a valid budget is accepted

    def test_the_renderer_refuses_to_listen_without_a_credential(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                self.renderer.require_worker_credential(self.renderer.build_parser().parse_args(
                    ["--temp-dir", "/tmp/x"]))

    def test_the_renderer_requires_a_temp_directory(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                self.renderer.build_parser().parse_args(["--api-key", "k"])

    def test_a_workflow_missing_the_pinned_nodes_is_refused(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json") as handle:
            json.dump({"prompt": {"4": {"inputs": {}}}}, handle)
            handle.flush()
            with self.assertRaises(SystemExit):
                self.renderer.load_workflow(handle.name)


class TLSListenerTests(unittest.TestCase):
    """The adapter's own TLS listener must keep serving verified clients while an idle
    unauthenticated connection lingers, and must keep enforcing verification (R6)."""

    def setUp(self):
        self.renderer = renderer_module()
        self.renderer.CLEANUP_SECONDS = 0.8
        self.comfyui = FakeComfyUI()
        self.upstream = self.comfyui.start()
        self.renderer.Handler.abandoned = {}
        self.renderer.Handler.workflow = self.renderer.load_workflow(OPS / "illustration-workflow.json")
        self.certs = tempfile.TemporaryDirectory(prefix="renderer-tls-")
        certificate = os.path.join(self.certs.name, "cert.pem")
        key = os.path.join(self.certs.name, "key.pem")
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", key,
                        "-out", certificate, "-days", "2", "-subj", "/CN=127.0.0.1",
                        "-addext", "subjectAltName=IP:127.0.0.1"], check=True, capture_output=True)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certificate, key)
        self.server = self.renderer.Server(("127.0.0.1", 0), self.renderer.Handler, context=context)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.renderer.Handler.arguments = self.renderer.build_parser().parse_args(
            ["--api-key", "scene-key", "--comfyui", self.upstream, "--temp-dir", self.comfyui.temp_dir,
             "--host", "127.0.0.1", "--port", "0", "--timeout", "2"])
        self.port = self.server.server_address[1]
        self.trusted = ssl.create_default_context(cafile=certificate)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.comfyui.stop()
        self.certs.cleanup()

    def verified_request(self, host="127.0.0.1", context=None, timeout=5):
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(
            context=context or self.trusted))
        request = urllib.request.Request(f"https://{host}:{self.port}/render", data=b"{}", method="POST")
        started = time.monotonic()
        try:
            with opener.open(request, timeout=timeout) as response:
                return response.status, time.monotonic() - started
        except urllib.error.HTTPError as error:
            return error.code, time.monotonic() - started

    def test_an_idle_connection_cannot_block_verified_clients(self):
        idle = socket.create_connection(("127.0.0.1", self.port))  # connects, sends no TLS bytes
        try:
            status, elapsed = self.verified_request()
            self.assertEqual(status, 401)  # verified TLS, unauthenticated: rejected, never stalled
            self.assertLess(elapsed, 3.0)
            status, _ = self.verified_request()  # the listener keeps serving after the drop
            self.assertEqual(status, 401)
        finally:
            idle.close()

    def test_certificate_and_hostname_verification_stay_enforced(self):
        with self.assertRaises(urllib.error.URLError) as failure:
            self.verified_request(host="localhost")  # the certificate names the IP, not localhost
        self.assertIn("certificate verify failed", str(failure.exception.reason))


if __name__ == "__main__":
    unittest.main()
