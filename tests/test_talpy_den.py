import contextlib
import importlib.util
import io
import json
import ast
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True  # keep __pycache__ out of the plasmoid package
ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("talpy_den", ROOT / "package/contents/code/talpy_den.py")
cs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cs)

PID = os.getpid()
PROC_START = cs.proc_start_time(PID)
DEAD_PID = 4194304 + 4242  # above the kernel's pid_max ceiling


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data))


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z")


def session(sid, **kw):
    return {"pid": PID, "procStart": PROC_START, "sessionId": sid, "cwd": "/tmp/proj-" + sid,
            "kind": "interactive", "status": "idle", "statusUpdatedAt": 1000, **kw}


def vscode_link_params(link):
    """What the extension that handles a vscode:// link gets: VS Code decodes
    the query once (its URI.parse), then the extension's URLSearchParams does."""
    import re
    from urllib.parse import unquote, unquote_plus
    query = re.sub(r"(%[0-9A-Za-z]{2})+", lambda m: unquote(m.group(0)), link.partition("?")[2])
    return {unquote_plus(k): unquote_plus(v) for k, _, v in (p.partition("=") for p in query.split("&") if p)}


def assistant(msg_id, ts, output, model="claude-opus-5-5"):
    return json.dumps({"type": "assistant", "timestamp": iso(ts), "requestId": "req_" + msg_id,
                       "message": {"id": msg_id, "model": model, "usage": {
                           "input_tokens": 2, "output_tokens": output,
                           "cache_read_input_tokens": 100, "cache_creation_input_tokens": 10}}})


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.cache = Path(self.tmp.name) / "cache"
        self.now = time.time()
        h = self.home
        # ~/.claude: default dir whose .claude.json lacks the account (Claude
        # Code keeps it in ~/.claude.json for the default dir)
        write(h / ".claude/.claude.json", {"machineID": "x"})
        write(h / ".claude.json", {"oauthAccount": {"accountUuid": "acct-pro", "organizationType": "claude_pro"}})
        write(h / ".claude/sessions/1.json", session("vscode", entrypoint="claude-vscode", status="busy"))
        write(h / ".claude-work/sessions/9.json", session("spare", kind="bg", spare=True))
        # ~/.claude-personal: same account as ~/.claude
        write(h / ".claude-personal/.profile-name", "personal\n")
        write(h / ".claude-personal/.claude.json", {"oauthAccount": {"accountUuid": "acct-pro", "organizationType": "claude_pro"}})
        write(h / ".claude-personal/sessions/2.json", session("perso-idle", statusUpdatedAt=2000))
        # ~/.claude-work: Team account
        w = h / ".claude-work"
        write(w / ".profile-name", "work")
        write(w / ".claude.json", {"oauthAccount": {"accountUuid": "acct-team", "organizationType": "claude_team"}})
        write(w / "sessions/10.json", session("waiting", status="waiting", waitingFor="Bash"))
        write(w / "sessions/11.json", session("busy", status="busy"))
        write(w / "sessions/12.json", session("dead", pid=DEAD_PID))
        write(w / "sessions/13.json", session("reused", procStart="1"))
        write(w / "sessions/14.json", session("spare", spare=True))
        write(w / "sessions/15.json", session("parked", parkedJobId="job1"))
        write(w / "sessions/16.json", session("bgdone", kind="bg", jobId="job2"))
        write(w / "jobs/job2/state.json", {"state": "done", "detail": "All tests\n pass."})
        write(w / "sessions/17.json", session("bgworking", kind="bg", status="busy", jobId="job3"))
        write(w / "jobs/job3/state.json", {"state": "working", "detail": "old question"})
        # Real case: record still "blocked" from an answered question while busy
        write(w / "sessions/18.json", session("bgstale", kind="bg", status="busy", jobId="job4"))
        write(w / "jobs/job4/state.json", {"state": "blocked", "tempo": "active", "detail": "my last reply"})
        # Real case: background job waiting for a permission
        write(w / "sessions/19.json", session("bgperm", kind="bg", status="waiting",
                                              waitingFor="permission prompt", jobId="job5"))
        write(w / "jobs/job5/state.json", {"state": "blocked", "tempo": "blocked",
                                           "needs": "approve Write: /tmp/x", "detail": "my last reply"})
        # Interactive session with the user's own /effort dialog open
        write(w / "sessions/20.json", session("dialog", status="waiting", waitingFor="dialog open"))
        write(w / "sessions/notjson.json", "{broken")
        # Unrelated dir without sessions/projects is ignored
        (h / ".claude-backup").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def collect(self, **kw):
        return cs.collect(self.home, self.cache, now=kw.pop("now", self.now), **kw)

    def group(self, result, name):
        return next(g for g in result["groups"] if g["name"] == name)


class SessionTests(Fixture):
    def test_groups_by_account(self):
        r = self.collect(with_tokens=False)
        self.assertEqual([(g["title"], g["profiles"]) for g in r["groups"]],
                         [("personal · Pro", ["main", "personal"]), ("work · Team", ["work"])])

    def test_lone_default_dir_named_after_account(self):
        h = Path(self.tmp.name) / "lone"
        write(h / ".claude/sessions/1.json", session("solo"))
        write(h / ".claude.json", {"oauthAccount": {"accountUuid": "a", "organizationType": "claude_max",
                                                     "displayName": "Ada"}})
        (h / ".claude-backup").mkdir()  # not a profile: no sessions/projects

        def title():
            groups = cs.collect(h, self.cache, with_tokens=False, now=self.now)["groups"]
            return [(g["title"], g["profiles"]) for g in groups]
        self.assertEqual(title(), [("Ada · Max", ["Ada"])])
        write(h / ".claude.json", {"oauthAccount": {"accountUuid": "a", "organizationType": "claude_max"}})
        self.assertEqual(title(), [("Claude · Max", ["Claude"])])
        write(h / ".claude/.profile-name", "mine")
        self.assertEqual(title(), [("mine · Max", ["mine"])])

    def test_parked_and_finished_jobs_listed(self):
        w = self.home / ".claude-work"
        now = self.now
        write(w / "jobs/parkedq/state.json", {"state": "blocked", "tempo": "blocked", "needs": "Which DB should I use?",
                                               "name": "db choice", "cwd": "/w/db", "sessionId": "s-parked",
                                               "updatedAt": iso(now - 7200)})
        write(w / "jobs/finished/state.json", {"state": "done", "tempo": "idle", "detail": "Report written.",
                                                "intent": "write report", "cwd": "/w/r", "updatedAt": iso(now - 3600)})
        write(w / "jobs/ancient/state.json", {"state": "done", "tempo": "idle", "updatedAt": iso(now - 3 * 86400)})
        write(w / "sessions/30.json", session("daemon-proc", kind="daemon"))
        work = self.group(self.collect(with_tokens=False), "work")
        by_id = {s["sessionId"]: s for s in work["sessions"]}
        self.assertEqual((by_id["s-parked"]["state"], by_id["s-parked"]["detail"], by_id["s-parked"]["pid"]),
                         ("waiting", "Which DB should I use?", None))
        self.assertEqual(by_id["s-parked"]["name"], "db choice")
        self.assertEqual((by_id["finished"]["state"], by_id["finished"]["name"], by_id["finished"]["detail"]),
                         ("done", "write report", "Report written."))
        self.assertNotIn("ancient", by_id)
        self.assertNotIn("daemon-proc", by_id)
        self.assertNotIn("job4", by_id)  # live sessions' jobs aren't listed twice
        none = self.group(self.collect(with_tokens=False, keep_done_hours=0), "work")
        self.assertNotIn("finished", {s["sessionId"] for s in none["sessions"]})

    def test_finished_history_alone_is_not_running(self):
        for f in (self.home / ".claude-work/sessions").glob("*.json"):
            f.unlink()
        for f in (self.home / ".claude/sessions").glob("*.json"):
            f.unlink()
        for f in (self.home / ".claude-personal/sessions").glob("*.json"):
            f.unlink()
        for d in (self.home / ".claude-work/jobs").iterdir():
            write(d / "state.json", {"state": "done", "tempo": "idle", "updatedAt": iso(self.now - 60)})
        r = self.collect(with_tokens=False)
        self.assertEqual(r["counts"]["done"], 4)  # job2..job5
        self.assertEqual(r["overall"], "none")

    def test_no_raw_account_ids_in_output(self):
        r = self.collect(with_tokens=False)
        text = json.dumps(r)
        self.assertNotIn("acct-pro", text)
        self.assertNotIn("acct-team", text)
        self.assertEqual(len({g["id"] for g in r["groups"]}), 2)

    def test_cache_dir_is_private(self):
        self.cache.mkdir(mode=0o755)
        self.collect(with_tokens=False)
        self.assertEqual(self.cache.stat().st_mode & 0o777, 0o700)

    def test_session_states_and_filtering(self):
        r = self.collect(with_tokens=False)
        work = self.group(r, "work")
        states = {s["sessionId"]: s["state"] for s in work["sessions"]}
        self.assertEqual(states, {"waiting": "waiting", "busy": "working", "bgworking": "working", "bgdone": "done",
                                  "bgstale": "working", "bgperm": "waiting", "dialog": "idle"})
        # the ones that need you first (asking longest first), the others in the
        # order they started, the newest last (a row and its pet don't move
        # while the chat works, idles or finishes)
        rows = work["sessions"]
        asking = [s for s in rows if s["state"] == "waiting"]
        self.assertEqual(rows[:len(asking)], asking)
        self.assertEqual([s["since"] or 0 for s in asking], sorted(s["since"] or 0 for s in asking))
        started = [s.get("startedAt") or s["since"] or 0 for s in rows[len(asking):]]
        self.assertEqual(started, sorted(started))
        self.assertEqual({s["state"] for s in rows[:2]}, {"waiting"})
        by_id = {s["sessionId"]: s for s in work["sessions"]}
        self.assertEqual((by_id["waiting"]["waitingFor"], by_id["waiting"]["reason"]), ("Bash", "Bash"))
        self.assertEqual((by_id["bgperm"]["reason"], by_id["bgperm"]["detail"]), ("permission", "approve Write: /tmp/x"))
        self.assertEqual((by_id["dialog"]["reason"], by_id["dialog"]["waitingFor"]), ("", "dialog open"))
        self.assertEqual(by_id["bgdone"]["detail"], "All tests pass.")
        self.assertEqual(by_id["bgworking"]["detail"], "")
        self.assertEqual(by_id["bgstale"]["detail"], "")
        self.assertEqual(r["counts"], {"waiting": 2, "working": 4, "idle": 2, "done": 1})
        self.assertEqual(r["overall"], "waiting")
        self.assertEqual(r["errors"], [])

    def test_rows_have_unique_keys(self):
        write(self.home / ".claude-personal/sessions/40.json", session("busy", status="idle"))   # same id twice
        r = self.collect(with_tokens=False)
        keys = [s["key"] for g in r["groups"] for s in g["sessions"]]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertIn(".claude-personal/busy/live", keys)
        self.assertIn(".claude-work/busy/live", keys)

    def test_overall_without_waiting(self):
        os.remove(self.home / ".claude-work/sessions/10.json")
        os.remove(self.home / ".claude-work/sessions/19.json")
        os.remove(self.home / ".claude-work/jobs/job5/state.json")  # else it's parked, still waiting
        self.assertEqual(self.collect(with_tokens=False)["overall"], "working")

    def test_liveness(self):
        self.assertTrue(cs.is_alive({"pid": PID, "procStart": PROC_START}))
        self.assertTrue(cs.is_alive({"pid": PID}))
        self.assertFalse(cs.is_alive({"pid": PID, "procStart": "1"}))
        self.assertFalse(cs.is_alive({"pid": DEAD_PID}))
        self.assertFalse(cs.is_alive({"pid": "12"}))

    def test_short_path(self):
        self.assertEqual(cs.short_path("/h/u", "/h/u"), "~")
        self.assertEqual(cs.short_path("/h/u/repos/x", "/h/u"), "~/repos/x")
        self.assertEqual(cs.short_path("/h/u/a/b/c/d", "/h/u"), "…/c/d")


class StateMappingTests(unittest.TestCase):
    """Cases seen on real sessions; expectations follow Claude Code 2.1."""

    def state(self, entry, job=None):
        return cs.session_state(entry, job)

    def test_interactive(self):
        self.assertEqual(self.state({"status": "busy"}), "working")
        self.assertEqual(self.state({"status": "idle"}), "idle")
        self.assertEqual(self.state({"status": "shell"}), "working")  # background shell after the turn
        self.assertEqual(self.state({"status": "waiting", "waitingFor": "permission prompt"}), "waiting")
        self.assertEqual(self.state({"status": "waiting", "waitingFor": "input needed"}), "waiting")
        self.assertEqual(self.state({"status": "waiting"}), "waiting")

    def test_own_dialog_is_not_waiting(self):
        # /effort, /model, ... opened by the user
        self.assertEqual(self.state({"status": "waiting", "waitingFor": "dialog open"}), "idle")

    def test_background_job_live_status_beats_stale_record(self):
        # job record still says blocked after the user answered; session is busy
        self.assertEqual(self.state({"status": "busy"}, {"state": "blocked", "tempo": "active"}), "working")
        self.assertEqual(self.state({"status": "idle"}, {"state": "blocked", "tempo": "active"}), "working")

    def test_background_job_needs_input(self):
        self.assertEqual(self.state({"status": "waiting", "waitingFor": "permission prompt"},
                                    {"state": "blocked", "tempo": "blocked"}), "waiting")
        self.assertEqual(self.state({"status": "idle"}, {"state": "blocked", "tempo": "blocked"}), "waiting")

    def test_background_job_not_started(self):
        # dispatched from the agent view without a prompt
        job = {"state": "blocked", "tempo": "blocked", "needs": cs.NOT_STARTED}
        self.assertEqual(self.state({"status": "idle"}, job), "idle")

    def test_background_job_finished(self):
        self.assertEqual(self.state({"status": "idle"}, {"state": "done", "tempo": "idle"}), "done")
        self.assertEqual(self.state({"status": "idle"}, {"state": "failed", "tempo": "idle"}), "done")
        self.assertEqual(self.state({"status": "idle"}, {"state": "done", "tempo": "active"}), "working")
        self.assertEqual(self.state({"status": "idle"}, {"state": "done", "tempo": "idle", "routine": {}}), "working")

    def test_background_turn_over_but_record_says_working(self):
        # Stopped (while it thought: nothing written; mid-reply: "[Request interrupted by user]"), or a
        # turn whose summary says it goes on: the state stays "working", the tempo went idle
        idle = {"status": "idle"}
        self.assertEqual(self.state(idle, {"state": "working", "tempo": "idle", "inFlight": {"tasks": 0, "queued": 0}}), "idle")
        self.assertEqual(self.state(idle, {"state": "working", "tempo": "idle", "inFlight": {"tasks": 0, "queued": 1}}), "idle")
        self.assertEqual(self.state(idle, {"state": "working", "tempo": "idle"}), "idle")
        self.assertEqual(self.state(idle, {"state": "blocked", "tempo": "idle"}), "idle")

    def test_background_still_at_work_with_an_idle_tempo_or_status(self):
        idle = {"status": "idle"}
        self.assertEqual(self.state(idle, {"state": "working", "tempo": "active"}), "working")  # start-up, a wake
        self.assertEqual(self.state({"status": "busy"}, {"state": "working", "tempo": "idle"}), "working")  # Stop hooks
        self.assertEqual(self.state({"status": "shell"}, {"state": "working", "tempo": "idle",
                                                          "inFlight": {"tasks": 1, "kinds": ["monitor"]}}), "working")
        self.assertEqual(self.state(idle, {"state": "working"}), "working")  # no tempo: an older Claude Code
        self.assertEqual(self.state(idle, {"state": "working", "tempo": "idle", "routine": {}}), "working")
        # a background task just ended: idle for 15-100 ms before its notification wakes the session
        self.assertEqual(self.state(idle, {"state": "working", "tempo": "idle",
                                           "inFlight": {"tasks": 1, "queued": 0, "kinds": ["local_bash"]}}), "working")


class ParkedJobTests(unittest.TestCase):
    """Job records whose session process is gone (`claude agents --all`)."""

    NOW = 1_800_000_000_000
    DAY = 24 * 3600_000

    def parked(self, job, present=False, keep=DAY):
        return cs.parked_job_state(job, present, self.NOW, keep)

    def iso(self, ms_ago):
        return iso((self.NOW - ms_ago) / 1000)

    def test_blocked_job_still_needs_you(self):
        job = {"state": "blocked", "tempo": "blocked", "needs": "approve Bash", "updatedAt": self.iso(9 * self.DAY)}
        self.assertEqual(self.parked(job), ("waiting", ""))

    def test_finished_jobs_kept_for_a_day(self):
        self.assertEqual(self.parked({"state": "done", "tempo": "idle", "updatedAt": self.iso(3600_000)}), ("done", ""))
        self.assertEqual(self.parked({"state": "failed", "tempo": "idle", "updatedAt": self.iso(60_000)}), ("done", "failed"))
        self.assertIsNone(self.parked({"state": "done", "tempo": "idle", "updatedAt": self.iso(25 * 3600_000)}))
        self.assertIsNone(self.parked({"state": "done", "tempo": "idle", "updatedAt": self.iso(60_000)}, keep=0))

    def test_died_mid_task(self):
        job = {"state": "working", "tempo": "active", "createdAt": self.iso(600_000), "updatedAt": self.iso(300_000)}
        self.assertEqual(self.parked(job), ("done", "failed"))
        self.assertEqual(self.parked(job, present=True), ("working", ""))  # daemon still has it
        self.assertIsNone(self.parked(job, keep=0))
        fresh = {**job, "createdAt": self.iso(1000)}
        self.assertEqual(self.parked(fresh), ("working", ""))  # just dispatched

    def test_answered_then_died(self):
        # state "blocked" is stale once you answered (tempo "active" again)
        job = {"state": "blocked", "tempo": "active", "needs": "Which database?",
               "createdAt": self.iso(600_000), "updatedAt": self.iso(300_000)}
        self.assertEqual(self.parked(job), ("done", "failed"))
        self.assertIsNone(self.parked({**job, "updatedAt": self.iso(30 * self.DAY)}))
        self.assertEqual(self.parked(job, present=True), ("working", ""))

    def test_turn_over_then_retired(self):
        # stopped (or its summary said it goes on), then the service let its process go: settled
        job = {"state": "working", "tempo": "idle", "createdAt": self.iso(600_000), "updatedAt": self.iso(300_000)}
        self.assertEqual(self.parked(job), ("done", ""))
        self.assertIsNone(self.parked(job, keep=0))
        self.assertEqual(self.parked(job, present=True), ("working", ""))

    def test_not_started_hidden(self):
        self.assertIsNone(self.parked({"state": "blocked", "tempo": "blocked", "needs": cs.NOT_STARTED}))


