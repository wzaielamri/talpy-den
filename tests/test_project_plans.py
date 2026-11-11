"""Plans in projects (talpy_den.py, sharing.py, jump.py, week.py): Claude's
plansDirectory setting (the account's, a project's, its local one), each plan
listed once, the project a plan keeps once its chat is gone, and plans whose
project isn't known."""
import claude_guard  # noqa: F401  (first: no test runs the real claude)
import contextlib
import importlib.util
import io
import json
import os
import stat
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True  # keep __pycache__ out of the plasmoid package
CODE = Path(__file__).resolve().parent.parent / "package/contents/code"
sys.path.insert(0, str(CODE))
spec = importlib.util.spec_from_file_location("jump_project_plans", CODE / "jump.py")
jump = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jump)
cs = jump.cs
sharing = jump.sharing
spec = importlib.util.spec_from_file_location("week_project_plans", CODE / "week.py")
week = importlib.util.module_from_spec(spec)
spec.loader.exec_module(week)

from test_talpy_den import Fixture, iso, write  # noqa: E402

CHAT_A = "aaaaaaaa-1111-2222-3333-444444444444"
CHAT_B = "bbbbbbbb-1111-2222-3333-444444444444"
CHAT_C = "cccccccc-1111-2222-3333-444444444444"


class ProjectPlanFixture(Fixture):
    def setUp(self):
        super().setUp()
        self.app = self.home / "repos/app"
        (self.app / ".git").mkdir(parents=True)

    def chat(self, profile, folder, chat_id, slug=None, ago=600, cwd=None):
        """A chat on the profile (".claude-work") that started in folder (cwd: where it went since), with a plan's slug."""
        folder = str(folder)
        key = folder.replace("/", "-").replace(".", "-")
        path = self.home / profile / "projects" / key / f"{chat_id}.jsonl"
        t = self.now - ago
        extra = {"slug": slug} if slug else {}
        write(path, "".join(json.dumps(e) + "\n" for e in (
            {"type": "user", "cwd": folder, "sessionId": chat_id, "timestamp": iso(t),
             "message": {"role": "user", "content": "plan it"}, **extra},
            {"type": "assistant", "cwd": cwd or folder, "sessionId": chat_id, "timestamp": iso(t + 5),
             "message": {"id": "m1", "role": "assistant", "content": [{"type": "text", "text": "Here."}],
                         "stop_reason": "end_turn"}, **extra})))
        os.utime(path, (t + 5, t + 5))
        return path

    def plan(self, path, title, ago=4000):   # (Claude wrote it before its chat's last reply)
        write(path, f"# {title}\n\nSteps.\n")
        os.utime(path, (self.now - ago, self.now - ago))
        return path

    def plans(self, name, **kw):
        return self.group(self.collect(with_tokens=False, **kw), name)["plans"]

    def listed(self, name, **kw):
        return [(p["slug"], p["inProject"], p["cwd"]) for p in self.plans(name, **kw)]


