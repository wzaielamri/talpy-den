"""The chat pane (pane.py): a chat's conversation, sending it a message,
answering its permission prompt (with the hook, permission_hook.py, or keys
in tmux) and reviewing what it changed (Undo, Commit, Mark reviewed); and
what the status rows carry for it (talpy_den.py)."""
import claude_guard  # noqa: F401  (first: no test runs the real claude)
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
import replies  # noqa: E402
import commands as commands_py  # noqa: E402
import turns  # noqa: E402

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
        self.assertEqual(names["/review"], {"name": "/review", "about": "Our own review", "kind": "project", "run": "here"})
        self.assertEqual((names["/compact"]["kind"], names["/compact"]["run"]), ("Claude", "here"))
        self.assertEqual(got["typed"]["settings"], {"run": "terminal", "of": "/config", "why": "opens Claude's settings panel"})
        self.assertIn(os.path.join("src", "app.py"), got["files"])
        self.assertFalse(any("node_modules" in f for f in got["files"]))
        self.assertEqual(got["history"], ["old one", "fix it"])
        # a new chat in Talpy Chat (none to read yet): its folder's, on its account
        with mock.patch.dict(os.environ, {"PATH": "/nonexistent"}):
            new = self.cli("--complete", "-", "--cwd", str(self.folder), "--profile", ".claude-work")
        self.assertEqual((new["cwd"], new["commands"], new["files"], new["history"]),
                         (str(self.folder), got["commands"], got["files"], got["history"]))
        self.assertFalse(self.cli("--complete", "-", "--cwd", str(self.folder), "--profile", ".claude-nope")["ok"])

    def test_a_command_linked_to_a_device_or_a_pipe_isnt_read(self):
        # (a repo can ship .claude/commands/deploy.md -> /dev/zero: reading it whole took all the memory)
        commands, skills = self.folder / ".claude/commands", self.folder / ".claude/skills"
        (skills / "x").mkdir(parents=True)
        commands.mkdir(parents=True)
        os.symlink("/dev/null", commands / "deploy.md")
        os.mkfifo(commands / "wait.md")
        os.mkfifo(skills / "x/SKILL.md")
        write(commands / "test.md", "Run the tests" + "x" * 9000)
        self.assertEqual([c["name"] for c in commands_py.command_files(commands, "project")], ["/test"])
        self.assertEqual(commands_py.skill_dirs(skills, "project"), [])

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
    def test_thinking_shown_as_updates_is_a_line_of_its_own(self):
        # (when thinking is shown as updates, Claude Code writes a line summing
        # up Claude's thinking: shown as thinking, not as Claude's reply, as
        # its terminal shows it; thinking Claude keeps to itself has no text)
        t = self.now - 100

        def thinking(text, ts, mid="m1", display="updates"):
            return {"type": "assistant", "timestamp": iso(ts), "thinkingDisplay": display,
                    "message": {"id": mid, "role": "assistant", "content": [{"type": "thinking", "thinking": text, "signature": "x"}]}}
        self.chat(prompt("tidy the tags", t, cwd=str(self.folder)),
                  thinking("", t + 1),
                  thinking("Making every tag start with a capital.", t + 2),
                  tool_use("t1", "Bash", {"command": "ls"}, t + 3, "m1"),
                  tool_result("t1", t + 4),
                  thinking("Pushing it.", t + 5, "m2"),
                  thinking("Then the tags.", t + 5, "m2"),
                  text_reply("Done: every tag has a capital.", t + 6, "m2"),
                  thinking("A thought of its own.", t + 7, "m3", display=None))
        items, _ = pane.conversation(self.transcript)
        self.assertEqual([(i["kind"], i["key"], i.get("text") or i.get("line"), i.get("thinking")) for i in items][1:],
                         [("claude", "m1/thinking", "Making every tag start with a capital.", True),
                          ("tool", "t1", "Bash: ls", None),
                          ("claude", "m2/thinking", "Pushing it.\n\nThen the tags.", True),
                          ("claude", "m2", "Done: every tag has a capital.", None)])

    def test_a_prompt_from_the_claude_code_panel_shows(self):
        # (the panel puts the file open in the editor, or the lines selected there, in front of what
        # you typed, each a text block of its own: such a prompt started with "<" and was left out,
        # 133 of 213 of a real account's panel prompts)
        t = self.now - 100

        def panel(ts, *texts):
            return {"type": "user", "timestamp": iso(ts), "entrypoint": "claude-vscode", "promptSource": "sdk", "cwd": str(self.folder),
                    "message": {"role": "user", "content": [{"type": "text", "text": x} for x in texts]}}
        opened = "<ide_opened_file>The user opened the file /x/a.c in the IDE. This may or may not be related to the current task.</ide_opened_file>"
        picked = "<ide_selection>The user selected the lines 3 to 4 from /x/a.c:\nint a;\n</a>\n\nThis may or may not be related.</ide_selection>"
        self.chat(panel(t, opened, "do step 4"),
                  text_reply("Done.", t + 1, "m1", stop="end_turn"),
                  panel(t + 2, opened, picked, "and <b>this</b> one?"),
                  text_reply("Yes.", t + 3, "m2", stop="end_turn"),
                  panel(t + 4, opened))   # (a note alone: nothing of yours)
        items, _ = pane.conversation(self.transcript)
        self.assertEqual([(i["kind"], i["text"]) for i in items],
                         [("you", "do step 4"), ("claude", "Done."), ("you", "and <b>this</b> one?"), ("claude", "Yes.")])
        self.assertEqual(cs.read_chat_info(self.transcript, self.transcript.stat().st_size)[0], "do step 4")   # (its name: your first words)
        self.assertEqual(pane.typed_text([{"type": "text", "text": picked}, {"type": "text", "text": "queued from the panel"}]),
                         "queued from the panel")
        self.assertEqual(cs.typed_part("<ide_opened_file>never closed"), "<ide_opened_file>never closed")

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

    def test_a_wake_up_claude_scheduled_isnt_yours(self):
        # (ScheduleWakeup or /loop: Claude Code 2.1.318 writes its prompt as enqueue, a scheduled_task_fire,
        # dequeue, then a meta user entry of the system's; it showed as yours, at the end, for good)
        t = self.now - 100
        wake = "continue the panel improvment work"
        self.chat(prompt("go on", t, cwd=str(self.folder)), text_reply("Working on it.", t + 1, "m1", "end_turn"),
                  {"type": "queue-operation", "operation": "enqueue", "timestamp": iso(t + 2), "content": wake},
                  {"type": "system", "subtype": "scheduled_task_fire", "uuid": "f1", "timestamp": iso(t + 2),
                   "content": "Claude resuming /loop wakeup (Nov 6 12:48am)", "isMeta": False, "prompt": wake, "taskKind": "loop"},
                  {"type": "queue-operation", "operation": "dequeue", "timestamp": iso(t + 2)},
                  {"type": "user", "uuid": "w1", "timestamp": iso(t + 2), "isMeta": True, "promptSource": "system",
                   "message": {"role": "user", "content": wake}},
                  text_reply("Picking it up again.", t + 3, "m2", "end_turn"),
                  prompt("thanks", t + 4, cwd=str(self.folder)))
        items = pane.conversation(self.transcript)[0]
        self.assertEqual([(i["kind"], i["text"]) for i in items],
                         [("you", "go on"), ("claude", "Working on it."), ("note", "Claude woke itself up: " + wake),
                          ("claude", "Picking it up again."), ("you", "thanks")])

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
        # (with its word tables for Claude's questions: --suggest reads them there)
        asked.assert_called_once_with("gpu", ["--conversation", SID, "--profile", ".claude-work", "--limit", "40"],
                                      name="pane.py", also=("reply_words.py", "replies.py", "commands.py", "turns.py", "chatpick.py", "made.py"),
                                      timeout=60)


# Claude Code's own fixed sentences around a No (always in English; the note after them is yours)
REFUSED = ("The user doesn't want to proceed with this tool use. The tool use was rejected (eg. if it was a file edit, "
           "the new_string was NOT written to the file). ")
SAID_TO_CLAUDE = REFUSED + "To tell you how to proceed, the user said:\n"
STOPPED = REFUSED + "STOP what you are doing and wait for the user to tell you how to proceed."
BY_YOU = {"decision": "reject", "source": "user_reject"}


def answered(tid, ts, text="ok", error=False, **kw):
    """A tool result entry, with what Claude Code writes beside it (toolUseResult, permissionDecision…)."""
    return dict(tool_result(tid, ts, error=error, text=text), **kw)


