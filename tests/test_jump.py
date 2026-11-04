import contextlib
import importlib.util
import io
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True  # keep __pycache__ out of the plasmoid package
CODE = Path(__file__).resolve().parent.parent / "package/contents/code"
sys.path.insert(0, str(CODE))
spec = importlib.util.spec_from_file_location("jump", CODE / "jump.py")
jump = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jump)
cs = jump.cs

from test_talpy_den import Fixture, session, vscode_link_params, write  # noqa: E402


class Patch:
    """Temporarily replace attributes of the jump module."""

    def __init__(self, **attrs):
        self.attrs, self.saved = attrs, {}

    def __enter__(self):
        for k, v in self.attrs.items():
            self.saved[k] = getattr(jump, k)
            setattr(jump, k, v)

    def __exit__(self, *exc):
        for k, v in self.saved.items():
            setattr(jump, k, v)


class DbusParsingTests(unittest.TestCase):
    def call(self, out, code=0):
        with Patch(run=lambda args, timeout=5: (code, out)):
            return jump.dbus_call("d", "/p", "m")

    def test_gdbus_values(self):
        self.assertEqual(self.call("(0,)"), 0)
        self.assertEqual(self.call("(['3', '4'],)"), ["3", "4"])
        self.assertEqual(self.call("(true,)"), True)
        self.assertEqual(self.call("('🏠 ◐ is true or false',)"), "🏠 ◐ is true or false")
        self.assertIsNone(self.call("", code=1))

    def test_children_skip_the_object_itself(self):
        out = "node /Windows {\n  interface org.freedesktop.DBus.Introspectable {\n  };\n  node 1 {\n  };\n  node 12 {\n  };\n};"
        with Patch(run=lambda args, timeout=5: (0, out)):
            self.assertEqual(jump.dbus_children("d", "/Windows"), ["1", "12"])