class PlansDirectoryTests(ProjectPlanFixture):
    def test_the_accounts_setting_is_for_every_project(self):
        write(self.home / ".claude-work/settings.json", {"plansDirectory": "docs/plans"})
        self.chat(".claude-work", self.app, CHAT_A, "calm-red-owl")
        self.plan(self.app / "docs/plans/calm-red-owl.md", "The plan")
        # (personal's chats there put their plans in personal's own plans/)
        self.chat(".claude-personal", self.home / "repos/web", CHAT_B, "blue-fox", ago=900)
        self.plan(self.home / "repos/web/docs/plans/blue-fox.md", "Not one")
        work = self.plans("work")
        self.assertEqual([(p["slug"], p["inProject"], p["cwd"], p["cwdShort"], p["chatId"], p["shared"], p["key"])
                          for p in work],
                         [("calm-red-owl", True, str(self.app), "~/repos/app", CHAT_A, False,
                           ".claude-work/calm-red-owl/project/plan")])
        self.assertEqual(work[0]["title"], "The plan")
        self.assertEqual(self.plans("personal"), [])

    def test_the_projects_local_setting_wins_over_its_shared_one(self):
        write(self.app / ".claude/settings.json", {"plansDirectory": "shared-plans"})
        write(self.app / ".claude/settings.local.json", {"plansDirectory": "my-plans", "permissions": {}})
        self.chat(".claude-work", self.app, CHAT_A)
        self.plan(self.app / "shared-plans/one-plan.md", "Shared")
        self.plan(self.app / "my-plans/two-plan.md", "Mine")
        self.assertEqual(self.listed("work"), [("two-plan", True, str(self.app))])
        # (the file changed: read again)
        write(self.app / ".claude/settings.local.json", {"permissions": {}})
        self.assertEqual(self.listed("work"), [("one-plan", True, str(self.app))])
        # an empty one is no folder: the account's plans/
        write(self.app / ".claude/settings.local.json", {"plansDirectory": ""})
        self.assertEqual(self.listed("work"), [])

    def test_a_worktree_takes_the_local_setting_of_its_repositorys_main_folder(self):
        tree = self.app / ".claude/worktrees/fix"
        (self.app / ".git/worktrees/fix").mkdir(parents=True)
        write(self.app / ".git/worktrees/fix/commondir", "../..\n")
        write(tree / ".git", f"gitdir: {self.app}/.git/worktrees/fix\n")
        write(self.app / ".claude/settings.local.json", {"plansDirectory": "plans-here"})
        write(tree / ".claude/settings.local.json", {"plansDirectory": "not-read"})  # (Claude doesn't read it there)
        self.assertEqual(cs.canonical_git_root(str(tree)), str(self.app))
        self.assertEqual(cs.canonical_git_root(str(tree / "deep")), str(self.app))
        self.assertEqual(cs.canonical_git_root(str(self.home)), "")
        self.chat(".claude-work", tree, CHAT_A)
        self.plan(tree / "plans-here/fix-plan.md", "Fix")
        self.plan(tree / "not-read/other-plan.md", "Other")
        self.assertEqual(self.listed("work"), [("fix-plan", True, str(tree))])

    def test_a_folder_out_of_the_project_counts_as_none(self):
        app = str(self.app)
        self.assertEqual(cs.plans_dir_in(app, "docs/plans"), app + "/docs/plans")
        self.assertEqual(cs.plans_dir_in(app, app + "/abs"), app + "/abs")
        self.assertEqual(cs.plans_dir_in(app, "."), app)
        for value in ("../elsewhere", "/etc", "", "a\\b", None, 3, "~/../../x"):
            self.assertIsNone(cs.plans_dir_in(app, value), value)
        # (~ is a folder of that name in the project, as for Claude)
        self.assertEqual(cs.plans_dir_in(app, "~/plans"), app + "/~/plans")
        # a link inside the project that leads out of it
        (self.home / "outside").mkdir()
        os.symlink(self.home / "outside", self.app / "out")
        self.assertIsNone(cs.plans_dir_in(app, "out/plans"))
        write(self.app / ".claude/settings.json", {"plansDirectory": "out/plans"})
        self.chat(".claude-work", self.app, CHAT_A)
        self.plan(self.home / "outside/plans/away-plan.md", "Away")
        self.plan(self.app / ".claude/plans/kept-plan.md", "Kept")  # (its .claude/plans is still read)
        self.assertEqual(self.listed("work"), [("kept-plan", True, str(self.app))])

    def test_never_an_accounts_own_plans_folder(self):
        # (a chat in your home folder: its .claude/plans is ~/.claude's own)
        self.chat(".claude", self.home, CHAT_A, "home-plan")
        self.plan(self.home / ".claude/plans/home-plan.md", "Home")
        listed = self.plans("personal")
        self.assertEqual([(p["slug"], p["inProject"], p["key"]) for p in listed],
                         [("home-plan", False, ".claude/home-plan/plan")])

    def test_a_link_out_of_the_project_is_never_its_plan(self):
        # (a repo can ship them: a plan that's a link to a private key, its plans folder a link to an account's)
        write(self.home / ".ssh/id_test", "SECRETKEY\n")
        (self.app / ".claude/plans").mkdir(parents=True)
        os.symlink("../../../../.ssh/id_test", self.app / ".claude/plans/setup-steps.md")
        web = self.home / "repos/web"
        (web / ".claude").mkdir(parents=True)
        write(self.home / ".claude-work/CLAUDE.md", "# My rules\n")
        os.symlink("../../../.claude-work", web / ".claude/plans")
        self.chat(".claude-work", self.app, CHAT_A)
        self.chat(".claude-work", web, CHAT_B, ago=900)
        self.assertEqual(self.listed("work"), [])
        profiles = cs.discover_profiles(self.home)
        for slug in ("setup-steps", "CLAUDE"):
            self.assertEqual(cs.find_project_plan(profiles, slug, self.home, self.cache), (None, None))
            with self.assertRaises(ValueError):
                jump.Task("Carry out this plan", plan=slug).prompt(self.home, profiles)
        asked = sharing.delete(profiles, "plan", "CLAUDE", None, sharing.store_root(self.home), self.home)
        self.assertFalse(asked["ok"])
        self.assertTrue((self.home / ".claude-work/CLAUDE.md").is_file())
        # a link that stays in the project is followed
        os.unlink(web / ".claude/plans")
        self.plan(web / "notes/web-plan.md", "Web")
        os.symlink("../notes", web / ".claude/plans")
        self.assertEqual(self.listed("work"), [("web-plan", True, str(web))])


class ListedOnceTests(ProjectPlanFixture):
    def test_under_the_account_of_its_chat_else_of_the_newest_chat_there(self):
        write(self.app / ".claude/settings.json", {"plansDirectory": ".claude/plans"})
        self.chat(".claude-work", self.app, CHAT_A, "made-on-work", ago=900)
        self.chat(".claude-personal", self.app, CHAT_B, ago=60)   # (the newest chat there)
        self.plan(self.app / ".claude/plans/made-on-work.md", "Work's")
        self.plan(self.app / ".claude/plans/nobodys-plan.md", "Nobody's", ago=3000)
        r = self.collect(with_tokens=False)
        work, personal = self.group(r, "work")["plans"], self.group(r, "personal")["plans"]
        self.assertEqual([(p["slug"], p["chatId"]) for p in work], [("made-on-work", CHAT_A)])
        self.assertEqual([(p["slug"], p["chatId"], p["cwd"]) for p in personal], [("nobodys-plan", None, str(self.app))])
        # (once matched to its chat, it stays with that account)
        noted = json.loads((self.cache / "plan-projects.json").read_text())["plans"]
        self.assertEqual({k: noted["made-on-work"][k] for k in ("cwd", "project", "chat", "profile")},
                         {"cwd": str(self.app), "project": str(self.app), "chat": CHAT_A, "profile": ".claude-work"})
        self.assertEqual(stat.S_IMODE((self.cache / "plan-projects.json").stat().st_mode) & 0o077, 0)

    def test_starred_hidden_and_counted_once(self):
        self.chat(".claude-work", self.app, CHAT_A, "star-plan")
        (self.app / ".claude").mkdir()
        self.plan(self.app / ".claude/plans/star-plan.md", "Starred")
        self.plan(self.app / ".claude/plans/hid-plan.md", "Hidden", ago=5000)
        cs.change_stars(self.cache, "plans", "star-plan")
        cs.change_hidden(self.cache, "plans", add="hid-plan")
        r = self.collect(with_tokens=False, plans=0)   # (as the front ends ask: only the starred ones)
        work = self.group(r, "work")
        self.assertEqual(work["plans"], [])
        self.assertEqual([(p["slug"], p["key"], p["starred"]) for p in work["starredPlans"]],
                         [("star-plan", ".claude-work/star-plan/project/starred", True)])
        self.assertEqual(r["hiddenPlans"], 1)

    def test_found_by_the_search_and_listed_in_its_project(self):
        self.chat(".claude-work", self.app, CHAT_A, "found-plan")
        self.plan(self.app / ".claude/plans/found-plan.md", "Rollout of the parser")
        found = cs.find_chats(self.home, self.cache, [], "parser rollout")
        self.assertEqual([(p["slug"], p["inProject"], p["cwd"], p["profileDir"], p["key"]) for p in found["plans"]],
                         [("found-plan", True, str(self.app), ".claude-work", ".claude-work/found-plan/project/plan")])
        _ctx, items = week.project_items(self.home, self.cache, cs.discover_profiles(self.home), int(self.now * 1000))
        self.assertEqual([(p["slug"], p["inProject"], p["cwd"]) for p in items["plans"]], [("found-plan", True, str(self.app))])
        rows = week.projects([], int(self.now * 1000), self.home, items["plans"], (), items["accounts"])
        self.assertEqual([(r["path"], [p["slug"] for p in r["plans"]]) for r in rows], [(str(self.app), ["found-plan"])])