class AnswersInChatTests(PaneFixture):
    """Your answers in the chat (A11): what Claude asked, on its tool item
    ("asked"), and what you said, as yours right after it."""

    QUESTION = {"question": "Which colour should the logo be?", "header": "Colour", "multiSelect": False,
                "options": [{"label": "Teal", "description": "calm"}, {"label": "Amber (Recommended)", "description": "warm"}]}
    TOPPINGS = {"question": "Which toppings?", "header": "Toppings", "multiSelect": True,
                "options": [{"label": "Basil"}, {"label": "Figs, dried"}, {"label": "Honey"}]}

    def items(self, *entries):
        t = self.now - 100
        self.chat(prompt("make a logo", t, cwd=str(self.folder)), *entries)
        return pane.conversation(self.transcript)[0]

    def ask(self, ts, *questions, tid="q1"):
        return tool_use(tid, "AskUserQuestion", {"questions": list(questions)}, ts, "m1")

    def test_one_question(self):
        t = self.now - 90
        items = self.items(self.ask(t, self.QUESTION),
                           answered("q1", t + 5, 'Your questions have been answered: "…"="Teal".', toolUseResult={
                               "questions": [self.QUESTION], "answers": {self.QUESTION["question"]: "Teal"}}))
        tool, you = items[1], items[2]
        self.assertEqual(tool["asked"]["state"], "answered")
        self.assertEqual([(q["header"], q["question"], q["picked"]) for q in tool["asked"]["questions"]],
                         [("Colour", "Which colour should the logo be?", ["Teal"])])
        self.assertEqual([o["label"] for o in tool["asked"]["questions"][0]["options"]], ["Teal", "Amber (Recommended)"])
        self.assertEqual(tool["summary"], "Answered")
        self.assertEqual({k: you[k] for k in ("kind", "key", "text", "answered")},
                         {"kind": "you", "key": "q1/answer", "text": "Teal", "answered": "question"})
        self.assertEqual(you["answers"], [{"header": "Colour", "question": "Which colour should the logo be?",
                                           "answer": "Teal", "notes": ""}])
        self.assertEqual(you["at"], int((t + 5) * 1000))

    def test_still_asking(self):
        items = self.items(self.ask(self.now - 90, self.QUESTION))
        self.assertEqual((items[-1]["status"], items[-1]["asked"]["state"], items[-1]["summary"]), ("open", "open", ""))
        self.assertEqual(items[-1]["asked"]["questions"][0]["picked"], [])

    def test_several_questions_multi_select_typed_and_notes(self):
        t = self.now - 90
        third = {"question": "Any slogan?", "header": "", "multiSelect": False, "options": [{"label": "None"}]}
        given = {self.QUESTION["question"]: "Amber (Recommended)",
                 self.TOPPINGS["question"]: 'Basil, "Figs, dried", a little salt',   # (as Claude's dialog joins them)
                 third["question"]: "Bright and simple"}
        items = self.items(self.ask(t, self.QUESTION, self.TOPPINGS, third),
                           answered("q1", t + 5, toolUseResult={
                               "questions": [self.QUESTION, self.TOPPINGS, third], "answers": given,
                               "annotations": {self.QUESTION["question"]: {"preview": "…", "notes": " a soft one "}}}))
        tool, you = items[1], items[2]
        self.assertEqual([q["picked"] for q in tool["asked"]["questions"]], [["Amber (Recommended)"], ["Basil", "Figs, dried"], []])
        self.assertEqual(you["text"], 'Colour: Amber (Recommended)\na soft one\nToppings: Basil, "Figs, dried", a little salt\n'
                                      "Any slogan?: Bright and simple")
        self.assertEqual([(a["header"], a["answer"], a["notes"]) for a in you["answers"]],
                         [("Colour", "Amber (Recommended)", "a soft one"), ("Toppings", given[self.TOPPINGS["question"]], ""),
                          ("", "Bright and simple", "")])

    def test_declined(self):
        t = self.now - 90
        # with a note, from Talpy Den (the permission hook's No): the note is yours
        items = self.items(self.ask(t, self.QUESTION),
                           answered("q1", t + 5, "The user didn't answer and said: ask me after lunch", error=True,
                                    permissionDecision={"decision": "reject", "source": "hook"}))
        self.assertEqual((items[1]["asked"]["state"], items[1]["summary"]), ("declined", "Declined"))
        self.assertEqual((items[2]["text"], items[2]["answered"]), ("ask me after lunch", "question"))
        # without one (Esc in its dialog, Decline with no note): nothing of yours
        for result in (answered("q1", t + 5, STOPPED, error=True, toolUseResult="User rejected tool use"),
                       answered("q1", t + 5, "The user didn't answer.", error=True)):
            items = self.items(self.ask(t, self.QUESTION), result)
            self.assertEqual([i["kind"] for i in items], ["you", "tool"])
            self.assertEqual(items[1]["asked"]["state"], "declined")
        # "Chat about this": Claude Code's own text, not yours (what you write next is your prompt)
        items = self.items(self.ask(t, self.QUESTION),
                           answered("q1", t + 5, SAID_TO_CLAUDE + "The user wants to clarify these questions.\n    Questions asked:\n- …",
                                    error=True, permissionDecision=BY_YOU),
                           prompt("which shades of teal?", t + 9))
        self.assertEqual([i["kind"] for i in items], ["you", "tool", "you"])
        self.assertEqual((items[1]["asked"]["state"], items[1]["summary"], items[2]["text"]),
                         ("chat", "Chat about this", "which shades of teal?"))
        # failed (not answered at all): as any failed call
        items = self.items(self.ask(t, self.QUESTION), answered("q1", t + 5, "<tool_use_error>bad input</tool_use_error>", error=True))
        self.assertEqual((items[1]["asked"]["state"], items[1]["summary"], len(items)), ("failed", "bad input", 2))

    def test_plan(self):
        t = self.now - 90
        plan = "# Logo plan\n\n1. Sketch\n2. Colour"
        call = tool_use("p1", "ExitPlanMode", {"plan": plan, "planFilePath": "/tmp/plan.md"}, t, "m1")
        items = self.items(call, answered("p1", t + 5, "User has approved your plan.", toolUseResult={
            "plan": plan, "isAgent": False, "filePath": "/tmp/plan.md"}))
        self.assertEqual({k: items[1]["asked"][k] for k in ("plan", "title", "state")}, {"plan": plan, "title": "Logo plan", "state": "approved"})
        self.assertEqual((items[1]["summary"], items[2]["key"], items[2]["text"], items[2]["answered"]),
                         ("Approved", "p1/answer", "Approved the plan", "plan"))
        # rejected: Keep planning, and your note (in Claude's terminal, or from Talpy Den;
        # Claude Code's own note after it isn't yours)
        for text, decided in ((SAID_TO_CLAUDE + "use fewer colours\n\nNote: The user's next message may contain a correction.", BY_YOU),
                              ("The user wants to keep planning and said: use fewer colours", {"decision": "reject", "source": "hook"})):
            items = self.items(call, answered("p1", t + 5, text, error=True, permissionDecision=decided))
            self.assertEqual((items[1]["asked"]["state"], items[1]["summary"], items[2]["text"]),
                             ("keep", "Keep planning", "Keep planning\nuse fewer colours"))
        items = self.items(call, answered("p1", t + 5, STOPPED, error=True, toolUseResult="User rejected tool use"))
        self.assertEqual(items[2]["text"], "Keep planning")

    def test_deny_with_a_note(self):
        t = self.now - 90
        a = str(self.folder / "a.py")
        edit = tool_use("e1", "Edit", {"file_path": a, "old_string": "x = 1", "new_string": "x = 2"}, t, "m1")
        for text, decided in ((SAID_TO_CLAUDE + "keep x as it is", BY_YOU),
                              (REFUSED + "The user provided the following reason for the rejection:  keep x as it is", None),
                              ("The user denied this and said: keep x as it is", {"decision": "reject", "source": "hook"})):
            items = self.items(edit, answered("e1", t + 5, text, error=True,
                                              **({"permissionDecision": decided} if decided else {})))
            self.assertEqual((items[1]["asked"], items[1]["summary"]), ({"state": "denied"}, "Denied"))
            self.assertEqual({k: items[2][k] for k in ("kind", "key", "text", "answered")},
                             {"kind": "you", "key": "e1/answer", "text": "keep x as it is", "answered": "permission"})
        # a plain Deny, a refusal that isn't yours (a rule, auto mode, another's hook): the Steps tab only
        for result in (answered("e1", t + 5, STOPPED, error=True, toolUseResult="User rejected tool use"),
                       answered("e1", t + 5, SAID_TO_CLAUDE + "not you", error=True,
                                permissionDecision={"decision": "reject", "source": "config", "reasonType": "classifier"}),
                       answered("e1", t + 5, "PreToolUse:Edit hook error: blocked", error=True,
                                permissionDecision={"decision": "reject", "source": "hook"}),
                       answered("e1", t + 5, "The user said: something", error=False)):
            items = self.items(edit, result)
            self.assertEqual(len(items), 2)
            self.assertNotIn("asked", items[1])

    def test_split_answer(self):
        self.assertEqual(pane.split_answer('Basil, "Figs, dried", "say \\"hi\\"", Honey'), ["Basil", "Figs, dried", 'say "hi"', "Honey"])
        self.assertEqual(pane.split_answer('"unclosed, Basil'), ['"unclosed', "Basil"])
        self.assertEqual(pane.split_answer("one"), ["one"])
        # what the pane sends is read back as it was meant
        self.assertEqual(pane.split_answer(pane.answer_text(["Basil", "Figs, dried", 'a "b"'], True)), ["Basil", "Figs, dried", 'a "b"'])


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
        # The button says what it does where that changes the chat's mode: it read "Always allow", and
        # the chat was in accept edits mode after the click (its commands still asking)
        self.assertEqual(view["alwaysLabel"], "Allow all edits")
        rule = [{"type": "addRules", "rules": [{"toolName": "Bash", "ruleContent": "git push:*"}], "behavior": "allow",
                 "destination": "localSettings"}]
        view = cs.permission_view("Bash", {"command": "git push"}, str(self.folder), rule)
        self.assertEqual((view["always"], view["alwaysLabel"]),
                         ("Bash(git push:*) in this project (.claude/settings.local.json)", ""))   # (a rule: Always allow)
        # (answered with keys in its terminal, Claude's second choice: an edit's is "allow all edits during this session")
        self.assertEqual(cs.permission_view("Edit", {"file_path": str(self.folder / "a"), "old_string": "a", "new_string": "b"},
                                            str(self.folder))["alwaysLabel"], "Allow all edits")
        self.assertEqual(cs.permission_view("Bash", {"command": "ls"}, str(self.folder))["alwaysLabel"], "")

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
            # (as written, never markup: Plasma's button guesses rich text, an <img src=…> option was fetched)
            self.assertIn(f"label: ask.choices.length > {i} ? root.plainLabel(ask.choices[{i}].label)", block)
            self.assertIn(f"onActivated: ask.choose({i})", block)
        self.assertIn('placeholderText = i18n("Reply to %1…", root.plainLabel(session.name))', main)
        self.assertIn('return String(s).replace(/</g, "<\\u200b")', main)


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
        # (none of the modules: --keys needs none of them, and each is more to send and compile there)
        self.assertEqual(asked.call_args[1], {"name": "pane.py", "also": (), "timeout": 60})


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
        return dict(os.environ, HOME=str(self.home), XDG_CACHE_HOME=str(self.cache), XDG_STATE_HOME=str(self.cache / "state"),
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
        self.assertEqual(list(cs.requests_dir(self.cache / "talpy-den").iterdir()), [])

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
        with mock.patch.dict(os.environ, {"HOME": str(self.home), "XDG_CACHE_HOME": str(self.cache), "XDG_STATE_HOME": str(self.cache / "state")}), \
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
        with mock.patch.dict(os.environ, {"HOME": str(self.home), "XDG_CACHE_HOME": str(self.cache), "XDG_STATE_HOME": str(self.cache / "state")}), \
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


class SendFixture(PaneFixture):
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

    def hook(self):
        """The permission hook a chat Talpy Chat starts or wakes gets for itself (claude --settings)."""
        command = pane.hook_command(self.home / ".local/share/talpy-den/permission-hook.py")
        return json.dumps({"hooks": {"PermissionRequest": [{"matcher": "*", "hooks": [
            {"type": "command", "command": command, "timeout": pane.HOOK_TIMEOUT_S}]}]}}, separators=(",", ":"))



class SendTests(SendFixture):
    def test_a_finished_chat_goes_on_in_the_background(self):
        answer = self.send()
        self.assertTrue(answer["ok"], answer)
        self.assertEqual((answer["how"], answer["message"]),
                         ("background", "Sent: the chat goes on with it in the background (1a2b3c4d)"))
        # (with the permission hook for it alone: a background chat has no terminal to ask in)
        self.assertEqual(self.calls(), [["--bg", "--resume", SID, "--settings", self.hook(), "and the docs"]])

    def test_a_background_session_takes_it_in_where_it_is(self):
        # (through Claude's background service, as `claude agents` answers one: queued while it works,
        # never stopped, so a terminal attached to it stays on it)
        from test_tasks import FakeService
        self.live(kind="bg", status="busy", jobId="bgjob1")
        profile = next(p for p in cs.discover_profiles(self.home) if p.key == ".claude-work")
        service = FakeService(self, profile, lambda r: {"ok": True, "op": r["op"]})
        with mock.patch.object(cs, "stop_background") as stopped:
            answer = self.send()
        self.assertEqual(answer, {"ok": True, "how": "typed", "message": "Sent (typed into the background chat)"})
        self.assertEqual([(r["short"], r["text"]) for r in service.ops("reply")], [("bgjob1", "and the docs")])
        self.assertEqual((stopped.call_count, self.calls()), (0, []))
        # one that asks you something isn't stopped for it, nor typed into (it would land in its
        # question): it's answered first (the pane's reply answers it)
        self.live(kind="bg", status="waiting", waitingFor="permission prompt", jobId="bgjob1")
        with mock.patch.object(cs, "stop_background", return_value=(True, "Stopped")) as stopped, \
                mock.patch.object(cs, "continue_chat", return_value={"ok": True, "id": "1a2b3c4d"}) as went_on:
            self.assertEqual(self.send(), {"ok": False, "message": "It's asking you something: answer that first"})
        self.assertEqual((stopped.call_count, went_on.call_count, len(service.ops("reply"))), (0, 0, 1))

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
        self.assertEqual(self.calls(), [["--bg", "--resume", SID, "--settings", self.hook(), "and the docs"]])

    def test_enter_copies_here_for_a_hosts_terminal(self):
        asked = {"ok": True, "how": "ask", "message": "Its terminal takes no text from outside"}
        with mock.patch("remote.host_answer", return_value=asked) as host, \
                mock.patch.object(pane, "copy_to_clipboard", return_value=True) as copy:
            answer = self.cli("--send", SID, "--host", "lab", "--text", "and the docs", "--how", "enter")
        self.assertEqual(host.call_args[0][1][:6], ["--send", SID, "--text", "and the docs", "--how", "enter"])
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
        self.assertEqual(host.call_args[0][1][:6], ["--send", SID, "--text", "and the docs", "--how", "auto"])
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


class StopTests(SendFixture):
    """Talpy Chat's Stop (pane.py --interrupt): the session that has the chat
    open now, by its own id or the chat's; Esc into a background chat
    (talpy_den.interrupt_background), Ctrl+C in tmux."""

    def test_it_interrupts_the_session_that_has_the_chat_open(self):
        calls = []
        self.live(kind="bg", status="busy", jobId="5c1d7a6e", version="2.1.318")
        with mock.patch.object(cs, "interrupt_background", side_effect=lambda p, e: calls.append(("bg", p.label, e["jobId"])) or (True, "Stopped")), \
                mock.patch.object(cs, "interrupt_chat", side_effect=lambda e: calls.append(("tmux", e["sessionId"])) or (True, "Interrupted")):
            self.assertEqual(self.cli("--interrupt", SID, "--profile", ".claude-work"), {"ok": True, "message": "Stopped"})
            # (a chat resumed in another session: by that session's id)
            self.live(sessionId="ab12cd34-0000-4000-8000-000000000000", status="busy", tmux="main:@1.%4")
            self.assertEqual(self.cli("--interrupt", SID, "--session", "ab12cd34-0000-4000-8000-000000000000"),
                             {"ok": True, "message": "Interrupted"})
            (self.home / ".claude-work/sessions/30.json").unlink()
            self.assertEqual(self.cli("--interrupt", SID), {"ok": False, "message": "That chat isn't running any more"})
            self.assertFalse(self.cli("--interrupt", "--x")["ok"])
        self.assertEqual(calls, [("bg", "work", "5c1d7a6e"), ("tmux", "ab12cd34-0000-4000-8000-000000000000")])


class TalpyChatHookTests(SendFixture):
    """Chats Talpy Chat starts, or wakes in the background, get the permission
    hook for themselves (claude --settings), so what they ask is answered in
    Talpy Chat: a background chat has no terminal to ask in."""

    JOB = "1a2b3c4d"   # (what the fake claude prints)
    NEW = JOB + "-5e6f-4a7b-8c9d-0e1f2a3b4c5d"

    def start(self, folder=None, text="Fix the tests", **kw):
        write(self.home / f".claude-work/jobs/{self.JOB}/state.json", {"sessionId": self.NEW, "respawnFlags": []})
        return pane.start_chat(self.home, [], ".claude-work", str(folder or self.folder), text, claude=str(self.bin / "claude"),
                               **kw)

    def test_a_new_chat_starts_in_the_background_with_its_own_hook(self):
        answer = self.start(model="haiku", effort="low", mode="default")
        self.assertEqual(answer, {"ok": True, "how": "background", "id": self.JOB, "chat": self.NEW,
                                  "profileDir": ".claude-work", "message": "Started in the background on work",
                                  "hooked": True})
        self.assertEqual(self.calls(), [["--bg", "--settings", self.hook(), "--model", "haiku", "--effort", "low",
                                         "--permission-mode", "default", "Fix the tests"]])
        self.assertEqual(self.scopes, ["claude"])   # (in a systemd scope of its own)
        # the hook's copy is put in place for it (the setting for every chat is off: none was there)
        hook = self.home / ".local/share/talpy-den/permission-hook.py"
        self.assertEqual(hook.read_bytes(), (CODE / "permission_hook.py").read_bytes())
        # nothing of the account's settings changes
        self.assertFalse((self.home / ".claude-work/settings.json").exists())

    def test_claudes_predicted_reply_on_with_suggest_replies(self):
        # (Suggest replies on: the chats Talpy Chat starts or wakes predict your reply, Claude's grey
        # suggestion, written into their job's record; with the hook, or alone where the hook runs anyway)
        predict = '"env":{"CLAUDE_CODE_ENABLE_PROMPT_SUGGESTION":"true"}'
        self.start(predict=True)
        self.assertEqual(self.calls()[-1][:3], ["--bg", "--settings", self.hook()[:-1] + "," + predict + "}"])
        pane.relay(self.home, [], True)
        self.assertEqual(pane.send(self.home, [], ".claude-work", SID, "and the docs", None, "auto", str(self.bin / "claude"),
                                   predict=True)["how"], "background")
        self.assertEqual(self.calls()[-1], ["--bg", "--resume", SID, "--settings", "{" + predict + "}", "and the docs"])
        self.start()   # (off: none)
        self.assertEqual(self.calls()[-1], ["--bg", "Fix the tests"])

    def test_claudes_predicted_reply_is_in_the_conversation(self):
        state = self.home / f".claude-work/jobs/{SID[:8]}/state.json"
        write(state, {"sessionId": SID, "tempo": "blocked", "needs": "pick one", "respawnFlags": []})
        self.chat(prompt("tidy up", self.now - 9, cwd=str(self.folder)),
                  text_reply("Should I delete the old logs or keep them?", self.now - 8, "m1"))
        ask = lambda **kw: self.cli("--conversation", SID, "--profile", ".claude-work", "--suggest", *kw.get("more", []))
        first = ask()
        self.assertEqual((first["ended"], first["predicted"]), ("asked", None))
        # a few seconds later, Claude's guess: a change, though the transcript isn't
        write(state, {"sessionId": SID, "tempo": "blocked", "needs": "pick one", "respawnFlags": [],
                      "suggestedReply": "  delete   them "})
        again = ask(more=["--if-changed", first["stamp"]])
        self.assertEqual(again["predicted"], "delete them")
        self.assertTrue(ask(more=["--if-changed", again["stamp"]])["unchanged"])
        # not while it works again, nor for a permission prompt, nor with Suggest replies off
        write(state, {"sessionId": SID, "tempo": "active", "suggestedReply": "delete them"})
        self.assertIsNone(ask()["predicted"])
        write(state, {"sessionId": SID, "tempo": "blocked", "block": {"kind": "permission"}, "suggestedReply": "yes"})
        self.assertIsNone(ask()["predicted"])
        self.assertNotIn("predicted", self.cli("--conversation", SID, "--profile", ".claude-work"))

    def test_no_hook_of_its_own_where_the_hook_runs_anyway_or_cant(self):
        # the setting for every chat on: the account's settings have the hook (it would run twice)
        pane.relay(self.home, [], True)
        self.start()
        self.assertEqual(self.calls()[-1], ["--bg", "Fix the tests"])
        self.assertEqual(self.send()["how"], "background")
        self.assertEqual(self.calls()[-1], ["--bg", "--resume", SID, "and the docs"])
        # managed settings that let only their own hooks run (or none)
        pane.relay(self.home, [], False)
        with mock.patch.object(cs, "managed_hooks_only", return_value=True):
            self.start()
        self.assertEqual(self.calls()[-1], ["--bg", "Fix the tests"])

    def test_a_folder_claude_doesnt_trust_isnt_started(self):
        other = self.home / "elsewhere"
        other.mkdir()
        answer = self.start(other)
        self.assertFalse(answer["ok"])
        self.assertIn("Claude doesn't trust ~/elsewhere yet", answer["message"])
        self.assertEqual(self.calls(), [])

    def test_its_first_message_names_the_plan(self):
        write(self.home / ".claude-work/plans/calm-red-owl.md", "# Calm plan\n\n1. Do it\n")
        self.assertTrue(self.start(text="", plan="calm-red-owl")["ok"])
        self.assertEqual(self.calls()[-1][-1], "Implement this plan.\n\nThe plan (saved as ~/.claude-work/plans/"
                                               "calm-red-owl.md):\n\n# Calm plan\n\n1. Do it\n")
        self.assertEqual(self.start(text=" ")["message"], "Write your message first")

    def test_a_stopped_background_job_gets_it_in_its_saved_options(self):
        # (options given with --resume for a chat with a job record start a copy: they go into what
        # Claude wakes it with instead, while nothing holds it; the wake gives none)
        state = self.home / f".claude-work/jobs/{SID[:8]}/state.json"
        write(state, {"sessionId": SID, "respawnFlags": ["--model", "opus"]})
        self.assertEqual(self.send()["how"], "background")
        self.assertEqual(self.calls(), [["--bg", "--resume", SID, "and the docs"]])
        self.assertEqual(json.loads(state.read_text())["respawnFlags"], ["--model", "opus", "--settings", self.hook()])
        # once: settings it has are its own (the ones it got before, or yours)
        write(state, {"sessionId": SID, "respawnFlags": ["--settings", "{}", "--model", "opus"]})
        self.send()
        self.assertEqual(json.loads(state.read_text())["respawnFlags"], ["--settings", "{}", "--model", "opus"])

    def go_on(self, **kw):
        """Keep going's or a queued go-on's way (jump.py): no settings of its own given."""
        return cs.continue_chat(self.home, [], ".claude-work", SID, text="go on", claude=str(self.bin / "claude"),
                                force=True, **kw)

    def test_a_copy_of_a_hooked_chat_keeps_its_hook(self):
        # (R16: Keep going, a queued go-on, or a wake of a job still held after the wait give no settings
        # of their own; the copy Claude makes then is given the hook the chat's job saved, so its prompts
        # still reach Talpy Chat. A job that wakes has it in its saved options already)
        state = self.home / f".claude-work/jobs/{SID[:8]}/state.json"
        write(state, {"sessionId": SID, "respawnFlags": ["--model", "opus", "--settings", self.hook()]})
        with mock.patch.object(cs, "daemon_holds", return_value=True):   # (still held: Claude copies it)
            self.assertTrue(self.go_on(wait=0)["ok"])
            argv = self.calls()[-1]
            self.assertEqual(argv[:3], ["--bg", "--resume", SID])
            self.assertEqual(argv[argv.index("--settings") + 1], self.hook())
            self.assertEqual(argv.count("--settings"), 1)
            # the --settings=… spelling too
            write(state, {"sessionId": SID, "respawnFlags": ["--settings=" + self.hook()]})
            self.go_on(wait=0)
            argv = self.calls()[-1]
            self.assertEqual(argv[argv.index("--settings") + 1], self.hook())
            # settings of your own (not the hook) stay with the job: the copy isn't given them
            write(state, {"sessionId": SID, "respawnFlags": ["--settings", '{"env":{"X":"1"}}']})
            self.go_on(wait=0)
            self.assertNotIn("--settings", self.calls()[-1])
            # nor another chat's job under the same short id
            other = SID[:8] + "-0000-4000-8000-000000000000"
            write(state, {"sessionId": other, "respawnFlags": ["--settings", self.hook()]})
            self.go_on(wait=0)
            self.assertNotIn("--settings", self.calls()[-1])
        # settled, its job wakes with what it saved: given nothing (anything given would start a copy)
        write(state, {"sessionId": SID, "respawnFlags": ["--settings", self.hook()]})
        self.go_on(wait=0)
        self.assertEqual(self.calls()[-1], ["--bg", "--resume", SID, "go on"])

    def test_one_wake_of_a_chat_at_a_time(self):
        # (R17: the lock around a wake: none waited for, the same thread takes it again (send's
        # continue_chat), and another one waits till it's let go)
        import threading
        with cs.wake_lock(self.home, SID) as waited:
            self.assertFalse(waited)
            with cs.wake_lock(self.home, SID) as again:
                self.assertFalse(again)
            took = []
            other = threading.Thread(target=lambda: took.append(cs.wake_lock(self.home, SID).__enter__()))
            other.start()
            other.join(0.3)
            self.assertTrue(other.is_alive(), "it waits")
        other.join(5)
        self.assertEqual(took, [True])
        # another chat's isn't held up; nor is a chat id that isn't one (nothing is locked)
        with cs.wake_lock(self.home, "not-an-id") as waited:
            self.assertFalse(waited)

    def test_two_front_ends_waking_one_chat_make_no_copy(self):
        # R17: Talpy Chat's window in Plasma and its tab in VS Code send to one stopped chat within a
        # second: the first wakes it; the second waits for that, finds its session and replies to it,
        # rather than claude --bg --resume while the service holds it (which starts a copy)
        import threading
        from test_tasks import FakeService
        profile = next(p for p in cs.discover_profiles(self.home) if p.key == ".claude-work")
        service = FakeService(self, profile, lambda r: {"ok": True, "op": r["op"]})
        started = []

        def start_background(*args, **kw):
            time.sleep(0.4)   # (claude --bg answers once its job is written; its session shows a moment later)
            started.append(args[2])
            threading.Timer(0.3, lambda: self.live(kind="bg", status="busy", jobId="1a2b3c4d")).start()
            return True, "Started in the background on work (1a2b3c4d)", "1a2b3c4d"

        answers = []
        with mock.patch.object(cs, "start_background", side_effect=start_background):
            sends = [threading.Thread(target=lambda t=t: answers.append(self.send(text=t))) for t in ("from Plasma", "from VS Code")]
            for t in sends:
                t.start()
            for t in sends:
                t.join(30)
        self.assertEqual(len(started), 1, ("one wake", answers))
        replied = [r["text"] for r in service.ops("reply")]
        self.assertEqual(sorted(started + replied), ["from Plasma", "from VS Code"], answers)
        self.assertEqual(sorted(a["how"] for a in answers), ["background", "typed"])
        # a go-on that comes meanwhile (Keep going, a queued one) waits too, then leaves the chat at work alone
        with cs.wake_lock(self.home, SID):
            late = []
            go = threading.Thread(target=lambda: late.append(self.go_on()))
            go.start()
            go.join(0.3)
            self.assertTrue(go.is_alive(), "it waits for the wake")
        go.join(30)
        self.assertEqual((late[0]["ok"], late[0]["message"]), (False, "It's at work again, so it stays where it is"))
        self.assertEqual(len(self.calls()), 0, "no claude --bg of its own")

    def test_the_command_line(self):
        write(self.home / f".claude-work/jobs/{self.JOB}/state.json", {"sessionId": self.NEW})
        with mock.patch.object(cs, "find_claude", return_value=str(self.bin / "claude")):
            answer = self.cli("--start", ".claude-work", "--cwd", str(self.folder), "--text", "Fix the tests",
                              "--model", "sonnet", "--permission-mode", "acceptEdits")
        self.assertEqual((answer["ok"], answer["chat"]), (True, self.NEW))
        self.assertEqual(self.calls()[-1], ["--bg", "--settings", self.hook(), "--model", "sonnet",
                                            "--permission-mode", "acceptEdits", "Fix the tests"])
        # on an SSH host (or in a container): started there, with the hook's code for its copy there
        with mock.patch("remote.host_answer", return_value={"ok": True, "chat": self.NEW, "hooked": True}) as host:
            answer = self.cli("--start", ".claude-work", "--cwd", "~", "--text", "x", "--host", "lab")
        self.assertEqual(answer, {"ok": True, "chat": self.NEW, "hooked": True})
        args = host.call_args[0][1]
        self.assertEqual(args[:6], ["--start", ".claude-work", "--cwd", "~", "--text", "x"])
        self.assertEqual(base64.b64decode(args[args.index("--hook-source") + 1]), (CODE / "permission_hook.py").read_bytes())
        # (a start waits for claude's background service there: longer than other actions; none of the modules)
        self.assertEqual(host.call_args[1], {"name": "pane.py", "also": (), "timeout": pane.HOST_START_TIMEOUT})
        # it got there and took too long: it may have started, so it isn't sent again
        with mock.patch("remote.host_answer", return_value={"ok": False, "timedOut": True, "message": "lab didn't answer"}):
            answer = self.cli("--start", ".claude-work", "--cwd", "~", "--text", "x", "--host", "lab")
        self.assertEqual((answer["ok"], answer["maybe"]), (False, True))
        self.assertIn("the chat may have started there", answer["message"])

    def test_a_job_record_that_never_names_its_chat(self):
        with mock.patch.object(pane, "JOB_RECORD_WAIT_S", 0.2):
            (self.home / ".claude-work/jobs").mkdir(parents=True, exist_ok=True)
            answer = pane.start_chat(self.home, [], ".claude-work", str(self.folder), "x", claude=str(self.bin / "claude"))
        self.assertFalse(answer["ok"])
        self.assertIn("It started (1a2b3c4d)", answer["message"])


class HostHookTests(SendFixture):
    """Talpy Chat on an SSH host or in a container (pane.py there, its code
    on stdin with no file of its own): the hook's copy there comes from the
    code the computer that asks sends (--hook-source), only ever newer; the
    chats it starts or wakes there get it as here, with no systemd scope."""

    JOB, NEW, start = TalpyChatHookTests.JOB, TalpyChatHookTests.NEW, TalpyChatHookTests.start

    def source(self, revision):
        return (CODE / "permission_hook.py").read_text().replace("HOOK_REVISION = 3", f"HOOK_REVISION = {revision}")

    def copy(self):
        return self.home / ".local/share/talpy-den/permission-hook.py"

    def test_its_copy_comes_from_the_code_sent_and_only_ever_newer(self):
        with mock.patch.object(pane, "__file__", "-"):   # (on a host: no file next to it to copy)
            self.assertEqual(pane.place_hook(self.home), (None, "its code isn't here to copy"))
            path, why = pane.place_hook(self.home, source=self.source(3))
        self.assertEqual((path, why), (self.copy(), ""))
        self.assertEqual(self.copy().read_text(), self.source(3))
        self.assertEqual(oct(self.copy().stat().st_mode & 0o777), "0o600")
        self.assertEqual(oct(self.copy().parent.stat().st_mode & 0o777), "0o700")
        # a newer one replaces it; an older one (a front end of an older version) doesn't
        pane.place_hook(self.home, source=self.source(5))
        pane.place_hook(self.home, source=self.source(4))
        self.assertIn("HOOK_REVISION = 5", self.copy().read_text())
        # nor does turning the hook on for every chat from it
        pane.relay(self.home, [], True, source=self.source(4))
        self.assertIn("HOOK_REVISION = 5", self.copy().read_text())
        self.assertEqual(list(self.copy().parent.glob("*.tmp")) + list(self.copy().parent.glob(".*.tmp")), [])

    def test_a_folder_others_may_write_in(self):
        # (an XDG_DATA_HOME on shared space: whoever may write there could swap in a hook that allows anything.
        # One of yours made under a looser umask, 0775 (dictation makes it too): made 0700, and a copy in it
        # that someone else may have put or changed is written anew)
        self.copy().parent.mkdir(parents=True)
        os.chmod(self.copy().parent, 0o777)
        self.copy().write_text("HOOK_REVISION = 99\nimport os  # allows everything\n")
        os.chmod(self.copy(), 0o666)
        path, why = pane.place_hook(self.home, source=self.source(3))
        self.assertEqual((path, why), (self.copy(), ""))
        self.assertEqual(oct(self.copy().parent.stat().st_mode & 0o777), "0o700")
        self.assertEqual(self.copy().read_text(), self.source(3))
        self.assertEqual(oct(self.copy().stat().st_mode & 0o777), "0o600")
        # a link where its folder goes: not a folder of yours, no copy; the chat starts all the same, unhooked
        shutil.rmtree(self.copy().parent)
        elsewhere = self.home / "elsewhere-data"
        elsewhere.mkdir()
        self.copy().parent.symlink_to(elsewhere)
        path, why = pane.place_hook(self.home, source=self.source(3))
        self.assertIsNone(path)
        self.assertIn("isn't a folder of yours", why)
        answer = self.start()
        self.assertEqual((answer["ok"], answer["hooked"]), (True, False))
        self.assertIn("Talpy Den couldn't put its permission hook in place:", answer["hookWhy"])
        self.assertEqual(self.calls()[-1], ["--bg", "Fix the tests"])
        with self.assertRaises(ValueError):
            pane.install_hook(self.home, [], True, "relay")
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_hooked_says_whether_talpy_chat_answers_what_it_asks(self):
        profile = next(p for p in cs.discover_profiles(self.home) if p.key == ".claude-work")
        self.assertEqual(pane.chat_hook_of(self.home, profile)["hooked"], True)
        # the hook for every chat in its settings: none of its own, and hooked all the same
        pane.relay(self.home, [], True)
        self.assertEqual(pane.chat_hook_of(self.home, profile), {"settings": None, "hooked": True, "why": ""})
        self.assertEqual(self.start()["hooked"], True)
        with mock.patch.object(cs, "managed_hooks_only", return_value=True):
            self.assertEqual(pane.chat_hook_of(self.home, profile),
                             {"settings": None, "hooked": False, "why": "managed settings let only their own hooks run"})

    def test_started_there_with_no_scope(self):
        self.scopes.clear()
        answer = self.start(scoped=False, hook_source=self.source(3))
        self.assertEqual((answer["ok"], answer["hooked"], answer["chat"]), (True, True, self.NEW))
        self.assertEqual(self.calls()[-1][:3], ["--bg", "--settings", self.hook()])
        self.assertEqual(self.scopes, [])   # (no systemd scope there: jump.py and plasmashell aren't)
        self.assertEqual(self.copy().read_text(), self.source(3))

    def test_a_folder_claude_doesnt_trust_there(self):
        other = self.home / "elsewhere"
        other.mkdir()
        answer = self.start(other, scoped=False)
        self.assertEqual((answer["ok"], answer["untrusted"]), (False, True))
        self.assertNotIn("untrusted", pane.start_chat(self.home, [], ".claude-work", str(self.home / "gone"), "x",
                                                      claude=str(self.bin / "claude")))

    def test_a_stopped_job_there_wakes_with_it(self):
        state = self.home / f".claude-work/jobs/{SID[:8]}/state.json"
        write(state, {"sessionId": SID, "respawnFlags": ["--model", "opus"]})
        self.scopes.clear()
        answer = pane.send(self.home, [], ".claude-work", SID, "and the docs", None, "auto", str(self.bin / "claude"),
                           scoped=False, hook_source=self.source(3))
        self.assertEqual((answer["how"], answer["hooked"]), ("background", True))
        # (the full id, no flags: what it saved, with the hook, wakes it; no copy)
        self.assertEqual(self.calls(), [["--bg", "--resume", SID, "and the docs"]])
        self.assertEqual(json.loads(state.read_text())["respawnFlags"], ["--model", "opus", "--settings", self.hook()])
        self.assertEqual(self.scopes, [])

    def test_its_row_says_whether_its_prompts_are_answered_here(self):
        # (a background chat's prompts reach Talpy Chat through the hook: Talpy Chat's for it, in what
        # Claude wakes it with, or the one for every chat in its account's settings)
        state = self.home / f".claude-work/jobs/{SID[:8]}/state.json"
        write(state, {"sessionId": SID, "state": "working", "respawnFlags": ["--model", "opus"]})
        self.live(kind="bg", status="busy", jobId=SID[:8])
        self.assertFalse(self.rows()[SID]["hooked"])
        write(state, {"sessionId": SID, "state": "working", "respawnFlags": ["--settings", self.hook()]})
        self.assertTrue(self.rows()[SID]["hooked"])
        write(state, {"sessionId": SID, "state": "working", "respawnFlags": []})
        pane.relay(self.home, [], True)
        self.assertTrue(self.rows()[SID]["hooked"])
        # (one in a terminal asks in its own dialog there)
        self.live(kind="interactive", status="busy")
        self.assertFalse(self.rows()[SID]["hooked"])

    def test_a_host_taken_off_the_list_forgets_the_hook_unless_a_chat_still_uses_it(self):
        # (user, 2026-11-05: its copy and its requests folder go, if no chat Talpy Chat started there still runs)
        self.start()
        requests = cs.requests_dir(self.cache)
        write(requests / "1-0a1b2c3d.json", {"id": "1-0a1b2c3d"})
        state = self.home / f".claude-work/jobs/{SID[:8]}/state.json"
        write(state, {"sessionId": SID, "state": "working", "respawnFlags": ["--settings", self.hook()]})
        self.live(kind="bg", status="busy", jobId=SID[:8])
        answer = pane.forget_hook(self.home, [])
        self.assertEqual((answer["kept"], answer["message"]), (1, "1 chat Talpy Chat started there still runs: its permission hook stays there for them"))
        self.assertTrue(self.copy().is_file())
        # the one for every chat: it stays
        (self.home / ".claude-work/sessions/30.json").unlink()
        pane.relay(self.home, [], True)
        self.assertEqual(pane.forget_hook(self.home, [])["kept"], "every")
        pane.relay(self.home, [], False, keep_copy=True)
        # a request waiting there: a hook still waits (a chat that runs where this can't see it: a home shared
        # over the network), nothing goes
        self.assertEqual(pane.forget_hook(self.home, [])["kept"], "asking")
        self.assertTrue(self.copy().is_file())
        (requests / "1-0a1b2c3d.json").unlink()
        write(requests / "1-0a1b2c3d.answer.json", {"behavior": "allow"})   # (an answer nobody took)
        # none of them: gone, with its requests folder
        with mock.patch.object(cs, "find_claude", return_value=str(self.bin / "claude")):
            answer = self.cli("--relay", "forget")
        self.assertEqual(answer, {"ok": True, "message": "Talpy Den's permission hook and its requests are gone from there"})
        self.assertFalse(self.copy().exists())
        self.assertFalse(requests.exists())
        self.assertEqual(pane.forget_hook(self.home, [])["message"], "Nothing of Talpy Chat's there")

    def test_which_home_it_is(self):
        # (a container that shares your home answers the same: its chats, hook and requests are this computer's)
        here = cs.home_id(self.home)
        self.assertRegex(here, "^[0-9a-f]{12}$")
        self.assertEqual(cs.home_id(self.home), here)
        self.assertNotEqual(cs.home_id(self.folder), here)
        self.assertEqual(cs.home_id(self.home / "gone"), "")

    def test_two_windows_answering_one_prompt(self):
        # (Plasma's window and VS Code's tab a moment apart: only the first answer counts)
        cache = self.cache
        folder = cs.requests_dir(cache)
        folder.mkdir(parents=True)
        rid = "1700000000000-0a1b2c3d"
        write(folder / f"{rid}.json", {"id": rid, "at": int(time.time() * 1000), "hookPid": os.getpid(),
                                       "sessionId": SID, "tool": "Bash", "input": {"command": "make"}})
        write(folder / f"{rid}.answer.json", {"behavior": "allow"})   # (the other window's)
        self.assertEqual(pane.answer_request(cache, rid, "deny"), (False, pane.ANSWERED_ELSEWHERE))
        self.assertEqual(json.loads((folder / f"{rid}.answer.json").read_text()), {"behavior": "allow"})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            pane.main(["--answer", rid, "--decision", "deny"])
        self.assertEqual(json.loads(out.getvalue()), {"ok": False, "message": pane.ANSWERED_ELSEWHERE, "changed": True})
        # where the folder takes no hard links: written as before
        (folder / f"{rid}.answer.json").unlink()
        import errno
        taken = []

        def hook_takes_it(seconds):   # (as the hook does: it reads the answer, then removes the request and it)
            answer = folder / f"{rid}.answer.json"
            if answer.exists():
                taken.append(json.loads(answer.read_text()))
            for p in (folder / f"{rid}.json", answer):
                if p.exists():
                    p.unlink()
        with mock.patch.object(os, "link", side_effect=OSError(errno.EPERM, "no links")), \
                mock.patch.object(time, "sleep", side_effect=hook_takes_it):
            self.assertEqual(pane.answer_request(cache, rid, "deny"), (True, "Denied"))
        self.assertEqual(taken[0]["behavior"], "deny")
        # its hook gone before the answer came (another window's taken, or the chat answered): the answer
        # left there is taken back, and it says so (not "Allowed")
        write(folder / f"{rid}.json", {"id": rid, "at": int(time.time() * 1000), "hookPid": os.getpid(),
                                       "sessionId": SID, "tool": "Bash", "input": {"command": "make"}})
        with mock.patch.object(time, "sleep", side_effect=lambda s: (folder / f"{rid}.json").exists() and (folder / f"{rid}.json").unlink()):
            self.assertEqual(pane.answer_request(cache, rid, "allow"), (False, pane.NOT_ASKING))
        self.assertFalse((folder / f"{rid}.answer.json").exists())


class ChatPickTests(SendFixture):
    """A chat's own model and effort, picked in Talpy Chat (pane.py
    --set-options, chatpick.py): for that chat alone, never your settings
    (Claude's /model and /effort save them as your default for every new chat)."""

    def setUp(self):
        super().setUp()
        import chatpick
        self.pick = chatpick
        self.state = self.home / f".claude-work/jobs/{SID[:8]}/state.json"
        self.settings = self.home / ".claude-work/settings.json"
        write(self.settings, {"model": "opus"})
        # (never the real claude: one found by asking your shell would wake a real background chat)
        found = mock.patch.object(cs, "find_claude", return_value=str(self.bin / "claude"))
        found.start()
        self.addCleanup(found.stop)

    def set(self, **kw):
        kw.setdefault("claude", str(self.bin / "claude"))
        kw.setdefault("wait", 1)
        return self.pick.set_options(self.home, [], ".claude-work", SID, **kw)

    def flags(self):
        return json.loads(self.state.read_text())["respawnFlags"]

    def test_a_settled_background_job_wakes_with_them_next(self):
        write(self.state, {"sessionId": SID, "respawnFlags": ["--permission-mode", "auto", "--model", "haiku",
                                                              "--effort=low", "--settings", "{}"]})
        answer = self.set(model="Sonnet", effort="medium")
        self.assertEqual(answer, {"ok": True, "how": "next", "model": "sonnet", "effort": "medium",
                                  "message": "Sonnet · medium effort for this chat, from your next message"})
        self.assertEqual(self.flags(), ["--permission-mode", "auto", "--settings", "{}",
                                        "--model", "sonnet", "--effort", "medium"])
        # one alone; "default": Claude's own (none saved)
        self.assertTrue(self.set(effort="default")["ok"])
        self.assertEqual(self.flags(), ["--permission-mode", "auto", "--settings", "{}", "--model", "sonnet"])
        self.assertEqual(self.set(model="claude-opus-5-5")["message"], "Opus 5.5 for this chat, from your next message")
        self.assertEqual(self.flags()[-2:], ["--model", "claude-opus-5-5"])
        # nothing started, your settings untouched
        self.assertEqual(self.calls(), [])
        self.assertEqual(json.loads(self.settings.read_text()), {"model": "opus"})

    def test_an_idle_background_chat_is_woken_again_with_them_at_once(self):
        # (live-checked on 2.1.318: claude stop, its saved options changed, claude --bg --resume FULL-ID with no
        # message: the same job, idle, its next turn on the new model, no "Switch model?")
        self.live(kind="bg", status="idle", jobId=SID[:8])
        write(self.state, {"sessionId": SID, "respawnFlags": ["--model", "haiku", "--effort", "low"]})
        stopped = []
        def stop(profile, job_id, job=None, home=None, claude=None):
            stopped.append(job_id)
            (self.home / ".claude-work/sessions/30.json").unlink()   # (its process ends)
            return True, "stopped"
        with mock.patch.object(cs, "stop_background", side_effect=stop), \
                mock.patch.object(cs, "daemon_holds", return_value=False):
            answer = self.cli("--set-options", SID, "--profile", ".claude-work", "--model", "sonnet")
        self.assertEqual((answer["ok"], answer["how"], answer["model"]), (True, "now", "sonnet"), answer)
        self.assertEqual(stopped, [SID[:8]])
        self.assertEqual(self.flags(), ["--effort", "low", "--model", "sonnet"])
        self.assertEqual(self.calls(), [["--bg", "--resume", SID]])   # (woken with no message)
        self.assertEqual(self.scopes, ["claude"])   # (in a systemd scope of its own, as a wake from here)
        self.assertEqual(json.loads(self.settings.read_text()), {"model": "opus"})

    def test_the_answer_of_a_wake(self):
        self.live(kind="bg", status="idle", jobId=SID[:8])
        write(self.state, {"sessionId": SID, "respawnFlags": []})
        gone = lambda *a, **k: (self.home / ".claude-work/sessions/30.json").unlink() or (True, "stopped")
        with mock.patch.object(cs, "stop_background", side_effect=gone), \
                mock.patch.object(cs, "daemon_holds", return_value=False):
            answer = self.set(model="haiku")
        self.assertEqual(answer, {"ok": True, "how": "now", "model": "haiku", "effort": None,
                                  "message": "Haiku for this chat from now on"})

    def test_not_now_and_not_from_here(self):
        write(self.state, {"sessionId": SID, "respawnFlags": ["--model", "haiku"]})
        with mock.patch.object(cs, "stop_background") as stopped:
            self.live(kind="bg", status="busy", jobId=SID[:8])
            self.assertEqual(self.set(model="sonnet")["message"], "Claude is at work: pick it again once this turn ends")
            self.live(kind="bg", status="waiting", waitingFor="permission prompt", jobId=SID[:8])
            self.assertEqual(self.set(model="sonnet")["message"], "It's asking you something: answer that first")
            # its background commands would end with it
            self.live(kind="bg", status="idle", jobId=SID[:8])
            with mock.patch.object(cs, "background_commands", return_value=["npm run dev"]):
                said = self.set(model="sonnet")["message"]
            self.assertIn("It runs a command in the background (npm run dev)", said)
            # a terminal's: /model there
            self.live(kind="interactive", status="idle")
            answer = self.set(model="sonnet")
            self.assertEqual((answer["ok"], answer["how"]), (False, "terminal"))
        self.assertEqual(stopped.call_count, 0)
        self.assertEqual(self.flags(), ["--model", "haiku"])
        self.assertEqual(self.set(model="gpt 5")["message"], "Not a model: gpt 5")
        self.assertEqual(self.set(effort="huge")["message"], "Not an effort level: huge (one of low, medium, high, xhigh, max, ultracode)")
        self.assertEqual(self.set()["message"], "Pick a model or an effort level")

    def test_ultracode_on_and_off_for_this_chat(self):
        # (live-checked on 2.1.318: woken with --effort ultracode, its next message notes ultra_effort_enter;
        # woken with --effort xhigh after it, ultra_effort_exit)
        write(self.state, {"sessionId": SID, "respawnFlags": ["--model", "haiku", "--effort", "low"]})
        self.assertEqual(self.set(effort="Ultracode")["message"],
                         "ultracode, with xhigh effort for this chat, from your next message")
        self.assertEqual(self.flags(), ["--model", "haiku", "--effort", "ultracode"])
        self.assertEqual(self.pick.options_now(self.home, self.profile(), SID),
                         {"model": "haiku", "effort": "xhigh", "ultracode": True, "next": False})
        self.assertTrue(self.set(effort="xhigh")["ok"])   # (off: the effort it had with it)
        self.assertEqual(self.pick.options_now(self.home, self.profile(), SID, ultracode=True),
                         {"model": "haiku", "effort": "xhigh", "ultracode": False, "next": False})
        self.assertEqual(json.loads(self.settings.read_text()), {"model": "opus"})

    def profile(self):
        return next(p for p in cs.discover_profiles(self.home, []) if p.key == ".claude-work")

    def test_what_it_uses_now(self):
        # (what the lists mark: what Claude wakes it with, "" for Claude's default; else what you picked for its
        # next wake; else what it last ran on)
        write(self.state, {"sessionId": SID, "respawnFlags": ["--permission-mode", "auto"]})
        self.assertEqual(self.pick.options_now(self.home, self.profile(), SID),
                         {"model": "", "effort": "", "ultracode": False, "next": False})
        self.state.unlink()
        with mock.patch.object(cs, "chat_model", return_value=("claude-opus-5-5", "high")):
            self.assertEqual(self.pick.options_now(self.home, self.profile(), SID, ultracode=True),
                             {"model": "claude-opus-5-5", "effort": "high", "ultracode": True, "next": False})
            self.set(effort="medium")
            self.assertEqual(self.pick.options_now(self.home, self.profile(), SID, ultracode=True),
                             {"model": "claude-opus-5-5", "effort": "medium", "ultracode": False, "next": True})
        # in the conversation's answer
        self.chat(prompt("hello", self.now - 5, cwd=str(self.folder)))
        options = self.cli("--conversation", SID, "--profile", ".claude-work")["options"]
        self.assertEqual((options["effort"], options["next"]), ("medium", True))

    def test_a_chat_with_no_job_of_its_own_wakes_with_them_from_here(self):
        # (it last ran in a terminal, closed now: kept for its next wake from Talpy Chat or a go-on)
        answer = self.set(model="haiku", effort="max")
        self.assertEqual((answer["ok"], answer["how"]), (True, "next"))
        self.assertEqual(cs.picked_options(self.home, SID), {"model": "haiku", "effort": "max"})
        self.assertEqual(self.send()["how"], "background")
        argv = self.calls()[-1]
        self.assertEqual(argv[argv.index("--model") + 1:argv.index("--model") + 4], ["haiku", "--effort", "max"])
        self.assertEqual(cs.picked_options(self.home, SID), {})   # (its job has them now)
        self.assertEqual(json.loads(self.settings.read_text()), {"model": "opus"})


class ManagedHooksTests(unittest.TestCase):
    def test_managed_settings_that_allow_only_their_own_hooks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertFalse(cs.managed_hooks_only([str(root / "none")]))
            write(root / "managed-settings.json", {"permissions": {}})
            self.assertFalse(cs.managed_hooks_only([str(root)]))
            write(root / "managed-settings.d/10-hooks.json", {"allowManagedHooksOnly": True})
            self.assertTrue(cs.managed_hooks_only([str(root)]))
            write(root / "managed-settings.d/10-hooks.json", {"allowManagedHooksOnly": False})
            write(root / "managed-settings.json", {"disableAllHooks": True})
            self.assertTrue(cs.managed_hooks_only([str(root)]))


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

    def test_a_long_file_is_compared_only_where_it_changed_and_a_big_one_not_read(self):
        # (difflib over all of a long file took minutes; a file of GBs was read whole)
        rows = lambda sign: "".join(f"row {i} = {i if i % 2 else sign * i}\n" for i in range(3000))
        write(self.home / f".claude-work/file-history/{SID}/aa11@v1", rows(1))
        write(self.folder / "a.py", rows(-1))
        review = lambda: next(f for f in pane.chat_review(self.home, [], SID)["files"] if f["label"] == "a.py")
        f = review()
        self.assertEqual(f["diff"][:2], ["@@ -1,3000 +1,3000 @@", "Too long to compare here: 3000 new lines in place of 3000"])
        self.assertEqual((f["added"], f["removed"]), (3000, 3000))
        write(self.folder / "a.py", "x" * (cs.DIFF_FILE_MAX + 1))
        f = review()
        self.assertEqual((f["diff"], f["deleted"], f["binary"]), (["Not compared here: a file of 2 MB"], False, False))

    def test_undo_never_writes_through_a_link_put_beside_the_file(self):
        # (a repo could ship a.py.talpy-den-undo -> ~/.bashrc: Undo's new file had that name)
        victim = self.home / ".bashrc"
        write(victim, "alias ll='ls -l'\n")
        a = self.folder / "a.py"
        os.symlink(str(victim), str(a) + ".talpy-den-undo")
        self.assertEqual(pane.undo(self.home, [], SID, None, {str(a)}), (True, "Put back 1 file as before the chat"))
        self.assertEqual((victim.read_text(), a.is_symlink(), a.read_text()), ("alias ll='ls -l'\n", False, "x = 1\ny = 2\n"))

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
                "npm run check && npm test", "gjs -m gnome/tests/test_logic.js", "python3 tests/test_week.py",
                "./run-tests.sh", "uv run pytest -x"]
        others = ['git commit -m "fix pytest run"', "python3 - <<'EOF'\nimport unittest\nEOF", "ls tests/",
                  "cargo build", 'echo "a \\" pytest"', "pip install pytest", "npm install -D vitest", "which pytest",
                  "pytest --version", "grep -rn jest src", "test -f x"]
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
        a, b, c = self.cache / "images/a.png", self.folder / "b.jpg", self.cache / "images/c.png"
        for f in (a, b, c):
            write(f, "-a picture-")
        # (only a regular file: a pty or a pipe never answers, and plasmashell's pictures waited on it for good)
        pipe = self.folder / "pipe.png"
        os.mkfifo(pipe)
        self.chat(prompt(f"look: [Image: {a}] and [Image: {b}] [Image: /dev/ptmx] [Image: {pipe}] [Image: /nowhere.png]", t,
                         cwd=str(self.folder)),
                  pasted,
                  {"type": "queue-operation", "operation": "enqueue", "timestamp": iso(t + 2),
                   "content": f"and [Image: {c}]"})
        folder = self.cache / "images"
        items = pane.conversation(self.transcript, 120, folder)[0]
        self.assertEqual([i.get("pictures") for i in items], [
            [str(a), str(b)], [str(folder / "chat-u-1-1.png")], [str(c)]])
        # an SSH host's: its paths there, shown from this computer only when one is a regular file here too
        self.assertEqual(pane.pictures_here([{"pictures": [str(a), "/dev/ptmx", str(pipe), "/on/lab.png"]}, {"text": "hi"}]),
                         [{"pictures": [str(a), "/dev/ptmx", str(pipe), "/on/lab.png"], "here": [str(a)]}, {"text": "hi"}])
        with mock.patch("remote.host_answer", return_value={"ok": True, "items": [{"kind": "you", "pictures": ["/dev/ptmx"]}]}):
            self.assertEqual(self.cli("--conversation", SID, "--host", "lab")["items"][0]["here"], [])
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


