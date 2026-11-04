"""The chat pane (pane.py): a chat's conversation, sending it a message,
answering its permission prompt (with the hook, permission_hook.py, or keys
in tmux) and reviewing what it changed (Undo, Commit, Mark reviewed); and
what the status rows carry for it (talpy_den.py)."""
import base64
import contextlib
import io
import json
import os
import re
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
import jump  # noqa: E402
import pane  # noqa: E402
import permission_hook  # noqa: E402

cs = pane.cs

from test_talpy_den import Fixture, iso, session, write  # noqa: E402
from test_tasks import FAKE_CLAUDE, lines, prompt  # noqa: E402

SID = "5c1d7a6e-0d4f-4a8b-9a51-1f2e3d4c5b6a"
# An AskUserQuestion call's input (as Claude Code 2.1.310 asks), with some junk
QUESTIONS = {"questions": [
    {"question": "Pick a color", "header": "Color", "multiSelect": False,
     "options": [{"label": "Red", "description": "warm"}, {"label": "Blue"}, {"description": "no label"}]},
    {"question": "Pick toppings", "multiSelect": True, "options": [{"label": "Cheese"}, {"label": "Olives, sliced"}]},
    "not a question", {"header": "no question"}]}


def tool_use(tid, name, inp, ts, msg="m2", **kw):
    return {"type": "assistant", "timestamp": iso(ts), **kw,
            "message": {"id": msg, "role": "assistant",
                        "content": [{"type": "tool_use", "id": tid, "name": name, "input": inp}]}}


def tool_result(tid, ts, error=False, text="ok"):
    return {"type": "user", "timestamp": iso(ts),
            "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tid, "is_error": error,
                                                     "content": text}]}}


def text_reply(text, ts, msg, stop=None):
    return {"type": "assistant", "timestamp": iso(ts),
            "message": {"id": msg, "role": "assistant", "content": [{"type": "text", "text": text}],
                        "stop_reason": stop}}


class PaneFixture(Fixture):
    def setUp(self):
        super().setUp()
        self.folder = self.home / "repos/app"
        self.folder.mkdir(parents=True)
        self.transcript = self.home / f".claude-work/projects/-repos-app/{SID}.jsonl"
        for p in (mock.patch.object(cs.Path, "home", return_value=self.home),
                  mock.patch.object(cs, "cache_dir", return_value=self.cache)):
            p.start()
            self.addCleanup(p.stop)

    def chat(self, *entries):
        write(self.transcript, lines(*entries))

    def cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            pane.main(list(args))
        text = out.getvalue()
        return json.loads(text.split(cs.REMOTE_MARK)[1] if cs.REMOTE_MARK in text else text)

    def rows(self):
        return {s["sessionId"]: s for g in cs.collect(self.home, self.cache, with_tokens=False)["groups"]
                for s in g["sessions"]}


class CompleteTests(PaneFixture):
    """What the reply box offers as you type (pane.py --complete)."""

    def test_commands_skills_files_and_past_prompts(self):
        t = self.now - 100
        self.chat(prompt("fix it", t, cwd=str(self.folder)))
        work = self.home / ".claude-work"
        write(work / "commands/ship.md", "---\ndescription: Ship the release\n---\nDo it.")
        write(work / "commands/git/sync.md", "# Pull and rebase\nsteps")
        write(work / "skills/notes/SKILL.md", "---\nname: notes\ndescription: Keep notes\n---\n")
        write(self.folder / ".claude/commands/test.md", "Run the tests")
        write(self.folder / ".claude/commands/review.md", "Our own review")   # (the project's, over Claude's)
        write(self.folder / "src/app.py", "x")
        write(self.folder / "node_modules/dep/index.js", "x")
        write(work / "history.jsonl", lines(
            {"display": "old one", "project": str(self.folder), "timestamp": t - 50},
            {"display": "elsewhere", "project": str(self.home / "other"), "timestamp": t - 40},
            {"display": "fix it", "project": str(self.folder), "timestamp": t - 30},
            {"display": "old one", "project": str(self.folder), "timestamp": t - 20}))
        with mock.patch.dict(os.environ, {"PATH": "/nonexistent"}):   # (no git: a walk)
            got = self.cli("--complete", SID, "--profile", ".claude-work")
        self.assertTrue(got["ok"], got)
        names = {c["name"]: c for c in got["commands"]}
        self.assertEqual(names["/ship"]["about"], "Ship the release")
        self.assertEqual(names["/git:sync"]["about"], "Pull and rebase")
        self.assertEqual(names["/notes"]["kind"], "your skill")
        self.assertEqual(names["/test"]["kind"], "project")
        self.assertEqual(names["/review"], {"name": "/review", "about": "Our own review", "kind": "project"})
        self.assertEqual(names["/compact"]["kind"], "Claude")
        self.assertIn(os.path.join("src", "app.py"), got["files"])
        self.assertFalse(any("node_modules" in f for f in got["files"]))
        self.assertEqual(got["history"], ["old one", "fix it"])

    def test_a_git_projects_files_leave_out_whats_ignored(self):
        if not shutil.which("git"):
            self.skipTest("git isn't installed")
        t = self.now - 100
        self.chat(prompt("go", t, cwd=str(self.folder)))
        subprocess.run(["git", "init", "-q", str(self.folder)], check=True)
        write(self.folder / ".gitignore", "secret.txt\n")
        write(self.folder / "secret.txt", "x")
        write(self.folder / "lib/util.py", "x")
        got = self.cli("--complete", SID, "--profile", ".claude-work")
        self.assertEqual(sorted(got["files"]), [".gitignore", "lib/util.py"])


class ConversationTests(PaneFixture):
    def test_thinking_shown_as_updates_is_a_reply(self):
        # (Claude Code shows a thinking block's text as a reply when thinking is
        # shown as updates; thinking it keeps to itself has no text)
        t = self.now - 100

        def thinking(text, ts, display="updates"):
            return {"type": "assistant", "timestamp": iso(ts), "thinkingDisplay": display,
                    "message": {"id": "m1", "role": "assistant", "content": [{"type": "thinking", "thinking": text, "signature": "x"}]}}
        self.chat(prompt("tidy the tags", t, cwd=str(self.folder)),
                  thinking("", t + 1),
                  thinking("Making every tag start with a capital.", t + 2),
                  tool_use("t1", "Bash", {"command": "ls"}, t + 3, "m1"),
                  thinking("A thought of its own.", t + 4, display=None))
        items, _ = pane.conversation(self.transcript)
        self.assertEqual([(i["kind"], i.get("text") or i.get("line")) for i in items],
                         [("you", "tidy the tags"), ("claude", "Making every tag start with a capital."), ("tool", "Bash: ls")])

    def test_items(self):
        t = self.now - 100
        a = str(self.folder / "a.py")
        self.chat(prompt("run the tests", t, cwd=str(self.folder)),
                  text_reply("I'll run them.", t + 1, "m1"),
                  text_reply("First the unit tests.", t + 1, "m1"),  # (a reply's blocks are entries of their own)
                  tool_use("t1", "Bash", {"command": "pytest -q"}, t + 2, "m1"),
                  tool_result("t1", t + 3, error=True, text="1 failed"),
                  tool_use("t2", "Read", {"file_path": a}, t + 4, "m2"),
                  tool_result("t2", t + 5),
                  tool_use("sub", "Bash", {"command": "ls"}, t + 5, "m9", isSidechain=True),
                  text_reply("One test fails.", t + 6, "m3", "end_turn"),
                  prompt("[Request interrupted by user]", t + 7),
                  {"type": "system", "subtype": "compact_boundary", "timestamp": iso(t + 8)},
                  {"type": "assistant", "timestamp": iso(t + 9), "isApiErrorMessage": True,
                   "message": {"id": "e", "role": "assistant",
                               "content": [{"type": "text", "text": "You've hit your session limit · resets 7pm"}]}},
                  tool_use("t3", "Edit", {"file_path": a, "old_string": "x = 1", "new_string": "x = 2"}, t + 10, "m4"))
        items, more = pane.conversation(self.transcript)
        self.assertFalse(more)
        self.assertEqual([(i["kind"], i.get("text") or i.get("line")) for i in items], [
            ("you", "run the tests"),
            ("claude", "I'll run them.\n\nFirst the unit tests."),
            ("tool", "Bash: pytest -q"),
            ("tool", "Read: a.py"),
            ("claude", "One test fails."),
            ("note", "Interrupted"),
            ("note", "The conversation was compacted"),
            ("note", "You've hit your session limit · resets 7pm"),
            ("tool", "Edit: a.py"),
        ])
        bash, read, edit = items[2], items[3], items[8]
        self.assertEqual((bash["status"], bash["input"], bash["output"]), ("error", "$ pytest -q", "1 failed"))
        self.assertEqual(read["status"], "ok")
        self.assertEqual(edit["status"], "open")  # (no result yet: it asks, or runs)
        self.assertIn("-x = 1", edit["input"])
        self.assertIn("+x = 2", edit["input"])
        self.assertEqual([i["key"] for i in items[1:4]], ["m1", "t1", "t2"])
        self.assertEqual(len({i["key"] for i in items}), len(items))

    def test_a_message_sent_while_claude_works_shows_when_it_is_sent(self):
        # Claude Code writes it when it's sent (enqueue), and again once the
        # turn takes it in (an attachment), after the next tool result
        t = self.now - 100

        def queue(op, text, ts, **kw):
            return {"type": "queue-operation", "operation": op, "timestamp": iso(ts), "content": text, **kw}

        def taken(text, ts, source, **kw):
            return {"type": "attachment", "uuid": f"a{ts}", "timestamp": iso(ts), "attachment": {
                "type": "queued_command", "prompt": text, "source_uuid": source, "commandMode": "prompt",
                "origin": {"kind": "human"}, **kw}}

        self.chat(prompt("go", t, cwd=str(self.folder)),
                  tool_use("t1", "Bash", {"command": "sleep 60"}, t + 1, "m1"),
                  queue("enqueue", "also this", t + 2))
        self.assertEqual([(i["kind"], i.get("text"), i.get("queued", False)) for i in pane.conversation(self.transcript)[0]],
                         [("you", "go", False), ("tool", None, False), ("you", "also this", True)])   # (waiting: last, queued)
        # taken in: still one, where Claude took it in
        self.chat(prompt("go", t, cwd=str(self.folder)),
                  tool_use("t1", "Bash", {"command": "sleep 60"}, t + 1, "m1"),
                  queue("enqueue", "also this", t + 2),
                  tool_result("t1", t + 9),
                  queue("remove", "also this", t + 9, reason="absorbed_mid_turn", commandUuid="c1"),
                  taken("also this", t + 2, "c1"))
        items = pane.conversation(self.transcript)[0]
        self.assertEqual([(i["kind"], i.get("text")) for i in items if i["kind"] == "you"],
                         [("you", "go"), ("you", "also this")])
        self.assertEqual([i["kind"] for i in items], ["you", "tool", "you"])
        self.assertFalse(any(i.get("queued") for i in items))
        # one whose enqueue isn't in the transcript shows when it's taken in, if it's yours
        self.chat(taken("never seen", t + 3, "c2"),
                  taken("a subagent's report", t + 4, "c3", origin={"kind": "peer", "from": "x"}),
                  taken("<task-notification>done</task-notification>", t + 5, "c4", commandMode="task-notification"),
                  taken([{"type": "text", "text": "with a picture"}, {"type": "image"}], t + 6, "c5"))
        self.assertEqual([i["text"] for i in pane.conversation(self.transcript)[0]], ["never seen", "with a picture"])

    def test_a_queued_message_taken_back_or_run_as_a_turn_shows_once(self):
        t = self.now - 100
        queued = {"type": "queue-operation", "operation": "enqueue", "timestamp": iso(t + 1), "content": "first"}
        # taken back into the input box
        self.chat(queued, {**queued, "operation": "popAll", "timestamp": iso(t + 2)})
        self.assertEqual(pane.conversation(self.transcript)[0], [])
        # run as the chat's next turn (dequeue, then its prompt)
        self.chat(queued, text_reply("done", t + 2, "m1", "end_turn"),
                  {**queued, "operation": "dequeue", "timestamp": iso(t + 3), "content": None},
                  prompt("first", t + 3, cwd=str(self.folder)))
        items = pane.conversation(self.transcript)[0]
        # (where Claude took it in: after the turn it waited for, no longer queued)
        self.assertEqual([(i["kind"], i["text"], i.get("queued", False)) for i in items],
                         [("claude", "done", False), ("you", "first", False)])
        # (put together with others: its own text, not twice)
        self.chat(queued, {**queued, "operation": "dequeue", "timestamp": iso(t + 3), "content": None},
                  prompt("first\nsecond", t + 3, cwd=str(self.folder)))
        self.assertEqual([i["text"] for i in pane.conversation(self.transcript)[0]], ["first\nsecond"])

    def test_an_edits_diff_shows_under_it(self):
        # At the file's line numbers: from the patch the call gave back, all
        # of a file a Write made, an edit not made yet from where its text is
        t = self.now - 100
        a, new, later = (str(self.folder / n) for n in ("a.py", "new.py", "later.py"))
        write(self.folder / "later.py", "one\ntwo\nthree = 3\n")
        done = tool_result("e1", t + 2)
        done["toolUseResult"] = {"filePath": a, "originalFile": "x\ny\nx = 1\n", "structuredPatch": [
            {"oldStart": 2, "oldLines": 2, "newStart": 2, "newLines": 2, "lines": [" y", "-x = 1", "+x = 2"]}]}
        made = tool_result("w1", t + 4)
        made["toolUseResult"] = {"type": "create", "filePath": new, "content": "z = 0\nz += 1\n", "originalFile": None}
        self.chat(tool_use("e1", "Edit", {"file_path": a, "old_string": "x = 1", "new_string": "x = 2"}, t + 1, "m1"),
                  done,
                  tool_use("w1", "Write", {"file_path": new, "content": "z = 0\nz += 1\n"}, t + 3, "m2"),
                  made,
                  tool_use("e2", "Edit", {"file_path": later, "old_string": "three = 3", "new_string": "three = 4"}, t + 5, "m3"),
                  tool_use("e3", "Edit", {"file_path": a, "old_string": "q", "new_string": "r"}, t + 6, "m4"),
                  tool_result("e3", t + 7, error=True, text="String not found"))
        edit, write_, waiting, failed = pane.conversation(self.transcript)[0]
        self.assertEqual(edit["diff"], ["@@ -2,2 +2,2 @@", " y", "-x = 1", "+x = 2"])
        self.assertEqual(write_["diff"], ["@@ -0,0 +1,2 @@", "+z = 0", "+z += 1"])
        self.assertEqual(waiting["diff"], ["@@ -3 +3 @@", "-three = 3", "+three = 4"])
        self.assertEqual(failed["diff"], [])

    def test_older_edits_keep_a_glimpse_of_their_diff(self):
        t = self.now - 100
        a = str(self.folder / "a.py")
        entries = []
        for n in range(30):
            old = "\n".join(f"old {n} {k}" for k in range(30))
            entries.append(tool_use(f"e{n}", "Edit", {"file_path": a, "old_string": old, "new_string": old.replace("old", "new")},
                                    t + n, f"m{n}"))
        self.chat(*entries)
        items = pane.conversation(self.transcript)[0]
        self.assertEqual(len(items[-1]["diff"]), pane.EDIT_DIFF_LINES + 1)   # (the newest: all it may have, and a note)
        self.assertEqual(items[0]["diff"][-1][:2], "… ")
        self.assertLessEqual(len(items[0]["diff"]), pane.DIFF_GLIMPSE + 1)
        self.assertLessEqual(sum(len(i["diff"]) for i in items), pane.DIFF_BUDGET + 2 * pane.DIFF_GLIMPSE * len(items))

    def test_what_came_of_each_tool_call(self):
        t = self.now - 100
        a = str(self.folder / "a.py")
        long_output = "\n".join(f"line {n}" for n in range(40))
        self.chat(tool_use("t1", "Bash", {"command": "pytest -q"}, t, "m1"),
                  tool_result("t1", t + 1, error=True, text="\n  1 failed, 2 passed\nmore"),
                  tool_use("t2", "Read", {"file_path": a}, t + 2, "m2"),
                  tool_result("t2", t + 3, text="     1\timport os\n     2\t\n     3\tx = 1\n\n<system-reminder>…</system-reminder>"),
                  tool_use("t3", "Edit", {"file_path": a, "old_string": "x = 1", "new_string": "x = 2\ny = 3"}, t + 4, "m3"),
                  tool_result("t3", t + 5, text="The file was updated."),
                  tool_use("t4", "Write", {"file_path": a, "content": "a\nb\nc\n"}, t + 6, "m4"),
                  tool_result("t4", t + 7, text="File created."),
                  tool_use("t5", "Bash", {"command": "seq 40"}, t + 8, "m5"),
                  tool_result("t5", t + 9, text=long_output),  # (more than the unfolded detail keeps)
                  tool_use("t6", "Bash", {"command": "true"}, t + 10, "m6"),
                  tool_result("t6", t + 11, text=""),
                  tool_use("t8", "Edit", {"file_path": a, "old_string": "x", "new_string": "y"}, t + 11, "m8"),
                  tool_result("t8", t + 11, error=True, text="<tool_use_error>File has not been read yet.</tool_use_error>"),
                  tool_use("t7", "Grep", {"pattern": "x"}, t + 12, "m7"))
        items, _ = pane.conversation(self.transcript)
        self.assertEqual([i["summary"] for i in items], [
            "1 failed, 2 passed",
            "3 lines",
            "2 lines added, 1 removed",
            "3 lines",
            "line 0 … +39 lines",
            "(no output)",
            "File has not been read yet.",
            "",  # (no result yet)
        ])
        # lines that start with -- or ++ count too (a Markdown rule, front matter, ++i)
        edit = {"file_path": a, "old_string": "intro\n---\n\n++i;\nend", "new_string": "intro\n\nend\n++"}
        self.assertEqual(pane.tool_summary("Edit", edit, "The file was updated.", False), "1 line added, 2 removed")
        patch = {"structuredPatch": [{"oldStart": 1, "oldLines": 4, "newStart": 1, "newLines": 3,
                                      "lines": [" a", "----", "-++i;", "++++", " b"]}]}
        self.assertEqual(pane.change_summary("Edit", pane.edit_lines("Edit", {}, patch)), "1 line added, 2 removed")

    def test_the_newest_items_and_more(self):
        t = self.now - 1000
        self.chat(*[prompt(f"prompt {n}", t + n) for n in range(50)])
        items, more = pane.conversation(self.transcript, limit=10)
        self.assertEqual([i["text"] for i in items], [f"prompt {n}" for n in range(40, 50)])
        self.assertTrue(more)
        # a big transcript: read from the end, further back until there's enough
        with mock.patch.object(pane, "PANE_TAIL_BYTES", 300):
            items, more = pane.conversation(self.transcript, limit=10)
        self.assertEqual(len(items), 10)
        self.assertTrue(more)

    def test_unchanged_answer(self):
        self.chat(prompt("hello", self.now, cwd=str(self.folder)))
        first = self.cli("--conversation", SID, "--profile", ".claude-work")
        self.assertTrue(first["ok"], first)
        self.assertEqual((first["name"], first["cwd"], first["profileDir"]), ("hello", str(self.folder), ".claude-work"))
        self.assertEqual(self.cli("--conversation", SID, "--if-changed", first["stamp"]), {"ok": True, "unchanged": True})
        with open(self.transcript, "a") as f:
            f.write(json.dumps(text_reply("hi", self.now + 1, "m1", "end_turn")) + "\n")
        again = self.cli("--conversation", SID, "--if-changed", first["stamp"])
        self.assertEqual([i["kind"] for i in again["items"]], ["you", "claude"])
        # (asking for more items isn't the same answer)
        self.assertNotIn("unchanged", self.cli("--conversation", SID, "--limit", "5", "--if-changed", again["stamp"]))

    def test_remote_answer_after_a_marker(self):
        self.chat(prompt("hello", self.now))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            pane.main(["--conversation", SID, "--remote"])
        self.assertTrue(out.getvalue().startswith("\n" + cs.REMOTE_MARK + " "))

    def test_on_a_host(self):
        with mock.patch("remote.host_answer", return_value={"ok": True, "items": []}) as asked:
            answer = self.cli("--conversation", SID, "--host", "gpu", "--profile", ".claude-work", "--limit", "40")
        self.assertEqual(answer, {"ok": True, "items": []})
        asked.assert_called_once_with("gpu", ["--conversation", SID, "--profile", ".claude-work", "--limit", "40"],
                                      name="pane.py")


