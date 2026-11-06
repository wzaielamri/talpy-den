"""Recaps, permission modes, usage limits that stopped chats, plans, finding
chats and starting tasks (talpy_den.py, jump.py, sharing.py, remote.py)."""
import claude_guard  # noqa: F401  (first: no test runs the real claude)
import base64
import contextlib
import importlib.util
import io
import json
import os
import shlex
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True  # keep __pycache__ out of the plasmoid package
CODE = Path(__file__).resolve().parent.parent / "package/contents/code"
sys.path.insert(0, str(CODE))
spec = importlib.util.spec_from_file_location("jump_tasks", CODE / "jump.py")
jump = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jump)
cs = jump.cs
sharing = jump.sharing

from test_talpy_den import Fixture, iso, session, vscode_link_params, write  # noqa: E402


def lines(*entries):
    return "".join(json.dumps(e, separators=(",", ":")) + "\n" for e in entries)  # (as Claude writes them)


def prompt(text, ts, **kw):
    return {"type": "user", "timestamp": iso(ts), "message": {"role": "user", "content": text}, **kw}


def reply(text, ts, msg_id="m1", **kw):
    return {"type": "assistant", "timestamp": iso(ts),
            "message": {"id": msg_id, "role": "assistant", "content": [{"type": "text", "text": text}],
                        "stop_reason": "end_turn"}, **kw}


def recap(text, ts):
    return {"type": "system", "subtype": "away_summary", "timestamp": iso(ts), "content": text}


def limit_error(text, ts):
    return {"type": "assistant", "timestamp": iso(ts), "isApiErrorMessage": True,
            "message": {"id": "err", "role": "assistant", "content": [{"type": "text", "text": text}],
                        "stop_reason": "stop_sequence"}}


class PeekTests(Fixture):
    def peek(self, *entries):
        path = self.home / ".claude-work/projects/-p/chat1.jsonl"
        write(path, lines(*entries))
        return cs.chat_peek(path)

    def test_recap_while_nothing_was_said_after_it(self):
        t = self.now - 600
        p = self.peek(prompt("fix it", t), reply("Fixed.", t + 10),
                      recap("You asked me to fix it; it's fixed. (disable recaps in /config)", t + 300))
        self.assertEqual(p["recap"], {"text": "You asked me to fix it; it's fixed.", "at": int((t + 300) * 1000)})
        # a prompt (or a reply) after it makes it old
        p = self.peek(prompt("fix it", t), reply("Fixed.", t + 10), recap("Old recap", t + 300),
                      prompt("and now?", t + 400))
        self.assertIsNone(p["recap"])
        p = self.peek(recap("Old recap", t), reply("More news", t + 10, msg_id="m2"))
        self.assertIsNone(p["recap"])

    def test_permission_mode_and_slug(self):
        t = self.now - 600
        p = self.peek({"type": "permission-mode", "permissionMode": "plan"},
                      prompt("plan it", t, permissionMode="plan", slug="happy-blue-fox"),
                      reply("Here's the plan.", t + 5, slug="happy-blue-fox"),
                      {"type": "permission-mode", "permissionMode": "acceptEdits"})
        self.assertEqual((p["mode"], p["slug"]), ("acceptEdits", "happy-blue-fox"))
        p = self.peek(prompt("hi", t, permissionMode="auto"), reply("Hello.", t + 5))
        self.assertEqual((p["mode"], p["slug"]), ("auto", None))
        # a slug that can't be a file name is no slug
        self.assertIsNone(self.peek(prompt("hi", t, slug="../x"), reply("Hi.", t + 1))["slug"])

    def test_ultracode_as_claude_last_noted_it(self):
        # Claude Code 2.1.312 notes ultracode with your next prompt after it
        # changes: an ultra_effort_enter attachment (on), ultra_effort_exit (off)
        t = self.now - 600
        on = {"type": "attachment", "attachment": {"type": "ultra_effort_enter", "reminderType": "full"}}
        off = {"type": "attachment", "attachment": {"type": "ultra_effort_exit"}}
        other = {"type": "attachment", "attachment": {"type": "date_change", "text": "ultra_effort_enter"}}
        self.assertFalse(self.peek(prompt("hi", t), reply("Hello.", t + 5))["ultracode"])
        self.assertTrue(self.peek(prompt("hi", t), on, reply("Hello.", t + 5), other)["ultracode"])
        self.assertFalse(self.peek(on, prompt("hi", t), reply("Hello.", t + 5), off, prompt("and now?", t + 9))["ultracode"])

    def test_what_stopped_it(self):
        t = self.now - 600
        p = self.peek(prompt("go on", t), limit_error("You've hit your session limit · resets 7:10pm (Europe/Berlin)", t + 2))
        self.assertEqual(p["stopped"], {"kind": "limit", "window": "five_hour", "at": int((t + 2) * 1000),
                                        "text": "You've hit your session limit · resets 7:10pm (Europe/Berlin)"})
        # (Claude Code 2.1.312 and later name it the 5-hour limit)
        p = self.peek(prompt("go on", t), limit_error("You've hit your 5-hour limit · resets 7:10pm (Europe/Berlin)", t + 2))
        self.assertEqual(p["stopped"]["window"], "five_hour")
        p = self.peek(prompt("go on", t), limit_error("You've hit your weekly limit · resets Oct 24, 9am", t + 2))
        self.assertEqual(p["stopped"]["window"], "seven_day")
        # the limit and its reset as Claude notes them with the error (whatever it calls the limit)
        error = dict(limit_error("You've hit your daily limit", t + 2),
                     quotaLimits={"status": "rejected", "resetsAt": 1792572000, "rateLimitType": "five_hour"})
        p = self.peek(prompt("go on", t), error)
        self.assertEqual((p["stopped"]["window"], p["stopped"]["resets"]), ("five_hour", 1792572000_000))
        p = self.peek(prompt("go on", t), limit_error("You've reached your Fable limit.", t + 2))
        self.assertEqual(p["stopped"]["window"], "seven_day_overage_included")
        p = self.peek(prompt("go on", t), limit_error("You've hit your monthly spend limit.", t + 2))
        self.assertEqual((p["stopped"]["kind"], p["stopped"]["window"]), ("limit", None))
        p = self.peek(prompt("go on", t), limit_error("Login expired · Please run /login", t + 2))
        self.assertEqual(p["stopped"]["kind"], "login")
        # another API error, or a prompt after it: nothing stopped it
        self.assertIsNone(self.peek(prompt("go", t), limit_error("API Error: Connection lost", t + 2))["stopped"])
        self.assertIsNone(self.peek(prompt("go", t), limit_error("You've hit your session limit", t + 2),
                                    prompt("again", t + 3))["stopped"])

    def test_cached_peek_of_an_older_copy_is_read_again(self):
        path = self.home / ".claude-work/projects/-p/chat1.jsonl"
        t = self.now - 600
        write(path, lines(prompt("hi", t), reply("Hello.", t + 1), recap("You said hi.", t + 100)))
        st = path.stat()
        old = {"activity": "", "prompt": "hi", "reply": "Hello.", "replyLine": "Hello.", "at": 1}
        write(self.cache / "chats.json", {"version": cs.CHAT_CACHE_VERSION, "edits": {},
                                          "peeks": {cs.file_key(st): [st.st_size, st.st_mtime_ns, old]}})
        chats = cs.ChatCache(self.cache / "chats.json")
        self.assertEqual(chats.peek(path)["recap"]["text"], "You said hi.")
        # (an older copy keeps the new keys it doesn't know: no reading again)
        chats.save()
        self.assertEqual(cs.ChatCache(self.cache / "chats.json").peek(path)["recap"]["text"], "You said hi.")


class LimitStopTests(unittest.TestCase):
    NOW = 1_800_000_000_000

    def stop(self, at, window="five_hour", text="You've hit your session limit"):
        return {"kind": "limit", "window": window, "text": text, "at": at}

    def test_resets_with_its_window(self):
        limits = {"windows": [{"key": "five_hour", "reset": False, "resetsAt": self.NOW + 3600_000}]}
        s = cs.limit_stop(self.stop(self.NOW - 600_000), limits, self.NOW)
        self.assertEqual((s["resetsAt"], s["over"]), (self.NOW + 3600_000, False))
        # the window started (4 h ago) after the chat stopped: that limit is over
        s = cs.limit_stop(self.stop(self.NOW - 5 * 3600_000), limits, self.NOW)
        self.assertEqual((s["resetsAt"], s["over"]), (None, True))

    def test_a_window_past_its_reset(self):
        limits = {"windows": [{"key": "five_hour", "reset": True, "resetsAt": None, "endedAt": self.NOW - 60_000}]}
        self.assertTrue(cs.limit_stop(self.stop(self.NOW - 600_000), limits, self.NOW)["over"])
        # numbers from before the chat stopped say nothing about it: the time in its message does
        text = "You've hit your session limit · resets 7:10pm (Europe/Berlin)"
        at = int(datetime(2026, 10, 20, 15, 0).timestamp() * 1000)
        limits = {"windows": [{"key": "five_hour", "reset": True, "resetsAt": None, "endedAt": at - 3600_000}]}
        s = cs.limit_stop(self.stop(at, text=text), limits, at + 60_000)
        self.assertEqual((s["resetsAt"], s["over"]), (int(datetime(2026, 10, 20, 19, 10).timestamp() * 1000), False))

    def test_time_in_the_message(self):
        at = int(datetime(2026, 10, 20, 23, 0).timestamp() * 1000)
        self.assertEqual(cs.reset_from_text("… · resets 5:10am (Europe/Berlin)", at),
                         int(datetime(2026, 10, 21, 5, 10).timestamp() * 1000))
        self.assertEqual(cs.reset_from_text("resets 12am", at), int(datetime(2026, 10, 21, 0, 0).timestamp() * 1000))
        self.assertIsNone(cs.reset_from_text("You've hit your monthly spend limit.", at))
        # more than a day out, Claude names the day (and the year, if it isn't this one)
        self.assertEqual(cs.reset_from_text("You've hit your Sonnet limit · resets Oct 30, 7pm (Europe/Berlin)", at),
                         int(datetime(2026, 10, 30, 19, 0).timestamp() * 1000))
        self.assertEqual(cs.reset_from_text("… · resets Jan 2, 2027, 9:30am", at),
                         int(datetime(2027, 1, 2, 9, 30).timestamp() * 1000))
        self.assertIsNone(cs.reset_from_text("… · resets Feb 30, 9am", at))
        s = cs.limit_stop(self.stop(at, window=None, text="resets 5:10am"), None,
                          int(datetime(2026, 10, 21, 6, 0).timestamp() * 1000))
        self.assertTrue(s["over"])

    def test_login_and_unknown_limits_dont_reset(self):
        s = cs.limit_stop({"kind": "login", "window": None, "text": "Login expired", "at": 1}, None, self.NOW)
        self.assertEqual((s["resetsAt"], s["over"]), (None, False))

    def group_at(self, pct, stops, updated=None):
        w = {"key": "five_hour", "pct": pct, "reset": False, "resetsAt": self.NOW + 3 * 3600_000,
             "forecast": {"evenPct": 40.0, "rate": 50.0, "atReset": 224.0, "fullAt": self.NOW + 1800_000, "basis": "hour"}}
        return {"limits": {"updatedAt": updated or self.NOW - 1500_000, "windows": [w]},
                "sessions": [{"stopped": s} for s in stops[:1]], "recent": [{"stopped": s} for s in stops[1:]]}

    def test_a_limit_hit_after_the_numbers_fills_the_window(self):
        # 74% as of 25 min ago, and a chat hit the session limit 12 min ago
        g = self.group_at(74.0, [self.stop(self.NOW - 720_000)])
        cs.note_limit_hits(g)
        w = g["limits"]["windows"][0]
        self.assertEqual((w["pct"], w["forecast"]["fullAt"], w["forecast"]["atReset"]), (100.0, None, 224.0))
        # a recent chat (closed since) counts too
        g = self.group_at(74.0, [None, self.stop(self.NOW - 720_000)])
        cs.note_limit_hits(g)
        self.assertEqual(g["limits"]["windows"][0]["pct"], 100.0)

    def test_a_limit_hit_that_says_nothing_of_the_numbers(self):
        before = self.NOW - 4 * 3600_000
        for stop, updated in ((self.stop(self.NOW - 1800_000), None),  # before the numbers were read
                              (self.stop(self.NOW - 3 * 3600_000), before),  # in the window before this one
                              (self.stop(self.NOW - 720_000, window="seven_day"), None),  # of another window
                              (self.stop(self.NOW - 720_000, window=None), None),
                              ({"kind": "login", "window": None, "text": "Login expired", "at": self.NOW - 720_000}, None)):
            g = self.group_at(74.0, [stop], updated)
            cs.note_limit_hits(g)
            self.assertEqual(g["limits"]["windows"][0]["pct"], 74.0, stop)
            self.assertEqual(g["limits"]["windows"][0]["forecast"]["fullAt"], self.NOW + 1800_000)
        g = {"limits": None, "sessions": [{"stopped": self.stop(self.NOW)}]}
        cs.note_limit_hits(g)  # (no numbers at all)
        self.assertIsNone(g["limits"])

    def test_a_shared_chat_another_account_hit_the_limit_in(self):
        # stopped by the other account's limit 12 min ago, then continued on
        # this one (Continue on): its session here started after the stop
        for shared in ({"profiles": ["work", "personal"]}, {"profiles": ["work", "personal"], "forkOf": "c0"}):
            g = self.group_at(74.0, [self.stop(self.NOW - 720_000)])
            g["sessions"][0].update(shared=shared, startedAt=self.NOW - 60_000)
            cs.note_limit_hits(g)
            self.assertEqual(g["limits"]["windows"][0]["pct"], 74.0, shared)
        # one it hit while it ran here is this account's
        g = self.group_at(74.0, [self.stop(self.NOW - 720_000)])
        g["sessions"][0].update(shared={"profiles": ["work", "personal"]}, startedAt=self.NOW - 3600_000)
        cs.note_limit_hits(g)
        self.assertEqual(g["limits"]["windows"][0]["pct"], 100.0)
        # and a chat only this account has stopped here, whenever its session started
        g = self.group_at(74.0, [self.stop(self.NOW - 720_000)])
        g["sessions"][0].update(shared=None, startedAt=self.NOW - 60_000)
        cs.note_limit_hits(g)
        self.assertEqual(g["limits"]["windows"][0]["pct"], 100.0)

    def test_a_recent_shared_chat_another_account_hit_the_limit_in(self):
        # (recent chats have no session start: the reset Claude noted with the stop says whose window it was)
        theirs = dict(self.stop(self.NOW - 720_000), resets=self.NOW + 5 * 3600_000)
        g = self.group_at(74.0, [None, theirs])
        g["recent"][0]["shared"] = True
        cs.note_limit_hits(g)
        self.assertEqual(g["limits"]["windows"][0]["pct"], 74.0)
        # and it resets when that account's window does
        s = cs.limit_stop(theirs, g["limits"], self.NOW)
        self.assertEqual((s["resetsAt"], s["over"]), (self.NOW + 5 * 3600_000, False))
        ours = dict(self.stop(self.NOW - 720_000), resets=self.NOW + 3 * 3600_000 + 2000)
        g = self.group_at(74.0, [None, ours])
        g["recent"][0]["shared"] = True
        cs.note_limit_hits(g)
        self.assertEqual(g["limits"]["windows"][0]["pct"], 100.0)


class RowTests(Fixture):
    """The new fields of a listed chat (and a recent one): its plan, what stopped it."""

    def test_a_chat_stopped_by_the_limit_and_its_plan(self):
        w = self.home / ".claude-work"
        t = self.now - 1200
        write(w / "projects/-p/perso-idle-w.jsonl", "")
        write(w / "sessions/30.json", session("limited", cwd="/tmp/x"))
        write(w / "projects/-tmp-x/limited.jsonl",
              lines(prompt("plan it", t, slug="calm-red-owl", cwd="/tmp/x"),
                    reply("Planned.", t + 5, slug="calm-red-owl", cwd="/tmp/x"),
                    limit_error("You've hit your session limit · resets 7:10pm (Europe/Berlin)", t + 60)))
        write(w / "plans/calm-red-owl.md", "# Calm plan\n\n1. Do it\n")
        snap = self.cache / "statusline/.claude-work/limited.json"
        write(snap, {"session_id": "limited", "rate_limits": {
            "five_hour": {"used_percentage": 100, "resets_at": int(self.now + 1800)}}})
        g = self.group(self.collect(with_tokens=False), "work")
        row = next(s for s in g["sessions"] if s["sessionId"] == "limited")
        self.assertEqual(row["plan"]["title"], "Calm plan")
        self.assertEqual(row["plan"]["path"], str(w / "plans/calm-red-owl.md"))
        self.assertEqual((row["stopped"]["kind"], row["stopped"]["over"]), ("limit", False))
        self.assertEqual(row["stopped"]["resetsAt"], int(self.now + 1800) * 1000)
        # the account's plans, with the chat that made each
        plan = g["plans"][0]
        self.assertEqual((plan["slug"], plan["title"], plan["chatId"], plan["cwd"], plan["shared"]),
                         ("calm-red-owl", "Calm plan", "limited", "/tmp/x", False))

    def test_a_background_session_the_limit_blocked_waits_for_the_limit(self):
        # Claude marks it "blocked" ("rate limited — wait and retry"), as if it
        # needed you: it's stopped by the limit instead
        w = self.home / ".claude-work"
        sid = "e3de1242-7bc8-40a5-938f-aadb5f5aa9ee"
        write(w / "sessions/31.json", session(sid, kind="bg", jobId="e3de1242", cwd="/tmp/x"))
        write(w / "jobs/e3de1242/state.json", {
            "state": "blocked", "tempo": "blocked", "sessionId": sid, "cwd": "/tmp/x",
            "detail": "You've hit your session limit · resets 10:40am (Europe/Berlin)",
            "needs": "rate limited — wait and retry · You've hit your session limit · resets 10:40am (Europe/Berlin)"})
        write(w / f"projects/-tmp-x/{sid}.jsonl",
              lines(prompt("test", self.now - 60), limit_error("You've hit your session limit · resets 10:40am (Europe/Berlin)", self.now - 59)))
        g = self.group(self.collect(with_tokens=False), "work")
        row = next(s for s in g["sessions"] if s["sessionId"] == sid)
        self.assertEqual((row["state"], row["detail"], row["stopped"]["kind"]), ("idle", "", "limit"))
        # blocked on something else, it still needs you
        write(w / f"projects/-tmp-x/{sid}.jsonl", lines(prompt("test", self.now - 60)))
        row = next(s for s in self.group(self.collect(with_tokens=False), "work")["sessions"] if s["sessionId"] == sid)
        self.assertEqual((row["state"], row["stopped"]), ("waiting", None))

    def test_a_chat_that_went_on_by_itself_keeps_its_name(self):
        # Claude names the background session after the message it went on with
        w = self.home / ".claude-work"
        sid = "e3de1242-7bc8-40a5-938f-aadb5f5aa9ee"
        write(w / "sessions/32.json", session(sid, kind="bg", jobId="e3de1242", cwd="/tmp/x", name=cs.CONTINUE_PROMPT))
        write(w / "jobs/e3de1242/state.json", {"state": "working", "tempo": "active", "sessionId": sid})
        write(w / f"projects/-tmp-x/{sid}.jsonl", lines(prompt("fix the thesis build", self.now - 60), {"type": "ai-title", "aiTitle": "Thesis build fix"},
                                                     prompt(cs.CONTINUE_PROMPT, self.now - 10)))
        row = next(s for s in self.group(self.collect(with_tokens=False), "work")["sessions"] if s["sessionId"] == sid)
        self.assertEqual(row["name"], "Thesis build fix")
        # (also when it went on after a turn that broke off)
        write(w / "sessions/32.json", session(sid, kind="bg", jobId="e3de1242", cwd="/tmp/x", name=cs.RETRY_PROMPT))
        row = next(s for s in self.group(self.collect(with_tokens=False), "work")["sessions"] if s["sessionId"] == sid)
        self.assertEqual(row["name"], "Thesis build fix")

    def test_ultracode_stays_on_after_a_big_turn(self):
        # Claude notes it again only every 10th prompt: past a turn with big
        # tool results, the end of the transcript doesn't say
        on = {"type": "attachment", "attachment": {"type": "ultra_effort_enter", "reminderType": "full"}}
        big = {"type": "user", "timestamp": iso(self.now - 50),
               "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t", "content": "x" * 100_000}]}}
        path = self.home / ".claude-work/projects/-tmp-x/ultra.jsonl"
        write(self.home / ".claude-work/sessions/33.json", session("ultra", cwd="/tmp/x"))
        write(path, lines(prompt("go", self.now - 60), on, reply("On it.", self.now - 55), *[big] * 3,
                          reply("Done.", self.now - 40, msg_id="m2"), prompt("and now?", self.now - 30),
                          reply("Sure.", self.now - 20, msg_id="m3")))
        self.assertFalse(cs.chat_peek(path)["ultracode"])
        row = lambda: next(s for s in self.group(self.collect(with_tokens=False), "work")["sessions"] if s["sessionId"] == "ultra")
        self.assertTrue(row()["peek"]["ultracode"])
        # turned off: off
        with open(path, "a") as f:
            f.write(lines({"type": "attachment", "attachment": {"type": "ultra_effort_exit"}}, *[big] * 3,
                          prompt("more", self.now - 10), reply("Ok.", self.now - 5, msg_id="m4")))
        self.assertFalse(row()["peek"]["ultracode"])

    def test_working_again_isnt_stopped(self):
        w = self.home / ".claude-work"
        write(w / "projects/-x/busy.jsonl", lines(limit_error("You've hit your session limit", self.now - 60)))
        g = self.group(self.collect(with_tokens=False), "work")
        self.assertIsNone(next(s for s in g["sessions"] if s["sessionId"] == "busy")["stopped"])

    def test_plans_newest_first_and_shared_once(self):
        w, p = self.home / ".claude-work", self.home / ".claude-personal"
        for i, slug in enumerate(["old-plan", "new-plan"]):
            write(w / f"plans/{slug}.md", f"# {slug}\n")
            os.utime(w / f"plans/{slug}.md", (self.now - 1000 + i, self.now - 1000 + i))
        write(w / "plans/not a slug.md", "# no\n")
        (p / "plans").mkdir(parents=True)
        os.link(w / "plans/new-plan.md", p / "plans/new-plan.md")
        r = self.collect(with_tokens=False)
        work = self.group(r, "work")
        self.assertEqual([(x["slug"], x["shared"]) for x in work["plans"]], [("new-plan", True), ("old-plan", False)])
        self.assertEqual([x["slug"] for x in self.group(r, "personal")["plans"]], ["new-plan"])
        self.assertEqual(self.collect(with_tokens=False, plans=1)["groups"][1]["plans"][0]["slug"], "new-plan")

    def test_starred_plans_stay_listed(self):
        w = self.home / ".claude-work"
        for i, slug in enumerate(["old-plan", "mid-plan", "new-plan"]):
            write(w / f"plans/{slug}.md", f"# {slug}\n")
            os.utime(w / f"plans/{slug}.md", (self.now - 1000 + i, self.now - 1000 + i))
        cs.change_stars(self.cache, "plans", "old-plan")
        cs.change_stars(self.cache, "plans", "mid-plan", host="lab")  # (an SSH host's)
        work = self.group(self.collect(with_tokens=False, plans=1), "work")
        self.assertEqual([(x["slug"], x["starred"]) for x in work["plans"]], [("new-plan", False)])
        self.assertEqual([(x["slug"], x["title"], x["key"]) for x in work["starredPlans"]],
                         [("old-plan", "old-plan", ".claude-work/old-plan/starred")])
        cs.change_stars(self.cache, "plans", "new-plan")
        work = self.group(self.collect(with_tokens=False), "work")
        self.assertEqual([(x["slug"], x["starred"]) for x in work["plans"]],
                         [("new-plan", True), ("mid-plan", False), ("old-plan", True)])
        self.assertEqual([x["slug"] for x in work["starredPlans"]], ["new-plan", "old-plan"])

    def test_starring_and_an_ssh_hosts_stars(self):
        home = self.home
        with mock.patch.object(jump.Path, "home", return_value=home):
            self.assertEqual(jump.star(home, "chats", "e3de1242-7bc8-40a5-938f-aadb5f5aa9ee"), (True, ""))
            self.assertEqual(jump.star(home, "plans", "calm-red-owl", "lab"), (True, ""))
            self.assertFalse(jump.star(home, "plans", "../etc/passwd")[0])
        stars = cs.load_stars(cs.cache_dir(home))
        self.assertEqual(stars, {"chats": [{"id": "e3de1242-7bc8-40a5-938f-aadb5f5aa9ee", "host": ""}],
                                 "plans": [{"id": "calm-red-owl", "host": "lab"}]})
        # the host's status run gets them from here
        import remote
        with mock.patch.object(remote.Path, "home", return_value=home), \
                mock.patch.object(remote, "ssh", side_effect=OSError("stop here")) as ssh:
            remote.status("lab")
        self.assertIn("--starred-plans calm-red-owl", ssh.call_args[0][1])
        self.assertNotIn("--starred-chats", ssh.call_args[0][1])
        jump.star(home, "plans", "calm-red-owl", "lab", on=False)
        self.assertEqual(cs.load_stars(cs.cache_dir(home))["plans"], [])

    def test_slugs_are_read_from_what_was_appended(self):
        path = self.home / ".claude-work/projects/-p/chat7.jsonl"
        write(path, lines(prompt("plan it", self.now - 60, slug="calm-red-owl")))
        slugs = cs.SlugCache(self.cache / "plans.json")
        self.assertEqual(slugs.slug(path, path.stat()), "calm-red-owl")
        reads = []
        real = cs.transcript_slug
        with mock.patch.object(cs, "transcript_slug", lambda p, size, start=0: reads.append(start) or real(p, size, start)):
            with open(path, "a") as f:
                f.write(lines(reply("Planned.", self.now - 50)))   # no slug in what came: it keeps its own
            self.assertEqual(slugs.slug(path, path.stat()), "calm-red-owl")
            size = path.stat().st_size
            self.assertEqual(slugs.slug(path, path.stat()), "calm-red-owl")   # unchanged: nothing read
        self.assertEqual(reads, [size - len(lines(reply("Planned.", self.now - 50)))])
        slugs.save()
        self.assertEqual(cs.SlugCache(self.cache / "plans.json").slug(path, path.stat()), "calm-red-owl")

    def test_recent_chats_carry_their_recap(self):
        w = self.home / ".claude-work"
        t = self.now - 3600
        write(w / "projects/-r/oldchat.jsonl", lines(prompt("tidy up", t, cwd="/r"), reply("Tidied.", t + 5, cwd="/r"),
                                                    recap("You asked me to tidy up; done.", t + 100)))
        recent = self.group(self.collect(with_tokens=False), "work")["recent"]
        chat = next(c for c in recent if c["sessionId"] == "oldchat")
        self.assertEqual((chat["recap"]["text"], chat["stopped"]), ("You asked me to tidy up; done.", None))

    def test_trusted_folders(self):
        w = self.home / ".claude-work"
        repo = self.home / "repos/app"
        (repo / ".git").mkdir(parents=True)
        (repo / "sub").mkdir()
        other = self.home / "notes/a"
        other.mkdir(parents=True)
        data = json.loads((w / ".claude.json").read_text())
        data["projects"] = {str(self.home / "repos"): {"hasTrustDialogAccepted": True},
                            str(self.home / "notes"): {"hasTrustDialogAccepted": True}}
        write(w / ".claude.json", data)
        profile = next(p for p in cs.discover_profiles(self.home) if p.label == "work")
        # Claude looks up the folders above, but not past a git repository's root
        self.assertTrue(cs.folder_trusted(profile, str(other), self.home))
        self.assertFalse(cs.folder_trusted(profile, str(repo / "sub"), self.home))
        data["projects"][str(repo)] = {"hasTrustDialogAccepted": True}
        write(w / ".claude.json", data)
        self.assertTrue(cs.folder_trusted(profile, str(repo / "sub"), self.home))
        # Claude never keeps trusting the home folder (an old record of it doesn't count)
        data["projects"][str(self.home)] = {"hasTrustDialogAccepted": True}
        write(w / ".claude.json", data)
        self.assertFalse(cs.folder_trusted(profile, str(self.home), self.home))

    def test_a_worktree_is_trusted_when_its_repository_is(self):
        # Claude keeps a worktree's trust under the repository it belongs to
        # (a chat that went on in one of its own, .claude/worktrees/x): its
        # .git is a file naming .git/worktrees/x there, which names it back
        w = self.home / ".claude-work"
        repo = self.home / "repos/app"
        tree = repo / ".claude/worktrees/round"
        gitdir = repo / ".git/worktrees/round"
        gitdir.mkdir(parents=True)
        (tree / "sub").mkdir(parents=True)
        (tree / ".git").write_text(f"gitdir: {gitdir}\n")
        (gitdir / "commondir").write_text("../..\n")
        (gitdir / "gitdir").write_text(f"{tree / '.git'}\n")
        data = json.loads((w / ".claude.json").read_text())
        data["projects"] = {str(self.home / "notes"): {"hasTrustDialogAccepted": True}}
        write(w / ".claude.json", data)
        profile = next(p for p in cs.discover_profiles(self.home) if p.label == "work")
        self.assertFalse(cs.folder_trusted(profile, str(tree), self.home))
        data["projects"][str(repo)] = {"hasTrustDialogAccepted": True}
        write(w / ".claude.json", data)
        self.assertTrue(cs.folder_trusted(profile, str(tree), self.home))
        self.assertTrue(cs.folder_trusted(profile, str(tree / "sub"), self.home))
        self.assertEqual(cs.main_repository(repo), repo)              # (the repository itself)
        # not one that only says so: its git folder doesn't name it back
        (gitdir / "gitdir").write_text(f"{self.home / 'elsewhere/.git'}\n")
        self.assertFalse(cs.folder_trusted(profile, str(tree), self.home))
        # a relative gitdir, as git writes with worktree.useRelativePaths
        (gitdir / "gitdir").write_text("../../../.claude/worktrees/round/.git\n")
        (tree / ".git").write_text("gitdir: ../../../.git/worktrees/round\n")
        self.assertTrue(cs.folder_trusted(profile, str(tree), self.home))


