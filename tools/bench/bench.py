#!/usr/bin/env python3
"""Talpy Chat's budgets in Plasma, measured the same way each time: the
widget from this repository rendered offscreen (tools/render_popup.sh) on
made-up chats (fake_chats.py, in a home folder of their own), with
bench.qml driving its Talpy Chat windows.

    tools/bench/bench.py [open|send|turn|scroll|idle|find|bookmarks|reads|all ...] [--out DIR] [--idle-seconds N] [--warm]

    open    opening a chat's window: first window, a new one, a closed one again (short and long chat)
    first   the first window only (open's first number, quicker: for comparing two packages often)
    send    Enter → your message shown (5 messages)
    turn    turn's end → shown, and → its chips drawn (5 turns appended line by line to a transcript)
    scroll  a 500-item chat scrolled end → top → end, on the Chat and Steps tabs
    idle    CPU of the offscreen plasmawindowed: no window, a window open, closed (60 s each)
    find    Talpy Chat's search on a 500-item chat (Steps tab): till all is searched, the longest the
            window waits meanwhile (a 5 ms timer's late ticks), steps to matches; and Ctrl+O on a chat
            of long replies and messages (fake_chats.make_folds, made for this scenario only)
    bookmarks  the long chat's 100 bookmarks: its window's first frame, then the one its ribbons show in;
            on 500 items, what each read costs them (place), a bookmark taken away and back (each
            one's frame), the list opened (first, then warm), Alt+↓, and a reach to the oldest one
    reads   pane.py --conversation from the shell (no window): the read alone

    --warm  each scenario runs twice with the widget's QML disk cache and data kept between them
            (render_popup.sh RENDER_KEEP), and the second is measured: as a real plasmashell has
            them after its first start. Without it, every run starts with a fresh cache

Nothing can reach a real chat: the home folder is a made-up one, and the
package copy's pane.py never sends, answers or presses keys (patch_pkg.py).
Your desktop isn't touched (no KWin, no plasmashell). One render at a time:
it waits while another plasmawindowed runs.

The numbers come from the software renderer on an offscreen screen: they're
for comparing a step with the one before it, on this computer, not what the
desktop shows.
"""

import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))
import fake_chats  # noqa: E402

SCENARIOS = ("open", "send", "turn", "scroll", "idle", "find", "first", "bookmarks")
SECONDS = {"open": 60, "send": 50, "turn": 70, "scroll": 90, "find": 90, "first": 30, "bookmarks": 150}   # (the render's limit; each ends sooner)
TICK = os.sysconf("SC_CLK_TCK")
RENDER_ID = "org.wzaielamri.talpyden.rendertest"


def ms():
    return time.time() * 1000


def others_rendering():
    return subprocess.run(["pgrep", "-x", "plasmawindowed"], stdout=subprocess.PIPE, text=True).stdout.split()


def wait_turn():
    """Wait (at most 10 minutes) while another plasmawindowed runs: one at a time."""
    for _ in range(60):
        if not others_rendering():
            return
        print("bench: another plasmawindowed runs, waiting…", flush=True)
        time.sleep(10)
    sys.exit("bench: another plasmawindowed is still running")


def home_for(work):
    """The made-up home: its chats, and your KDE colours and fonts (kdeglobals) for the look."""
    home = fake_chats.make(work / "home")
    (home / ".config").mkdir(exist_ok=True)
    real = Path.home() / ".config/kdeglobals"
    if real.is_file():
        shutil.copy(real, home / ".config/kdeglobals")
    return home