class PermissionViewTests(PaneFixture):
    def test_the_oldest_call_without_a_result(self):
        t = self.now - 10
        self.chat(prompt("go", t),
                  tool_use("a", "Read", {"file_path": "/x"}, t + 1, "m1"),
                  tool_use("b", "Bash", {"command": "rm -rf build"}, t + 1, "m1"),
                  tool_result("a", t + 2))  # (parallel calls: one has its result, the other asks)
        self.assertEqual(cs.pending_tool(self.transcript)["id"], "b")
        with open(self.transcript, "a") as f:
            f.write(json.dumps(tool_result("b", t + 3)) + "\n")
        self.assertIsNone(cs.pending_tool(self.transcript))
        # two calls that change things, open: Claude runs (and asks about) the first one first
        with open(self.transcript, "a") as f:
            f.write(lines(tool_use("c", "Bash", {"command": "rm -rf dist"}, t + 4, "m2"),
                          tool_use("d", "Bash", {"command": "npm publish"}, t + 4, "m2")))
        self.assertEqual([c["id"] for c in cs.open_tools(self.transcript)], ["c", "d"])
        self.assertEqual(cs.pending_permission(self.transcript, str(self.folder))["toolUse"], "c")

    def test_views(self):
        bash = cs.permission_view("Bash", {"command": "npm publish"}, str(self.folder),
                                  [{"type": "addRules", "rules": [{"toolName": "Bash", "ruleContent": "npm publish"}],
                                    "behavior": "allow", "destination": "localSettings"}])
        self.assertEqual((bash["line"], bash["command"], bash["always"]),
                         ("Bash: npm publish", "npm publish", "Bash(npm publish) in this project (.claude/settings.local.json)"))
        edit = cs.permission_view("Edit", {"file_path": str(self.folder / "src/a.py"), "old_string": "a\nb",
                                           "new_string": "a\nc"}, str(self.folder))
        self.assertEqual(edit["file"], "src/a.py")
        self.assertEqual(edit["diff"][-2:], ["-b", "+c"])
        write(self.folder / "b.txt", "old\n")
        whole = cs.permission_view("Write", {"file_path": str(self.folder / "b.txt"), "content": "new\n"},
                                   str(self.folder), [{"type": "addDirectories", "directories": [str(self.home / "other")],
                                                       "destination": "session"}])
        self.assertEqual(whole["diff"][-2:], ["-old", "+new"])
        self.assertEqual(whole["always"], "access to ~/other in this chat")

    def test_always_allow_says_all_it_does(self):
        # (Claude 2.1.317's suggestions for a write outside the chat's folders: it said "the folder ~/other",
        # saved in settings.local.json, and the click also turned on accept edits for the whole chat)
        outside = [{"type": "setMode", "mode": "acceptEdits", "destination": "session"},
                   {"type": "addDirectories", "directories": [str(self.home / "other")], "destination": "session"},
                   {"type": "addRules", "rules": [{"toolName": "Bash", "ruleContent": "rm -rf /"}], "behavior": "deny",
                    "destination": "localSettings"},
                   {"type": "addRules", "rules": [{"toolName": "Bash"}], "behavior": "allow", "destination": "elsewhere"}]
        view = cs.permission_view("Write", {"file_path": str(self.home / "other/x"), "content": "hi"}, str(self.folder), outside)
        self.assertEqual(view["always"], "all edits (accept edits mode) and access to ~/other, in this chat")
        self.assertEqual(pane.decision_of("always", "", outside)["updatedPermissions"], outside[:2])  # (what it says: no more)

    def test_a_write_over_a_big_file_or_a_pipe(self):
        # (each check made the view: it read the whole file and diffed it, minutes of CPU for a big one)
        write(self.folder / "big.txt", "".join("row %d\n" % i for i in range(3000)))
        new = "".join("row %d\n" % i if i % 50 else "changed\n" for i in range(3000))
        with mock.patch.object(cs, "DIFF_FILE_MAX", 1000):
            view = cs.permission_view("Write", {"file_path": str(self.folder / "big.txt"), "content": new}, str(self.folder))
        self.assertEqual(view["diff"][:3], ["@@ -0,0 +1,3000 @@", "Replaces a file of 1 MB, not compared here: the new text",
                                            "+changed"])
        self.assertEqual(len(view["diff"]), cs.DIFF_LINES)
        with mock.patch.object(cs, "DIFF_COMPARE_LINES", 1000):
            view = cs.permission_view("Write", {"file_path": str(self.folder / "big.txt"), "content": new}, str(self.folder))
        self.assertEqual(view["diff"][:2], ["@@ -1,2953 +1,2953 @@", "Too long to compare here: 2953 new lines in place of 2953"])
        os.mkfifo(self.folder / "pipe")
        view = cs.permission_view("Write", {"file_path": str(self.folder / "pipe"), "content": "x\n"}, str(self.folder))
        self.assertEqual(view["diff"], ["@@ -0,0 +1 @@", "Replaces something that isn't a plain file, not compared here: the new text", "+x"])

    def test_what_an_mcp_tool_asks_with(self):
        # (its prompt showed only "slack: send_message": Allow sent a secret to a channel the user never saw)
        view = cs.permission_view("mcp__slack__send_message", {"channel": "#attacker-dm", "text": "AWS_SECRET=x\ny",
                                                               "blocks": [{"type": "section"}], "thread": None}, "/tmp")
        self.assertEqual((view["line"], view["args"]), ("slack: send_message", [
            "channel: #attacker-dm", "text: AWS_SECRET=x\ny", 'blocks: [{"type": "section"}]']))
        url = cs.permission_view("WebFetch", {"url": "https://x.org/?k=" + "s" * 2000}, "")["args"][0]
        self.assertEqual((len(url), url[-2:]), (len("url: ") + cs.ARG_CHARS, "s…"))
        self.assertEqual(cs.permission_view("Bash", {"command": "ls", "description": "list"}, "")["args"], [])

    def test_a_question(self):
        view = cs.permission_view("AskUserQuestion", QUESTIONS, str(self.folder))
        self.assertEqual(view["line"], "Pick a color")
        self.assertEqual(view["questions"], [
            {"question": "Pick a color", "header": "Color", "multiSelect": False,
             "options": [{"label": "Red", "description": "warm"}, {"label": "Blue", "description": ""}]},
            {"question": "Pick toppings", "header": "", "multiSelect": True,
             "options": [{"label": "Cheese", "description": ""}, {"label": "Olives, sliced", "description": ""}]}])
        self.assertEqual(cs.permission_view("Bash", {"command": "ls"}, "")["questions"], [])

    def test_rows_with_a_question(self):
        # A chat with a question waits for "input needed" (Claude Code 2.1.310), as one an MCP server asks does
        w = self.home / ".claude-work"
        for sid in ("asking", "mcp"):
            write(w / f"sessions/2{len(sid)}.json", session(sid, status="waiting", waitingFor="input needed"))
        write(w / "projects/-tmp-proj-asking/asking.jsonl",
              lines(prompt("ask me", self.now - 5), tool_use("q", "AskUserQuestion", QUESTIONS, self.now - 4)))
        write(w / "projects/-tmp-proj-mcp/mcp.jsonl",
              lines(prompt("log in", self.now - 5), tool_use("m", "mcp__x__login", {}, self.now - 4)))
        rows = self.rows()
        asks = rows["asking"]["permission"]
        self.assertEqual((asks["tool"], len(asks["questions"]), asks["answer"]), ("AskUserQuestion", 2, ""))
        self.assertIsNone(rows["mcp"]["permission"])  # (an MCP server's question: not one the widget shows)
        # relayed by the hook: answered from the widget
        hook = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        self.addCleanup(lambda: (hook.kill(), hook.wait()))
        for rid, sid, tool, inp in (("123-abcdef01", "asking", "AskUserQuestion", QUESTIONS),
                                    ("124-abcdef02", "mcp", "Bash", {"command": "ls"})):
            write(self.cache / f"permissions/{rid}.json",
                  {"id": rid, "at": int(self.now * 1000), "hookPid": hook.pid, "sessionId": sid, "tool": tool,
                   "input": inp, "suggestions": [], "cwd": "/tmp"})
        rows = self.rows()
        asks = rows["asking"]["permission"]
        self.assertEqual((asks["questions"][1]["question"], asks["answer"], asks["request"]),
                         ("Pick toppings", "hook", "123-abcdef01"))
        self.assertIsNone(rows["mcp"]["permission"])
        # in tmux too: a question's keys aren't pressed for you
        row = {"state": "waiting", "waitingFor": "input needed", "sessionId": "x", "tmux": "s:1.%3"}
        with mock.patch.object(cs, "pending_permission", return_value=cs.permission_view("AskUserQuestion", QUESTIONS, "")):
            cs.note_permissions([{"sessions": [row]}], mock.Mock(profiles=[]), {})
        self.assertEqual(row["permission"]["answer"], "")

    def test_rows_waiting_for_a_permission(self):
        # bgperm (Fixture) waits for a permission; what it asks comes from its transcript
        write(self.home / ".claude-work/projects/-tmp-proj-bgperm/bgperm.jsonl",
              lines(prompt("write it", self.now - 5),
                    tool_use("w", "Write", {"file_path": "/tmp/x", "content": "hi"}, self.now - 4)))
        rows = self.rows()
        self.assertEqual((rows["bgperm"]["permission"]["line"], rows["bgperm"]["permission"]["answer"]), ("Write: x", ""))
        self.assertIsNone(rows["waiting"]["permission"])  # (waiting for something else)
        self.assertIsNone(rows["busy"]["permission"])
        # relayed by the hook: its request, which the widget can answer
        hook = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        self.addCleanup(lambda: (hook.kill(), hook.wait()))
        write(self.cache / "permissions/123-abcdef01.json",
              {"id": "123-abcdef01", "at": int(self.now * 1000), "hookPid": hook.pid, "sessionId": "bgperm",
               "tool": "Bash", "input": {"command": "make deploy"}, "suggestions": [], "cwd": "/tmp"})
        write(self.cache / "permissions/100-00000000.json",  # (its hook is gone: dropped)
              {"id": "100-00000000", "at": 1, "hookPid": 4194304 + 4242, "sessionId": "bgperm"})
        rows = self.rows()
        self.assertEqual((rows["bgperm"]["permission"]["line"], rows["bgperm"]["permission"]["answer"],
                          rows["bgperm"]["permission"]["request"]), ("Bash: make deploy", "hook", "123-abcdef01"))
        self.assertFalse((self.cache / "permissions/100-00000000.json").exists())

    def test_reply_routes(self):
        rows = self.rows()
        self.assertEqual(rows["vscode"]["reply"], "vscode")
        self.assertEqual(rows["bgworking"]["reply"], "background")
        self.assertEqual(rows["busy"]["reply"], "terminal")
        self.assertEqual(cs.reply_route({"pid": 5, "kind": "interactive", "tmux": True}), "tmux")
        self.assertEqual(cs.reply_route({"pid": None, "kind": "interactive"}), "background")