class RememberedProjectTests(ProjectPlanFixture):
    def test_a_plan_keeps_its_project_once_its_chat_is_gone(self):
        transcript = self.chat(".claude-work", self.app, CHAT_A, "kept-plan", cwd=str(self.app / "sub"))
        self.plan(self.home / ".claude-work/plans/kept-plan.md", "Kept")
        plan = self.plans("work")[0]
        self.assertEqual((plan["inProject"], plan["cwd"], plan["projectFolder"], plan["chatId"]),
                         (False, str(self.app / "sub"), str(self.app), CHAT_A))
        transcript.unlink()
        plan = self.plans("work")[0]
        self.assertEqual((plan["cwd"], plan["cwdShort"], plan["projectFolder"], plan["chatId"]),
                         (str(self.app / "sub"), "~/repos/app/sub", str(self.app), None))
        # deleting it forgets it
        cs.forget_deleted(self.cache, "plans", "kept-plan")
        self.assertNotIn("kept-plan", cs.load_plan_projects(self.cache))

    def test_a_plan_whose_project_isnt_known(self):
        self.plan(self.home / ".claude-work/plans/lone-plan.md", "Lone")
        plan = self.plans("work")[0]
        self.assertEqual((plan["cwd"], plan["cwdShort"], plan["projectFolder"], plan["chatId"]), ("", "", "", None))
        # the Projects tab lists it last, in its card of plans whose chat is gone
        _ctx, items = week.project_items(self.home, self.cache, cs.discover_profiles(self.home), int(self.now * 1000))
        rows = week.projects([], int(self.now * 1000), self.home, items["plans"], (), items["accounts"])
        self.assertEqual([(r["path"], [p["slug"] for p in r["plans"]]) for r in rows], [("", ["lone-plan"])])


class ActionTests(ProjectPlanFixture):
    def setUp(self):
        super().setUp()
        self.chat(".claude-work", self.app, CHAT_A, "act-plan")
        self.path = self.plan(self.app / ".claude/plans/act-plan.md", "Act on it")

    def test_found_by_its_slug(self):
        profiles = cs.discover_profiles(self.home)
        self.assertEqual(cs.find_plan(profiles, "act-plan", ".claude-work", self.home), self.path)
        self.assertIsNone(cs.find_plan(profiles, "act-plan", ".claude-work"))   # (without home: the accounts' only)
        self.assertEqual(cs.find_project_plan(profiles, "act-plan", self.home, self.cache), (self.path, str(self.app)))
        md = cs.plan_markdown(self.home, [], "act-plan", ".claude-work")
        self.assertEqual((md["ok"], md["title"], md["path"]), (True, "Act on it", str(self.path)))
        self.assertIn("Act on it", jump.Task("go", "act-plan", ".claude-work").prompt(self.home, profiles))
        # a chat's own plan, where its project keeps them
        ctx = cs.Context(home=self.home, profiles=profiles, plan_dirs=cs.PlanDirs(self.cache / "plan-dirs.json"))
        plan = cs.plan_of(profiles[0], "act-plan", ctx)
        self.assertEqual((plan["path"], plan["inProject"]), (str(self.path), True))
        self.assertIsNone(cs.plan_of(profiles[0], "act-plan"))

    def test_deleted_to_the_trash_and_never_shared(self):
        profiles = cs.discover_profiles(self.home)
        ok, message = sharing.plan_sharing(profiles, "act-plan", ".claude-work", True, home=self.home)
        self.assertFalse(ok)
        self.assertIn("every account has it", message)
        asked = sharing.delete(profiles, "plan", "act-plan", ".claude-work", sharing.store_root(self.home), self.home,
                               describe=True)
        self.assertEqual((asked["ok"], asked["accounts"], asked["folder"]), (True, [], "~/repos/app/.claude/plans"))
        self.assertEqual(asked["question"], "Delete the plan “Act on it” from ~/repos/app/.claude/plans? It goes to the Trash.")
        self.assertTrue(self.path.is_file())
        done = sharing.delete(profiles, "plan", "act-plan", ".claude-work", sharing.store_root(self.home), self.home)
        self.assertTrue(done["ok"], done)
        self.assertFalse(self.path.exists())
        self.assertTrue((self.home / ".local/share/Trash/files/act-plan.md").is_file())

    def test_deleting_takes_the_tasks_queued_to_carry_it_out(self):
        # (else at its time a task fails with "That plan isn't there any more", and waits till you cancel it)
        cache, at = cs.cache_dir(self.home), int(self.now * 1000) + 3600_000
        for host, plan in (("", "act-plan"), ("lab", "act-plan"), ("", "other-plan")):
            cs.change_queue(cache, add=cs.queue_entry(".claude-work", str(self.app), "", at, host, plan=plan))
        profiles, root = cs.discover_profiles(self.home), sharing.store_root(self.home)
        asked = sharing.delete(profiles, "plan", "act-plan", ".claude-work", root, self.home, describe=True)
        self.assertEqual(asked["question"], "Delete the plan “Act on it” from ~/repos/app/.claude/plans? It goes to the "
                                            "Trash. So does the task queued to carry it out.")
        self.assertTrue(sharing.delete(profiles, "plan", "act-plan", ".claude-work", root, self.home)["ok"])
        self.assertEqual([(t["host"], t["plan"]) for t in cs.load_queue(cache)], [("lab", "act-plan"), ("", "other-plan")])