class LimitTests(Fixture):
    def test_a_fetch_under_any_folder_of_the_account_says_its_on_its_way(self):
        # (~/.claude and ~/.claude-personal are one account: the fetch is claimed under the one that fetches)
        write(self.cache / "usage-check.json", {"started": {str((self.home / ".claude-personal").resolve()): 1234}})
        g = next(g for g in self.collect(with_tokens=False)["groups"] if ".claude-personal" in g["profileKeys"])
        self.assertEqual((len(g["profileKeys"]), g["usageFetchAt"]), (2, 1234))

    def test_unknown_values_name_no_front_end(self):
        text = cs.unknown_values_text({("status", "napping"): "2.1.400"})
        self.assertEqual(text, "Claude Code 2.1.400 writes something Talpy Den doesn't know yet (status \"napping\"): "
                               "some chats may show the wrong state until Talpy Den is updated.")

    def snapshot(self, profile, sid, data, age=0):
        path = self.cache / "statusline" / profile / f"{sid}.json"
        write(path, data)
        os.utime(path, (self.now - age, self.now - age))

    def test_limits_and_context(self):
        self.snapshot(".claude-work", "busy", {
            "session_id": "busy",
            "model": {"display_name": "Opus 5.5"},
            "effort": {"level": "max"},
            "context_window": {"used_percentage": 34.4},
            "cost": {"total_cost_usd": 1.25},
            "rate_limits": {
                "seven_day": {"used_percentage": 50, "resets_at": self.now - 60},  # already reset
                "five_hour": {"used_percentage": 42.5, "resets_at": self.now + 3600},
            },
        })
        r = self.collect(with_tokens=False)
        work = self.group(r, "work")
        busy = next(s for s in work["sessions"] if s["sessionId"] == "busy")
        self.assertEqual((busy["context"], busy["model"], busy["costUsd"]), (34.4, "Opus 5.5", 1.25))
        self.assertEqual(busy["effort"], "max")
        self.assertIsNone(next(s for s in work["sessions"] if s["sessionId"] == "waiting")["effort"])
        five, seven = work["limits"]["windows"]
        self.assertEqual((five["label"], five["pct"], five["reset"]), ("5h", 42.5, False))
        self.assertEqual(five["resetsAt"], int((self.now + 3600) * 1000))
        self.assertEqual((seven["label"], seven["pct"], seven["reset"]), ("7d", 0.0, True))
        self.assertIsNone(self.group(r, "personal")["limits"])

    def test_a_run_with_no_status_line_shows_no_earlier_runs_snapshot(self):
        # resumed in VS Code's panel 2 minutes ago; its terminal run 5 days ago left a snapshot
        write(self.home / ".claude-work/sessions/30.json",
              session("panel", entrypoint="claude-vscode", status="busy", startedAt=int((self.now - 120) * 1000)))
        self.snapshot(".claude-work", "panel", {"model": {"display_name": "Opus 4.5"}, "effort": {"level": "xhigh"},
                                                "context_window": {"used_percentage": 12}}, age=5 * 86400)
        write(self.home / ".claude-work/projects/-tmp-proj-panel/panel.jsonl", assistant("m1", self.now - 60, 5, "claude-haiku-4-5"))
        row = next(s for s in self.group(self.collect(with_tokens=False), "work")["sessions"] if s["sessionId"] == "panel")
        self.assertEqual((row["model"], row["effort"], row["context"]), ("Haiku 4.5", None, None))

    def usage_cache(self, fetched_ago, account="acct-pro"):
        # what Claude Code keeps in .claude.json (2.1.30x): /usage, the VS Code panel
        path = self.home / ".claude-personal/.claude.json"
        data = json.loads(path.read_text())
        data["cachedUsageUtilization"] = {
            "fetchedAtMs": int((self.now - fetched_ago) * 1000), "accountUuid": account,
            "utilization": {
                "five_hour": {"utilization": 35, "resets_at": iso(self.now + 3600), "limit_dollars": None},
                "seven_day": {"utilization": 87, "resets_at": iso(self.now - 60)},  # just reset
                "seven_day_opus": None, "tangelo": None,
                "extra_usage": {"is_enabled": False, "monthly_limit": 4000, "utilization": 0},
            }}
        write(path, data)

    def test_claude_codes_own_usage_when_its_newer(self):
        # An account used only in VS Code's panel (no status line there) kept
        # the numbers of its last terminal chat: a day old
        self.snapshot(".claude-personal", "old", {"rate_limits": {
            "five_hour": {"used_percentage": 0, "resets_at": self.now + 900}}}, age=21 * 3600)
        self.usage_cache(fetched_ago=3600)
        limits = self.group(self.collect(with_tokens=False), "personal")["limits"]
        self.assertEqual(limits["updatedAt"], int((self.now - 3600) * 1000))
        five, seven = limits["windows"]
        self.assertEqual((five["key"], five["pct"], five["resetsAt"]), ("five_hour", 35.0, int((self.now + 3600) * 1000)))
        self.assertEqual((seven["key"], seven["pct"], seven["reset"]), ("seven_day", 0.0, True))
        # a status line newer than the cache wins
        self.snapshot(".claude-personal", "new", {"rate_limits": {
            "five_hour": {"used_percentage": 40, "resets_at": self.now + 3600}}}, age=60)
        five, seven = self.group(self.collect(with_tokens=False), "personal")["limits"]["windows"]
        self.assertEqual((five["pct"], seven["reset"]), (40.0, True))  # (the cache's week, over by now)

    def test_a_weekly_window_missing_after_its_reset_shows_as_reset(self):
        # Claude Code leaves the weekly window out until the new week has usage
        self.snapshot(".claude-personal", "before", {"rate_limits": {
            "five_hour": {"used_percentage": 17, "resets_at": self.now - 3600},
            "seven_day": {"used_percentage": 99, "resets_at": self.now - 600}}}, age=7200)
        self.snapshot(".claude-personal", "after", {"rate_limits": {
            "five_hour": {"used_percentage": 5, "resets_at": self.now + 3600}}}, age=60)
        five, seven = self.group(self.collect(with_tokens=False), "personal")["limits"]["windows"]
        self.assertEqual((five["key"], five["pct"], five["reset"]), ("five_hour", 5.0, False))
        self.assertEqual((seven["key"], seven["pct"], seven["reset"]), ("seven_day", 0.0, True))
        # one that hasn't reset yet isn't made up
        self.snapshot(".claude-personal", "before", {"rate_limits": {
            "seven_day": {"used_percentage": 99, "resets_at": self.now + 600}}}, age=7200)
        (five,) = self.group(self.collect(with_tokens=False), "personal")["limits"]["windows"]
        self.assertEqual(five["key"], "five_hour")

    def test_a_usage_cache_of_another_account_is_left_out(self):
        self.usage_cache(fetched_ago=60, account="someone-else")
        self.assertIsNone(self.group(self.collect(with_tokens=False), "personal")["limits"])

    def two_of_one_name(self):
        """/data/.claude, an account of its own (--config-dir), next to ~/.claude."""
        other = Path(self.tmp.name) / "data/.claude"
        write(other / ".claude.json", {"oauthAccount": {"accountUuid": "acct-data", "organizationType": "claude_max"}})
        (other / "projects").mkdir(parents=True)
        return other

    def test_two_folders_of_one_name_keep_their_usage_apart(self):
        other = self.two_of_one_name()
        self.snapshot(".claude", "theirs", {"talpyDenConfigDir": str(other),
                                            "rate_limits": {"five_hour": {"used_percentage": 97}}}, age=10)
        self.snapshot(".claude", "mine", {"talpyDenConfigDir": str(self.home / ".claude"),
                                          "rate_limits": {"five_hour": {"used_percentage": 12}}}, age=300)
        r = cs.collect(self.home, self.cache, [str(other)], with_tokens=False, now=self.now)
        self.assertEqual(self.group(r, "personal")["limits"]["windows"][0]["pct"], 12)
        self.assertEqual(self.group(r, "claude")["limits"]["windows"][0]["pct"], 97)
        # a folder named through a link is that folder
        (Path(self.tmp.name) / "data-link").symlink_to(other.parent)
        self.snapshot(".claude", "theirs", {"talpyDenConfigDir": str(Path(self.tmp.name) / "data-link/.claude"),
                                            "rate_limits": {"five_hour": {"used_percentage": 98}}}, age=5)
        r = cs.collect(self.home, self.cache, [str(other)], with_tokens=False, now=self.now)
        self.assertEqual(self.group(r, "personal")["limits"]["windows"][0]["pct"], 12)
        self.assertEqual(self.group(r, "claude")["limits"]["windows"][0]["pct"], 98)
        # an older snippet's (no folder named) counts for both, as it always did
        self.snapshot(".claude", "older", {"rate_limits": {"five_hour": {"used_percentage": 50}}}, age=1)
        r = cs.collect(self.home, self.cache, [str(other)], with_tokens=False, now=self.now)
        self.assertEqual([self.group(r, n)["limits"]["windows"][0]["pct"] for n in ("personal", "claude")], [50, 50])

    def test_a_sessions_context_from_its_own_folder(self):
        other = self.two_of_one_name()
        write(other / "sessions/40.json", session("theirs", status="busy"))
        write(self.home / ".claude/sessions/41.json", session("theirs2", status="busy"))
        self.snapshot(".claude", "theirs", {"talpyDenConfigDir": str(other), "context_window": {"used_percentage": 40}})
        self.snapshot(".claude", "theirs2", {"talpyDenConfigDir": str(other), "context_window": {"used_percentage": 60}})
        r = cs.collect(self.home, self.cache, [str(other)], with_tokens=False, now=self.now)
        rows = {s["sessionId"]: s for g in r["groups"] for s in g["sessions"]}
        self.assertEqual((rows["theirs"]["context"], rows["theirs2"]["context"]), (40, None))
        self.assertTrue(cs.snapshot_of({"talpyDenConfigDir": "relative/.claude"}, [other]))   # (not a folder it can name)
        self.assertTrue(cs.snapshot_of(None, [other]))

    def test_newest_snapshot_across_group_profiles(self):
        self.snapshot(".claude", "a", {"rate_limits": {"five_hour": {"used_percentage": 10}}}, age=300)
        self.snapshot(".claude-personal", "b", {"rate_limits": {"five_hour": {"used_percentage": 20}}}, age=10)
        self.snapshot(".claude-personal", "c", {"session_id": "c"}, age=0)  # no limits yet
        limits = self.group(self.collect(with_tokens=False), "personal")["limits"]
        self.assertEqual(limits["windows"][0]["pct"], 20)

    def test_an_idle_chats_status_line_drawn_again_is_an_old_reading(self):
        # work at 100% (a chat at it at 10:44), and at 10:52 another chat's
        # status line, idle since 09:52, drawn again as its prompt cache went
        # cold: with its 32% of then. The Chats tab and the Recap said 32%.
        resets = self.now + 2 * 3600
        self.snapshot(".claude-work", "busy", {
            "rate_limits": {"five_hour": {"used_percentage": 100, "resets_at": resets}},
            "prompt_cache": {"warm": True, "ttl": "1h", "expires_at": self.now - 480 + 3600 - 12}}, age=480)
        self.snapshot(".claude-work", "idle", {
            "rate_limits": {"five_hour": {"used_percentage": 32, "resets_at": resets}},
            "prompt_cache": {"warm": False, "ttl": "1h", "expires_at": self.now - 1}}, age=0)
        limits = self.group(self.collect(with_tokens=False), "work")["limits"]
        self.assertEqual(limits["windows"][0]["pct"], 100)
        self.assertEqual(limits["updatedAt"], int((self.now - 492) * 1000))  # (as of its last request)
        # once that chat replies again, its numbers are the newest
        self.snapshot(".claude-work", "idle", {
            "rate_limits": {"five_hour": {"used_percentage": 100, "resets_at": resets}},
            "prompt_cache": {"warm": True, "ttl": "5m", "expires_at": self.now + 299}}, age=0)
        limits = self.group(self.collect(with_tokens=False), "work")["limits"]
        self.assertEqual(limits["updatedAt"], int((self.now - 1) * 1000))
        # an older Claude Code's (no prompt_cache): when it was written, as before
        self.snapshot(".claude-work", "older", {"rate_limits": {"five_hour": {"used_percentage": 40, "resets_at": resets}}}, age=0)
        self.assertEqual(self.group(self.collect(with_tokens=False), "work")["limits"]["windows"][0]["pct"], 40)

    def test_when_a_snapshots_numbers_were_read(self):
        t = 1_800_000_000_000
        self.assertEqual(cs.limits_read_at({"prompt_cache": {"ttl": "1h", "expires_at": 1_800_000_000}}, t), t - 3600_000)
        self.assertEqual(cs.limits_read_at({"prompt_cache": {"ttl": "5m", "expires_at": 1_800_000_000 + 600}}, t), t)  # (never later than written)
        for cache in (None, {}, {"ttl": "1h"}, {"ttl": "soon", "expires_at": 1_800_000_000}, {"ttl": "1h", "expires_at": True}):
            self.assertEqual(cs.limits_read_at({"prompt_cache": cache}, t), t)
        self.assertEqual([cs.cache_ttl_ms(v) for v in ("5m", "1h", "30s", "h", "1.5h", 3600)],
                         [300_000, 3600_000, 30_000, None, None, None])

    def test_a_snapshot_that_goes_away_doesnt_take_the_others_along(self):
        # (another copy's check pruning an old one while this one lists the folder; here links to nothing)
        for i in range(10):
            self.snapshot(".claude-work", f"s{i}", {"rate_limits": {"five_hour": {"used_percentage": i}}}, age=i)
            (self.cache / "statusline/.claude-work" / f"gone{i}.json").symlink_to(self.cache / "nowhere")
        work = next(p for p in cs.discover_profiles(self.home) if p.label == "work")
        self.assertEqual(len(cs.snapshot_files(self.cache / "statusline", [work])), 10)

    def test_old_snapshots_pruned(self):
        self.snapshot(".claude-work", "old", {"rate_limits": {"five_hour": {"used_percentage": 99}}}, age=9 * 86400)
        self.collect()
        self.assertFalse((self.cache / "statusline/.claude-work/old.json").exists())

    def test_iso_resets_at(self):
        self.assertEqual(cs.to_ms("2026-01-01T00:00:00Z"), 1767225600000)
        self.assertEqual(cs.to_ms(1767225600), 1767225600000)
        self.assertEqual(cs.to_ms(1767225600000), 1767225600000)
        self.assertIsNone(cs.to_ms("soon"))


class TokenTests(Fixture):
    def transcript(self):
        return self.home / ".claude-work/projects/-tmp-proj/abc.jsonl"

    def test_odd_lines_dont_cost_the_totals(self):
        odd = [
            '["not", "an", "object", "usage"]',
            json.dumps({"type": "assistant", "timestamp": 1e20, "message": {"id": "far", "usage": {"output_tokens": 5}}}),
            json.dumps({"type": "assistant", "timestamp": iso(self.now), "message": {
                "id": {"odd": 1}, "model": ["x"], "usage": {"output_tokens": 5}}}),
            '{"type": "assistant", "timestamp": "%s", "message": {"id": "nan", "usage": {"output_tokens": NaN}}}' % iso(self.now),
        ]
        write(self.transcript(), "\n".join(odd + [assistant("m1", self.now - 60, 16)]) + "\n")
        r = self.collect(now=self.now)
        self.assertEqual(r["errors"], [])
        self.assertEqual(self.group(r, "work")["tokens"]["today"]["output"], 16)

    def test_dedupe_partial_line_and_rescan(self):
        now = self.now
        lines = [
            assistant("m1", now - 60, 16),
            assistant("m1", now - 60, 305),  # same message, final output count
            assistant("old", now - 10 * 86400, 999),
            json.dumps({"type": "assistant", "timestamp": iso(now), "message": {
                "id": "syn", "model": "<synthetic>", "usage": {"input_tokens": 0, "output_tokens": 0}}}),
            json.dumps({"type": "user", "message": {"content": "hi"}}),
        ]
        partial = assistant("m2", now - 30, 7)
        write(self.transcript(), "\n".join(lines) + "\n" + partial[:40])

        today = self.group(self.collect(now=now), "work")["tokens"]["today"]
        self.assertEqual((today["messages"], today["output"]), (1, 305))
        self.assertEqual(today["total"], 2 + 305 + 100 + 10)

        # Finish the half-written line; within the scan interval nothing changes
        with open(self.transcript(), "a") as f:
            f.write(partial[40:] + "\n")
        self.assertEqual(self.group(self.collect(now=now + 5), "work")["tokens"]["today"]["messages"], 1)

        tokens = self.group(self.collect(now=now + cs.TOKEN_SCAN_INTERVAL + 1), "work")["tokens"]
        self.assertEqual((tokens["today"]["messages"], tokens["today"]["output"]), (2, 312))
        self.assertEqual(tokens["week"]["messages"], 2)
        self.assertEqual(tokens["models"][0]["model"], "claude-opus-5-5")

        # Another scan with nothing new must not double count
        tokens = self.group(self.collect(now=now + 2 * cs.TOKEN_SCAN_INTERVAL + 2), "work")["tokens"]
        self.assertEqual(tokens["today"]["messages"], 2)

    def test_group_sums_profiles(self):
        write(self.home / ".claude/projects/p/a.jsonl", assistant("x1", self.now - 5, 1) + "\n")
        write(self.home / ".claude-personal/projects/p/b.jsonl", assistant("x2", self.now - 5, 2) + "\n")
        today = self.group(self.collect(), "personal")["tokens"]["today"]
        self.assertEqual((today["messages"], today["output"]), (2, 3))

    def test_truncated_file_rescanned(self):
        write(self.transcript(), assistant("a1", self.now - 5, 5) + "\n" + assistant("a2", self.now - 5, 6) + "\n")
        self.collect()
        write(self.transcript(), assistant("a3", self.now - 5, 7) + "\n")  # rewritten, shorter
        work = next(p for p in cs.discover_profiles(self.home) if p.label == "work")
        path = cs.token_cache_path(self.cache, work)
        cache = json.loads(path.read_text())
        cache["scannedAt"] = 0
        write(path, cache)
        today = self.group(self.collect(), "work")["tokens"]["today"]
        self.assertEqual(today["messages"], 3)

    def test_a_chat_shared_later_counts_as_shared_from_its_first_message(self):
        mine = self.home / ".claude-personal/projects/p/chat.jsonl"
        write(mine, assistant("m1", self.now - 30, 5) + "\n")
        personal = next(p for p in cs.discover_profiles(self.home) if p.label == "personal")
        cache = cs.scan_transcripts(personal, cs.empty_token_cache(), self.now)
        self.assertEqual(cs.token_totals([cache], self.now)["today"]["shared"], 0)
        # hard-linked into another account's folder, and the chat goes on: that account counts all of it
        (self.home / ".claude-work/projects/p").mkdir(parents=True)
        os.link(mine, self.home / ".claude-work/projects/p/chat.jsonl")
        with open(mine, "a") as f:
            f.write(assistant("m2", self.now - 5, 6) + "\n")
        cache = cs.scan_transcripts(personal, cache, self.now + 1)
        today = cs.token_totals([cache], self.now + 1)["today"]
        self.assertEqual((today["messages"], today["shared"]), (2, today["total"]))


# The shells a status-line script may be written for (on Debian and Ubuntu, sh is dash)
SHELLS = [s for s in ("sh", "dash", "bash", "zsh") if shutil.which(s)]


class LegacyDirTests(unittest.TestCase):
    """The folders of the first name (claude-widget) move to talpy-den."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        env = mock.patch.dict(os.environ, {"XDG_CACHE_HOME": "", "XDG_DATA_HOME": ""})
        env.start()
        self.addCleanup(env.stop)

    def test_cache_and_data_move_and_leave_a_link(self):
        write(self.home / ".cache/claude-widget/keep.json", "{}")
        write(self.home / ".cache/claude-widget/statusline/p/s.json", "{}")
        write(self.home / ".local/share/claude-widget/live-hook.py", "hook")
        cs.adopt_legacy_dirs(self.home)
        self.assertEqual((self.home / ".cache/talpy-den/keep.json").read_text(), "{}")
        self.assertTrue((self.home / ".cache/talpy-den/statusline/p/s.json").is_file())
        self.assertEqual((self.home / ".local/share/talpy-den/live-hook.py").read_text(), "hook")
        # an older snippet or hook still writing/reading the old name lands in the new folder
        self.assertTrue((self.home / ".cache/claude-widget").is_symlink())
        write(self.home / ".cache/claude-widget/statusline/p/t.json", "{}")
        self.assertTrue((self.home / ".cache/talpy-den/statusline/p/t.json").is_file())
        self.assertEqual(stat.S_IMODE((self.home / ".cache/talpy-den").stat().st_mode), 0o700)
        cs.adopt_legacy_dirs(self.home)  # (nothing more to do)
        self.assertTrue((self.home / ".cache/talpy-den/keep.json").is_file())

    def test_what_the_new_folder_has_already_is_kept(self):
        write(self.home / ".cache/claude-widget/keep.json", '{"old": 1}')
        write(self.home / ".cache/claude-widget/stars.json", '{"old": 1}')
        write(self.home / ".cache/talpy-den/keep.json", '{"new": 1}')
        cs.adopt_legacy_dirs(self.home)
        self.assertEqual((self.home / ".cache/talpy-den/keep.json").read_text(), '{"new": 1}')
        self.assertEqual((self.home / ".cache/talpy-den/stars.json").read_text(), '{"old": 1}')
        # the old folder keeps what couldn't move: not replaced by a link
        self.assertTrue((self.home / ".cache/claude-widget/keep.json").is_file())
        self.assertFalse((self.home / ".cache/claude-widget").is_symlink())

    def test_nothing_to_move(self):
        cs.adopt_legacy_dirs(self.home)
        self.assertFalse((self.home / ".cache/claude-widget").exists())
        self.assertFalse((self.home / ".cache/talpy-den").exists())


@unittest.skipUnless(shutil.which("jq"), "the status-line snippet needs jq")
class SnippetTests(unittest.TestCase):
    def run_snippet(self, payload, cfg):
        """Runs the snippet in every shell here; all must do the same."""
        results = set()
        for shell in SHELLS:
            with tempfile.TemporaryDirectory() as tmp:
                script = 'input=$(cat)\n' + (ROOT / "statusline-snippet.sh").read_text() + 'echo ok\n'
                env = {**os.environ, "HOME": tmp, "XDG_CACHE_HOME": tmp + "/cache", "CLAUDE_CONFIG_DIR": cfg}
                out = subprocess.run([shell, "-c", script], input=json.dumps(payload), env=env,
                                     capture_output=True, text=True, check=True)
                files = tuple(sorted((str(p.relative_to(tmp)), p.stat().st_mode & 0o777)
                                     for p in Path(tmp).rglob("*") if p.is_file()))
                results.add((out.stdout, out.stderr, files))
        self.assertEqual(len(results), 1, f"the shells disagree: {results}")
        out, err, files = results.pop()
        return out, err, list(files)

    def test_plain_posix_sh(self):
        """No bash-only syntax: the snippet also goes into #!/bin/sh scripts."""
        code = [line for line in (ROOT / "statusline-snippet.sh").read_text().splitlines()
                if not line.lstrip().startswith("#")]
        for bashism in ("[[", "<<<", "<(", "$'", "==", "function ", "local "):
            self.assertFalse(any(bashism in line for line in code), bashism)

    def test_quotes_and_spaces_in_paths(self):
        payload = {"session_id": "s3", "transcript_path": "/h/it's a $(dir)/.claude-personal/projects/-x/s3.jsonl"}
        out, err, files = self.run_snippet(payload, "/x/.claude-work")
        self.assertEqual((out, err), ("ok\n", ""))
        self.assertEqual([f for f, _ in files], ["cache/talpy-den/statusline/.claude-personal/s3.json"])

    def test_writes_snapshot_per_profile(self):
        out, err, files = self.run_snippet({"session_id": "abc-123", "rate_limits": {}}, "/x/.claude-work/")
        self.assertEqual((out, err), ("ok\n", ""))
        self.assertEqual(files, [("cache/talpy-den/statusline/.claude-work/abc-123.json", 0o600)])

    def test_profile_from_transcript_path(self):
        payload = {"session_id": "s1",
                   "transcript_path": "/h/projects/.claude-personal/projects/-h-repo/s1/subagents/a.jsonl"}
        out, err, files = self.run_snippet(payload, "/x/.claude-work")
        self.assertEqual([f for f, _ in files], ["cache/talpy-den/statusline/.claude-personal/s1.json"])

    def test_link_filed_under_the_real_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / ".claude-personal"
            real.mkdir()
            (Path(tmp) / ".claude").symlink_to(real)
            payload = {"session_id": "s2", "transcript_path": f"{tmp}/.claude/projects/-h-repo/s2.jsonl"}
            out, err, files = self.run_snippet(payload, "/x/.claude-work")
            self.assertEqual([f for f, _ in files], ["cache/talpy-den/statusline/.claude-personal/s2.json"])

    def test_rejects_unsafe_session_id(self):
        out, err, files = self.run_snippet({"session_id": "../../evil"}, "/x/.claude")
        self.assertEqual((out, err, files), ("ok\n", "", []))

    def test_a_snapshot_names_its_folder(self):
        # (two folders of one name, ~/.claude and /data/.claude, file theirs in
        # one place: what each one is of tells them apart)
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / "it's data/.claude"
            real.mkdir(parents=True)
            (Path(tmp) / "link").symlink_to(real.parent)
            payload = {"session_id": "s4", "transcript_path": f"{tmp}/link/.claude/projects/-h/s4.jsonl",
                       "rate_limits": {"five_hour": {"used_percentage": 7}}, "model": {"display_name": "Opus"}}
            for shell in SHELLS:
                with tempfile.TemporaryDirectory() as out:
                    script = 'set -eu\ninput=$(cat)\n' + (ROOT / "statusline-snippet.sh").read_text() + 'echo ok\n'
                    env = {**os.environ, "HOME": out, "XDG_CACHE_HOME": out + "/cache"}
                    done = subprocess.run([shell, "-c", script], input=json.dumps(payload), env=env,
                                          capture_output=True, text=True, check=True)
                    self.assertEqual((done.stdout, done.stderr), ("ok\n", ""))
                    snap = json.loads(Path(out, "cache/talpy-den/statusline/.claude/s4.json").read_text())
                    self.assertEqual(snap, dict(payload, talpyDenConfigDir=str(real)), shell)