SCREEN = """\
 Bash command
 python3 -c 'print(42)'
 This command requires approval
 Do you want to proceed?
 ❯ 1. Yes
   2. Yes, and don’t ask again for: python3 *
   3. Yes, and switch to auto mode · auto mode handles these prompts for you
   4. No
 Esc to cancel · Tab to amend
"""


class AskNotificationTests(unittest.TestCase):
    """A permission prompt's notification (main.qml): its buttons in Claude's
    own order, as in its row and its pane, and in VS Code's notification."""

    def test_buttons_in_claudes_order(self):
        main = (CODE.parent / "ui/main.qml").read_text()
        block = main[main.index("id: askNotificationComponent"):]
        block = block[:block.index("onClosed:")]
        actions = re.search(r"questions.length === 0 \? \(cut \? \[([^\]]*)\]\s*: withAlways \? \[([^\]]*)\] : \[([^\]]*)\]\)", block)
        self.assertEqual([a.strip() for a in actions.group(2).split(",")],
                         ["allowAction", "alwaysAction", "denyAction", "noteAction"])
        self.assertEqual([a.strip() for a in actions.group(3).split(",")], ["allowAction", "denyAction", "noteAction"])
        # (a command it can't show whole: Open, to read it all, Allow once and Deny; no Always allow)
        self.assertEqual([a.strip() for a in actions.group(1).split(",")], ["openAction", "allowAction", "denyAction"])
        # Plasma puts a reply button before all the others (its ActionContainer.qml)
        self.assertNotIn("replyAction", block)

    def test_a_questions_buttons(self):
        # one question with one answer: its options (at most 4), then Other…; else Answer… (the pane)
        main = (CODE.parent / "ui/main.qml").read_text()
        block = main[main.index("id: askNotificationComponent"):]
        block = block[:block.index("onClosed:")]
        self.assertIn("choices: questions.length === 1 && !questions[0].multiSelect ? questions[0].options.slice(0, 4) : []",
                      block)
        self.assertIn(": choices.length ? [choice0, choice1, choice2, choice3].slice(0, choices.length).concat([otherAction])\n"
                      "                     : [answerAction]", block)
        for i in range(4):
            self.assertIn(f"label: ask.choices.length > {i} ? ask.choices[{i}].label", block)
            self.assertIn(f"onActivated: ask.choose({i})", block)


class KeysTests(unittest.TestCase):
    """Answering the dialog of a chat in tmux (as Claude Code 2.1.310 shows it)."""

    def test_options(self):
        self.assertEqual(pane.dialog_options(SCREEN)["2"], "Yes, and don’t ask again for: python3 *")
        self.assertEqual(pane.dialog_options("❯ 1. Yes\n"), {})  # (no dialog: a list in a reply)

    def keys(self, decision, note="", screen=SCREEN):
        sent = []

        def run(base, args, data=None):
            sent.append(args)
            return (True, screen) if args[0] == "capture-pane" else (True, "")
        with mock.patch.object(pane, "tmux_base", return_value=(["tmux"], "%3")), \
                mock.patch.object(pane, "tmux_run", side_effect=run), \
                mock.patch.object(pane, "tmux_type", return_value=(True, "")) as typed, \
                mock.patch.object(pane.time, "sleep"):
            ok, message = pane.answer_with_keys({"pid": 1, "tmux": "s:1.%3"}, decision, note)
        return ok, message, [a[-1] for a in sent if a[0] == "send-keys"], typed.call_args

    def test_keys(self):
        self.assertEqual(self.keys("allow")[2], ["1"])
        self.assertEqual(self.keys("always")[2], ["2"])
        ok, message, keys, typed = self.keys("deny", "use make instead")
        self.assertEqual((ok, keys, typed[0][1]), (True, ["4"], "use make instead"))
        ok, message, keys, _ = self.keys("allow", screen="❯ \n")
        self.assertEqual((ok, keys), (False, []))
        self.assertIn("no permission question", message)
        # an edit's dialog: Always is its "allow all edits during this session"
        edit = (" Edit file\n parser.py\n Do you want to make this edit to parser.py?\n ❯ 1. Yes\n"
                "   2. Yes, allow all edits during this session (shift+tab)\n"
                "   3. No, and tell Claude what to do differently (esc)\n")
        self.assertEqual(self.keys("always", screen=edit)[:3], (True, "Allowed, and from now on", ["2"]))
        self.assertEqual(self.keys("deny", screen=edit)[2], ["3"])
        # (never auto mode, which isn't what Always says)
        ok, message, keys, _ = self.keys("always", screen=" Do you want to proceed?\n ❯ 1. Yes\n   2. Yes, and switch to "
                                                          "auto mode · auto mode handles these prompts for you\n   3. No\n")
        self.assertEqual((ok, keys), (False, []))

    def test_each_paste_has_its_own_buffer(self):
        # two replies typed at once (each in its own process) mustn't paste each other's text
        sent = []

        def run(base, args, data=None):
            sent.append(args)
            return (False, "tmux: can't find pane: %9") if args[0] == "paste-buffer" and args[-1] == "%9" else (True, "")
        with mock.patch.object(pane, "tmux_base", side_effect=lambda e: (["tmux"], e["tmux"])), \
                mock.patch.object(pane, "tmux_run", side_effect=run), mock.patch.object(pane.time, "sleep"):
            self.assertEqual(pane.tmux_type({"pid": 1, "tmux": "%3"}, "one"), (True, ""))
            self.assertEqual(pane.tmux_type({"pid": 1, "tmux": "%9"}, "two")[0], False)
        loads = [a[a.index("-b") + 1] for a in sent if a[0] == "load-buffer"]
        pastes = [a[a.index("-b") + 1] for a in sent if a[0] == "paste-buffer"]
        self.assertEqual(loads, pastes)
        self.assertNotEqual(loads[0], loads[1])
        # (a paste that failed doesn't leave its text in tmux)
        self.assertEqual(sent[-1], ["delete-buffer", "-b", loads[1]])
        # (a plan's line with ESC[201~ can't end the paste and type Ctrl+C and a !command)
        sent.clear()
        with mock.patch.object(pane, "tmux_base", side_effect=lambda e: (["tmux"], e["tmux"])), \
                mock.patch.object(pane, "tmux_run", side_effect=lambda base, args, data=None: (sent.append(data), (True, ""))[1]), \
                mock.patch.object(pane.time, "sleep"):
            pane.tmux_type({"pid": 1, "tmux": "%3"}, "3. Run the tests\x1b[201~\x03!touch /tmp/x\x1b[200~\x9b201~\r\n4.\tShip")
        self.assertEqual(sent[0], "3. Run the tests[201~!touch /tmp/x[200~201~\n4.\tShip".encode())
        # jump.py types plan feedback the same way
        with mock.patch.object(pane, "tmux_type", return_value=(True, "")) as typed:
            self.assertEqual(jump.tmux_paste({"pid": 1, "tmux": "%3"}, "fb"), (True, ""))
        self.assertEqual(typed.call_args[0][1], "fb")


class ToolUseTests(PaneFixture):
    """The tool call a row's prompt is about ("toolUse"), and keys pressed
    only while the chat still asks about it (pane.py --keys --expect)."""

    def setUp(self):
        super().setUp()
        write(self.home / ".claude-work/sessions/30.json",
              session("tmuxed", status="waiting", waitingFor="permission prompt", tmux="s:1.%3"))
        self.path = self.home / ".claude-work/projects/-tmp-proj-tmuxed/tmuxed.jsonl"
        write(self.path, lines(prompt("deploy", self.now - 5), tool_use("toolu_1", "Bash", {"command": "make deploy"}, self.now - 4)))

    def test_rows_name_it(self):
        rows = self.rows()
        self.assertEqual((rows["tmuxed"]["permission"]["toolUse"], rows["tmuxed"]["permission"]["answer"]), ("toolu_1", "keys"))
        self.assertEqual(cs.chat_tool_use(self.home, [], "tmuxed"), "toolu_1")
        self.assertEqual(cs.chat_tool_use(self.home, [], "tmuxed", ".claude-work"), "toolu_1")
        self.assertIsNone(cs.chat_tool_use(self.home, [], "tmuxed", ".claude-personal"))
        self.assertIsNone(cs.chat_tool_use(self.home, [], "no-such-chat"))
        # through the hook: what its request names (null: Claude named none)
        hook = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        self.addCleanup(lambda: (hook.kill(), hook.wait()))
        for rid, tool_use_id in (("123-abcdef01", None), ("124-abcdef02", "toolu_9")):
            write(self.cache / f"permissions/{rid}.json",
                  {"id": rid, "at": int(self.now * 1000), "hookPid": hook.pid, "sessionId": "tmuxed", "tool": "Bash",
                   "input": {"command": "make deploy"}, "suggestions": [], "cwd": "/tmp", "toolUse": tool_use_id})
            permission = self.rows()["tmuxed"]["permission"]
            self.assertEqual((permission["answer"], permission["request"], permission["toolUse"]), ("hook", rid, tool_use_id))
            (self.cache / f"permissions/{rid}.json").unlink()
        # every row's permission has it, even one a stand-in view leaves out
        row = {"state": "waiting", "waitingFor": "permission prompt", "sessionId": "x", "tmux": "s:1.%3"}
        with mock.patch.object(cs, "pending_permission", return_value=cs.permission_view("Bash", {"command": "ls"}, "")):
            cs.note_permissions([{"sessions": [row]}], mock.Mock(profiles=[]), {})
        self.assertIsNone(row["permission"]["toolUse"])

    def test_no_keys_for_a_call_that_may_not_be_the_one_asked_about(self):
        # two calls open (which one the prompt is about isn't written down), or
        # a subagent's call (what it asks is in its own transcript): no keys
        for calls in ([tool_use("toolu_1", "Bash", {"command": "rm -rf build"}, self.now - 4, "m1"),
                       tool_use("toolu_2", "Bash", {"command": "git status"}, self.now - 4, "m1")],
                      [tool_use("toolu_3", "Agent", {"description": "Tidy the repo", "prompt": "Tidy it"}, self.now - 4)]):
            write(self.path, lines(prompt("deploy", self.now - 5), *calls))
            permission = self.rows()["tmuxed"]["permission"]
            self.assertEqual((permission["answer"], "sure" in permission), ("", False))
        self.assertEqual([c["id"] for c in cs.open_tools(self.path)], ["toolu_3"])

    def keys(self, *args, meanwhile=None):
        """pane.py --keys tmuxed … with tmux stood in for: (its answer, the keys sent)."""
        sent = []

        def run(base, argv, data=None):
            if argv[0] == "capture-pane":
                if meanwhile:
                    with open(self.path, "a") as f:
                        f.write(lines(*meanwhile))
                return True, SCREEN
            sent.append(argv[-1])
            return True, ""
        with mock.patch.object(pane, "tmux_base", return_value=(["tmux"], "%3")), \
                mock.patch.object(pane, "tmux_run", side_effect=run), mock.patch.object(pane.time, "sleep"):
            return self.cli("--keys", "tmuxed", "--profile", ".claude-work", "--decision", "allow", *args), sent

    def test_keys_for_the_call_it_asks_about(self):
        self.assertEqual(self.keys("--expect", "toolu_1"), ({"ok": True, "message": "Allowed"}, ["1"]))

    def test_no_keys_once_it_asks_something_else(self):
        # answered in the chat while you clicked, and the next call asks
        nxt = [tool_result("toolu_1", self.now - 3), tool_use("toolu_2", "Bash", {"command": "rm -rf build"}, self.now - 2, "m3")]
        self.assertEqual(self.keys("--expect", "toolu_1", meanwhile=nxt),
                         ({"ok": False, "message": "It asks something else now", "changed": True}, []))
        # or it asks nothing now
        write(self.path, lines(prompt("deploy", self.now - 5), tool_use("toolu_1", "Bash", {"command": "make deploy"}, self.now - 4)))
        self.assertEqual(self.keys("--expect", "toolu_1", meanwhile=[tool_result("toolu_1", self.now - 3)]),
                         ({"ok": False, "message": "It asks something else now", "changed": True}, []))

    def test_without_expect_as_before(self):
        nxt = [tool_result("toolu_1", self.now - 3), tool_use("toolu_2", "Bash", {"command": "rm -rf build"}, self.now - 2, "m3")]
        with mock.patch.object(cs, "chat_tool_use") as looked:
            self.assertEqual(self.keys(meanwhile=nxt), ({"ok": True, "message": "Allowed"}, ["1"]))
            self.assertEqual(self.keys("--expect", "")[1], ["1"])   # (an empty one: no check)
        looked.assert_not_called()

    def test_on_a_host(self):
        with mock.patch("remote.host_answer", return_value={"ok": False, "message": "It asks something else now",
                                                             "changed": True}) as asked:
            answer = self.cli("--keys", "tmuxed", "--decision", "allow", "--expect", "toolu_1", "--host", "gpu")
        self.assertTrue(answer["changed"])
        self.assertEqual(asked.call_args[0][1], ["--keys", "tmuxed", "--decision", "allow", "--expect", "toolu_1"])
        self.assertEqual(asked.call_args[1], {"name": "pane.py"})


