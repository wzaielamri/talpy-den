"""(2026-11-22) The Qt tests ran with your environment: Qt's KDE theme
talked to your session bus, and under a bus of their own (dbus-run-session,
test_beat's, or the whole suite run so) it started xdg-desktop-portal,
ksecretd and the like there, which outlived that bus. They go through
qt_offscreen now: no session bus at all, or one of their own that nothing
starts on (no desktop theme) and whatever is left on it ended by pid."""
import claude_guard  # noqa: F401  (first: no test runs the real claude)
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
TESTS = Path(__file__).resolve().parent
UI = TESTS.parent / "package/contents/ui"
sys.path.insert(0, str(TESTS))
from test_pets import NEEDS_PLASMA_QML  # noqa: E402

COMPILE = """import sys
from PySide6.QtCore import QUrl, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
app = QGuiApplication(sys.argv)
engine = QQmlEngine()
c = QQmlComponent(engine, QUrl.fromLocalFile(sys.argv[1]), QQmlComponent.PreferSynchronous)
print("status", c.status().name)
QTimer.singleShot(1000, app.quit)
app.exec()
"""


class QtOffscreenTests(unittest.TestCase):
    def test_every_qt_test_goes_through_qt_offscreen(self):
        for path in sorted(TESTS.glob("test_*.py")):
            if path.name == Path(__file__).name:
                continue
            text = path.read_text()
            self.assertFalse("QT_QPA_PLATFORM" in text, path.name + " sets Qt's environment itself")
            self.assertFalse('["dbus-run-session"' in text, path.name + " starts a bus itself")

    @NEEDS_PLASMA_QML
    @unittest.skipUnless(shutil.which("dbus-run-session"), "needs dbus-run-session")
    def test_a_qt_run_leaves_nothing_running(self):
        import qt_offscreen
        chat_pane = str(UI / "ChatPane.qml")   # (Plasma's and Kirigami's modules loaded)
        # the suite run under a bus of its own: a Qt test reaches none, so nothing is started on it
        with tempfile.TemporaryDirectory() as tmp:
            addr = Path(tmp) / "bus"
            driver = ("import os, sys; sys.path.insert(0, %r); import qt_offscreen\n"
                      "open(%r, 'w').write(os.environ['DBUS_SESSION_BUS_ADDRESS'])\n"
                      "r = qt_offscreen.run_qt([sys.executable, '-c', %r, %r])\n"
                      "open(%r, 'w').write(r.stdout)\n" % (str(TESTS), str(addr), COMPILE, chat_pane, str(Path(tmp) / "out")))
            subprocess.run(["dbus-run-session", "--", sys.executable, "-c", driver], stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180)
            self.assertEqual((Path(tmp) / "out").read_text().strip(), "status Ready")
            left = qt_offscreen.reap(addr.read_text())   # (ours if any: started on this run's own bus)
            self.assertEqual(left, {})
        # a test with a bus of its own (test_beat's): nothing is started on it, and nothing would be left
        r = qt_offscreen.run_qt([sys.executable, "-c", COMPILE, chat_pane], own_bus=True)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "status Ready"), r.stderr[-2000:])
        self.assertEqual(r.reaped, {})
        self.assertEqual(qt_offscreen.on_bus(r.bus), {})
