"""SSH hosts: the host list, and status/open/run through a stand-in ssh that
runs the command locally in a fake remote home."""
import contextlib
import importlib.util
import io
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
CODE = Path(__file__).resolve().parent.parent / "package/contents/code"
sys.path.insert(0, str(CODE))
spec = importlib.util.spec_from_file_location("remote", CODE / "remote.py")
remote = importlib.util.module_from_spec(spec)
spec.loader.exec_module(remote)
cs = remote.cs

FAKE_SSH = r'''#!/bin/bash
# Stand-in for ssh: skip options, take the host, run the command here with bash
# in the fake remote home. FAKE_SSH_MODE picks a failure to imitate.
log="$FAKE_SSH_LOG"
while [ $# -gt 0 ]; do
  case "$1" in
    -o) shift 2 ;;
    -T|-t) shift ;;
    -O) shift 2 ;;  # (a control command, e.g. -O check: the "connection" is always there)
    *) break ;;
  esac
done
host="$1"; shift
cmd="$*"
printf '%s\t%s\n' "$host" "$cmd" >> "$log"
[ -n "$FAKE_SSH_PIDFILE" ] && echo $$ > "$FAKE_SSH_PIDFILE"
case "$FAKE_SSH_MODE" in
  denied) echo "$host: Permission denied (publickey)." >&2; exit 255 ;;
  hostkey) echo "Host key verification failed." >&2; exit 255 ;;
  unreachable) echo "ssh: connect to host x port 22: Connection timed out" >&2; exit 255 ;;
  slow) sleep 5 ;;
  noisy) echo "Welcome to the cluster! Quota: 80%" ;;
  flood) head -c 3000000 /dev/zero | tr '\0' x ;;
  latin1) printf 'Gr\374\337 Gott\n' ;;
  fish|tcsh)  # a login shell that reads quotes its own way (LOGIN_SHELL)
    cd "$FAKE_HOME" && exec env -i HOME="$FAKE_HOME" PATH="$FAKE_PATH" XDG_CACHE_HOME="$FAKE_HOME/.cache" \
      python3 -I "$(dirname "$0")/login_shell.py" "$FAKE_SSH_MODE" "$cmd" ;;
  warning)  # the host's shell warns on stderr after the command's output
    cd "$FAKE_HOME" && env -i HOME="$FAKE_HOME" PATH="$FAKE_PATH" XDG_CACHE_HOME="$FAKE_HOME/.cache" bash -c "$cmd"
    rc=$?; echo "bash: warning: setlocale: LC_ALL: cannot change locale (de_DE.UTF-8)" >&2; exit $rc ;;
esac
cd "$FAKE_HOME" && exec env -i HOME="$FAKE_HOME" PATH="$FAKE_PATH" XDG_CACHE_HOME="$FAKE_HOME/.cache" bash -c "$cmd"
'''


# A stand-in for fish or tcsh as the host's login shell: it splits the
# command into words its way and runs them. In single quotes, fish takes \\
# and \' as escapes; tcsh refuses a newline and expands !history.
LOGIN_SHELL = r'''
import os, sys
kind, line = sys.argv[1], sys.argv[2]

def fail(message):
    sys.stderr.write(message + "\n")
    sys.exit(1)

words, word, inword, i = [], "", False, 0
while i < len(line):
    c = line[i]
    if c in " \t":
        if inword:
            words.append(word)
        word, inword, i = "", False, i + 1
        continue
    inword = True
    if c == "'":
        i += 1
        while True:
            if i >= len(line) or (kind == "tcsh" and line[i] == "\n"):
                fail("Unmatched '.")
            if line[i] == "'":
                break
            if kind == "tcsh" and line[i] == "!" and line[i + 1:i + 2] not in ("", " ", "\t", "\n", "="):
                fail(line[i:].split()[0] + ": Event not found.")
            if kind == "fish" and line[i] == "\\" and line[i + 1:i + 2] in ("\\", "'"):
                i += 1
            word += line[i]
            i += 1
        i += 1
    elif c == '"':
        i += 1
        while i < len(line) and line[i] != '"':
            if line[i] in "$`\\!":
                fail("not imitated in double quotes: " + line[i])
            word += line[i]
            i += 1
        if i >= len(line):
            fail('Unmatched ".')
        i += 1
    elif c.isalnum() or c in "-_./=:,+@%":
        word += c
        i += 1
    else:
        fail("not imitated: " + c)
if inword:
    words.append(word)
os.execvp(words[0], words)
'''


def unwrapped(command):
    """The command inside remote.posix()'s `sh -c '…'` (or the printf of it there)."""
    words = shlex.split(command)
    if words[:2] != ["sh", "-c"] or len(words) != 3:
        return command
    escaped = re.fullmatch(r'eval "\$\(printf "(.*)"\)"', words[2], re.DOTALL)
    if escaped is None:
        return words[2]
    return re.sub(rb"\\([0-7]{3})", lambda m: bytes([int(m.group(1), 8)]), escaped.group(1).encode()).decode()