class FindTests(Fixture):
    def setUp(self):
        super().setUp()
        w, p = self.home / ".claude-work", self.home / ".claude-personal"
        t = self.now - 7200
        write(w / "projects/-a/aaa.jsonl", lines(prompt("refactor the parser", t, cwd="/srv/app"),
                                                 reply("Done.", t + 1, cwd="/srv/app"),
                                                 {"type": "ai-title", "aiTitle": "Parser cleanup"}))
        write(w / "projects/-b/bbb.jsonl", lines(prompt("write docs", t + 10, cwd="/srv/docs"),
                                                 reply("Done.", t + 11, cwd="/srv/docs")))
        write(w / "history.jsonl", lines({"display": "write docs", "sessionId": "bbb", "timestamp": (t + 10) * 1000},
                                         {"display": "and mention the PARSER flags", "sessionId": "bbb",
                                          "timestamp": (t + 20) * 1000}))
        os.utime(w / "projects/-b/bbb.jsonl", (t + 30, t + 30))
        os.utime(w / "projects/-a/aaa.jsonl", (t + 5, t + 5))
        # a chat shared with personal, used there last
        write(w / "projects/-c/ccc.jsonl", lines(prompt("parser tests", t, cwd="/srv/app"), reply("Ok.", t + 1, cwd="/srv/app")))
        (p / "projects/-c").mkdir(parents=True)
        os.link(w / "projects/-c/ccc.jsonl", p / "projects/-c/ccc.jsonl")
        write(p / "history.jsonl", lines({"display": "parser tests", "sessionId": "ccc", "timestamp": (t + 40) * 1000}))
        os.utime(w / "projects/-c/ccc.jsonl", (t, t))

    def find(self, query, limit=30):
        return cs.find_chats(self.home, self.cache, [], query, limit)

    def test_every_word_in_name_folder_or_prompts(self):
        found = self.find("parser")
        self.assertEqual([c["sessionId"] for c in found["results"]], ["bbb", "aaa", "ccc"])
        docs = found["results"][0]
        self.assertEqual((docs["name"], docs["account"], docs["match"]),
                         ("write docs", "work · Team", "and mention the PARSER flags"))
        self.assertEqual(found["results"][1]["name"], "Parser cleanup")
        self.assertEqual([c["sessionId"] for c in self.find("PARSER srv/app")["results"]], ["aaa", "ccc"])
        self.assertEqual(self.find("nothing like this")["results"], [])
        self.assertEqual(self.find("   ")["results"], [])

    def test_says_when_by_its_clock(self):
        # (an SSH host's answer: its times are put on this computer's clock by it)
        before = int(time.time() * 1000)
        self.assertTrue(before <= self.find("parser")["generatedAt"] <= int(time.time() * 1000))

    def test_project_folders_plans_and_memories_too(self):
        w = self.home / ".claude-work"
        write(w / "plans/calm-red-owl.md", "# Release plan\n\nBump the PARSER version.\n")
        write(w / "plans/other-plan-here.md", "# Docs\n\nNothing to see.\n")
        write(w / "projects/-srv-app/memory/parser-flags.md",
              "---\nname: parser-flags\ndescription: Strict mode is on\ntype: project\n---\n\nThe parser runs with --strict.\n")
        found = self.find("parser")
        self.assertEqual([p["slug"] for p in found["plans"]], ["calm-red-owl"])  # (by its text)
        self.assertEqual((found["plans"][0]["title"], found["plans"][0]["account"]), ("Release plan", "work · Team"))
        self.assertEqual([m["name"] for m in found["memories"]], ["parser-flags"])
        self.assertEqual(found["memories"][0]["account"], "work · Team")
        self.assertEqual(found["projects"], [])  # (no folder with "parser" in its path)
        app = self.find("srv/app")["projects"]
        self.assertEqual([(p["folder"], p["chats"], p["account"]) for p in app], [("/srv/app", 2, "work · Team")])
        self.assertEqual(self.find("nothing like this")["memories"], [])

    def test_a_shared_chat_once_on_the_account_it_was_used_on_last(self):
        ccc = [c for c in self.find("tests")["results"] if c["sessionId"] == "ccc"]
        self.assertEqual([(c["profileDir"], c["shared"]) for c in ccc], [(".claude-personal", True)])
        with open(self.home / ".claude-work/history.jsonl", "a") as f:   # then used on work
            f.write(lines({"display": "more parser tests", "sessionId": "ccc", "timestamp": (self.now - 60) * 1000}))
        ccc = [c for c in self.find("tests")["results"] if c["sessionId"] == "ccc"]
        self.assertEqual([(c["profileDir"], c["account"]) for c in ccc], [(".claude-work", "work · Team")])

    def test_a_chat_and_its_copies_once(self):
        w = self.home / ".claude-work"
        t = self.now - 7200
        start = dict(prompt("refactor the parser", t, cwd="/srv/app"), uuid="u-first")
        write(w / "projects/-a/fork.jsonl", lines(start, reply("Forked.", t + 50, cwd="/srv/app")))
        os.utime(w / "projects/-a/fork.jsonl", (t + 60, t + 60))
        write(w / "projects/-a/aaa.jsonl", lines(start, reply("Done.", t + 1, cwd="/srv/app"),
                                                 {"type": "ai-title", "aiTitle": "Parser cleanup"}))
        os.utime(w / "projects/-a/aaa.jsonl", (t + 5, t + 5))
        self.assertEqual([c["sessionId"] for c in self.find("refactor")["results"]], ["fork"])

    def test_limit(self):
        found = self.find("parser", limit=2)
        self.assertEqual((len(found["results"]), found["more"]), (2, True))

    def test_command_line(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.object(cs.Path, "home", return_value=self.home), \
                mock.patch.object(cs, "cache_dir", return_value=self.cache):
            cs.main(["--find", "docs", "--remote"])
        answer = json.loads(out.getvalue().split(cs.REMOTE_MARK)[1])
        self.assertEqual([c["sessionId"] for c in answer["results"]], ["bbb"])
        self.assertIn("--resume bbb", answer["results"][0]["openCommand"])


FAKE_CLAUDE = """#!{python}
import json, os, sys
with open({log!r}, "a") as f:
    f.write(json.dumps({{"argv": sys.argv[1:], "cwd": os.getcwd(),
                         "config": os.environ.get("CLAUDE_CONFIG_DIR"),
                         "session": os.environ.get("CLAUDECODE"),
                         "noAgentView": os.environ.get("CLAUDE_CODE_DISABLE_AGENT_VIEW")}}) + "\\n")
if "--bg" in sys.argv:  # (what Claude Code 2.1.306 prints)
    print("backgrounded · 1a2b3c4d\\n  claude agents             list sessions\\n"
          "  claude attach 1a2b3c4d    open in this terminal\\n  claude stop 1a2b3c4d      stop this session")
"""


class TaskFixture(Fixture):
    """A fake claude that notes how it was run, a trusted folder and a plan."""

    def setUp(self):
        super().setUp()
        self.bin = self.home / "bin"
        self.log = self.home / "claude.log"
        write(self.bin / "claude", FAKE_CLAUDE.format(python=sys.executable, log=str(self.log)))
        (self.bin / "claude").chmod(0o755)
        self.folder = self.home / "repos/app"
        self.folder.mkdir(parents=True)
        w = self.home / ".claude-work"
        data = json.loads((w / ".claude.json").read_text())
        data["projects"] = {str(self.folder): {"hasTrustDialogAccepted": True}}
        write(w / ".claude.json", data)
        write(w / "plans/calm-red-owl.md", "# Calm plan\n\n1. Do it\n")
        self.profile = next(p for p in cs.discover_profiles(self.home) if p.label == "work")

    def calls(self):
        return [json.loads(l) for l in self.log.read_text().splitlines()] if self.log.exists() else []


class TaskTests(TaskFixture):
    def test_prompt_with_a_plan(self):
        text = cs.task_prompt("Do step 1 only.", self.home / ".claude-work/plans/calm-red-owl.md", self.home)
        self.assertEqual(text, "Do step 1 only.\n\nThe plan (saved as ~/.claude-work/plans/calm-red-owl.md):\n\n"
                               "# Calm plan\n\n1. Do it\n")
        self.assertTrue(cs.task_prompt("", self.home / ".claude-work/plans/calm-red-owl.md", self.home)
                        .startswith("Implement this plan.\n"))

    def test_a_long_plan_fits_in_an_ssh_hosts_terminal(self):
        # every ' grows each time the prompt is quoted: in the host's command,
        # its sh -c and the ssh line of the terminal (one argument: 128 KB)
        import remote
        plan = self.home / ".claude-work/plans/long-plan.md"
        write(plan, "# Long plan\n\n" + "It's the user's step, don't skip it.\n" * 2400)  # 86 KB
        prompt = cs.task_prompt("Go.", plan, self.home)
        line = remote.posix(cs.task_command(self.profile, prompt, self.home))
        self.assertLess(len(shlex.quote(line).encode()), 128 * 1024)
        self.assertTrue(prompt.startswith("Go.\n\nThe plan (saved as ~/.claude-work/plans/long-plan.md):\n\n# Long plan\n"))
        self.assertTrue(prompt.endswith("don't skip it.\n\n(The plan goes on in that file.)\n"), prompt[-80:])
        # (a plan longer than TASK_PLAN_MAX is cut too, and says so)
        write(plan, "x" * (cs.TASK_PLAN_MAX + 10))
        self.assertTrue(cs.task_prompt("", plan, self.home).endswith("x\n\n(The plan goes on in that file.)\n"))

    def test_background(self):
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1", "CLAUDE_CODE_DISABLE_AGENT_VIEW": "1"}):
            ok, message, job = cs.start_background(self.profile, str(self.folder), "--fix the tests",
                                                   self.home, str(self.bin / "claude"))
        self.assertEqual((ok, job), (True, "1a2b3c4d"), message)
        call, = self.calls()
        # a prompt that looks like an option stays the prompt; the account's
        # folder by name; not as part of this session
        self.assertEqual(call["argv"], ["--bg", " --fix the tests"])
        self.assertEqual((call["cwd"], call["config"], call["session"]),
                         (str(self.folder), str((self.home / ".claude-work").resolve()), None))
        self.assertIsNone(call["noAgentView"])   # (Claude refuses --bg with it)

    def test_a_one_word_task_isnt_one_of_claudes_commands(self):
        # `claude update` would update Claude, not start a chat about it
        self.assertEqual([cs.prompt_arg(p) for p in ("update", "doctor", "fix-it", "update the docs", "Fix it.")],
                         [" update", " doctor", " fix-it", "update the docs", "Fix it."])
        self.assertTrue(cs.task_command(self.profile, "install", self.home).endswith(" ' install'"))

    def test_background_needs_a_trusted_folder(self):
        for folder in (str(self.home), str(self.home / "repos")):
            ok, message, _ = cs.start_background(self.profile, folder, "go", self.home, str(self.bin / "claude"))
            self.assertFalse(ok)
            self.assertIn("doesn't trust", message)
        self.assertEqual(self.calls(), [])

    def test_background_reports_claudes_refusal(self):
        write(self.bin / "claude", f"#!{sys.executable}\nimport sys\nprint('Workspace not trusted.', file=sys.stderr)\nsys.exit(1)\n")
        ok, message, _ = cs.start_background(self.profile, str(self.folder), "go", self.home, str(self.bin / "claude"))
        self.assertEqual((ok, message), (False, "Workspace not trusted."))

    def test_terminal_command(self):
        answer = cs.run_task(self.home, [], False, str(self.folder), ".claude-work", "go on", "calm-red-owl",
                             claude="claude")
        self.assertTrue(answer["ok"])
        words = shlex.split(answer["command"])
        self.assertEqual(words[:3], ["cd", str(self.folder), "2>/dev/null;"])
        self.assertIn("CLAUDE_CODE_DISABLE_AGENT_VIEW=1", words)
        self.assertTrue(words[-1].startswith("go on\n\nThe plan (saved as ~/.claude-work/plans/calm-red-owl.md)"))
        gone = cs.run_task(self.home, [], False, str(self.folder), ".claude-work", "", "no-such-plan", claude="claude")
        self.assertEqual(gone, {"ok": False, "message": "That plan isn't there any more"})

    def test_jump_new_chat_with_a_task(self):
        opened = []
        out = io.StringIO()
        prefixes = []
        with mock.patch.object(jump, "open_terminal", lambda cwd, command: opened.append((cwd, command)) or True), \
                mock.patch.object(jump, "scope_prefix", lambda name: prefixes.append(name) or []), \
                mock.patch.object(jump, "claude_in_terminal", return_value="claude"), \
                mock.patch.object(jump, "claude_path", return_value=str(self.bin / "claude")), \
                mock.patch.object(jump.Path, "home", return_value=self.home), contextlib.redirect_stdout(out):
            jump.main(["--new-chat", ".claude-work", "--cwd", str(self.folder), "--prompt", "write tests"])
            jump.main(["--new-chat", ".claude-work", "--cwd", str(self.folder), "--plan", "calm-red-owl", "--bg"])
            jump.main(["--new-chat", ".claude-work", "--cwd", str(self.folder), "--plan", "gone", "--bg"])
        answers = [json.loads(l) for l in out.getvalue().splitlines()]
        self.assertEqual([a["ok"] for a in answers], [True, True, False])
        self.assertEqual(answers[2]["message"], "That plan isn't there any more")
        (cwd, command), = opened
        self.assertEqual(cwd, str(self.folder))
        self.assertEqual(shlex.split(command)[-1], "write tests")
        call, = self.calls()
        self.assertTrue(call["argv"][1].startswith("Implement this plan.\n\nThe plan (saved as"))
        self.assertEqual(prefixes, ["claude"])   # in a systemd scope of its own (the service may start with it)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            jump.main(["--new-chat", ".claude-work", "--bg", "--vscode", "--prompt", "x"])

    def test_a_new_chat_with_the_model_and_effort_you_picked(self):
        opened = []
        out = io.StringIO()
        with mock.patch.object(jump, "open_terminal", lambda cwd, command: opened.append(command) or True), \
                mock.patch.object(jump, "scope_prefix", lambda name: []), \
                mock.patch.object(jump, "claude_in_terminal", return_value="claude"), \
                mock.patch.object(jump, "claude_path", return_value=str(self.bin / "claude")), \
                mock.patch.object(jump.Path, "home", return_value=self.home), contextlib.redirect_stdout(out):
            jump.main(["--new-chat", ".claude-work", "--cwd", str(self.folder), "--model", "opus", "--effort", "xhigh"])
            jump.main(["--new-chat", ".claude-work", "--cwd", str(self.folder), "--prompt", "write tests",
                       "--model", "claude-opus-5-5[1m]", "--effort", "max"])
            jump.main(["--new-chat", ".claude-work", "--cwd", str(self.folder), "--prompt", "go on", "--bg",
                       "--model", "sonnet", "--effort", "high", "--permission-mode", "plan"])
            jump.main(["--new-chat", ".claude-work", "--cwd", str(self.folder), "--model", "opus", "--effort", "extreme"])
            jump.main(["--new-chat", ".claude-work", "--cwd", str(self.folder), "--model", "opus; rm -rf ~"])
            jump.main(["--new-chat", ".claude-work", "--cwd", str(self.folder), "--permission-mode", "yolo"])
            jump.main(["--new-chat", ".claude-work", "--cwd", str(self.folder), "--permission-mode", "manual"])
        answers = [json.loads(l) for l in out.getvalue().splitlines()]
        self.assertEqual([a["ok"] for a in answers], [True, True, True, False, False, False, True])
        self.assertIn("Not an effort level: extreme", answers[3]["message"])
        self.assertEqual(answers[4]["message"], "Not a model name: opus; rm -rf ~")
        self.assertIn("Not a permission mode: yolo", answers[5]["message"])
        plain, task, manual = (shlex.split(c) for c in opened)
        self.assertEqual(plain[-4:], ["--model", "opus", "--effort", "xhigh"])
        self.assertEqual(task[-5:], ["--model", "claude-opus-5-5[1m]", "--effort", "max", "write tests"])
        self.assertEqual(manual[-2:], ["--permission-mode", "default"], "(the name older Claude knows too)")
        call, = self.calls()
        self.assertEqual(call["argv"], ["--bg", "--model", "sonnet", "--effort", "high", "--permission-mode", "plan", "go on"])
        # an SSH host's task, there: the same
        answer = cs.run_task(self.home, [], False, str(self.folder), ".claude-work", "go on", model="opus",
                             effort="xhigh", claude="claude", mode="auto")
        self.assertEqual(shlex.split(answer["command"])[-7:], ["--model", "opus", "--effort", "xhigh",
                                                               "--permission-mode", "auto", "go on"])
        # (Claude's own defaults when none was picked)
        self.assertNotIn("--model", cs.run_task(self.home, [], False, str(self.folder), ".claude-work", "go",
                                                claude="claude")["command"])

    def test_vscode_link_types_the_task_in(self):
        # whole, though VS Code decodes the link before the Claude extension does
        task = "Run make && make test, then port the C++ parser (100% of it)\n#2: a=b?"
        link = jump.vscode_task_link(task)
        self.assertTrue(link.startswith("vscode://anthropic.claude-code/open?prompt="), link)
        self.assertEqual(vscode_link_params(link), {"prompt": task})
        self.assertEqual(jump.vscode_task_link(""), "vscode://anthropic.claude-code/open")

    def test_a_long_plans_vscode_link_fits_in_one_argument(self):
        # in the link, most characters but letters and digits take 5 (%25XX),
        # and the link is one argument (of xdg-open, then VS Code): 128 KB at most
        import remote
        plan = self.home / ".claude-work/plans/code-plan.md"
        write(plan, "# Code plan\n\n" + "    if (a[i] != b[i]) { return -1; }\n" * 2600)  # 96 KB
        with mock.patch.object(jump, "vscode_for", return_value=("/usr/bin/code", self.profile)), \
                mock.patch.object(jump, "start_vscode_chat") as started:
            ok, message = jump.new_chat_vscode(self.home, [], ".claude-work", str(self.folder),
                                               jump.Task("Go.", "code-plan"))
            self.assertTrue(ok, message)
            link = started.call_args[0][2]
            self.assertLess(len(link.encode()), 128 * 1024)
            self.assertTrue(vscode_link_params(link)["prompt"].endswith("return -1; }\n\n(The plan goes on in that file.)\n"))
            # a task too long by itself isn't cut: it says so, and nothing opens
            ok, message = jump.new_chat_vscode(self.home, [], ".claude-work", str(self.folder), jump.Task("[x] " * 40000))
            self.assertEqual((ok, started.call_count), (False, 1))
            self.assertIn("too long", message)
        # an SSH host's plan too
        with mock.patch.object(remote, "plan_text", return_value={"ok": True, "markdown": plan.read_text(),
                                                                  "where": "~/.claude/plans/code-plan.md"}), \
                mock.patch.object(jump, "remote_vscode", side_effect=lambda host, folder, link, what: (True, link)):
            ok, link = jump.new_chat_remote_vscode("lab", "/srv", task=jump.Task("Go.", "code-plan"))
        self.assertLess(len(link.encode()), 128 * 1024)
        self.assertTrue(vscode_link_params(link)["prompt"].endswith("(The plan goes on in that file.)\n"))


class PlanSharingTests(Fixture):
    def setUp(self):
        super().setUp()
        self.w, self.p = self.home / ".claude-work", self.home / ".claude-personal"
        write(self.w / "plans/calm-red-owl.md", "# Calm plan\n")
        self.profiles = cs.discover_profiles(self.home)
        self.work = sharing.named(self.profiles, ".claude-work")
        self.personal = sharing.named(self.profiles, ".claude-personal")

    def test_share_and_keep_only(self):
        ok, message = sharing.plan_sharing(self.profiles, "calm-red-owl", ".claude-work", True, ".claude-personal")
        self.assertTrue(ok, message)
        self.assertTrue(os.path.samefile(self.w / "plans/calm-red-owl.md", self.p / "plans/calm-red-owl.md"))
        self.assertFalse((self.home / ".claude/plans/calm-red-owl.md").exists())
        # a change on one is a change on both (Claude writes plans in place)
        with open(self.p / "plans/calm-red-owl.md", "a") as f:
            f.write("2. More\n")
        self.assertIn("2. More", (self.w / "plans/calm-red-owl.md").read_text())
        ok, message = sharing.plan_sharing(self.profiles, "calm-red-owl", ".claude-personal", False)
        self.assertTrue(ok, message)
        self.assertEqual((self.w / "plans/calm-red-owl.md").exists(), False)
        self.assertTrue((self.p / "plans/calm-red-owl.md").exists())
        self.assertEqual(sharing.plan_sharing(self.profiles, "calm-red-owl", ".claude-personal", False),
                         (False, "This plan isn't shared"))

    def test_another_plan_of_that_name_stays(self):
        write(self.p / "plans/calm-red-owl.md", "# Another\n")
        ok, message = sharing.plan_sharing(self.profiles, "calm-red-owl", ".claude-work", True, ".claude-personal")
        self.assertFalse(ok)
        self.assertIn("another plan of that name", message)
        self.assertEqual((self.p / "plans/calm-red-owl.md").read_text(), "# Another\n")

    def test_a_shared_chat_takes_its_plan_along(self):
        write(self.w / "projects/-p/chat9.jsonl", lines(prompt("plan", self.now - 60, slug="calm-red-owl")))
        target, there = sharing.give_to(self.profiles, "chat9", ".claude-personal", sharing.store_root(self.home))
        self.assertIsNotNone(target, there)
        self.assertTrue(os.path.samefile(self.w / "plans/calm-red-owl.md", self.p / "plans/calm-red-owl.md"))

    def test_jump_command_line(self):
        out = io.StringIO()
        with mock.patch.object(jump.Path, "home", return_value=self.home), contextlib.redirect_stdout(out):
            jump.main(["--share-plan", "calm-red-owl", "--profile", ".claude-work"])
        self.assertTrue(json.loads(out.getvalue())["ok"])
        self.assertTrue((self.home / ".claude/plans/calm-red-owl.md").exists())


class HandoverTests(Fixture):
    """Continuing a chat a usage limit stopped on another account: an idle
    session that has it open quits first; one in VS Code isn't touched."""

    def test_vscode_and_busy_sessions_stay(self):
        w = self.home / ".claude-work"
        write(w / "sessions/40.json", session("in-vscode", entrypoint="claude-vscode"))
        ok, message = cs.end_for_handover(self.home, cs.discover_profiles(self.home), "in-vscode")
        self.assertEqual((ok, message), (False, "It's open in VS Code's Claude: close its tab there first"))
        ok, message = cs.end_for_handover(self.home, cs.discover_profiles(self.home), "busy")
        self.assertEqual((ok, message), (False, "It's at work again, so it stays where it is"))
        self.assertEqual(cs.end_for_handover(self.home, cs.discover_profiles(self.home), "nobody"),
                         (True, "Nothing had it open"))

    def test_an_idle_chat_in_a_terminal_quits(self):
        proc = subprocess.Popen([sys.executable, "-c", "import time; print('ready', flush=True); time.sleep(60)"],
                                stdout=subprocess.PIPE, text=True)
        self.addCleanup(proc.stdout.close)
        self.addCleanup(lambda: (proc.kill(), proc.wait()) if proc.poll() is None else None)
        self.assertEqual(proc.stdout.readline().strip(), "ready")
        w = self.home / ".claude-work"
        write(w / f"sessions/{proc.pid}.json", session("limited", pid=proc.pid, procStart=cs.proc_start_time(proc.pid)))
        write(w / "projects/-p/limited.jsonl", lines(prompt("go", self.now - 60)))
        # (its parent here reaps it once it quits, as a terminal's shell does)
        reaper = threading.Thread(target=proc.wait)
        reaper.start()
        self.addCleanup(reaper.join, 10)
        target, there = sharing.give_to(cs.discover_profiles(self.home), "limited", ".claude-personal",
                                        sharing.store_root(self.home), end_first=True, home=self.home)
        self.assertEqual(proc.wait(timeout=5), -15)
        self.assertIsNotNone(target, there)
        self.assertTrue((self.home / ".claude-personal/projects/-p/limited.jsonl").exists())


if __name__ == "__main__":
    unittest.main()


class QueueTests(TaskFixture):
    """Background tasks that wait for a usage limit to reset."""

    def queue(self, *args):
        out = io.StringIO()
        with mock.patch.object(jump.Path, "home", return_value=self.home), \
                mock.patch.object(jump, "claude_path", return_value=str(self.bin / "claude")), \
                mock.patch.object(jump, "scope_prefix", return_value=[]), contextlib.redirect_stdout(out):
            jump.main(list(args))
        return json.loads(out.getvalue())

    def test_queue_then_start_once(self):
        at = int((time.time() + 3600) * 1000)
        answer = self.queue("--queue", ".claude-work", "--cwd", str(self.folder), "--at", str(at), "--prompt", "fix it",
                            "--plan", "calm-red-owl", "--plan-profile", ".claude-work", "--account", "work · Team")
        self.assertTrue(answer["ok"], answer)
        self.assertRegex(answer["message"], r"^Queued: it starts (tomorrow )?at \d\d:\d\d, when the limit resets$")
        (task,) = cs.queued_tasks(self.cache_root(), int(time.time() * 1000))
        self.assertEqual((task["prompt"], task["plan"], task["planTitle"], task["account"], task["due"]),
                         ("fix it", "calm-red-owl", "Calm plan", "work · Team", False))
        self.assertTrue(cs.queued_tasks(self.cache_root(), at + 1)[0]["due"])
        # the status lists it
        status = cs.collect(self.home, self.cache_root(), with_tokens=False, now=self.now)
        self.assertEqual([t["id"] for t in status["queue"]], [task["id"]])
        # starting it takes it out of the queue: a second copy starts nothing
        self.assertEqual(self.queue("--start-queued", task["id"]), {"ok": True, "message": "Started in the background on work (1a2b3c4d)"})
        self.assertEqual(self.queue("--start-queued", task["id"]), {"ok": True, "message": ""})
        call, = self.calls()
        self.assertEqual(call["argv"][0], "--bg")
        self.assertTrue(call["argv"][1].startswith("fix it\n\nThe plan (saved as"))
        self.assertEqual(cs.load_queue(self.cache_root()), [])

    def cache_root(self):
        return cs.cache_dir(self.home)

    def test_a_task_that_fails_to_start_stays_with_the_error(self):
        at = int(time.time() * 1000)
        self.assertTrue(self.queue("--queue", ".claude-work", "--cwd", str(self.folder), "--at", str(at), "--prompt", "go")["ok"])
        (task,) = cs.load_queue(self.cache_root())
        write(self.bin / "claude", f"#!{sys.executable}\nimport sys\nprint('Workspace not trusted.', file=sys.stderr)\nsys.exit(1)\n")
        self.assertEqual(self.queue("--start-queued", task["id"]), {"ok": False, "message": "Workspace not trusted."})
        (back,) = cs.queued_tasks(self.cache_root(), at + 1)
        self.assertEqual((back["id"], back["error"], back["due"]), (task["id"], "Workspace not trusted.", False))
        self.assertEqual(self.queue("--unqueue", task["id"]), {"ok": True, "message": "Cancelled the queued task"})
        self.assertEqual(cs.load_queue(self.cache_root()), [])

    def test_a_queued_task_starts_with_its_model_and_effort(self):
        at = str(int(time.time() * 1000))
        self.assertTrue(self.queue("--queue", ".claude-work", "--cwd", str(self.folder), "--at", at, "--prompt", "do it later",
                                   "--model", "opus", "--effort", "xhigh", "--permission-mode", "acceptEdits")["ok"])
        (task,) = cs.load_queue(self.cache_root())
        self.assertEqual((task["model"], task["effort"], task["mode"]), ("opus", "xhigh", "acceptEdits"))
        self.queue("--start-queued", task["id"])
        self.assertEqual(self.calls()[0]["argv"], ["--bg", "--model", "opus", "--effort", "xhigh",
                                                   "--permission-mode", "acceptEdits", "do it later"])
        # an SSH host's: handed over to the host
        self.assertTrue(self.queue("--queue", ".claude", "--cwd", "/srv/app", "--at", at, "--prompt", "x", "--host", "lab",
                                   "--model", "sonnet", "--effort", "low", "--permission-mode", "plan")["ok"])
        (task,) = cs.load_queue(self.cache_root())
        import remote
        with mock.patch.object(remote, "host_answer", return_value={"ok": True, "message": "Started"}) as ask:
            self.queue("--start-queued", task["id"])
        ask.assert_called_once_with("lab", ["--start-task", "/srv/app", "--profile", ".claude", "--prompt", "x",
                                            "--model", "sonnet", "--effort", "low", "--permission-mode", "plan"])
        self.assertFalse(self.queue("--queue", ".claude-work", "--cwd", str(self.folder), "--at", at, "--prompt", "x",
                                    "--effort", "ultra")["ok"])

    def test_a_task_whose_account_is_at_its_limit_waits_on(self):
        at = int(time.time() * 1000)
        self.assertTrue(self.queue("--queue", ".claude-work", "--cwd", str(self.folder), "--at", str(at), "--prompt", "go")["ok"])
        (task,) = cs.load_queue(self.cache_root())
        later = at + 3600_000
        answer = self.queue("--requeue", task["id"], "--at", str(later))
        self.assertTrue(answer["ok"])
        self.assertRegex(answer["message"], r"^It waits for the usage limit: it starts (tomorrow )?at \d\d:\d\d$")
        (back,) = cs.queued_tasks(self.cache_root(), at + 1)
        self.assertEqual((back["id"], back["startAt"], back["due"]), (task["id"], later, False))
        self.assertEqual(self.queue("--requeue", "gone0000", "--at", str(later)), {"ok": True, "message": ""})
        # a weekly limit can reset days later: the day is said too
        answer = self.queue("--requeue", task["id"], "--at", str(at + 3 * 86400_000))
        self.assertRegex(answer["message"], r"^It waits for the usage limit: it starts on \w{3} \d\d \w{3} at \d\d:\d\d$")

    def test_a_task_at_a_time_you_pick(self):
        at = int((time.time() + 3 * 86400) * 1000)  # (48 hours after midnight can be tomorrow, when the clocks go back)
        answer = self.queue("--queue", ".claude-work", "--cwd", str(self.folder), "--at", str(at), "--prompt", "nightly check",
                            "--scheduled")
        self.assertTrue(answer["ok"], answer)
        self.assertRegex(answer["message"], r"^Queued: it starts on \w{3} \d\d \w{3} at \d\d:\d\d$")
        (task,) = cs.queued_tasks(self.cache_root(), int(time.time() * 1000))
        self.assertEqual((task["scheduled"], task["chat"], task["due"]), (True, None, False))
        self.assertTrue(cs.queued_tasks(self.cache_root(), at)[0]["due"])  # it starts like the others then
        now = time.mktime(time.localtime()[:3] + (12, 0, 0, 0, 0, -1))  # (noon: an hour later is today)
        self.assertEqual(jump.start_time(int((now + 3600) * 1000), now), "at 13:00")
        self.assertTrue(jump.start_time(int((now + 86400) * 1000), now).startswith("tomorrow at "))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.queue("--new-chat", ".claude-work", "--cwd", str(self.folder), "--prompt", "x", "--scheduled")

    def test_only_trusted_folders_and_a_task(self):
        at = str(int(time.time() * 1000))
        self.assertIn("doesn't trust", self.queue("--queue", ".claude-work", "--cwd", str(self.home), "--at", at, "--prompt", "x")["message"])
        self.assertEqual(self.queue("--queue", ".claude-work", "--cwd", str(self.folder), "--at", at),
                         {"ok": False, "message": "Write what Claude should do first"})
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.queue("--queue", ".claude-work", "--cwd", str(self.folder), "--prompt", "x")  # no time
        # an SSH host's task: checked there when it starts
        self.assertTrue(self.queue("--queue", ".claude", "--cwd", "/srv/app", "--at", at, "--prompt", "x", "--host", "lab")["ok"])
        self.assertEqual(cs.load_queue(self.cache_root())[0]["host"], "lab")


FAKE_CLIPBOARD = """#!{python}
import sys
offered, picture = {offered!r}, {picture!r}
args = sys.argv[1:]
if args in (["--list-types"], ["-selection", "clipboard", "-o", "-t", "TARGETS"]):
    print("\\n".join(offered))
elif args[-1] in offered and args[-1].startswith("image/"):
    sys.stdout.buffer.write(picture)
else:
    sys.exit(1)
"""


class PictureTests(TaskFixture):
    """A picture pasted into a new chat's task (jump.py --paste-image)."""

    PNG = b"\x89PNG\r\n\x1a\n a picture"

    def clipboard(self, tool, offered, picture=PNG, wayland=True):
        """The clipboard holds what offered names, read with tool (wl-paste or xclip)."""
        tools = Path(tempfile.mkdtemp(dir=self.home))
        if tool:
            write(tools / tool, FAKE_CLIPBOARD.format(python=sys.executable, offered=offered, picture=picture))
            (tools / tool).chmod(0o755)
        env = mock.patch.dict(os.environ, {"PATH": str(tools), "WAYLAND_DISPLAY": "wayland-0"})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("XDG_CACHE_HOME", None)
        if not wayland:
            del os.environ["WAYLAND_DISPLAY"]

    def paste(self):
        out = io.StringIO()
        with mock.patch.object(jump.Path, "home", return_value=self.home), contextlib.redirect_stdout(out):
            jump.main(["--paste-image"])
        return json.loads(out.getvalue())

    def test_the_clipboards_picture_is_saved_for_the_task(self):
        self.clipboard("wl-paste", ["text/html", "image/bmp", "image/png"])
        first, second = self.paste(), self.paste()
        self.assertTrue(first["ok"], first)
        folder = cs.images_dir(self.home)
        self.assertEqual(Path(first["path"]).parent, folder)
        self.assertRegex(Path(first["path"]).name, r"^\d{8}-\d{6}\.png$")
        self.assertEqual(Path(first["path"]).read_bytes(), self.PNG)
        # yours alone; a second one in the same second doesn't take its place
        self.assertEqual((stat.S_IMODE(folder.stat().st_mode), stat.S_IMODE(Path(first["path"]).stat().st_mode)),
                         (0o700, 0o600))
        self.assertNotEqual(second["path"], first["path"])
        self.assertEqual(Path(second["path"]).read_bytes(), self.PNG)

    def test_old_pictures_go(self):
        self.clipboard("wl-paste", ["image/jpeg"])
        old = cs.images_dir(self.home) / "20260101-120000.png"
        write(old, "old")
        then = time.time() - (cs.IMAGES_KEEP_DAYS + 1) * 86400
        os.utime(old, (then, then))
        answer = self.paste()
        self.assertTrue(answer["path"].endswith(".jpg"), answer)
        self.assertEqual(list(cs.images_dir(self.home).iterdir()), [Path(answer["path"])])

    def test_on_x11_with_xclip(self):
        self.clipboard("xclip", ["TARGETS", "image/png"], wayland=False)
        self.assertEqual(Path(self.paste()["path"]).read_bytes(), self.PNG)

    def test_no_picture_or_no_tool_says_so(self):
        self.clipboard("wl-paste", ["text/plain", "image/bmp"])
        self.assertEqual(self.paste(), {"ok": False, "message": "There's no picture on the clipboard"})
        self.clipboard("wl-paste", ["image/png"], picture=b"")
        self.assertEqual(self.paste(), {"ok": False, "message": "Couldn't read the picture on the clipboard"})
        self.clipboard(None, [])
        self.assertEqual(self.paste()["message"], "To paste pictures, install wl-clipboard (it has wl-paste)")
        self.clipboard(None, [], wayland=False)
        self.assertEqual(self.paste()["message"], "To paste pictures, install xclip")
        self.assertFalse(cs.images_dir(self.home).exists())

    def run_jump(self, args):
        out = io.StringIO()
        with mock.patch.object(jump.Path, "home", return_value=self.home), contextlib.redirect_stdout(out):
            jump.main(args)
        return json.loads(out.getvalue())

    def test_a_region_screenshot_is_saved_as_a_picture(self):
        # A stand-in Spectacle: writes its --output (cancelled: writes nothing)
        tools = Path(tempfile.mkdtemp(dir=self.home))
        write(tools / "spectacle", "#!/bin/sh\n[ -n \"$CANCEL\" ] && exit 0\n"
              "while [ $# -gt 1 ]; do [ \"$1\" = --output ] && printf 'PNGDATA' > \"$2\"; shift; done\n")
        (tools / "spectacle").chmod(0o755)
        with mock.patch.dict(os.environ, {"PATH": f"{tools}:/usr/bin:/bin"}):
            os.environ.pop("XDG_CACHE_HOME", None)
            shot = self.run_jump(["--screenshot"])
            self.assertTrue(shot["ok"], shot)
            self.assertEqual(Path(shot["path"]).parent, cs.images_dir(self.home))
            self.assertEqual(Path(shot["path"]).read_bytes(), b"PNGDATA")
            with mock.patch.dict(os.environ, {"CANCEL": "1"}):
                self.assertEqual(self.run_jump(["--screenshot"]), {"ok": False, "message": "No screenshot taken"})
            self.assertEqual([p.name for p in cs.images_dir(self.home).iterdir()], [Path(shot["path"]).name])
        with mock.patch.dict(os.environ, {"PATH": str(tools / "none")}):
            self.assertIn("install Spectacle", self.run_jump(["--screenshot"])["message"])

    def test_a_dropped_picture_is_copied_in_and_a_file_is_named(self):
        os.environ.pop("XDG_CACHE_HOME", None)
        picture, notes = self.home / "Pictures/cat.JPG", self.home / "notes.txt"
        write(picture, "jpeg data")
        write(notes, "notes")
        dropped = self.run_jump(["--attach", str(picture)])
        self.assertTrue(dropped["picture"], dropped)
        self.assertTrue(dropped["path"].endswith(".jpg"))
        self.assertEqual(Path(dropped["path"]).parent, cs.images_dir(self.home))
        self.assertEqual(Path(dropped["path"]).read_text(), "jpeg data")
        self.assertEqual(self.run_jump(["--attach", str(notes)]), {"ok": True, "message": "", "path": str(notes.resolve()), "picture": False})
        self.assertFalse(self.run_jump(["--attach", str(self.home / "gone.png")])["ok"])

    def test_a_card_is_copied_to_the_clipboard_as_a_picture(self):
        tools = Path(tempfile.mkdtemp(dir=self.home))
        got = self.home / "clip.bin"
        write(tools / "wl-copy", f"#!/bin/sh\necho \"$*\" > {got}.args\ncat > {got}\n")
        (tools / "wl-copy").chmod(0o755)
        card = self.home / "card.png"
        card.write_bytes(b"\x89PNG card")
        with mock.patch.dict(os.environ, {"PATH": f"{tools}:/usr/bin:/bin", "WAYLAND_DISPLAY": "wayland-0"}):
            self.assertEqual(self.run_jump(["--copy-image", str(card)]), {"ok": True, "message": "Copied: paste it anywhere"})
            deadline = time.time() + 5
            while time.time() < deadline and not (got.exists() and got.read_bytes()):
                time.sleep(0.05)
        self.assertEqual(got.read_bytes(), b"\x89PNG card")
        self.assertEqual(Path(str(got) + ".args").read_text().strip(), "--type image/png")

    def save(self, kind, data):
        out = io.StringIO()
        with mock.patch.object(jump.Path, "home", return_value=self.home), contextlib.redirect_stdout(out), \
                mock.patch.object(sys, "stdin", io.StringIO(data)):
            jump.main(["--save-image", kind])
        return json.loads(out.getvalue())

    def test_a_picture_handed_over_is_saved_like_a_pasted_one(self):
        # (the VS Code extension's: pasted in its page, as base64)
        os.environ.pop("XDG_CACHE_HOME", None)
        answer = self.save("image/png", base64.b64encode(self.PNG).decode() + "\n")
        self.assertTrue(answer["ok"], answer)
        path = Path(answer["path"])
        self.assertEqual((path.parent, path.read_bytes(), stat.S_IMODE(path.stat().st_mode)),
                         (cs.images_dir(self.home), self.PNG, 0o600))
        self.assertRegex(path.name, r"^\d{8}-\d{6}\.png$")
        self.assertEqual(self.save("image/bmp", "AAAA")["message"], "Claude takes PNG, JPEG, WebP and GIF pictures")
        self.assertEqual(self.save("image/png", "not base64!")["message"], "That isn't a picture")
        self.assertEqual(self.save("image/png", "")["message"], "That isn't a picture")
        self.assertEqual(len(list(cs.images_dir(self.home).iterdir())), 1)

    def test_a_chat_whose_task_names_a_picture_can_open_it(self):
        # it's outside the chat's folder: Claude would ask first (claude --add-dir)
        self.clipboard("wl-paste", ["image/png"])
        picture = self.paste()["path"]
        task = f"What's wrong here? [Image: {picture}] Fix it."
        opened = []
        out = io.StringIO()
        with mock.patch.object(jump, "open_terminal", lambda cwd, command: opened.append(command) or True), \
                mock.patch.object(jump, "scope_prefix", lambda name: []), \
                mock.patch.object(jump, "claude_in_terminal", return_value="claude"), \
                mock.patch.object(jump, "claude_path", return_value=str(self.bin / "claude")), \
                mock.patch.object(jump.Path, "home", return_value=self.home), contextlib.redirect_stdout(out):
            jump.main(["--new-chat", ".claude-work", "--cwd", str(self.folder), "--prompt", task, "--model", "opus"])
            jump.main(["--new-chat", ".claude-work", "--cwd", str(self.folder), "--prompt", task, "--bg"])
            jump.main(["--new-chat", ".claude-work", "--cwd", str(self.folder), "--prompt", "no picture", "--bg"])
            at = str(int(time.time() * 1000))
            jump.main(["--queue", ".claude-work", "--cwd", str(self.folder), "--at", at, "--prompt", task, "--scheduled"])
            (queued,) = cs.load_queue(cs.cache_dir(self.home))
            jump.main(["--start-queued", queued["id"]])
        self.assertTrue(all(json.loads(l)["ok"] for l in out.getvalue().splitlines()), out.getvalue())
        add_dir = f"--add-dir={cs.images_dir(self.home)}"
        terminal, = opened
        self.assertEqual(shlex.split(terminal)[-4:], ["--model", "opus", add_dir, task])
        background, plain, later = (c["argv"] for c in self.calls())
        self.assertEqual((background, plain, later), (["--bg", add_dir, task], ["--bg", "no picture"], ["--bg", add_dir, task]))


class ContinueAfterResetTests(TaskFixture):
    """A chat a usage limit stopped, queued to go on once the limit resets."""

    SID = "e3de1242-7bc8-40a5-938f-aadb5f5aa9ee"
    queue, cache_root = QueueTests.queue, QueueTests.cache_root

    def stopped_chat(self, *more):
        t = self.now - 120
        write(self.home / f".claude-work/projects/-repos-app/{self.SID}.jsonl",
              lines(prompt("fix it", t, cwd=str(self.folder)),
                    limit_error("You've hit your session limit · resets 10:40am (Europe/Berlin)", t + 1), *more))

    def test_queue_then_go_on_in_the_background(self):
        self.stopped_chat()
        at = int((time.time() + 3600) * 1000)
        answer = self.queue("--queue-continue", self.SID, "--profile", ".claude-work", "--at", str(at),
                            "--name", "Fix it", "--account", "work · Team")
        self.assertTrue(answer["ok"], answer)
        self.assertRegex(answer["message"], r"^Queued: it goes on (tomorrow )?at \d\d:\d\d, when the limit resets$")
        self.assertEqual(cs.kept_chats(self.cache_root()), [], "once: it doesn't keep going")
        answer = self.queue("--queue-continue", self.SID, "--profile", ".claude-work", "--at", str(at),
                            "--name", "Fix it", "--account", "work · Team", "--keep")  # (twice: queued once)
        self.assertRegex(answer["message"], r"^Queued: it goes on (tomorrow )?at \d\d:\d\d, when the limit resets, "
                                            r"and after later limits too until it's done$")
        (task,) = cs.queued_tasks(self.cache_root(), int(time.time() * 1000))
        self.assertEqual((task["chat"], task["name"], task["folder"], task["prompt"], task["account"]),
                         (self.SID, "Fix it", str(self.folder), "", "work · Team"))
        # with --keep, it keeps going from then on (once, however often it was queued)
        (kept,) = cs.kept_chats(self.cache_root())
        self.assertEqual((kept["chat"], kept["profile"], kept["name"], kept["wentOnAt"]), (self.SID, ".claude-work", "Fix it", None))
        self.assertEqual(self.queue("--start-queued", task["id"]),
                         {"ok": True, "message": "Went on in the background on work (1a2b3c4d)"})
        call, = self.calls()
        self.assertEqual(call["argv"], ["--bg", "--resume", self.SID, cs.CONTINUE_PROMPT])
        self.assertEqual(call["cwd"], str(self.folder))
        self.assertEqual(cs.load_queue(self.cache_root()), [])
        self.assertIsNotNone(cs.kept_chats(self.cache_root())[0]["wentOnAt"])  # (when it went on: noted before it did)

    def test_it_goes_on_in_its_own_permission_mode(self):
        t = self.now - 120
        write(self.home / f".claude-work/projects/-repos-app/{self.SID}.jsonl",
              lines(prompt("fix it", t, cwd=str(self.folder), permissionMode="default"),
                    {"type": "permission-mode", "permissionMode": "auto", "sessionId": self.SID},
                    limit_error("You've hit your session limit", t + 1)))
        go_on = lambda: cs.continue_chat(self.home, [], ".claude-work", self.SID, None, "", str(self.bin / "claude"))
        self.assertTrue(go_on()["ok"])
        self.assertEqual(self.calls()[-1]["argv"], ["--bg", "--resume", self.SID, "--permission-mode", "auto",
                                                    cs.CONTINUE_PROMPT])
        # its background session saved that: woken, it keeps it (options would start a copy)
        write(self.home / f".claude-work/jobs/{self.SID[:8]}/state.json",
              {"sessionId": self.SID, "respawnFlags": ["--permission-mode", "auto"]})
        self.assertTrue(go_on()["ok"])
        self.assertEqual(self.calls()[-1]["argv"], ["--bg", "--resume", self.SID, cs.CONTINUE_PROMPT])

    def test_it_goes_on_with_its_own_model_and_effort(self):
        # as its status line last named them: its background session saves
        # them, and every later wake goes on with them
        self.stopped_chat()
        write(cs.cache_dir(self.home) / "statusline/.claude-work" / f"{self.SID}.json",
              {"session_id": self.SID, "model": {"id": "claude-opus-5-5", "display_name": "Opus 5.5"},
               "effort": {"level": "xhigh"}})
        self.assertTrue(cs.continue_chat(self.home, [], ".claude-work", self.SID, None, "", str(self.bin / "claude"))["ok"])
        self.assertEqual(self.calls()[-1]["argv"], ["--bg", "--resume", self.SID, "--model", "claude-opus-5-5",
                                                    "--effort", "xhigh", cs.CONTINUE_PROMPT])
        self.assertEqual(cs.chat_model(self.home, self.profile, "e3de1242-0000-4000-8000-000000000000"), (None, None))

    def test_a_background_chat_of_it_wakes_with_its_own_options_and_what_they_lack(self):
        # (the options its job saved are Claude's own, rewritten on /model, /effort and a mode
        # change in it: they win; its transcript and status line only add what they lack)
        self.stopped_chat(dict(reply("On it.", self.now - 100), message=dict(reply("On it.", self.now - 100)["message"],
                                                                                 model="claude-opus-5-5")))
        write(cs.cache_dir(self.home) / "statusline/.claude-work" / f"{self.SID}.json",
              {"session_id": self.SID, "model": {"id": "claude-haiku-5-5"}, "effort": {"level": "xhigh"}})
        state = self.home / f".claude-work/jobs/{self.SID[:8]}/state.json"
        write(state, {"sessionId": self.SID, "name": "Fix it", "respawnFlags": ["--permission-mode", "auto", "--effort", "low"]})
        answer = cs.continue_chat(self.home, [], ".claude-work", self.SID, None, "", str(self.bin / "claude"), force=True)
        self.assertEqual(answer["message"], "Went on in the background on work (Opus 5.5 · low)")
        self.assertEqual(self.calls()[-1]["argv"], ["--bg", "--resume", self.SID, cs.CONTINUE_PROMPT])  # (no copy)
        self.assertEqual(json.loads(state.read_text()), {"sessionId": self.SID, "name": "Fix it", "respawnFlags": [
            "--permission-mode", "auto", "--effort", "low", "--model", "claude-opus-5-5"]})
        # a record of another shape is left as it is, and the answer says so
        write(state, {"sessionId": self.SID, "respawnFlags": "--model opus"})
        answer = cs.continue_chat(self.home, [], ".claude-work", self.SID, None, "", str(self.bin / "claude"), force=True)
        self.assertEqual(answer["message"], "Went on in the background on work (1a2b3c4d), "
                                            "with the model and effort Claude saved for it")
        self.assertEqual(json.loads(state.read_text())["respawnFlags"], "--model opus")

    def mode_and_effort_not_the_accounts(self):
        """A chat in auto mode on xhigh effort, on an account whose settings
        say model "opus" and the default mode, stopped by the limit."""
        write(self.home / ".claude-work/settings.json", {"model": "opus", "permissions": {"defaultMode": "default"}})
        t = self.now - 120
        write(self.home / f".claude-work/projects/-repos-app/{self.SID}.jsonl",
              lines(prompt("fix it", t, cwd=str(self.folder), permissionMode="default"),
                    {"type": "permission-mode", "permissionMode": "auto", "sessionId": self.SID},
                    dict(reply("On it.", t + 1), message=dict(reply("On it.", t + 1)["message"], model="claude-opus-5-5")),
                    limit_error("You've hit your session limit", t + 2)))
        write(cs.cache_dir(self.home) / "statusline/.claude-work" / f"{self.SID}.json",
              {"session_id": self.SID, "model": {"id": "claude-opus-5-5"}, "effort": {"level": "xhigh"}})
        return self.home / f".claude-work/jobs/{self.SID[:8]}/state.json"

    def test_a_copy_that_saved_only_its_model_wakes_in_the_chats_mode_and_effort(self):
        # (a copy Claude made of a background chat runs in the chat's mode but saves only the
        # model the account's settings name: woken with that, it would come back in the default
        # mode and effort; so the go-on adds them to what it saved, then wakes it)
        state = self.mode_and_effort_not_the_accounts()
        write(state, {"sessionId": self.SID, "template": "bg", "respawnFlags": ["--model", "opus"]})
        answer = cs.continue_chat(self.home, [], ".claude-work", self.SID, None, "", str(self.bin / "claude"))
        self.assertEqual(answer["message"], "Went on in the background on work (Opus · xhigh)")
        self.assertEqual(self.calls()[-1]["argv"], ["--bg", "--resume", self.SID, cs.CONTINUE_PROMPT])  # (woken, no copy)
        self.assertEqual(json.loads(state.read_text())["respawnFlags"],
                         ["--model", "opus", "--permission-mode", "auto", "--effort", "xhigh"])

    def test_a_job_its_service_still_holds_goes_on_as_a_copy_with_the_jobs_own_options(self):
        # (one Claude's background service still holds after the wait is copied by claude --bg
        # --resume, which saves only the options given: so they're the job's own, never none)
        state = self.mode_and_effort_not_the_accounts()
        write(state, {"sessionId": self.SID, "template": "bg",
                      "respawnFlags": ["--permission-mode", "auto", "--model", "claude-opus-5-5", "--effort", "xhigh"]})
        entry = {"sessionId": self.SID, "kind": "bg", "jobId": self.SID[:8], "status": "idle"}
        stops = []
        with mock.patch.object(cs, "stop_background", side_effect=lambda *a, **k: stops.append(a[1]) or (True, "stopped")), \
                mock.patch.object(cs, "live_entries_all", side_effect=lambda *_: [] if stops else [(entry, self.profile, self.profile)]), \
                mock.patch.object(cs, "daemon_holds", return_value=True):  # (still held after the wait)
            answer = cs.continue_chat(self.home, [], ".claude-work", self.SID, None, "", str(self.bin / "claude"), wait=0.3)
        self.assertTrue(answer["ok"], answer)
        self.assertEqual(stops, [self.SID[:8]])
        self.assertEqual(self.calls()[-1]["argv"], ["--bg", "--resume", self.SID, "--permission-mode", "auto",
                                                    "--model", "claude-opus-5-5", "--effort", "xhigh", cs.CONTINUE_PROMPT])
        self.assertEqual(answer["message"], "Went on in the background on work (Opus 5.5 · xhigh)")
        # once it let go, the same job is woken with them (no options, which would start a copy)
        stops.clear()
        with mock.patch.object(cs, "stop_background", side_effect=lambda *a, **k: stops.append(a[1]) or (True, "stopped")), \
                mock.patch.object(cs, "live_entries_all", side_effect=lambda *_: [] if stops else [(entry, self.profile, self.profile)]), \
                mock.patch.object(cs, "daemon_holds", return_value=False):
            self.assertTrue(cs.continue_chat(self.home, [], ".claude-work", self.SID, None, "", str(self.bin / "claude"))["ok"])
        self.assertEqual(self.calls()[-1]["argv"], ["--bg", "--resume", self.SID, cs.CONTINUE_PROMPT])

    def test_another_chats_job_under_its_short_id_means_a_copy_with_its_options(self):
        # (Claude starts a copy then, whatever is given: it saves these)
        self.mode_and_effort_not_the_accounts()
        write(self.home / f".claude-work/jobs/{self.SID[:8]}/state.json",
              {"sessionId": self.SID[:8] + "-0000-4000-8000-000000000000", "respawnFlags": ["--model", "sonnet"]})
        self.assertTrue(cs.continue_chat(self.home, [], ".claude-work", self.SID, None, "", str(self.bin / "claude"))["ok"])
        self.assertEqual(self.calls()[-1]["argv"], ["--bg", "--resume", self.SID, "--permission-mode", "auto",
                                                    "--model", "claude-opus-5-5", "--effort", "xhigh", cs.CONTINUE_PROMPT])

    def test_the_answer_says_when_claude_started_a_copy_after_all(self):
        state = self.mode_and_effort_not_the_accounts()
        write(state, {"sessionId": self.SID, "respawnFlags": ["--permission-mode", "auto", "--model", "claude-opus-5-5",
                                                              "--effort", "xhigh"]})
        write(self.bin / "claude", FAKE_CLAUDE.format(python=sys.executable, log=str(self.log)) + (
            "sys.stderr.write('note: session e3de1242 is already running in the background, so this started a copy '\n"
            "                 'as 1a2b3c4d. `claude attach e3de1242` opens the original.\\n')\n"))
        answer = cs.continue_chat(self.home, [], ".claude-work", self.SID, None, "", str(self.bin / "claude"))
        self.assertEqual(answer["message"], "Went on in the background on work (Opus 5.5 · xhigh), as a copy (1a2b3c4d)")


    def test_a_panel_chat_goes_on_in_the_mode_its_first_prompt_named(self):
        # (Claude Code's panel names it at the first prompt only; big tool results after it)
        t = self.now - 120
        big = {"type": "user", "timestamp": iso(t + 3),
               "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t", "content": "x" * 100_000}]}}
        write(self.home / f".claude-work/projects/-repos-app/{self.SID}.jsonl",
              lines(prompt("fix it", t, cwd=str(self.folder), permissionMode="acceptEdits"), *[big] * 4,
                    reply("Fixed.", t + 4), prompt("and the tests", t + 5, cwd=str(self.folder)),
                    limit_error("You've hit your session limit", t + 6)))
        self.assertIsNone(cs.chat_peek(self.home / f".claude-work/projects/-repos-app/{self.SID}.jsonl")["mode"])
        self.assertTrue(cs.continue_chat(self.home, [], ".claude-work", self.SID, None, "", str(self.bin / "claude"))["ok"])
        self.assertEqual(self.calls()[-1]["argv"], ["--bg", "--resume", self.SID, "--permission-mode", "acceptEdits",
                                                    cs.CONTINUE_PROMPT])

    def test_a_message_naming_a_picture_can_open_it(self):
        # (a reply from the chat pane with a pasted picture, going on in the background)
        self.stopped_chat()
        picture = cs.images_dir(self.home) / "20261026-101500.png"
        text = f"And this? [Image: {picture}]"
        go_on = lambda: cs.continue_chat(self.home, [], ".claude-work", self.SID, None, text, str(self.bin / "claude"), force=True)
        self.assertTrue(go_on()["ok"])
        self.assertEqual(self.calls()[-1]["argv"], ["--bg", "--resume", self.SID, f"--add-dir={picture.parent}", text])
        # a background session of it wakes with the options it saved (any here would start a copy)
        write(self.home / f".claude-work/jobs/{self.SID[:8]}/state.json", {"sessionId": self.SID})
        self.assertTrue(go_on()["ok"])
        self.assertEqual(self.calls()[-1]["argv"], ["--bg", "--resume", self.SID, text])

    def test_never_bypassing_permissions_by_itself(self):
        t = self.now - 120
        write(self.home / f".claude-work/projects/-repos-app/{self.SID}.jsonl",
              lines(prompt("fix it", t, cwd=str(self.folder), permissionMode="bypassPermissions"),
                    limit_error("You've hit your session limit", t + 1)))
        self.assertTrue(cs.continue_chat(self.home, [], ".claude-work", self.SID, None, "", str(self.bin / "claude"))["ok"])
        self.assertEqual(self.calls()[-1]["argv"], ["--bg", "--resume", self.SID, cs.CONTINUE_PROMPT])

    def test_a_chat_that_went_on_already_is_left_alone(self):
        self.stopped_chat(reply("Done.", self.now - 10))
        at = int(time.time() * 1000)
        self.assertTrue(self.queue("--queue-continue", self.SID, "--profile", ".claude-work", "--at", str(at),
                                   "--prompt", "go on with step 2")["ok"])
        (task,) = cs.load_queue(self.cache_root())
        self.assertEqual(self.queue("--start-queued", task["id"]), {"ok": True, "message": ""})
        self.assertEqual((self.calls(), cs.load_queue(self.cache_root())), ([], []))

    def test_a_session_that_still_has_it_open_is_stopped_first(self):
        # (with no background service to take the go-on in: see BackgroundServiceTests)
        self.stopped_chat()
        stops = []
        entry = {"sessionId": self.SID, "kind": "bg", "jobId": "e3de1242", "status": "idle"}
        with mock.patch.object(cs, "stop_background", side_effect=lambda *a, **k: stops.append(a[1]) or (True, "stopped")), \
                mock.patch.object(cs, "live_entries_all",
                                  side_effect=lambda profiles: [] if stops else [(entry, self.profile, self.profile)]):
            answer = cs.continue_chat(self.home, [], ".claude-work", self.SID, None, "", str(self.bin / "claude"))
        self.assertTrue(answer["ok"], answer)
        self.assertEqual(stops, ["e3de1242"])
        self.assertEqual(self.calls()[0]["argv"][:3], ["--bg", "--resume", self.SID])

    def test_its_folder_must_be_trusted_and_ssh_hosts_go_through_ssh(self):
        t = self.now - 120
        write(self.home / f".claude-work/projects/-home/{self.SID}.jsonl",
              lines(prompt("hi", t, cwd=str(self.home)), limit_error("You've hit your session limit", t + 1)))
        at = str(int(time.time() * 1000))
        answer = self.queue("--queue-continue", self.SID, "--profile", ".claude-work", "--at", at)
        self.assertFalse(answer["ok"])
        self.assertIn("Claude doesn't trust your home folder", answer["message"])
        self.assertEqual(self.queue("--queue-continue", "nope", "--profile", ".claude-work", "--at", at),
                         {"ok": False, "message": "That chat isn't on this account any more"})
        # on an SSH host (or in a container): checked there, when it goes on; it can keep going too
        # (kept here, with its host: KeepGoingOnHostsTests)
        self.assertTrue(self.queue("--queue-continue", self.SID, "--profile", ".claude", "--at", at, "--cwd", "/srv/app",
                                   "--host", "lab", "--name", "Fix it", "--keep")["ok"])
        self.assertEqual([(k["chat"], k["host"], k["profile"], k["wentOnAt"]) for k in cs.load_keep(self.cache_root())["chats"]],
                         [(self.SID, "lab", ".claude", None)])
        (task,) = cs.load_queue(self.cache_root())
        import remote
        with mock.patch.object(remote, "host_answer", return_value={"ok": True, "message": "Went on in the background on work (1a2b3c4d)"}) as ask:
            self.assertEqual(self.queue("--start-queued", task["id"])["message"], "Went on in the background on work (1a2b3c4d)")
        _, args = ask.call_args[0]
        self.assertEqual(args[:6], ["--continue-chat", self.SID, "--profile", ".claude", "--folder", "/srv/app"])
        self.assertEqual(args[6:7], ["--ends-at"])  # (its background commands are waited for until then: GoOnWaitsTests)
        self.assertNotIn("--force", args)  # (only a try again goes on whatever its newest turn)
        (k,) = cs.load_keep(self.cache_root())["chats"]
        self.assertIsNotNone(k["wentOnAt"])  # (noted before it went on, as this computer's)

    def test_queue_in_a_folder_picked_in_the_dialog(self):
        at = str(int((time.time() + 3600) * 1000))
        with mock.patch.object(jump, "choose_folder", return_value=(str(self.folder), "")), \
                mock.patch.object(jump, "claude_in_terminal", return_value="claude"):
            answer = self.queue("--queue", ".claude-work", "--choose-folder", "--at", at, "--prompt", "fix it")
        self.assertTrue(answer["ok"], answer)
        self.assertEqual(cs.load_queue(self.cache_root())[0]["folder"], str(self.folder))
        with mock.patch.object(jump, "choose_folder", return_value=(None, "")), \
                mock.patch.object(jump, "claude_in_terminal", return_value="claude"):
            self.assertEqual(self.queue("--queue", ".claude-work", "--choose-folder", "--at", at, "--prompt", "x"),
                             {"ok": True, "message": ""})  # (cancelled)
        self.assertEqual(len(cs.load_queue(self.cache_root())), 1)


