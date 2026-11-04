import importlib.util
import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.dont_write_bytecode = True  # keep __pycache__ out of the plasmoid package
ROOT = Path(__file__).resolve().parent.parent
CODE = ROOT / "package/contents/code"
sys.path.insert(0, str(CODE))
spec = importlib.util.spec_from_file_location("week", CODE / "week.py")
week = importlib.util.module_from_spec(spec)
spec.loader.exec_module(week)
cs = week.cs

MIN = 60_000


def line(e):
    return json.dumps(e, separators=(",", ":")) + "\n"  # (as Claude Code writes them)


def iso(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat().replace("+00:00", "Z")


class Transcript:
    """Lines of a made-up transcript, the way Claude Code writes them."""

    def __init__(self, folder="/w/app"):
        self.lines, self.folder, self.n = [], folder, 0

    def uuid(self):
        self.n += 1
        return "%08d-0000-4000-8000-%012d" % (id(self) % 10 ** 8, self.n)

    def add(self, e):
        e.setdefault("uuid", self.uuid())
        e.setdefault("cwd", self.folder)
        self.lines.append(e)
        return self

    def prompt(self, ms, text="do it"):
        return self.add({"type": "user", "timestamp": iso(ms), "origin": {"kind": "human"},
                         "message": {"role": "user", "content": text}})

    def reply(self, ms, mid, output=100, model="claude-opus-5-5", read=1000, write=0, inp=5, tools=(), effort=None,
              hour_writes=False, **extra):
        usage = {"input_tokens": inp, "output_tokens": output, "cache_read_input_tokens": read,
                 "cache_creation_input_tokens": write}
        if hour_writes:
            usage["cache_creation"] = {"ephemeral_1h_input_tokens": write, "ephemeral_5m_input_tokens": 0}
        content = [{"type": "tool_use", "id": tid, "name": name, "input": inp_}
                   for tid, name, inp_ in tools] or [{"type": "text", "text": "ok"}]
        e = {"type": "assistant", "timestamp": iso(ms), "requestId": "req_" + mid,
             "message": {"id": "msg_" + mid, "model": model, "role": "assistant", "content": content, "usage": usage}}
        if effort:
            e["effort"] = effort
        e.update(extra)
        return self.add(e)

    def result(self, ms, tool_id, source="config", text="done", reason=None, decision="accept"):
        pd = {"decision": decision, "source": source}
        if reason:
            pd["reasonCode"] = reason
        return self.add({"type": "user", "timestamp": iso(ms),
                         "message": {"role": "user", "content": [{"tool_use_id": tool_id, "type": "tool_result",
                                                                  "content": text}]},
                         "toolUseResult": {"stdout": text}, "permissionDecision": pd})

    def compacted(self, ms):
        return self.add({"type": "system", "subtype": "compact_boundary", "timestamp": iso(ms)})

    def duration(self, ms, worked):
        return self.add({"type": "system", "subtype": "turn_duration", "durationMs": worked, "timestamp": iso(ms)})

    def interrupted(self, ms):
        return self.add({"type": "user", "timestamp": iso(ms),
                         "message": {"role": "user", "content": [{"type": "text", "text": "[Request interrupted by user]"}]}})

    def limit(self, ms):
        return self.add({"type": "assistant", "timestamp": iso(ms), "isApiErrorMessage": True,
                         "message": {"id": "msg_err%d" % ms, "model": "<synthetic>", "role": "assistant",
                                     "content": [{"type": "text", "text": "You've hit your session limit · resets 7pm"}],
                                     "usage": {"input_tokens": 0, "output_tokens": 0}}})

    def title(self, text):
        return self.add({"type": "custom-title", "customTitle": text})

    def text(self):
        return "".join(line(e) for e in self.lines)


class Home(unittest.TestCase):
    """A made-up home: ~/.claude-work (a Team account) and ~/.claude-personal (a Pro one)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "home"
        self.cache_root = Path(self.tmp.name) / "cache"
        for name, account in (("work", "acct-team"), ("personal", "acct-pro")):
            d = self.home / (".claude-" + name)
            (d / "projects/-w").mkdir(parents=True)
            (d / ".profile-name").write_text(name)
            (d / ".claude.json").write_text(json.dumps({"oauthAccount": {"accountUuid": account}}))
        # a fixed day, in the middle of the week shown: 7 days back from "now"
        self.now = int(datetime(2026, 10, 24, 18, 0).timestamp() * 1000)
        self.t0 = int(datetime(2026, 10, 24, 10, 0).timestamp() * 1000)

    def write(self, transcript, chat="chat-a", profile="work", sub=None):
        path = self.home / (".claude-" + profile) / "projects/-w" / (chat + ".jsonl")
        if sub:
            path = path.parent / chat / "subagents" / (sub + ".jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(transcript.text())
        return path

    def profiles(self):
        return cs.discover_profiles(self.home)

    def scan(self, cache=None):
        cache = cache if cache is not None else {"files": {}}
        week.scan(self.profiles(), cache, self.now)
        return cache

    def chats(self, cache=None, days=14):
        cache = self.scan(cache)
        return week.chats_between(cache, self.profiles(), self.now - days * week.DAY_MS, self.now + week.DAY_MS, self.home)

    def recap(self, account="", back=0, extra=(), days=14, usage=None, added=(), span="week"):
        cache = self.scan()
        chats = week.chats_between(cache, self.profiles(), self.now - days * week.DAY_MS, self.now + week.DAY_MS, self.home)
        _, accounts = week.account_ids(self.profiles())
        return week.recap([{"host": "", "chats": chats, "accounts": accounts}, *extra], back, account, self.now,
                          self.home, usage, added, span, week.first_activity(cache))


class PriceTests(unittest.TestCase):
    def test_the_same_cost_as_claude_code(self):
        # a chat whose /usage said $5.678759 (its cost-state record)
        opus = week.request_cost("claude-opus-5-5", [88, 78252, 9536740, 0, 275735, 0, 1])
        haiku = week.request_cost("claude-haiku-5-5", [1289, 21, 0, 0, 0, 0, 1])
        self.assertAlmostEqual(opus + haiku, 5.6787594, places=6)

    def test_what_changes_a_price(self):
        mtok = [1_000_000, 0, 0, 0, 0, 0, 1]
        self.assertAlmostEqual(week.request_cost("claude-opus-5-5|f", mtok), 8)  # fast mode
        self.assertAlmostEqual(week.request_cost("claude-opus-5-5|f", [0, 0, 1_000_000, 0, 0, 0, 1]), 0.4)
        self.assertAlmostEqual(week.request_cost("claude-haiku-5-5|l", mtok), 0.5)  # a prompt over 100k tokens
        self.assertAlmostEqual(week.request_cost("claude-opus-5-5|u", mtok), 4.4)  # US-only inference
        self.assertAlmostEqual(week.request_cost("claude-sonnet-5-5", [0, 0, 0, 1_000_000, 0, 3, 1]), 2.53)
        self.assertEqual(week.price_key("claude-opus-5-5", {"speed": "fast"}, 10), "claude-opus-5-5|f")
        self.assertEqual(week.price_key("claude-haiku-5-5", {}, 150_000), "claude-haiku-5-5|l")

    def test_a_model_the_list_doesnt_know(self):
        self.assertEqual(week.price_model("claude-sonnet-4-5-20250929"), ("sonnet-4-5", False))
        self.assertEqual(week.price_model("claude-opus-5-5[1m]"), ("opus-5-5", False))
        self.assertEqual(week.price_model("claude-opus-9-9"), ("opus-5-5", True))  # the newest of its family
        self.assertEqual(week.price_model("gpt-9"), (None, True))
        self.assertEqual(week.request_cost("gpt-9", [1, 1, 1, 1, 1, 1, 1]), 0)

    def test_weights_as_claude_codes_usage(self):
        self.assertEqual(week.usage_weight("claude-opus-5-5", 1, 1, 1, 1), (1 + 10 + 12.5 + 50) * 5)
        self.assertEqual(week.usage_weight("claude-sonnet-5-5", 0, 0, 10, 0), 30)
        self.assertEqual(week.usage_weight("claude-haiku-5-5", 0, 0, 10, 0), 10)
        self.assertEqual(week.usage_weight("claude-fable-5-1", 0, 0, 10, 0), 100)


class TurnTests(Home):
    """A turn: Claude's own count of its work, and where the rest of it went."""

    def turns(self, transcript, chat="chat-a"):
        self.write(transcript, chat)
        return [t[:4] for t in self.chats()[chat]["turns"]]  # (without their tokens)

    def test_waiting_for_your_permission_isnt_work(self):
        t0 = self.t0
        tr = (Transcript().prompt(t0).reply(t0 + 5000, "a", tools=[("T1", "Edit", {})])
              .result(t0 + 305_000, "T1", source="user_temporary").reply(t0 + 310_000, "b").duration(t0 + 320_000, 20_000))
        self.assertEqual(self.turns(tr), [[t0, t0 + 320_000, 20_000, [[t0 + 5000, t0 + 305_000, "y"]]]])

    def test_a_tool_allowed_by_your_settings_is_work(self):
        t0 = self.t0
        tr = (Transcript().prompt(t0).reply(t0 + 5000, "a", tools=[("T1", "Bash", {"command": "make"})])
              .result(t0 + 305_000, "T1").reply(t0 + 310_000, "b").duration(t0 + 320_000, 320_000))
        self.assertEqual(self.turns(tr), [[t0, t0 + 320_000, 320_000, []]])

    def test_a_question_waits_for_you(self):
        t0 = self.t0
        tr = (Transcript().prompt(t0).reply(t0 + 5000, "a", tools=[("Q", "AskUserQuestion", {})])
              .result(t0 + 125_000, "Q").reply(t0 + 130_000, "b"))  # (no turn_duration: VS Code's)
        self.assertEqual(self.turns(tr), [[t0, t0 + 130_000, 10_000, [[t0 + 5000, t0 + 125_000, "y"]]]])

    def test_without_turn_records_a_turn_ends_at_the_next_prompt(self):
        t0 = self.t0
        tr = Transcript().prompt(t0).reply(t0 + 60_000, "a").prompt(t0 + 600_000).reply(t0 + 660_000, "b")
        self.assertEqual(self.turns(tr), [[t0, t0 + 60_000, 60_000, []], [t0 + 600_000, t0 + 660_000, 60_000, []]])

    def test_a_sleep_is_not_work(self):
        t0 = self.t0
        tr = (Transcript().prompt(t0).reply(t0 + 10_000, "a").reply(t0 + 2 * 3600_000, "b")
              .duration(t0 + 2 * 3600_000 + 10_000, 2 * 3600_000 + 10_000))  # (Claude Code counted it)
        (turn,) = self.turns(tr)
        self.assertEqual(turn[2], 20_000)
        self.assertEqual(turn[3], [[t0 + 10_000, t0 + 2 * 3600_000, "p"]])

    def test_a_prompt_sent_while_claude_works_is_the_same_turn(self):
        t0 = self.t0
        tr = (Transcript().prompt(t0).reply(t0 + 5000, "a").duration(t0 + 6000, 6000)
              .prompt(t0 + 60_000).reply(t0 + 70_000, "b", tools=[("T", "Bash", {})]).prompt(t0 + 80_000, "and this")
              .result(t0 + 100_000, "T").reply(t0 + 110_000, "c").duration(t0 + 120_000, 60_000))
        self.write(tr)
        chat = self.chats()["chat-a"]
        self.assertEqual([t[:3] for t in chat["turns"]], [[t0, t0 + 6000, 6000], [t0 + 60_000, t0 + 120_000, 60_000]])
        self.assertEqual(len(chat["prompts"]), 3)

    def test_a_stopped_turn_ends_where_you_stopped_it(self):
        t0 = self.t0
        tr = (Transcript().prompt(t0).reply(t0 + 5000, "a").duration(t0 + 6000, 6000)
              .prompt(t0 + 60_000).reply(t0 + 70_000, "b").interrupted(t0 + 80_000).prompt(t0 + 100_000)
              .reply(t0 + 110_000, "c").duration(t0 + 120_000, 20_000))
        self.assertEqual([t[:3] for t in self.turns(tr)],
                         [[t0, t0 + 6000, 6000], [t0 + 60_000, t0 + 80_000, 20_000], [t0 + 100_000, t0 + 120_000, 20_000]])

    def test_the_turn_going_on(self):
        t0 = self.t0
        tr = (Transcript().prompt(t0).reply(t0 + 5000, "a", tools=[("T", "Edit", {})])
              .result(t0 + 65_000, "T", source="user_permanent").reply(t0 + 90_000, "b"))
        self.assertEqual(self.turns(tr), [[t0, t0 + 90_000, 30_000, [[t0 + 5000, t0 + 65_000, "y"]]]])

    def test_a_turn_carries_its_tokens(self):
        t0 = self.t0
        tr = (Transcript().prompt(t0).reply(t0 + 1000, "a", output=100, read=1000).reply(t0 + 2000, "b", output=50, read=0)
              .duration(t0 + 3000, 3000).prompt(t0 + 60_000).reply(t0 + 61_000, "c", model="claude-haiku-5-5"))
        self.write(tr)
        first, second = self.chats()["chat-a"]["turns"]
        self.assertEqual(first[4], {"claude-opus-5-5": [10, 150, 1000, 0, 0, 0]})
        self.assertEqual(second[4], {"claude-haiku-5-5": [5, 100, 1000, 0, 0, 0]})  # (the turn going on)


class UsageTests(Home):
    """Each reply's usage, counted once."""

    def test_a_reply_in_blocks_over_two_scans(self):
        t0 = self.t0
        tr = Transcript().prompt(t0).reply(t0 + 1000, "a", output=10)
        path = self.write(tr)
        cache = self.scan()
        with open(path, "a") as f:  # its next blocks, with the final count
            f.write(line(dict(tr.lines[-1], uuid="x2", timestamp=iso(t0 + 2000))))
            last = json.loads(json.dumps(tr.lines[-1]))
            last["message"]["usage"]["output_tokens"] = 50
            f.write(line(dict(last, uuid="x3", timestamp=iso(t0 + 3000))))
        chat = self.chats(cache)["chat-a"]
        (agg,) = chat["hours"].values()
        self.assertEqual(agg["t"], {"claude-opus-5-5": [5, 50, 1000, 0, 0, 0, 1]})
        self.assertEqual(agg["w"][week.W_ALL], week.usage_weight("claude-opus-5-5", 5, 50, 1000, 0))

    def test_copies_count_once(self):
        t0 = self.t0
        original = Transcript().title("original").prompt(t0).reply(t0 + 1000, "a").duration(t0 + 2000, 2000)
        self.write(original, "chat-a")
        copy = Transcript()
        copy.lines = [dict(e) for e in original.lines]  # (a fork keeps the uuids and ids)
        copy.prompt(t0 + 60_000).reply(t0 + 61_000, "b").duration(t0 + 62_000, 2000)
        self.write(copy, "chat-b")
        r = self.recap()
        self.assertAlmostEqual(r["sum"]["cost"], 2 * week.request_cost("claude-opus-5-5", [5, 100, 1000, 0, 0, 0, 1]), 4)
        self.assertEqual((r["sum"]["prompts"], r["sum"]["turns"], r["sum"]["workedMs"]), (2, 2, 4000))

    def test_a_forked_subagent_starts_with_a_copy_of_the_call(self):
        t0 = self.t0
        main = Transcript().prompt(t0).reply(t0 + 1000, "call", tools=[("A", "Agent", {})])
        self.write(main)
        sub = Transcript()
        sub.lines = [dict(main.lines[-1], isSidechain=True)]
        sub.prompt(t0 + 1500, "your directive").reply(t0 + 2000, "own", isSidechain=True)
        self.write(sub, sub="agent-x")
        (agg,) = self.chats()["chat-a"]["hours"].values()
        self.assertEqual(agg["w"][week.N_ALL], 2)
        self.assertEqual(agg["w"][week.N_SUB], 1)

    def test_a_chat_shared_by_hard_links(self):
        t0 = self.t0
        path = self.write(Transcript().prompt(t0).reply(t0 + 1000, "a").duration(t0 + 2000, 2000))
        os.link(path, self.home / ".claude-personal/projects/-w/chat-a.jsonl")
        self.assertEqual(len(self.scan()["files"]), 1)  # read once
        chat = self.chats()["chat-a"]
        self.assertEqual(sorted(chat["profiles"]), [".claude-personal", ".claude-work"])
        by_profile, _ = week.account_ids(self.profiles())
        for account in by_profile.values():  # on each account it's on, once in all
            self.assertEqual(self.recap(account)["sum"]["turns"], 1)
        self.assertEqual(self.recap()["sum"]["turns"], 1)

    def test_reading_on_gives_what_reading_once_gives(self):
        t0, tr = self.t0, Transcript()
        tr.prompt(t0).reply(t0 + 5000, "a", tools=[("T1", "Edit", {})]).result(t0 + 90_000, "T1", source="user_temporary")
        tr.reply(t0 + 95_000, "b", output=10).reply(t0 + 96_000, "b", output=30).duration(t0 + 100_000, 15_000)
        tr.prompt(t0 + 200_000).reply(t0 + 210_000, "c", tools=[("T2", "Bash", {"command": "ls"})])
        tr.result(t0 + 230_000, "T2", text="x" * 30_000).reply(t0 + 240_000, "d", read=200_000).limit(t0 + 250_000)
        tr.prompt(t0 + 5000_000).reply(t0 + 5010_000, "e").duration(t0 + 5020_000, 20_000)
        whole = Transcript()
        whole.lines = list(tr.lines)
        self.write(whole)
        once = self.chats()
        cache = {"files": {}}
        for n in range(1, len(tr.lines) + 1):  # each line written, then read
            part = Transcript()
            part.lines = tr.lines[:n]
            self.write(part)
            self.scan(cache)
        self.assertEqual(self.chats(cache), once)


class YourTimeTests(unittest.TestCase):
    def test_gaps_under_idle_count(self):
        m = MIN
        # your prompts at 0, 5 and 40 min; Claude's turns ended at 2, 10 and 60
        spans = week.your_time([0, 5 * m, 40 * m], [2 * m, 10 * m, 60 * m])
        self.assertEqual(spans, [[-1 * m, 10 * m], [39 * m, 40 * m]])

    def test_two_chats_ending_dont_make_your_time(self):
        self.assertEqual(week.your_time([], [0, 5 * MIN]), [])


class RecapTests(Home):
    def test_a_week_of_days(self):
        t0 = self.t0
        self.write(Transcript().prompt(t0).reply(t0 + 60_000, "a").duration(t0 + 120_000, 120_000))
        r = self.recap()
        self.assertEqual([d["day"] for d in r["days"]],
                         [(date(2026, 10, 24) - timedelta(days=6 - i)).isoformat() for i in range(7)])
        today = r["days"][-1]
        self.assertEqual(today["work"], [[t0, t0 + 120_000, 1]])
        self.assertEqual(today["you"], [[t0 - week.PROMPT_LEAD_MS, t0 + 120_000]])
        self.assertEqual((r["sum"]["workedMs"], r["sum"]["youMs"], r["sum"]["prompts"]), (120_000, 180_000, 1))
        self.assertEqual(r["projects"][0]["name"], "app")
        self.assertEqual((r["chats"][0]["chatId"], r["chats"][0]["cwd"]), ("chat-a", "/w/app"))
        self.assertEqual(r["models"][0]["model"], "Opus 5.5")
        self.assertEqual(self.recap(back=1)["sum"]["workedMs"], 0)
        self.assertEqual(self.recap(back=1)["to"], "2026-10-17")

    def test_a_project_in_the_home_folder_is_shown_short_and_opened_by_its_folder(self):
        # (the Projects tab's rows go by the whole folder: a click opens that one)
        app = str(self.home / "repos" / "app")
        self.write(Transcript(app).prompt(self.t0).reply(self.t0 + 60_000, "a").duration(self.t0 + 120_000, 120_000))
        p = self.recap()["projects"][0]
        self.assertEqual((p["path"], p["folder"]), ("~/repos/app", app))

    def test_the_week_before(self):
        before = self.t0 - 7 * week.DAY_MS
        self.write(Transcript().prompt(before).reply(before + 1000, "a").duration(before + 30_000, 30_000))
        r = self.recap()
        self.assertEqual((r["sum"]["workedMs"], r["previous"]["workedMs"]), (0, 30_000))

    def test_chats_at_once(self):
        t0 = self.t0
        for i, chat in enumerate(("a", "b")):
            s = t0 + i * 60_000
            self.write(Transcript().prompt(s).reply(s + 1000, chat).duration(s + 120_000, 120_000), "chat-" + chat)
        r = self.recap()
        self.assertEqual(r["days"][-1]["work"], [[t0, t0 + 60_000, 1], [t0 + 60_000, t0 + 120_000, 2],
                                                [t0 + 120_000, t0 + 180_000, 1]])
        self.assertEqual((r["sum"]["peakAtOnce"], r["sum"]["busyMs"], r["sum"]["workedMs"]), (2, 180_000, 240_000))

    def test_one_account(self):
        t0 = self.t0
        self.write(Transcript().prompt(t0).reply(t0 + 1000, "a").duration(t0 + 2000, 2000), "chat-a", "work")
        self.write(Transcript().prompt(t0).reply(t0 + 1000, "b").duration(t0 + 3000, 3000), "chat-b", "personal")
        by_profile, _ = week.account_ids(self.profiles())
        self.assertEqual(self.recap(by_profile[".claude-work"])["sum"]["workedMs"], 2000)
        self.assertEqual(self.recap(by_profile[".claude-personal"])["sum"]["workedMs"], 3000)
        self.assertEqual(self.recap()["sum"]["workedMs"], 5000)
        self.assertEqual(sorted(a["name"] for a in self.recap()["accounts"]), ["personal", "work"])

    def test_an_ssh_hosts_chats(self):
        t0 = self.t0
        host_chat = {"profiles": [".claude"], "accounts": ["x"], "folder": "/srv/job", "project": "/srv/job",
                     "name": "train", "turns": [[t0, t0 + 600_000, 600_000, []]], "prompts": [t0], "limits": [],
                     "hours": {}, "startTokens": None}
        r = self.recap(extra=[{"host": "gpu", "chats": {"c1": host_chat}, "accounts": [{"id": "x", "name": "lab"}]}])
        self.assertEqual(r["sum"]["workedMs"], 600_000)
        self.assertEqual((r["projects"][0]["name"], r["projects"][0]["host"]), ("job", "gpu"))

    def test_limits_hit_by_several_chats_are_one_time(self):
        t0, hour = self.t0, 3600_000
        self.write(Transcript().prompt(t0).limit(t0 + 1000).limit(t0 + 60_000), "chat-a")
        self.write(Transcript().prompt(t0).limit(t0 + 2000).limit(t0 + 5 * hour), "chat-b")
        r = self.recap()
        self.assertEqual(r["sum"]["limits"], 2)
        self.assertEqual(r["days"][-1]["limits"], [t0 + 1000, t0 + 2000, t0 + 60_000, t0 + 5 * hour])  # (marks on the timeline)

    def test_a_days_chats_and_a_projects(self):
        t0 = self.t0
        self.write(Transcript().prompt(t0).reply(t0 + 1000, "a").duration(t0 + 120_000, 120_000).title("Fix it"), "chat-a")
        self.write(Transcript().prompt(t0 - week.DAY_MS).reply(t0 - week.DAY_MS + 1000, "b")
                   .duration(t0 - week.DAY_MS + 90_000, 90_000), "chat-b")
        r = self.recap()
        self.assertEqual([(c["chatId"], c["name"], c["workedMs"], c["prompts"]) for c in r["days"][-1]["chats"]],
                         [("chat-a", "Fix it", 120_000, 1)])
        self.assertEqual([c["chatId"] for c in r["days"][-2]["chats"]], ["chat-b"])
        self.assertEqual([c["chatId"] for c in r["projects"][0]["chats"]], ["chat-a", "chat-b"])
        self.assertEqual(r["projects"][0]["chatCount"], 2)

    def test_the_trend_of_five_weeks(self):
        t0 = self.t0
        self.write(Transcript().prompt(t0).reply(t0 + 1000, "a").duration(t0 + 60_000, 60_000), "chat-a")
        old = t0 - 21 * week.DAY_MS
        self.write(Transcript().prompt(old).reply(old + 1000, "b").duration(old + 30_000, 30_000), "chat-b")
        r = self.recap(days=40)
        self.assertEqual([w and w["workedMs"] for w in r["trend"]], [None, 30_000, 0, 0, 60_000])  # (None: before the first chat)
        self.assertEqual(r["trend"][-1]["start"], r["days"][0]["start"])
        self.assertEqual(r["trend"][3]["workedMs"], r["previous"]["workedMs"])
        self.assertEqual(self.recap(back=4, days=40)["trend"][:4], [None] * 4)  # (before the first chat kept)

    def test_a_day_and_everything(self):
        t0 = self.t0
        self.write(Transcript().prompt(t0).reply(t0 + 1000, "a").duration(t0 + 60_000, 60_000), "chat-a")
        yesterday = t0 - week.DAY_MS
        self.write(Transcript().prompt(yesterday).reply(yesterday + 1000, "b").duration(yesterday + 30_000, 30_000), "chat-b")
        old = t0 - 16 * week.DAY_MS
        self.write(Transcript().prompt(old).reply(old + 1000, "c").duration(old + 20_000, 20_000), "chat-c")
        day = self.recap(span="day", days=40)
        self.assertEqual((day["span"], day["from"], day["to"], len(day["days"])), ("day", "2026-10-24", "2026-10-24", 1))
        self.assertEqual((day["sum"]["workedMs"], day["previous"]["workedMs"]), (60_000, 30_000))  # (the day before)
        self.assertEqual([t and t["workedMs"] for t in day["trend"]], [0, 0, 0, 30_000, 60_000])
        self.assertEqual(day["backMax"], 16)  # (back to the first chat's day)
        self.assertEqual(self.recap(span="day", back=1, days=40)["sum"]["workedMs"], 30_000)
        everything = self.recap(span="all", days=40)
        self.assertEqual((everything["from"], everything["to"], everything["first"]), ("2026-10-08", "2026-10-24", "2026-10-08"))
        self.assertEqual(everything["sum"]["workedMs"], 110_000)
        self.assertIsNone(everything["previous"])
        self.assertEqual(everything["trend"], [])
        # a row per 7 days, newest first, ending today, back to the first chat
        self.assertEqual([(r["day"], r["to"], r["workedMs"]) for r in everything["days"]],
                         [("2026-10-18", "2026-10-24", 90_000), ("2026-10-11", "2026-10-17", 0), ("2026-10-04", "2026-10-10", 20_000)])
        self.assertEqual(sum(r["workedMs"] for r in everything["days"]), everything["sum"]["workedMs"])

    def test_a_month(self):
        # the 30 days ending today, a row per 7 days (newest first, the oldest
        # only the month's own days); the 30 before to compare; 30 days a step back
        t0 = self.t0
        self.write(Transcript().prompt(t0).reply(t0 + 1000, "a").duration(t0 + 60_000, 60_000), "chat-a")
        early = t0 - 27 * week.DAY_MS  # (in the month's oldest row)
        self.write(Transcript().prompt(early).reply(early + 1000, "c").duration(early + 20_000, 20_000), "chat-c")
        old = t0 - 35 * week.DAY_MS
        self.write(Transcript().prompt(old).reply(old + 1000, "b").duration(old + 30_000, 30_000), "chat-b")
        month = self.recap(span="month", days=80)
        self.assertEqual((month["span"], month["from"], month["to"]), ("month", "2026-09-25", "2026-10-24"))
        self.assertEqual([(r["day"], r["to"], r["workedMs"]) for r in month["days"]],
                         [("2026-10-18", "2026-10-24", 60_000), ("2026-10-11", "2026-10-17", 0), ("2026-10-04", "2026-10-10", 0),
                          ("2026-09-27", "2026-10-03", 20_000), ("2026-09-25", "2026-09-26", 0)])
        self.assertEqual((month["sum"]["workedMs"], month["previous"]["workedMs"]), (80_000, 30_000))
        self.assertEqual(sum(r["workedMs"] for r in month["days"]), month["sum"]["workedMs"])
        self.assertEqual(month["sum"]["busiestDay"], "2026-10-24")  # (a day, not a row)
        self.assertEqual([t and t["workedMs"] for t in month["trend"]][-2:], [30_000, 80_000])
        self.assertEqual(month["backMax"], 1)  # (35 days back: one step)
        self.assertEqual(self.recap(span="month", back=1, days=80)["sum"]["workedMs"], 30_000)
        self.assertEqual(week.span_days("month", 0, self.now)[0][0], "2026-09-25")

    def test_the_tokens_of_a_day_a_week_and_everything(self):
        t0 = self.t0
        once = 5 + 100 + 1000  # (a reply: input, output, cache reads)
        self.write(Transcript().prompt(t0).reply(t0 + 1000, "a").reply(t0 + 2000, "a2", write=40, hour_writes=True)
                   .duration(t0 + 60_000, 60_000), "chat-a")
        yesterday = t0 - week.DAY_MS
        self.write(Transcript().prompt(yesterday).reply(yesterday + 1000, "b").duration(yesterday + 30_000, 30_000), "chat-b")
        old = t0 - 9 * week.DAY_MS
        self.write(Transcript().prompt(old).reply(old + 1000, "c", output=900).duration(old + 20_000, 20_000), "chat-c")
        r = self.recap(days=40)
        self.assertEqual(r["sum"]["tokenTotal"], 2 * once + 40 + once)  # (cache writes count, searches don't)
        self.assertEqual(r["sum"]["tokenTotal"], sum(r["sum"]["tokens"][k] for k in list(week.USAGE_KEYS)[:5]))
        self.assertEqual([d["tokenTotal"] for d in r["days"]], [0, 0, 0, 0, 0, once, 2 * once + 40])
        self.assertEqual(r["previous"]["tokenTotal"], once + 800)
        self.assertEqual(r["trend"][-1]["tokenTotal"], r["sum"]["tokenTotal"])
        self.assertEqual(r["trend"][-2]["tokenTotal"], r["previous"]["tokenTotal"])
        day = self.recap(span="day", days=40)
        self.assertEqual((day["sum"]["tokenTotal"], day["previous"]["tokenTotal"]), (2 * once + 40, once))
        everything = self.recap(span="all", days=40)
        self.assertEqual(everything["sum"]["tokenTotal"], 4 * once + 40 + 800)
        self.assertEqual(sum(d["tokenTotal"] for d in everything["days"]), everything["sum"]["tokenTotal"])


class HistoryTests(Home):
    """What the cache read stays after Claude deletes a transcript, unless
    the history is off; deleting it starts again from the transcripts."""

    def setUp(self):
        super().setUp()
        t0 = self.t0
        self.kept = self.write(Transcript().prompt(t0).reply(t0 + 1000, "a").duration(t0 + 60_000, 60_000), "chat-a")
        self.deleted = self.write(Transcript().prompt(t0).reply(t0 + 2000, "b").duration(t0 + 30_000, 30_000), "chat-b")
        week.updated_cache(self.cache_root, self.profiles(), self.now)

    def worked(self):
        cache = week.updated_cache(self.cache_root, self.profiles(), self.now)
        chats = week.chats_between(cache, self.profiles(), 0, self.now + week.DAY_MS, self.home)
        return sorted((k, sum(t[2] for t in c["turns"])) for k, c in chats.items())

    def test_a_deleted_transcript_stays_in_the_history(self):
        self.deleted.unlink()  # (Claude's cleanup)
        self.assertEqual(self.worked(), [("chat-a", 60_000), ("chat-b", 30_000)])
        self.assertEqual(week.history_status(self.cache_root)["deletedChats"], 1)
        self.assertEqual(self.worked(), [("chat-a", 60_000), ("chat-b", 30_000)])  # (and on the next read)

    def test_a_chat_claude_moved_to_another_folder_counts_once(self):
        # (Claude moves a chat's transcript when it goes into a worktree: the
        # old path's record stays as history, the new file has the same turns)
        moved = self.kept.parent.parent / "-w--claude-worktrees-x" / self.kept.name
        moved.parent.mkdir()
        self.kept.rename(moved)
        self.assertEqual(self.worked(), [("chat-a", 60_000), ("chat-b", 30_000)])
        self.assertEqual(week.history_status(self.cache_root)["deletedChats"], 0)
        self.assertEqual(week.recap([{"host": "", "chats": week.chats_between(
            week.updated_cache(self.cache_root, self.profiles(), self.now), self.profiles(), 0, self.now + week.DAY_MS,
            self.home), "accounts": week.account_ids(self.profiles())[1]}], 0, "", self.now, self.home)["ok"], True)

    def test_off_it_keeps_only_what_claude_has(self):
        self.deleted.unlink()
        self.worked()
        past = self.cache_root / week.cs.USAGE_PAST_FILE  # (the plan windows that ended go too)
        week.cs.write_json_atomic(past, {"version": 1, "windows": [{"key": "five_hour"}]})
        self.assertEqual(week.history_status(self.cache_root)["planWindows"], 1)  # (so the question asks)
        # (it says how many chats it forgot, as the question before counted them)
        self.assertEqual(week.set_history(self.cache_root, False),
                         (True, "The Recap keeps only what Claude still has (it forgot 1 deleted chat and your "
                                "plan's windows that ended)"))
        self.assertEqual(self.worked(), [("chat-a", 60_000)])
        self.assertFalse(week.history_status(self.cache_root)["keep"])
        self.assertFalse(past.exists())
        self.assertTrue(week.set_history(self.cache_root, True)[0])
        self.assertTrue(week.history_status(self.cache_root)["keep"])

    def test_off_a_moved_chat_keeps_its_tokens(self):
        moved = self.kept.parent.parent / "-w--claude-worktrees-x" / self.kept.name
        moved.parent.mkdir()
        self.kept.rename(moved)
        self.worked()
        week.set_history(self.cache_root, False)
        cache = week.updated_cache(self.cache_root, self.profiles(), self.now)
        chat = week.chats_between(cache, self.profiles(), 0, self.now + week.DAY_MS, self.home)["chat-a"]
        self.assertEqual(sum(t[1] for agg in chat["hours"].values() for t in agg["t"].values()), 100)  # (its output)

    def test_a_chat_of_a_folder_this_run_doesnt_read_isnt_deleted(self):
        # (another front end's settings have no such extra Claude folder: they share the cache)
        self.write(Transcript().prompt(self.t0).reply(self.t0 + 1000, "c"), "chat-c", "personal")
        week.updated_cache(self.cache_root, self.profiles(), self.now)
        week.updated_cache(self.cache_root, [p for p in self.profiles() if p.real.name == ".claude-work"], self.now)
        self.assertEqual(week.history_status(self.cache_root)["deletedChats"], 0)

    def test_forget_starts_again_from_the_transcripts(self):
        self.deleted.unlink()
        self.worked()
        past = self.cache_root / week.cs.USAGE_PAST_FILE
        week.cs.write_json_atomic(past, {"version": 1, "windows": []})
        self.assertTrue(week.forget_history(self.cache_root)[0])
        self.assertFalse((self.cache_root / week.CACHE_FILE).exists())
        self.assertFalse(past.exists())
        self.assertEqual(self.worked(), [("chat-a", 60_000)])
        self.assertEqual(week.history_status(self.cache_root)["since"], "2026-10-24")


class TipTests(Home):
    def hour(self, **w):
        agg = {"t": {}, "w": [0] * week.W_SIZE, "b": {}, "a": {}, "g": {}}
        for name, v in w.items():
            agg["w"][getattr(week, name)] = v
        return agg

    def chat(self, hours, **kw):
        return dict({"key": kw.pop("key", "|c"), "hours": hours, "startTokens": None}, **kw)

    def test_a_behavior_from_a_tenth_of_the_usage(self):
        h = str(self.t0 // week.HOUR_MS)
        chats = [self.chat({h: self.hour(W_ALL=100, W_MAX=12, W_LONG=9, N_ALL=10)})]
        tips = week.tips(chats, self.t0 - week.DAY_MS, self.now, {}, [])
        self.assertEqual([(t["key"], t["pct"]) for t in tips], [("max_effort", 12)])  # not long context: 9%

    def test_many_chats_at_once(self):
        h = str(self.t0 // week.HOUR_MS)
        chats = [self.chat({h: dict(self.hour(W_ALL=10, N_ALL=1), b={"3": 10})}, key="|%d" % i) for i in range(4)]
        tips = week.tips(chats, self.t0 - week.DAY_MS, self.now, {}, [])
        self.assertEqual([(t["key"], t["pct"], t["detail"]) for t in tips], [("high_parallel", 100, "up to 4 at once")])

    def test_a_chat_running_for_hours(self):
        hours = {str(self.t0 // week.HOUR_MS - i): self.hour(W_ALL=10, N_ALL=1) for i in range(8)}
        tips = week.tips([self.chat(hours)], self.t0 - week.DAY_MS, self.now, {}, [])
        self.assertEqual([t["key"] for t in tips], ["long_running"])

    def test_subagents(self):
        h = str(self.t0 // week.HOUR_MS)
        heavy = self.chat({h: self.hour(W_ALL=10, W_SUB=8, N_SUB=1, N_ALL=2)}, key="|a")
        light = self.chat({h: self.hour(W_ALL=10, W_SUB=1, N_SUB=1, N_ALL=2)}, key="|b")
        self.assertEqual([(t["key"], t["pct"]) for t in week.tips([heavy, light], self.t0 - week.DAY_MS, self.now, {}, [])],
                         [("subagent_heavy", 50)])

    def test_what_made_the_large_results(self):
        self.assertEqual(week.big_result_tip({"Read|/w/app/data.csv": [3, 40_000], "Bash|ls": [1, 12_000]}),
                         ("Read data.csv in parts", "up to 40k tokens, 3 times", ""))
        self.assertEqual(week.big_result_tip({"Bash|pytest -v": [1, 12_000]})[0], 'Shorten the output of "pytest -v"')
        self.assertEqual(week.big_result_tip({"mcp__github__search|": [1, 12_000]})[0], "Ask github for smaller results")

    def test_waiting_and_limits(self):
        waits = [[self.t0, self.t0 + 20 * MIN]]
        tips = week.tips([], self.t0 - week.DAY_MS, self.now, {"limits": 3}, waits)
        self.assertEqual([t["key"] for t in tips], ["waits", "limits"])
        self.assertIn("20m 0s", tips[0]["detail"])

    def test_tips_from_transcripts(self):
        t0, tr = self.t0, Transcript()
        tr.prompt(t0).reply(t0 + 1000, "a", effort="max", inp=150_000, read=0)
        tr.duration(t0 + 2000, 2000)
        self.write(tr)
        keys = {t["key"] for t in self.recap()["tips"]}
        self.assertTrue({"max_effort", "cache_miss", "always_on_context"} <= keys, keys)
        self.assertNotIn("long_context", keys)  # (150k is the limit, not over it)


class time_zone:
    """The local time zone for a while (TZ, time.tzset); skipped where its tz data isn't."""

    def __init__(self, test, name):
        if name != "UTC" and not os.path.exists(os.path.join("/usr/share/zoneinfo", name)):
            test.skipTest("no time zone data for " + name)
        self.name = name

    def __enter__(self):
        self.old = os.environ.get("TZ")
        os.environ["TZ"] = self.name
        time.tzset()

    def __exit__(self, *exc):
        if self.old is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = self.old
        time.tzset()


class LocalHourTests(Home):
    """A chat's hours are the local clock's (week.hour_start): in a half-hour
    (India) or 45-minute (Nepal) time zone, what a reply cost counts for the
    day it came on; in a whole-hour one the keys are what they always were."""

    def every_5_minutes(self, start, hours):
        return range(start, start + hours * week.HOUR_MS, week.BUCKET_MS)

    def test_whole_hour_zones_keep_their_keys_across_dst(self):
        # Berlin and New York leave summer time on 2026-10-25 and 2026-11-01, enter it on 2026-03-29 and 2026-03-08
        for name, utc in (("UTC", (2026, 10, 24, 22)), ("Europe/Berlin", (2026, 10, 24, 22)),
                          ("Europe/Berlin", (2026, 3, 28, 22)), ("America/New_York", (2026, 11, 1, 3)),
                          ("America/New_York", (2026, 3, 8, 4))):
            start = int(datetime(*utc, tzinfo=timezone.utc).timestamp() * 1000)
            with time_zone(self, name), self.subTest(name=name, at=utc):
                for ts in self.every_5_minutes(start, 6):
                    h = week.hour_key(week.hour_start(ts))
                    self.assertEqual(h, str(ts // week.HOUR_MS))
                    self.assertEqual((ts - week.hour_ms(h)) // week.BUCKET_MS, (ts // week.BUCKET_MS) % 12)

    def test_half_and_three_quarter_hour_zones(self):
        # Lord Howe Island: +10:30, and +11 in summer (half an hour: from
        # 2026-10-04 02:00 to 2026-04-05 02:00, back to 01:30)
        def clock_hour(ms):
            local = datetime.fromtimestamp(ms / 1000)
            return local.date(), local.hour, local.fold   # (fold: an hour the clock went through twice)
        for name, fraction, local_start in (("Asia/Kolkata", ".5", (2026, 10, 23, 20)),
                                            ("Asia/Kathmandu", ".25", (2026, 10, 23, 20)),
                                            ("Australia/Lord_Howe", None, (2026, 10, 3, 20)),
                                            ("Australia/Lord_Howe", None, (2026, 4, 4, 20))):
            with time_zone(self, name), self.subTest(name=name, at=local_start):
                for ts in self.every_5_minutes(int(datetime(*local_start).timestamp() * 1000), 12):
                    h = week.hour_key(week.hour_start(ts))
                    begun = week.hour_ms(h)
                    # the first moment of the clock's hour ts is in
                    self.assertTrue(0 <= ts - begun < week.HOUR_MS)
                    self.assertEqual(clock_hour(begun), clock_hour(ts), (datetime.fromtimestamp(ts / 1000), h))
                    self.assertNotEqual(clock_hour(begun - 1000), clock_hour(ts))
                    if fraction:
                        self.assertTrue(h.endswith(fraction), h)
                        local = datetime.fromtimestamp(ts / 1000)
                        self.assertEqual(begun, int(local.replace(minute=0, second=0, microsecond=0).timestamp() * 1000))

    def test_a_reply_after_midnight_counts_for_its_day(self):
        with time_zone(self, "Asia/Kolkata"):
            self.now = int(datetime(2026, 10, 24, 12, 0).timestamp() * 1000)
            t = int(datetime(2026, 10, 24, 0, 15).timestamp() * 1000)
            self.write(Transcript().prompt(t - MIN).reply(t, "a").duration(t + MIN, 2 * MIN))
            once = 5 + 100 + 1000
            day = self.recap(span="day")
            self.assertEqual((day["from"], day["sum"]["tokenTotal"], day["previous"]["tokenTotal"]), ("2026-10-24", once, 0))
            self.assertGreater(day["sum"]["cost"], 0)
            self.assertEqual([c["cost"] > 0 for c in day["days"][0]["chats"]], [True])
            self.assertEqual(self.recap(span="day", back=1)["sum"]["tokenTotal"], 0)
            # its 5 minutes: the ones it came in (how many chats ran at once)
            (rec,) = [r for r in self.scan()["files"].values() if not r.get("sub")]
            ((h, agg),) = rec["data"]["hours"].items()
            ((b, _),) = agg["b"].items()
            self.assertEqual(week.hour_ms(h) // week.BUCKET_MS + int(b), t // week.BUCKET_MS)

    def test_an_older_cache_is_read_as_it_was(self):
        # Hours read before (UTC hours, in any zone) still count: the history stays
        t = int(datetime(2026, 10, 24, 6, 15, tzinfo=timezone.utc).timestamp() * 1000)   # (11:45 in India)
        tr = Transcript().prompt(t - MIN).reply(t, "a")
        self.write(tr)
        with time_zone(self, "UTC"):
            cache = self.scan()
        self.assertEqual(list(next(iter(cache["files"].values()))["data"]["hours"]), [str(t // week.HOUR_MS)])
        with time_zone(self, "Asia/Kolkata"):
            self.write(tr.reply(t + 2 * MIN, "b").duration(t + 3 * MIN, 4 * MIN))
            cache = self.scan(cache)   # (what was added: its reply in a local hour, 11:00 there)
            hours = next(iter(cache["files"].values()))["data"]["hours"]
            self.assertEqual(sorted(hours), sorted([str(t // week.HOUR_MS), "498005.5"]))
            self.assertEqual(week.hour_ms("498005.5"), int(datetime(2026, 10, 24, 11, 0).timestamp() * 1000))
            chats = week.chats_between(cache, self.profiles(), t - week.DAY_MS, t + week.DAY_MS, self.home)
            self.assertEqual(sorted(chats["chat-a"]["hours"]), sorted(hours))
            self.assertEqual(week.first_activity(cache), week.hour_ms("498005.5"))   # (its earliest hour began then)
            once = 5 + 100 + 1000
            self.now = t + week.HOUR_MS
            self.assertEqual(self.recap(span="day")["sum"]["tokenTotal"], 2 * once)

    def test_hours_that_overlap_the_span(self):
        hours = {"100": {}, "100.5": {}, "101": {}, "99.75": {}}
        cache = {"files": {"f": {"chat": "c", "profiles": [], "data": {
            "hours": {h: dict(week.new_hour()) for h in hours}, "turns": [], "prompts": [], "limits": []}}}}
        got = week.chats_between(cache, [], 100 * week.HOUR_MS + 1, 101 * week.HOUR_MS - 1, self.home)
        self.assertEqual(sorted(got["c"]["hours"]), ["100", "100.5", "99.75"])   # (not 101: it starts after)


class WeekRowClockTests(unittest.TestCase):
    """The Recap's Week view (WeekView.qml) places a time on its day's row by
    that day's own clock, under the hours over the rows: on a day of 25 hours
    (Berlin, Sun 25 Oct 2026) or 23 (New York, Sun 8 Mar 2026) 18:00 was
    drawn at 17:15 or 18:45 of the other rows."""

    def run_qml_functions(self, name, days, script):
        import re
        import shutil
        import subprocess
        if not shutil.which("node"):
            self.skipTest("node isn't installed")
        qml = (ROOT / "package/contents/ui/WeekView.qml").read_text()
        functions = "".join(re.search(r"\n    (function %s\(.*?\n    \})\n" % f, qml, re.S).group(1) + "\n"
                            for f in ("dayPlace", "dayMoment"))
        with time_zone(self, name):
            spans = [(d, start, end) for d, start, end in week.span_days("week", 0, days[1]) if d == days[0]]
        out = subprocess.run(["node", "-e", functions + "const day = " + json.dumps({"start": spans[0][1], "end": spans[0][2]})
                              + ";\n" + script], capture_output=True, text=True, timeout=60, env=dict(os.environ, TZ=name))
        if out.returncode:
            raise AssertionError(out.stderr)
        return day_hours(spans[0]), json.loads(out.stdout)

    def test_a_day_the_clock_changes_has_its_times_under_its_hours(self):
        for name, day, hours in (("Europe/Berlin", "2026-10-25", 25), ("Europe/Berlin", "2026-03-29", 23),
                                 ("America/New_York", "2026-03-08", 23), ("UTC", "2026-10-25", 24)):
            with time_zone(self, name):
                y, m, d = map(int, day.split("-"))
                at = {h: int(datetime(y, m, d, h).timestamp() * 1000) for h in (0, 1, 6, 12, 18)}
                now = int(datetime(y, m, d + 2, 12).timestamp() * 1000)
            with self.subTest(name=name, day=day):
                length, places = self.run_qml_functions(name, (day, now), "console.log(JSON.stringify({"
                    "at: " + json.dumps(at) + ", place: Object.fromEntries(Object.entries(" + json.dumps(at)
                    + ").map(([h, ms]) => [h, dayPlace(day, ms)])), back: [6, 12, 18].map(h => dayMoment(day, h / 24)),"
                    " ends: [dayPlace(day, day.start - 1), dayPlace(day, day.end), dayMoment(day, 0), dayMoment(day, 1)]}))")
                self.assertEqual(length, hours)
                self.assertEqual({int(h): round(p * 24, 6) for h, p in places["place"].items()}, {0: 0, 1: 1, 6: 6, 12: 12, 18: 18})
                self.assertEqual(places["back"], [at[6], at[12], at[18]])
                self.assertEqual(places["ends"][:2], [0, 1])
                self.assertEqual(places["ends"][2:], [at[0], at[0] + hours * week.HOUR_MS])


def day_hours(span):
    return (span[2] - span[1]) / week.HOUR_MS



class OneRefreshTests(unittest.TestCase):
    """The popup's Refresh (its top row's; in VS Code the view's title bar's,
    the Command Palette's or an editor tab's header's) also reads the tab
    shown again, as when it opens: the Recap (week.py for the days shown),
    Permissions or Projects. The Recap's own Read again (↻) beside its days
    is gone, so there's one Refresh (Plasma, GNOME and VS Code)."""

    def body(self, pattern, text):
        import re
        found = re.search(pattern, text, re.S)
        self.assertIsNotNone(found, pattern)
        return found.group(1)

    def test_plasma(self):
        ui = ROOT / "package/contents/ui"
        refresh = self.body(r'text: i18n\("Refresh"\)\s+onClicked: \{(.*?)\n                \}',
                            (ui / "FullRepresentation.qml").read_text())
        for read in ("root.loadWeek()", "root.loadPerms()", 'if (root.popupTab === "projects")\n                        root.loadProjects()'):
            self.assertIn(read, refresh)
        main = (ui / "main.qml").read_text()
        self.assertIn('if (popupTab !== "week")\n            return', self.body(r"\n    function loadWeek\(\) \{(.*?)\n    \}", main))
        self.assertIn('if (popupTab !== "perms"', self.body(r"\n    function loadPerms\(\) \{(.*?)\n    \}", main))
        week = (ui / "WeekView.qml").read_text()
        for gone in ("Icons.plasma.refresh", "root.loadWeek", "Read again", "These days read again"):
            self.assertFalse(gone in week, gone)
        for kept in ("Icons.plasma.share", "Icons.plasma.previous", "Icons.plasma.next", "root.setWeekSpan(modelData[0])"):
            self.assertIn(kept, week)
        for view in ("PermsView.qml", "ProjectsView.qml"):
            self.assertNotIn("Icons.plasma.refresh", (ui / view).read_text())

    def test_gnome(self):
        ext = ROOT / "gnome/extension"
        indicator = (ext / "indicator.js").read_text()
        self.assertIn("this._loadTab();", self.body(r"iconButton\(Icons\.gnome\.refresh, \(\) => \{(.*?)\}\), 'Refresh'\)", indicator))
        tab = self.body(r"\n    _loadTab\(\) \{(.*?)\n    \}", indicator)
        self.assertIn("this.loadWeek()", tab)
        self.assertIn("this.loadPerms()", tab)
        week = (ext / "ui/weekView.js").read_text()
        for gone in ("Icons.gnome.refresh", "loadWeek", "Read again", "These days read again"):
            self.assertFalse(gone in week, gone)
        self.assertIn("Icons.gnome.previous", week)
        self.assertNotIn("Icons.gnome.refresh", (ext / "ui/permsView.js").read_text())

    def test_vscode(self):
        vs = ROOT / "vscode"
        self.assertIn('registerCommand("talpyDen.refresh", () => view.refresh())', (vs / "src/extension.ts").read_text())
        self.assertIn('this.broadcast({ type: "readAgain" });', self.body(r"\n  refresh\(\): void \{(.*?)\n  \}", (vs / "src/view.ts").read_text()))
        self.assertIn('case "readAgain":\n      readAgain.set(readAgain.get() + 1);', (vs / "webview/main.tsx").read_text())
        components = vs / "webview/components"
        for name, read in (("WeekView.tsx", "useReadAgain(visible, ask);"), ("PermsView.tsx", "useReadAgain(visible, ask);"),
                           ("ProjectsView.tsx", 'useReadAgain(visible, () => post({ type: "projects" }));')):
            with self.subTest(name=name):
                source = (components / name).read_text()
                self.assertTrue(read in source, read)
                self.assertFalse("I.refresh" in source, name)
        week = (components / "WeekView.tsx").read_text()
        for gone in ("Read again", "These days read again"):
            self.assertFalse(gone in week, gone)
        self.assertIn("I.share", week)

class SpendTests(Home):
    def test_cold_resumes(self):
        t0, hour = self.t0, 3600_000
        tr = Transcript().prompt(t0).reply(t0 + 1000, "a", output=1000, read=0, write=100_000, hour_writes=True)
        tr.duration(t0 + 2000, 2000).prompt(t0 + 2 * hour)
        tr.reply(t0 + 2 * hour + 1000, "b", output=1000, read=0, write=100_000, hour_writes=True)  # (its cache gone)
        tr.duration(t0 + 2 * hour + 2000, 2000).prompt(t0 + 2 * hour + 60_000)
        tr.reply(t0 + 2 * hour + 61_000, "c", output=10, read=100_000).duration(t0 + 2 * hour + 62_000, 2000)
        self.write(tr)
        s = self.recap()["spend"]
        self.assertEqual((s["cold"]["count"], s["cold"]["cost"]), (1, 0.78))  # (written again at 8, not read at 0.2)
        self.assertEqual(s["cold"]["chats"][0]["resumes"], 1)
        self.assertEqual(set(s), {"cold"})  # (the costliest turns and chats went with the Recap's section)


class WorkTests(Home):
    def test_what_claude_did(self):
        t0 = self.t0
        edit = {"file_path": "/w/app/a.py", "old_string": "a\nb\n", "new_string": "a\nc\nd\n"}
        tr = Transcript().prompt(t0).reply(t0 + 1000, "a", tools=[
            ("E", "Edit", edit), ("W", "Write", {"file_path": "/w/app/b.py", "content": "x\ny\n"}),
            ("E2", "Edit", dict(edit, old_string="a")), ("B", "Bash", {"command": "make test"}),
            ("A", "Agent", {"prompt": "look"}), ("M", "mcp__github__search", {})])
        tr.compacted(t0 + 50_000).reply(t0 + 60_000, "b", tools=[("S", "WebFetch", {"url": "https://x.org"})])
        tr.duration(t0 + 70_000, 70_000)
        self.write(tr)
        w = self.recap()["work"]
        self.assertEqual((w["toolCalls"], w["commands"], w["edits"], w["files"], w["subagents"], w["compactions"],
                          w["webFetches"]), (7, 1, 3, 2, 1, 1, 1))
        self.assertEqual((w["linesAdded"], w["linesRemoved"]), (2 + 2 + 2, 1 + 0 + 0))
        self.assertIn(["MCP: github", 1], w["tools"])
        self.assertEqual(week.edit_lines("Write", {"content": "1\n2\n3"}), (3, 0))
        self.assertEqual(week.edit_lines("MultiEdit", {"edits": [edit, edit]}), (4, 2))


class PlanTests(Home):
    def test_how_the_windows_filled(self):
        profiles = self.profiles()
        gid = {m.label: cs.short_id(g) for g, members in cs.group_profiles(profiles) for m in members}
        t0 = self.t0
        usage = {"groups": {gid["work"]: {"five_hour": {"resetsAt": t0 + 3600_000, "points": [[t0, 10], [t0 + 60_000, 25]]},
                                          "seven_day": {"resetsAt": t0 + 7 * week.DAY_MS, "points": [[t0, 40]]},
                                          "somewhere": {"points": [[t0, 1]]}}}}
        cs.write_json_atomic(self.cache_root / "usage.json", usage)
        plans = week.plan_windows(self.cache_root, profiles, t0 + 60_000)
        self.assertEqual([(p["name"], [(w["key"], w["label"], w["pct"]) for w in p["windows"]]) for p in plans],
                         [("work", [("five_hour", "5h", 25), ("seven_day", "7d", 40)])])
        self.assertEqual(plans[0]["windows"][0]["points"], [[t0, 10], [t0 + 60_000, 25]])
        self.assertEqual(self.recap(usage=plans)["plan"], plans)
        self.assertEqual(self.recap(account=gid["personal"], usage=plans)["plan"], [])
        self.assertEqual(self.recap(back=1, usage=plans)["plan"], [])

    def test_a_window_past_its_reset_is_at_0(self):
        # as on the Chats tab: no reply since the 5-hour window reset at 11:00
        # (after a limit stop), and its 97% and "resets 11:00" were shown at 18:00
        profiles = self.profiles()
        gid = {m.label: cs.short_id(g) for g, members in cs.group_profiles(profiles) for m in members}
        t0 = self.t0
        usage = {"groups": {gid["work"]: {"five_hour": {"resetsAt": t0 + 3600_000, "points": [[t0, 10], [t0 + 60_000, 97]]},
                                          "seven_day": {"resetsAt": t0 + 7 * week.DAY_MS, "points": [[t0, 40]]}}}}
        cs.write_json_atomic(self.cache_root / "usage.json", usage)
        five, seven = week.plan_windows(self.cache_root, profiles, self.now)[0]["windows"]
        self.assertEqual((five["pct"], five["resetsAt"], five["reset"], five["points"]), (0, None, True, []))
        self.assertEqual((seven["pct"], seven["resetsAt"], seven["reset"]), (40, t0 + 7 * week.DAY_MS, False))

    def test_a_window_not_started_is_shown_too(self):
        # personal at 96% of its week and no reply in the last 5 hours: Claude
        # says its 5-hour window is at 0% with no reset time, which the usage
        # history doesn't keep, and the Recap showed only "personal · 7d"
        t0 = self.t0
        d = self.home / ".claude-personal"
        d.joinpath(".claude.json").write_text(json.dumps({"oauthAccount": {"accountUuid": "acct-pro"}, "cachedUsageUtilization": {
            "fetchedAtMs": t0, "accountUuid": "acct-pro", "utilization": {
                "five_hour": {"utilization": 0, "resets_at": None},
                "seven_day": {"utilization": 96, "resets_at": "2026-10-24T22:00:00+00:00"}}}}))
        profiles = self.profiles()
        gid = {m.label: cs.short_id(g) for g, members in cs.group_profiles(profiles) for m in members}
        resets = cs.to_ms("2026-10-24T22:00:00+00:00")
        cs.write_json_atomic(self.cache_root / "usage.json",
                             {"groups": {gid["personal"]: {"seven_day": {"resetsAt": resets, "points": [[t0 - 60_000, 95], [t0, 96]]}}}})
        plans = {p["name"]: p["windows"] for p in week.plan_windows(self.cache_root, profiles, t0 + 60_000)}
        self.assertEqual([(w["key"], w["pct"], w["resetsAt"], w["reset"], len(w["points"])) for w in plans["personal"]],
                         [("five_hour", 0, None, False, 0), ("seven_day", 96, resets, False, 2)])


class LimitHistoryTests(Home):
    """The Recap's How your limits changed: a window's size is its usage (API
    prices) by a reading over the share of it the reading says was used. An
    Opus 5.5 reply of 100k output tokens costs $2."""

    def account(self, profile, **oauth):
        d = self.home / (".claude-" + profile)
        account = {"accountUuid": "acct-" + profile}
        account.update(oauth)
        (d / ".claude.json").write_text(json.dumps({"oauthAccount": account}))

    def gid(self, label):
        return {m.label: cs.short_id(g) for g, members in cs.group_profiles(self.profiles()) for m in members}[label]

    def window(self, t, start, n, usd=2.0, model="claude-opus-5-5", every=10 * MIN):
        price = {"claude-opus-5-5": 20, "claude-sonnet-5-5": 10}[model]
        for i in range(n):
            t.reply(start + i * every, "%s-%d-%d" % (model[-10:], start, i), output=int(usd / price * 1e6), read=0, inp=0,
                    model=model)
        return start + (n - 1) * every

    def past(self, *windows):
        cs.write_json_atomic(self.cache_root / cs.USAGE_PAST_FILE, {"version": 1, "windows": list(windows)})

    def history(self, account=""):
        return week.limit_history(self.cache_root, self.profiles(), self.now, account, self.home)

    def of(self, result, label):
        return next(a for a in result["accounts"] if a["name"] == label)

    def two_weeks(self, plans=("Team", "Team")):
        """Three 5-hour windows a week: $40 each the week before, $32 this week,
        and this week's weekly window: 20% at $48 ($240)."""
        self.account("work", organizationType="claude_team", seatTier="team_standard")
        reset = self.now + 2 * week.DAY_MS
        t, past = Transcript(), []
        for k in range(3):
            s = reset - (13 - k) * week.DAY_MS
            self.window(t, s, 10)  # $20 by s + 90 min
            past.append({"group": self.gid("work"), "key": "five_hour", "plan": plans[0], "resetsAt": s + 5 * 3600_000,
                         "points": [[s, 0], [s + 95 * MIN, 50]]})
        for k in range(3):
            s = reset - (6 - k) * week.DAY_MS
            self.window(t, s, 8)  # $16 by s + 70 min
            past.append({"group": self.gid("work"), "key": "five_hour", "plan": plans[1], "resetsAt": s + 5 * 3600_000,
                         "points": [[s, 0], [s + 75 * MIN, 50]]})
        self.write(t)
        self.past(*past)
        weekly_at = reset - 4 * week.DAY_MS + 2 * 3600_000  # (after the three windows: $48)
        cs.write_json_atomic(self.cache_root / "usage.json", {"version": 1, "groups": {self.gid("work"): {
            "seven_day": {"resetsAt": reset, "points": [[reset - week.WEEK_MS + 3600_000, 0], [weekly_at, 20]]}}}})
        return reset

    def test_sizes_week_by_week_and_what_changed(self):
        self.two_weeks()
        work = self.of(self.history(), "work")
        self.assertEqual(work["plan"], "Team · standard seat")
        self.assertEqual([w["full"] for w in work["windows"]], [40, 40, 40, 32, 32, 32])
        before, now = work["periods"]
        self.assertEqual(before["fiveHour"], {"cost": 40, "n": 3, "lo": 40, "hi": 40})
        self.assertEqual(before["weeks"], {})
        self.assertEqual(now["fiveHour"]["cost"], 32)
        self.assertEqual(now["weeks"]["seven_day"], {"cost": 240, "pct": 20})
        self.assertEqual(now["share"]["pct"], round(32 / 240 * 100, 1))
        self.assertEqual(now["fill"]["wallMs"], 75 * MIN * 2)  # (its first reply to its reading at 50%)
        self.assertEqual(now["tokens"]["output"], 1_600_000)
        self.assertEqual(work["changes"]["fiveHour"], {"kind": "change", "pct": -20, "against": before["from"]})
        self.assertEqual(work["changes"]["seven_day"]["kind"], "new")  # (the account had no weekly limit the week before)
        self.assertEqual(work["equivalents"]["model"], "Opus 5.5")
        self.assertEqual(work["equivalents"]["fiveHour"]["output"], 1_600_000)
        self.assertEqual(work["equivalents"]["week"]["cacheRead"], int(240 / 0.2 * 1e6))
        self.assertEqual(self.history(self.gid("personal"))["accounts"], [])

    def test_a_plan_change_isnt_a_percentage(self):
        self.two_weeks(plans=("Pro", "Max 5×"))
        self.account("work", organizationType="claude_max", organizationRateLimitTier="default_claude_max_5x")
        # (no reading saw it: between two windows; by how much: their sizes)
        change = self.of(self.history(), "work")["changes"]["fiveHour"]
        self.assertEqual((change["kind"], change["from"], change["to"], change["factor"]), ("limits", "Pro", "Max 5×", 0.8))

    def test_limits_that_changed_in_a_window(self):
        # a bigger plan while at the 5-hour limit: 100% became 20%, the week's
        # 35% 7%, with nothing used between: about 5 times the limits since
        self.two_weeks(plans=("Pro", "Pro"))
        gid = self.gid("work")
        s = self.now - 3 * 3600_000
        t = Transcript()
        self.window(t, s, 10, usd=4.0)  # $40 by s + 90 min
        self.write(t, chat="today")
        reset = self.now + 2 * week.DAY_MS
        weekly = json.loads((self.cache_root / "usage.json").read_text())["groups"][gid]["seven_day"]
        weekly["points"] += [[s + 100 * MIN, 35], [s + 160 * MIN, 7], [s + 170 * MIN, 7]]
        cs.write_json_atomic(self.cache_root / "usage.json", {"version": 1, "groups": {gid: {
            "seven_day": weekly,
            "five_hour": {"resetsAt": s + 5 * 3600_000, "points": [[s, 0], [s + 95 * MIN, 100], [s + 160 * MIN, 20],
                                                                    [s + 170 * MIN, 20]]}}}})
        self.account("work", organizationType="claude_max", organizationRateLimitTier="default_claude_max_5x")
        work = self.of(self.history(), "work")
        (event,) = work["events"]
        self.assertEqual((event["at"], event["factors"]), (s + 160 * MIN, {"five_hour": 5, "seven_day": 5}))
        self.assertEqual((event["from"], event["to"]), ("Pro", "Max 5×"))
        change = work["changes"]["fiveHour"]
        self.assertEqual((change["kind"], change["factor"], change["at"]), ("limits", 5, s + 160 * MIN))
        # (no window measured in the new limits yet: the week's before, times 5)
        before = work["periods"][-1]
        self.assertEqual(before["era"], 0)
        self.assertEqual((work["now"]["fiveHour"]["cost"], work["now"]["fiveHour"]["scaled"]), (32 * 5, 5))
        self.assertEqual(work["now"]["weeks"]["seven_day"]["cost"], round(before["weeks"]["seven_day"]["cost"] * 5, 2))

    def test_too_few_windows_to_compare(self):
        self.two_weeks()
        data = json.loads((self.cache_root / cs.USAGE_PAST_FILE).read_text())
        self.past(*data["windows"][:-1])  # (two this week)
        self.assertEqual(self.of(self.history(), "work")["changes"]["fiveHour"]["kind"], "few")

    def test_a_weekly_limit_that_began_in_its_window(self):
        # a weekly limit that began in the middle of its window: counted from
        # its first reading at 0%, not from its start a week before
        reset = self.two_weeks()
        began = reset - 5 * week.DAY_MS - 3600_000  # (after this week's first window: $32 since)
        cs.write_json_atomic(self.cache_root / "usage.json", {"version": 1, "groups": {self.gid("work"): {
            "seven_day": {"resetsAt": reset, "points": [[began, 0], [reset - 4 * week.DAY_MS + 2 * 3600_000, 20]]}}}})
        weeks = self.of(self.history(), "work")["periods"][1]["weeks"]
        self.assertEqual(weeks["seven_day"]["cost"], 160)  # ($32 of two windows since it began)
        self.assertTrue(weeks["seven_day"]["partial"])
        self.assertEqual(weeks["seven_day"]["countedFrom"], began)

    def today(self, five, week_points, seat="team_standard"):
        """$20 used today (10 replies, s to s + 90 min), and the readings of
        the 5-hour window and the week (minutes after s, percent)."""
        self.account("work", organizationType="claude_team", seatTier=seat)
        s = self.now - 3 * 3600_000
        t = Transcript()
        self.window(t, s, 10)
        self.write(t, chat="today")
        reset = self.now + 2 * week.DAY_MS
        cs.write_json_atomic(self.cache_root / "usage.json", {"version": 1, "groups": {self.gid("work"): {
            "five_hour": {"resetsAt": s + 5 * 3600_000, "points": [[s + m * MIN, p] for m, p in five]},
            "seven_day": {"resetsAt": reset, "points": [[reset - week.WEEK_MS + 3600_000, 0]] +
                          [[s + m * MIN, p] for m, p in week_points]}}}})
        return s, self.of(self.history(), "work")

    def test_a_smaller_plan_in_a_window(self):
        # a downgrade: both windows' readings went up 5 times with nothing used
        # between (premium's 10% of the 5-hour window is standard's 50%)
        s, work = self.today([(0, 0), (95, 10), (120, 50), (130, 50)], [(95, 2), (120, 10), (130, 10)])
        (event,) = work["events"]
        self.assertEqual((event["at"], event["factors"]), (s + 120 * MIN, {"five_hour": 0.2, "seven_day": 0.2}))
        self.assertEqual(event["to"], "Team · standard seat")
        change = work["changes"]["fiveHour"]
        self.assertEqual((change["kind"], change["factor"]), ("limits", 0.2))
        self.assertEqual(work["now"]["fiveHour"]["cost"], 40)  # (measured after it: $20 at 50%)
        self.assertNotIn("scaled", work["now"]["fiveHour"])

    def test_a_smaller_plan_with_the_5_hour_window_full(self):
        # the 5-hour window at 100% after it (more than full: no size); the week held up
        s, work = self.today([(0, 0), (95, 40), (120, 100), (130, 100)], [(95, 4), (120, 10), (130, 10)])
        (event,) = work["events"]
        self.assertEqual(event["factors"], {"five_hour": 0.4, "seven_day": 0.4})
        self.assertIsNone(work["now"]["fiveHour"])  # (40% isn't enough to tell the size before, 100% after)

    def test_what_isnt_a_change_of_the_limits(self):
        # the 5-hour window alone went up with nothing used here: use on claude.ai
        self.assertEqual(self.today([(0, 0), (95, 10), (120, 25), (130, 26)], [(95, 2), (120, 4), (130, 4)])[1]["events"], [])
        # the week went up by what this computer used meanwhile
        self.assertEqual(self.today([(0, 0)], [(5, 1), (95, 10), (100, 10)])[1]["events"], [])
        # one low reading at the end (a status line written with old numbers)
        self.assertEqual(self.today([(0, 0), (95, 60), (100, 30)], [(95, 12)])[1]["events"], [])

    def test_a_max_plans_model_weeks_count_their_own_model(self):
        self.account("personal", organizationType="claude_max", organizationRateLimitTier="default_claude_max_20x")
        reset = self.now + 2 * week.DAY_MS
        s = reset - 3 * week.DAY_MS
        t = Transcript()
        self.window(t, s, 5)  # Opus: $10
        self.window(t, s + 1, 5, usd=1.0, model="claude-sonnet-5-5")  # Sonnet: $5
        self.write(t, profile="personal")
        at = s + 2 * 3600_000
        start = reset - week.WEEK_MS
        cs.write_json_atomic(self.cache_root / "usage.json", {"version": 1, "groups": {self.gid("personal"): {
            "seven_day": {"resetsAt": reset, "points": [[start, 0], [at, 30]]},
            "seven_day_opus": {"resetsAt": reset, "points": [[start, 0], [at, 20]]},
            "seven_day_sonnet": {"resetsAt": reset, "points": [[start, 0], [at, 25]]}}}})
        personal = self.of(self.history(), "personal")
        self.assertEqual(personal["plan"], "Max 20×")
        self.assertEqual({k: v["cost"] for k, v in personal["now"]["weeks"].items()},
                         {"seven_day": 50, "seven_day_opus": 50, "seven_day_sonnet": 20})

    def test_a_shared_chat_counts_where_it_was_run(self):
        s = self.now - 6 * 3600_000
        t = Transcript()
        self.window(t, s, 10)
        path = self.write(t, chat="shared")
        other = self.home / ".claude-personal/projects/-w/shared.jsonl"
        os.link(str(path), str(other))  # (one file in both profiles: sharing.py)
        cs.write_json_atomic(self.cache_root / "usage.json", {"version": 1, "groups": {self.gid("personal"): {
            "five_hour": {"resetsAt": s + 5 * 3600_000, "points": [[s, 0], [s + 95 * MIN, 50]]}}}})
        self.assertEqual(self.of(self.history(), "personal")["windows"], [])  # (no sign of who ran it: left out)
        (self.home / ".claude-personal/history.jsonl").write_text(
            line({"display": "go on", "timestamp": s - MIN, "project": "/w", "sessionId": "shared"}))
        self.assertEqual([w["full"] for w in self.of(self.history(), "personal")["windows"]], [40])

    def test_a_snapshots_ended_window_is_kept(self):
        s = self.now - 6 * 3600_000
        t = Transcript().prompt(s - 1000)
        last = self.window(t, s, 10)
        self.write(t.duration(last + 1000, 60_000), chat="sess")
        snap = self.cache_root / "statusline/.claude-work/sess.json"
        cs.write_json_atomic(snap, {"session_id": "sess", "rate_limits": {
            "five_hour": {"used_percentage": 50, "resets_at": (s + 5 * 3600_000) // 1000}}})
        os.utime(str(snap), ((last + 5 * MIN) / 1000, (last + 5 * MIN) / 1000))
        (work,) = [a for a in self.history()["accounts"] if a["name"] == "work"]
        self.assertEqual(work["windows"][0]["at"], last + 5 * MIN)  # (when it was written)
        self.assertEqual(work["windows"][0]["full"], 40)
        kept = json.loads((self.cache_root / cs.USAGE_PAST_FILE).read_text())["windows"]
        self.assertEqual([(w["key"], w["group"]) for w in kept], [("five_hour", self.gid("work"))])
        # (kept also while a status check holds the lock a moment)
        (self.cache_root / cs.USAGE_PAST_FILE).unlink()
        import fcntl
        import threading
        fd = os.open(str(self.cache_root / "tokens.lock"), os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        threading.Timer(0.3, lambda: os.close(fd)).start()
        self.history()
        self.assertTrue((self.cache_root / cs.USAGE_PAST_FILE).exists())
        (self.cache_root / cs.USAGE_PAST_FILE).unlink()
        cs.write_json_atomic(self.cache_root / cs.HISTORY_SETTING_FILE, {"keep": False})
        self.history()
        self.assertFalse((self.cache_root / cs.USAGE_PAST_FILE).exists())  # (the history off: none kept)

    def test_main_answers_limits(self):
        import io
        import shutil
        from contextlib import redirect_stdout
        self.two_weeks()
        cache = Path(self.tmp.name) / "xdg"
        shutil.copytree(str(self.cache_root), str(cache / "talpy-den"))
        saved = dict(os.environ)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(saved)))
        os.environ["HOME"], os.environ["XDG_CACHE_HOME"] = str(self.home), str(cache)
        real_time = week.time.time
        week.time.time = lambda: self.now / 1000
        self.addCleanup(setattr, week.time, "time", real_time)
        out = io.StringIO()
        with redirect_stdout(out):
            week.main(["--limits", "--account", self.gid("work")])
        result = json.loads(out.getvalue())
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["currency"]["code"], "USD")
        self.assertEqual([a["name"] for a in result["accounts"]], ["work"])


class Projects(Home):
    """Two of your projects, ~/repos/app (where the chats start) and ~/repos/lib."""

    def setUp(self):
        super().setUp()
        self.app, self.lib = self.home / "repos/app", self.home / "repos/lib"
        for d in (self.app / ".git", self.lib / ".git", self.lib / "src"):
            d.mkdir(parents=True)
        self.settings = self.app / ".claude/settings.local.json"

    def asked(self):
        t0, tr = self.t0, Transcript(str(self.app))
        tr.prompt(t0)
        for i, (tool, inp, kw) in enumerate((
                ("Read", {"file_path": str(self.lib / "src/x.py")}, {"reason": "workingDir"}),
                ("Read", {"file_path": str(self.lib / "README.md")}, {}),
                ("Edit", {"file_path": str(self.app / "m.py"), "old_string": "a", "new_string": "b"}, {}),
                ("Bash", {"command": "git status --short"}, {}),
                ("Bash", {"command": "rm -rf build"}, {"source": "user_reject", "decision": "reject"}),
                ("Bash", {"command": "cat x | sh"}, {}),
                ("Bash", {"command": "grep -r x ."}, {"reason": "safetyCheck"}),
                ("WebFetch", {"url": "https://docs.example.org/a"}, {}),
                ("Read", {"file_path": str(self.home / ".ssh/config")}, {}),
                ("Read", {"file_path": "/etc/hosts"}, {}),
                ("Bash", {"command": "make"}, {"source": "config"}))):  # (let through by your settings)
            s = t0 + (i + 1) * 100_000
            tr.reply(s, "r%d" % i, tools=[("T%d" % i, tool, inp)])
            tr.result(s + 60_000, "T%d" % i, **dict({"source": "user_temporary"}, **kw))
        tr.duration(t0 + 1200_000, 600_000)
        self.write(tr)


class PromptTests(Projects):
    """The permission prompts you answered, and rules that let them through."""

    def test_rules_for_the_prompts_you_answered(self):
        self.asked()
        p = self.recap()["prompts"]
        self.assertEqual((p["answered"], p["refused"], p["waitMs"]), (10, 1, 600_000))
        self.assertEqual(p["byTool"][:3], [["Bash", 4], ["Read", 4], ["Edit", 1]])
        rules = [(r["kind"], r["value"], r["count"], r["state"]) for r in p["rules"]]
        self.assertEqual(rules, [("dir", str(self.lib), 2, "new"), ("edits", str(self.app), 1, "new"),
                                 ("allow", "Bash(git status *)", 1, "new"),
                                 ("allow", "WebFetch(domain:docs.example.org)", 1, "new")])
        self.assertEqual(p["rules"][0]["title"], "Let chats in app use ~/repos/lib (read; edit too when they accept edits)")
        self.assertIn("additionalDirectories", p["rules"][0]["change"])

    def test_a_forked_chat_counts_its_prompts_and_compactions_once(self):
        t0 = self.t0
        original = (Transcript(str(self.app)).prompt(t0)
                    .reply(t0 + 1000, "a", tools=[("T1", "Bash", {"command": "git status"})])
                    .result(t0 + 61_000, "T1", source="user_temporary")
                    .reply(t0 + 62_000, "a2").compacted(t0 + 63_000).duration(t0 + 64_000, 4000))
        self.write(original, "chat-a")
        self.recap()
        fork = Transcript(str(self.app))
        fork.lines = [dict(e) for e in original.lines]  # (claude --resume --fork-session: a copy, then its own turns)
        fork.prompt(t0 + 600_000).reply(t0 + 601_000, "b").duration(t0 + 602_000, 2000)
        self.write(fork, "chat-b")
        r = self.recap()
        self.assertEqual((r["prompts"]["answered"], r["prompts"]["rules"][0]["count"], r["work"]["compactions"]), (1, 1, 1))
        p = week.permissions(self.scan(), self.profiles(), self.now, self.home)
        self.assertEqual(p["prompts"]["answered"], 1)

    def test_prompts_at_once_wait_once(self):
        t0, tr = self.t0, Transcript(str(self.app))
        tr.prompt(t0).reply(t0 + 1000, "a", tools=[("A", "Read", {"file_path": str(self.lib / "a")}),
                                                   ("B", "Read", {"file_path": str(self.lib / "b")})])
        tr.result(t0 + 61_000, "A", source="user_temporary").result(t0 + 61_000, "B", source="user_temporary")
        self.write(tr)
        p = self.recap()["prompts"]
        self.assertEqual((p["answered"], p["waitMs"], p["rules"][0]["waitMs"]), (2, 60_000, 60_000))

    def test_a_rule_your_settings_have_already(self):
        self.asked()
        # another account's settings don't count (Claude reads its own folder's), nor Don't ask mode (it refuses)
        cs.write_json_atomic(self.home / ".claude-personal/settings.json", {"permissions": {"allow": ["Bash(git status *)"]}})
        cs.write_json_atomic(self.settings, {"permissions": {"defaultMode": "dontAsk"}})
        states = {r["value"]: r["state"] for r in self.recap()["prompts"]["rules"]}
        self.assertEqual((states["Bash(git status *)"], states[str(self.app)]), ("new", "new"))
        cs.write_json_atomic(self.home / ".claude-work/settings.json", {"permissions": {"allow": ["Bash(git status *)"]}})
        states = {r["value"]: r["state"] for r in self.recap()["prompts"]["rules"]}
        self.assertEqual(states["Bash(git status *)"], "allowed")

    def test_a_rule_an_extra_claude_folders_settings_have(self):
        # an account in a Claude folder of the settings (--config-dir): its own settings.json counts too
        extra = self.home / "other-claude"
        (extra / "projects").mkdir(parents=True)
        cs.write_json_atomic(extra / "settings.json", {"permissions": {"allow": ["Bash(git status *)"]}})
        t0, tr = self.t0, Transcript(str(self.app))
        tr.prompt(t0).reply(t0 + 1000, "a", tools=[("T1", "Bash", {"command": "git status"})])
        tr.result(t0 + 61_000, "T1", source="user_temporary")
        (extra / "projects/-w").mkdir()
        (extra / "projects/-w/chat-x.jsonl").write_text(tr.text())
        profiles = cs.discover_profiles(self.home, [str(extra)])
        cache = {"files": {}}
        week.scan(profiles, cache, self.now)
        p = week.permissions(cache, profiles, self.now, self.home)
        self.assertEqual({r["value"]: r["state"] for r in p["prompts"]["rules"]}["Bash(git status *)"], "allowed")

    def test_allow_and_undo(self):
        self.asked()
        week.updated_cache(self.cache_root, self.profiles(), self.now)
        ok, message, rid = week.allow_rule(self.home, self.cache_root, "dir", str(self.lib), str(self.app))
        self.assertTrue(ok, message)
        self.assertEqual(json.loads(self.settings.read_text()), {"permissions": {"additionalDirectories": [str(self.lib)]}})
        states = {r["value"]: r["state"] for r in self.recap(added=week.load_added(self.cache_root))["prompts"]["rules"]}
        self.assertEqual(states[str(self.lib)], "added")
        self.assertEqual(week.undo_rule(self.home, self.cache_root, rid)[0], True)
        self.assertFalse(self.settings.exists())  # (the file it made, gone again)
        self.assertEqual(week.load_added(self.cache_root), [])
        self.assertFalse(week.undo_rule(self.home, self.cache_root, rid)[0])

    def test_a_settings_file_that_is_a_link_is_left_alone(self):
        # (a repo can ship .claude/settings.local.json -> the account's settings.json: Allow changed that)
        self.asked()
        week.updated_cache(self.cache_root, self.profiles(), self.now)
        account = self.home / ".claude/settings.json"
        cs.write_json_atomic(account, {"env": {"A": "1"}})
        self.settings.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(os.path.relpath(account, self.settings.parent), self.settings)
        ok, message, _ = week.allow_rule(self.home, self.cache_root, "edits", str(self.app), str(self.app))
        self.assertEqual((ok, message), (False, "~/repos/app/.claude/settings.local.json is a link to another file: "
                                                "Talpy Den doesn't change a rule through a link"))
        self.assertEqual(json.loads(account.read_text()), {"env": {"A": "1"}})
        os.unlink(self.settings)
        ok, _, rid = week.allow_rule(self.home, self.cache_root, "edits", str(self.app), str(self.app))
        self.assertTrue(ok)
        self.settings.unlink()  # (made a link after the rule went in: Undo leaves the account's file too)
        cs.write_json_atomic(account, {"permissions": {"defaultMode": "acceptEdits"}})
        os.symlink(account, self.settings)
        self.assertFalse(week.undo_rule(self.home, self.cache_root, rid)[0])
        self.assertEqual(json.loads(account.read_text()), {"permissions": {"defaultMode": "acceptEdits"}})

    def test_a_link_beside_the_settings_file_is_never_written_through(self):
        # (a repo could ship .claude/.settings.local.json.<pid>.tmp -> ~/.bashrc: the new file's name)
        self.asked()
        week.updated_cache(self.cache_root, self.profiles(), self.now)
        victim = self.home / ".bashrc"
        victim.write_text("alias ll='ls -l'\n")
        self.settings.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(victim, self.settings.with_name(".settings.local.json.%d.tmp" % os.getpid()))
        self.assertTrue(week.allow_rule(self.home, self.cache_root, "edits", str(self.app), str(self.app))[0])
        self.assertEqual(victim.read_text(), "alias ll='ls -l'\n")
        self.assertEqual(json.loads(self.settings.read_text()), {"permissions": {"defaultMode": "acceptEdits"}})

    def test_your_own_settings_stay(self):
        self.asked()
        week.updated_cache(self.cache_root, self.profiles(), self.now)
        mine = {"env": {"A": "1"}, "permissions": {"allow": ["Bash(make *)"], "defaultMode": "plan"}}
        cs.write_json_atomic(self.settings, mine)
        ids = [week.allow_rule(self.home, self.cache_root, kind, value, str(self.app))[2]
               for kind, value in (("edits", str(self.app)), ("allow", "Bash(git status *)"))]
        self.assertEqual(json.loads(self.settings.read_text())["permissions"],
                         {"allow": ["Bash(make *)", "Bash(git status *)"], "defaultMode": "acceptEdits"})
        self.assertEqual(week.allow_rule(self.home, self.cache_root, "allow", "Bash(git status *)", str(self.app))[:2],
                         (True, "Already allowed in ~/repos/app/.claude/settings.local.json"))
        for rid in ids:
            self.assertTrue(week.undo_rule(self.home, self.cache_root, rid)[0])
        self.assertEqual(json.loads(self.settings.read_text()), mine)

    def test_rules_it_never_writes(self):
        self.asked()
        week.updated_cache(self.cache_root, self.profiles(), self.now)
        app = str(self.app)
        for kind, value, project in (("allow", "Bash(ls *)", str(self.lib)),  # (no chat started there)
                                     ("allow", "Bash(rm *)", app), ("allow", "Bash(git status *) && rm", app),
                                     ("allow", "Read(**)", app), ("dir", str(self.lib / "src"), app),  # (not a project)
                                     ("dir", str(self.home / ".ssh"), app), ("dir", "/etc", app),
                                     ("edits", str(self.lib), app), ("allow", "Bash(ls *)", str(self.home / ".ssh")),
                                     ("allow", "Bash(ls *)", "relative/app"),
                                     # (commands whose options run programs, write files or delete branches)
                                     ("allow", "Bash(rg *)", app), ("allow", "Bash(tree *)", app),
                                     ("allow", "Bash(git branch *)", app), ("allow", "Bash(git diff *)", app),
                                     ("allow", "Bash(git log *)", app), ("allow", "Bash(git show *)", app)):
            ok, message, _ = week.allow_rule(self.home, self.cache_root, kind, value, project)
            self.assertFalse(ok, (kind, value, project))
        for command in ("rg --pre ./run.sh x .", "tree -o /home/u/.profile", "git branch -D main",
                        "git diff --output=/home/u/.bashrc", "git log -p", "git show HEAD"):
            self.assertIsNone(week.rule_for("Bash", command, "", app, str(self.home)), command)
        self.assertEqual(week.rule_for("Bash", "git status --short", "", app, str(self.home)), ("allow", "Bash(git status *)"))
        self.assertFalse(self.settings.exists())
        self.assertFalse((self.lib / ".claude").exists())
        cs.write_json_atomic(self.settings, ["not", "settings"])
        self.assertFalse(week.allow_rule(self.home, self.cache_root, "allow", "Bash(ls *)", app)[0])
        self.assertEqual(json.loads(self.settings.read_text()), ["not", "settings"])


class GrantedTests(Projects):
    """The permissions you gave: every rule and mode that lets chats go
    without asking, and revoking them."""

    def setUp(self):
        super().setUp()
        # one user settings file for both accounts (a link from each), and
        # the folders Claude ran in, as each account's .claude.json lists them
        self.user = self.home / ".claude-shared/settings.json"
        self.user.parent.mkdir()
        cs.write_json_atomic(self.user, {"model": "opus", "permissions": {"allow": ["Bash(npm test *)"], "defaultMode": "default"}})
        for name in ("work", "personal"):
            (self.home / (".claude-" + name) / "settings.json").symlink_to(self.user)
        data = json.loads((self.home / ".claude-work/.claude.json").read_text())
        data["projects"] = {str(self.app): {}, str(self.lib): {}, "/gone": {}}
        (self.home / ".claude-work/.claude.json").write_text(json.dumps(data))
        cs.write_json_atomic(self.settings, {"permissions": {"allow": ["Bash(git status *)", "WebFetch(domain:docs.example.org)"],
                                                             "additionalDirectories": [str(self.lib)], "defaultMode": "acceptEdits"}})
        self.settings.chmod(0o644)
        cs.write_json_atomic(self.app / ".claude/settings.json", {"permissions": {"allow": ["WebSearch"], "deny": ["Bash(rm *)"]}})

    def granted(self):
        profiles = self.profiles()
        return week.granted_rules(self.home, week.rule_folders(self.home, {"files": {}}, profiles), profiles,
                                  week.load_added(self.cache_root))

    def revoke(self, kind, value):
        rid = next(g["id"] for g in self.granted() if (g["kind"], g["value"]) == (kind, value))
        return week.revoke_rule(self.home, self.cache_root, self.profiles(), rid)

    def test_every_rule_that_lets_chats_go_without_asking(self):
        self.assertEqual([(g["kind"], g["value"], g["title"], g["place"], g["where"]) for g in self.granted()], [
            ("allow", "Bash(npm test *)", "Run “npm test *”", "every chat of personal, work", "~/.claude-shared/settings.json"),
            ("mode", "acceptEdits", "Accept file edits without asking", "chats started in app", "~/repos/app/.claude/settings.local.json"),
            ("dir", str(self.lib), "Use files in ~/repos/lib (read; edit too when chats accept edits)", "chats started in app", "~/repos/app/.claude/settings.local.json"),
            ("allow", "Bash(git status *)", "Run “git status *”", "chats started in app", "~/repos/app/.claude/settings.local.json"),
            ("allow", "WebFetch(domain:docs.example.org)", "Open pages from docs.example.org", "chats started in app",
             "~/repos/app/.claude/settings.local.json"),
            ("allow", "WebSearch", "WebSearch", "chats started in app (shared through git)", "~/repos/app/.claude/settings.json")])
        self.assertEqual([g["shared"] for g in self.granted()], [False] * 5 + [True])
        self.assertEqual(self.granted()[3]["change"],
                         "takes Bash(git status *) out of permissions.allow in ~/repos/app/.claude/settings.local.json")

    def test_revoke_takes_it_out_of_its_file(self):
        self.addCleanup(os.umask, os.umask(0o077))  # (as week.py runs)
        self.assertTrue(self.revoke("allow", "Bash(git status *)")[0])
        self.assertTrue(self.revoke("dir", str(self.lib))[0])
        self.assertEqual(self.revoke("mode", "acceptEdits"), (True, "Revoked: Accept file edits without asking "
                                                                    "(~/repos/app/.claude/settings.local.json)"))
        self.assertEqual(json.loads(self.settings.read_text()), {"permissions": {"allow": ["WebFetch(domain:docs.example.org)"]}})
        self.assertEqual(self.settings.stat().st_mode & 0o777, 0o644)  # (who may read it stays as it was)
        # your user settings: the rest of the file stays, the links stay links
        self.assertTrue(self.revoke("allow", "Bash(npm test *)")[0])
        self.assertEqual(json.loads(self.user.read_text()), {"model": "opus", "permissions": {"defaultMode": "default"}})
        self.assertTrue((self.home / ".claude-work/settings.json").is_symlink())

    def test_what_it_never_revokes(self):
        shared = self.app / ".claude/settings.json"
        before = shared.read_text()
        self.assertEqual(self.revoke("allow", "WebSearch"),
                         (False, "~/repos/app/.claude/settings.json is shared through git: change it there"))
        self.assertEqual(shared.read_text(), before)
        self.assertEqual(week.revoke_rule(self.home, self.cache_root, self.profiles(), "0123456789ab"),
                         (False, "That rule isn't in your settings any more"))

    def test_a_folders_settings_outside_a_repository_arent_shared(self):
        (self.app / ".git").rmdir()
        g = self.granted()[-1]
        self.assertEqual((g["value"], g["place"], g["shared"]), ("WebSearch", "chats started in app", False))

    def test_the_permissions_tab_has_this_weeks_prompts_and_the_permissions_you_gave(self):
        self.asked()
        out = week.permissions(self.scan(), self.profiles(), self.now, self.home)
        self.assertEqual((out["prompts"]["answered"], out["prompts"]["refused"]), (10, 1))
        self.assertEqual([r["value"] for r in out["prompts"]["rules"]][:1], [str(self.lib)])
        self.assertEqual([(g["kind"], g["value"]) for g in out["granted"]], [(g["kind"], g["value"]) for g in self.granted()])
        later = self.now + 8 * week.DAY_MS  # (a week on, those prompts are gone)
        self.assertEqual(week.permissions(self.scan(), self.profiles(), later, self.home)["prompts"]["answered"], 0)

    def test_trusted_folders_and_what_claude_json_keeps(self):
        claude_json = self.home / ".claude-work/.claude.json"
        data = json.loads(claude_json.read_text())
        data["bypassPermissionsModeAccepted"] = True
        data["projects"] = {str(self.app): {"hasTrustDialogAccepted": True, "allowedTools": ["Bash(make *)"],
                                            "enabledMcpjsonServers": ["db"], "enableAllProjectMcpServers": True},
                            str(self.lib): {"hasTrustDialogAccepted": False},
                            "/gone": {"hasTrustDialogAccepted": True}}  # (a folder deleted: nothing to trust)
        claude_json.write_text(json.dumps(data))
        kept = [(g["kind"], g["value"], g["folder"], g["place"]) for g in self.granted() if g["where"] == "~/.claude-work/.claude.json"]
        self.assertEqual(kept, [
            ("flag", "bypassPermissionsModeAccepted", "", "every chat of work"),
            ("trust", str(self.app), str(self.app), "for work"),
            ("allow", "Bash(make *)", str(self.app), "chats started in app, for work"),
            ("mcp", "db", str(self.app), "chats started in app, for work"),
            ("flag", "enableAllProjectMcpServers", str(self.app), "chats started in app, for work")])
        for kind, value in (("trust", str(self.app)), ("allow", "Bash(make *)"), ("mcp", "db"), ("flag", "enableAllProjectMcpServers"),
                            ("flag", "bypassPermissionsModeAccepted")):
            rid = next(g["id"] for g in self.granted() if (g["kind"], g["value"]) == (kind, value) and g["where"].endswith(".claude.json"))
            self.assertTrue(week.revoke_rule(self.home, self.cache_root, self.profiles(), rid)[0], (kind, value))
        after = json.loads(claude_json.read_text())
        self.assertEqual(after["projects"][str(self.app)], {"hasTrustDialogAccepted": False, "allowedTools": [],
                                                            "enabledMcpjsonServers": [], "enableAllProjectMcpServers": False})
        self.assertIs(after["bypassPermissionsModeAccepted"], False)
        self.assertEqual(after["oauthAccount"], data["oauthAccount"])  # (the rest stays)
        self.assertFalse([g for g in self.granted() if g["where"].endswith(".claude.json")])

    def test_settings_that_loosen_a_check_and_the_administrators(self):
        cs.write_json_atomic(self.user, {"skipDangerousModePermissionPrompt": True, "sandbox": {"autoAllowBashIfSandboxed": True},
                                         "enabledMcpjsonServers": ["github"], "skipAutoPermissionPrompt": False})
        managed = Path(self.tmp.name) / "etc-claude-code"
        managed.mkdir()
        cs.write_json_atomic(managed / "managed-settings.json", {"permissions": {"allow": ["Bash(ls *)"]}})
        with mock.patch.object(week, "MANAGED_DIR", managed):
            granted = self.granted()
            self.assertEqual([(g["kind"], g["value"], g["shared"]) for g in granted[:4]], [
                ("allow", "Bash(ls *)", True),  # (the administrator's first, not changed here)
                ("flag", "skipDangerousModePermissionPrompt", False), ("flag", "sandbox.autoAllowBashIfSandboxed", False),
                ("mcp", "github", False)])
            self.assertEqual(granted[0]["place"], "every chat (set by your administrator)")
            self.assertFalse(week.revoke_rule(self.home, self.cache_root, self.profiles(), granted[0]["id"])[0])
            for g in granted[1:4]:
                self.assertTrue(week.revoke_rule(self.home, self.cache_root, self.profiles(), g["id"])[0], g["value"])
        self.assertEqual(json.loads(self.user.read_text()), {"skipDangerousModePermissionPrompt": False,
                                                              "sandbox": {"autoAllowBashIfSandboxed": False},
                                                              "skipAutoPermissionPrompt": False})  # (an emptied list goes)

    def test_revoking_a_rule_the_recap_allowed_puts_back_what_was_before(self):
        self.asked()
        week.updated_cache(self.cache_root, self.profiles(), self.now)
        cs.write_json_atomic(self.settings, {"permissions": {"defaultMode": "plan"}})
        self.assertTrue(week.allow_rule(self.home, self.cache_root, "edits", str(self.app), str(self.app))[0])
        mode = next(g for g in self.granted() if g["kind"] == "mode")
        self.assertTrue(mode["added"])
        self.assertTrue(self.revoke("mode", "acceptEdits")[0])
        self.assertEqual(json.loads(self.settings.read_text()), {"permissions": {"defaultMode": "plan"}})
        self.assertEqual(week.load_added(self.cache_root), [])


RATES = """<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01" xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
<Cube><Cube time='2026-10-23'><Cube currency='USD' rate='1.1250'/><Cube currency='GBP' rate='0.8500'/></Cube></Cube>
</gesmes:Envelope>"""


class CurrencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.fetched = 0

    def fetch(self, text=RATES):
        def get():
            self.fetched += 1
            if text is None:
                raise OSError("offline")
            return text
        return get

    def test_the_ecbs_rates(self):
        self.assertEqual(week.parse_rates(RATES), {"date": "2026-10-23", "rates": {"USD": 1.125, "GBP": 0.85, "EUR": 1.0}})
        self.assertIsNone(week.parse_rates("<html>maintenance</html>"))
        eur = week.currency_of("eur", self.root, 1000, self.fetch())
        self.assertEqual((eur["code"], round(eur["rate"], 4), eur["date"]), ("EUR", 0.8889, "2026-10-23"))
        gbp = week.currency_of("GBP", self.root, 2000, self.fetch(None))  # (the saved rates: fetched a moment ago)
        self.assertEqual((round(gbp["rate"], 4), self.fetched), (0.7556, 1))

    def test_offline_the_last_rates_serve(self):
        week.currency_of("EUR", self.root, 1000, self.fetch())
        later = week.currency_of("EUR", self.root, 1000 + week.RATES_EVERY_S + 1, self.fetch(None))
        self.assertEqual((later["code"], later["date"], self.fetched), ("EUR", "2026-10-23", 2))
        week.currency_of("EUR", self.root, 1000 + week.RATES_EVERY_S + 60, self.fetch(None))  # (not again so soon)
        self.assertEqual(self.fetched, 2)
        week.currency_of("EUR", self.root, 1000 + week.RATES_EVERY_S + week.RATES_RETRY_S + 2, self.fetch())
        self.assertEqual(self.fetched, 3)

    def test_dollars_need_nothing(self):
        self.assertEqual(week.currency_of("USD", self.root, 1000, self.fetch(None)),
                         {"code": "USD", "rate": 1.0, "date": "", "error": ""})
        self.assertEqual(week.currency_of("../x", self.root, 1000, self.fetch(None))["code"], "USD")
        self.assertEqual(self.fetched, 0)
        none = week.currency_of("EUR", self.root, 1000, self.fetch(None))
        self.assertEqual(none["code"], "USD")
        self.assertIn("European Central Bank", none["error"])
        self.assertIn("XYZ", week.currency_of("XYZ", self.root, 1000, self.fetch())["error"])


sys.path.insert(0, str(ROOT / "tests"))
from test_remote import FakeSSH  # noqa: E402  (a stand-in ssh: runs the command here, in a made-up home)


class HostTests(FakeSSH):
    """An SSH host's week: this file runs there (on python3's stdin, after
    talpy_den.py) and sends its chats of those days back."""

    def test_an_ssh_hosts_chats(self):
        now = int(time.time() * 1000)
        t0 = now - 3600_000
        tr = Transcript("/srv/x").prompt(t0).reply(t0 + 1000, "r").duration(t0 + 60_000, 60_000)
        (self.fake_home / ".claude/projects/-p/chat-r.jsonl").write_text(tr.text())
        source = week.host_chats("lab", 0)
        self.assertTrue(source["ok"], source)
        self.assertEqual(list(source["chats"]), ["chat-r"])
        # (the days shown here, not the host's: it sends what's between the times asked for)
        self.assertEqual(week.host_chats("lab", 1, "day", since=now + 7200_000, until=now + 7300_000)["chats"], {})
        r = week.recap([{"host": "", "chats": {}, "accounts": []}, source], 0, "", now, Path(self.tmp.name))
        self.assertEqual((r["sum"]["workedMs"], r["projects"][0]["host"], r["sources"][1]["ok"]), (60_000, "lab", True))

    def test_an_ssh_hosts_permissions_and_revoking_one_there(self):
        proj = self.fake_home / "proj"
        (proj / ".claude").mkdir(parents=True)
        (proj / ".claude/settings.local.json").write_text(json.dumps({"permissions": {"allow": ["Bash(make *)"]}}))
        claude_json = self.fake_home / ".claude/.claude.json"
        data = json.loads(claude_json.read_text())
        data["projects"] = {str(proj): {"hasTrustDialogAccepted": True}}
        claude_json.write_text(json.dumps(data))
        source = week.host_permissions("lab")
        self.assertTrue(source["ok"], source)
        self.assertEqual(sorted((g["kind"], g["value"]) for g in source["granted"]), [("allow", "Bash(make *)"), ("trust", str(proj))])
        import io
        from contextlib import redirect_stdout
        rid = next(g["id"] for g in source["granted"] if g["kind"] == "allow")
        out = io.StringIO()
        with redirect_stdout(out):
            week.main(["--revoke", rid, "--on", "lab"])
        self.assertTrue(json.loads(out.getvalue())["ok"], out.getvalue())
        self.assertEqual(json.loads((proj / ".claude/settings.local.json").read_text()), {})
        self.assertEqual([g["kind"] for g in week.host_permissions("lab")["granted"]], ["trust"])

    def test_a_hosts_hours_follow_its_clock_as_its_turns_do(self):
        import remote
        now = int(time.time() * 1000)
        h = now // week.HOUR_MS * week.HOUR_MS - 5 * week.HOUR_MS  # (by the host's clock, 2 hours behind)
        hour = dict(week.new_hour(), p=[[h + 700_000, "Bash", "make", "", 0, True]])
        chat = {"turns": [[h + 600_000, h + 1200_000, 600_000, []]], "prompts": [h + 600_000], "limits": [],
                "hours": {week.hour_key(h): hour}}
        answer = {"ok": True, "now": now - 2 * week.HOUR_MS, "chats": {"c": chat}, "accounts": []}
        with mock.patch.object(remote, "host_answer", return_value=answer):
            c = week.host_chats("lab", 0)["chats"]["c"]
        shift = c["turns"][0][0] - (h + 600_000)
        self.assertGreaterEqual(shift, 2 * week.HOUR_MS)
        ((key, agg),) = c["hours"].items()
        self.assertEqual((week.hour_ms(key), agg["p"][0][0]), (h + shift, h + 700_000 + shift))

    def test_a_host_that_turns_you_away(self):
        self.mode("denied")
        source = week.host_chats("lab", 0)
        self.assertFalse(source["ok"])
        self.assertIn("refused", source["error"])


class OutputTests(Home):
    def test_main_prints_the_recap(self):
        import io
        from contextlib import redirect_stdout
        t0 = self.t0
        self.write(Transcript().prompt(t0).reply(t0 + 1000, "a").duration(t0 + 2000, 2000))
        out = io.StringIO()
        saved = dict(os.environ)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(saved)))
        os.environ["HOME"], os.environ["XDG_CACHE_HOME"] = str(self.home), str(self.cache_root)
        real_time = week.time.time
        week.time.time = lambda: self.now / 1000
        self.addCleanup(setattr, week.time, "time", real_time)
        with redirect_stdout(out):
            week.main([])
        result = json.loads(out.getvalue())
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["sum"]["turns"], 1)
        self.assertEqual(result["currency"]["code"], "USD")
        self.assertTrue((self.cache_root / "talpy-den" / week.CACHE_FILE).is_file())
        out = io.StringIO()
        with redirect_stdout(out):
            week.main(["--data", "--remote"])
        text = out.getvalue()
        answer = json.loads(text[text.rfind("\n" + cs.REMOTE_MARK) + 1 + len(cs.REMOTE_MARK):])
        self.assertEqual(list(answer["chats"]), ["chat-a"])
        # the times the computer asking wants (its days, by its calendar), as they are on this clock
        for since, until, now, chats in ((t0 + 7200_000, self.now, self.now, []), (t0 - 60_000, t0 + 60_000, self.now, ["chat-a"]),
                                         (t0 + 9000_000, self.now, self.now + 3 * 3600_000, ["chat-a"])):
            out = io.StringIO()
            with redirect_stdout(out):
                week.main(["--data", "--remote", "--since", str(since), "--until", str(until), "--now", str(now)])
            text = out.getvalue()
            answer = json.loads(text[text.rfind("\n" + cs.REMOTE_MARK) + 1 + len(cs.REMOTE_MARK):])
            self.assertEqual(list(answer["chats"]), chats, (since, until, now))

    def test_the_monday_recap_counts_the_ssh_hosts_shown(self):
        import io
        from contextlib import redirect_stdout
        from unittest import mock
        self.write(Transcript().prompt(self.t0).reply(self.t0 + 1000, "a").duration(self.t0 + 2000, 2000))
        saved = dict(os.environ)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(saved)))
        os.environ["HOME"], os.environ["XDG_CACHE_HOME"] = str(self.home), str(self.cache_root)
        real_time = week.time.time
        week.time.time = lambda: self.now / 1000
        self.addCleanup(setattr, week.time, "time", real_time)

        def host(name, back, span, since, until):  # (the same chats, as a host's: remote.py would run week.py --data there)
            cache = week.load_cache(cs.cache_dir(self.home))
            return {"host": name, "chats": week.chats_between(cache, self.profiles(), since, until, self.home), "accounts": []}

        def monday(*args):
            out = io.StringIO()
            with mock.patch.object(week, "monday_due", return_value="2026-W45"), \
                    mock.patch.object(week, "host_chats", side_effect=host), redirect_stdout(out):
                week.main(["--monday-recap", *args])
            return json.loads(out.getvalue())
        self.assertEqual(monday()["chats"], 1)
        self.assertEqual(monday("--host", "lab")["chats"], 2)

    def test_a_hidden_project_is_left_out_of_the_projects_tab(self):
        import io
        from contextlib import redirect_stdout
        self.write(Transcript().prompt(self.t0).reply(self.t0 + 1000, "a").duration(self.t0 + 2000, 2000))
        saved = dict(os.environ)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(saved)))
        os.environ["HOME"], os.environ["XDG_CACHE_HOME"] = str(self.home), str(self.cache_root)

        def projects():
            out = io.StringIO()
            with redirect_stdout(out):
                week.main(["--projects"])
            return json.loads(out.getvalue())
        result = projects()
        self.assertEqual((len(result["projects"]), result["hidden"], result["hiddenPaths"]), (1, 0, []))
        row = result["projects"][0]
        self.assertEqual(([c["sessionId"] for c in row["chats"]], row["accounts"], row["recap"], row["plans"]),
                         (["chat-a"], ["work"], None, []))
        hid = result["projects"][0]["path"]
        cs.hide_item(cs.cache_dir(self.home), "projects", hid)
        result = projects()
        # (a hidden project's folder is said, so its open chats show in no other project)
        self.assertEqual((result["projects"], result["hidden"], result["hiddenPaths"]), ([], 1, [hid]))


if __name__ == "__main__":
    unittest.main()


class MondayRecapTests(unittest.TestCase):
    """The Monday recap (week.py --monday-recap): once a week, Monday from 9
    o'clock or the first check after, for whichever copy asks first."""

    def test_once_a_week_from_monday_morning(self):
        cache = Path(tempfile.mkdtemp())
        monday = time.mktime((2026, 10, 26, 10, 0, 0, 0, 0, -1))
        self.assertIsNone(week.monday_due(cache, monday))                     # (installed now: from next week on)
        self.assertEqual(week.monday_due(cache, monday + 7 * 86400), "2026-W45")
        self.assertIsNone(week.monday_due(cache, monday + 7 * 86400 + 60))     # (another copy asks: once)
        self.assertIsNone(week.monday_due(cache, monday + 14 * 86400 - 3 * 3600))   # (Monday 7:00)
        self.assertEqual(week.monday_due(cache, monday + 16 * 86400), "2026-W46")   # (off on Monday: Wednesday)
        self.assertEqual(json.loads((cache / week.MONDAY_FILE).read_text())["week"], "2026-W46")

    def test_the_plasma_notification_shows_a_projects_name_as_written(self):
        # (a folder named '<a href="file:&#47;&#47;&#47;…">Open the Recap' was a link in the popup)
        main = (ROOT / "package/contents/ui/main.qml").read_text()
        self.assertIn('{ title: i18n("Your week with Claude"), text: root.escapeHtml(lines.join("\\n")) }', main)


class LaneTests(unittest.TestCase):
    """The Day view's lanes (week.day_lanes): each chat's day, worked, waited for you, paused."""

    def test_a_chats_day_in_stretches(self):
        h = 3_600_000
        chats = [
            {"key": "|a", "id": "a" * 8, "host": "", "name": "fix parser", "folder": "", "profiles": [".claude"],
             "turns": [[1 * h, 3 * h, 0, [[2 * h, 2 * h + 600_000, "y"]], {}], [5 * h, 6 * h, 0, [[5 * h, 5 * h + 1800_000, "p"]], {}]]},
            {"key": "|b", "id": "b" * 8, "host": "lab", "name": "train", "folder": "", "profiles": [],
             "turns": [[-2 * h, 30 * 60_000, 0, [], {}]]},
            {"key": "|c", "id": "c" * 8, "host": "", "name": "old", "folder": "", "profiles": [], "turns": [[-5 * h, -4 * h, 0, [], {}]]},
        ]
        lanes = week.day_lanes(chats, 0, 24 * h, Path("/home/x"))
        self.assertEqual([l["id"] for l in lanes], ["b" * 8, "a" * 8])     # (in the order they began; none for c)
        self.assertEqual(lanes[0]["parts"], [[0, 30 * 60_000, "w"]])        # (clipped to the day)
        a = lanes[1]
        self.assertEqual([p[2] for p in a["parts"]], ["w", "y", "w", "p", "w"])
        self.assertEqual(a["waitedMs"], 600_000)
        self.assertEqual(a["workedMs"], 2 * h - 600_000 + h - 1800_000)


class ProjectTests(unittest.TestCase):
    """The Projects tab (week.projects): chats, plans and memories by project, newest first."""

    def test_a_worktrees_chat_is_its_repositorys(self):
        home = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(home))
        repo, wt = home / "repo", home / "repo/.claude/worktrees/w1"
        (repo / ".git/worktrees/w1").mkdir(parents=True)
        (wt / "src").mkdir(parents=True)
        (wt / ".git").write_text("gitdir: %s\n" % (repo / ".git/worktrees/w1"))
        (repo / ".git/worktrees/w1/commondir").write_text("../..\n")
        (repo / ".git/worktrees/w1/gitdir").write_text("%s\n" % (wt / ".git"))
        self.assertEqual(week.project_of(str(wt / "src"), home, {}), str(repo))

    def test_projects_with_their_chats_plans_and_memories_newest_first(self):
        now = 100 * 86400_000
        home = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(home))
        app, web = home / "r/app", home / "r/web"
        (app / ".git").mkdir(parents=True)
        (app / "sub").mkdir()
        chat = lambda cid, project, name, turns, prompts=(), profiles=(".claude-work",): {
            "id": cid, "project": project, "folder": project and project + "/sub", "name": name, "profiles": list(profiles),
            "hours": {}, "turns": turns, "prompts": list(prompts)}
        chats = [chat("a" * 8, str(app), "fix it", [[now - 2 * 86400_000, now - 2 * 86400_000 + 3600_000, 3600_000, [], {}]]),
                 chat("b" * 8, str(app), "old one", [[now - 30 * 86400_000, now - 30 * 86400_000 + 600_000, 600_000, [], {}]],
                      profiles=(".claude-personal",)),
                 chat("c" * 8, str(web), "today", [[now - 3600_000, now - 60_000, 1800_000, [], {}]]),
                 chat("d" * 8, "", "nowhere", [[now - 60_000, now, 60_000, [], {}]]),
                 chat("e" * 8, "/r/empty", "never", []),
                 chat("g" * 8, str(web), "deleted since", [[now - 60_000, now, 60_000, [], {}]])]
        plans = [{"slug": "p1", "title": "Plan one", "cwd": str(app / "sub"), "profileDir": ".claude-work", "updatedAt": now - 10},
                 {"slug": "p2", "title": "Plan two", "cwd": "", "profileDir": ".claude-work", "updatedAt": now - 20}]
        memories = [{"key": "m1", "name": "notes", "folder": str(app), "profileDir": ".claude-work", "updatedAt": now - 30},
                     {"key": "m2", "name": "gone", "folder": str(home / "r/gone"), "profileDir": ".claude-work",
                      "updatedAt": now - 40 * 86400_000}]
        accounts = {".claude-work": "work", ".claude-personal": "personal"}
        there = {"a" * 8, "b" * 8, "c" * 8, "d" * 8, "e" * 8}
        rows = week.projects(chats, now, home, plans, memories, accounts, starred={"b" * 8}, there=there)
        self.assertEqual([p["name"] for p in rows], ["web", "app", "gone", ""])   # (a plan whose chat is gone: last)
        web_row, app_row, gone, nowhere = rows
        self.assertEqual(([c["name"] for c in web_row["chats"]], web_row["chatCount"]), (["today"], 1))  # (not the deleted one)
        self.assertEqual(([c["name"] for c in app_row["chats"]], app_row["chatCount"]), (["fix it", "old one"], 2))
        first, second = app_row["chats"]
        self.assertEqual({k: first[k] for k in ("sessionId", "cwd", "cwdShort", "profileDir", "account", "starred")},
                         {"sessionId": "a" * 8, "cwd": str(app / "sub"), "cwdShort": "~/r/app/sub",
                          "profileDir": ".claude-work", "account": "work", "starred": False})
        self.assertEqual((second["account"], second["starred"]), ("personal", True))
        self.assertEqual(sorted(app_row["accounts"]), ["personal", "work"])      # (its lines get an account tag)
        self.assertEqual(([p["slug"] for p in app_row["plans"]], [m["key"] for m in app_row["memories"]]), (["p1"], ["m1"]))
        self.assertEqual(app_row["plans"][0]["account"], "work")
        self.assertNotIn("workedMs", app_row)                                     # (no time or money: the Recap has them)
        self.assertEqual((gone["gone"], gone["lastAt"], gone["chatCount"], app_row["gone"]), (True, now - 40 * 86400_000, 0, False))
        self.assertEqual(([p["slug"] for p in nowhere["plans"]], nowhere["path"]), (["p2"], ""))
        # a chat Claude moved to the background under a new id is that one now: its old id
        # isn't listed apart once the new one is (talpy_den.chat_moves)
        moved = chats + [chat("f" * 8, str(app), "fix it", [[now - 60_000, now, 60_000, [], {}]])]
        rows = week.projects(moved, now, home, accounts=accounts, there=there | {"f" * 8},
                             moves={"a" * 8: "f" * 8, "b" * 8: "9" * 8})
        app_row = next(p for p in rows if p["name"] == "app")
        self.assertEqual([c["sessionId"] for c in app_row["chats"]], ["f" * 8, "b" * 8])  # (b's new one isn't there)