class OpenTerminalTests(unittest.TestCase):
    def start(self, installed, chosen=()):
        """open_terminal's command line, with these programs installed and this default terminal."""
        started = []
        which = lambda name: f"/usr/bin/{name}" if name in installed else None
        with Patch(subprocess=type("S", (), {"Popen": lambda *a, **k: started.append((a[0], k["cwd"])),
                                            "DEVNULL": None}),
                   shutil=type("W", (), {"which": staticmethod(which)}), kde_terminal=lambda: list(chosen),
                   on_gnome=lambda: False):
            ok = jump.open_terminal("/nonexistent", "claude attach x")
        return ok, started

    def test_command_runs_on_the_command_line_then_a_shell(self):
        ok, [(args, cwd)] = self.start({"konsole"})
        self.assertTrue(ok)
        self.assertEqual(args[0], "/usr/bin/konsole")
        self.assertEqual(args[1:3], ["--workdir", str(Path.home())])
        self.assertEqual((args[-2], cwd), ("-c", str(Path.home())))
        self.assertTrue(args[-1].startswith("trap : INT; claude attach x; exec "))

    def test_your_default_terminal_or_another_one(self):
        home = shlex.quote(str(Path.home()))
        ok, [(args, _)] = self.start({"konsole", "kitty"}, chosen=["kitty", "--single-instance"])
        self.assertEqual(args[:3], ["kitty", "--single-instance", "-e"])
        self.assertTrue(args[-1].startswith(f"cd {home} && trap : INT; claude attach x; exec "))
        ok, [(args, _)] = self.start({"konsole"}, chosen=["kitty"])        # chosen one isn't installed
        self.assertEqual(args[0], "/usr/bin/konsole")
        ok, [(args, _)] = self.start({"xterm"})
        self.assertEqual(args[:2], ["/usr/bin/xterm", "-e"])
        self.assertEqual(self.start(set()), (False, []))

    def test_terminal_gets_a_scope_of_its_own(self):
        started = []
        with Patch(subprocess=type("S", (), {"Popen": lambda *a, **k: started.append(a[0]), "DEVNULL": None}),
                   shutil=type("W", (), {"which": staticmethod(lambda n: f"/usr/bin/{n}" if n == "konsole" else None)}),
                   kde_terminal=lambda: [], scope_prefix=lambda name: ["systemd-run", "--user", "--scope", f"--unit={name}", "--"]):
            self.assertTrue(jump.open_terminal("/nonexistent", "claude attach x"))
        (args,) = started
        self.assertEqual(args[:6], ["systemd-run", "--user", "--scope", "--unit=konsole", "--", "/usr/bin/konsole"])

    def test_default_terminal_from_kdeglobals(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get("XDG_CONFIG_HOME")
            os.environ["XDG_CONFIG_HOME"] = tmp
            try:
                self.assertEqual(jump.kde_terminal(), [])
                for text, words in [("[General]\nTerminalApplication=kitty -1\n", ["kitty", "-1"]),
                                    ("[General]\nTerminalApplication=konsole\n", []),
                                    ("[General]\nTerminalApplication=/usr/bin/konsole\n", []),
                                    ("[KDE]\nTerminalApplication=kitty\n[General]\nfoo=1\n", []),
                                    ("[General]\nTerminalApplication=alacritty 'oops\n", [])]:
                    Path(tmp, "kdeglobals").write_text(text)
                    self.assertEqual(jump.kde_terminal(), words, text)
            finally:
                if old is None:
                    os.environ.pop("XDG_CONFIG_HOME")
                else:
                    os.environ["XDG_CONFIG_HOME"] = old


class DesktopTests(unittest.TestCase):
    """Plasma keeps doing what it did; GNOME gets its own terminal, dialog and window raising."""

    def on(self, value):
        old = os.environ.get("XDG_CURRENT_DESKTOP")
        if value is None:
            os.environ.pop("XDG_CURRENT_DESKTOP", None)
        else:
            os.environ["XDG_CURRENT_DESKTOP"] = value
        try:
            return jump.on_gnome()
        finally:
            if old is None:
                os.environ.pop("XDG_CURRENT_DESKTOP", None)
            else:
                os.environ["XDG_CURRENT_DESKTOP"] = old

    def test_which_desktop(self):
        self.assertTrue(self.on("GNOME"))
        self.assertTrue(self.on("ubuntu:GNOME"))
        self.assertFalse(self.on("KDE"))
        self.assertFalse(self.on("GNOME-Flashback:GNOME:KDE"))
        self.assertFalse(self.on(""))
        self.assertFalse(self.on(None))

    def raised(self, kwin, gnome):
        """raise_window with KWin answering kwin and the GNOME extension gnome (None: not running)."""
        calls = []

        def dbus(dest, path, method, *args):
            calls.append((dest, method, args))
            if dest == "org.kde.KWin":
                return kwin if method.endswith("loadScript") else None
            return gnome
        with Patch(dbus_call=dbus, time=type("T", (), {"sleep": staticmethod(lambda s: None)})):
            ok = jump.raise_window([10, 1], "my tab", prefer="x")
        return ok, calls

    def test_kwin_raises_on_plasma(self):
        ok, calls = self.raised(kwin=7, gnome=True)
        self.assertTrue(ok)
        self.assertEqual({dest for dest, _, _ in calls}, {"org.kde.KWin"})   # GNOME never asked

    def test_gnome_extension_raises_without_kwin(self):
        ok, calls = self.raised(kwin=None, gnome=True)
        self.assertTrue(ok)
        dest, method, (arg,) = calls[-1]
        self.assertEqual((dest, method), ("org.gnome.Shell", "org.gnome.Shell.Extensions.TalpyDen.RaiseWindow"))
        self.assertEqual(json.loads(json.loads(arg)), {"pids": [10, 1], "caption": "my tab",
                                                       "require": False, "prefer": "x"})
        self.assertFalse(self.raised(kwin=None, gnome=None)[0])     # extension not running
        self.assertFalse(self.raised(kwin=-1, gnome=False)[0])

    def test_raise_argument_is_a_gvariant_string(self):
        try:
            from gi.repository import GLib
        except ImportError:
            self.skipTest("no PyGObject")
        want = {"pids": [1], "caption": 'a "quoted" \\ tab\n🏠 ◐', "require": True, "prefer": ""}
        arg = json.dumps(json.dumps(want, ensure_ascii=False), ensure_ascii=False)
        self.assertEqual(json.loads(GLib.Variant.parse(GLib.VariantType("s"), arg).unpack()), want)

    def terminal(self, installed, gnome):
        started = []
        which = lambda name: f"/usr/bin/{name}" if name in installed else None
        with Patch(subprocess=type("S", (), {"Popen": lambda *a, **k: started.append(a[0]), "DEVNULL": None}),
                   shutil=type("W", (), {"which": staticmethod(which)}), kde_terminal=lambda: [],
                   on_gnome=lambda: gnome, scope_prefix=lambda name: []):
            ok = jump.open_terminal("/nonexistent", "claude")
        return started[0] if ok else None

    def test_gnome_terminals(self):
        home = shlex.quote(str(Path.home()))
        args = self.terminal({"xdg-terminal-exec", "ptyxis", "konsole"}, gnome=True)
        # sh runs the (POSIX) command whatever your shell is; then your shell
        self.assertEqual(args[:3], ["/usr/bin/xdg-terminal-exec", "/bin/sh", "-c"])
        yours = shlex.quote(os.environ.get("SHELL") or "/bin/bash")
        self.assertEqual(args[3], f"cd {home} && trap : INT; claude; exec {yours}")
        self.assertEqual(self.terminal({"ptyxis", "gnome-terminal"}, gnome=True)[:3],
                         ["/usr/bin/ptyxis", "--new-window", "--"])
        self.assertEqual(self.terminal({"gnome-terminal", "kgx"}, gnome=True)[:3],
                         ["/usr/bin/gnome-terminal", "--window", "--"])
        self.assertEqual(self.terminal({"kgx"}, gnome=True)[:2], ["/usr/bin/kgx", "--"])
        self.assertEqual(self.terminal({"konsole"}, gnome=True)[:2], ["/usr/bin/konsole", "--workdir"])
        self.assertEqual(self.terminal({"xterm"}, gnome=True)[:2], ["/usr/bin/xterm", "-e"])
        self.assertIsNone(self.terminal(set(), gnome=True))

    def test_plasma_terminal_unchanged_with_gnome_terminals_installed(self):
        args = self.terminal({"konsole", "ptyxis", "xdg-terminal-exec"}, gnome=False)
        self.assertEqual(args[:3], ["/usr/bin/konsole", "--workdir", str(Path.home())])

    def test_folder_dialog(self):
        which = lambda name: f"/usr/bin/{name}"
        ran = []
        run = lambda args, **kw: ran.append(args) or subprocess.CompletedProcess(args, 1, "", "")
        fake = type("S", (), {"run": staticmethod(run), "DEVNULL": None, "PIPE": None})
        for gnome, first in ((True, "zenity"), (False, "kdialog")):
            with Patch(shutil=type("W", (), {"which": staticmethod(which)}), subprocess=fake, on_gnome=lambda: gnome):
                jump.choose_folder("t", Path("/home/me"))
            self.assertEqual(ran.pop()[0], first)
        with Patch(shutil=type("W", (), {"which": staticmethod(lambda n: None)}), on_gnome=lambda: True):
            self.assertEqual(jump.choose_folder("t", Path("/")), (None, "No folder dialog found (install zenity)"))

    def test_raise_hint(self):
        with Patch(on_gnome=lambda: True):
            self.assertEqual(jump.raise_hint(), "is the Talpy Den extension enabled?")
        with Patch(on_gnome=lambda: False):
            self.assertEqual(jump.raise_hint(), "is KWin scripting available?")


class PlaceWindowTests(unittest.TestCase):
    """The chat pane's window beside the popup: KWin puts it there as it appears."""

    def test_the_script_stays_loaded_for_the_window_to_come(self):
        calls, scripts = [], []

        def dbus(dest, path, method, *args):
            calls.append((path, method.rsplit(".", 1)[1]) + args)
            if method.endswith(".loadScript"):
                scripts.append(Path(args[0]).read_text())
                return 3
            return ()   # (gdbus's "()")
        with Patch(dbus_call=dbus):
            self.assertTrue(jump.place_window("* — Talpy Chat", 10, 20, 600, 700))
        path = calls[1][2]
        self.assertEqual(calls, [("/Scripting", "unloadScript", "talpy-den-place"),   # (the last pane's)
                                 ("/Scripting", "loadScript", path, "talpy-den-place"),
                                 ("/Scripting/Script3", "run")])
        self.assertFalse(Path(path).exists())
        want = json.loads(scripts[0].split("\n", 1)[0][len("const want = "):-1])
        self.assertEqual({k: want[k] for k in ("caption", "x", "y", "width", "height")},
                         {"caption": "* — Talpy Chat", "x": 10, "y": 20, "width": 600, "height": 700})
        self.assertLessEqual(abs(want["at"] - time.time() * 1000), 5000)

    def test_without_kwin_scripting(self):
        for loaded in (None, -1):
            with Patch(dbus_call=lambda dest, path, method, *args: loaded if method.endswith(".loadScript") else ()):
                self.assertFalse(jump.place_window("Fix — Talpy Chat", 0, 0, 1, 1))

    @unittest.skipUnless(shutil.which("node"), "node isn't installed")
    def test_where_and_when_kwin_puts_it(self):
        """KWIN_PLACE_SCRIPT run by node, with a stand-in for KWin's workspace and windows."""
        want = {"pids": [5, 1], "caption": "* — Talpy Chat", "x": 900, "y": 100, "width": 500, "height": 700,
                "at": 1000}
        code = """
function Signal() {
    const fns = [];
    return {connect: f => fns.push(f), disconnect: f => { if (fns.indexOf(f) >= 0) fns.splice(fns.indexOf(f), 1); },
            emit: w => fns.slice().forEach(f => f(w)), get count() { return fns.length; }};
}
// A window KWin moves only once it's drawn at its new size (drawn())
function Win(caption, pid, size, opacity) {
    let g = {x: 1, y: 2, width: size[0], height: size[1]};
    const w = {caption: caption, pid: pid, normalWindow: true, opacity: opacity === undefined ? 1 : opacity,
               frameGeometryChanged: Signal(), asked: null};
    Object.defineProperty(w, "frameGeometry", {get: () => g, set: v => { w.asked = v; }});
    w.drawn = () => { g = w.asked; w.frameGeometryChanged.emit(); };
    return w;
}
let timers = [];
function QTimer() { this.timeout = Signal(); timers.push(this); }
QTimer.prototype.start = function () { this.started = true; };
function run(windows, now) {
    const workspace = {windowList: () => windows, windowAdded: Signal()};
    timers = [];
    new Function("workspace", "QTimer", "Date", SCRIPT)(workspace, QTimer, {now: () => now || 2000});
    return workspace;
}
const at = w => w.asked && [w.asked.x, w.asked.y, w.asked.width, w.asked.height];
const out = {};

const another = Win("Fix — Talpy Chat", 77, [500, 700]), open = Win("Fix — Talpy Chat <2>", 5, [400, 300]);
let ws = run([another, open]);
out.open = [at(open), open.opacity, at(another), ws.windowAdded.count];
const next = Win("Other — Talpy Chat", 5, [500, 728]);
ws.windowAdded.emit(next);
out.next = [at(next), at(open), ws.windowAdded.count];

const elsewhere = Win("Fix — Talpy Chat", 77, [400, 300]), other = Win("Talpy Chat settings", 5, [400, 300]);
const coming = Win("Renamed since — Talpy Chat", 5, [500, 728]);
ws = run([]);
ws.windowAdded.emit(elsewhere);
ws.windowAdded.emit(other);
out.notMine = [at(elsewhere), at(other), ws.windowAdded.count];
ws.windowAdded.emit(coming);
out.hidden = [at(coming), coming.opacity, ws.windowAdded.count, !!timers[0].started, timers[0].interval];
coming.drawn();
out.drawn = [coming.opacity, coming.frameGeometryChanged.count];

const slow = Win("Fix — Talpy Chat", 5, [500, 728], 0.9);
ws = run([]);
ws.windowAdded.emit(slow);
timers[0].timeout.emit();
out.timer = [slow.opacity, slow.frameGeometryChanged.count];

const sized = Win("Fix — Talpy Chat", 1, [500, 700]);
ws = run([]);
ws.windowAdded.emit(sized);
out.sized = [at(sized), sized.opacity, timers.length];

const late = Win("Fix — Talpy Chat", 5, [500, 728]);
ws = run([], 6000);
ws.windowAdded.emit(late);
out.late = [at(late), late.opacity, ws.windowAdded.count];
process.stdout.write(JSON.stringify(out));
"""
        script = jump.KWIN_PLACE_SCRIPT % json.dumps(want)
        node = subprocess.run(["node", "-e", f"const SCRIPT = {json.dumps(script)};\n" + code],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(node.returncode, 0, node.stderr)
        out = json.loads(node.stdout)
        target = [900, 100, 500, 700]
        # another chat's window, open already, stays where it is (each chat has
        # a window of its own): the one asked about is waited for
        self.assertEqual(out["open"], [None, 1, None, 1])
        self.assertEqual(out["next"], [target, None, 0])
        # not there yet: waited for; another program's window isn't it, nor one titled otherwise
        self.assertEqual(out["notMine"], [None, None, 1])
        # it appears (its name changed since: * stands for any): hidden till
        # it's drawn at its new size, then as it was
        self.assertEqual(out["hidden"], [target, 0, 0, True, 500])
        self.assertEqual(out["drawn"], [1, 0])
        self.assertEqual(out["timer"], [0.9, 0])   # (never drawn: shown after half a second anyway)
        self.assertEqual(out["sized"], [target, 1, 0])   # (its size already: only moved)
        self.assertEqual(out["late"], [None, 1, 0])   # (5 s on, the window isn't the one asked about)


class SmallJumpTests(unittest.TestCase):
    def test_remote_folder_address(self):
        self.assertEqual(jump.remote_folder_uri("lab", "/home/u/C# tools?"), "vscode-remote://ssh-remote+lab/home/u/C%23%20tools%3F")

    def test_tmux_on_the_chats_own_server(self):
        ran = []
        with Patch(run=lambda args, **kw: ran.append(args) or (0, "4242 s\n")):
            self.assertEqual(jump.tmux_client_pids("s:@1.%3", "/tmp/tmux-1000/work"), [4242])
        self.assertTrue(all(args[:3] == ["tmux", "-S", "/tmp/tmux-1000/work"] for args in ran), ran)

    def test_a_tmux_session_no_terminal_shows(self):
        with Patch(tmux_client_pids=lambda pane, socket=None: []):
            ok, message = jump.jump_terminal({"pid": os.getpid(), "tmux": "s:@1.%3"})
        self.assertEqual((ok, message), (False, "This session runs in a tmux session no terminal shows right now: "
                                                "attach to it to see it"))


class ProcessNameTests(unittest.TestCase):
    def test_a_name_cut_inside_a_character(self):
        # the kernel keeps 15 bytes of a name: any process on the system can
        # have half a character at its end, and every one is looked at
        child = subprocess.Popen([sys.executable, "-c", "import sys, time; open('/proc/self/comm', 'wb')"
                                  ".write(b'app-\\xe6\\xb5\\x8b\\xe8\\xaf\\x95\\xe7\\xa8\\x8b\\xe5\\xba'); "
                                  "print('ready', flush=True); time.sleep(30)"], stdout=subprocess.PIPE)
        self.addCleanup(child.wait)
        self.addCleanup(child.kill)
        child.stdout.readline()
        self.assertTrue(jump.proc_name(child.pid).startswith("app-"))
        self.assertEqual(jump.parent_pid(child.pid), os.getpid())
        jump.konsole_pids()
        jump.vscode_main_pids()
        with mock.patch.object(cs, "VSCODE_APPS", (("code-that-isnt-there", "Nothing"),)):
            self.assertEqual(cs.vscode_running_config_dir(), (False, None))


class AttachCommandTests(unittest.TestCase):
    def profile(self, path, default):
        p = cs.Profile.__new__(cs.Profile)
        p.path, p.is_default = Path(path), default
        return p

    def test_plain_default_profile_unsets_config_dir(self):
        self.assertEqual(jump.attach_command(self.profile("/h/.claude", True), "12ab34cd"),
                         "env -u CLAUDE_CODE_DISABLE_AGENT_VIEW -u CLAUDE_CONFIG_DIR claude attach 12ab34cd")

    def test_linked_profile_uses_the_link_name_when_no_service_runs(self):
        # ~/.claude -> ~/.claude-personal: no ~/.claude.json to fall back on, and
        # terminals/VS Code name the folder ~/.claude, so attach under that name
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            real = home / ".claude-personal"
            real.mkdir()
            (home / ".claude").symlink_to(real)
            for path, default in ((home / ".claude", True), (real, False)):
                self.assertEqual(jump.attach_command(self.profile(path, default), "5ab1c0de", home),
                                 f"env -u CLAUDE_CODE_DISABLE_AGENT_VIEW CLAUDE_CONFIG_DIR={home / '.claude'} claude attach 5ab1c0de")

    def test_reuses_the_running_service_name(self):
        # the service's name is whatever CLAUDE_CONFIG_DIR it runs with (here: this test process)
        with tempfile.TemporaryDirectory() as tmp:
            prof = Path(tmp) / ".claude-work"
            prof.mkdir()
            cs.write_json_atomic(prof / "daemon.status.json", {
                "supervisorPid": os.getpid(), "supervisorProcStart": cs.proc_start_time(os.getpid())})
            expected = os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude")
            self.assertEqual(jump.service_config_dir(self.profile(prof, False)), expected)
            cs.write_json_atomic(prof / "daemon.status.json", {"supervisorPid": 4194304 + 7})  # dead
            self.assertIsNone(jump.service_config_dir(self.profile(prof, False)))

    def test_a_service_named_after_a_switched_link(self):
        # personal's service was started as ~/.claude; then the link moved to
        # work. Its jobs still go through it; a new or resumed chat of
        # personal must not open on work.
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            personal, work = home / ".claude-personal", home / ".claude-work"
            personal.mkdir()
            work.mkdir()
            (home / ".claude").symlink_to(personal)
            env = {"PATH": os.environ["PATH"], "HOME": str(home), "CLAUDE_CONFIG_DIR": str(home / ".claude")}
            service = subprocess.Popen(["sleep", "60"], env=env)
            self.addCleanup(service.wait)
            self.addCleanup(service.kill)
            for _ in range(500):
                if cs.process_config_dir(service.pid):
                    break
                time.sleep(0.01)
            cs.write_json_atomic(personal / "daemon.status.json", {
                "supervisorPid": service.pid, "supervisorProcStart": cs.proc_start_time(service.pid)})
            prof = self.profile(personal, False)
            self.assertEqual(jump.resume_command(prof, "c1", home), f"CLAUDE_CONFIG_DIR={home / '.claude'} claude --resume c1")
            (home / ".claude").unlink()
            (home / ".claude").symlink_to(work)
            self.assertEqual(jump.attach_command(prof, "j1", home), f"env -u CLAUDE_CODE_DISABLE_AGENT_VIEW CLAUDE_CONFIG_DIR={home / '.claude'} claude attach j1")
            self.assertEqual(jump.resume_command(prof, "c1", home), f"CLAUDE_CONFIG_DIR={personal} claude --resume c1")
            self.assertEqual(cs.new_chat_command(prof, home),
                             f"CLAUDE_CODE_DISABLE_AGENT_VIEW=1 CLAUDE_CONFIG_DIR={personal} claude")

    def test_uses_the_name_the_job_was_started_with(self):
        # No service running: start it under the job's own name, not the link
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            real = home / ".claude-personal"
            real.mkdir()
            (home / ".claude").symlink_to(real)
            job = {"providerEnv": {"CLAUDE_CONFIG_DIR": str(real)}}
            self.assertEqual(jump.attach_command(self.profile(home / ".claude", True), "5ab1c0de", home, job),
                             f"env -u CLAUDE_CODE_DISABLE_AGENT_VIEW CLAUDE_CONFIG_DIR={real} claude attach 5ab1c0de")
            # a name of some other folder is ignored
            job = {"providerEnv": {"CLAUDE_CONFIG_DIR": str(home / ".claude-work")}}
            self.assertEqual(jump.attach_command(self.profile(real, False), "5ab1c0de", home, job),
                             f"env -u CLAUDE_CODE_DISABLE_AGENT_VIEW CLAUDE_CONFIG_DIR={home / '.claude'} claude attach 5ab1c0de")

    def test_explains_the_trust_question_for_untrusted_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            prof = home / ".claude-work"
            prof.mkdir()
            cs.write_json_atomic(prof / ".claude.json", {"projects": {
                str(home): {"hasTrustDialogAccepted": False},
                str(home / "proj"): {"hasTrustDialogAccepted": True}}})
            cmd = jump.attach_command(self.profile(prof, False), "j1", home, {"cwd": str(home)})
            self.assertTrue(cmd.startswith("printf '%s\\n\\n' 'Claude will ask whether you trust ~ before"), cmd)
            self.assertTrue(cmd.endswith(f"; env -u CLAUDE_CODE_DISABLE_AGENT_VIEW CLAUDE_CONFIG_DIR={prof} claude attach j1"), cmd)
            self.assertEqual(jump.attach_command(self.profile(prof, False), "j1", home, {"cwd": str(home / "proj")}),
                             f"env -u CLAUDE_CODE_DISABLE_AGENT_VIEW CLAUDE_CONFIG_DIR={prof} claude attach j1")
            # the note survives the shell: run it
            out = subprocess.run(["bash", "-c", cmd.split("; env -u ")[0]], capture_output=True, text=True).stdout
            self.assertIn('Choose "Yes, I trust this folder" to continue', out)

    def test_named_profile_sets_config_dir(self):
        self.assertEqual(jump.attach_command(self.profile("/h/my claude", False), "x;rm"),
                         "env -u CLAUDE_CODE_DISABLE_AGENT_VIEW CLAUDE_CONFIG_DIR='/h/my claude' claude attach 'x;rm'")


class FindSessionTests(Fixture):
    def test_live_and_parked(self):
        profile, entry, job, job_id = jump.find_session(self.home, [], "busy")
        self.assertEqual((profile.label, entry["sessionId"], job_id), ("work", "busy", None))
        profile, entry, job, job_id = jump.find_session(self.home, [], "bgperm")
        self.assertEqual((entry["kind"], job_id, job["tempo"]), ("bg", "job5", "blocked"))
        # the short job id finds the live session too (not just its record)
        self.assertEqual(jump.find_session(self.home, [], "job5")[1]["sessionId"], "bgperm")
        os.remove(self.home / ".claude-work/sessions/19.json")  # its process is gone
        profile, entry, job, job_id = jump.find_session(self.home, [], "job5")
        self.assertEqual((entry, job_id), (None, "job5"))
        self.assertEqual(jump.find_session(self.home, [], "nope")[0], None)
        self.assertEqual(jump.find_session(self.home, [], "spare")[1], None)  # spares are not sessions

    def test_routing(self):
        calls = []
        with Patch(jump_terminal=lambda e, what="session": calls.append(("terminal", e["sessionId"])) or (True, ""),
                   jump_vscode=lambda e: calls.append(("vscode", e["sessionId"])) or (True, ""),
                   jump_job=lambda p, jid, job, name, home=None: calls.append(("job", jid)) or (True, "")):
            for sid in ("busy", "vscode", "bgperm"):
                jump.jump(self.home, [], sid)
        self.assertEqual(calls, [("terminal", "busy"), ("vscode", "vscode"), ("job", "job5")])
        self.assertEqual(jump.jump(self.home, [], "nope"), (False, "That chat isn't running any more"))


class StopTests(Fixture):
    def run_stop(self, session_id, returncode=0, stdout="", stderr=""):
        calls = []

        class FakeSubprocess:
            DEVNULL = None
            TimeoutExpired = TimeoutError

            @staticmethod
            def run(args, **kw):
                calls.append((args, kw["env"].get("CLAUDE_CONFIG_DIR", "<unset>")))
                return type("R", (), {"returncode": returncode, "stdout": stdout, "stderr": stderr})()

        # (claude stop runs in talpy_den.stop_background)
        with Patch(shutil=type("W", (), {"which": staticmethod(lambda n: "/usr/bin/" + n)})), \
                mock.patch.object(subprocess, "run", FakeSubprocess.run):
            return jump.stop(self.home, [], session_id), calls

    def test_stops_background_session_under_its_profile(self):
        (ok, msg), calls = self.run_stop("bgperm", stdout="Stopped job5\n")
        self.assertEqual((ok, msg), (True, "Stopped job5"))
        (args, config_dir), = calls
        self.assertEqual(args, ["/usr/bin/claude", "stop", "job5"])
        self.assertEqual(config_dir, str((self.home / ".claude-work").resolve()))

    def test_leaves_chats_that_arent_idle_unless_told(self):
        # "busy", "waiting" and "vscode" run in this test's own process: it mustn't get a signal
        self.assertEqual(self.run_stop("busy")[0], (False, "It's working again, so it wasn't stopped"))
        self.assertEqual(self.run_stop("waiting")[0], (False, "It's waiting for you now, so it wasn't stopped"))
        self.assertEqual(self.run_stop("vscode")[0], (False, "It's working again, so it wasn't stopped"))
        self.assertEqual(self.run_stop("busy")[1], [])  # and claude stop isn't run for them

    def test_reports_claude_errors(self):
        (ok, msg), _ = self.run_stop("bgperm", returncode=1, stderr="No job matching 'job5'.\n")
        self.assertEqual((ok, msg), (False, "No job matching 'job5'."))
        self.assertEqual(self.run_stop("nope")[0], (False, "That chat isn't running any more"))


class ChatStopTests(Fixture):
    """A chat with a process (terminal or VS Code) can be stopped: SIGTERM in a
    terminal, SIGINT for VS Code's panel (Claude's clean exit there), a kill
    only if it hangs on, and commands it leaves behind are ended. In tmux a
    working chat can be interrupted instead (Ctrl+C in its pane)."""

    def chat(self, sid, setup="", **kw):
        """A stand-in for a chat's claude process, listed as an idle terminal session
        (setup runs before it says it's ready)."""
        proc = subprocess.Popen([sys.executable, "-c", f"{setup}\nimport time; print('ready', flush=True); time.sleep(60)"],
                                stdout=subprocess.PIPE, text=True)
        self.addCleanup(proc.stdout.close)
        self.addCleanup(lambda: (proc.kill(), proc.wait()) if proc.poll() is None else None)
        self.assertEqual(proc.stdout.readline().strip(), "ready")
        write(self.home / f".claude-work/sessions/{proc.pid}.json",
              session(sid, pid=proc.pid, procStart=cs.proc_start_time(proc.pid), **kw))
        return proc

    def test_idle_chat_quits_on_sigterm(self):
        proc = self.chat("idle-chat")
        self.assertEqual(jump.stop(self.home, [], "idle-chat", ".claude-work"), (True, "Stopped; the chat is kept"))
        self.assertEqual(proc.wait(timeout=5), -15)   # SIGTERM: Claude shuts down as when its terminal closes
        self.assertEqual(jump.stop(self.home, [], "idle-chat"), (False, "That chat isn't running any more"))

    def test_vscode_chat_gets_sigint(self):
        # VS Code's panel takes Claude's exit after SIGINT (code 0) like its own stop button
        proc = self.chat("panel", "import os, signal; signal.signal(signal.SIGINT, lambda *a: os._exit(0))",
                         entrypoint="claude-vscode", status="busy")
        self.assertEqual(jump.stop(self.home, [], "panel", busy=True), (True, "Stopped; the chat is kept"))
        self.assertEqual(proc.wait(timeout=5), 0)

    def test_busy_only_when_you_were_told(self):
        for sid, kw in (("working", {"status": "busy"}), ("shell", {"status": "shell"}),
                        ("asks", {"status": "waiting", "waitingFor": "permission prompt"})):
            proc = self.chat(sid, **kw)
            ok, message = cs.stop_chat_by_id(self.home, [], sid, wait=0.5)
            self.assertFalse(ok, sid)
            self.assertIn("so it wasn't stopped", message)
            self.assertIsNone(proc.poll(), sid)   # still running
            self.assertTrue(cs.stop_chat_by_id(self.home, [], sid, busy_ok=True)[0])
            self.assertEqual(proc.wait(timeout=5), -15, sid)
        # its own /model dialog open counts as idle (as in Claude's terminal status)
        proc = self.chat("dialog-open", status="waiting", waitingFor="dialog open")
        self.assertTrue(cs.stop_chat_by_id(self.home, [], "dialog-open")[0])
        self.assertEqual(proc.wait(timeout=5), -15)

    def test_one_that_hangs_on_is_killed(self):
        proc = self.chat("stuck", "import signal; signal.signal(signal.SIGTERM, signal.SIG_IGN)")
        ok, message = cs.stop_chat_by_id(self.home, [], "stuck", wait=0.5)
        self.assertEqual((ok, message), (True, "It hadn't quit after 0.5 s, so it was killed; the chat is kept"))
        self.assertEqual(proc.wait(timeout=5), -9)

    def test_commands_it_leaves_behind_are_ended(self):
        # VS Code's claude exits on SIGINT but leaves its running command behind
        pids = Path(self.tmp.name) / "child"
        proc = self.chat("panel", "import os, signal, subprocess; c = subprocess.Popen(['sleep', '60']);"
                                  f"open({str(pids)!r}, 'w').write(str(c.pid));"
                                  "signal.signal(signal.SIGINT, lambda *a: os._exit(0))",
                         entrypoint="claude-vscode", status="busy")
        child = int(pids.read_text())
        start = cs.proc_start_time(child)
        ok, message = cs.stop_chat_by_id(self.home, [], "panel", busy_ok=True)
        self.assertEqual((ok, message), (True, "Stopped; the chat is kept (and 1 command it was running ended)"))
        self.assertEqual(proc.wait(timeout=5), 0)
        self.assertTrue(cs.process_gone({"pid": child, "procStart": start}))

    def test_profile_and_pid_reuse(self):
        proc = self.chat("mine")
        self.assertEqual(cs.stop_chat_by_id(self.home, [], "mine", ".claude-personal"),
                         (False, "That chat isn't running any more"))
        # its pid now belongs to another process: the file's start time doesn't match
        write(self.home / f".claude-work/sessions/{proc.pid}.json", session("mine", pid=proc.pid, procStart="1"))
        self.assertEqual(cs.stop_chat_by_id(self.home, [], "mine"), (False, "That chat isn't running any more"))
        self.assertIsNone(proc.poll())

    @unittest.skipUnless(shutil.which("tmux"), "needs tmux")
    def test_interrupt_presses_ctrl_c_in_its_tmux_pane(self):
        tmp = Path(self.tmp.name)
        sock, keys, ready = tmp / "tmux.sock", tmp / "keys", tmp / "ready"
        # a stand-in claude that reads its terminal raw, as Claude's own UI does
        script = (f"import os, sys, tty; tty.setraw(0); open({str(ready)!r}, 'w').write(str(os.getpid()));"
                  f"open({str(keys)!r}, 'wb').write(os.read(0, 16)); import time; time.sleep(30)")
        subprocess.run(["tmux", "-S", str(sock), "-f", "/dev/null", "new-session", "-d", "-s", "t", "-x", "80", "-y", "24",
                        f"{sys.executable} -c {shlex.quote(script)}"], check=True)
        self.addCleanup(lambda: subprocess.run(["tmux", "-S", str(sock), "kill-server"], capture_output=True))
        for _ in range(100):
            if ready.exists() and ready.read_text():
                break
            time.sleep(0.05)
        pid = int(ready.read_text())
        pane = subprocess.run(["tmux", "-S", str(sock), "display-message", "-p", "-t", "t",
                               "#{session_name}:#{window_id}.#{pane_id}"], capture_output=True, text=True).stdout.strip()
        write(self.home / f".claude-work/sessions/{pid}.json",
              session("in-tmux", pid=pid, procStart=cs.proc_start_time(pid), status="busy", tmux=pane))
        self.assertEqual(cs.interrupt_chat_by_id(self.home, [], "in-tmux"),
                         (True, "Interrupted (Ctrl+C in its tmux pane); the chat stays open there"))
        for _ in range(100):
            if keys.exists() and keys.read_bytes():
                break
            time.sleep(0.05)
        self.assertEqual(keys.read_bytes(), b"\x03")   # Ctrl+C, as if pressed there (a key: its terminal is raw)
        self.assertTrue(cs.is_alive({"pid": pid, "procStart": cs.proc_start_time(pid)}))   # the chat stays

    def test_interrupt_only_in_tmux_and_while_working(self):
        self.chat("plain", status="busy")
        self.assertIn("doesn't run in tmux", cs.interrupt_chat_by_id(self.home, [], "plain")[1])
        self.chat("done-now", tmux="t:@1.%1")
        self.assertIn("nothing to interrupt", cs.interrupt_chat_by_id(self.home, [], "done-now")[1])
        self.chat("shell-left", tmux="t:@1.%2", status="shell")  # turn over, a background command runs
        self.assertIn("would land at its prompt", cs.interrupt_chat_by_id(self.home, [], "shell-left")[1])

    def test_command_line(self):
        proc = self.chat("cli-chat", status="busy")
        env = dict(os.environ, HOME=str(self.home), XDG_CACHE_HOME=str(self.cache))
        run = lambda *args: json.loads(subprocess.run([sys.executable, "-I", str(CODE / "talpy_den.py"), *args],
                                                      capture_output=True, text=True, env=env).stdout)
        self.assertFalse(run("--end", "cli-chat", "--profile", ".claude-work")["ok"])   # it's working: not without --busy
        self.assertEqual(run("--end", "cli-chat", "--profile", ".claude-work", "--busy"),
                         {"ok": True, "message": "Stopped; the chat is kept"})
        self.assertEqual(proc.wait(timeout=5), -15)
        calls = []
        with Patch(stop=lambda home, extra, sid, prof=None, busy=False: calls.append(("stop", sid, busy)) or (True, ""),
                   interrupt=lambda home, extra, sid, prof=None: calls.append(("interrupt", sid, prof)) or (True, "")), \
                contextlib.redirect_stdout(io.StringIO()):
            jump.main(["--stop", "a", "--busy"])
            jump.main(["--stop", "b"])
            jump.main(["--interrupt", "c", "--profile", ".claude-work"])
        self.assertEqual(calls, [("stop", "a", True), ("stop", "b", False), ("interrupt", "c", ".claude-work")])


class NewChatTests(Fixture):
    def test_opens_claude_on_the_profile_in_the_folder(self):
        folder = self.home / "repos/a"
        folder.mkdir(parents=True)
        opened = []
        with Patch(open_terminal=lambda cwd, cmd: opened.append((cwd, cmd)) or True,
                   shutil=type("W", (), {"which": staticmethod(lambda n: "/usr/bin/" + n)})):
            ok, msg = jump.new_chat(self.home, [], ".claude-work", str(folder))
            self.assertEqual(jump.new_chat(self.home, [], ".claude-nope")[0], False)
        self.assertTrue(ok, msg)
        # with background sessions around, plain `claude` opens the agent view: ask for a normal chat
        self.assertEqual(opened, [(str(folder), "CLAUDE_CODE_DISABLE_AGENT_VIEW=1 "
                                   f"CLAUDE_CONFIG_DIR={(self.home / '.claude-work').resolve()} claude")])

    def test_profile_picks_the_right_copy_of_a_shared_chat(self):
        # the same chat id live in two profiles (a chat shared across profiles)
        write(self.home / ".claude-personal/sessions/40.json", session("busy", status="idle"))
        self.assertEqual(jump.find_session(self.home, [], "busy", ".claude-personal")[0].label, "personal")
        self.assertEqual(jump.find_session(self.home, [], "busy", ".claude-work")[0].label, "work")


class ScopeTests(unittest.TestCase):
    """Programs the widget starts get a systemd scope of their own, where there's a systemd user manager."""

    def prefix(self, name="konsole", installed=True, manager=True, check=0):
        checks = []

        def run(args, **kw):
            checks.append(args)
            if isinstance(check, Exception):
                raise check
            return subprocess.CompletedProcess(args, check)
        with tempfile.TemporaryDirectory() as runtime:
            if manager:
                Path(runtime, "systemd").mkdir()
                Path(runtime, "systemd", "private").touch()
            old = os.environ.get("XDG_RUNTIME_DIR")
            os.environ["XDG_RUNTIME_DIR"] = runtime
            try:
                which = lambda n: "/usr/bin/systemd-run" if installed and n == "systemd-run" else None
                with Patch(shutil=type("W", (), {"which": staticmethod(which)}),
                           subprocess=type("S", (), {"run": staticmethod(run), "DEVNULL": None,
                                                     "TimeoutExpired": subprocess.TimeoutExpired})):
                    return jump.scope_prefix(name), checks
            finally:
                if old is None:
                    os.environ.pop("XDG_RUNTIME_DIR")
                else:
                    os.environ["XDG_RUNTIME_DIR"] = old

    def test_scope_named_after_the_program(self):
        prefix, [check] = self.prefix("code-insiders")
        self.assertEqual(check, ["/usr/bin/systemd-run", "--user", "--scope", "--quiet", "--collect", "--", "true"])
        self.assertEqual(prefix[:5], ["/usr/bin/systemd-run", "--user", "--scope", "--quiet", "--collect"])
        self.assertRegex(prefix[5], r"^--unit=app-talpyden-code_insiders-[0-9a-f]{8}\.scope$")
        self.assertEqual(prefix[6:], ["--"])
        self.assertNotEqual(self.prefix()[0][5], self.prefix()[0][5])   # a new name each time

    def test_started_as_before_without_a_working_systemd(self):
        self.assertEqual(self.prefix(installed=False), ([], []))
        self.assertEqual(self.prefix(manager=False), ([], []))
        self.assertEqual(self.prefix(check=1)[0], [])
        self.assertEqual(self.prefix(check=OSError("no"))[0], [])
        self.assertEqual(self.prefix(check=subprocess.TimeoutExpired("systemd-run", 5))[0], [])


class ChooseFolderTests(Fixture):
    """New chat in a folder you pick: the desktop's folder dialog, opening in your home folder."""

    def dialog(self, installed, returncode=0, stdout=""):
        ran = []

        def run(args, **kw):
            ran.append(args)
            return subprocess.CompletedProcess(args, returncode, stdout, "")
        which = lambda name: f"/usr/bin/{name}" if name in installed else None
        with Patch(shutil=type("W", (), {"which": staticmethod(which)}), on_gnome=lambda: False,
                   subprocess=type("S", (), {"run": staticmethod(run), "DEVNULL": None, "PIPE": None,
                                             "CompletedProcess": subprocess.CompletedProcess})):
            return jump.choose_folder("New chat in…", self.home), ran

    def test_kde_dialog_opens_in_the_home_folder(self):
        result, [args] = self.dialog({"kdialog", "zenity"}, stdout="/home/me/repos/b\n")
        self.assertEqual(result, ("/home/me/repos/b", ""))
        self.assertEqual(args, ["kdialog", "--title", "New chat in…", "--getexistingdirectory", str(self.home)])

    def test_cancelled(self):
        self.assertEqual(self.dialog({"kdialog"}, returncode=1)[0], (None, ""))
        self.assertEqual(self.dialog({"kdialog"}, stdout="  \n")[0], (None, ""))

    def test_gtk_dialog_without_kdialog_and_none_at_all(self):
        result, [args] = self.dialog({"zenity"}, stdout="/srv/x\n")
        self.assertEqual((result, args[:3], args[-1]), (("/srv/x", ""), ["zenity", "--file-selection", "--directory"],
                                                         f"--filename={self.home}/"))
        self.assertEqual(self.dialog(set()), ((None, "No folder dialog found (install kdialog)"), []))

    def choosing(self, dirname, chosen):
        asked, opened = [], []

        def choose(title, start):
            asked.append((title, start))
            return chosen
        with Patch(choose_folder=choose, open_terminal=lambda cwd, cmd: opened.append(cwd) or True,
                   shutil=type("W", (), {"which": staticmethod(lambda n: "/usr/bin/" + n)})):
            return jump.new_chat_choosing_folder(self.home, [], dirname), asked, opened

    def test_new_chat_in_the_chosen_folder(self):
        folder = self.home / "repos/b"
        folder.mkdir(parents=True)
        (ok, msg), asked, opened = self.choosing(".claude-work", (str(folder), ""))
        self.assertTrue(ok, msg)
        self.assertEqual(asked, [("New Claude chat on work in…", self.home)])
        self.assertEqual(opened, [str(folder)])

    def test_cancelling_does_nothing_and_errors_are_reported(self):
        self.assertEqual(self.choosing(".claude-work", (None, "")), ((True, ""), [("New Claude chat on work in…", self.home)], []))
        (result, _, opened) = self.choosing(".claude-work", (None, "No folder dialog found (install kdialog)"))
        self.assertEqual((result, opened), ((False, "No folder dialog found (install kdialog)"), []))
        (result, _, opened) = self.choosing(".claude-work", (str(self.home / "gone"), ""))
        self.assertEqual((result[0], opened), (False, []))

    def test_unknown_profile_fails_before_asking(self):
        (ok, msg), asked, _ = self.choosing(".claude-nope", (str(self.home), ""))
        self.assertEqual((ok, asked), (False, []))

    def test_command_line(self):
        calls = []
        out = io.StringIO()
        with Patch(new_chat_choosing_folder=lambda home, extra, dirname, start, task: calls.append((dirname, extra)) or (True, "")), \
                contextlib.redirect_stdout(out):
            jump.main(["--new-chat", ".claude-work", "--choose-folder", "--config-dir", "/x"])
        self.assertEqual(calls, [(".claude-work", ["/x"])])
        self.assertEqual(json.loads(out.getvalue()), {"ok": True, "message": ""})


class ResumeChatTests(Fixture):
    """A finished chat with no session or job on the profile (a shared chat
    last used there): reopened with `claude --resume`."""

    def setUp(self):
        super().setUp()
        self.folder = self.home / "repos/w"
        self.folder.mkdir(parents=True)
        lines = [{"type": "user", "cwd": "/elsewhere", "sessionId": "chatx"},
                 {"type": "assistant", "cwd": str(self.folder), "sessionId": "chatx"}]
        write(self.home / ".claude-personal/projects/-w/chatx.jsonl", "".join(json.dumps(l) + "\n" for l in lines))
        write(self.home / ".claude-personal/.claude.json", {
            "oauthAccount": {"accountUuid": "acct-pro", "organizationType": "claude_pro"},
            "projects": {str(self.folder): {"hasTrustDialogAccepted": True}}})

    def opened(self, *args):
        opened = []
        with Patch(open_terminal=lambda cwd, cmd: opened.append((cwd, cmd)) or True,
                   shutil=type("W", (), {"which": staticmethod(lambda n: "/usr/bin/" + n)})):
            result = jump.jump(self.home, [], *args)
        return result, opened

    def test_resumes_in_the_chats_last_folder(self):
        (ok, msg), opened = self.opened("chatx", ".claude-personal")
        self.assertEqual((ok, msg), (True, "Reopened the chat in a terminal"))
        real = (self.home / ".claude-personal").resolve()
        self.assertEqual(opened, [(str(self.folder), f"CLAUDE_CONFIG_DIR={real} claude --resume chatx")])

    def test_only_on_the_profile_asked_for(self):
        (ok, msg), opened = self.opened("chatx", ".claude-work")
        self.assertEqual((ok, msg, opened), (False, "That chat isn't running any more", []))

    def test_explains_trust_question(self):
        cs.write_json_atomic(self.home / ".claude-personal/.claude.json", {"projects": {}})
        prof = next(p for p in cs.discover_profiles(self.home) if p.label == "personal")
        cmd = jump.resume_command(prof, "chatx", self.home, str(self.folder))
        self.assertIn("Claude will ask whether you trust ~/repos/w before", cmd)
        self.assertTrue(cmd.endswith("claude --resume chatx"))

    def test_profile_named_by_real_folder_or_path(self):
        prof = next(p for p in cs.discover_profiles(self.home) if p.label == "work")
        self.assertTrue(cs.matches_profile(prof, ".claude-work"))
        self.assertTrue(cs.matches_profile(prof, str(self.home / ".claude-work")))
        self.assertFalse(cs.matches_profile(prof, ".claude-personal"))


class SwitchedLinkTests(unittest.TestCase):
    """A session started through ~/.claude before it was switched: its file is
    still in the old profile, but it runs on the new one."""

    def test_found_under_the_profile_it_runs_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            for name in ("work", "personal"):
                write(home / f".claude-{name}/.profile-name", name)
                write(home / f".claude-{name}/.claude.json", {"oauthAccount": {"accountUuid": name}})
                (home / f".claude-{name}/sessions").mkdir()
            (home / ".claude").symlink_to(home / ".claude-personal")
            env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CONFIG_DIR"}
            env["CLAUDE_CONFIG_DIR"] = str(home / ".claude")
            child = subprocess.Popen(["sleep", "60"], env=env)
            try:
                # Popen returns before exec has set up the new environment
                for _ in range(500):
                    if cs.proc_start_time(child.pid) and cs.process_config_dir(child.pid):
                        break
                    time.sleep(0.01)
                start = cs.proc_start_time(child.pid)
                write(home / f".claude-work/sessions/{child.pid}.json",
                      {"pid": child.pid, "procStart": start, "sessionId": "s1", "kind": "interactive", "status": "busy"})
                profile, entry, _, _ = jump.find_session(home, [], "s1", ".claude-personal")
                self.assertEqual((profile.label, entry["sessionId"]), ("personal", "s1"))
                self.assertIsNone(jump.find_session(home, [], "s1", ".claude-work")[1] and None)
            finally:
                child.kill()
                child.wait()


class DismissHelperTests(unittest.TestCase):
    def test_dismiss_and_undo(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get("XDG_CACHE_HOME")
            os.environ["XDG_CACHE_HOME"] = tmp
            try:
                self.assertTrue(jump.dismiss(Path(tmp), [], "abc")[0])
                self.assertIn("abc", cs.load_dismissed(cs.cache_dir(Path(tmp))))
                self.assertEqual(jump.undismiss_all(Path(tmp), [])[1], "Showing 1 hidden chat again")
                self.assertEqual(cs.load_dismissed(cs.cache_dir(Path(tmp))), {})
                self.assertEqual(jump.undismiss_all(Path(tmp), [])[1], "No chat was hidden")
            finally:
                if old is None:
                    os.environ.pop("XDG_CACHE_HOME")
                else:
                    os.environ["XDG_CACHE_HOME"] = old


class AttachedTabTests(unittest.TestCase):
    # tabs: (session, shell pid, foreground pid, title)
    TABS = {100: [("1", 11, 11, "~ : bash"), ("2", 12, 22, "🏠 ◑ fix the parser"), ("3", 13, 23, "🏠 ✳ other"),
                  ("4", 14, 14, "🏠")]}
    CHILDREN = {11: [], 12: [22], 13: [23], 14: [24]}

    def find(self, cmdlines, config_dirs, job_id="ab12cd34", name="fix the parser", config_dir=Path("/h/.claude-work")):
        with Patch(konsole_pids=lambda: list(self.TABS), konsole_tabs=lambda k: self.TABS[k],
                   process_children=lambda: self.CHILDREN,
                   proc_name=lambda pid: "claude" if pid in cmdlines else "bash",
                   proc_cmdline=lambda pid: cmdlines.get(pid, []),
                   proc_config_dir=lambda pid: config_dirs.get(pid)):
            return jump.find_attached_tab(job_id, name, config_dir)

    def test_claude_attach_on_command_line(self):
        self.assertEqual(self.find({23: ["claude", "attach", "ab12cd34"]}, {}), (100, "3"))

    def test_attach_under_a_wrapper_shell(self):
        # the widget's own windows: bash -c "...; claude attach <id>; exec bash" is the foreground
        self.assertEqual(self.find({24: ["claude", "attach", "ab12cd34"]}, {}), (100, "4"))

    def test_agent_view_matched_by_title_and_profile(self):
        self.assertEqual(self.find({22: ["claude"]}, {22: Path("/h/.claude-work")}), (100, "2"))
        self.assertIsNone(self.find({22: ["claude"]}, {22: Path("/h/.claude-personal")}))  # other profile

    def test_nothing_attached(self):
        self.assertIsNone(self.find({}, {}))


class AttachedElsewhereTests(unittest.TestCase):
    """A background job attached in a terminal that isn't Konsole (VS Code's,
    GNOME's, a tmux pane) is brought up, not attached a second time."""

    PROFILE = type("P", (), {"path": Path("/h/.claude-work")})()

    def clients(self, cmdlines, config_dirs, name="fix the parser"):
        with Patch(claude_pids=lambda: list(cmdlines), proc_cmdline=lambda pid: cmdlines[pid],
                   proc_config_dir=lambda pid: config_dirs.get(pid)):
            return jump.attach_clients("ab12cd34", name, Path("/h/.claude-work"))

    def test_attach_clients_by_id_or_by_name_on_this_profile(self):
        self.assertEqual(self.clients({5: ["claude", "attach", "ab12cd34"], 6: ["claude"], 7: ["claude", "attach", "ff00ff00"]}, {}), [5])
        self.assertEqual(self.clients({8: ["claude", "attach", "fix the parser"]}, {8: Path("/h/.claude-work")}), [8])
        self.assertEqual(self.clients({8: ["claude", "attach", "fix the parser"]}, {8: Path("/h/.claude-personal")}), [], "another profile's job")
        self.assertEqual(self.clients({8: ["claude", "attach", ""]}, {8: Path("/h/.claude-work")}, name=""), [])

    def jump_job(self, clients, shown):
        raised, opened = [], []
        with Patch(live_entries=lambda p: [], find_attached_tab=lambda *a: None,
                   attach_clients=lambda job_id, name, config_dir: clients,
                   tmux_pane_of=lambda pid: "work:@1.%3" if pid == 9 else "",
                   jump_terminal=lambda entry, what: raised.append(entry) or shown(entry["pid"]),
                   claude_in_terminal=lambda home: "claude", attach_command=lambda *a: "claude attach ab12cd34",
                   open_terminal=lambda cwd, cmd: opened.append(cmd) or True):
            answer = jump.jump_job(self.PROFILE, "ab12cd34", {"cwd": "/h/repos/api"}, "fix the parser", Path("/h"))
        return answer, raised, opened

    def test_a_terminal_attached_elsewhere_comes_up(self):
        answer, raised, opened = self.jump_job([5], lambda pid: (True, "Switched to the VS Code terminal running this background job"))
        self.assertEqual(answer, (True, "Switched to the VS Code terminal running this background job"))
        self.assertEqual(raised, [{"pid": 5, "cwd": "/h/repos/api", "tmux": ""}])
        self.assertEqual(opened, [], "no second client")

    def test_one_in_tmux_selects_its_pane(self):
        _, raised, _ = self.jump_job([9], lambda pid: (True, ""))
        self.assertEqual(raised[0]["tmux"], "work:@1.%3")

    def test_one_that_cant_be_shown_still_gets_a_terminal(self):
        # (e.g. attached in an SSH login to this computer: no window here)
        answer, raised, opened = self.jump_job([5], lambda pid: (False, "no window"))
        self.assertEqual(answer, (True, "Opened the background job in a terminal"))
        self.assertEqual(opened, ["claude attach ab12cd34"])


class LinkedProfileTests(unittest.TestCase):
    """~/.claude as a link to ~/.claude-personal: one profile, snapshots under both names."""

    def test_linked_default_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            home, cache = Path(tmp) / "home", Path(tmp) / "cache"
            write(home / ".claude-personal/.profile-name", "personal")
            write(home / ".claude-personal/.claude.json",
                  {"oauthAccount": {"accountUuid": "acct", "organizationType": "claude_pro"}})
            write(home / ".claude-personal/sessions/1.json", session("s1", status="busy"))
            (home / ".claude").symlink_to(home / ".claude-personal")
            write(cache / "statusline/.claude-personal/s1.json", {"context_window": {"used_percentage": 12},
                                                                  "rate_limits": {"five_hour": {"used_percentage": 7}}})
            profiles = cs.discover_profiles(home)
            self.assertEqual([(p.label, sorted(p.snapshot_dirs)) for p in profiles],
                             [("personal", [".claude", ".claude-personal"])])
            self.assertEqual(profiles[0].path, home / ".claude-personal")  # named after itself, not the link
            r = cs.collect(home, cache, with_tokens=False)
            (group,) = r["groups"]
            self.assertEqual([s["sessionId"] for s in group["sessions"]], ["s1"])  # not listed twice
            self.assertEqual(group["sessions"][0]["context"], 12)
            self.assertEqual(group["limits"]["windows"][0]["pct"], 7)



class FindClaudeTests(unittest.TestCase):
    """claude is found where the desktop session's PATH doesn't reach."""

    CHAT = "7c1e0000-0000-4000-8000-000000000001"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        (self.home / "empty").mkdir()
        saved = {k: os.environ.get(k) for k in ("PATH", "SHELL")}
        self.addCleanup(lambda: [os.environ.__setitem__(k, v) if v is not None else os.environ.pop(k, None)
                                 for k, v in saved.items()])
        os.environ["PATH"] = str(self.home / "empty")  # nothing on PATH
        os.environ["SHELL"] = str(self.home / "no-shell")

    def exe(self, path, text="#!/bin/sh\n"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        path.chmod(0o755)
        return path

    def test_install_places_and_the_newest_nvm_node(self):
        self.assertEqual(cs.find_claude(self.home), "claude")  # nowhere
        self.exe(self.home / ".nvm/versions/node/v9.11.2/bin/claude")
        newest = self.exe(self.home / ".nvm/versions/node/v20.3.0/bin/claude")
        self.assertEqual(cs.find_claude(self.home), str(newest))
        installer = self.exe(self.home / ".local/bin/claude")
        self.assertEqual(cs.find_claude(self.home), str(installer))  # Claude's installer comes first

    def test_the_login_shells_path_only_when_asked(self):
        claude = self.exe(self.home / "tools/bin/claude")
        os.environ["SHELL"] = str(self.exe(self.home / "login-shell",
                                           f"#!/bin/sh\necho Welcome back\necho PATH={claude.parent}:/usr/bin\n"))
        self.assertEqual(cs.find_claude(self.home), "claude")  # status checks never start a shell
        self.assertEqual(cs.find_claude(self.home, ask_shell=True), str(claude))

    def test_status_checks_ask_the_login_shell_once_an_hour(self):
        cache = self.home / "cache"
        claude = self.exe(self.home / "tools/bin/claude")
        asked = self.home / "asked"
        os.environ["SHELL"] = str(self.exe(self.home / "login-shell",
                                           f"#!/bin/sh\necho x >> {asked}\necho PATH={claude.parent}\n"))
        now = 1000000.0
        self.assertEqual(cs.cached_find_claude(self.home, cache, now), str(claude))
        self.assertEqual(cs.cached_find_claude(self.home, cache, now + 60), str(claude))
        self.assertEqual(asked.read_text().count("x"), 1)   # the second check used the first answer
        claude.unlink()   # uninstalled: noticed at once
        self.assertIsNone(cs.cached_find_claude(self.home, cache, now + 120))
        self.assertIsNone(cs.cached_find_claude(self.home, cache, now + 3700))   # an hour on: asked again
        self.assertEqual(asked.read_text().count("x"), 2)
        found = self.exe(self.home / ".local/bin/claude")   # where it's usually installed: no shell needed
        self.assertEqual(cs.cached_find_claude(self.home, cache, now + 3800), str(found))
        self.assertEqual(asked.read_text().count("x"), 2)

    def test_node_next_to_claude_goes_on_path(self):
        claude = self.exe(self.home / ".nvm/versions/node/v20.3.0/bin/claude")
        self.assertEqual(cs.claude_words("claude"), "claude")
        self.assertEqual(cs.claude_words(str(claude)), str(claude))
        self.exe(claude.parent / "node")
        self.assertEqual(cs.claude_words(str(claude)), f'PATH={claude.parent}:"$PATH" {claude}')

    def test_reopening_runs_it_by_its_full_path_or_says_what_to_do(self):
        folder = self.home / "proj"
        folder.mkdir()
        write(self.home / ".claude/projects/-proj" / f"{self.CHAT}.jsonl",
              json.dumps({"type": "user", "cwd": str(folder), "sessionId": self.CHAT}) + "\n")
        opened = []
        with Patch(open_terminal=lambda cwd, cmd: opened.append(cmd) or True,
                   shutil=type("W", (), {"which": staticmethod(lambda n: None)})):  # not on the desktop's PATH
            self.assertEqual(jump.resume(self.home, [], self.CHAT), (False, jump.NO_CLAUDE))
            claude = self.exe(self.home / ".local/bin/claude")
            self.assertEqual(jump.resume(self.home, [], self.CHAT), (True, "Reopened the chat in a terminal"))
        self.assertEqual(len(opened), 1)
        self.assertTrue(opened[0].endswith(f"env -u CLAUDE_CONFIG_DIR {claude} --resume {self.CHAT}"), opened[0])


class SharedChatActionTests(unittest.TestCase):
    """Share, continue on another account and unshare (sharing.py), on a stock
    ~/.claude next to ~/.claude-work: no .profile-name files, no other tools."""

    CHAT = "9a8b7c6d-0000-4000-8000-000000000001"
    KEY = "-repos-app"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.folder = self.home / "repos/app"
        self.folder.mkdir(parents=True)
        trusted = {"projects": {str(self.folder): {"hasTrustDialogAccepted": True}}}
        write(self.home / ".claude.json", {"oauthAccount": {"accountUuid": "personal"}, **trusted})
        write(self.home / ".claude-work/.claude.json", {"oauthAccount": {"accountUuid": "work"}, **trusted})
        for d in (".claude", ".claude-work"):
            (self.home / d / "sessions").mkdir(parents=True)
        mine = self.home / ".claude"
        write(mine / "projects" / self.KEY / f"{self.CHAT}.jsonl",
              json.dumps({"type": "user", "cwd": str(self.folder), "sessionId": self.CHAT}) + "\n")
        write(mine / "projects" / self.KEY / self.CHAT / "subagents/agent-1.jsonl", "{}\n")
        write(mine / "file-history" / self.CHAT / "abc@v1", "old text\n")
        self.store = self.home / ".local/share/claude-status/shared-chats" / self.KEY
        env = {k: os.environ.get(k) for k in ("XDG_STATE_HOME", "XDG_DATA_HOME")}
        os.environ["XDG_STATE_HOME"] = str(self.home / "state")
        os.environ.pop("XDG_DATA_HOME", None)
        self.addCleanup(lambda: [os.environ.__setitem__(k, v) if v else os.environ.pop(k, None) for k, v in env.items()])

    def tearDown(self):
        self.tmp.cleanup()

    def run_action(self, action, *args):
        opened = []
        with Patch(open_terminal=lambda cwd, cmd: opened.append((cwd, cmd)) or True,
                   shutil=type("W", (), {"which": staticmethod(lambda n: "/usr/bin/" + n)})):
            result = action(self.home, [], self.CHAT, *args)
        return result, opened

    def part(self, profile, what):
        base = self.home / profile
        return {"chat": base / "projects" / self.KEY / f"{self.CHAT}.jsonl",
                "folder": base / "projects" / self.KEY / self.CHAT,
                "history": base / "file-history" / self.CHAT}[what]

    def assert_linked(self, profile):
        """The profile has the shared chat: the same file, its folders through the store."""
        self.assertTrue(os.path.samefile(self.part(profile, "chat"), self.store / f"{self.CHAT}.jsonl"))
        self.assertEqual(Path(os.readlink(self.part(profile, "folder"))), self.store / self.CHAT)
        self.assertEqual(Path(os.readlink(self.part(profile, "history"))), self.store / f"{self.CHAT}.file-history")

    def assert_own(self, profile):
        """The profile has the chat as a normal chat of its own."""
        for what in ("chat", "folder", "history"):
            self.assertFalse(self.part(profile, what).is_symlink(), what)
        self.assertEqual(os.stat(self.part(profile, "chat")).st_nlink, 1)
        self.assertEqual((self.part(profile, "folder") / "subagents/agent-1.jsonl").read_text(), "{}\n")
        self.assertEqual((self.part(profile, "history") / "abc@v1").read_text(), "old text\n")

    def assert_gone(self, profile):
        for what in ("chat", "folder", "history"):
            self.assertFalse(os.path.lexists(self.part(profile, what)), what)

    def test_continue_on_another_account_shares_then_resumes_there(self):
        (ok, msg), opened = self.run_action(jump.continue_on, ".claude-work")
        self.assertEqual((ok, msg), (True, "Reopened the chat in a terminal"))
        self.assert_linked(".claude")
        self.assert_linked(".claude-work")
        self.assertEqual((self.part(".claude-work", "folder") / "subagents/agent-1.jsonl").read_text(), "{}\n")
        self.assertEqual(self.store.stat().st_mode & 0o077, 0)  # only you can read the store
        work = (self.home / ".claude-work").resolve()
        self.assertEqual(opened, [(str(self.folder), f"CLAUDE_CONFIG_DIR={work} claude --resume {self.CHAT}")])
        # already shared: just reopened
        (ok, _), opened = self.run_action(jump.continue_on, ".claude-work")
        self.assertTrue(ok)
        self.assertEqual(len(opened), 1)
        self.assert_linked(".claude-work")

    def test_continue_shares_with_that_account_only(self):
        (self.home / ".claude-lab/sessions").mkdir(parents=True)
        (ok, msg), _ = self.run_action(jump.continue_on, ".claude-work")
        self.assertTrue(ok, msg)
        self.assert_gone(".claude-lab")

    def test_shared_chat_shows_as_shared(self):
        self.run_action(jump.share)
        r = cs.collect(self.home, self.home / "cache", with_tokens=False)
        self.assertTrue(r["canShare"])
        self.assertEqual(sorted(g["shareProfile"] for g in r["groups"]), [".claude", ".claude-work"])
        shared = [c for g in r["groups"] for c in g["recent"] if c["sessionId"] == self.CHAT]
        self.assertTrue(shared and all(c["shared"] for c in shared))

    def test_refuses_while_open_in_a_session(self):
        write(self.home / ".claude/sessions/50.json",
              {"pid": os.getpid(), "procStart": cs.proc_start_time(os.getpid()), "sessionId": self.CHAT,
               "kind": "interactive", "status": "idle"})
        for action, args in ((jump.continue_on, (".claude-work",)), (jump.share, ()), (jump.unshare, (".claude",))):
            (ok, msg), opened = self.run_action(action, *args)
            self.assertFalse(ok)
            self.assertIn("open on main", msg)
            self.assertEqual(opened, [])
        self.assertFalse(self.store.exists())
        self.assert_own(".claude")

    def test_share_then_keep_only_on_one_account(self):
        (ok, msg), _ = self.run_action(jump.share)
        self.assertEqual((ok, msg), (True, "Chat shared: it's now on main, work."))
        (ok, msg), _ = self.run_action(jump.share)
        self.assertEqual((ok, msg), (True, "This chat is already shared with main, work."))
        (ok, msg), _ = self.run_action(jump.unshare, ".claude")
        self.assertEqual((ok, msg), (True, "This chat is now a normal chat of main again. Removed from work."))
        self.assert_own(".claude")
        self.assert_gone(".claude-work")
        self.assertFalse(self.store.exists())

    def test_keep_only_on_the_other_account(self):
        self.run_action(jump.share)
        (ok, msg), _ = self.run_action(jump.unshare, ".claude-work")
        self.assertTrue(ok, msg)
        self.assert_own(".claude-work")
        self.assert_gone(".claude")
        self.assertFalse(self.store.exists())

    def test_unshare_needs_a_shared_chat_and_a_profile(self):
        (ok, msg), _ = self.run_action(jump.unshare, ".claude")
        self.assertEqual((ok, msg), (False, "This chat isn't shared"))
        (ok, msg), _ = self.run_action(jump.unshare, ".claude-nope")
        self.assertEqual((ok, msg), (False, "No Claude profile called .claude-nope"))
        self.assert_own(".claude")

    def test_different_chat_with_the_same_id_left_alone(self):
        write(self.part(".claude-work", "chat"), "{}\n")  # its own file
        (ok, msg), opened = self.run_action(jump.continue_on, ".claude-work")
        self.assertFalse(ok)
        self.assertIn("different chat with the same id", msg)
        (ok, msg), _ = self.run_action(jump.share)
        self.assertFalse(ok)
        self.assertIn("Different chats have this id", msg)
        (ok, msg), _ = self.run_action(jump.share, ".claude")  # this copy: the other profile is skipped
        self.assertEqual((ok, msg), (False, "Not shared: work already has a different chat with the same id"))
        self.assertEqual(self.part(".claude-work", "chat").read_text(), "{}\n")

    def test_left_over_store_folder(self):
        write(self.store / self.CHAT / "stale.txt", "?")
        (ok, msg), _ = self.run_action(jump.share)
        self.assertFalse(ok)
        self.assertIn("is already there", msg)
        self.assertFalse(self.part(".claude", "folder").is_symlink())
        self.assertFalse((self.store / f"{self.CHAT}.jsonl").exists())  # refused before changing anything

    def test_a_linked_projects_folder_is_one_copy_not_two(self):
        """~/.claude-work/projects linked to ~/.claude/projects: both see the
        same file. Keeping it on one account must never delete it."""
        (self.home / ".claude-work/projects").symlink_to(self.home / ".claude/projects")
        (ok, msg), _ = self.run_action(jump.unshare, ".claude")
        self.assertEqual((ok, msg), (False, "This chat isn't shared"))
        self.assertTrue(self.part(".claude", "chat").is_file())
        self.run_action(jump.share)
        for keep in (".claude", ".claude-work"):
            (ok, msg), _ = self.run_action(jump.unshare, keep)
            self.assertTrue(self.part(".claude", "chat").is_file(), (keep, ok, msg))
            self.assertEqual((self.part(".claude", "folder") / "subagents/agent-1.jsonl").read_text(), "{}\n")
            self.run_action(jump.share)

    def test_a_bind_mounted_projects_folder_is_one_copy_not_two(self):
        """The same through a bind mount (mount --bind), which no symlink
        explains: two paths, one file and one directory entry. Keeping it on
        one account deleted that entry, the chat's only one."""
        if not shutil.which("unshare") or subprocess.run(["unshare", "-rm", "true"], capture_output=True).returncode:
            self.skipTest("no user namespace for a bind mount here")
        (self.home / ".claude-work/projects").mkdir()
        chat = self.part(".claude", "chat")
        script = (f"import json, subprocess, sys\nsys.path.insert(0, {str(CODE)!r})\nimport jump\n"
                  f"from pathlib import Path\nhome, chat = Path({str(self.home)!r}), Path({str(chat)!r})\n"
                  "subprocess.run(['mount', '--bind', str(home / '.claude/projects'), str(home / '.claude-work/projects')],"
                  " check=True)\n"
                  f"out = [[*jump.unshare(home, [], {self.CHAT!r}, '.claude'), chat.is_file()]]\n"
                  "for keep in ('.claude', '.claude-work'):\n"
                  f"    out.append([*jump.share(home, [], {self.CHAT!r}), chat.is_file()])\n"
                  f"    out.append([*jump.unshare(home, [], {self.CHAT!r}, keep), chat.is_file()])\n"
                  "print(json.dumps(out))\n")
        r = subprocess.run(["unshare", "-rm", sys.executable, "-I", "-B", "-c", script], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        steps = json.loads(r.stdout)
        self.assertEqual(steps[0], [False, "This chat isn't shared", True])
        self.assertTrue(all(step[2] for step in steps), steps)
        self.assertEqual((self.part(".claude", "folder") / "subagents/agent-1.jsonl").read_text(), "{}\n")

    def test_keep_only_takes_back_what_the_others_left_in_the_store(self):
        """Shared before by another tool (one file, but a folder of each
        account's own): the store's folder isn't left behind."""
        self.part(".claude-work", "chat").parent.mkdir(parents=True)
        os.link(self.part(".claude", "chat"), self.part(".claude-work", "chat"))
        write(self.part(".claude-work", "folder") / "subagents/agent-2.jsonl", "{}\n")
        (ok, msg), _ = self.run_action(jump.share)
        self.assertTrue(ok, msg)
        (ok, msg), _ = self.run_action(jump.unshare, ".claude-work")
        self.assertTrue(ok, msg)
        folder = self.part(".claude-work", "folder")
        self.assertEqual(sorted(p.name for p in (folder / "subagents").iterdir()), ["agent-1.jsonl", "agent-2.jsonl"])
        self.assertFalse(self.store.exists())
        (ok, msg), _ = self.run_action(jump.share)
        self.assertEqual((ok, msg), (True, "Chat shared: it's now on main, work."))

    def test_chat_shared_into_another_store(self):
        """Shared the same way by another tool, into its own store: handled where it is."""
        other = self.home / "elsewhere" / self.KEY
        other.mkdir(parents=True)
        mine = self.home / ".claude"
        os.link(self.part(".claude", "chat"), other / f"{self.CHAT}.jsonl")
        for what, name in (("folder", self.CHAT), ("history", f"{self.CHAT}.file-history")):
            os.rename(self.part(".claude", what), other / name)
            os.symlink(other / name, self.part(".claude", what))
        (self.home / ".claude-work/projects" / self.KEY).mkdir(parents=True)
        os.link(other / f"{self.CHAT}.jsonl", self.part(".claude-work", "chat"))
        os.symlink(other / self.CHAT, self.part(".claude-work", "folder"))
        # a third account joins: linked to that store
        (self.home / ".claude-lab/sessions").mkdir(parents=True)
        (ok, msg), _ = self.run_action(jump.continue_on, ".claude-lab")
        self.assertTrue(ok, msg)
        self.assertEqual(Path(os.readlink(self.part(".claude-lab", "folder"))), other / self.CHAT)
        self.assertEqual(Path(os.readlink(self.part(".claude-lab", "history"))), other / f"{self.CHAT}.file-history")
        self.assertFalse(self.store.exists())
        # and kept only on work: its folders come back from there
        (ok, msg), _ = self.run_action(jump.unshare, ".claude-work")
        self.assertTrue(ok, msg)
        self.assert_own(".claude-work")
        self.assert_gone(".claude")
        self.assert_gone(".claude-lab")
        self.assertFalse(other.exists())
        self.assertTrue(mine.is_dir())

    def test_one_filesystem_or_nothing_happens(self):
        real = jump.sharing.device
        jump.sharing.device = lambda p: -1 if ".claude-work" in str(p) else real(p)  # work on another disk
        try:
            (ok, msg), opened = self.run_action(jump.continue_on, ".claude-work")
        finally:
            jump.sharing.device = real
        self.assertFalse(ok)
        self.assertIn("work is on another disk or partition than this chat", msg)
        self.assertEqual(opened, [])
        self.assert_own(".claude")
        self.assertFalse(self.store.exists())

    def test_continue_can_hand_back_the_command(self):
        """For the VS Code extension: shared, no terminal opened, the command to run instead."""
        opened = []
        with Patch(open_terminal=lambda cwd, cmd: opened.append(cmd) or True,
                   shutil=type("W", (), {"which": staticmethod(lambda n: "/usr/bin/" + n)})):
            ok, msg, command = jump.continue_command(self.home, [], self.CHAT, ".claude-work")
        self.assertEqual((ok, msg, opened), (True, "Continuing it on work", []))
        self.assert_linked(".claude-work")
        work = (self.home / ".claude-work").resolve()
        self.assertEqual(command, f"cd {self.folder} 2>/dev/null; CLAUDE_CONFIG_DIR={work} claude --resume {self.CHAT}")
        out = subprocess.run([sys.executable, "-I", str(CODE / "jump.py"), "--share", self.CHAT, "--print-command"],
                             capture_output=True, text=True)
        self.assertIn("usage", out.stderr)  # only with --continue

    def test_resume_can_hand_back_the_command(self):
        """For the VS Code extension (a chat the Recap names): no terminal
        opened, the command --resume would have opened one with."""
        (ok, msg, command), opened = self.run_action(jump.resume_command_of, ".claude")
        self.assertEqual((ok, msg, opened), (True, "", []))
        (ok, _), opened = self.run_action(jump.resume, ".claude")
        self.assertTrue(ok)
        self.assertEqual(opened, [(str(self.folder), command.split("; ", 1)[1])])
        self.assertTrue(command.startswith(f"cd {self.folder} 2>/dev/null; "), command)
        self.assertIn(f"--resume {self.CHAT}", command)
        (ok, msg, command), _ = self.run_action(jump.resume_command_of, ".claude-work")
        self.assertEqual((ok, msg, command), (False, "That chat isn't on this account", None))
        out = subprocess.run([sys.executable, "-I", "-B", str(CODE / "jump.py"), "--resume", self.CHAT, "--vscode",
                              "--profile", ".claude", "--print-command"], capture_output=True, text=True)
        self.assertIn("usage", out.stderr)  # (not with --vscode: that opens it there)

    def test_command_line(self):
        out = subprocess.run([sys.executable, "-I", str(CODE / "jump.py"), "--continue", self.CHAT],
                             capture_output=True, text=True)
        self.assertNotEqual(out.returncode, 0)  # --continue needs --profile
        self.assertIn("usage", out.stderr)


class RemoteShowTests(unittest.TestCase):
    """Sessions that run on an SSH host but show here (VS Code Remote-SSH, ssh in a terminal)."""

    def test_ssh_target(self):
        cases = {
            ("ssh", "labserver"): "labserver",
            ("ssh", "-v", "-T", "-D", "33023", "-o", "ConnectTimeout=15", "labserver", "-T"): "labserver",
            ("ssh", "-t", "alice@labserver.uni.example", "claude"): "labserver.uni.example",
            ("ssh", "-l", "me", "-p", "2222", "box"): "box",
            ("ssh", "-p2222", "-tt", "box:22"): "box",
            ("ssh", "-Xp", "2222", "gpu"): "gpu",   # a group whose last flag takes the next word
            ("ssh", "-vp2222", "gpu"): "gpu",
            ("ssh", "jdoe@corp.example.com@gpu"): "gpu",   # ssh splits at the last @
            ("ssh", "-W", "[labserver]:22", "bastion"): None,       # a ProxyJump helper, not the session
            ("ssh", "-o", "X=1"): None,
            ("bash", "labserver"): None,
            ("/usr/bin/ssh", "--", "host"): "host",
        }
        for argv, want in cases.items():
            self.assertEqual(jump.ssh_target(list(argv)), want, argv)

    def procs(self, tree, names, argvs):
        return dict(process_children=lambda: tree, proc_name=lambda pid: names.get(pid, "bash"),
                    proc_cmdline=lambda pid: argvs.get(pid, []), host_names=lambda host: {host} | ({"labserver.uni.example"} if host == "labserver" else set()))

    def test_a_reply_link_opens_in_the_window_that_runs_the_chat(self):
        # (VS Code opens a link in the window focused last: the chat's is raised first)
        raised, opened = [], []
        fake = type("S", (), {"Popen": staticmethod(lambda args, **k: opened.append(args)), "DEVNULL": None})
        entry = {"pid": 500, "cwd": "/home/me/app", "sessionId": "abc-123"}
        with Patch(raise_window=lambda *a, **k: raised.append(a) or True, ancestors=lambda pid: [pid, 400],
                   subprocess=fake, shutil=type("W", (), {"which": staticmethod(lambda n: "/usr/bin/" + n)}),
                   time=type("T", (), {"sleep": staticmethod(lambda s: None)})), \
                mock.patch.object(cs, "find_chat_entry", return_value=entry):
            link = "vscode://anthropic.claude-code/open?session=abc-123&prompt=hi"
            self.assertEqual(jump.open_vscode_link(Path("/home/me"), [], "abc-123", link), (True, ""))
            self.assertFalse(jump.open_vscode_link(Path("/home/me"), [], "abc-123", "file:///etc/passwd")[0])
        self.assertEqual((raised, opened), ([([500, 400], "app")], [["/usr/bin/xdg-open", link]]))

    def test_vscode_window_connected_to_the_host(self):
        raised, opened = [], []
        tree = {100: [110], 110: [120]}
        names = {100: "code", 120: "ssh"}
        argvs = {100: ["/usr/share/code/code"], 120: ["ssh", "-T", "-D", "1", "labserver"]}
        fake = type("S", (), {"Popen": staticmethod(lambda args, **k: opened.append(args)), "DEVNULL": None})
        with Patch(vscode_main_pids=lambda: [100], raise_window=lambda *a, **k: raised.append((a, k)) or True,
                   subprocess=fake, shutil=type("W", (), {"which": staticmethod(lambda n: "/usr/bin/" + n)}),
                   time=type("T", (), {"sleep": staticmethod(lambda s: None)}), **self.procs(tree, names, argvs)):
            ok, msg = jump.jump_remote_vscode("labserver", "abc-123", "/home/me/proj")
        self.assertEqual((ok, msg), (True, "Opened the conversation in VS Code (labserver)"))
        self.assertEqual(raised, [(([100], "[SSH: labserver]"), {"require": True, "prefer": "proj"})])
        self.assertEqual(opened, [["/usr/bin/xdg-open", "vscode://anthropic.claude-code/open?session=abc-123"]])
        # a window connected by the host's HostName: its title has that name
        raised.clear()
        argvs[120] = ["ssh", "-T", "-D", "1", "labserver.uni.example"]
        with Patch(vscode_main_pids=lambda: [100], raise_window=lambda *a, **k: raised.append((a, k)) or True,
                   subprocess=fake, shutil=type("W", (), {"which": staticmethod(lambda n: "/usr/bin/" + n)}),
                   time=type("T", (), {"sleep": staticmethod(lambda s: None)}), **self.procs(tree, names, argvs)):
            self.assertTrue(jump.jump_remote_vscode("labserver", "abc-123", "/home/me/proj")[0])
        self.assertEqual(raised, [(([100], "[SSH: labserver.uni.example]"), {"require": True, "prefer": "proj"})])

    def test_an_ssh_typed_in_a_vscode_terminal_isnt_remote_ssh(self):
        # VS Code's terminals give their shells TERM_PROGRAM=vscode; Remote-SSH's
        # ssh (the extension host's, with its -D) has VS Code's own environment
        tree = {100: [110, 130], 110: [120], 130: [131]}
        names = {100: "code", 120: "ssh", 131: "ssh"}
        argvs = {100: ["/usr/share/code/code"], 120: ["ssh", "labserver"], 131: ["ssh", "-T", "-D", "1", "gpu"]}
        env = {120: "vscode", 131: None, 100: None}
        with Patch(vscode_main_pids=lambda: [100], proc_env_value=lambda pid, name: env.get(pid),
                   **self.procs(tree, names, argvs)):
            self.assertEqual(jump.vscode_connected_to("labserver"), ([], "[SSH: labserver]"))
            self.assertEqual(jump.vscode_connected_to("gpu"), ([100], "[SSH: gpu]"))
            # Remote-SSH's own, shown in a terminal (its -D says it's the connection)
            env[131] = "vscode"
            self.assertEqual(jump.vscode_connected_to("gpu")[0], [100])
            # a VS Code started from such a terminal: no telling, so it counts
            env[100] = "vscode"
            self.assertEqual(jump.vscode_connected_to("labserver")[0], [100])

    def test_vscode_opened_on_the_host_when_not_connected(self):
        opened = []
        fake = type("S", (), {"Popen": staticmethod(lambda args, **k: opened.append(args)), "DEVNULL": None})
        later = []
        with Patch(vscode_main_pids=lambda: [100], raise_window=lambda *a, **k: self.fail("nothing to raise"),
                   subprocess=fake, shutil=type("W", (), {"which": staticmethod(lambda n: "/usr/bin/" + n)}),
                   scope_prefix=lambda name: ["systemd-run", f"--unit={name}", "--"], later=later.append,
                   **self.procs({100: []}, {100: "code"}, {100: ["code"]})), \
                mock.patch("remote.vscode_allowed", return_value=True):  # (you said yes for it: test_containers)
            ok, msg = jump.jump_remote_vscode("labserver", "abc-123", "/home/me/proj")
        self.assertTrue(ok, msg)
        # VS Code gets a scope of its own: restarting plasmashell mustn't stop it
        self.assertEqual(opened, [["systemd-run", "--unit=code", "--", "/usr/bin/code", "--folder-uri",
                                   "vscode-remote://ssh-remote+labserver/home/me/proj"]])
        self.assertEqual(len(later), 1)  # (the link once that window is connected: open_remote_vscode_chat)

    def test_terminal_tab_with_the_ssh_session(self):
        tabs = {300: [("1", 11, 11, "~ : bash"), ("2", 12, 22, "🏠 ✳ other chat"), ("3", 13, 23, "🏠 ◐ fix parser")]}
        tree = {11: [], 12: [22], 13: [23]}
        names = {22: "ssh", 23: "ssh"}
        argvs = {22: ["ssh", "labserver"], 23: ["ssh", "labserver.uni.example"]}
        shown = []
        with Patch(konsole_pids=lambda: [300], konsole_tabs=lambda k: tabs[k],
                   show_konsole_tab=lambda k, s: shown.append((k, s)) or True, **self.procs(tree, names, argvs)):
            self.assertEqual(jump.jump_remote_terminal("labserver", "fix parser")[0], True)
            self.assertEqual(jump.jump_remote_terminal("labserver", "")[0], True)
            ok, msg = jump.jump_remote_terminal("buildbox", "fix parser")
        self.assertEqual(shown, [(300, "3"), (300, "2")])
        self.assertFalse(ok)
        self.assertIn("no terminal here has an ssh connection to buildbox", msg)


# VS Code's terminal host on an SSH host (`node … --type=ptyHost`), and a
# terminal of it: a shell running a command
PTY_HOST = ("import subprocess; p = subprocess.Popen(['sh', '-c', 'sleep 60; :']); "
            "print(p.pid, flush=True); p.wait()")


class VscodeTerminalTests(unittest.TestCase):
    """A chat in VS Code's terminal: VS Code shows its window, the Claude
    Status extension the terminal (even with the panel closed)."""

    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.home)
        self.raised, self.opened = [], []
        fake = type("S", (), {"Popen": staticmethod(lambda args, **k: self.opened.append(args)), "DEVNULL": None})
        self.desktop = dict(raise_window=lambda *a, **k: self.raised.append((a, k)) or True, subprocess=fake,
                            shutil=type("W", (), {"which": staticmethod(lambda n: "/usr/bin/" + n)}),
                            time=type("T", (), {"sleep": staticmethod(lambda s: None)}))

    def extension(self, version):
        write(self.home / ".vscode/extensions/extensions.json",
              [{"identifier": {"id": "wzaielamri.talpy-den"}, "version": version}])

    def test_the_terminal_a_process_runs_in(self):
        host = subprocess.Popen([sys.executable, "-c", PTY_HOST, "--type=ptyHost"], stdout=subprocess.PIPE,
                                text=True, start_new_session=True)
        self.addCleanup(host.stdout.close)
        self.addCleanup(host.wait)
        self.addCleanup(os.killpg, host.pid, 9)
        shell = int(host.stdout.readline())
        command = None
        for _ in range(100):
            command = Path(f"/proc/{shell}/task/{shell}/children").read_text().split()
            if command:
                break
            time.sleep(0.02)
        (command,) = map(int, command)
        self.assertTrue(cs.is_vscode_terminal_host(host.pid))
        self.assertEqual(cs.vscode_terminal(command), shell)  # the process VS Code started, not the host
        self.assertEqual(cs.vscode_terminal(shell), shell)
        self.assertIsNone(cs.vscode_terminal(1))
        self.assertIsNone(cs.vscode_terminal(None))
        # the rows of an SSH host say so (only chats with a process, not VS Code's Claude tabs)
        rows = [{"key": f"x/{n}", "profileDir": "x", "pid": pid, "entrypoint": entrypoint, "kind": kind}
                for n, (pid, entrypoint, kind) in enumerate([(command, "cli", "interactive"),
                                                             (command, "claude-vscode", "interactive"),
                                                             (None, "cli", "chat")])]
        result = {"groups": [{"chatProfile": None, "sessions": rows, "projects": [], "recent": [], "sharedHere": []}]}
        cs.add_remote_commands(result, self.home, claude="/usr/bin/claude")
        self.assertEqual([s["vscodeTerminal"] for s in rows], [shell, None, None])

    def test_no_terminal_without_vscode(self):
        # (made up: these tests may well run in a VS Code terminal themselves)
        real = cs.parent_pid
        cs.parent_pid = {9000003: 9000002, 9000002: 9000001, 9000001: 1}.get  # past any pid_max
        self.addCleanup(setattr, cs, "parent_pid", real)
        self.assertIsNone(cs.vscode_terminal(9000003))

    def test_a_chat_here_brings_its_terminal_up(self):
        # claude 500 ← sh 400 (the terminal) ← VS Code's terminal host 300 ← VS Code 200
        chain = {500: [500, 400, 300, 200], 700: [700, 650, 300, 200]}
        names = {300: "code", 200: "code"}
        entry = {"pid": 500, "cwd": "/home/me/app"}
        procs = dict(ancestors=lambda pid: chain.get(pid, []), proc_name=lambda pid: names.get(pid, "sh"))
        real = cs.vscode_terminal
        cs.vscode_terminal = lambda pid: {500: 400, 700: 650}.get(pid)
        self.addCleanup(setattr, cs, "vscode_terminal", real)
        self.extension("1.11.0")
        with Patch(**self.desktop, **procs), mock_home(self.home):
            ok, message = jump.jump_terminal(entry)
            self.assertEqual((ok, message), (True, "Switched to the VS Code terminal running this session"))
            # in tmux: the terminal of the client that shows it
            with Patch(tmux_client_pids=lambda pane, socket=None: [700]):
                self.assertTrue(jump.jump_terminal({**entry, "tmux": "s:@1.%3"})[0])
        self.assertEqual(self.raised, [(([500, 400, 300, 200], "app"), {}), (([700, 650, 300, 200], "app"), {})])
        self.assertEqual(self.opened, [["/usr/bin/xdg-open", "vscode://wzaielamri.talpy-den/terminal?pid=400"],
                                       ["/usr/bin/xdg-open", "vscode://wzaielamri.talpy-den/terminal?pid=650"]])
        # an extension too old for the link (it would say it doesn't know it): the window only
        self.raised, self.opened = [], []
        self.extension("1.10.1")
        with Patch(**self.desktop, **procs), mock_home(self.home):
            self.assertEqual(jump.jump_terminal(entry), (True, "Switched to the terminal running this session"))
        self.assertEqual((len(self.raised), self.opened), (1, []))

    def test_a_chat_on_an_ssh_host_in_a_remote_ssh_window(self):
        procs = RemoteShowTests.procs(None, {100: [110], 110: [120]}, {100: "code", 120: "ssh"},
                                      {100: ["/usr/share/code/code"], 120: ["ssh", "-T", "-D", "1", "labserver"]})
        self.extension("1.11.0")
        with Patch(**self.desktop, **procs, vscode_main_pids=lambda: [100],
                   konsole_pids=lambda: self.fail("it's in VS Code, not in a terminal tab")), mock_home(self.home):
            ok, message = jump.jump_remote_terminal("labserver", "fix parser", 4321, "/home/me/proj")
            self.assertEqual((ok, message), (True, "Switched to the VS Code terminal running this chat on labserver"))
            # no window connected to the host
            ok, message = jump.jump_remote_terminal("buildbox", "fix parser", 4321, "/home/me/proj")
            self.assertEqual((ok, message), (False, "This chat runs in a VS Code terminal on buildbox, "
                                                    "and no VS Code window here is connected to it"))
        self.assertEqual(self.raised, [(([100], "[SSH: labserver]"), {"require": True, "prefer": "proj"})])
        self.assertEqual(self.opened, [["/usr/bin/xdg-open",
                                        "vscode://wzaielamri.talpy-den/terminal?pid=4321&host=labserver"]])

    def test_command_line(self):
        calls = []
        with Patch(jump_remote_terminal=lambda *a: calls.append(a) or (True, "ok")), \
                contextlib.redirect_stdout(io.StringIO()):
            jump.main(["--remote-terminal", "lab", "--name", "fix", "--vscode-terminal", "4321", "--cwd", "/p"])
            jump.main(["--remote-terminal", "lab", "--name", "fix"])
            with self.assertRaises(SystemExit):
                jump.main(["abc", "--vscode-terminal", "4321"])
        self.assertEqual(calls, [("lab", "fix", 4321, "/p"), ("lab", "fix", None, "")])


if __name__ == "__main__":
    unittest.main()


class ChangesTests(Fixture):
    """jump.py --changes: what a chat changed, before ↔ now, opened in VS Code."""

    def setUp(self):
        super().setUp()
        self.proj = self.home / "repos/app"
        (self.proj / "src").mkdir(parents=True)
        self.backups = self.home / ".claude-work/file-history/chat1"
        lines = [
            {"type": "user", "cwd": str(self.proj), "sessionId": "chat1", "message": {"content": "go"}},
            {"type": "file-history-snapshot", "messageId": "p1", "isSnapshotUpdate": False,
             "snapshot": {"messageId": "p1", "trackedFileBackups": {}}},
            self.delta("p1", "src/edited.py", "e@v1"),
            self.delta("p1", "src/same.py", "s@v1"),
            self.delta("p1", "src/new.py", None),
            self.delta("p1", "src/gone.py", "g@v1"),
            {"type": "file-history-snapshot", "messageId": "p2", "isSnapshotUpdate": False,
             "snapshot": {"messageId": "p2", "trackedFileBackups": {
                 "src/edited.py": {"backupFileName": "e@v2", "version": 2, "realParentDir": str(self.proj / "src")}}}},
            {"type": "assistant", "sessionId": "chat1", "message": {"content": [
                {"type": "tool_use", "id": "t", "name": "Edit", "input": {"file_path": str(self.proj / "notes.md")}},
                {"type": "tool_use", "id": "u", "name": "Write", "input": {"file_path": str(self.home / ".claude-work/plans/p.md")}}]}},
        ]
        write(self.home / ".claude-work/projects/-app/chat1.jsonl", "".join(json.dumps(l) + "\n" for l in lines))
        for name, data in (("e@v1", "v1\n"), ("e@v2", "v2\n"), ("s@v1", "same\n"), ("g@v1", "old\n")):
            write(self.backups / name, data)
        for rel, data in (("src/edited.py", "v3\n"), ("src/same.py", "same\n"), ("src/new.py", "hi\n"), ("notes.md", "now\n")):
            write(self.proj / rel, data)

    def delta(self, snap, rel, name):
        return {"type": "file-history-delta", "snapshotMessageId": snap, "trackingPath": rel,
                "backup": {"backupFileName": name, "version": 1, "realParentDir": str(self.proj / os.path.dirname(rel))}}

    def compare(self, **kw):
        return jump.chat_comparison(self.home, [], "chat1", ".claude-work", **kw)

    def test_before_the_chat_and_now(self):
        with Patch(git_original=lambda path, missing=b"": b"committed\n" if path.endswith("notes.md") else None):
            ok, message, comparison = self.compare()
        self.assertTrue(ok, message)
        self.assertEqual(message, "4 changed files since it started")
        items = {i["label"]: i for i in comparison["items"]}
        self.assertEqual(sorted(items), ["notes.md", "src/edited.py", "src/gone.py", "src/new.py"])  # same.py unchanged
        self.assertEqual(Path(items["src/edited.py"]["original"]).read_text(), "v1\n")
        self.assertEqual(Path(items["src/edited.py"]["original"]).name, "edited.py")  # named for highlighting
        self.assertEqual((items["src/new.py"]["created"], Path(items["src/new.py"]["original"]).read_text()), (True, ""))
        self.assertTrue(items["src/gone.py"]["deleted"])
        self.assertEqual(Path(items["notes.md"]["original"]).read_text(), "committed\n")  # no backup: git's HEAD
        self.assertEqual(comparison["folder"], str(self.proj))

    def test_last_turn(self):
        ok, message, comparison = self.compare(turn=True)
        self.assertEqual((ok, message), (True, "1 changed file in its last turn"))
        (item,) = comparison["items"]
        self.assertEqual((item["label"], Path(item["original"]).read_text()), ("src/edited.py", "v2\n"))

    def test_without_earlier_versions(self):
        for f in self.backups.iterdir():
            f.unlink()
        with Patch(git_original=lambda path, missing=b"": None):
            ok, message, comparison = self.compare()
        self.assertTrue(ok)
        self.assertEqual([i["label"] for i in comparison["items"]], ["src/new.py"])
        self.assertIn("4 more with no earlier version to compare with", message)  # edited, same, gone, notes

    def test_a_file_without_backups_as_its_calls_gave_it_back(self):
        # as in the pane's review: what the chat's first Edit or Write of it
        # gave back (Claude keeps no backups of a file outside its folder)
        today = self.home / "notes/today.md"
        write(today, "# Today\n")
        with open(self.home / ".claude-work/projects/-app/chat1.jsonl", "a") as f:
            for e in ({"type": "assistant", "sessionId": "chat1", "message": {"content": [
                          {"type": "tool_use", "id": "w", "name": "Write", "input": {"file_path": str(today)}}]}},
                      {"type": "user", "sessionId": "chat1", "toolUseResult": {"type": "create", "filePath": str(today)},
                       "message": {"content": [{"type": "tool_result", "tool_use_id": "w", "content": "ok"}]}},
                      {"type": "user", "sessionId": "chat1",
                       "toolUseResult": {"filePath": str(self.proj / "notes.md"), "originalFile": "before\n"},
                       "message": {"content": [{"type": "tool_result", "tool_use_id": "t", "content": "ok"}]}}):
                f.write(json.dumps(e) + "\n")
        with Patch(git_original=lambda path, missing=b"": None):
            ok, message, comparison = self.compare()
        items = {i["label"]: i for i in comparison["items"]}
        self.assertEqual(Path(items["notes.md"]["original"]).read_text(), "before\n")
        self.assertEqual((items["~/notes/today.md"]["created"], Path(items["~/notes/today.md"]["original"]).read_text()),
                         (True, ""))

    def test_a_pipe_or_a_huge_file_isnt_read(self):
        # (a chat can leave a named pipe where it edited a file: opening it waited for good)
        os.unlink(self.proj / "src/edited.py")
        os.mkfifo(self.proj / "src/edited.py")
        write(self.proj / "notes.md", "x" * ((1 << 20) + 1))
        with Patch(git_original=lambda path, missing=b"": b"committed\n"), mock.patch.object(jump, "CHANGES_FILE_MAX", 1 << 20):
            ok, message, comparison = self.compare()
        self.assertEqual([i["label"] for i in comparison["items"]], ["src/gone.py", "src/new.py"])
        self.assertEqual(message, "2 changed files since it started; 2 more not compared here: over 1 MB, or not a plain file")

    def test_a_removed_backup_of_a_file_git_doesnt_have(self):
        # it was there before the chat (Claude backed it up): not empty then;
        # nor was notes.md (no backup, edited: it was there) new
        (self.backups / "e@v1").unlink()
        with Patch(git_original=lambda path, missing=b"": missing):
            ok, message, comparison = self.compare()
        self.assertEqual([i["label"] for i in comparison["items"]], ["src/gone.py", "src/new.py"])
        self.assertEqual(message, "2 changed files since it started; 2 more with no earlier version to compare with")

    def test_a_file_git_has_empty_was_there(self):
        # notes.md (no backup) is empty in git's last commit: there, empty, not new
        with Patch(git_original=lambda path, missing=b"": b"" if path.endswith("notes.md") else missing):
            ok, message, comparison = self.compare()
        items = {i["label"]: i for i in comparison["items"]}
        self.assertEqual((items["notes.md"]["created"], items["src/new.py"]["created"]), (False, True))

    def test_real_git_fallback(self):
        if not shutil.which("git"):
            self.skipTest("no git")
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
                   GIT_COMMITTER_EMAIL="t@t", GIT_CONFIG_GLOBAL=os.devnull)
        git = lambda *a: subprocess.run(["git", "-C", str(self.proj), *a], env=env, capture_output=True, check=True)
        git("init", "-q")
        (self.proj / "notes.md").write_text("committed\n")
        git("add", "notes.md")
        git("commit", "-qm", "x")
        (self.proj / "notes.md").write_text("now\n")
        self.assertEqual(jump.git_original(str(self.proj / "notes.md")), b"committed\n")
        self.assertEqual(jump.git_original(str(self.proj / "src/new.py")), b"")  # not committed: new
        self.assertIsNone(jump.git_original(str(self.home / "x.txt")))  # no repository

    def test_opens_one_view_through_the_extension(self):
        write(self.home / ".vscode/extensions/extensions.json",
              [{"identifier": {"id": "wzaielamri.talpy-den"}, "version": "1.8.0"}])
        started, diffs = [], []
        with Patch(start_vscode_chat=lambda code, folder, link: started.append((folder, link)),
                   later=lambda task: diffs.append(task)), \
                mock_home(self.home), mock_vscode():
            ok, message = jump.show_changes(self.home, [], "chat1", ".claude-work", turn=True)
        self.assertEqual((ok, message), (True, "Comparing 1 changed file in its last turn in VS Code"))
        ((folder, link),) = started
        self.assertEqual(folder, str(self.proj))
        self.assertTrue(link.startswith("vscode://wzaielamri.talpy-den/changes?file="), link)
        manifest = json.loads(Path(vscode_link_params(link)["file"]).read_text())
        self.assertEqual([i["label"] for i in manifest["items"]], ["src/edited.py"])
        self.assertEqual(diffs, [])

    def test_one_by_one_without_the_extension(self):
        write(self.home / ".vscode/extensions/extensions.json",
              [{"identifier": {"id": "wzaielamri.talpy-den"}, "version": "1.7.0"}])  # too old
        tasks, runs = [], []
        with Patch(later=lambda task: tasks.append(task)), mock_home(self.home), mock_vscode(), \
                Patch(subprocess=FakeRun(runs)):
            ok, message = jump.show_changes(self.home, [], "chat1", ".claude-work", turn=True)
            self.assertTrue(ok, message)
            (task,) = tasks
            task()
        ((cmd, *_),) = runs
        self.assertEqual(cmd[:3], ["/usr/bin/code", "--reuse-window", "--diff"])
        self.assertEqual(cmd[4], str(self.proj / "src/edited.py"))


class FakeRun:
    """Stands in for the subprocess module: records run() calls."""

    def __init__(self, runs):
        self.runs, self.DEVNULL, self.PIPE = runs, subprocess.DEVNULL, subprocess.PIPE

    def run(self, cmd, **kw):
        self.runs.append((cmd, kw))
        return subprocess.CompletedProcess(cmd, 0, b"", b"")


@contextlib.contextmanager
def mock_home(home):
    saved = os.environ.get("HOME")
    os.environ["HOME"] = str(home)
    try:
        yield
    finally:
        os.environ["HOME"] = saved


@contextlib.contextmanager
def mock_vscode():
    real = cs.vscode_app
    cs.vscode_app = lambda: ("/usr/bin/code", "Code")
    try:
        with Patch(shutil=type("W", (), {"which": staticmethod(lambda n: "/usr/bin/" + n),
                                         "rmtree": staticmethod(shutil.rmtree)})):
            yield
    finally:
        cs.vscode_app = real


class PhoneTests(unittest.TestCase):
    """jump.py --phone: a message to your phone through KDE Connect (a stand-in kdeconnect-cli)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bin = Path(self.tmp.name)
        self.log = self.bin / "pings"
        cli = self.bin / "kdeconnect-cli"
        cli.write_text(f"""#!/bin/sh
case "$*" in
  "-l --id-name-only") printf 'aaa Pixel 9\\nbbb Old tablet\\n' ;;
  "-a --id-only") cat "{self.bin}/reachable" 2>/dev/null; echo "$(cat "{self.bin}/reachable" 2>/dev/null | wc -l) devices found" >&2 ;;
  -d*) echo "$2|$4" >> "{self.log}" ;;
