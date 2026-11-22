#!/usr/bin/env python3
"""Talpy Chat's New since … line (newsince.mjs, NewSinceLine.qml) checked in the real widget: rendered offscreen
(tools/render_popup.sh) on the made-up long chat (fake_chats.py, in a temporary home folder of its own), its
window driven by bench.qml's helpers.

    tools/bench/newsince.py [--shots DIR]

Since you last looked's answer is given to the window at the end of the chat (the line out of view above), then:
  - never seen, the line stays past 10 s at the end;
  - scrolled through, in view only while the list moves (a glimpse mid-scroll), and back: still not seen, it stays;
  - the bar's click: the line in view at the top, seen once the list is at rest;
  - on Steps, above the first step since;
  - seen: 5 s at the end, scrolled away before the 10 s (it stays), back at the end 10 s (it goes);
  - a new point; hidden, it goes; shown again with nothing new, there's none;
  - between two steps on Steps, within its row's room (not over the row above); on Chat, none there; closed, gone.
It exits 1 if a check fails (or the render gave no answer). --shots: a PNG of the main steps is kept in DIR.
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

CHECKS = 19

RUN = r'''
        function shot(win, name, cb) {
            const dir = "__SHOTS__"
            if (dir === "")
                return cb()
            win.contentItem.grabToImage(function(r) { r.saveToFile(dir + "/" + name + ".png"); cb() })
        }
        function check(what, ok, seen) { log("check", { ok: !!ok, what: what, seen: seen === undefined ? "" : seen }) }
        // the line's words, drawn: a Text that starts "New since", made and visible (in a row's gap or the head)
        function lineOf(win) {
            return find(win.contentItem, o => typeof o.text === "string" && o.text.indexOf("New since") === 0 && o.visible && o.width > 0)
        }
        function lineState(win) {
            const list = listOf(win), t = lineOf(win)
            const p = t ? t.mapToItem(list, 0, 0) : null
            return { line: t !== null, text: t ? t.text : "", inView: p !== null && p.y >= 0 && p.y + t.height <= list.height,
                     y: p ? Math.round(p.y) : -1, mark: win.newSince !== null, at: win.newSinceAt, bar: win.away !== null, atEnd: win.atEnd }
        }
        function toEnd(win) { const l = listOf(win); l.contentY = l.originY + l.contentHeight - l.height }
        function seenHere(win) { return win.newSince !== null && win.newSince.seen && win.newSince.seen[win.listTab === "steps" ? "steps" : "chat"] === true }
        // a scroll through the line, 16 ms a step (in view only while the list moves), then back to the end at once
        function sweep(win, row, cb) {
            const l = listOf(win), from = l.contentY, to = Math.max(l.originY, row.y - l.height * 2), steps = 30
            let i = 0
            const step = () => {
                i++
                l.contentY = from + (to - from) * i / steps
                if (i < steps)
                    after(16, step)
                else {
                    toEnd(win)
                    cb()
                }
            }
            step()
        }
        function runLine() {
            open(ids.long, "long chat", win => {
                when(() => win.loaded && win.lastItems.length > 40, () => after(2500, () => {
                    // where you left: the sixth reply from the end, the first step after the message before it
                    const items = win.lastItems
                    let n = 0, at = -1
                    for (let i = items.length - 1; i >= 0 && at < 0; i--)
                        if (items[i].kind === "claude" && !items[i].thinking && ++n === 6)
                            at = i
                    let j = at - 1
                    while (j >= 0 && items[j].kind === "tool")
                        j--
                    const key = String(items[at].key), stepKey = String(items[j + 1].key)
                    const since = (items[j] && items[j].at) || items[at].at - 60000
                    log("left", { key: key, stepKey: stepKey, items: items.length })
                    log("first read", lineState(win))   // (the made-up chat's own answer: since your last message)
                    toEnd(win)
                    win.tookAway({ from: "seen", since: since, key: key, stepKey: stepKey, steps: 9, replies: 3, files: ["src/parse.ts"],
                                   fileCount: 1, test: { command: "pytest -q", ok: true }, asks: "", partial: false })
                    after(11000, () => {
                        let s = lineState(win)
                        check("comes with Since you last looked, above where you left", s.mark && s.bar && s.at === key, s)
                        check("never seen: stays past 10 s at the end", s.mark && !seenHere(win) && s.atEnd && !s.inView, s)
                        check("says when you left", /^New since (\S+ )?\d{1,2}:\d{2}$/.test(s.text), s.text)
                        shot(win, "plasma-1-back-at-end", () => {
                            const row = find(listOf(win).contentItem, o => o.key === key && o.listed === true)
                            let glimpsed = false
                            const peek = () => { if (lineState(win).inView) glimpsed = true }
                            listOf(win).contentYChanged.connect(peek)
                            sweep(win, row, () => after(11000, () => {
                                listOf(win).contentYChanged.disconnect(peek)
                                s = lineState(win)
                                check("a glimpse mid-scroll isn't seen: stays past 10 s at the end", glimpsed && s.mark && !seenHere(win) && s.atEnd, { glimpsed: glimpsed, s: s })
                                goBack()
                            }))
                        })
                        function goBack() {
                            win.goAway()
                            after(2000, () => {
                                s = lineState(win)
                                check("after the jump: drawn, in view, the bar gone", s.line && s.inView && !s.bar && !s.atEnd, s)
                                check("after the jump, at rest: seen", seenHere(win), seenHere(win))
                                shot(win, "plasma-2-after-jump", () => {
                                    const l = listOf(win)
                                    l.contentY = Math.max(l.originY, l.contentY - 120)   // (a little above: what came before too)
                                    after(800, () => shot(win, "plasma-3-after-jump-context", () => {
                                        win.tab = "steps"
                                        after(1500, () => {
                                            s = lineState(win)
                                            check("on Steps: at the first step since", s.mark && s.at === stepKey, s)
                                            const row = find(listOf(win).contentItem, o => o.key === stepKey && o.listed === true)
                                            if (row)
                                                listOf(win).contentY = Math.max(listOf(win).originY, row.y - 160)
                                            after(1000, () => {
                                                s = lineState(win)
                                                check("on Steps: drawn", s.line, s)
                                                shot(win, "plasma-4-steps", () => {
                                                    win.tab = "chat"
                                                    after(800, () => readAtEnd(win))
                                                })
                                            })
                                        })
                                    }))
                                })
                            })
                        }
                    })
                }), 30000, "items")
            })
        }
        // scrolled up it stays; 10 s at the end with the window shown it goes; hidden it stays; a new point moves it
        function readAtEnd(win) {
            const l = listOf(win)
            toEnd(win)
            after(5000, () => {
                check("seen, 5 s at the end: still there", win.newSince !== null && win.atEnd, win.atEnd)
                l.contentY = l.originY
                after(7000, () => {
                check("seen, scrolled away before the 10 s: stays", win.newSince !== null && !win.atEnd, win.atEnd)
                toEnd(win)
                after(5000, () => {
                    check("back at the end 5 s: still there", win.newSince !== null && win.atEnd, win.atEnd)
                    after(5600, () => {
                        check("10 s at the end: gone", win.newSince === null && lineOf(win) === null, win.newSince === null)
                        shot(win, "plasma-5-read-gone", () => {
                            const items = win.lastItems
                            let k = ""
                            for (let i = items.length - 1; i >= 0 && !k; i--)
                                if (items[i].kind === "claude" && !items[i].thinking)
                                    k = String(items[i].key)
                            win.tookAway({ from: "seen", since: Date.now() - 600000, key: k, stepKey: k, steps: 2, replies: 1, files: [],
                                           fileCount: 0, test: null, asks: "", partial: false })
                            toEnd(win)
                            after(600, () => {
                                check("a new point, at the newest reply", win.newSince !== null && win.newSinceAt === k, win.newSinceAt === k)
                                win.visible = false
                                after(600, () => {
                                    check("hidden: gone", win.newSince === null, win.newSince === null)
                                    win.visible = true
                                    after(2500, () => {
                                        const s = lineState(win)
                                        check("shown again, nothing new: none", !s.mark && !s.line, s)
                                        stepGap(win)
                                    })
                                })
                            })
                        })
                    })
                })
            })
            })
        }
        // on Steps, a step right after a step (the least room above it): the line still drawn there
        function stepGap(win) {
            win.tab = "steps"
            after(1200, () => {
                const items = win.lastItems
                let tk = ""
                for (let i = items.length - 8; i > 0 && !tk; i--)
                    if (items[i].kind === "tool" && items[i - 1].kind === "tool")
                        tk = String(items[i].key)
                win.newSince = { key: "", stepKey: tk, since: Date.now() - 3600000, seen: { chat: false, steps: false } }
                after(600, () => {
                    const row = find(listOf(win).contentItem, o => o.key === tk && o.listed === true)
                    if (row)
                        listOf(win).contentY = Math.max(listOf(win).originY, row.y - 200)
                    after(1200, () => {
                        const s = lineState(win)
                        check("on Steps, right after a step: drawn there", s.line && s.at === tk && s.inView, s)
                        const t = lineOf(win), at = t ? t.mapToItem(row, 0, 0) : null
                        check("on Steps, right after a step: within the room above it", at !== null && at.y >= 0 && at.y + t.height <= row.gap + 0.5,
                              at ? { y: Math.round(at.y), h: Math.round(t.height), gap: Math.round(row.gap) } : null)
                        shot(win, "plasma-7-steps-step-gap", () => {
                            win.tab = "chat"
                            after(600, () => {
                                check("on Chat, nothing since there: none", lineOf(win) === null && win.newSinceAt === "", win.newSinceAt)
                                closeIt(win)
                            })
                        })
                    })
                })
            })
        }
        function closeIt(win) {
            win.close()
            after(800, () => {
                check("window closed: gone", win.newSince === null, win.newSince === null)
                done()
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
    work = Path(tempfile.mkdtemp(prefix="talpy-newsince-"))
    try:
        home = bench.home_for(work)   # (a made-up home: HOME and its folders are the render's own)
        ids = {"short": fake_chats.SHORT, "long": fake_chats.LONG, "turn": fake_chats.TURN, "folds": fake_chats.FOLDS}
        qml = (HERE / "bench.qml").read_text().replace("__SCENARIO__", "newsince").replace("__IDS__", json.dumps(ids)) \
            .replace("__IDLE_MS__", "1000")
        qml = qml.replace("        Component.onCompleted: {", RUN.replace("__SHOTS__", shots) + "\n        Component.onCompleted: {", 1)
        qml = qml.replace("first: () => open(", "newsince: runLine, first: () => open(", 1)
        env = bench.env_for(home)
        env.update(EXTRA=qml, PATCH="python3 -I " + str(HERE / "patch_pkg.py"), WIN_W="900", WIN_H="700")
        png, log = Path(work) / "popup.png", Path(work) / "popup.log"
        subprocess.run([str(REPO / "tools/render_popup.sh"), str(png), "220"], env=env, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, text=True)
        lines = bench.bench_lines(log) if log.exists() else []
        if not any(k == "check" for k, _ in lines) and log.exists():
            print("\n".join(l for l in log.read_text(errors="replace").splitlines() if "rror" in l or "BENCH" in l or "RENDER" in l)[-3000:])
    finally:
        shutil.rmtree(work, ignore_errors=True)
    checks = [d for k, d in lines if k == "check"]
    for d in checks:
        print(("ok   " if d["ok"] else "FAIL ") + d["what"] + ("" if d["ok"] else ": " + json.dumps(d.get("seen"))[:300]))
    if len(checks) != CHECKS or not all(d["ok"] for d in checks):
        sys.exit(f"newsince: {sum(not d['ok'] for d in checks)} of {len(checks)} checks failed ({CHECKS} expected), or the render gave no answer")


if __name__ == "__main__":
    main(sys.argv[1:])
