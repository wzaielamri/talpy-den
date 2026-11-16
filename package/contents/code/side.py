"""Side questions for Talpy Chat (pane.py --side-question): a question about a
chat answered beside it, the way Claude's /btw answers one, without adding
to the chat or stopping what it does.

Claude Code takes a side question as a control request of its stream-json
mode (subtype "side_question": {question, history}, answered with
{response, synthetic}; live-checked on Claude Code 2.1.325). It's put to a
copy of the chat that's never written down:

    claude -p --resume ID --fork-session --no-session-persistence
           --input-format stream-json --output-format stream-json --verbose

which reads the chat as its transcript has it now (a turn under way too)
and answers with Claude's own side-question prompt: no tools, one answer,
earlier answers (history) for follow-ups. Hooks are off in it
(disableAllHooks: no SessionStart of a chat nobody sees).

The cost: a copy starts its request the way it was read, so it reuses the
prompt cache of the chat only where the two start the same (a chat run with
claude -p, measured: all of it). A background chat's prompt names its own
job, so its copy writes the chat into the cache once; questions after that,
within the cache's life, read it from there (a resumed chat keeps the
context it started with: the same start every time).

A module of its own (pane.py, run as a script, is compiled at every call).
Python 3.7+ and the standard library only (the SSH host backend too).
"""
import json
import os
import select
import subprocess
import time

import talpy_den as cs

REQUEST_ID = "talpy-side"
NO_HOOKS = '{"disableAllHooks":true}'
STOP_WAIT_S = 3
LINE_MAX = 64 << 20   # (an answer is one line: SIDE_ANSWER characters, written as JSON escapes, and room)


def command(claude, chat_id, model):
    """claude's words for a copy of the chat that answers side questions."""
    return [claude, "-p", "--resume", chat_id, "--fork-session", "--no-session-persistence",
            "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
            *(["--model", model] if model else []), "--settings", NO_HOOKS]


def request(question, history):
    return {"type": "control_request", "request_id": REQUEST_ID,
            "request": {"subtype": "side_question", "question": question, "history": list(history)}}


def environment(profile, home, claude):
    """claude's environment for the profile, as start_background's (no session of the caller's)."""
    env = {k: v for k, v in os.environ.items() if k not in cs.SESSION_ENV and k != cs.NO_AGENT_VIEW}
    value = cs.config_dir_value(profile, home)
    if value is None:
        env.pop("CLAUDE_CONFIG_DIR", None)
    else:
        env["CLAUDE_CONFIG_DIR"] = value
    folder_bin = os.path.dirname(claude)
    if folder_bin and os.path.isfile(os.path.join(folder_bin, "node")):
        env["PATH"] = folder_bin + os.pathsep + env.get("PATH", "")
    return env


def read_answer(proc, deadline, clock=time.monotonic):
    """The control response to our request, from claude's stdout: (answer
    dict, None, "") or (None, why not, the end of what it wrote on stderr).
    Reads line by line till the deadline; stderr is read as it comes (a
    full pipe would stop claude)."""
    buf, err = b"", b""
    out_fd, err_fd = proc.stdout.fileno(), proc.stderr.fileno()
    fds = [out_fd, err_fd]
    while True:
        left = deadline - clock()
        if left <= 0:
            return None, "timeout", err.decode("utf-8", "replace")
        ready, _, _ = select.select(fds, [], [], min(left, 1.0))
        if err_fd in ready:
            chunk = os.read(err_fd, 1 << 16)
            if chunk:
                err = (err + chunk)[-(1 << 16):]
            else:
                fds.remove(err_fd)
        if out_fd not in ready:
            continue
        chunk = os.read(out_fd, 1 << 16)
        if not chunk:
            if err_fd in fds:   # (what it said as it ended)
                try:
                    proc.wait(STOP_WAIT_S)
                except subprocess.TimeoutExpired:
                    pass
                while select.select([err_fd], [], [], 0)[0]:
                    more = os.read(err_fd, 1 << 16)
                    if not more:
                        break
                    err = (err + more)[-(1 << 16):]
            return None, "ended", err.decode("utf-8", "replace")
        buf += chunk
        if len(buf) > LINE_MAX:
            return None, "too long", err.decode("utf-8", "replace")
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            try:
                msg = json.loads(line.decode("utf-8", "replace"))
            except ValueError:
                continue
            if isinstance(msg, dict) and msg.get("type") == "control_response":
                response = msg.get("response") if isinstance(msg.get("response"), dict) else {}
                if response.get("request_id") == REQUEST_ID:
                    return response, None, ""