def api_error(text, ts):
    e = limit_error(text, ts)
    e["error"] = "server_error"
    return e


class MovedChatTests(TaskFixture):
    """Closing a chat's terminal makes Claude (2.1.316) move it to the
    background under a NEW id, its transcript a copy of the history whose
    entries keep the old id in `session_id` (snake case). At the reset, the
    go-on resumed the old id: two copies of one conversation at work
    (2026-11-01). The chat goes on under the new id: keep going, its queued
    go-on, its row, its star and its name follow it."""

    OLD = ContinueAfterResetTests.SID
    NEW = "5def6803-dbca-4a13-8ca4-4331fb6ce1f4"
    queue, cache_root = QueueTests.queue, QueueTests.cache_root

    def setUp(self):
        super().setUp()
        t = self.now - 600
        self.project = self.home / ".claude-work/projects/-repos-app"
        attach = lambda sid, ts: {"type": "attachment", "uuid": "a-" + str(ts), "timestamp": iso(ts), "sessionId": sid,
                                  "session_id": sid, "attachment": {"type": "date"}}
        stop = limit_error("You've hit your session limit · resets 10:40am (Europe/Berlin)", t + 2)
        write(self.project / f"{self.OLD}.jsonl",
              lines({"type": "ai-title", "aiTitle": "talpy-den-64", "sessionId": self.OLD},
                    prompt("fix it", t, cwd=str(self.folder), sessionId=self.OLD, uuid="u1"), attach(self.OLD, t + 1),
                    dict(stop, sessionId=self.OLD, uuid="u2")))
        # the copy: its entries' sessionId is the new id, the copied attachments keep the old one
        copy = lambda e: dict(e, sessionId=self.NEW)
        write(self.project / f"{self.NEW}.jsonl",
              lines({"type": "ai-title", "aiTitle": "shared creature code tug", "sessionId": self.NEW},
                    copy(prompt("fix it", t, cwd=str(self.folder), uuid="u1")), copy(attach(self.OLD, t + 1)),
                    copy(dict(stop, uuid="u2"))))
        os.utime(self.project / f"{self.OLD}.jsonl", (t + 2, t + 2))

    def status(self):
        return cs.collect(self.home, self.cache_root(), with_tokens=False, now=self.now)

    def rows(self, status):
        return [s for g in status["groups"] for s in g["sessions"]]

    def test_a_moved_transcript_names_the_chat_it_continues_read_once(self):
        links = cs.LinkCache(self.cache_root() / "links.json")
        new, old = self.project / f"{self.NEW}.jsonl", self.project / f"{self.OLD}.jsonl"
        self.assertEqual((links.moved_from(new), links.moved_from(old)), (self.OLD, ""))
        # its own entries after the copy: still the chat it moved from, and what's added isn't read
        with open(new, "a") as f:
            f.write(json.dumps({"type": "attachment", "sessionId": self.NEW, "session_id": self.NEW}) + "\n")
        self.assertEqual(links.moved_from(new), self.OLD)
        links.save()
        again = cs.LinkCache(self.cache_root() / "links.json")
        with open(new, "a") as f:
            f.write(json.dumps({"type": "attachment", "sessionId": self.NEW, "session_id": self.OLD}) + "\n")
        with mock.patch("builtins.open", side_effect=AssertionError("read again")):
            self.assertEqual(again.moved_from(new), self.OLD)
        # moved twice: the copy carries both ids, the last before its own is the one it moved from
        newer = "7de0b1f3-0000-4000-8000-000000000001"
        write(self.project / f"{newer}.jsonl", lines(
            {"type": "attachment", "uuid": "u2", "sessionId": newer, "session_id": self.OLD},
            {"type": "attachment", "sessionId": newer, "session_id": self.NEW},
            {"type": "attachment", "sessionId": newer, "session_id": newer}))
        self.assertEqual(links.moved_from(self.project / f"{newer}.jsonl"), self.NEW)
        # a chat whose own entries come first isn't a moved one, whatever it quotes later
        quoted = "9c6c239a-0000-4000-8000-000000000002"
        write(self.project / f"{quoted}.jsonl", lines(
            {"type": "attachment", "sessionId": quoted, "session_id": quoted},
            {"type": "attachment", "sessionId": quoted, "session_id": self.OLD}))
        self.assertEqual(links.moved_from(self.project / f"{quoted}.jsonl"), "")
        # after /clear (or /resume) in a chat, the new conversation's entries carry the id its
        # process started with too: they're new, not in that chat, so it isn't a moved one (its
        # transcript in another folder: Claude moves it there when the chat changes folder)
        cleared = "d0c1ea2e-0000-4000-8000-000000000003"
        elsewhere = self.project.with_name("-repos-app--claude-worktrees-fix")
        write(elsewhere / f"{cleared}.jsonl", lines(
            prompt("<command-name>/clear</command-name>", self.now, sessionId=cleared, uuid="c1"),
            prompt("something else", self.now, sessionId=cleared, uuid="c2"),
            {"type": "attachment", "uuid": "c3", "sessionId": cleared, "session_id": self.OLD},
            dict(reply("Sure.", self.now), uuid="c4", sessionId=cleared, session_id=self.OLD)))
        self.assertEqual(links.moved_from(elsewhere / f"{cleared}.jsonl"), "")
        # (a copy whose chat's transcript is gone can't be told from it: taken as moved)
        gone = "0ad0be11-0000-4000-8000-000000000004"
        write(self.project / f"{gone}.jsonl", lines(
            {"type": "attachment", "uuid": "g1", "sessionId": gone, "session_id": "0ff0ff00-0000-4000-8000-000000000005"},
            {"type": "attachment", "uuid": "g2", "sessionId": gone, "session_id": gone}))
        self.assertEqual(links.moved_from(self.project / f"{gone}.jsonl"), "0ff0ff00-0000-4000-8000-000000000005")
        cs_moves = {self.OLD: self.NEW, self.NEW: newer}
        self.assertEqual(cs.moved_chat(self.OLD, cs_moves), newer)
        self.assertEqual(cs.moved_chat(newer, {newer: self.OLD, self.OLD: newer}), self.OLD)  # (no loop)

    def test_the_go_on_goes_on_with_the_new_id_never_the_old(self):
        cs.keep_chat(self.cache_root(), ".claude-work", self.OLD, "talpy-den-64", str(self.folder))
        at = int(time.time() * 1000) - 1000
        self.assertTrue(self.queue("--queue-continue", self.OLD, "--profile", ".claude-work", "--at", str(at),
                                   "--name", "talpy-den-64")["ok"])
        (task,) = cs.load_queue(self.cache_root())
        answer = self.queue("--start-queued", task["id"])
        self.assertEqual(answer, {"ok": True, "message": "Went on in the background on work (1a2b3c4d)"})
        self.assertEqual(self.calls()[0]["argv"], ["--bg", "--resume", self.NEW, cs.CONTINUE_PROMPT])
        (kept,) = cs.kept_chats(self.cache_root())
        self.assertEqual(kept["chat"], self.NEW)
        self.assertIsNotNone(kept["wentOnAt"])

    def test_nothing_to_do_when_the_new_one_is_at_work(self):
        write(self.home / ".claude-work/sessions/50.json", session(self.NEW, kind="bg", status="busy", cwd=str(self.folder)))
        write(self.project / f"{self.NEW}.jsonl", (self.project / f"{self.NEW}.jsonl").read_text()
              + lines(prompt("continue", self.now - 60, sessionId=self.NEW, uuid="u3")))
        answer = cs.continue_chat(self.home, [], ".claude-work", self.OLD, None, "", str(self.bin / "claude"), force=True)
        self.assertEqual(answer, {"ok": True, "message": ""})
        self.assertEqual(self.calls(), [])

    def test_its_row_star_keep_and_queued_go_on_follow_it(self):
        cs.keep_chat(self.cache_root(), ".claude-work", self.OLD, "talpy-den-64", str(self.folder))
        cs.change_stars(self.cache_root(), "chats", self.OLD)
        at = int(time.time() * 1000) + 3600_000
        self.assertTrue(self.queue("--queue-continue", self.OLD, "--profile", ".claude-work", "--at", str(at),
                                   "--name", "talpy-den-64")["ok"])
        status = self.status()
        self.assertEqual(status["moved"], {self.OLD: self.NEW})
        # one row, the new id's: a kept chat with no process stays listed, with what stopped it
        (row,) = [s for s in self.rows(status) if self.OLD in (s["sessionId"], s["chatId"]) or s["chatId"] == self.NEW]
        self.assertEqual((row["chatId"], row["kind"], row["pid"], row["name"]), (self.NEW, "chat", None, "shared creature code tug"))
        self.assertEqual(row["stopped"]["kind"], "limit")
        self.assertTrue(row["starred"])
        self.assertNotIn(self.OLD, [r["sessionId"] for g in status["groups"] for r in g["recent"]])
        self.assertEqual(cs.starred_of(cs.load_stars(self.cache_root()))["chats"], {self.NEW})
        # the keep engine moves keep.json and the queue over, named as it's called now
        cs.look_after_kept(self.home, self.cache_root(), [], status["groups"], int(self.now * 1000), 0, status["moved"])
        (kept,) = cs.kept_chats(self.cache_root())
        self.assertEqual((kept["chat"], kept["name"]), (self.NEW, "shared creature code tug"))
        (task,) = cs.load_queue(self.cache_root())
        self.assertEqual((task["chat"], task["name"]), (self.NEW, "shared creature code tug"))

    def test_its_row_says_it_moved_and_a_hide_follows_it(self):
        # (its background job's start is when it moved)
        write(self.home / f".claude-work/jobs/{self.NEW[:8]}/state.json",
              {"sessionId": self.NEW, "createdAt": "2026-11-01T15:01:12.738Z", "template": "bg"})
        cs.keep_chat(self.cache_root(), ".claude-work", self.OLD, "talpy-den-64", str(self.folder))
        (row,) = [s for s in self.rows(self.status()) if s["chatId"] == self.NEW]
        self.assertEqual(row["movedFrom"], {"id": self.OLD, "at": cs.to_ms("2026-11-01T15:01:12.738Z")})
        # the same on an SSH host or in a container (its status: talpy_den.py --remote there)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.object(cs.Path, "home", return_value=self.home), \
                mock.patch.object(cs, "cache_dir", return_value=self.cache_root()):
            cs.main(["--remote"])
        there = json.loads(out.getvalue().split(cs.REMOTE_MARK)[1])
        self.assertEqual([s["movedFrom"]["id"] for g in there["groups"] for s in g["sessions"] if s.get("movedFrom")], [self.OLD])
        # a chat you hid stays hidden under its new id (and the old one is forgotten)
        hid = int(self.now * 1000) - 60_000
        cs.change_dismissed(self.cache_root(), add=self.OLD, now_ms=hid)
        status = self.status()
        self.assertEqual(cs.load_dismissed(self.cache_root()), {self.NEW: hid})
        self.assertEqual([s for s in self.rows(status) if self.NEW in (s["sessionId"], s["chatId"])], [])
        self.assertEqual(status["dismissed"], 1)

    def test_search_finds_it_once_under_its_new_id(self):
        found = cs.find_chats(self.home, self.cache_root(), [], "app")
        self.assertEqual([c["sessionId"] for c in found["results"]], [self.NEW])

    def test_deleting_it_takes_what_it_was_before_along(self):
        # (2026-11-03) the old id's transcript came back as a recent chat of the same name
        with mock.patch.dict(os.environ, {"XDG_DATA_HOME": str(Path(self.tmp.name) / "data")}):
            asked = jump.delete_item(self.home, [], "chat", self.NEW, ".claude-work", describe=True)[2]
            self.assertIn("checkpoints, and its older copy from before Claude moved it to the background;", asked["question"])
            self.assertEqual(jump.delete_item(self.home, [], "chat", self.NEW, ".claude-work")[1], "Moved to the Trash")
        self.assertEqual(list(self.project.glob("*.jsonl")), [])


