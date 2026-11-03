"""New chats in VS Code: which account VS Code's Claude extension runs on
(its environmentVariables setting, VS Code's environment, else ~/.claude),
and jump.py opening the folder there and asking the extension for a chat."""
import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
CODE = Path(__file__).resolve().parent.parent / "package/contents/code"
sys.path.insert(0, str(CODE))
spec = importlib.util.spec_from_file_location("jump_vscode", CODE / "jump.py")
jump = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jump)
cs = jump.cs


class Patch:
    """Temporarily replace attributes of modules: Patch((module, name, value), ...)."""

    def __init__(self, *changes):
        self.changes, self.saved = changes, []

    def __enter__(self):
        try:
            for module, name, value in self.changes:
                self.saved.append((module, name, getattr(module, name)))
                setattr(module, name, value)
        except Exception:
            self.__exit__()   # put back what was changed so far
            raise

    def __exit__(self, *exc):
        for module, name, value in reversed(self.saved):
            setattr(module, name, value)


class Home(unittest.TestCase):
    """A home with the work and personal profiles; ~/.claude links to work."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        for name in ("work", "personal"):
            d = self.home / f".claude-{name}"
            (d / "sessions").mkdir(parents=True)
            (d / ".profile-name").write_text(name)
        (self.home / ".claude").symlink_to(self.home / ".claude-work")
        self.config = Path(self.tmp.name) / "config"
        self.env = {k: os.environ.get(k) for k in ("XDG_CONFIG_HOME", "CLAUDE_CONFIG_DIR")}
        os.environ["XDG_CONFIG_HOME"] = str(self.config)
        os.environ.pop("CLAUDE_CONFIG_DIR", None)

    def tearDown(self):
        for k, v in self.env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()

    def settings(self, text):
        path = self.config / "Code/User/settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def profiles(self):
        return cs.discover_profiles(self.home)

    def label(self, running=(False, None), installed=True):
        app = ("/usr/bin/code", "Code") if installed else (None, None)
        with Patch((cs, "vscode_app", lambda: app), (cs, "vscode_running_config_dir", lambda: running)):
            found, profile = cs.vscode_profile(self.home, self.profiles())
        return found, profile.label if profile else None


class SettingsTests(Home):
    def test_settings_with_comments_and_trailing_commas(self):
        self.assertEqual(cs.jsonc('{\n // a "comment"\n "a": "http://x/*y*/", /* more */ "b": [1, 2,],\n}'),
                         {"a": "http://x/*y*/", "b": [1, 2]})
        self.assertEqual(cs.jsonc('{"q": "say \\"hi\\" // no comment"}'), {"q": 'say "hi" // no comment'})

    def test_config_dir_from_the_extension_setting(self):
        self.assertIsNone(cs.vscode_setting_config_dir(self.home, "Code"))   # no settings file
        self.settings('{"claudeCode.environmentVariables": [{"name": "FOO", "value": "1"},'
                      ' {"name": "CLAUDE_CONFIG_DIR", "value": "/x/.claude-y"},], // mine\n}')
        self.assertEqual(cs.vscode_setting_config_dir(self.home, "Code"), "/x/.claude-y")
        self.settings('{"claudeCode.environmentVariables": [{"name": "FOO", "value": "1"}]}')
        self.assertIsNone(cs.vscode_setting_config_dir(self.home, "Code"))
        self.settings('{"broken": ')
        self.assertIsNone(cs.vscode_setting_config_dir(self.home, "Code"))

    def test_a_comma_in_a_string_is_no_trailing_comma(self):
        self.assertEqual(cs.jsonc('{"a": "x, }", "b": ["1, ]", /* c */ ], // d\n}'), {"a": "x, }", "b": ["1, ]"]})
        # nor does the switch change another variable that has one
        path = self.config / "Code/User/settings.json"
        self.settings('{"claudeCode.environmentVariables": [{"name": "OPTS", "value": "{\\"a\\": [1, ]}"}]}')
        self.assertTrue(cs.set_config_dir_setting(path, "/h/.claude-y", self.home)[0])
        self.assertEqual(json.loads(path.read_text())["claudeCode.environmentVariables"], [
            {"name": "OPTS", "value": '{"a": [1, ]}'}, {"name": "CLAUDE_CONFIG_DIR", "value": "/h/.claude-y"}])

    def test_a_byte_order_mark(self):
        # (VS Code reads a settings file that starts with one; it stays)
        path = self.config / "Code/User/settings.json"
        self.settings('\ufeff{"claudeCode.environmentVariables": [{"name": "CLAUDE_CONFIG_DIR", "value": "/x/.claude-y"}]}')
        self.assertEqual(cs.vscode_setting_config_dir(self.home, "Code"), "/x/.claude-y")
        self.assertTrue(cs.set_config_dir_setting(path, "/h/.claude-z", self.home)[0])
        self.assertTrue(path.read_text(encoding="utf-8").startswith("\ufeff{"))
        self.assertEqual(cs.vscode_setting_config_dir(self.home, "Code"), "/h/.claude-z")

    def test_windows_line_ends_stay(self):
        path = self.config / "Code/User/settings.json"
        for text in ('{\r\n    "a": 1\r\n}\r\n', '{\r\n    "claudeCode.environmentVariables": [\r\n    ],\r\n}\r\n'):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode())
            self.assertTrue(cs.set_config_dir_setting(path, "/h/.claude-y", self.home)[0])
            raw = path.read_bytes()
            self.assertNotIn(b"\n", raw.replace(b"\r\n", b""), raw)
            self.assertEqual(cs.config_dir_in_settings(path), "/h/.claude-y")

    def test_a_linked_settings_file_stays_a_link(self):
        # (your dotfiles: the switch changes the file the link points to)
        path = self.config / "Code/User/settings.json"
        dotfile = Path(self.tmp.name) / "dotfiles/settings.json"
        dotfile.parent.mkdir(parents=True)
        dotfile.write_text('{\n    "a": 1\n}\n')
        path.parent.mkdir(parents=True)
        path.symlink_to(dotfile)
        self.assertTrue(cs.set_config_dir_setting(path, "/h/.claude-y", self.home)[0])
        self.assertTrue(path.is_symlink())
        self.assertEqual(cs.config_dir_in_settings(dotfile), "/h/.claude-y")
        self.assertEqual(sorted(p.name for p in dotfile.parent.iterdir()), ["settings.json"])


class SettingsEditTests(unittest.TestCase):
    """One setting changed in a file you edit by hand: the rest stays as it is."""

    KEY = "claudeCode.environmentVariables"

    def check(self, text, value=None):
        value = value if value is not None else [{"name": "CLAUDE_CONFIG_DIR", "value": "/h/.claude"}]
        new = cs.jsonc_set(text, self.KEY, value)
        before = cs.jsonc(text) if text.strip() else {}
        self.assertEqual(cs.jsonc(new), {**before, self.KEY: value})
        return new

    def test_replaces_only_that_value(self):
        text = ('{\n    // my font\n    "editor.fontSize": 14, /* big */\n    "claudeCode.environmentVariables": [\n'
                '        {"name": "FOO", "value": "}"} // a brace in a string\n    ],\n    "x": {"y": [1, 2,]},\n}\n')
        new = self.check(text)
        self.assertIn("// my font", new)
        self.assertIn('"editor.fontSize": 14, /* big */', new)
        self.assertIn('    "x": {"y": [1, 2,]},\n}\n', new)
        self.assertNotIn("FOO", new)

    def test_adds_it_after_the_last_setting(self):
        self.assertTrue(self.check('{\n  "a": 1\n}\n').startswith('{\n  "a": 1,\n  "claudeCode'))
        self.assertTrue(self.check('{\n    "a": 1, // trailing comma\n}').startswith('{\n    "a": 1,\n    "claudeCode'))
        self.check("{}")
        self.check('{\n    // only a comment\n}')

    def test_a_key_in_a_comment_is_no_key(self):
        new = self.check('{\n    // "claudeCode.environmentVariables": [],\n    "a": true\n}')
        self.assertIn('// "claudeCode.environmentVariables": [],', new)

    def test_refuses_what_isnt_an_object(self):
        for text in ("[1]", '{"a": 1', '{"a" 1}', "{1: 2}"):
            with self.assertRaises(ValueError, msg=text):
                cs.jsonc_set(text, self.KEY, [])


class ProfileTests(Home):
    def test_the_setting_decides_and_links_are_followed(self):
        self.settings(json.dumps({"claudeCode.environmentVariables": [
            {"name": "CLAUDE_CONFIG_DIR", "value": str(self.home / ".claude")}]}))
        self.assertEqual(self.label(running=(True, str(self.home / ".claude-personal"))), (True, "work"))
        (self.home / ".claude").unlink()   # switched to the other profile
        (self.home / ".claude").symlink_to(self.home / ".claude-personal")
        self.assertEqual(self.label(), (True, "personal"))

    def test_else_the_running_vscode_else_what_the_widget_would_start_it_with(self):
        self.assertEqual(self.label(running=(True, str(self.home / ".claude-personal"))), (True, "personal"))
        self.assertEqual(self.label(running=(True, None)), (True, "work"))       # ~/.claude
        self.assertEqual(self.label(), (True, "work"))
        os.environ["CLAUDE_CONFIG_DIR"] = str(self.home / ".claude-personal")
        self.assertEqual(self.label(), (True, "personal"))

    def test_not_installed_or_no_such_profile(self):
        self.assertEqual(self.label(installed=False), (False, None))
        self.assertEqual(self.label(running=(True, "/nowhere/.claude")), (True, None))

    def test_ssh_host_uses_its_own_claude_folder(self):
        with Patch((cs, "vscode_app", lambda: (None, None))):
            installed, profile = cs.vscode_profile(self.home, self.profiles(), remote=True)
        self.assertEqual((installed, profile.label), (None, "work"))

    def test_groups_say_where_a_vscode_chat_goes(self):
        result = {"groups": [{"profileKeys": [p.key]} for p in self.profiles()]}
        with Patch((cs, "vscode_app", lambda: ("/usr/bin/code", "Code")),
                   (cs, "vscode_running_config_dir", lambda: (False, None))):
            cs.add_vscode(result, self.home)
        self.assertEqual(result["vscode"], {"installed": True, "on": "work"})
        here = {p.label: g["vscodeHere"] for p, g in zip(self.profiles(), result["groups"])}
        self.assertEqual(here, {"work": True, "personal": False})

    def test_an_ssh_hosts_vscode_runs_on_what_its_server_settings_say(self):
        # Windows connected to a host read the Claude extension's
        # environmentVariables (a machine setting) from the host's VS Code
        # server, never from the settings on your computer
        settings = self.home / ".vscode-server/data/Machine/settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text(json.dumps({"claudeCode.environmentVariables": [
            {"name": "CLAUDE_CONFIG_DIR", "value": str(self.home / ".claude-personal")}]}))
        with Patch((cs, "vscode_app", lambda: (None, None))):
            installed, profile = cs.vscode_profile(self.home, self.profiles(), remote=True)
        self.assertEqual((installed, profile.label), (None, "personal"))

    def test_switching_an_ssh_hosts_vscode_to_another_account(self):
        settings = self.home / ".vscode-server/data/Machine/settings.json"
        personal = str(self.home / ".claude-personal")
        self.assertEqual(cs.set_vscode_server_config_dir(self.home, personal),
                         (True, "VS Code's Claude runs on personal here now"))
        self.assertEqual(json.loads(settings.read_text()),
                         {"claudeCode.environmentVariables": [{"name": "CLAUDE_CONFIG_DIR", "value": personal}]})
        # other settings and variables stay; back on ~/.claude (a link here) by its name
        settings.write_text(json.dumps({"editor.fontSize": 13, "claudeCode.environmentVariables": [
            {"name": "FOO", "value": "1"}, {"name": "CLAUDE_CONFIG_DIR", "value": personal}]}))
        self.assertTrue(cs.set_vscode_server_config_dir(self.home, str(self.home / ".claude"))[0])
        self.assertEqual(json.loads(settings.read_text()), {"editor.fontSize": 13, "claudeCode.environmentVariables": [
            {"name": "FOO", "value": "1"}, {"name": "CLAUDE_CONFIG_DIR", "value": str(self.home / ".claude")}]})
        # only this host's Claude folders; a file edited by hand keeps its comments
        ok, message = cs.set_vscode_server_config_dir(self.home, "/etc")
        self.assertFalse(ok)
        self.assertIn("isn't a Claude folder", message)
        settings.write_text('{\n  // mine\n  "editor.fontSize": 14,\n}\n')
        self.assertTrue(cs.set_vscode_server_config_dir(self.home, personal)[0])
        text = settings.read_text()
        self.assertIn("// mine", text)
        self.assertEqual(cs.jsonc(text), {"editor.fontSize": 14, "claudeCode.environmentVariables": [
            {"name": "CLAUDE_CONFIG_DIR", "value": personal}]})
        settings.write_text("{broken")
        ok, message = cs.set_vscode_server_config_dir(self.home, personal)
        self.assertFalse(ok)
        self.assertIn("couldn't be changed", message)
        self.assertEqual(settings.read_text(), "{broken")
        self.assertFalse(cs.set_vscode_server_config_dir(self.home, personal, server="../../etc")[0])

    def test_each_hosts_account_says_what_vscodes_claude_needs_for_it(self):
        # (~/.claude links to work here: named by the link, as terminals name it)
        result = {"groups": [{"chatProfile": p.key, "sessions": [], "projects": [], "recent": [], "sharedHere": []}
                             for p in self.profiles()]}
        cs.add_remote_commands(result, self.home, claude="/usr/bin/claude")
        self.assertEqual({g["chatProfile"]: g["configDir"] for g in result["groups"]},
                         {".claude-work": str(self.home / ".claude"), ".claude-personal": str(self.home / ".claude-personal")})
        # a starred chat (and a starred plan's chat) opens like a recent one: its ★ Starred entry is a copy
        chat = {"profileDir": ".claude-personal", "sessionId": "0a1b2c3d", "cwd": "/srv/app"}
        plan = {"chatProfileDir": ".claude-personal", "chatId": "0a1b2c3d", "cwd": "/srv/app"}
        result = {"groups": [{"chatProfile": None, "sessions": [], "recent": [], "starred": [chat],
                              "plans": [], "starredPlans": [plan]}]}
        cs.add_remote_commands(result, self.home, claude="/usr/bin/claude")
        self.assertIn("--resume 0a1b2c3d", chat["openCommand"])
        self.assertEqual(plan["openCommand"], chat["openCommand"])

    def test_the_account_vscode_is_on_comes_first(self):
        # You switch VS Code's account in its settings; ~/.claude (listed
        # first otherwise) may still point to the other one
        self.settings(json.dumps({"claudeCode.environmentVariables": [
            {"name": "CLAUDE_CONFIG_DIR", "value": str(self.home / ".claude-personal")}]}))
        result = {"groups": [{"name": p.label, "profileKeys": [p.key]} for p in self.profiles()]}
        self.assertEqual([g["name"] for g in result["groups"]], ["work", "personal"])
        with Patch((cs, "vscode_app", lambda: ("/usr/bin/code", "Code")),
                   (cs, "vscode_running_config_dir", lambda: (False, None))):
            cs.add_vscode(result, self.home)
        self.assertEqual([(g["name"], g["vscodeHere"]) for g in result["groups"]], [("personal", True), ("work", False)])


class VscodeHome(Home):
    """Stand-ins for VS Code, xdg-open and KWin, recording what they're asked."""

    def setUp(self):
        super().setUp()
        self.started, self.raised, self.opened = [], [], []
        self.folder = self.home / "repos/app"
        self.folder.mkdir(parents=True)

    def fakes(self, running=False):
        fake_popen = type("P", (), {"Popen": staticmethod(lambda args, **k: self.opened.append(args)),
                                    "DEVNULL": None, "PIPE": None})
        self.waits = []
        return [
            (cs, "vscode_app", lambda: ("/usr/bin/code", "Code")),
            (cs, "vscode_running_config_dir", lambda: (running, None)),
            (jump, "vscode_main_pids", lambda: [100] if running else []),
            (jump, "start_app", lambda args, cwd=None: self.started.append(args)),
            (jump, "later", lambda task: task()),
            (jump, "raise_window", lambda pids, caption="", require=False, prefer="": self.raised.append((caption, require))),
            (jump, "time", type("T", (), {"sleep": staticmethod(lambda s: self.waits.append(s)),
                                          "monotonic": staticmethod(lambda: sum(self.waits))})),
            (jump, "vscode_connected_to", lambda host: ([100], f"[SSH: {host}]")),
            (jump, "subprocess", fake_popen),
            (jump, "shutil", type("W", (), {"which": staticmethod(lambda n: f"/usr/bin/{n}")})),
        ]


