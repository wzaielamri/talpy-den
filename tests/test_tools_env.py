"""The bench's tools never reach your desktop's session: a render (tools/render_popup.sh, and bench.py and
the others through it) runs plasmawindowed on a D-Bus of its own, with no display of yours, and ends what
it left on that bus; the browsers of the VS Code benches start with no bus and no display of yours, and
their processes go with them when they time out."""
import claude_guard  # noqa: F401  (first: no test runs the real claude)
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
BENCH = ROOT / "tools/bench"
sys.path.insert(0, str(BENCH))
import bench  # noqa: E402

# (made-up values standing for yours: the tests never carry your own)
YOURS = {"DBUS_SESSION_BUS_ADDRESS": "unix:path=/nonexistent/yours/bus", "DISPLAY": ":77", "WAYLAND_DISPLAY": "wayland-77"}


class TheTestsEnvironmentTests(unittest.TestCase):
    def test_no_test_carries_your_bus_or_display(self):
        # (claude_guard, imported first by every test, takes them out before any test runs: given made-up ones)
        code = ("import sys; sys.path.insert(0, %r); import claude_guard, os; "
                "print(sorted(k for k in %r if k in os.environ))" % (str(ROOT / "tests"), tuple(YOURS)))
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=dict(os.environ, **YOURS))
        self.assertEqual(r.stdout.strip(), "[]", r.stderr[-500:])


class TheBenchsEnvironmentTests(unittest.TestCase):
    def test_a_render_is_given_no_bus_and_no_display_of_yours(self):
        with mock.patch.dict(os.environ, YOURS):
            env = bench.env_for(Path("/nonexistent/home"))
        for k in YOURS:
            self.assertFalse(k in env, k)

    def test_the_browsers_start_with_no_bus_and_no_display_of_yours(self):
        with mock.patch.dict(os.environ, YOURS):
            env = bench.browser_env()
        for k in YOURS:
            self.assertFalse(k in env, k)
        self.assertIn("--password-store=basic", bench.CHROME_FLAGS)
        self.assertIn("--use-mock-keychain", bench.CHROME_FLAGS)
        for name in ("vscode_bench.py", "newsince_vscode.py", "wheel_vscode.py"):
            text = (BENCH / name).read_text()
            self.assertIn("bench.browser_env(", text, name)
            self.assertIn("bench.CHROME_FLAGS", text, name)

    def test_a_browser_bench_that_times_out_takes_its_browser_with_it(self):
        for name in ("wheel_vscode.py", "vscode_bench.py"):
            text = (BENCH / name).read_text()
            self.assertIn("start_new_session=True", text, name)
            self.assertIn("os.killpg(", text, name)

    def test_render_popup_has_no_way_to_your_bus(self):
        text = (ROOT / "tools/render_popup.sh").read_text()
        self.assertNotIn("$XDG_RUNTIME_DIR/bus", text)
        self.assertIn("dbus-run-session", text)


@unittest.skipUnless(shutil.which("dbus-run-session"), "needs dbus-run-session")
class RenderPopupOnABusOfItsOwnTests(unittest.TestCase):
    """render_popup.sh run for real with stand-ins for plasmawindowed and kpackagetool6: what plasmawindowed
    is given, and what's left on its bus after."""

    def test_plasmawindowed_runs_on_a_bus_of_its_own_with_no_display_and_nothing_is_left(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            (bin_dir / "kpackagetool6").write_text("#!/bin/sh\nexit 0\n")
            # (a service it starts on the bus, as plasmashell's portals are: left running by itself)
            (bin_dir / "plasmawindowed").write_text(
                "#!/bin/sh\nenv > \"$SEEN\"\nsleep 300 < /dev/null > /dev/null 2>&1 &\necho $! > \"$SEEN.left\"\n"
                "echo 'RENDER: saved 1x1'\n")
            for f in bin_dir.iterdir():
                f.chmod(0o755)
            home = tmp / "home"
            home.mkdir()
            env = {k: v for k, v in os.environ.items() if k not in YOURS and not k.startswith("XDG_")}
            env.update(YOURS, PATH=f"{bin_dir}:{os.environ['PATH']}", HOME=str(home), SEEN=str(tmp / "seen"))
            r = subprocess.run([str(ROOT / "tools/render_popup.sh"), str(tmp / "out.png"), "1"], env=env,
                               capture_output=True, text=True, timeout=120)
            self.assertTrue((tmp / "seen").exists(), r.stdout + r.stderr)
            seen = dict(line.split("=", 1) for line in (tmp / "seen").read_text().splitlines() if "=" in line)
            self.assertTrue(seen.get("DBUS_SESSION_BUS_ADDRESS", "").startswith("unix:path=/tmp/dbus-"), seen.get("DBUS_SESSION_BUS_ADDRESS"))
            self.assertNotIn("DISPLAY", seen)
            self.assertNotIn("WAYLAND_DISPLAY", seen)
            left = int((tmp / "seen.left").read_text())
            for _ in range(20):
                if not Path(f"/proc/{left}").exists():
                    break
                time.sleep(0.1)
            alive = Path(f"/proc/{left}").exists()
            if alive:   # (not left running by the test either)
                os.kill(left, 15)
            self.assertFalse(alive, "what it started on its bus was left running")


if __name__ == "__main__":
    unittest.main()
