#!/usr/bin/env python3
"""The bar by a selection in Talpy Chat ("Reply to this", "Explain this"), checked in the real widget:
rendered offscreen (tools/render_popup.sh) on the made-up long chat (fake_chats.py, a home folder of its
own), with its list scrolled and rows put in above it by bench.qml's helpers.

    tools/bench/selbar.py [--shots DIR]

Text is selected across messages and the bar offered; then the bar's y is compared, each time, with where the
selection's last line really is (found from the text boxes, not from the pane's own anchor):
  - as the list scrolls a little (the bar moves with it), and far (out of view: hidden), and back;
  - after "Show earlier" put rows in above the selection (the bar stays with the text, not where it was);
  - scrolled to the selection again, where it was put (the bar is there, with it), and once more.
It exits 1 if the bar is anywhere else, or shown out of view. --shots: a PNG of each step is kept in DIR.
Nothing can reach a real chat (patch_pkg.py); your desktop isn't touched; offscreen only.
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))
import bench  # noqa: E402
import fake_chats  # noqa: E402

RUN = r'''
        function selShot(win, name, cb) {
            const dir = "__SHOTS__"
            if (dir === "")
                return cb()
            win.contentItem.grabToImage(function(r) { r.saveToFile(dir + "/" + name + ".png"); cb() })
        }
        // the bar's loader, and where the selection's last line really is, in the bar's parent (found from the
        // text boxes: the last row with something selected, the bottom of its selection's end), NaN for none
        function selBarOf(list) { return find(list.parent, o => o.barY !== undefined) }
        function selLineEnd(list, sc) {
            for (let i = list.count - 1; i >= 0; i--) {
                const d = list.itemAtIndex(i), b = d ? d.textBox : null
                if (b && b.selectedText !== "") {
                    const r = b.positionToRectangle(b.selectionEnd)
                    return b.mapToItem(sc, 0, r.y + r.height).y
                }
            }
            return NaN
        }
        function selCheck(win, list, name) {
            const bar = selBarOf(list), sc = bar ? bar.parent : list.parent
            const end = selLineEnd(list, sc), gap = 4
            const inView = end >= 0 && end <= sc.height - gap
            let ok, why = ""
            if (!bar)
                ok = false, why = "no bar"
            else if (!inView)
                ok = !bar.visible, why = "out of view, shown"
            else
                ok = bar.visible && Math.abs(bar.y - Math.min(end + gap, sc.height - Kirigami.Units.gridUnit * 2)) < 3, why = "bar at " + bar.y + ", line end " + end
            log("check", { name: name, ok: ok, why: ok ? "" : why, end: Math.round(end), barY: bar ? Math.round(bar.y) : null, visible: bar ? bar.visible : null })
        }
        function runSelBar() {
            open(ids.long, "long chat", win => {
                win.limit = 60
                win.stamp = ""
                win.load()
                when(() => win.loaded && win.lastItems.length >= 50, () => after(3000, () => {
                    const list = listOf(win)
                    const bottom = () => Math.max(list.originY, list.originY + list.contentHeight - list.height)
                    list.contentY = bottom() - 500
                    after(1500, () => {
                        let found = false
                        for (let y = 20; y < 200 && !found; y += 20) {
                            win.selectStart(Qt.point(40, y))
                            win.selectAcross(Qt.point(list.width - 60, list.height - 40))
                            if (win.selectionText().trim() !== "") {
                                const p = list.mapToItem(list.parent, list.width - 60, list.height - 40)
                                win.offerQuote(Qt.point(p.x, p.y))
                                found = true
                            }
                        }
                        log("selected", { found: found })
                        const y0 = list.contentY
                        const step = (name, move, next) => {
                            move()
                            after(1000, () => { selCheck(win, list, name); selShot(win, name, next) })
                        }
                        step("1-selected", () => {}, () =>
                        step("2-scrolled-120", () => list.contentY = y0 + 120, () =>
                        step("3-out-of-view", () => list.contentY = y0 + 480, () =>
                        step("4-back", () => list.contentY = y0, () => {
                            const before = win.lastItems.length
                            win.limit = 200
                            win.stamp = ""
                            win.load()
                            when(() => win.lastItems.length > before, () => after(2500, () =>
                                step("5-rows-above-inserted", () => {}, () =>
                                step("6-scrolled-to-it", () => list.contentY = list.contentY + selLineEnd(list, list.parent) - 250, () =>
                                step("7-then-scrolled-120", () => list.contentY = list.contentY + 120, () => done())))), 20000, "show earlier")
                        }))))
                    })
                }), 30000, "items")
            })
        }
'''


def main(argv):
    shots = ""
    if argv[:1] == ["--shots"] and len(argv) > 1:
        shots = str(Path(argv[1]).resolve())
        Path(shots).mkdir(parents=True, exist_ok=True)
    elif argv:
        sys.exit(__doc__)
    bench.wait_turn()
    work = Path(tempfile.mkdtemp(prefix="talpy-selbar-"))
    try:
        home = bench.home_for(work)
        ids = {"short": fake_chats.SHORT, "long": fake_chats.LONG, "turn": fake_chats.TURN, "folds": fake_chats.FOLDS}
        qml = (HERE / "bench.qml").read_text().replace("__SCENARIO__", "selbar").replace("__IDS__", json.dumps(ids)) \
            .replace("__IDLE_MS__", "1000")
        qml = qml.replace("        Component.onCompleted: {", RUN.replace("__SHOTS__", shots) + "\n        Component.onCompleted: {", 1)
        qml = qml.replace("first: () => open(", "selbar: runSelBar, first: () => open(", 1)
        env = bench.env_for(home)
        env.update(EXTRA=qml, PATCH="python3 -I " + str(HERE / "patch_pkg.py"), WIN_W="900", WIN_H="700")
        png, log = Path(work) / "popup.png", Path(work) / "popup.log"
        subprocess.run([str(REPO / "tools/render_popup.sh"), str(png), "90"], env=env, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, text=True)
        lines = bench.bench_lines(log) if log.exists() else []
        if not any(k == "check" for k, _ in lines) and log.exists():
            print("\n".join(l for l in log.read_text(errors="replace").splitlines() if "Error" in l or "BENCH" in l or "RENDER" in l)[-3000:])
    finally:
        shutil.rmtree(work, ignore_errors=True)
    checks = [d for k, d in lines if k == "check"]
    for d in checks:
        print(("ok   " if d["ok"] else "FAIL ") + d["name"] + ("" if d["ok"] else ": " + d["why"]) + f"  (line end {d['end']}, bar {d['barY']}, shown {d['visible']})")
    if len(checks) != 7 or not all(d["ok"] for d in checks) or not any(k == "selected" and d["found"] for k, d in lines):
        sys.exit("selbar: the bar is not where the selection is (or the render gave no answer)")


if __name__ == "__main__":
    main(sys.argv[1:])
