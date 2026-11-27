"""Contract tests for the INT8 ComfyUI adapter in ops/illustration-renderer.py (issue #29).

A fake loopback ComfyUI stands in for the real runtime: the adapter must submit the pinned graph
byte-for-byte except for the prompt text and noise seed, forward the seed, return a bounded WebP
with the checkpoint revision, reject unauthenticated, mismatched and malformed requests before any
inference is queued, admit one render at a time, bound the wait, and delete the temporary output.
"""
import importlib.util
import io
import json
import threading
import time
import unittest
import urllib.error
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
    """A loopback ComfyUI stand-in that records every request and can fail, hang or delay."""

    def __init__(self, *, fail=False, hang=False, history_polls_before_done=0):
        self.requests, self.deleted = [], []
        self.fail, self.hang = fail, hang
        self.polls_before_done = history_polls_before_done
        self.rendered = threading.Event()
        self.in_flight = 0
        self.overlapped = False
        self.lock = threading.Lock()
        self._done = threading.Event()

    def start(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def _record(self):
                with outer.lock:
                    outer.requests.append({"path": self.path, "body": getattr(self, "_body", None)})

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                self._body = json.loads(self.rfile.read(length)) if length else {}
                self._record()
                if self.path == "/prompt":
                    with outer.lock:
                        outer.in_flight += 1
                        if outer.in_flight > 1:
                            outer.overlapped = True
                    time.sleep(0.3)  # hold the submission open to expose concurrent admissions
                    with outer.lock:
                        outer.in_flight -= 1
                    outer.rendered.set()
                    return self._json({"prompt_id": "job-1"})
                if self.path == "/history":
                    outer.deleted.append(self._body.get("delete"))
                    self.send_response(200)  # the real runtime answers the delete with an empty 200
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                self.send_error(404)

            def do_GET(self):
                self._record()
                if self.path.startswith("/history/"):
                    if outer.hang:
                        return self._json({})  # in flight: ComfyUI returns no entry yet
                    if not outer._done.is_set():
                        if outer.polls_before_done > 0:
                            outer.polls_before_done -= 1
                            return self._json({})
                        outer._done.set()
                    if outer.fail:
                        return self._json({"job-1": {"status": {"completed": True, "status_str": "error"}}})
                    return self._json({"job-1": {
                        "status": {"completed": True, "status_str": "success"},
                        "outputs": {"12": {"images": [{"filename": "scene_00001_.png",
                                                       "subfolder": "", "type": "temp"}]}}}})
                if self.path.startswith("/view"):
                    return self._raw(scene_png())
                self.send_error(404)

            def _json(self, payload):
                body = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _raw(self, payload):
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


class RendererContractTests(unittest.TestCase):
    """Drive the real adapter Handler against the fake upstream over HTTP."""

    def setUp(self):
        self.renderer = renderer_module()
        self.comfyui = FakeComfyUI()
        self.upstream = self.comfyui.start()
        self.arguments = self.renderer.build_parser().parse_args(
            ["--api-key", "scene-key", "--comfyui", self.upstream, "--revision", "int8-test@cafe",
             "--host", "127.0.0.1", "--port", "0", "--timeout", "2"])
        self.renderer.require_worker_credential(self.arguments)
        self.renderer.Handler.arguments = self.arguments
        self.renderer.Handler.workflow = self.renderer.load_workflow(OPS / "illustration-workflow.json")
        self.server = self.renderer.ThreadingHTTPServer(("127.0.0.1", 0), self.renderer.Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.endpoint = f"http://127.0.0.1:{self.server.server_address[1]}/render"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.comfyui.stop()

    def render_request(self, body=None, authorization="Bearer scene-key", timeout=30):
        payload = json.dumps(body or {"model": "black-forest-labs/flux-3-image-klein",
                                      "prompt": "A test scene.", "seed": 424242}).encode()
        headers = {"Content-Type": "application/json"}
        if authorization is not None:
            headers["Authorization"] = authorization
        request = urllib.request.Request(self.endpoint, data=payload, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as error:
            return error.code, dict(error.headers), error.read()

    def upstream_paths(self):
        return [request["path"].split("?")[0] for request in self.comfyui.requests]

    def test_submits_the_pinned_graph_with_only_prompt_and_seed_substituted(self):
        status, headers, image = self.render_request(
            body={"model": "black-forest-labs/flux-3-image-klein",
                  "prompt": "A hand-painted kitchen scene.", "seed": 987654})
        self.assertEqual(status, 200)
        [submitted] = [request["body"]["prompt"] for request in self.comfyui.requests
                       if request["path"] == "/prompt"]
        pinned = json.loads((OPS / "illustration-workflow.json").read_text())["prompt"]
        self.assertEqual(submitted["4"]["inputs"]["text"], "A hand-painted kitchen scene.")
        self.assertEqual(submitted["6"]["inputs"]["noise_seed"], 987654)
        del submitted["4"], submitted["6"]
        del pinned["4"], pinned["6"]
        self.assertEqual(submitted, pinned)  # loaders, latent size, sigmas: all pinned, byte for byte

    def test_success_returns_a_decodable_bounded_webp_with_the_revision(self):
        status, headers, image = self.render_request()
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "image/webp")
        self.assertEqual(headers["X-Illustration-Revision"], "int8-test@cafe")
        self.assertLessEqual(len(image), 128 * 1024)
        with Image.open(io.BytesIO(image)) as decoded:
            self.assertEqual(decoded.format, "WEBP")
            self.assertEqual(decoded.size, (512, 384))

    def test_authentication_is_required_before_any_inference_is_queued(self):
        for authorization in (None, "Bearer wrong", "bearer scene-key"):
            with self.subTest(authorization=authorization):
                status, _, _ = self.render_request(authorization=authorization)
                self.assertEqual(status, 401)
                self.assertEqual(self.comfyui.requests, [])

    def test_a_model_mismatch_is_rejected_before_any_inference_is_queued(self):
        status, _, _ = self.render_request(body={"model": "someone-else", "prompt": "x", "seed": 1})
        self.assertEqual(status, 400)
        self.assertEqual(self.comfyui.requests, [])

    def test_malformed_requests_are_rejected_before_any_inference_is_queued(self):
        for body in ({"model": "black-forest-labs/flux-3-image-klein", "prompt": "   ", "seed": 1},
                     {"model": "black-forest-labs/flux-3-image-klein", "prompt": "x", "seed": 2**32},
                     {"model": "black-forest-labs/flux-3-image-klein", "prompt": "x"},
                     {"model": "black-forest-labs/flux-3-image-klein", "prompt": "x", "seed": "7"}):
            with self.subTest(body=body):
                status, _, _ = self.render_request(body=body)
                self.assertEqual(status, 400)
        self.assertEqual(self.comfyui.requests, [])

    def test_an_oversized_body_is_rejected(self):
        request = urllib.request.Request(self.endpoint, data=b"x" * (65 * 1024), method="POST",
                                         headers={"Authorization": "Bearer scene-key"})
        try:
            urllib.request.urlopen(request, timeout=10)
            self.fail("the oversized body must be rejected")
        except urllib.error.HTTPError as error:
            self.assertEqual(error.code, 413)
        self.assertEqual(self.comfyui.requests, [])

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
        self.assertFalse(self.comfyui.overlapped)  # no second graph was ever submitted mid-render

    def test_a_timed_out_render_is_rejected_and_cleaned_up(self):
        self.comfyui.hang = True
        status, _, _ = self.render_request(timeout=30)
        self.assertEqual(status, 504)
        self.assertIn(["job-1"], self.comfyui.deleted)  # the submitted graph's output is deleted

    def test_a_failed_render_is_rejected_and_cleaned_up(self):
        self.comfyui.fail = True
        status, _, _ = self.render_request(timeout=30)
        self.assertEqual(status, 502)
        self.assertIn(["job-1"], self.comfyui.deleted)

    def test_a_successful_render_cleans_up_its_temporary_output(self):
        self.render_request()
        self.assertIn(["job-1"], self.comfyui.deleted)

    def test_an_unreachable_comfyui_reports_a_clean_failure(self):
        self.arguments.comfyui = "http://127.0.0.1:1"  # nothing listens there
        self.renderer.Handler.arguments = self.arguments
        status, _, _ = self.render_request(timeout=30)
        self.assertEqual(status, 502)
        self.renderer.Handler.arguments = self.arguments  # restore for tearDown symmetry

    def test_the_renderer_refuses_to_listen_without_a_credential(self):
        with self.assertRaises(SystemExit):
            self.renderer.require_worker_credential(self.renderer.build_parser().parse_args([]))

    def test_a_workflow_missing_the_pinned_nodes_is_refused(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json") as handle:
            json.dump({"prompt": {"4": {"inputs": {}}}}, handle)
            handle.flush()
            with self.assertRaises(SystemExit):
                self.renderer.load_workflow(handle.name)
