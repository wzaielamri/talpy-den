"""Which chats the widget lists, where, and how they relate to shared chats.

Scenarios are built from the files Claude Code writes (sessions/, jobs/,
projects/ transcripts, status-line snapshots, prompt history) and the
hard links / locks of a shared-chat tool, then checked against what the
widget must show.
"""
import importlib.util
import json
import os
import random
import shlex
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("talpy_den_chats", ROOT / "package/contents/code/talpy_den.py")
cs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cs)

PID = os.getpid()
PROC_START = cs.proc_start_time(PID)
PROJECT = "-w-proj"


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z")


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data))


def jl(entries):
    return "".join(json.dumps(e, separators=(",", ":")) + "\n" for e in entries)


def user(uuid, ts, sid, text="hi", parent=None):
    return {"type": "user", "uuid": uuid, "parentUuid": parent, "timestamp": iso(ts), "sessionId": sid,
            "message": {"role": "user", "content": text}}


def reply(uuid, ts, sid, text="ok", parent=None, stop="end_turn", **kw):
    return {"type": "assistant", "uuid": uuid, "parentUuid": parent, "timestamp": iso(ts), "sessionId": sid,
            "message": {"id": "msg_" + uuid, "role": "assistant", "content": [{"type": "text", "text": text}],
                        "stop_reason": stop, "model": "claude-opus-5-5",
                        "usage": {"input_tokens": 1, "output_tokens": 2}}, **kw}


def continued(sid, new):
    return {"type": "continued-in", "timestamp": iso(time.time()), "sessionId": sid, "continuedInSessionId": new}


def title(sid, text):
    return {"type": "ai-title", "aiTitle": text, "sessionId": sid}


