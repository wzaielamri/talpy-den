"""The bench's tools and the tests never reach your desktop's session: a render (tools/render_popup.sh, and
bench.py and the others through it) runs plasmawindowed on a D-Bus of its own, started with the render's
own folders, with no display of yours, and ends what it left on that bus; the browsers of the VS Code
benches start with no bus and no display of yours, and their processes go with them when they time out.
Taking the bus's address out isn't enough: with none given, libdbus and GDBus (a browser's, Qt's) look for
the session bus at $XDG_RUNTIME_DIR/bus, which is yours, so each is given an address that isn't there and
a runtime folder of its own; checked for real with a stand-in bus at that place."""
import claude_guard  # noqa: F401  (first: no test runs the real claude)
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
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
# (a session bus's clients, libdbus's and GDBus's, asked for the session bus)
CLIENTS = [["dbus-send", "--session", "--print-reply", "--dest=org.freedesktop.DBus", "/", "org.freedesktop.DBus.ListNames"],
           ["gdbus", "call", "--session", "--dest", "org.freedesktop.DBus", "--object-path", "/",
            "--method", "org.freedesktop.DBus.ListNames"]]


class StandInBus:
    """A runtime folder standing for yours, with a socket where your session bus is ($XDG_RUNTIME_DIR/bus):
    it counts who connects to it and hangs up on them at once (no bus behind it: nothing is started)."""

    def __enter__(self):
        self.dir = Path(tempfile.mkdtemp(prefix="talpy-den-yours-run-"))
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(str(self.dir / "bus"))
        self.sock.listen(16)
        self.sock.settimeout(0.1)
        self.connected, self.done = 0, False
        self.thread = threading.Thread(target=self._accept, daemon=True)
        self.thread.start()
        return self

    def _accept(self):
        while not self.done:
            try:
                conn, _ = self.sock.accept()
            except (socket.timeout, OSError):
                continue
            self.connected += 1
            conn.close()

    def ask(self, env):
        """The clients run with `env`; how many reached this folder's bus."""
        before = self.connected
        for cmd in CLIENTS:
            subprocess.run(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        time.sleep(0.2)
        return self.connected - before

    def yours(self):
        """An environment as yours would be with no bus address: its runtime folder this one."""
        env = {k: v for k, v in os.environ.items() if k not in YOURS}
        env["XDG_RUNTIME_DIR"] = str(self.dir)
        return env

    def __exit__(self, *exc):
        self.done = True
        self.thread.join(2)
        self.sock.close()
        shutil.rmtree(self.dir, ignore_errors=True)


@unittest.skipUnless(shutil.which("dbus-send") and shutil.which("gdbus"), "needs dbus-send and gdbus")
class NothingReachesTheBusInYourRuntimeFolderTests(unittest.TestCase):
    def test_with_no_address_libdbus_and_gdbus_look_for_it_there(self):
        # (why an address that isn't there is given: the stand-in is reached when none is)
        with StandInBus() as bus:
            self.assertEqual(bus.ask(bus.yours()), len(CLIENTS))

    def test_a_tests_child_reaches_no_bus_there(self):
        with StandInBus() as bus:
            code = ("import sys, subprocess; sys.path.insert(0, %r); import claude_guard, os; "
                    "[subprocess.run(c, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30) for c in %r]; "
                    "print(os.environ['XDG_RUNTIME_DIR'])" % (str(ROOT / "tests"), CLIENTS))
            r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=bus.yours(), timeout=120)
            time.sleep(0.2)
            self.assertEqual(r.returncode, 0, r.stderr[-500:])
            self.assertEqual(bus.connected, 0)
            run = Path(r.stdout.strip())
            self.assertNotEqual(run, bus.dir)
            self.assertFalse(run.exists())   # (its own, gone with it)

    def test_a_render_reaches_no_bus_there(self):
        with StandInBus() as bus:
            with mock.patch.dict(os.environ, bus.yours(), clear=True):
                env = bench.env_for(Path("/nonexistent/home"))
            self.assertEqual(bus.ask(env), 0)
            self.assertEqual(env["DBUS_SESSION_BUS_ADDRESS"], bench.NO_BUS)
            self.assertNotEqual(env["XDG_RUNTIME_DIR"], str(bus.dir))

    def test_a_browser_reaches_no_bus_there(self):
        with StandInBus() as bus:
            with mock.patch.dict(os.environ, bus.yours(), clear=True):
                env = bench.browser_env()
            self.assertEqual(bus.ask(env), 0)
            run = Path(env["XDG_RUNTIME_DIR"])
            self.assertNotEqual(run, bus.dir)
            self.assertEqual(run.stat().st_mode & 0o777, 0o700)   # (private, as a runtime folder is)


