"""Supervised private FLUX.3 Klein INT8 renderer for Vocabulary example illustrations.

Run on the GPU host beside loopback ComfyUI with the isolated INT8 interpreter:

    <miniforge>/envs/vocab-image-flux3-int8/bin/python ops/illustration-renderer.py \
        --model black-forest-labs/flux-3-image-klein \
        --api-key <worker credential> --host <gpu-host private IP> --port 8443 \
        --temp-dir <ComfyUI base-directory>/temp \
        --tls-certfile <cert.pem> --tls-keyfile <key.pem>

Set ILLUSTRATION_ENDPOINT / ILLUSTRATION_MODEL / ILLUSTRATION_API_KEY on the application to point at
the renderer's private HTTPS endpoint and share the same API key. The adapter submits the pinned
repository graph (ops/illustration-workflow.json, the tested INT8 pilot) to the loopback ComfyUI
v0.46.0 runtime with only the request's prompt text and noise seed substituted, admits one render
at a time, and bounds the entire round trip — admission, submission, every poll, the expiry check
before a result is accepted, streamed response reads included — by one request deadline. It owns
its inference work end to end: every accepted graph carries a caller-supplied prompt id, a queued
or running render is cancelled and waited out on failure or timeout, and the render's temporary
output files are removed from ComfyUI's temp directory (they are not auto-cleaned and a history
delete only forgets the in-memory entry). A cleanup that cannot complete keeps the history entry
as the ownership record and gates admission — the renderer answers a bounded 503 instead of
submitting new inference — until recovery finishes; an id whose submission was never acknowledged
is retained and reconciled for a bounded window, cancelled if it appears later. The renderer
refuses to start without --api-key, --temp-dir and a positive finite --timeout, and authenticates
every request. Prompts and credentials never reach the logs.
"""
import argparse
import copy
import io
import json
import math
import os
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAX_BODY_BYTES = 64 * 1024
PROMPT_NODE, SEED_NODE, OUTPUT_NODE = "4", "6", "12"
POLL_SECONDS = 0.125
CLEANUP_SECONDS = 5.0  # bounded cancellation/cleanup window, independent of the render deadline
RECONCILE_SECONDS = 60.0  # how long an unacknowledged submission id is retained for reconciliation
HANDSHAKE_SECONDS = 10.0  # bounded TLS handshake so one idle connection cannot stall the accept loop
# The pilot host's HTTP proxy variables must not redirect loopback ComfyUI traffic.
UPSTREAM = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="black-forest-labs/flux-3-image-klein",
                        help="the only model identifier this renderer accepts")
    parser.add_argument("--workflow", default=None,
                        help="path of the pinned ComfyUI graph; defaults to the file beside this script")
    parser.add_argument("--comfyui", default="http://127.0.0.1:8188",
                        help="loopback base URL of the local ComfyUI runtime")
    parser.add_argument("--temp-dir", required=True,
                        help="ComfyUI's temp directory, where this adapter removes its owned render files")
    parser.add_argument("--revision", default="int8-convrot@3b767ff9b5261d71645e2ec49d87d298d955238d",
                        help="INT8 checkpoint identity recorded in image provenance")
    parser.add_argument("--api-key", default="", help="worker credential; empty disables authentication")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--timeout", type=float, default=120.0,
                        help="bounded budget in seconds for one admitted render, including its queue wait")
    parser.add_argument("--tls-certfile", default=None, help="certificate chain for private HTTPS")
    parser.add_argument("--tls-keyfile", default=None, help="private key for private HTTPS")
    return parser


def load_workflow(path):
    """The pinned graph is the tested pilot artifact byte for byte: loaders, dimensions, the
    16-step Euler schedule and every other inference input stay fixed; only the prompt text and
    noise seed are substituted per request."""
    graph = json.loads(Path(path).read_text())["prompt"]
    for node in (PROMPT_NODE, SEED_NODE, OUTPUT_NODE):
        if node not in graph:
            raise SystemExit(f"--workflow is missing the pinned node {node}.")
    return graph


def remaining(deadline):
    left = deadline - time.monotonic()
    if left <= 0:
        raise TimeoutError("The render did not finish within its time budget.")
    return left


def read_bounded(response, deadline):
    """Read the whole response body while the absolute deadline holds: a socket timeout only bounds
    one blocking read, so a trickling sender must be cut by the deadline itself, not per chunk."""
    parts = []
    while True:
        remaining(deadline)
        chunk = response.read(65536)
        if not chunk:
            return b"".join(parts)
        parts.append(chunk)


def comfyui_request(base, route, body=None, *, deadline):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(base + route, data=data,
                                     headers={"Content-Type": "application/json"})
    with UPSTREAM.open(request, timeout=remaining(deadline)) as response:
        payload = read_bounded(response, deadline)
        return json.loads(payload) if payload else {}  # the history delete answers an empty 200


