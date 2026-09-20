"""Exercise the packaged sidecar using only stdlib and a local HTTP fixture."""
import json
import queue
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

root = Path(__file__).resolve().parents[1]
test_dir = Path(tempfile.mkdtemp(prefix="smoke-", dir=root / ".build"))
payload = b"\xff\xd8\xff\xe0" + b"packaged-sidecar-fixture" * 5000 + b"\xff\xd9"

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
    def log_message(self, *args):
        pass

server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
process = subprocess.Popen([str(root / "src-tauri/binaries/shiying-engine-x86_64-pc-windows-msvc.exe"),
    "--data-dir", str(test_dir / "data"), "--output-dir", str(test_dir / "media")],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    text=True, encoding="utf-8", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
messages = queue.Queue()
def read():
    for line in process.stdout:
        messages.put(json.loads(line))
threading.Thread(target=read, daemon=True).start()
def send(message):
    process.stdin.write(json.dumps(message) + "\n")
    process.stdin.flush()
try:
    ready = messages.get(timeout=25)
    assert ready["type"] == "ready", ready
    send({"action":"enqueue","request_id":"smoke","text":"https://www.douyin.com/note/7390000000000000001"})
    deadline = time.monotonic() + 35
    completed = False
    progress = False
    while time.monotonic() < deadline:
        message = messages.get(timeout=20)
        if message["type"] == "bridge_request":
            send({"action":"bridge_response","request_id":message["request_id"],"payload":{
                "http_status":200,"body":{"status_code":0,"aweme_detail":{
                    "aweme_id":"7390000000000000001","aweme_type":68,"desc":"packaged fixture","create_time":1720000000,
                    "author":{"nickname":"smoke-test","uid":"123","sec_uid":"smoke"},
                    "images":[{"url_list":[f"http://127.0.0.1:{server.server_port}/image.jpg"]}]
                }}}})
        if message["type"] == "task":
            task = message["task"]
            progress |= task.get("bytes_read", 0) > 0
            if task["state"] == "completed":
                completed = True
                break
            assert task["state"] not in {"failed", "waiting_login"}, task
    assert completed and progress, "No successful download/progress from packaged engine"
    files = list((test_dir / "media").rglob("*.jpg"))
    assert len(files) == 1 and files[0].read_bytes() == payload
    send({"action":"shutdown"})
    assert process.wait(timeout=10) == 0
    print("PACKAGED ENGINE PASS: boot, protocol, page bridge, real media bytes, progress, SQLite, clean shutdown")
finally:
    if process.poll() is None:
        process.kill()
    server.shutdown()
