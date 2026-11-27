"""Supervised private FLUX.3 Image Klein renderer for Vocabulary example illustrations.

Run on the GPU host with the isolated `vocab-image-flux3` Conda interpreter:

    <miniforge>/envs/vocab-image-flux3/bin/python ops/illustration-renderer.py \
        --model black-forest-labs/flux-3-image-klein \
        --checkpoint /models/flux3-image-klein \
        --revision 3b767ff9b5261d71645e2ec49d87d298d955238d \
        --api-key <worker credential> --host 127.0.0.1 --port 8790

Set ILLUSTRATION_ENDPOINT / ILLUSTRATION_MODEL / ILLUSTRATION_API_KEY on the application to point
at http://<host>:<port>/render and share the same API key. The renderer loads
one operator-configured compatible checkpoint from local disk at startup, authenticates the worker
with the Bearer credential, serves one inference at a time, keeps prompt upsampling disabled, and
returns a 512×384 WebP (encoded from one 768×576 render at 16 steps) with the checkpoint revision
in the X-Illustration-Revision header. A request naming another model identifier is a clear 400.
"""
import argparse
import io
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_BODY_BYTES = 64 * 1024


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="black-forest-labs/flux-3-image-klein",
                        help="the only model identifier this renderer accepts")
    parser.add_argument("--checkpoint", required=True, help="local path of the compatible checkpoint")
    parser.add_argument("--revision", default="", help="checkpoint revision recorded in image provenance")
    parser.add_argument("--api-key", default="", help="worker credential; empty disables authentication")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8790)
    return parser


def load_pipeline(args):
    """Load the compatible checkpoint once at startup; one inference at a time, upsampling off."""
    import torch
    from diffusers import DiffusionPipeline
    pipeline = DiffusionPipeline.from_pretrained(args.checkpoint, torch_dtype=torch.bfloat16)
    pipeline.to("cuda" if torch.cuda.is_available() else "cpu")
    return pipeline


def render(pipeline, args, prompt, seed):
    import torch
    from PIL import Image
    generator = torch.Generator(device=pipeline.device).manual_seed(seed)
    with torch.inference_mode():
        result = pipeline(prompt=prompt, width=768, height=576, num_inference_steps=16,
                          guidance_scale=2.5, prompt_upsampling=False, generator=generator)
    image = result.images[0]
    image.thumbnail((512, 384), Image.LANCZOS)
    encoded = io.BytesIO()
    image.save(encoded, format="WEBP", quality=76)
    return encoded.getvalue()


class Handler(BaseHTTPRequestHandler):
    pipeline = None
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
                image = render(self.pipeline, self.arguments, prompt, seed)
            except Exception as error:
                return self.reply(500, f"Rendering failed: {error.__class__.__name__}.")
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
    print(f"Loading checkpoint {arguments.checkpoint} ...", flush=True)
    Handler.pipeline = load_pipeline(arguments)
    server = ThreadingHTTPServer((arguments.host, arguments.port), Handler)
    server.daemon_threads = True
    print(f"Illustration renderer serving {arguments.model} on {arguments.host}:{arguments.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
