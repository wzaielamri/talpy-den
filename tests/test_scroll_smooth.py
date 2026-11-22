"""Talpy Chat's conversation scrolls at an even pace (Plasma): the wheel and the
touchpad move it a step a frame, evenly, by whole pixels, and nothing runs once
it's still (package/contents/ui/WheelScroll.qml, wheel.mjs; their arithmetic:
vscode/test/wheel.test.ts).

Kirigami's WheelHandler, every Plasma scroll view's, started an ease of its own
at each event from where the list was: in a quick spin each notch threw the
list forward again (a frame's step went 10, 20, 16, 13, 22, 18, 15, 24 px…), a
touchpad's stream was a chain of 50 ms eases (steps up and down, now and then a
frame that didn't move), and as the fingers lifted its glide began at less than
half the speed. Run here as Talpy Chat's list is (a ListView in a
PlasmaComponents3.ScrollView, with what ChatPane.qml gives its list for the
wheel), offscreen on Qt Quick's threaded loop, given the events as Plasma's
Wayland gives them (a notch's 120; a touchpad's phases, its pixels and its angle
12 a pixel) at their times, the list's place read once a frame.
"""
import claude_guard  # noqa: F401  (first: no test runs the real claude)
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "package/contents/ui"
PANE = (UI / "ChatPane.qml").read_text()
FRAME = 1000 / 60.03

NEEDS_QT = unittest.skipUnless(subprocess.run(
    ["python3", "-c", "import PySide6.QtQuick"], capture_output=True).returncode == 0, "needs PySide6")


def the_list():
    """The conversation's ListView in ChatPane.qml, as text."""
    at = PANE.index("                ListView {\n                    id: list\n")
    end = PANE.index("\n                    header: Item {", at)
    return PANE[at:end]


def what_the_list_has_for_the_wheel():
    """ChatPane's list's own scroller, as the scene below gives it to its list (none: Kirigami's alone)."""
    m = re.search(r"\n(\s*)WheelScroll \{\n.*?\n\1\}", the_list(), re.S)
    return "WheelScroll { id: wheelScroll; flickable: list }" if m and "flickable: list" in m.group(0) else ""


RUNNER = r"""
import json, sys, time
from PySide6.QtCore import QPoint, QPointF, Qt, QTimer, QUrl
from PySide6.QtGui import QGuiApplication, QWheelEvent
from PySide6.QtQuick import QQuickView

runs = json.loads(open(sys.argv[2]).read())
app = QGuiApplication(sys.argv)
view = QQuickView()
view.setSource(QUrl.fromLocalFile(sys.argv[1]))
if view.status() != QQuickView.Ready:
    print("ERROR", [e.toString() for e in view.errors()])
    sys.exit(1)
view.show()
root = view.rootObject()
out, state = [], {"run": 0, "i": 0, "t0": 0.0}
PHASE = {"none": Qt.NoScrollPhase, "begin": Qt.ScrollBegin, "update": Qt.ScrollUpdate, "end": Qt.ScrollEnd}


def start():
    if state["run"] >= len(runs):
        print("RESULT", json.dumps(out))
        app.quit()
        return
    root.setProperty("startY", 6000 + state["run"])
    QTimer.singleShot(500, go)


def go():
    root.setProperty("on", True)
    state["i"], state["t0"] = 0, time.perf_counter()
    pump.start()


def tick():
    events = runs[state["run"]]["events"]
    now = (time.perf_counter() - state["t0"]) * 1000
    while state["i"] < len(events) and events[state["i"]][0] <= now:
        t, phase, angle, pixel = events[state["i"]]
        src = Qt.MouseEventNotSynthesized if phase == "none" else Qt.MouseEventSynthesizedBySystem
        ev = QWheelEvent(QPointF(300, 350), QPointF(300, 350), QPoint(0, pixel), QPoint(0, angle), Qt.NoButton,
                         Qt.NoModifier, PHASE[phase], False, src)
        ev.setTimestamp(int(t))
        QGuiApplication.sendEvent(view, ev)
        state["i"] += 1
    if state["i"] >= len(events):
        pump.stop()
        QTimer.singleShot(900, finish)


def finish():
    root.setProperty("on", False)
    get = lambda k: [float(x) for x in (lambda v: v.toVariant() if hasattr(v, "toVariant") else v)(root.property(k))]
    out.append({"label": runs[state["run"]]["label"], "ys": get("ys"), "ts": get("ts"), "idle": root.property("idle")})
    state["run"] += 1
    QTimer.singleShot(300, start)


pump = QTimer()
pump.setTimerType(Qt.PreciseTimer)
pump.setInterval(1)
pump.timeout.connect(tick)
QTimer.singleShot(1500, start)
app.exec()
"""