def limit_hit(ts):
    return {"type": "assistant", "timestamp": iso(ts), "isApiErrorMessage": True,
            "message": {"id": "e%d" % ts, "model": "<synthetic>", "role": "assistant",
                        "content": [{"type": "text", "text": "You've hit your session limit · resets 7pm"}]}}


def stand_in(ts):
    """Claude Code's reply when a chat it stopped is resumed."""
    return {"type": "assistant", "timestamp": iso(ts),
            "message": {"id": "s%d" % ts, "model": "<synthetic>", "role": "assistant", "stop_reason": "stop_sequence",
                        "content": [{"type": "text", "text": "No response requested."}]}}


def chips(asks):
    return None if asks is None else (asks["kind"], [(c["label"], c["send"], c["recommended"]) for c in asks["choices"]])


class AsksTests(unittest.TestCase):
    """B2: the question Claude ends its reply with, as chips, by its shape (made-up replies)."""

    def test_yes_no(self):
        self.assertEqual(chips(replies.asks_of("I fixed the parser.\n\nShould I commit it?")),
                         ("yesno", [("Yes", "Yes", False), ("No", "No", False)]))
        self.assertEqual(chips(replies.asks_of("Done.\n\nMerge to main and install?")),   # (a few words, no question word)
                         ("yesno", [("Yes", "Yes", False), ("No", "No", False)]))
        # in the question's language
        self.assertEqual(chips(replies.asks_of("Der Test läuft jetzt durch.\n\nSoll ich das mergen?"))[1][0][0], "Ja")
        self.assertEqual(chips(replies.asks_of("C'est corrigé.\n\nVeux-tu que je le pousse ?"))[1][:1], [("Oui", "Oui", False)])
        self.assertEqual(chips(replies.asks_of("Listo.\n\n¿Quieres que lo suba ahora?"))[1][0][0], "Sí")

    def test_no_chips(self):
        for reply in ("All tests pass.",                                       # (no question)
                      "Two things:\n\nShould I merge it? And should I tag it too?",   # (several: one click can't answer)
                      "What should the new command be called?",                # (an open question)
                      # (a long either/or)
                      "Should I rewrite the whole parser from scratch with the new grammar and its tests, or keep patching the old one?",
                      "", "   "):
            self.assertIsNone(replies.asks_of(reply), reply)

    def test_options(self):
        reply = ("Two ways to go:\n\n1. Run the screening first\n2. Start the rename on a branch (Recommended)\n"
                 "3. Leave it as it is\n\nWhich one?")
        self.assertEqual(chips(replies.asks_of(reply)), ("options", [
            ("1 · Run the screening first", "1. Run the screening first", False),
            ("2 · Start the rename on a branch", "2. Start the rename on a branch", True),
            ("3 · Leave it as it is", "3. Leave it as it is", False)]))
        # the one Claude names, a letter list, bold numbers, an option's details after a dash
        said = "a) **Keep** — the old name stays\nb) **Rename** — everywhere\n\nI'd go with option b. Which do you prefer?"
        self.assertEqual(chips(replies.asks_of(said)), ("options", [("a · Keep", "a. Keep", False), ("b · Rename", "b. Rename", True)]))
        bold = "**1.** Squash them\n**2.** Keep each commit\n\nWhich way?"
        self.assertEqual([c[1] for c in chips(replies.asks_of(bold))[1]], ["1. Squash them", "2. Keep each commit"])
        # bullets: the words alone
        self.assertEqual([c[:2] for c in chips(replies.asks_of("- Opus\n- Sonnet\n\nWhich model?"))[1]],
                         [("Opus", "Opus"), ("Sonnet", "Sonnet")])
        # another language's list
        self.assertEqual(chips(replies.asks_of("1. Zuerst testen\n2. Gleich mergen\n\nWelche Variante?"))[0], "options")

    def test_a_list_of_finished_work_isnt_options(self):
        done = ("I changed three things:\n\n"
                "1. The parser now reads every kind of header that the old files had, including the ones that start with tabs or spaces\n"
                "2. The writer keeps the order of the keys exactly as they were in the file it read, so the diffs stay small and easy to read\n"
                "3. The tests cover both of them, with files made up for each case that used to fail before this change went in\n\n")
        self.assertEqual(chips(replies.asks_of(done + "Should I merge it?"))[0], "yesno")
        self.assertIsNone(replies.asks_of(done + "Which one should go in first?"))   # (long items: not options)
        # a yes/no question wins over a short list before it too; seven items aren't options
        self.assertEqual(chips(replies.asks_of("1. Lint\n2. Tests\n\nShould I run both?"))[0], "yesno")
        seven = "\n".join("%d. Step %d" % (i, i) for i in range(1, 8)) + "\n\nWhich one first?"
        self.assertIsNone(replies.asks_of(seven))

    def test_either_or(self):
        self.assertEqual(chips(replies.asks_of("The tests are slow.\n\nShould I run the screening first, or start the rename on a branch?")),
                         ("either", [("Run the screening first", "Run the screening first", False),
                                     ("Start the rename on a branch", "Start the rename on a branch", False)]))
        self.assertEqual(chips(replies.asks_of("Soll ich zuerst testen oder gleich mergen?"))[1][1][0], "Gleich mergen")
        # the question's start that no either/or start takes isn't part of the first half (seen live, 2.1.322)
        self.assertEqual(chips(replies.asks_of("Should the next file be named alpha.txt or beta.txt?")),
                         ("either", [("Alpha.txt", "Alpha.txt", False), ("Beta.txt", "Beta.txt", False)]))
        self.assertEqual([c[0] for c in chips(replies.asks_of("Do the tests pass or fail?"))[1]], ["Pass", "Fail"])
        self.assertEqual([c[0] for c in chips(replies.asks_of("Should we keep the old parser or rewrite it?"))[1]],
                         ["Keep the old parser", "Rewrite it"])   # (taken by its either/or start: as it was)
        # "or not" isn't a choice
        self.assertEqual(chips(replies.asks_of("Should I keep it or not?"))[0], "yesno")


