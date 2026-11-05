import importlib.util
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True  # keep __pycache__ out of the plasmoid package
ROOT = Path(__file__).resolve().parent.parent
CODE = ROOT / "package/contents/code"
sys.path.insert(0, str(CODE))
spec = importlib.util.spec_from_file_location("cleanup", CODE / "cleanup.py")
cleanup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cleanup)
cs = cleanup.cs

DAY = 86400
A, B, S, L, Q, K, D, X = ("aaaaaaaa-0000-4000-8000-00000000000%d" % i for i in range(8))


def aged(path, days, now):
    """Make path (a file or a folder, not through a link) days old."""
    t = now - days * DAY
    os.utime(str(path), (t, t), follow_symlinks=False)


class Home(unittest.TestCase):
    """A made-up home: ~/.claude-work and ~/.claude-personal, their settings
    one file shared through links (as many set it up), and Talpy Den's cache,
    state and data folders inside it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "home"
        env = {"HOME": str(self.home), "XDG_CACHE_HOME": str(self.home / ".cache"),
               "XDG_STATE_HOME": str(self.home / ".local/state"), "XDG_DATA_HOME": str(self.home / ".local/share")}
        saved = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        self.addCleanup(lambda: [os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
                                 for k, v in saved.items()])
        self.cache = cs.cache_dir(self.home)
        cs.private_dir(self.cache)
        (self.home / ".claude-shared").mkdir(parents=True)
        self.shared_settings = self.home / ".claude-shared/settings.json"
        self.shared_settings.write_text(json.dumps({"theme": "dark"}))
        for name in ("work", "personal"):
            d = self.home / (".claude-" + name)
            (d / "projects/-w").mkdir(parents=True)
            (d / ".profile-name").write_text(name)
            (d / ".claude.json").write_text(json.dumps({"oauthAccount": {"accountUuid": "acct-" + name}}))
            (d / "settings.json").symlink_to(self.shared_settings)
        self.work = self.home / ".claude-work"
        self.now = time.time()
        self.running = mock.patch.object(cleanup, "running", return_value=(set(), set()))
        self.running.start()
        self.addCleanup(self.running.stop)

    def chat(self, chat, days, profile="work", text=None):
        path = self.home / (".claude-" + profile) / "projects/-w" / (chat + ".jsonl")
        path.write_text(text or json.dumps({"type": "user", "sessionId": chat, "entrypoint": "cli"}) + "\n")
        aged(path, days, self.now)
        return path

    def thing(self, rel, days, folder=False, profile="work"):
        path = self.home / (".claude-" + profile) / rel
        if folder:
            path.mkdir(parents=True, exist_ok=True)
            (path / "inside.txt").write_text("x" * 10)
            aged(path / "inside.txt", days, self.now)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x" * 10)
        aged(path, days, self.now)
        return path

    def run_here(self):
        with mock.patch.object(cleanup, "hosts_to_visit", return_value=[]):
            return cleanup.run(self.home, self.cache, now=self.now)["runs"][""]

    def talpy(self, days=30):
        return cleanup.set_mode(self.home, self.cache, (), "talpy", days, start=False)


class ChatTests(Home):
    def test_an_old_chat_goes_with_its_files_what_stays_stays(self):
        old = self.chat(A, 40)
        for rel in (A + ".ccr-tip.json", A + ".precompact.json"):
            self.thing("projects/-w/" + rel, 40)
        sub = self.thing("projects/-w/%s/subagents" % A, 40, folder=True)
        side = [self.thing("file-history/" + A, 40, folder=True), self.thing("session-env/" + A, 40, folder=True),
                self.thing("todos/%s-agent-%s.json" % (A, A), 40), self.thing("debug/%s.txt" % A, 40)]
        recent = self.chat(B, 2)
        undo_b = self.thing("file-history/" + B, 50, folder=True)  # (old, but its chat stays: so does it)
        starred, live, queued, keeping = self.chat(S, 40), self.chat(L, 40), self.chat(Q, 40), self.chat(K, 40)
        desktop = self.chat(D, 40, text=json.dumps({"type": "user", "entrypoint": "claude-desktop"}) + "\n")
        orphan_old = self.thing("file-history/" + X, 40, folder=True)
        orphan_new = self.thing("session-env/" + X, 3, folder=True)
        snap_old, snap_new = self.thing("shell-snapshots/a.sh", 40), self.thing("shell-snapshots/b.sh", 1)
        (self.work / "debug/latest").symlink_to(self.work / "debug" / (A + ".txt"))
        cs.change_stars(self.cache, "chats", S)
        cs.change_stars(self.cache, "chats", A, "lab")  # (a host's star: not this computer's chat)
        state = cs.state_dir(self.cache)
        cs.write_json_atomic(state / "keep.json", {"chats": [{"chat": K, "profile": "work"}]})
        cs.write_json_atomic(state / "queue.json", {"tasks": [{"id": "t1", "chat": Q, "host": "", "profile": "work"}]})
        self.talpy()
        self.running.stop()
        with mock.patch.object(cleanup, "running", return_value=({L}, set())):
            r = self.run_here()
        self.running.start()
        for gone in [old, sub.parent, orphan_old, snap_old] + side + [old.with_name(A + c) for c in cleanup.COMPANIONS]:
            self.assertFalse(os.path.lexists(str(gone)), gone)
        for stays in (recent, undo_b, starred, live, queued, keeping, desktop, orphan_new, snap_new,
                      self.work / "debug/latest"):
            self.assertTrue(os.path.lexists(str(stays)), stays)
        self.assertEqual((r["ok"], r["chats"], r["keptChats"]), (True, 1, 4))
        self.assertGreaterEqual(r["files"], 4)
        self.assertGreater(r["bytes"], 0)

    def test_a_chat_shared_between_accounts_goes_whole_once_every_copy_is_old(self):
        store = self.home / ".local/share/claude-status/shared-chats/-w"
        store.mkdir(parents=True)
        (store / A).mkdir()
        (store / (A + ".file-history")).mkdir()
        first = self.chat(A, 40)
        os.link(str(first), str(store / (A + ".jsonl")))
        os.link(str(first), str(self.home / ".claude-personal/projects/-w" / (A + ".jsonl")))
        for profile in ("work", "personal"):
            (self.home / (".claude-" + profile) / "projects/-w" / A).symlink_to(store / A)
            (self.home / (".claude-" + profile) / "file-history").mkdir()
            (self.home / (".claude-" + profile) / "file-history" / A).symlink_to(store / (A + ".file-history"))
        aged(first, 40, self.now)
        self.talpy()
        r = self.run_here()
        self.assertEqual(r["chats"], 2)  # (one per account's copy)
        self.assertEqual(sorted(os.listdir(str(store))) if store.exists() else [], [])
        for profile in ("work", "personal"):
            self.assertEqual(os.listdir(str(self.home / (".claude-" + profile) / "file-history")), [])

    def test_a_shared_chat_an_account_still_has_keeps_its_store(self):
        store = self.home / ".local/share/claude-status/shared-chats/-w"
        store.mkdir(parents=True)
        kept = self.chat(A, 40)
        os.link(str(kept), str(store / (A + ".jsonl")))
        cs.change_stars(self.cache, "chats", A)
        self.talpy()
        self.run_here()
        self.assertTrue((store / (A + ".jsonl")).exists())

    def test_background_chats_that_finished_go_the_others_stay(self):
        def job(name, state, days, sid=None):
            d = self.thing("jobs/" + name, days, folder=True)
            (d / "state.json").write_text(json.dumps({"state": state, "tempo": "idle", "sessionId": sid or name}))
            aged(d / "state.json", days, self.now)
            aged(d, days, self.now)
            return d
        done, working, live, starred, new = (job("j1", "done", 40), job("j2", "working", 40), job("j3", "done", 40),
                                             job("j4", "failed", 40, S), job("j5", "done", 2))
        cs.change_stars(self.cache, "chats", S)
        self.talpy()
        self.running.stop()
        with mock.patch.object(cleanup, "running", return_value=(set(), {"j3"})):
            r = self.run_here()
        self.running.start()
        self.assertFalse(done.exists())
        self.assertTrue(all(d.exists() for d in (working, live, starred, new)))
        self.assertEqual(r["backgroundChats"], 1)

    def test_the_status_says_what_a_run_would_delete_and_deletes_nothing(self):
        old = self.chat(A, 40)
        self.thing("plans/old-plan.md", 40)
        st = cleanup.status(self.home, self.cache, now=self.now)
        self.assertEqual((st["mode"], st["days"], st["preview"]["chats"], st["preview"]["plans"]), ("claude", 30, 1, 1))
        self.assertTrue(old.exists())
        self.assertEqual(st["claudeDays"], [{"account": "personal", "days": 30}, {"account": "work", "days": 30}]
                         if st["claudeDays"][0]["account"] == "personal" else
                         [{"account": "work", "days": 30}, {"account": "personal", "days": 30}])
        self.assertNotIn(cleanup.SETTING_KEY, json.loads(self.shared_settings.read_text()))  # (nothing changed)

    def test_claudes_own_cleanup_deletes_nothing_of_ours(self):
        old = self.chat(A, 40)
        cleanup.set_mode(self.home, self.cache, (), "claude", start=False)
        r = self.run_here()
        self.assertTrue(old.exists())
        self.assertEqual((r["mode"], r["raised"]), ("claude", False))


class PlanTests(Home):
    def test_old_plans_go_to_the_trash_once_starred_queued_and_living_ones_stay(self):
        one = self.thing("plans/old-plan.md", 40)
        other = self.home / ".claude-personal/plans/old-plan.md"
        other.parent.mkdir()
        os.link(str(one), str(other))
        aged(one, 40, self.now)
        starred, queued, living = (self.thing("plans/%s.md" % s, 40) for s in ("starred", "queued", "living"))
        recent = self.thing("plans/recent.md", 2)
        half = self.thing("plans/x.md.tmp.123", 40)
        cs.change_stars(self.cache, "plans", "starred")
        cs.write_json_atomic(cs.state_dir(self.cache) / "queue.json",
                             {"tasks": [{"id": "t1", "plan": "queued", "host": "", "profile": "work"}]})
        self.chat(B, 2)
        cs.write_json_atomic(self.cache / "plan-projects.json", {"plans": {"living": {"cwd": "/w", "chat": B}}})
        self.talpy()
        r = self.run_here()
        self.assertFalse(one.exists() or other.exists())
        trash = self.home / ".local/share/Trash"
        self.assertEqual(os.listdir(str(trash / "files")), ["old-plan.md"])
        self.assertIn("Path=", (trash / "info/old-plan.md.trashinfo").read_text())
        self.assertTrue(all(p.exists() for p in (starred, queued, living, recent)))
        self.assertFalse(half.exists())
        self.assertEqual((r["plans"], r["keptPlans"]), (1, 2))  # (kept: starred and queued; living goes with its chat)


class ClaudeSettingTests(Home):
    def settings(self):
        return json.loads(self.shared_settings.read_text())

    def test_kept_from_cleaning_through_the_link_and_put_back(self):
        r = self.talpy()
        self.assertTrue(r["ok"], r)
        self.assertEqual(self.settings(), {"theme": "dark", "cleanupPeriodDays": 3650})
        self.assertTrue(self.work.joinpath("settings.json").is_symlink())  # (written through it)
        self.assertEqual(list(cleanup.load_changed(self.cache)), [str(self.shared_settings)])  # (once: one real file)
        cleanup.set_mode(self.home, self.cache, (), "claude", start=False)
        self.assertEqual(self.settings(), {"theme": "dark"})
        self.assertEqual(cleanup.load_changed(self.cache), {})

    def test_what_you_had_comes_back_and_what_you_changed_since_stays(self):
        self.shared_settings.write_text(json.dumps({"cleanupPeriodDays": 45}))
        self.talpy()
        cleanup.set_mode(self.home, self.cache, (), "claude", start=False)
        self.assertEqual(self.settings(), {"cleanupPeriodDays": 45})
        self.talpy()
        self.shared_settings.write_text(json.dumps({"cleanupPeriodDays": 60}))
        cleanup.set_mode(self.home, self.cache, (), "claude", start=False)
        self.assertEqual(self.settings(), {"cleanupPeriodDays": 60})

    def test_a_settings_file_it_made_goes_again_and_one_that_isnt_json_is_left(self):
        for name in ("work", "personal"):
            (self.home / (".claude-" + name) / "settings.json").unlink()
        (self.home / ".claude-personal/settings.json").write_text("{not json")
        r = self.talpy()
        self.assertFalse(r["ok"])
        self.assertIn("isn't a JSON object", r["message"])
        self.assertEqual(json.loads((self.work / "settings.json").read_text()), {"cleanupPeriodDays": 3650})
        self.assertEqual((self.home / ".claude-personal/settings.json").read_text(), "{not json")
        cleanup.set_mode(self.home, self.cache, (), "claude", start=False)
        self.assertFalse((self.work / "settings.json").exists())

    def test_uninstalling_puts_claudes_cleanup_back_and_leaves_an_unused_one_alone(self):
        import contextlib
        import io

        def uninstall():
            out, mask = io.StringIO(), os.umask(0o022)
            os.umask(mask)
            try:
                with mock.patch.object(cleanup, "hosts_to_visit", return_value=[]), contextlib.redirect_stdout(out):
                    cleanup.main(["--uninstall"])
            finally:
                os.umask(mask)
            return json.loads(out.getvalue())["message"]
        self.assertEqual(uninstall(), "")
        self.assertFalse(cleanup.setting_path(self.cache).exists())  # (never chosen: nothing written)
        self.talpy()
        self.assertEqual(uninstall(), "Claude Code cleans up old chats again")
        self.assertEqual(self.settings(), {"theme": "dark"})
        self.assertEqual(cleanup.load_setting(self.cache)["mode"], "claude")

    def test_pending_until_every_place_has_claudes_cleanup_back(self):
        self.talpy()
        cleanup.set_mode(self.home, self.cache, (), "claude", start=False)
        self.assertTrue(cleanup.load_setting(self.cache)["pending"])
        self.run_here()
        self.assertFalse(cleanup.load_setting(self.cache)["pending"])


class DueTests(Home):
    def test_due_once_a_day_and_when_the_setting_changes(self):
        stamp = self.cache / cs.CLEANUP_STAMP
        self.assertFalse(cs.cleanup_due(self.cache, time.time()))  # (never set: Claude Code's own cleanup)
        self.talpy()
        now = time.time()  # (as the status check asks: after the setting was written)
        self.assertTrue(cs.cleanup_due(self.cache, now))
        self.assertFalse(cs.cleanup_due(self.cache, now + 60))
        self.assertTrue(cs.cleanup_due(self.cache, now + DAY + 1))
        os.utime(str(stamp), (now - 10, now - 10))
        os.utime(str(cleanup.setting_path(self.cache)), (now, now))
        self.assertTrue(cs.cleanup_due(self.cache, now))  # (the setting changed since)
        cleanup.set_mode(self.home, self.cache, (), "claude", start=False)
        now = time.time()
        self.assertTrue(cs.cleanup_due(self.cache, now))  # (pending: put back on the hosts too)
        cleanup.change_setting(self.cache, lambda s: s.update(pending=False))
        now = time.time()
        self.assertFalse(cs.cleanup_due(self.cache, now))
        self.assertFalse(cs.cleanup_due(self.cache, now + DAY + 1))

    def test_one_copy_starts_it_without_waiting(self):
        self.talpy()
        with mock.patch.object(cs, "start_cleanup") as start, mock.patch.object(cs, "collect", return_value={
                "ok": True, "groups": [], "errors": []}), mock.patch.object(cs, "add_vscode"), \
                mock.patch.object(cs, "refresh_hooks"), mock.patch.object(cs, "upgrade_hook_settings"), \
                mock.patch("sys.stdout"):
            cs.main(["--recent", "0"])  # (a copy that doesn't notify: not this one)
            start.assert_not_called()
            cs.main(["--cleanup-check"])
            self.assertEqual(start.call_count, 1)
            cs.main(["--cleanup-check"])  # (not due again until tomorrow)
            self.assertEqual(start.call_count, 1)

    def test_the_run_is_one_at_a_time(self):
        self.talpy()
        with open(str(self.cache / cleanup.LOCK_FILE), "a") as held:
            import fcntl
            fcntl.flock(held, fcntl.LOCK_EX)
            self.assertEqual(cleanup.run(self.home, self.cache)["message"], "A cleanup is running already")


class HostsTests(Home):
    def test_the_hosts_a_run_goes_to(self):
        answers = self.cache / "hosts"
        answers.mkdir()
        for host, days in (("lab", 0.2), ("old-box", 3), ("docker:web", 0.1)):
            (answers / (host + ".json")).write_text("{}")
            aged(answers / (host + ".json"), days, self.now)
        self.assertEqual(cleanup.hosts_to_visit(self.cache, {}, "talpy", self.now), ["docker:web", "lab"])
        runs = {"": {"raised": True}, "old-box": {"raised": True}, "lab": {"raised": False}}
        self.assertEqual(cleanup.hosts_to_visit(self.cache, runs, "claude", self.now), ["old-box"])

    def test_a_hosts_stars_go_with_its_run(self):
        import remote
        cs.change_stars(self.cache, "chats", A, "lab")
        cs.change_stars(self.cache, "plans", "my-plan", "lab")
        cs.change_stars(self.cache, "chats", B)  # (this computer's)
        with mock.patch.object(remote, "host_answer", return_value={"ok": True}) as asked:
            cleanup.on_host("lab", self.cache, "talpy", 21)
        host, args = asked.call_args[0][:2]
        self.assertEqual((host, args), ("lab", ["--place", "21", "--keep-chats", A, "--keep-plans", "my-plan"]))
        self.assertEqual(asked.call_args[1], {"name": "cleanup.py", "also": ("accounts.py",)})

    def test_a_host_out_of_reach_keeps_what_it_did_before(self):
        import remote
        self.talpy()
        before = {"lab": {"ok": True, "at": 1, "chats": 3, "raised": True}}
        cs.write_json_atomic(self.cache / cleanup.RUNS_FILE, before)
        with mock.patch.object(cleanup, "hosts_to_visit", return_value=["lab"]), \
                mock.patch.object(remote, "host_answer", return_value={"ok": False, "reached": False, "message": "down"}):
            runs = cleanup.run(self.home, self.cache, now=self.now)["runs"]
        self.assertEqual((runs["lab"]["ok"], runs["lab"]["chats"], runs["lab"]["raised"], runs["lab"]["message"]),
                         (False, 3, True, "down"))


from test_remote import FakeSSH  # noqa: E402  (a stand-in ssh: runs the command here, in a made-up home)


class OverSSHTests(FakeSSH):
    """cleanup.py on a host: on python3's stdin there, after talpy_den.py and accounts.py."""

    def test_a_hosts_old_chats_go_its_starred_ones_stay_and_claudes_comes_back(self):
        now = time.time()
        folder = self.fake_home / ".claude/projects/-p"
        old, starred = folder / (A + ".jsonl"), folder / (S + ".jsonl")
        for path in (old, starred):
            path.write_text(json.dumps({"type": "user", "entrypoint": "cli"}) + "\n")
            aged(path, 40, now)
        plan = self.fake_home / ".claude/plans/old-plan.md"
        plan.parent.mkdir()
        plan.write_text("# Old\n")
        aged(plan, 40, now)
        here = cs.cache_dir(Path.home())
        cs.change_stars(here, "chats", S, "lab")
        r = cleanup.on_host("lab", here, "talpy", 30)
        self.assertTrue(r["ok"], r)
        self.assertEqual((r["chats"], r["plans"], r["keptChats"], r["raised"]), (1, 1, 1, True))
        self.assertFalse(old.exists())
        self.assertTrue(starred.exists())
        self.assertTrue((self.fake_home / ".local/share/Trash/files/old-plan.md").exists())
        settings = self.fake_home / ".claude/settings.json"
        self.assertEqual(json.loads(settings.read_text()), {"cleanupPeriodDays": 3650})
        r = cleanup.on_host("lab", here, "claude", 30)
        self.assertEqual((r["ok"], r["raised"]), (True, False))
        self.assertFalse(settings.exists())  # (Talpy Den had made it: it goes again)


if __name__ == "__main__":
    unittest.main()