class NewChatTests(VscodeHome):
    def new(self, profile, folder=None, running=False, choose=None):
        changes = self.fakes(running)
        if choose is not None:
            changes.append((jump, "choose_folder", lambda title, start: (choose, "")))
        with Patch(*changes):
            if choose is not None:
                return jump.new_chat_choosing_folder(self.home, [], profile, jump.new_chat_vscode)
            return jump.new_chat_vscode(self.home, [], profile, folder)

    def test_opens_the_folder_then_asks_for_a_new_chat(self):
        ok, message = self.new(".claude-work", str(self.folder))
        self.assertTrue(ok, message)
        self.assertEqual(self.started, [["/usr/bin/code", str(self.folder)]])
        self.assertEqual(self.raised, [("app", True)])   # the folder's window first...
        self.assertEqual(self.opened, [["/usr/bin/xdg-open", "vscode://anthropic.claude-code/open"]])   # ...then the link
        self.assertEqual(self.waits[0], 8)   # VS Code wasn't running: give it time to start

    def test_a_running_vscode_is_quicker(self):
        self.new(".claude-work", str(self.folder), running=True)
        self.assertEqual(self.waits[0], 2.5)

    def test_refuses_an_account_vscode_isnt_on(self):
        ok, message = self.new(".claude-personal", str(self.folder))
        self.assertFalse(ok)
        self.assertIn("runs on work, not personal", message)
        self.assertEqual((self.started, self.opened), ([], []))

    def test_chosen_folder(self):
        ok, _ = self.new(".claude-work", choose=str(self.folder))
        self.assertTrue(ok)
        self.assertEqual(self.started, [["/usr/bin/code", str(self.folder)]])

    def test_ssh_host(self):
        changes = [(cs, "vscode_app", lambda: ("/usr/bin/code", "Code")),
                   (jump, "start_app", lambda args, cwd=None: self.started.append(args)),
                   (jump, "later", lambda task: task()),
                   (jump, "raise_window", lambda pids, caption="", require=False, prefer="":
                    self.raised.append((caption, prefer))),
                   (jump, "vscode_main_pids", lambda: []),
                   (jump, "vscode_connected_to", lambda host: ([100], f"[SSH: {host}]")),
                   (jump, "time", type("T", (), {"sleep": staticmethod(lambda s: None), "monotonic": staticmethod(lambda: 0)})),
                   (jump, "subprocess", type("P", (), {"Popen": staticmethod(lambda args, **k: self.opened.append(args)),
                                                       "DEVNULL": None})),
                   (jump, "shutil", type("W", (), {"which": staticmethod(lambda n: f"/usr/bin/{n}")}))]
        with Patch(*changes):
            self.assertTrue(jump.new_chat_remote_vscode("lab", "/srv/proj")[0])
            self.assertTrue(jump.new_chat_remote_vscode("lab")[0])
        self.assertEqual(self.started, [["/usr/bin/code", "--folder-uri", "vscode-remote://ssh-remote+lab/srv/proj"],
                                        ["/usr/bin/code", "--remote", "ssh-remote+lab"]])
        self.assertEqual(self.raised, [("[SSH: lab]", "proj"), ("[SSH: lab]", "")])

    def test_command_line(self):
        calls = []
        with Patch((jump, "new_chat_vscode", lambda home, extra, name, folder, task: calls.append(("vscode", name, folder)) or (True, "")),
                   (jump, "new_chat", lambda home, extra, name, folder, task: calls.append(("terminal", name, folder)) or (True, "")),
                   (jump, "new_chat_remote_vscode", lambda host, folder, account=None, task=None:
                    calls.append(("ssh", host, folder, account)) or (True, "")),
                   (jump, "new_chat_choosing_folder", lambda home, extra, name, start=None, task=None:
                    calls.append(("choose", name, start is jump.new_chat_vscode)) or (True, ""))), \
                contextlib.redirect_stdout(io.StringIO()):
            jump.main(["--new-chat", ".claude-work", "--cwd", "/p", "--vscode"])
            jump.main(["--new-chat", ".claude-work", "--cwd", "/p"])
            jump.main(["--remote-new-vscode", "lab", "--cwd", "/srv"])
            jump.main(["--remote-new-vscode", "lab", "--cwd", "/srv", "--account", "/home/me/.claude-personal"])
            jump.main(["--new-chat", ".claude-work", "--choose-folder", "--vscode"])
        self.assertEqual(calls, [("vscode", ".claude-work", "/p"), ("terminal", ".claude-work", "/p"),
                                 ("ssh", "lab", "/srv", None), ("ssh", "lab", "/srv", "/home/me/.claude-personal"),
                                 ("choose", ".claude-work", True)])

    def test_a_host_chat_on_another_account_switches_vscode_there_first(self):
        import remote
        opened, switched = [], []
        with Patch((jump, "remote_vscode", lambda host, folder, link, what: opened.append((host, folder)) or (True, "ok"))):
            with Patch((remote, "vscode_account", lambda host, value: switched.append((host, value)) or (False, "it has comments"))):
                ok, message = jump.new_chat_remote_vscode("lab", "/srv", "/home/me/.claude-personal")
            self.assertFalse(ok)
            self.assertIn("it has comments", message)
            self.assertEqual(opened, [])  # the chat would have started on the other account
            with Patch((remote, "vscode_account", lambda host, value: switched.append((host, value)) or (True, "now personal"))):
                self.assertTrue(jump.new_chat_remote_vscode("lab", "/srv", "-")[0])
        self.assertEqual(switched, [("lab", "/home/me/.claude-personal"), ("lab", None)])
        self.assertEqual(opened, [("lab", "/srv")])

    def test_the_switch_goes_to_the_server_of_your_vscode(self):
        import remote
        runs = []
        with Patch((remote, "run_status_script", lambda host, args: runs.append((host, args)) or (True, "")),
                   (cs, "vscode_app", lambda: ("/usr/bin/code-insiders", "Code - Insiders"))):
            remote.vscode_account("lab", "/home/me/.claude-personal")
            remote.vscode_account("lab", None)
        self.assertEqual(runs, [("lab", ["--vscode-account", "/home/me/.claude-personal", "--vscode-server", ".vscode-server-insiders"]),
                                ("lab", ["--vscode-account", "-", "--vscode-server", ".vscode-server-insiders"])])