class SuggestedRepliesTests(PaneFixture):
    """The turn's end (--conversation --suggest: ended, asks) and your usual replies (--replies, B3)."""

    def answer(self, *entries):
        self.chat(*entries)
        got = self.cli("--conversation", SID, "--suggest")
        return got.get("ended"), got.get("over"), chips(got.get("asks"))

    def test_how_the_turn_ended(self):
        t, cwd = self.now - 100, str(self.folder)
        start = prompt("fix it", t, cwd=cwd)
        self.assertEqual(self.answer(start, text_reply("Fixed.\n\nShould I commit it?", t + 1, "m1", "end_turn")),
                         ("asked", True, ("yesno", [("Yes", "Yes", False), ("No", "No", False)])))
        self.assertEqual(self.answer(start, text_reply("Fixed.", t + 1, "m1", "end_turn")), ("finished", True, None))
        self.assertEqual(self.answer(start, limit_hit(t + 1)), ("limit", True, None))
        self.assertEqual(self.answer(start, text_reply("Looking.", t + 1, "m1", "tool_use"), prompt("[Request interrupted by user]", t + 2)),
                         ("interrupted", True, None))
        self.assertEqual(self.answer(start, stand_in(t + 1)), ("stopped", True, None))
        failed = dict(limit_hit(t + 1), message={"id": "x", "role": "assistant", "model": "<synthetic>",
                                                  "content": [{"type": "text", "text": "API Error: 500 Internal server error"}]})
        self.assertEqual(self.answer(start, failed), ("failed", True, None))
        # (your prompt with no reply: stopped before Claude's first words, or it's thinking: the chat's state tells)
        self.assertEqual(self.answer(start), ("stopped", False, None))
        # mid-turn: a tool call, its result, or a message waiting in Claude's queue: nothing yet
        self.assertEqual(self.answer(start, text_reply("Running them?", t + 1, "m1", "tool_use"),
                                     tool_use("t1", "Bash", {"command": "ls"}, t + 2, "m1")), (None, False, None))
        self.assertEqual(self.answer(start, tool_use("t1", "Bash", {"command": "ls"}, t + 1, "m1"), tool_result("t1", t + 2)),
                         (None, False, None))
        self.assertEqual(self.answer(start, text_reply("Fixed?", t + 1, "m1", "end_turn"),
                                     {"type": "queue-operation", "operation": "enqueue", "timestamp": iso(t + 2), "content": "and the docs"}),
                         (None, False, None))
        # (only when asked: without --suggest none of it)
        got = self.cli("--conversation", SID)
        self.assertFalse({"ended", "over", "asks"} & set(got))

    def turns(self, profile, sid, cwd, *steps, ago=0.0):
        """A transcript of made-up turns: steps are ("you", text), ("reply", text), ("ask", text),
        ("limit",), ("stopped",), ("interrupted",); ago: days back."""
        t = self.now - ago * 86400 - 1000
        entries = [prompt("start", t, cwd=cwd, sessionId=sid, uuid="%s-0" % sid)]
        for i, step in enumerate(steps, 1):
            ts = t + i
            if step[0] == "you":
                entries.append(prompt(step[1], ts, cwd=cwd, sessionId=sid, uuid="%s-%d" % (sid, i)))
            elif step[0] in ("reply", "ask"):
                entries.append(text_reply(step[1], ts, "%s-m%d" % (sid, i), "end_turn"))
            elif step[0] == "limit":
                entries.append(limit_hit(ts))
            elif step[0] == "stopped":
                entries.append(stand_in(ts))
            elif step[0] == "interrupted":
                entries.append(prompt("[Request interrupted by user]", ts))
        path = self.home / profile / "projects" / cwd.replace("/", "-") / ("%s.jsonl" % sid)
        write(path, lines(*entries))
        return path

    def replies(self, *args):
        got = self.cli("--replies", SID, *args)
        self.assertTrue(got["ok"], got)
        return got

    def test_your_usual_replies(self):
        app, other = str(self.folder), str(self.home / "repos/other")
        self.chat(prompt("start", self.now - 50, cwd=app, sessionId=SID))
        # after a usage limit you go on with the same word, in three chats (one misspelled: merged, shown as usual)
        self.turns(".claude-work", "c1", app, ("reply", "Half done."), ("limit",), ("you", "continue"),
                   ("ask", "Done.\n\nShould I commit it?"), ("you", "yes"), ("reply", "Committed."), ("you", "push"))
        self.turns(".claude-work", "c2", app, ("limit",), ("you", "continue"), ("stopped",), ("you", "go on"))
        self.turns(".claude-work", "c3", other, ("limit",), ("you", "Contniue"), ("stopped",), ("you", "go on"),
                   ("reply", "Pushed."), ("you", "push"))
        # what isn't a usual reply: long, several lines, a command, a path, a picture, Keep going's own words
        self.turns(".claude-work", "c4", app, ("limit",), ("you", "please also rewrite the parser while you're at it"),
                   ("reply", "x"), ("you", "one\ntwo"), ("reply", "x"), ("you", "/compact"), ("reply", "x"), ("you", "look at src/app.py"),
                   ("reply", "x"), ("you", "[Image #1] this"), ("limit",), ("you", cs.CONTINUE_PROMPT))
        # another account's: not in this one's
        self.turns(".claude-personal", "p1", app, ("limit",), ("you", "weiter"))
        self.turns(".claude-personal", "p2", app, ("limit",), ("you", "weiter"))
        got = self.replies("--profile", ".claude-work")
        self.assertEqual(got["chips"].get("limit"), ["continue"])
        self.assertEqual(got["chips"].get("stopped"), ["go on"])   # (two chats)
        self.assertNotIn("asked", got["chips"])                     # (yes: one chat only)
        self.assertEqual(got["chips"].get("finished"), ["push"])
        self.assertEqual(got["ranked"][0], "continue")
        self.assertEqual(set(got["ranked"]), {"continue", "go on", "push", "yes"})   # (a chat's first prompt answers no turn)
        personal = self.cli("--replies", "p1", "--profile", ".claude-personal")
        self.assertEqual(personal["chips"], {"limit": ["weiter"]})

    def test_recent_and_this_projects_first(self):
        app, other = str(self.folder), str(self.home / "repos/other")
        self.chat(prompt("start", self.now - 50, cwd=app, sessionId=SID))
        for n in range(2):   # (a month ago, in two chats: it weighs a fifth of today's)
            self.turns(".claude-work", "old%d" % n, app, ("reply", "Done."), ("you", "ship it"), ago=30)
            self.turns(".claude-work", "new%d" % n, app, ("reply", "Done."), ("you", "push"))
        got = self.replies("--profile", ".claude-work")
        self.assertEqual(got["chips"]["finished"], ["push"])          # ("ship it": under the share it needs)
        self.assertEqual(got["ranked"][:2], ["push", "ship it"])
        # long ago (over two months): not counted at all
        self.turns(".claude-work", "older", app, ("reply", "Done."), ("you", "deploy"), ago=90)
        self.assertNotIn("deploy", self.replies("--profile", ".claude-work")["ranked"])
        # this project's first: the same use elsewhere counts half
        for n in range(2):
            self.turns(".claude-work", "o%d" % n, other, ("ask", "Ok?"), ("you", "fine"))
        self.turns(".claude-work", "h0", app, ("ask", "Ok?"), ("you", "sure"))
        self.turns(".claude-work", "h1", app, ("ask", "Ok?"), ("you", "sure"))
        got = self.replies("--profile", ".claude-work")
        self.assertEqual(got["chips"]["asked"], ["sure", "fine"])

    def test_dont_suggest_this(self):
        app = str(self.folder)
        self.chat(prompt("start", self.now - 50, cwd=app, sessionId=SID))
        for n in range(2):
            self.turns(".claude-work", "c%d" % n, app, ("limit",), ("you", "continue"))
        self.assertEqual(self.replies("--profile", ".claude-work")["chips"], {"limit": ["continue"]})
        self.assertTrue(self.cli("--hide-reply", "Continue.")["ok"])   # (as you'd type it: one reply)
        got = self.replies("--profile", ".claude-work")
        self.assertEqual((got["chips"], got["ranked"]), ({}, []))
        hidden = cs.state_dir(self.cache) / "replies-hidden.json"
        self.assertEqual(hidden.stat().st_mode & 0o777, 0o600)
        self.assertTrue(self.cli("--hide-reply", "-", "--off")["ok"])   # (all of them again)
        self.assertEqual(self.replies("--profile", ".claude-work")["chips"], {"limit": ["continue"]})

    def test_a_transcript_is_read_once(self):
        # what was read is kept by the transcript's size and time; one that grew is read from where it was left
        app = str(self.folder)
        self.chat(prompt("start", self.now - 50, cwd=app, sessionId=SID))
        c1 = self.turns(".claude-work", "c1", app, ("limit",), ("you", "continue"))
        self.turns(".claude-work", "c2", app, ("limit",), ("you", "continue"))
        self.assertEqual(self.replies("--profile", ".claude-work")["chips"], {"limit": ["continue"]})
        kept = list((self.cache / "replies").glob("*.json"))
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].stat().st_mode & 0o777, 0o600)
        # (what was read stays as it was read: the same bytes changed now aren't read again)
        data = c1.read_text().replace('"continue"', '"cxntinue"')
        write(c1, data + lines(text_reply("More.", self.now - 10, "c1-mz", "end_turn"),
                               prompt("ok", self.now - 9, cwd=app, sessionId="c1", uuid="c1-z")))
        got = self.replies("--profile", ".claude-work")
        self.assertEqual(got["chips"]["limit"], ["continue"])
        self.assertIn("ok", got["ranked"])
        # (one that's shorter now was written again: read whole)
        write(c1, data)
        self.assertNotIn("ok", self.replies("--profile", ".claude-work")["ranked"])
        with mock.patch.object(replies, "reply_records", side_effect=AssertionError("read again")):
            self.replies("--profile", ".claude-work")   # (nothing changed: nothing read)


