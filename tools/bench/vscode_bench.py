#!/usr/bin/env python3
"""Talpy Chat's budgets in VS Code's chat tab, the same way each time: the
webview in its browser harness (vscode/dev/chat.html) in headless Firefox,
given the made-up chats (fake_chats.py) as pane.py reads them, and timed
with performance.now() (vscode_bench.html).

    tools/bench/vscode_bench.py [--out DIR] [--no-build]

- render: a conversation posted to an empty list (16, 120 and 500 items):
  in the page and laid out, then painted (the frame after), ms;
- scroll: the 500-item chat, 120 px a frame, end → top → end (Chat tab);
- send: Enter in the reply box → your message in the list.

It builds the extension and its harness first (node esbuild.mjs, then
--harness; vscode/node_modules must be there). Firefox runs with a new,
empty profile, and the page is served on 127.0.0.1 only. Like bench.py's,
these numbers are for comparing one step with the one before, on this
computer: Firefox isn't VS Code's Chromium.
"""

import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))
import bench  # noqa: E402
import fake_chats  # noqa: E402


def conversations(work):
    """{name: pane.py's answer} for the made-up chats, as the extension gets them."""
    home = fake_chats.make(work / "home")
    env = bench.env_for(home)
    out = {}
    for name, sid, limit in (("short", fake_chats.SHORT, 120), ("long", fake_chats.LONG, 120),
                             ("long500", fake_chats.LONG, 500)):
        r = subprocess.run(["python3", "-I", str(REPO / "package/contents/code/pane.py"), "--conversation", sid,
                            "--limit", str(limit)], env=env, stdout=subprocess.PIPE, text=True, check=True)
        out[name] = json.loads(r.stdout)
    return out


def main(argv):
    out, build = None, True
    while argv:
        a = argv.pop(0)
        if a == "--out" and argv:
            out = Path(argv.pop(0))
        elif a == "--no-build":
            build = False
        else:
            sys.exit(__doc__)
    if build:
        for args in (["node", "esbuild.mjs"], ["node", "esbuild.mjs", "--harness"]):
            r = subprocess.run(args, cwd=REPO / "vscode", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            if r.returncode:
                sys.exit(f"bench: {' '.join(args)} failed:\n{r.stdout}")
    work = Path(tempfile.mkdtemp(prefix="talpy-bench-"))
    result = {}
    got = threading.Event()
    try:
        data = conversations(work)
        page = (HERE / "vscode_bench.html").read_bytes()

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *a, **kw):
                super().__init__(*a, directory=str(REPO), **kw)

            def do_GET(self):
                path = urllib.parse.urlparse(self.path)
                if path.path == "/result":
                    result.update(json.loads(urllib.parse.unquote(path.query)))
                    got.set()
                    body = b"ok"
                elif path.path == "/bench.html":
                    body = page
                elif path.path.startswith("/bench-data/"):
                    body = json.dumps(data[Path(path.path).stem]).encode()
                else:
                    return super().do_GET()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        profile = work / "firefox"
        profile.mkdir()
        fox = subprocess.Popen(["firefox", "--headless", "--no-remote", "--profile", str(profile), "--window-size", "760,960",
                                f"http://127.0.0.1:{server.server_port}/bench.html"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            if not got.wait(180):
                result["error"] = "no result in 3 minutes"
        finally:
            fox.terminate()
            try:
                fox.wait(10)
            except subprocess.TimeoutExpired:
                fox.kill()
            server.shutdown()
    finally:
        shutil.rmtree(work, ignore_errors=True)
    result = {"when": time.strftime("%Y-%m-%d %H:%M"), "load": round(os.getloadavg()[0], 1), **result}
    print(json.dumps(result, indent=1))
    if out:
        out.mkdir(parents=True, exist_ok=True)
        (out / "vscode.json").write_text(json.dumps(result, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
