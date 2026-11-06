"""How full a chat's context is and how Claude's turn has gone so far, for
Talpy Chat's header and working line (pane.py --conversation "context" and
"turn"; a module of its own: compiled once and kept, as replies.py is, where
pane.py, run as a script, is compiled at every call, and read only for a
chat's conversation, not with talpy_den.py by everything else):

- context_left: from the token counts of Claude's last message, against its
  model's window, and how much is left till Claude compacts the chat on its
  own (auto-compact), as Claude Code counts it;
- TurnSoFar: Claude's turn so far, followed entry by entry in pane.py's
  conversation_items (beside replies.TurnEnd: how it ended);
- turn_before: the start of a turn longer than what Talpy Chat reads of the
  chat, found further back once and kept.

Python 3.7+ and the standard library only (the SSH host backend too).
"""
import json
import os
import re
import time

import talpy_den as cs

# ---------------------------------------------------------------- context left
# (talpy_den's: the popup's rows say it too, from their status lines)
CONTEXT_1M, CONTEXT_WINDOWS, COMPACT_ROOM, COMPACT_CLOSE = cs.CONTEXT_1M, cs.CONTEXT_WINDOWS, cs.COMPACT_ROOM, cs.COMPACT_CLOSE
model_key, context_window, context_left = cs.model_key, cs.context_window, cs.context_left


def status_window(home, profile, chat_id, model):
    """The context window a chat's newest status-line snapshot gives
    (context_window_size, or 1M for a model named with [1m]), when it's of
    the model of Claude's last message; else None."""
    for _, path in cs.snapshot_paths(cs.cache_dir(home) / "statusline", profile, [chat_id]):
        snap = cs.read_json(path)
        part = lambda key: snap.get(key) if isinstance(snap, dict) and isinstance(snap.get(key), dict) else {}
        named, size = part("model").get("id"), part("context_window").get("context_window_size")
        if not isinstance(named, str) or not isinstance(model, str) or named.split("[")[0] != model.split("[")[0]:
            return None
        if isinstance(size, int) and not isinstance(size, bool) and size > 0:
            return size
        return CONTEXT_1M if "[1m]" in named.lower() else None
    return None


# ---------------------------------------------------------------- the turn so far

class TurnSoFar:
    """Claude's turn so far, followed entry by entry (pane.py's
    conversation_items), beside how it ends (end: replies.TurnEnd, or None
    when nobody asks): when your prompt that started it came (started, ms:
    None when it isn't in what was read, 0 when it doesn't say), the tool
    calls Claude made since (steps: conversation_items counts them as it
    lists them), whether it's over (the transcript says so), and the token
    counts of Claude's last message of its own (usage, on model) for how
    full its context is. Per entry only what's needed to tell them at the
    end (last, mine): it's on every read of a chat."""
    __slots__ = ("end", "started", "steps", "last", "mine")

    def __init__(self, end=None):
        # last: what its last entry says: None (it goes on: a prompt, a tool result), True (an
        # interruption, an API error, Claude Code's stand-in reply), or Claude's message (its stop
        # reason); mine: Claude's last message of its own
        self.end, self.started, self.steps, self.last, self.mine = end, None, 0, None, None

    def prompt(self, at=None):
        self.started, self.steps, self.last = at or 0, 0, None
        if self.end is not None:
            self.end.prompt()

    def tool_result(self, error):
        self.last = None
        if self.end is not None:
            self.end.tool_result(error)

    def interrupted(self):
        self.last = True
        if self.end is not None:
            self.end.interrupted()

    def compacted(self):
        self.mine = None   # (what's left of it: known once Claude says something again)

    def assistant(self, e, msg, blocks):
        if self.end is not None:
            self.end.assistant(e, msg, blocks)
        if e.get("isApiErrorMessage") or msg.get("model") == "<synthetic>":
            self.last = True
        else:
            self.last = self.mine = msg

    @property
    def over(self):
        last = self.last
        if last is None or last is True:
            return last is True
        content = last.get("content")
        return last.get("stop_reason") in ("end_turn", "stop_sequence") and not (
            isinstance(content, list) and any(isinstance(c, dict) and c.get("type") == "tool_use" for c in content))

    @property
    def usage(self):
        usage = self.mine.get("usage") if self.mine is not None else None
        return usage if isinstance(usage, dict) else None

    @property
    def model(self):
        return self.mine.get("model") if self.mine is not None else None

    def now(self, path, start, kept=None):
        """{"startedAt", "steps"} of the turn going on, None when it's over or
        its start can't be known. start: where the lines read begin in the
        transcript at path (a line's start; 0: all of it was read); a prompt
        before is found there (turn_before)."""
        if self.over:
            return None
        started, steps = self.started, self.steps
        if started is None and start:
            before = turn_before(path, start, kept)
            started, steps = (before[0], before[1] + steps) if before else (None, steps)
        return {"startedAt": started, "steps": steps} if started else None


# ---------------------------------------------------------------- a long turn's start