def touchpad(hz, speed, ms, start=5.3):
    """Wayland's: a ScrollBegin, a move a report (its pixels, the rest carried, and its angle, 12 a pixel),
    a ScrollEnd as the fingers lift."""
    out, rest, t = [[start, "begin", 0, 0]], 0.0, start
    while t <= start + ms + 1e-9:
        d = speed / hz
        px = round(d + rest)
        rest += d - px
        out.append([t, "update", round(12 * d), px])
        t += 1000 / hz
    out.append([start + ms + 1000 / hz, "end", 0, 0])
    return out


RUNS = [{"label": "notch", "events": [[0, "none", 120, 0]]},
        {"label": "spin", "events": [[i * 50, "none", 120, 0] for i in range(6)]},
        {"label": "touchpad 90", "events": touchpad(90, 200, 600)},
        {"label": "touchpad 125", "events": touchpad(125, 200, 600)}]


def run_scene(wheel):
    """The runs above in a list as Talpy Chat's; each run's place a frame (an animation step that came less than
    0.6 of a frame after the one before isn't a frame of its own: the loop steps again when a step changed
    nothing; it isn't drawn apart from the next)."""
    scene = """
import QtQuick
import org.kde.plasma.components as PlasmaComponents3
import "%s"
Item {
    id: root
    width: 600; height: 700
    property var ys: []
    property var ts: []
    property bool on: false
    property real startY: -1
    readonly property bool idle: wheel === null || !wheel.frames.running
    property QtObject wheel: %s
    onStartYChanged: list.contentY = startY
    onOnChanged: if (on) { ys = [list.contentY]; ts = [Date.now()] }
    PlasmaComponents3.ScrollView {
        anchors.fill: parent
        ListView {
            id: list
            model: 400
            pixelAligned: true
            cacheBuffer: 100000
            boundsBehavior: Flickable.StopAtBounds
            clip: true
            delegate: Item {
                width: ListView.view.width
                height: 30 + (index * 37) %% 70
                Text { anchors.fill: parent; anchors.margins: 4; text: "Line " + index; wrapMode: Text.Wrap }
            }
            %s
        }
    }
    function sample() { if (on) { ys.push(list.contentY); ts.push(Date.now()) } }
    FrameAnimation { running: root.on; onTriggered: Qt.callLater(root.sample) }
}
""" % (UI.as_uri(), "wheelScroll" if wheel else "null", wheel)
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "scene.qml").write_text(scene)
        (Path(tmp) / "runs.json").write_text(json.dumps(RUNS))
        (Path(tmp) / "run.py").write_text(RUNNER)
        env = {k: v for k, v in os.environ.items() if k not in ("WAYLAND_DISPLAY", "DISPLAY", "QT_QPA_PLATFORMTHEME")}
        # (no D-Bus at all: nothing to start on any bus; offscreen, drawn on a thread of its own as plasmashell draws)
        env.update(QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", QSG_RENDER_LOOP="threaded",
                   DBUS_SESSION_BUS_ADDRESS="unix:path=/nonexistent/bus")
        r = subprocess.run(["python3", str(Path(tmp) / "run.py"), str(Path(tmp) / "scene.qml"), str(Path(tmp) / "runs.json")],
                           capture_output=True, text=True, timeout=90, env=env)
    line = next((x for x in r.stdout.splitlines() if x.startswith("RESULT ")), None)
    if not line:
        raise AssertionError(r.stdout[-2000:] + r.stderr[-3000:])
    out = {}
    for d in json.loads(line[len("RESULT "):]):
        ys, kept = [d["ys"][0]], [d["ts"][0]]
        for y, t in zip(d["ys"][1:], d["ts"][1:]):
            if len(ys) > 1 and t - kept[-1] < 0.6 * FRAME:
                ys[-1] = y
            else:
                ys.append(y)
                kept.append(t)
        steps = [a - b for a, b in zip(ys, ys[1:])]
        moving = [k for k, s in enumerate(steps) if abs(s) > 1e-6]
        out[d["label"]] = {"ys": d["ys"], "steps": steps[moving[0]:moving[-1] + 1] if moving else [], "idle": d["idle"]}
    return out


def turns(steps, tol=1.5):
    """How often the steps go from growing to shrinking or back by more than whole-pixel rounding."""
    n, trend, extreme = 0, 0, steps[0]
    for s in steps[1:]:
        if trend >= 0 and s < extreme - tol:
            n, trend, extreme = n + (trend > 0), -1, s
        elif trend <= 0 and s > extreme + tol:
            n, trend, extreme = n + (trend < 0), 1, s
        elif (trend >= 0 and s > extreme) or (trend <= 0 and s < extreme):
            extreme = s
    return n


