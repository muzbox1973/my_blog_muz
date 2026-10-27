"""Loopback-only view: expose the dashboard and state, never the post directory."""
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def serve(directory, port=0):
    directory = Path(directory)
    token = secrets.token_urlsafe(24)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, data, content_type="application/json", status=200):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers(); self.wfile.write(data)

        def do_GET(self):
            name = urlsplit(self.path).path
            if name == "/health":
                self.reply(b'{"ok":true}'); return
            files = {"/": "office.html", "/office.html": "office.html", "/status.json": "status.json", "/status.js": "status.js"}
            if name not in files:
                self.reply(b"{}", status=404); return
            try:
                types = {".html": "text/html; charset=utf-8", ".json": "application/json; charset=utf-8", ".js": "text/javascript; charset=utf-8"}
                path = directory / files[name]
                self.reply(path.read_bytes(), types[path.suffix])
            except FileNotFoundError:
                self.reply(b"{}", status=404)

        def do_POST(self):
            if self.path != "/stop" or self.headers.get("X-Harness-Token") != token:
                self.reply(b"{}", status=403); return
            self.reply(b'{"stopped":true}')
            threading.Thread(target=server.shutdown, daemon=True).start()

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    metadata = {"url": f"http://127.0.0.1:{server.server_port}/office.html", "token": token}
    info = directory / ".progress-server.json"
    from status import write_atomic
    write_atomic(info, json.dumps(metadata))
    print(metadata["url"], flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()
        if info.exists() and json.loads(info.read_text(encoding="utf-8")).get("token") == token:
            info.unlink()


def stop(directory):
    info = Path(directory) / ".progress-server.json"
    meta = json.loads(info.read_text(encoding="utf-8"))
    url = urlsplit(meta["url"])
    if url.hostname != "127.0.0.1" or url.scheme != "http":
        raise ValueError("로컬 진행 화면 주소가 아닙니다")
    request = Request(f"http://127.0.0.1:{url.port}/stop", method="POST", headers={"X-Harness-Token": meta["token"]})
    with urlopen(request, timeout=3) as response:
        print(response.read().decode())