class AgentTests(Fixture):
    """Subagents: status and current step from each agent's transcript, nested as a tree."""

    def agent(self, sid, agent_id, lines, depth=1, tool_use_id="toolu_x", description="", shape="sync", **meta):
        d = self.home / ".claude-work/projects/-w-proj" / sid / "subagents"
        write(d / f"agent-{agent_id}.meta.json", {"agentType": "Explore", "description": description,
                                                  "spawnDepth": depth, "toolUseId": tool_use_id,
                                                  "requestShape": shape, **meta})
        write(d / f"agent-{agent_id}.jsonl", "\n".join(json.dumps(l) for l in lines) + "\n")
        return d

    def line(self, kind, content, stop=None):
        return {"type": kind, "timestamp": iso(self.now), "isSidechain": True,
                "message": {"role": kind, "content": content, "stop_reason": stop}}

    def setUp(self):
        super().setUp()
        tool = lambda i, name, inp: {"type": "tool_use", "id": i, "name": name, "input": inp}
        self.agent("busy", "a1", [self.line("user", "find the parser"),
                                  self.line("assistant", [{"type": "text", "text": "Found it in parser.py\nmore"}], "end_turn")],
                   description="Find the parser")
        self.agent("busy", "a2", [self.line("user", "run tests"),
                                  self.line("assistant", [tool("toolu_child", "Agent", {"description": "check flaky test"})], "tool_use"),
                                  self.line("assistant", [tool("toolu_b", "Bash", {"command": "pytest -x tests/\necho"})], "tool_use")],
                   description="Run the tests")
        self.agent("busy", "a3", [self.line("user", "look at flaky test"),
                                  self.line("assistant", [tool("toolu_r", "Read", {"file_path": "/w/proj/tests/test_io.py"})], "tool_use"),
                                  self.line("user", [{"type": "tool_result", "tool_use_id": "toolu_r", "content": "..."}])],
                   depth=2, tool_use_id="toolu_child", description="Check flaky test")

    def test_counts_tree_and_activity(self):
        work = self.group(self.collect(with_tokens=False), "work")
        a = next(s for s in work["sessions"] if s["sessionId"] == "busy")["agents"]
        self.assertEqual((a["total"], a["done"], a["running"], a["stopped"]), (3, 1, 2, 0))
        rows = [(t["id"], t["depth"], t["status"], t["activity"]) for t in a["tree"]]
        self.assertEqual(rows, [
            ("a1", 0, "done", "Found it in parser.py"),
            ("a2", 0, "running", "Bash: pytest -x tests/ echo"),
            ("a3", 1, "running", "Read: test_io.py (thinking about the result)"),
        ])
        self.assertIsNone(next(s for s in work["sessions"] if s["sessionId"] == "waiting")["agents"])

    def test_handback_means_done(self):
        # Current Claude Code agents finish by handing their report back through a tool call
        tool = {"type": "tool_use", "id": "toolu_h", "name": "SubagentHandback",
                "input": {"message": "**Summary**\nThere are 10 .qml files"}}
        self.agent("busy", "a4", [self.line("user", "list files"),
                                  self.line("assistant", [tool]),
                                  self.line("user", [{"type": "tool_result", "tool_use_id": "toolu_h", "content": [{"type": "text", "text": "ok"}]}])],
                   description="List files")
        a = next(s for s in self.group(self.collect(with_tokens=False), "work")["sessions"] if s["sessionId"] == "busy")["agents"]
        a4 = next(t for t in a["tree"] if t["id"] == "a4")
        self.assertEqual((a4["status"], a4["activity"]), ("done", "Summary"))
        self.assertEqual(cs.report_line("| Lines | File |\n|--|"), "Lines | File |")

    def agents_of_busy(self):
        a = next(s for s in self.group(self.collect(with_tokens=False), "work")["sessions"] if s["sessionId"] == "busy")["agents"]
        return a, {t["id"]: (t["status"], t["activity"]) for t in a["tree"]}

    def test_how_an_agent_can_end(self):
        error = self.line("assistant", [{"type": "text", "text": "You've hit your session limit · resets 2:40pm"}], "stop_sequence")
        error["isApiErrorMessage"] = True
        self.agent("busy", "e1", [self.line("user", "look"), error], description="Died", finished=True)
        self.agent("busy", "e2", [self.line("user", "look"), self.line("user", "[Request interrupted by user]")],
                   description="Interrupted")
        long = self.line("assistant", [{"type": "text", "text": "Half an ans"}], "max_tokens")
        self.agent("busy", "e3", [self.line("user", "look"), long], description="Cut short", finished=True)
        a, rows = self.agents_of_busy()
        self.assertEqual(rows["e1"], ("failed", "You've hit your session limit · resets 2:40pm"))
        self.assertEqual(rows["e2"], ("stopped", "interrupted"))
        self.assertEqual(rows["e3"], ("done", "finished"))
        self.assertEqual((a["failed"], a["stopped"], a["done"], a["running"]), (1, 1, 2, 2))

    def test_a_running_agent_read_again_once_claude_says_it_finished(self):
        lines = [self.line("user", "look"), self.line("assistant", [{"type": "text", "text": "Half an ans"}], "max_tokens")]
        d = self.agent("busy", "e4", lines, description="Cut short")
        self.assertEqual(self.agents_of_busy()[1]["e4"], ("running", "writing…"))
        meta = d / "agent-e4.meta.json"
        meta.write_text(json.dumps({**json.loads(meta.read_text()), "finished": True}))  # the transcript is unchanged
        self.assertEqual(self.agents_of_busy()[1]["e4"], ("done", "finished"))

    def test_a_message_from_its_chat_wakes_a_finished_agent(self):
        message = self.line("user", "Also check the docs")
        message.update(isMeta=True, origin={"kind": "coordinator"})
        self.agent("busy", "e5", [self.line("user", "look"),
                                  self.line("assistant", [{"type": "text", "text": "Done"}], "end_turn"), message])
        self.assertEqual(self.agents_of_busy()[1]["e5"], ("running", "reading a message from its chat…"))

    def test_a_parent_not_found_isnt_looked_for_on_every_check(self):
        self.agent("busy", "n1", [self.line("user", "nested")], depth=2, tool_use_id="toolu_nowhere")
        self.collect(with_tokens=False)
        reads = []
        real = Path.read_bytes
        with mock.patch.object(cs.Path, "read_bytes", lambda p: reads.append(p.name) or real(p)):
            self.collect(with_tokens=False)
        self.assertEqual(reads, [])
        self.assertIn("n1", json.loads((self.cache / "agents.json").read_text())["misses"])

    def test_agents_of_an_ended_session_are_stopped(self):
        cache = cs.AgentCache(self.cache / "agents.json")
        profile = next(p for p in cs.discover_profiles(self.home) if p.label == "work")
        a = cache.session_agents(profile, "busy", alive=False)
        self.assertEqual((a["done"], a["running"], a["stopped"]), (1, 0, 2))

    def test_agents_of_the_process_before_a_resume_are_stopped(self):
        # claude --resume keeps the chat's id: the agents that ran in its
        # earlier process can't be running in this one
        busy = self.home / ".claude-work/sessions/11.json"
        write(busy, session("busy", status="busy", startedAt=int((self.now + 60) * 1000)))
        a, rows = self.agents_of_busy()
        self.assertEqual((a["running"], a["stopped"], rows["a1"][0]), (0, 2, "done"))
        write(busy, session("busy", status="busy", startedAt=int((self.now - 60) * 1000)))
        self.assertEqual(self.agents_of_busy()[0]["running"], 2)

    def test_unchanged_transcripts_are_not_read_again(self):
        self.collect(with_tokens=False)
        calls = []
        real = cs.agent_progress
        cs.agent_progress = lambda path, *more: calls.append(path) or real(path, *more)
        try:
            self.collect(with_tokens=False)
            self.assertEqual(calls, [])
            with open(self.home / ".claude-work/projects/-w-proj/busy/subagents/agent-a2.jsonl", "a") as f:
                f.write(json.dumps(self.line("assistant", [{"type": "text", "text": "All 12 pass"}], "end_turn")) + "\n")
            work = self.group(self.collect(with_tokens=False), "work")
        finally:
            cs.agent_progress = real
        self.assertEqual([p.name for p in calls], ["agent-a2.jsonl"])
        a = next(s for s in work["sessions"] if s["sessionId"] == "busy")["agents"]
        self.assertEqual((a["done"], a["running"]), (2, 1))

    def test_each_agents_model(self):
        tool = {"type": "tool_use", "id": "toolu_g", "name": "Grep", "input": {"pattern": "def parse"}}
        reply = self.line("assistant", [tool], "tool_use")
        reply["message"]["model"] = "claude-haiku-4-5-20251001"
        self.agent("busy", "a5", [self.line("user", "search"), reply], description="Search")
        a = next(s for s in self.group(self.collect(with_tokens=False), "work")["sessions"] if s["sessionId"] == "busy")["agents"]
        self.assertEqual(next(t for t in a["tree"] if t["id"] == "a5")["model"], "Haiku 4.5")
        self.assertIsNone(next(t for t in a["tree"] if t["id"] == "a1")["model"])   # no model recorded
        # tool results come in after its reply: the model it had stays
        with open(self.home / ".claude-work/projects/-w-proj/busy/subagents/agent-a5.jsonl", "a") as f:
            for _ in range(8):
                f.write(json.dumps(self.line("user", [{"type": "tool_result", "tool_use_id": "toolu_g", "content": "x"}])) + "\n")
        a = next(s for s in self.group(self.collect(with_tokens=False), "work")["sessions"] if s["sessionId"] == "busy")["agents"]
        self.assertEqual(next(t for t in a["tree"] if t["id"] == "a5")["model"], "Haiku 4.5")

    def tree_of(self, sid="busy", result=None):
        work = self.group(result or self.collect(with_tokens=False), "work")
        return {t["id"]: t for t in next(s for s in work["sessions"] if s["sessionId"] == sid)["agents"]["tree"]}

    def test_task_steps_and_report(self):
        tool = lambda i, name, inp: {"type": "tool_use", "id": i, "name": name, "input": inp}
        lines = [self.line("user", "Find where `parse` is defined.\nLook in src/.")]
        for n in range(8):
            lines += [self.line("assistant", [tool(f"toolu_{n}", "Read", {"file_path": f"/w/proj/f{n}.py"})], "tool_use"),
                      self.line("user", [{"type": "tool_result", "tool_use_id": f"toolu_{n}", "content": "x"}])]
        lines += [self.line("assistant", [tool("toolu_h", "SubagentHandback", {"message": "## Found\n**parser.py** has it"})]),
                  self.line("user", [{"type": "tool_result", "tool_use_id": "toolu_h", "content": "ok"}])]
        self.agent("busy", "a6", lines, description="Find parse")
        write(self.home / ".claude-work/projects/-w-proj/busy.jsonl", "")  # the chat itself
        tree = self.tree_of()
        a6 = tree["a6"]
        self.assertEqual(a6["task"], "Find where parse is defined.\nLook in src/.")
        self.assertEqual(a6["steps"], [f"Read: f{n}.py" for n in range(2, 8)])  # the last six, oldest first
        self.assertEqual(a6["report"], "Found\nparser.py has it")
        self.assertEqual((a6["toolCalls"], a6["tokens"]), (8, 0))  # the handback isn't a step
        self.assertEqual(tree["a1"]["report"], "Found it in parser.py\nmore")  # a final answer
        self.assertEqual((tree["a2"]["report"], tree["a2"]["steps"]), ("", ["Agent: check flaky test", "Bash: pytest -x tests/ echo"]))

    def test_a_forks_task_is_its_directive(self):
        tool = {"type": "tool_use", "id": "toolu_p", "name": "Agent", "input": {"description": "GNOME port"}}
        rules = "<fork-boilerplate>\nYou are a worker fork.\n</fork-boilerplate>\n\nYour directive: Port the stats to GNOME."
        self.agent("busy", "a7", [self.line("assistant", [tool], "tool_use"),  # a copy of the call that started it
                                  self.line("user", [{"type": "tool_result", "tool_use_id": "toolu_p", "content": None},
                                                     {"type": "text", "text": rules}])])
        self.assertEqual(self.tree_of()["a7"]["task"], "Port the stats to GNOME.")

    def test_a_forks_copy_of_the_call_isnt_its_work(self):
        call = self.line("assistant", [{"type": "tool_use", "id": "toolu_p", "name": "Agent", "input": {"description": "x"}}],
                         "tool_use")
        call["message"].update(id="msg-parent", usage={"input_tokens": 5, "output_tokens": 5000})
        rules = "<fork-boilerplate>\nrules\n</fork-boilerplate>\n\nYour directive: Go."
        own = self.line("assistant", [{"type": "text", "text": "Gone."}], "end_turn")
        own["message"].update(id="msg-own", usage={"input_tokens": 1, "output_tokens": 9})
        self.agent("busy", "a9", [call, self.line("user", [{"type": "tool_result", "tool_use_id": "toolu_p", "content": None},
                                                          {"type": "text", "text": rules}]), own])
        write(self.home / ".claude-work/projects/-w-proj/busy.jsonl", "")  # the chat itself
        a9 = self.tree_of()["a9"]
        self.assertEqual((a9["status"], a9["steps"], a9["toolCalls"], a9["tokens"]), ("done", [], 0, 10))

    def test_big_results_at_the_end(self):
        # The end of a transcript can be one huge tool result: read further back
        big = "x" * (cs.AGENT_TAIL_BYTES + 1000)
        tool = {"type": "tool_use", "id": "toolu_b", "name": "Bash", "input": {"command": "seq 60"}}
        self.agent("busy", "a8", [self.line("user", "count"), self.line("assistant", [tool], "tool_use"),
                                  self.line("user", [{"type": "tool_result", "tool_use_id": "toolu_b", "content": big}]),
                                  {"type": "attachment", "isSidechain": True, "attachment": {"blob": big}}])
        a8 = self.tree_of()["a8"]
        self.assertEqual((a8["activity"], a8["steps"]), ("Bash: seq 60 (thinking about the result)", ["Bash: seq 60"]))

    def test_details_have_a_cache_file_of_their_own(self):
        # Older copies of the script (a VS Code extension not updated yet)
        # rewrite agents.json as they know it: the details aren't in it
        self.collect(with_tokens=False)
        agents = json.loads((self.cache / "agents.json").read_text())
        self.assertTrue({"version", "files", "parents"} <= set(agents))
        self.assertTrue(all(len(rec) == 7 for rec in agents["files"].values()))  # no details in there
        (self.cache / "agent-details.json").unlink()
        calls = []
        real = cs.agent_progress
        cs.agent_progress = lambda path, *more: calls.append(path.name) or real(path, *more)
        try:
            tree = self.tree_of()  # read again once
            self.assertEqual(sorted(calls), ["agent-a1.jsonl", "agent-a2.jsonl", "agent-a3.jsonl"])
            self.assertEqual(tree["a1"]["task"], "find the parser")
            calls.clear()
            self.assertEqual(self.tree_of()["a3"]["task"], "look at flaky test")
            self.assertEqual(calls, [])
        finally:
            cs.agent_progress = real


    def test_model_label(self):
        for model, label in (("claude-opus-5-5", "Opus 5.5"), ("claude-opus-5-5[1m]", "Opus 5.5"),
                             ("claude-haiku-4-5-20251001", "Haiku 4.5"), ("claude-3-5-sonnet-20241022", "Sonnet 3.5"),
                             ("claude-fable-5-1", "Fable 5.1"), ("<synthetic>", None), (None, None)):
            self.assertEqual(cs.model_label(model), label, model)

    def test_describe_tool(self):
        self.assertEqual(cs.describe_tool({"name": "Edit", "input": {"file_path": "/a/b/parser.py"}}), "Edit: parser.py")
        self.assertEqual(cs.describe_tool({"name": "mcp__github__create_issue", "input": {}}), "github: create_issue")
        self.assertEqual(cs.describe_tool({"name": "TodoWrite", "input": {"todos": []}}), "TodoWrite")


class TokenCountTests(unittest.TestCase):
    def test_the_unit_by_what_it_rounds_to(self):
        self.assertEqual([cs.token_count(n) for n in (999, 1500, 999_949, 999_960, 2_500_000)],
                         ["999", "1.5k", "999.9k", "1.0M", "2.5M"])


