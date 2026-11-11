import claude_guard  # noqa: F401  (first: no test runs the real claude)
import importlib.util
import io
import json
import os
import shlex
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
spec = importlib.util.spec_from_file_location("accounts", CODE / "accounts.py")
accounts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(accounts)
cs = accounts.cs
import jump  # noqa: E402  (accounts.py opens its terminals through it)

from test_talpy_den import session, write  # noqa: E402

# A stand-in claude: notes each call (its arguments and CLAUDE_CONFIG_DIR),
# answers `auth status` from the folder's .claude.json and logs out the way
# Claude does (oauthAccount gone from .claude.json, the login file deleted)
# (run by the Python running the tests: PATH here may not have python3, as in
# the python:3.7 image, where it is in /usr/local/bin)
FAKE_CLAUDE = "#!" + sys.executable + r"""
import json, os, sys
d = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
with open(os.environ["CALLS"], "a") as f:
    f.write(json.dumps({"args": sys.argv[1:], "dir": os.environ.get("CLAUDE_CONFIG_DIR")}) + "\n")
path = os.path.join(d, ".claude.json")
try:
    data = json.load(open(path))
except OSError:
    data = {}
if sys.argv[1:3] == ["auth", "status"]:
    account = data.get("oauthAccount")
    print(json.dumps({"loggedIn": bool(account), "authMethod": "claude.ai" if account else "none",
                      **({"email": account.get("emailAddress")} if account else {})}))
    sys.exit(0 if account else 1)
if sys.argv[1:3] == ["auth", "logout"]:
    if os.environ.get("LOGOUT_FAILS"):
        print("Logout failed: network down", file=sys.stderr)
        sys.exit(1)
    data.pop("oauthAccount", None)
    json.dump(data, open(path, "w"))
    try:
        os.unlink(os.path.join(d, ".credentials.json"))
    except OSError:
        pass
    print("Successfully logged out from your Anthropic account.")
"""


