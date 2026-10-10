"""Temporary loopback mock UI; no source adapter, API credentials or persistent state."""
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Literal


def mock_html(failure: Literal["none", "application", "timeout"] = "none") -> str:
    # Static trusted test code, never model-generated or source-repository JavaScript.
    response = {
        "none": "document.querySelector('#cards').hidden=false;",
        "application": "document.querySelector('#error').hidden=false;",
        "timeout": "",
    }[failure]
    return """<!doctype html><html lang="en"><meta charset="utf-8">
<title>RepoFusion mock product</title>
<h1>Mock study cards</h1><p>Fixture only. No real repository integration or model inference.</p>
<button data-target-id="load-sample" onclick="document.querySelector('#notes').value=
'Photosynthesis uses sunlight. Water freezes at 0 C.';
document.querySelector('#generate').disabled=false;">Load sample</button>
<label for="notes">Sample notes</label><textarea id="notes" readonly></textarea>
<button id="generate" data-target-id="generate-cards" disabled onclick="RESPONSE">Generate cards</button>
<p id="error" role="alert" hidden>Mock application failure</p>
<section id="cards" hidden aria-label="Study cards">
<article><h2>What does photosynthesis use?</h2><p>Sunlight</p></article>
<article><h2>At what temperature does water freeze?</h2><p>0 C</p></article>
</section></html>""".replace("RESPONSE", response)


@contextmanager
def serve_mock_product(failure: Literal["none", "application", "timeout"] = "none"):
    if failure not in {"none", "application", "timeout"}:
        raise ValueError("Unknown mock failure")
    body = mock_html(failure).encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