class TheTestsEnvironmentTests(unittest.TestCase):
    def test_no_test_carries_your_bus_or_display(self):
        # (claude_guard, imported first by every test, takes them out before any test runs: given made-up ones;
        # the bus's address one that isn't there)
        code = ("import sys; sys.path.insert(0, %r); import claude_guard, os; "
                "print(sorted((k, os.environ[k]) for k in %r if k in os.environ))" % (str(ROOT / "tests"), tuple(YOURS)))
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=dict(os.environ, **YOURS))
        self.assertEqual(r.stdout.strip(), "[('DBUS_SESSION_BUS_ADDRESS', 'unix:path=/nonexistent/bus')]", r.stderr[-500:])


class TheBenchsEnvironmentTests(unittest.TestCase):
    def test_a_render_is_given_no_bus_and_no_display_of_yours(self):
        with mock.patch.dict(os.environ, YOURS):
            env = bench.env_for(Path("/nonexistent/home"))
        for k in YOURS:
            self.assertNotEqual(env.get(k), YOURS[k], k)
        self.assertNotIn("DISPLAY", env)
        self.assertNotIn("WAYLAND_DISPLAY", env)

    def test_no_claude_variable_of_yours_reaches_a_render_or_a_browser(self):
        # (in a Claude Code shell CLAUDE_CONFIG_DIR is your real ~/.claude: a render's widget would read your chats)
        claude = {"CLAUDE_CONFIG_DIR": "/nonexistent/yours/.claude", "CLAUDECODE": "1", "CLAUDE_CODE_SESSION_ID": "yours",
                  "CLAUDE_CODE_ENTRYPOINT": "cli"}
        with mock.patch.dict(os.environ, claude):
            for env in (bench.env_for(Path("/nonexistent/home")), bench.browser_env(), bench.browser_env(Path("/nonexistent/home"))):
                self.assertEqual([k for k in env if k.startswith("CLAUDE")], [])
                self.assertNotIn("/nonexistent/yours/.claude", env.values())

    def test_a_renders_widget_asks_a_kscreen_doctor_of_the_benchs(self):
        # (Talpy Chat's scroller asks for its screen's refresh rate, code/screen_rate.py: never your desktop)
        env = bench.env_for(Path("/nonexistent/home"))
        doctor = shutil.which("kscreen-doctor", path=env["PATH"])
        self.assertEqual(Path(doctor).parent, Path(bench.own_bin()))
        r = subprocess.run([sys.executable, "-I", str(ROOT / "package/contents/code/screen_rate.py"), ""],
                           capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(json.loads(r.stdout), {"ok": True, "name": "eDP-1", "hz": 60.033, "rates": [60.033]})

    def test_the_browsers_start_with_no_bus_and_no_display_of_yours(self):
        with mock.patch.dict(os.environ, YOURS):
            env = bench.browser_env()
        for k in YOURS:
            self.assertNotEqual(env.get(k), YOURS[k], k)
        self.assertNotIn("DISPLAY", env)
        self.assertNotIn("WAYLAND_DISPLAY", env)
        self.assertIn("--password-store=basic", bench.CHROME_FLAGS)
        self.assertIn("--use-mock-keychain", bench.CHROME_FLAGS)
        for name in ("vscode_bench.py", "newsince_vscode.py", "wheel_vscode.py"):
            text = (BENCH / name).read_text()
            self.assertIn("bench.browser_env(", text, name)
            self.assertIn("bench.CHROME_FLAGS", text, name)

    def test_a_browser_bench_that_times_out_takes_its_browser_with_it(self):
        for name in ("wheel_vscode.py", "vscode_bench.py", "newsince_vscode.py"):
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
        with tempfile.TemporaryDirectory() as tmp, StandInBus() as yours:
            tmp = Path(tmp)
            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            # (what runs before the bus asks for one, as kpackagetool6 may)
            (bin_dir / "kpackagetool6").write_text("#!/bin/sh\n" + "\n".join(" ".join(c) + " >/dev/null 2>&1" for c in CLIENTS) + "\nexit 0\n")
            # (what the render's bus was started with: what D-Bus starts on it inherits it; and a service it
            # starts on the bus, as plasmashell's portals are: left running by itself)
            (bin_dir / "plasmawindowed").write_text(
                "#!/bin/sh\nenv > \"$SEEN\"\n"
                "pid=$(dbus-send --session --print-reply --dest=org.freedesktop.DBus / "
                "org.freedesktop.DBus.GetConnectionUnixProcessID string:org.freedesktop.DBus | sed -n 's/.*uint32 //p')\n"
                "tr '\\0' '\\n' < /proc/$pid/environ > \"$SEEN.bus\"\n"
                "sleep 300 < /dev/null > /dev/null 2>&1 &\necho $! > \"$SEEN.left\"\n"
                "echo 'RENDER: saved 1x1'\n")
            for f in bin_dir.iterdir():
                f.chmod(0o755)
            home = tmp / "home"
            (home / ".config").mkdir(parents=True)
            env = {k: v for k, v in os.environ.items() if k not in YOURS and not k.startswith("XDG_")}
            # (yours: a display, and a runtime folder whose bus it may look for with no address given)
            env.update({k: v for k, v in YOURS.items() if k != "DBUS_SESSION_BUS_ADDRESS"}, PATH=f"{bin_dir}:{os.environ['PATH']}",
                       HOME=str(home), SEEN=str(tmp / "seen"), XDG_RUNTIME_DIR=str(yours.dir),
                       XDG_CONFIG_HOME=str(home / ".config"))
            r = subprocess.run([str(ROOT / "tools/render_popup.sh"), str(tmp / "out.png"), "1"], env=env,
                               capture_output=True, text=True, timeout=120)
            self.assertTrue((tmp / "seen").exists(), r.stdout + r.stderr)
            seen = dict(line.split("=", 1) for line in (tmp / "seen").read_text().splitlines() if "=" in line)
            self.assertTrue(seen.get("DBUS_SESSION_BUS_ADDRESS", "").startswith("unix:path=/tmp/dbus-"), seen.get("DBUS_SESSION_BUS_ADDRESS"))
            self.assertNotIn("DISPLAY", seen)
            self.assertNotIn("WAYLAND_DISPLAY", seen)
            self.assertEqual(yours.connected, 0)
            daemon = dict(line.split("=", 1) for line in (tmp / "seen.bus").read_text().splitlines() if "=" in line)
            for k in ("XDG_RUNTIME_DIR", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME"):
                self.assertEqual(daemon.get(k), seen.get(k), k)
            self.assertNotEqual(daemon.get("XDG_RUNTIME_DIR"), str(yours.dir))
            self.assertNotEqual(daemon.get("XDG_CONFIG_HOME"), str(home / ".config"))
            left = int((tmp / "seen.left").read_text())
            for _ in range(20):
                if not Path(f"/proc/{left}").exists():
                    break
                time.sleep(0.1)
            alive = Path(f"/proc/{left}").exists()
            if alive:   # (not left running by the test either)
                os.kill(left, 15)
            self.assertFalse(alive, "what it started on its bus was left running")

    def test_its_widget_asks_a_kscreen_doctor_of_its_own_never_yours(self):
        # (run by hand with your PATH, its Talpy Chat window's scroller would ask your desktop's kscreen-doctor for the
        # screen's refresh rate, code/screen_rate.py: the render's own comes first)
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            (bin_dir / "kpackagetool6").write_text("#!/bin/sh\nexit 0\n")
            (bin_dir / "kscreen-doctor").write_text('#!/bin/sh\ntouch "$SEEN.yours"\nexit 1\n')   # (yours: never run)
            (bin_dir / "plasmawindowed").write_text('#!/bin/sh\nkscreen-doctor -j > "$SEEN.screens"\n'
                                                    'python3 -I "$SCREEN_RATE" "" > "$SEEN.rate"\necho "RENDER: saved 1x1"\n')
            for f in bin_dir.iterdir():
                f.chmod(0o755)
            home = tmp / "home"
            (home / ".config").mkdir(parents=True)
            env = {k: v for k, v in os.environ.items() if k not in YOURS and not k.startswith("XDG_")}
            env.update(PATH=f"{bin_dir}:{os.environ['PATH']}", HOME=str(home), SEEN=str(tmp / "seen"),
                       SCREEN_RATE=str(ROOT / "package/contents/code/screen_rate.py"))
            r = subprocess.run([str(ROOT / "tools/render_popup.sh"), str(tmp / "out.png"), "1"], env=env,
                               capture_output=True, text=True, timeout=120)
            self.assertTrue((tmp / "seen.screens").exists(), r.stdout + r.stderr)
            self.assertFalse((tmp / "seen.yours").exists())
            self.assertEqual(json.loads((tmp / "seen.screens").read_text())["outputs"][0]["name"], "eDP-1")
            self.assertEqual(json.loads((tmp / "seen.rate").read_text()), {"ok": True, "name": "eDP-1", "hz": 60.033, "rates": [60.033]})


if __name__ == "__main__":
    unittest.main()
