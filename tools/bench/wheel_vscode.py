#!/usr/bin/env python3
"""bench.py wheel's inputs in VS Code's chat tab: the webview in its browser
harness (vscode/dev/chat.html) in a headless Chromium (VS Code's engine),
given the made-up 500-item chat as pane.py reads it, driven over the devtools
protocol (wheel_vscode.mjs). Every frame's step, and how even they are, as
bench.py wheel reports them; and what a frame costs while it moves 12 px a
frame (the page's script, layout and style, from Chromium's own counters).

    tools/bench/wheel_vscode.py [--out DIR] [--no-build]

The Chromium: TALPY_BENCH_CHROME, else Playwright's (~/.cache/ms-playwright).
It builds the extension and its harness first (node esbuild.mjs, then
--harness; vscode/node_modules must be there). What the protocol can give differs from a desktop's: a notch
is a wheel event Chromium animates (not precise), 100 px; a touchpad's
events are precise pixel deltas, each its own short gesture (no phases), so
Chromium applies each as it comes, at the next frame.
"""

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))
import bench  # noqa: E402
import vscode_bench  # noqa: E402


def chrome():
    given = os.environ.get("TALPY_BENCH_CHROME")
    if given:
        return given
    found = sorted(Path.home().glob(".cache/ms-playwright/chromium-*/chrome-linux64/chrome"))
    return str(found[-1]) if found else None


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
    browser = chrome() or sys.exit("wheel_vscode: no Chromium (TALPY_BENCH_CHROME)")
    if build:   # (the extension, for its styles, then its harness)
        for args in (["node", "esbuild.mjs"], ["node", "esbuild.mjs", "--harness"]):
            r = subprocess.run(args, cwd=REPO / "vscode", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            if r.returncode:
                sys.exit(f"wheel_vscode: {' '.join(args)} failed:\n{r.stdout}")
    work = Path(tempfile.mkdtemp(prefix="talpy-wheel-"))
    try:
        data = work / "long500.json"
        data.write_text(json.dumps(vscode_bench.conversations(work)["long500"]))
        # (no session bus or display of yours; node and its Chromium in a session of their own: if it hangs,
        # all of it ends with it)
        env = bench.browser_env(work / "home")
        env["TALPY_CHROME_FLAGS"] = " ".join(bench.CHROME_FLAGS)
        node = subprocess.Popen(["node", str(HERE / "wheel_vscode.mjs"), str(REPO), str(data), browser],
                                stdout=subprocess.PIPE, text=True, env=env, start_new_session=True)
        try:
            stdout = node.communicate(timeout=300)[0]
        except subprocess.TimeoutExpired:
            os.killpg(node.pid, signal.SIGKILL)
            stdout = node.communicate()[0] + "\nerror timed out"
    finally:
        shutil.rmtree(work, ignore_errors=True)
    result = {"when": time.strftime("%Y-%m-%d %H:%M"), "load": round(os.getloadavg()[0], 1), "motion": {}, "pace": {}}
    for line in stdout.splitlines():
        what, _, rest = line.partition(" ")
        if what == "error":
            result["error"] = rest
        elif what == "motion":
            d = json.loads(rest)
            ys = d["ys"]
            steps = bench.steps_of(ys)
            first = next((i for i, (a, b) in enumerate(zip(ys, ys[1:])) if abs(a - b) > 0.001), None)
            mid = [abs(s) for s in steps[3:-8]] if len(steps) > 14 else []
            mean = sum(mid) / len(mid) if mid else 0
            result["motion"][d["label"]] = {
                "steps": [round(s, 2) for s in steps], "distance": round(ys[0] - ys[-1], 1), "frames": len(steps),
                "still_frames_inside": sum(1 for s in steps if abs(s) < 0.001), "turns": bench.turns([abs(s) for s in steps]),
                "max_step": max((abs(s) for s in steps), default=0),
                "mid_cv_pct": round((sum((x - mean) ** 2 for x in mid) / len(mid)) ** 0.5 / mean * 100, 1) if mean else None,
                "frame_ms": d["ts"][first:first + 12] if first is not None else [], "hover_changes": d.get("hoverChanges"),
                **({"scrollbar": d["scrollbar"]} if "scrollbar" in d else {})}
        elif what == "pace":
            d = json.loads(rest)
            result["pace"][d.pop("label")] = d
    print(json.dumps(result, indent=1))
    if out:
        out.mkdir(parents=True, exist_ok=True)
        (out / "wheel_vscode.json").write_text(json.dumps(result, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