class SameNameTests(ProjectPlanFixture):
    """An account's plan and a project's of the same name are one plan, the
    newer file: a chat wrote its plan in the account's plans/, its project
    got a plans folder, and Claude wrote it there."""

    def setUp(self):
        super().setUp()
        self.chat(".claude-work", self.app, CHAT_A, "twice-plan")
        self.old = self.plan(self.home / ".claude-work/plans/twice-plan.md", "Old version", ago=9000)
        self.new = self.plan(self.app / ".claude/plans/twice-plan.md", "New version", ago=4000)
        self.profiles = cs.discover_profiles(self.home)
        self.work = next(p for p in self.profiles if p.key == ".claude-work")

    def ctx(self):
        return cs.Context(home=self.home, profiles=self.profiles, plan_dirs=cs.PlanDirs(self.cache / "plan-dirs.json"))

    def test_listed_once_as_the_newer_file(self):
        self.assertEqual([(p["slug"], p["inProject"], p["title"]) for p in self.plans("work")],
                         [("twice-plan", True, "New version")])
        found = cs.find_chats(self.home, self.cache, [], "version")
        self.assertEqual([(p["slug"], p["inProject"]) for p in found["plans"]], [("twice-plan", True)])
        _ctx, items = week.project_items(self.home, self.cache, self.profiles, int(self.now * 1000))
        self.assertEqual([(p["slug"], p["inProject"]) for p in items["plans"]], [("twice-plan", True)])
        # the account's written later: that one
        os.utime(self.old, (self.now - 1000, self.now - 1000))
        self.assertEqual([(p["slug"], p["inProject"], p["title"]) for p in self.plans("work")],
                         [("twice-plan", False, "Old version")])

    def test_every_action_takes_the_file_its_line_shows(self):
        self.assertEqual(cs.find_plan(self.profiles, "twice-plan", ".claude-work", self.home), self.new)
        self.assertEqual(cs.find_plan(self.profiles, "twice-plan", ".claude-work"), self.old)   # (without home)
        self.assertEqual(cs.plan_of(self.work, "twice-plan", self.ctx())["path"], str(self.new))
        self.assertEqual(cs.plan_markdown(self.home, [], "twice-plan", ".claude-work")["title"], "New version")
        self.assertIn("New version", jump.Task("go", "twice-plan", ".claude-work").prompt(self.home, self.profiles))
        self.assertIn("every account has it",
                      sharing.plan_sharing(self.profiles, "twice-plan", ".claude-work", True, home=self.home)[1])
        web = self.home / "repos/web"
        web.mkdir(parents=True)
        self.chat(".claude-personal", web, CHAT_B, ago=60)
        asked = sharing.move_plan(self.profiles, self.home, "twice-plan", ".claude-work", folder=str(web), describe=True)
        self.assertEqual((asked["ok"], asked["target"]), (True, str(web / ".claude/plans/twice-plan.md")), asked)
        self.assertTrue(sharing.move_plan(self.profiles, self.home, "twice-plan", ".claude-work", folder=str(web),
                                          setting=False)["ok"])
        self.assertEqual((web / ".claude/plans/twice-plan.md").read_text(), "# New version\n\nSteps.\n")
        self.assertTrue(self.old.is_file())
        # the account's newer: it's the plan
        os.utime(self.old, (self.now - 10, self.now - 10))
        self.assertEqual(cs.find_plan(self.profiles, "twice-plan", ".claude-work", self.home), self.old)
        self.assertEqual(cs.plan_of(self.work, "twice-plan", self.ctx())["path"], str(self.old))

    def test_deleting_takes_the_older_file_along(self):
        root = sharing.store_root(self.home)
        asked = sharing.delete(self.profiles, "plan", "twice-plan", ".claude-work", root, self.home, describe=True)
        self.assertEqual(asked["question"], "Delete the plan “New version” from ~/repos/app/.claude/plans? It goes to "
                                            "the Trash. So does its older copy in ~/.claude-work/plans.")
        done = sharing.delete(self.profiles, "plan", "twice-plan", ".claude-work", root, self.home)
        self.assertTrue(done["ok"], done)
        self.assertFalse(self.new.exists())
        self.assertFalse(self.old.exists())

    def test_deleting_the_accounts_newer_one_takes_the_projects_along(self):
        # (else the project's older version would show again, as the plan)
        os.utime(self.old, (self.now - 10, self.now - 10))
        root = sharing.store_root(self.home)
        asked = sharing.delete(self.profiles, "plan", "twice-plan", ".claude-work", root, self.home, describe=True)
        self.assertEqual(asked["question"], "Delete the plan “Old version” on work? It goes to the Trash. "
                                            "So does its older copy in ~/repos/app/.claude/plans.")
        self.assertTrue(sharing.delete(self.profiles, "plan", "twice-plan", ".claude-work", root, self.home)["ok"])
        self.assertFalse(self.new.exists())
        self.assertEqual(self.plans("work"), [])
        self.assertEqual(self.plans("work"), [])