class KeptChatListedTests(TaskFixture):
    """A kept chat whose terminal was closed vanished from its account's
    list, its Keeps going and Goes on at with it, while its go-on waited
    in the queue (2026-11-01): it stays listed until it's let go."""

    SID = ContinueAfterResetTests.SID
    cache_root = QueueTests.cache_root
    stopped_chat = ContinueAfterResetTests.stopped_chat

    def test_listed_while_kept_with_its_limit(self):
        self.stopped_chat()
        status = lambda: cs.collect(self.home, self.cache_root(), with_tokens=False, now=self.now)
        listed = lambda st: [s for g in st["groups"] for s in g["sessions"] if s["chatId"] == self.SID]
        self.assertEqual(listed(status()), [], "not kept: a closed chat is a recent one")
        cs.keep_chat(self.cache_root(), ".claude-work", self.SID, "Fix it", str(self.folder))
        (row,) = listed(status())
        self.assertEqual((row["key"], row["kind"], row["pid"], row["state"], row["cwd"]),
                         (f".claude-work/{self.SID}/chat", "chat", None, "done", str(self.folder)))
        self.assertEqual(row["stopped"]["kind"], "limit")
        self.assertEqual(row["reply"], "background")
        # its live row when it runs again: listed once
        write(self.home / ".claude-work/sessions/50.json", session(self.SID, cwd=str(self.folder)))
        (row,) = listed(status())
        self.assertIsNotNone(row["pid"])
        # Keep going off: a recent chat again
        (self.home / ".claude-work/sessions/50.json").unlink()
        cs.keep_chat(self.cache_root(), ".claude-work", self.SID, on=False)
        self.assertEqual(listed(status()), [])