esac
""")
        cli.chmod(0o755)
        self.which = staticmethod(lambda name: str(cli) if name == "kdeconnect-cli" else None)

    def tearDown(self):
        self.tmp.cleanup()

    def reachable(self, *ids):
        (self.bin / "reachable").write_text("".join(i + "\n" for i in ids))

    def pings(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def call(self, fn, *args):
        with Patch(shutil=type("W", (), {"which": self.which})):
            return fn(*args)

    def test_lists_paired_phones(self):
        self.reachable("aaa")
        ok, _, devices = self.call(jump.phone_devices)
        self.assertTrue(ok)
        self.assertEqual(devices, [{"id": "aaa", "name": "Pixel 9", "reachable": True},
                                   {"id": "bbb", "name": "Old tablet", "reachable": False}])

    def test_every_reachable_phone_or_the_one_picked(self):
        self.reachable("aaa")
        self.assertEqual(self.call(jump.send_to_phone, "fix-parser needs you"), (True, "Sent to Pixel 9"))
        self.assertEqual(self.pings(), ["aaa|fix-parser needs you"])
        ok, msg = self.call(jump.send_to_phone, "hi", "bbb")
        self.assertEqual((ok, msg), (False, "Old tablet isn't reachable (is it on the same network?)"))
        self.assertEqual(len(self.pings()), 1)

    def test_nothing_reachable_or_no_kde_connect(self):
        self.reachable()
        self.assertEqual(self.call(jump.send_to_phone, "hi"), (False, "No paired phone is reachable through KDE Connect right now"))
        with Patch(shutil=type("W", (), {"which": staticmethod(lambda name: None)})):
            self.assertFalse(jump.send_to_phone("hi")[0])
            self.assertEqual(jump.phone_devices()[1], "KDE Connect isn't installed (kdeconnect-cli)")


class AgentRunFileTests(Fixture):
    """jump.py --agent-run: a subagent's run saved as Markdown and opened."""

    def setUp(self):
        super().setUp()
        d = self.home / ".claude-work/projects/-w-proj/chat1/subagents"
        write(d / "agent-ab12cd34ef.meta.json", {"agentType": "Explore", "description": "Find / the parser: now!"})
        write(d / "agent-ab12cd34ef.jsonl", json.dumps({"type": "user", "isSidechain": True, "message": {"content": "Find it"}}) + "\n")
        self.saved = os.environ.get("XDG_CACHE_HOME")
        os.environ["XDG_CACHE_HOME"] = str(self.cache)

    def tearDown(self):
        if self.saved is None:
            os.environ.pop("XDG_CACHE_HOME", None)
        else:
            os.environ["XDG_CACHE_HOME"] = self.saved
        super().tearDown()

    def test_saved_and_opened(self):
        opened = []
        with Patch(open_markdown=lambda path, home=None: opened.append(path) or (True, "")):
            ok, message, path = jump.show_agent_run(self.home, [], "chat1", "ab12cd34ef", ".claude-work")
        self.assertEqual((ok, message), (True, "The run of “Find / the parser: now!”"))
        self.assertEqual(Path(path), self.cache / "talpy-den/agent-runs/Find the parser now! (ab12cd34).md")
        self.assertTrue(Path(path).read_text().startswith("# Find / the parser: now!\n"))
        self.assertEqual(opened, [Path(path)])

    def test_old_runs_are_removed(self):
        old = self.cache / "talpy-den/agent-runs/old (x).md"
        write(old, "x")
        os.utime(old, (time.time() - 2 * 86400,) * 2)
        with Patch(open_markdown=lambda path, home=None: (True, "")):
            jump.show_agent_run(self.home, [], "chat1", "ab12cd34ef")
        self.assertFalse(old.exists())

    def test_not_found(self):
        self.assertEqual(jump.show_agent_run(self.home, [], "chat1", "nope"),
                         (False, "Can't find that subagent's transcript", None))

    def test_opened_with_xdg_open(self):
        started = []
        with Patch(start_app=lambda args: started.append(args)):
            opened = jump.open_file(Path("/x/run.md"))
        if shutil.which("xdg-open"):
            self.assertEqual((opened, started), (True, [[shutil.which("xdg-open"), "/x/run.md"]]))
        else:
            self.assertEqual((opened, started), (False, []))

    def test_command_line(self):
        out = io.StringIO()
        with mock.patch.object(jump.Path, "home", return_value=self.home), contextlib.redirect_stdout(out):
            jump.main(["--agent-run", "ab12cd34ef", "--chat", "chat1", "--profile", ".claude-work", "--no-open"])
        answer = json.loads(out.getvalue())
        self.assertTrue(answer["ok"], answer)
        self.assertTrue(answer["file"].endswith("agent-runs/Find the parser now! (ab12cd34).md"))
        for bad in (["--agent-run", "ab12cd34ef"], ["--no-open", "chat1"]):
            with self.assertRaises(SystemExit):
                jump.main(bad)
