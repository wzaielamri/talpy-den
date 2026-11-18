"""The shells a chat runs in the background now, for Talpy Chat's working
line (pane.py --conversation "shells"): a Bash call Claude ran in the
background (run_in_background), or one it moved there after its timeout.

Which of them run now: Claude's own list, where there is one, a background
session's job record (state.json "fan": {"id", "kind": "shell", "label"
(cut), "startedAt"}, gone once it ends; it also has a command that runs long
in the foreground, and a subagent's shells, which aren't listed). What each
is, and which a chat in a terminal runs: the transcript. A start is a tool
result whose toolUseResult has
"backgroundTaskId" (the Bash call it answers: the command and its
description); an end is the task notification Claude queues as the shell
ends (a queue-operation, the attachment or a prompt: "<task-notification>
<task-id>ID</task-id>…", written at once, mid-turn too) or a TaskStop (or the
older KillShell) result, which gets none. A shell the transcript leaves open
from before the session's process started died with the one before.

A transcript is read once: what's read is kept in the cache folder's shells/
(where the whole lines read end, and the shells still open there), so each
read after that only looks at what was written since (about 1 ms; a 60 MB
transcript read whole takes 20-60 ms). The words are found with mmap's find
and only the lines they're on are parsed."""

import json
import mmap
import os

import talpy_den as td

START = b'"backgroundTaskId":"'
NOTE = b"<task-id>"
STOPS = (b"Successfully stopped task: ", b"Successfully killed shell: ")
KEPT_VERSION = 1
COMMAND_MAX = 20_000   # characters of a command kept (and shown, folded, on the Steps tab)


def line_at(mm, pos):
    """The transcript line pos is on, parsed (None: not JSON), and where it starts."""
    start = mm.rfind(b"\n", 0, pos) + 1
    end = mm.find(b"\n", pos)
    try:
        return json.loads(mm[start:end if end >= 0 else len(mm)]), start
    except ValueError:
        return None, start


def started(mm, pos):
    """(id, {"command", "description", "started"}) of the start whose
    "backgroundTaskId" is at pos, or None (the words in a text: not one)."""
    e, start = line_at(mm, pos)
    result = e.get("toolUseResult") if isinstance(e, dict) else None
    shell = result.get("backgroundTaskId") if isinstance(result, dict) else None
    if not isinstance(shell, str) or not shell:
        return None
    content = (e.get("message") or {}).get("content") if isinstance(e.get("message"), dict) else None
    use = next((c.get("tool_use_id") for c in content if isinstance(c, dict) and c.get("type") == "tool_result")
               if isinstance(content, list) else (), None)
    command, description = "", ""
    if isinstance(use, str) and use:
        at = mm.rfind(b'"id":"' + use.encode() + b'"', 0, start)
        call, _ = line_at(mm, at) if at >= 0 else (None, 0)
        blocks = (call.get("message") or {}).get("content") if isinstance(call, dict) and isinstance(call.get("message"), dict) else None
        for b in blocks if isinstance(blocks, list) else ():
            if isinstance(b, dict) and b.get("id") == use and isinstance(b.get("input"), dict):
                command = b["input"].get("command") if isinstance(b["input"].get("command"), str) else ""
                description = b["input"].get("description") if isinstance(b["input"].get("description"), str) else ""
    return shell, {"command": command[:COMMAND_MAX], "description": description[:300],
                   "started": td.to_ms(e.get("timestamp")) or 0}


def ended(mm, pos, stop):
    """The id of the shell an end at pos says is over (stop: a TaskStop's or
    KillShell's result, else a task notification), or None."""
    e, _ = line_at(mm, pos)
    if not isinstance(e, dict):
        return None
    if stop:
        result = e.get("toolUseResult")
        shell = (result.get("task_id") or result.get("shell_id")) if isinstance(result, dict) else None
        return shell if isinstance(shell, str) else None
    # (Claude's own note: queued, taken in as an attachment, or a prompt of its text; not a
    # tool's output that has the words in it)
    note = e.get("content") if e.get("type") == "queue-operation" else \
        (e.get("attachment") or {}).get("prompt") if e.get("type") == "attachment" and isinstance(e.get("attachment"), dict) else \
        (e.get("message") or {}).get("content") if e.get("type") == "user" and isinstance(e.get("message"), dict) else None
    if not isinstance(note, str) or not note.lstrip().startswith("<task-notification>"):
        return None
    at = note.find("<task-id>")
    close = note.find("</task-id>", at)
    return note[at + 9:close].strip() if at >= 0 and close > at else None