def remove_owned_files(arguments, entry):
    """Unlink the temp files this job's history entry owns — never any other file. A file that is
    already gone counts as clean; anything outside the temp directory is refused."""
    temp_root = os.path.realpath(arguments.temp_dir)
    removed = True
    for node in (entry.get("outputs") or {}).values():
        for image in node.get("images", []):
            if image.get("type") != "temp":
                continue
            path = os.path.realpath(os.path.join(arguments.temp_dir, image.get("subfolder", ""),
                                                 image["filename"]))
            if os.path.dirname(path) != temp_root:
                removed = False
                continue
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    removed = False
    return removed


def cleanup_job(arguments, prompt_id, known):
    """Cancel the owned job if it is queued or running, wait out its terminal state within the
    bounded cleanup window, then remove its temporary files and — only once they are gone — its
    history entry, which is the ownership record. Returns (resolved, seen): unresolved files leave
    the job unresolved, and an unknown submission that appears in neither queue nor history is not
    treated as terminal, because it may still be queued by the runtime later."""
    deadline = time.monotonic() + CLEANUP_SECONDS

    def left():
        return max(0.01, deadline - time.monotonic())

    try:
        comfyui_request(arguments.comfyui, "/queue", {"delete": [prompt_id]}, deadline=deadline)
        comfyui_request(arguments.comfyui, "/interrupt", {"prompt_id": prompt_id}, deadline=deadline)
        seen = False
        while time.monotonic() < deadline:
            queue = comfyui_request(arguments.comfyui, "/queue", deadline=deadline)
            ids = [item[1] for section in ("queue_running", "queue_pending")
                   for item in queue.get(section) or []]
            if prompt_id not in ids:
                break
            seen = True
            time.sleep(POLL_SECONDS)
        else:
            return False, seen  # the job never reached a terminal state within the window
        entry = comfyui_request(arguments.comfyui, f"/history/{prompt_id}", deadline=deadline).get(prompt_id)
        if not entry:
            return known or seen, seen  # an acknowledged-and-absent job is terminal; absence alone is not
        seen = True
        if not remove_owned_files(arguments, entry):
            return False, seen  # keep the history entry until every owned file is gone
        comfyui_request(arguments.comfyui, "/history", {"delete": [prompt_id]}, deadline=deadline)
        return True, seen
    except (urllib.error.URLError, OSError, ValueError):
        return False, False  # ComfyUI unreachable or unresponsive; the job is retried before the next render


def render(workflow, arguments, prompt, seed, deadline):
    """One ComfyUI round trip inside the caller's budget: submit the pinned graph under a
    caller-supplied prompt id, poll until the deadline, and fetch the temporary output. The
    finally block cancels the job and removes its files whether the render succeeded or not;
    an unresolved cleanup is retained so admission stays gated until recovery completes."""
    graph = copy.deepcopy(workflow)
    graph[PROMPT_NODE]["inputs"]["text"] = prompt
    graph[SEED_NODE]["inputs"]["noise_seed"] = seed
    prompt_id = str(uuid.uuid4())  # owned before submission: tracked even if the acknowledgement is lost
    known = False
    try:
        comfyui_request(arguments.comfyui, "/prompt",
                        {"prompt": graph, "prompt_id": prompt_id}, deadline=deadline)
        known = True  # the runtime accepted the id: absence now means terminal, not unknown
        while True:
            history = comfyui_request(arguments.comfyui, f"/history/{prompt_id}",
                                      deadline=deadline).get(prompt_id)
            if history is not None:
                status = history["status"]
                if not status["completed"] or status["status_str"] != "success":
                    raise RuntimeError(f"ComfyUI reported the render as {status['status_str']}.")
                remaining(deadline)  # a late completion is not served past its budget
                [output] = history["outputs"][OUTPUT_NODE]["images"]
                query = urllib.parse.urlencode({key: output[key] for key in ("filename", "subfolder", "type")})
                with UPSTREAM.open(arguments.comfyui + "/view?" + query,
                                   timeout=remaining(deadline)) as response:
                    scene = read_bounded(response, deadline)
                from PIL import Image
                with Image.open(io.BytesIO(scene)) as image:
                    image.thumbnail((512, 384), Image.LANCZOS)
                    encoded = io.BytesIO()
                    image.save(encoded, format="WEBP", quality=76)
                remaining(deadline)  # an expired render is cancelled, not served late
                return encoded.getvalue()
            time.sleep(POLL_SECONDS)
    finally:
        resolved, seen = cleanup_job(arguments, prompt_id, known)
        if not resolved:
            with Handler.abandoned_lock:
                previous = Handler.abandoned.get(prompt_id)
                Handler.abandoned[prompt_id] = {
                    "first_seen": previous["first_seen"] if previous else time.monotonic(),
                    "known": known or seen or previous is not None}