# Commands as Claude Code writes them (made-up words): a command's own entry, as a user
# entry or a system local_command one, and what it printed in the next one
def ran(name, args, ts, system=False, message=None, **kw):
    text = (f"<command-name>/{name}</command-name>\n            <command-message>{message or name}</command-message>\n"
            f"            <command-args>{args}</command-args>")
    if system:
        return {"type": "system", "subtype": "local_command", "level": "info", "timestamp": iso(ts), "content": text,
                "isMeta": False, **kw}
    return {"type": "user", "timestamp": iso(ts), "message": {"role": "user", "content": text}, **kw}


def printed(text, ts, system=False, tag="stdout"):
    body = f"<local-command-{tag}>{text}</local-command-{tag}>"
    if system:
        return {"type": "system", "subtype": "local_command", "level": "info", "timestamp": iso(ts), "content": body}
    return {"type": "user", "timestamp": iso(ts), "message": {"role": "user", "content": body}}


def caveat(ts):
    return {"type": "user", "timestamp": iso(ts), "isMeta": True, "message": {"role": "user", "content":
            "<local-command-caveat>The command below was run directly.</local-command-caveat>"}}


def queued(op, text, ts):
    return {"type": "queue-operation", "operation": op, "timestamp": iso(ts), **({"content": text} if text else {})}


class CommandsInChatTests(PaneFixture):
    """A command you ran shows in the chat (commands.Commands), wherever you
    ran it: as yours, in the code font, with what it printed under it."""

    def items(self, *entries, ends=None):
        self.chat(*entries)
        return pane.conversation(self.transcript, ends=ends)[0]

    def test_a_command_with_and_without_arguments_and_what_it_printed(self):
        t = self.now - 100
        panel = "\x1b[1mFill level\x1b[22m\n\x1b[38;5;244m■ ■ □\x1b[39m  12k of 200k"
        items = self.items(prompt("hello", t, cwd=str(self.folder)), text_reply("Hi.", t + 1, "m1", "end_turn"),
                           ran("context", "", t + 2, system=True), printed(panel, t + 2, system=True),
                           {"type": "user", "timestamp": iso(t + 2), "isMeta": True,
                            "message": {"role": "user", "content": "## Fill level\n| a | b |"}},
                           caveat(t + 3), ran("model", "fable", t + 3), printed("Set model to Fable", t + 3),
                           caveat(t + 4), ran("exit", "", t + 4), printed("(no content)", t + 4),
                           ran("clear", "", t + 5), printed("", t + 5, system=True))
        self.assertEqual([(i["kind"], i["text"], i.get("command")) for i in items], [
            ("you", "hello", None), ("claude", "Hi.", None),
            ("you", "/context", {"output": panel}),     # (its colours kept: the chat draws them)
            ("you", "/model fable", {"output": "Set model to Fable"}),
            ("you", "/exit", {}), ("you", "/clear", {})])
        self.assertEqual(len({i["key"] for i in items}), len(items))
        # (what it printed on its own, with no command before it, isn't shown)
        self.assertEqual(self.items(printed("stray", t)), [])

    def test_compact_keeps_its_note(self):
        t = self.now - 100
        summary = {"type": "user", "timestamp": iso(t + 2), "isCompactSummary": True,
                   "message": {"role": "user", "content": "A summary of it all."}}
        boundary = {"type": "system", "subtype": "compact_boundary", "timestamp": iso(t + 2), "content": "Conversation compacted"}
        items = self.items(prompt("/compact", t + 1, cwd=str(self.folder)), boundary, summary, caveat(t + 3),
                           ran("compact", "", t + 3), printed("\x1b[2mCompacted (ctrl+o to see more)\x1b[22m", t + 4))
        self.assertEqual([(i["kind"], i["text"], i.get("command")) for i in items],
                         [("you", "/compact", {}), ("note", "The conversation was compacted", None)])
        # (its prompt and its command entry are one: the prompt's key)
        self.assertEqual(items[0]["key"], self.items(prompt("/compact", t + 1, cwd=str(self.folder)))[0]["key"])
        # failed: why, as what it printed
        items = self.items(prompt("/compact", t + 1), caveat(t + 2), ran("compact", "", t + 2),
                           printed("Error during compaction: out of usage", t + 3, system=True, tag="stderr"))
        self.assertEqual(items[0]["command"], {"output": "Error during compaction: out of usage", "error": True})

    def test_a_shell_command(self):
        t = self.now - 100

        def shell(text, ts):
            return {"type": "user", "timestamp": iso(ts), "message": {"role": "user", "content": text}}
        items = self.items(shell("<bash-input>ls docs</bash-input>", t), shell("<bash-stdout>a.md\nb.md</bash-stdout><bash-stderr></bash-stderr>", t + 1),
                           text_reply("Two files.", t + 2, "m1", "end_turn"),
                           shell("<bash-input>cat nope</bash-input>", t + 3), shell("<bash-stdout></bash-stdout><bash-stderr>cat: nope: No such file</bash-stderr>", t + 4))
        self.assertEqual([(i["kind"], i["text"], i.get("command")) for i in items], [
            ("you", "!ls docs", {"shell": True, "output": "a.md\nb.md"}), ("claude", "Two files.", None),
            ("you", "!cat nope", {"shell": True, "output": "cat: nope: No such file", "error": True})])
        # sent through Claude's queue (a background chat's reply), it's queued without its !: one item, its key kept
        items = self.items(queued("enqueue", "ls docs", t), queued("dequeue", None, t + 1),
                           shell("<bash-input>ls docs</bash-input>", t + 1), shell("<bash-stdout>a.md</bash-stdout><bash-stderr></bash-stderr>", t + 2))
        waiting = self.items(queued("enqueue", "ls docs", t))   # (while it waits in the queue: as it was queued)
        self.assertEqual([(i["text"], i.get("queued")) for i in waiting], [("ls docs", True)])
        self.assertEqual([(i["key"], i["text"], i["command"]) for i in items],
                         [(waiting[0]["key"], "!ls docs", {"shell": True, "output": "a.md"})])
        # a chat woken with it on claude's command line: Claude reads it as a message (not a command)
        self.assertEqual([(i["text"], i.get("command")) for i in self.items(prompt("!ls docs", t))], [("!ls docs", None)])

    def test_a_command_through_claudes_queue_keeps_its_key(self):
        t = self.now - 100
        items = self.items(prompt("hello", t - 5, cwd=str(self.folder)), text_reply("Hi.", t - 4, "m1", "end_turn"),
                           queued("enqueue", "/recap", t), queued("dequeue", None, t + 1),
                           ran("recap", "", t + 2), printed("Said hello, nothing else yet.", t + 2, system=True))
        self.assertEqual([(i["key"], i["text"], i.get("command")) for i in items[2:]],
                         [(self.items(queued("enqueue", "/recap", t))[0]["key"], "/recap", {"output": "Said hello, nothing else yet."})])

    def test_prompt_commands_skills_and_claudes_own(self):
        t = self.now - 100
        skill = {"type": "user", "timestamp": iso(t), "message": {"role": "user", "content":
                 "<command-message>ship</command-message>\n<command-name>/ship</command-name>\n<command-args>v2</command-args>"}}
        expanded = {"type": "user", "timestamp": iso(t), "isMeta": True, "message": {"role": "user", "content": "Ship it: v2"}}
        loaded = {"type": "user", "timestamp": iso(t + 1), "isMeta": True, "message": {"role": "user", "content":
                  "<command-message>notes</command-message>\n<command-name>notes</command-name>"}}
        ends = {}
        items = self.items(skill, expanded, loaded, text_reply("Shipped.", t + 2, "m1", "end_turn"),
                           caveat(t + 3), ran("rate-limit-options", "", t + 3), printed("It goes on at 2pm. Press esc.", t + 3), ends=ends)
        # (yours: the skill you ran; not Claude's own: a skill it loaded, a limit's options)
        self.assertEqual([(i["kind"], i["text"], i.get("command")) for i in items],
                         [("you", "/ship v2", {}), ("claude", "Shipped.", None)])
        self.assertEqual(ends["ended"], "finished")
        # (a prompt command starts Claude's turn: no reply to it yet)
        self.items(skill, ends=ends)
        self.assertEqual((ends["ended"], ends["over"]), ("stopped", False))

    def test_a_command_claude_doesnt_know(self):
        t = self.now - 100
        unknown = {"type": "system", "subtype": "informational", "timestamp": iso(t + 1),
                   "content": "Unknown command: /skil. Did you mean /skills?"}
        items = self.items(queued("enqueue", "/skil all", t), queued("dequeue", None, t + 1), unknown)
        self.assertEqual([(i["key"], i["text"], i["command"]) for i in items], [
            (self.items(queued("enqueue", "/skil all", t))[0]["key"], "/skil all",
             {"output": "Unknown command: /skil. Did you mean /skills?", "error": True})])
        self.assertEqual([i["text"] for i in self.items(unknown)], ["/skil"])
        self.assertEqual(self.items({**unknown, "content": "Something else"}), [])

    def test_long_output_is_cut(self):
        t = self.now - 100
        long = "\n".join(f"\x1b[32mline {n}\x1b[39m" for n in range(200))
        items = self.items(ran("context", "", t, system=True), printed(long, t, system=True))
        out = items[0]["command"]["output"]
        self.assertEqual(len(out.split("\n")), commands_py.OUTPUT_LINES + 1)
        self.assertTrue(out.endswith("\x1b[0m\n…"))
        # (an escape cut at the end isn't left half there)
        self.assertEqual(commands_py.clip_output("x" * (commands_py.OUTPUT_CHARS - 2) + "\x1b[38;5;2m" + "y" * 50),
                         "x" * (commands_py.OUTPUT_CHARS - 2) + "\x1b[0m\n…")

    def test_no_command_no_module(self):
        # (commands.py is read only for a chat that has a command in it)
        t = self.now - 100
        with mock.patch.object(pane, "commands_of", side_effect=AssertionError("read")):
            self.assertEqual(len(self.items(prompt("hello", t), text_reply("Hi.", t + 1, "m1", "end_turn"))), 2)