class HookTests(unittest.TestCase):
    """permission_hook.py, run as Claude runs it (this test is its Claude)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.cache = self.home / "cache"
        self.state = self.home / ".claude-x/sessions" / f"{os.getpid()}.json"
        write(self.state, {"pid": os.getpid(), "status": "waiting"})

    def env(self):
        return dict(os.environ, HOME=str(self.home), XDG_CACHE_HOME=str(self.cache),
                    CLAUDE_CONFIG_DIR=str(self.home / ".claude-x"))

    def start(self, tool="Bash", inp=None, suggestions=None):
        hook = subprocess.Popen([sys.executable, "-I", str(CODE / "permission_hook.py")], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, env=self.env())
        self.addCleanup(lambda: (hook.poll() is None and hook.kill(), hook.wait(), hook.stdout.close()))
        if suggestions is None:
            suggestions = [{"type": "addRules", "rules": [{"toolName": "Bash", "ruleContent": "make"}],
                            "behavior": "allow", "destination": "localSettings"}]
        hook.stdin.write(json.dumps({"session_id": SID, "tool_name": tool, "tool_input": inp or {"command": "make"},
                                     "cwd": "/tmp", "permission_suggestions": suggestions}).encode())
        hook.stdin.close()
        deadline = time.time() + 5
        while time.time() < deadline and not cs.permission_requests(self.cache / "talpy-den"):
            time.sleep(0.05)
        (request,) = cs.permission_requests(self.cache / "talpy-den").values()
        return hook, request

    def test_the_widget_answers(self):
        hook, request = self.start()
        self.assertEqual((request["tool"], request["input"], request["hookPid"]), ("Bash", {"command": "make"}, hook.pid))
        ok, message = pane.answer_request(self.cache / "talpy-den", request["id"], "always")
        self.assertEqual((ok, message), (True, "Allowed, and from now on"))
        out = json.loads(hook.stdout.read())
        hook.wait(5)
        decision = out["hookSpecificOutput"]["decision"]
        self.assertEqual(decision["behavior"], "allow")
        self.assertEqual(decision["updatedPermissions"][0]["rules"][0]["ruleContent"], "make")
        self.assertEqual(list((self.cache / "talpy-den/permissions").iterdir()), [])

    def test_answered_in_the_chat(self):
        hook, request = self.start()
        write(self.state, {"pid": os.getpid(), "status": "busy"})  # (you answered its dialog)
        self.assertEqual(hook.stdout.read(), b"")  # no word: the dialog decided
        self.assertEqual(hook.wait(5), 0)
        ok, message = pane.answer_request(self.cache / "talpy-den", request["id"], "allow")
        self.assertFalse(ok)
        self.assertIn("isn't asking any more", message)
        # the front ends hear it may ask something else now (as with --keys --expect)
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"HOME": str(self.home), "XDG_CACHE_HOME": str(self.cache)}), \
                contextlib.redirect_stdout(out):
            pane.main(["--answer", request["id"], "--decision", "allow"])
        self.assertEqual(json.loads(out.getvalue()), {"ok": False, "message": message, "changed": True})

    def test_decisions(self):
        self.assertEqual(pane.decision_of("deny", " use make test ", []),
                         {"behavior": "deny", "message": "The user denied this and said: use make test"})
        self.assertTrue(pane.decision_of("deny", "", [])["interrupt"])
        self.assertEqual(pane.decision_of("always", "", []), {"behavior": "allow"})  # (nothing to remember)
        # a question: not answered (with what you said instead), or the call with your answers
        self.assertEqual(pane.decision_of("deny", "ask me later", [], QUESTIONS, {}),
                         {"behavior": "deny", "message": "The user didn't answer and said: ask me later"})
        self.assertEqual(pane.decision_of("deny", "", [], QUESTIONS, {}),
                         {"behavior": "deny", "message": "The user didn't answer.", "interrupt": True})
        self.assertEqual(pane.decision_of("answer", "", [], {"questions": []}, {"Q": "A"}),
                         {"behavior": "allow", "updatedInput": {"questions": [], "answers": {"Q": "A"}}})

    def test_answers_as_claudes_dialog_sends_them(self):
        self.assertEqual(pane.answer_text(["Blue"], False), "Blue")
        self.assertEqual(pane.answer_text(["  a typed answer, with a comma "], False), "a typed answer, with a comma")
        self.assertEqual(pane.answer_text(["Cheese", "Olives, sliced", 'say "hi"', " "], True),
                         'Cheese, "Olives, sliced", "say \\"hi\\""')
        self.assertEqual(pane.question_answers(QUESTIONS, {"Pick a color": ["Red"], "Pick toppings": [],
                                                           "Not asked": ["x"]}), {"Pick a color": "Red"})

    def test_a_question(self):
        hook, request = self.start("AskUserQuestion", QUESTIONS, [])
        cache = self.cache / "talpy-den"
        self.assertEqual(pane.answer_request(cache, request["id"], "allow"), (False, "Choose your answers first"))
        self.assertEqual(pane.answer_request(cache, request["id"], "answer", answers={"Pick a color": [" "]}),
                         (False, "Choose your answers first"))
        answers = {"Pick a color": ["Blue"], "Pick toppings": ["Cheese", "Olives, sliced"]}
        out = subprocess.run([sys.executable, "-I", str(CODE / "pane.py"), "--answer", request["id"], "--decision",
                              "answer", "--answers", json.dumps(answers)], stdout=subprocess.PIPE, env=self.env())
        self.assertEqual(json.loads(out.stdout), {"ok": True, "message": "Answered"})
        decision = json.loads(hook.stdout.read())["hookSpecificOutput"]["decision"]
        hook.wait(5)
        self.assertEqual(decision, {"behavior": "allow", "updatedInput": dict(QUESTIONS, answers={
            "Pick a color": "Blue", "Pick toppings": 'Cheese, "Olives, sliced"'})})

    def test_a_plan_is_approved_or_planned_on(self):
        # Verified on Claude Code 2.1.311 (ExitPlanMode through the hook): an
        # allow must carry the call's input, a setMode makes it accept edits,
        # a deny's message is your feedback and it plans on
        plan = {"plan": "# Fix the parser\n1. Read it\n2. Fix it", "planFilePath": "/tmp/plan.md"}
        cache = self.cache / "talpy-den"
        hook, request = self.start("ExitPlanMode", plan, [])
        self.assertEqual(pane.answer_request(cache, request["id"], "allow"), (False, "Approve the plan or keep planning"))
        self.assertEqual(pane.answer_request(cache, request["id"], "answer", answers={}), (False, "Approve the plan or keep planning"))
        out = subprocess.run([sys.executable, "-I", str(CODE / "pane.py"), "--answer", request["id"], "--decision", "approve-edits"],
                             stdout=subprocess.PIPE, env=self.env())
        self.assertEqual(json.loads(out.stdout), {"ok": True, "message": "Approved: it starts, accepting edits"})
        decision = json.loads(hook.stdout.read())["hookSpecificOutput"]["decision"]
        hook.wait(5)
        self.assertEqual(decision, {"behavior": "allow", "updatedInput": plan,
                                    "updatedPermissions": [{"type": "setMode", "mode": "acceptEdits", "destination": "session"}]})
        self.assertEqual(pane.plan_decision("approve", "", plan), {"behavior": "allow", "updatedInput": plan})
        self.assertEqual(pane.plan_decision("keep", " also a docstring ", plan),
                         {"behavior": "deny", "message": "The user wants to keep planning and said: also a docstring"})
        self.assertNotIn("interrupt", pane.plan_decision("keep", "", plan))   # (it plans on, it isn't stopped)
        # a permission isn't a plan
        hook, request = self.start()
        self.assertEqual(pane.answer_request(cache, request["id"], "approve"), (False, "It asks for a permission, not about a plan"))

    def test_a_plans_view(self):
        view = cs.permission_view("ExitPlanMode", {"plan": "\n## Fix the parser\nsteps", "planFilePath": "/p.md"}, "/tmp")
        self.assertEqual(view["plan"], {"text": "\n## Fix the parser\nsteps", "cut": False, "file": "/p.md", "title": "Fix the parser"})
        self.assertEqual(view["line"], "Plan: Fix the parser")
        path = self.home / "plan.md"
        write(path, "# From the file\nmore")
        self.assertEqual(cs.permission_view("ExitPlanMode", {"planFilePath": str(path)}, "")["plan"]["title"], "From the file")
        self.assertIsNone(cs.permission_view("Bash", {"command": "make"}, "")["plan"])

    def hook_for(self, sid, tool="Bash", inp=None):
        hook = subprocess.Popen([sys.executable, "-I", str(CODE / "permission_hook.py")], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, env=self.env())
        self.addCleanup(lambda: (hook.poll() is None and hook.kill(), hook.wait(), hook.stdout.close()))
        hook.stdin.write(json.dumps({"session_id": sid, "tool_name": tool, "tool_input": inp or {"command": "make"},
                                     "cwd": "/tmp", "permission_suggestions": []}).encode())
        hook.stdin.close()
        deadline = time.time() + 5
        while time.time() < deadline and sid not in cs.permission_requests(self.cache / "talpy-den"):
            time.sleep(0.05)
        time.sleep(0.01)   # (the next one is younger)
        return hook

    def test_keyboard_answers_take_the_oldest_prompt(self):
        cache = self.cache / "talpy-den"
        self.assertEqual(pane.answer_oldest(cache, "allow"), (False, "No chat waits for a permission"))
        question = self.hook_for("q" * 8, "AskUserQuestion", QUESTIONS)
        self.assertEqual(pane.answer_oldest(cache, "allow"), (False, "A question waits: answer it in the panel"))
        first = self.hook_for("a" * 8, "Bash", {"command": "make first"})
        second = self.hook_for("b" * 8, "Bash", {"command": "make second"})
        ok, said = pane.answer_oldest(cache, "deny")
        self.assertTrue(ok, said)
        self.assertIn("Denied · Bash: make first", said)
        self.assertEqual(json.loads(first.stdout.read())["hookSpecificOutput"]["decision"]["behavior"], "deny")
        self.assertIsNone(second.poll())   # (still waiting: it's the next one)
        plan = self.hook_for("c" * 8, "ExitPlanMode", {"plan": "# Do it"})
        pane.answer_oldest(cache, "allow")   # (the Bash one)
        ok, said = pane.answer_oldest(cache, "allow")
        self.assertIn("Approved: it starts", said)
        self.assertEqual(json.loads(plan.stdout.read())["hookSpecificOutput"]["decision"]["updatedInput"], {"plan": "# Do it"})
        self.assertEqual(pane.answer_oldest(cache, "always"), (False, "Not an answer: always"))
        question.kill()

    def test_a_chat_that_asked_again_is_answered_about_the_new_prompt(self):
        # you answered the first prompt in the chat and it asked again at once
        # (its status stayed "waiting"): the first one's hook may still wait
        cache = self.cache / "talpy-den"
        first = self.hook_for(SID, "Bash", {"command": "make first"})
        old = cs.permission_requests(cache)[SID]
        second = self.hook_for(SID, "Bash", {"command": "make second"})
        deadline = time.time() + 5
        while time.time() < deadline and cs.permission_requests(cache)[SID]["id"] == old["id"]:
            time.sleep(0.05)
        new = cs.permission_requests(cache)[SID]
        self.assertEqual(new["input"], {"command": "make second"})   # what the row, pane and notification show
        self.assertEqual(pane.oldest_request(cache)[0]["id"], new["id"])   # (and what the keys answer)
        # an answer to the one shown before isn't taken: it says so
        self.assertEqual(pane.answer_request(cache, old["id"], "deny"), (False, "It asks something else now"))
        self.assertIsNone(first.poll())
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"HOME": str(self.home), "XDG_CACHE_HOME": str(self.cache)}), \
                contextlib.redirect_stdout(out):
            pane.main(["--answer", old["id"], "--decision", "deny"])
        self.assertEqual(json.loads(out.getvalue()), {"ok": False, "message": "It asks something else now", "changed": True})
        self.assertEqual(pane.answer_request(cache, new["id"], "deny"), (True, "Denied"))
        self.assertEqual(json.loads(second.stdout.read())["hookSpecificOutput"]["decision"]["behavior"], "deny")

    def test_keyboard_shortcuts_go_where_they_are_free(self):
        # A stand-in gdbus: Meta+Alt+N belongs to KWin here; every call logged
        bin_dir = self.home / "bin"
        log = self.home / "gdbus.log"
        write(bin_dir / "gdbus", "#!/bin/sh\n"
              f"echo \"$*\" >> {log}\n"
              "case \"$*\" in *'getGlobalShortcutsByKey 402653262'*) echo \"([('kwin', 'Walk Through Windows', '', '', '', '', [], [])],)\";;\n"
              "*getGlobalShortcutsByKey*) echo '(@a(ssssssaiai) [],)';; *) echo '()';; esac\n")
        (bin_dir / "gdbus").chmod(0o755)
        with mock.patch.dict(os.environ, {"PATH": f"{bin_dir}:{os.environ['PATH']}", "XDG_DATA_HOME": str(self.home / "data")}):
            ok, said = pane.shortcuts(self.home, True)
            path = pane.shortcuts_file(self.home)
            text = path.read_text()
            self.assertIn("Meta+Alt+N is another shortcut's", said)
            self.assertIn("X-KDE-Shortcuts=Meta+Alt+Y\n", text)
            self.assertIn("[Desktop Action deny]", text)
            self.assertIn("X-KDE-Shortcuts=\n", text)   # (none for deny)
            self.assertIn(f"Exec=python3 -I {CODE / 'pane.py'} --oldest allow --osd", text)
            calls = log.read_text()
            self.assertIn("doRegister [\"org.wzaielamri.talpyden.answers.desktop\", \"allow\"", calls)
            self.assertIn("setShortcutKeys [\"org.wzaielamri.talpyden.answers.desktop\", \"allow\", \"Talpy Den\", "
                          "\"Allow the oldest prompt\"] [([402653273],)] 6", calls)
            self.assertIn("\"deny\", \"Talpy Den\", \"Deny the oldest prompt\"] @a(ai) [] 6", calls)
            self.assertEqual(pane.shortcuts(self.home, None), (True, "on"))
            self.assertEqual(pane.shortcuts(self.home, False), (True, "Keyboard answers are off"))
            self.assertFalse(path.exists())
            self.assertIn("unregister \"org.wzaielamri.talpyden.answers.desktop\" \"deny\"", log.read_text())

    def test_the_tool_call_it_asks_about(self):
        # (Claude Code 2.1.311 names none in a permission request: null then)
        hook, request = self.start()
        self.assertIsNone(request["toolUse"])
        self.assertIsNone(cs.request_view(request)["toolUse"])
        hook.kill()
        hook.wait()
        named = subprocess.Popen([sys.executable, "-I", str(CODE / "permission_hook.py")], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, env=self.env())
        self.addCleanup(lambda: (named.poll() is None and named.kill(), named.wait(), named.stdout.close()))
        named.stdin.write(json.dumps({"session_id": "named", "tool_name": "Bash", "tool_use_id": "toolu_7",
                                      "tool_input": {"command": "ls"}}).encode())
        named.stdin.close()
        deadline = time.time() + 5
        while time.time() < deadline and "named" not in cs.permission_requests(self.cache / "talpy-den"):
            time.sleep(0.05)
        request = cs.permission_requests(self.cache / "talpy-den")["named"]
        self.assertEqual((request["toolUse"], cs.request_view(request)["toolUse"]), ("toolu_7", "toolu_7"))

    def test_run_through_a_shell_it_finds_its_claude(self):
        # Claude runs a hook's command with sh -c; dash, Debian's and
        # Ubuntu's sh, stays between them unless the command execs (an
        # entry written before doesn't): the hook still finds this Claude,
        # and waits while it shows its dialog (not just NO_DIALOG_S)
        shells = [s for s in ("sh", "dash", "bash") if shutil.which(s)]
        python, script = shlex.quote(sys.executable), shlex.quote(str(CODE / "permission_hook.py"))
        for shell in shells:
            with self.subTest(shell):
                hook = subprocess.Popen([shell, "-c", f"{python} -I {script}"], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, env=self.env())
                self.addCleanup(lambda h=hook: (h.poll() is None and h.kill(), h.wait(), h.stdout.close()))
                hook.stdin.write(json.dumps({"session_id": SID, "tool_name": "Bash", "tool_input": {"command": "make"},
                                             "cwd": "/tmp", "permission_suggestions": []}).encode())
                hook.stdin.close()
                deadline = time.time() + 5
                while time.time() < deadline and not cs.permission_requests(self.cache / "talpy-den"):
                    time.sleep(0.05)
                (request,) = cs.permission_requests(self.cache / "talpy-den").values()
                self.assertEqual(request["pid"], os.getpid())
                if shell == shells[0]:
                    time.sleep(permission_hook.NO_DIALOG_S + 1)
                    self.assertIsNone(hook.poll())   # (its Claude still asks)
                self.assertEqual(pane.answer_request(self.cache / "talpy-den", request["id"], "allow"), (True, "Allowed"))
                self.assertEqual(json.loads(hook.stdout.read())["hookSpecificOutput"]["decision"], {"behavior": "allow"})
                hook.wait(5)

    def test_claudes_process_through_shells(self):
        # its parent; the parent of the shell that ran it (one that stays:
        # a command after it); without /proc, its parent
        probe = (f"import sys; sys.path.insert(0, {str(CODE)!r}); import permission_hook, live_hook; "
                 "print(permission_hook.claude_pid(), live_hook.claude_pid())")
        command = f"{shlex.quote(sys.executable)} -I -B -c {shlex.quote(probe)}"   # (-B: no __pycache__ in the package)
        runs = [("itself", [sys.executable, "-I", "-B", "-c", probe])]
        runs += [(s, [s, "-c", command + "; :"]) for s in ("sh", "dash", "bash") if shutil.which(s)]
        for name, argv in runs:
            with self.subTest(name):
                out = subprocess.run(argv, capture_output=True, text=True, timeout=30)
                self.assertEqual(out.stdout.split(), [str(os.getpid())] * 2, out.stderr)
        with mock.patch.object(permission_hook, "parent_of", return_value=None):
            self.assertEqual(permission_hook.claude_pid(), os.getppid())
        self.assertEqual(permission_hook.parent_of(os.getpid())[0], os.getppid())

    def test_a_permission_takes_no_answers(self):
        hook, request = self.start()
        ok, message = pane.answer_request(self.cache / "talpy-den", request["id"], "answer", answers={"x": ["y"]})
        self.assertEqual((ok, message), (False, "It asks for a permission, not a question"))


class SendTests(PaneFixture):
    def setUp(self):
        super().setUp()
        self.bin = self.home / "bin"
        self.log = self.home / "claude.log"
        write(self.bin / "claude", FAKE_CLAUDE.format(python=sys.executable, log=str(self.log)))
        (self.bin / "claude").chmod(0o755)
        w = self.home / ".claude-work"
        data = json.loads((w / ".claude.json").read_text())
        data["projects"] = {str(self.folder): {"hasTrustDialogAccepted": True}}
        write(w / ".claude.json", data)
        self.chat(prompt("fix it", self.now - 100, cwd=str(self.folder)),
                  text_reply("Done.", self.now - 90, "m1", "end_turn"))
        # (no real systemd scope in the tests: the one a chat woken in the background gets, said)
        self.scopes = []
        scoped = mock.patch.object(jump, "scope_prefix", lambda name: self.scopes.append(name) or [])
        scoped.start()
        self.addCleanup(scoped.stop)

    def send(self, how="auto", text="and the docs"):
        return pane.send(self.home, [], ".claude-work", SID, text, None, how, str(self.bin / "claude"))

    def calls(self):
        return [json.loads(l)["argv"] for l in self.log.read_text().splitlines()] if self.log.exists() else []

    def live(self, **kw):
        write(self.home / ".claude-work/sessions/30.json", session(SID, cwd=str(self.folder), **kw))

    def test_a_finished_chat_goes_on_in_the_background(self):
        answer = self.send()
        self.assertTrue(answer["ok"], answer)
        self.assertEqual((answer["how"], answer["message"]),
                         ("background", "Sent: the chat goes on with it in the background (1a2b3c4d)"))
        self.assertEqual(self.calls(), [["--bg", "--resume", SID, "and the docs"]])

    def test_a_background_session_takes_it_in_where_it_is(self):
        # (through Claude's background service, as `claude agents` answers one: queued while it works,
        # never stopped, so a terminal attached to it stays on it)
        from test_tasks import FakeService
        self.live(kind="bg", status="busy", jobId="bgjob1")
        profile = next(p for p in cs.discover_profiles(self.home) if p.key == ".claude-work")
        service = FakeService(self, profile, lambda r: {"ok": True, "op": r["op"]})
        with mock.patch.object(cs, "stop_background") as stopped:
            answer = self.send()
        self.assertEqual(answer, {"ok": True, "how": "typed", "message": "Sent (typed into its background session)"})
        self.assertEqual([(r["short"], r["text"]) for r in service.ops("reply")], [("bgjob1", "and the docs")])
        self.assertEqual((stopped.call_count, self.calls()), (0, []))
        # one that asks you something stops first, as before (a message typed in would land in its question)
        self.live(kind="bg", status="waiting", waitingFor="permission prompt", jobId="bgjob1")
        with mock.patch.object(cs, "stop_background", return_value=(True, "Stopped")) as stopped, \
                mock.patch.object(cs, "continue_chat", return_value={"ok": True, "id": "1a2b3c4d"}):
            self.assertEqual(self.send()["how"], "background")
        self.assertEqual((stopped.call_count, len(service.ops("reply"))), (1, 1))

    def test_a_background_session_stops_first(self):
        # (one whose service doesn't take it in: there's none here)
        self.live(kind="bg", status="busy", jobId="bgjob1")
        write(self.home / ".claude-work/jobs/bgjob1/state.json", {"state": "working", "sessionId": SID})
        with mock.patch.object(cs, "stop_background", return_value=(True, "Stopped")) as stopped, \
                mock.patch.object(cs, "continue_chat", return_value={"ok": True, "id": "1a2b3c4d"}) as went_on:
            answer = self.send()
        self.assertEqual(answer["how"], "background")
        self.assertEqual(stopped.call_args[0][1], "bgjob1")
        self.assertEqual(went_on.call_args[1]["text"], "and the docs")

    def test_a_chat_woken_in_the_background_lives_on_its_own(self):
        # Woken from the widget, Claude's background service would be in plasmashell's group of
        # processes, ended (with every background chat it runs) when plasmashell restarts: it
        # starts in a systemd scope of its own, as the widget's go-ons and tasks do; on an SSH host not
        with mock.patch.object(jump, "scope_prefix", return_value=["systemd-run", "--user", "--scope", "--"]), \
                mock.patch.object(cs, "continue_chat", return_value={"ok": True, "id": "1a2b3c4d"}) as went_on:
            self.assertEqual(self.send()["how"], "background")
            self.assertEqual(went_on.call_args[1]["prefix"], ["systemd-run", "--user", "--scope", "--"])
            pane.send(self.home, [], ".claude-work", SID, "and the docs", None, "auto", str(self.bin / "claude"), scoped=False)
            self.assertEqual(went_on.call_args[1]["prefix"], [])

    def test_vscode(self):
        self.live(entrypoint="claude-vscode")
        answer = self.send(text="also: README & a+b 100%20")
        self.assertEqual(answer["how"], "vscode")
        base, query = answer["link"].split("?", 1)
        self.assertEqual(base, "vscode://anthropic.claude-code/open")
        # VS Code decodes the query once, the extension's URLSearchParams again
        from urllib.parse import parse_qs, unquote
        self.assertEqual(parse_qs(unquote(query)), {"session": [SID], "prompt": ["also: README & a+b 100%20"]})
        self.assertEqual(self.calls(), [])

    def test_tmux(self):
        self.live(tmux="main:1.%3")
        with mock.patch.object(pane, "tmux_type", return_value=(True, "")) as typed:
            self.assertEqual(self.send()["how"], "typed")
        self.assertEqual(typed.call_args[0][1], "and the docs")
        self.live(tmux="main:1.%3", status="waiting", waitingFor="permission prompt")
        answer = self.send()
        self.assertFalse(answer["ok"])  # (it would land in its dialog)
        self.assertIn("answer that first", answer["message"])

    def test_a_terminal_asks(self):
        self.live()
        self.assertEqual(self.send()["how"], "ask")
        with mock.patch.object(cs, "stop_chat", return_value=(True, "Stopped")) as stopped, \
                mock.patch.object(cs, "continue_chat", return_value={"ok": True}) as went_on:
            self.assertEqual(self.send("background")["how"], "background")
        stopped.assert_called_once()
        went_on.assert_called_once()
        self.live(status="busy")
        with mock.patch.object(cs, "stop_chat") as stopped:
            answer = self.send("background")
        self.assertIn("send it when this turn ends", answer["message"])
        stopped.assert_not_called()
        with mock.patch.object(pane, "copy_to_clipboard", return_value=True):
            self.assertEqual(self.send("copy")["how"], "copy")

    def test_enter_copies_for_a_terminal(self):
        # Enter in the pane: Claude in a terminal that takes no text never quits on it
        self.live()
        with mock.patch.object(pane, "copy_to_clipboard", return_value=True) as copy, \
                mock.patch.object(cs, "stop_chat") as stopped:
            answer = self.cli("--send", SID, "--profile", ".claude-work", "--text", " and the docs ", "--how", "enter")
        self.assertEqual(answer, {"ok": True, "how": "copy", "copied": True, "text": "",
                                  "message": "Its terminal takes no text from outside, so your message is "
                                             "in the clipboard: paste it there"})
        copy.assert_called_once_with("and the docs")
        stopped.assert_not_called()
        with mock.patch.object(pane, "copy_to_clipboard", return_value=False):
            answer = self.cli("--send", SID, "--profile", ".claude-work", "--text", "and the docs", "--how", "enter")
        self.assertEqual((answer["copied"], answer["text"], answer["message"]),
                         (False, "and the docs", "Couldn't use the clipboard here"))
        # a finished chat goes on in the background, as with auto
        (self.home / ".claude-work/sessions/30.json").unlink()
        with mock.patch.object(pane, "copy_to_clipboard") as copy:
            self.assertEqual(self.send("enter")["how"], "background")
        copy.assert_not_called()
        self.assertEqual(self.calls(), [["--bg", "--resume", SID, "and the docs"]])

    def test_enter_copies_here_for_a_hosts_terminal(self):
        asked = {"ok": True, "how": "ask", "message": "Its terminal takes no text from outside"}
        with mock.patch("remote.host_answer", return_value=asked) as host, \
                mock.patch.object(pane, "copy_to_clipboard", return_value=True) as copy:
            answer = self.cli("--send", SID, "--host", "lab", "--text", "and the docs", "--how", "enter")
        self.assertEqual(host.call_args[0][1], ["--send", SID, "--text", "and the docs", "--how", "enter"])
        self.assertEqual(answer["how"], "copy")
        copy.assert_called_once_with("and the docs")  # (this computer's clipboard)
        with mock.patch("remote.host_answer", return_value={"ok": True, "how": "typed", "message": "Sent"}), \
                mock.patch.object(pane, "copy_to_clipboard") as copy:
            self.assertEqual(self.cli("--send", SID, "--host", "lab", "--text", "x", "--how", "enter")["how"], "typed")
        copy.assert_not_called()
        # the host itself leaves it to this computer (its own clipboard is out of reach over ssh)
        with mock.patch.object(pane, "send", return_value=asked), mock.patch.object(pane, "copy_to_clipboard") as copy, \
                contextlib.redirect_stdout(io.StringIO()) as out:
            pane.main(["--send", SID, "--profile", ".claude-work", "--text", "x", "--how", "enter", "--remote"])
        copy.assert_not_called()
        self.assertEqual(json.loads(out.getvalue().split(cs.REMOTE_MARK)[-1])["how"], "ask")

    def test_a_hosts_vscode_link_is_made_here(self):
        # (a host chose the link Plasma opened: file://, any URI handler)
        other = "0123abcd-0000-0000-0000-000000000000"
        for link in ("file:///etc/passwd", pane.vscode_prompt_link(other, "run this"), None):
            hostile = {"ok": True, "how": "vscode", "link": link, "message": "In VS Code"}
            with mock.patch("remote.host_answer", return_value=hostile):
                answer = self.cli("--send", SID, "--host", "lab", "--text", "and the docs", "--how", "auto")
            self.assertEqual(answer["link"], pane.vscode_prompt_link(SID, "and the docs"))
        # (the id the host found it by, of those asked)
        good = {"ok": True, "how": "vscode", "link": pane.vscode_prompt_link(other, "x")}
        with mock.patch("remote.host_answer", return_value=good):
            answer = self.cli("--send", SID, "--session", other, "--host", "lab", "--text", "x")
        self.assertEqual(answer["link"], good["link"])

    def test_a_long_text_comes_in_a_file_of_its_own(self):
        # (one command-line argument holds 128 KiB at most: VS Code hands over a long reply in a file)
        text = "語" * 60000
        self.cache.mkdir(parents=True, exist_ok=True)
        f = self.cache / "text-1.txt"
        f.write_text(text, encoding="utf-8")
        with mock.patch.object(pane, "send", return_value={"ok": True, "how": "typed", "message": "Sent"}) as sent:
            self.assertTrue(self.cli("--send", SID, "--profile", ".claude-work", "--text-file", str(f))["ok"])
        self.assertEqual(sent.call_args[0][4], text)
        self.assertFalse(f.exists(), "read once, then removed")
        # a host's chat: the text itself goes on (remote.host_answer takes it there)
        f.write_text("and the docs", encoding="utf-8")
        with mock.patch("remote.host_answer", return_value={"ok": True, "how": "typed", "message": "Sent"}) as host:
            self.cli("--send", SID, "--host", "lab", "--text-file", str(f), "--how", "auto")
        self.assertEqual(host.call_args[0][1], ["--send", SID, "--text", "and the docs", "--how", "auto"])
        # only a text file of the cache's
        other = self.home / "notes.txt"
        other.write_text("secret", encoding="utf-8")
        self.assertFalse(self.cli("--send", SID, "--text-file", str(other))["ok"])
        self.assertTrue(other.exists())

    def test_after_the_turn(self):
        answer = self.cli("--send", SID, "--profile", ".claude-work", "--text", "next: docs", "--after-turn",
                          "--how", "background", "--session", SID, "--name", "Fix it")
        self.assertEqual(answer, {"ok": True, "message": "It's sent when this turn ends"})
        self.cli("--send", SID, "--profile", ".claude-work", "--text", "next: the docs", "--after-turn")
        (task,) = cs.queued_tasks(self.cache, int(time.time() * 1000))  # (one waits per chat)
        self.assertEqual((task["chat"], task["prompt"], task["afterTurn"], task["due"], task["how"]),
                         (SID, "next: the docs", True, False, "auto"))
        import jump
        with mock.patch.object(pane, "send", return_value={"ok": True, "how": "typed", "message": "Sent"}) as sent, \
                mock.patch.object(jump.cs, "cache_dir", return_value=self.cache), \
                mock.patch.object(jump, "claude_path", return_value="claude"):
            self.assertEqual(jump.start_queued(self.home, [], task["id"]), (True, "Sent"))
        self.assertEqual(sent.call_args[0][1:6], ([], ".claude-work", SID, "next: the docs", None))
        self.assertEqual(cs.load_queue(self.cache), [])

    def test_a_reply_after_the_turn_leaves_keep_going_alone(self):
        # cancelling it, or turning Keep going off meanwhile, is about the reply only
        import jump
        cs.keep_chat(self.cache, ".claude-work", SID, "Fix it")
        self.cli("--send", SID, "--profile", ".claude-work", "--text", "next: the docs", "--after-turn")
        (task,) = cs.load_queue(self.cache)
        with mock.patch.object(jump.cs, "cache_dir", return_value=self.cache):
            self.assertEqual(jump.unqueue(self.home, [], task["id"]), (True, "Cancelled your message"))
            self.assertEqual([k["chat"] for k in cs.kept_chats(self.cache)], [SID])
            self.cli("--send", SID, "--profile", ".claude-work", "--text", "next: the docs", "--after-turn")
            self.assertEqual(jump.keep_off(self.home, [], SID), (True, "It won't go on by itself any more"))
        self.assertEqual(len(cs.load_queue(self.cache)), 1)


HAVE_GIT = shutil.which("git") is not None
GIT_ENV = {"GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@example.org", "GIT_COMMITTER_NAME": "T",
           "GIT_COMMITTER_EMAIL": "t@example.org", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


class ReviewTests(PaneFixture):
    def setUp(self):
        super().setUp()
        p = mock.patch.dict(os.environ, GIT_ENV)
        p.start()
        self.addCleanup(p.stop)
        write(self.folder / "a.py", "x = 1\ny = 2\n")
        write(self.folder / "other.py", "keep\n")
        if HAVE_GIT:  # (the Python 3.7 image CI uses for SSH hosts has none)
            self.git("init", "-q")
            self.git("add", ".")
            self.git("commit", "-qm", "start")
        # the chat: a.py edited (a backup of how it was), new.py made; other.py isn't the chat's
        write(self.home / f".claude-work/file-history/{SID}/aa11@v1", "x = 1\ny = 2\n")
        t = self.now - 100
        a, new = str(self.folder / "a.py"), str(self.folder / "new.py")
        self.chat(prompt("change x", t, cwd=str(self.folder)),
                  {"type": "file-history-delta", "trackingPath": a, "snapshotMessageId": "p",
                   "backup": {"backupFileName": "aa11@v1", "version": 1}, "sessionId": SID},
                  tool_use("e1", "Edit", {"file_path": a, "old_string": "x = 1", "new_string": "x = 3"}, t + 1),
                  tool_result("e1", t + 2),
                  {"type": "file-history-delta", "trackingPath": new, "snapshotMessageId": "p",
                   "backup": {"backupFileName": None, "version": 1}, "sessionId": SID},
                  tool_use("e2", "Write", {"file_path": new, "content": "z = 0\n"}, t + 3),
                  tool_result("e2", t + 4),
                  tool_use("t1", "Bash", {"command": "python3 -m pytest -q"}, t + 5),
                  tool_result("t1", t + 6),
                  {"type": "system", "subtype": "away_summary", "timestamp": iso(t + 7),
                   "content": "You changed x to 3 and added new.py."})
        write(self.folder / "a.py", "x = 3\ny = 2\n")
        write(self.folder / "new.py", "z = 0\n")
        write(self.folder / "other.py", "mine, not the chat's\n")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.folder), *args], check=True, capture_output=True, text=True).stdout

    def test_review(self):
        r = self.cli("--review", SID)
        self.assertTrue(r["ok"], r)
        self.assertEqual([(f["label"], f["added"], f["removed"], f["created"]) for f in r["files"]],
                         [("a.py", 1, 1, False), ("new.py", 1, 0, True)])
        self.assertEqual(r["files"][0]["diff"][-3:], ["-x = 1", "+x = 3", " y = 2"])
        self.assertEqual((r["tests"]["command"], r["tests"]["ok"]), ("python3 -m pytest -q", True))
        self.assertEqual(r["repos"], [str(self.folder)] if HAVE_GIT else [])
        self.assertEqual(r["message"], "change x\n\nYou changed x to 3 and added new.py.")

    def test_a_file_without_backups(self):
        # A file outside the chat's folder has no backups (Claude keeps none
        # there, nor does git): what the chat's Edit or Write calls gave back
        # says how it was; one that says nothing shows how it is now
        t = self.now - 50
        notes, plan, odd = (str(self.home / "notes" / n) for n in ("today.md", "plan.md", "odd.md"))
        write(self.home / "notes/today.md", "# Today\nwrote this\n")
        write(self.home / "notes/plan.md", "step 1\nstep 2 done\n")
        write(self.home / "notes/odd.md", "a\nb\n")
        made = tool_result("n1", t + 1)
        made["toolUseResult"] = {"type": "create", "filePath": notes, "content": "# Today\nwrote this\n", "originalFile": None}
        edited = tool_result("n2", t + 3)
        edited["toolUseResult"] = {"filePath": plan, "originalFile": "step 1\nstep 2\n", "structuredPatch": []}
        later = tool_result("n4", t + 7)
        later["toolUseResult"] = {"filePath": plan, "originalFile": "step 1\nstep 2 wrong\n", "structuredPatch": []}
        with open(self.transcript, "a") as f:
            f.write(lines(tool_use("n1", "Write", {"file_path": notes, "content": "x"}, t, "n1"), made,
                          tool_use("n2", "Edit", {"file_path": plan, "old_string": "step 2", "new_string": "step 2 done"}, t + 2, "n2"),
                          edited,
                          tool_use("n3", "Edit", {"file_path": odd, "old_string": "a", "new_string": "a"}, t + 4, "n3"),
                          tool_result("n3", t + 5),
                          tool_use("n4", "Edit", {"file_path": plan, "old_string": "x", "new_string": "y"}, t + 6, "n4"), later))
        files = {f["label"]: f for f in self.cli("--review", SID)["files"]}
        self.assertEqual((files["~/notes/today.md"]["created"], files["~/notes/today.md"]["diff"]),
                         (True, ["@@ -0,0 +1,2 @@", "+# Today", "+wrote this"]))
        self.assertEqual(files["~/notes/plan.md"]["diff"], ["@@ -1,2 +1,2 @@", " step 1", "-step 2", "+step 2 done"])
        self.assertEqual((files["~/notes/odd.md"]["unknown"], files["~/notes/odd.md"]["now"]), (True, ["a", "b"]))

    @unittest.skipUnless(HAVE_GIT, "needs git")
    def test_a_file_git_doesnt_have_isnt_taken_for_new(self):
        # Changed with no backup and no earlier content in its tool's result
        # (a notebook edit): in the repository but not committed (nb.ipynb),
        # or in one with no commit yet (fresh/notes.txt). They were there
        # before the chat: unknown, so Undo leaves them
        t = self.now - 50
        nb, fresh = self.folder / "nb.ipynb", self.home / "fresh/notes.txt"
        write(nb, '{"cells": ["mine and the chat\'s"]}')
        write(fresh, "mine, then the chat's\n")
        subprocess.run(["git", "init", "-q", str(fresh.parent)], check=True, capture_output=True)
        edit = {"cell_id": "c1", "new_source": "x"}
        with open(self.transcript, "a") as f:
            f.write(lines(tool_use("nb1", "NotebookEdit", dict(edit, notebook_path=str(nb)), t, "nb1"),
                          tool_result("nb1", t + 1),
                          tool_use("fr1", "NotebookEdit", dict(edit, notebook_path=str(fresh)), t + 2, "fr1"),
                          tool_result("fr1", t + 3)))
        files = {f["label"]: f for f in self.cli("--review", SID)["files"]}
        for label in ("nb.ipynb", "~/fresh/notes.txt"):
            self.assertEqual((files[label]["created"], files[label]["unknown"], files[label]["deleted"]), (False, True, False))
        self.assertEqual(self.cli("--undo", SID)["message"], "Put back 2 files as before the chat (2 with no earlier version kept)")
        self.assertEqual(nb.read_text(), '{"cells": ["mine and the chat\'s"]}')   # (still there)
        self.assertEqual(fresh.read_text(), "mine, then the chat's\n")

    @unittest.skipUnless(HAVE_GIT, "needs git")
    def test_a_file_that_was_empty_comes_back_empty(self):
        # Empty before the chat (git has it empty; an Edit's result said so):
        # Undo empties it again, it doesn't delete it
        t = self.now - 50
        init, blank = self.folder / "pkg/__init__.py", self.home / "notes/blank.md"
        write(init, "")
        self.git("add", "pkg/__init__.py")
        self.git("commit", "-qm", "pkg")
        write(init, "VERSION = 2\n")
        write(blank, "filled in\n")
        filled = tool_result("bl1", t + 3)
        filled["toolUseResult"] = {"filePath": str(blank), "originalFile": "", "structuredPatch": []}
        with open(self.transcript, "a") as f:
            f.write(lines(tool_use("in1", "NotebookEdit", {"notebook_path": str(init), "new_source": "x"}, t, "in1"),
                          tool_result("in1", t + 1),
                          tool_use("bl1", "Edit", {"file_path": str(blank), "old_string": "", "new_string": "x"}, t + 2, "bl1"),
                          filled))
        files = {f["label"]: f for f in self.cli("--review", SID)["files"]}
        self.assertEqual((files["pkg/__init__.py"]["created"], files["pkg/__init__.py"]["added"]), (False, 1))
        self.assertEqual((files["~/notes/blank.md"]["created"], files["~/notes/blank.md"]["unknown"]), (False, False))
        ok, said = pane.undo(self.home, [], SID, None, {str(init), str(blank)})
        self.assertEqual((ok, said), (True, "Put back 2 files as before the chat"))
        self.assertEqual((init.read_text(), blank.read_text()), ("", ""))

    @unittest.skipUnless(HAVE_GIT, "needs git")
    def test_a_removed_file_comes_back_with_its_mode(self):
        # the chat edited a script, then removed its folder: Undo brings both
        # back as git has them (executable) and as your umask makes them, not
        # private to you like the files pane.py writes for itself
        script = self.folder / "bin/run.sh"
        write(script, "echo hi\n")
        script.chmod(0o755)
        self.git("add", "bin/run.sh")
        self.git("commit", "-qm", "script")
        write(self.home / f".claude-work/file-history/{SID}/bb22@v1", "echo hi\n")
        t = self.now - 50
        with open(self.transcript, "a") as f:
            f.write(lines({"type": "file-history-delta", "trackingPath": str(script), "snapshotMessageId": "p",
                           "backup": {"backupFileName": "bb22@v1", "version": 1}, "sessionId": SID},
                          tool_use("s1", "Edit", {"file_path": str(script), "old_string": "hi", "new_string": "bye"}, t, "s1"),
                          tool_result("s1", t + 1)))
        shutil.rmtree(self.folder / "bin")
        mask = os.umask(0o022)
        try:
            self.assertEqual(self.cli("--undo", SID, "--file", str(script))["message"], "Put back 1 file as before the chat")
        finally:
            os.umask(mask)
        self.assertEqual(script.read_text(), "echo hi\n")
        self.assertEqual((script.stat().st_mode & 0o777, script.parent.stat().st_mode & 0o777), (0o755, 0o755))

    @unittest.skipUnless(HAVE_GIT, "needs git")
    def test_commit_takes_names_as_they_are(self):
        # a file named like a pattern (a route folder [id], a[1].txt) commits
        # that file only, not others the pattern matches
        write(self.folder / "a1.txt", "mine\n")
        self.git("add", "a1.txt")
        self.git("commit", "-qm", "mine")
        write(self.folder / "a1.txt", "mine, changed\n")
        odd = self.folder / "a[1].txt"
        t = self.now - 50
        made = tool_result("o1", t + 1)
        made["toolUseResult"] = {"type": "create", "filePath": str(odd), "content": "made\n", "originalFile": None}
        with open(self.transcript, "a") as f:
            f.write(lines({"type": "file-history-delta", "trackingPath": str(odd), "snapshotMessageId": "p",
                           "backup": {"backupFileName": None, "version": 1}, "sessionId": SID},
                          tool_use("o1", "Write", {"file_path": str(odd), "content": "made\n"}, t, "o1"), made))
        write(odd, "made\n")
        answer = self.cli("--commit", SID, "--message", "Odd", "--file", str(odd))
        self.assertTrue(answer["ok"], answer)
        self.assertEqual(self.git("show", "--name-only", "--format=", "HEAD").split(), ["a[1].txt"])
        self.assertIn("a1.txt", self.git("status", "--porcelain"))

    def test_undo(self):
        ok, message = pane.undo(self.home, [], SID, None, {str(self.folder / "new.py")})
        self.assertEqual((ok, message), (True, "Put back 1 file as before the chat"))
        self.assertFalse((self.folder / "new.py").exists())
        self.assertEqual(self.cli("--undo", SID)["message"], "Put back 1 file as before the chat")
        self.assertEqual((self.folder / "a.py").read_text(), "x = 1\ny = 2\n")
        self.assertEqual((self.folder / "other.py").read_text(), "mine, not the chat's\n")  # (not the chat's)

    def test_undo_through_a_link_puts_back_the_file_it_points_to(self):
        # (a dotfile kept elsewhere: the chat's Edit wrote through the link)
        t = self.now - 50
        real, link = self.home / "dotfiles/bashrc", self.folder / ".bashrc"
        write(real, "alias ll='ls -l'\nexport EDITOR=vim\n")
        link.symlink_to(real)
        edited = tool_result("ln1", t + 1)
        edited["toolUseResult"] = {"filePath": str(link), "originalFile": "alias ll='ls -l'\n", "structuredPatch": []}
        with open(self.transcript, "a") as f:
            f.write(lines(tool_use("ln1", "Edit", {"file_path": str(link), "old_string": "", "new_string": "x"}, t, "ln1"),
                          edited))
        self.assertEqual(pane.undo(self.home, [], SID, None, {str(link)}), (True, "Put back 1 file as before the chat"))
        self.assertEqual((link.is_symlink(), real.read_text()), (True, "alias ll='ls -l'\n"))

    @unittest.skipUnless(HAVE_GIT, "needs git")
    def test_commit_leaves_out_files_git_ignores(self):
        write(self.folder / ".gitignore", ".env\n")
        self.git("add", ".gitignore")
        self.git("commit", "-qm", "ignore")
        env = self.folder / ".env"
        t = self.now - 50
        made = tool_result("e1", t + 1)
        made["toolUseResult"] = {"type": "create", "filePath": str(env), "content": "TOKEN=x\n", "originalFile": None}
        with open(self.transcript, "a") as f:
            f.write(lines({"type": "file-history-delta", "trackingPath": str(env), "snapshotMessageId": "p",
                           "backup": {"backupFileName": None, "version": 1}, "sessionId": SID},
                          tool_use("e1", "Write", {"file_path": str(env), "content": "TOKEN=x\n"}, t, "e1"), made))
        write(env, "TOKEN=x\n")
        answer = self.cli("--commit", SID, "--message", "Set x to 3")
        self.assertTrue(answer["ok"], answer)
        self.assertRegex(answer["message"], r"^Committed 2 files in .*\) \(left out 1 file git ignores\)$")
        self.assertEqual(self.git("show", "--name-only", "--format=", "HEAD").split(), ["a.py", "new.py"])
        self.assertEqual(self.cli("--commit", SID, "--message", "Env", "--file", str(env)),
                         {"ok": False, "message": "Nothing to commit: git ignores its file"})

    def test_without_git_it_reviews_but_doesnt_commit(self):
        with mock.patch.object(pane.shutil, "which", return_value=None):
            self.assertEqual([f["label"] for f in self.cli("--review", SID)["files"]], ["a.py", "new.py"])
            answer = self.cli("--commit", SID, "--message", "Set x to 3")
        self.assertEqual(answer, {"ok": False, "message": "None of its files is in a git repository"})

    @unittest.skipUnless(HAVE_GIT, "needs git")
    def test_commit_only_its_files(self):
        answer = self.cli("--commit", SID, "--message", "Set x to 3\n\nAnd new.py.")
        self.assertTrue(answer["ok"], answer)
        self.assertRegex(answer["message"], r"^Committed 2 files in .*app \([0-9a-f]{7,}\)$")
        self.assertEqual(self.git("show", "--name-only", "--format=%s", "HEAD").split(),
                         ["Set", "x", "to", "3", "a.py", "new.py"])
        self.assertIn("other.py", self.git("status", "--porcelain"))  # yours stays as it was

    def test_marked_reviewed(self):
        since = cs.collect(self.home, self.cache, with_tokens=False, now=self.now)["reviewedSince"]
        self.assertEqual(since, int(self.now * 1000))  # (what chats changed before the first look isn't to review)
        self.cli("--reviewed", SID)
        self.assertGreater(cs.load_reviewed(self.cache)[SID], 0)
        self.assertIsNotNone(self.cli("--review", SID)["reviewedAt"])
        self.cli("--reviewed", SID, "--host", "gpu")  # (a host's chat: marked here)
        self.assertIn("gpu|" + SID, cs.load_reviewed(self.cache))
        self.cli("--reviewed", SID, "--off")
        self.assertEqual(cs.load_reviewed(self.cache)[SID], 0)  # not reviewed, however old its changes
        result = cs.collect(self.home, self.cache, with_tokens=False, now=self.now + 60)
        self.assertIn("gpu|" + SID, result["reviewed"])
        self.assertEqual(result["reviewedSince"], since)


class TestsAfterEditTests(PaneFixture):
    def test_tests_since_the_last_edit(self):
        t = self.now - 100
        a = str(self.folder / "a.py")
        self.chat(prompt("go", t, cwd=str(self.folder)),
                  tool_use("e1", "Edit", {"file_path": a, "old_string": "a", "new_string": "b"}, t + 1),
                  tool_result("e1", t + 2),
                  tool_use("t1", "Bash", {"command": "npm test"}, t + 3),
                  tool_result("t1", t + 4, error=True))
        cache = cs.TestsCache(self.cache / "tests.json")
        review = cache.review(self.transcript)
        self.assertEqual((review["tests"]["command"], review["tests"]["ok"]), ("npm test", False))
        # edited again since: no run counts
        with open(self.transcript, "a") as f:
            f.write(lines(tool_use("e2", "Edit", {"file_path": a, "old_string": "b", "new_string": "c"}, t + 5)))
        self.assertIsNone(cache.review(self.transcript)["tests"])
        with open(self.transcript, "a") as f:
            f.write(lines(tool_use("t2", "Bash", {"command": "cd app && npm test"}, t + 6), tool_result("t2", t + 7)))
        self.assertTrue(cache.review(self.transcript)["tests"]["ok"])
        cache.save()
        # read once: the next check reads only what was added
        again = cs.TestsCache(self.cache / "tests.json")
        with mock.patch.object(cs, "scan_tests", wraps=cs.scan_tests) as scanned:
            self.assertTrue(again.review(self.transcript)["tests"]["ok"])
        scanned.assert_not_called()
        # another copy that lists other chats (VS Code, say) keeps what this one read
        cs.TestsCache(self.cache / "tests.json").save()
        with mock.patch.object(cs, "scan_tests", wraps=cs.scan_tests) as scanned:
            self.assertTrue(cs.TestsCache(self.cache / "tests.json").review(self.transcript)["tests"]["ok"])
        scanned.assert_not_called()

    def test_no_edits_no_review(self):
        self.chat(prompt("explain", self.now - 5), tool_use("t1", "Bash", {"command": "pytest"}, self.now - 4))
        self.assertIsNone(cs.TestsCache(self.cache / "tests.json").review(self.transcript))

    def test_what_counts_as_a_test_run(self):
        runs = ["python3 -I -m unittest discover -s tests 2>&1 | tail -3", "cd x && npm test", "make -C build test",
                "./gradlew test", "pytest -q tests/test_a.py", "node --test", "go test ./...", "bash run_tests.sh",
                "npm run check && npm test"]
        others = ['git commit -m "fix pytest run"', "python3 - <<'EOF'\nimport unittest\nEOF", "ls tests/",
                  "cargo build", 'echo "a \\" pytest"']
        self.assertEqual([c for c in runs if not cs.is_test_run(c)], [])
        self.assertEqual([c for c in others if cs.is_test_run(c)], [])


class QuickChatTests(PaneFixture):
    """What makes the pane quick: --wait answers the moment the transcript
    changes; a send with no profile named works; the terminal's font."""

    def test_wait_answers_when_the_transcript_changes(self):
        t = self.now - 100
        self.chat(prompt("run the tests", t, cwd=str(self.folder)))
        stamp = self.cli("--conversation", SID)["stamp"]
        start = time.time()
        # (nothing new: unchanged once the wait is over)
        self.assertEqual(self.cli("--conversation", SID, "--if-changed", stamp, "--wait", "0.3"), {"ok": True, "unchanged": True})
        self.assertGreaterEqual(time.time() - start, 0.25)

        def later():
            time.sleep(0.3)
            with open(self.transcript, "a") as f:
                f.write(lines(text_reply("They pass.", t + 1, "m1", "end_turn")))
        import threading
        threading.Thread(target=later).start()
        start = time.time()
        answer = self.cli("--conversation", SID, "--if-changed", stamp, "--wait", "20")
        self.assertLess(time.time() - start, 5)
        self.assertEqual(answer["items"][-1]["text"], "They pass.")
        self.assertNotEqual(answer["stamp"], stamp)

    def test_your_pictures(self):
        # (the files a prompt names, then those pasted into it, saved once for the thumbnails;
        # a queued one's too; an SSH host's chat: the files it names only, nothing saved there)
        t = self.now - 100
        png = base64.b64encode(b"\x89PNG\r\n\x1a\n-a picture-").decode()
        pasted = {"type": "user", "uuid": "u-1", "timestamp": iso(t + 1), "message": {"role": "user", "content": [
            {"type": "text", "text": "[Image #1] what's this?"},
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": png}}]}}
        self.chat(prompt("look: [Image: /home/me/.cache/talpy-den/images/a.png] and [Image: /tmp/b.jpg]", t, cwd=str(self.folder)),
                  pasted,
                  {"type": "queue-operation", "operation": "enqueue", "timestamp": iso(t + 2),
                   "content": "and [Image: /home/me/.cache/talpy-den/images/c.png]"})
        folder = self.cache / "images"
        items = pane.conversation(self.transcript, 120, folder)[0]
        self.assertEqual([i.get("pictures") for i in items], [
            ["/home/me/.cache/talpy-den/images/a.png", "/tmp/b.jpg"], [str(folder / "chat-u-1-1.png")],
            ["/home/me/.cache/talpy-den/images/c.png"]])
        saved = folder / "chat-u-1-1.png"
        self.assertEqual(saved.read_bytes(), b"\x89PNG\r\n\x1a\n-a picture-")
        self.assertEqual(saved.stat().st_mode & 0o777, 0o600)
        made = saved.stat().st_mtime_ns
        pane.conversation(self.transcript, 120, folder)   # (read again: not written again)
        self.assertEqual(saved.stat().st_mtime_ns, made)
        self.assertEqual([i.get("pictures") for i in pane.conversation(self.transcript)[0]][1], None)   # (no folder: an SSH host's)

    def test_wait_isnt_sent_to_a_host(self):
        with mock.patch("remote.host_answer", return_value={"ok": True, "unchanged": True}) as asked:
            self.cli("--conversation", SID, "--if-changed", "1:2/120", "--wait", "50", "--host", "gpu")
        self.assertEqual(asked.call_args[0][1], ["--conversation", SID, "--if-changed", "1:2/120"])

    def test_no_profile_named_matches_none(self):
        profile = cs.discover_profiles(self.home)[0]
        self.assertFalse(cs.matches_profile(profile, None))
        self.assertFalse(cs.matches_profile(profile, ""))

    def test_terminal_font(self):
        cfg = self.home / ".config"
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(cfg), "XDG_DATA_HOME": str(self.home / ".local/share")}):
            # Konsole's built-in profile: none named (the pane takes a fixed-width one)
            self.assertEqual(pane.terminal_font(self.home), {"ok": True, "family": "", "terminal": "konsole"})
            write(cfg / "konsolerc", "[Desktop Entry]\nDefaultProfile=Mine.profile\n")
            write(self.home / ".local/share/konsole/Mine.profile",
                  "[General]\nName=Mine\n\n[Appearance]\nColorScheme=Breeze\nFont=JetBrains Mono,12,-1,5,400,0,0,0,0,0\n")
            self.assertEqual(pane.terminal_font(self.home)["family"], "JetBrains Mono")
            # the terminal picked in System Settings, from its own settings
            write(cfg / "kdeglobals", "[General]\nTerminalApplication=kitty\n")
            write(cfg / "kitty/kitty.conf", "# fonts\nfont_family      Fira Code\nfont_size 11\n")
            self.assertEqual(pane.terminal_font(self.home), {"ok": True, "family": "Fira Code", "terminal": "kitty"})
            write(cfg / "kitty/kitty.conf", 'font_family family="Iosevka Term" style=Regular\n')
            self.assertEqual(pane.terminal_font(self.home)["family"], "Iosevka Term")
            write(cfg / "kdeglobals", "[General]\nTerminalApplication=alacritty\n")
            write(cfg / "alacritty/alacritty.toml", '[font]\nsize = 11\n\n[font.normal]\nfamily = "Hack"\n')
            self.assertEqual(pane.terminal_font(self.home)["family"], "Hack")
            write(cfg / "kdeglobals", "[General]\nTerminalApplication=foot\n")
            write(cfg / "foot/foot.ini", "[main]\nfont=Source Code Pro:size=10,Noto Color Emoji\n")
            self.assertEqual(pane.terminal_font(self.home)["family"], "Source Code Pro")
            write(cfg / "kdeglobals", "[General]\nTerminalApplication=ghostty\n")
            write(cfg / "ghostty/config", 'theme = dark\nfont-family = "Cascadia Mono"\n')
            self.assertEqual(pane.terminal_font(self.home)["family"], "Cascadia Mono")
            write(cfg / "kdeglobals", "[General]\nTerminalApplication=xfce4-terminal\n")
            write(cfg / "xfce4/terminal/terminalrc", "[Configuration]\nFontName=DejaVu Sans Mono 12\n")
            self.assertEqual(pane.terminal_font(self.home)["family"], "DejaVu Sans Mono")
        self.assertEqual(self.cli("--terminal-font")["ok"], True)


class RelayTests(PaneFixture):
    def test_on_and_off(self):
        shared = self.home / ".claude-shared/settings.json"
        mine = {"matcher": "Bash", "hooks": [{"type": "command", "command": "mine"}]}
        write(shared, {"model": "opus", "hooks": {
            "PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "guard"}]}],
            "PermissionRequest": [mine]}})
        (self.home / ".claude-work/settings.json").symlink_to(shared)
        self.assertEqual(pane.relay(self.home, [], True), (True, "Permission prompts can be answered from Talpy Den"))
        self.assertTrue((self.home / ".claude-work/settings.json").is_symlink())  # (written through the link)
        groups = json.loads(shared.read_text())["hooks"]["PermissionRequest"]
        hook = self.home / ".local/share/talpy-den/permission-hook.py"
        self.assertEqual(groups[0], mine)
        self.assertEqual(groups[1]["hooks"][0], {"type": "command", "command": f"[ -f {hook} ] || exit 0; exec python3 -I {hook}",
                                                 "timeout": pane.HOOK_TIMEOUT_S})
        self.assertEqual(hook.read_text(), (CODE / "permission_hook.py").read_text())
        self.assertTrue(self.cli("--relay", "status")["on"])
        self.assertEqual(pane.relay(self.home, [], True)[1],
                         "Permission prompts can be answered from Talpy Den (they could already)")
        pane.relay(self.home, [], False)
        data = json.loads(shared.read_text())
        self.assertEqual((data["hooks"]["PermissionRequest"], data["model"]), ([mine], "opus"))
        self.assertFalse(hook.exists())
        self.assertFalse(self.cli("--relay", "status")["some"])

    def test_an_entry_written_before_is_replaced_not_added_to(self):
        # Before: python3 -I PATH (no exec, unquoted), also in the folder of
        # the first name. Still the hook's: on, it's replaced (once); off, it goes
        settings = self.home / ".claude-work/settings.json"
        data = self.home / ".local/share"
        older = [f"python3 -I {data}/talpy-den/permission-hook.py", f"python3 -I {data}/claude-widget/permission-hook.py"]
        mine = {"matcher": "Bash", "hooks": [{"type": "command", "command": "mine"}]}
        write(settings, {"hooks": {"PermissionRequest": [mine] + [
            {"matcher": "*", "hooks": [{"type": "command", "command": c, "timeout": 86400}]} for c in older]}})
        self.assertTrue(self.cli("--relay", "status")["some"])
        self.assertEqual(pane.relay(self.home, [], True), (True, "Permission prompts can be answered from Talpy Den"))
        groups = json.loads(settings.read_text())["hooks"]["PermissionRequest"]
        hook = pane.hook_path(self.home, "relay")
        self.assertEqual(groups, [mine, {"matcher": "*", "hooks": [
            {"type": "command", "command": f"[ -f {hook} ] || exit 0; exec python3 -I {hook}", "timeout": pane.HOOK_TIMEOUT_S}]}])
        self.assertEqual(pane.relay(self.home, [], True)[1],
                         "Permission prompts can be answered from Talpy Den (they could already)")
        # off takes an older one out too
        write(settings, {"hooks": {"PermissionRequest": [mine, {"matcher": "*", "hooks": [{"type": "command", "command": older[1]}]}]}})
        pane.relay(self.home, [], False)
        self.assertEqual(json.loads(settings.read_text())["hooks"]["PermissionRequest"], [mine])

    def test_a_hook_whose_copy_is_gone_leaves_the_prompt_to_claude(self):
        # (its folder cleaned up by hand: no answer, status 0; python3 would end with 2, a refusal)
        command = pane.hook_command(self.home / "gone dir/permission-hook.py")
        r = subprocess.run(["sh", "-c", command], input=b"{}", capture_output=True, timeout=30)
        self.assertEqual((r.returncode, r.stdout), (0, b""))
        # settings an older version wrote get it, at the next status check
        settings = self.home / ".claude-work/settings.json"
        older = f"exec python3 -I {pane.hook_path(self.home, 'relay')}"
        mine = {"matcher": "Bash", "hooks": [{"type": "command", "command": "mine"}]}
        write(settings, {"model": "opus", "hooks": {"PermissionRequest": [mine, {"matcher": "*", "hooks": [
            {"type": "command", "command": older, "timeout": pane.HOOK_TIMEOUT_S}]}]}})
        self.assertEqual(cs.upgrade_hook_settings(self.home), 1)
        data = json.loads(settings.read_text())
        self.assertEqual((data["model"], data["hooks"]["PermissionRequest"]), ("opus", [mine, {"matcher": "*", "hooks": [
            {"type": "command", "command": pane.hook_command(pane.hook_path(self.home, "relay")), "timeout": pane.HOOK_TIMEOUT_S}]}]))
        before = settings.stat().st_mtime_ns
        self.assertEqual(cs.upgrade_hook_settings(self.home), 0)  # (once)
        self.assertEqual(settings.stat().st_mtime_ns, before)

    def test_a_folder_name_with_a_space(self):
        # The command Claude runs (sh -c) finds the hook, and the hook is
        # Claude's child (exec): here, this test's
        data = Path(self.tmp.name) / "it's my data"
        with mock.patch.dict(os.environ, {"XDG_DATA_HOME": str(data)}):
            pane.relay(self.home, [], True)
            pane.live(self.home, [], True)
        hooks = json.loads((self.home / ".claude-work/settings.json").read_text())["hooks"]
        relay = hooks["PermissionRequest"][0]["hooks"][0]["command"]
        live_hook = hooks["SessionStart"][0]["hooks"][0]["command"]
        relay_hook, live_copy = str(data / "talpy-den/permission-hook.py"), str(data / "talpy-den/live-hook.py")
        self.assertEqual(shlex.split(relay), ["[", "-f", relay_hook, "]", "||", "exit", "0;", "exec", "python3", "-I", relay_hook])
        self.assertEqual(shlex.split(live_hook), ["[", "-f", live_copy, "]", "||", "exit", "0;", "exec", "python3", "-I", "-S", live_copy])
        cache = Path(self.tmp.name) / "c"
        env = dict(os.environ, HOME=str(self.home), XDG_CACHE_HOME=str(cache), PATH=f"{Path(sys.executable).parent}:/usr/bin:/bin")
        event = {"session_id": SID, "hook_event_name": "UserPromptSubmit", "cwd": "/tmp"}
        done = subprocess.run(["/bin/sh", "-c", live_hook], input=json.dumps(event), env=env, capture_output=True,
                              text=True, timeout=30)
        self.assertEqual((done.returncode, done.stderr), (0, ""))
        self.assertEqual(json.loads((cache / f"talpy-den/live/{SID}.json").read_text())["pid"], os.getpid())
        hook = subprocess.Popen(["/bin/sh", "-c", relay], stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env)
        self.addCleanup(lambda: (hook.poll() is None and hook.kill(), hook.wait(), hook.stdout.close()))
        hook.stdin.write(json.dumps({"session_id": SID, "tool_name": "Bash", "tool_input": {"command": "ls"}}).encode())
        hook.stdin.close()
        deadline = time.time() + 5
        while time.time() < deadline and not cs.permission_requests(cache / "talpy-den"):
            time.sleep(0.05)
        (request,) = cs.permission_requests(cache / "talpy-den").values()
        self.assertEqual((request["pid"], request["hookPid"]), (os.getpid(), hook.pid))   # (exec: the shell is the hook)

    def test_on_a_host_it_gets_the_hook(self):
        with mock.patch("remote.host_answer", return_value={"ok": True, "message": "ok"}) as asked:
            self.cli("--relay", "on", "--host", "gpu")
        args = asked.call_args[0][1]
        self.assertEqual(args[:2], ["--relay", "on"])
        self.assertEqual(base64.b64decode(args[args.index("--hook-source") + 1]),
                         (CODE / "permission_hook.py").read_bytes())


if __name__ == "__main__":
    unittest.main()


MARKDOWN = CODE.parent / "ui/markdown.mjs"
STYLE = {"pt": 11, "mono": "Hack", "text": "#eeeeee", "strong": "#3daee9", "muted": "#999999", "accent": "#d97757", "heading": "#d97757",
         "code": "#b1b9f9", "codeBg": "#333333", "blockBg": "#111111", "border": "#444444", "link": "#3daee9"}


def markdown(call):
    """What node gets from markdown.mjs for call (an expression with toHtml, codeBlocks, …)."""
    if not shutil.which("node"):
        raise unittest.SkipTest("node isn't installed")
    code = (f"import * as Md from {json.dumps(str(MARKDOWN))};\nconst style = {json.dumps(STYLE)};\n"
            f"process.stdout.write(JSON.stringify({call}));")
    out = subprocess.run(["node", "--input-type=module", "-e", code], capture_output=True, text=True, timeout=60)
    if out.returncode:
        raise AssertionError(out.stderr)
    return json.loads(out.stdout)


class PaneMarkdownTests(unittest.TestCase):
    """Claude's replies as Qt rich text in the Plasma pane (markdown.mjs)."""

    def test_nothing_in_a_reply_becomes_a_tag(self):
        html = markdown('Md.toHtml("<img src=x onerror=1> & <b>bold?</b>\\n\\n```\\n<script>x</script>\\n```", style)')
        self.assertNotIn("<img", html)
        self.assertNotIn("<script", html)
        self.assertNotIn("<b>bold", html)
        self.assertIn("&lt;img src=x onerror=1&gt; &amp; &lt;b&gt;", html)
        self.assertIn("&lt;script&gt;x&lt;/script&gt;", html)

    def test_links_only_to_the_web_or_mail(self):
        html = markdown('Md.toHtml("[a](https://example.org/x) [b](javascript:alert(1)) [c](file:///etc/passwd) '
                        'https://example.com/y.", style)')
        self.assertEqual(re.findall(r'href="([^"]*)"', html), ["https://example.org/x", "https://example.com/y"])
        self.assertIn(" b", html)  # (as text)
        self.assertIn(" c ", html)

    def test_a_link_keeps_parentheses_in_its_address(self):
        html = markdown('Md.toHtml("[C](https://en.wikipedia.org/wiki/C_(programming_language)) and [x](https://a.b/c).", style)')
        self.assertEqual(re.findall(r'href="([^"]*)"', html),
                         ["https://en.wikipedia.org/wiki/C_(programming_language)", "https://a.b/c"])
        self.assertIn("</a> and <a", html)

    def test_a_bare_address_keeps_its_parentheses(self):
        html = markdown('Md.toHtml("see https://en.wikipedia.org/wiki/Rust_(programming_language) now, or https://a.b/c).", style)')
        self.assertEqual(re.findall(r'href="([^"]*)"', html),
                         ["https://en.wikipedia.org/wiki/Rust_(programming_language)", "https://a.b/c"])
        self.assertIn("</a> now", html)

    def test_a_heading_keeps_a_hash_at_its_end(self):
        texts = markdown('["## Notes on C#", "### F#", "# Title ##", "## Issue #42", "# x #"].map(t => Md.blocks(t)[0].text)')
        self.assertEqual(texts, ["Notes on C#", "F#", "Title", "Issue #42", "x"])

    def test_a_code_blocks_colors(self):
        # (in its language's colors, as a tool's listing: by the name after its ```)
        style = dict(STYLE, syntax={"kw": "#ff7b72", "lit": "#79c0ff", "str": "#a5d6ff", "com": "#8b949e", "num": "#79c0ff",
                                    "fn": "#d2a8ff", "key": "#7ee787"})
        html = markdown(f"Md.toHtml({json.dumps(chr(96) * 3 + 'python' + chr(10) + 'def f(): return 1  # one' + chr(10) + chr(96) * 3)}, "
                        f"{json.dumps(style)})")
        self.assertIn('<span style="color:#ff7b72">def</span>', html)
        self.assertIn('<span style="color:#8b949e"># one</span>', html)
        # a language it doesn't know, or no colors given: as written
        self.assertIn("&lt;x&gt;", markdown(f"Md.toHtml({json.dumps(chr(96) * 3 + 'brainfuck' + chr(10) + '<x>' + chr(10) + chr(96) * 3)}, style)"))

    def test_blocks(self):
        text = ("# Title\n\nSome **bold**, *it*, snake_case_name and `code`.\n\n## Steps\n\n1. one\n2. two\n"
                "   - nested\n\n```python\nprint(1)\n```\n\n> quoted\n\n---\n\n| a | b |\n|---|---|\n| 1 | 2 |\n")
        kinds = markdown(f"Md.blocks({json.dumps(text)}).map(b => b.kind)")
        self.assertEqual(kinds, ["heading", "para", "heading", "list", "code", "quote", "rule", "table"])
        html = markdown(f"Md.toHtml({json.dumps(text)}, style)")
        self.assertIn("snake_case_name", html)
        self.assertIn('<b style="color:#3daee9">bold</b>', html)
        self.assertIn("<i>it</i>", html)
        self.assertEqual(html.count("<ol"), html.count("</ol>"))
        self.assertEqual(html.count("<ul"), html.count("</ul>"))
        self.assertIn('href="copy:0"', html)
        self.assertEqual(markdown(f"Md.codeBlocks({json.dumps(text)})"), ["print(1)"])

    def test_bold_ends_at_its_own_closing_marks(self):
        # (a one-character bold before another bold on the line, as **Edit**, **✕** and **Send now**,
        # was bold up to the last one's closing marks; a bold never runs over another's marks)
        for text, want in [("with **Edit**, **✕** and **Send now**.", ["Edit", "✕", "Send now"]),
                           ("f(*args, **kw) and **bold**", ["bold"]), ("__x__ y __z__", ["x", "z"])]:
            html = markdown(f"Md.inline({json.dumps(text)}, style)")
            self.assertEqual(re.findall(r"<b[^>]*>(.*?)</b>", html), want, html)
        self.assertEqual(markdown('Md.inline("~~1~~ or ~~2~~", style)'), "<s>1</s> or <s>2</s>")

    def test_asterisks_in_globs_and_args_stay(self):
        # (a closing * or ** comes right after text, and not between punctuation and a word;
        # __x__ like _x_ only between words' edges)
        for text in ["Look at the *.py and *.js files", "Use **kwargs and *args in f(*args, **kwargs)",
                     "foo__bar__baz", "2 * 3 * 4"]:
            html = markdown(f"Md.toHtml({json.dumps(text)}, style)")
            self.assertNotIn("<i>", html, text)
            self.assertNotIn("<b>", html, text)
            self.assertEqual(html.count("*"), text.count("*"), text)
        html = markdown('Md.toHtml("**Note:** a *b* and __c__, a*b*c, ~~d~~", style)')
        for part in ['<b style="color:#3daee9">Note:</b>', "<i>b</i>", '<b style="color:#3daee9">c</b>', "a<i>b</i>c", "<s>d</s>"]:
            self.assertIn(part, html)

    def test_escapes_and_pipes_in_a_table(self):
        html = markdown('Md.toHtml("| cmd | what |\\n|---|---|\\n| `a \\\\| b` | pipe \\\\| x |", style)')
        self.assertEqual(len(re.findall(r"<td>", html)), 2)
        self.assertIn("a | b", html)
        self.assertIn("pipe | x", html)
        self.assertNotIn("\\", html)
        html = markdown('Md.toHtml("text with \\\\*escaped\\\\* stars and \\\\_this\\\\_", style)')
        self.assertIn("text with *escaped* stars and _this_", html)

    def test_copy_leaves_out_the_bang_of_a_command_for_claudes_prompt(self):
        # (Claude writes "! cmd" for you to type in its prompt; the pane shows it, Copy gives the command)
        cases = {"! chmod 644 scripts/x.py": "chmod 644 scripts/x.py", "! git add a\n\n!  git commit": "git add a\n\ngit commit"}
        for code in ["if ! grep -q x f; then echo no; fi", "! git add a\ngit commit", "!pip install x", "!", "", "a != b"]:
            cases[code] = code
        got = markdown(f"{json.dumps(list(cases))}.map(Md.clipboardCode)")
        self.assertEqual(got, list(cases.values()))
        fenced = json.dumps(chr(96) * 3 + chr(10) + "! chmod 644 x" + chr(10) + chr(96) * 3)
        self.assertIn("! chmod", markdown(f"Md.toHtml({fenced}, style)"))
        # (Copied a moment after a click: the pane gives that block's index)
        self.assertIn('href="copy:0"', markdown(f"Md.toHtml({fenced}, style, 0)"))
        self.assertIn(">Copied</a>", markdown(f"Md.toHtml({fenced}, style, 0)"))
        self.assertIn(">Copy</a>", markdown(f"Md.toHtml({fenced}, style)"))

    def test_a_code_block_in_a_list_item_loses_the_lists_indent(self):
        text = "1. Run:\n   ```python\n   if x:\n       go()\n   ```\n2. Next"
        self.assertEqual(markdown(f"Md.codeBlocks({json.dumps(text)})"), ["if x:\n    go()"])

    def test_tables_have_no_margin_of_their_own(self):
        # (Qt Quick paints a table's background over its margin: the gap above
        # one is a spacer line, never the table's own margin)
        html = markdown('Md.toHtml("text\\n\\n```\\ncode\\n```\\n\\n| a |\\n|---|\\n| 1 |", style)')
        for table in re.findall(r"<table[^>]*>", html):
            self.assertNotIn("margin-top", table)

    def test_it_runs_in_qt_javascript(self):
        # Qt's JavaScript: no ?. or ??, no lookbehind in a pattern
        text = "\n".join(line for line in MARKDOWN.read_text().splitlines() if not line.lstrip().startswith("//"))
        self.assertNotRegex(text, r"\?\.[\w(\[]|\?\?")
        self.assertNotIn("(?<", text)


UI = Path(__file__).resolve().parent.parent / "package/contents/ui"


@unittest.skipUnless(shutil.which("node"), "node isn't installed")
class CodeViewTests(unittest.TestCase):
    """codeview.mjs (shared with the VS Code extension) and codehtml.mjs (the pane's rich text)."""

    def node(self, script):
        code = (f"import * as C from {json.dumps(str(UI / 'codeview.mjs'))};\n"
                f"import * as H from {json.dumps(str(UI / 'codehtml.mjs'))};\n" + script)
        out = subprocess.run(["node", "--input-type=module", "-e", code], capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def test_rows_side_by_side_and_what_changed(self):
        r = self.node("""
const lines = ['@@ -10,3 +10,4 @@ tick', ' a', '-let b = foo(2);', '+let b = foo(3);', '+c', ' d', '… (2 more lines)'];
const rows = C.diffRows(lines);
console.log(JSON.stringify({
    rows: rows.map(r => [r.kind, r.old, r.new]),
    split: C.splitRows(rows).map(p => [p.left && p.left.kind, p.right && p.right.kind]),
    changed: C.changed('let b = foo(2);', 'let b = foo(3);'), unlike: C.changed('abc', 'xyz'),
    plain: C.diffRows(['@@ @@', '-a', '+b']).map(r => r.old), made: C.diffRows(['@@ -0,0 +1,2 @@', '+a', '+b']).map(r => r.new),
    read: C.readLines('    12\\tx = 1\\n    13\\ty'), notRead: C.readLines('Error: no such file'),
    js: C.highlight('const x = f("a") // hi', 'js'), lang: [C.language('a/b.qml'), C.language('Makefile'), C.language('x.bin')]
}));""")
        self.assertEqual(r["rows"], [["hunk", None, None], ["same", 10, 10], ["del", 11, None], ["add", None, 11],
                                     ["add", None, 12], ["same", 12, 13], ["note", None, None]])
        self.assertEqual(r["split"], [["hunk", "hunk"], ["same", "same"], ["del", "add"], [None, "add"], ["same", "same"],
                                      ["note", "note"]])
        self.assertEqual((r["changed"], r["unlike"]), ([12, 13, 13], None))
        self.assertEqual((r["plain"], r["made"]), ([None, None, None], [None, 1, 2]))
        self.assertEqual((r["read"], r["notRead"]), ([{"no": 12, "text": "x = 1"}, {"no": 13, "text": "y"}], None))
        self.assertEqual(r["js"], [["kw", "const"], ["", " x = "], ["fn", "f"], ["", "("], ["str", '"a"'], ["", ") "],
                                   ["com", "// hi"]])
        self.assertEqual(r["lang"], ["js", "sh", ""])

    def test_html_escapes_everything_and_folds(self):
        r = self.node("""
const p = H.palette(true, '#eeeeee', '#202020', 'monospace', 10);
const lines = ['@@ -1,2 +1,2 @@', '-<b>old</b>', '+<img src=x onerror=alert(1)>', ...Array.from({ length: 20 }, (_, i) => ' ctx ' + i)];
console.log(JSON.stringify({ unified: H.diffHtml(lines, 'a.html', p, 0), folded: H.diffHtml(lines, 'a.html', p, 6),
    split: H.splitHtml(lines, 'a.html', p, 0), tool: H.toolHtml({ name: 'Bash', input: '$ echo "<x>"', output: '<y>' }, '', p),
    listing: H.listingHtml(['<z>', '… (3 more lines)'], 'a.md', p, 0) }));""")
        for name, html in r.items():
            for raw in ("<b>old", "<img", "<x>", "<y>", "<z>"):
                self.assertNotIn(raw, html, name)
        self.assertIn("… 17 more", r["folded"])
        self.assertNotIn("ctx 10", r["folded"])

    def test_a_wrapped_line_goes_on_under_its_code(self):
        # (the hanging indent is as wide as what comes before the code: a number of w digits, a space,
        # the mark and a space (a listing: number and two spaces), in characters of the code's size)
        r = self.node("""
const lines = ['@@ -9,2 +9,2 @@', '-a', '+b', ' c'];
const at = (html) => html.match(/margin-left:(\\d+)px; text-indent:-(\\d+)px/).slice(1).map(Number);
const guess = H.palette(true, '#eeeeee', '#202020', 'monospace', 11.5);
const measured = H.palette(true, '#eeeeee', '#202020', 'monospace', 11.5, 7);
console.log(JSON.stringify({ diff: at(H.diffHtml(lines, 'a.py', guess, 0)), diffMeasured: at(H.diffHtml(lines, 'a.py', measured, 0)),
    plain: at(H.diffHtml(['@@ @@', '-a', '+b'], '', measured, 0)), listing: at(H.listingHtml(['x', 'y'], 'a.py', measured, 0)) }));""")
        self.assertEqual(r["diff"], [round(5 * 11.5 * 0.88 * 1.333 * 0.6)] * 2)
        self.assertEqual(r["diffMeasured"], [35, 35])
        self.assertEqual(r["plain"], [14, 14])
        self.assertEqual(r["listing"], [21, 21])