class GoOnWaitsTests(TaskFixture):
    """A chat a usage limit stopped that still runs commands in the
    background (a server it started) looks at work: its go-on waits for
    them, and ends them GO_ON_WAIT_MS after its time; said and logged only
    then."""

    SID = ContinueAfterResetTests.SID
    queue, cache_root = QueueTests.queue, QueueTests.cache_root
    stopped_chat = ContinueAfterResetTests.stopped_chat

    def setUp(self):
        super().setUp()
        self.stopped_chat()
        self.session_file = self.home / ".claude-work/sessions/50.json"
        write(self.session_file, session(self.SID, kind="bg", status="busy", jobId=self.SID[:8]))
        write(self.home / f".claude-work/jobs/{self.SID[:8]}/state.json", {
            "sessionId": self.SID, "state": "working", "fan": [
                {"id": "b1", "kind": "shell", "label": "python3 -m http.server 8000", "startedAt": 1},
                {"id": "b0", "kind": "shell", "label": "ls", "startedAt": 1, "doneAt": 2},
                {"id": "a1", "kind": "agent", "label": "Look around", "startedAt": 1}]})
        self.at = int(time.time() * 1000) - 1000
        cs.keep_chat(self.cache_root(), ".claude-work", self.SID, "Fix it", str(self.folder))
        self.assertTrue(self.queue("--queue-continue", self.SID, "--profile", ".claude-work", "--at", str(self.at),
                                   "--name", "Fix it")["ok"])

    def log_lines(self):
        path = self.cache_root() / "go-on.log"
        return path.read_text().splitlines() if path.exists() else []

    def test_it_waits_for_its_background_commands_then_ends_them(self):
        (task,) = cs.load_queue(self.cache_root())
        answer = self.queue("--start-queued", task["id"])
        self.assertRegex(answer["waits"], r"^Waits for its background command “python3 -m http.server 8000” to finish "
                                          r"before it goes on; (tomorrow )?at \d\d:\d\d it ends it$")
        self.assertEqual((answer["ok"], answer["notify"]), (True, True))
        self.assertEqual(answer["message"], "“Fix it” w" + answer["waits"][1:])
        self.assertEqual(self.calls(), [], "it didn't go on")
        # back in the queue, tried again in a minute, with no error: from its own time, the deadline
        (back,) = cs.queued_tasks(self.cache_root(), int(time.time() * 1000))
        self.assertEqual((back["id"], back["error"], back["waits"], back["dueAt"], back["due"]),
                         (task["id"], "", answer["waits"], self.at, False))
        self.assertAlmostEqual(back["startAt"], time.time() * 1000 + 60_000, delta=5000)
        # not a go-on that didn't take: the keep engine waits with it, and doesn't queue it twice
        self.assertIsNone(cs.kept_chats(self.cache_root())[0]["wentOnAt"])
        later = int(time.time() * 1000) + cs.KEEP_TAKE_MS + 60_000
        cs.look_after_kept(self.home, self.cache_root(), [], [{"profileKeys": [".claude-work"], "sessions": []}], later)
        self.assertEqual([t["id"] for t in cs.load_queue(self.cache_root())], [task["id"]])
        # said and logged once
        (line,) = self.log_lines()
        self.assertRegex(line, r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d  “Fix it” waits for its background command “python3 -m "
                               r"http.server 8000” to finish before it goes on; (tomorrow )?at \d\d:\d\d it ends it$")
        again = self.queue("--start-queued", task["id"])
        self.assertEqual((again["ok"], again["notify"], again["waits"]), (True, False, answer["waits"]))
        self.assertEqual(len(self.log_lines()), 1)
        # its time + GO_ON_WAIT_MS: it ends them and goes on, and says what it ended
        (back,) = cs.load_queue(self.cache_root())
        cs.change_queue(self.cache_root(), put_back=dict(back, dueAt=self.at - cs.GO_ON_WAIT_MS))
        ended = []

        def end(home, entry, profile, claude=None):
            ended.append((entry["jobId"], profile.key))
            self.session_file.unlink()  # (its session quit)
            return True, "Stopped"
        with mock.patch.object(cs, "end_background_work", side_effect=end):
            answer = self.queue("--start-queued", task["id"])
        self.assertEqual(ended, [(self.SID[:8], ".claude-work")])
        self.assertEqual(answer, {"ok": True, "message": "“Fix it” ended its background command “python3 -m http.server 8000” "
                                                         "and went on in the background on work (1a2b3c4d)",
                                  "ended": ["python3 -m http.server 8000"], "notify": True})
        self.assertEqual(self.calls()[0]["argv"], ["--bg", "--resume", self.SID, cs.CONTINUE_PROMPT])
        self.assertEqual(cs.load_queue(self.cache_root()), [])
        self.assertIsNotNone(cs.kept_chats(self.cache_root())[0]["wentOnAt"])
        self.assertEqual(len(self.log_lines()), 2)
        self.assertTrue(self.log_lines()[1].endswith(answer["message"]))

    def test_start_it_now_ends_what_it_waits_for_at_once_and_says_so(self):
        # "yes end it and say that" (2026-11-01): Start it now on a go-on
        # that waits for its chat's background commands doesn't wait on
        (task,) = cs.load_queue(self.cache_root())
        self.assertTrue(self.queue("--start-queued", task["id"])["waits"])
        ended = []

        def end(home, entry, profile, claude=None):
            ended.append(entry["jobId"])
            self.session_file.unlink()
            return True, "Stopped"
        with mock.patch.object(cs, "end_background_work", side_effect=end):
            answer = self.queue("--start-queued", task["id"], "--now")
        self.assertEqual(ended, [self.SID[:8]])
        self.assertEqual(answer, {"ok": True, "message": "“Fix it” started now: it ended its background command "
                                                         "“python3 -m http.server 8000” and went on in the background on "
                                                         "work (1a2b3c4d)",
                                  "ended": ["python3 -m http.server 8000"], "notify": True})
        self.assertEqual(cs.load_queue(self.cache_root()), [])
        self.assertTrue(self.log_lines()[-1].endswith(answer["message"]))
        # an SSH host's: it asks the host to end them at once (its clock may be behind)
        self.assertTrue(self.queue("--queue-continue", self.SID, "--profile", ".claude", "--at", str(self.at), "--cwd",
                                   "/srv/app", "--host", "lab", "--name", "Lab chat")["ok"])
        (lab,) = cs.load_queue(self.cache_root())
        import remote
        with mock.patch.object(remote, "host_answer", return_value={"ok": True, "message": "Went on"}) as ask:
            self.queue("--start-queued", lab["id"], "--now")
        self.assertEqual(ask.call_args[0][1][-2:], ["--ends-at", "1"])
        # the queued line's Start it now asks for it, in both front ends (the go-on at its time doesn't)
        repo = Path(__file__).resolve().parent.parent
        self.assertIn("onClicked: root.startQueued(queuedLine.task, true)",
                      (repo / "package/contents/ui/GroupSection.qml").read_text())
        main = (repo / "package/contents/ui/main.qml").read_text()
        self.assertIn('(now ? " --now" : "")', main)
        self.assertIn("            startQueued(t)\n", main)
        self.assertIn('post({ type: "startQueued", id: t.id, now: true })',
                      (repo / "vscode/webview/components/QueuedTasks.tsx").read_text())
        self.assertIn('...(now ? ["--now"] : [])', (repo / "vscode/src/dashboard.ts").read_text())

    def test_a_go_on_with_nothing_in_the_background_is_as_ever(self):
        self.session_file.unlink()
        (task,) = cs.load_queue(self.cache_root())
        self.assertEqual(self.queue("--start-queued", task["id"]),
                         {"ok": True, "message": "Went on in the background on work (1a2b3c4d)"})
        self.assertEqual(self.log_lines(), [])
        # one that went on by itself already isn't a go-on that didn't take either
        cs.keep_chat(self.cache_root(), ".claude-work", self.SID, "Fix it", str(self.folder))
        self.assertTrue(self.queue("--queue-continue", self.SID, "--profile", ".claude-work", "--at", str(self.at))["ok"])
        self.stopped_chat(prompt("go on", self.now - 30), reply("Done.", self.now - 20, msg_id="m2"))
        (task,) = cs.load_queue(self.cache_root())
        went = cs.kept_chats(self.cache_root())[0]["wentOnAt"]
        self.assertEqual(self.queue("--start-queued", task["id"]), {"ok": True, "message": ""})
        self.assertEqual(cs.kept_chats(self.cache_root())[0]["wentOnAt"], went)

    def test_a_chat_at_work_without_a_limit_stop_and_a_wait_for_the_limit(self):
        # (not stopped by a limit: at work, it stays where it is, as before)
        write(self.home / f".claude-work/projects/-repos-app/{self.SID}.jsonl",
              lines(prompt("fix it", self.now - 60, cwd=str(self.folder))))
        answer = cs.continue_chat(self.home, [], ".claude-work", self.SID, None, "", str(self.bin / "claude"), force=True,
                                  ends_at=int(time.time() * 1000) + 60_000)
        self.assertEqual(answer, {"ok": False, "message": "It's at work again, so it stays where it is"})
        # a go-on that waited, then waits for the usage limit: it waits afresh from its new time
        self.stopped_chat()
        (task,) = cs.load_queue(self.cache_root())
        self.assertTrue(self.queue("--start-queued", task["id"])["waits"])
        later = int(time.time() * 1000) + 3600_000
        self.assertTrue(self.queue("--requeue", task["id"], "--at", str(later))["ok"])
        (back,) = cs.load_queue(self.cache_root())
        self.assertEqual((back["startAt"], "dueAt" in back, "waits" in back), (later, False, False))

    def test_an_ssh_hosts_go_on_waits_there(self):
        self.assertTrue(self.queue("--queue-continue", self.SID, "--profile", ".claude", "--at", str(self.at), "--cwd",
                                   "/srv/app", "--host", "lab", "--name", "Lab chat")["ok"])
        task = next(t for t in cs.load_queue(self.cache_root()) if t["host"] == "lab")
        import remote
        ends = self.at + cs.GO_ON_WAIT_MS
        with mock.patch.object(remote, "host_answer", return_value={
                "ok": False, "message": "", "waits": True, "commands": ["npm run dev", "tail -f log"], "endsAt": ends}) as ask:
            answer = self.queue("--start-queued", task["id"])
        ask.assert_called_once_with("lab", ["--continue-chat", self.SID, "--profile", ".claude", "--folder", "/srv/app",
                                            "--ends-at", str(ends)])
        self.assertRegex(answer["message"], r"^“Lab chat” waits for its background commands “npm run dev” and “tail -f log” "
                                            r"to finish before it goes on; (tomorrow )?at \d\d:\d\d it ends them$")
        self.assertTrue(answer["notify"])
        self.assertTrue(self.log_lines()[0].endswith(" · lab"))
        back = next(t for t in cs.load_queue(self.cache_root()) if t["host"] == "lab")
        self.assertEqual((back["error"], back["dueAt"]), ("", self.at))
        # there: --ends-at reaches continue_chat
        mask = os.umask(0o022)
        os.umask(mask)
        self.addCleanup(os.umask, mask)
        with mock.patch.object(cs, "continue_chat", return_value={"ok": True, "message": ""}) as go_on, \
                mock.patch.object(cs.Path, "home", return_value=self.home), contextlib.redirect_stdout(io.StringIO()):
            cs.main(["--continue-chat", self.SID, "--profile", ".claude", "--ends-at", "123"])
        self.assertEqual(go_on.call_args[1]["ends_at"], 123)

    def test_its_commands_named_and_ended(self):
        # a session's own shells, when its job names none: Claude's bash -c 'source <snapshot> … && eval …'
        script = ("source /nowhere/shell-snapshots/snapshot-bash-1.sh 2>/dev/null || true && "
                  "eval 'sleep 30 && echo '\"'\"'done'\"'\"'' < /dev/null && pwd -P >| /dev/null")
        proc = subprocess.Popen([sys.executable, "-c", "import subprocess, sys, time\n"
                                 f"subprocess.Popen(['bash', '-c', {script!r}])\nprint('ready', flush=True)\ntime.sleep(60)"],
                                stdout=subprocess.PIPE, text=True)
        self.addCleanup(proc.stdout.close)
        self.addCleanup(lambda: (proc.kill(), proc.wait()) if proc.poll() is None else None)
        self.assertEqual(proc.stdout.readline().strip(), "ready")
        reaper = threading.Thread(target=proc.wait)
        reaper.start()
        self.addCleanup(reaper.join, 10)
        entry = session(self.SID, pid=proc.pid, procStart=cs.proc_start_time(proc.pid), kind="bg", status="busy",
                        jobId="nojob")
        deadline = time.time() + 5
        while not cs.background_commands(entry, self.profile) and time.time() < deadline:
            time.sleep(0.05)
        self.assertEqual(cs.background_commands(entry, self.profile), ["sleep 30 && echo 'done'"])
        tree = cs.process_tree(proc.pid)
        self.assertTrue(tree)

        def stop(profile, job_id, job=None, home=None, claude=None):  # (claude stop: its process quits, not its shells)
            os.kill(proc.pid, 15)
            return True, "Stopped"
        with mock.patch.object(cs, "stop_background", side_effect=stop):
            self.assertEqual(cs.end_background_work(self.home, entry, self.profile), (True, "Stopped"))
        self.assertTrue(all(cs.process_gone({"pid": p, "procStart": s}) for p, s in tree), "its leftovers ended")
        self.assertIsNone(cs.claude_shell_command(["bash", "-c", "npm test"]))


class FakeService:
    """Claude's background service for a profile, as Talpy Den asks it: a
    Unix socket at its place (cs.DAEMON_TMP, patched to a folder of the
    test's), one JSON line in, answer(request) as one JSON line out; the
    requests are kept. Its key is daemon/control.key in the profile."""

    KEY = "0123456789abcdef0123456789abcdef"

    def __init__(self, test, profile, answer):
        import socket
        self.requests, self.answer = [], answer
        root = Path(tempfile.mkdtemp(prefix="td-", dir="/tmp"))  # (a socket's path: at most 107 bytes)
        test.addCleanup(lambda: __import__("shutil").rmtree(root, ignore_errors=True))
        value = str(profile.path)
        patches = [mock.patch.object(cs, "DAEMON_TMP", root), mock.patch.object(cs, "DAEMON_RETRY_GAP", 0),
                   mock.patch.object(cs, "service_config_dir", side_effect=lambda p: value if p.path == profile.path else None)]
        for p in patches:
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
                request = json.loads(data.split(b"\n", 1)[0])
                self.requests.append(request)
                conn.sendall((json.dumps(self.answer(request)) + "\n").encode())

    def ops(self, op):
        return [r for r in self.requests if r.get("op") == op]


class BackgroundServiceTests(TaskFixture):
    """A background session at its usage limit takes the go-on in where it
    is, through Claude's background service (the way `claude agents`
    answers one): never stopped, so a terminal that shows it (claude attach)
    stays on it, and no copy of the chat. The user's report of 2026-11-02:
    at the reset, the go-on stopped the session (claude stop) and the
    terminal attached to it said "Session 06682d7c has exited."; the claude
    --bg --resume that followed, 0.4 s later, came while the service still
    held it, so Claude started a copy (9e5d7c9d) that lost its auto mode and
    xhigh effort."""

    SID = ContinueAfterResetTests.SID
    queue, cache_root = QueueTests.queue, QueueTests.cache_root
    stopped_chat = ContinueAfterResetTests.stopped_chat

    def setUp(self):
        super().setUp()
        self.stopped_chat()
        self.session_file = self.home / ".claude-work/sessions/50.json"
        self.live("idle")

    def live(self, status, **kw):
        write(self.session_file, session(self.SID, kind="bg", status=status, jobId=self.SID[:8], **kw))

    @staticmethod
    def takes_it(request):
        if request["op"] == "reply":
            return {"ok": True, "op": "reply"}
        return {"ok": True, "op": request["op"], "alive": True, "present": True, "ready": True}

    def go_on(self, **kw):
        return cs.continue_chat(self.home, [], ".claude-work", self.SID, None, kw.pop("text", ""), str(self.bin / "claude"),
                                **kw)

    def test_its_session_takes_the_go_on_in_and_isnt_stopped(self):
        service = FakeService(self, self.profile, self.takes_it)
        cs.keep_chat(self.cache_root(), ".claude-work", self.SID, "Fix it", str(self.folder))
        self.assertTrue(self.queue("--queue-continue", self.SID, "--profile", ".claude-work",
                                   "--at", str(int(time.time() * 1000) - 1000), "--name", "Fix it")["ok"])
        (task,) = cs.load_queue(self.cache_root())
        self.assertEqual(self.queue("--start-queued", task["id"]),
                         {"ok": True, "message": "Went on in its background chat on work (e3de1242)"})
        self.assertEqual(service.requests, [{"op": "reply", "short": "e3de1242", "text": cs.CONTINUE_PROMPT,
                                             "auth": FakeService.KEY, "proto": 1}])
        self.assertEqual(self.calls(), [], "no claude stop, no claude --bg --resume")
        self.assertEqual(cs.load_queue(self.cache_root()), [])
        self.assertIsNotNone(cs.kept_chats(self.cache_root())[0]["wentOnAt"], "a go-on that didn't take is tried again")

    def test_one_at_work_on_the_background_commands_the_limit_left_takes_it_in_at_once(self):
        # (they run on: no wait for them, nothing ended)
        service = FakeService(self, self.profile, self.takes_it)
        self.live("busy")
        answer = self.go_on(text="go on with step 2", ends_at=int(time.time() * 1000) + 60_000)
        self.assertEqual(answer, {"ok": True, "message": "Went on in its background chat on work (e3de1242)",
                                  "id": "e3de1242"})
        self.assertEqual([r["text"] for r in service.ops("reply")], ["go on with step 2"])
        # one at work on more than that (its newest turn isn't the limit's) isn't typed into
        write(self.home / f".claude-work/projects/-repos-app/{self.SID}.jsonl",
              lines(prompt("fix it", self.now - 60, cwd=str(self.folder))))
        self.assertEqual(self.go_on(force=True), {"ok": False, "message": "It's at work again, so it stays where it is"})
        # nor one that asks you something
        self.stopped_chat()
        self.live("waiting", waitingFor="permission prompt")
        self.assertFalse(self.go_on(force=True)["ok"])
        self.assertEqual(len(service.ops("reply")), 1)
        self.assertEqual(self.calls(), [])

    def test_a_reply_starting_or_restarting_is_tried_again_as_claude_does(self):
        tries = []

        def starting(request):
            tries.append(request["op"])
            if request["op"] == "reply" and len(tries) < 3:
                return {"ok": False, "error": "the session is still starting", "code": "ESTARTING"}
            return self.takes_it(request)
        FakeService(self, self.profile, starting)
        self.assertTrue(self.go_on()["ok"])
        self.assertEqual(tries, ["reply"] * 3)
        self.assertEqual(self.calls(), [])

    def test_one_it_wont_take_stops_and_goes_on_once_the_service_let_go(self):
        # (its key doesn't match, say: as before, claude stop then claude --bg --resume, but not
        # while the service still holds its session, which would start a copy)
        held = {"n": 3}

        def refuses(request):
            if request["op"] == "reply":
                return {"ok": False, "error": "reply rejected: the presented daemon control key doesn't match",
                        "code": "EAUTH"}
            held["n"] -= 1
            return {"ok": True, "op": "has", "alive": held["n"] > 0, "present": held["n"] > 0, "ready": True}
        service = FakeService(self, self.profile, refuses)
        stops, starts = [], []

        def stop(profile, job_id, job=None, home=None, claude=None):
            stops.append(job_id)
            self.session_file.unlink()  # (its process quit; the service lets go a moment later)
            return True, "Stopped"
        start = cs.start_background
        with mock.patch.object(cs, "stop_background", side_effect=stop), \
                mock.patch.object(cs, "start_background", side_effect=lambda *a, **k: starts.append(held["n"]) or start(*a, **k)):
            answer = self.go_on()
        self.assertEqual(answer, {"ok": True, "message": "Went on in the background on work (1a2b3c4d)", "id": "1a2b3c4d"})
        self.assertEqual((stops, starts), (["e3de1242"], [0]))
        self.assertEqual([r["short"] for r in service.ops("has")], ["e3de1242"] * 3)
        self.assertEqual(self.calls()[-1]["argv"], ["--bg", "--resume", self.SID, cs.CONTINUE_PROMPT])

    def test_no_service_no_key_or_no_answer_is_as_before(self):
        self.assertEqual(cs.reply_to_background(self.profile, "e3de1242", "hi"),
                         (False, "Claude's background service can't be asked"))  # (no key)
        service = FakeService(self, self.profile, lambda r: {"ok": False, "error": "unknown op: reply", "code": "EUNKNOWN"})
        self.assertEqual(cs.reply_to_background(self.profile, "e3de1242", "hi"),
                         (False, "Claude's background service didn't take it: unknown op: reply"))
        self.assertEqual(cs.reply_to_background(self.profile, "../x", "hi"), (False, "Claude's background service can't be asked"))
        with mock.patch.object(cs, "service_config_dir", return_value=None):
            self.assertEqual(cs.reply_to_background(self.profile, "e3de1242", "hi"),
                             (False, "Claude's background service didn't answer"))
            self.assertFalse(cs.daemon_holds([self.profile], ["e3de1242"]))
        # (a service of another user, who made that folder in /tmp first: never told your message or the key)
        asked = len(service.requests)
        with mock.patch.object(cs, "peer_uid", return_value=os.getuid() + 1):
            self.assertEqual(cs.reply_to_background(self.profile, "e3de1242", "hi"),
                             (False, "Claude's background service didn't answer"))
        self.assertEqual(len(service.requests), asked)
        import socket
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.connect(str(service.path))
            self.assertEqual(cs.peer_uid(s), os.getuid())
        # (where Claude puts it: /tmp/cc-daemon-<uid>/<sha256 of the CLAUDE_CONFIG_DIR it runs with>[:8])
        with mock.patch.object(cs, "service_config_dir", return_value="/home/u/.claude-work"), \
                mock.patch.object(cs, "DAEMON_TMP", Path("/tmp")):
            self.assertEqual(str(cs.daemon_socket(self.profile)), f"/tmp/cc-daemon-{os.getuid()}/9fa37e90/control.sock")