class CacheTests(ProjectPlanFixture):
    def test_a_quiet_project_is_looked_at_again_after_a_while(self):
        self.chat(".claude-work", self.app, CHAT_A, ago=3 * 3600)   # (no chat there lately)
        self.assertEqual(self.listed("work"), [])
        self.plan(self.app / ".claude/plans/late-plan.md", "Late")
        self.assertEqual(self.listed("work"), [])   # (not yet)
        cache = json.loads((self.cache / "plan-dirs.json").read_text())
        self.assertEqual(stat.S_IMODE((self.cache / "plan-dirs.json").stat().st_mode) & 0o077, 0)
        cache["projects"][str(self.app)][1] -= cs.PROJECT_RECHECK_S + 1
        write(self.cache / "plan-dirs.json", cache)
        self.assertEqual(self.listed("work"), [("late-plan", True, str(self.app))])

    def test_a_project_at_work_or_one_a_plan_just_went_to_at_once(self):
        self.chat(".claude-work", self.app, CHAT_A, ago=60)
        self.assertEqual(self.listed("work"), [])
        self.plan(self.app / ".claude/plans/new-plan.md", "New")
        self.assertEqual(self.listed("work"), [("new-plan", True, str(self.app))])
        web = self.home / "repos/web"
        self.chat(".claude-work", web, CHAT_B, ago=3 * 3600)
        self.assertEqual(len(self.listed("work")), 1)
        self.plan(web / ".claude/plans/moved-plan.md", "Moved")
        cs.change_plan_projects(self.cache, put={"moved-plan": {"cwd": str(web), "project": str(web), "chat": "",
                                                                "profile": ".claude-work", "at": int(time.time() * 1000)}})
        self.assertEqual([p[0] for p in self.listed("work")], ["new-plan", "moved-plan"])