class World(unittest.TestCase):
    """Two accounts: personal (Pro) and work (Team)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.home, self.cache, self.state = root / "home", root / "cache", root / "state"
        self.now = time.time()
        os.environ["XDG_STATE_HOME"] = str(self.state)
        self.addCleanup(os.environ.pop, "XDG_STATE_HOME", None)
        self.children = []
        self.profile("personal", "acct-p", "claude_pro")
        self.profile("work", "acct-w", "claude_team")

    def tearDown(self):
        for child in self.children:
            child.kill()
            child.wait()
        self.tmp.cleanup()

    # -- building the world

    def dir(self, prof):
        return self.home / f".claude-{prof}"

    def profile(self, name, account, plan):
        d = self.dir(name)
        write(d / ".profile-name", name + "\n")
        write(d / ".claude.json", {"oauthAccount": {"accountUuid": account, "organizationType": plan}})
        (d / "sessions").mkdir(parents=True, exist_ok=True)
        (d / "projects").mkdir(parents=True, exist_ok=True)

    def link_default(self, prof, age=0):
        """~/.claude as a link to a profile, made `age` seconds ago."""
        link = self.home / ".claude"
        if link.is_symlink():
            link.unlink()
        link.symlink_to(self.dir(prof))
        t = self.now - age
        os.utime(link, (t, t), follow_symlinks=False)

    def transcript(self, prof, sid, entries, project=PROJECT, age=None):
        path = self.dir(prof) / "projects" / project / f"{sid}.jsonl"
        write(path, jl(entries))
        if age is not None:
            os.utime(path, (self.now - age, self.now - age))
        return path

    def append(self, prof, sid, entries, project=PROJECT):
        with open(self.dir(prof) / "projects" / project / f"{sid}.jsonl", "a") as f:
            f.write(jl(entries))

    def share(self, sid, src, dst, project=PROJECT):
        a = self.dir(src) / "projects" / project / f"{sid}.jsonl"
        b = self.dir(dst) / "projects" / project / f"{sid}.jsonl"
        b.parent.mkdir(parents=True, exist_ok=True)
        os.link(a, b)

    def job(self, prof, job_id, age, state="stopped", tempo="idle", **kw):
        rec = {"state": state, "tempo": tempo, "sessionId": job_id, "resumeSessionId": job_id,
               "cwd": "/w/proj", "name": kw.pop("name", job_id), "createdAt": iso(self.now - age - 600),
               "updatedAt": iso(self.now - age), **kw}
        write(self.dir(prof) / "jobs" / job_id[:8] / "state.json", rec)
        return rec

    def live(self, prof, stem, sid, pid=PID, start=PROC_START, **kw):
        entry = {"pid": pid, "procStart": start, "sessionId": sid, "cwd": "/w/proj", "kind": "interactive",
                 "status": "idle", "statusUpdatedAt": int(self.now * 1000), "startedAt": int(self.now * 1000) - 60000, **kw}
        write(self.dir(prof) / "sessions" / f"{stem}.json", entry)
        return entry

    def spawn(self, env_dir=None):
        """A real process (for liveness and its config dir)."""
        env = dict(os.environ)
        env.pop("CLAUDE_CONFIG_DIR", None)
        env["HOME"] = str(self.home)
        if env_dir is not None:
            env["CLAUDE_CONFIG_DIR"] = str(env_dir)
        child = subprocess.Popen(["sleep", "120"], env=env)
        self.children.append(child)
        # Popen returns before exec has set up the new environment, and
        # /proc/<pid>/environ reads empty until it has
        for _ in range(500):
            if cs.proc_start_time(child.pid) and cs.process_config_dir(child.pid):
                break
            time.sleep(0.01)
        return child.pid, cs.proc_start_time(child.pid)

    def snapshot(self, dirname, sid, age, **data):
        path = self.cache / "statusline" / dirname / f"{sid}.json"
        write(path, {"session_id": sid, **data})
        t = self.now - age
        os.utime(path, (t, t))

    def prompt(self, prof, sid, age, project="/w/proj"):
        with open(self.dir(prof) / "history.jsonl", "a") as f:
            f.write(json.dumps({"display": "go", "timestamp": int((self.now - age) * 1000),
                                "project": project, "sessionId": sid}) + "\n")

    def lock(self, sid, prof, age, pid=4194311, start="1"):
        path = self.state / "claude-shared-chats" / f"lock-{sid}"
        write(path, f"{pid}-{start} {self.dir(prof)}\n")
        os.utime(path, (self.now - age, self.now - age))

    # -- reading the result

    def collect(self, **kw):
        kw.setdefault("with_tokens", False)
        return cs.collect(self.home, self.cache, now=kw.pop("now", self.now), **kw)

    def listing(self, r=None):
        """{account: [(session id, kind, state, chat id, relation)]} + {account: [links]}."""
        r = r or self.collect()
        rows, links = {}, {}
        for g in r["groups"]:
            out = []
            for s in g["sessions"]:
                info = s["shared"] or {}
                rel = "copy" if info.get("forkOf") else "shared" if info else ""
                out.append((s["sessionId"], s["kind"], s["state"], s["chatId"], rel))
            rows[g["name"]] = out
            links[g["name"]] = [(h["sessionId"], h["profile"], h["copy"]) for h in g["sharedHere"]]
        return rows, links

    def row(self, r, sid):
        return next(s for g in r["groups"] for s in g["sessions"] if s["sessionId"] == sid)


class ProfileLinkTests(World):
    """~/.claude as a link that the user switches between profiles."""

    def test_rows_keyed_by_real_folder(self):
        self.link_default("personal", age=100)
        self.live("personal", "50", "chat-a")
        r = self.collect()
        s = self.row(r, "chat-a")
        self.assertEqual((s["profileDir"], s["key"]), (".claude-personal", ".claude-personal/chat-a/live"))
        g = next(g for g in r["groups"] if g["name"] == "personal")
        self.assertEqual((g["chatProfile"], g["profileKeys"]), (".claude-personal", [".claude-personal"]))

    def test_snapshot_under_link_name_only_counts_after_the_switch(self):
        # Before the switch (link made 600 s ago) ~/.claude meant work
        self.link_default("personal", age=600)
        self.snapshot(".claude", "old", age=900, rate_limits={"five_hour": {"used_percentage": 88}})
        r = self.collect()
        personal = next(g for g in r["groups"] if g["name"] == "personal")
        self.assertIsNone(personal["limits"])  # work's numbers aren't personal's
        self.snapshot(".claude", "new", age=60, rate_limits={"five_hour": {"used_percentage": 12}})
        personal = next(g for g in self.collect()["groups"] if g["name"] == "personal")
        self.assertEqual(personal["limits"]["windows"][0]["pct"], 12)
        # the real folder's name always counts, whatever its age
        self.snapshot(".claude-personal", "realname", age=30, rate_limits={"five_hour": {"used_percentage": 7}})
        personal = next(g for g in self.collect()["groups"] if g["name"] == "personal")
        self.assertEqual(personal["limits"]["windows"][0]["pct"], 7)

    def test_context_from_newest_valid_snapshot(self):
        self.link_default("personal", age=600)
        self.live("personal", "50", "chat-a", startedAt=int((self.now - 1500) * 1000))  # (its snapshots are this run's)
        self.snapshot(".claude", "chat-a", age=900, context_window={"used_percentage": 90})   # before the switch
        self.snapshot(".claude-personal", "chat-a", age=1200, context_window={"used_percentage": 40})
        self.assertEqual(self.row(self.collect(), "chat-a")["context"], 40)
        self.snapshot(".claude", "chat-a", age=10, context_window={"used_percentage": 55})
        self.assertEqual(self.row(self.collect(), "chat-a")["context"], 55)

    def test_tokens_dont_move_with_the_link(self):
        self.link_default("work", age=3600)
        self.transcript("work", "w1", [reply("w-1", self.now - 50, "w1")])
        self.transcript("personal", "p1", [reply("p-1", self.now - 50, "p1")])
        r = self.collect(with_tokens=True)
        by = {g["name"]: g["tokens"]["today"]["messages"] for g in r["groups"]}
        self.assertEqual(by, {"personal": 1, "work": 1})
        # The user switches ~/.claude to personal: still one message each
        self.link_default("personal", age=0)
        r = self.collect(with_tokens=True, now=self.now + cs.TOKEN_SCAN_INTERVAL + 1)
        by = {g["name"]: g["tokens"]["today"]["messages"] for g in r["groups"]}
        self.assertEqual(by, {"personal": 1, "work": 1})
        names = sorted(p.name for p in self.cache.glob("tokens-*.json"))
        self.assertEqual(len(names), 2)
        self.assertTrue(all(n.startswith(("tokens-.claude-personal-", "tokens-.claude-work-")) for n in names))

    def test_old_token_caches_removed(self):
        write(self.cache / "tokens-.claude.json", {"version": 2})
        self.collect(with_tokens=True)
        self.assertFalse((self.cache / "tokens-.claude.json").exists())


class LiveAttributionTests(World):
    def test_same_process_in_two_profiles_listed_once_where_it_runs(self):
        # Started on work through ~/.claude, which was then switched to personal:
        # the process follows the link, and its old file stays in work.
        self.link_default("personal", age=100)
        pid, start = self.spawn(env_dir=self.home / ".claude")
        self.live("work", str(pid), "chat-a", pid=pid, start=start, status="busy", statusUpdatedAt=1000)
        self.live("personal", str(pid), "chat-a", pid=pid, start=start, status="idle", statusUpdatedAt=2000)
        rows, _ = self.listing()
        self.assertEqual(rows, {"personal": [("chat-a", "interactive", "idle", "chat-a", "")], "work": []})

    def test_process_listed_under_the_profile_it_runs_on(self):
        self.link_default("personal", age=100)
        pid, start = self.spawn(env_dir=self.home / ".claude")
        self.live("work", str(pid), "chat-a", pid=pid, start=start, status="busy")   # not rewritten yet
        rows, _ = self.listing()
        self.assertEqual(rows["personal"], [("chat-a", "interactive", "working", "chat-a", "")])
        self.assertEqual(rows["work"], [])

    def test_unknown_config_dir_keeps_the_file_profile(self):
        pid, start = self.spawn(env_dir=Path(self.tmp.name) / "elsewhere")
        self.live("work", str(pid), "chat-a", pid=pid, start=start)
        rows, _ = self.listing()
        self.assertEqual([r[0] for r in rows["work"]], ["chat-a"])

    def test_default_config_dir_from_the_process_home(self):
        self.link_default("work", age=100)
        pid, start = self.spawn(env_dir=None)  # no CLAUDE_CONFIG_DIR: $HOME/.claude
        self.live("personal", str(pid), "chat-a", pid=pid, start=start)
        rows, _ = self.listing()
        self.assertEqual([r[0] for r in rows["work"]], ["chat-a"])

    def test_job_in_two_profiles_listed_once(self):
        self.job("work", "aaaaaaaa", age=600)
        self.job("personal", "aaaaaaaa", age=60, state="done")
        rows, _ = self.listing()
        self.assertEqual(rows, {"personal": [("aaaaaaaa", "bg", "done", "aaaaaaaa", "")], "work": []})


class ChatLinkTests(World):
    """chatId and the relation to shared chats."""

    def shared_chat(self, sid="T", owner="personal", other="work", n=3):
        entries, parent = [], None
        for i in range(n):
            entries += [user(f"{sid}-u{i}", self.now - 3000 + i * 10, sid, parent=parent),
                        reply(f"{sid}-a{i}", self.now - 2995 + i * 10, sid, parent=f"{sid}-u{i}")]
            parent = f"{sid}-a{i}"
        self.transcript(owner, sid, entries)
        self.share(sid, owner, other)

    def test_shared_chat_itself(self):
        self.shared_chat()
        self.job("work", "T", age=60)
        r = self.collect()
        self.assertEqual(self.row(r, "T")["shared"]["profiles"], ["work", "personal"])

    def test_background_session_writing_into_the_chat(self):
        self.shared_chat()
        self.transcript("work", "J", [title("J", "t")])  # its own file: a title only
        self.job("work", "J", age=60, resumeSessionId="T")
        r = self.collect()
        s = self.row(r, "J")
        self.assertEqual((s["chatId"], s["shared"]["continues"]), ("T", "T"))

    def test_continuation_named_by_continued_in_record(self):
        self.shared_chat()
        self.transcript("work", "J", [title("J", "t")])
        self.job("work", "J", age=60)  # resumeSessionId is its own id
        self.append("personal", "T", [continued("T", "J")])
        s = self.row(self.collect(), "J")
        self.assertEqual((s["chatId"], s["shared"]["continues"]), ("T", "T"))

    def test_continuation_without_own_transcript_found_through_cwd(self):
        self.shared_chat()
        self.job("work", "J", age=60)  # no J.jsonl at all
        self.append("personal", "T", [continued("T", "J")])
        s = self.row(self.collect(), "J")
        self.assertEqual(s["chatId"], "T")

    def test_copy_found_by_its_history(self):
        # Forked in a terminal (no job, no link at all): the copy starts with
        # the chat's history, so its first entry is in the shared transcript
        self.shared_chat()
        copied = [{"type": "file-history-snapshot", "messageId": "x"},
                  {"type": "system", "subtype": "compact_boundary", "uuid": "T-a1", "sessionId": "S"},
                  user("S-u0", self.now - 100, "S", parent="T-a1")]
        self.transcript("personal", "S", copied)
        self.live("personal", "50", "S")
        s = self.row(self.collect(), "S")
        self.assertEqual((s["chatId"], s["shared"]["forkOf"], s["shared"]["forkOn"]), ("S", "T", "personal"))

    def test_new_conversation_is_not_a_copy(self):
        # The continued-in record names the job, but the job started blank
        self.shared_chat()
        self.transcript("work", "N", [user("N-u0", self.now - 50, "N"), reply("N-a0", self.now - 45, "N")])
        self.job("work", "J", age=30, resumeSessionId="N")
        self.live("work", "60", "N", kind="bg", jobId="J", status="busy")
        self.append("personal", "T", [continued("T", "J"), user("T-later", self.now - 20, "T"),
                                      reply("T-later-a", self.now - 15, "T")])
        s = self.row(self.collect(), "N")
        self.assertEqual((s["chatId"], s["shared"]), ("N", None))

    def test_copy_named_by_its_job(self):
        self.shared_chat()
        self.transcript("work", "F", [user("F-u0", self.now - 50, "F")])
        self.job("work", "F", age=30, forkParentSessionId="T")
        s = self.row(self.collect(), "F")
        self.assertEqual(s["shared"]["forkOf"], "T")

    def test_first_uuid_skips_entries_without_one(self):
        cache = cs.LinkCache(self.cache / "links.json")
        path = self.transcript("personal", "X", [{"type": "file-history-snapshot"}, title("X", "t"),
                                                  user("X-first", self.now, "X"), user("X-second", self.now, "X")])
        self.assertEqual(cache.first_uuid(path), "X-first")


class LinkCacheTests(World):
    def test_incremental_scan(self):
        path = self.transcript("personal", "T", [user("u1", self.now, "T"), reply("a1", self.now, "T")])
        cache = cs.LinkCache(self.cache / "links.json")
        rec = cache.transcript(path)
        self.assertEqual((rec["conts"], rec["final"] > 0), ([], True))
        size = rec["size"]
        cache.save()
        # appended: a continued-in record and a half-written line
        with open(path, "a") as f:
            f.write(json.dumps(continued("T", "J"), separators=(",", ":")) + "\n" + '{"type":"assi')
        cache2 = cs.LinkCache(self.cache / "links.json")
        reads = []
        real_open = open

        def spy(file, mode="r", *a, **kw):
            reads.append(file)
            return real_open(file, mode, *a, **kw)
        cs.open = spy
        try:
            rec2 = cache2.transcript(path)
        finally:
            del cs.open
        self.assertEqual([c[0] for c in rec2["conts"]], ["J"])
        self.assertEqual(rec2["conts"][0][1], size)          # offset of the new line
        self.assertLess(rec2["size"], path.stat().st_size)   # half-written line left for later
        self.assertEqual(len(reads), 1)

    def test_finished_reply_rules(self):
        ok = reply("a", self.now, "T")
        self.assertTrue(cs.finished_reply(ok))
        self.assertFalse(cs.finished_reply({**ok, "isApiErrorMessage": True}))
        self.assertFalse(cs.finished_reply(reply("b", self.now, "T", stop=None)))
        self.assertFalse(cs.finished_reply(user("c", self.now, "T")))


class MovedOnTests(World):
    """Claude's rule: a chat whose last `continued-in` record comes after its
    last finished reply moved on to that session."""

    def setUp(self):
        super().setUp()
        self.transcript("work", "T", [user("T-u0", self.now - 9000, "T"), reply("T-a0", self.now - 8990, "T", parent="T-u0")])
        self.share("T", "work", "personal")
        self.job("work", "T", age=7200)  # stopped when it moved on
        copied = [{"type": "system", "subtype": "compact_boundary", "uuid": "T-a0", "sessionId": "S"},
                  user("S-u0", self.now - 400, "S"), reply("S-a0", self.now - 390, "S")]
        self.transcript("personal", "S", copied)

    def test_chat_that_moved_to_a_copy_is_listed_as_the_copy(self):
        self.job("personal", "S", age=300, state="failed")
        self.append("work", "T", [continued("T", "S")])
        rows, links = self.listing()
        self.assertEqual(rows, {"personal": [("S", "bg", "done", "S", "copy")], "work": []})
        self.assertEqual(links, {"personal": [], "work": [("S", "personal", True)]})
        r = self.collect()
        info = self.row(r, "S")["shared"]
        self.assertEqual((info["forkOf"], info["movedHere"], info["stoppedCopies"]), ("T", True, ["work"]))

    def test_chat_used_after_the_record_did_not_move(self):
        self.job("personal", "S", age=300, state="failed")
        self.append("work", "T", [continued("T", "S"), user("T-u1", self.now - 200, "T"),
                                  reply("T-a1", self.now - 190, "T")])
        rows, links = self.listing()
        self.assertEqual(rows["work"], [("T", "bg", "done", "T", "shared")])
        self.assertEqual(rows["personal"], [("S", "bg", "done", "S", "copy")])
        self.assertEqual(links, {"personal": [], "work": []})   # a copy isn't linked; T is listed

    def test_api_error_after_the_record_still_moved(self):
        self.job("personal", "S", age=300, state="failed")
        self.append("work", "T", [continued("T", "S"), reply("T-err", self.now - 100, "T", isApiErrorMessage=True)])
        rows, _ = self.listing()
        self.assertEqual(rows["work"], [])

    def test_moved_to_a_session_that_isnt_listed(self):
        self.append("work", "T", [continued("T", "S")])  # S has no row (no job, not running)
        rows, links = self.listing()
        self.assertEqual(rows, {"personal": [], "work": [("T", "bg", "done", "T", "shared")]})
        self.assertEqual(links["personal"], [("T", "work", False)])

    def test_chat_that_moved_to_a_copy_that_was_shared_too(self):
        # The copy was shared back, so it's a shared chat of its own (no
        # forkOf); the chat it continues still moved on and isn't listed
        # (seen 2026-10-15: listed twice, linked from both accounts)
        self.share("S", "personal", "work")
        self.live("work", "71", "S", status="busy")
        self.append("work", "T", [continued("T", "S")])
        rows, links = self.listing()
        self.assertEqual(rows, {"personal": [], "work": [("S", "interactive", "working", "S", "shared")]})
        self.assertEqual(links, {"personal": [("S", "work", False)], "work": []})
        r = self.collect(recent=5)
        self.assertNotIn("T", [c["sessionId"] for g in r["groups"] for c in g["recent"]])

    def test_running_chat_is_listed_even_if_it_had_moved(self):
        self.job("personal", "S", age=300, state="failed")
        self.append("work", "T", [continued("T", "S")])
        self.live("work", "70", "T", status="busy")  # resumed again, no reply yet
        r = self.collect()
        rows, _ = self.listing(r)
        self.assertEqual(rows["work"], [("T", "interactive", "working", "T", "shared")])
        self.assertNotIn("movedHere", self.row(r, "S")["shared"])  # the chat is listed itself


class PlacementTests(World):
    """A finished shared chat is listed under the account it was used on last."""

    def setUp(self):
        super().setUp()
        self.transcript("work", "T", [user("T-u0", self.now - 9000, "T"), reply("T-a0", self.now - 8990, "T")])
        self.share("T", "work", "personal")
        self.job("work", "T", age=7200, detail="all done")

    def test_record_stays_without_later_use(self):
        rows, links = self.listing()
        self.assertEqual(rows, {"personal": [], "work": [("T", "bg", "done", "T", "shared")]})
        self.assertEqual(links["personal"], [("T", "work", False)])

    def test_used_later_on_another_account_moves_there(self):
        self.prompt("personal", "T", age=600)
        r = self.collect()
        rows, links = self.listing(r)
        self.assertEqual(rows, {"personal": [("T", "chat", "done", "T", "shared")], "work": []})
        self.assertEqual(links["work"], [("T", "personal", False)])
        s = self.row(r, "T")
        self.assertEqual((s["profileDir"], s["key"], s["since"], s["reason"], s["detail"], s["pid"]),
                         (".claude-personal", ".claude-personal/T/chat", int((self.now - 600) * 1000), "", "", None))
        self.assertEqual(s["shared"]["stoppedCopies"], ["work"])
        work = next(g for g in r["groups"] if g["name"] == "work")
        self.assertTrue(work["sharedHere"][0]["stoppedHere"])

    def test_snapshot_evidence(self):
        self.snapshot(".claude-personal", "T", age=600, context_window={"used_percentage": 61})
        r = self.collect()
        s = self.row(r, "T")
        self.assertEqual((s["profileDir"], s["kind"], s["context"]), (".claude-personal", "chat", 61))

    def test_lock_evidence(self):
        self.lock("T", "personal", age=600)
        self.assertEqual(self.row(self.collect(), "T")["profileDir"], ".claude-personal")

    def test_close_times_dont_move_it(self):
        self.prompt("personal", "T", age=7200 - 30)  # within a minute of the record
        self.assertEqual(self.row(self.collect(), "T")["profileDir"], ".claude-work")

    def test_snapshot_under_a_link_from_before_the_switch_is_no_evidence(self):
        self.link_default("personal", age=300)
        self.snapshot(".claude", "T", age=600)  # ~/.claude meant work then
        self.assertEqual(self.row(self.collect(), "T")["profileDir"], ".claude-work")
        self.snapshot(".claude", "T", age=100)  # after the switch: personal
        self.assertEqual(self.row(self.collect(), "T")["profileDir"], ".claude-personal")

    def test_records_on_both_accounts_keep_the_newest_users(self):
        self.job("personal", "J", age=3600, resumeSessionId="T")
        self.transcript("personal", "J", [title("J", "t")])
        rows, links = self.listing()
        self.assertEqual(rows, {"personal": [("J", "bg", "done", "T", "shared")], "work": []})
        self.assertEqual(links["work"], [("J", "personal", False)])
        self.prompt("work", "T", age=60)  # then used on work again
        rows, _ = self.listing()
        self.assertEqual(rows, {"personal": [], "work": [("T", "bg", "done", "T", "shared")]})

    def test_running_chat_stays_where_it_runs(self):
        self.prompt("work", "T", age=10)
        self.live("personal", "50", "T", status="busy")
        rows, links = self.listing()
        self.assertEqual(rows, {"personal": [("T", "interactive", "working", "T", "shared")], "work": []})
        self.assertEqual(links["work"], [("T", "personal", False)])

    def test_dismissed_chat_stays_hidden_after_moving(self):
        self.prompt("personal", "T", age=600)
        cs.private_dir(self.cache)
        cs.save_dismissed(self.cache, {"T": 1})
        r = self.collect()
        self.assertEqual((self.listing(r)[0], r["dismissed"]), ({"personal": [], "work": []}, 1))

    def test_a_copy_doesnt_hide_a_chat_that_never_moved_on(self):
        # Shared chat A, finished, no `continued-in`; copied in a terminal on
        # personal (copy B starts with A's history)
        history = [user("A-u1", self.now - 4000, "A"), reply("A-a1", self.now - 3990, "A", parent="A-u1")]
        self.transcript("work", "A", history, age=3000)
        self.share("A", "work", "personal")
        self.job("work", "A", age=3000, state="done")
        self.transcript("personal", "B", [*history, user("B-u2", self.now - 20, "B", parent="A-a1")])
        self.live("personal", "50", "B")
        r = self.collect(recent=5)
        rows, _ = self.listing(r)
        self.assertIn(("A", "bg", "done", "A", "shared"), rows["work"])
        b = self.row(r, "B")
        self.assertEqual(b["shared"]["forkOf"], "A")
        self.assertNotIn("movedHere", b["shared"])

    def test_not_shared_chats_never_move(self):
        self.transcript("work", "U", [user("U-u0", self.now - 9000, "U")])
        self.job("work", "U", age=7200)
        self.prompt("personal", "U", age=60)
        self.assertEqual(self.row(self.collect(), "U")["profileDir"], ".claude-work")


class SharedPointerTests(unittest.TestCase):
    def test_a_chat_listed_twice_gets_one_pointer(self):
        # one shared chat open on two accounts at once, and shared with a third
        def row(prof):
            return {"key": f".claude-{prof}/X", "sessionId": "X", "chatId": "X", "name": "x", "cwdShort": "~/w",
                    "state": "working", "reason": "", "since": 1, "profile": prof, "profileDir": f".claude-{prof}",
                    "shared": {"profiles": ["personal", "work", "team"]}}
        groups = [{"profiles": ["personal"], "sessions": [row("personal")]},
                  {"profiles": ["work"], "sessions": [row("work")]}, {"profiles": ["team"], "sessions": []}]
        cs.link_shared_elsewhere(groups)
        self.assertEqual([(h["sessionId"], h["profile"]) for h in groups[2]["sharedHere"]], [("X", "personal")])
        self.assertEqual((groups[0]["sharedHere"], groups[1]["sharedHere"]), ([], []))


class RecentChatTests(World):
    def recent(self, r=None, **kw):
        r = r or self.collect(**kw)
        return {g["name"]: [(c["sessionId"], c["name"]) for c in g["recent"]] for g in r["groups"]}

    def chat(self, prof, sid, age, entries=None, project=PROJECT):
        return self.transcript(prof, sid, entries or [user(f"{sid}-u", self.now - age, sid, text=f"about {sid}"),
                                                      reply(f"{sid}-a", self.now - age, sid)], project=project, age=age)

    def test_newest_first_not_listed_and_limited(self):
        for i, age in enumerate([50, 400, 300, 200, 100, 600]):
            self.chat("work", f"c{i}", age)
        self.job("work", "c0", age=10)  # listed as a session: not a recent chat
        got = self.recent(recent=3)
        self.assertEqual(got["work"], [("c4", "about c4"), ("c3", "about c3"), ("c2", "about c2")])
        self.assertEqual(self.recent(recent=0), {"personal": [], "work": []})

    def test_all_recent_chats_are_counted(self):
        # (for "Show N more" and "Recent chats (3 of 5)": the first page listed, all of them counted)
        for i, age in enumerate([50, 400, 300, 200, 100, 600]):
            self.chat("work", f"c{i}", age)
        self.chat("personal", "p0", 70)
        self.job("work", "c0", age=10)  # listed as a session: not counted
        self.transcript("work", "empty", [{"type": "ai-title", "aiTitle": "nothing said"}], age=30)  # no messages: neither
        groups = {g["name"]: g for g in self.collect(recent=3)["groups"]}
        self.assertEqual((len(groups["work"]["recent"]), groups["work"]["recentCount"]), (3, 5))
        self.assertEqual((len(groups["personal"]["recent"]), groups["personal"]["recentCount"]), (1, 1))
        # a copy of a chat (its first entry the same) counts once, as it's listed once
        self.chat("work", "c4copy", 20, [user("c4-u", self.now - 100, "c4", text="about c4"), reply("x-a", self.now - 20, "x")])
        work = next(g for g in self.collect(recent=10)["groups"] if g["name"] == "work")
        self.assertEqual([c["sessionId"] for c in work["recent"]], ["c4copy", "c3", "c2", "c1", "c5"])
        self.assertEqual(work["recentCount"], 5)
        # none asked for: none counted
        self.assertEqual(next(g for g in self.collect(recent=0)["groups"] if g["name"] == "work")["recentCount"], 0)

    def test_past_the_checked_ones_chats_are_counted_by_their_files(self):
        for i in range(6):
            self.chat("work", f"c{i}", 50 + i * 10)
        self.transcript("work", "empty", [{"type": "ai-title", "aiTitle": "nothing said"}], age=500)
        with mock.patch.object(cs, "RECENT_CHECKED", 2):
            work = next(g for g in self.collect(recent=2)["groups"] if g["name"] == "work")
        self.assertEqual(([c["sessionId"] for c in work["recent"]], work["recentCount"]), (["c0", "c1"], 7))
        work = next(g for g in self.collect(recent=2)["groups"] if g["name"] == "work")
        self.assertEqual(work["recentCount"], 6)

    def test_starred_chats_stay_listed_however_old(self):
        for i, age in enumerate([50, 400, 300, 200, 100, 600]):
            self.chat("work", f"c{i}", age)
        self.job("work", "c0", age=10)  # listed as a session: marked there, not repeated
        for sid in ("c5", "c4", "c0"):
            cs.change_stars(self.cache, "chats", sid)
        cs.change_stars(self.cache, "chats", "c1", host="lab")  # an SSH host's chat of that id: not this one
        work = next(g for g in self.collect(recent=3)["groups"] if g["name"] == "work")
        self.assertEqual([(c["sessionId"], c["starred"]) for c in work["recent"]], [("c4", True), ("c3", False), ("c2", False)])
        self.assertEqual([(c["sessionId"], c["key"]) for c in work["starred"]],
                         [("c4", ".claude-work/c4/starred"), ("c5", ".claude-work/c5/starred")], "newest first")
        self.assertTrue(next(s for s in work["sessions"] if s["sessionId"] == "c0")["starred"])
        # also with no recent chats asked for; not any more once unstarred
        cs.change_stars(self.cache, "chats", "c5", on=False)
        work = next(g for g in self.collect(recent=0)["groups"] if g["name"] == "work")
        self.assertEqual(([c["sessionId"] for c in work["starred"]], work["recent"]), (["c4"], []))
        # a host's status run gets the host's (from the computer that asks), not the cache's
        self.assertEqual(cs.starred_of(cs.load_stars(self.cache), "lab"), {"chats": {"c1"}, "plans": set()})
        work = next(g for g in self.collect(recent=3, starred=cs.starred_of(cs.load_stars(self.cache), "lab"))["groups"]
                    if g["name"] == "work")
        self.assertEqual([c["sessionId"] for c in work["starred"]], ["c1"])

    def test_name_precedence(self):
        def base(sid):  # each chat's own entries (same uuids would make them copies of each other)
            return [user(f"{sid}-u", self.now - 9, sid, text="first prompt here"), reply(f"{sid}-a", self.now - 9, sid)]
        self.chat("work", "n1", 10, base("n1"))
        self.chat("work", "n2", 20, base("n2") + [title("n2", "ai title")])
        self.chat("work", "n3", 30, [{"type": "agent-name", "agentName": "my session"}] + base("n3") + [title("n3", "ai")])
        self.chat("work", "n4", 40, base("n4") + [{"type": "custom-title", "customTitle": "renamed"},
                                                   {"type": "agent-name", "agentName": "session"}])
        meta = [user("m", self.now - 9, "x", text="<command-name>/model</command-name>"),
                {**user("m2", self.now - 9, "x", text="caveat"), "isMeta": True}, reply("a2", self.now - 9, "x")]
        self.chat("work", "n5", 50, meta + [user("m3", self.now - 8, "x", text="real question")])
        self.assertEqual(self.recent()["work"], [("n1", "first prompt here"), ("n2", "ai title"),
                                                 ("n3", "my session"), ("n4", "renamed"), ("n5", "real question")])

    def test_one_odd_line_doesnt_empty_the_list(self):
        self.chat("work", "ok1", 10)
        self.transcript("work", "odd", [{"type": "user", "message": "just a string"}, reply("odd-a", self.now - 20, "odd")],
                        age=20)
        self.assertEqual([sid for sid, _ in self.recent()["work"]], ["ok1", "odd"])

    def test_a_chat_that_moved_on_to_a_listed_session_isnt_recent(self):
        # C continued in background session J, whose transcript starts with C's history
        history = [user("C-u", self.now - 900, "C", text="about C"), reply("C-a", self.now - 890, "C")]
        self.transcript("work", "C", history + [{"type": "continued-in", "continuedInSessionId": "J"}], age=800)
        self.transcript("work", "J", history + [user("J-u", self.now - 30, "J", parent="C-a")])
        self.job("work", "J", age=30, state="blocked", tempo="blocked")
        self.assertNotIn("C", [sid for sid, _ in self.recent()["work"]])

    def test_skips_empty_and_orphaned(self):
        self.chat("work", "ok1", 10)
        self.transcript("work", "empty", [title("empty", "only a title")], age=5)
        self.transcript("work", "ok1.orphaned-1-x", [user("o", self.now, "ok1")], age=1)
        self.assertEqual(self.recent()["work"], [("ok1", "about ok1")])

    def test_removed_from_the_list_shows_as_recent(self):
        # a stopped background session, then hidden with its remove button
        self.chat("work", "older", 900)
        self.chat("work", "job1", 60)
        self.job("work", "job1", age=30, state="stopped")
        r = self.collect()
        self.assertEqual([s["sessionId"] for g in r["groups"] for s in g["sessions"]], ["job1"])
        self.assertEqual(self.recent(r)["work"], [("older", "about older")])
        cs.private_dir(self.cache)
        cs.save_dismissed(self.cache, {"job1": 1})
        r = self.collect()
        self.assertEqual([s["sessionId"] for g in r["groups"] for s in g["sessions"]], [])
        self.assertEqual(self.recent(r)["work"], [("job1", "about job1"), ("older", "about older")])

    def test_copies_listed_once(self):
        orig = [user("same-first", self.now - 500, "o1"), reply("o1-a", self.now - 490, "o1")]
        self.chat("work", "o1", 500, orig)
        self.chat("work", "o2", 100, orig + [user("o2-more", self.now - 100, "o2")])  # a copy, used later
        self.assertEqual([c[0] for c in self.recent()["work"]], ["o2"])

    def test_shared_chat_under_the_account_used_last(self):
        self.chat("work", "sh", 300)
        self.share("sh", "work", "personal")
        self.prompt("work", "sh", age=300)
        self.assertEqual(self.recent(), {"personal": [], "work": [("sh", "about sh")]})
        self.prompt("personal", "sh", age=60)
        got = self.collect()
        self.assertEqual(self.recent(got), {"personal": [("sh", "about sh")], "work": []})
        item = next(g for g in got["groups"] if g["name"] == "personal")["recent"][0]
        self.assertEqual((item["shared"], item["profileDir"], item["cwd"]), (True, ".claude-personal", ""))

    def test_moved_on_chat_not_recent(self):
        self.transcript("work", "T", [user("T-u0", self.now - 9000, "T"), reply("T-a0", self.now - 8990, "T")])
        self.share("T", "work", "personal")
        self.transcript("personal", "S", [{"type": "system", "subtype": "compact_boundary", "uuid": "T-a0"},
                                          user("S-u0", self.now - 400, "S"), reply("S-a0", self.now - 390, "S")])
        self.job("personal", "S", age=300, state="failed")
        self.append("work", "T", [continued("T", "S")])
        self.assertEqual(self.recent(), {"personal": [], "work": []})

    def test_names_cached_until_the_file_grows(self):
        path = self.chat("work", "c1", 10)
        self.collect()
        calls = []
        real = cs.read_chat_info
        cs.read_chat_info = lambda p, size: calls.append(p) or real(p, size)
        try:
            self.collect()
            self.assertEqual(calls, [])
            with open(path, "a") as f:
                f.write(json.dumps({"type": "custom-title", "customTitle": "new name"}) + "\n")
            self.assertEqual(self.recent()["work"], [("c1", "new name")])
            self.assertEqual(len(calls), 1)
        finally:
            cs.read_chat_info = real


class RemoteModeTests(World):
    """What the widget gets from a host it reaches over SSH."""

    def run_remote(self, *args, path_dirs=()):
        fake_bin = self.home / ".local/bin"
        fake_bin.mkdir(parents=True, exist_ok=True)
        claude = fake_bin / "claude"
        claude.write_text("#!/bin/sh\n")
        claude.chmod(0o755)
        env = {"HOME": str(self.home), "PATH": ":".join([*path_dirs, str(self.home / "no-bin")]),
               "XDG_CACHE_HOME": str(self.cache), "XDG_STATE_HOME": str(self.state)}
        out = subprocess.run([sys.executable, "-I", "-", "--remote", "--no-tokens", *args], env=env,
                             input=(ROOT / "package/contents/code/talpy_den.py").read_text(),
                             capture_output=True, text=True, check=True).stdout
        mark = out.rindex("@@talpy-den@@ ")
        return json.loads(out[mark + len("@@talpy-den@@ "):]), claude

    def test_rows_carry_their_commands(self):
        folder = self.home / "proj"
        folder.mkdir(parents=True)
        self.job("work", "j1", age=60, state="done", cwd=str(folder))
        pid, start = self.spawn()
        self.live("work", str(pid), "j2", pid=pid, start=start, kind="bg", jobId="j2", status="busy", cwd=str(folder))
        self.job("work", "j2", age=1, state="working", tempo="active", cwd=str(folder))
        self.transcript("work", "old", [user("o", self.now - 900, "old", text="old chat"), reply("oa", self.now - 900, "old"),
                                        {"type": "user", "cwd": str(folder), "sessionId": "old"}])
        with open(self.dir("work") / "history.jsonl", "w") as f:
            f.write(json.dumps({"project": str(folder), "timestamp": int(self.now * 1000), "sessionId": "old"}) + "\n")
        r, claude = self.run_remote()
        self.assertEqual(r["claude"], str(claude))  # found though it's not on PATH
        work = next(g for g in r["groups"] if g["name"] == "work")
        rows = {s["sessionId"]: s for s in work["sessions"]}
        cfg = shlex.quote(str(self.dir("work").resolve()))
        cd = f"cd {shlex.quote(str(folder))} 2>/dev/null; "
        trust = "printf '%s\\n\\n' 'Claude will ask whether you trust ~/proj before it reopens this chat."
        self.assertTrue(rows["j1"]["openCommand"].startswith(cd + trust), rows["j1"]["openCommand"])
        self.assertTrue(rows["j1"]["openCommand"].endswith(f"env -u CLAUDE_CODE_DISABLE_AGENT_VIEW CLAUDE_CONFIG_DIR={cfg} {claude} attach j1"))
        self.assertIsNone(rows["j1"]["stopCommand"])  # no process to stop
        self.assertEqual(rows["j2"]["stopCommand"], f"env -u CLAUDE_CODE_DISABLE_AGENT_VIEW CLAUDE_CONFIG_DIR={cfg} {claude} stop j2")
        (recent,) = work["recent"]
        self.assertTrue(recent["openCommand"].endswith(f"CLAUDE_CONFIG_DIR={cfg} {claude} --resume old"))
        self.assertEqual(work["projects"][0]["newChatCommand"],
                         cd + f"CLAUDE_CODE_DISABLE_AGENT_VIEW=1 CLAUDE_CONFIG_DIR={cfg} {claude}")
        self.assertTrue(work["homeChatCommand"].startswith(f"cd {shlex.quote(str(self.home))} 2>/dev/null; "))

    def test_marker_after_noisy_login_output(self):
        # the JSON is found after the marker even if something printed before it
        r, _ = self.run_remote()
        self.assertTrue(r["ok"])
        self.assertIn("host", r)

    def test_dismiss_over_the_wire(self):
        env = {"HOME": str(self.home), "PATH": "/usr/bin:/bin", "XDG_CACHE_HOME": str(self.cache)}
        script = (ROOT / "package/contents/code/talpy_den.py").read_text()
        out = subprocess.run([sys.executable, "-I", "-", "--remote", "--dismiss", "abc"], env=env, input=script,
                             capture_output=True, text=True, check=True).stdout
        self.assertEqual(json.loads(out.split("@@talpy-den@@ ")[-1])["ok"], True)
        self.assertIn("abc", cs.load_dismissed(self.cache / "talpy-den"))
        subprocess.run([sys.executable, "-I", "-", "--undismiss-all"], env=env, input=script, check=True,
                       capture_output=True, text=True)
        self.assertEqual(cs.load_dismissed(self.cache / "talpy-den"), {})


class RecurringTests(unittest.TestCase):
    """Claude Code 2.1.300: routines, self-waking and /loop jobs aren't done between runs."""

    def test_loop_jobs(self):
        job = {"state": "done", "tempo": "idle", "intent": "  /LOOP 5m check the deploy"}
        self.assertTrue(cs.is_recurring(job))
        self.assertEqual(cs.session_state({"status": "idle"}, job), "working")
        self.assertTrue(cs.is_recurring({"initialPrompt": "/loop"}))
        self.assertFalse(cs.is_recurring({"intent": "please /loop later"}))

    def test_parked_recurring_job_between_runs(self):
        now = 1_800_000_000_000
        job = {"state": "done", "tempo": "idle", "routine": {}, "updatedAt": iso((now - 9 * 86400_000) / 1000)}
        self.assertEqual(cs.parked_job_state(job, False, now, 86400_000), ("working", ""))
        self.assertEqual(cs.parked_job_state({**job, "tempo": "blocked"}, False, now, 86400_000), ("waiting", ""))
        self.assertEqual(cs.parked_job_state({**job, "routine": None, "state": "failed"}, False, now, 86400_000), None)