class AgentRunTests(Fixture):
    """A subagent's whole run as Markdown (agent_run: what the widget opens)."""

    def setUp(self):
        super().setUp()
        d = self.home / ".claude-work/projects/-w-proj"
        write(d / "chat1.jsonl", json.dumps({"type": "user", "cwd": str(self.home / "repos/app"), "sessionId": "chat1",
                                             "timestamp": iso(self.now - 100), "message": {"content": "Fix the parser"}}) + "\n")
        self.dir = d / "chat1/subagents"
        write(self.dir / "agent-ag1.meta.json", {"agentType": "Explore", "description": "Find parse", "requestShape": "background"})

    def line(self, kind, content, ts, **kw):
        return {"type": kind, "timestamp": iso(self.now - 60 + ts), "isSidechain": True,
                "message": {"role": kind, "content": content, "model": "claude-haiku-5-5"}, **kw}

    def run_of(self, lines, agent="ag1", chat="chat1"):
        write(self.dir / f"agent-{agent}.jsonl", "".join(json.dumps(l) + "\n" for l in lines))
        return cs.agent_run(self.home, [], chat, agent, ".claude-work")

    def test_the_whole_run(self):
        tool = lambda i, name, inp: {"type": "tool_use", "id": i, "name": name, "input": inp}
        result = lambda i, content, **kw: {"type": "tool_result", "tool_use_id": i, "content": content, **kw}
        listing = "\n".join(["```"] + [f"line {n}" for n in range(99)])
        ok, message, title, md = self.run_of([
            self.line("user", "Find `parse` in src/", 0),
            self.line("user", "<system-reminder>\nReport through SubagentHandback.", 0, isMeta=True),
            self.line("assistant", [{"type": "thinking", "thinking": "", "signature": "x"}], 1),
            self.line("assistant", [{"type": "thinking", "thinking": "Let me grep."}], 1),
            self.line("assistant", [{"type": "text", "text": "Looking."}], 2),
            self.line("assistant", [tool("t1", "Bash", {"command": "grep -rn parse src", "description": "Search"})], 3),
            self.line("user", [result("t1", "src/a.py:1:def parse")], 4),
            self.line("user", "The coordinator sent a message:\nAlso check tests/", 5, isMeta=True, origin={"kind": "coordinator"}),
            self.line("assistant", [tool("t2", "Edit", {"file_path": "/w/a.py", "old_string": "a", "new_string": "b"})], 6),
            self.line("user", [result("t2", [{"type": "text", "text": "File not found"}], is_error=True)], 7),
            self.line("assistant", [tool("t3", "Read", {"file_path": "/w/b.py"})], 8),
            self.line("user", [result("t3", listing)], 9),
            self.line("assistant", [tool("t4", "SubagentHandback", {"message": "## Done\nIt's in `src/a.py`"})], 70),
            self.line("user", [result("t4", "ok")], 71),
        ])
        self.assertEqual((ok, message, title), (True, "The run of “Find parse”", "Find parse"))
        head = md.split("## Task")[0]
        self.assertIn("# Find parse\n\nExplore agent · Haiku 5.5 · in the background · done after 1m 11s · 3 tool calls\n", head)
        self.assertIn("A subagent of “Fix the parser” · in ~/repos/app · started ", head)
        self.assertIn("## Task\n\nFind `parse` in src/\n\n## Steps", md)
        self.assertNotIn("system-reminder", md)
        self.assertIn("> *Thinking:* Let me grep.", md)
        self.assertIn("· Claude**\n\nLooking.", md)
        self.assertIn("**▸ Bash** · Search\n\n```bash\ngrep -rn parse src\n```\n\n*Result:*\n\n```\nsrc/a.py:1:def parse\n```", md)
        self.assertIn("· Message from the main chat**\n\n> The coordinator sent a message:\n> Also check tests/", md)
        self.assertIn("**▸ Edit** `/w/a.py`\n\n```diff\n- a\n+ b\n```\n\n*Error:*\n\n```\nFile not found\n```", md)
        # a long result is cut short, in a fence its own backticks can't close
        self.assertIn("````\n```\nline 0\n", md)
        self.assertIn(f"line {cs.RUN_RESULT_LINES - 2}\n````\n*… {100 - cs.RUN_RESULT_LINES} more lines*", md)
        self.assertTrue(md.split("## Report\n\n")[1].startswith("## Done\nIt's in `src/a.py`\n\n---\n*Transcript: `"))

    def test_still_running(self):
        ok, _, _, md = self.run_of([self.line("user", "Count", 0),
                                    self.line("assistant", [{"type": "tool_use", "id": "t", "name": "Bash",
                                                             "input": {"command": "seq 9"}}], 1)])
        self.assertTrue(ok)
        self.assertIn("· not finished · last step: Bash: seq 9 · 1 tool call", md)
        self.assertIn("## Report\n\n*None yet: it hadn't finished at ", md)

    def test_a_fork(self):
        rules = "<fork-boilerplate>\nYou are a worker fork.\n</fork-boilerplate>\n\nYour directive: Port it."
        _, _, _, md = self.run_of([
            self.line("assistant", [{"type": "tool_use", "id": "p", "name": "Agent", "input": {"prompt": "Port it."}}], 0),
            self.line("user", [{"type": "tool_result", "tool_use_id": "p", "content": None}, {"type": "text", "text": rules}], 1)])
        self.assertIn("## Task\n\nPort it.\n\n## Steps\n\n*None yet.*", md)  # not the call that started it
        self.assertIn("· 0 tool calls", md)

    def test_markdown_stays_markdown(self):
        self.assertEqual(cs.closed_fences("see:\n```py\nx = 1"), "see:\n```py\nx = 1\n```")
        self.assertEqual(cs.closed_fences("```\na\n```\nok"), "```\na\n```\nok")
        self.assertEqual(cs.closed_fences("````\n```\nstill code"), "````\n```\nstill code\n````")
        self.assertEqual((cs.code_span("a`b"), cs.code_span("`x"), cs.code_span("p")), ("``a`b``", "`` `x ``", "`p`"))

    def test_unknown_or_unsafe_ids(self):
        self.assertEqual(cs.agent_run(self.home, [], "chat1", "nope"), (False, "Can't find that subagent's transcript", None, None))
        for chat, agent in (("chat1", "../x"), ("*", "ag1"), ("chat1", "a*")):
            self.assertFalse(cs.agent_run(self.home, [], chat, agent)[0], (chat, agent))

    def test_command_line(self):
        self.run_of([self.line("user", "Count", 0)])
        out = io.StringIO()
        with mock.patch.object(cs.Path, "home", return_value=self.home), contextlib.redirect_stdout(out):
            cs.main(["--agent-run", "ag1", "--chat", "chat1", "--profile", ".claude-work"])
        answer = json.loads(out.getvalue())
        self.assertEqual((answer["ok"], answer["title"]), (True, "Find parse"))
        self.assertTrue(answer["markdown"].startswith("# Find parse\n"))
        with self.assertRaises(SystemExit):
            cs.main(["--agent-run", "ag1"])  # which chat's?