class MoveTests(ProjectPlanFixture):
    """Move to project… and Move back (sharing.move_plan through jump.py)."""

    def setUp(self):
        super().setUp()
        self.chat(".claude-work", self.app, CHAT_A, "calm-red-owl")
        self.src = self.plan(self.home / ".claude-work/plans/calm-red-owl.md", "The plan")
        self.cache_root = cs.cache_dir(self.home)   # (what the actions use)

    def move(self, *args):
        with mock.patch.object(jump.Path, "home", return_value=self.home), \
                mock.patch.object(sys, "argv", ["jump.py", "--move-plan", "calm-red-owl", "--profile", ".claude-work", *args]), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            jump.main()
        return json.loads(out.getvalue())

    def test_asking_moves_nothing(self):
        asked = self.move("--describe")
        self.assertEqual({k: asked[k] for k in ("ok", "project", "default", "target", "setting", "exists", "account", "slug")},
                         {"ok": True, "project": str(self.app), "default": str(self.app), "slug": "calm-red-owl",
                          "target": str(self.app / ".claude/plans/calm-red-owl.md"), "setting": "", "exists": False,
                          "account": "work"})
        self.assertEqual(asked["choices"][0], {"path": str(self.app), "short": "~/repos/app"})
        self.assertIn("without it, Claude's chats there won't find the plan by its name", asked["question"])
        # (a drop on a project only asks: nothing moves until Move)
        self.assertTrue(self.src.is_file())
        self.assertFalse((self.app / ".claude").exists())

    def test_into_the_project_with_its_setting_kept_beside_the_others(self):
        write(self.app / ".claude/settings.local.json", {"permissions": {"allow": ["Bash(ls)"]}, "model": "opus"})
        write(self.app / ".claude/settings.json", {"model": "sonnet"})
        before = (self.app / ".claude/settings.json").read_text()
        moved = self.move()
        self.assertTrue(moved["ok"], moved)
        self.assertFalse(self.src.exists())
        self.assertEqual((self.app / ".claude/plans/calm-red-owl.md").read_text(), "# The plan\n\nSteps.\n")
        self.assertEqual(json.loads((self.app / ".claude/settings.local.json").read_text()),
                         {"permissions": {"allow": ["Bash(ls)"]}, "model": "opus", "plansDirectory": ".claude/plans"})
        self.assertEqual((self.app / ".claude/settings.json").read_text(), before)   # (never touched)
        # listed in its project now, with its chat, under the same account
        plan = self.plans("work")[0]
        self.assertEqual((plan["slug"], plan["inProject"], plan["cwd"], plan["chatId"], plan["path"]),
                         ("calm-red-owl", True, str(self.app), CHAT_A, str(self.app / ".claude/plans/calm-red-owl.md")))
        self.assertEqual(cs.load_plan_projects(self.cache_root)["calm-red-owl"]["project"], str(self.app))

    def test_without_the_setting_it_says_claude_wont_find_it(self):
        moved = self.move("--no-setting")
        self.assertTrue(moved["ok"], moved)
        self.assertFalse((self.app / ".claude/settings.local.json").exists())
        self.assertTrue((self.app / ".claude/plans/calm-red-owl.md").is_file())
        # the project's own plansDirectory: there, and nothing to add
        write(self.app / ".claude/settings.json", {"plansDirectory": "docs/plans"})
        src = self.plan(self.home / ".claude-work/plans/calm-red-owl.md", "Again")
        asked = self.move("--describe")
        self.assertEqual((asked["setting"], asked["target"]), ("project", str(self.app / "docs/plans/calm-red-owl.md")))
        self.assertNotIn("won't find", asked["question"])
        self.assertTrue(self.move()["ok"])
        self.assertFalse(src.exists())
        self.assertFalse((self.app / ".claude/settings.local.json").exists())

    def test_never_through_a_link_out_of_the_project(self):
        # (a repo can ship them: its .claude/plans a link to ~/.claude/rules, its settings.local.json to yours)
        user = self.home / ".claude-work/settings.json"
        write(user, {"model": "opus"})
        (self.home / ".claude-work/rules").mkdir()
        (self.app / ".claude").mkdir()
        os.symlink("../../../.claude-work/rules", self.app / ".claude/plans")
        os.symlink("../../../.claude-work/settings.json", self.app / ".claude/settings.local.json")
        for args in (("--describe",), ()):
            moved = self.move(*args)
            self.assertEqual((moved["ok"], moved["message"]),
                             (False, "~/repos/app/.claude/plans is a link to another folder: "
                                     "Talpy Den doesn't move a plan through a link"))
        os.unlink(self.app / ".claude/plans")
        moved = self.move()
        self.assertEqual((moved["ok"], moved["message"]),
                         (False, "~/repos/app/.claude/settings.local.json is a link to another file: "
                                 "Talpy Den doesn't change a setting through a link"))
        self.assertEqual((json.loads(user.read_text()), os.listdir(self.home / ".claude-work/rules")), ({"model": "opus"}, []))
        self.assertTrue(self.src.is_file())
        # (without the setting, into the project's own folder)
        self.assertTrue(self.move("--no-setting")["ok"])
        self.assertTrue((self.app / ".claude/plans/calm-red-owl.md").is_file())
        self.assertEqual(json.loads(user.read_text()), {"model": "opus"})

    def test_never_over_another_plan_of_that_name(self):
        other = self.plan(self.app / ".claude/plans/calm-red-owl.md", "Another one")
        cs.change_stars(self.cache_root, "plans", "calm-red-owl")
        cs.change_hidden(self.cache_root, "plans", add="calm-red-owl")
        task = lambda host: cs.queue_entry(".claude-work", str(self.app), "", 1, host=host, plan="calm-red-owl",
                                           plan_profile=".claude-work")
        cs.change_queue(self.cache_root, add=task(""))
        cs.change_queue(self.cache_root, add=task("lab"))  # (an SSH host's plan of that name: not this one)
        asked = self.move("--describe")
        self.assertEqual((asked["exists"], asked["free"]), (True, "calm-red-owl-2"))
        self.assertIn("keep both (calm-red-owl-2), or replace it?", asked["question"])
        refused = self.move()
        self.assertFalse(refused["ok"])
        self.assertTrue(self.src.is_file())
        self.assertEqual(other.read_text(), "# Another one\n\nSteps.\n")
        # keep both: it gets a free name, its star, its hiding, its project and its chat with it
        kept = self.move("--if-exists", "keep")
        self.assertEqual((kept["ok"], kept["slug"]), (True, "calm-red-owl-2"))
        self.assertEqual(other.read_text(), "# Another one\n\nSteps.\n")
        self.assertEqual((self.app / ".claude/plans/calm-red-owl-2.md").read_text(), "# The plan\n\nSteps.\n")
        self.assertIn("calm-red-owl-2", cs.starred_of(cs.load_stars(self.cache_root))["plans"])
        self.assertIn("calm-red-owl-2", cs.load_hidden(self.cache_root)["plans"])
        # a queued task that carries it out takes it by its new name
        self.assertEqual([(t["host"], t["plan"]) for t in cs.load_queue(self.cache_root)],
                         [("", "calm-red-owl-2"), ("lab", "calm-red-owl")])
        noted = cs.load_plan_projects(self.cache_root)["calm-red-owl-2"]
        self.assertEqual((noted["project"], noted["chat"]), (str(self.app), CHAT_A))

    def test_replacing_puts_the_other_in_the_trash(self):
        self.plan(self.app / ".claude/plans/calm-red-owl.md", "Another one")
        replaced = self.move("--if-exists", "replace")
        self.assertTrue(replaced["ok"], replaced)
        self.assertEqual((self.app / ".claude/plans/calm-red-owl.md").read_text(), "# The plan\n\nSteps.\n")
        self.assertEqual((self.home / ".local/share/Trash/files/calm-red-owl.md").read_text(), "# Another one\n\nSteps.\n")

    def test_git_says_whether_it_would_show_up(self):
        import shutil
        import subprocess
        if not shutil.which("git"):
            self.skipTest("no git")
        shutil.rmtree(self.app / ".git")
        self.assertIsNone(self.move("--describe")["git"])   # (not a repository)
        subprocess.run(["git", "init", "-q", str(self.app)], check=True)
        asked = self.move("--describe")
        self.assertTrue(asked["git"])
        self.assertIn("It would show up in git there.", asked["question"])
        write(self.app / ".gitignore", ".claude/plans/\n")
        asked = self.move("--describe")
        self.assertIs(asked["git"], False)
        self.assertNotIn("git", asked["question"])

    def test_a_shared_plan_leaves_every_account(self):
        (self.home / ".claude-personal/plans").mkdir(parents=True)
        os.link(self.src, self.home / ".claude-personal/plans/calm-red-owl.md")
        self.assertTrue(self.move()["ok"])
        self.assertFalse((self.home / ".claude-personal/plans/calm-red-owl.md").exists())
        self.assertEqual([p["slug"] for p in self.plans("personal")], [])

    def test_into_a_project_picked_and_back(self):
        web = self.home / "repos/web"
        web.mkdir(parents=True)
        self.chat(".claude-personal", web, CHAT_B, ago=60)
        asked = self.move("--describe")
        self.assertEqual([c["short"] for c in asked["choices"]], ["~/repos/app", "~/repos/web"])
        self.assertTrue(self.move("--into", str(web), "--no-setting")["ok"])
        moved = web / ".claude/plans/calm-red-owl.md"
        self.assertTrue(moved.is_file())
        self.assertFalse(self.move("--into", str(self.home / "nowhere"))["ok"])
        back = self.move("--back", "--describe")
        self.assertEqual((back["ok"], back["account"], back["lost"]), (True, "work", False))
        self.assertEqual(back["question"], "Move “The plan” back to work?")
        self.assertTrue(self.move("--back")["ok"])
        self.assertFalse(moved.exists())
        self.assertTrue(self.src.is_file())
        # (where the project names its plans folder, the chats there won't find it back on the account)
        write(self.app / ".claude/settings.local.json", {"plansDirectory": ".claude/plans"})
        self.assertTrue(self.move()["ok"])
        back = self.move("--back", "--describe")
        self.assertTrue(back["lost"])
        self.assertIn("they won't find it there", back["question"])

    def test_from_one_project_to_another(self):
        web = self.home / "repos/web"
        web.mkdir(parents=True)
        self.chat(".claude-personal", web, CHAT_B, ago=60)
        self.assertTrue(self.move("--no-setting")["ok"])
        in_app = self.app / ".claude/plans/calm-red-owl.md"
        asked = self.move("--into", str(web), "--describe")
        self.assertEqual((asked["ok"], asked["target"]), (True, str(web / ".claude/plans/calm-red-owl.md")))
        self.assertTrue(in_app.is_file())
        self.assertEqual(self.move("--into", str(self.app))["message"], "It's there already")
        moved = self.move("--into", str(web), "--no-setting")
        self.assertTrue(moved["ok"], moved)
        self.assertFalse(in_app.exists())
        self.assertTrue((web / ".claude/plans/calm-red-owl.md").is_file())

    def test_a_plan_made_in_the_home_folder_asks_which_project(self):
        # (its .claude is ~/.claude, an account's own: the plan would leave its account)
        self.chat(".claude-work", self.home, CHAT_B, "home-plan", ago=60)
        home_plan = self.plan(self.home / ".claude-work/plans/home-plan.md", "Planned at home")
        asked = sharing.move_plan(cs.discover_profiles(self.home), self.home, "home-plan", ".claude-work", describe=True)
        self.assertEqual((asked["ok"], asked["default"], [c["short"] for c in asked["choices"]]),
                         (True, "", ["~/repos/app"]))
        self.assertEqual(asked["question"], "Move “Planned at home” to which project?")
        moved = sharing.move_plan(cs.discover_profiles(self.home), self.home, "home-plan", ".claude-work",
                                  folder=str(self.home), setting=False)
        self.assertEqual((moved["ok"], moved["message"]), (False, "~/.claude/plans is an account's own plans folder"))
        self.assertTrue(home_plan.is_file())

    def test_wrong_asks(self):
        self.assertFalse(self.move("--into", "relative/folder")["ok"])
        with self.assertRaises(SystemExit):
            self.move("--into", str(self.app), "--back")
        with mock.patch.object(sys, "argv", ["jump.py", "--into", str(self.app), "--delete-plan", "x"]), \
                self.assertRaises(SystemExit):
            jump.main()
        self.assertTrue(self.src.is_file())