class HostListTests(unittest.TestCase):
    def test_parses_hosts_includes_and_skips_patterns(self):
        with tempfile.TemporaryDirectory() as tmp:
            ssh = Path(tmp)
            (ssh / "conf.d").mkdir()
            (ssh / "conf.d/lab.conf").write_text("Host gpu1 gpu2\n  HostName %h.lab.example\n  User me\n")
            (ssh / "config").write_text(textwrap.dedent(f"""\
                # global
                Host *
                    ForwardX11 yes
                Include {ssh}/conf.d/*.conf
                Host bastion
                 HostName bastion01.example.org
                 User alice
                 Port 2222
                Host gpubox
                 HostName=gpubox.intra
                 ProxyJump bastion
                 HostName second-value-ignored
                Host web-* !web-bad *.internal
                 User nobody
                Host pre
                Match host foo
                 User matched
                Host "quoted"
                """))
            hosts = remote.ssh_hosts(ssh / "config")
        self.assertEqual([h["name"] for h in hosts], ["gpu1", "gpu2", "bastion", "gpubox", "pre", "quoted"])
        by = {h["name"]: h for h in hosts}
        self.assertEqual(by["bastion"], {"name": "bastion", "hostname": "bastion01.example.org", "user": "alice",
                                      "port": "2222", "jump": ""})
        self.assertEqual((by["gpubox"]["hostname"], by["gpubox"]["jump"]), ("gpubox.intra", "bastion"))
        self.assertEqual(by["gpu2"]["user"], "me")
        self.assertEqual(by["pre"]["user"], "")  # a Match block doesn't apply to the host before it

    def test_comments_and_includes_inside_a_host_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            ssh = Path(tmp)
            (ssh / "extra.conf").write_text("Host gitlab\n  User git\n")
            (ssh / "config").write_text(textwrap.dedent(f"""\
                Host lab # GPU box in room 3
                  HostName 192.0.2.7 # the old one was .6
                  Include {ssh}/extra.conf
                  User alice
                """))
            by = {h["name"]: h for h in remote.ssh_hosts(ssh / "config")}
        self.assertEqual(sorted(by), ["gitlab", "lab"])
        self.assertEqual((by["lab"]["hostname"], by["lab"]["user"]), ("192.0.2.7", "alice"))
        self.assertEqual(by["gitlab"]["user"], "git")

    def test_missing_config(self):
        self.assertEqual(remote.ssh_hosts(Path("/nonexistent/config")), [])

    def test_include_loop_is_harmless(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "config"
            cfg.write_text(f"Include {cfg}\nHost a\n")
            self.assertEqual([h["name"] for h in remote.ssh_hosts(cfg)], ["a"])

    def test_a_python3_too_old_there_says_so(self):
        # (2026-11-03) RHEL 8's 3.6 said "AttributeError: type object 'datetime.datetime' has no attribute 'fromisoformat'"
        from unittest import mock
        for script in (remote.host_script(), remote.host_script("sharing.py", ("accounts.py",))):
            out = io.StringIO()
            with contextlib.redirect_stdout(out), mock.patch.object(sys, "version_info", (3, 6, 8, "final", 0)), \
                    self.assertRaises(SystemExit):
                exec(compile(script, "<stdin>", "exec"), {"__name__": "__main__"})
            self.assertEqual(remote.answer_after_mark(out.getvalue())["error"], "python3 there is 3.6; Talpy Den needs 3.7 or newer")

    def test_host_names_checked(self):
        for bad in ("-oProxyCommand=evil", "a b", "", "x;rm", "$(id)"):
            with self.assertRaises(ValueError):
                remote.check_host(bad)
        self.assertEqual(remote.check_host("user@host.example:22"), "user@host.example:22")


class FakeSSH(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.bin, self.fake_home, self.log = root / "bin", root / "remote-home", root / "ssh.log"
        self.bin.mkdir()
        (self.bin / "ssh").write_text(FAKE_SSH)
        (self.bin / "ssh").chmod(0o755)
        (self.bin / "login_shell.py").write_text(LOGIN_SHELL)
        # the remote: one profile with a finished background job
        prof = self.fake_home / ".claude"
        (prof / "sessions").mkdir(parents=True)
        (prof / "projects/-p").mkdir(parents=True)
        (prof / ".claude.json").write_text(json.dumps({"oauthAccount": {"accountUuid": "r", "organizationType": "claude_max",
                                                                       "displayName": "Remote Me"}}))
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 60))
        (prof / "jobs/abc12345").mkdir(parents=True)
        (prof / "jobs/abc12345/state.json").write_text(json.dumps(
            {"state": "done", "tempo": "idle", "sessionId": "abc12345", "name": "remote job", "cwd": "/srv/x",
             "updatedAt": stamp, "createdAt": stamp}))
        python_dir = str(Path(sys.executable).parent)
        self.env = {"PATH": f"{self.bin}:{os.environ['PATH']}", "FAKE_HOME": str(self.fake_home),
                    "FAKE_PATH": f"{python_dir}:/usr/bin:/bin", "FAKE_SSH_LOG": str(self.log),
                    "XDG_CACHE_HOME": str(root / "local-cache")}
        self.saved = {k: os.environ.get(k) for k in [*self.env, "FAKE_SSH_MODE"]}
        os.environ.update(self.env)

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()

    def mode(self, name):
        os.environ["FAKE_SSH_MODE"] = name

    def raw_calls(self):
        return [line.split("\t", 1) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def calls(self):
        return [[host, unwrapped(command)] for host, command in self.raw_calls()]


class LoginShellTests(FakeSSH):
    """A host whose login shell is fish or tcsh runs the widget's POSIX
    commands as sh would (sh gets them in a word those shells leave alone)."""

    def test_any_login_shell(self):
        words = ["a\\b", "c:\\", "it's", "x!y", "$HOME", "100%", '"q"', "`id`", "Grüße", "two\nlines", "-n"]
        command = "printf '%s|' " + " ".join(shlex.quote(w) for w in words)
        for shell in ("", "fish", "tcsh"):
            self.mode(shell)
            r = remote.ssh("lab", command)
            self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "|".join(words) + "|", ""), shell)
        self.assertEqual(self.calls()[0], ["lab", command])
        self.assertEqual(remote.posix("python3 -I - --remote"), "sh -c 'python3 -I - --remote'")  # (as it is, when it can)

    def test_a_picture_goes_to_a_tcsh_host(self):
        here = cs.images_dir(Path.home()) / "20261026-101500.png"
        here.parent.mkdir(parents=True)
        here.write_bytes(b"\x89PNG\r\n\x1a\n\x00\xff a picture")
        self.mode("tcsh")
        answer = remote.put_image("lab", str(here))
        self.assertTrue(answer["ok"], answer)
        self.assertEqual((self.fake_home / ".cache/talpy-den/images" / here.name).read_bytes(), here.read_bytes())


    def test_your_text_goes_on_stdin(self):
        # (a command is in the process list for every user there and here; one argument holds 128 KiB at most;
        # tcsh refuses a newline in it)
        for text in ("語" * 50000 + " it's\n!x", "and the docs"):
            self.mode("tcsh")
            answer = remote.host_answer("lab", ["--send", "abc12345", "--text", text, "--how", "auto", "--after-turn",
                                                 "--profile", ".claude"],
                                        name="pane.py")
            self.assertTrue(answer["ok"], answer)
            self.assertEqual(self.calls()[-1][1], "python3 -I - --remote --send abc12345 --how auto --after-turn --profile .claude")
            (queued,) = cs.load_queue(self.fake_home / ".cache/talpy-den")
            self.assertEqual(queued["prompt"], text)  # (queued there, for when its turn ends)


class StatusTests(FakeSSH):
    def test_status_of_a_host(self):
        out = remote.status("lab", recent=3, tokens=False)
        self.assertTrue(out["ok"], out)
        result = out["result"]
        (group,) = result["groups"]
        self.assertEqual(group["title"], "Remote Me · Max")
        (row,) = group["sessions"]
        self.assertEqual((row["name"], row["state"]), ("remote job", "done"))
        self.assertIn("claude attach abc12345", row["openCommand"])
        ((host, command),) = self.calls()
        self.assertEqual((host, command), ("lab", "python3 -I - --remote --recent 3 --no-tokens"))
        # nothing was written on the remote except the widget's cache
        self.assertEqual(sorted(p.name for p in (self.fake_home / ".cache").iterdir()), ["talpy-den"])
        # how old the host's plan usage may get before Claude Code fetches it there
        self.assertTrue(remote.status("lab", tokens=False, usage_refresh=15)["ok"])
        self.assertEqual(self.calls()[-1][1], "python3 -I - --remote --no-tokens --usage-refresh 15")

    def test_a_chat_id_that_is_a_flag_is_dropped(self):
        # (passed on as a word of jump.py's command line, "--screenshot" was taken for that flag)
        rows = [{"sessionId": "--screenshot"}, {"sessionId": "abc12345", "chatId": "--pick-files"},
                {"sessionId": "a/../b"}, {"sessionId": "abc12345", "chatId": None}, {"sessionId": ""}]
        result = remote.chats_with_ids({"groups": [{"sessions": list(rows), "recent": list(rows), "starred": rows[:1]}]})
        (group,) = result["groups"]
        self.assertEqual(group["sessions"], rows[3:])
        self.assertEqual((group["recent"], group["starred"]), (rows[3:], []))

    def test_a_host_that_sends_too_much(self):
        # (it was all kept in memory, in hosts/lab.json and read again at every start)
        self.assertTrue(remote.status("lab", tokens=False)["ok"])
        kept = remote.answer_file("lab").read_bytes()
        self.mode("flood")
        with mock.patch.object(remote, "ANSWER_MAX", 1 << 20):
            out = remote.status("lab", tokens=False)
            self.assertEqual(out["error"], "lab sent too much (over 1 MB): Talpy Den stopped reading it.")
            self.assertEqual(remote.answer_file("lab").read_bytes(), kept, "not kept")
            self.assertIn("lab", remote.last_answers(["lab"]))
            remote.answer_file("lab").write_text(json.dumps({"answer": {"ok": True, "pad": "x" * (4 << 20)}}))
            self.assertEqual(remote.last_answers(["lab"]), {})  # (one kept before the cap)

    def test_login_noise_before_the_answer(self):
        self.mode("noisy")
        self.assertTrue(remote.status("lab")["ok"])

    def test_failures_explained(self):
        cases = {"denied": "refused the login", "hostkey": "host key isn't known yet",
                 "unreachable": "Can't reach lab"}
        for mode, words in cases.items():
            self.mode(mode)
            out = remote.status("lab")
            self.assertFalse(out["ok"])
            self.assertIn(words, out["error"], mode)

    def test_python_missing(self):
        os.environ["FAKE_PATH"] = "/nonexistent"
        out = remote.status("lab")
        self.assertIn("python3 isn't installed on lab", out["error"])

    def test_timeout(self):
        self.mode("slow")
        old = remote.STATUS_TIMEOUT
        remote.STATUS_TIMEOUT = 1
        try:
            out = remote.status("lab")
        finally:
            remote.STATUS_TIMEOUT = old
        self.assertEqual(out, {"ok": False, "host": "lab", "error": "lab didn't answer within 1 s."})

    def test_main_prints_json(self):
        r = subprocess.run([sys.executable, "-I", str(CODE / "remote.py"), "--status", "lab", "--no-tokens",
                            "--usage-refresh", "0"], capture_output=True, text=True, env=os.environ)
        self.assertTrue(json.loads(r.stdout)["ok"], r.stdout + r.stderr)
        r = subprocess.run([sys.executable, "-I", str(CODE / "remote.py"), "--status", "-oProxyCommand=x"],
                           capture_output=True, text=True, env=os.environ)
        self.assertFalse(json.loads(r.stdout)["ok"])