def named(mm, pos, shells):
    """Does the <task-id> at pos name one of shells (before its line is parsed)?"""
    close = mm.find(b"</task-id>", pos, pos + 200)
    return close > pos and mm[pos + len(NOTE):close].decode("utf-8", "replace").strip() in shells


def find_all(mm, word, start, end):
    at = mm.find(word, start, end)
    while at >= 0:
        yield at
        at = mm.find(word, at + len(word), end)


def open_shells(path, kept_path):
    """{id: {"command", "description", "started"}} of the shells the
    transcript at path leaves open, read from where kept_path says the last
    read ended."""
    try:
        st = os.stat(path)
    except OSError:
        return {}
    kept = td.read_json(kept_path)
    if not isinstance(kept, dict) or kept.get("v") != KEPT_VERSION or kept.get("ino") != st.st_ino \
            or not isinstance(kept.get("at"), int) or kept["at"] > st.st_size or not isinstance(kept.get("open"), dict):
        kept = {"v": KEPT_VERSION, "ino": st.st_ino, "at": 0, "open": {}}   # (new, or another file now: from its start)
    shells, at = dict(kept["open"]), kept["at"]
    if st.st_size <= at:
        return shells
    try:
        with open(path, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            end = mm.rfind(b"\n", at) + 1   # (whole lines: the last one may be half written)
            if end <= at:
                return shells
            events = [(p, "start") for p in find_all(mm, START, at, end)]
            since = at if shells else events[0][0] if events else end   # (ends: only of a shell open, or started)
            events += [(p, "note") for p in find_all(mm, NOTE, since, end)] \
                + [(p, "stop") for word in STOPS for p in find_all(mm, word, since, end)]
            for pos, kind in sorted(events):   # (in the order they were written)
                if kind == "start":
                    found = started(mm, pos)
                    if found:
                        shells[found[0]] = found[1]
                elif shells and (kind == "stop" or named(mm, pos, shells)):   # (parsed only when it may end one)
                    shells.pop(ended(mm, pos, kind == "stop"), None)
    except (OSError, ValueError):
        return shells
    try:
        td.write_json_atomic(kept_path, {"v": KEPT_VERSION, "ino": st.st_ino, "at": end, "open": shells}, private=True)
    except OSError:
        pass
    return shells


def live_entry(profile, chat_id):
    """The live session process of a chat on this profile, or None."""
    return next((e for e, _, _ in td.live_entries_all([profile]) if e.get("sessionId") == chat_id), None)


def running(home, profile, chat_id, path, record):
    """[{"id", "command", "description", "started" (ms)}] of the shells a
    chat runs in the background now, oldest first. record: its job's record
    (chatpick.job_record), None if it has none."""
    shells = open_shells(path, td.cache_dir(home) / "shells" / f"{chat_id}.json")
    if not shells:
        return []
    fan = record.get("fan") if isinstance(record, dict) else None
    if isinstance(fan, list):   # (a background session's own list: those of them that run now)
        # (it has a command that runs long in the foreground too, and a subagent's shells, which
        # the transcript doesn't: only the chat's own background shells are listed)
        now = {f["id"] for f in fan if isinstance(f, dict) and f.get("kind") == "shell" and not f.get("doneAt")
               and isinstance(f.get("id"), str)}
        return sorted(({"id": k, **v} for k, v in shells.items() if k in now), key=lambda s: s["started"])
    entry = live_entry(profile, chat_id)
    since = td.to_ms(entry.get("startedAt")) or 0 if entry else None
    if since is None:
        return []   # (no process: none of them runs)
    return sorted(({"id": k, **v} for k, v in shells.items() if v.get("started", 0) >= since - 1000),
                  key=lambda s: s["started"])