def compact(entry):
    return json.dumps(entry, separators=(",", ":"))   # (as Claude writes a transcript's lines)


class ClaudesProjectListTests(ProjectPlanFixture):
    """A project's plans folder is still read once Claude deleted its chats:
    Claude keeps the folder in its list of projects (.claude.json)."""

    def known(self, config, *folders):
        data = json.loads(config.read_text()) if config.is_file() else {}
        data["projects"] = {str(f): {"allowedTools": []} for f in folders}
        write(config, data)

    def test_read_once_its_chats_are_deleted(self):
        transcript = self.chat(".claude-work", self.app, CHAT_A)
        self.plan(self.app / ".claude/plans/still-here.md", "Still here")
        self.assertEqual(self.listed("work"), [("still-here", True, str(self.app))])
        transcript.unlink()   # (Claude deleted it: cleanupPeriodDays)
        self.assertEqual(self.listed("work"), [])
        self.known(self.home / ".claude-work/.claude.json", self.app, self.home / "repos/gone")
        self.assertEqual(self.listed("work"), [("still-here", True, str(self.app))])
        # the Projects tab has it in its project
        _ctx, items = week.project_items(self.home, self.cache, cs.discover_profiles(self.home), int(self.now * 1000))
        rows = week.projects([], int(self.now * 1000), self.home, items["plans"], (), items["accounts"])
        self.assertEqual([(r["path"], [p["slug"] for p in r["plans"]]) for r in rows], [(str(self.app), ["still-here"])])

    def test_under_the_account_that_ran_there(self):
        # (the default ~/.claude keeps its list in ~/.claude.json, with its account)
        self.known(self.home / ".claude.json", self.app)
        write(self.app / ".claude/settings.json", {"plansDirectory": "docs/plans"})
        self.plan(self.app / "docs/plans/home-listed.md", "Listed")
        self.assertEqual(self.listed("personal"), [("home-listed", True, str(self.app))])
        self.assertEqual(self.listed("work"), [])

    def test_never_claudes_own_folders(self):
        job = self.home / ".claude-work/jobs/j1/proj"
        self.known(self.home / ".claude-work/.claude.json", job)
        self.plan(job / ".claude/plans/job-plan.md", "A job's")
        self.assertEqual(self.listed("work"), [])