class CommandKindsTests(unittest.TestCase):
    """Claude's commands in the / list (Claude Code 2.1.318), each with how
    Talpy Chat runs it: here, a page of Talpy Den's, or in its terminal."""

    def test_each_builtin_commands_kind(self):
        offers = {c["name"]: c for c in commands_py.builtin_offers()}
        self.assertEqual(len(offers), len(commands_py.BUILTIN_COMMANDS))
        for c in offers.values():
            self.assertIn(c["run"], ("here", "page", "picker", "terminal"), c)
            # (each one that opens there says why; the picker's too, for a chat in a terminal)
            self.assertEqual(bool(c.get("why")), c["run"] in ("terminal", "picker"), c)
        here = {"/compact", "/context", "/recap", "/rename", "/plan", "/fork", "/subtask", "/init", "/insights",
                "/code-review", "/security-review", "/simplify", "/debug", "/doctor"}
        self.assertEqual({n for n, c in offers.items() if c["run"] == "here"}, here)
        self.assertEqual({n for n, c in offers.items() if c["run"] == "page"}, {"/permissions"})
        # (with an argument: /export FILE writes it, /goal COND sets it; without, Claude asks or shows a box)
        self.assertEqual({n: c["runArgs"] for n, c in offers.items() if "runArgs" in c}, {"/export": "here", "/goal": "here"})
        # /model and /effort save your default for every new chat: never sent from here, with or without a
        # name; Talpy Chat's own list sets them for the chat alone (chatpick.py), a terminal's opens them there
        for name in ("/model", "/effort"):
            self.assertEqual((offers[name]["run"], offers[name].get("runArgs")), ("picker", None))
            self.assertIn("as your default", offers[name]["why"])
        # (gone in 2.1.318: no longer offered)
        self.assertFalse({"/pr-comments", "/todos", "/cost", "/review", "/agents"} & set(offers))

    def test_typed_names_not_listed(self):
        typed = commands_py.typed_kinds()
        self.assertEqual(typed["review"], {"run": "here", "of": "/code-review"})
        self.assertEqual(typed["allowed-tools"], {"run": "page", "of": "/permissions"})
        self.assertEqual(typed["theme"]["run"], "terminal")
        listed = {c["name"][1:] for c in commands_py.builtin_offers()}
        self.assertFalse(listed & set(typed))


class TypeInTests(SendFixture):
    """A command that needs Claude's own panel (pane.py --type-in): typed
    into its tmux pane, not sent; in its Claude Code panel's input; else on
    the clipboard. The front end opens its terminal then."""

    def test_tmux_types_it_without_enter(self):
        self.live(tmux="main:1.%3")
        # (tmux itself needn't be installed here)
        with mock.patch.object(pane, "tmux_base", return_value=(["tmux"], "%3")), \
                mock.patch.object(pane, "tmux_run", return_value=(True, "")) as tmux:
            answer = self.cli("--type-in", SID, "--text", "/config ", "--profile", ".claude-work")
        self.assertEqual(answer, {"ok": True, "how": "typed", "message": "It's typed into its terminal: press Enter there"})
        self.assertEqual([c[0][1][0] for c in tmux.call_args_list], ["load-buffer", "paste-buffer"])   # (no Enter)
        self.assertEqual(tmux.call_args_list[0][0][2], b"/config")
        # one that asks something: not typed into its question
        self.live(tmux="main:1.%3", status="waiting")
        with mock.patch.object(pane, "tmux_run") as tmux, mock.patch.object(pane, "copy_to_clipboard", return_value=True):
            answer = self.cli("--type-in", SID, "--text", "/config")
        self.assertEqual((answer["how"], answer["message"], tmux.call_count),
                         ("copy", "It's in the clipboard. It's asking you something: answer that first, then paste it there", 0))

    def test_vscode_and_the_clipboard(self):
        self.live(entrypoint="claude-vscode")
        answer = self.cli("--type-in", SID, "--text", "/model fable")
        self.assertEqual(answer["how"], "vscode")
        self.assertTrue(answer["link"].endswith("&prompt=%252Fmodel+fable"), answer)
        # a background chat, one in a terminal, one that isn't running: the clipboard
        (self.home / ".claude-work/sessions/30.json").unlink()
        with mock.patch.object(pane, "copy_to_clipboard", return_value=True) as copied:
            self.assertEqual(self.cli("--type-in", SID, "--text", "/btw why?"),
                             {"ok": True, "how": "copy", "copied": True, "text": "", "message": "It's in the clipboard. Paste it into its terminal"})
        copied.assert_called_once_with("/btw why?")
        # on an SSH host: the text back, for this computer's clipboard
        with mock.patch.object(pane, "copy_to_clipboard") as copied:
            self.assertEqual(self.cli("--type-in", SID, "--text", "/btw why?", "--remote"),
                             {"ok": True, "how": "copy", "copied": False, "text": "/btw why?", "message": "Paste it into its terminal"})
        self.assertEqual(copied.call_count, 0)
        with mock.patch.object(pane, "copy_to_clipboard") as copied:   # (VS Code: its own clipboard)
            self.assertEqual(self.cli("--type-in", SID, "--text", "/btw why?", "--no-copy")["text"], "/btw why?")
        self.assertEqual(copied.call_count, 0)
        self.assertFalse(self.cli("--type-in", SID, "--text", " ")["ok"])
        self.assertFalse(self.cli("--type-in", "--x", "--text", "/x")["ok"])
        # (never sent: nothing ran)
        self.assertEqual(self.calls(), [])


def using(ts, msg, model, read, written=0, cached=0, stop="end_turn", **kw):
    """Claude's reply with its token counts (what it read: new, written to the cache, read from it)."""
    return {"type": "assistant", "timestamp": iso(ts), **kw,
            "message": {"id": msg, "role": "assistant", "model": model, "content": [{"type": "text", "text": "Done."}],
                        "stop_reason": stop, "usage": {"input_tokens": read, "cache_creation_input_tokens": written,
                                                       "cache_read_input_tokens": cached, "output_tokens": 700}}}


def steps(n, ts, start=0, msg="s"):
    """n tool calls of Claude's, each with its result, a second apart from ts."""
    out = []
    for i in range(start, start + n):
        out += [tool_use(f"t{i}", "Bash", {"command": f"step {i} " + "x" * 200}, ts + i - start, f"{msg}{i}"),
                tool_result(f"t{i}", ts + i - start, text="y" * 300)]
    return out


class WholeReplyTests(PaneFixture):
    """Copy (a message's, or Ctrl+Shift+C) copies all of it: a reply longer than
    Talpy Chat keeps (pane.TEXT_CHARS, shown cut with "…") is read whole from
    the transcript on the click (pane.py --reply-text, replies.whole_text)."""

    def test_a_long_reply_whole_as_the_conversation_joins_it(self):
        t = self.now - 100
        part = "Lorem ipsum dolor sit amet, consectetur adipiscing elit.\n" * 300   # (made-up, ~17 000 characters)
        first = dict(text_reply(part, t + 1, "m1"), uuid="a-1")
        second = dict(text_reply("Second half:\n" + part, t + 2, "m1", stop="end_turn"), uuid="a-2")
        # (a subagent's entry with the same id isn't the chat's; thinking kept to itself isn't shown)
        side = dict(text_reply("from a subagent", t + 2, "m1"), uuid="a-3", isSidechain=True)
        hidden = {"type": "assistant", "timestamp": iso(t + 2), "uuid": "a-4",
                  "message": {"id": "m1", "role": "assistant", "content": [{"type": "thinking", "thinking": "private"}]}}
        self.chat(dict(prompt("Write it all out", t, cwd=str(self.folder)), uuid="u-1"), first, side, hidden, second)
        item = [i for i in self.cli("--conversation", SID)["items"] if i["kind"] == "claude"][0]
        self.assertTrue(item["text"].endswith("\n…") and len(item["text"]) <= pane.TEXT_CHARS + 2)
        whole = self.cli("--reply-text", SID, "--key", item["key"])
        self.assertEqual(whole, {"ok": True, "text": part.strip() + "\n\nSecond half:\n" + part.strip()})
        self.assertTrue(whole["text"].startswith(item["text"][:-2]))
        # (by its entry's uuid too: a reply with no message id)
        self.assertEqual(self.cli("--reply-text", SID, "--key", "a-1", "--profile", ".claude-work")["text"], part.strip())

    def test_yours_and_thinking_shown_as_updates(self):
        t = self.now - 100
        long = "Here is the log:\n" + "line of a made-up log\n" * 1200
        updates = {"type": "assistant", "timestamp": iso(t + 1), "uuid": "a-9", "thinkingDisplay": "updates",
                   "message": {"id": "m9", "role": "assistant", "content": [{"type": "thinking", "thinking": "Looking at it."},
                                                                              {"type": "text", "text": "Found it."}]}}
        self.chat(dict(prompt(long, t, cwd=str(self.folder)), uuid="u-9"), updates)
        self.assertEqual(self.cli("--reply-text", SID, "--key", "u-9")["text"], long.strip())
        self.assertEqual(self.cli("--reply-text", SID, "--key", "m9")["text"], "Found it.")
        self.assertEqual(self.cli("--reply-text", SID, "--key", "m9/thinking")["text"], "Looking at it.")

    def test_none_with_that_key(self):
        self.chat(dict(prompt("hello", self.now - 5, cwd=str(self.folder)), uuid="u-1"))
        self.assertEqual(self.cli("--reply-text", SID, "--key", "m-gone"),
                         {"ok": False, "message": "That message isn't in the chat any more"})
        self.assertFalse(self.cli("--reply-text", "not-a-chat!", "--key", "u-1")["ok"])
        self.assertFalse(self.cli("--reply-text", SID)["ok"])   # (no key)


class BookmarkTests(PaneFixture):
    """Talpy Chat's bookmarks (pane.py --bookmark): kept on this computer, an
    SSH host's chat's too (never sent there), and carried in --conversation's
    answers once the chat has had one."""

    def mark(self, key, *more):
        return self.cli("--bookmark", SID, "--key", key, *more)

    def keys(self, answer):
        return [m["key"] for m in answer["bookmarks"]]

    def test_it_answers_the_whole_list_and_its_v(self):
        got = self.mark("m1", "--kind", "claude", "--at", "2000", "--text", "Done:  the tests\npass.")
        self.assertEqual((got["ok"], got["message"], len(got["bookmarks"])), (True, "", 1), got)
        self.assertEqual({k: got["bookmarks"][0][k] for k in ("key", "kind", "at", "text")},
                         {"key": "m1", "kind": "claude", "at": 2000, "text": "Done: the tests pass."})
        first = got["bookmarksV"]
        self.assertGreater(first, 0)
        got = self.mark("u1", "--kind", "you", "--at", "1000", "--text", "run the tests")
        self.assertEqual(self.keys(got), ["u1", "m1"])   # (in the chat's order)
        self.assertGreater(got["bookmarksV"], first)
        self.assertEqual((got["bookmarks"], got["bookmarksV"]), tuple(cs.load_bookmarks(self.cache, SID)))
        self.assertEqual(oct(os.stat(self.cache / "bookmarks" / f"{SID}.json").st_mode & 0o777), "0o600")
        # removed; again, and adding one it has: done, nothing written
        got = self.mark("m1", "--off")
        self.assertEqual((got["ok"], self.keys(got)), (True, ["u1"]))
        again = self.mark("m1", "--off")
        self.assertEqual((again["ok"], again["bookmarks"], again["bookmarksV"]), (True, got["bookmarks"], got["bookmarksV"]))
        self.assertEqual(self.mark("u1", "--kind", "you", "--at", "1000")["bookmarksV"], got["bookmarksV"])
        # refused: a message on its way, no key, a key that is a flag, a kind other than yours or Claude's, not a chat
        for refused in (self.mark("pending-3", "--kind", "you"), self.cli("--bookmark", SID, "--kind", "you"),
                        self.mark("-x", "--kind", "you"), self.mark("t1", "--kind", "tool")):
            self.assertEqual((refused["ok"], refused["message"], self.keys(refused)), (False, "Which message?", ["u1"]))
        self.assertEqual(self.cli("--bookmark", "../x", "--key", "m1", "--kind", "claude"),
                         {"ok": False, "message": "Not a chat: ../x", "bookmarks": [], "bookmarksV": 0})
        self.assertFalse((self.cache / "bookmarks" / "x.json").exists())

    def test_a_hosts_is_kept_here_and_never_sent_there(self):
        with mock.patch("remote.host_answer", side_effect=AssertionError("forwarded")) as asked, \
                mock.patch.object(pane, "forward", side_effect=AssertionError("forwarded")) as forwarded:
            got = self.cli("--bookmark", SID, "--key", "m1", "--kind", "claude", "--at", "5", "--text", "hi", "--host", "gpu")
            off = self.cli("--bookmark", SID, "--key", "m2", "--off", "--host", "gpu")
        self.assertEqual((got["ok"], self.keys(got), off["ok"], self.keys(off)), (True, ["m1"], True, ["m1"]), got)
        asked.assert_not_called()
        forwarded.assert_not_called()
        root = self.cache / "bookmarks"
        self.assertEqual(os.listdir(root), ["host-" + cs.short_id("gpu")])
        self.assertEqual(cs.load_bookmarks(self.cache, SID, "gpu")[0], got["bookmarks"])
        self.assertEqual(cs.load_bookmarks(self.cache, SID), ([], 0))   # (not this computer's chat of that id)

    def test_the_conversation_carries_them_once_there_are_some(self):
        t = self.now - 100
        self.chat(dict(prompt("run the tests", t, cwd=str(self.folder)), uuid="u1"),
                  text_reply("They pass.", t + 1, "m1", "end_turn"))
        first = self.cli("--conversation", SID)
        self.assertTrue(first["ok"], first)
        self.assertNotIn("bookmarks", first)   # (none yet: no file, nothing said)
        self.assertNotIn("bookmarksV", first)
        marked = self.mark("m1", "--kind", "claude", "--at", str(first["items"][1]["at"]), "--text", "They pass.")
        got = self.cli("--conversation", SID)
        self.assertEqual((got["bookmarks"], got["bookmarksV"]), (marked["bookmarks"], marked["bookmarksV"]))
        # an unchanged answer is only that (the list comes with the next changed one)
        self.assertEqual(self.cli("--conversation", SID, "--if-changed", got["stamp"]), {"ok": True, "unchanged": True})
        # the last one removed: an empty list, its v still growing (so it wins over the list before)
        gone = self.mark("m1", "--off")
        got = self.cli("--conversation", SID)
        self.assertEqual((got["bookmarks"], got["bookmarksV"]), ([], gone["bookmarksV"]))
        self.assertGreater(gone["bookmarksV"], marked["bookmarksV"])
        # on an SSH host (--remote): none of the host's own (they're kept on the computer that asks)
        self.mark("u1", "--kind", "you", "--at", "1")
        self.assertNotIn("bookmarks", self.cli("--conversation", SID, "--remote"))

    def test_a_hosts_conversation_gets_this_computers_list(self):
        self.cli("--bookmark", SID, "--key", "m1", "--kind", "claude", "--at", "5", "--text", "hi", "--host", "gpu")
        self.mark("u9", "--kind", "you", "--at", "1")   # (this computer's chat of that id: not the host's)
        there = {"ok": True, "items": [], "stamp": "1:2/120", "more": False}
        with mock.patch("remote.host_answer", side_effect=lambda *a, **kw: dict(there)) as asked:
            got = self.cli("--conversation", SID, "--host", "gpu", "--reach", "m1")
            other = self.cli("--conversation", SID, "--host", "box")
        self.assertEqual([m["key"] for m in got["bookmarks"]], ["m1"])
        self.assertEqual(got["bookmarksV"], cs.load_bookmarks(self.cache, SID, "gpu")[1])
        self.assertNotIn("bookmarks", other)
        # (--reach goes with the rest: the host reads that far back)
        self.assertEqual(asked.call_args_list[0][0], ("gpu", ["--conversation", SID, "--reach", "m1"]))
        with mock.patch("remote.host_answer", return_value={"ok": True, "unchanged": True}):
            self.assertEqual(self.cli("--conversation", SID, "--host", "gpu", "--if-changed", "1:2/120"),
                             {"ok": True, "unchanged": True})
        with mock.patch("remote.host_answer", return_value={"ok": False, "message": "Couldn't reach gpu"}):
            self.assertNotIn("bookmarks", self.cli("--conversation", SID, "--host", "gpu"))

    def test_the_usage_says_so(self):
        self.assertIn("--bookmark CHAT --key KEY [--off] [--kind you|claude] [--at MS] [--text TEXT] [--host HOST]", pane.__doc__)
        self.assertIn("[--suggest] [--reach KEY]", pane.__doc__)