class KeepGoingTests(TaskFixture):
    """A chat that keeps going until it's done: after each usage limit that
    stops it, it goes on by itself (look_after_kept queues each go-on)."""

    SID = ContinueAfterResetTests.SID
    queue, cache_root = QueueTests.queue, QueueTests.cache_root

    def setUp(self):
        super().setUp()
        self.now_ms = int(self.now * 1000)
        self.reset = self.now_ms + 3600_000
        self.path = self.home / f".claude-work/projects/-repos-app/{self.SID}.jsonl"
        self.entries = [prompt("fix it", self.now - 600, cwd=str(self.folder))]

    def say(self, *more):
        self.entries += more
        write(self.path, lines(*self.entries))

    def limit(self, ts):
        return limit_error("You've hit your session limit · resets 10:40am (Europe/Berlin)", ts)

    def look(self, now_ms, rows=(), pct=100, cap=0):
        groups = [{"profileKeys": [".claude-work"], "sessions": list(rows),
                   "limits": {"windows": [{"key": "five_hour", "label": "5h", "pct": pct, "resetsAt": self.reset}]}}]
        cs.note_caps(groups, cap, now_ms)
        cs.look_after_kept(self.home, self.cache_root(), [], groups, now_ms, cap)
        return cs.load_queue(self.cache_root())

    def kept(self):
        return cs.kept_chats(self.cache_root())

    def test_it_goes_on_after_each_limit_until_its_done(self):
        self.say(self.limit(self.now - 60))
        self.assertEqual(self.queue("--keep-going", self.SID, "--profile", ".claude-work", "--name", "Fix it")["message"],
                         "It keeps going: when a usage limit stops it, it goes on by itself after the reset, until it's done")
        (task,) = self.look(self.now_ms)
        self.assertEqual((task["chat"], task["name"], task["startAt"], task["why"], task["prompt"]),
                         (self.SID, "Fix it", self.reset + 60_000, "", ""))
        self.assertEqual(len(self.look(self.now_ms + 1000)), 1, "queued once")
        # the limit resets: it goes on (and while it starts, a status doesn't queue it again)
        start, where = cs.continue_chat, cs.continuation

        def going_on(*a, **k):
            self.assertEqual(self.look(int(time.time() * 1000)), [])
            return start(*a, **k)

        def looking_up(*a, **k):  # (taken out of the queue, not started yet: 2026-11-03)
            self.assertEqual(self.look(int(time.time() * 1000)), [])
            return where(*a, **k)
        with mock.patch.object(cs, "continue_chat", side_effect=going_on), \
                mock.patch.object(cs, "continuation", side_effect=looking_up):
            self.assertEqual(self.queue("--start-queued", task["id"])["message"], "Went on in the background on work (1a2b3c4d)")
        self.assertIsNotNone(self.kept()[0]["wentOnAt"])
        # a limit stops it again in the next window: it goes on after that one too
        after = self.reset / 1000
        self.say(prompt(cs.CONTINUE_PROMPT, after + 60), reply("On it.", after + 70, msg_id="m2"), self.limit(after + 600))
        self.reset += 5 * 3600_000
        (task,) = self.look(int((after + 660) * 1000))
        self.assertEqual(task["startAt"], self.reset + 60_000)
        self.queue("--start-queued", task["id"])
        # and once a turn of it ends by itself, it's done
        went = self.kept()[0]["wentOnAt"] / 1000
        self.say(prompt(cs.CONTINUE_PROMPT, went + 5), reply("All done.", went + 10, msg_id="m3"))
        self.assertEqual(self.look(int((went + 20) * 1000)), [])
        self.assertEqual((self.kept(), len(self.calls())), ([], 2))

    def test_a_go_on_that_didnt_take_is_tried_again_then_given_up(self):
        self.say(self.limit(self.now - 60))
        cs.keep_chat(self.cache_root(), ".claude-work", self.SID, "Fix it", str(self.folder), now_ms=self.now_ms - 120_000)
        t = self.now_ms
        for pause in cs.KEEP_RETRY_MINUTES:
            cs.note_went_on(self.cache_root(), self.SID, t)  # (nothing new in the chat since)
            self.assertEqual(self.look(t + 60_000), [], "it may still be starting")
            t += cs.KEEP_TAKE_MS + 1000
            (task,) = self.look(t)
            self.assertEqual((task["why"], task["startAt"]), ("retry", t + pause * 60_000))
            cs.change_queue(self.cache_root(), take=task["id"])
        cs.note_went_on(self.cache_root(), self.SID, t)
        self.assertEqual(self.look(t + cs.KEEP_TAKE_MS + 1000), [])
        self.assertEqual(self.kept()[0]["error"], "Gave up after 5 tries: it didn't go on")
        self.assertEqual(self.look(t + 3 * cs.KEEP_TAKE_MS), [], "given up")
        # something new in the chat starts it over
        self.say(self.limit((t + 3 * cs.KEEP_TAKE_MS) / 1000 + 10))
        (task,) = self.look(t + 4 * cs.KEEP_TAKE_MS)
        self.assertEqual((task["why"], self.kept()[0]["error"]), ("", ""))

    def test_a_turn_that_broke_off_on_an_api_error_goes_on_again(self):
        self.say(self.limit(self.now - 600))
        cs.keep_chat(self.cache_root(), ".claude-work", self.SID, "Fix it", str(self.folder), now_ms=self.now_ms - 500_000)
        cs.note_went_on(self.cache_root(), self.SID, self.now_ms - 300_000)
        self.say(prompt(cs.CONTINUE_PROMPT, self.now - 290),
                 api_error("API Error: Connection lost mid-response. The response above may be incomplete.", self.now - 280))
        (task,) = self.look(self.now_ms)
        self.assertEqual((task["why"], task["prompt"], task["startAt"]), ("retry", cs.RETRY_PROMPT, self.now_ms + 2 * 60_000))
        # (it goes on whatever its newest turn: that isn't a limit's)
        self.assertEqual(self.queue("--start-queued", task["id"])["message"], "Went on in the background on work (1a2b3c4d)")
        self.assertEqual(self.calls()[0]["argv"], ["--bg", "--resume", self.SID, cs.RETRY_PROMPT])

    def test_when_it_waits(self):
        at = self.now_ms - 60_000
        k = {"chat": self.SID, "profile": ".claude-work", "since": at - 60_000, "wentOnAt": None, "tries": 0}
        limit = {"kind": "limit", "window": "five_hour", "text": "You've hit your session limit", "at": at, "ended": True}
        limits = {"windows": [{"key": "five_hour", "pct": 100, "resetsAt": self.reset}]}
        row = {"sessionId": self.SID, "chatId": self.SID, "pid": 42, "state": "idle", "entrypoint": "cli"}
        self.assertEqual(cs.kept_step(dict(k), limit, row, False, limits, self.now_ms), ("go on", self.reset + 60_000, "", ""))
        self.assertIsNone(cs.kept_step(dict(k), limit, row, True, limits, self.now_ms), "its go-on is queued")
        for state in ("working", "waiting"):
            self.assertIsNone(cs.kept_step(dict(k), limit, dict(row, state=state), False, limits, self.now_ms))
        tab = dict(k)
        self.assertIsNone(cs.kept_step(tab, limit, dict(row, entrypoint="claude-vscode"), False, limits, self.now_ms))
        self.assertIn("open in a Claude Code panel", tab["note"])
        resumed = dict(k)
        self.assertIsNone(cs.kept_step(resumed, limit, dict(row, sessionId="0a1b2c3d"), False, limits, self.now_ms))
        self.assertEqual(resumed["note"], "It's open in a chat it was resumed in: it can't go on by itself while that one is open")
        login = dict(k)
        self.assertIsNone(cs.kept_step(login, dict(limit, kind="login"), None, False, limits, self.now_ms))
        self.assertIn("log in again", login["note"])
        # kept while it works: done once that turn ends by itself, not before
        ended = {"kind": "reply", "at": at, "ended": True}
        self.assertIsNone(cs.kept_step(dict(k, since=at + 1000), ended, row, False, limits, self.now_ms), "nothing new since")
        self.assertEqual(cs.kept_step(dict(k), ended, row, False, limits, self.now_ms), "done")
        # a turn with no process to finish it broke off: on again
        open_turn = {"kind": "reply", "at": self.now_ms - cs.KEEP_TAKE_MS - 1000, "ended": False}
        self.assertIsNone(cs.kept_step(dict(k), dict(open_turn, at=self.now_ms - 1000), None, False, limits, self.now_ms))
        self.assertEqual(cs.kept_step(dict(k), open_turn, None, False, limits, self.now_ms)[2], "retry")

    def test_a_chat_you_interrupted_is_let_go(self):
        # (Esc while it works, then the chat closed: you took over)
        note = "[Request interrupted by user for tool use]"
        cut = tool_result("b", self.now - 589)
        cut["message"]["content"][0]["content"] = note
        self.say(tool_use("b", "Bash", {"command": "make"}, self.now - 590), cut,
                 {"type": "user", "timestamp": iso(self.now - 589), "message": {"role": "user", "content": [{"type": "text", "text": note}]}})
        self.assertEqual(cs.last_turn(self.path), {"kind": "interrupted", "at": int((self.now - 589) * 1000), "ended": True})
        cs.keep_chat(self.cache_root(), ".claude-work", self.SID, "Fix it", str(self.folder), now_ms=self.now_ms - 700_000)
        self.assertEqual(self.look(self.now_ms + cs.KEEP_TAKE_MS + 60_000), [])
        self.assertEqual(self.kept(), [])
        # a prompt after it: a turn of its own again
        self.say(prompt("go on", self.now - 500))
        self.assertEqual(cs.last_turn(self.path)["kind"], "prompt")

    def test_a_limit_with_no_known_reset_waits_longer_each_time(self):
        at = self.now_ms - 60_000
        k = {"chat": self.SID, "profile": ".claude-work", "since": at - 60_000, "wentOnAt": None, "tries": 0}
        limits = {"windows": [{"key": "five_hour", "pct": 100, "resetsAt": self.reset}]}
        row = {"sessionId": self.SID, "chatId": self.SID, "pid": 42, "state": "idle", "entrypoint": "cli"}
        # out of usage credits: no window, no time in the message (not on again right away, each time it hits it)
        out = {"kind": "limit", "window": None, "text": "You're out of usage credits", "at": at, "ended": True}
        for n, minutes in enumerate(cs.KEEP_RETRY_MINUTES):
            self.assertEqual(cs.kept_step(k, dict(out, at=at + n), row, False, limits, self.now_ms),
                             ("go on", self.now_ms + minutes * 60_000, "", ""))
        self.assertIsNone(cs.kept_step(k, dict(out, at=at + 9), row, False, limits, self.now_ms))
        self.assertEqual(k["error"], "Gave up after 5 tries: You're out of usage credits")
        # a limit with no window on record whose message names the day it resets: on after that
        day = datetime.fromtimestamp(self.now + 3 * 86400)
        sonnet = {"kind": "limit", "window": "seven_day_sonnet", "at": at, "ended": True,
                  "text": f"You've hit your Sonnet limit · resets {day:%b} {day.day}, {day.year}, 7pm (Europe/Berlin)"}
        k = {"chat": self.SID, "profile": ".claude-work", "since": at - 60_000, "wentOnAt": None, "tries": 3}
        reset = int(day.replace(hour=19, minute=0, second=0, microsecond=0).timestamp() * 1000)
        self.assertEqual(cs.kept_step(k, sonnet, row, False, limits, self.now_ms), ("go on", reset + 60_000, "", ""))
        self.assertEqual(k["tries"], 0)

    def test_the_usage_cap_stops_what_works_once_and_kept_chats_go_on_after(self):
        self.say(reply("On it.", self.now - 30, msg_id="m2"))
        cs.keep_chat(self.cache_root(), ".claude-work", self.SID, "Fix it", str(self.folder), now_ms=self.now_ms - 60_000)
        rows = [{"sessionId": self.SID, "chatId": self.SID, "pid": 4242, "state": "working", "kind": "interactive"},
                {"sessionId": "other", "chatId": "other", "pid": 4343, "state": "working", "kind": "bg", "jobId": "e3de1242"},
                {"sessionId": "calm", "chatId": "calm", "pid": 4444, "state": "idle", "kind": "interactive"}]
        stopped = []
        with mock.patch.object(cs, "in_background", side_effect=lambda task: task()), \
                mock.patch.object(cs, "stop_all", side_effect=lambda home, extra, sessions: stopped.extend(s["sessionId"] for s in sessions)):
            self.assertEqual(self.look(self.now_ms, rows, pct=89, cap=90), [])
            self.assertEqual(stopped, [], "below the cap")
            self.assertEqual(self.look(self.now_ms, rows, pct=92, cap=90), [])
            self.assertEqual(stopped, [self.SID, "other"])
            self.look(self.now_ms + 1000, rows, pct=95, cap=90)
            self.assertEqual(stopped, [self.SID, "other"], "once in that window")
        # stopped, the chat that keeps going goes on after that window resets (whatever its newest turn)
        (task,) = self.look(self.now_ms + 2000, [], pct=95, cap=90)
        self.assertEqual((task["chat"], task["why"], task["startAt"]), (self.SID, "cap", self.reset + 60_000))
        self.assertEqual(self.queue("--start-queued", task["id"])["message"], "Went on in the background on work (1a2b3c4d)")
        # the account is marked while it's at the cap (queued tasks wait for that window)
        groups = [{"limits": {"windows": [{"key": "seven_day", "label": "7d", "pct": 91, "resetsAt": self.reset}]}}]
        cs.note_caps(groups, 90, self.now_ms)
        self.assertEqual(groups[0]["cap"], {"pct": 90, "label": "7d", "key": "seven_day", "resetsAt": self.reset})
        cs.note_caps(groups, 0, self.now_ms)
        self.assertIsNone(groups[0]["cap"])

    def test_turning_it_off_and_where_it_cant(self):
        self.say(self.limit(self.now - 60))
        at = str(self.reset + 60_000)
        self.assertTrue(self.queue("--queue-continue", self.SID, "--profile", ".claude-work", "--at", at, "--keep")["ok"])
        self.assertEqual(len(self.kept()), 1)
        answer = self.queue("--keep-off", self.SID)
        self.assertRegex(answer["message"], r"^It goes on (tomorrow )?at \d\d:\d\d as queued, but not after later limits$")
        self.assertEqual((self.kept(), len(cs.load_queue(self.cache_root()))), ([], 1), "its queued go-on stays")
        (task,) = cs.load_queue(self.cache_root())
        self.queue("--unqueue", task["id"])
        self.assertEqual(self.queue("--keep-off", self.SID), {"ok": True, "message": "It won't go on by itself any more"})
        # cancelling its go-on stops it keeping going (else it would be queued again at once)
        self.assertTrue(self.queue("--queue-continue", self.SID, "--profile", ".claude-work", "--at", at, "--keep")["ok"])
        (task,) = cs.load_queue(self.cache_root())
        self.queue("--unqueue", task["id"])
        self.assertEqual((self.kept(), self.look(self.now_ms)), ([], []))
        # a chat whose folder Claude doesn't trust can't go on by itself
        write(self.home / f".claude-work/projects/-home/{self.SID}.jsonl",
              lines(prompt("hi", self.now, cwd=str(self.home)), self.limit(self.now + 1)))
        self.path.unlink()
        answer = self.queue("--keep-going", self.SID, "--profile", ".claude-work")
        self.assertFalse(answer["ok"])
        self.assertIn("Claude doesn't trust your home folder", answer["message"])


def tool_use(tid, name, inp, ts):
    return {"type": "assistant", "timestamp": iso(ts),
            "message": {"id": "m" + tid, "role": "assistant", "content": [{"type": "tool_use", "id": tid, "name": name, "input": inp}]}}


