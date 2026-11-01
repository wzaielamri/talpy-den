"""Plans in projects (talpy_den.py, sharing.py, jump.py, week.py): Claude's
plansDirectory setting (the account's, a project's, its local one), each plan
listed once, the project a plan keeps once its chat is gone, and plans whose
project isn't known."""
import importlib.util
import json
import os
import stat
import sys
import time
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