class ReachTests(PaneFixture):
    """A bookmark further back than what's shown (pane.py --conversation
    --reach KEY): the answer shows it, its limit grown as Show earlier grows
    it, or says it's too far back ("far") or not in the chat any more ("gone")."""

    def prompts(self, n, start=0):
        t = self.now - 10000
        return [dict(prompt(f"prompt {k}", t + k), uuid=f"u{k}") for k in range(start, start + n)]

    def reach(self, key, *more):
        return self.cli("--conversation", SID, "--reach", key, *more)

    def test_the_limit_grows_as_show_earlier_grows_it(self):
        self.assertEqual([pane.reach_limit(120, 303), pane.reach_limit(40, 10), pane.reach_limit(960, 1000),
                          pane.reach_limit(1920, 1999), pane.reach_limit(2000, 2000)], [480, 120, 1920, 2000, 2000])

    def test_a_key_300_items_back(self):
        self.chat(*self.prompts(600))
        # (not in the first read, which has more than the limit's items: further back, as Show earlier)
        with mock.patch.object(pane, "PANE_TAIL_BYTES", 20000):
            got = self.reach("u300")
        self.assertEqual((got["limit"], got["reach"], got["reached"], len(got["items"]), got["more"]),
                         (480, "u300", "here", 480, True))
        self.assertTrue(got["stamp"].endswith("/480"))
        keys = [i["key"] for i in got["items"]]
        self.assertGreaterEqual(keys.index("u300"), pane.REACH_ABOVE)
        self.assertEqual(keys[-1], "u599")
        # (the next look, at that limit, is the same answer)
        self.assertEqual(self.cli("--conversation", SID, "--limit", "480", "--if-changed", got["stamp"]),
                         {"ok": True, "unchanged": True})

    def test_a_key_already_loaded_keeps_the_limit(self):
        self.chat(*self.prompts(600))
        got = self.reach("u590")
        self.assertEqual((got["limit"], got["reached"], len(got["items"])), (120, "here", 120))
        self.assertTrue(got["stamp"].endswith("/120"))
        self.assertEqual(self.reach("u400", "--limit", "240")["limit"], 240)
        plain = self.cli("--conversation", SID)
        self.assertFalse({"limit", "reach", "reached"} & set(plain))   # (only with --reach)

    def test_more_than_pane_items_max_back_is_far(self):
        self.chat(*self.prompts(2100))
        far = self.reach("u50")
        self.assertEqual((far["reached"], far["limit"], len(far["items"])), ("far", 120, 120))
        self.assertTrue(far["stamp"].endswith("/120"))
        edge = self.reach("u103")   # (2000 with the three above it: the most Talpy Chat shows)
        self.assertEqual((edge["reached"], edge["limit"], edge["items"][pane.REACH_ABOVE]["key"]), ("here", 2000, "u103"))

    def test_a_key_not_in_the_chat_is_gone(self):
        self.chat(*self.prompts(600))
        got = self.reach("m-gone")
        self.assertEqual((got["reached"], got["limit"], len(got["items"])), ("gone", 120, 120))
        # (not found in all it may read of a huge one: further back than that)
        with mock.patch.object(pane, "PANE_TAIL_BYTES", 1000), mock.patch.object(pane, "PANE_TAIL_MAX", 4000):
            self.assertEqual(self.reach("m-gone")["reached"], "far")

    def test_a_queued_prompt_is_found_once_the_read_grows(self):
        # (sent while Claude worked: keyed queued-<ms> while its enqueue line
        # is read, else by the line Claude took it in with)
        t = self.now - 20000
        self.chat(dict(prompt("go", t, cwd=str(self.folder)), uuid="u-go"),
                  tool_use("t1", "Bash", {"command": "sleep 60"}, t + 1, "m1"),
                  {"type": "queue-operation", "operation": "enqueue", "timestamp": iso(t + 2), "content": "also this"},
                  tool_result("t1", t + 9),
                  {"type": "queue-operation", "operation": "remove", "timestamp": iso(t + 9), "content": "also this",
                   "commandUuid": "c1"},
                  {"type": "attachment", "uuid": "a-1", "timestamp": iso(t + 9), "attachment": {
                      "type": "queued_command", "prompt": "also this", "source_uuid": "c1", "commandMode": "prompt",
                      "origin": {"kind": "human"}}},
                  *self.prompts(300))
        key = next(i["key"] for i in pane.conversation(self.transcript, limit=400)[0] if i.get("text") == "also this")
        self.assertTrue(key.startswith("queued-"), key)
        with mock.patch.object(pane, "PANE_TAIL_BYTES", 15000):   # (more than the limit's items, the enqueue line not in it)
            self.assertNotIn(key, [i["key"] for i in self.cli("--conversation", SID)["items"]])
            got = self.reach(key)
        self.assertEqual((got["reached"], got["limit"]), ("here", 480))
        self.assertIn(key, [i["key"] for i in got["items"]])

    def test_if_changed_isnt_looked_at(self):
        self.chat(*self.prompts(600))
        first = self.cli("--conversation", SID)
        got = self.cli("--conversation", SID, "--if-changed", first["stamp"], "--reach", "u300")
        self.assertEqual((got["ok"], got.get("unchanged"), got["reached"], got["limit"]), (True, None, "here", 480))


class AwayTests(PaneFixture):
    """Since you last looked (A9): a Talpy Chat window that shows a chat says
    so (--seen: when, kept here, a host's chat's too), and one that shows it
    again asks what it did since (--away: its steps, the files it changed,
    its newest test run, what it waits for), or since your last message."""

    def work(self, t, tests_ok=True):
        """A prompt of yours at t, then Claude's work: two edits (one refused), a file written, a test run and a reply."""
        cwd = str(self.folder)
        return [dict(prompt("fix the parser", t, cwd=cwd), uuid="u1"),
                tool_use("t1", "Edit", {"file_path": cwd + "/src/parse.py", "old_string": "a", "new_string": "b"}, t + 10, "m1"),
                dict(tool_result("t1", t + 11), cwd=cwd),
                tool_use("t2", "Edit", {"file_path": cwd + "/src/lex.py", "old_string": "a", "new_string": "b"}, t + 20, "m2"),
                dict(tool_result("t2", t + 21, error=True, text="String not found"), cwd=cwd),
                tool_use("t3", "Write", {"file_path": "/etc/elsewhere.conf", "content": "x"}, t + 30, "m3"),
                dict(tool_result("t3", t + 31), cwd=cwd),
                tool_use("t4", "Bash", {"command": "python3 -m pytest tests | tail -3\necho done"}, t + 40, "m4"),
                dict(tool_result("t4", t + 41, error=not tests_ok, text="3 passed" if tests_ok else "1 failed"), cwd=cwd),
                text_reply("Fixed: the parser reads nested lists now.", t + 50, "m5", "end_turn")]

    def away(self, *more):
        return self.cli("--conversation", SID, "--away", *more)["away"]

    def test_since_your_last_message(self):
        t = self.now - 600
        self.chat(*self.work(t))
        got = self.away()
        self.assertEqual(got, {"from": "you", "since": int(t * 1000), "key": "m5", "stepKey": "t1", "steps": 4,
                               "replies": 1, "files": ["src/parse.py", "/etc/elsewhere.conf"], "fileCount": 2,
                               "test": {"command": "python3 -m pytest tests | tail -3", "ok": True}, "asks": "",
                               "partial": False})
        self.chat(*self.work(t, tests_ok=False))
        self.assertEqual(self.away()["test"], {"command": "python3 -m pytest tests | tail -3", "ok": False})
        # without --away: nothing of it is worked out
        self.assertNotIn("away", self.cli("--conversation", SID))

    def test_claudes_own_recap_comes_with_it(self):
        # (Claude Code writes one when you come back to its terminal: an away_summary system entry; a prompt
        # or a reply after it makes it old, as the rows' Recap line)
        t = self.now - 600
        recap = {"type": "system", "subtype": "away_summary", "timestamp": iso(t + 60),
                 "content": "You asked to fix the parser; it's fixed and tested. (disable recaps in /config)"}
        self.chat(*self.work(t), recap)
        got = self.cli("--conversation", SID)["recap"]
        self.assertEqual(got, {"text": "You asked to fix the parser; it's fixed and tested.", "at": int((t + 60) * 1000)})
        self.chat(*self.work(t), recap, dict(prompt("thanks", t + 70, cwd=str(self.folder)), uuid="u9"))
        self.assertIsNone(self.cli("--conversation", SID)["recap"])

    def test_nothing_to_tell(self):
        t = self.now - 600
        # since your last message, Claude's reply alone (or a step or two): that's what the chat shows
        self.chat(dict(prompt("what is a monad?", t, cwd=str(self.folder)), uuid="u1"),
                  tool_use("t1", "Read", {"file_path": "/x"}, t + 1, "m1"), tool_result("t1", t + 2),
                  text_reply("A monoid in the category of endofunctors.", t + 5, "m2", "end_turn"))
        self.assertIsNone(self.away())
        # less than a minute ago
        self.chat(*self.work(self.now - 55))
        self.assertIsNone(self.away())
        # no message of yours and never shown: since when?
        self.chat(*self.work(t)[1:])
        self.assertIsNone(self.away())

    def test_since_a_window_last_showed_it(self):
        t = self.now - 3600
        self.chat(*self.work(t), dict(prompt("and the docs", t + 100, cwd=str(self.folder)), uuid="u2"),
                  text_reply("Done.", t + 200, "m6", "end_turn"))
        # shown after its last reply: nothing since
        cs.mark_seen(self.cache, SID, "", int((t + 300) * 1000))
        self.assertIsNone(self.away())
        # shown before Claude's last reply: that reply, though it's only one (you were away)
        cs.mark_seen(self.cache, SID, "", 1)   # (a mark only moves on)
        self.assertEqual(cs.seen_mark(self.cache, SID), int((t + 300) * 1000))
        (self.cache / cs.SEEN).unlink()
        cs.mark_seen(self.cache, SID, "", int((t + 150) * 1000))
        got = self.away()
        self.assertEqual({k: got[k] for k in ("from", "since", "key", "stepKey", "steps", "replies", "fileCount", "test")},
                         {"from": "seen", "since": int((t + 150) * 1000), "key": "m6", "stepKey": "m6", "steps": 0,
                          "replies": 1, "fileCount": 0, "test": None})
        # your message after the window last showed it: since then (there, its reply alone: nothing to tell)
        (self.cache / cs.SEEN).unlink()
        cs.mark_seen(self.cache, SID, "", int((t + 30) * 1000))
        self.assertIsNone(self.away())
        self.chat(dict(prompt("hi", t, cwd=str(self.folder)), uuid="u0"), text_reply("Hello.", t + 5, "m0", "end_turn"),
                  dict(prompt("and the docs", t + 45, cwd=str(self.folder)), uuid="u2"), *self.work(t + 100)[1:])
        got = self.away()
        self.assertEqual((got["from"], got["since"], got["steps"], got["stepKey"]), ("you", int((t + 45) * 1000), 4, "t1"))

    def test_what_it_waits_for(self):
        t = self.now - 600
        self.chat(*self.work(t))
        # (a step not done yet isn't a prompt it waits on: the front ends tell that from its row's state)
        with mock.patch.object(cs, "pending_permission", return_value=cs.permission_view("Bash", {"command": "ls"}, "")):
            self.assertEqual(self.away()["asks"], "")
        entries = self.work(t)
        entries[-1] = text_reply("Should I also fix the lexer?", t + 50, "m5", "end_turn")
        self.chat(*entries)
        self.assertEqual(self.away()["asks"], "question")

    def test_seen_is_kept_here(self):
        t = self.now - 600
        self.chat(*self.work(t))
        shown = int((t + 21) * 1000)   # (the newest item the window shows: what it took of the answers before)
        first = self.cli("--conversation", SID, "--seen", str(shown))
        self.assertEqual(cs.seen_mark(self.cache, SID), shown)
        self.assertEqual(oct(os.stat(self.cache / cs.SEEN).st_mode & 0o777), "0o600")
        # kept before the read: a watcher's wait doesn't hold it back
        with mock.patch.object(pane, "wait_for_change", side_effect=lambda *a, **kw: self.assertEqual(
                cs.seen_mark(self.cache, SID), shown + 5) or False):
            self.assertEqual(self.cli("--conversation", SID, "--seen", str(shown + 5), "--if-changed", first["stamp"],
                                      "--wait", "5"), {"ok": True, "unchanged": True})
        # --away and --seen together: what it did since what a window showed before, then the mark moves
        got = self.cli("--conversation", SID, "--away", "--seen", str(int((t + 50) * 1000)))["away"]
        self.assertEqual((got["from"], got["since"], got["steps"], got["stepKey"]), ("seen", shown + 5, 2, "t3"))
        self.assertIsNone(self.cli("--conversation", SID, "--away")["away"])
        # on an SSH host (--remote): nothing kept there; away from the --since the computer asking gives
        (self.cache / cs.SEEN).unlink()
        self.cli("--conversation", SID, "--seen", "5", "--remote")
        self.assertFalse((self.cache / cs.SEEN).exists())
        got = self.cli("--conversation", SID, "--away", "--since", str(int((t + 35) * 1000)), "--remote")["away"]
        self.assertEqual((got["from"], got["steps"], got["fileCount"]), ("seen", 1, 0))

    def test_a_hosts_mark_is_kept_here(self):
        cs.mark_seen(self.cache, SID, "gpu", 5000)
        cs.mark_seen(self.cache, SID, "", 9000)   # (this computer's chat of that id: not the host's)
        there = {"ok": True, "items": [], "stamp": "1:2/120", "more": False, "away": None}

        def answer(*a, **kw):
            self.assertEqual(cs.seen_mark(self.cache, SID, "gpu"), 7000)   # (kept before it's asked there)
            return dict(there)
        with mock.patch("remote.host_answer", side_effect=answer) as asked:
            self.cli("--conversation", SID, "--host", "gpu", "--away", "--seen", "7000")
        # (the mark before goes as --since; --seen isn't sent there)
        self.assertEqual(asked.call_args_list[0][0], ("gpu", ["--conversation", SID, "--away", "--since", "5000"]))
        self.assertEqual((cs.seen_mark(self.cache, SID, "gpu"), cs.seen_mark(self.cache, SID)), (7000, 9000))
        with mock.patch("remote.host_answer", return_value={"ok": True, "unchanged": True}):
            self.cli("--conversation", SID, "--host", "gpu", "--if-changed", "1:2/120")   # (no --seen: nothing kept)
        self.assertEqual(cs.seen_mark(self.cache, SID, "gpu"), 7000)

    def test_marks_follow_the_chat(self):
        other = "6d2e8b7f-1e5a-4b9c-8b62-2a3f4e5d6c7b"
        for chat, at in ((SID, 1000), (other, 2000)):
            cs.mark_seen(self.cache, chat, "", at)
        cs.mark_seen(self.cache, SID, "gpu", 3000)
        # moved to the background under a new id: its mark goes along (the newer of the two)
        new = "7e3f9c80-2f6b-4cad-9c73-3b4f5e6d7e8c"
        cs.seen_moved(self.cache, {SID: new})
        self.assertEqual((cs.seen_mark(self.cache, SID), cs.seen_mark(self.cache, new)), (0, 1000))
        # deleted: gone (a host's of that id stays)
        cs.forget_seen(self.cache, [new, "not an id"])
        self.assertEqual(cs.load_seen(self.cache), {other: 2000, cs.review_key(SID, "gpu"): 3000})
        # the newest SEEN_MAX kept
        with mock.patch.object(cs, "SEEN_MAX", 2):
            cs.mark_seen(self.cache, new, "", 4000)
        self.assertEqual(set(cs.load_seen(self.cache)), {cs.review_key(SID, "gpu"), new})

    def test_read_from_further_on(self):
        away = turns.Away(1000)
        away.entry(5000)
        away.step(6000, "t1")
        away.step(7000, "t2")
        away.reply(8000, "m1")
        self.assertTrue(away.result(10 ** 9, whole=False)["partial"])   # (what came before 5000 wasn't read)
        self.assertFalse(away.result(10 ** 9, whole=True)["partial"])
        away = turns.Away(5000)
        away.entry(4000)
        away.reply(8000, "m1")
        self.assertFalse(away.result(10 ** 9, whole=False)["partial"])

    def test_the_usage_says_so(self):
        self.assertIn("[--suggest] [--reach KEY] [--seen MS] [--away]", pane.__doc__)


