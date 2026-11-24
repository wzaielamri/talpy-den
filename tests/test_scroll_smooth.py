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
wheel), offscreen on Qt Quick's threaded loop, its window drawn at 60.03 frames
a second as a screen would (and beside another window, as plasmashell shows its
panel and desktop: Qt then steps its animations on a timer of its own), given
the events as Plasma's Wayland gives them (a notch's 120; a touchpad's phases,
its pixels and its angle 12 a pixel) at their times, the list's place read in
each frame drawn.
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
from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, Qt, QTimer, QUrl
from PySide6.QtGui import QGuiApplication, QWheelEvent
from PySide6.QtQuick import QQuickView, QQuickWindow

runs = json.loads(open(sys.argv[2]).read())
windows = int(sys.argv[3])
app = QGuiApplication(sys.argv)
view = QQuickView()
view.setSource(QUrl.fromLocalFile(sys.argv[1]))
if view.status() != QQuickView.Ready:
    print("ERROR", [e.toString() for e in view.errors()])
    sys.exit(1)
view.show()
# (more windows shown, as plasmashell's panel and desktop are beside a popup or a Talpy Chat window: Qt's threaded
# loop then steps its animations on a timer of its own, not once a frame)
others = []
for _ in range(windows - 1):
    other = QQuickWindow()
    other.resize(40, 40)
    other.show()
    others.append(other)
root = view.rootObject()
out, state = [], {"run": 0, "i": 0, "t0": 0.0, "vsync": 0}
PHASE = {"none": Qt.NoScrollPhase, "begin": Qt.ScrollBegin, "update": Qt.ScrollUpdate, "end": Qt.ScrollEnd}
VSYNC = 1000 / 60.03
T0 = time.perf_counter()

# The screen as Qt Wayland meets it (qwaylandwindow.cpp): a frame asked for (requestUpdate: here the platform's
# update request, given at once, QT_QPA_UPDATE_IDLE_TIME=0) with no frame callback pending is drawn at once;
# a frame drawn, the next waits for the compositor's frame callback, which comes at the next vsync (60.03 a
# second, a callback reached half a vsync late or more missing that frame). Nothing asked for, nothing drawn.
# Hidden, or stalled (a minimized window: the compositor sends it no frame callbacks), nothing is drawn
wl = {"waiting": False, "asked": False, "delivering": False, "stalled": False}


def draw():
    wl["asked"], wl["waiting"], wl["delivering"] = False, True, True
    QGuiApplication.sendEvent(view, QEvent(QEvent.UpdateRequest))
    wl["delivering"] = False


class Frames(QObject):
    def eventFilter(self, obj, ev):
        if ev.type() != QEvent.UpdateRequest or wl["delivering"]:
            return False
        if not wl["waiting"] and not wl["stalled"] and view.isVisible():
            wl["asked"], wl["waiting"] = False, True   # (no callback pending: drawn at once)
            return False
        wl["asked"] = True
        return True


frames = Frames()
view.installEventFilter(frames)


def snapshot(tag):
    return {"tag": tag, "at": len(root.property("ys").toVariant() if hasattr(root.property("ys"), "toVariant") else root.property("ys")),
            "moving": root.property("idle") is False, "quiet": root.property("quiet"), "y": root.property("listY")}