def stop(proc):
    """Let the copy go: its stdin closed (it ends), else ended."""
    try:
        proc.stdin.close()
    except OSError:
        pass
    try:
        proc.wait(STOP_WAIT_S)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(STOP_WAIT_S)
        except subprocess.TimeoutExpired:
            pass


def last_line(text):
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    return lines[-1][:300] if lines else ""


def ask(home, extra_dirs, profile_key, chat_id, question, pick="", history=(), claude=None, wait=None):
    """Put a side question to a copy of the chat: {"ok", "answer", "model",
    "synthetic"} or {"ok": False, "message"}. pick: "" (the chat's own
    model, cs.chat_model) or one of cs.SIDE_PICKS. A chat Claude moved to
    the background goes on under its new id (cs.continuation): asked there."""
    question = (question or "").strip()
    if not question:
        return {"ok": False, "message": "Write your question first"}
    pick = cs.side_pick(pick)
    if pick is None:
        return {"ok": False, "message": "Not a model side questions can use"}
    if not cs.valid_id(chat_id):
        return {"ok": False, "message": f"Not a chat: {chat_id}"}
    profiles = cs.discover_profiles(home, extra_dirs)
    ordered = sorted(profiles, key=lambda p: not (profile_key and cs.matches_profile(p, profile_key)))
    profile = next((p for p in ordered if cs.transcript_path(p, chat_id) is not None), None)
    if profile is None:
        return {"ok": False, "missing": True, "message": "That chat isn't there any more"}
    now_id = cs.continuation(home, extra_dirs, profile.key, chat_id)
    if now_id != chat_id:
        moved = next((p for p in [profile] + profiles if cs.transcript_path(p, now_id) is not None), None)
        if moved is not None:
            profile, chat_id = moved, now_id
    path = cs.transcript_path(profile, chat_id)
    model = pick or cs.chat_model(home, profile, chat_id, path)[0] or ""
    folder = cs.chat_folder(path) or str(home)
    if not os.path.isdir(folder):
        folder = str(home)
    claude = claude or cs.find_claude(home, ask_shell=True)
    try:
        proc = subprocess.Popen(command(claude, chat_id, model), cwd=folder, env=environment(profile, home, claude),
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                start_new_session=True)
    except OSError as exc:
        return {"ok": False, "message": f"Couldn't run claude: {exc}"}
    try:
        try:
            proc.stdin.write((json.dumps(request(question, history)) + "\n").encode("utf-8"))
            proc.stdin.flush()
        except OSError:
            pass   # (it ended already: what it said is read below)
        wait = cs.SIDE_WAIT_S if wait is None else wait
        response, why, err = read_answer(proc, time.monotonic() + wait)
    finally:
        stop(proc)
        proc.stderr.close()
        proc.stdout.close()
    err = last_line(err)
    if response is None:
        if why == "timeout":
            return {"ok": False, "message": f"No answer within {wait // 60} minutes" if wait >= 120
                    else f"No answer within {wait} s"}
        return {"ok": False, "message": err or "Claude ended without answering"}
    if response.get("subtype") != "success":
        said = response.get("error")
        return {"ok": False, "message": said if isinstance(said, str) and said else "Claude couldn't answer it"}
    body = response.get("response") if isinstance(response.get("response"), dict) else {}
    answer = body.get("response")
    if not isinstance(answer, str) or not answer.strip():
        return {"ok": False, "message": "Claude gave no answer"}
    return {"ok": True, "answer": answer, "model": model, "synthetic": body.get("synthetic") is True}