class ContextAndTurnTests(PaneFixture):
    """Talpy Chat's header says how much of the chat's context is left till
    Claude compacts it (A7), its working line how long Claude's turn has run
    and its steps so far (A8): both from the transcript, in the
    --conversation answer (turns.py: context_left, TurnSoFar)."""

    def answer(self, *entries, limit=None):
        self.chat(*entries)
        return self.cli("--conversation", SID, *(("--limit", str(limit)) if limit else ()))

    def test_context_left_till_claude_compacts_the_chat(self):
        t = self.now - 100
        a = self.answer(prompt("hello", t, cwd=str(self.folder)), using(t + 1, "m1", "claude-opus-5-5", 2000, 8000, 290000))
        # (what Claude's last message read, cached or not, against its model's window; Claude Code compacts
        # the chat at the window less the room it keeps for Claude's reply (20k) and 13k more)
        self.assertEqual(a["context"], {"used": 300000, "window": 1000000, "compactAt": 967000, "left": 69, "near": False})
        a = self.answer(prompt("hello", t, cwd=str(self.folder)), using(t + 1, "m1", "claude-opus-5-5", 10, 0, 950000))
        self.assertEqual((a["context"]["left"], a["context"]["near"]), (2, True))   # (Claude Code says so 20k before)

    def test_the_window_by_model(self):
        left, u = turns.context_left, (lambda n: {"input_tokens": n})
        self.assertEqual(left(u(150000), "claude-sonnet-4-5-20250929"),
                         {"used": 150000, "window": 200000, "compactAt": 167000, "left": 10, "near": True})
        for model in ("claude-opus-4-20250514", "claude-opus-4-1-20250805", "claude-haiku-4-5-20251001",
                      "us.anthropic.claude-sonnet-4-5-20250929-v1:0", "claude-opus-4-1@20250805", "claude-opus-4-6"):
            self.assertEqual(left(u(1000), model)["window"], 200000, model)
        for model in ("claude-opus-5-5", "claude-opus-4-7", "claude-sonnet-5", "claude-haiku-5-5", "claude-fable-5-1", "claude-fable-5-2"):
            self.assertEqual(left(u(1000), model)["window"], 1000000, model)
        # 1M chosen ([1m], or the status line says so), or a chat already past 200k: 1M
        self.assertEqual(left(u(1000), "claude-sonnet-4-6[1m]")["window"], 1000000)
        self.assertEqual(left(u(250000), "claude-sonnet-4-6")["window"], 1000000)
        self.assertEqual(left(u(1000), "claude-sonnet-4-6", lambda: 1000000)["window"], 1000000)
        self.assertEqual(left(u(1000), "claude-opus-5-5", lambda: 200000)["window"], 200000)   # (the status line knows best)
        self.assertEqual(left(u(1000), "claude-mystery-9", lambda: 400000)["window"], 400000)
        # not known: nothing rather than a guess
        for model in ("claude-mystery-9", "claude-3-5-sonnet-20241022", "gpt-4", None, "<synthetic>"):
            self.assertIsNone(left(u(1000), model), model)
        for usage in ({}, {"input_tokens": 0}, None, {"input_tokens": "many"}):
            self.assertIsNone(left(usage, "claude-opus-5-5"), usage)
        self.assertEqual(left(u(990000), "claude-opus-5-5")["left"], 0)   # (past it: auto-compact off)

    def test_the_auto_compact_window_you_set(self):
        # (Claude Code 2.1.318: CLAUDE_CODE_AUTO_COMPACT_WINDOW first, else autoCompactWindow, the model's in
        # modelSettings first; "auto": the model's own; from 100k to 1M; below the model's window it compacts by it)
        tokens = cs.compact_tokens
        self.assertEqual([tokens(v) for v in ("200k", "1M", "200000", "300", 250000, " 400K ", "50k", "5M", "auto", "", "x", True, None)],
                         [200000, 1000000, 200000, 300000, 250000, 400000, 100000, 1000000, None, None, None, None, None])
        settings = self.home / ".claude-work/settings.json"
        window = lambda model="claude-opus-5-5": cs.compact_window(self.home / ".claude-work", model)
        self.assertIsNone(window())   # (none: the model's own)
        write(settings, {"autoCompactWindow": 300000, "modelSettings": {"claude-sonnet-5": {"autoCompactWindow": "auto"},
                                                                         "claude-haiku-5-5": {"autoCompactWindow": 150000}}})
        self.assertEqual((window(), window("claude-sonnet-5-20260101"), window("claude-haiku-5-5")), (300000, None, 150000))
        write(settings, {"autoCompactWindow": 300000, "env": {"CLAUDE_CODE_AUTO_COMPACT_WINDOW": "200k"}, "x": 1})
        self.assertEqual(window(), 200000)   # (the env first; read again once the file changed)
        left = cs.context_left({"input_tokens": 150000}, "claude-opus-5-5", None, window())
        self.assertEqual((left["window"], left["compactAt"], left["left"], left["near"]), (200000, 167000, 10, True))
        # Talpy Chat's header says the same
        t = self.now - 100
        a = self.answer(prompt("hello", t, cwd=str(self.folder)), using(t + 1, "m1", "claude-opus-5-5", 10, 0, 149990))
        self.assertEqual((a["context"]["window"], a["context"]["left"]), (200000, 10))

    def test_context_is_claudes_last_message_of_its_own(self):
        t = self.now - 100
        start = (prompt("hello", t, cwd=str(self.folder)), using(t + 1, "m1", "claude-opus-5-5", 1000, 0, 49000))
        sub = using(t + 2, "m9", "claude-haiku-5-5", 5, 0, 99000, isSidechain=True)   # (a subagent's context is its own)
        limit = {"type": "assistant", "timestamp": iso(t + 3), "isApiErrorMessage": True,
                 "message": {"id": "e", "role": "assistant", "model": "<synthetic>", "usage": {"input_tokens": 0},
                             "content": [{"type": "text", "text": "You've hit your session limit"}]}}
        self.assertEqual(self.answer(*start, sub, limit)["context"]["used"], 50000)
        # compacted: not known till Claude's next message
        compacted = {"type": "system", "subtype": "compact_boundary", "timestamp": iso(t + 4)}
        self.assertIsNone(self.answer(*start, compacted)["context"])
        self.assertEqual(self.answer(*start, compacted, using(t + 5, "m2", "claude-opus-5-5", 9000))["context"]["used"], 9000)
        # no token counts, a model not known
        self.assertIsNone(self.answer(start[0], text_reply("Hi.", t + 1, "m1", "end_turn"))["context"])
        self.assertIsNone(self.answer(start[0], using(t + 1, "m1", "claude-mystery-9", 1000))["context"])

    def test_the_status_line_says_which_window(self):
        t = self.now - 100
        chat = (prompt("hello", t, cwd=str(self.folder)), using(t + 1, "m1", "claude-sonnet-4-6", 1000, 0, 99000))
        self.assertEqual(self.answer(*chat)["context"]["window"], 200000)
        snapshot = self.cache / "statusline/.claude-work" / f"{SID}.json"
        write(snapshot, {"session_id": SID, "model": {"id": "claude-sonnet-4-6[1m]"}})
        self.assertEqual(self.answer(*chat)["context"]["window"], 1000000)
        write(snapshot, {"session_id": SID, "model": {"id": "claude-sonnet-4-6"}, "context_window": {"context_window_size": 500000}})
        self.assertEqual(self.answer(*chat)["context"]["window"], 500000)
        # (one of another model: not this one's)
        write(snapshot, {"session_id": SID, "model": {"id": "claude-opus-5-5"}, "context_window": {"context_window_size": 1000000}})
        self.assertEqual(self.answer(*chat)["context"]["window"], 200000)

    def test_the_turn_so_far(self):
        t = self.now - 100
        go = prompt("run the tests", t, cwd=str(self.folder))
        both = {"type": "assistant", "timestamp": iso(t + 3), "message": {"id": "m2", "role": "assistant", "content": [
            {"type": "tool_use", "id": "t2", "name": "Read", "input": {}}, {"type": "tool_use", "id": "t3", "name": "Read", "input": {}}]}}
        a = self.answer(prompt("first", t - 50, cwd=str(self.folder)), text_reply("Done.", t - 49, "m0", "end_turn"), go,
                        tool_use("t1", "Bash", {"command": "ls"}, t + 1, "m1"), tool_result("t1", t + 2), both,
                        tool_use("sub", "Bash", {"command": "ls"}, t + 4, "m9", isSidechain=True),   # (a subagent's)
                        tool_result("t2", t + 5), tool_result("t3", t + 5), text_reply("Now the tests.", t + 6, "m3"))
        self.assertEqual(a["turn"], {"startedAt": cs.to_ms(iso(t)), "steps": 3})
        # over: nothing on the working line
        self.assertIsNone(self.answer(go, tool_use("t1", "Bash", {}, t + 1, "m1"), tool_result("t1", t + 2),
                                      text_reply("All pass.", t + 3, "m2", "end_turn"))["turn"])
        self.assertIsNone(self.answer(go, text_reply("All pass.", t + 3, "m2", "end_turn"),
                                      {"type": "system", "subtype": "compact_boundary", "timestamp": iso(t + 4)})["turn"])
        # (a message of yours Claude takes in as it works is no new turn; a prompt command is)
        taken = {"type": "attachment", "timestamp": iso(t + 3), "attachment": {
            "type": "queued_command", "prompt": "also this", "commandMode": "prompt", "origin": {"kind": "human"}}}
        self.assertEqual(self.answer(go, *steps(2, t + 1), taken, *steps(1, t + 4, start=2))["turn"],
                         {"startedAt": cs.to_ms(iso(t)), "steps": 3})
        skill = {"type": "user", "timestamp": iso(t + 5), "message": {"role": "user", "content":
                 "<command-message>tidy</command-message>\n<command-name>/tidy</command-name>"}}
        self.assertEqual(self.answer(go, *steps(2, t + 1), text_reply("Done.", t + 4, "m8", "end_turn"), skill,
                                     *steps(1, t + 6, start=2))["turn"], {"startedAt": cs.to_ms(iso(t + 5)), "steps": 1})

    def test_a_long_turn_counts_from_its_prompt_before_what_is_read(self):
        # (Talpy Chat reads the chat's last items only: a turn longer than that has its prompt further
        # back, found once and kept; the next read looks only at what was written since)
        t = self.now - 1000
        chat = [prompt("first", t - 9, cwd=str(self.folder)), text_reply("Done.", t - 8, "m", "end_turn"),
                prompt("go on", t - 5)] + steps(40, t)
        with mock.patch.object(pane, "PANE_TAIL_BYTES", 4000):
            a = self.answer(*chat, limit=10)
            self.assertTrue(a["more"])
            self.assertEqual(a["turn"], {"startedAt": cs.to_ms(iso(t - 5)), "steps": 40})
            self.assertEqual(cs.read_json(self.cache / "turns" / f"{SID}.json")["at"], cs.to_ms(iso(t - 5)))
            with mock.patch.object(turns, "turn_backward", side_effect=AssertionError("read again")):
                self.assertEqual(self.answer(*chat, *steps(3, t + 40, start=40), limit=10)["turn"]["steps"], 43)
                # a prompt of yours since: its turn
                self.assertEqual(self.answer(*chat, *steps(3, t + 40, start=40), prompt("next", t + 50),
                                             *steps(30, t + 51, start=43), limit=10)["turn"],
                                 {"startedAt": cs.to_ms(iso(t + 50)), "steps": 30})
            # (written again from the start: what was kept isn't of it; no prompt of yours in it: none)
            self.assertIsNone(self.answer(*steps(40, t), limit=10)["turn"])


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

    def test_off_asks_about_the_chats_talpy_chat_started(self):
        # (chats Talpy Chat started answer their prompts with a hook of their own, in their jobs' saved options:
        # turned off for every chat, you choose whether they keep it)
        pane.relay(self.home, [], True)
        hook = self.home / ".local/share/talpy-den/permission-hook.py"
        own = json.dumps(pane.set_hook({}, pane.hook_command(hook), True), separators=(",", ":"))
        write(self.home / ".claude-work/jobs/1a2b3c4d/state.json", {"sessionId": "x", "respawnFlags": ["--settings", own]})
        write(self.home / ".claude-work/jobs/5e6f7a8b/state.json", {"sessionId": "y", "respawnFlags": ["--settings", "{}"]})
        write(self.home / ".claude-personal/jobs/9c0d1e2f/state.json", {"sessionId": "z", "respawnFlags": ["--settings=" + own]})
        self.assertEqual(self.cli("--relay", "status")["hooked"], 2)
        # no: off for every chat, theirs stays
        self.assertEqual(self.cli("--relay", "off", "--keep-copy")["message"],
                         "Permission prompts are answered in the chats, but for the chats started from Talpy Chat")
        self.assertTrue(hook.exists())
        self.assertFalse(self.cli("--relay", "status")["some"])
        # yes: theirs goes too (they ask in their own prompt: the hook's command runs nothing then)
        pane.relay(self.home, [], False)
        self.assertFalse(hook.exists())

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
        # a mail link to its addresses only (?attach= would put a file of yours in the mail)
        html = markdown('Md.toHtml("[m](mailto:a@evil.example?attach=/home/you/.ssh/id_ed25519&body=x)", style)')
        self.assertEqual(re.findall(r'href="([^"]*)"', html), ["mailto:a@evil.example"])

    def test_a_links_address_shows_before_the_click(self):
        # [github.com/…](https://evil.example/) showed the GitHub words and opened the other site
        ui = CODE.parent / "ui"
        pane = (ui / "ChatPane.qml").read_text()
        self.assertIn("pane.linkHovered(replyText, link, replyHover.point.position)", pane)   # (onLinkHovered, with the Copy frame)
        self.assertIn('active: pane.linkShown !== "" && pane.linkBox !== null', pane)   # (made only while hovered)
        self.assertIn('active: planText.hoveredLink !== ""', (ui / "PermissionAsk.qml").read_text())

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
class AnsiTests(unittest.TestCase):
    """ansi.mjs: what a command printed, its colours as runs (VS Code) and as Qt rich text (Plasma)."""

    def node(self, script):
        code = f"import * as A from {json.dumps(str(UI / 'ansi.mjs'))};\n" + script
        out = subprocess.run(["node", "--input-type=module", "-e", code], capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def test_colours_and_the_rest_left_out(self):
        r = self.node("""
const t = "\\x1b[1mBold\\x1b[22m \\x1b[31mred\\x1b[39m \\x1b[38;5;196mx\\x1b[0m \\x1b[38;2;1;2;3my\\x1b[0m"
        + " \\x1b[2mdim\\x1b[22m \\x1b]0;a title\\x07\\x1b[2Kz\\x1b[7mi\\x1b[27m <&>\\n2";
console.log(JSON.stringify({
    runs: A.runs(t).map(r => [r.text, r.fg, r.bold, r.dim, r.inverse]),
    plain: A.plain(t), grey: A.color256(244), cube: A.color256(16 + 36 * 5),
    html: A.html(t, {fg: "#cccccc", bg: "#000000", dark: true}),
    light: A.runs("\\x1b[31mr", A.LIGHT)[0].fg, cut: A.plain("ok\\x1b[38;5")
}));""")
        self.assertEqual(r["runs"], [["Bold", "", True, False, False], [" ", "", False, False, False], ["red", "#f0726a", False, False, False],
                                     [" ", "", False, False, False], ["x", "#ff0000", False, False, False], [" ", "", False, False, False],
                                     ["y", "#010203", False, False, False], [" ", "", False, False, False], ["dim", "", False, True, False],
                                     [" z", "", False, False, False], ["i", "", False, False, True], [" <&>\n2", "", False, False, False]])
        self.assertEqual(r["plain"], "Bold red x y dim zi <&>\n2")
        self.assertEqual((r["grey"], r["cube"], r["light"], r["cut"]), ("#808080", "#ff0000", "#c4372c", "ok"))
        self.assertTrue(r["html"].startswith('<p style="white-space:pre-wrap;margin:0"><span style="font-weight:600">Bold</span>'))
        self.assertIn('<span style="color:#707070">dim</span>', r["html"])   # (dim: half over the background)
        self.assertIn('<span style="color:#000000;background-color:#cccccc">i</span>', r["html"])   # (inverse)
        self.assertIn(" &lt;&amp;&gt;<br>2</p>", r["html"])


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