class Server(ThreadingHTTPServer):
    """TLS handshakes run in each connection's own thread with a finite timeout, so an idle or
    invalid connection can never stall the accept loop for other clients."""

    def __init__(self, address, handler, context=None):
        self.context = context
        super().__init__(address, handler)

    def process_request_thread(self, request, client_address):
        if self.context is None:
            return super().process_request_thread(request, client_address)
        request = self.context.wrap_socket(request, server_side=True, do_handshake_on_connect=False)
        request.settimeout(HANDSHAKE_SECONDS)
        try:
            request.do_handshake()
        except (OSError, ssl.SSLError):
            return self.shutdown_request(request)  # drop it; other clients keep being served
        super().process_request_thread(request, client_address)


class Handler(BaseHTTPRequestHandler):
    workflow = None
    arguments = None
    lock = threading.Lock()  # one inference at a time
    abandoned = {}  # prompt id -> {"first_seen", "known"}: owned jobs whose cleanup did not complete
    abandoned_lock = threading.Lock()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_BODY_BYTES:
            return self.reply(413, "The request body is too large.")
        if self.headers.get("Authorization") != "Bearer " + self.arguments.api_key:
            return self.reply(401, "Renderer credentials are missing or wrong.")
        try:
            body = json.loads(self.rfile.read(length))
        except ValueError:
            return self.reply(400, "The request body is not valid JSON.")
        if not isinstance(body, dict):
            return self.reply(400, "The request body must be a JSON object.")
        if body.get("model") != self.arguments.model:
            return self.reply(400, f"This renderer serves {self.arguments.model}; configure ILLUSTRATION_MODEL to match.")
        prompt = body.get("prompt")
        seed = body.get("seed")
        if not isinstance(prompt, str) or not prompt.strip() or type(seed) is not int or not 0 <= seed < 2**32:
            return self.reply(400, "The request needs a nonempty prompt and a 32-bit integer seed.")
        deadline = time.monotonic() + self.arguments.timeout  # one budget across admission and the round trip
        if not self.lock.acquire(timeout=max(0.0, deadline - time.monotonic())):
            return self.reply(503, "The renderer is busy with another render; retry shortly.")
        try:
            if not self.recover_abandoned():
                return self.reply(503, "The renderer is still recovering an earlier render; retry shortly.")
            try:
                image = render(self.workflow, self.arguments, prompt, seed, deadline)
            except TimeoutError:
                return self.reply(504, "The render exceeded its time budget. Retry once the renderer is healthy.")
            except Exception as error:
                return self.reply(502, f"Rendering failed: {error.__class__.__name__}.")
        finally:
            self.lock.release()
        self.send_response(200)
        self.send_header("Content-Type", "image/webp")
        self.send_header("Content-Length", str(len(image)))
        self.send_header("X-Illustration-Revision", self.arguments.revision)
        self.end_headers()
        self.wfile.write(image)

    def recover_abandoned(self):
        """Bounded best-effort recovery of jobs whose cleanup did not complete. Returns False while
        any owned job remains unresolved, and the caller must then admit no new inference."""
        with self.abandoned_lock:
            stale = list(self.abandoned.items())
        for prompt_id, record in stale:
            if not record["known"] and time.monotonic() - record["first_seen"] > RECONCILE_SECONDS:
                with self.abandoned_lock:
                    self.abandoned.pop(prompt_id, None)  # the submission never arrived; nothing is owned
                continue
            resolved, seen = cleanup_job(self.arguments, prompt_id, record["known"])
            if seen:
                record["known"] = True  # the job exists: reconcile and cancel it, however late
            if resolved:
                with self.abandoned_lock:
                    self.abandoned.pop(prompt_id, None)
        with self.abandoned_lock:
            return not self.abandoned

    def reply(self, status, message):
        body = json.dumps({"error": message}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # keep credentials and prompts out of logs
        pass


def require_worker_credential(arguments):
    """The renderer authenticates every request; an absent key must never disable that."""
    if not arguments.api_key:
        raise SystemExit("--api-key is required: the renderer refuses to listen without a worker credential.")


def require_bounded_timeout(arguments):
    """A non-positive or non-finite --timeout would leave renders unbounded."""
    if not math.isfinite(arguments.timeout) or arguments.timeout <= 0:
        raise SystemExit("--timeout must be a positive, finite number of seconds.")


def main():
    arguments = build_parser().parse_args()
    require_worker_credential(arguments)
    require_bounded_timeout(arguments)
    Handler.arguments = arguments
    Handler.workflow = load_workflow(arguments.workflow or
                                     Path(__file__).resolve().parent / "illustration-workflow.json")
    context = None
    if bool(arguments.tls_certfile) != bool(arguments.tls_keyfile):
        raise SystemExit("--tls-certfile and --tls-keyfile must be provided together.")
    if arguments.tls_certfile:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(arguments.tls_certfile, arguments.tls_keyfile)
    server = Server((arguments.host, arguments.port), Handler, context=context)
    server.daemon_threads = True
    print(f"Illustration renderer serving {arguments.model} via {arguments.comfyui} "
          f"on {'https' if context else 'http'}://{arguments.host}:{arguments.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