class Home(unittest.TestCase):
    """A home with ~/.claude (a plain folder, logged in), ~/.claude-work and
    the stand-in claude in ~/.local/bin."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = h = Path(self.tmp.name) / "home"
        write(h / ".claude/projects/-x/a.jsonl", "")
        write(h / ".claude/settings.json", {"statusLine": {"type": "command", "command": "~/.claude/statusline.sh"}})
        write(h / ".claude/CLAUDE.md", "my rules")
        write(h / ".claude/skills/mine/SKILL.md", "a skill")
        write(h / ".claude/skills/synced/org-skill/SKILL.md", "claude.ai's")
        write(h / ".claude/agents/reviewer.md", "an agent")
        write(h / ".claude.json", {"oauthAccount": {"accountUuid": "acct-pro", "organizationType": "claude_pro"}})
        w = h / ".claude-work"
        write(w / ".profile-name", "work\n")
        write(w / ".claude.json", {"oauthAccount": {"accountUuid": "acct-team", "organizationType": "claude_team",
                                                    "emailAddress": "me@example.com"}})
        write(w / ".credentials.json", "{}")
        write(w / "projects/-y/b.jsonl", "")
        self.bin = h / ".local/bin"
        self.claude = self.bin / "claude"
        write(self.claude, FAKE_CLAUDE)
        self.claude.chmod(0o755)
        self.calls = Path(self.tmp.name) / "calls.jsonl"
        env = {"HOME": str(h), "PATH": f"{self.bin}:/usr/bin:/bin", "CALLS": str(self.calls),
               "XDG_CACHE_HOME": str(Path(self.tmp.name) / "cache"), "XDG_DATA_HOME": str(h / ".local/share")}
        self.env = mock.patch.dict(os.environ, env)
        self.env.start()
        os.environ.pop("CLAUDE_CONFIG_DIR", None)
        self.opened = []
        self.patches = [
            mock.patch.object(jump, "open_terminal", lambda cwd, cmd: self.opened.append((cwd, cmd)) or True),
            mock.patch.object(cs, "vscode_profile", lambda *a, **k: (False, None)),
            mock.patch.object(cs, "login_shell_path", lambda home: ""),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.env.stop()
        self.tmp.cleanup()

    def calls_made(self):
        try:
            return [json.loads(line) for line in self.calls.read_text().splitlines()]
        except OSError:
            return []

    def listed(self, check=False):
        ok, _, more = accounts.list_accounts(self.home, [], check)
        self.assertTrue(ok)
        return {a["key"]: a for a in more["accounts"]}

    def add(self, name, **kw):
        return accounts.add_account(self.home, [], name, **kw)


class AddTests(Home):
    def test_new_folder_is_an_account_not_logged_in(self):
        ok, message, profile = self.add("side")
        self.assertTrue(ok, message)
        folder = self.home / ".claude-side"
        self.assertEqual((folder / ".profile-name").read_text(), "side\n")  # claude-switch's marker
        self.assertEqual(folder.stat().st_mode & 0o777, 0o700)
        self.assertEqual(profile.key, ".claude-side")
        # the status check lists it, as an account to log in
        result = cs.collect(self.home, cs.cache_dir(self.home), with_tokens=False)
        group = next(g for g in result["groups"] if g["name"] == "side")
        self.assertTrue(group["loggedOut"])
        self.assertIsNone(group["limits"])
        self.assertFalse(next(g for g in result["groups"] if g["name"] == "work")["loggedOut"])
        self.assertFalse(self.listed()[".claude-side"]["loggedIn"])

    def test_names(self):
        for name, problem in [("", "Give the account a name"), ("default", "default is taken"), ("main", "main is what ~/.claude is called"),
                              ("1st", "starting with a letter"), ("a b", "letters, digits"),
                              ("x" * 33, "up to 32"), ("work", "There's an account called work"),
                              ("../etc", "letters, digits")]:
            ok, message, _ = self.add(name)
            self.assertFalse(ok, name)
            self.assertIn(problem, message)
        (self.home / ".claude-notes").mkdir()  # a folder that isn't an account
        self.assertIn("~/.claude-notes is there already", self.add("notes")[1])
        self.assertTrue(self.add("my_Work-2")[0])

    def test_shares_settings_from_the_real_files(self):
        # ~/.claude links to work: sharing from it links work's real files,
        # so switching the link later changes nothing here
        shared = self.home / "shared"
        write(shared / "settings.json", {"statusLine": {"type": "command", "command": "x"}})
        w = self.home / ".claude-work"
        os.symlink(shared / "settings.json", w / "settings.json")
        write(w / "skills/own/SKILL.md", "work's skill")
        os.symlink(shared, w / "commands")  # a folder shared whole
        ok, message, _ = self.add("side", share_from=".claude-work")
        self.assertTrue(ok, message)
        side = self.home / ".claude-side"
        self.assertEqual(os.readlink(side / "settings.json"), str(shared / "settings.json"))
        self.assertEqual(os.readlink(side / "skills/own"), str(w / "skills/own"))
        self.assertEqual(os.readlink(side / "commands"), str(shared))
        self.assertIn("sharing settings.json, skills (1), commands with work", message)

    def test_own_skills_one_by_one_without_claude_ais(self):
        ok, message, _ = self.add("side", share_from=".claude")
        self.assertTrue(ok, message)
        side, main = self.home / ".claude-side", self.home / ".claude"
        self.assertEqual(os.readlink(side / "settings.json"), str(main / "settings.json"))
        self.assertEqual(os.readlink(side / "CLAUDE.md"), str(main / "CLAUDE.md"))
        self.assertFalse(side.joinpath("skills").is_symlink())  # a folder of its own…
        self.assertEqual(sorted(os.listdir(side / "skills")), ["mine"])  # …without skills/synced
        self.assertEqual(os.readlink(side / "agents/reviewer.md"), str(main / "agents/reviewer.md"))
        for kept in (".claude.json", ".credentials.json", "plugins", "projects", "keybindings.json"):
            self.assertFalse(os.path.lexists(side / kept), kept)

    def test_unknown_profile_to_share_from(self):
        ok, message, _ = self.add("side", share_from=".claude-nope")
        self.assertFalse(ok)
        self.assertFalse((self.home / ".claude-side").exists())

    def test_command(self):
        ok, message, profile = self.add("side", with_command=True)
        self.assertTrue(ok, message)
        self.assertIn("Added claude-side", message)
        script = self.bin / "claude-side"
        self.assertEqual(script.stat().st_mode & 0o777, 0o755)
        # it runs claude on the account
        r = subprocess.run([str(script), "--version"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.calls_made()[-1], {"args": ["--version"], "dir": str(self.home / ".claude-side")})
        self.assertTrue(self.listed()[".claude-side"]["command"])
        self.assertEqual(accounts.remove_command(profile, self.home), (True, "Removed claude-side"))
        self.assertFalse(script.exists())

    def test_command_uses_the_link_name_where_claude_does(self):
        # ~/.claude links to work: terminals run work as ~/.claude (Claude
        # keys its background service by that name), so the command does too
        os.rename(self.home / ".claude", self.home / ".claude-old")
        os.symlink(self.home / ".claude-work", self.home / ".claude")
        profile, _ = accounts.find_profile(self.home, [], ".claude-work")
        self.assertTrue(accounts.add_command(profile, self.home)[0])
        subprocess.run([str(self.bin / "claude-work")], check=True)
        self.assertEqual(self.calls_made()[-1]["dir"], str(self.home / ".claude"))

    def test_command_with_a_name_of_two_lines(self):
        # .profile-name is other tools' too: a second line stays in the
        # script's comment, it never runs
        write(self.home / ".claude-work/.profile-name", "work\nprintf injected; #\n")
        profile, _ = accounts.find_profile(self.home, [], ".claude-work")
        self.assertTrue(accounts.add_command(profile, self.home)[0])
        r = subprocess.run([str(self.bin / "claude-work"), "--version"], capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout), (0, ""), r.stderr)
        self.assertEqual(self.calls_made()[-1]["dir"], str(self.home / ".claude-work"))

    def test_command_never_replaces_another_program(self):
        write(self.bin / "claude-switch", "#!/bin/sh\necho the real claude-switch\n")
        ok, message, _ = self.add("switch", with_command=True)
        self.assertFalse(ok)
        self.assertIn("~/.local/bin/claude-switch is there already (not made by Talpy Den)", message)
        self.assertFalse((self.home / ".claude-switch").exists())  # nothing made
        self.assertTrue(self.add("switch")[0])  # without the command it's fine
        profile, _ = accounts.find_profile(self.home, [], ".claude-switch")
        self.assertFalse(accounts.remove_command(profile, self.home)[0])
        self.assertIn("the real claude-switch", (self.bin / "claude-switch").read_text())

    def test_command_off_path_says_so(self):
        os.environ["PATH"] = "/usr/bin:/bin"
        profile, _ = accounts.find_profile(self.home, [], ".claude-work")
        ok, message = accounts.add_command(profile, self.home)
        self.assertTrue(ok)
        self.assertIn("~/.local/bin isn't on your PATH", message)

    def test_main_has_no_command(self):
        profile, _ = accounts.find_profile(self.home, [], ".claude")
        self.assertFalse(accounts.add_command(profile, self.home)[0])
        self.assertIsNone(self.listed()[".claude"]["commandName"])


class LoginTests(Home):
    def test_add_opens_claudes_login_in_a_terminal(self):
        out = self.main("--add", "side")
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["key"], ".claude-side")
        [(cwd, command)] = self.opened
        self.assertEqual(cwd, str(self.home))
        self.assertIn(f"CLAUDE_CONFIG_DIR={shlex.quote(str(self.home / '.claude-side'))} claude auth login", command)
        self.assertIn("Log in to Claude for side (~/.claude-side)", command)

    def test_print_command_for_a_terminal_of_your_own(self):
        out = self.main("--login", ".claude-work", "--print-command")
        self.assertTrue(out["ok"])
        self.assertEqual(self.opened, [])
        self.assertTrue(out["command"].endswith(f"{self.claude} auth login"))

    def test_plain_default_logs_in_without_the_variable(self):
        out = self.main("--login", ".claude", "--print-command")
        self.assertIn("env -u CLAUDE_CONFIG_DIR", out["command"])

    def test_check_asks_claude(self):
        accounts_ = self.listed(check=True)
        self.assertTrue(accounts_[".claude-work"]["checked"])
        self.assertEqual(accounts_[".claude-work"]["email"], "me@example.com")
        self.assertEqual(accounts_[".claude-work"]["method"], "claude.ai")
        self.assertEqual({c["dir"] for c in self.calls_made()}, {None, str(self.home / ".claude-work")})

    def test_logout(self):
        ok, message = accounts.logout(self.home, [], ".claude-work")
        self.assertTrue(ok, message)
        self.assertEqual(self.calls_made()[-1], {"args": ["auth", "logout"], "dir": str(self.home / ".claude-work")})
        # the popup says so, though the folder has chats (and no .profile-name)
        (self.home / ".claude-work/.profile-name").unlink()
        result = cs.collect(self.home, cs.cache_dir(self.home), with_tokens=False)
        self.assertTrue(next(g for g in result["groups"] if g["name"] == "work")["loggedOut"])
        self.assertFalse(self.listed()[".claude-work"]["loggedIn"])

    def test_logout_refused_while_chats_run(self):
        write(self.home / ".claude-work/sessions/1.json", session("busy", status="busy"))
        ok, message = accounts.logout(self.home, [], ".claude-work")
        self.assertFalse(ok)
        self.assertIn("A chat runs on work", message)
        self.assertEqual(self.calls_made(), [])

    def test_logout_failure_is_reported(self):
        os.environ["LOGOUT_FAILS"] = "1"
        ok, message = accounts.logout(self.home, [], ".claude-work")
        self.assertFalse(ok)
        self.assertIn("network down", message)

    def main(self, *args):
        with mock.patch("sys.stdout") as out:
            accounts.main(list(args))
        return json.loads("".join(c[0][0] for c in out.write.call_args_list))  # (call.args: Python 3.8+)


class RemoveTests(Home):
    def trash(self):
        return self.home / ".local/share/Trash"

    def test_logs_out_then_moves_to_the_trash(self):
        profile, _ = accounts.find_profile(self.home, [], ".claude-work")
        accounts.add_command(profile, self.home)
        ok, message = accounts.remove_account(self.home, [], ".claude-work")
        self.assertTrue(ok, message)
        self.assertFalse(os.path.lexists(self.home / ".claude-work"))
        self.assertEqual(self.calls_made()[-1]["args"], ["auth", "logout"])
        moved = self.trash() / "files/.claude-work"
        self.assertTrue((moved / "projects/-y/b.jsonl").exists())
        self.assertFalse(os.path.lexists(moved / ".credentials.json"))
        info = (self.trash() / "info/.claude-work.trashinfo").read_text()
        self.assertIn(f"Path={self.home / '.claude-work'}\n", info)
        self.assertIn("DeletionDate=", info)
        self.assertFalse((self.bin / "claude-work").exists())
        self.assertIn("Removed claude-work", message)
        # one with the same name again goes next to it
        self.add("work")
        self.assertTrue(accounts.remove_account(self.home, [], ".claude-work")[0])
        self.assertTrue((self.trash() / "files/.claude-work.2/.profile-name").exists())
        self.assertNotIn(".claude-work", {a["key"] for a in self.listed().values()})

    def test_login_never_reaches_the_trash(self):
        os.environ["LOGOUT_FAILS"] = "1"
        ok, message = accounts.remove_account(self.home, [], ".claude-work")
        self.assertTrue(ok)
        self.assertIn("couldn't log out first", message)
        self.assertFalse(os.path.lexists(self.trash() / "files/.claude-work/.credentials.json"))

    def test_refusals(self):
        self.assertIn("main Claude folder", accounts.remove_account(self.home, [], ".claude")[1])
        write(self.home / ".claude-work/sessions/1.json", session("busy", status="busy"))
        self.assertIn("A chat runs on it", accounts.remove_account(self.home, [], ".claude-work")[1])
        (self.home / ".claude-work/sessions/1.json").unlink()
        with mock.patch.object(cs, "vscode_profile", lambda home, profiles, *a, **k: (True, profiles[1])):
            self.assertIn("VS Code's Claude runs on it", accounts.remove_account(self.home, [], ".claude-work")[1])
        extra = Path(self.tmp.name) / "elsewhere"
        write(extra / ".profile-name", "elsewhere")
        self.assertIn("Only ~/.claude-NAME folders", accounts.remove_account(self.home, [str(extra)], str(extra))[1])
        os.rename(self.home / ".claude", self.home / ".claude-old")
        os.symlink(self.home / ".claude-work", self.home / ".claude")
        self.assertIn("~/.claude links to it", accounts.remove_account(self.home, [], ".claude-work")[1])
        self.assertTrue((self.home / ".claude-work/.credentials.json").exists())
        self.assertEqual(self.calls_made(), [])
        self.assertTrue(self.listed()[".claude-work"]["notRemovable"])

    def test_not_across_disks_without_gio(self):
        with mock.patch.object(accounts, "device", lambda p: 2 if str(p).endswith("files") else 1), \
                mock.patch.object(accounts.shutil, "which", lambda name: None):
            ok, message = accounts.remove_account(self.home, [], ".claude-work")
        self.assertFalse(ok)
        self.assertIn("another disk than your Trash", message)
        self.assertTrue((self.home / ".claude-work/.credentials.json").exists())

    def test_hands_over_what_other_accounts_link_into_it(self):
        # side and third share work's CLAUDE.md, side its projects/ folder
        # too: Remove gives them to side (the first that links to each),
        # third's link points there, and work's folder goes to the Trash
        # with links to them
        write(self.home / ".claude-work/CLAUDE.md", "work's rules")
        self.assertTrue(self.add("side", share_from=".claude-work")[0])
        self.assertTrue(self.add("third", share_from=".claude-work")[0])
        side, third = self.home / ".claude-side", self.home / ".claude-third"
        os.symlink(self.home / ".claude-work/projects", side / "projects")
        listed = self.listed()[".claude-work"]
        self.assertEqual(listed["notRemovable"], "")
        self.assertEqual(listed["handOver"], "What your other accounts share from it moves to them first: "
                                             "CLAUDE.md and projects to side (third keeps sharing them there).")
        self.assertEqual(self.listed()[".claude-side"]["handOver"], "")
        ok, message = accounts.remove_account(self.home, [], ".claude-work")
        self.assertTrue(ok, message)
        self.assertIn("; CLAUDE.md and projects moved to side (third keeps sharing them there)", message)
        self.assertFalse(os.path.islink(side / "CLAUDE.md"))
        self.assertEqual((side / "CLAUDE.md").read_text(), "work's rules")
        self.assertTrue((side / "projects/-y/b.jsonl").is_file())
        self.assertFalse(os.path.islink(side / "projects"))
        self.assertEqual(os.readlink(third / "CLAUDE.md"), os.path.realpath(side / "CLAUDE.md"))
        moved = self.trash() / "files/.claude-work"
        self.assertEqual(os.readlink(moved / "CLAUDE.md"), os.path.realpath(side / "CLAUDE.md"))
        self.assertEqual(sorted(os.listdir(side)), [".profile-name", "CLAUDE.md", "projects"])

    def test_the_default_account_gets_it_first(self):
        write(self.home / ".claude-work/CLAUDE.md", "work's rules")
        self.add("side", share_from=".claude-work")
        self.add("third", share_from=".claude-work")
        third = self.home / ".claude-third"
        default = lambda home, profiles, *a, **k: (True, next(p for p in profiles if p.label == "third"))  # noqa: E731
        with mock.patch.object(cs, "vscode_profile", default):
            self.assertIn("CLAUDE.md to third (side keeps sharing it there)", self.listed()[".claude-work"]["handOver"])
            self.assertTrue(accounts.remove_account(self.home, [], ".claude-work")[0])
        self.assertEqual((third / "CLAUDE.md").read_text(), "work's rules")
        self.assertEqual(os.readlink(self.home / ".claude-side/CLAUDE.md"), os.path.realpath(third / "CLAUDE.md"))

    def test_a_link_into_a_folder_that_moved_whole_points_at_its_new_place(self):
        # side links work's skills/ whole, third one skill of it: skills/ moves to side (the
        # default account), and third's link points there, not through work's folder in the Trash
        write(self.home / ".claude-work/skills/a/SKILL.md", "a skill")
        self.add("side")
        self.add("third")
        side, third = self.home / ".claude-side", self.home / ".claude-third"
        os.symlink(self.home / ".claude-work/skills", side / "skills")
        (third / "skills").mkdir()
        os.symlink(self.home / ".claude-work/skills/a", third / "skills/a")
        default = lambda home, profiles, *a, **k: (True, next(p for p in profiles if p.label == "side"))  # noqa: E731
        with mock.patch.object(cs, "vscode_profile", default):
            self.assertIn("skills to side (third keeps sharing it there)", self.listed()[".claude-work"]["handOver"])
            self.assertTrue(accounts.remove_account(self.home, [], ".claude-work")[0])
        self.assertEqual(os.readlink(third / "skills/a"), os.path.realpath(side / "skills/a"))
        self.assertEqual((third / "skills/a/SKILL.md").read_text(), "a skill")

    def test_a_link_through_it_points_past_it(self):
        # work's settings.json is a link to a shared one, side's a link to
        # work's: side's then points at the shared one, nothing moves
        shared = self.home / "dotfiles/settings.json"
        write(shared, {"theme": "dark"})
        os.symlink(shared, self.home / ".claude-work/settings.json")
        self.add("side")
        os.symlink(self.home / ".claude-work/settings.json", self.home / ".claude-side/settings.json")
        self.assertEqual(self.listed()[".claude-work"]["handOver"], "")
        ok, message = accounts.remove_account(self.home, [], ".claude-work")
        self.assertTrue(ok, message)
        self.assertNotIn(" to side", message)
        self.assertEqual(os.readlink(self.home / ".claude-side/settings.json"), os.path.realpath(shared))

    def test_on_another_disk_it_is_copied(self):
        write(self.home / ".claude-work/CLAUDE.md", "work's rules")
        self.add("side", share_from=".claude-work")
        work, rename = str(self.home / ".claude-work") + os.sep, os.rename

        def across(src, dst):
            if str(src).startswith(work) and not str(dst).startswith(work):
                raise OSError(accounts.errno.EXDEV, "Invalid cross-device link")
            return rename(src, dst)
        with mock.patch.object(accounts.os, "rename", across):
            ok, message = accounts.remove_account(self.home, [], ".claude-work")
        self.assertTrue(ok, message)
        side = self.home / ".claude-side/CLAUDE.md"
        self.assertFalse(os.path.islink(side))
        self.assertEqual(side.read_text(), "work's rules")
        moved = self.trash() / "files/.claude-work"
        self.assertEqual((moved / "CLAUDE.md.handed-over").read_text(), "work's rules")
        self.assertEqual(os.readlink(moved / "CLAUDE.md"), os.path.realpath(side))

    def test_a_failed_move_keeps_every_link_whole(self):
        write(self.home / ".claude-work/CLAUDE.md", "work's rules")
        self.add("side", share_from=".claude-work")
        with mock.patch.object(accounts.os, "replace", mock.Mock(side_effect=PermissionError(13, "Permission denied"))):
            ok, message = accounts.remove_account(self.home, [], ".claude-work")
        self.assertFalse(ok)
        self.assertIn("isn't removed: CLAUDE.md couldn't move to side (Permission denied)", message)
        self.assertEqual((self.home / ".claude-side/CLAUDE.md").read_text(), "work's rules")
        self.assertEqual((self.home / ".claude-work/CLAUDE.md").read_text(), "work's rules")
        self.assertTrue((self.home / ".claude-work/.credentials.json").exists())
        self.assertEqual(self.calls_made(), [])

    def test_not_while_a_link_points_at_the_whole_folder(self):
        self.add("side")
        os.symlink(self.home / ".claude-work", self.home / ".claude-side/old")
        ok, message = accounts.remove_account(self.home, [], ".claude-work")
        self.assertFalse(ok)
        self.assertIn("side's old is a link to the whole folder: remove that link first", message)
        self.assertTrue((self.home / ".claude-work/.credentials.json").exists())
        self.assertEqual(self.calls_made(), [])

    def test_not_with_a_mount_inside(self):
        # a folder bind-mounted in it (another account's projects/, say) would
        # go to the Trash mounted, and emptying the Trash would delete it there
        mountinfo = Path(self.tmp.name) / "mountinfo"
        write(mountinfo, "22 1 0:21 / / rw - btrfs /dev/x rw\n"
                         f"36 22 0:21 /p {os.path.realpath(self.home)}/.claude-work/my\\040projects rw - btrfs /dev/x rw\n")
        with mock.patch.object(accounts, "MOUNTINFO", str(mountinfo)):
            ok, message = accounts.remove_account(self.home, [], ".claude-work")
            self.assertFalse(ok)
            self.assertIn(".claude-work/my projects is a mount point", message)
            self.assertTrue((self.home / ".claude-work/.credentials.json").exists())
            self.assertEqual(self.calls_made(), [])
            # mounts elsewhere don't count
            write(mountinfo, f"36 22 0:21 /p {self.home}/.claude-work2 rw - btrfs /dev/x rw\n")
            self.assertTrue(accounts.remove_account(self.home, [], ".claude-work")[0])


class LinkedHome(Home):
    """~/.claude links to work; VS Code's Claude runs on the folder its
    settings name (a file with comments)."""

    def setUp(self):
        super().setUp()
        os.rename(self.home / ".claude", self.home / ".claude-personal")
        write(self.home / ".claude-personal/.profile-name", "personal")
        write(self.home / ".claude-personal/.claude.json",
              {"oauthAccount": {"accountUuid": "acct-pro", "organizationType": "claude_pro"}})
        os.symlink(self.home / ".claude-work", self.home / ".claude")
        self.config = Path(self.tmp.name) / "config"
        os.environ["XDG_CONFIG_HOME"] = str(self.config)
        self.settings = self.config / "Code/User/settings.json"
        write(self.settings, '{\n    // my editor\n    "editor.fontSize": 14,\n    "claudeCode.environmentVariables": [\n'
                             '        {"name": "CLAUDE_CONFIG_DIR", "value": "%s"}\n    ],\n}\n' % (self.home / ".claude-personal"))
        self.children = []
        self.patches.append(mock.patch.object(cs, "vscode_app", lambda: ("/usr/bin/code", "Code")))
        self.patches.append(mock.patch.object(cs, "vscode_running_config_dir", lambda: (False, None)))
        self.patches.pop(1).stop()  # the real vscode_profile: it reads the settings above
        for p in self.patches[-2:]:
            p.start()

    def tearDown(self):
        for c in self.children:
            c.kill()
            c.wait()
        super().tearDown()

    def chat_through(self, name):
        """A live chat started with CLAUDE_CONFIG_DIR=name."""
        env = {**os.environ, "CLAUDE_CONFIG_DIR": str(name)}
        child = subprocess.Popen(["sleep", "120"], env=env)
        self.children.append(child)
        for _ in range(500):
            if cs.proc_start_time(child.pid) and cs.process_config_dir(child.pid):
                break
            time.sleep(0.01)
        write(self.home / ".claude-work/sessions" / f"{child.pid}.json",
              session("chat", pid=child.pid, procStart=cs.proc_start_time(child.pid)))

    def first(self):
        result = cs.collect(self.home, cs.cache_dir(self.home), with_tokens=False)
        cs.add_vscode(result, self.home)
        return [(g["name"], g["defaultHere"], g["vscodeHere"], g["plainHere"]) for g in result["groups"]]


class DefaultTests(LinkedHome):
    def test_the_default_is_vscodes_and_comes_first(self):
        self.assertEqual(self.first(), [("personal", True, True, False), ("work", False, False, True)])
        listed = self.listed()
        self.assertTrue(listed[".claude-personal"]["default"])
        self.assertTrue(listed[".claude-work"]["main"])

    def test_without_vscode_plain_claudes(self):
        with mock.patch.object(cs, "vscode_app", lambda: (None, None)):
            self.assertEqual(self.first()[0], ("work", True, False, True))

    def test_make_default_points_both_there(self):
        ok, message = accounts.make_default(self.home, [], ".claude-personal")
        self.assertTrue(ok, message)
        self.assertEqual(os.readlink(self.home / ".claude"), str(self.home / ".claude-personal"))
        text = self.settings.read_text()
        self.assertIn("// my editor", text)  # the rest of the file as it was
        self.assertEqual(cs.jsonc(text)["claudeCode.environmentVariables"],
                         [{"name": "CLAUDE_CONFIG_DIR", "value": str(self.home / ".claude")}])  # follows the link now
        self.assertIn(": plain claude runs on it", message)
        # and back: VS Code follows the link, plain claude moves
        ok, message = accounts.make_default(self.home, [], ".claude-work")
        self.assertTrue(ok, message)
        self.assertEqual(os.readlink(self.home / ".claude"), str(self.home / ".claude-work"))
        self.assertEqual(self.first()[0][0], "work")
        self.assertIn("already", accounts.make_default(self.home, [], ".claude-work")[1])

    def test_a_relative_link_stays_relative(self):
        (self.home / ".claude").unlink()
        os.symlink(".claude-work", self.home / ".claude")
        self.assertTrue(accounts.make_default(self.home, [], ".claude-personal")[0])
        self.assertEqual(os.readlink(self.home / ".claude"), ".claude-personal")

    def test_a_relative_link_to_a_folder_elsewhere(self):
        # a relative link names a folder next to it: one that isn't in the
        # home folder (--config-dir) gets its full path
        (self.home / ".claude").unlink()
        os.symlink(".claude-work", self.home / ".claude")
        extra = Path(self.tmp.name) / "elsewhere/claude"
        write(extra / ".profile-name", "elsewhere")
        ok, message = accounts.make_default(self.home, [str(extra)], str(extra))
        self.assertTrue(ok, message)
        self.assertEqual(os.path.realpath(self.home / ".claude"), str(extra.resolve()))

    def test_an_account_found_only_through_the_link_isnt_dropped(self):
        # ~/.claude links to a folder not named ~/.claude-*: moving the link
        # would leave it out of every list
        (self.home / ".claude").unlink()
        work = Path(self.tmp.name) / "accounts/work"
        write(work / ".profile-name", "work")
        os.symlink(str(work), self.home / ".claude")
        ok, message = accounts.make_default(self.home, [], ".claude-personal")
        self.assertFalse(ok)
        self.assertIn("found only through that link", message)
        self.assertEqual(os.readlink(self.home / ".claude"), str(work))
        # one in the extra config folders is found without it
        ok, message = accounts.make_default(self.home, [str(work)], ".claude-personal")
        self.assertTrue(ok, message)
        self.assertEqual(os.readlink(self.home / ".claude"), str(self.home / ".claude-personal"))

    def test_refused_while_a_chat_runs_through_the_link(self):
        self.chat_through(self.home / ".claude")
        ok, message = accounts.make_default(self.home, [], ".claude-personal")
        self.assertFalse(ok)
        self.assertIn("a Claude process runs through ~/.claude", message)
        self.assertEqual(os.readlink(self.home / ".claude"), str(self.home / ".claude-work"))
        self.assertIn(str(self.home / ".claude-personal"), self.settings.read_text())  # nothing changed

    def test_refused_while_a_chat_works_in_vscodes_claude(self):
        # VS Code's Claude would switch: a chat working in its panel would be cut off when the window reloads
        child = subprocess.Popen(["sleep", "120"])
        self.children.append(child)
        for _ in range(500):
            if cs.proc_start_time(child.pid):
                break
            time.sleep(0.01)
        write(self.home / ".claude-personal/sessions" / f"{child.pid}.json",
              session("panel", pid=child.pid, procStart=cs.proc_start_time(child.pid), entrypoint="claude-vscode",
                      status="busy"))
        ok, message = accounts.make_default(self.home, [], ".claude-work")
        self.assertFalse(ok)
        self.assertIn("a chat works in VS Code's Claude", message)
        self.assertEqual(os.readlink(self.home / ".claude"), str(self.home / ".claude-work"))  # nothing changed
        # done working: it may switch
        write(self.home / ".claude-personal/sessions" / f"{child.pid}.json",
              session("panel", pid=child.pid, procStart=cs.proc_start_time(child.pid), entrypoint="claude-vscode"))
        self.assertTrue(accounts.make_default(self.home, [], ".claude-work")[0])

    def test_a_chat_on_the_folders_own_name_doesnt_move(self):
        self.chat_through(self.home / ".claude-work")
        self.assertTrue(accounts.make_default(self.home, [], ".claude-personal")[0])

    def test_a_main_folder_stays_a_folder(self):
        (self.home / ".claude").unlink()
        os.rename(self.home / ".claude-work", self.home / ".claude")
        ok, message = accounts.make_default(self.home, [], ".claude-personal")
        self.assertTrue(ok, message)
        self.assertTrue((self.home / ".claude").is_dir() and not (self.home / ".claude").is_symlink())
        self.assertIn("plain claude stays on ~/.claude (a folder", message)
        self.assertEqual(self.first()[0][0], "personal")
        # the main folder as the default: VS Code's Claude without the variable
        self.assertTrue(accounts.make_default(self.home, [], ".claude")[0])
        self.assertEqual(cs.jsonc(self.settings.read_text())["claudeCode.environmentVariables"], [])

    def test_no_main_folder_gets_no_link(self):
        # only ~/.claude-NAME folders: a link made there would mix accounts
        # (plain claude reads ~/.claude.json without CLAUDE_CONFIG_DIR)
        (self.home / ".claude").unlink()
        ok, message = accounts.make_default(self.home, [], ".claude-work")
        self.assertTrue(ok, message)
        self.assertFalse(os.path.lexists(self.home / ".claude"))
        self.assertIn("plain claude has no ~/.claude here: run claude-work", message)
        self.assertEqual(self.first()[0][0], "work")  # VS Code's Claude runs on it now
        with mock.patch.object(cs, "vscode_app", lambda: (None, None)):
            listed = accounts.list_accounts(self.home, [])[2]
        self.assertFalse(listed["canDefault"])  # nothing Make Default could change
        self.assertTrue(accounts.list_accounts(self.home, [])[2]["canDefault"])

    def test_one_account(self):
        import shutil
        shutil.rmtree(self.home / ".claude-personal")
        self.settings.unlink()
        self.assertEqual(self.first(), [("work", True, True, True)])
        self.assertIn("already", accounts.make_default(self.home, [], ".claude-work")[1])


class HideTests(LinkedHome):
    """Hiding an account you don't use (personal is the default: VS Code's
    Claude runs on it; ~/.claude links to work)."""

    def status(self):
        result = cs.collect(self.home, cs.cache_dir(self.home), with_tokens=False)
        cs.add_vscode(result, self.home)
        return [g["name"] for g in result["groups"]], [g["name"] for g in result["hiddenGroups"]], result

    def test_nothing_of_a_hidden_account_is_read(self):
        self.assertTrue(accounts.hide_account(self.home, [], ".claude-work", True)[0])
        read = []
        history_tail, live_entries_all = cs.history_tail, cs.live_entries_all
        with mock.patch.object(cs, "history_tail", lambda p: read.append(p.key) or history_tail(p)), \
                mock.patch.object(cs, "live_entries_all", lambda ps: read.extend(p.key for p in ps) or live_entries_all(ps)):
            self.status()
        self.assertEqual(set(read), {".claude-personal"})

    def test_hide_leaves_it_out_until_shown(self):
        ok, message = accounts.hide_account(self.home, [], ".claude-work", True)
        self.assertTrue(ok, message)
        self.assertIn("work is hidden", message)
        self.assertEqual({k: a["hidden"] for k, a in self.listed().items()}, {".claude-personal": False, ".claude-work": True})
        shown, hidden, result = self.status()
        self.assertEqual((shown, hidden), (["personal"], ["work"]))
        # (what Make Default needs of it, without its lists)
        self.assertEqual((result["hiddenGroups"][0]["chatProfile"], result["hiddenGroups"][0]["recent"]), (".claude-work", []))
        ok, message = accounts.hide_account(self.home, [], ".claude-work", False)
        self.assertEqual((ok, message), (True, "work shows again"))
        self.assertEqual(self.status()[:2], (["personal", "work"], []))

    def test_not_the_default_nor_the_last_one_shown(self):
        ok, message = accounts.hide_account(self.home, [], ".claude-personal", True)
        self.assertFalse(ok)
        self.assertIn("personal is the default account", message)
        self.assertEqual(cs.load_hidden(cs.cache_dir(self.home))["accounts"], {})
        with mock.patch.object(cs, "default_profile", lambda *a, **k: (False, None, None, None)):
            self.assertTrue(accounts.hide_account(self.home, [], ".claude-work", True)[0])
            ok, message = accounts.hide_account(self.home, [], ".claude-personal", True)
        self.assertFalse(ok)
        self.assertIn("the only account shown", message)

    def test_one_with_a_chat_going_on_shows(self):
        self.assertTrue(accounts.hide_account(self.home, [], ".claude-work", True)[0])
        # a background chat that finished doesn't count
        updated = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(time.time() - 600))
        write(self.home / ".claude-work/jobs/0a1b2c3d/state.json",
              {"sessionId": "chat", "state": "done", "tempo": "idle", "updatedAt": updated, "createdAt": updated})
        self.assertEqual(self.status()[:2], (["personal"], ["work"]))
        self.chat_through(self.home / ".claude-work")
        shown, hidden, result = self.status()
        self.assertEqual((shown, hidden), (["personal", "work"], []))
        self.assertTrue(result["groups"][1]["hidden"])

    def test_the_default_shows_again(self):
        self.assertTrue(accounts.hide_account(self.home, [], ".claude-work", True)[0])
        self.assertTrue(accounts.make_default(self.home, [], ".claude-work")[0])
        self.assertEqual(cs.load_hidden(cs.cache_dir(self.home))["accounts"], {})
        # made the default elsewhere (VS Code's own setting): the status forgets its hide
        self.assertTrue(accounts.hide_account(self.home, [], ".claude-personal", True)[0])
        write(self.settings, '{"claudeCode.environmentVariables": [{"name": "CLAUDE_CONFIG_DIR", "value": "%s"}]}'
              % (self.home / ".claude-personal"))
        self.assertEqual(self.status()[:2], (["personal", "work"], []))
        self.assertEqual(cs.load_hidden(cs.cache_dir(self.home))["accounts"], {})

    def test_from_the_command_line(self):
        out = io.StringIO()
        with mock.patch("sys.stdout", out):
            accounts.main(["--hide", ".claude-work"])
        self.assertTrue(json.loads(out.getvalue())["ok"])
        self.assertIn(".claude-work", cs.load_hidden(cs.cache_dir(self.home))["accounts"])


class CommandLineTests(unittest.TestCase):
    def test_usage(self):
        for args in ([], ["--logout"], ["--list", "--command"], ["--logout", "x", "--print-command"], ["--bogus"]):
            with self.assertRaises(SystemExit, msg=args):
                accounts.main(args)

    def test_runs_as_a_script(self):
        with tempfile.TemporaryDirectory() as home:
            env = {"HOME": home, "PATH": "/usr/bin:/bin", "XDG_CACHE_HOME": home + "/cache"}
            r = subprocess.run([sys.executable, "-I", str(CODE / "accounts.py"), "--list"], env=env,
                               capture_output=True, text=True, timeout=60)
            out = json.loads(r.stdout)
            self.assertEqual((out["ok"], out["accounts"]), (True, []))


if __name__ == "__main__":
    unittest.main()
