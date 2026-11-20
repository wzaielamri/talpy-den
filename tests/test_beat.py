"""The beat (hub/Beat.qml): what keeps moving while Claude works (Talpy's
glyphs, Talpy Chat's blinking dots) moves on one clock, so a window is drawn
again once a beat, not once for each thing in it, and only while something
follows it."""
import claude_guard  # noqa: F401  (first: no test runs the real claude)
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

UI = Path(__file__).resolve().parent.parent / "package/contents/ui"

NEEDS_QT = unittest.skipUnless(subprocess.run(
    ["python3", "-c", "import PySide6.QtQuick"], capture_output=True).returncode == 0, "needs PySide6")


def run_qml(body, ms):
    """Runs body (an Item with a string property report) offscreen in a shown
    window for ms, with the widget's QML and hub/ imported; returns report."""
    with tempfile.TemporaryDirectory() as tmp:
        qml = Path(tmp) / "t.qml"
        qml.write_text(f'import QtQuick\nimport "{UI.as_uri()}"\nimport "{(UI / "hub").as_uri()}"\n{body}\n')
        script = (
            "import sys\n"
            "from PySide6.QtCore import QUrl, QTimer\n"
            "from PySide6.QtGui import QGuiApplication\n"
            "from PySide6.QtQuick import QQuickView\n"
            "app = QGuiApplication(sys.argv)\n"
            "view = QQuickView()\n"
            "view.setSource(QUrl.fromLocalFile(sys.argv[1]))\n"
            "view.show()\n"
            "r = view.rootObject()\n"
            "QTimer.singleShot(int(sys.argv[2]), app.quit)\n"
            "app.exec()\n"
            "print('REPORT', r.property('report') if r else '')\n")
        out = subprocess.run(["python3", "-c", script, str(qml), str(ms)], capture_output=True, text=True, timeout=60,
                             env=dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software",
                                      QT_FORCE_STDERR_LOGGING="1"))
    report = next((line[len("REPORT "):] for line in out.stdout.splitlines() if line.startswith("REPORT ")), "")
    if not report:
        raise AssertionError(out.stderr[-3000:])
    return json.loads(report)


@NEEDS_QT
class BeatTests(unittest.TestCase):
    def test_glyphs_move_together_every_other_beat_and_the_beat_stops_with_them(self):
        got = run_qml("""
Item {
    id: t
    width: 120; height: 60
    property var paints: ({ a: [], b: [] })
    property bool tickedBefore: Beat.timer.running
    property string report: ""
    TalpyIcon { id: a; width: 24; height: 24; mode: "working" }
    TalpyIcon { id: b; x: 40; width: 24; height: 24; mode: "waiting" }
    Connections { target: a; function onPainted() { t.paints.a.push(Beat.count) } }
    Connections { target: b; function onPainted() { t.paints.b.push(Beat.count) } }
    Timer {
        interval: 1200; running: true
        onTriggered: {
            t.report = JSON.stringify({ tickedBefore: t.tickedBefore, ticking: Beat.timer.running,
                                        followers: Beat.followers, a: t.paints.a, b: t.paints.b })
            a.mode = "idle"
            b.mode = "none"
        }
    }
    Timer {
        interval: 1400; running: true
        onTriggered: {
            const r = JSON.parse(t.report)
            r.tickingAfter = Beat.timer.running
            r.followersAfter = Beat.followers
            t.report = JSON.stringify(r)
        }
    }
}""", 1600)
        self.assertTrue(got["ticking"], got)
        self.assertEqual(got["followers"], 2, got)
        # (after the first picture, painted as each was made) on the same beats, every other one
        moved_a, moved_b = [n for n in got["a"] if n > 0], [n for n in got["b"] if n > 0]
        self.assertGreaterEqual(len(moved_a), 8, got)   # ~12 in 1.2 s at 80 ms
        self.assertLessEqual(len(moved_a), 16, got)
        self.assertEqual(moved_a, moved_b, got)
        self.assertTrue(all(n % 2 == 0 for n in moved_a), got)
        # nothing moving: nothing follows the beat and it stops
        self.assertEqual(got["followersAfter"], 0, got)
        self.assertFalse(got["tickingAfter"], got)

    def test_a_blinking_dot_fades_as_its_own_animation_did(self):
        got = run_qml("""
Item {
    id: t
    property string report: ""
    Component.onCompleted: {
        Beat.now = 100000
        const at = ms => Math.round(Beat.fade(100000 - ms) * 1000) / 1000
        report = JSON.stringify([at(0), at(150), at(300), at(600), at(900), at(1200), at(1500), at(-50)])
    }
}""", 200)
        # 1 down to 0.25 in 600 ms and back, eased in and out (Easing.InOutSine), and on round
        self.assertEqual(got, [1, 0.89, 0.625, 0.25, 0.625, 1, 0.625, 1])


class NothingMovesForeverTests(unittest.TestCase):
    def test_no_animation_runs_forever_on_its_own_clock(self):
        # One that does has its whole window drawn at the screen's rate for as
        # long as it runs (Talpy Chat's dot: 60 frames a second while a tool
        # ran); what moves for a long while follows hub/Beat.qml
        found = [f"{p.relative_to(UI)}:{n}" for p in sorted(UI.rglob("*.qml"))
                 for n, line in enumerate(p.read_text().splitlines(), 1) if re.search(r"Animation\.Infinite", line)]
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