class TranscriptFileTests(World):
    def test_follows_linked_folders_and_marks_them_shared(self):
        store = self.home / ".claude-shared/chats" / PROJECT / "T"
        write(store / "subagents/agent-a1.jsonl", jl([reply("sub-1", self.now - 5, "T")]))
        target = self.dir("work") / "projects" / PROJECT / "T"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(store)
        (store / "loop").symlink_to(store)  # a loop must not hang the scan
        self.transcript("work", "own", [reply("own-1", self.now - 5, "own")])
        work = next(p for p in cs.discover_profiles(self.home) if p.label == "work")
        files = sorted((p.name, linked) for p, linked in cs.transcript_files(work))
        self.assertEqual(files, [("agent-a1.jsonl", True), ("own.jsonl", False)])
        tokens = next(g for g in self.collect(with_tokens=True)["groups"] if g["name"] == "work")["tokens"]
        self.assertEqual((tokens["today"]["messages"], tokens["today"]["shared"]), (2, 3))


class RealDayTests(World):
    """The day the widget got this wrong, replayed: a chat started on work,
    shared, moved to personal in a terminal, handed to a background session
    there, which later forked it; meanwhile a blank background session on work."""

    def test_replay(self):
        now = self.now
        T, S, F, A = "1a2b3c4d", "5e6f7a8b", "9c0d1e2f", "3a4b5c6d"
        # a background chat on work, shared, then stopped on work
        self.transcript("work", T, [user("u0", now - 36000, T), reply("a0", now - 35990, T, parent="u0"),
                                    {"type": "system", "subtype": "compact_boundary", "uuid": "cb1", "sessionId": T}])
        self.share(T, "work", "personal")
        self.job("work", T, age=20000, detail="stopped from session", name="parser rewrite")
        self.snapshot(".claude-work", T, age=20000, context_window={"used_percentage": 87})
        # a background session on work names the chat, then dies unused
        self.append("work", T, [continued(T, F)])
        # ... while the chat goes on in a terminal on personal
        self.append("work", T, [user("u1", now - 18000, T, parent="cb1"), reply("a1", now - 17990, T, parent="u1")])
        self.lock(T, "personal", age=17000)
        self.snapshot(".claude-personal", T, age=17000)
        # handed to a background session on personal, stopped 5 s later
        self.append("work", T, [continued(T, S)])
        self.transcript("personal", S + ".orphaned-1-x", [title(S, "t")])
        # woken later: Claude forks the chat into S's own transcript
        self.transcript("personal", S, [{"type": "file-history-snapshot"},
                                        {"type": "system", "subtype": "compact_boundary", "uuid": "cb1", "sessionId": S},
                                        user("s1", now - 8000, S), reply("s2", now - 7990, S)])
        self.job("personal", S, age=7000, state="failed", name="parser rewrite",
                 detail="process gone while supervisor was down")
        # meanwhile the work session restarted blank, into a transcript of its own
        self.transcript("work", A, [user("b1", now - 600, A), reply("b2", now - 590, A)])
        self.job("work", F, age=5, state="working", tempo="active", resumeSessionId=A,
                 name="parser rewrite (2)")
        self.live("work", "4242", A, kind="bg", jobId=F, status="busy", name="parser rewrite (2)")
        r = self.collect()
        rows, links = self.listing(r)
        self.assertEqual(rows, {"personal": [(S, "bg", "done", S, "copy")],
                                "work": [(A, "bg", "working", A, "")]})
        self.assertEqual(links, {"personal": [], "work": [(S, "personal", True)]})
        self.assertEqual(r["counts"], {"waiting": 0, "working": 1, "idle": 0, "done": 1})