class ResumeTests(VscodeHome):
    """A recent chat reopened in VS Code: its folder, then the extension's
    link with the chat's id (it resumes the chat in a new tab)."""

    CHAT = "5e550000-0000-4000-8000-000000000001"

    def setUp(self):
        super().setUp()
        transcript = self.home / ".claude-work/projects/-repos-app" / f"{self.CHAT}.jsonl"
        transcript.parent.mkdir(parents=True)
        transcript.write_text(json.dumps({"type": "user", "cwd": str(self.folder), "sessionId": self.CHAT}) + "\n")

    def resume(self, profile, chat=None):
        with Patch(*self.fakes()):
            return jump.resume_vscode(self.home, [], chat or self.CHAT, profile)

    def test_opens_the_chats_folder_then_the_chat(self):
        ok, message = self.resume(".claude-work")
        self.assertEqual((ok, message), (True, "Reopening the chat in VS Code (~/repos/app)"))
        self.assertEqual(self.started, [["/usr/bin/code", str(self.folder)]])
        self.assertEqual(self.raised, [("app", True)])
        self.assertEqual(self.opened, [["/usr/bin/xdg-open", f"vscode://anthropic.claude-code/open?session={self.CHAT}"]])

    def moved(self, started, last):
        """A chat Claude Code filed under the folder it started in, whose
        last turns ran in another one (Claude's `cd`s)."""
        sid = "5e550000-0000-4000-8000-000000000002"
        transcript = self.home / ".claude-work/projects" / cs.mangle(str(started)) / f"{sid}.jsonl"
        transcript.parent.mkdir(parents=True)
        transcript.write_text("".join(json.dumps({"type": "user", "cwd": str(c), "sessionId": sid}) + "\n" for c in (started, last)))
        return sid

    def test_a_chat_that_went_into_a_subfolder_opens_its_project(self):
        # (VS Code brings up the window that has the project open, instead of a new one for the subfolder)
        sub = self.folder / "source"
        sub.mkdir()
        ok, message = self.resume(".claude-work", self.moved(self.folder, sub))
        self.assertEqual((ok, message), (True, "Reopening the chat in VS Code (~/repos/app)"))
        self.assertEqual(self.started, [["/usr/bin/code", str(self.folder)]])

    def test_a_chat_started_in_the_home_folder_opens_where_it_went(self):
        # (not all of your home folder in a VS Code window)
        self.resume(".claude-work", self.moved(self.home, self.folder))
        self.assertEqual(self.started, [["/usr/bin/code", str(self.folder)]])

    def test_refused_where_it_cant_open(self):
        self.assertIn("runs on work, not personal", self.resume(".claude-personal")[1])
        self.assertEqual(self.resume(".claude-work", "0ther000-0000-4000-8000-000000000001"),
                         (False, "That chat isn't on work"))
        self.folder.rmdir()
        self.assertIn("isn't there any more", self.resume(".claude-work")[1])
        self.assertEqual((self.started, self.opened), ([], []))

    def test_ssh_host(self):
        with Patch(*self.fakes()):
            self.assertTrue(jump.resume_remote_vscode("lab", self.CHAT, "/srv/proj")[0])
        self.assertEqual(self.started, [["/usr/bin/code", "--folder-uri", "vscode-remote://ssh-remote+lab/srv/proj"]])
        self.assertEqual(self.raised, [("[SSH: lab]", True)])
        self.assertEqual(self.opened, [["/usr/bin/xdg-open", f"vscode://anthropic.claude-code/open?session={self.CHAT}"]])
        # (a window that doesn't connect: the link would go to the VS Code window used last, one of this computer)
        self.opened.clear()
        with Patch(*self.fakes(), (jump, "vscode_connected_to", lambda host: ([], f"[SSH: {host}]"))), \
                mock.patch("pane.show_note") as note:
            self.assertTrue(jump.resume_remote_vscode("lab", self.CHAT, "/srv/proj")[0])
        self.assertEqual(self.opened, [])
        note.assert_called_once_with("VS Code didn't connect to lab yet: the chat wasn't opened", False)

    def test_resume_command_line(self):
        calls = []
        with Patch((jump, "resume_vscode", lambda home, extra, sid, prof: calls.append(("vscode", sid, prof)) or (True, "")),
                   (jump, "resume", lambda home, extra, sid, prof: calls.append(("terminal", sid, prof)) or (True, "")),
                   (jump, "resume_remote_vscode", lambda host, sid, folder: calls.append(("ssh", host, sid, folder)) or (True, ""))), \
                contextlib.redirect_stdout(io.StringIO()):
            jump.main(["--resume", "abc", "--profile", ".claude-work", "--vscode"])
            jump.main(["--resume", "abc", "--profile", ".claude-work"])
            jump.main(["--remote-resume-vscode", "lab", "abc", "--cwd", "/srv"])
            with self.assertRaises(SystemExit):
                jump.main(["--remote-resume-vscode", "lab"])   # which chat?
            # a host's chat id that is another action's flag isn't taken for it (a region screenshot, here)
            for action in ("--remote-resume-vscode", "--remote-vscode"):
                with Patch((jump, "screenshot", lambda *a: calls.append("screenshot") or (True, ""))), \
                        self.assertRaises(SystemExit):
                    jump.main([action, "lab", "--screenshot", "--cwd", "/srv"])
        self.assertEqual(calls, [("vscode", "abc", ".claude-work"), ("terminal", "abc", ".claude-work"),
                                 ("ssh", "lab", "abc", "/srv")])


class LaterTests(unittest.TestCase):
    def test_runs_on_its_own_after_we_answer(self):
        # The child runs the task with its output closed, so the widget gets
        # this script's answer without waiting for it
        with tempfile.TemporaryDirectory() as tmp:
            done = Path(tmp) / "done"
            start = time.time()
            jump.later(lambda: (time.sleep(0.3), done.write_text(str(os.getpid()))))
            self.assertLess(time.time() - start, 0.2)
            for _ in range(50):
                if done.exists() and done.read_text():
                    break
                time.sleep(0.05)
            self.assertNotEqual(done.read_text(), str(os.getpid()))


if __name__ == "__main__":
    unittest.main()