def tick():
    now = (time.perf_counter() - T0) * 1000
    if state.get("on"):
        events = runs[state["run"]]["events"]
        at = (time.perf_counter() - state["t0"]) * 1000
        while state["i"] < len(events) and events[state["i"]][0] <= at:
            t, phase, angle, pixel = events[state["i"]]
            state["i"] += 1
            if phase in ("hide", "show", "stall", "resume", "freeze"):
                state["marks"].append(snapshot(phase))
                if phase == "hide":
                    view.hide()
                elif phase == "show":
                    view.show()
                elif phase == "freeze":
                    time.sleep(angle / 1000)   # (the GUI thread busy: nothing runs, no frame, no timer)
                else:
                    wl["stalled"] = phase == "stall"
                continue
            if not view.isVisible():
                continue   # (a hidden window gets no wheel)
            src = Qt.MouseEventNotSynthesized if phase == "none" else Qt.MouseEventSynthesizedBySystem
            ev = QWheelEvent(QPointF(300, 350), QPointF(300, 350), QPoint(0, pixel), QPoint(0, angle), Qt.NoButton,
                             Qt.NoModifier, PHASE[phase], False, src)
            ev.setTimestamp(int(t))
            QGuiApplication.sendEvent(view, ev)
        if state["i"] >= len(events) and not state.get("ending"):
            state["ending"] = True
            QTimer.singleShot(900, finish)
    k = int(now // VSYNC)
    if k > state["vsync"]:
        state["vsync"] = k
        if wl["waiting"] and not wl["stalled"] and now - k * VSYNC < 0.5 * VSYNC:   # (the frame callback)
            wl["waiting"] = False
            if wl["asked"] and view.isVisible():
                draw()


def start():
    if state["run"] >= len(runs):
        print("RESULT", json.dumps(out))
        app.quit()
        return
    root.setProperty("startY", runs[state["run"]].get("start", 6000 + state["run"]))
    QTimer.singleShot(500, go)


def go():
    # (its time 0 at `phase` ms after a vsync, when the run says)
    root.setProperty("on", True)
    t0 = time.perf_counter()
    phase = runs[state["run"]].get("phase")
    if phase is not None:
        k = int((t0 - T0) * 1000 // VSYNC) + 2
        t0 = T0 + (k * VSYNC + phase) / 1000
    state["i"], state["t0"], state["on"], state["ending"], state["marks"] = 0, t0, True, False, []


def finish():
    state["on"] = False
    root.setProperty("on", False)
    get = lambda k: [float(x) for x in (lambda v: v.toVariant() if hasattr(v, "toVariant") else v)(root.property(k))]
    out.append({"label": runs[state["run"]]["label"], "ys": get("ys"), "ts": get("ts"), "idle": root.property("idle"),
                "inner": root.property("inner"), "quiet": root.property("quiet"), "y": root.property("listY"),
                "marks": state["marks"]})
    state["run"] += 1
    QTimer.singleShot(300, start)


pump = QTimer()
pump.setTimerType(Qt.PreciseTimer)
pump.setInterval(1)
pump.timeout.connect(tick)
pump.start()
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


# (a first motion: the screen's frame learned, as in a plasmashell that has scrolled since it began; that
# first one moves a frame later, once two frames have told it the screen's, and the test checks it neither
# races nor jumps)
RUNS = [{"label": "first", "events": [[0, "none", 120, 0]]},
        {"label": "notch", "events": [[0, "none", 120, 0]]},
        {"label": "spin", "events": [[i * 50, "none", 120, 0] for i in range(6)]},
        {"label": "touchpad 90", "events": touchpad(90, 200, 600)},
        {"label": "touchpad 125", "events": touchpad(125, 200, 600)}]
# (down from the top of a list with a box of its own every fourth row, as a plan or a page shown in the chat
# is, MadeLine.qml: a box comes under the pointer after 100 px)
NESTED = [{"label": "spin over a box", "start": 0, "events": [[i * 50, "none", -120, 0] for i in range(12)]},
          {"label": "touchpad over a box", "start": 0, "events": touchpad(125, -200, 400)}]


PLAIN = """Item {
                width: ListView.view.width
                height: 30 + (index * 37) % 70
                Text { anchors.fill: parent; anchors.margins: 4; text: "Line " + index; wrapMode: Text.Wrap }
            }"""
BOXED = """Item {
                width: ListView.view.width
                height: index % 4 === 3 ? 320 : 150
                Text { visible: index % 4 !== 3; anchors.fill: parent; text: "Line " + index }
                Loader {
                    active: index % 4 === 3
                    width: parent.width - 20; x: 10; height: 300
                    sourceComponent: PlasmaComponents3.ScrollView {
                        id: box
                        Component.onCompleted: if (index === 3) root.boxes = [box]
                        Text { width: box.availableWidth; text: Array(150).fill("a line of the box").join("\\n") }
                    }
                }
            }"""


def run_scene(wheel, nested=False, runs=RUNS, windows=1, ui=None):
    """The runs above in a list as Talpy Chat's, in a window drawn as Qt Wayland draws it on a 60.03 Hz screen
    (RUNNER: a frame only when asked for, at once when none is pending, else at the next vsync), with
    `windows` - 1 more shown beside it (as plasmashell shows its panel and desktop); each run's place in each
    frame drawn, as the window was about to draw it (its afterAnimating, before the scroller's step there:
    the place each frame draws, a frame apart either way)."""
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
    readonly property bool idle: wheel === null || !wheel.moving
    // (nothing of the scroller listening or running: its frames, the lock, its watch)
    readonly property bool quiet: wheel === null || !(wheel.moving || (wheel.frames && wheel.frames.enabled === true)
                                                     || (wheel.lock && wheel.lock.enabled === true) || (wheel.watch && wheel.watch.running === true))
    readonly property real listY: list.contentY
    property var boxes: []
    readonly property real inner: boxes.length ? boxes[0].contentItem.contentY : -1
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
            delegate: %s
            %s
        }
    }
    Connections {
        target: root.Window.window
        function onAfterAnimating() { if (root.on) { root.ys.push(list.contentY); root.ts.push(Date.now()) } }
    }
}
""" % ((ui or UI).as_uri(), "wheelScroll" if wheel else "null", BOXED if nested else PLAIN, wheel)
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "scene.qml").write_text(scene)
        (Path(tmp) / "runs.json").write_text(json.dumps(runs))
        (Path(tmp) / "run.py").write_text(RUNNER)
        env = {k: v for k, v in os.environ.items() if k not in ("WAYLAND_DISPLAY", "DISPLAY", "QT_QPA_PLATFORMTHEME")}
        # (no D-Bus at all: nothing to start on any bus; offscreen, drawn on a thread of its own as plasmashell
        # draws; its frames the runner's, a vsync apart)
        env.update(QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", QSG_RENDER_LOOP="threaded",
                   QT_QPA_UPDATE_IDLE_TIME="0", DBUS_SESSION_BUS_ADDRESS="unix:path=/nonexistent/bus")
        r = subprocess.run(["python3", str(Path(tmp) / "run.py"), str(Path(tmp) / "scene.qml"), str(Path(tmp) / "runs.json"),
                            str(windows)], capture_output=True, text=True, timeout=120, env=env)
    line = next((x for x in r.stdout.splitlines() if x.startswith("RESULT ")), None)
    if not line:
        raise AssertionError(r.stdout[-2000:] + r.stderr[-3000:])
    out = {}
    for d in json.loads(line[len("RESULT "):]):
        ys = d["ys"]
        steps = [a - b for a, b in zip(ys, ys[1:])]
        moving = [k for k, s in enumerate(steps) if abs(s) > 1e-6]
        out[d["label"]] = {"ys": ys, "ts": d["ts"], "steps": steps[moving[0]:moving[-1] + 1] if moving else [],
                           "idle": d["idle"], "inner": d["inner"], "quiet": d["quiet"], "y": d["y"], "marks": d["marks"]}
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
        self.assertIn("property bool moving: false", ws)
        take = ws[ws.index("function take(event)"):ws.index("function frame()")]
        self.assertLess(take.index("handler.starting()"), take.index("flickable.contentY = r.put"))

    def test_it_takes_the_wheel_and_the_touchpad_with_no_key_held(self):
        ws = (UI / "WheelScroll.qml").read_text()
        self.assertIn("acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad", ws)
        self.assertIn("acceptedModifiers: Qt.NoModifier", ws)   # (Ctrl: the text's size; Shift, Alt: Kirigami's)
        self.assertIn("Application.styleHints.wheelScrollLines * 20", ws)   # (a notch: the desktop's lines)

    def test_a_wheel_motion_counts_as_scrolling(self):
        # (the end isn't followed, nor the top held, while the wheel moves the list: listResized, resized, settle)
        at = PANE.index("    function scrolling() {")
        body = PANE[at:PANE.index("\n    }", at)]
        self.assertIn("wheelScroll.moving", body)

    def test_the_wheel_stays_the_lists_while_it_scrolls(self):
        # (Kirigami's 400 ms latch: an item over the list's content takes the wheel while it scrolls and 400 ms
        # after, so a scroll view in the list that comes under the pointer doesn't take a spin over)
        ws = (UI / "WheelScroll.qml").read_text()
        cover = ws[ws.index("property Item cover: Item {"):]
        self.assertIn("parent: handler.flickable", cover)
        self.assertIn("enabled: handler.latched", cover)
        self.assertIn("onWheel: event => handler.take(event)", cover)
        self.assertRegex(ws, r"Timer \{\s*interval: 400")
        self.assertIn("readonly property bool latched: moving || latch.running", ws)

    def test_its_arithmetic_is_es2017(self):
        code = re.sub(r"//.*", "", (UI / "wheel.mjs").read_text())   # (QML imports it as it is)
        self.assertNotIn("?.", code)
        self.assertNotIn("??", code)

    def test_it_runs_only_while_it_moves_and_by_whole_pixels(self):
        ws = (UI / "WheelScroll.qml").read_text()
        # (the 400 ms latch, after an event, and the watch for a window that stopped drawing, only while it
        # moves: single-shot both)
        self.assertEqual(ws.count("Timer {"), 2)
        self.assertNotIn("repeat: true", ws)
        self.assertIn("onMovingChanged: if (!moving) watch.stop()", ws)
        # (its frames listened to only while it moves; the next one asked for only while it moves)
        frames = ws[ws.index("property Connections frames: Connections {"):]
        self.assertIn("enabled: handler.moving\n", frames[:frames.index("}")])
        self.assertEqual(re.sub(r"//.*", "", ws).count("requestUpdate()"), 1)
        frame = ws[ws.index("function frame()"):ws.index("function next()")]
        self.assertRegex(frame, r"if \(Wheel\.moving\(motion\)\) \{\n\s*rearm\(\)\n\s*next\(\)\n\s*\} else \{\n\s*moving = false")
        self.assertIn("s.written = Math.round(y);", (UI / "wheel.mjs").read_text())
        self.assertNotIn("Behavior on", ws)

    def test_it_steps_on_its_windows_frames_not_on_qts_animation_timer(self):
        # (plasmashell shows several windows: Qt steps its animations on a timer of its own then, which drifts
        # against the frames: a FrameAnimation's steps doubled up in a frame about every 0.4 s. Its step is
        # taken as its window readies a frame, the window's afterAnimating: AStepEachFrameBesideOtherWindowsTests)
        ws = (UI / "WheelScroll.qml").read_text()
        self.assertNotIn("FrameAnimation", re.sub(r"//.*", "", ws))
        self.assertRegex(ws, r"target: handler\.flickable\.Window\.window\n\s*enabled: handler\.moving\n"
                             r"\s*function onAfterAnimating\(\) \{\n\s*handler\.frame\(\)")
        self.assertIn("Wheel.tick(motion, Date.now(), flickable.contentY, top(), bottom())", ws)
        self.assertNotIn("moves nothing", ws)


class Retried:
    """Runs measured in real time, offscreen, can catch a computer busy with something else: a check that
    fails is tried once more on a second run, and fails only if it fails there too (Kirigami's fail both)."""
    nested = False
    runs_of = RUNS
    windows = 1

    @classmethod
    def setUpClass(cls):
        cls.runs = [run_scene(what_the_list_has_for_the_wheel(), cls.nested, cls.runs_of, cls.windows)]

    def retried(self, check):
        try:
            check(self.runs[0])
        except AssertionError:
            if len(self.runs) == 1:
                self.runs.append(run_scene(what_the_list_has_for_the_wheel(), self.nested, self.runs_of, self.windows))
            check(self.runs[1])


def missed(steps, pace):
    """Frames that didn't move, or moved two frames' worth, inside a motion of `pace` px a frame."""
    return [s for s in steps if s == 0 or s >= 1.8 * pace]


@NEEDS_QT
class TheListScrollsEvenlyTests(Retried, unittest.TestCase):
    """Run: the list as Talpy Chat's, given the wheel's and the touchpad's events as Wayland does."""

    def test_a_notch_is_the_desktops_lines_its_steps_only_fall_by_whole_pixels(self):
        def check(runs):
            first = runs["first"]["steps"]
            self.assertEqual(sum(first), 60, first)
            self.assertTrue(all(a <= 2 * b + 1 for a, b in zip(first, first[1:4])), first)   # (no race, then a crawl)
            r = runs["notch"]
            self.assertEqual(sum(r["steps"]), 60, r["steps"])
            # (its steps only fall, within 2 px in its first few (a frame the busy runner missed goes two
            # frames' way): Kirigami's went 13, 21)
            self.assertTrue(all(b <= a + (2 if k < 3 else 1) for k, (a, b) in enumerate(zip(r["steps"], r["steps"][1:]))), r["steps"])
            self.assertTrue(all(y == round(y) for y in r["ys"]), r["ys"])
        self.retried(check)

    def test_a_spin_keeps_its_pace(self):
        def check(runs):
            r = runs["spin"]
            self.assertEqual(sum(r["steps"]), 360, r["steps"])
            # (past its first steps, up once and down once: Kirigami's 9 to 12)
            self.assertLessEqual(turns(r["steps"][3:]), 2, r["steps"])
            self.assertLessEqual(r["steps"].count(0), 1, r["steps"])
        self.retried(check)

    def test_a_touchpads_stream_moves_it_every_frame_evenly(self):
        def check(runs):
            for label in ("touchpad 90", "touchpad 125"):
                r = runs[label]
                steps = r["steps"]
                mid = steps[10:34]
                pace = sorted(mid)[len(mid) // 2]
                # (Kirigami's: frames now and then that didn't move, then two frames' worth: 3 or more)
                self.assertLessEqual(len(missed(steps[3:-6], pace)), 1, f"{label}: {steps}")
                off = [s for s in mid if abs(s - pace) > 0.15 * pace + 1]
                self.assertLessEqual(len(off), 3, f"{label}: {mid}")
                self.assertTrue(all(y == round(y) for y in r["ys"]), label)
        self.retried(check)

    def test_as_the_fingers_lift_it_glides_on_at_the_speed_it_had(self):
        def check(runs):
            for label in ("touchpad 90", "touchpad 125"):
                steps = runs[label]["steps"]
                pace = sorted(steps[10:34])[12]
                # (from the pace it had down to rest, no frame slows by more than a third of it: Kirigami's halved at once)
                drops = [a - b for a, b in zip(steps[30:], steps[31:])]
                self.assertLessEqual(max(drops), pace / 3, f"{label}: {steps[30:]}")
        self.retried(check)

    def test_nothing_runs_once_it_is_still(self):
        for label, r in self.runs[0].items():
            self.assertTrue(r["idle"], label)


# (a second of each: about two and a half times the 0.4 s in which Qt's own timer and the frames drift a step apart)
LONG_RUNS = [RUNS[0],
             {"label": "spin", "events": [[i * 50, "none", 120, 0] for i in range(14)]},
             {"label": "touchpad 90", "events": touchpad(90, 200, 1000)},
             {"label": "touchpad 125", "events": touchpad(125, 200, 1000)}]


@NEEDS_QT
class AStepEachFrameBesideOtherWindowsTests(Retried, unittest.TestCase):
    """Run as plasmashell shows it, beside other windows (its panel, its desktop): Qt's threaded loop then steps
    its animations on a timer of its own (int(1000 / the screen's rate) ms: 16 at 60.03 a second), not once a
    frame (qsgthreadedrenderloop.cpp, startOrStopAnimationTimer: exposedWindows == 1), so a FrameAnimation's steps
    and the frames drift apart and about every 0.4 s a frame draws two steps (Talpy Chat's scroller till
    round 3: 19, 38, 19 in a touchpad's stream). The scroller steps on the window's own frames: one step a
    frame drawn."""
    windows = 2
    runs_of = LONG_RUNS

    def test_every_frame_drawn_in_a_motion_moves_it_one_step(self):
        def check(runs):
            for label in ("touchpad 90", "touchpad 125"):
                steps = runs[label]["steps"]
                mid = steps[8:-12]   # (from its start's ease-in to its glide)
                pace = sorted(mid)[len(mid) // 2]
                self.assertEqual(missed(mid, pace), [], f"{label}: {steps}")
            spin = runs["spin"]["steps"]
            # (a spin: up once and down once, no frame still or doubled inside it)
            self.assertLessEqual(turns(spin[3:]), 1, spin)
            self.assertNotIn(0, spin[:-3], spin)
        self.retried(check)


# (a motion from rest a few ms before a vsync: its window, at rest, draws its first frame at once and its
# second at the vsync, a few ms later)
VSYNC = 1000 / 60.03
FROM_REST = [RUNS[0]] + [{"label": f"notch {ms} ms before a vsync", "phase": VSYNC - ms, "events": [[0, "none", 120, 0]]}
                         for ms in (2, 4, 7)] + \
            [{"label": "spin 3 ms before a vsync", "phase": VSYNC - 3, "events": [[i * 50, "none", 120, 0] for i in range(4)]}]


@NEEDS_QT
class AMotionFromRestTests(Retried, unittest.TestCase):
    """A window at rest draws a frame asked for at once, the next at the compositor's frame callback (Qt
    Wayland, qwaylandwindow.cpp requestUpdate), 0 to a frame later; the two are shown a vsync apart. The
    runner draws only the frames asked for, so the scroller must ask for its own."""
    runs_of = FROM_REST

    def test_its_second_frame_goes_a_frame(self):
        # (round 3: 14, 1, 11 with the vsync 2 ms after the first frame; a frame's way: 14, 11)
        def check(runs):
            for label in [r["label"] for r in FROM_REST[1:]]:
                steps = runs[label]["steps"]
                self.assertTrue(abs(steps[0] - 14) <= 1 and abs(steps[1] - 11) <= 2, f"{label}: {steps}")
        self.retried(check)

    def test_a_notch_asks_for_its_frames_moves_and_finishes(self):
        # (nothing else draws the window here: a scroller that didn't ask for its frames wouldn't move a frame at
        # a time; it would only jump there as its watch gives up, 100 ms on)
        def check(runs):
            for label in [r["label"] for r in FROM_REST[1:4]]:
                steps = runs[label]["steps"]
                self.assertEqual(sum(steps), 60, label)
                self.assertTrue(len(steps) >= 8 and max(steps) <= 15, f"{label}: {steps}")
                self.assertTrue(runs[label]["idle"] and runs[label]["quiet"], label)
        self.retried(check)


# (its window hidden, or minimized (no frame callbacks; still shown), during a notch, a spin and a touchpad's
# glide; shown again later)
GONE = [RUNS[0],
        {"label": "notch, hidden", "events": [[0, "none", 120, 0], [40, "hide", 0, 0], [700, "show", 0, 0]]},
        {"label": "spin, hidden", "events": [[i * 50, "none", 120, 0] for i in range(6) if i * 50 < 180]
                                            + [[180, "hide", 0, 0]] + [[i * 50, "none", 120, 0] for i in range(6) if i * 50 > 180]
                                            + [[800, "show", 0, 0]]},
        {"label": "glide", "events": touchpad(125, 200, 300)},
        {"label": "glide, hidden", "events": touchpad(125, 200, 300) + [[360, "hide", 0, 0], [1000, "show", 0, 0]]},
        {"label": "notch, minimized", "events": [[0, "none", 120, 0], [40, "stall", 0, 0], [700, "resume", 0, 0]]},
        {"label": "fast glide", "events": touchpad(125, 400, 300)},
        {"label": "fast glide, frozen", "events": touchpad(125, 400, 300) + [[360, "freeze", 250, 0]]}]


@NEEDS_QT
class AMotionItsWindowStopsDrawingTests(Retried, unittest.TestCase):
    """Its window hidden or minimized mid-motion draws no frame, so no step comes: the motion ends at once
    where it was going (in whole pixels), nothing of it stays on, and showing the window again moves
    nothing (round 3's held it, moving, and jumped 21 px on show)."""
    runs_of = GONE

    def test_it_ends_where_it_was_going_and_nothing_stays_on(self):
        def check(runs):
            start = {r["label"]: r.get("start", 6000 + k) for k, r in enumerate(GONE)}
            glide = start["glide"] - runs["glide"]["y"]   # (up: contentY goes down)
            for label, went, back in (("notch, hidden", 60, "show"), ("spin, hidden", 4 * 60, "show"),
                                      ("glide, hidden", glide, "show"), ("notch, minimized", 60, "resume")):
                r = runs[label]
                mark = next(m for m in r["marks"] if m["tag"] == back)
                # (by the time it's shown again: ended where it was going, nothing on)
                self.assertFalse(mark["moving"], f"{label}: {mark}")
                self.assertTrue(mark["quiet"], f"{label}: {mark}")
                self.assertLessEqual(abs(start[label] - mark["y"] - went), 2 if label.startswith("glide") else 0, f"{label}: {mark}")
                self.assertEqual(mark["y"], round(mark["y"]), label)
                # (shown again: nothing moves)
                after = r["ys"][mark["at"]:]
                self.assertTrue(all(y == mark["y"] for y in after), f"{label}: after {back} {after[:12]}")
                self.assertTrue(r["idle"] and r["quiet"], label)
        self.retried(check)


@NEEDS_QT
class AFrozenEventLoopTests(Retried, unittest.TestCase):
    """Plasmashell's GUI thread stalls now and then (loading chats, other widgets): no frame comes, but its timers
    don't run either. A glide frozen 250 ms mid-way goes on to where it was going over the frames after, as
    after missed frames, not in one jump there (the window didn't stop drawing it: its watch fired late)."""
    runs_of = [GONE[0], GONE[6], GONE[7]]

    def test_it_goes_on_after_the_freeze(self):
        def check(runs):
            r = runs["fast glide, frozen"]
            mark = next(m for m in r["marks"] if m["tag"] == "freeze")
            left = mark["y"] - r["y"]   # (what was left of it as the freeze began)
            ys = r["ys"][mark["at"] - 1:]
            after = [a - b for a, b in zip(ys, ys[1:])]
            moving = [x for x in after if x]
            pace = r["ys"][mark["at"] - 2] - r["ys"][mark["at"] - 1]
            self.assertGreater(left, 3 * pace, f"the freeze came too late in the glide: {left} px left, pace {pace}")
            self.assertGreaterEqual(len(moving), 3, f"after the freeze: {after[:12]} (left {left})")
            self.assertLess(max(moving), left, f"after the freeze: {after[:12]} (left {left})")
            self.assertLessEqual(max(moving), 3.5 * pace + 1, f"after the freeze: {after[:12]} (pace {pace})")
            self.assertTrue(r["idle"] and r["quiet"])
        self.retried(check)


@NEEDS_QT
class AScrollGoesOnOverABoxInTheListTests(Retried, unittest.TestCase):
    """A plan or a page shown in the chat (MadeLine.qml) is a scroll view of its own in the list: a spin or a
    touchpad's swipe that brings one under the pointer goes on scrolling the list, as Kirigami's did (it takes
    the wheel over the list's content while it scrolls and 400 ms after), not the box."""
    nested = True
    runs_of = NESTED

    def test_a_spin_goes_on_scrolling_the_list(self):
        def check(runs):
            r = runs["spin over a box"]
            self.assertEqual(-sum(r["steps"]), 12 * 60, r["steps"])
            self.assertEqual(r["inner"], 0, "the box scrolled")
        self.retried(check)

    def test_a_touchpads_swipe_goes_on_scrolling_the_list_and_glides(self):
        def check(runs):
            r = runs["touchpad over a box"]
            moves = sum(e[2] for e in touchpad(125, -200, 400) if e[1] == "update") / 120 * 60
            self.assertGreater(-sum(r["steps"]), -moves, r["steps"])   # (its moves and a glide)
            self.assertEqual(r["inner"], 0, "the box scrolled")
        self.retried(check)


if __name__ == "__main__":
    unittest.main()
