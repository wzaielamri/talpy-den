"""Live mode: the live hook (live_hook.py), the watcher (live.py --wait),
turning it on and off (pane.py --live) and the rows that carry it."""
import claude_guard  # noqa: F401  (first: no test runs the real claude)
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_talpy_den import PID, ROOT, Fixture, cs, session, write  # noqa: E402

CODE = ROOT / "package/contents/code"
sys.path.insert(0, str(CODE))
import live  # noqa: E402
import pane  # noqa: E402

SID = "9462af8a-86f1-4200-8aad-f8c6ee7fec6b"
CWD = "/home/me/repos/app"


def event(kind, **kw):
    """A hook event as Claude Code 2.1.310 sends it (the fields the hook reads)."""
    base = {"session_id": SID, "transcript_path": "/home/me/.claude/projects/-home-me-repos-app/%s.jsonl" % SID,
            "cwd": CWD, "permission_mode": "default", "hook_event_name": kind}
    return dict(base, **kw)


def bash(tid, command):
    return {"tool_name": "Bash", "tool_input": {"command": command, "description": "run it"}, "tool_use_id": tid}


EDIT = {"tool_name": "Edit", "tool_use_id": "toolu_e", "tool_input": {
    "file_path": CWD + "/parser.py", "old_string": "hello", "new_string": "bye", "replace_all": False}}
EDITED = {"filePath": CWD + "/parser.py", "oldString": "hello", "newString": "bye", "originalFile": "hello file\n",
          "structuredPatch": [{"oldStart": 1, "oldLines": 3, "newStart": 1, "newLines": 4,
                               "lines": [" a", "-hello file", "+bye file", "+one more", " b"]}]}