class TheListsWheelTests(unittest.TestCase):
    """Read as text: what ChatPane gives its list, and what WheelScroll.qml runs (nothing while it's still)."""

    def test_the_conversation_has_its_own_scroller(self):
        self.assertEqual(what_the_list_has_for_the_wheel(), "WheelScroll { id: wheelScroll; flickable: list }")
        self.assertIn("readonly property QtObject wheelScroller: wheelScroll", the_list())

    def test_the_hovered_message_holds_while_the_wheel_moves_the_list(self):
        # (its tools go with their message till the list rests, as a browser's do: they hopped to each message
        # that passed under the pointer, three in a touchpad's 0.6 s, and the binding ran every frame)
        hover = the_list()[the_list().index("property Item hoverRow: {"):]
        hover = hover[:hover.index("onHoverRowChanged")]
        self.assertLess(hover.index("if (wheelScroll.moving)\n"), hover.index("void list.contentY"))
        self.assertIn("return heldRow", hover)
        self.assertIn("onStarting: list.heldRow = list.hoverRow", the_list())
        ws = (UI / "WheelScroll.qml").read_text()
        self.assertIn("readonly property bool moving: frames.running", ws)
        self.assertLess(ws.index("handler.starting()"), ws.index("first = true"))

    def test_it_takes_the_wheel_and_the_touchpad_with_no_key_held(self):
        ws = (UI / "WheelScroll.qml").read_text()
        self.assertIn("acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad", ws)
        self.assertIn("acceptedModifiers: Qt.NoModifier", ws)   # (Ctrl: the text's size; Shift, Alt: Kirigami's)
        self.assertIn("Application.styleHints.wheelScrollLines * 20", ws)   # (a notch: the desktop's lines)

    def test_its_arithmetic_is_es2017(self):
        code = re.sub(r"//.*", "", (UI / "wheel.mjs").read_text())   # (QML imports it as it is)
        self.assertNotIn("?.", code)
        self.assertNotIn("??", code)

    def test_it_runs_only_while_it_moves_and_by_whole_pixels(self):
        ws = (UI / "WheelScroll.qml").read_text()
        self.assertNotIn("Timer {", ws)
        self.assertRegex(ws, r"FrameAnimation \{\n\s*running: false\n")
        self.assertIn("frames.running = false", ws)
        self.assertIn("written = Math.round(y)", ws)
        self.assertNotIn("Behavior on", ws)


@NEEDS_QT
class TheListScrollsEvenlyTests(unittest.TestCase):
    """Run: the list as Talpy Chat's, given the wheel's and the touchpad's events as Wayland does."""

    @classmethod
    def setUpClass(cls):
        cls.runs = run_scene(what_the_list_has_for_the_wheel())

    def test_a_notch_is_the_desktops_lines_its_steps_only_fall_by_whole_pixels(self):
        r = self.runs["notch"]
        self.assertEqual(sum(r["steps"]), 60, r["steps"])
        self.assertTrue(all(b <= a + 1 for a, b in zip(r["steps"], r["steps"][1:])), r["steps"])
        self.assertTrue(all(y == round(y) for y in r["ys"]), r["ys"])

    def test_a_spin_keeps_its_pace(self):
        r = self.runs["spin"]
        self.assertEqual(sum(r["steps"]), 360, r["steps"])
        self.assertLessEqual(turns(r["steps"]), 2, r["steps"])   # (Kirigami's: 9 or 10)
        self.assertNotIn(0, r["steps"])

    def test_a_touchpads_stream_moves_it_every_frame_evenly(self):
        for label in ("touchpad 90", "touchpad 125"):
            r = self.runs[label]
            steps = r["steps"]
            self.assertNotIn(0, steps, label)   # (Kirigami's: a frame now and then that didn't move)
            mid = steps[10:34]
            pace = sorted(mid)[len(mid) // 2]
            off = [s for s in mid if abs(s - pace) > 0.15 * pace + 1]
            self.assertLessEqual(len(off), 3, f"{label}: {mid}")
            self.assertTrue(all(y == round(y) for y in r["ys"]), label)

    def test_as_the_fingers_lift_it_glides_on_at_the_speed_it_had(self):
        for label in ("touchpad 90", "touchpad 125"):
            steps = self.runs[label]["steps"]
            pace = sorted(steps[10:34])[12]
            # (from the pace it had down to rest, no frame slows by more than a third of it: Kirigami's halved at once)
            drops = [a - b for a, b in zip(steps[30:], steps[31:])]
            self.assertLessEqual(max(drops), pace / 3, f"{label}: {steps[30:]}")

    def test_nothing_runs_once_it_is_still(self):
        for label, r in self.runs.items():
            self.assertTrue(r["idle"], label)


if __name__ == "__main__":
    unittest.main()
