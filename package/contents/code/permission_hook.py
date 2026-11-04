#!/usr/bin/env python3
"""Claude Code's PermissionRequest hook for Talpy Den, so a
permission prompt can be answered from Talpy Den (Allow once, Always
allow, Deny with a note) as well as in the chat; and Claude's questions
(AskUserQuestion asks for a permission too: the answers go back in it).

Claude runs it whenever a chat asks for a permission, side by side with its
own dialog: whichever is answered first counts. It writes the request to
~/.cache/talpy-den/permissions/<id>.json and waits for Talpy Den's
answer (<id>.answer.json, written by pane.py --answer). It ends without a
word, so the dialog alone decides, once the chat stops waiting (you
answered it there), when its Claude is gone, or when no dialog shows a few
seconds after it started (a Claude that waits for hooks before it asks).

It is copied to ~/.local/share/talpy-den/permission-hook.py and named
in each Claude profile's settings.json by pane.py --relay on (the
setting "Answer permission prompts from Talpy Den"); --relay off
takes it out again. Standard library only, and Python 3.7 (SSH hosts).
"""
import json
import os
import signal
import sys
import time

# This file's version: a status check brings an older copy of it in
# ~/.local/share/talpy-den up to date (talpy_den.refresh_hooks)
HOOK_REVISION = 2
POLL_S = 0.3
STATE_EVERY_S = 1.0
NO_DIALOG_S = 5.0  # a chat that isn't waiting by then asks only after its hooks: let it
LONGEST_S = 23 * 3600  # (the settings give it 24 h; it ends before Claude would cut it off)
# Shells that may stand between Claude and the hook: Claude runs a hook's
# command with sh -c, and dash (Debian's and Ubuntu's sh) stays as the
# command's parent unless the command starts with exec (older entries in
# settings.json don't)
SHELLS = frozenset(("sh", "dash", "bash", "zsh", "ksh", "ksh93", "mksh", "lksh", "pdksh", "ash", "busybox", "yash",
                    "posh"))


def parent_of(pid):
    """(parent pid, command name) of a process, from Linux's /proc, or None."""
    try:
        with open("/proc/%d/stat" % pid, "rb") as f:
            stat = f.read().decode("utf-8", "replace")
        end = stat.rindex(")")  # (the name may have spaces and parentheses)
        return int(stat[end + 2:].split()[1]), stat[stat.index("(") + 1:end]
    except (OSError, ValueError, IndexError):
        return None


def claude_pid():
    """The Claude process the hook runs for: its parent, or, when that's the
    shell Claude ran the command with, the shell's parent. Without /proc
    (not Linux), its parent."""
    pid = os.getppid()
    for _ in range(4):
        found = parent_of(pid)
        if found is None or found[1] not in SHELLS or found[0] <= 1:
            break
        pid = found[0]
    return pid


def cache_root():
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "talpy-den", "permissions")


def session_file(pid):
    """The session file of the Claude process pid (its sessions/<pid>.json), or None."""
    home = os.path.expanduser("~")
    folders = [os.environ.get("CLAUDE_CONFIG_DIR") or "", os.path.join(home, ".claude")]
    try:
        folders += sorted(os.path.join(home, n) for n in os.listdir(home) if n.startswith(".claude"))
    except OSError:
        pass
    for folder in folders:
        path = os.path.join(folder, "sessions", "%d.json" % pid) if folder else ""
        if path and os.path.isfile(path):
            return path
    return None


def session_status(path):
    """The chat's status in its session file ("waiting", "busy", …), or None."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data.get("status") if isinstance(data, dict) else None


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def write_private(path, data):
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def remove(*paths):
    for path in paths:
        try:
            os.unlink(path)
        except OSError:
            pass


def main():
    try:
        request = json.load(sys.stdin)
    except (ValueError, RecursionError):
        return 0
    if not isinstance(request, dict):
        return 0
    parent, claude = os.getppid(), claude_pid()
    folder = cache_root()
    try:
        os.makedirs(folder, mode=0o700, exist_ok=True)
    except OSError:
        return 0
    rid = "%d-%s" % (int(time.time() * 1000), os.urandom(4).hex())
    path = os.path.join(folder, rid + ".json")
    answer_path = os.path.join(folder, rid + ".answer.json")

    def leave(*_):
        remove(path, answer_path, path + ".tmp")
        sys.exit(0)

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, leave)
    started = time.time()
    try:
        write_private(path, {
            "id": rid, "at": int(started * 1000), "pid": claude, "hookPid": os.getpid(),
            "sessionId": request.get("session_id"), "transcript": request.get("transcript_path"),
            "cwd": request.get("cwd"), "mode": request.get("permission_mode"),
            "tool": request.get("tool_name"), "input": request.get("tool_input"),
            "suggestions": request.get("permission_suggestions") or [],
            # the tool call it's about, if Claude names it (2.1.311 doesn't)
            "toolUse": request.get("tool_use_id") if isinstance(request.get("tool_use_id"), str) else None,
        })
    except OSError:
        return 0
    session = session_file(claude)
    seen_waiting, checked = False, 0.0
    while time.time() - started < LONGEST_S:
        if os.path.exists(answer_path):
            try:
                with open(answer_path, encoding="utf-8") as f:
                    decision = json.load(f)
            except (OSError, ValueError):
                decision = None
            if isinstance(decision, dict) and decision.get("behavior") in ("allow", "deny"):
                sys.stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": "PermissionRequest",
                                                                     "decision": decision}}))
                sys.stdout.flush()
                leave()
            remove(answer_path)
        now = time.time()
        if now - checked >= STATE_EVERY_S:
            checked = now
            if not alive(claude) or os.getppid() != parent:
                leave()
            status = session_status(session) if session else None
            if status == "waiting":
                seen_waiting = True
            elif seen_waiting or now - started >= NO_DIALOG_S:
                leave()  # answered in the chat (or it never showed a dialog)
        time.sleep(POLL_S)
    leave()


if __name__ == "__main__":
    sys.exit(main())