class HookFixture(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.live = self.home / ".cache/talpy-den/live"

    def hook(self, *events, raw=None):
        """Run the hook as Claude runs it (python3 -I -S, the event on stdin), once per event."""
        env = {"HOME": str(self.home), "PATH": os.environ.get("PATH", "/usr/bin")}
        for e in events:
            done = subprocess.run([sys.executable, "-I", "-S", str(CODE / "live_hook.py")],
                                  input=raw if raw is not None else json.dumps(e), env=env,
                                  capture_output=True, text=True, timeout=20)
            self.assertEqual((done.returncode, done.stdout, done.stderr), (0, "", ""))
        return self.view()

    def view(self, sid=SID):
        path = self.live / (sid + ".json")
        return json.loads(path.read_text()) if path.exists() else None


class LiveHookTests(HookFixture):
    def test_a_turn_step_by_step(self):
        v = self.hook(event("SessionStart", source="startup", model="claude-haiku-5-5"))
        self.assertEqual((v["state"], v["doing"], v["steps"], v["pid"]), ("idle", "", [], os.getpid()))
        self.assertEqual((v["sessionId"], v["cwd"], v["event"]), (SID, CWD, "SessionStart"))
        v = self.hook(event("UserPromptSubmit", prompt="fix the parser"))
        self.assertEqual((v["state"], v["doing"]), ("working", "thinking…"))
        v = self.hook(event("PreToolUse", **bash("toolu_b", "sleep 4; echo hi")))
        self.assertEqual((v["state"], v["doing"]), ("working", "Bash: sleep 4; echo hi"))
        self.assertEqual([(s["id"], s["end"], s["ok"]) for s in v["steps"]], [("toolu_b", None, None)])
        v = self.hook(event("PostToolUse", tool_response={"stdout": "hi"}, duration_ms=5519, **bash("toolu_b", "sleep 4; echo hi")))
        self.assertTrue(v["steps"][0]["ok"])
        self.assertIsNotNone(v["steps"][0]["end"])
        self.assertNotIn("add", v["steps"][0])  # (not an edit)
        # (a permission request names no tool call, as Claude Code 2.1.310 sends it)
        asked = {k: val for k, val in EDIT.items() if k != "tool_use_id"}
        v = self.hook(event("PreToolUse", **EDIT), event("PermissionRequest", permission_suggestions=[], **asked))
        self.assertEqual((v["state"], v["asks"], v["doing"]), ("waiting", "permission", "Edit: parser.py"))
        self.assertEqual([s["id"] for s in v["steps"]], ["toolu_b", "toolu_e"])  # (the request is the same step)
        v = self.hook(event("Notification", message="Claude needs your permission", notification_type="permission_prompt"))
        self.assertEqual((v["state"], v["asks"]), ("waiting", "permission"))
        v = self.hook(event("PostToolUse", tool_response=EDITED, **EDIT))
        self.assertEqual((v["state"], v["asks"]), ("working", None))  # (allowed: it ran)
        self.assertEqual((v["steps"][1]["text"], v["steps"][1]["add"], v["steps"][1]["del"]), ("Edit: parser.py", 2, 1))
        v = self.hook(event("Stop", stop_hook_active=False, last_assistant_message="**Done.** `parse` in\nworks now.",
                            background_tasks=[], session_crons=[]))
        self.assertEqual((v["state"], v["doing"], v["said"]), ("idle", "", "Done. parse in"))
        v = self.hook(event("SessionEnd", reason="prompt_input_exit"))
        self.assertEqual((v["state"], v["pid"]), ("ended", os.getpid()))  # (Claude is gone by then: its pid stays)

    def test_a_quick_tools_end_can_come_first(self):
        read = {"tool_name": "Read", "tool_use_id": "toolu_r", "tool_input": {"file_path": CWD + "/a.txt"}}
        v = self.hook(event("PostToolUse", tool_response={"type": "text"}, **read), event("PreToolUse", **read))
        self.assertEqual([(s["text"], s["ok"]) for s in v["steps"]], [("Read: a.txt", True)])
        self.assertIsNotNone(v["steps"][0]["end"])

    def test_failures_new_files_and_questions(self):
        v = self.hook(event("PostToolUseFailure", error="Exit code 1\nboom", **bash("toolu_f", "pytest")))
        self.assertEqual((v["steps"][0]["ok"], v["steps"][0]["error"]), (False, "Exit code 1 boom"))
        write_new = {"tool_name": "Write", "tool_use_id": "toolu_w",
                     "tool_input": {"file_path": CWD + "/b.txt", "content": "one\ntwo\nthree"}}
        v = self.hook(event("PostToolUse", tool_response={"type": "create", "structuredPatch": []}, **write_new))
        self.assertEqual((v["steps"][1]["add"], v["steps"][1]["del"]), (3, 0))
        ask = {"tool_name": "AskUserQuestion", "tool_use_id": "toolu_q", "tool_input": {"questions": []}}
        v = self.hook(event("PermissionRequest", **ask))
        self.assertEqual((v["state"], v["asks"]), ("waiting", "question"))
        v = self.hook(event("StopFailure", error="rate_limit", error_details="You've hit your session limit"))
        self.assertEqual((v["state"], v["failed"], v["said"]), ("idle", "rate_limit", "You've hit your session limit"))
        v = self.hook(event("UserPromptSubmit", prompt="go on"))
        self.assertNotIn("failed", v)

    def test_subagents(self):
        v = self.hook(event("SubagentStart", agent_id="a1", agent_type="Explore"),
                      event("PreToolUse", agent_id="a1", agent_type="Explore",
                            **{"tool_name": "Grep", "tool_use_id": "toolu_g", "tool_input": {"pattern": "def parse"}}))
        self.assertEqual(v["agents"][0]["type"], "Explore")
        self.assertEqual(v["agents"][0]["doing"], "Grep: def parse")
        self.assertEqual((v["steps"][0]["agent"], v["doing"]), ("Explore", ""))  # (the main thread's line stays)
        v = self.hook(event("PermissionRequest", agent_id="a1", **bash("toolu_x", "rm -r build")))
        self.assertEqual(v["state"], "idle")  # (a subagent's: the session file says it)
        v = self.hook(event("SubagentStop", agent_id="a1", agent_type="Explore", agent_transcript_path="/x",
                            stop_hook_active=False))
        self.assertEqual(v["agents"], [])

    def test_steps_are_few_and_short(self):
        v = self.hook(*[event("PreToolUse", **bash("toolu_%d" % i, "echo %d " % i + "x" * 200)) for i in range(12)])
        self.assertEqual(len(v["steps"]), live_hook_steps())
        self.assertEqual(v["steps"][-1]["id"], "toolu_11")
        self.assertLessEqual(len(v["doing"]), 70)

    def test_events_at_once_are_all_kept(self):
        # (Claude doesn't wait for one event's hook before it sends the next)
        env = {"HOME": str(self.home), "PATH": os.environ.get("PATH", "/usr/bin")}
        procs = [subprocess.Popen([sys.executable, "-I", "-S", str(CODE / "live_hook.py")], stdin=subprocess.PIPE,
                                  env=env, text=True) for _ in range(6)]
        for i, p in enumerate(procs):
            p.stdin.write(json.dumps(event("PreToolUse", **bash("toolu_%d" % i, "echo %d" % i))))
            p.stdin.close()
        for p in procs:
            self.assertEqual(p.wait(20), 0)
        self.assertEqual(sorted(s["id"] for s in self.view()["steps"]), ["toolu_%d" % i for i in range(6)])

    def test_what_it_ignores(self):
        self.hook(raw="not json")
        self.hook(event("Stop", session_id="../../etc/passwd"))
        self.hook(event("Notification", notification_type="auth_success", message="hi"))
        self.hook(event("CwdChanged"))
        self.assertFalse(self.live.exists() and [n for n in os.listdir(self.live) if n.endswith(".json")])

    def test_old_live_files_go_when_a_session_starts(self):
        old = self.live / "old.json"
        write(old, {"v": 1})
        os.utime(old, (time.time() - 4 * 86400,) * 2)
        self.hook(event("SessionStart", source="startup"))
        self.assertFalse(old.exists())
        self.assertEqual(oct(os.stat(self.live / (SID + ".json")).st_mode & 0o777), "0o600")

    def test_a_long_chats_lock_stays(self):
        # a lock is never written (its time is the chat's first event): it
        # goes with its live file only, else two events of a chat running for
        # days could fold at once
        days = (time.time() - 4 * 86400,) * 2
        write(self.live / "long.json", {"v": 1})
        for name in ("long.lock", "gone.lock"):
            write(self.live / name, "")
            os.utime(self.live / name, days)
        self.hook(event("SessionStart", source="startup"))
        self.assertTrue((self.live / "long.lock").exists())
        self.assertFalse((self.live / "gone.lock").exists())   # (its chat's live file went before)
        os.utime(self.live / "long.json", days)
        self.hook(event("SessionStart", source="startup"))
        self.assertEqual([n for n in os.listdir(self.live) if n.startswith("long")], [])


def live_hook_steps():
    import importlib.util
    spec = importlib.util.spec_from_file_location("live_hook", CODE / "live_hook.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.STEPS


class ThroughAShellTests(HookFixture):
    """Claude runs a hook's command with sh -c (Claude Code 2.1.311: its
    spawn with shell: true). dash, Debian's and Ubuntu's sh, stays as the
    hook's parent unless the command execs: an entry written before the
    command had exec doesn't. Either way the live file names Claude (here,
    this test), so its row carries it."""

    def run_as(self, shell, command):
        env = {"HOME": str(self.home), "PATH": os.environ.get("PATH", "/usr/bin")}
        done = subprocess.run([shell, "-c", command], input=json.dumps(event("UserPromptSubmit", prompt="go")),
                              env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual((done.returncode, done.stdout, done.stderr), (0, "", ""))
        return self.view()

    def test_old_and_new_commands(self):
        import shlex
        script = shlex.quote(str(CODE / "live_hook.py"))
        python = shlex.quote(sys.executable)
        for shell in [s for s in ("sh", "dash", "bash") if shutil.which(s)]:
            for command in (f"{python} -I -S {script}", f"exec {python} -I -S {script}"):
                with self.subTest(shell=shell, command=command[:4]):
                    v = self.run_as(shell, command)
                    self.assertEqual((v["state"], v["pid"]), ("working", os.getpid()))
                    self.assertEqual(cs.live_view(self.home / ".cache/talpy-den", SID, os.getpid())["state"], "working")


class HookRefreshTests(unittest.TestCase):
    """A widget updated while a hook is on: the hook's copy that Claude's
    settings name comes up to date at the next status check
    (talpy_den.refresh_hooks), only ever to a newer one, and one that's off
    stays off."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "home"
        self.data = self.home / ".local/share/talpy-den"
        self.data.mkdir(parents=True)
        p = mock.patch.dict(os.environ, {"XDG_DATA_HOME": ""})
        p.start()
        self.addCleanup(p.stop)

    def test_an_older_copy_is_replaced(self):
        live_copy = self.data / "live-hook.py"
        live_copy.write_text("# the live hook, as an older version had it\n")
        live_copy.chmod(0o640)
        self.assertEqual(cs.refresh_hooks(self.home), ["live-hook.py"])
        self.assertEqual(live_copy.read_bytes(), (CODE / "live_hook.py").read_bytes())
        self.assertEqual(live_copy.stat().st_mode & 0o777, 0o640)
        self.assertFalse((self.data / "permission-hook.py").exists())   # (off: not turned on)
        self.assertEqual(sorted(p.name for p in self.data.iterdir()), ["live-hook.py"])
        self.assertEqual(cs.refresh_hooks(self.home), [])   # (up to date)

    def test_never_an_older_one(self):
        newer = "HOOK_REVISION = %d\n# from a newer version\n" % (cs.hook_revision((CODE / "permission_hook.py").read_bytes()) + 1)
        (self.data / "permission-hook.py").write_text(newer)
        self.assertEqual(cs.refresh_hooks(self.home), [])
        self.assertEqual((self.data / "permission-hook.py").read_text(), newer)
        self.assertEqual(cs.hook_revision(b"no line"), 1)
        for name in ("permission_hook.py", "live_hook.py"):
            self.assertGreaterEqual(cs.hook_revision((CODE / name).read_bytes()), 2)

    def test_at_a_status_check(self):
        (self.data / "permission-hook.py").write_text("# older\n")
        env = dict(os.environ, HOME=str(self.home), XDG_CACHE_HOME=str(self.home / ".cache"), XDG_DATA_HOME="")
        out = subprocess.run([sys.executable, "-I", str(CODE / "talpy_den.py"), "--no-tokens"], env=env,
                             capture_output=True, text=True, timeout=60)
        self.assertTrue(json.loads(out.stdout)["ok"], out.stdout)
        self.assertEqual((self.data / "permission-hook.py").read_bytes(), (CODE / "permission_hook.py").read_bytes())
        # on an SSH host the script comes on stdin, without the hooks: their copies stay as they are
        (self.data / "permission-hook.py").write_text("# older\n")
        out = subprocess.run([sys.executable, "-I", "-", "--remote", "--no-tokens"], env=env, capture_output=True,
                             text=True, timeout=60, input=(CODE / "talpy_den.py").read_text())
        self.assertTrue(json.loads(out.stdout.split(cs.REMOTE_MARK)[1])["ok"])
        self.assertEqual((self.data / "permission-hook.py").read_text(), "# older\n")


class WaitTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.sessions = self.home / ".claude-work/sessions"
        self.sessions.mkdir(parents=True)
        (self.home / ".claude").symlink_to(self.home / ".claude-work")  # (the same folder: watched once)
        self.live = self.home / ".cache/talpy-den/live"
        env = mock.patch.dict(os.environ, {"XDG_CACHE_HOME": str(self.home / ".cache")})
        env.start()
        self.addCleanup(env.stop)

    def wait(self, timeout=5, later=None, after=0.3):
        """live.wait, with later() run after a moment (a change while it waits)."""
        if later:
            threading.Timer(after, later).start()
        started = time.time()
        answer = live.wait(self.home, (), "test", timeout)
        return answer, time.time() - started

    def put(self, sid, kind, doing=""):
        write(self.live / (sid + ".json"), {"v": 1, "sessionId": sid, "event": kind, "doing": doing})

    def test_first_answer_then_only_changes(self):
        self.assertEqual(live.session_dirs(self.home), [str(self.sessions.resolve())])
        self.put("a", "Stop")
        answer, took = self.wait()
        self.assertEqual((answer["sessions"], answer["urgent"], [v["sessionId"] for v in answer["live"]]),
                         (True, True, ["a"]))
        self.assertLess(took, 1)
        answer, took = self.wait(timeout=1)
        self.assertEqual((answer["timeout"], answer["live"], answer["sessions"]), (True, [], False))
        self.assertGreaterEqual(took, 0.9)

    def test_a_session_file_wakes_it_at_once(self):
        self.wait()
        answer, took = self.wait(later=lambda: write(self.sessions / "123.json", session("x")))
        self.assertEqual((answer["sessions"], answer["urgent"], answer["live"]), (True, True, []))
        self.assertLess(took, 1)
        # (written in place, as Claude does)
        answer, _ = self.wait(later=lambda: write(self.sessions / "123.json", session("x", status="busy")))
        self.assertTrue(answer["sessions"])
        answer, _ = self.wait(later=lambda: (self.sessions / "123.json").unlink())
        self.assertTrue(answer["sessions"])

    def test_steps_alone_come_at_most_every_gap(self):
        self.wait()
        answer, _ = self.wait(later=lambda: self.put("b", "PreToolUse", "Bash: ls"))
        self.assertEqual((answer["urgent"], answer["sessions"], answer["live"][0]["doing"]), (False, False, "Bash: ls"))
        self.put("b", "PostToolUse", "Bash: ls")  # (right after the last answer)
        answer, took = self.wait()
        self.assertEqual(answer["live"][0]["event"], "PostToolUse")
        self.assertGreater(took, live.MIN_GAP_S * 0.5)
        self.put("b", "Stop")  # (a turn's end doesn't wait)
        answer, took = self.wait()
        self.assertTrue(answer["urgent"])
        self.assertLess(took, live.MIN_GAP_S * 0.5)

    def test_a_clock_set_back_doesnt_hold_steps_back(self):
        # the last answer's time is later than now (the clock went back an
        # hour): a step comes at once, not an hour later, and so does the timeout
        self.wait()
        self.put("d", "PreToolUse", "Bash: ls")
        answers = []
        run = threading.Thread(target=lambda: answers.append(live.wait(self.home, (), "test", 2,
                                                                       clock=lambda: time.time() - 3600)), daemon=True)
        run.start()
        run.join(5)
        self.assertEqual([a["live"][0]["doing"] for a in answers], ["Bash: ls"])
        answers.clear()
        run = threading.Thread(target=lambda: answers.append(live.wait(self.home, (), "test", 1,
                                                                       clock=lambda: time.time() - 7200)), daemon=True)
        run.start()
        run.join(5)
        self.assertEqual([a["timeout"] for a in answers], [True])

    def test_nothing_between_two_runs_is_missed(self):
        self.wait()
        self.put("c", "UserPromptSubmit")  # (while no watcher runs)
        answer, took = self.wait()
        self.assertEqual([v["event"] for v in answer["live"]], ["UserPromptSubmit"])
        self.assertLess(took, 1)

    def test_command_line(self):
        out = subprocess.run([sys.executable, "-I", str(CODE / "live.py"), "--wait", "--as", "x", "--timeout", "1"],
                             env=dict(os.environ, HOME=str(self.home)), capture_output=True, text=True, timeout=20)
        self.assertTrue(json.loads(out.stdout)["ok"])


class HostWatchTests(WaitTests):
    """(2026-11-06) live.py on an SSH host or in a container (remote.py
    --watch): the permission hook's requests too (a prompt shows within a
    second), what changed between two runs never lost, no live files, and
    gone as soon as the connection that asked is."""

    def setUp(self):
        super().setUp()
        self.asks = self.home / ".local/state/talpy-den/permissions"   # (beside ~/.cache, as the hook has it)

    def wait(self, timeout=5, later=None, after=0.3):
        if later:
            threading.Timer(after, later).start()
        started = time.time()
        answer = live.wait(self.home, (), "host", timeout, requests=True, remote=True)
        return answer, time.time() - started

    def ask(self, rid, sid="s1"):
        write(self.asks / f"{rid}.json", {"id": rid, "sessionId": sid, "tool": "Bash"})

    def test_first_answer_then_only_changes(self):
        answer, took = self.wait()
        self.assertEqual((answer["sessions"], answer["requests"], answer["changed"], answer["live"]), (True, True, [], []))
        self.assertEqual(oct(self.asks.stat().st_mode & 0o777), "0o700")   # (made, so it can be watched)
        answer, took = self.wait(timeout=1)
        self.assertEqual((answer["timeout"], answer["requests"], answer["changed"]), (True, False, []))
        # no live files there: a step of a chat doesn't wake it (nothing there uses them)
        self.put("a", "Stop")
        answer, _ = self.wait(timeout=1)
        self.assertTrue(answer["timeout"])

    def test_a_request_wakes_it_at_once(self):
        self.wait()
        answer, took = self.wait(later=lambda: self.ask("1-0a1b2c3d", "chat-1"))
        self.assertEqual((answer["requests"], answer["urgent"], answer["sessions"], answer["changed"]),
                         (True, True, False, ["chat-1"]))
        self.assertLess(took, 1)
        # your answer beside it isn't one; its going is (answered)
        answer, _ = self.wait(timeout=1, later=lambda: write(self.asks / "1-0a1b2c3d.answer.json", {"behavior": "allow"}))
        self.assertTrue(answer["timeout"])
        answer, _ = self.wait(later=lambda: (self.asks / "1-0a1b2c3d.json").unlink())
        self.assertEqual((answer["requests"], answer["changed"]), (True, ["chat-1"]))
        # a session file: the chats whose files changed, a gone one's too
        answer, _ = self.wait(later=lambda: write(self.sessions / "123.json", session("chat-2", status="busy")))
        self.assertEqual((answer["sessions"], answer["requests"], answer["changed"]), (True, False, ["chat-2"]))
        answer, _ = self.wait(later=lambda: (self.sessions / "123.json").unlink())
        self.assertEqual(answer["changed"], ["chat-2"])

    def test_nothing_between_two_runs_is_missed(self):
        self.wait()
        self.ask("2-0a1b2c3d", "chat-3")   # (while no watcher runs: the request comes before the next run)
        answer, took = self.wait()
        self.assertEqual((answer["requests"], answer["changed"]), (True, ["chat-3"]))
        self.assertLess(took, 1)

    def test_steps_alone_come_at_most_every_gap(self):
        pass   # (no live files there)

    def test_a_clock_set_back_doesnt_hold_steps_back(self):
        pass

    def test_not_a_requests_folder_others_may_write_in(self):
        self.asks.mkdir(parents=True)
        os.chmod(self.asks, 0o777)
        self.assertEqual(live.request_dirs(self.home), [])
        os.chmod(self.asks, 0o700)
        self.assertEqual(live.request_dirs(self.home), [str(self.asks)])

    def test_command_line_after_the_marker(self):
        out = subprocess.run([sys.executable, "-I", "-", "--wait", "--requests", "--remote", "--as", "x", "--timeout", "1"],
                             input=(CODE / "live.py").read_text(), env=dict(os.environ, HOME=str(self.home)),
                             capture_output=True, text=True, timeout=20)
        self.assertTrue(out.stdout.startswith("\n" + cs.REMOTE_MARK + " "), out.stdout)
        self.assertTrue(json.loads(out.stdout.split(cs.REMOTE_MARK)[1])["ok"])

    def test_command_line(self):
        pass

    def test_gone_with_the_connection_that_asked(self):
        # (ssh killed here: sshd closes the channel, its stdout hangs up; an orphan would wait out its 50 s)
        r, w = os.pipe()
        proc = subprocess.Popen([sys.executable, "-I", str(CODE / "live.py"), "--wait", "--requests", "--remote",
                                 "--as", "x", "--timeout", "30"], stdout=w, env=dict(os.environ, HOME=str(self.home)))
        os.close(w)
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        first = os.read(r, 65536)   # (the first answer: everything is new to "x")
        self.assertIn(cs.REMOTE_MARK.encode(), first)
        proc.wait(5)
        proc = subprocess.Popen([sys.executable, "-I", str(CODE / "live.py"), "--wait", "--requests", "--remote",
                                 "--as", "x", "--timeout", "30"], stdout=subprocess.PIPE, env=dict(os.environ, HOME=str(self.home)))
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        time.sleep(0.5)
        proc.stdout.close()   # (whoever asked is gone)
        started = time.time()
        proc.wait(5)
        self.assertLess(time.time() - started, 2)
        os.close(r)


class LiveSwitchTests(Fixture):
    def setUp(self):
        super().setUp()
        p = mock.patch.dict(os.environ, {"XDG_DATA_HOME": str(self.home / ".local/share")})
        p.start()
        self.addCleanup(p.stop)

    def test_on_and_off(self):
        shared = self.home / ".claude-work/settings.json"
        guard = {"hooks": [{"type": "command", "command": "guard"}]}
        write(shared, {"model": "opus", "hooks": {"SessionStart": [guard], "PreToolUse": [dict(guard, matcher="*")]}})
        pane.relay(self.home, [], True)
        self.assertEqual(pane.live(self.home, [], True), (True, "Chats show each step as it happens"))
        hooks = json.loads(shared.read_text())["hooks"]
        hook = self.home / ".local/share/talpy-den/live-hook.py"
        self.assertEqual(hook.read_text(), (CODE / "live_hook.py").read_text())
        self.assertEqual(sorted(hooks), sorted(set(pane.LIVE_EVENTS)))
        mine = {"type": "command", "command": f"[ -f {hook} ] || exit 0; exec python3 -I -S {hook}", "async": True, "timeout": 10}
        self.assertEqual(hooks["SessionStart"], [guard, {"hooks": [mine]}])
        self.assertEqual(hooks["PreToolUse"], [dict(guard, matcher="*"), {"matcher": "*", "hooks": [mine]}])
        self.assertEqual(len(hooks["PermissionRequest"]), 2)  # (the permission hook stays)
        self.assertTrue(pane.relay_status(self.home, [], "live")["on"])
        before = shared.stat().st_mtime_ns
        self.assertEqual(pane.live(self.home, [], True)[1], "Chats show each step as it happens (they did already)")
        self.assertEqual(shared.stat().st_mtime_ns, before)
        # an older copy that had fewer events gets the rest
        data = json.loads(shared.read_text())
        del data["hooks"]["PreCompact"]
        write(shared, data)
        self.assertFalse(pane.relay_status(self.home, [], "live")["on"])
        pane.live(self.home, [], True)
        self.assertTrue(pane.relay_status(self.home, [], "live")["on"])
        self.assertTrue(cs.live_hook_on(self.home))
        pane.live(self.home, [], False)
        hooks = json.loads(shared.read_text())["hooks"]
        self.assertEqual((hooks["SessionStart"], hooks["PreToolUse"]), ([guard], [dict(guard, matcher="*")]))
        self.assertEqual(sorted(hooks), ["PermissionRequest", "PreToolUse", "SessionStart"])
        self.assertFalse(hook.exists())
        self.assertFalse(cs.live_hook_on(self.home))
        self.assertTrue(pane.relay_status(self.home, [], "relay")["on"])

    def test_an_entry_written_before_is_replaced(self):
        # python3 -I -S PATH (no exec): still the live hook's, replaced once
        settings = self.home / ".claude-work/settings.json"
        older = "python3 -I -S %s" % (self.home / ".local/share/talpy-den/live-hook.py")
        write(settings, {"hooks": {e: [{"hooks": [{"type": "command", "command": older, "async": True, "timeout": 10}]}]
                                   for e in pane.LIVE_EVENTS}})
        self.assertTrue(pane.relay_status(self.home, [], "live")["some"])
        pane.live(self.home, [], True)
        hooks = json.loads(settings.read_text())["hooks"]
        self.assertEqual({e: [h["command"] for g in groups for h in g["hooks"]] for e, groups in hooks.items()},
                         {e: [pane.hook_command(pane.hook_path(self.home, "live"), "live")] for e in pane.LIVE_EVENTS})
        pane.live(self.home, [], False)
        self.assertNotIn("hooks", json.loads(settings.read_text()))

    def test_command_line(self):
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.object(cs.Path, "home", return_value=self.home):
            pane.main(["--live", "status"])
        self.assertEqual(json.loads(out.getvalue())["on"], False)


class LiveRowTests(Fixture):
    def test_a_running_chats_row_carries_its_live_file(self):
        live_dir = self.cache / "live"
        write(live_dir / "busy.json", {"v": 1, "sessionId": "busy", "pid": PID, "state": "working",
                                       "doing": "Bash: pytest", "steps": [], "agents": [], "at": 5})
        write(live_dir / "waiting.json", {"v": 1, "sessionId": "waiting", "pid": PID + 1, "state": "working"})
        write(live_dir / "perso-idle.json", {"v": 1, "sessionId": "perso-idle", "pid": PID, "state": "ended"})
        status = cs.collect(self.home, self.cache, with_tokens=False)
        rows = {s["sessionId"]: s for g in status["groups"] for s in g["sessions"]}
        self.assertEqual((rows["busy"]["live"]["doing"], rows["busy"]["live"]["state"]), ("Bash: pytest", "working"))
        self.assertIsNone(rows["waiting"]["live"])  # (another process's)
        self.assertIsNone(rows["perso-idle"]["live"])  # (ended)
        self.assertIsNone(rows["bgworking"]["live"])
        self.assertFalse(status["liveHook"])


if __name__ == "__main__":
    unittest.main()