TOOL_CALL_LINE = rb'"type":\s*"tool_use"'
TURN_CHUNK = 1 << 20
TURN_BACK_MAX = 64 << 20   # (as far back as Talpy Chat reads a chat: pane.py PANE_TAIL_MAX)
KEPT_TURN_DAYS = 30


def turn_prompt_at(line):
    """When the prompt of yours on this transcript line came (ms, 0 if it
    doesn't say), if it's one that starts Claude's turn (or a command that's
    a prompt: yours, a skill); else None."""
    if not cs.USER_LINE.search(line) or b'"tool_use_id"' in line:
        return None
    try:
        e = json.loads(line)
    except (ValueError, RecursionError):
        return None
    if not isinstance(e, dict) or e.get("type") != "user" or e.get("isMeta") or e.get("isSidechain"):
        return None
    if cs.human_prompt(e) is None and not cs.message_text(cs.blocks_of(e)[0]).lstrip().startswith("<command-message>"):
        return None
    return cs.to_ms(e.get("timestamp")) or 0


def tool_calls(line):
    """How many tool calls of Claude's own (not a subagent's) a transcript line has."""
    if not re.search(TOOL_CALL_LINE, line):
        return 0
    try:
        e = json.loads(line)
    except (ValueError, RecursionError):
        return 0
    if not isinstance(e, dict) or e.get("type") != "assistant" or e.get("isSidechain"):
        return 0
    return sum(1 for c in cs.blocks_of(e)[1] if c.get("type") == "tool_use")


def turn_forward(f, start, end, found):
    """found (offset, at, steps) carried through the whole lines of f from
    start to end: a prompt of yours starts again from it, tool calls add up."""
    f.seek(start)
    offset = start
    for line in f.read(end - start).split(b"\n"):
        at = turn_prompt_at(line) if line else None
        found = (offset, at, 0) if at is not None else (found[0], found[1], found[2] + tool_calls(line))
        offset += len(line) + 1
    return found


def turn_backward(f, end):
    """(offset, at, steps) of the last prompt of yours before end in f, and
    the tool calls after it; None when there's none TURN_BACK_MAX before."""
    pos, rest, after = end, b"", 0
    while pos > 0 and end - pos < TURN_BACK_MAX:
        start = max(0, pos - TURN_CHUNK)
        f.seek(start)
        lines = (f.read(pos - start) + rest).split(b"\n")
        offsets, o = [], start
        for line in lines:
            offsets.append(o)
            o += len(line) + 1
        rest = lines[0] if start > 0 else b""   # (cut: whole with the bytes before it)
        for i in range(len(lines) - 1, 0 if start > 0 else -1, -1):
            at = turn_prompt_at(lines[i]) if lines[i] else None
            if at is not None:
                return offsets[i], at, after
            after += tool_calls(lines[i])
        pos = start
    return None


def turn_before(path, end, kept=None):
    """(started, steps) of the turn going on at byte end of a transcript (a
    line's start): when the prompt of yours that started it came (ms) and
    Claude's tool calls from there to end; None when there's no prompt of
    yours in the TURN_BACK_MAX bytes before. kept: a file it's kept in
    (yours alone), so the next read looks only at what was written since."""
    keys = ("offset", "at", "upto", "steps")
    try:
        with open(path, "rb") as f:
            ino = os.fstat(f.fileno()).st_ino
            was = cs.read_json(kept, 4096) if kept is not None else None
            if not (isinstance(was, dict) and was.get("ino") == ino
                    and all(isinstance(was.get(k), int) and not isinstance(was.get(k), bool) for k in keys)
                    and was["offset"] < end and was["offset"] <= was["upto"]):
                was = None
            if was is not None:   # (still its prompt there: the transcript wasn't written again)
                f.seek(was["offset"])
                if turn_prompt_at(f.readline().rstrip(b"\n")) != was["at"]:
                    was = None
            if was is None:
                found = turn_backward(f, end)
            elif was["upto"] <= end:
                found = turn_forward(f, was["upto"], end, (was["offset"], was["at"], was["steps"]))
            else:   # (read from further back this time)
                found = turn_forward(f, was["offset"], end, (was["offset"], was["at"], 0))
    except OSError:
        return None
    if found is None:
        return None
    offset, at, steps = found
    if kept is not None and (was is None or [was[k] for k in keys] != [offset, at, end, steps]):
        try:
            if was is None:
                prune_kept(kept.parent, KEPT_TURN_DAYS)
            cs.private_dir(kept.parent)
            cs.write_json_atomic(kept, {"ino": ino, "offset": offset, "at": at, "upto": end, "steps": steps}, private=True)
        except OSError:
            pass
    return at, steps


def prune_kept(folder, days):
    """Remove the files in folder not written for days (what's kept of chats long done)."""
    cut = time.time() - days * 86400
    try:
        with os.scandir(str(folder)) as it:
            for f in it:
                if f.is_file(follow_symlinks=False) and f.stat(follow_symlinks=False).st_mtime < cut:
                    os.unlink(f.path)
    except OSError:
        pass
