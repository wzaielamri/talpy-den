#!/usr/bin/env python3
"""Talpy Chat's New since … line (newsince.mjs) checked in VS Code's chat tab: the webview in its browser harness
(vscode/dev/chat.html, ?away=seen: Since you last looked's answer) in headless Firefox, driven step by step by
newsince_vscode.html.

    tools/bench/newsince_vscode.py [--no-build]

  - at the end of a long chat, the line out of view above: never seen, it stays past 10 s; it takes no room of its
    own and fits the room above its row;
  - scrolled through, in view only while the list moves (a glimpse mid-scroll), and back: still not seen, it stays;
  - the bar's click: the line in view at the top; on Steps, above the first step since; in the light theme too;
  - seen: 5 s at the end, scrolled away before the 10 s (it stays), back at the end 10 s (it goes);
  - another tab in front takes it; shown again with nothing new, none; back with more, at the new point;
  - Recap keeps it, a message you send takes it; a new tab with nothing new has none.
It exits 1 if a check fails (or the page gave no answer). It builds the extension and its harness first (node
esbuild.mjs, then --harness; vscode/node_modules must be there) unless --no-build. The browser runs with HOME and
its profile in a new, empty folder, removed after, and the page is served on 127.0.0.1 only.
TALPY_BENCH_CHROME=/path/to/chrome runs it in a Chromium instead (VS Code's own engine).
"""

import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))
import bench  # noqa: E402

CHECKS = 19


def main(argv):
    build = True
    if argv == ["--no-build"]:
        build = False
    elif argv:
        sys.exit(__doc__)
    if build:
        for args in (["node", "esbuild.mjs"], ["node", "esbuild.mjs", "--harness"]):
            r = subprocess.run(args, cwd=REPO / "vscode", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            if r.returncode:
                sys.exit(f"newsince_vscode: {' '.join(args)} failed:\n{r.stdout}")
    work = Path(tempfile.mkdtemp(prefix="talpy-newsince-vscode-"))
    result = {}
    got = threading.Event()
    try:
        page = (HERE / "newsince_vscode.html").read_bytes()

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *a, **kw):
                super().__init__(*a, directory=str(REPO), **kw)

            def do_GET(self):
                path = urllib.parse.urlparse(self.path)
                if path.path == "/result":
                    result.update(json.loads(urllib.parse.unquote(path.query)))
                    got.set()
                    body = b"ok"
                elif path.path == "/newsince.html":
                    body = page
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
        home, profile = work / "home", work / "profile"
        home.mkdir()
        profile.mkdir()
        env = bench.browser_env(home)   # (a made-up home: nothing of yours is read or written; no bus or display of yours)
        url = f"http://127.0.0.1:{server.server_port}/newsince.html"
        chrome = os.environ.get("TALPY_BENCH_CHROME")
        browser = subprocess.Popen([chrome, "--headless=new", f"--user-data-dir={profile}", "--no-first-run", "--window-size=800,760",
                                    *bench.CHROME_FLAGS, url]
                                   if chrome else
                                   ["firefox", "--headless", "--no-remote", "--profile", str(profile), "--window-size", "800,760", url],
                                   env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            if not got.wait(240):
                result["checks"] = [{"what": "an answer in 4 minutes", "ok": False, "seen": ""}]
        finally:
            browser.terminate()
            try:
                browser.wait(10)
            except subprocess.TimeoutExpired:
                browser.kill()
            server.shutdown()
    finally:
        shutil.rmtree(work, ignore_errors=True)
    checks = result.get("checks", [])
    for c in checks:
        print(("ok   " if c["ok"] else "FAIL ") + c["what"] + ("" if c["ok"] else ": " + c["seen"]))
    if len(checks) != CHECKS or not all(c["ok"] for c in checks):
        sys.exit(f"newsince_vscode: {sum(not c['ok'] for c in checks)} of {len(checks)} checks failed ({CHECKS} expected)")


if __name__ == "__main__":
    main(sys.argv[1:])