class ActionTests(FakeSSH):
    def test_run_and_its_errors(self):
        self.assertEqual(remote.run("lab", "echo stopped abc"), (True, "stopped abc"))
        self.assertEqual(remote.run("lab", "echo oops >&2; exit 3"), (False, "oops"))
        self.mode("denied")
        ok, message = remote.run("lab", "true")
        self.assertFalse(ok)
        self.assertIn("refused the login", message)

    def test_dismiss_on_the_host(self):
        self.assertEqual(remote.dismiss("lab", "abc12345"), (True, "Hid this chat"))
        self.assertIn("abc12345", cs.load_dismissed(self.fake_home / ".cache/talpy-den"))
        out = remote.status("lab", tokens=False)
        self.assertEqual(out["result"]["groups"][0]["sessions"], [])
        self.assertEqual(remote.dismiss("lab")[0], True)
        self.assertEqual(cs.load_dismissed(self.fake_home / ".cache/talpy-den"), {})

    def test_delete_on_the_host_to_its_trash(self):
        prof = self.fake_home / ".claude"
        (prof / "projects/-p/chat9.jsonl").write_text(json.dumps({"type": "custom-title", "customTitle": "Old work"}) + "\n")
        (prof / "projects/-p/chat9/subagents").mkdir(parents=True)
        (prof / "plans").mkdir()
        (prof / "plans/calm-red-owl.md").write_text("# Calm plan\n")
        local = cs.cache_dir(Path.home())
        cs.change_stars(local, "chats", "chat9", host="lab")  # (an SSH host's stars are kept here)
        asked = remote.delete("lab", "chat", "chat9", describe=True)
        self.assertEqual((asked["ok"], asked["accounts"], asked["question"]),
                         (True, ["Remote Me"], "Delete “Old work” on Remote Me? It goes to the Trash with its subagents and "
                                          "checkpoints; the Recap keeps its numbers."))
        self.assertEqual(remote.delete("lab", "chat", "chat9")["message"], "Moved to the Trash")
        trash = self.fake_home / ".local/share/Trash/files"
        self.assertEqual(sorted(f.name for f in trash.iterdir()), ["chat9", "chat9.jsonl"])
        self.assertFalse((prof / "projects/-p/chat9.jsonl").exists())
        self.assertEqual(cs.load_stars(local)["chats"], [])
        r = subprocess.run([sys.executable, "-I", str(CODE / "remote.py"), "--delete-plan", "lab", "calm-red-owl",
                            ".claude", "--describe"], capture_output=True, text=True, env=os.environ)
        self.assertEqual(json.loads(r.stdout)["question"], "Delete the plan “Calm plan” on Remote Me? It goes to the Trash.")
        self.assertEqual(remote.delete("lab", "plan", "calm-red-owl", ".claude")["message"], "Moved to the Trash")
        self.assertFalse(remote.delete("lab", "memory", ".claude/CLAUDE.md/memory")["ok"])

    def test_hide_on_the_host(self):
        # (kept on the host: its status leaves them out there)
        self.assertEqual(remote.hide("lab", "plans", "calm-red-owl"), (True, "Hid this plan"))
        self.assertEqual(remote.hide("lab", "projects", "/srv/app"), (True, "Hid this project"))
        self.assertEqual(list(cs.load_hidden(self.fake_home / ".cache/talpy-den")["plans"]), ["calm-red-owl"])
        self.assertEqual(remote.status("lab", tokens=False)["result"]["hiddenProjects"], 1)
        self.assertEqual(remote.hide("lab", "plans"), (True, "Showing 1 hidden plan again"))
        self.assertEqual(remote.hide("lab", "memories"), (True, "No memory was hidden"))
        self.assertEqual(remote.hide("lab", "chats", "abc12345"), (True, "Hid this chat"))
        self.assertIn("abc12345", cs.load_dismissed(self.fake_home / ".cache/talpy-den"))

    def test_stop_an_idle_chat_on_the_host(self):
        proc = subprocess.Popen([sys.executable, "-c", "print('ready', flush=True); import time; time.sleep(60)"],
                                stdout=subprocess.PIPE, text=True)
        self.addCleanup(proc.stdout.close)
        self.addCleanup(lambda: (proc.kill(), proc.wait()) if proc.poll() is None else None)
        self.assertEqual(proc.stdout.readline().strip(), "ready")
        (self.fake_home / f".claude/sessions/{proc.pid}.json").write_text(json.dumps(
            {"pid": proc.pid, "procStart": cs.proc_start_time(proc.pid), "sessionId": "idle-there",
             "cwd": "/srv/x", "kind": "interactive", "status": "idle"}))
        self.assertEqual(remote.end("lab", "idle-there", ".claude-work"), (False, "That chat isn't running any more"))
        self.assertIsNone(proc.poll())
        self.assertEqual(remote.end("lab", "idle-there", ".claude"), (True, "Stopped; the chat is kept"))
        self.assertEqual(proc.wait(timeout=5), -15)
        self.assertEqual(self.calls()[-1], ["lab", "python3 -I - --remote --end idle-there --profile .claude"])

    def test_stop_a_working_chat_or_interrupt_it_on_the_host(self):
        proc = subprocess.Popen([sys.executable, "-c", "print('ready', flush=True); import time; time.sleep(60)"],
                                stdout=subprocess.PIPE, text=True)
        self.addCleanup(proc.stdout.close)
        self.addCleanup(lambda: (proc.kill(), proc.wait()) if proc.poll() is None else None)
        self.assertEqual(proc.stdout.readline().strip(), "ready")
        (self.fake_home / f".claude/sessions/{proc.pid}.json").write_text(json.dumps(
            {"pid": proc.pid, "procStart": cs.proc_start_time(proc.pid), "sessionId": "busy-there",
             "cwd": "/srv/x", "kind": "interactive", "status": "busy"}))
        self.assertIn("doesn't run in tmux", remote.interrupt("lab", "busy-there")[1])
        self.assertEqual(self.calls()[-1], ["lab", "python3 -I - --remote --interrupt busy-there"])
        self.assertFalse(remote.end("lab", "busy-there")[0])   # working: only when you were told
        self.assertIsNone(proc.poll())
        out = subprocess.run([sys.executable, "-I", str(CODE / "remote.py"), "--end", "lab", "busy-there", ".claude", "--busy"],
                             capture_output=True, text=True, env=os.environ).stdout
        self.assertEqual(json.loads(out), {"ok": True, "message": "Stopped; the chat is kept"})
        self.assertEqual(proc.wait(timeout=5), -15)
        self.assertEqual(self.calls()[-1], ["lab", "python3 -I - --remote --end busy-there --profile .claude --busy"])

    def test_host_says_whether_claude_is_there(self):
        self.assertEqual(remote.status("lab", tokens=False)["result"]["cli"], {"installed": False})
        claude = self.fake_home / ".local/bin/claude"
        claude.parent.mkdir(parents=True)
        claude.write_text("#!/bin/sh\n")
        claude.chmod(0o755)
        result = remote.status("lab", tokens=False)["result"]
        self.assertEqual((result["cli"], result["claude"]), ({"installed": True}, str(claude)))

    def test_open_runs_the_command_unchanged_on_the_host(self):
        # A command with quotes, spaces and $: it must reach the host as is.
        command = "cd '/srv/my dir' 2>/dev/null; printf '%s\\n' \"$HOME\" 'it''s' > /dev/null; echo done"
        opened = []
        import jump
        old = jump.open_terminal
        jump.open_terminal = lambda cwd, cmd: opened.append(cmd) or True
        try:
            self.assertEqual(remote.open_remote("lab", command), (True, "Opened a terminal on lab"))
        finally:
            jump.open_terminal = old
        (ssh_line,) = opened
        words = shlex.split(ssh_line)
        self.assertEqual((words[0], words[-3:]), ("ssh", ["-t", "lab", remote.posix(command)]))
        self.assertNotIn("BatchMode=yes", ssh_line)  # a terminal may ask for a password
        out = subprocess.run(["bash", "-c", ssh_line], capture_output=True, text=True, env=os.environ)
        self.assertEqual(out.stdout.strip(), "done")
        self.assertEqual(self.calls()[-1], ["lab", command])

    def test_a_subagents_run_comes_here(self):
        d = self.fake_home / ".claude/projects/-p/abc12345/subagents"
        d.mkdir(parents=True)
        (d / "agent-ag1.meta.json").write_text(json.dumps({"agentType": "Explore", "description": "Check the host"}))
        report = {"type": "tool_use", "id": "h", "name": "SubagentHandback",
                  "input": {"message": "The widget's answer starts after \n" + cs.REMOTE_MARK + " {\"ok\": false}"}}
        (d / "agent-ag1.jsonl").write_text("".join(json.dumps(l) + "\n" for l in (
            {"type": "user", "isSidechain": True, "message": {"content": "Look around"}},
            {"type": "assistant", "isSidechain": True, "message": {"content": [report]}})))
        self.mode("noisy")  # a login banner first
        import jump
        opened, old = [], jump.open_markdown
        jump.open_markdown = lambda path, home=None: opened.append(path) or (True, "")
        try:
            ok, message, path = remote.agent_run("lab", "abc12345", "ag1")
            self.assertEqual(self.calls()[-1], ["lab", "python3 -I - --remote --agent-run ag1 --chat abc12345"])
            self.assertEqual(remote.agent_run("lab", "abc12345", "nope", ".claude", open_it=False),
                             (False, "lab: Can't find that subagent's transcript", None))
            self.assertEqual(self.calls()[-1], ["lab", "python3 -I - --remote --agent-run nope --chat abc12345 --profile .claude"])
        finally:
            jump.open_markdown = old
        self.assertEqual((ok, message), (True, "The run of “Check the host” on lab"))
        self.assertEqual(Path(path).parent, Path(self.env["XDG_CACHE_HOME"]) / "talpy-den/agent-runs")  # saved here
        self.assertIn(cs.REMOTE_MARK + ' {"ok": false}', Path(path).read_text())  # the marker in the run is just text
        self.assertEqual(opened, [Path(path)])
        self.mode("unreachable")
        self.assertFalse(remote.agent_run("lab", "abc12345", "ag1")[0])

    def test_agent_run_command_line(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            remote.main(["--agent-run", "lab", "abc12345", "missing", "--no-open"])
        self.assertEqual(json.loads(out.getvalue()), {"ok": False, "message": "lab: Can't find that subagent's transcript"})

    def test_control_socket_folder_is_short_and_only_yours(self):
        saved = (os.environ.get("XDG_RUNTIME_DIR"), remote.SOCKET_TMP)

        def restore():
            os.environ.pop("XDG_RUNTIME_DIR", None)
            if saved[0] is not None:
                os.environ["XDG_RUNTIME_DIR"] = saved[0]
            remote.SOCKET_TMP = saved[1]
        self.addCleanup(restore)
        with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
            os.environ["XDG_RUNTIME_DIR"] = tmp
            d = remote.control_dir()
            self.assertEqual(d, Path(tmp) / "talpy-den-ssh")
            self.assertEqual(d.stat().st_mode & 0o777, 0o700)
            self.assertIn(f"ControlPath={d}/%C", remote.ssh_options())
            self.assertLessEqual(len(f"{d}/{'0' * 40}.{'x' * 16}"), 107)  # what ssh binds
            # no runtime folder: one in /tmp, unless it's a link (or someone else's)
            del os.environ["XDG_RUNTIME_DIR"]
            remote.SOCKET_TMP = tmp
            self.assertEqual(remote.control_dir(), Path(tmp) / f"talpy-den-ssh-{os.getuid()}")
            os.rmdir(str(remote.control_dir()))
            os.symlink(tmp, str(Path(tmp) / f"talpy-den-ssh-{os.getuid()}"))
            self.assertIsNone(remote.control_dir())
            self.assertNotIn("ControlMaster=auto", remote.ssh_options())
            # a runtime folder so long that the socket path wouldn't fit: none either
            os.environ["XDG_RUNTIME_DIR"] = str(Path(tmp) / ("r" * 60))
            os.mkdir(os.environ["XDG_RUNTIME_DIR"])
            self.assertIsNone(remote.control_dir())


class TwoAccountHost(FakeSSH):
    """A host with two Claude accounts, a chat of the first one's and claude."""

    CHAT = "9a8b7c6d-0000-4000-8000-000000000002"

    def setUp(self):
        super().setUp()
        self.work = self.fake_home / ".claude-work"
        (self.work / "sessions").mkdir(parents=True)
        (self.work / ".claude.json").write_text(json.dumps({"oauthAccount": {"accountUuid": "w"}}))
        self.chat = self.fake_home / ".claude/projects/-srv-x" / f"{self.CHAT}.jsonl"
        self.chat.parent.mkdir(parents=True)
        self.chat.write_text(json.dumps({"type": "user", "cwd": "/srv/x", "sessionId": self.CHAT}) + "\n")
        self.there = self.work / "projects/-srv-x" / f"{self.CHAT}.jsonl"
        self.store = self.fake_home / ".local/share/claude-status/shared-chats/-srv-x"
        self.claude = self.fake_home / ".local/bin/claude"
        self.claude.parent.mkdir(parents=True)
        self.claude.write_text("#!/bin/sh\n")
        self.claude.chmod(0o755)


class SharingTests(TwoAccountHost):
    """Sharing a chat between the host's accounts: sharing.py runs there, sent
    with talpy_den.py like the status script."""

    def open_in_a_session(self):
        proc = subprocess.Popen([sys.executable, "-c", "print('ready', flush=True); import time; time.sleep(60)"],
                                stdout=subprocess.PIPE, text=True)
        self.addCleanup(proc.stdout.close)
        self.addCleanup(lambda: (proc.kill(), proc.wait()) if proc.poll() is None else None)
        self.assertEqual(proc.stdout.readline().strip(), "ready")
        (self.fake_home / f".claude/sessions/{proc.pid}.json").write_text(json.dumps(
            {"pid": proc.pid, "procStart": cs.proc_start_time(proc.pid), "sessionId": self.CHAT,
             "cwd": "/srv/x", "kind": "interactive", "status": "idle"}))

    def continue_there(self, *args, **kw):
        import jump
        opened, old = [], jump.open_terminal
        jump.open_terminal = lambda cwd, cmd: opened.append(cmd) or True
        try:
            return remote.continue_on("lab", self.CHAT, *args, **kw), opened
        finally:
            jump.open_terminal = old

    def test_the_hosts_accounts_can_share(self):
        result = remote.status("lab", tokens=False)["result"]
        self.assertTrue(result["canShare"])
        self.assertEqual(sorted(g["shareProfile"] for g in result["groups"]), [".claude", ".claude-work"])

    def test_share_then_keep_only_on_one_account(self):
        self.assertEqual(remote.share("lab", self.CHAT), (True, "Chat shared: it's now on main, work."))
        self.assertEqual(self.calls()[-1], ["lab", f"python3 -I - --remote --share {self.CHAT}"])
        self.assertTrue(os.path.samefile(self.there, self.chat))
        self.assertTrue(os.path.samefile(self.store / f"{self.CHAT}.jsonl", self.chat))
        shared = [c for g in remote.status("lab", tokens=False)["result"]["groups"] for c in g["recent"]]
        self.assertTrue(shared and all(c["shared"] for c in shared))
        self.assertEqual(remote.unshare("lab", self.CHAT, ".claude"),
                         (True, "This chat is now a normal chat of main again. Removed from work."))
        self.assertEqual(self.calls()[-1], ["lab", f"python3 -I - --remote --unshare {self.CHAT} --profile .claude"])
        self.assertFalse(os.path.lexists(self.there))
        self.assertFalse(self.store.exists())
        self.assertEqual(os.stat(self.chat).st_nlink, 1)

    def test_continue_on_another_account_there(self):
        (ok, message, command), opened = self.continue_there(".claude-work")
        self.assertEqual((ok, message), (True, "Opened a terminal on lab"))
        self.assertEqual(self.calls()[0], ["lab", f"python3 -I - --remote --continue {self.CHAT} --profile .claude-work"])
        self.assertTrue(os.path.samefile(self.there, self.chat))  # shared with work only
        self.assertTrue(command.startswith("cd /srv/x 2>/dev/null; "), command)
        self.assertTrue(command.endswith(f"CLAUDE_CONFIG_DIR={self.work.resolve()} {self.claude} --resume {self.CHAT}"),
                        command)
        (ssh_line,) = opened
        self.assertEqual(shlex.split(ssh_line)[-3:], ["-t", "lab", remote.posix(command)])

    def test_continue_can_hand_back_the_command(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            remote.main(["--continue", "lab", self.CHAT, ".claude-work", "--print-command"])
        answer = json.loads(out.getvalue())
        self.assertEqual((answer["ok"], answer["message"]), (True, "Continuing it on work"))
        self.assertTrue(answer["command"].endswith(f"--resume {self.CHAT}"))
        self.assertTrue(os.path.samefile(self.there, self.chat))

    def test_refused_while_a_session_has_it_open(self):
        self.open_in_a_session()
        ok, message = remote.share("lab", self.CHAT)
        self.assertFalse(ok)
        self.assertIn("It's open on main", message)
        (ok, message, command), opened = self.continue_there(".claude-work")
        self.assertEqual((ok, command, opened), (False, None, []))
        self.assertIn("It's open on main", message)
        self.assertFalse(os.path.lexists(self.there))
        self.assertFalse(self.store.exists())

    def test_errors_come_back(self):
        self.assertEqual(remote.unshare("lab", self.CHAT, ".claude-nope"), (False, "No Claude profile called .claude-nope"))
        self.assertEqual(remote.unshare("lab", self.CHAT, ".claude"), (False, "This chat isn't shared"))
        self.mode("denied")
        ok, message = remote.share("lab", self.CHAT)
        self.assertFalse(ok)
        self.assertIn("refused the login", message)

    def test_a_refusal_stays_one_when_the_shell_warns(self):
        # A warning on stderr used to be taken as the answer: "done"
        self.mode("warning")
        self.assertEqual(remote.unshare("lab", self.CHAT, ".claude"), (False, "This chat isn't shared"))
        self.open_in_a_session()
        ok, message = remote.share("lab", self.CHAT)
        self.assertFalse(ok)
        self.assertIn("It's open on main", message)


class HostNoiseTests(FakeSSH):
    """Whatever a host prints besides the answer can't change it."""

    def test_a_chat_that_mentions_the_marker(self):
        state = self.fake_home / ".claude/jobs/abc12345/state.json"
        job = json.loads(state.read_text())
        state.write_text(json.dumps({**job, "name": f"why {cs.REMOTE_MARK} breaks"}))
        out = remote.status("lab")
        self.assertTrue(out["ok"], out)
        (row,) = out["result"]["groups"][0]["sessions"]
        self.assertEqual(row["name"], f"why {cs.REMOTE_MARK} breaks")

    def test_a_greeting_that_isnt_utf8(self):
        self.mode("latin1")
        out = remote.status("lab")
        self.assertTrue(out["ok"], out)

    def test_warnings_on_stderr(self):
        self.mode("warning")
        self.assertEqual(remote.dismiss("lab", "abc12345"), (True, "Hid this chat"))
        self.assertEqual(remote.run("lab", "echo hello"), (True, "hello"))
        ok, message = remote.end("lab", "not-there")
        self.assertFalse(ok)
        self.assertNotIn("setlocale", message)

    def test_commands_run_in_sh_whatever_the_login_shell(self):
        remote.run("lab", "echo hi")
        ((host, raw),) = self.raw_calls()
        self.assertEqual(shlex.split(raw)[:2], ["sh", "-c"])

    def test_the_hosts_own_remote_command_and_forwards_are_left_out(self):
        for opts in (remote.ssh_options(), remote.ssh_options(batch=False)):
            self.assertIn("RemoteCommand=none", opts)
            self.assertIn("ClearAllForwardings=yes", opts)

    def test_sigterm_ends_its_ssh_too(self):
        pidfile = Path(self.tmp.name) / "ssh.pid"
        self.mode("slow")
        proc = subprocess.Popen([sys.executable, "-I", str(CODE / "remote.py"), "--status", "lab"],
                                env={**os.environ, "FAKE_SSH_PIDFILE": str(pidfile)},
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            if pidfile.exists() and pidfile.read_text().strip():
                break
            time.sleep(0.05)
        ssh_pid = int(pidfile.read_text())
        proc.terminate()
        self.assertEqual(proc.wait(timeout=10), 143)
        with self.assertRaises(ProcessLookupError):
            os.kill(ssh_pid, 0)

class AccountTests(FakeSSH):
    """The host's Claude accounts: accounts.py runs there, sent with
    talpy_den.py like sharing.py; a login opens a terminal here (ssh -t)."""

    def setUp(self):
        super().setUp()
        self.claude = self.fake_home / ".local/bin/claude"
        self.claude.parent.mkdir(parents=True)
        self.claude.write_text("#!/bin/sh\necho \"Successfully logged out.\"\n")
        self.claude.chmod(0o755)

    def run_main(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            remote.main(list(args))
        return json.loads(out.getvalue())

    def opening(self, *args):
        import jump
        opened, old = [], jump.open_terminal
        jump.open_terminal = lambda cwd, cmd: opened.append(cmd) or True
        try:
            return self.run_main("--accounts", "lab", *args), opened
        finally:
            jump.open_terminal = old

    def test_the_hosts_accounts(self):
        answer = self.run_main("--accounts", "lab", "--list")
        self.assertTrue(answer["ok"], answer)
        self.assertEqual([a["key"] for a in answer["accounts"]], [".claude"])
        self.assertEqual(self.calls()[-1], ["lab", "python3 -I - --remote --list"])

    def test_add_one_and_log_in_here_over_ssh(self):
        answer, opened = self.opening("--add", "side", "--command")
        self.assertTrue(answer["ok"], answer)
        side = self.fake_home / ".claude-side"
        self.assertEqual((side / ".profile-name").read_text(), "side\n")
        self.assertTrue((self.fake_home / ".local/bin/claude-side").exists())
        (line,) = opened  # a terminal here, running Claude's login there
        words = shlex.split(line)
        self.assertEqual(words[0], "ssh")
        self.assertEqual(words[-2], "lab")
        self.assertIn(f"CLAUDE_CONFIG_DIR={side} {self.claude} auth login", words[-1])
        self.assertIn("paste the code", words[-1])
        self.assertNotIn("command", answer)

    def test_the_login_command_for_a_terminal_of_your_own(self):
        answer, opened = self.opening("--login", ".claude", "--print-command")
        self.assertEqual(opened, [])
        self.assertTrue(answer["command"].endswith(f"env -u CLAUDE_CONFIG_DIR {self.claude} auth login"), answer)
        self.assertEqual(self.calls()[-1], ["lab", "python3 -I - --remote --login .claude"])

    def test_default_and_remove_there(self):
        main = self.fake_home / ".claude"
        os.rename(main, self.fake_home / ".claude-main")
        os.symlink(".claude-main", main)
        (self.fake_home / ".claude-work/projects").mkdir(parents=True)
        (self.fake_home / ".claude-work/.profile-name").write_text("work")
        answer = self.run_main("--accounts", "lab", "--default", ".claude-work")
        self.assertTrue(answer["ok"], answer)
        self.assertEqual(os.readlink(main), ".claude-work")  # the host's link, as it was written (relative)
        answer = self.run_main("--accounts", "lab", "--remove", ".claude-main")
        self.assertTrue(answer["ok"], answer)
        self.assertTrue((self.fake_home / ".local/share/Trash/files/.claude-main/jobs").is_dir())

    def test_default_on_a_host_with_vscode(self):
        # the host's VS Code server gives Claude Code there its account: Make
        # Default changes that entry (comments kept) and the host's ~/.claude link
        main = self.fake_home / ".claude"
        os.rename(main, self.fake_home / ".claude-main")
        os.symlink(self.fake_home / ".claude-main", main)
        (self.fake_home / ".claude-work/projects").mkdir(parents=True)
        (self.fake_home / ".claude-work/.profile-name").write_text("work")
        settings = self.fake_home / ".vscode-server/data/Machine/settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text('{\n    // the host\'s own\n    "claudeCode.environmentVariables": [\n'
                            f'        {{"name": "CLAUDE_CONFIG_DIR", "value": "{self.fake_home / ".claude-main"}"}}\n    ]\n}}\n')
        status = remote.status("lab", tokens=False)["result"]
        self.assertEqual([(g["name"], g["defaultHere"]) for g in status["groups"]][0], ("main", True))
        listed = self.run_main("--accounts", "lab", "--list")
        self.assertTrue(listed["canDefault"])
        self.assertTrue(next(a for a in listed["accounts"] if a["key"] == ".claude-main")["default"])
        answer = self.run_main("--accounts", "lab", "--default", ".claude-work")
        self.assertTrue(answer["ok"], answer)
        self.assertEqual(os.readlink(main), str(self.fake_home / ".claude-work"))
        text = settings.read_text()
        self.assertIn("// the host's own", text)
        self.assertEqual(cs.jsonc(text)["claudeCode.environmentVariables"],
                         [{"name": "CLAUDE_CONFIG_DIR", "value": str(main)}])  # the link's name: it leads there now
        self.assertEqual(answer["configDir"], str(main))
        status = remote.status("lab", tokens=False)["result"]
        self.assertEqual([(g["name"], g["defaultHere"]) for g in status["groups"]][0], ("work", True))

    def test_only_accounts_actions(self):
        self.assertFalse(self.run_main("--accounts", "lab", "--status")["ok"])



class HostTaskTests(TwoAccountHost):
    """Finding chats, starting tasks and plans on a host (talpy_den.py and
    sharing.py there, sent over the connection)."""

    def setUp(self):
        super().setUp()
        self.plan = self.fake_home / ".claude/plans/calm-red-owl.md"
        self.plan.parent.mkdir(parents=True)
        self.plan.write_text("# Calm plan\n\n1. Do it\n")
        self.folder = self.fake_home / "srv-app"
        self.folder.mkdir()
        (self.fake_home / ".claude/.claude.json").write_text(json.dumps({
            "oauthAccount": {"accountUuid": "r", "organizationType": "claude_max", "displayName": "Remote Me"},
            "projects": {str(self.folder): {"hasTrustDialogAccepted": True}}}))
        self.claude.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$HOME/claude-args\"\necho 'Started 1a2b3c4d'\n")

    def test_find_there(self):
        answer = remote.find("lab", "/srv/x")
        self.assertTrue(answer["ok"], answer)
        (found,) = answer["results"]
        self.assertEqual(found["sessionId"], self.CHAT)
        self.assertIn(f"--resume {self.CHAT}", found["openCommand"])
        self.assertEqual(self.calls()[-1], ["lab", "python3 -I - --remote --find /srv/x"])

    def test_a_task_in_the_background_there(self):
        answer = remote.task("lab", ".claude", str(self.folder), "fix it", "calm-red-owl", ".claude", background=True)
        self.assertEqual((answer["ok"], answer["id"]), (True, "1a2b3c4d"), answer)
        args = (self.fake_home / "claude-args").read_text()
        self.assertNotIn("fix it", self.calls()[-1][1])  # (on stdin: remote.with_texts)
        self.assertTrue(args.startswith("--bg\nfix it\n\nThe plan (saved as ~/.claude/plans/calm-red-owl.md):"), args)
        # not where Claude doesn't trust the folder (its home, here)
        answer = remote.task("lab", ".claude", "~", "fix it", background=True)
        self.assertFalse(answer["ok"])
        self.assertIn("doesn't trust your home folder", answer["message"])

    def test_a_task_in_a_terminal_here(self):
        import jump
        opened, old = [], jump.open_terminal
        jump.open_terminal = lambda cwd, cmd: opened.append(cmd) or True
        try:
            answer = remote.task("lab", ".claude-work", str(self.folder), "write tests")
        finally:
            jump.open_terminal = old
        self.assertTrue(answer["ok"], answer)
        (ssh_line,) = opened
        command = shlex.split(ssh_line)[-1]
        self.assertEqual(shlex.split(unwrapped(command))[-1], "write tests")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            remote.main(["--task", "lab", ".claude", str(self.folder), "--prompt", "go", "--print-command"])
        # (one word: with a space in front, so it isn't one of claude's commands)
        self.assertTrue(json.loads(out.getvalue())["command"].endswith(" ' go'"))

    def test_a_picture_goes_there_for_a_task_that_opens_it(self):
        here = cs.images_dir(Path.home()) / "20261026-101500.png"
        here.parent.mkdir(parents=True)
        here.write_bytes(b"\x89PNG\r\n\x1a\n\x00\xff a picture")
        answer = remote.put_image("lab", str(here))
        there = self.fake_home / ".cache/talpy-den/images"
        self.assertEqual(answer, {"ok": True, "message": "", "path": str(there / here.name), "local": str(here)})
        self.assertEqual((there / here.name).read_bytes(), here.read_bytes())
        self.assertEqual((oct(there.stat().st_mode & 0o777), oct((there / here.name).stat().st_mode & 0o777)),
                         ("0o700", "0o600"))
        # another one of that name there (from another computer) stays
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            remote.main(["--put-image", "lab", str(here)])
        self.assertEqual(json.loads(out.getvalue())["path"], str(there / "20261026-101500-h2.png"))
        # only pictures pasted into a task
        for other in (self.plan, here.parent / "notes.txt"):
            self.assertEqual(remote.put_image("lab", str(other)),
                             {"ok": False, "message": "That isn't a picture pasted into a task"})
        self.mode("denied")
        self.assertFalse(remote.put_image("lab", str(here))["ok"])
        self.mode("")
        # the task naming it there: Claude there may open that folder
        answer = remote.task("lab", ".claude", str(self.folder), f"What's wrong? [Image: {there / here.name}]",
                             background=True)
        self.assertTrue(answer["ok"], answer)
        args = (self.fake_home / "claude-args").read_text().splitlines()
        self.assertEqual(args[:2], ["--bg", f"--add-dir={there}"])

    def test_a_plan_comes_here_and_is_shared_there(self):
        import jump
        opened, old = [], jump.open_markdown
        jump.open_markdown = lambda path, home=None: opened.append(path) or (True, "")
        try:
            ok, message, path = remote.open_plan("lab", "calm-red-owl", ".claude")
        finally:
            jump.open_markdown = old
        self.assertEqual((ok, message), (True, "Opened the plan Calm plan from lab (a copy)"))
        self.assertEqual(Path(path).read_text(), "# Calm plan\n\n1. Do it\n")
        self.assertEqual(opened, [Path(path)])
        self.assertEqual(remote.plan_sharing("lab", "calm-red-owl", ".claude", True),
                         (True, "Plan shared: it's on main, work now."))
        self.assertTrue(os.path.samefile(self.plan, self.work / "plans/calm-red-owl.md"))
        self.assertEqual(remote.plan_sharing("lab", "calm-red-owl", ".claude-work", False),
                         (True, "The plan is only on work now. Removed from main."))
        self.assertFalse(self.plan.exists())

    def test_a_plan_moves_into_its_project_there(self):
        chat = "dddddddd-1111-2222-3333-444444444444"
        transcript = self.fake_home / ".claude/projects/-srv-app" / f"{chat}.jsonl"
        transcript.parent.mkdir(parents=True)
        transcript.write_text(json.dumps({"type": "user", "cwd": str(self.folder), "sessionId": chat, "slug": "calm-red-owl",
                                          "message": {"role": "user", "content": "plan it"}}) + "\n")
        os.utime(self.plan, (time.time() - 600, time.time() - 600))
        here = Path(os.environ["XDG_CACHE_HOME"]) / "talpy-den"
        cs.change_stars(here, "plans", "calm-red-owl", "lab")   # (an SSH host's stars are kept here)
        (self.folder / ".claude/plans").mkdir(parents=True)
        (self.folder / ".claude/plans/calm-red-owl.md").write_text("# Another plan\n")
        # (older than the account's: else it's the plan, the account's an old copy: cs.project_wins)
        os.utime(self.folder / ".claude/plans/calm-red-owl.md", (time.time() - 1200, time.time() - 1200))
        asked = remote.move_plan("lab", "calm-red-owl", ".claude", describe=True)
        self.assertTrue(asked["ok"], asked)
        self.assertEqual((asked["default"], asked["exists"], asked["free"], asked["setting"]),
                         (str(self.folder), True, "calm-red-owl-2", ""))
        self.assertTrue(self.plan.is_file())   # (asking moves nothing)
        moved = remote.move_plan("lab", "calm-red-owl", ".claude", if_exists="keep")
        self.assertEqual((moved["ok"], moved["slug"]), (True, "calm-red-owl-2"), moved)
        self.assertFalse(self.plan.exists())
        self.assertEqual((self.folder / ".claude/plans/calm-red-owl-2.md").read_text(), "# Calm plan\n\n1. Do it\n")
        self.assertEqual(json.loads((self.folder / ".claude/settings.local.json").read_text()),
                         {"plansDirectory": ".claude/plans"})
        self.assertIn("calm-red-owl-2", cs.starred_of(cs.load_stars(here), "lab")["plans"])
        self.assertEqual(self.calls()[-1][1].split(" --remote ")[1],
                         "--move-plan calm-red-owl --profile .claude --if-exists keep")
        # listed there in its project, and back again
        group = next(g for g in remote.status("lab", tokens=False)["result"]["groups"] if g["chatProfile"] == ".claude")
        self.assertEqual([(p["slug"], p["inProject"], p["cwd"]) for p in group["plans"]],
                         [("calm-red-owl-2", True, str(self.folder)), ("calm-red-owl", True, str(self.folder))])
        back = remote.move_plan("lab", "calm-red-owl-2", ".claude", back=True)
        self.assertTrue(back["ok"], back)
        self.assertTrue((self.fake_home / ".claude/plans/calm-red-owl-2.md").is_file())

    def test_its_plans_are_listed(self):
        group = next(g for g in remote.status("lab", tokens=False)["result"]["groups"] if g["chatProfile"] == ".claude")
        (plan,) = group["plans"]
        self.assertEqual((plan["slug"], plan["title"], plan["chatId"], plan["openCommand"]),
                         ("calm-red-owl", "Calm plan", None, None))


ARGV_SSH = r'''#!/bin/bash
# Stand-in ssh that notes its whole command line; FAKE_LOGIN says how a login goes
printf '%s\n' "$(printf '%q ' "$@")" >> "$FAKE_SSH_LOG"
# whether it was started with SIGHUP ignored (bit 0 of SigIgn)
echo $(( 0x$(awk '/^SigIgn:/{print $2}' /proc/$$/status) & 1 )) > "$FAKE_SSH_LOG.hup"
if [ "$1" = -O ] || [[ " $* " == *" -O "* ]]; then exit 0; fi
[ "$FAKE_LOGIN" = ok ] && exit 0
echo "lab: Permission denied (publickey,password)." >&2
exit 255
'''


class KeepGoingThereTests(TwoAccountHost):
    """(2026-11-02) A host's chat that keeps going, end to end through the
    stand-in ssh: kept here, its status run there says how it stands
    (--kept-chats), the engine here queues its go-on from that answer, and
    the go-on resumes it there in the background."""

    def setUp(self):
        super().setUp()  # (as HostTaskTests: a folder Claude trusts there, and a claude that notes its arguments)
        self.folder = self.fake_home / "srv-app"
        self.folder.mkdir()
        (self.fake_home / ".claude/.claude.json").write_text(json.dumps({
            "oauthAccount": {"accountUuid": "r", "organizationType": "claude_max", "displayName": "Remote Me"},
            "projects": {str(self.folder): {"hasTrustDialogAccepted": True}}}))
        self.claude.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$HOME/claude-args\"\necho 'Started 1a2b3c4d'\n")

    def test_a_hosts_chat_a_limit_stopped_goes_on_there_from_here(self):
        import jump
        t = time.time() - 120
        stamp = lambda s: time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(s))
        # (the fixture's transcript of the chat: one file, as Claude keeps it; two of one id
        # would be found in the file system's order)
        self.chat.write_text("".join(json.dumps(e) + "\n" for e in [
            {"type": "user", "timestamp": stamp(t), "cwd": str(self.folder), "sessionId": self.CHAT,
             "message": {"role": "user", "content": "fix it"}},
            {"type": "assistant", "timestamp": stamp(t + 1), "isApiErrorMessage": True, "sessionId": self.CHAT,
             "message": {"id": "err", "role": "assistant", "stop_reason": "stop_sequence",
                         "content": [{"type": "text", "text": "You've hit your session limit"}]}}]))
        cache = cs.cache_dir(Path.home())
        cs.keep_chat(cache, ".claude", self.CHAT, "Fix it", str(self.folder), host="lab")
        # its status there: asked how it stands, and the answer is kept here
        answer = remote.status("lab", tokens=False)
        self.assertTrue(answer["ok"], answer)
        self.assertIn(f"--kept-chats {self.CHAT}/.claude", self.calls()[-1][1])
        self.assertEqual(answer["result"]["keptTurns"][self.CHAT]["turn"]["kind"], "limit")
        # the engine here (the copy that notifies): its go-on, for lab, from that answer
        cs.look_after_kept(Path.home(), cache, [], [], int(time.time() * 1000))
        (task,) = cs.load_queue(cache)
        self.assertEqual((task["host"], task["chat"], task["profile"], task["folder"]), ("lab", self.CHAT, ".claude", str(self.folder)))
        # it goes on there, in the background, when its time comes
        ok, message = jump.start_queued(Path.home(), [], task["id"])
        self.assertTrue(ok, message)
        args = (self.fake_home / "claude-args").read_text().split("\n")
        self.assertEqual(args[:3], ["--bg", "--resume", self.CHAT])
        (kept,) = cs.load_keep(cache)["chats"]
        self.assertIsNotNone(kept["wentOnAt"])
        self.assertEqual(cs.load_queue(cache), [])

    def test_a_hosts_chat_moved_to_the_background_takes_its_star_keep_going_and_go_on_along(self):
        # (2026-11-03) its go-on under the old id got a second one beside it, and its star couldn't be taken off
        new = "9a8b7c6d-0000-4000-8000-000000000003"
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(time.time() - 120))
        line = lambda sid: json.dumps({"type": "user", "uuid": "u1", "timestamp": stamp, "cwd": str(self.folder),
                                       "sessionId": sid, "session_id": self.CHAT,
                                       "message": {"role": "user", "content": "fix it"}}, separators=(",", ":")) + "\n"
        self.chat.write_text(line(self.CHAT))
        self.chat.with_name(f"{new}.jsonl").write_text(line(new))  # (Claude's copy of it, under its new id)
        cache = cs.cache_dir(Path.home())
        now = int(time.time() * 1000)
        cs.keep_chat(cache, ".claude", self.CHAT, "Fix it", str(self.folder), host="lab")
        cs.change_stars(cache, "chats", self.CHAT, "lab")
        cs.change_queue(cache, add=cs.queue_entry(".claude", str(self.folder), "", now + 3600_000, host="lab",
                                                  chat=self.CHAT, name="Fix it"))
        answer = remote.status("lab", tokens=False)
        self.assertEqual(answer["result"]["moved"], {self.CHAT: new})
        self.assertEqual(cs.starred_of(cs.load_stars(cache), "lab")["chats"], {new})
        self.assertEqual([k["chat"] for k in cs.load_keep(cache)["chats"]], [new])
        cs.look_after_kept(Path.home(), cache, [], [], now)
        self.assertEqual([(t["host"], t["chat"]) for t in cs.load_queue(cache)], [("lab", new)])