class WrittenPlanTests(ProjectPlanFixture):
    """A plan file a chat wrote itself (no slug, as a progress log it was
    asked to keep): its chat is the newest one that wrote it, found by the
    Projects tab, not one that only read it or quoted a call that wrote it."""

    def setUp(self):
        super().setUp()
        self.web = self.home / "repos/web"
        self.web.mkdir(parents=True)
        self.log = self.plan(self.home / ".claude-work/plans/progress-log.md", "Progress", ago=300)

    def calls(self, profile, folder, chat_id, *calls, **kw):
        """A chat in folder whose replies made the tool calls ((name, input, result)); path: its transcript."""
        folder, ago, dump = str(folder), kw.get("ago", 200), kw.get("dump", compact)
        path = kw.get("path") or self.home / profile / "projects" / folder.replace("/", "-").replace(".", "-") / (chat_id + ".jsonl")
        t = self.now - ago
        lines = [{"type": "user", "cwd": folder, "sessionId": chat_id, "timestamp": iso(t),
                  "message": {"role": "user", "content": "go on"}}]
        for i, (name, inp, result) in enumerate(calls):
            lines += [{"type": "assistant", "cwd": folder, "sessionId": chat_id, "timestamp": iso(t + 1),
                       "message": {"id": "m%d" % i, "role": "assistant",
                                   "content": [{"type": "tool_use", "id": "t%d" % i, "name": name, "input": inp}]}},
                      {"type": "user", "cwd": folder, "sessionId": chat_id, "timestamp": iso(t + 2),
                       "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t%d" % i,
                                                                "content": result}]}}]
        write(path, "".join(dump(e) + "\n" for e in lines))
        os.utime(path, (t + 2, t + 2))
        return path

    def projects_tab(self):
        ctx, items = week.project_items(self.home, self.cache, cs.discover_profiles(self.home), int(self.now * 1000))
        for saved in (ctx.links, ctx.slugs, ctx.chats, ctx.plan_dirs, ctx.plan_projects, ctx.plan_writes):
            saved.save()
        return {p["slug"]: p for p in items["plans"]}

    def test_the_chat_that_wrote_it(self):
        log = str(self.log)
        self.calls(".claude-work", self.app, CHAT_A,
                   ("Write", {"file_path": log, "content": "# Progress\n"}, "File created successfully at: " + log), ago=400)
        self.calls(".claude-work", self.web, CHAT_B,
                   ("Read", {"file_path": log}, "# Progress"),
                   ("Bash", {"command": "cat " + log, "description": "Show it"}, "# Progress"),
                   ("Bash", {"command": "grep -rh progress-log ~/.claude-work/projects"},   # (a call quoted: escaped)
                    compact({"name": "Bash", "input": {"command": "echo done >> " + log}})), ago=100)
        # (the status check doesn't look for it)
        self.assertEqual([(p["cwd"], p["chatId"]) for p in self.plans("work")], [("", None)])
        plan = self.projects_tab()["progress-log"]
        self.assertEqual((plan["cwd"], plan["projectFolder"], plan["chatId"], plan["chatProfileDir"]),
                         (str(self.app), str(self.app), CHAT_A, ".claude-work"))
        rows = week.projects([], int(self.now * 1000), self.home, [plan], (), {})
        self.assertEqual([r["path"] for r in rows], [str(self.app)])
        # noted: the status check has it too, and it keeps its project once the chat is gone
        self.assertEqual([(p["cwd"], p["chatId"]) for p in self.plans("work")], [(str(self.app), CHAT_A)])
        next(self.home.glob(".claude-work/projects/*/%s.jsonl" % CHAT_A)).unlink()
        self.assertEqual([(p["cwd"], p["chatId"]) for p in self.plans("work")], [(str(self.app), None)])

    def test_the_newest_chat_that_wrote_it(self):
        self.calls(".claude-work", self.app, CHAT_A, ("Write", {"file_path": str(self.log), "content": "1"}, "ok"), ago=400)
        self.calls(".claude-personal", self.web, CHAT_B,
                   ("Edit", {"replace_all": False, "file_path": str(self.log), "old_string": "1", "new_string": "2"}, "ok"),
                   ago=100)
        plan = self.projects_tab()["progress-log"]
        self.assertEqual((plan["cwd"], plan["chatId"], plan["chatProfileDir"]), (str(self.web), CHAT_B, ".claude-personal"))

    def test_a_shell_command_that_writes_it(self):
        names = ("a-log", "b-log", "c-log", "d-log", "e-log")
        for name in names:
            self.plan(self.home / ".claude-work/plans" / (name + ".md"), name, ago=300)
        os.symlink(self.home / ".claude-work", self.home / "alias")
        commands = ("echo one >> ~/.claude-work/plans/a-log.md",
                    'printf x | tee -a "$HOME/.claude-work/plans/b-log.md" > /dev/null',
                    "cat > '%s/alias/plans/c-log.md' <<'EOF'\n# C\nEOF" % self.home,  # (through a link)
                    "date>>${HOME}/.claude-work/plans/d-log.md")
        for n, command in enumerate(commands):
            self.calls(".claude-work", self.app, "%08d-1111-2222-3333-444444444444" % n,
                       ("Bash", {"command": command, "description": "Note it"}, ""), ago=100 + n)
        # (a transcript written with spaces after its colons)
        self.calls(".claude-work", self.web, CHAT_C, ("Bash", {"command": "echo 5 >> ~/.claude-work/plans/e-log.md"}, ""),
                   dump=json.dumps)
        # (only named, not written)
        self.plan(self.home / ".claude-work/plans/f-log.md", "f", ago=300)
        self.calls(".claude-work", self.web, CHAT_B, ("Bash", {"command": "wc -l ~/.claude-work/plans/f-log.md"}, "1"))
        found = self.projects_tab()
        self.assertEqual([found[name]["cwd"] for name in names + ("f-log",)], [str(self.app)] * 4 + [str(self.web), ""])

    def test_written_by_its_subagent(self):
        main = self.calls(".claude-work", self.app, CHAT_A, ("Task", {"prompt": "Append to " + str(self.log)}, "Done"))
        self.calls(".claude-work", self.app, CHAT_A, ("Bash", {"command": "echo step >> " + str(self.log)}, ""),
                   path=main.parent / CHAT_A / "subagents" / "agent-a1.jsonl")
        plan = self.projects_tab()["progress-log"]
        self.assertEqual((plan["cwd"], plan["chatId"]), (str(self.app), CHAT_A))

    def test_read_once_then_where_it_grew(self):
        transcript = self.calls(".claude-work", self.app, CHAT_A, ("Read", {"file_path": "/etc/hosts"}, "x"))
        line = compact({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Write", "input": {"file_path": str(self.log), "content": "x"}}]}}) + "\n"
        cut = line.index("/plans/") + 3   # (Claude was writing it: the call cut in its file's name)
        writes = cs.PlanWrites(self.cache / "plan-writes.json", self.home)
        with open(str(transcript), "a") as f:
            f.write(line[:cut])
        self.assertEqual(writes.paths(transcript, transcript.stat()), [])
        with open(str(transcript), "a") as f:
            f.write(line[cut:])
        self.assertEqual(writes.paths(transcript, transcript.stat()), [str(self.log)])
        writes.save()
        again = cs.PlanWrites(self.cache / "plan-writes.json", self.home)
        with mock.patch.object(cs, "plan_writes", side_effect=AssertionError("read again")):
            self.assertEqual(again.paths(transcript, transcript.stat()), [str(self.log)])

    def test_a_long_history_is_read_a_part_at_a_time(self):
        self.calls(".claude-work", self.app, CHAT_A, ("Write", {"file_path": str(self.log), "content": "x" * 5000}, "ok"), ago=400)
        self.calls(".claude-work", self.web, CHAT_B, ("Read", {"file_path": "/etc/hosts"}, "y" * 5000), ago=100)
        with mock.patch.object(cs, "PLAN_WRITES_BUDGET", 1000):
            self.assertIsNone(self.projects_tab()["progress-log"]["chatId"])   # (the newest chat read, then no more)
            self.assertEqual(self.projects_tab()["progress-log"]["chatId"], CHAT_A)


if __name__ == "__main__":
    unittest.main()