def tool_result(tid, ts, error=False):
    return {"type": "user", "timestamp": iso(ts),
            "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tid, "is_error": error, "content": "ok"}]}}


class KeepGoingOnHostsTests(TaskFixture):
    """(2026-11-02, the user: Keep going on SSH hosts and in containers too)
    A chat of an SSH host or a container that keeps going is kept here, with
    its host, and goes on from here over ssh, as its queued go-on does. The
    host's status run keeps it listed and says how it stands (--kept-chats:
    keptTurns); the engine here judges it from that host's last answer (as
    remote.py keeps it), as of when that came, on this computer's clock."""

    SID = ContinueAfterResetTests.SID
    NEW = "0a1b2c3d-4e5f-4061-8a7b-9c0d1e2f3a4b"
    queue, cache_root = QueueTests.queue, QueueTests.cache_root
    HOST = "lab"

    def setUp(self):
        super().setUp()
        self.now_ms = int(self.now * 1000)
        self.reset = self.now_ms + 3600_000

    def answer(self, turn=None, at=None, offset=0, rows=(), host=None, kept=True, gone=False, moved=None, chat=None):
        """host's last answer, saved as remote.py saves it: its times on its
        own clock, offset ms behind this computer's."""
        at = self.now_ms if at is None else at
        result = {"ok": True, "generatedAt": at - offset, "moved": moved or {},
                  "groups": [{"title": "lab · Max", "profileKeys": [".claude"], "sessions": list(rows),
                              "limits": {"windows": [{"key": "five_hour", "pct": 100, "resetsAt": self.reset - offset}]}}]}
        if kept:
            result["keptTurns"] = {chat or self.SID: {"gone": True} if gone else {"turn": turn}}
        write(self.cache_root() / "hosts" / f"{host or self.HOST}.json",
              {"at": at, "offset": offset, "answer": {"ok": True, "host": host or self.HOST, "result": result}})

    def limit(self, at, offset=0):
        return {"kind": "limit", "window": "five_hour", "text": "You've hit your session limit", "at": at - offset, "ended": True}

    def look(self, now_ms, groups=()):
        cs.look_after_kept(self.home, self.cache_root(), [], list(groups), now_ms)
        return cs.load_queue(self.cache_root())

    def kept(self):
        return cs.kept_chats(self.cache_root())

    def keep(self, host=None):
        return self.queue("--keep-going", self.SID, "--profile", ".claude", "--cwd", "/srv/app", "--name", "Fix it",
                          "--host", host or self.HOST)

    def test_it_goes_on_from_here_after_each_limit_until_its_done(self):
        import remote
        self.assertEqual(self.keep()["message"],
                         "It keeps going: when a usage limit stops it, it goes on by itself after the reset, until it's done")
        self.assertEqual([(k["chat"], k["host"], k["profile"]) for k in self.kept()], [(self.SID, "lab", ".claude")])
        self.answer(self.limit(self.now_ms - 60_000))
        (task,) = self.look(self.now_ms)
        self.assertEqual((task["host"], task["chat"], task["profile"], task["account"], task["folder"], task["startAt"], task["why"]),
                         ("lab", self.SID, ".claude", "lab · Max", "/srv/app", self.reset + 60_000, ""))
        self.assertEqual(len(self.look(self.now_ms + 1000)), 1, "queued once")
        # the limit resets: it goes on over ssh (as you queued it), noted first
        with mock.patch.object(remote, "host_answer", return_value={"ok": True, "message": "Went on in the background on work (1a2b3c4d)"}) as ask:
            self.assertEqual(self.queue("--start-queued", task["id"])["message"], "Went on in the background on work (1a2b3c4d)")
        self.assertEqual(ask.call_args[0][0], "lab")
        self.assertNotIn("--force", ask.call_args[0][1])
        went = self.kept()[0]["wentOnAt"]
        self.assertIsNotNone(went)
        # an answer from before it went on says nothing about that go-on, however late it's read
        self.answer(self.limit(self.now_ms - 60_000), at=went - 1000)
        self.assertEqual(self.look(went + cs.KEEP_TAKE_MS * 2), [])
        self.assertEqual((self.kept()[0]["tries"], self.kept()[0]["error"]), (0, ""))
        # the next one: a turn of it ended by itself after the go-on: it's done
        self.answer({"kind": "reply", "at": went + 60_000, "ended": True}, at=went + 120_000)
        self.assertEqual(self.look(went + 125_000), [])
        self.assertEqual(self.kept(), [])

    def test_its_times_are_put_on_this_computers_clock(self):
        # the host's clock is 2 hours behind: its limit and its reset are 2 hours "earlier"
        self.keep()
        self.answer(self.limit(self.now_ms - 60_000, offset=7200_000), offset=7200_000)
        (task,) = self.look(self.now_ms)
        self.assertEqual(task["startAt"], self.reset + 60_000)
        # and a turn there that ended after it was kept ended after it, though the host's clock says 2 hours before
        cs.change_queue(self.cache_root(), take=task["id"])
        cs.keep_chat(self.cache_root(), ".claude", self.SID, host="lab", on=False)
        cs.keep_chat(self.cache_root(), ".claude", self.SID, "Fix it", "/srv/app", now_ms=self.now_ms, host="lab")
        self.answer({"kind": "reply", "at": self.now_ms + 60_000 - 7200_000, "ended": True}, at=self.now_ms + 120_000,
                    offset=7200_000)
        self.assertEqual((self.look(self.now_ms + 125_000), self.kept()), ([], []))

    def test_a_go_on_that_didnt_take_there_is_tried_again_whatever_its_newest_turn(self):
        import remote
        self.keep()
        t = self.now_ms
        cs.note_went_on(self.cache_root(), self.SID, t, host="lab")
        self.answer(self.limit(t - 600_000), at=t + 60_000)
        self.assertEqual(self.look(t + 60_000), [], "it may still be starting")
        self.answer(self.limit(t - 600_000), at=t + cs.KEEP_TAKE_MS + 1000)
        (task,) = self.look(t + cs.KEEP_TAKE_MS + 2000)
        self.assertEqual((task["why"], task["startAt"], task["host"]), ("retry", t + cs.KEEP_TAKE_MS + 1000 + 2 * 60_000, "lab"))
        with mock.patch.object(remote, "host_answer", return_value={"ok": True, "message": "Went on"}) as ask:
            self.queue("--start-queued", task["id"])
        self.assertIn("--force", ask.call_args[0][1])
        # a go-on that went on already (nothing to do there): it doesn't count as one that didn't take
        cs.note_went_on(self.cache_root(), self.SID, t, host="lab")
        (task,) = [cs.queue_entry(".claude", "/srv/app", "", t, host="lab", chat=self.SID)]
        cs.change_queue(self.cache_root(), add=task)
        with mock.patch.object(remote, "host_answer", return_value={"ok": True, "message": ""}):
            self.queue("--start-queued", task["id"])
        self.assertEqual(self.kept()[0]["wentOnAt"], t)

    def test_while_its_host_doesnt_answer_it_waits_and_says_so(self):
        self.keep()
        self.answer(self.limit(self.now_ms - 60_000), at=self.now_ms - cs.KEEP_HOST_STALE_MS - 60_000)
        self.assertEqual(self.look(self.now_ms), [])
        self.assertEqual(self.kept()[0]["note"], "Talpy Den hasn't heard from lab for a while: it can go on once that answers again")
        # (a container's name, and its host's)
        self.assertEqual(cs.host_words("docker:web@lab"), "web on lab")
        self.assertEqual(cs.host_words("podman:dev"), "dev")
        # its answer comes: on it goes, and the note goes
        self.answer(self.limit(self.now_ms - 60_000))
        self.assertEqual(len(self.look(self.now_ms)), 1)
        self.assertEqual(self.kept()[0]["note"], "")
        # (2026-11-03) also while its go-on waits for the reset
        self.answer(self.limit(self.now_ms - 60_000), at=self.now_ms - cs.KEEP_HOST_STALE_MS - 60_000)
        self.look(self.now_ms)
        self.answer(self.limit(self.now_ms - 60_000))
        self.assertEqual((len(self.look(self.now_ms)), self.kept()[0]["note"]), (1, ""))

    def test_an_answer_from_before_it_was_kept_or_of_a_chat_gone_there(self):
        self.keep()
        self.answer(kept=False)  # (asked before it was kept: no word on it)
        self.assertEqual((self.look(self.now_ms), len(self.kept())), ([], 1))
        self.answer(gone=True)  # (its transcript is gone there)
        self.assertEqual((self.look(self.now_ms), self.kept()), ([], []))

    def test_it_follows_its_chat_claude_moved_to_the_background_there(self):
        self.keep()
        self.answer(self.limit(self.now_ms - 60_000), moved={self.SID: self.NEW}, chat=self.NEW)
        (task,) = self.look(self.now_ms)
        self.assertEqual((task["chat"], self.kept()[0]["chat"]), (self.NEW, self.NEW))

    def test_at_work_or_open_in_a_claude_code_panel_there(self):
        self.keep()
        row = {"sessionId": self.SID, "chatId": self.SID, "pid": 42, "state": "working", "entrypoint": "cli", "name": "Fix it now"}
        self.answer(self.limit(self.now_ms - 60_000), rows=[row])
        self.assertEqual(self.look(self.now_ms), [])
        self.assertEqual(self.kept()[0]["name"], "Fix it now")  # (as it's called there now)
        self.answer(self.limit(self.now_ms - 60_000), rows=[dict(row, state="idle", entrypoint="claude-vscode")])
        self.assertEqual(self.look(self.now_ms), [])
        self.assertIn("open in a Claude Code panel", self.kept()[0]["note"])

    def test_this_computers_chat_and_a_hosts_are_kept_apart(self):
        # (one id on both: a copy made by hand, say; and one host's isn't another's)
        self.keep()
        self.keep("docker:web@lab")
        cs.keep_chat(self.cache_root(), ".claude-work", self.SID, "Fix it", str(self.folder))
        self.assertEqual(sorted(k["host"] for k in self.kept()), ["", "docker:web@lab", "lab"])
        self.assertEqual(self.queue("--keep-off", self.SID, "--host", "lab")["message"], "It won't go on by itself any more")
        self.assertEqual(sorted(k["host"] for k in self.kept()), ["", "docker:web@lab"])
        # cancelling a host's queued go-on stops that one keeping going, not this computer's
        task = cs.queue_entry(".claude", "", "", self.reset, host="docker:web@lab", chat=self.SID)
        cs.change_queue(self.cache_root(), add=task)
        self.queue("--unqueue", task["id"])
        self.assertEqual([k["host"] for k in self.kept()], [""])
        # a chat deleted there: forgotten here too (its keep going is kept here)
        self.keep()
        cs.forget_deleted(self.cache_root(), "chats", self.SID, "lab")
        self.assertEqual([k["host"] for k in self.kept()], [""])
        # this computer's look doesn't read a host's transcript here; its own goes on as before
        self.assertFalse(any(k["host"] for k in cs.load_keep(self.cache_root())["chats"] if k["chat"] != self.SID))
        with self.assertRaises(ValueError):
            cs.keep_chat(self.cache_root(), ".claude", self.SID, host="lab; rm -rf /")

    def test_queued_with_keep_on_a_host(self):
        at = str(self.reset + 60_000)
        self.assertEqual(self.queue("--queue-continue", self.SID, "--profile", ".claude", "--at", at, "--host", "lab",
                                    "--name", "Fix it", "--keep")["message"],
                         f"Queued: it goes on {jump.start_time(int(at))}, when the limit resets, and after later limits too until it's done")
        self.assertEqual([(k["chat"], k["host"]) for k in self.kept()], [(self.SID, "lab")])

    def test_a_go_on_that_couldnt_reach_its_host_starts_once_that_answers_again(self):
        # (2026-11-02, the user: disconnected, does it still go on?) Not while the host can't be
        # reached; then it does by itself. One the host refused waits for you, as before.
        import remote
        self.keep()
        task = cs.queue_entry(".claude", "/srv/app", "", self.now_ms - 1000, host="lab", chat=self.SID)
        cs.change_queue(self.cache_root(), add=task)
        unreached = {"ok": False, "reached": False, "message": "Can't reach lab: Connection timed out."}
        with mock.patch.object(remote, "host_answer", return_value=unreached):
            self.assertFalse(self.queue("--start-queued", task["id"])["ok"])
        (back,) = cs.load_queue(self.cache_root())
        self.assertEqual(back["error"], "Can't reach lab: Connection timed out. It starts once lab answers again")
        self.assertIsNone(self.kept()[0]["wentOnAt"])  # (it didn't go on: no "didn't take" to try again later)
        self.assertFalse(cs.queued_tasks(self.cache_root(), self.now_ms)[0]["due"])
        # an answer from before it failed changes nothing; one since makes it due again
        self.answer(self.limit(self.now_ms - 60_000), at=back["unreachable"] - 1000)
        self.look(back["unreachable"] + 1000)
        self.assertTrue(cs.load_queue(self.cache_root())[0]["error"])
        self.answer(self.limit(self.now_ms - 60_000), at=back["unreachable"] + 60_000)
        self.look(back["unreachable"] + 61_000)
        (again,) = cs.load_queue(self.cache_root())
        self.assertEqual((again["error"], "unreachable" in again, again["id"]), ("", False, task["id"]))
        self.assertTrue(cs.queued_tasks(self.cache_root(), back["unreachable"] + 61_000)[0]["due"])
        # a container that isn't running counts as not reached too; what the host said no to doesn't
        with mock.patch.object(remote, "host_answer", return_value={"ok": False, "message": "Claude doesn't trust /srv/app"}):
            self.queue("--start-queued", task["id"])
        (refused,) = cs.load_queue(self.cache_root())
        self.assertEqual((refused["error"], "unreachable" in refused), ("Claude doesn't trust /srv/app", False))
        self.answer(self.limit(self.now_ms - 60_000), at=self.now_ms + 3600_000)
        self.look(self.now_ms + 3600_000)
        self.assertEqual(cs.load_queue(self.cache_root())[0]["error"], "Claude doesn't trust /srv/app")

    def test_plasma_offers_it_on_a_hosts_and_a_containers_rows(self):
        ui = Path(__file__).resolve().parent.parent / "package/contents/ui"
        main, row = (ui / "main.qml").read_text(), (ui / "SessionRow.qml").read_text()
        recent, group = (ui / "RecentLine.qml").read_text(), (ui / "GroupSection.qml").read_text()
        can = main[main.index("function canKeepGoing("):][:300]
        self.assertNotIn("!host", can)
        self.assertIn('k.chat === chatId && (k.host || "") === (host || "")', main)
        self.assertIn('(host ? " --host " + shellQuote(host) : "")\n                             + configDirArgs', main)  # keepGoing
        self.assertIn('+ (keep ? " --keep" : "")', main)
        self.assertIn('keptChat(s.chatId || s.sessionId, host)', main)  # (its notification says it goes on by itself)
        self.assertIn('(keepOffChat ? " --keep-off " + shellQuote(keepOffChat) : "")', main)  # remoteEnd
        self.assertIn("readonly property var kept: root.keptChat(session.chatId || session.sessionId, remoteHost)", row)
        self.assertIn("visible: row.goOnAt > 0 && row.goingOn === null && row.kept === null\n", row)
        self.assertNotRegex(row, r"remoteHost \? null : root\.keptChat|row\.kept === null && !row\.remoteHost|kept !== null && !row\.remoteHost")
        self.assertIn("root.remoteEnd(remoteHost, session.sessionId, session.profileDir, busy, keepOff && kept ? kept.chat : \"\")", row)
        self.assertEqual(row.count("root.keepGoing(row.session, "), 2)
        self.assertEqual(row.count("root.keepGoing(row.session, true, row.remoteHost)") + row.count("root.keepGoing(row.session, false, row.remoteHost)"), 2)
        self.assertNotIn('i18n("This happens once.")', row)
        self.assertNotRegex(recent, r"!recentLine\.remoteHost && \(root\.keptChat|kept === null && !recentLine\.remoteHost"
                                    r"|recentLine\.remoteHost \? null : root\.keptChat|recentLine\.remoteHost \? \"\" : \" \" \+ i18n\(\"Keep going")
        self.assertIn("root.keptChat(recentLine.chat.sessionId, recentLine.remoteHost)", recent)
        self.assertIn("root.keptChat(queuedLine.task.chat, queuedLine.task.host) !== null", group)

    def test_plasma_says_what_keeps_going_on_hosts_that_arent_shown(self):
        # (unpicked, or a container while Show containers is off: it goes on all the same, so the list
        # says so where the hosts go, with Show and Stop / Cancel; a task you wrote has Show only)
        ui = Path(__file__).resolve().parent.parent / "package/contents/ui"
        main, full, line = (ui / "main.qml").read_text(), (ui / "FullRepresentation.qml").read_text(), (ui / "UnseenLine.qml").read_text()
        items = main[main.index("readonly property var unseenHostItems:"):][:900]
        self.assertIn("if (!k.host || shown.indexOf(k.host) >= 0)", items)
        self.assertIn("if (t.host && shown.indexOf(t.host) < 0 && !out.some(x => x.task === t))", items)
        show = main[main.index("function showHost(host)"):][:300]
        self.assertIn("if (pickedHosts.indexOf(host) < 0)\n            toggleHost(host)", show)   # (never unpicks it)
        self.assertIn("Plasmoid.configuration.showContainers = true", show)
        self.assertLess(full.index("model: root.focusView ? 0 : root.unseenHostItems.length"), full.index("delegate: HostSection {"))
        self.assertIn("onClicked: root.showHost(line.host)", line)
        self.assertIn("visible: !line.wrote", line)
        self.assertIn("root.unqueue(line.task)", line)
        self.assertIn("root.keepGoing({ chatId: line.kept.chat, sessionId: line.kept.chat }, false, line.host)", line)
        self.assertIn('icon.color: Icons.color("cancel", Kirigami.Theme)', line)

    def test_the_hosts_run_lists_them_and_says_how_each_stands(self):
        # (the host's status, talpy_den.py --remote there, with what's kept here for it)
        t = self.now - 300
        write(self.home / f".claude-work/projects/-repos-app/{self.SID}.jsonl",
              lines(prompt("fix it", t, cwd=str(self.folder)), limit_error("You've hit your session limit", t + 1)))
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.object(cs.Path, "home", return_value=self.home), \
                mock.patch.object(cs, "cache_dir", return_value=self.cache_root()):
            cs.main(["--remote", "--no-tokens", "--kept-chats", f"{self.SID}/.claude-work,{self.NEW}/.claude-work"])
        there = json.loads(out.getvalue().split(cs.REMOTE_MARK)[1])
        turn = there["keptTurns"][self.SID]["turn"]
        self.assertEqual((turn["kind"], turn["ended"]), ("limit", True))
        self.assertEqual(there["keptTurns"][self.NEW], {"gone": True})
        # listed while it keeps going, with no process (its terminal closed): a chat to reopen
        (row,) = [s for g in there["groups"] for s in g["sessions"] if s["chatId"] == self.SID]
        self.assertEqual((row["kind"], row["state"]), ("chat", "done"))
        # without them, no word on them (and an answer for this computer has none)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.object(cs.Path, "home", return_value=self.home), \
                mock.patch.object(cs, "cache_dir", return_value=self.cache_root()):
            cs.main(["--remote", "--no-tokens"])
        there = json.loads(out.getvalue().split(cs.REMOTE_MARK)[1])
        self.assertNotIn("keptTurns", there)
        self.assertEqual([s for g in there["groups"] for s in g["sessions"] if s["chatId"] == self.SID], [])

    def test_the_status_asks_the_host_about_them_and_a_stop_there_can_turn_it_off(self):
        import remote
        self.keep()
        self.keep("docker:web@lab")
        with mock.patch.object(remote.Path, "home", return_value=self.home), \
                mock.patch.object(remote, "ssh", side_effect=OSError("stop here")) as ssh:
            remote.status("lab")
        command = ssh.call_args[0][1]
        self.assertIn(f"--kept-chats {self.SID}/.claude", command)  # (only lab's: the container's is asked of it)
        self.assertEqual(command.count("--kept-chats"), 1)
        self.assertEqual(command.count(self.SID), 1)
        # Stop and turn Keep going off: off once it's stopped there, not when it isn't
        for ok, left in ((False, ["docker:web@lab", "lab"]), (True, ["docker:web@lab"])):
            out = io.StringIO()
            with contextlib.redirect_stdout(out), mock.patch.object(remote.Path, "home", return_value=self.home), \
                    mock.patch.object(remote, "run_status_script", return_value=(ok, "Stopped it" if ok else "It's busy")) as end:
                remote.main(["--end", "lab", self.SID, ".claude", "--busy", "--keep-off", self.SID])
            self.assertEqual(end.call_args[0], ("lab", ["--end", self.SID, "--profile", ".claude", "--busy"]))
            self.assertEqual(sorted(k["host"] for k in self.kept()), left)
        self.assertIn("It won't go on by itself any more", json.loads(out.getvalue())["message"])


class PlanFeedbackTests(TaskFixture):
    """Your changes to a plan and your comments on it, sent to the chat that made it."""

    SID = "a1b2c3d4-0000-4000-8000-000000000001"

    def setUp(self):
        super().setUp()
        w = self.home / ".claude-work"
        self.plan = w / "plans/calm-red-owl.md"
        t = self.now - 600
        pf = str(self.home / ".claude/plans/calm-red-owl.md")  # (the plan by the link name: the same file)
        write(w / f"projects/-repos-app/{self.SID}.jsonl", lines(
            prompt("plan it", t, cwd=str(self.folder), slug="calm-red-owl"),
            tool_use("t1", "Write", {"file_path": pf, "content": "# Calm plan\n\n1. Do it\n2. Test it\n"}, t + 1),
            tool_result("t1", t + 2),
            tool_use("t2", "Edit", {"file_path": pf, "old_string": "2. Test it", "new_string": "2. Test it well"}, t + 3),
            tool_result("t2", t + 4),
            tool_use("t3", "Edit", {"file_path": pf, "old_string": "1. Do it", "new_string": "1. Skip it"}, t + 5),
            tool_result("t3", t + 6, error=True),  # (refused: the file didn't change)
            tool_use("t4", "ExitPlanMode", {"planFilePath": pf}, t + 7), tool_result("t4", t + 8, error=True)))
        write(self.plan, "# Calm plan\n\n1. Do it first\n2. Test it well\n")  # (you changed step 1)

    def send(self, *extra, comments=None):
        out = io.StringIO()
        args = ["--plan-feedback", "calm-red-owl", "--profile", ".claude-work", "--chat", self.SID, *extra]
        if comments is not None:
            args += ["--comments", json.dumps(comments)]
        with mock.patch.object(jump.Path, "home", return_value=self.home), \
                mock.patch.object(jump, "claude_in_terminal", return_value=str(self.bin / "claude")), \
                contextlib.redirect_stdout(out):
            jump.main(args)
        return json.loads(out.getvalue())

    def test_claudes_version_is_rebuilt_from_its_transcript(self):
        transcript = self.home / f".claude-work/projects/-repos-app/{self.SID}.jsonl"
        self.assertEqual(cs.claude_plan(transcript, "calm-red-owl"), "# Calm plan\n\n1. Do it\n2. Test it well\n")
        self.assertIsNone(cs.claude_plan(transcript, "other-plan-here"))
        # an edit that doesn't fit what it knows: it can't tell
        self.assertIsNone(cs.apply_plan_tool("# A\n", "Edit", {"old_string": "B", "new_string": "C"}))
        self.assertEqual(cs.apply_plan_tool("a a", "MultiEdit", {"edits": [{"old_string": "a", "new_string": "b", "replace_all": True}]}), "b b")
        self.assertEqual(cs.apply_plan_tool(None, "ExitPlanMode", {"plan": "# P\n"}), "# P\n")

    def test_a_line_claude_took_out_goes_with_its_line_break(self):
        # (as Claude's Edit does: an empty new_string takes the end of the line along)
        self.assertEqual(cs.apply_plan_tool("# P\n\n1. Do it\n2. Test it\n", "Edit",
                                            {"old_string": "1. Do it", "new_string": ""}), "# P\n\n2. Test it\n")
        self.assertEqual(cs.apply_plan_tool("a\nb", "Edit", {"old_string": "b", "new_string": ""}), "a\n")
        self.assertEqual(cs.apply_plan_tool("x\nyx\n", "MultiEdit", {"edits": [
            {"old_string": "x", "new_string": "", "replace_all": True}]}), "y")
        # so a plan Claude took a line out of, unchanged since: nothing to say
        transcript = self.home / f".claude-work/projects/-repos-app/{self.SID}.jsonl"
        pf = str(self.home / ".claude-work/plans/calm-red-owl.md")
        with open(transcript, "a") as f:
            f.write(lines(tool_use("t5", "Edit", {"file_path": pf, "old_string": "2. Test it well", "new_string": ""},
                                   self.now - 500), tool_result("t5", self.now - 499)))
        write(self.plan, "# Calm plan\n\n1. Do it\n")
        self.assertEqual(cs.plan_feedback(self.plan, cs.claude_plan(transcript, "calm-red-owl"), [], self.home), "")

    def test_a_long_message_fits_in_one_argument(self):
        # (the command that reopens the chat has it in one argument, of 128 KB
        # at most: a plan in Chinese takes three bytes a character)
        old = "".join(f"{chr(0x4e00 + i)}先把这个模块的接口整理好，然后再写测试，最后更新文档和说明。\n" for i in range(2000))
        write(self.plan, old.replace("模块", "组件"))
        why = "为什么要这样做？" * 250
        text = cs.plan_feedback(self.plan, old, [{"from": 1, "to": 1, "quote": "", "text": why}], self.home)
        self.assertLessEqual(len(shlex.quote(text).encode()), 120_000)
        self.assertIn("(more changes: read the file)", text)
        self.assertTrue(text.endswith(why))

    def test_the_message_has_your_changes_and_comments(self):
        text = cs.plan_feedback(self.plan, "# Calm plan\n\n1. Do it\n2. Test it well\n",
                                [{"from": 3, "to": 3, "quote": "1. Do it first", "text": "Why first?"}], self.home)
        self.assertTrue(text.startswith("Here is my feedback on your plan (~/.claude-work/plans/calm-red-owl.md)."))
        self.assertIn("stay in plan mode", text)
        self.assertIn("-1. Do it\n+1. Do it first", text)
        self.assertIn("Comment 1, on line 3:\n> 1. Do it first\nWhy first?", text)
        self.assertEqual(cs.plan_feedback(self.plan, self.plan.read_text(), [], self.home), "")  # nothing to say
        self.assertIn("read ~/.claude-work/plans/calm-red-owl.md again", cs.plan_feedback(self.plan, None, [], self.home))

    def test_a_chat_without_a_process_reopens_in_plan_mode_with_it(self):
        answer = self.send("--print-command")
        self.assertTrue(answer["ok"], answer)
        self.assertEqual(answer["how"], "resumed")
        words = shlex.split(answer["command"].split("; ", 1)[1])
        self.assertEqual(words[-5:-1], ["--resume", self.SID, "--permission-mode", "plan"])
        self.assertIn("-1. Do it\n+1. Do it first", words[-1])
        self.assertTrue(answer["command"].startswith(f"cd {self.folder} 2>/dev/null; "))

    def test_an_open_chat_gets_it_typed_in_or_pasted(self):
        w = self.home / ".claude-work"
        write(w / "sessions/50.json", session(self.SID, cwd=str(self.folder), tmux="s:@1.%3"))
        with mock.patch.object(jump, "tmux_paste", return_value=(True, "")) as paste:
            answer = self.send()
        self.assertEqual((answer["ok"], answer["how"]), (True, "typed"))
        self.assertIn("Do it first", paste.call_args[0][1])
        # in a terminal tmux doesn't show: the clipboard, and the chat comes up
        write(w / "sessions/50.json", session(self.SID, cwd=str(self.folder), status="waiting", waitingFor="permission prompt"))
        with mock.patch.object(jump, "copy_to_clipboard", return_value=True) as copy, \
                mock.patch.object(jump, "jump", return_value=(True, "")) as up:
            answer = self.send()
        self.assertEqual((answer["how"], answer["copied"], answer["text"]), ("clipboard", True, ""))
        self.assertIn("keep planning", answer["message"])
        self.assertIn("Do it first", copy.call_args[0][0])
        up.assert_called_once()
        # for VS Code: the text, to paste or type in itself
        answer = self.send("--print-command", comments=[{"from": 1, "to": 1, "quote": "# Calm plan", "text": "Rename it"}])
        self.assertEqual(answer["how"], "clipboard")
        self.assertIn("Rename it", answer["text"])

    def test_a_shared_chat_open_on_another_account_comes_up_itself(self):
        # its transcript is in both accounts, and personal (the first) isn't where it runs
        w = self.home / ".claude-work"
        there = self.home / f".claude-personal/projects/-repos-app/{self.SID}.jsonl"
        there.parent.mkdir(parents=True)
        os.link(w / f"projects/-repos-app/{self.SID}.jsonl", there)
        write(w / "sessions/50.json", session(self.SID, cwd=str(self.folder), status="waiting", waitingFor="permission prompt"))
        with mock.patch.object(jump, "copy_to_clipboard", return_value=True), \
                mock.patch.object(jump, "jump_terminal", return_value=(True, "")) as up, \
                mock.patch.object(jump, "resume_chat", return_value=(True, "")) as again:
            answer = self.send()
        self.assertEqual((answer["ok"], answer["how"]), (True, "clipboard"))
        self.assertEqual(up.call_args[0][0]["sessionId"], self.SID)
        again.assert_not_called()   # (no second claude --resume of it)

    def test_a_former_background_session_reopens_without_options(self):
        # (it keeps its own: an option would start a copy of it)
        write(self.home / ".claude-work/jobs" / self.SID[:8] / "state.json", {"sessionId": self.SID, "state": "stopped"})
        words = shlex.split(self.send_to(self.SID)["command"].split("; ", 1)[1])
        self.assertEqual(words[-3:-1], ["--resume", self.SID])
        self.assertNotIn("--permission-mode", words)

    def test_the_chat_found_by_the_plans_name(self):
        transcript = self.home / f".claude-work/projects/-repos-app/{self.SID}.jsonl"
        profile, found = cs.plan_chat(cs.discover_profiles(self.home), "calm-red-owl")
        self.assertEqual((profile.key, found), (".claude-work", transcript))
        self.assertEqual(cs.plan_chat(cs.discover_profiles(self.home), "no-such-plan"), (None, None))
        self.assertEqual(self.send_to("-")["how"], "resumed")

    def send_to(self, chat):
        out = io.StringIO()
        with mock.patch.object(jump.Path, "home", return_value=self.home), \
                mock.patch.object(jump, "claude_in_terminal", return_value=str(self.bin / "claude")), \
                contextlib.redirect_stdout(out):
            jump.main(["--plan-feedback", "calm-red-owl", "--profile", ".claude-work", "--chat", chat, "--print-command"])
        return json.loads(out.getvalue())

    def test_nothing_to_send_and_a_chat_thats_gone(self):
        write(self.plan, "# Calm plan\n\n1. Do it\n2. Test it well\n")
        self.assertEqual(self.send(), {"ok": False, "message": "Nothing to send: the plan is as Claude wrote it, and there are no comments"})
        out = io.StringIO()
        with mock.patch.object(jump.Path, "home", return_value=self.home), contextlib.redirect_stdout(out):
            jump.main(["--plan-feedback", "calm-red-owl", "--chat", "a1b2c3d4-0000-4000-8000-000000000009"])
        self.assertIn("isn't there any more", json.loads(out.getvalue())["message"])

    def test_a_plan_you_changed_keeps_its_chat_and_says_so(self):
        def plan():
            return next(p for p in self.group(self.collect(with_tokens=False), "work")["plans"] if p["slug"] == "calm-red-owl")
        os.utime(self.plan, (self.now - 10, self.now - 10))  # (as Claude wrote it: before its chat's last line)
        self.assertEqual((plan()["chatId"], plan()["edited"]), (self.SID, False))
        # you changed it later: newer than its chat, still its chat (noted before)
        os.utime(self.plan, (self.now + 3600, self.now + 3600))
        self.assertEqual((plan()["chatId"], plan()["edited"]), (self.SID, True))


class MemoryTests(Fixture):
    """Each account's memories: Claude's notes in projects/<folder>/memory."""

    def test_an_accounts_memories_newest_first_with_their_folder(self):
        w = self.home / ".claude-work"
        folder = self.home / "repos/my_app.v2"
        folder.mkdir(parents=True)
        mem = w / "projects" / cs.mangle(str(folder)) / "memory"
        write(mem / "MEMORY.md", "- [Batch releases](batch-releases.md) — one tag for many features\n")
        write(mem / "batch-releases.md", '---\nname: batch-releases\ndescription: "Tag \\"many\\" features at once"\n'
                                         "metadata:\n  node_type: memory\n  type: feedback\n---\n\nThe user said so.\n")
        write(mem / "plain.md", "No header here.\n")
        os.utime(mem / "plain.md", (self.now - 3600, self.now - 3600))
        write(w / "projects/-gone-folder/memory/old.md", "---\nname: old\ntype: user\n---\n")
        os.utime(w / "projects/-gone-folder/memory/old.md", (self.now - 7200, self.now - 7200))
        g = self.group(self.collect(with_tokens=False), "work")
        self.assertEqual([m["name"] for m in g["memories"]], ["batch-releases", "plain", "old"])  # (no CLAUDE.md yet)
        # the account's own CLAUDE.md, a link to one file for all accounts: first
        write(self.home / "shared/CLAUDE.md", "# My instructions\n\nNo co-author lines.\n")
        (w / "CLAUDE.md").symlink_to(self.home / "shared/CLAUDE.md")
        g = self.group(self.collect(with_tokens=False), "work")
        self.assertEqual([m["name"] for m in g["memories"]], ["CLAUDE.md", "batch-releases", "plain", "old"])
        self.assertEqual((g["memories"][0]["type"], g["memories"][0]["path"]), ("account", str(w / "CLAUDE.md")))
        self.assertIn("shared with other accounts", g["memories"][0]["description"])
        self.assertEqual(g["instructions"], g["memories"][:1])
        # (--memories 0, as Plasma asks: none listed but its CLAUDE.md, its own line, hidden or not)
        cs.hide_item(self.cache, "memories", g["memories"][0]["key"])
        lean = self.group(self.collect(with_tokens=False, memories=0), "work")
        self.assertEqual(([m["name"] for m in lean["instructions"]], lean["memories"]), (["CLAUDE.md"], []))
        cs.show_hidden(self.cache, "memories")
        self.assertEqual(cs.memory_file(cs.discover_profiles(self.home), str(w / "CLAUDE.md")), w / "CLAUDE.md")
        self.assertIsNone(cs.memory_file(cs.discover_profiles(self.home), str(self.home / "shared/CLAUDE.md")))
        g["memories"].pop(0)
        first = g["memories"][0]
        self.assertEqual((first["description"], first["type"], first["folder"], first["profileDir"]),
                         ('Tag "many" features at once', "feedback", str(folder), ".claude-work"))
        self.assertEqual((g["memories"][1]["type"], first["folderShort"], first["folderGone"]), ("", "~/repos/my_app.v2", False))
        # a folder that isn't there any more: its name read back, and said so
        self.assertEqual({k: g["memories"][2][k] for k in ("folder", "folderShort", "folderGone")},
                         {"folder": "/gone/folder", "folderShort": "/gone/folder", "folderGone": True})
        # only memory files of a profile open
        profiles = cs.discover_profiles(self.home)
        self.assertEqual(cs.memory_file(profiles, str(mem / "plain.md")), (mem / "plain.md").resolve())
        self.assertIsNone(cs.memory_file(profiles, str(self.home / "notes.md")))
        with mock.patch.object(jump, "open_markdown", return_value=(True, "")) as shown, \
                mock.patch.object(jump, "edit_markdown", return_value=(True, "")) as edited:
            self.assertEqual(jump.open_memory(self.home, [], str(mem / "plain.md")), (True, ""))
            self.assertEqual(jump.open_memory(self.home, [], str(mem / "plain.md"), edit=True), (True, ""))
            self.assertFalse(jump.open_memory(self.home, [], "/etc/passwd")[0])
        self.assertEqual((shown.call_count, edited.call_count), (1, 1))

    def test_the_folder_of_a_renamed_repository_from_its_chats(self):
        # (renamed or moved: the folder a chat filed there ran in, as its transcript says)
        w = self.home / ".claude-work"
        old = self.home / "repos/talpy-den.old"
        project = w / "projects" / cs.mangle(str(old))
        write(project / "memory/notes.md", "---\nname: notes\ntype: project\n---\n")
        write(project / "0a1b2c3d.jsonl", lines({"type": "file-history-snapshot"},
                                                 prompt("hi", self.now - 60, cwd=str(old / "sub")),  # (after a cd)
                                                 prompt("hi", self.now - 60, cwd=str(old))))
        listed = next(m for m in self.group(self.collect(with_tokens=False), "work")["memories"] if m["name"] == "notes")
        self.assertEqual((listed["folder"], listed["folderShort"], listed["folderGone"]),
                         (str(old), "~/repos/talpy-den.old", True))
        # back where it was: found on disk
        old.mkdir(parents=True)
        listed = next(m for m in self.group(self.collect(with_tokens=False), "work")["memories"] if m["name"] == "notes")
        self.assertEqual((listed["folder"], listed["folderGone"]), (str(old), False))

    def test_memories_linked_from_a_renamed_folder_are_the_folders_there(self):
        # (renamed: one projects/<folder>'s memory/ linked to the other's, for its chats, either way round)
        w = self.home / ".claude-work"
        glob = Path.glob

        def listed(name):
            for backwards in (False, True):   # (whichever the folder lists first)
                with mock.patch.object(Path, "glob", lambda self, pattern: sorted(glob(self, pattern), reverse=backwards)):
                    yield [(m["folder"], m["folderGone"]) for m in self.group(self.collect(with_tokens=False), "work")["memories"]
                           if m["name"] == name]
        for n, linked_to_new in enumerate((True, False)):
            old, new = self.home / f"repos/old{n}", self.home / f"repos/new{n}"
            new.mkdir(parents=True)
            real, link = (new, old) if linked_to_new else (old, new)
            write(w / "projects" / cs.mangle(str(real)) / f"memory/notes{n}.md", f"---\nname: notes{n}\ntype: project\n---\n")
            (w / "projects" / cs.mangle(str(link))).mkdir(parents=True)
            (w / "projects" / cs.mangle(str(link)) / "memory").symlink_to(w / "projects" / cs.mangle(str(real)) / "memory")
            self.assertEqual(list(listed(f"notes{n}")), [[(str(new), False)]] * 2)
        # both folders there: the one it's really in
        (self.home / "repos/old1").mkdir()
        self.assertEqual(list(listed("notes1")), [[(str(self.home / "repos/old1"), False)]] * 2)

    def test_memories_open_with_projects_kept_elsewhere(self):
        # (projects/ linked to a folder on another disk: its memories are still the profile's)
        w = self.home / ".claude-work"
        (self.home / "data/projects").mkdir(parents=True)
        (w / "projects").symlink_to(self.home / "data/projects")
        write(w / "projects/-repos-app/memory/notes.md", "---\nname: notes\ntype: project\n---\n")
        listed = next(m for m in self.group(self.collect(with_tokens=False), "work")["memories"] if m["name"] == "notes")
        profiles = cs.discover_profiles(self.home)
        self.assertEqual(cs.memory_file(profiles, listed["path"]),
                         (self.home / "data/projects/-repos-app/memory/notes.md").resolve())
        self.assertIsNone(cs.memory_file(profiles, str(self.home / "data/notes.md")))


class OverlapTests(Fixture):
    def test_two_chats_with_a_process_that_changed_the_same_files(self):
        rows = [{"key": k, "name": k.upper(), "sessionId": k, "chatId": k, "profileDir": ".claude-work", "pid": pid,
                 "cwd": "/srv/app", "overlaps": None} for k, pid in (("a", 1), ("b", 2), ("c", None), ("d", 4))]
        rows[3]["chatId"] = "a"   # the same chat listed twice
        changed = {"a": {"/srv/app/x.py", "/srv/app/y.py"}, "b": {"/srv/app/y.py", "/home/me/z.md"},
                   "c": {"/srv/app/x.py"}, "d": {"/srv/app/x.py"}}
        cs.note_overlaps([{"sessions": rows}], changed, Path("/home/me"))
        a, b, c, d = rows
        self.assertEqual(a["overlaps"], [{"key": "b", "name": "B", "sessionId": "b", "chatId": "b", "profileDir": ".claude-work",
                                          "count": 1, "files": ["y.py"]}])
        self.assertEqual([o["key"] for o in b["overlaps"]], ["a"])
        self.assertEqual((c["overlaps"], d["overlaps"]), (None, None))  # no process; the same chat

    def test_a_chat_listed_twice_is_named_once(self):
        rows = [{"key": k, "name": k.upper(), "sessionId": k, "chatId": chat, "profileDir": ".claude-work", "pid": pid,
                 "cwd": "/srv/app", "overlaps": None} for k, chat, pid in (("a", "a", 1), ("d", "a", 4), ("b", "b", 2))]
        changed = {"a": {"/srv/app/y.py"}, "d": {"/srv/app/y.py"}, "b": {"/srv/app/y.py"}}
        cs.note_overlaps([{"sessions": rows}], changed, Path("/home/me"))
        a, d, b = rows
        self.assertEqual([o["key"] for o in b["overlaps"]], ["a"])
        self.assertEqual(([o["key"] for o in a["overlaps"]], [o["key"] for o in d["overlaps"]]), (["b"], ["b"]))

    def test_rows_get_them_from_what_the_chats_changed(self):
        w = self.home / ".claude-work"
        write(w / "sessions/50.json", session("one", cwd="/srv/app"))
        write(w / "sessions/51.json", session("two", cwd="/srv/app"))
        edit = lambda f: {"type": "assistant", "timestamp": iso(self.now - 30), "message": {"id": "m" + f, "role": "assistant",
                          "content": [{"type": "tool_use", "id": "t" + f, "name": "Edit", "input": {"file_path": f}}]}}
        write(w / "projects/-srv-app/one.jsonl", lines(prompt("go", self.now - 60), edit("/srv/app/x.py")))
        write(w / "projects/-srv-app/two.jsonl", lines(prompt("go", self.now - 60), edit("/srv/app/x.py")))
        rows = {s["sessionId"]: s for s in self.group(self.collect(with_tokens=False), "work")["sessions"]}
        self.assertEqual([(o["name"], o["files"]) for o in rows["one"]["overlaps"]], [(rows["two"]["name"], ["x.py"])])


class MarkdownTests(Fixture):
    def open(self, app, which=("okular", "xdg-open", "code"), name="run.md", folder=None):
        started = []
        if app:
            write(cs.state_dir(self.cache / "talpy-den") / "settings.json", {"at": 1, "by": "x", "values": {"markdownApp": app}})
        path = (folder or self.cache / "talpy-den/agent-runs") / name
        write(path, "# Run\n\nDone.\n")
        self.cache.mkdir(parents=True, exist_ok=True)
        with mock.patch.object(jump, "start_app", lambda args, cwd=None: started.append(args)), \
                mock.patch.object(jump.cs, "cache_dir", return_value=self.cache / "talpy-den"), \
                mock.patch.object(jump.shutil, "which", lambda n: f"/usr/bin/{n}" if n in which else None), \
                mock.patch.object(jump.cs, "vscode_app", return_value=("/usr/bin/code", "Code") if "code" in which else (None, None)), \
                mock.patch.object(jump, "status_extension_since", return_value=True), \
                mock.patch.object(jump, "runs_folder", return_value=self.cache):
            return jump.open_markdown(path, self.home), started

    def test_okular_where_installed_else_a_page_in_the_browser(self):
        run = self.cache / "talpy-den/agent-runs/run.md"
        self.assertEqual(self.open(None)[1], [["/usr/bin/okular", str(run)]])
        (ok, _), started = self.open(None, which=("xdg-open",))
        self.assertTrue(ok)
        self.assertEqual(started, [["/usr/bin/xdg-open", str(self.cache / "run.html")]])
        self.assertIn("<h1>Run</h1>", (self.cache / "run.html").read_text())
        self.assertEqual(self.open("okular", which=("xdg-open",))[1][0][1], str(self.cache / "run.html"))
        self.assertEqual(self.open("browser")[1][0][1], str(self.cache / "run.html"))
        self.assertEqual(self.open("default")[1], [["/usr/bin/xdg-open", str(run)]])
        self.assertTrue(self.open("vscode")[1][0][1].startswith("vscode://wzaielamri.talpy-den/markdown?path="))
        # a run is named after its task: all of it reaches the extension
        name = "Port C++ parser & tests (100%) (abcd1234).md"
        self.assertEqual(vscode_link_params(self.open("vscode", name=name)[1][0][1]), {"path": str(run.parent / name)})
        plans = self.home / ".claude-work/plans"
        self.assertEqual(vscode_link_params(self.open("vscode", name="calm-owl.md", folder=plans)[1][0][1]),
                         {"path": str(plans / "calm-owl.md")})
        # the extension's link shows only those: a memory or a CLAUDE.md opens in VS Code itself
        memory = self.home / ".claude-work/projects/-w-proj/memory"
        self.assertEqual(self.open("vscode", name="user.md", folder=memory)[1], [["/usr/bin/code", str(memory / "user.md")]])
        account = self.home / ".claude-work"
        self.assertEqual(self.open("vscode", name="CLAUDE.md", folder=account)[1], [["/usr/bin/code", str(account / "CLAUDE.md")]])
        self.assertEqual(self.open("auto", which=())[0][0], False)  # nothing to show it with

    def edit(self, app, defaults, which=("xdg-open", "gtk-launch", "code")):
        started = []
        write(cs.state_dir(self.cache / "talpy-den") / "settings.json", {"at": 1, "by": "x", "values": {"markdownApp": app or "auto"}})
        path = self.home / "plan.md"
        with mock.patch.object(jump, "start_app", lambda args, cwd=None: started.append(args)), \
                mock.patch.object(jump.cs, "cache_dir", return_value=self.cache / "talpy-den"), \
                mock.patch.object(jump.shutil, "which", lambda n: f"/usr/bin/{n}" if n in which else None), \
                mock.patch.object(jump.cs, "vscode_app", return_value=("/usr/bin/code", "Code") if "code" in which else (None, None)), \
                mock.patch.object(jump, "default_app", lambda mime: defaults.get(mime, "")):
            return jump.edit_markdown(path, self.home), started

    def test_a_plan_opens_itself_in_a_text_editor_to_change_it(self):
        md = str(self.home / "plan.md")
        kwrite = {"text/markdown": "org.kde.kwrite.desktop", "text/plain": "org.kde.kwrite.desktop"}
        self.assertEqual(self.edit(None, kwrite)[1], [["/usr/bin/xdg-open", md]])  # your app for Markdown
        self.assertEqual(self.edit("vscode", kwrite)[1], [["/usr/bin/code", md]])  # VS Code, picked for Markdown
        # Okular only shows Markdown: your app for text files instead
        okular = {"text/markdown": "okularApplication_md.desktop", "text/plain": "org.kde.kate.desktop"}
        self.assertEqual(self.edit(None, okular)[1], [["/usr/bin/gtk-launch", "org.kde.kate.desktop", md]])
        self.assertEqual(self.edit(None, okular, which=("xdg-open",))[1], [["/usr/bin/xdg-open", md]])
        self.assertEqual(self.edit(None, kwrite, which=())[0][0], False)
        # a plan by its name; an SSH host's file in VS Code
        write(self.home / ".claude-work/plans/calm-red-owl.md", "# Calm plan\n")
        with mock.patch.object(jump, "edit_markdown", return_value=(True, "")) as edit:
            self.assertEqual(jump.edit_plan(self.home, [], "calm-red-owl", ".claude-work"),
                             (True, "Opened the plan's file ~/.claude-work/plans/calm-red-owl.md"))
        edit.assert_called_once_with(self.home / ".claude-work/plans/calm-red-owl.md", self.home)
        self.assertEqual(jump.edit_plan(self.home, [], "gone-plan-here", None), (False, "That plan isn't there any more"))
        started = []
        with mock.patch.object(jump, "start_app", lambda args, cwd=None: started.append(args)), \
                mock.patch.object(jump.cs, "vscode_app", return_value=("/usr/bin/code", "Code")):
            self.assertTrue(jump.edit_remote_file("lab", "/home/u/.claude/plans/a b.md")[0])
            with self.assertRaises(ValueError):
                jump.edit_remote_file("-oProxyCommand=x", "/p.md")
        self.assertEqual(started, [["/usr/bin/code", "--file-uri", "vscode-remote://ssh-remote+lab/home/u/.claude/plans/a%20b.md"]])

    def test_the_page_loads_nothing_and_runs_nothing(self):
        import markdown_page as mp
        page = mp.page("# T\n\n<script>alert(1)</script> [x](javascript:alert(1)) [y](https://example.com/a?b=1&c=2)\n\n"
                       "![pic](https://example.com/p.png)\n\n| a | b |\n|---|---|\n| 1 | `|` |\n\n- [x] done\n- [ ] todo\n"
                       "  1. nested\n\n```py\n<b>code</b>\n```\n")
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn('href="javascript', page)
        self.assertIn('<a href="https://example.com/a?b=1&amp;c=2" rel="noreferrer noopener">y</a>', page)
        self.assertNotIn("<img", page)
        self.assertIn("[image: pic]", page)
        self.assertIn("default-src 'none'", page)
        self.assertIn("<th>a</th>", page)
        self.assertIn("☑ done", page)
        self.assertIn("<ol>", page)
        self.assertIn("&lt;b&gt;code&lt;/b&gt;", page)
        self.assertIn("<ol><li>One</li>", mp.body("Steps:\n1. One\n2. Two"))
        # a step's code block, fenced under it (as Claude's plans often have it)
        self.assertEqual(mp.body("1. Run:\n   ```bash\n   npm test\n     --watch\n   ```\n2. Next"),
                         '<ol><li>Run:<pre><code class="language-bash">npm test\n  --watch</code></pre></li><li>Next</li></ol>')

    def test_the_page_reads_as_markdown_means(self):
        import markdown_page as mp
        # bold and italics never reach into a link's address
        self.assertEqual(mp.body("See [the *package*](https://e.com/pkg/__init__.py)"),
                         '<p>See <a href="https://e.com/pkg/__init__.py" rel="noreferrer noopener">the <em>package</em></a></p>')
        self.assertEqual(mp.body("[x](https://e.com/_a) b_c_"),
                         '<p><a href="https://e.com/_a" rel="noreferrer noopener">x</a> b_c_</p>')
        self.assertEqual(mp.body("**[x](https://e.com)** and [y](notes_a_b.md)"),
                         '<p><strong><a href="https://e.com" rel="noreferrer noopener">x</a></strong> and y (notes_a_b.md)</p>')
        # a fence with more after its language, and one inside another
        page = mp.body('Intro\n\n```python title="setup.py"\nprint(1)\n```\n\n## Next step\n\nText after.')
        self.assertIn('<pre><code class="language-python">print(1)</code></pre>', page)
        self.assertIn("<h2>Next step</h2>", page)
        self.assertIn("<pre><code>```py\nx\n</code></pre>", mp.body("````\n```py\nx\n\n````"))
        # C# and F# keep their #; a closing run goes
        self.assertEqual(mp.body("## Port the parser to C#"), "<h2>Port the parser to C#</h2>")
        self.assertEqual(mp.body("## Done ##"), "<h2>Done</h2>")
        self.assertIn("<title>Notes on F#</title>", mp.page("# Notes on F#"))


class HideTests(Fixture):
    """Hide: a chat, a plan, a memory or a project left out of its list (jump.py --hide KIND ID)."""

    def setUp(self):
        super().setUp()
        os.environ["XDG_CACHE_HOME"] = str(self.cache.parent)
        self.addCleanup(os.environ.pop, "XDG_CACHE_HOME", None)
        self.cache = cs.cache_dir(self.home)

    def run_jump(self, *args):
        out = io.StringIO()
        with mock.patch.object(Path, "home", return_value=self.home), contextlib.redirect_stdout(out):
            jump.main(list(args))
        return json.loads(out.getvalue())

    def test_plans_memories_and_projects_hide_and_come_back(self):
        w = self.home / ".claude-work"
        for i, slug in enumerate(["old-plan", "new-plan"]):
            write(w / f"plans/{slug}.md", f"# {slug}\n")
            os.utime(w / f"plans/{slug}.md", (self.now - 1000 + i, self.now - 1000 + i))
        mem = w / "projects/-gone-folder/memory"
        write(mem / "a.md", "---\nname: a\n---\n")
        write(mem / "b.md", "---\nname: b\n---\n")
        r = self.collect(with_tokens=False, plans=1)
        self.assertEqual((r["hiddenPlans"], r["hiddenMemories"], r["hiddenProjects"]), (0, 0, 0))
        key = next(m["key"] for m in self.group(r, "work")["memories"] if m["name"] == "a")
        self.assertEqual(self.run_jump("--hide", "plans", "new-plan")["message"], "Hid this plan")
        self.assertEqual(self.run_jump("--hide", "memories", key)["message"], "Hid this memory")
        self.assertEqual(self.run_jump("--hide", "projects", "/r/app")["message"], "Hid this project")
        self.assertFalse(self.run_jump("--hide", "plans", "not a slug")["ok"])
        self.assertFalse(self.run_jump("--hide", "folders", "/r/app")["ok"])
        r = self.collect(with_tokens=False, plans=1)
        work = self.group(r, "work")
        # (the next one moves up: the list keeps its length)
        self.assertEqual([p["slug"] for p in work["plans"]], ["old-plan"])
        self.assertEqual([m["name"] for m in work["memories"]], ["b"])
        self.assertEqual((r["hiddenPlans"], r["hiddenMemories"], r["hiddenProjects"]), (1, 1, 1))
        self.assertEqual(self.run_jump("--show-hidden", "plans")["message"], "Showing 1 hidden plan again")
        self.assertEqual(self.run_jump("--show-hidden", "plans")["message"], "No plan was hidden")
        self.assertEqual(self.run_jump("--show-hidden", "memories")["message"], "Showing 1 hidden memory again")
        self.assertEqual(self.run_jump("--show-hidden", "projects")["message"], "Showing 1 hidden project again")
        r = self.collect(with_tokens=False, plans=1)
        self.assertEqual([p["slug"] for p in self.group(r, "work")["plans"]], ["new-plan"])
        self.assertEqual((r["hiddenPlans"], r["hiddenMemories"], r["hiddenProjects"]), (0, 0, 0))

    def test_chats_hide_as_dismissed_ones_do(self):
        self.assertEqual(self.run_jump("--hide", "chats", "bgdone")["message"], "Hid this chat")
        self.assertIn("bgdone", cs.load_dismissed(self.cache))
        self.assertEqual(self.collect(with_tokens=False)["dismissed"], 1)
        self.assertEqual(self.run_jump("--dismiss", "dead")["message"], "Hid this chat")
        self.assertEqual(self.run_jump("--show-hidden", "chats")["message"], "Showing 2 hidden chats again")
        self.assertEqual(self.run_jump("--undismiss-all")["message"], "No chat was hidden")


class DeleteTests(Fixture):
    """Delete: a chat, a plan or a memory to the Trash, from every account that has it."""

    def setUp(self):
        super().setUp()
        root = Path(self.tmp.name)
        saved = {k: os.environ.get(k) for k in ("XDG_CACHE_HOME", "XDG_DATA_HOME")}
        self.addCleanup(lambda: [os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
                                 for k, v in saved.items()])
        os.environ["XDG_CACHE_HOME"], os.environ["XDG_DATA_HOME"] = str(self.cache.parent), str(root / "data")
        self.cache, self.trash = cs.cache_dir(self.home), root / "data/Trash"
        self.w, self.p = self.home / ".claude-work", self.home / ".claude-personal"

    def delete(self, kind, item, profile=None, describe=False):
        ok, message, more = jump.delete_item(self.home, [], kind, item, profile, describe)
        return dict(more, ok=ok, message=message)

    def trashed(self):
        return sorted(f.name for f in (self.trash / "files").iterdir()) if (self.trash / "files").is_dir() else []

    def test_a_shared_chat_goes_from_every_account_with_its_folders(self):
        t = self.now - 600
        write(self.w / "projects/-p/chat9.jsonl", lines({"type": "custom-title", "customTitle": "Fix the build"},
                                                         prompt("fix it", t), reply("Fixed.", t + 5)))
        write(self.w / "projects/-p/chat9/subagents/agent-1.jsonl", "{}\n")
        write(self.w / "file-history/chat9/abc@v1", "old\n")
        write(self.w / "projects/-p/other.jsonl", lines(prompt("keep me", t)))
        profiles = cs.discover_profiles(self.home)
        root = sharing.store_root(self.home)
        self.assertTrue(sharing.share(profiles, "chat9", [sharing.named(profiles, ".claude-personal")], root)[0])
        self.assertTrue((self.p / "projects/-p/chat9").is_symlink())
        # what the stars, Hide, Keep going and the queue had of it goes too
        cs.change_stars(self.cache, "chats", "chat9")
        cs.change_dismissed(self.cache, add="chat9")
        cs.keep_chat(self.cache, ".claude-work", "chat9")
        cs.change_queue(self.cache, add=cs.queue_entry(".claude-work", "/p", "", 1, chat="chat9"))
        asked = self.delete("chat", "chat9", ".claude-personal", describe=True)
        self.assertTrue(asked["ok"], asked)
        self.assertEqual(sorted(asked["accounts"]), ["personal", "work"])
        self.assertEqual(asked["question"], f"Delete “Fix the build” on {' and '.join(asked['accounts'])}? It goes to the "
                                            "Trash with its subagents and checkpoints; the Recap keeps its numbers.")
        self.assertEqual((asked["message"], asked["name"], asked["open"]), (asked["question"], "Fix the build", ""))
        self.assertEqual(self.trashed(), [])  # (asking deletes nothing)
        self.assertEqual(self.delete("chat", "chat9")["message"], "Moved to the Trash")
        for prof in (self.w, self.p):
            for part in ("projects/-p/chat9.jsonl", "projects/-p/chat9", "file-history/chat9"):
                self.assertFalse(os.path.lexists(prof / part), prof / part)
        self.assertFalse(os.path.lexists(root / "-p/chat9"))
        self.assertTrue((self.w / "projects/-p/other.jsonl").is_file())
        # in the Trash: each account's links and the store's folders, none lost
        names = self.trashed()
        self.assertEqual(names.count("chat9.jsonl") + sum(n.startswith("chat9.jsonl.") for n in names), 3)
        self.assertIn("subagents", {f.name for d in (self.trash / "files").iterdir() if d.is_dir() and not d.is_symlink()
                                    for f in d.iterdir()})
        self.assertEqual(len(list((self.trash / "info").iterdir())), len(names))
        self.assertEqual((cs.load_stars(self.cache)["chats"], cs.load_dismissed(self.cache), cs.load_keep(self.cache)["chats"],
                          cs.load_queue(self.cache)), ([], {}, [], []))
        self.assertEqual(self.delete("chat", "chat9")["message"], "That chat isn't there any more")

    def test_a_finished_background_chat_goes_with_its_job_folder(self):
        # Delete… of a finished background chat left jobs/<id[:8]>/, so its
        # row stayed as Done · Not open (2026-11-01)
        sid = "aaaaaaaa-1111-4222-8333-444444444444"
        t = self.now - 600
        write(self.w / f"projects/-p/{sid}.jsonl", lines(prompt("fix it", t), reply("Fixed.", t + 5)))
        job = {"sessionId": sid, "state": "done", "tempo": "idle", "cwd": "/p", "name": "Fix it",
               "createdAt": iso(t), "updatedAt": iso(t + 5), "linkScanPath": str(self.w / f"projects/-p/{sid}.jsonl")}
        write(self.w / f"jobs/{sid[:8]}/state.json", job)
        write(self.w / "jobs/bbbbbbbb/state.json", dict(job, sessionId="bbbbbbbb-0000-4000-8000-000000000000"))
        listed = lambda: [s["sessionId"] for g in self.collect(with_tokens=False)["groups"] for s in g["sessions"]]
        self.assertIn(sid, listed())
        # while it isn't finished, it isn't deleted
        write(self.w / f"jobs/{sid[:8]}/state.json", dict(job, state="working", tempo="active"))
        asked = self.delete("chat", sid, describe=True)
        self.assertEqual((asked["ok"], asked["message"]), (False, "It runs in the background on work. Stop it first."))
        self.assertFalse(self.delete("chat", sid)["ok"])
        write(self.w / f"jobs/{sid[:8]}/state.json", job)
        self.assertEqual(self.delete("chat", sid)["message"], "Moved to the Trash")
        self.assertFalse(os.path.lexists(self.w / f"jobs/{sid[:8]}"))
        self.assertTrue((self.w / "jobs/bbbbbbbb/state.json").is_file())
        self.assertIn(sid[:8], self.trashed())  # (restorable with it)
        self.assertNotIn(sid, listed())
        # a finished job whose chat is gone (deleted before) isn't listed either
        write(self.w / f"jobs/{sid[:8]}/state.json", job)
        self.assertNotIn(sid, listed())

    def test_a_chat_open_in_a_session_stays(self):
        write(self.w / "projects/-tmp-proj-busy/busy.jsonl", lines(prompt("go", self.now - 60)))
        asked = self.delete("chat", "busy", describe=True)
        self.assertEqual((asked["ok"], asked["open"], asked["message"]),
                         (False, "work", "It's open on work. Exit it there first."))
        self.assertIn("“go”", asked["question"])
        self.assertEqual(self.delete("chat", "busy"), {"ok": False, "message": "It's open on work. Exit it there first."})
        self.assertTrue((self.w / "projects/-tmp-proj-busy/busy.jsonl").is_file())
        self.assertEqual(self.trashed(), [])

    def test_a_plan_from_every_account_its_linked_into(self):
        write(self.w / "plans/calm-red-owl.md", "# Calm plan\n")
        (self.p / "plans").mkdir(parents=True)
        os.link(self.w / "plans/calm-red-owl.md", self.p / "plans/calm-red-owl.md")
        write(self.home / ".claude/plans/calm-red-owl.md", "# Another plan of that name\n")
        cs.change_stars(self.cache, "plans", "calm-red-owl")
        cs.hide_item(self.cache, "plans", "calm-red-owl")
        self.assertIn("say which account", self.delete("plan", "calm-red-owl")["message"])
        asked = self.delete("plan", "calm-red-owl", ".claude-work", describe=True)
        self.assertEqual(asked["question"], f"Delete the plan “Calm plan” on {' and '.join(asked['accounts'])}? It goes to the Trash.")
        self.assertEqual(sorted(asked["accounts"]), ["personal", "work"])
        self.assertEqual(self.delete("plan", "calm-red-owl", ".claude-work")["message"], "Moved to the Trash")
        self.assertFalse((self.w / "plans/calm-red-owl.md").exists() or (self.p / "plans/calm-red-owl.md").exists())
        self.assertEqual((self.home / ".claude/plans/calm-red-owl.md").read_text(), "# Another plan of that name\n")
        self.assertEqual(self.trashed(), ["calm-red-owl.md", "calm-red-owl.md.2"])
        self.assertEqual((cs.load_stars(self.cache)["plans"], cs.load_hidden(self.cache)["plans"]), ([], {}))

    def test_a_memory_and_only_its_line_in_memory_md(self):
        folder = self.home / "repos/app"
        folder.mkdir(parents=True)
        mem = self.w / "projects" / cs.mangle(str(folder)) / "memory"
        index = (b"# Memories\r\n- [Batch releases](batch-releases.md) \xe2\x80\x94 tag at once\r\n"
                 b"- [Other](other.md) \xe2\x80\x94 stays\n- [Batch again](./batch-releases.md)\n  not a link: batch-releases.md")
        write(mem / "MEMORY.md", "")
        (mem / "MEMORY.md").write_bytes(index)
        (mem / "MEMORY.md").chmod(0o640)
        write(mem / "batch-releases.md", "---\nname: Batch releases\ntype: feedback\n---\nOne tag.\n")
        write(mem / "other.md", "---\nname: other\n---\n")
        key = f".claude-work/{mem.parent.name}/batch-releases/memory"
        cs.hide_item(self.cache, "memories", key)
        asked = self.delete("memory", key, describe=True)
        self.assertEqual(asked["question"], "Delete the memory “Batch releases”? It goes to the Trash, and Claude stops "
                                            "reading it in new chats in ~/repos/app.")
        self.assertEqual(self.delete("memory", key)["message"], "Moved to the Trash")
        self.assertFalse((mem / "batch-releases.md").exists())
        self.assertEqual((mem / "MEMORY.md").read_bytes(),
                         b"# Memories\r\n- [Other](other.md) \xe2\x80\x94 stays\n  not a link: batch-releases.md")
        self.assertEqual(stat.S_IMODE((mem / "MEMORY.md").stat().st_mode), 0o640)
        self.assertEqual(self.trashed(), ["batch-releases.md"])
        self.assertEqual(cs.load_hidden(self.cache)["memories"], {})
        # the account's CLAUDE.md isn't deleted this way
        write(self.w / "CLAUDE.md", "# Mine\n")
        self.assertFalse(self.delete("memory", ".claude-work/CLAUDE.md/memory")["ok"])
        self.assertFalse(self.delete("memory", ".claude-work/../memory")["ok"])
        self.assertTrue((self.w / "CLAUDE.md").is_file())


class StopKeepOffTests(Fixture):
    """Stop and turn Keep going off (jump.py --stop ID --and-keep-off CHAT_ID): both, or neither."""

    def test_stopped_and_let_go_under_the_lock(self):
        cache = Path(self.tmp.name) / "cache/talpy-den"
        saved = os.environ.get("XDG_CACHE_HOME")
        os.environ["XDG_CACHE_HOME"] = str(cache.parent)
        self.addCleanup(lambda: os.environ.pop("XDG_CACHE_HOME") if saved is None else os.environ.__setitem__("XDG_CACHE_HOME", saved))
        cs.keep_chat(cache, ".claude-work", "kept1")
        looked = []

        def stopped(home, extra, session_id, profile_dir=None, busy=False):
            # (meanwhile the copy that looks after kept chats can't take the lock: it skips)
            looked.append(cs.change_keep(cache, lambda data: True, wait=False))
            return True, "Stopped"
        with mock.patch.object(jump, "stop", side_effect=stopped):
            self.assertEqual(jump.stop_keep_off(self.home, [], "sess1", "kept1"),
                             (True, "Stopped. It won't go on by itself any more"))
        self.assertEqual((looked, cs.load_keep(cache)["chats"]), ([False], []))
        # not stopped: Keep going stays on
        cs.keep_chat(cache, ".claude-work", "kept1")
        with mock.patch.object(jump, "stop", return_value=(False, "That chat isn't running any more")):
            self.assertEqual(jump.stop_keep_off(self.home, [], "sess1", "kept1"), (False, "That chat isn't running any more"))
        self.assertEqual([k["chat"] for k in cs.load_keep(cache)["chats"]], ["kept1"])
        with self.assertRaises(SystemExit):
            jump.main(["--keep-off", "kept1", "--and-keep-off", "kept1"])
