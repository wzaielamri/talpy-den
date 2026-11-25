"""The refresh rate of a Talpy Chat window's screen (package/contents/code/screen_rate.py), which its scroller's
steps go by (WheelScroll.qml, wheel.mjs): kscreen-doctor's answer read, each test with a kscreen-doctor of its
own (the guard's fails any test that runs the real one: claude_guard.py)."""
import claude_guard  # noqa: F401  (first: no test runs the real claude, nor kscreen-doctor)
import ast
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HELPER = ROOT / "package/contents/code/screen_rate.py"

# (kscreen-doctor -j as Plasma 6.8's gives it, a laptop's screen and a monitor; trimmed to what's read)
ANSWER = {"outputs": [
    {"id": 1, "name": "eDP-1", "enabled": True, "connected": True, "currentModeId": "1",
     "modes": [{"id": "1", "name": "1920x1080@60", "refreshRate": 60.03300094604492},
               {"id": "10", "name": "1600x900@60", "refreshRate": 59.94599914550781},
               {"id": "12", "name": "1368x768@60", "refreshRate": 59.88199996948242}]},
    {"id": 2, "name": "DP-2", "enabled": True, "connected": True, "currentModeId": "7",
     "modes": [{"id": "6", "name": "2560x1440@60", "refreshRate": 59.951},
               {"id": "7", "name": "2560x1440@144", "refreshRate": 143.912}]},
    {"id": 3, "name": "HDMI-A-1", "enabled": False, "connected": False, "currentModeId": "",
     "modes": []}],
    "screen": {"id": 0}}


class ScreenRateTests(unittest.TestCase):
    def ask(self, name, script):
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            doctor = bin_dir / "kscreen-doctor"
            doctor.write_text("#!/bin/sh\n" + script)
            doctor.chmod(0o755)
            env = dict(os.environ, PATH=os.pathsep.join([str(bin_dir), os.environ.get("PATH", "")]))
            r = subprocess.run([sys.executable, "-I", str(HELPER), name], capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def answering(self, answer, before=""):
        return '[ "$1" = "-j" ] || exit 2\n%scat <<\'EOF\'\n%s\nEOF\n' % (before, json.dumps(answer))

    def test_the_rate_of_the_screen_its_named_after(self):
        self.assertEqual(self.ask("eDP-1", self.answering(ANSWER)),
                         {"ok": True, "name": "eDP-1", "hz": 60.033, "rates": [59.882, 59.946, 60.033]})
        self.assertEqual(self.ask("DP-2", self.answering(ANSWER)),
                         {"ok": True, "name": "DP-2", "hz": 143.912, "rates": [59.951, 143.912]})

    def test_no_screen_on_by_that_name(self):
        for name in ("HDMI-A-1", "Virtual-1"):   # (off, or not there)
            r = self.ask(name, self.answering(ANSWER))
            self.assertFalse(r["ok"], name)
            self.assertEqual(r["rates"], [59.882, 59.946, 59.951, 60.033, 143.912])   # (every screen's modes, still)
            self.assertIn(name, r["message"])

    def test_a_screen_with_no_name_is_the_only_one_on(self):
        one = {"outputs": [ANSWER["outputs"][0], ANSWER["outputs"][2]]}
        self.assertEqual(self.ask("", self.answering(one))["hz"], 60.033)
        self.assertFalse(self.ask("", self.answering(ANSWER))["ok"])   # (two on: which?)

    def test_kscreen_doctor_failing_or_saying_something_else(self):
        r = self.ask("eDP-1", 'echo "kscreen-doctor: could not connect to the screen backend" >&2\nexit 1\n')
        self.assertEqual((r["ok"], r["rates"]), (False, []))
        self.assertIn("could not connect", r["message"])
        r = self.ask("eDP-1", 'echo "not json"\n')
        self.assertEqual((r["ok"], r["rates"]), (False, []))
        # (a line of its own before the answer is passed over)
        self.assertTrue(self.ask("eDP-1", self.answering(ANSWER, before='echo "kscreen.doctor: hello"\n'))["ok"])
        # (a mode it can't read: not a rate)
        odd = {"outputs": [dict(ANSWER["outputs"][0], modes=[{"id": "1", "refreshRate": "fast"}])]}
        self.assertFalse(self.ask("eDP-1", self.answering(odd))["ok"])

    def test_no_kscreen_doctor(self):
        # (a PATH with nothing on it: never one where the real one is, /usr/bin)
        with tempfile.TemporaryDirectory() as empty:
            r = subprocess.run([sys.executable, "-I", str(HELPER), "eDP-1"], capture_output=True, text=True, timeout=30,
                               env=dict(os.environ, PATH=empty))
        self.assertEqual(json.loads(r.stdout), {"ok": False, "rates": [], "message": "kscreen-doctor isn't installed"})

    def test_no_syntax_or_calls_newer_than_37(self):
        # (as test_talpy_den.py's OldPythonTests: no := or f"{x=}", no newer methods)
        source = HELPER.read_text()
        tree = ast.parse(source, feature_version=(3, 7)) if sys.version_info >= (3, 8) else ast.parse(source)
        newer = {"removeprefix", "removesuffix", "is_relative_to", "with_stem", "hardlink_to"}
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword):
                self.assertNotIn(node.arg, {"missing_ok", "strict"}, f"line {node.value.lineno}")
            if isinstance(node, ast.Attribute):
                self.assertNotIn(node.attr, newer, f"line {node.lineno}")


if __name__ == "__main__":
    unittest.main()