class SharedCacheFileTests(unittest.TestCase):
    """Copies of the script that list different chats share the cache files."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.lines = [json.dumps({"type": "user", "message": {"content": f"prompt {n}"}}) for n in range(3)]

    def transcript(self, name, lines):
        path = self.dir / f"{name}.jsonl"
        path.write_text("".join(l + "\n" for l in lines))
        return path

    def test_one_copy_keeps_the_others_entries(self):
        a, b = self.transcript("a", self.lines), self.transcript("b", self.lines)
        for path in (a, b):  # e.g. the panel lists a, the VS Code extension b
            cache = cs.ChatCache(self.dir / "chats.json")
            cache.edits(path)
            cache.save()
        cache = cs.ChatCache(self.dir / "chats.json")
        reads = []
        real = cs.scan_edits
        with mock.patch.object(cs, "scan_edits", lambda path, *rest: reads.append(path.name) or real(path, *rest)):
            self.assertEqual(cache.edits(a)["stats"]["prompts"], 3)
        self.assertEqual(reads, [])

    def test_entries_no_copy_used_for_long_go(self):
        a = self.transcript("a", self.lines)
        cache = cs.ChatCache(self.dir / "chats.json")
        cache.edits(a)
        with mock.patch.object(cs.time, "time", return_value=time.time() - cs.CACHE_KEEP_S - 60):
            cache.save()
        later = cs.ChatCache(self.dir / "chats.json")
        later.save()
        self.assertEqual(json.loads((self.dir / "chats.json").read_text())["edits"], {})

    def test_counts_what_an_older_copy_read_without_counting(self):
        path = self.transcript("a", self.lines[:1])
        cache = cs.ChatCache(self.dir / "chats.json")
        cache.edits(path)
        cache.save()
        # 1.8 read on to the end and kept "stats" as it was
        path.write_text("".join(l + "\n" for l in self.lines))
        data = json.loads((self.dir / "chats.json").read_text())
        (entry,) = data["edits"].values()
        entry["size"] = path.stat().st_size
        cs.write_json_atomic(self.dir / "chats.json", {**data, "edits": {cs.file_key(path.stat()): entry}})
        self.assertEqual(cs.ChatCache(self.dir / "chats.json").edits(path)["stats"]["prompts"], 3)

    def test_a_failed_write_leaves_nothing_behind(self):
        # a full disk fails the write halfway; every check is a new process
        cs.write_json_atomic(self.dir / "chats.json", {"version": 1})
        with self.assertRaises(TypeError):
            cs.write_json_atomic(self.dir / "chats.json", {"version": 1, "edits": {"a": [1, {2}]}})
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["chats.json"])
        self.assertEqual(json.loads((self.dir / "chats.json").read_text()), {"version": 1})


class OneAccountTwoProfilesTests(unittest.TestCase):
    def test_a_chat_shared_between_them_counts_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            home, cache, now = Path(tmp) / "home", Path(tmp) / "cache", time.time()
            for name in (".claude-a", ".claude-b"):
                write(home / name / ".claude.json", {"oauthAccount": {"accountUuid": "same"}})
            chat = home / ".claude-a/projects/p/chat.jsonl"
            write(chat, assistant("m1", now - 5, 1000) + "\n")
            (home / ".claude-b/projects/p").mkdir(parents=True)
            os.link(chat, home / ".claude-b/projects/p/chat.jsonl")  # what "Share with all accounts" does
            (g,) = cs.collect(home, cache, now=now)["groups"]
        self.assertEqual((g["tokens"]["today"]["output"], g["tokens"]["today"]["messages"]), (1000, 1))
        self.assertEqual(g["stats"]["days"][-1]["messages"], 1)

    def test_a_shared_chat_counts_once_after_its_messages_age_out(self):
        # (the caches keep each message for TOKEN_DAYS; older days are each profile's sums)
        with tempfile.TemporaryDirectory() as tmp:
            home, cache, now = Path(tmp) / "home", Path(tmp) / "cache", time.time()
            for name in (".claude-a", ".claude-b"):
                write(home / name / ".claude.json", {"oauthAccount": {"accountUuid": "same"}})
            chat = home / ".claude-a/projects/p/chat.jsonl"
            write(chat, assistant("m1", now - 10 * 86400, 1000) + "\n" + assistant("m2", now - 5, 10) + "\n")
            write(home / ".claude-a/projects/p/own.jsonl", assistant("m3", now - 10 * 86400, 200) + "\n")
            (home / ".claude-b/projects/p").mkdir(parents=True)
            os.link(chat, home / ".claude-b/projects/p/chat.jsonl")
            (g,) = cs.collect(home, cache, now=now)["groups"]
        day = g["stats"]["days"][-11]
        self.assertEqual((day["output"], day["messages"], day["chats"]), (1200, 2, 2))
        self.assertEqual(g["stats"]["sum"]["output"], 1210)
        self.assertEqual(sum(m["total"] for m in g["stats"]["models"]), g["stats"]["sum"]["total"])


class ProfileNameTests(unittest.TestCase):
    def test_a_linked_profile_keeps_its_own_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            for name in (".claude-personal", ".claude-work"):
                (home / name / "sessions").mkdir(parents=True)
            (home / ".claude").symlink_to(home / ".claude-personal")
            labels = sorted(p.label for p in cs.discover_profiles(home))
            (home / ".claude").unlink()
            (home / ".claude").symlink_to(home / ".claude-work")  # switched: the names stay
            self.assertEqual(labels, sorted(p.label for p in cs.discover_profiles(home)))
            self.assertEqual(labels, ["personal", "work"])

    def test_two_folders_of_the_same_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            (home / ".claude/sessions").mkdir(parents=True)
            other = Path(tmp) / "data/.claude"
            (other / "sessions").mkdir(parents=True)
            profiles = cs.discover_profiles(home, [str(other)])
            self.assertEqual(len({p.key for p in profiles}), 2)
            self.assertIs(next(p for p in profiles if cs.matches_profile(p, str(other))).real, profiles[1].real)


class TokenCachePruneTests(Fixture):
    def test_another_copys_profiles_keep_their_caches(self):
        profiles = cs.discover_profiles(self.home)
        self.cache.mkdir(parents=True, exist_ok=True)
        mine = cs.token_cache_path(self.cache, profiles[0])
        theirs = self.cache / "tokens-.claude-extra-0123abcd.json"  # a profile only another copy knows
        gone = self.cache / "tokens-.claude-old-89abcdef.json"
        for f in (mine, theirs, gone):
            f.write_text("{}")
        old = time.time() - cs.TOKEN_CACHE_KEEP_S - 60
        os.utime(gone, (old, old))
        cs.prune_token_caches(self.cache, profiles)
        self.assertEqual(sorted(f.name for f in self.cache.glob("tokens-*.json")), sorted([mine.name, theirs.name]))


class TokenScanTimeTests(Fixture):
    def test_a_scan_from_the_future_is_due(self):
        profile = cs.discover_profiles(self.home)[0]
        self.cache.mkdir(parents=True, exist_ok=True)
        cs.write_json_atomic(cs.token_cache_path(self.cache, profile),
                             {**cs.empty_token_cache(), "scannedAt": self.now + 6 * 3600})  # the clock was set back
        scans = []
        with mock.patch.object(cs, "scan_transcripts", lambda p, cache, now: scans.append(now) or cache):
            cs.load_token_cache(self.cache, profile, self.now, True)
        self.assertEqual(scans, [self.now])


class OutputTests(Fixture):
    def test_half_an_emoji_in_a_title_cant_break_the_output(self):
        # JavaScript can cut an emoji in half; JSON.stringify writes that as \ud83d
        title = '{"type":"ai-title","aiTitle":"Fix the \\ud83d"}\n'
        prompt = json.dumps({"type": "user", "cwd": "/tmp/x", "message": {"content": "go"}}) + "\n"
        reply = json.dumps({"type": "assistant", "cwd": "/tmp/x", "message": {"content": [{"type": "text", "text": "ok"}]}})
        write(self.home / ".claude-work/projects/-tmp-x/half-emoji.jsonl", title + prompt + reply + "\n")
        env = {**os.environ, "HOME": str(self.home), "XDG_CACHE_HOME": str(self.cache)}
        for args in ([], ["--remote"]):
            out = subprocess.run([sys.executable, "-I", str(ROOT / "package/contents/code/talpy_den.py"), "--no-tokens", *args],
                                 capture_output=True, text=True, env=env)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertTrue(out.stdout.isascii())
            answer = json.loads(out.stdout.rsplit("@@talpy-den@@", 1)[-1])
            names = [c["name"] for g in answer["groups"] for c in g["recent"]]
            self.assertIn("Fix the \ud83d", names)

    @unittest.skipIf(sys.version_info < (3, 8), "3.7 has no pycache_prefix")
    def test_compiled_code_is_never_kept_in_the_cache(self):
        # (a container given ~/.cache could put code there that a check ran here)
        data = self.home / ".local/share"
        env = {**os.environ, "HOME": str(self.home), "XDG_CACHE_HOME": str(self.cache), "XDG_DATA_HOME": str(data)}
        out = subprocess.run([sys.executable, "-I", str(ROOT / "package/contents/code/poll.py"), "--no-tokens"],
                             capture_output=True, text=True, env=env)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(list(self.cache.rglob("*.pyc")), [])
        self.assertTrue(list((data / "talpy-den/pycache").rglob("talpy_den.*.pyc")))


class ContentFileTests(Fixture):
    """Files a repository or a chat can name: read only when plain files, at
    most so much, however deep their JSON."""

    def test_settings_linked_to_a_device_or_a_pipe_arent_read(self):
        d = self.home / "repos/evil/.claude"
        d.mkdir(parents=True)
        os.symlink("/dev/null", d / "settings.json")  # (/dev/zero in the proof: no test of that here, it would take the memory)
        os.mkfifo(d / "settings.local.json")
        dirs = cs.PlanDirs(self.cache / "plan-dirs.json", save=False)
        self.assertEqual([dirs.setting(str(d / n)) for n in ("settings.json", "settings.local.json")], [(False, None)] * 2)

    def test_a_git_file_that_is_a_pipe_isnt_read(self):
        proj, worktree = self.home / "Downloads/proj", self.home / "Downloads/wt"
        proj.mkdir(parents=True)
        os.mkfifo(proj / ".git")
        self.assertEqual(cs.main_repository(proj), proj)
        (worktree / "gitdir").mkdir(parents=True)
        write(worktree / ".git", "gitdir: gitdir\n")
        os.mkfifo(worktree / "gitdir/commondir")
        self.assertEqual(cs.canonical_git_root(str(worktree)), str(worktree))
        self.assertEqual(cs.main_repository(worktree), worktree)

    def test_json_nested_deeper_than_python_reads_is_skipped(self):
        deep = '{"x": ' + "[" * 200000 + "]" * 200000 + "}"
        write(self.home / "repos/app/.claude/settings.local.json", deep)
        self.assertIsNone(cs.read_json(self.home / "repos/app/.claude/settings.local.json"))
        title = '{"type":"ai-title","aiTitle":"Deep one"}\n'
        prompt = json.dumps({"type": "user", "cwd": "/tmp/x", "message": {"content": "go"}}) + "\n"
        reply = json.dumps({"type": "assistant", "cwd": "/tmp/x", "message": {"content": [{"type": "text", "text": "ok"}]}})
        write(self.home / ".claude-work/projects/-tmp-x/deep.jsonl", title + prompt + deep + "\n" + reply + "\n")
        result = self.collect()
        self.assertNotIn("recent chats", " ".join(result.get("errors") or []))
        self.assertIn("Deep one", [c["name"] for g in result["groups"] for c in g["recent"]])


class StateTests(Fixture):
    def test_what_talpy_den_acts_on_is_kept_out_of_the_cache(self):
        # (a container given ~/.cache could queue a task there, or change the settings every copy takes)
        write(self.cache / "queue.json", {"tasks": [{"id": "task1", "prompt": "mine"}]})
        write(self.cache / "settings.json", {"at": 1, "by": "x", "values": {"usageCap": 80}})
        self.assertEqual([t["id"] for t in cs.load_queue(self.cache)], ["task1"])  # (moved over, once)
        self.assertEqual(cs.shared_settings(self.cache)["values"], {"usageCap": 80})
        self.assertFalse((self.cache / "queue.json").exists() or (self.cache / "settings.json").exists())
        write(self.cache / "queue.json", {"tasks": [{"id": "task2", "prompt": "planted"}]})
        cs._STATE.clear()  # (as a new check)
        self.assertEqual([t["id"] for t in cs.load_queue(self.cache)], ["task1"])
        self.assertEqual(oct(cs.state_dir(self.cache).stat().st_mode & 0o777), "0o700")
        fresh = Path(self.tmp.name) / "fresh/.cache/talpy-den"  # (nothing kept yet: one put there later isn't taken either)
        cs.state_dir(fresh)
        write(fresh / "keep.json", {"chats": [{"chat": "planted"}]})
        cs._STATE.clear()
        self.assertEqual(cs.load_keep(fresh)["chats"], [])


class RecentProjectTests(Fixture):
    def test_newest_first_skipping_gone_and_scratch_folders(self):
        real_a, real_b = self.home / "repos/a", self.home / "repos/b"
        real_a.mkdir(parents=True)
        real_b.mkdir(parents=True)
        scratch = self.home / ".claude-work/jobs/x/tmp/proj"
        scratch.mkdir(parents=True)
        lines = [{"project": str(real_a), "timestamp": 1000}, {"project": str(real_b), "timestamp": 3000},
                 {"project": str(self.home / "gone"), "timestamp": 4000}, {"project": str(scratch), "timestamp": 5000},
                 {"project": str(real_a), "timestamp": 2000}]
        write(self.home / ".claude-work/history.jsonl", "\n".join(json.dumps(l) for l in lines) + "\n")
        work = self.group(self.collect(with_tokens=False), "work")
        self.assertEqual([p["short"] for p in work["projects"]], ["~/repos/b", "~/repos/a"])
        self.assertEqual(work["chatProfile"], ".claude-work")


class DismissTests(Fixture):
    def test_hidden_while_done_back_when_active(self):
        cs.private_dir(self.cache)
        now = int(self.now * 1000)
        cs.save_dismissed(self.cache, {"bgdone": now, "busy": now, "gone": now, "long-gone": now - cs.DISMISSED_KEEP_MS - 1})
        r = self.collect(with_tokens=False)
        shown = {s["sessionId"] for g in r["groups"] for s in g["sessions"]}
        self.assertNotIn("bgdone", shown)              # finished: hidden
        self.assertIn("busy", shown)                   # working: never hidden
        self.assertEqual((r["dismissed"], r["counts"]["done"]), (1, 0))
        # one that's active again is forgotten; one not listed now may be by
        # another copy of the script (other settings): forgotten after a while
        self.assertEqual(set(cs.load_dismissed(self.cache)), {"bgdone", "gone"})

    def test_removing_while_a_check_runs(self):
        cs.private_dir(self.cache)
        cs.save_dismissed(self.cache, {"busy": int(self.now * 1000)})
        real, landed = cs.load_dismissed, []
        def load_then_remove(root):  # jump.py --dismiss lands right after the check read the file
            sessions = real(root)
            if not landed:
                landed.append(True)
                with mock.patch.object(cs, "load_dismissed", real):
                    cs.change_dismissed(root, add="bgdone")
            return sessions
        with mock.patch.object(cs, "load_dismissed", load_then_remove):
            self.collect(with_tokens=False)
        self.assertEqual(set(cs.load_dismissed(self.cache)), {"bgdone"})


class SharedChatTests(Fixture):
    """A chat shared across profiles = one transcript hard-linked into each."""

    def setUp(self):
        super().setUp()
        work = self.home / ".claude-work/projects/-w-proj"
        personal = self.home / ".claude-personal/projects/-w-proj"
        write(work / "busy.jsonl", assistant("m-shared", self.now - 30, 7) + "\n")
        personal.mkdir(parents=True)
        os.link(work / "busy.jsonl", personal / "busy.jsonl")
        write(work / "waiting.jsonl", assistant("m-own", self.now - 30, 5) + "\n")   # not shared
        self.state = Path(self.tmp.name) / "state"
        os.environ["XDG_STATE_HOME"] = str(self.state)
        self.addCleanup(os.environ.pop, "XDG_STATE_HOME")

    def sessions(self):
        r = self.collect()
        return {s["sessionId"]: s for s in self.group(r, "work")["sessions"]}, r

    def test_shared_flag_and_holder(self):
        write(self.state / "claude-shared-chats" / "lock-busy",
              f"{os.getpid()}-{cs.proc_start_time(os.getpid())} {self.home / '.claude-personal'}\n")
        by_id, _ = self.sessions()
        self.assertEqual(by_id["busy"]["shared"], {"profiles": ["work", "personal"], "openIn": "personal"})
        self.assertIsNone(by_id["waiting"]["shared"])

    def test_dead_holder_is_ignored(self):
        write(self.state / "claude-shared-chats" / "lock-busy", "4194311-1 /nowhere\n")
        by_id, _ = self.sessions()
        self.assertEqual(by_id["busy"]["shared"]["openIn"], None)

    def test_tokens_report_the_shared_part(self):
        _, r = self.sessions()
        today = self.group(r, "work")["tokens"]["today"]
        self.assertEqual((today["messages"], today["shared"]), (2, 2 + 7 + 100 + 10))


class SharedCopiesTests(Fixture):
    def setUp(self):
        super().setUp()
        work = self.home / ".claude-work/projects/-w-proj"
        personal = self.home / ".claude-personal/projects/-w-proj"
        write(personal / "chat1.jsonl", assistant("m1", self.now - 30, 1) + "\n")
        work.mkdir(parents=True, exist_ok=True)
        os.link(personal / "chat1.jsonl", work / "chat1.jsonl")              # a shared chat
        os.environ["XDG_STATE_HOME"] = str(Path(self.tmp.name) / "state")
        self.addCleanup(os.environ.pop, "XDG_STATE_HOME")

    def test_stopped_copy_left_out_when_listed_elsewhere(self):
        write(self.home / ".claude-personal/sessions/50.json", session("chat1", status="busy"))
        write(self.home / ".claude-work/jobs/chat1/state.json",
              {"state": "stopped", "tempo": "idle", "sessionId": "chat1", "updatedAt": iso(self.now - 600)})
        r = self.collect(with_tokens=False)
        rows = [(g["name"], s["sessionId"]) for g in r["groups"] for s in g["sessions"] if s["sessionId"] == "chat1"]
        self.assertEqual(rows, [("personal", "chat1")])
        kept = next(s for s in self.group(r, "personal")["sessions"] if s["sessionId"] == "chat1")
        self.assertEqual(kept["shared"]["stoppedCopies"], ["work"])
        # work points to it instead
        here = self.group(r, "work")["sharedHere"]
        self.assertEqual([(c["sessionId"], c["profile"], c["state"], c["stoppedHere"]) for c in here],
                         [("chat1", "personal", "working", True)])
        self.assertEqual(self.group(r, "personal")["sharedHere"], [])

    def test_job_waiting_at_a_limit_left_out_while_the_chat_runs_elsewhere(self):
        write(self.home / ".claude-personal/sessions/50.json", session("chat1", status="busy"))
        write(self.home / ".claude-work/jobs/chat1/state.json",
              {"state": "blocked", "tempo": "blocked", "sessionId": "chat1", "updatedAt": iso(self.now - 600)})
        r = self.collect(with_tokens=False)
        rows = [(g["name"], s["sessionId"]) for g in r["groups"] for s in g["sessions"] if s["sessionId"] == "chat1"]
        self.assertEqual(rows, [("personal", "chat1")])
        self.assertEqual([c["sessionId"] for c in self.group(r, "work")["sharedHere"]], ["chat1"])

    def test_record_left_behind_when_kept_only_on_another_account(self):
        # A background chat of personal, shared, then kept only on work: the
        # transcript left personal, its finished background record didn't
        write(self.home / ".claude-work/projects/-w-proj/chat2.jsonl", assistant("m2", self.now - 30, 1) + "\n")
        write(self.home / ".claude-personal/jobs/chat2/state.json",
              {"state": "stopped", "tempo": "idle", "sessionId": "chat2", "updatedAt": iso(self.now - 600)})
        r = self.collect(with_tokens=False)
        self.assertEqual([g["name"] for g in r["groups"] for s in g["sessions"] if s["sessionId"] == "chat2"], [])
        # one with no transcript anywhere yet (just started) is still listed
        write(self.home / ".claude-personal/jobs/fresh/state.json",
              {"state": "stopped", "tempo": "idle", "sessionId": "fresh", "updatedAt": iso(self.now - 600)})
        r = self.collect(with_tokens=False)
        self.assertIn("fresh", [s["sessionId"] for s in self.group(r, "personal")["sessions"]])

    def test_shared_chat_points_from_the_other_account(self):
        write(self.home / ".claude-personal/sessions/50.json", session("chat1", status="busy"))
        r = self.collect(with_tokens=False)
        self.assertNotIn("chat1", [s["sessionId"] for s in self.group(r, "work")["sessions"]])
        here = self.group(r, "work")["sharedHere"]
        self.assertEqual([(c["sessionId"], c["profileDir"], c["stoppedHere"]) for c in here],
                         [("chat1", ".claude-personal", False)])

    def test_background_session_continuing_the_chat_is_that_chat(self):
        # Resumed as a background session on work: new id, but it wrote into the
        # shared transcript; its own file only got a title
        write(self.home / ".claude-personal/sessions/50.json", session("chat1", status="busy"))
        write(self.home / ".claude-work/projects/-w-proj/cont1.jsonl",
              json.dumps({"type": "ai-title", "aiTitle": "t", "sessionId": "cont1"}) + "\n")
        write(self.home / ".claude-work/jobs/cont1/state.json",
              {"state": "stopped", "tempo": "idle", "sessionId": "cont1", "resumeSessionId": "chat1",
               "updatedAt": iso(self.now - 600)})
        r = self.collect(with_tokens=False)
        self.assertNotIn("cont1", [s["sessionId"] for s in self.group(r, "work")["sessions"]])
        kept = next(s for s in self.group(r, "personal")["sessions"] if s["sessionId"] == "chat1")
        self.assertEqual(kept["shared"]["stoppedCopies"], ["work"])
        self.assertEqual([c["sessionId"] for c in self.group(r, "work")["sharedHere"]], ["chat1"])

    def continued_in(self, new_id):
        with open(self.home / ".claude-personal/projects/-w-proj/chat1.jsonl", "a") as f:
            f.write(json.dumps({"type": "continued-in", "sessionId": "chat1", "continuedInSessionId": new_id},
                               separators=(",", ":")) + "\n")

    def test_continuation_found_by_the_chats_continued_in_record(self):
        # The job names itself in resumeSessionId; only the chat's transcript links them
        write(self.home / ".claude-work/jobs/chat1/state.json",
              {"state": "stopped", "tempo": "idle", "sessionId": "chat1", "updatedAt": iso(self.now - 3000)})
        write(self.home / ".claude-personal/projects/-w-proj/cont1.jsonl",
              json.dumps({"type": "ai-title", "aiTitle": "t", "sessionId": "cont1"}) + "\n")
        write(self.home / ".claude-personal/jobs/cont1/state.json",
              {"state": "stopped", "tempo": "idle", "sessionId": "cont1", "resumeSessionId": "cont1",
               "updatedAt": iso(self.now - 240)})
        self.continued_in("cont1")
        r = self.collect(with_tokens=False)
        kept = [(g["name"], s["sessionId"]) for g in r["groups"] for s in g["sessions"] if s["sessionId"] in ("chat1", "cont1")]
        self.assertEqual(kept, [("personal", "cont1")])   # one row for the chat, the newest
        cont = next(s for s in self.group(r, "personal")["sessions"] if s["sessionId"] == "cont1")
        self.assertEqual((cont["shared"]["continues"], cont["shared"]["stoppedCopies"]), ("chat1", ["work"]))
        self.assertEqual([c["sessionId"] for c in self.group(r, "work")["sharedHere"]], ["cont1"])
        self.assertEqual(self.group(r, "personal")["sharedHere"], [])

    def test_continuation_that_started_a_new_conversation_is_its_own_chat(self):
        write(self.home / ".claude-work/projects/-w-proj/new1.jsonl", assistant("m2", self.now - 30, 1) + "\n")
        write(self.home / ".claude-work/jobs/job1/state.json",
              {"state": "stopped", "tempo": "idle", "sessionId": "job1", "resumeSessionId": "new1",
               "updatedAt": iso(self.now - 60)})
        write(self.home / ".claude-work/sessions/60.json", {**session("new1", status="busy"), "kind": "bg", "jobId": "job1"})
        self.continued_in("job1")
        r = self.collect(with_tokens=False)
        new = next(s for s in self.group(r, "work")["sessions"] if s["sessionId"] == "new1")
        self.assertIsNone(new["shared"])

    def test_no_pointer_where_a_fork_is_listed(self):
        write(self.home / ".claude-personal/sessions/50.json", session("chat1", status="busy"))
        write(self.home / ".claude-work/projects/-w-proj/fork1.jsonl", assistant("m2", self.now - 30, 1) + "\n")
        write(self.home / ".claude-work/jobs/fork1/state.json",
              {"state": "stopped", "tempo": "idle", "sessionId": "fork1", "resumeSessionId": "chat1",
               "updatedAt": iso(self.now - 600)})
        r = self.collect(with_tokens=False)
        self.assertEqual(self.group(r, "work")["sharedHere"], [])
        self.assertEqual(self.group(r, "personal")["sharedHere"], [])   # a fork isn't shared itself

    def test_fork_of_shared_chat_is_marked(self):
        write(self.home / ".claude-work/projects/-w-proj/fork1.jsonl", assistant("m2", self.now - 30, 1) + "\n")
        write(self.home / ".claude-work/jobs/fork1/state.json",
              {"state": "stopped", "tempo": "idle", "sessionId": "fork1", "resumeSessionId": "chat1",
               "updatedAt": iso(self.now - 600)})
        r = self.collect(with_tokens=False)
        fork = next(s for s in self.group(r, "work")["sessions"] if s["sessionId"] == "fork1")
        self.assertEqual((fork["shared"]["forkOf"], fork["shared"]["forkOn"]), ("chat1", "work"))


class OldPythonTests(unittest.TestCase):
    """talpy_den.py, sharing.py, accounts.py, week.py and the live hook also run on SSH hosts, whose python3 may be as old as 3.7
    (and dictate.py's tests run on the CI's Python 3.7 too)."""

    def test_no_syntax_or_calls_newer_than_37(self):
        for name in ("talpy_den.py", "sharing.py", "accounts.py", "week.py", "live_hook.py", "live.py", "dictate.py"):
            source = (ROOT / "package/contents/code" / name).read_text()
            # no := or f"{x=}" (3.7 itself parses only what it supports)
            tree = ast.parse(source, feature_version=(3, 7)) if sys.version_info >= (3, 8) else ast.parse(source)
            newer_methods = {"removeprefix", "removesuffix", "is_relative_to", "with_stem", "readlink", "hardlink_to"}
            newer_calls = {("shlex", "join"), ("functools", "cache"), ("functools", "cached_property"),
                           ("math", "prod"), ("math", "isqrt")}
            for node in ast.walk(tree):
                if isinstance(node, ast.keyword):
                    self.assertNotIn(node.arg, {"missing_ok", "strict"}, f"{name} line {node.value.lineno}: {node.arg}= needs a newer Python")
                if isinstance(node, ast.Attribute):
                    owner = getattr(node.value, "id", "")
                    if (owner, node.attr) != ("os", "readlink"):  # (Path.readlink is 3.9's, os.readlink old)
                        self.assertNotIn(node.attr, newer_methods, f"{name} line {node.lineno}: .{node.attr} needs a newer Python")
                    self.assertNotIn((owner, node.attr), newer_calls, f"{name} line {node.lineno}: {owner}.{node.attr} needs a newer Python")

class StatusCheckCostTests(unittest.TestCase):
    """What a status check (every 2 s) no longer redoes each time."""

    def test_day_sums_give_the_same_totals(self):
        from datetime import date, timedelta
        now = 1_800_000_000

        def day(n):
            return (date.fromtimestamp(now) - timedelta(days=n)).isoformat()
        messages = {"a": [day(0), "opus", 1, 2, 3, 4, 0], "b": [day(0), "opus", 5, 6, 7, 8, 1],
                    "c": [day(3), "sonnet", 10, 20, 0, 0, 0], "d": [day(9), "opus", 99, 99, 99, 99, 0]}
        from_messages = cs.token_totals([{"messages": messages}], now)  # a cache saved before the sums
        from_days = cs.token_totals([{"messages": {}, "days": cs.day_totals(messages), "scannedAt": 5, "daysAt": 5}],
                                    now)
        self.assertEqual(from_days, from_messages)
        # sums an older version didn't update when it rescanned: the messages count
        stale = cs.token_totals([{"messages": messages, "days": {}, "scannedAt": 6, "daysAt": 5}], now)
        self.assertEqual(stale, from_messages)
        self.assertEqual((from_days["today"]["messages"], from_days["today"]["shared"]), (2, 5 + 6 + 7 + 8))
        self.assertEqual(from_days["week"]["messages"], 3)  # day 9 is past the week

    def test_vscode_looked_up_at_most_every_30_seconds(self):
        calls = []
        real = cs.vscode_lookup
        cs.vscode_lookup = lambda home: calls.append(home) or (True, "/x/.claude-work")
        self.addCleanup(setattr, cs, "vscode_lookup", real)
        saved = os.environ.get("XDG_CONFIG_HOME")
        self.addCleanup(lambda: os.environ.__setitem__("XDG_CONFIG_HOME", saved) if saved is not None
                        else os.environ.pop("XDG_CONFIG_HOME", None))
        with tempfile.TemporaryDirectory() as tmp:
            home, cache = Path(tmp), Path(tmp) / "cache"
            os.environ["XDG_CONFIG_HOME"] = str(home / ".config")
            self.assertEqual(cs.cached_vscode_lookup(home, cache, 1000), (True, "/x/.claude-work"))
            self.assertEqual(cs.cached_vscode_lookup(home, cache, 1010), (True, "/x/.claude-work"))
            self.assertEqual(len(calls), 1)
            settings = home / ".config/Code/User/settings.json"
            settings.parent.mkdir(parents=True)
            settings.write_text("{}")  # a setting changed: looked up again at once
            cs.cached_vscode_lookup(home, cache, 1011)
            cs.cached_vscode_lookup(home, cache, 1012)
            self.assertEqual(len(calls), 2)
            cs.cached_vscode_lookup(home, cache, 1011 + cs.VSCODE_CHECK_INTERVAL)
            self.assertEqual(len(calls), 3)
            # VS Code just installed (a new file in a folder on PATH): looked up again at once
            saved_path = os.environ.get("PATH")
            self.addCleanup(os.environ.__setitem__, "PATH", saved_path or "")
            bin_dir = home / "bin"
            bin_dir.mkdir()
            os.environ["PATH"] = str(bin_dir)
            cs.cached_vscode_lookup(home, cache, 1050)
            cs.cached_vscode_lookup(home, cache, 1051)
            looked = len(calls)
            time.sleep(0.05)
            (bin_dir / "code").write_text("")
            cs.cached_vscode_lookup(home, cache, 1052)
            self.assertEqual(len(calls), looked + 1)


if __name__ == "__main__":
    unittest.main()


class TmuxFlagTests(Fixture):
    def test_rows_say_whether_a_chat_runs_in_tmux(self):
        write(self.home / ".claude-work/sessions/30.json", session("in-tmux", status="busy", tmux="main:@1.%4"))
        work = self.group(self.collect(with_tokens=False), "work")
        flag = {s["sessionId"]: s["tmux"] for s in work["sessions"]}
        self.assertEqual((flag["in-tmux"], flag["busy"]), (True, False))


class FakeAttach:
    """Claude's background service as Talpy Chat's Stop sees it: a Unix
    socket at its place (cs.DAEMON_TMP, patched to a folder of the test's),
    its attach line in, answer(request) as one line out; once that's ok, a
    bit of what the session shows (frame), and every byte that comes in after
    the line is kept in typed (what the session got as typed) till the
    client lets go. Its key is daemon/control.key in the profile."""

    KEY = "0123456789abcdef0123456789abcdef"

    def __init__(self, test, profile, answer, frame=b"\x1b[?1049h\x1b[H> working"):
        import socket
        import threading
        self.requests, self.typed, self.answer, self.frame = [], [], answer, frame
        self.done = threading.Event()
        root = Path(tempfile.mkdtemp(prefix="td-", dir="/tmp"))  # (a socket's path: at most 107 bytes)
        test.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        value = str(profile.path)
        for p in (mock.patch.object(cs, "DAEMON_TMP", root),
                  mock.patch.object(cs, "service_config_dir", side_effect=lambda q: value if q.path == profile.path else None)):
            p.start()
            test.addCleanup(p.stop)
        self.path = cs.daemon_socket(profile)
        self.path.parent.mkdir(parents=True)
        write(profile.path / "daemon/control.key", self.KEY + "\n")
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(str(self.path))
        self.server.listen(8)
        test.addCleanup(self.server.close)
        threading.Thread(target=self.serve, daemon=True).start()

    def serve(self):
        while True:
            try:
                conn, _ = self.server.accept()
            except OSError:
                return
            with conn:
                data = b""
                while b"\n" not in data:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    data += chunk
                line, _, typed = data.partition(b"\n")
                if not line:   # (a client that told it nothing)
                    continue
                self.requests.append(json.loads(line))
                answer = self.answer(self.requests[-1])
                conn.sendall((json.dumps(answer) + "\n").encode())
                if answer.get("ok"):
                    conn.sendall(self.frame)
                    while True:
                        chunk = conn.recv(65536)
                        if not chunk:
                            break
                        typed += chunk
                self.typed.append(typed)
                self.done.set()

    @staticmethod
    def takes_it(request):
        return {"ok": True, "op": "attach", "via": "pty", "booting": False, "tempo": "active", "state": "working",
                "cached": False, "stale": False, "workerCliVersion": "2.1.318"}


class BackgroundStopTests(Fixture):
    """Talpy Chat's Stop in a background chat: Claude's background service
    has no interrupt, so Talpy Den attaches to the session for a moment as
    `claude attach` does and types one Esc (checked live on Claude Code
    2.1.318: "[Request interrupted by user]", the chat stays). It attaches at
    the size the session's terminal has now, so a terminal that shows it
    isn't resized. Undocumented: only on the Claude Code versions it was
    checked on (no Stop button on another), and nothing is typed unless the
    service answers as expected."""

    def setUp(self):
        super().setUp()
        self.profile = next(p for p in cs.discover_profiles(self.home) if p.label == "work")
        self.entry = session("bgworking", kind="bg", status="busy", jobId="job3", version="2.1.318")
        for p in (mock.patch.object(cs, "tty_size", side_effect=lambda pid: (120, 40) if pid == PID else None),
                  mock.patch.object(cs, "cache_dir", return_value=self.cache)):
            p.start()
            self.addCleanup(p.stop)

    def test_the_claude_code_versions_it_was_checked_on(self):
        for version, known in (("2.1.318", True), ("2.1.330", True), ("2.1.317", False), ("2.2.0", False),
                               ("3.0.1", False), ("2.1.318-beta.1", False), ("", False), (None, False), (2, False)):
            self.assertEqual(cs.bg_stop_known(version), known, version)

    def test_rows_say_whether_stop_can_interrupt_a_background_chat(self):
        w = self.home / ".claude-work"
        write(w / "sessions/17.json", self.entry)
        write(w / "sessions/30.json", session("bg-old", kind="bg", status="busy", jobId="job6", version="2.1.300"))
        write(w / "sessions/31.json", session("term-new", status="busy", version="2.1.318"))
        rows = {s["sessionId"]: s for s in self.group(self.collect(with_tokens=False), "work")["sessions"]}
        self.assertEqual({sid: rows[sid]["bgStop"] for sid in ("bgworking", "bg-old", "term-new", "bgdone", "busy")},
                         {"bgworking": True, "bg-old": False, "term-new": False, "bgdone": False, "busy": False})

    def test_esc_goes_in_at_the_size_its_terminal_has_now(self):
        service = FakeAttach(self, self.profile, FakeAttach.takes_it)
        ok, message = cs.interrupt_background(self.profile, self.entry)
        self.assertTrue(ok, message)
        self.assertTrue(service.done.wait(5))
        (request,) = service.requests
        self.assertEqual({k: request[k] for k in ("proto", "op", "short", "auth", "cols", "rows")},
                         {"proto": 1, "op": "attach", "short": "job3", "auth": FakeAttach.KEY, "cols": 120, "rows": 40})
        self.assertRegex(request["attachId"], r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
        # (no theme of its own, and no browser: the session keeps its own)
        self.assertNotIn("systemTheme", request["caps"])
        self.assertNotIn("browser", request["caps"])
        self.assertEqual(service.typed, [b"\x1b"], "one Esc, nothing else")

    def test_one_stop_at_a_time(self):
        # (two Esc in a row open Claude's rewind menu: a second Stop within 2 s, from another
        # front end say, types nothing)
        service = FakeAttach(self, self.profile, FakeAttach.takes_it)
        self.assertTrue(cs.interrupt_background(self.profile, self.entry)[0])
        self.assertEqual(cs.interrupt_background(self.profile, self.entry), (False, "It was stopped a moment ago"))
        self.assertEqual(len(service.requests), 1)
        self.assertTrue(cs.stop_turn("job3", time.time() + cs.BG_STOP_GAP + 0.1))
        self.assertTrue(cs.stop_turn("other"))
        self.assertEqual(stat.S_IMODE((self.cache / "stops.json").stat().st_mode), 0o600)

    def test_nothing_is_typed_unless_it_works_on_a_version_it_knows(self):
        service = FakeAttach(self, self.profile, FakeAttach.takes_it)
        for entry, said in ((dict(self.entry, version="2.2.0"), "Claude Code 2.2.0"),
                            (dict(self.entry, version=None), "this Claude Code"),
                            (dict(self.entry, status="idle"), "nothing to stop"),
                            (dict(self.entry, status="waiting", waitingFor="permission prompt"), "nothing to stop"),
                            (dict(self.entry, status="shell"), "Its turn is over"),
                            (dict(self.entry, pid=os.getppid()), "size of its terminal"),
                            (dict(self.entry, jobId="../x"), "can't stop")):
            ok, message = cs.interrupt_background(self.profile, entry)
            self.assertFalse(ok, entry)
            self.assertIn(said, message)
        self.assertEqual(service.requests, [], "never attached")

    def test_nothing_is_typed_when_the_service_answers_otherwise(self):
        for answer, said in (({"ok": False, "error": "attach rejected: bad key", "code": "EAUTH"}, "attach rejected: bad key"),
                             ({"ok": True, "op": "has"}, "didn't take it"),
                             (dict(FakeAttach.takes_it({}), workerCliVersion="2.3.0"), "Claude Code 2.3.0"),
                             (dict(FakeAttach.takes_it({}), booting=True), "starting")):
            with self.subTest(answer=answer):
                service = FakeAttach(self, self.profile, lambda r, a=answer: a)
                ok, message = cs.interrupt_background(self.profile, self.entry)
                self.assertFalse(ok)
                self.assertIn(said, message)
                self.assertTrue(service.done.wait(5))
                self.assertEqual(service.typed, [b""])

    def test_no_service_no_key_or_another_users_socket(self):
        with mock.patch.object(cs, "service_config_dir", return_value=None):
            self.assertEqual(cs.interrupt_background(self.profile, self.entry),
                             (False, "Claude's background service can't be asked"))
        service = FakeAttach(self, self.profile, FakeAttach.takes_it)
        with mock.patch.object(cs, "peer_uid", return_value=os.getuid() + 1):
            self.assertEqual(cs.interrupt_background(self.profile, self.entry),
                             (False, "Claude's background service didn't answer"))
        (self.profile.path / "daemon/control.key").unlink()
        self.assertEqual(cs.interrupt_background(self.profile, self.entry),
                         (False, "Claude's background service can't be asked"))
        self.assertEqual(service.requests, [], "never told the key")

    def test_interrupt_by_id_types_esc_into_a_background_chat_and_ctrl_c_into_tmux(self):
        write(self.home / ".claude-work/sessions/17.json", self.entry)
        write(self.home / ".claude-work/sessions/30.json", session("in-tmux", status="busy", tmux="main:@1.%4"))
        calls = []
        with mock.patch.object(cs, "interrupt_background", side_effect=lambda p, e: calls.append((p.label, e["jobId"])) or (True, "bg")), \
                mock.patch.object(cs, "interrupt_chat", side_effect=lambda e: calls.append(("tmux", e["sessionId"])) or (True, "tmux")):
            self.assertEqual(cs.interrupt_chat_by_id(self.home, [], "bgworking", ".claude-work"), (True, "bg"))
            self.assertEqual(cs.interrupt_chat_by_id(self.home, [], "in-tmux"), (True, "tmux"))
            self.assertEqual(cs.interrupt_chat_by_id(self.home, [], "gone"), (False, "That chat isn't running any more"))
        self.assertEqual(calls, [("work", "job3"), ("tmux", "in-tmux")])



class TtySizeTests(unittest.TestCase):
    def test_the_size_of_a_process_terminal(self):
        # (read without touching what goes through it: what a Stop attaches at)
        import fcntl
        import struct
        import termios
        master, slave = os.openpty()
        self.addCleanup(os.close, master)
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
        proc = subprocess.Popen(["sleep", "30"], stdin=slave, stdout=subprocess.DEVNULL)
        os.close(slave)
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        plain = subprocess.Popen(["sleep", "30"], stdin=subprocess.DEVNULL)
        self.addCleanup(plain.wait)
        self.addCleanup(plain.kill)
        self.assertEqual(cs.tty_size(proc.pid), (120, 40))
        self.assertIsNone(cs.tty_size(plain.pid))   # (no terminal)
        self.assertIsNone(cs.tty_size(DEAD_PID))
        self.assertIsNone(cs.tty_size(None))


class SeveralWidgetsTests(unittest.TestCase):
    """A panel widget and one in the system tray: one of them notifies, and they share their settings."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "cache"

    def test_the_widget_running_longest_notifies(self):
        self.assertTrue(cs.elect_notifier(self.root, "panel", 2000, 1000))
        self.assertFalse(cs.elect_notifier(self.root, "tray", 2000, 1500))
        self.assertTrue(cs.elect_notifier(self.root, "panel", 2000, 3000))
        # the panel's widget is gone: after 3 of its check intervals and some grace, the tray's takes over
        self.assertFalse(cs.elect_notifier(self.root, "tray", 2000, 3000 + 3 * 2000 + cs.INSTANCE_GRACE_MS))
        self.assertTrue(cs.elect_notifier(self.root, "tray", 2000, 3001 + 3 * 2000 + cs.INSTANCE_GRACE_MS))
        # one that checks rarely (nothing runs) isn't counted out early
        self.assertFalse(cs.elect_notifier(self.root, "old", 60000, 0) and False)
        root = Path(self.tmp.name) / "other"
        cs.elect_notifier(root, "slow", 60000, 0)
        self.assertFalse(cs.elect_notifier(root, "fast", 2000, 150000))   # 2.5 min later: slow still counts

    def test_a_copy_noted_before_the_clock_was_set_back_has_gone_too(self):
        hour = 3600_000
        self.assertTrue(cs.elect_notifier(self.root, "panel", 2000, 100 * hour))
        self.assertFalse(cs.elect_notifier(self.root, "tray", 2000, 100 * hour + 2000))
        # the clock goes back 6 hours and the panel's widget is closed: its note is "from the
        # future" and mustn't keep the tray's widget from notifying until the clock catches up
        self.assertTrue(cs.elect_notifier(self.root, "tray", 2000, 94 * hour))
        self.assertTrue(cs.elect_notifier(self.root, "tray", 2000, 94 * hour + 2000))

    def test_settings_are_shared(self):
        defaults = cs.config_defaults()
        self.assertEqual((defaults["pollInterval"], defaults["showPet"], defaults["sshHosts"]), (2000, True, ""))
        self.assertIsNone(cs.shared_settings(self.root))
        # a widget nobody set up yet mustn't replace what the others use
        self.assertEqual(cs.save_shared_settings(self.root, "tray", dict(defaults), 1000, unless_default=True),
                         (False, "Nothing set up yet"))
        self.assertIsNone(cs.shared_settings(self.root))
        values = dict(defaults, sshHosts="lab", bogus=1)
        self.assertTrue(cs.save_shared_settings(self.root, "panel", values, 2000, unless_default=True)[0])
        shared = cs.shared_settings(self.root)
        self.assertEqual((shared["at"], shared["by"], shared["values"]["sshHosts"]), (2000, "panel", "lab"))
        self.assertNotIn("bogus", shared["values"])
        self.assertEqual(oct((cs.state_dir(self.root) / "settings.json").stat().st_mode & 0o777), "0o600")

    def test_through_the_status_check(self):
        home = Path(self.tmp.name) / "home"
        (home / ".claude/sessions").mkdir(parents=True)
        env = dict(os.environ, HOME=str(home), XDG_CACHE_HOME=str(Path(self.tmp.name)))
        run = lambda *a: json.loads(subprocess.run([sys.executable, "-I", str(ROOT / "package/contents/code/talpy_den.py"),
                                                    "--no-tokens", *a], capture_output=True, text=True, env=env).stdout)
        jobs = Path(self.tmp.name) / "talpy-den/jobs.json"   # (another home than this account's: in its cache)
        self.assertNotIn("notifier", run())   # GNOME and VS Code: one copy, no question
        self.assertFalse(jobs.exists())   # (not the copy that does the computer's work: it doesn't write the jobs file)
        first = run("--instance", "12/3", "--interval-ms", "2000")
        self.assertEqual((first["notifier"], first["sharedSettings"]), (True, None))
        self.assertEqual(json.loads(jobs.read_text())["jobs"], [])   # (the one that notifies does; no chats here)
        self.assertFalse(run("--instance", "40/1", "--interval-ms", "2000")["notifier"])
        jump = [sys.executable, "-I", str(ROOT / "package/contents/code/jump.py")]
        out = subprocess.run(jump + ["--save-settings", json.dumps({"sshHosts": "lab"}), "--by", "12/3"],
                             capture_output=True, text=True, env=env).stdout
        self.assertTrue(json.loads(out)["ok"], out)
        shared = run("--instance", "40/1")["sharedSettings"]
        self.assertEqual((shared["by"], shared["values"]), ("12/3", {"sshHosts": "lab"}))


class JobsFileTests(unittest.TestCase):
    """This computer's chats and their states, for other programs: a status bar, a desk display."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "run/talpy-den/jobs.json"
        self.groups = [
            {"name": "work", "sessions": [
                {"key": ".claude-work/s1/live", "name": "Fix the parser", "state": "waiting", "since": 1000,
                 "cwdShort": "~/app", "peek": "a secret prompt", "waitingFor": "Bash(rm -rf secret)"},
                {"key": ".claude-work/s2/job", "name": "", "state": "idle", "since": 2000, "cwdShort": "~/docs"}]},
            {"name": "personal", "sessions": [
                {"key": ".claude-personal/s3/live", "name": "Release notes", "state": "done", "since": 3000,
                 "cwdShort": "~/site"}]}]

    def test_only_what_a_status_shows(self):
        self.assertTrue(cs.publish_jobs(self.path, self.groups, 5000))
        self.assertEqual(json.loads(self.path.read_text()), {"version": 1, "updatedAt": 5000, "jobs": [
            {"id": ".claude-work/s1/live", "name": "Fix the parser", "state": "waiting", "since": 1000,
             "account": "work", "folder": "~/app"},
            {"id": ".claude-work/s2/job", "name": "", "state": "idle", "since": 2000,
             "account": "work", "folder": "~/docs"},
            {"id": ".claude-personal/s3/live", "name": "Release notes", "state": "done", "since": 3000,
             "account": "personal", "folder": "~/site"}]})
        self.assertNotIn("secret", self.path.read_text())   # (no prompts, nor what a chat asks)
        self.assertEqual(oct(self.path.stat().st_mode & 0o777), "0o600")
        self.assertEqual(oct(self.path.parent.stat().st_mode & 0o777), "0o700")

    def test_written_again_only_when_a_chat_changes(self):
        cs.publish_jobs(self.path, self.groups, 5000)
        first = self.path.stat()
        self.assertFalse(cs.publish_jobs(self.path, self.groups, 6000))   # the same: no new file, so no event
        self.assertEqual((self.path.stat().st_ino, json.loads(self.path.read_text())["updatedAt"]),
                         (first.st_ino, 5000))
        self.groups[0]["sessions"][0].update(state="working", since=5500)
        self.assertTrue(cs.publish_jobs(self.path, self.groups, 7000))
        self.assertNotEqual(self.path.stat().st_ino, first.st_ino)   # a new file renamed over it (IN_MOVED_TO)
        self.assertEqual(json.loads(self.path.read_text())["jobs"][0]["state"], "working")
        self.assertEqual([p.name for p in self.path.parent.iterdir()], ["jobs.json"])   # (no temporary file left)
        self.groups[0]["sessions"].pop()   # a chat that's gone
        self.assertTrue(cs.publish_jobs(self.path, self.groups, 8000))
        self.assertEqual(len(json.loads(self.path.read_text())["jobs"]), 2)

    def test_in_your_runtime_folder(self):
        import pwd
        runtime, cache = Path(self.tmp.name) / "run", Path(self.tmp.name) / "cache"
        runtime.mkdir()
        own = Path(pwd.getpwuid(os.getuid()).pw_dir)
        with mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(runtime)}):
            self.assertEqual(cs.jobs_file_path(own, cache), runtime / "talpy-den/jobs.json")
            # another home than your account's (a sandbox, the tests): in its own cache folder
            self.assertEqual(cs.jobs_file_path(Path(self.tmp.name) / "home", cache), cache / "jobs.json")
        with mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(runtime / "gone")}):
            self.assertEqual(cs.jobs_file_path(own, cache), cache / "jobs.json")
        with mock.patch.dict(os.environ):
            os.environ.pop("XDG_RUNTIME_DIR", None)
            self.assertEqual(cs.jobs_file_path(own, cache), cache / "jobs.json")


def chat_line(kind, content, msg_id=None, stop=None, ts=None, **kw):
    """A transcript entry: a prompt or tool result (user), or one block of a reply (assistant)."""
    message = {"role": kind, "content": content}
    if msg_id:
        message["id"] = msg_id
    if stop:
        message["stop_reason"] = stop
    return {"type": kind, "timestamp": iso(ts or time.time()), "message": message, **kw}


def tool_use(name, inp, i="toolu_1"):
    return {"type": "tool_use", "id": i, "name": name, "input": inp}


class PeekTests(Fixture):
    """What a chat is doing and what it said last, from the end of its transcript."""

    def transcript(self, sid, entries, profile=".claude-work"):
        path = self.home / profile / "projects/-w-proj" / f"{sid}.jsonl"
        write(path, "\n".join(e if isinstance(e, str) else json.dumps(e) for e in entries) + "\n")
        return path

    def peek(self, sid="busy"):
        work = self.group(self.collect(with_tokens=False), "work")
        return next(s for s in work["sessions"] if s["sessionId"] == sid)["peek"]

    def test_working_on_a_tool(self):
        self.transcript("busy", [
            chat_line("user", "fix the parser"),
            chat_line("assistant", [{"type": "thinking", "thinking": ""}], "m1"),
            chat_line("assistant", [{"type": "text", "text": "Let me run the tests."}], "m1"),
            chat_line("assistant", [tool_use("Bash", {"command": "pytest -x"})], "m1"),
        ])
        p = self.peek()
        self.assertEqual((p["activity"], p["prompt"], p["reply"]), ("Bash: pytest -x", "fix the parser", "Let me run the tests."))
        self.assertEqual(p["replyLine"], "Let me run the tests.")

    def test_thinking_about_a_tool_result(self):
        self.transcript("busy", [
            chat_line("user", "fix the parser"),
            chat_line("assistant", [tool_use("Read", {"file_path": "/w/proj/parser.py"})], "m1", "tool_use"),
            chat_line("user", [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "..."}]),
        ])
        p = self.peek()
        self.assertEqual((p["activity"], p["prompt"], p["reply"]), ("Read: parser.py (thinking about the result)", "fix the parser", ""))

    def test_finished_reply_in_several_blocks(self):
        self.transcript("busy", [
            chat_line("user", "fix the parser"),
            chat_line("assistant", [{"type": "text", "text": "Older step."}], "m1", "tool_use"),
            chat_line("assistant", [tool_use("Bash", {"command": "make"})], "m1", "tool_use"),
            chat_line("user", [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "ok"}]),
            chat_line("assistant", [{"type": "thinking", "thinking": ""}], "m2", "end_turn"),
            chat_line("assistant", [{"type": "text", "text": "## Fixed\n\n\n\nThe parser **works** now."}], "m2", "end_turn"),
            chat_line("assistant", [{"type": "text", "text": "Want me to commit?"}], "m2", "end_turn"),
        ])
        p = self.peek()
        self.assertEqual(p["activity"], "")
        self.assertEqual(p["reply"], "Fixed\n\nThe parser works now.\n\nWant me to commit?")
        self.assertEqual(p["replyLine"], "Fixed")

    def test_markdown_read_as_plain_text(self):
        self.assertEqual(cs.plain_text("## Plan\n- run `make`\n  * then **ship** it\n```sh\nmake\n```\n3 * 4 = 12"),
                         "Plan\n• run make\n  • then ship it\nmake\n3 * 4 = 12")

    def test_no_old_reply_after_a_new_prompt(self):
        self.transcript("busy", [
            chat_line("user", "first"),
            chat_line("assistant", [{"type": "text", "text": "Done with the first."}], "m1", "end_turn"),
            chat_line("user", [{"type": "text", "text": "now the second"}]),
        ])
        p = self.peek()
        self.assertEqual((p["activity"], p["prompt"], p["reply"]), ("thinking…", "now the second", ""))

    def test_own_notes_are_not_prompts(self):
        self.transcript("busy", [
            chat_line("user", "the real question"),
            chat_line("assistant", [{"type": "text", "text": "The answer."}], "m1", "end_turn"),
            chat_line("user", "<local-command-stdout>Set model</local-command-stdout>"),
            chat_line("user", "Caveat: generated by a command", isMeta=True),
            chat_line("user", [{"type": "text", "text": "[Request interrupted by user]"}]),
        ])
        p = self.peek()
        self.assertEqual((p["prompt"], p["reply"]), ("the real question", "The answer."))

    def test_reads_further_back_past_big_lines(self):
        big = "x" * (cs.PEEK_TAIL_BYTES + 1000)
        self.transcript("busy", [
            chat_line("user", "summarize the log"),
            chat_line("assistant", [tool_use("Read", {"file_path": "/w/log.txt"})], "m1", "tool_use"),
            chat_line("user", [{"type": "tool_result", "tool_use_id": "toolu_1", "content": big}]),
            chat_line("assistant", [{"type": "text", "text": "It's mostly x."}], "m2", "end_turn"),
        ])
        p = self.peek()
        self.assertEqual((p["prompt"], p["reply"]), ("summarize the log", "It's mostly x."))

    def test_last_prompt_record_saves_reading_everything(self):
        big = "x" * (cs.PEEK_TAIL_MAX + 1000)
        self.transcript("busy", [
            chat_line("user", "summarize the log"),
            chat_line("user", [{"type": "tool_result", "tool_use_id": "toolu_1", "content": big}]),
            chat_line("assistant", [{"type": "text", "text": "It's mostly x."}], "m2", "end_turn"),
            {"type": "last-prompt", "lastPrompt": "summarize the log", "sessionId": "busy"},
        ])
        p = self.peek()
        self.assertEqual((p["prompt"], p["reply"]), ("summarize the log", "It's mostly x."))

    def test_unchanged_transcript_is_not_read_again(self):
        path = self.transcript("busy", [chat_line("user", "hi"),
                                        chat_line("assistant", [{"type": "text", "text": "Hello."}], "m1", "end_turn")])
        calls = []
        real = cs.chat_peek
        cs.chat_peek = lambda p: calls.append(p) or real(p)
        try:
            self.assertEqual(self.peek()["reply"], "Hello.")
            self.assertEqual(self.peek()["reply"], "Hello.")
            self.assertEqual(len(calls), 1)
            with open(path, "a") as f:
                f.write(json.dumps(chat_line("user", "again")) + "\n")
            self.assertEqual(self.peek()["prompt"], "again")
            self.assertEqual(len(calls), 2)
        finally:
            cs.chat_peek = real

    def test_no_transcript_no_peek(self):
        self.assertIsNone(self.peek("waiting"))


class ChangedFilesTests(Fixture):
    """The files a chat changed, from the backups Claude records before it edits them."""

    def setUp(self):
        super().setUp()
        self.proj = "/tmp/proj-busy"  # the busy session's folder (Fixture)
        self.path = self.home / ".claude-work/projects/-w-proj/busy.jsonl"
        self.lines = []

    def add(self, *entries):
        self.lines += [json.dumps(e) for e in entries]
        write(self.path, "\n".join(self.lines) + "\n")

    def snapshot(self, mid, files, update=False):
        return {"type": "file-history-snapshot", "messageId": mid, "isSnapshotUpdate": update,
                "snapshot": {"messageId": mid, "trackedFileBackups": files}}

    def delta(self, snap, rel, name, version=1):
        parent = os.path.dirname(os.path.join(self.proj, rel))
        return {"type": "file-history-delta", "snapshotMessageId": snap, "trackingPath": rel,
                "backup": {"backupFileName": name, "version": version, "realParentDir": parent}}

    def changes(self):
        work = self.group(self.collect(with_tokens=False), "work")
        return next(s for s in work["sessions"] if s["sessionId"] == "busy")["changes"]

    def test_backed_up_created_and_edited_files(self):
        plans = str(self.home / ".claude-work/plans/plan.md")
        self.add(
            self.snapshot("p1", {}),
            chat_line("user", "go", uuid="p1"),
            self.delta("p1", "src/parser.py", "aaa@v1"),
            self.delta("p1", "src/new.py", None),
            chat_line("assistant", [tool_use("Edit", {"file_path": self.proj + "/README.md"}),
                                    tool_use("Write", {"file_path": plans})], "m1"),
            chat_line("assistant", [tool_use("Read", {"file_path": self.proj + "/only-read.py"})], "m2"),
        )
        sub = self.home / ".claude-work/projects/-w-proj/busy/subagents/agent-a1.jsonl"
        write(sub, json.dumps(chat_line("assistant", [tool_use("MultiEdit", {"file_path": self.proj + "/docs/guide.md"})], "s1")) + "\n")
        self.assertEqual(self.changes(), {"count": 4, "files": ["README.md", "docs/guide.md", "src/new.py", "src/parser.py"]})

    def test_appended_records_are_read_once(self):
        self.add(self.snapshot("p1", {}), self.delta("p1", "a.py", "a@v1"))
        self.assertEqual(self.changes()["count"], 1)
        rec = cs.ChatCache(self.cache / "chats.json").edits(self.path)
        self.assertEqual(set(rec["files"]), {self.proj + "/a.py"})
        self.add(self.delta("p1", "b.py", "b@v1"))
        self.assertEqual(self.changes()["files"], ["a.py", "b.py"])
        saved = json.loads((self.cache / "chats.json").read_text())["edits"]
        self.assertEqual([e["size"] for e in saved.values()], [self.path.stat().st_size])

    def test_first_backup_and_last_turn(self):
        a, b = self.proj + "/a.py", self.proj + "/b.py"
        self.add(
            self.snapshot("p1", {}),
            self.delta("p1", "a.py", "a@v1"),
            self.snapshot("p2", {"a.py": {"backupFileName": "a@v2", "version": 2, "realParentDir": self.proj}}),
            self.delta("p2", "b.py", None),
        )
        rec = cs.chat_edits(self.path)
        self.assertEqual(rec["files"], {a: ["a@v1", 1], b: [None, 1]})
        self.assertEqual((rec["snap"], rec["snapFiles"], rec["turn"]), ("p2", {a: "a@v2"}, {b: None}))
        self.assertIn("busy", rec["sessions"])

    def test_older_snapshot_updates(self):
        a = self.proj + "/a.py"
        self.add(self.snapshot("p1", {}),
                 self.snapshot("p1", {"a.py": {"backupFileName": "a@v1", "version": 1, "realParentDir": self.proj}}, update=True))
        rec = cs.chat_edits(self.path)
        self.assertEqual((rec["files"], rec["turn"]), ({a: ["a@v1", 1]}, {a: "a@v1"}))

    def test_no_edits_no_changes(self):
        self.add(chat_line("user", "hi"))
        self.assertIsNone(self.changes())


class ForecastTests(unittest.TestCase):
    """Where a plan window is heading at your pace."""

    H = 3600_000

    def window(self, pct, resets_in_h, key="five_hour"):
        self.now = 10_000 * self.H
        return {"key": key, "pct": pct, "resetsAt": self.now + int(resets_in_h * self.H), "reset": False}

    def test_window_pace_without_history(self):
        w = self.window(40, 3)  # 2 h into the window, 20 %/h
        f = cs.usage_forecast(w, [], self.now)
        self.assertEqual((f["basis"], f["rate"], f["evenPct"]), ("window", 20.0, 40.0))
        self.assertEqual(f["atReset"], 100.0)
        self.assertIsNone(f["fullAt"])  # exactly at the reset: not before it

    def test_last_hours_pace_runs_out_first(self):
        w = self.window(60, 2)
        points = [[self.now - 2 * self.H, 20], [self.now - self.H - 1, 30], [self.now - 600_000, 55]]
        f = cs.usage_forecast(w, points, self.now)
        self.assertEqual((f["basis"], f["rate"]), ("hour", 30.0))
        self.assertAlmostEqual(f["fullAt"], self.now + int(40 / 30 * self.H), delta=10)
        self.assertEqual(f["atReset"], 120.0)

    def test_hour_pace_over_the_real_gap(self):
        # the newest point from an hour ago or more is 2.5 h old: 30 % since then is 12 %/h
        w = self.window(40, 2)
        f = cs.usage_forecast(w, [[self.now - int(2.5 * self.H), 10]], self.now)
        self.assertEqual((f["basis"], f["rate"]), ("hour", 12.0))

    def test_quiet_hour_means_no_more_use(self):
        w = self.window(50, 2)
        f = cs.usage_forecast(w, [[self.now - 2 * self.H, 50]], self.now)
        self.assertEqual((f["rate"], f["atReset"], f["fullAt"]), (0.0, 50.0, None))

    def test_too_early_or_reset(self):
        self.assertIsNone(cs.usage_forecast(self.window(5, 4.9), [], self.now))
        self.assertIsNone(cs.usage_forecast(dict(self.window(5, 2), reset=True), [], self.now))
        self.assertIsNone(cs.usage_forecast(self.window(5, 2, key="spend_limit"), [], self.now))

    def test_weekly_window_even_pace(self):
        w = self.window(30, 84, key="seven_day")  # half the week gone
        f = cs.usage_forecast(w, [[self.now - 10 * self.H, 1]], self.now)  # weekly: the window's pace
        self.assertEqual((f["basis"], f["evenPct"], f["atReset"]), ("window", 50.0, 60.0))

    def test_full_already(self):
        f = cs.usage_forecast(self.window(100, 1), [], self.now)
        self.assertEqual((f["atReset"], f["fullAt"]), (100, None))


class UsageHistoryTests(Fixture):
    def snapshot(self, pct, age, resets_in=3600):
        path = self.cache / "statusline/.claude-work/busy.json"
        write(path, {"rate_limits": {"five_hour": {"used_percentage": pct, "resets_at": self.now + resets_in}}})
        os.utime(path, (self.now - age, self.now - age))

    def history(self):
        data = json.loads((self.cache / "usage.json").read_text())
        (points,) = [w["points"] for g in data["groups"].values() for w in g.values()]
        return [p[1] for p in points]

    def test_points_noted_when_usage_changes(self):
        self.snapshot(10, 600)
        self.collect(with_tokens=False)
        self.collect(with_tokens=False)  # same snapshot: nothing new
        self.snapshot(12, 0)
        r = self.collect(with_tokens=False)
        self.assertEqual(self.history(), [10, 12])
        (five,) = self.group(r, "work")["limits"]["windows"]
        self.assertEqual(five["forecast"]["basis"], "window")  # no hour on record yet
        self.snapshot(0, 0, resets_in=5 * 3600)  # a new window
        self.collect(with_tokens=False)
        self.assertEqual(self.history(), [0])

    def test_hour_pace_from_the_history(self):
        gid = self.group(self.collect(with_tokens=False), "work")["id"]
        now_ms = int(self.now * 1000)
        resets = now_ms + 3600_000
        write(self.cache / "usage.json", {"version": 1, "groups": {gid: {"five_hour": {
            "resetsAt": resets, "points": [[now_ms - 7200_000, 10], [now_ms - 3700_000, 20]]}}}})
        self.snapshot(50, 0)
        (five,) = self.group(self.collect(with_tokens=False), "work")["limits"]["windows"]
        self.assertEqual((five["forecast"]["basis"], five["forecast"]["rate"]), ("hour", round(30 / (3700 / 3600), 2)))

    def test_a_clock_set_back(self):
        gid = self.group(self.collect(with_tokens=False), "work")["id"]
        now_ms = int(self.now * 1000)
        write(self.cache / "usage.json", {"version": 1, "groups": {gid: {"five_hour": {
            "resetsAt": now_ms + 3600_000, "points": [[now_ms + 7200_000, 10]]}}}})  # noted while the clock ran ahead
        self.snapshot(20, 0)
        self.collect(with_tokens=False)
        self.assertEqual(self.history(), [20])

    def past(self):
        data = json.loads((self.cache / cs.USAGE_PAST_FILE).read_text())
        return [(w["key"], w["plan"], [p[1] for p in w["points"]]) for w in data["windows"]]

    def test_an_ended_window_is_kept_thinned_with_its_plan(self):
        gid = self.group(self.collect(with_tokens=False), "work")["id"]
        now_ms = int(self.now * 1000)
        values = [0, 2, 4, 5, 9, 10, 10, 12]  # (5% steps: 0, 5, 10, and the last value, 12)
        write(self.cache / "usage.json", {"version": 1, "groups": {gid: {"five_hour": {
            "resetsAt": now_ms - 600_000, "points": [[now_ms - 4 * 3600_000 + i * 60_000, v] for i, v in enumerate(values)]}}}})
        self.snapshot(1, 0, resets_in=5 * 3600)  # the next window began
        self.collect(with_tokens=False)
        self.assertEqual(self.past(), [("five_hour", "Team", [0, 5, 10, 12])])
        self.assertEqual(self.history(), [1])
        self.collect(with_tokens=False)
        self.assertEqual(len(self.past()), 1)  # (noted once)

    def test_a_window_gone_a_day_is_kept_and_old_ones_go(self):
        gid = self.group(self.collect(with_tokens=False), "work")["id"]
        now_ms = int(self.now * 1000)
        day = 86400_000
        write(self.cache / cs.USAGE_PAST_FILE, {"version": 1, "windows": [
            {"group": gid, "key": "seven_day", "plan": "Team", "resetsAt": now_ms - 91 * day, "points": [[1, 50]]},
            {"group": gid, "key": "seven_day", "plan": "Team", "resetsAt": now_ms - 89 * day, "points": [[1, 60]]}]})
        write(self.cache / "usage.json", {"version": 1, "groups": {gid: {"seven_day": {
            "resetsAt": now_ms - 2 * day, "points": [[now_ms - 3 * day, 70], [now_ms - 3 * day + 1, 71]]}}}})
        self.snapshot(5, 0)  # (no weekly window in it)
        self.collect(with_tokens=False)
        self.assertEqual(self.past(), [("seven_day", "Team", [60]), ("seven_day", "Team", [70, 71])])
        self.assertEqual(self.history(), [5])

    def test_none_kept_with_the_history_off(self):
        gid = self.group(self.collect(with_tokens=False), "work")["id"]
        now_ms = int(self.now * 1000)
        write(cs.history_file(self.cache), {"keep": False})
        write(self.cache / cs.USAGE_PAST_FILE, {"version": 1, "windows": []})
        write(self.cache / "usage.json", {"version": 1, "groups": {gid: {"five_hour": {
            "resetsAt": now_ms - 600_000, "points": [[now_ms - 3600_000, 40]]}}}})
        self.snapshot(1, 0, resets_in=5 * 3600)
        self.collect(with_tokens=False)
        self.assertFalse((self.cache / cs.USAGE_PAST_FILE).exists())
        self.assertEqual(self.history(), [1])

    def test_the_history_setting_is_kept_in_the_state_folder(self):
        # an older version's history.json in the cache moves there once; one put in the cache later counts for nothing
        write(self.cache / cs.HISTORY_SETTING_FILE, {"keep": False, "since": 5})
        self.assertEqual(cs.history_setting(self.cache), (False, 5))
        self.assertFalse((self.cache / cs.HISTORY_SETTING_FILE).exists())
        self.assertEqual(cs.history_file(self.cache).parent, cs.state_dir(self.cache))
        cs.write_json_atomic(cs.history_file(self.cache), {"keep": True})
        write(self.cache / cs.HISTORY_SETTING_FILE, {"keep": False})
        self.assertTrue(cs.history_kept(self.cache))

    def test_the_plan_with_its_tier(self):
        for plan, account, detail in (
                ("Max", {"organizationRateLimitTier": "default_claude_max_20x"}, "Max 20×"),
                ("Max", {"userRateLimitTier": "default_claude_max_5x"}, "Max 5×"),
                ("Max", {}, "Max"),
                ("Team", {"seatTier": "team_standard"}, "Team · standard seat"),
                ("Team", {"seatTier": "team_premium"}, "Team · premium seat"),
                ("Pro", {"organizationRateLimitTier": "default_claude_ai"}, "Pro"),
                (None, {"seatTier": "team_premium"}, None)):
            self.assertEqual(cs.plan_detail(plan, account), detail)

    def test_a_long_window_drops_repeats_before_its_start(self):
        # a weekly window: its value noted again every 10 minutes while unchanged
        runs = [[i, i // 10] for i in range(400)]  # 40 runs of 10 points
        kept = cs.trimmed_points(runs)
        self.assertEqual(len(kept), 80)  # (each run's first and last point)
        self.assertEqual(kept[:3], [[0, 0], [9, 0], [10, 1]])
        self.assertEqual(kept[-1], [399, 39])
        rising = [[i, i] for i in range(400)]  # (nothing to drop but the oldest)
        self.assertEqual(cs.trimmed_points(rising), rising[-300:])
        self.assertEqual(cs.trimmed_points(rising[:5]), rising[:5])


class TaskProgressTests(Fixture):
    """A chat's task list, as Claude keeps it in <cfg>/tasks/<session id>/."""

    def task(self, sid, n, subject, status, active=""):
        write(self.home / ".claude-work/tasks" / sid / f"{n}.json",
              {"id": str(n), "subject": subject, "activeForm": active, "status": status, "blocks": [], "blockedBy": []})

    def tasks(self, sid="busy"):
        work = self.group(self.collect(with_tokens=False), "work")
        return next(s for s in work["sessions"] if s["sessionId"] == sid)["tasks"]

    def test_progress_and_current_task(self):
        for n, subject, status in ((1, "Write the parser", "completed"), (2, "Test it", "in_progress"),
                                   (10, "Ship it", "pending"), (3, "Gone", "deleted")):
            self.task("busy", n, subject, status, active="Testing the parser" if n == 2 else "")
        (self.home / ".claude-work/tasks/busy/.lock").write_text("")
        t = self.tasks()
        self.assertEqual((t["done"], t["total"], t["current"]), (1, 3, "Testing the parser"))
        self.assertEqual([i["subject"] for i in t["items"]], ["Write the parser", "Test it", "Ship it"])

    def test_no_tasks(self):
        (self.home / ".claude-work/tasks/busy").mkdir(parents=True)
        self.assertIsNone(self.tasks())


def usage_line(msg_id, ts, output, cwd, model="claude-opus-5-5", tool=None):
    """One block of a reply, with its usage (repeated on every block of the reply)."""
    content = [{"type": "tool_use", "id": "t-" + msg_id, "name": tool, "input": {}}] if tool else [{"type": "text", "text": "ok"}]
    return {"type": "assistant", "timestamp": iso(ts), "cwd": cwd, "message": {
        "id": msg_id, "model": model, "content": content,
        "usage": {"input_tokens": 1, "output_tokens": output, "cache_read_input_tokens": 100, "cache_creation_input_tokens": 9}}}


class StatsTests(Fixture):
    """An account's last days: tokens per day, chats, your prompts, busiest folders."""

    DAY = 86400

    def setUp(self):
        super().setUp()
        self.now = datetime(2026, 10, 18, 15, 0).timestamp()
        w = self.home / ".claude-work/projects/-w"
        write(w / "chat-a.jsonl", "\n".join(json.dumps(l) for l in [
            usage_line("a1", self.now - 2 * self.DAY, 10, "/w/app"),
            usage_line("a2", self.now - 600, 20, "/w/app/tests"),  # cd'd into a subfolder: still /w/app
            usage_line("a2", self.now - 600, 25, "/w/app/tests"),  # same reply, final count
        ]) + "\n")
        write(w / "chat-b.jsonl", json.dumps(usage_line("b1", self.now - 300, 5, "/w/site", model="claude-haiku-5-5")) + "\n")
        write(w / "chat-a/subagents/agent-x.jsonl", json.dumps(usage_line("x1", self.now - 500, 3, "/w/app")) + "\n")
        write(w / "old.jsonl", json.dumps(usage_line("o1", self.now - 20 * self.DAY, 7, "/w/old")) + "\n")
        os.utime(w / "old.jsonl", (self.now - 20 * self.DAY, self.now - 20 * self.DAY))
        prompts = [{"display": "go", "timestamp": int((self.now - t) * 1000), "project": f, "sessionId": "chat-a"}
                   for t, f in ((700, "/w/app"), (650, "/w/app"), (2 * self.DAY, "/w/app"), (400, "/w/site"))]
        write(self.home / ".claude-work/history.jsonl", "".join(json.dumps(p) + "\n" for p in prompts))

    def stats(self, **kw):
        return self.group(self.collect(**kw), "work")["stats"]

    def test_days_folders_models(self):
        st = self.stats()
        days = st["days"]
        self.assertEqual(len(days), cs.STATS_SHOWN_DAYS)
        self.assertEqual(days[-1]["day"], "2026-10-18")
        today, two_ago = days[-1], days[-3]
        self.assertEqual((today["output"], today["messages"], today["chats"], today["prompts"]), (25 + 3 + 5, 3, 2, 3))
        self.assertEqual(today["total"], 3 * 110 + 25 + 3 + 5)
        self.assertEqual((two_ago["output"], two_ago["chats"], two_ago["prompts"]), (10, 1, 1))
        self.assertEqual([(p["name"], p["output"], p["prompts"]) for p in st["projects"]],
                         [("app", 38, 3), ("site", 5, 1)])  # old is beyond the days shown
        self.assertEqual([m["model"] for m in st["models"]], ["Opus 5.5", "Haiku 5.5"])
        self.assertEqual((st["sum"]["chats"], st["sum"]["prompts"], st["sum"]["activeDays"]), (2, 4, 2))

    def test_history_outlives_the_messages(self):
        self.stats()
        work = next(p for p in cs.discover_profiles(self.home) if p.label == "work")
        cache = json.loads(cs.token_cache_path(self.cache, work).read_text())
        self.assertIn((date.fromtimestamp(self.now) - timedelta(days=20)).isoformat(), cache["history"])  # read back 30 days once
        self.assertNotIn("o1", cache["messages"])  # messages: only TOKEN_DAYS
        later = self.now + 9 * self.DAY  # a2 and b1 are no longer in the messages kept
        st = self.stats(now=later)
        self.assertEqual(st["days"][-10]["output"], 33)  # nine days ago: from the history
        self.assertEqual(st["days"][-1]["output"], 0)

    def test_no_history_without_tokens(self):
        self.assertIsNone(self.group(self.collect(with_tokens=False), "work")["stats"])


class ChatRecapTests(Fixture):
    """A chat's numbers: prompts, tool calls, tokens, how long Claude worked."""

    def test_recap(self):
        t = time.time() - 3600
        main = self.home / ".claude-work/projects/-w/busy.jsonl"
        lines = [
            chat_line("user", "first", ts=t),
            usage_line("m1", t + 10, 5, "/w", tool="Bash"),
            usage_line("m1", t + 11, 8, "/w", tool="Read"),  # the same reply's next block
            chat_line("user", [{"type": "tool_result", "tool_use_id": "t", "content": "x"}], ts=t + 30),
            usage_line("m2", t + 60, 4, "/w"),
            chat_line("user", "second", ts=t + 600),
            usage_line("m3", t + 620, 2, "/w", tool="Bash"),
        ]
        write(main, "\n".join(json.dumps(l) for l in lines) + "\n")
        write(main.parent / "busy/subagents/agent-a.jsonl",
              json.dumps(chat_line("user", "find it", ts=t + 14)) + "\n" + json.dumps(usage_line("s1", t + 15, 6, "/w", tool="Grep")) + "\n")
        work = self.group(self.collect(with_tokens=False), "work")
        st = next(s for s in work["sessions"] if s["sessionId"] == "busy")["stats"]
        self.assertEqual((st["prompts"], st["toolCalls"]), (2, 4))
        self.assertEqual(st["tools"], [["Bash", 2], ["Grep", 1], ["Read", 1]])
        self.assertEqual(st["tokens"]["output"], 8 + 4 + 2 + 6)
        self.assertEqual(st["tokens"]["total"], 4 * 110 + 20)
        self.assertEqual(st["workedMs"], 60_000 + 20_000)
        self.assertEqual((st["startedAt"], st["lastAt"]), (int(t * 1000), int((t + 620) * 1000)))

    def test_no_recap_without_a_transcript(self):
        work = self.group(self.collect(with_tokens=False), "work")
        self.assertIsNone(next(s for s in work["sessions"] if s["sessionId"] == "busy")["stats"])


class OlderCopiesTests(Fixture):
    """An older copy of this script (a VS Code extension not updated yet) reads
    and writes the same caches: neither may make the other read everything again."""

    def test_token_cache_from_before_the_stats(self):
        path = self.home / ".claude-work/projects/-w/c.jsonl"
        write(path, json.dumps(usage_line("a1", self.now - 60, 5, "/w/app")) + "\n")
        work = next(p for p in cs.discover_profiles(self.home) if p.label == "work")
        cache_file = cs.token_cache_path(self.cache, work)
        old = {"version": cs.CACHE_VERSION, "scannedAt": 0, "messages": {"a1": [cs.local_day(iso(self.now - 60)), "m", 1, 5, 100, 9, 0]},
               "files": {str(path): {"offset": path.stat().st_size, "ino": path.stat().st_ino}}}
        write(cache_file, old)  # as 1.8 left it: the file read to its end
        st = self.group(self.collect(), "work")["stats"]
        self.assertEqual(st["projects"][0]["name"], "app")  # read again for the stats
        cache = json.loads(cache_file.read_text())
        self.assertEqual(cache["version"], cs.CACHE_VERSION)
        cache.pop("scannedAt")
        cache["scannedAt"] = 0  # an older copy rescans: it keeps the keys it doesn't know
        write(cache_file, cache)
        self.collect()
        self.assertIn("history", json.loads(cache_file.read_text()))

    def test_message_records_of_an_older_copy(self):
        msgs = {"x": ["2026-10-18", "claude-opus-5-5", 1, 2, 3, 4, 0]}  # 7 fields: no folder or chat
        self.assertEqual(cs.day_history(msgs)["2026-10-18"]["projects"], {})
        self.assertEqual(cs.day_totals(msgs)["2026-10-18"]["claude-opus-5-5"][:2], [1, 2])

    def test_chat_records_without_stats_are_read_again(self):
        path = self.home / ".claude-work/projects/-w/busy.jsonl"
        write(path, json.dumps(chat_line("user", "go")) + "\n")
        old = {"version": cs.CHAT_CACHE_VERSION, "peeks": {}, "edits": {
            cs.file_key(path.stat()): {"size": path.stat().st_size, "rec": {"files": {}, "snap": None, "snapFiles": {}, "turn": {}, "sessions": []}}}}
        write(self.cache / "chats.json", old)
        work = self.group(self.collect(with_tokens=False), "work")
        self.assertEqual(next(s for s in work["sessions"] if s["sessionId"] == "busy")["stats"]["prompts"], 1)


class NewClaudeValuesTests(Fixture):
    """The widget reads files Claude Code doesn't document. A status it
    doesn't know counted as idle and a new kind of session wasn't listed, with
    nothing to say so; now the popup does."""

    def test_new_values_are_named_with_the_version(self):
        w = self.home / ".claude-work"
        write(w / "sessions/40.json", session("new-status", status="compacting", version="2.1.400"))
        write(w / "sessions/41.json", session("new-kind", kind="headless", version="2.1.399"))
        write(w / "jobs/newjob/state.json", {"state": "paused", "tempo": "dozing", "cliVersion": "2.1.401",
                                             "updatedAt": iso(self.now - 60)})
        errors = self.collect(with_tokens=False)["errors"]
        self.assertEqual(len(errors), 1, errors)
        for part in ("Claude Code 2.1.401", 'chat status "compacting"', 'chat kind "headless"',
                     'job state "paused"', 'job tempo "dozing"', "may show the wrong state"):
            self.assertIn(part, errors[0])

    def test_what_claude_writes_today_says_nothing(self):
        # (the fixture holds every status, kind and job state the widget knows)
        w = self.home / ".claude-work"
        for i, (state, tempo) in enumerate([("working", "active"), ("running", "idle"), ("failed", "idle"),
                                            ("stopped", "idle"), ("blocked", "blocked")]):
            write(w / f"jobs/today{i}/state.json", {"state": state, "tempo": tempo, "updatedAt": iso(self.now - 60)})
        write(w / "sessions/42.json", session("bg-shell", kind="bg", status="shell"))
        write(w / "sessions/43.json", session("worker", kind="daemon-worker"))
        self.assertEqual(self.collect(with_tokens=False)["errors"], [])

    def test_a_value_that_is_no_text_is_named_too(self):
        write(self.home / ".claude-work/sessions/44.json", session("odd", status=3))
        self.assertIn('chat status "3"', self.collect(with_tokens=False)["errors"][0])


class UsageFetchFixture(Fixture):
    """A logged-in work account whose plan usage is an hour old, and the
    fetches started (spawned)."""

    CLAUDE = "/opt/claude/bin/claude"

    def setUp(self):
        super().setUp()
        self.spawned = []
        for p in (mock.patch.object(cs, "find_claude", lambda home, ask_shell=False: self.CLAUDE),
                  mock.patch.object(cs, "spawn_detached", lambda argv, cwd, env: self.spawned.append((argv, cwd, env)))):
            p.start()
            self.addCleanup(p.stop)
        self.work = self.home / ".claude-work"
        write(self.work / ".credentials.json", "{}")  # logged in (it's never opened)
        self.usage_cache(fetched_ago=3600)

    def usage_cache(self, fetched_ago):
        path = self.work / ".claude.json"
        data = json.loads(path.read_text())
        data["cachedUsageUtilization"] = {
            "fetchedAtMs": int((self.now - fetched_ago) * 1000), "accountUuid": "acct-team",
            "utilization": {"five_hour": {"utilization": 12, "resets_at": iso(self.now + 3600)}}}
        write(path, data)

    def only_session(self, **kw):
        """The work profile's one chat."""
        shutil.rmtree(self.work / "sessions", ignore_errors=True)
        write(self.work / "sessions/1.json", session("mine", **{"entrypoint": "claude-vscode", **kw}))

    def check(self, now=None, minutes=5, **kw):
        """The profiles a status check had fetch their plan usage (CLAUDE_CONFIG_DIR)."""
        self.spawned.clear()
        self.result = self.collect(with_tokens=False, usage_refresh=minutes, now=self.now if now is None else now, **kw)
        return [env.get("CLAUDE_CONFIG_DIR") for _, _, env in self.spawned]


class UsageRefreshTests(UsageFetchFixture):
    """An account used only in VS Code's panel (no status line there): while
    one of its chats works and its plan usage is old, Claude Code fetches it."""

    def test_old_usage_fetched_while_a_chat_works(self):
        folder = self.cache / "usage-check"
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "cli",
                                          "CLAUDE_CONFIG_DIR": "/somewhere/else"}):
            self.assertEqual(self.check(), [str(self.work)])
        (argv, cwd, env), = self.spawned
        timeout = shutil.which("timeout")
        self.assertEqual(argv, [
            "/bin/sh", "-c", cs.USAGE_CHECK_SCRIPT, "sh", str(self.work / "projects" / cs.mangle(str(folder))),
            *([timeout, "-k", "10", "60"] if timeout else []),
            self.CLAUDE, "-p", "/usage", "--no-session-persistence", "--setting-sources", "user", "--strict-mcp-config",
            "--settings", '{"disableAllHooks":true}', "--output-format", "json"])
        self.assertEqual(cwd, str(folder))
        self.assertEqual(oct(folder.stat().st_mode & 0o777), "0o700")
        self.assertNotIn("CLAUDECODE", env)  # (else it would count as part of the session the widget runs in)
        self.assertNotIn("CLAUDE_CODE_ENTRYPOINT", env)
        self.assertEqual(json.loads((self.cache / "usage-check.json").read_text()),
                         {"started": {str(self.work): int(self.now * 1000)}})
        # what it fetched counts at the next check, as Claude Code's own usage
        self.usage_cache(fetched_ago=0)
        os.unlink(self.cache / "usage-check.json")
        self.assertEqual(self.check(now=self.now + 60), [])
        self.assertEqual(self.group(self.result, "work")["limits"]["updatedAt"], int(self.now * 1000))

    def test_a_plain_claude_folder_runs_without_claude_config_dir(self):
        write(self.home / ".claude/.credentials.json", "{}")  # VS Code's chat in ~/.claude works (the fixture's)
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": "/somewhere/else"}):
            self.assertEqual(self.check(), [None, str(self.work)])
        argv = self.spawned[0][0]
        self.assertEqual(argv[4], str(self.home / ".claude/projects" / cs.mangle(str(self.cache / "usage-check"))))

    def test_at_most_once_in_five_minutes_whichever_copy_checks(self):
        self.assertEqual(len(self.check()), 1)
        self.assertEqual(self.check(now=self.now + 2), [])
        self.assertEqual(self.check(now=self.now + 299), [])
        self.assertEqual(len(self.check(now=self.now + 301)), 1)
        # another copy deciding right now: this one leaves it
        import fcntl
        with open(self.cache / "usage-check.lock", "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            self.assertEqual(self.check(now=self.now + 700), [])
        self.assertEqual(len(self.check(now=self.now + 700)), 1)
        # the clock set back: not waited for until then
        self.assertEqual(len(self.check(now=self.now - 600)), 1)

    def test_not_while_the_usage_is_fresh(self):
        self.usage_cache(fetched_ago=120)
        self.assertEqual(self.check(), [])
        self.assertEqual(len(self.check(now=self.now + 200)), 1)  # 5 min old now
        # a terminal chat's status line keeps it fresh: an old cache doesn't matter
        self.usage_cache(fetched_ago=86400)
        path = self.cache / "statusline/.claude-work/term.json"
        write(path, {"rate_limits": {"five_hour": {"used_percentage": 30, "resets_at": self.now + 3600}}})
        os.utime(path, (self.now + 590, self.now + 590))
        self.assertEqual(self.check(now=self.now + 600), [])

    def test_not_while_nothing_works(self):
        long_ago = int((self.now - 601) * 1000)  # (the interval and 5 minutes)
        self.only_session(status="idle", statusUpdatedAt=long_ago)
        self.assertEqual(self.check(), [])
        self.only_session(status="waiting", waitingFor="permission prompt", statusUpdatedAt=long_ago)
        self.assertEqual(self.check(), [])
        self.only_session(status="shell", statusUpdatedAt=long_ago)  # a dev server runs on
        self.assertEqual(self.check(), [])
        shutil.rmtree(self.work / "sessions")
        self.assertEqual(self.check(), [])
        self.assertFalse((self.cache / "usage-check.json").exists())
        # a turn that ended 8 minutes ago used the plan after the numbers (once
        # more after the turn, whenever the last fetch was)
        self.only_session(status="idle", statusUpdatedAt=int((self.now - 480) * 1000))
        self.assertEqual(self.check(), [str(self.work)])

    def test_not_for_an_account_that_isnt_logged_in(self):
        os.unlink(self.work / ".credentials.json")
        self.assertEqual(self.check(), [])
        write(self.work / ".credentials.json", "{}")
        data = json.loads((self.work / ".claude.json").read_text())
        del data["oauthAccount"]  # (claude auth logout)
        write(self.work / ".claude.json", data)
        self.assertEqual(self.check(), [])
        self.assertTrue(self.group(self.result, "work")["loggedOut"])

    def test_not_without_claude(self):
        with mock.patch.object(cs, "find_claude", lambda home, ask_shell=False: "claude"):
            self.assertEqual(self.check(), [])
        self.assertFalse((self.cache / "usage-check.json").exists())

    def test_the_interval_is_a_setting(self):
        self.usage_cache(fetched_ago=600)
        self.assertEqual(self.check(minutes=15), [])
        self.assertEqual(self.check(minutes=0), [])  # never
        self.assertEqual(len(self.check(minutes=9)), 1)
        self.assertEqual(self.check(now=self.now + 9 * 60 - 1, minutes=9), [])  # (at most that often)
        self.assertEqual(len(self.check(now=self.now + 9 * 60, minutes=9)), 1)

    def test_only_for_the_status_check(self):
        self.collect(with_tokens=False)
        self.assertEqual(self.spawned, [])
        self.usage_cache(fetched_ago=50 * 60)
        xdg = Path(self.tmp.name) / "xdg"

        def run(*args):
            self.spawned.clear()
            env = {"HOME": str(self.home), "XDG_CACHE_HOME": str(xdg)}
            with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(io.StringIO()) as out:
                cs.main(["--no-tokens", *args])
            self.assertTrue(json.loads(out.getvalue())["ok"])
            return [e.get("CLAUDE_CONFIG_DIR") for _, _, e in self.spawned]
        self.assertEqual(run("--usage-refresh", "0"), [])
        self.assertEqual(run("--usage-refresh", "120"), [])  # (60 at most)
        self.assertEqual(run(), [str(self.work)])  # (5 minutes unless set)
        self.assertEqual(self.spawned[0][1], str(xdg / "talpy-den/usage-check"))
        (xdg / "talpy-den/usage-check.json").unlink()
        self.assertEqual(run("--usage-refresh", "49"), [str(self.work)])
        with self.assertRaises(SystemExit):
            run("--usage-refresh", "soon")

    def test_its_own_session_isnt_a_chat(self):
        # Claude registers it for the second it runs: busy, "interactive", in its folder
        self.only_session(status="busy", cwd=str(self.cache / "usage-check"), entrypoint="sdk-cli")
        write(self.work / "sessions/2.json", session("other-copy", status="busy",
                                                     cwd="/home/x/.cache/talpy-den/usage-check/"))
        self.assertEqual(self.check(), [])  # (nor does it count as a chat at work)
        listed = [s["sessionId"] for g in self.result["groups"] for s in g["sessions"]]
        self.assertEqual([i for i in listed if i in ("mine", "other-copy")], [])
        self.assertNotIn("usage-check", json.dumps(self.result))  # (not in Recent chats, Projects, … either)
        self.assertTrue(cs.is_usage_check("/a/talpy-den/usage-check"))
        self.assertFalse(cs.is_usage_check("/a/usage-check"))
        self.assertFalse(cs.is_usage_check(None))


class FetchUsageTests(UsageFetchFixture):
    """Refresh (talpy_den.py --fetch-usage): every account's plan usage over a
    minute old is fetched now, chat at work or not, at most once a minute."""

    def fetch(self, now=None):
        self.spawned.clear()
        self.answer = cs.fetch_usage_now(self.home, self.cache, now=self.now if now is None else now)
        return [env.get("CLAUDE_CONFIG_DIR") for _, _, env in self.spawned]

    def test_old_usage_fetched_with_no_chat_at_work(self):
        self.assertEqual(self.fetch(), [str(self.work)])
        self.assertEqual(self.answer, {"ok": True, "started": ["work"]})
        self.assertEqual(self.fetch(now=self.now + 30), [], "twice in a minute")
        # the status says it's on its way, until its numbers are in
        result = self.collect(with_tokens=False, usage_refresh=0, now=self.now + 5)
        self.assertEqual(self.group(result, "work")["usageFetchAt"], int(self.now * 1000))

    def test_new_usage_left_alone(self):
        self.usage_cache(fetched_ago=30)
        self.assertEqual(self.fetch(), [])


class ModeTests(unittest.TestCase):
    """A chat's permission mode: VS Code's Claude Code panel names it at the
    first prompt only (one that begins with a note of the file open there)."""

    def test_named_once_then_kept(self):
        first = {"type": "user", "permissionMode": "auto", "origin": {"kind": "human"},
                 "message": {"role": "user", "content": [{"type": "text", "text": "<ide_opened_file>The user opened a.tex</ide_opened_file>"},
                                                         {"type": "text", "text": "tidy the abstract"}]}}
        later = {"type": "user", "message": {"role": "user", "content": "and the intro"}}
        self.assertEqual(cs.names_mode(first), "auto")
        self.assertIsNone(cs.names_mode(later))
        self.assertIsNone(cs.names_mode({**first, "isSidechain": True}))
        self.assertEqual(cs.names_mode({"type": "permission-mode", "permissionMode": "plan"}), "plan")
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "chat.jsonl"
            path.write_text("".join(json.dumps(e) + "\n" for e in (first, later, later)))
            self.assertEqual(cs.scan_mode(path, path.stat().st_size), "auto")
            cache = cs.ChatCache(Path(d) / "chats.json")
            self.assertEqual(cache.edits(path)["mode"], "auto")
            with open(path, "a") as f:   # (changed later on: the newest one)
                f.write(json.dumps({"type": "permission-mode", "permissionMode": "plan"}) + "\n")
            self.assertEqual(cs.ChatCache(Path(d) / "chats.json").edits(path)["mode"], "plan")


class TerminalTests(unittest.TestCase):
    """The terminal a chat runs in, by name, and where a background session is shown (claude attach)."""

    def tree(self, names):
        """pid -> its process name; each one's parent is the next pid up."""
        return (mock.patch.object(cs, "process_name", lambda pid: names.get(pid, "")),
                mock.patch.object(cs, "parent_pid", lambda pid: pid + 1 if pid + 1 in names else 1),
                mock.patch.object(cs, "is_vscode_terminal_host", lambda pid: names.get(pid) == "code"))

    def test_the_terminal_by_name(self):
        for names, want in (({10: "claude", 11: "bash", 12: "konsole"}, "Konsole"),
                            ({10: "claude", 11: "fish", 12: "gnome-terminal-"}, "GNOME Terminal"),
                            ({10: "claude", 11: "zsh", 12: "tmux: server", 13: "kitty"}, ""),   # (in tmux)
                            ({10: "claude", 11: "bash", 12: "code"}, "VS Code"),                # (a VS Code terminal)
                            ({10: "claude", 11: "sshd-session"}, "")):
            patches = self.tree(names)
            with patches[0], patches[1], patches[2]:
                self.assertEqual(cs.terminal_name(10), want, names)

    def test_a_background_session_shown_in_a_terminal(self):
        row = lambda job, name, profile=".claude": {"jobId": job, "sessionId": job + "-s", "chatId": job + "-s", "name": name,  # noqa: E731
                                                    "profileDir": profile, "kind": "bg", "pid": 1}
        a, b, c = row("0a1b2c3d", "fix parser"), row("eeeeeeee", "Minor version tag", ".claude-work"), row("ffffffff", "notes")
        twin1, twin2 = row("11111111", "same name"), row("22222222", "same name")
        rows = [a, b, c, twin1, twin2]
        reals = {".claude": Path("/home/me/.claude"), ".claude-work": Path("/home/me/.claude-work")}

        def shown(opened, title, here=Path("/home/me/.claude")):
            with mock.patch.object(cs, "process_config_dir", lambda pid: here):
                found = cs.shown_row(20, opened, title, rows, reals)
            return found and found["jobId"]
        # opened by id (claude attach <id>, or the agent view's CLAUDE_AGENTS_SELECT), any terminal, no readable title
        self.assertEqual(shown("0a1b2c3d", ""), "0a1b2c3d")
        self.assertEqual(shown("eeeeeeee-s", ""), "eeeeeeee")      # (by its session id)
        # Konsole's own title ("%d : %n"), which names no chat: the one it was opened for
        self.assertEqual(shown("0a1b2c3d", "talpy-den : claude"), "0a1b2c3d")
        # the agent view switched to another chat: its title names it, whichever profile
        self.assertEqual(shown("0a1b2c3d", "Minor version tag"), "eeeeeeee")
        self.assertEqual(shown("", "notes"), "ffffffff")           # (a plain claude agent view)
        # two chats of that name: the one it was opened for if it's one of them, else none
        self.assertEqual(shown("22222222", "same name"), "22222222")
        self.assertIsNone(shown("0a1b2c3d", "same name"))
        # opened by name: on the profile it runs on only
        self.assertEqual(shown("fix parser", ""), "0a1b2c3d")
        self.assertIsNone(shown("fix parser", "", Path("/home/me/.claude-work")))
        self.assertIsNone(shown("99999999", ""))
        clients = [(20, "0a1b2c3d", "talpy-den : claude"), (30, "", "notes"), (40, "eeeeeeee", "")]
        with mock.patch.object(cs, "tmux_socket", lambda pid: "/tmp/tmux-1/default" if pid == 40 else None), \
                mock.patch.object(cs, "terminal_name", lambda pid: "VS Code" if pid == 30 else "Konsole"):
            self.assertEqual(cs.attached_in(a, rows, clients, reals), {"in": "terminal", "app": "Konsole"})
            self.assertEqual(cs.attached_in(c, rows, clients, reals), {"in": "vscode", "app": ""})
            self.assertEqual(cs.attached_in(b, rows, clients, reals), {"in": "tmux", "app": ""})
            self.assertIsNone(cs.attached_in(twin1, rows, clients, reals))

    def test_the_row_of_a_session_attached_in_konsole_says_so(self):
        # (Konsole's default tab title: the tag comes from the id it was opened with)
        fx = Fixture()
        fx.setUp()
        self.addCleanup(fx.tearDown)
        with mock.patch.object(cs, "attach_clients", lambda: [(20, "job3", "talpy-den : claude")]), \
                mock.patch.object(cs, "tmux_socket", lambda pid: None), \
                mock.patch.object(cs, "terminal_name", lambda pid: "Konsole"):
            rows = {s["sessionId"]: s for g in fx.collect(with_tokens=False)["groups"] for s in g["sessions"]}
        self.assertEqual(rows["bgworking"]["attached"], {"in": "terminal", "app": "Konsole"})
        self.assertIsNone(rows["bgdone"]["attached"])

    def test_the_title_without_its_marks(self):
        self.assertEqual(cs.TITLE_MARKS.sub("", "🏠 ◐ Minor version 1.16.2 tag").strip(), "Minor version 1.16.2 tag")
        self.assertEqual(cs.TITLE_MARKS.sub("", "✳ (draft) notes").strip(), "(draft) notes")


class UsageRefreshCommandTests(unittest.TestCase):
    """The command itself, with a stand-in claude."""

    def test_it_runs_and_leaves_no_folder_behind(self):
        with tempfile.TemporaryDirectory() as tmp:
            home, cache = Path(tmp) / "home", Path(tmp) / "cache"
            write(home / ".claude-work/.profile-name", "work")
            write(home / ".claude-work/.claude.json", {"oauthAccount": {"accountUuid": "a"}})
            write(home / ".claude-work/projects/-keep/memory/note.md", "mine")
            claude, out = Path(tmp) / "bin/claude", Path(tmp) / "out.txt"
            # (Claude makes an empty memory folder for the folder it runs in)
            write(claude, '#!/bin/sh\nprintf "%s\\n" "$PWD" "$CLAUDE_CONFIG_DIR" "$@" > "$OUT"\n'
                          'mkdir -p "$CLAUDE_CONFIG_DIR/projects/$(pwd | sed "s/[^A-Za-z0-9]/-/g")/memory"\n')
            claude.chmod(0o755)
            profile = next(p for p in cs.discover_profiles(home) if p.label == "work")
            folder = cache / "usage-check"
            folder.mkdir(parents=True)
            with mock.patch.dict(os.environ, {"OUT": str(out)}):
                argv, env = cs.usage_refresh_command(profile, home, str(claude), folder)
            proc = cs.spawn_detached(argv, str(folder), env)
            self.assertEqual(proc.wait(timeout=30), 0)
            self.assertEqual(out.read_text().splitlines(), [
                str(folder), str(home / ".claude-work"), "-p", "/usage", "--no-session-persistence",
                "--setting-sources", "user", "--strict-mcp-config", "--settings", '{"disableAllHooks":true}',
                "--output-format", "json"])
            self.assertEqual(os.listdir(home / ".claude-work/projects"), ["-keep"])
            # without timeout, it runs without a time limit
            with mock.patch("shutil.which", lambda name, *a, **kw: None):
                argv, _ = cs.usage_refresh_command(profile, home, str(claude), folder)
            self.assertEqual(argv[5:7], [str(claude), "-p"])