class UnreachedTests(TwoAccountHost):
    def test_an_answer_says_when_the_host_couldnt_be_reached(self):
        # (a queued go-on then starts once the host answers again: KeepGoingOnHostsTests)
        self.mode("unreachable")
        answer = remote.continue_chat("lab", ".claude", self.CHAT)
        self.assertEqual((answer["ok"], answer.get("reached")), (False, False), answer)
        self.mode("")
        answer = remote.continue_chat("lab", ".claude", "0a1b2c3d-4e5f-4061-8a7b-9c0d1e2f3a4b")  # (there, but no such chat)
        self.assertFalse(answer["ok"])
        self.assertNotIn("reached", answer)
        # (2026-11-03) nor one that took too long: it got there and may have gone on, so it isn't started again by itself
        from unittest import mock
        with mock.patch.object(remote, "ssh", side_effect=subprocess.TimeoutExpired("ssh", remote.RUN_TIMEOUT)):
            answer = remote.continue_chat("lab", ".claude", self.CHAT)
        self.assertEqual((answer["ok"], answer["message"]), (False, "lab didn't answer within 60 s"))
        self.assertNotIn("reached", answer)


class LoginTests(FakeSSH):
    """A host that wants a password: you type it into ssh itself, in a
    terminal, and the checks then share that login's connection."""

    def setUp(self):
        super().setUp()
        self.run_dir = Path(self.tmp.name) / "run"
        self.run_dir.mkdir(mode=0o700)
        self.saved["XDG_RUNTIME_DIR"] = os.environ.get("XDG_RUNTIME_DIR")
        self.saved["FAKE_LOGIN"] = os.environ.get("FAKE_LOGIN")
        os.environ["XDG_RUNTIME_DIR"] = str(self.run_dir)
        self.old_shown, remote.LOGIN_SHOWN = remote.LOGIN_SHOWN, 0
        self.hup_before = signal.getsignal(signal.SIGHUP)
        self.addCleanup(setattr, remote, "LOGIN_SHOWN", self.old_shown)

    def argv_ssh(self):
        (self.bin / "ssh").write_text(ARGV_SSH)

    def argvs(self):
        return [shlex.split(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_status_says_when_a_login_would_help(self):
        for mode, login in (("denied", True), ("hostkey", True), ("unreachable", False)):
            self.mode(mode)
            self.assertIs(remote.status("lab")["login"], login, mode)
        # (2026-11-03) not a container's engine saying no there: a login changes nothing, its error says why
        from unittest import mock
        denied = subprocess.CompletedProcess([], 1, "", "permission denied while trying to connect to the Docker daemon "
                                             "socket at unix:///var/run/docker.sock: connect: permission denied\n")
        with mock.patch.object(remote, "ssh", return_value=denied):
            self.assertIs(remote.status("docker:web@lab")["login"], False)

    def test_logged_in_while_the_connection_you_opened_is_there(self):
        self.assertIs(remote.status("lab")["loggedIn"], False)
        self.assertEqual(len(self.calls()), 1)  # no connection check without a login
        remote.login_marker("lab").write_text("")
        self.assertIs(remote.status("lab")["loggedIn"], True)

    def test_login_lets_ssh_ask_and_keeps_the_connection(self):
        self.argv_ssh()
        os.environ["FAKE_LOGIN"] = "ok"
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(remote.login_here("lab"), 0)
        (argv,) = self.argvs()
        # ssh takes an option's first value: the login's own come first
        self.assertEqual(argv[:8], ["-o", "ControlMaster=auto", "-o", "ControlPersist=30m",
                                    "-o", "ForwardAgent=no", "-o", "ForwardX11=no"])
        self.assertNotIn("BatchMode=yes", argv)  # it may ask for a password, a code, a host key
        self.assertIn(f"ControlPath={self.run_dir}/talpy-den-ssh/%C", argv)
        self.assertNotIn("StrictHostKeyChecking=no", " ".join(argv))
        self.assertEqual(argv[-3:], ["-T", "lab", "sh -c true"])
        self.assertTrue(remote.login_marker("lab").exists())
        self.assertEqual(remote.login_marker("lab").stat().st_mode & 0o777, 0o600)
        self.assertIn("never sees it", out.getvalue())
        # Through a jump host (ProxyJump), the connection to it is a child of
        # this ssh that stays in the window's session: started with SIGHUP
        # ignored, it outlives the window (checked with real OpenSSH)
        self.assertEqual(Path(str(self.log) + ".hup").read_text().strip(), "1")
        self.assertIs(signal.getsignal(signal.SIGHUP), self.hup_before)

    def test_a_failed_login_keeps_nothing(self):
        self.argv_ssh()
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(remote.login_here("lab"), 255)
        self.assertFalse(remote.login_marker("lab").exists())
        self.assertIn("didn't work", out.getvalue())

    def test_disconnect_closes_the_connection(self):
        self.argv_ssh()
        remote.login_marker("lab").write_text("")
        ok, message = remote.disconnect("lab")
        self.assertTrue(ok)
        self.assertEqual(message, "Disconnected from lab")
        ((*options, op, what, host),) = self.argvs()
        self.assertEqual((op, what, host), ("-O", "stop", "lab"))  # (terminals open over it go on)
        self.assertFalse(remote.login_marker("lab").exists())

    def test_login_opens_a_terminal_that_closes_once_in(self):
        import jump
        lines = []
        real = jump.open_terminal
        jump.open_terminal = lambda cwd, line: lines.append(line) or True
        self.addCleanup(setattr, jump, "open_terminal", real)
        self.assertEqual(remote.login("lab"), (True, "Log in to lab in the terminal"))
        (line,) = lines
        self.assertTrue(line.endswith(" --login-here lab && exit"), line)
        self.assertIn(" -I ", line)
        with self.assertRaises(ValueError):
            remote.login("-oProxyCommand=evil")


if __name__ == "__main__":
    unittest.main()