def env_for(home):
    """This environment with the made-up home, and none of your own XDG folders (render_popup.sh sets its own)."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("XDG_") or k in ("XDG_RUNTIME_DIR", "XDG_CONFIG_DIRS", "XDG_DATA_DIRS")}
    env["HOME"] = str(home)
    return env


def bench_lines(log):
    out = []
    for line in log.read_text(errors="replace").splitlines():
        m = re.search(r"BENCH (\w+) (\{.*\})\s*$", line)
        if m:
            out.append((m.group(1), json.loads(m.group(2))))
    return out


class Feeder(threading.Thread):
    """The turn test's Claude: on "BENCH feed n" in the log, turn n written to
    the turn chat's transcript a line at a time (0.25 s apart, its reply 1 s
    after the line before), as Claude writes them; when each was written."""

    def __init__(self, log, home):
        super().__init__(daemon=True)
        self.log, self.home, self.stop, self.written = log, home, False, {}

    def run(self):
        path, seen = fake_chats.transcript(self.home, fake_chats.TURN), 0
        while not self.stop:
            time.sleep(0.02)
            try:
                text = self.log.read_text(errors="replace")
            except OSError:
                continue
            asks = re.findall(r'BENCH feed \{"n":(\d+)\}', text)
            for n in asks[seen:]:
                lines = fake_chats.turn_lines(self.home, int(n))
                for i, line in enumerate(lines):
                    time.sleep(1.0 if i == len(lines) - 1 else 0.25)
                    with open(path, "a") as f:
                        f.write(line)
                    self.written[int(n)] = ms()   # (the last one's: the reply)
            seen = len(asks)


class Sampler(threading.Thread):
    """The render's CPU, from /proc every second: [(ms, own ticks, children's ticks)]."""

    def __init__(self):
        super().__init__(daemon=True)
        self.samples, self.stop, self.pid = [], False, None

    def run(self):
        for _ in range(600):
            r = subprocess.run(["pgrep", "-f", "^plasmawindowed " + RENDER_ID], stdout=subprocess.PIPE, text=True)
            if r.stdout.split():
                self.pid = int(r.stdout.split()[0])
                break
            time.sleep(0.1)
        while self.pid and not self.stop:
            try:
                f = Path(f"/proc/{self.pid}/stat").read_text()
            except OSError:
                return
            v = f[f.rfind(")") + 2:].split()
            self.samples.append((ms(), int(v[11]) + int(v[12]), int(v[13]) + int(v[14])))
            time.sleep(1)

    def at(self, t):
        """(own, children's) ticks at t ms, between the two samples around it."""
        s = self.samples
        for a, b in zip(s, s[1:]):
            if a[0] <= t <= b[0]:
                k = (t - a[0]) / (b[0] - a[0]) if b[0] > a[0] else 0
                return a[1] + k * (b[1] - a[1]), a[2] + k * (b[2] - a[2])
        return None


def render(scenario, out, idle_s, keep=None):
    """One render driving scenario: its BENCH lines, the feeder's times, the CPU samples (keep: the
    folder whose QML cache and data the render keeps for the next one)."""
    wait_turn()
    work = Path(tempfile.mkdtemp(prefix="talpy-bench-"))
    try:
        home = home_for(work)
        ids = {"short": fake_chats.SHORT, "long": fake_chats.LONG, "turn": fake_chats.TURN, "folds": fake_chats.FOLDS}
        if scenario == "find":
            fake_chats.make_folds(home)
        extra = (HERE / "bench.qml").read_text().replace("__SCENARIO__", scenario) \
            .replace("__IDS__", json.dumps(ids)).replace("__IDLE_MS__", str(int(idle_s * 1000)))
        env = env_for(home)
        env.update(EXTRA=extra, PATCH="python3 -I " + str(HERE / "patch_pkg.py"))
        if keep:
            env["RENDER_KEEP"] = str(keep)
        png = out / f"{scenario}.png"
        log = out / f"{scenario}.log"
        secs = SECONDS.get(scenario, int(3 * idle_s + 60))
        feeder = Feeder(log, home) if scenario == "turn" else None
        sampler = Sampler() if scenario == "idle" else None
        proc = subprocess.Popen([str(REPO / "tools/render_popup.sh"), str(png), str(secs)], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for t in (feeder, sampler):
            if t:
                t.start()
        said = proc.communicate()[0]
        for t in (feeder, sampler):
            if t:
                t.stop = True
        lines = bench_lines(log) if log.exists() else []
        if not lines:
            print(f"bench: {scenario}: no BENCH lines (another render running?):\n{said}", file=sys.stderr)
        return lines, feeder.written if feeder else {}, sampler
    finally:
        shutil.rmtree(work, ignore_errors=True)


def median(xs):
    xs = [x for x in xs if x is not None and x >= 0]
    return round(statistics.median(xs), 1) if xs else None


def report_open(lines):
    by = {}
    for kind, d in lines:
        if kind == "open":
            by.setdefault(d["label"], []).append(d)
    out = {}
    for label, runs in by.items():
        out[label] = {k: median([r.get(k) for r in runs]) for k in ("call", "loaded", "visible", "frame", "dataFrame")}
        out[label]["items"] = runs[0].get("items")
        out[label]["runs"] = len(runs)
    return out


def report_send(lines):
    runs = [d for k, d in lines if k == "send"]
    return {"runs": len(runs), "call_ms": median([r["call"] for r in runs]), "frame_ms": median([r["frame"] for r in runs]),
            "max_frame_ms": max((r["frame"] for r in runs), default=None),
            "shown_as_pending": all(str(r["last"]).startswith("pending-") for r in runs) if runs else False,
            "box_emptied": all(r["boxAfter"] == "" for r in runs) if runs else False}


def report_turn(lines, written):
    runs = [d for k, d in lines if k == "turn"]
    ins = [d["in"] - written[d["n"]] for d in runs if "in" in d and d["n"] in written]
    frames = [d["frame"] - written[d["n"]] for d in runs if d.get("frame", -1) > 0 and d["n"] in written]
    # (Talpy Chat's chips for the reply's question: the frame they're drawn in; none before step 2)
    chips = [d["frame"] - written[d["n"]] for k, d in lines if k == "chips" and d["n"] in written]
    return {"runs": len(runs), "timeouts": sum(1 for d in runs if d.get("timeout")),
            "in_ms": median(ins), "frame_ms": median(frames), "max_frame_ms": round(max(frames), 1) if frames else None,
            "all_frame_ms": [round(x) for x in frames], "chips_frame_ms": median(chips),
            "max_chips_frame_ms": round(max(chips), 1) if chips else None, "chips_runs": len(chips)}


def report_scroll(lines):
    return {d["tab"]: d for k, d in lines if k == "scroll"}


def report_idle(lines, sampler):
    marks = {d["name"]: d for k, d in lines if k == "mark"}
    out = {}
    for phase in ("none", "open", "closed"):
        a, b = marks.get(phase + "-start"), marks.get(phase + "-end")
        if not (a and b and sampler):
            continue
        ta, tb = sampler.at(a["t"]), sampler.at(b["t"])
        if not (ta and tb):
            continue
        secs = (b["t"] - a["t"]) / 1000
        out[phase] = {"seconds": round(secs), "cpu_own_pct": round((tb[0] - ta[0]) / TICK / secs * 100, 2),
                      "cpu_children_pct": round((tb[1] - ta[1]) / TICK / secs * 100, 2),
                      "popup_frames_per_min": round((b["popupFrames"] - a["popupFrames"]) / secs * 60),
                      "pane_frames_per_min": round((b["paneFrames"] - a["paneFrames"]) / secs * 60)}
    return out


def report_find(lines):
    out = {}
    for kind, d in lines:
        if kind in ("search", "steps", "foldAll"):
            out.setdefault(kind, []).append(d)
    return out


def report_bookmarks(lines):
    out = {}
    for kind, d in lines:
        if kind in ("bookmarksOpen", "place", "placeMade", "scroll", "toggle", "list", "pill", "step", "reach", "earlier", "bookmarks"):
            out.setdefault(kind, []).append(d)
    return out


def report_reads():
    """pane.py --conversation run from the shell on the made-up chats: its read alone (median of 5, ms),
    with its modules compiled once and kept, as the installed widget's are (pane.py: pycache)."""
    work = Path(tempfile.mkdtemp(prefix="talpy-bench-"))
    try:
        home = fake_chats.make(work / "home")
        env = env_for(home)
        env["XDG_DATA_HOME"] = str(work / "data")
        (work / "data/talpy-den/pycache").mkdir(parents=True)
        code = REPO / "package/contents/code"
        subprocess.run(["python3", "-I", str(code / "pane.py"), "--conversation", fake_chats.SHORT], env=env,
                       stdout=subprocess.DEVNULL)   # (compiled once)
        out = {}
        for label, sid, limit in (("short chat, 120", fake_chats.SHORT, 120), ("long chat, 120", fake_chats.LONG, 120),
                                  ("long chat, 500", fake_chats.LONG, 500)):
            times = []
            for _ in range(5):
                t = ms()
                r = subprocess.run(["python3", "-I", str(code / "pane.py"), "--conversation", sid,
                                    "--limit", str(limit)], env=env, stdout=subprocess.PIPE, text=True)
                times.append(ms() - t)
                answer = json.loads(r.stdout)
            out[label] = {"ms": median(times), "items": len(answer.get("items", [])), "bytes": len(r.stdout)}
        return out
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv):
    args, out, idle_s, warm = [], None, 60.0, False
    while argv:
        a = argv.pop(0)
        if a == "--out" and argv:
            out = Path(argv.pop(0))
        elif a == "--idle-seconds" and argv:
            idle_s = float(argv.pop(0))
        elif a == "--warm":
            warm = True
        elif a in SCENARIOS + ("reads", "all"):
            args.append(a)
        else:
            sys.exit(__doc__)
    todo = [s for s in ("reads",) + SCENARIOS if ("all" in args and s != "first") or s in args] or sys.exit(__doc__)
    out = out or Path(tempfile.mkdtemp(prefix="talpy-bench-out-"))
    out.mkdir(parents=True, exist_ok=True)
    load = os.getloadavg()[0]
    if load > (os.cpu_count() or 1) / 2:
        print(f"bench: the computer is busy (load {load:.1f}): the numbers will be slower than usual", flush=True)
    results = {"when": time.strftime("%Y-%m-%d %H:%M"), "load": round(load, 1), "commit": subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], stdout=subprocess.PIPE, text=True).stdout.strip(),
        "warm": warm}
    for s in todo:
        if s == "reads":
            results["reads"] = report_reads()
        else:
            keep = None
            if warm:   # (a first run fills the QML cache and the data; the second is measured)
                keep = out / f"keep-{s}"
                shutil.rmtree(keep, ignore_errors=True)
                keep.mkdir(parents=True)
                render(s, out, idle_s, keep)
            lines, written, sampler = render(s, out, idle_s, keep)
            if not lines:   # (another session's render took plasmawindowed: once more, after it)
                time.sleep(30)
                lines, written, sampler = render(s, out, idle_s, keep)
            if keep:
                shutil.rmtree(keep, ignore_errors=True)
            results[s] = {"open": lambda: report_open(lines), "first": lambda: report_open(lines), "send": lambda: report_send(lines),
                          "turn": lambda: report_turn(lines, written), "scroll": lambda: report_scroll(lines),
                          "idle": lambda: report_idle(lines, sampler), "find": lambda: report_find(lines),
                          "bookmarks": lambda: report_bookmarks(lines)}[s]()
            if s != "open":
                results[s]["window"] = report_open(lines)
        print(f"{s}: {json.dumps(results[s], indent=1)}", flush=True)
    (out / "results.json").write_text(json.dumps(results, indent=1))
    print(f"bench: results and logs in {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