class InvariantTests(World):
    """Random mixes of shared chats, records, live sessions and evidence: the
    widget's listing must always obey its rules."""

    PROFILES = ("personal", "work")

    def build(self, rng, n_chats):
        truth = {}
        for c in range(n_chats):
            chat = f"chat{c:02d}"
            owner = rng.choice(self.PROFILES)
            other = "work" if owner == "personal" else "personal"
            self.transcript(owner, chat, [user(f"{chat}-u", self.now - 50000, chat),
                                          reply(f"{chat}-a", self.now - 49990, chat)])
            shared = rng.random() < 0.7
            if shared:
                self.share(chat, owner, other)
            profiles = self.PROFILES if shared else (owner,)
            facts = {"shared": shared, "profiles": profiles, "records": {}, "live": None, "evidence": {}}
            for p in profiles:
                if rng.random() < 0.6:
                    age = rng.choice([30, 600, 3600, 7200, 20000])
                    jid = f"{chat}{p[0]}"
                    self.job(p, jid, age=age, resumeSessionId=chat)
                    self.transcript(p, jid, [title(jid, "t")])
                    facts["records"][p] = int((self.now - age) * 1000)
                if rng.random() < 0.4:
                    age = rng.choice([10, 300, 900, 5000, 30000])
                    self.prompt(p, chat, age=age)
                    facts["evidence"][p] = max(facts["evidence"].get(p, 0), int((self.now - age) * 1000))
            if rng.random() < 0.2:
                p = rng.choice(profiles)
                self.live(p, f"9{c:03d}", chat, status=rng.choice(["busy", "idle", "waiting"]),
                          waitingFor="permission prompt")
                facts["live"] = p
            truth[chat] = facts
        return truth

    def check(self, truth, r):
        groups = {g["name"]: g for g in r["groups"]}
        rows = [(g["name"], s) for g in r["groups"] for s in g["sessions"]]
        listed = {}
        for name, s in rows:
            self.assertIn(s["profile"], groups[name]["profiles"])
            listed.setdefault(s["chatId"], []).append((name, s))
        self.assertEqual(sum(r["counts"].values()), len(rows))
        for chat, facts in truth.items():
            got = listed.get(chat, [])
            if facts["live"]:
                self.assertEqual([(n, s["pid"] is not None) for n, s in got], [(facts["live"], True)], chat)
                continue
            if not facts["records"]:
                self.assertEqual(got, [], chat)
                continue
            self.assertEqual(len(got), 1, chat)
            where = got[0][0]
            if facts["shared"]:
                seen = dict(facts["evidence"])
                for p, t in facts["records"].items():
                    seen[p] = max(seen.get(p, 0), t)
                best = max(seen.values())
                newest_record = max(facts["records"].values())
                if best - max(seen[p] for p in facts["records"]) >= cs.REHOME_SLACK_MS:
                    self.assertEqual(seen[where], best, chat)
                    self.assertEqual(got[0][1]["kind"], "chat", chat)
                else:
                    self.assertIn(where, facts["records"], chat)
                    self.assertEqual(got[0][1]["kind"], "bg", chat)
                    self.assertTrue(seen[where] == best or facts["records"][where] == newest_record, chat)
            else:
                self.assertEqual(where, facts["profiles"][0], chat)
        # every other account sharing a listed shared chat points to it once
        for chat, facts in truth.items():
            got = listed.get(chat, [])
            if not facts["shared"] or len(got) != 1:
                continue
            where = got[0][0]
            for name, g in groups.items():
                pointers = [h for h in g["sharedHere"] if h["sessionId"] == got[0][1]["sessionId"]]
                self.assertEqual(len(pointers), 0 if name == where else 1, (chat, name))

    def test_random_worlds(self):
        for seed in range(60):
            with self.subTest(seed=seed):
                self.tearDown()
                self.setUp()
                rng = random.Random(seed)
                truth = self.build(rng, n_chats=rng.randint(1, 8))
                self.check(truth, self.collect())


if __name__ == "__main__":
    unittest.main()
