"""Supervised private FLUX.3 Klein INT8 renderer for Vocabulary example illustrations.

Run on the GPU host beside loopback ComfyUI with the isolated INT8 interpreter:

    <miniforge>/envs/vocab-image-flux3-int8/bin/python ops/illustration-renderer.py \
        --model black-forest-labs/flux-3-image-klein \
        --api-key <worker credential> --host <gpu-host private IP> --port 8790

Set ILLUSTRATION_ENDPOINT / ILLUSTRATION_MODEL / ILLUSTRATION_API_KEY on the application to point
at the renderer through a TLS-terminating proxy (or plain HTTP inside the private network with the
development-only ALLOW_INSECURE_PROVIDER_HTTP=1) and share the same API key. The adapter submits
the pinned repository graph (ops/illustration-workflow.json, the tested INT8 pilot) to the loopback
ComfyUI v0.46.0 runtime with only the request's prompt text and noise seed substituted, admits one
render at a time, bounds the wait for the result, cleans up its temporary inference outputs, and
returns a 512×384 WebP (encoded from the 768×576 render) with the INT8 checkpoint identity in the
X-Illustration-Revision header. A request naming another model identifier is a clear 400. Prompts
and credentials never reach the logs.
"""
import argparse
import copy
import io
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAX_BODY_BYTES = 64 * 1024
PROMPT_NODE, SEED_NODE, OUTPUT_NODE = "4", "6", "12"
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
    parser.add_argument("--revision", default="int8-convrot@3b767ff9b5261d71645e2ec49d87d298d955238d",
                        help="INT8 checkpoint identity recorded in image provenance")
    parser.add_argument("--api-key", default="", help="worker credential; empty disables authentication")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--timeout", type=float, default=120.0,
                        help="bounded wait in seconds for one ComfyUI render")
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


def comfyui_request(base, route, body=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(base + route, data=data,
                                     headers={"Content-Type": "application/json"})
    with UPSTREAM.open(request, timeout=timeout) as response:
        payload = response.read()
        return json.loads(payload) if payload else {}  # the history delete answers an empty 200


def render(workflow, arguments, prompt, seed):
    """One ComfyUI round trip: submit the pinned graph, poll within the time budget, fetch the
    temporary output and encode it; the inference output is deleted whether the render succeeds
    or fails, so a failed render never accumulates work."""
    graph = copy.deepcopy(workflow)
    graph[PROMPT_NODE]["inputs"]["text"] = prompt
    graph[SEED_NODE]["inputs"]["noise_seed"] = seed
    prompt_id = None
    try:
        submitted = comfyui_request(arguments.comfyui, "/prompt", {"prompt": graph})
        prompt_id = submitted["prompt_id"]
        deadline = time.monotonic() + arguments.timeout
        while True:
            history = comfyui_request(arguments.comfyui, f"/history/{prompt_id}",
                                      timeout=10).get(prompt_id)
            if history is not None:
                break
            if time.monotonic() >= deadline:
                raise TimeoutError("The render did not finish within its time budget.")
            time.sleep(0.125)
        status = history["status"]
        if not status["completed"] or status["status_str"] != "success":
            raise RuntimeError(f"ComfyUI reported the render as {status['status_str']}.")
        [output] = history["outputs"][OUTPUT_NODE]["images"]
        query = urllib.parse.urlencode({key: output[key] for key in ("filename", "subfolder", "type")})
        with UPSTREAM.open(arguments.comfyui + "/view?" + query, timeout=30) as response:
            scene = response.read()
        from PIL import Image
        with Image.open(io.BytesIO(scene)) as image:
            image.thumbnail((512, 384), Image.LANCZOS)
            encoded = io.BytesIO()
            image.save(encoded, format="WEBP", quality=76)
            return encoded.getvalue()
    finally:
        if prompt_id is not None:
            try:
                comfyui_request(arguments.comfyui, "/history", {"delete": [prompt_id]}, timeout=10)
            except (urllib.error.URLError, OSError):
                pass  # the cleanup is best effort; a missed delete is retried by the next render


class Handler(BaseHTTPRequestHandler):
    workflow = None
    arguments = None
    lock = threading.Lock()  # one inference at a time

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
        if body.get("model") != self.arguments.model:
            return self.reply(400, f"This renderer serves {self.arguments.model}; configure ILLUSTRATION_MODEL to match.")
        prompt = body.get("prompt")
        seed = body.get("seed")
        if not isinstance(prompt, str) or not prompt.strip() or not isinstance(seed, int) or not 0 <= seed < 2**32:
            return self.reply(400, "The request needs a nonempty prompt and a 32-bit seed.")
        with self.lock:
            try:
                image = render(self.workflow, self.arguments, prompt, seed)
            except TimeoutError:
                return self.reply(504, "The render exceeded its time budget. Retry once the renderer is healthy.")
            except Exception as error:
                return self.reply(502, f"Rendering failed: {error.__class__.__name__}.")
        self.send_response(200)
        self.send_header("Content-Type", "image/webp")
        self.send_header("Content-Length", str(len(image)))
        self.send_header("X-Illustration-Revision", self.arguments.revision)
        self.end_headers()
        self.wfile.write(image)

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


def main():
    arguments = build_parser().parse_args()
    require_worker_credential(arguments)
    Handler.arguments = arguments
    Handler.workflow = load_workflow(arguments.workflow or
                                     Path(__file__).resolve().parent / "illustration-workflow.json")
    server = ThreadingHTTPServer((arguments.host, arguments.port), Handler)
    server.daemon_threads = True
    print(f"Illustration renderer serving {arguments.model} via {arguments.comfyui} "
          f"on {arguments.host}:{arguments.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
