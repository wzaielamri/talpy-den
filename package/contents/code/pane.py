#!/usr/bin/env python3
"""The chat pane of Talpy Den: one chat's conversation, a reply to it,
its permission prompt and its review.

    python3 -I pane.py ACTION [--host HOST] [--config-dir DIR]... [--remote] [--pretty]

  --conversation CHAT [--profile P] [--limit N] [--if-changed STAMP [--wait S]] [--suggest]
        the chat as the pane shows it: your prompts, Claude's replies
        (markdown), each tool call as one line with how it went, and notes
        (a usage limit, an interruption); the newest N items. STAMP: the
        "stamp" of the last answer; while the transcript is as it was then,
        the answer is only {"ok", "unchanged"}. --wait: while it's as it was,
        wait up to S seconds (at most WAIT_MAX_S) for it to change, and answer
        the moment it does (the pane's watcher: what Claude writes shows at
        once, not at the next look). Not on an SSH host (it's left out there).
        --suggest (Suggest replies): how its last turn ended, "ended" and
        "over", and the question it ends with as chips, "asks" (asks_of)
  --replies CHAT [--profile P]
        your usual replies for the chat (usual_replies): {"ok", "chips": {how
        a turn ended: [replies]}, "ranked": [replies, to complete what you
        type]}; CHAT "-" with --cwd FOLDER --profile P: a new chat's
  --hide-reply TEXT [--off]
        don't suggest TEXT again (--off: do again; "-" --off: all of them)
  --send CHAT --profile P --text T [--session ID] [--how auto|background|copy|enter] [--after-turn] [--name N]
        your message to the chat, the way it can take one (send) (or
        --text-file F: a long one in F, a text-*.txt of the cache folder,
        removed once read); typed into its tmux pane; put in the input of its VS Code tab; or
        Claude goes on with it in the background (claude --bg --resume),
        after a background session that has it stops. A chat in a terminal
        that takes no text from outside asks first (how background: it goes
        on in the background; copy: the message goes to the clipboard).
        How enter (Enter in the pane): auto, but a terminal that takes no
        text gets the copy (Claude there never quits on an Enter).
        --after-turn: queued, it's sent once the chat's turn ends.
  --start PROFILE --cwd FOLDER --text T [--model M] [--effort E] [--permission-mode MODE] [--plan SLUG [--plan-profile P]]
        a new chat Talpy Chat starts, with T as its first message (or
        --text-file F): in the background on that profile, in FOLDER (claude
        --bg), with the permission hook for it alone unless the profile's
        settings have it (--settings: Talpy Chat answers what it asks), in a
        systemd scope of its own. {"ok", "message", "how": "background",
        "id": its job's short id, "chat": its chat id, "profileDir"}
  --interrupt CHAT [--session ID] [--profile P]
        Talpy Chat's Stop: what Claude does now in a chat at work stops, as
        Esc in its terminal: Ctrl+C in its tmux pane, or Esc into a
        background chat through Claude's background service. The chat stays
        where it runs and takes your next message
  --answer REQUEST --decision allow|always|deny|answer|approve|approve-edits|keep [--note T] [--answers JSON]
        answer a permission request the hook relayed (permission_hook.py);
        Claude's questions (AskUserQuestion): answer, with JSON {question:
        [chosen labels, or what you typed]}, or deny (decline, with a note).
        A request that's gone (answered in the chat), or one the chat asked
        again after: "changed": true
  --keys CHAT --decision allow|always|deny [--note T] [--profile P] [--expect TOOL_USE]
        answer a permission prompt of a chat in tmux with its keys (CHAT: its
        session id). --expect: the id of the tool call the prompt you answered
        is about (its row's permission "toolUse"); when the chat asks about
        another one by the time a key would be pressed, or about none, no key
        is pressed: {"ok": false, "message": "It asks something else now",
        "changed": true}
  --review CHAT [--profile P]
        what the chat changed: each file with its added and removed lines
        and a diff (against the file before the chat, from Claude's own
        backups), whether tests ran after its last edit and how they went,
        and a commit message from its name and recap
  --undo CHAT [--file PATH]... [--profile P]
        put the files back as they were before the chat (all, or those)
  --commit CHAT --message M [--file PATH]... [--profile P]
        commit only the files the chat changed (or those), in each git
        repository they are in
  --reviewed CHAT [--off]
        mark the chat reviewed (until it changes files again), or not
  --relay on|off|status
        the permission hook in each Claude profile's settings.json
  --live on|off|status
        live mode: the live hook (live_hook.py) in each Claude profile's
        settings.json, so the widget shows each step of each chat as it happens
  --complete CHAT [--profile P]
        what the reply box offers as you type: / commands (Claude's own, yours
        and the project's) and skills, the project's files for @, and your
        past prompts in its folder (newest first) for ↑. CHAT "-" with
        --cwd FOLDER --profile P: a new chat's, in that folder
  --terminal-font
        your terminal's font family, as the pane shows the conversation in
        it: {"ok", "family" ("" if it names none), "terminal"} (terminal_font)
  --oldest allow|deny [--osd]
        answer the oldest prompt a chat waits on (one the hook relayed; a plan:
        approve it, or keep planning), for a keyboard shortcut; --osd: say on
        screen what was answered
  --shortcuts on|off|status
        keyboard answers: the shortcuts for --oldest (Plasma's global
        shortcuts: Meta+Alt+Y allows, Meta+Alt+N denies, where they're free)

--host HOST: the same on an SSH host (remote.py runs this file there, after
talpy_den.py); --remote: the JSON after a marker line, as there.
Python 3.7+ and the standard library only.
"""
import base64
import difflib
import fcntl
import itertools
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True  # no __pycache__ inside the installed widget...
if os.path.isfile(globals().get("__file__") or ""):  # (on an SSH host it comes on stdin, after talpy_den.py)
    if sys.version_info >= (3, 8):  # ...but talpy_den.py compiled in the data folder, as poll.py does (never the cache)
        _compiled = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "talpy-den" / "pycache"
        if _compiled.is_dir():
            sys.pycache_prefix = str(_compiled)
            sys.dont_write_bytecode = False
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # -I leaves the script dir off sys.path
import talpy_den as cs  # noqa: E402

# ---------------------------------------------------------------- the conversation

PANE_ITEMS = 120  # items the pane gets at first ("Show earlier" asks for more)
PANE_ITEMS_MAX = 2000
PANE_TAIL_BYTES = 512 << 10
PANE_TAIL_MAX = 64 << 20
TEXT_CHARS = 20000  # of one prompt or reply
DETAIL_CHARS = 1200  # of a tool call's input or output, unfolded
DETAIL_LINES = 24
PANE_LINE = re.compile(rb'"type":\s*"(?:user|assistant|system|queue-operation|queued_command)"')
INTERRUPTED = "[Request interrupted"
NO_CHAT = "This chat hasn't started yet, or it isn't there any more"   # (no transcript: none yet, or deleted)


def clip(text, chars=DETAIL_CHARS, lines=DETAIL_LINES):
    """text cut to lines lines and chars characters (… where it was cut)."""
    text = (text or "").rstrip()
    rows = text.split("\n")
    cut = len(rows) > lines
    text = "\n".join(rows[:lines])
    if len(text) > chars:
        text, cut = text[:chars - 1].rstrip(), True
    return text + ("\n…" if cut else "")


def result_text(block):
    """The text of a tool_result block."""
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(c.get("text") for c in content
                         if isinstance(c, dict) and c.get("type") == "text" and isinstance(c.get("text"), str))
    return ""


def tool_input_text(block):
    """What a tool call was asked to do, for its unfolded line: the command,
    the file and the change, the search…"""
    name = block.get("name") or ""
    inp = block.get("input") if isinstance(block.get("input"), dict) else {}
    if name == "Bash" and isinstance(inp.get("command"), str):
        return "$ " + inp["command"]
    path = inp.get("file_path") or inp.get("notebook_path")
    if name in ("Edit", "MultiEdit", "Write", "NotebookEdit") and isinstance(path, str):
        return "\n".join([path] + cs.edit_diff(name, inp, None)[:DETAIL_LINES])
    parts = []
    for key, value in inp.items():
        if isinstance(value, (str, int, float, bool)) and str(value).strip():
            parts.append(f"{key}: {value}")
    return "\n".join(parts)


EDITS = ("Edit", "MultiEdit", "Write", "NotebookEdit")
EDIT_DIFF_LINES = 40  # of one edit's diff, in the chat (the Review tab has whole files)
DIFF_BUDGET = 600  # of all the edits' diffs in one answer, the newest first: older ones keep a glimpse
DIFF_GLIMPSE = 6
READ_LINE = re.compile(r"^\s*\d+[\t\u2192]")
TOOL_ERROR = re.compile(r"</?tool_use_error>")


def plural(n, word):
    return f"{n} {word}" + ("" if n == 1 else "s")


def edit_lines(name, inp, result, current=None):
    """The lines of a unified diff (@@ lines included) of what an Edit,
    MultiEdit, Write or NotebookEdit call changed, as the chat shows it under
    the call: from what the call gave back (its patch, at the file's line
    numbers; all of a new file), else from what it was asked (numbered from
    the change, with current: the file's text, at its line numbers; nothing
    for a Write, which may replace a whole file)."""
    lines = None
    if isinstance(result, dict):
        patch = result.get("structuredPatch")
        if result.get("type") == "create" and isinstance(result.get("content"), str):
            body = result["content"].splitlines()
            lines = [f"@@ -0,0 +1,{len(body)} @@"] + ["+" + l for l in body]
        elif isinstance(patch, list) and patch:
            lines = []
            for h in patch:
                if isinstance(h, dict) and isinstance(h.get("lines"), list):
                    lines.append(f"@@ -{h.get('oldStart', 0)},{h.get('oldLines', 0)} +{h.get('newStart', 0)},{h.get('newLines', 0)} @@")
                    lines += [l for l in h["lines"] if isinstance(l, str)]
    if lines is None:
        lines = cs.edit_diff(name, inp, current, limit=None) if name != "Write" else []
    return lines


def capped(lines):
    """An edit's diff lines as the chat gets them: the first EDIT_DIFF_LINES, and how many more."""
    shown = [l[:500] for l in lines[:EDIT_DIFF_LINES]]
    if len(lines) > EDIT_DIFF_LINES:
        shown.append(f"… ({len(lines) - EDIT_DIFF_LINES} more lines)")
    return shown


def change_summary(name, diff, fallback=""):
    """What an edit changed, in a line: from its diff's lines (@@ lines and
    content, no file headers: a "---" is a removed "--")."""
    added = sum(1 for d in diff if d.startswith("+"))
    removed = sum(1 for d in diff if d.startswith("-"))
    if name != "Edit" and name != "MultiEdit" and not removed:
        return plural(added, "line")
    if added and removed:
        return f"{plural(added, 'line')} added, {removed} removed"
    return f"{plural(added, 'line')} added" if added else f"{plural(removed, 'line')} removed" if removed else fallback


def tool_summary(name, inp, output, error):
    """What came of a tool call, in one line, as Claude's terminal shows it
    under the call: the error, the lines it read or changed, else the first
    line of what came back and how many more there are."""
    rows = [r for r in TOOL_ERROR.sub("", output or "").strip().split("\n") if r.strip()]
    first = cs.short_text(rows[0], 120) if rows else ""
    if error:
        return first or "Failed"
    if name == "Read":
        read = sum(1 for r in rows if READ_LINE.match(r))
        return plural(read, "line") if read else first   # (an image, a PDF: no numbered lines)
    if name in EDITS:
        return change_summary(name, cs.edit_diff(name, inp, None, limit=None), first)
    if not rows:
        return "(no output)" if name == "Bash" else ""
    return first + (f" … +{plural(len(rows) - 1, 'line')}" if len(rows) > 1 else "")


def typed_text(content):
    """What a message you sent while Claude worked says (a string, or the
    text blocks of one with pictures), "" for one that isn't yours to read
    (a task notification, a subagent's report)."""
    text = cs.message_text({"content": content}).strip()
    return "" if text.startswith("<") else text


def same_text(a, b):
    return " ".join(a.split()) == " ".join(b.split())


# ---------------------------------------------------------------- your answers in the chat
#
# What Claude asked (AskUserQuestion, a plan: ExitPlanMode) and what you said
# to it, read from the transcript's structure wherever you answered (Talpy
# Chat, a notification, a row, Claude's terminal, the Claude Code panel): the
# tool result's toolUseResult ({questions, answers {question: text},
# annotations {question: {notes}}}; an approved plan's {plan}); a note given
# with a No: what follows Claude Code's own fixed sentence, always in English
# ("…, the user said:" and its older "…reason for the rejection:"), or the
# permission hook's (decision_of, plan_decision). Your note is in your words.

REJECTED_USE = "User rejected tool use"   # (Claude Code's toolUseResult for a No without a note)
REFUSALS = ("The user doesn't want to proceed with this tool use.", "Permission for this tool use was denied.")
SAID = re.compile(r"(?:the user said:|The user said:|the following reason for the rejection:)[ \t]*\n?")
OUR_NO = re.compile(r"The user (?:didn't answer|denied this|wants to keep planning)(?P<said> and said: |[.:])")
CLARIFY = "The user wants to clarify these questions."   # (Claude Code's, as the note: "Chat about this")
NEXT_NOTE = "\n\nNote: The user's next message may contain"   # (Claude Code's, after some notes: not yours)


def rejection(entry, text, error):
    """Your note, if this tool result is your No to the call ("" for a No
    without one); None for any other result: one that ran, an error, or a
    refusal by a rule, auto mode's classifier or a hook of another's."""
    if not error:
        return None
    decided = entry.get("permissionDecision")
    if isinstance(decided, dict) and (decided.get("decision") != "reject"
                                      or decided.get("source") not in ("user_reject", "hook")):
        return None
    cut = text.find(NEXT_NOTE)
    text = (text[:cut] if cut >= 0 else text).strip()
    ours = OUR_NO.match(text)
    if ours:
        return text[ours.end():].strip() if ours.group("said") == " and said: " else ""
    if text.startswith(REFUSALS):
        said = SAID.search(text.split("\n", 1)[0])
        if said:
            return text[said.end():].strip()
        if isinstance(decided, dict) or entry.get("toolUseResult") == REJECTED_USE:
            return ""
    return None


def split_answer(text):
    """A multi-select answer's parts, as Claude's dialog joins them (answer_text):
    ", " between them, one with ", " or a quote in it JSON-quoted."""
    parts, at = [], 0
    while at < len(text):
        if text[at] == '"':
            try:
                value, end = json.JSONDecoder().raw_decode(text, at)
            except ValueError:
                value, end = None, at
            if isinstance(value, str) and (end == len(text) or text.startswith(", ", end)):
                parts.append(value)
                at = end + 2
                continue
        end = text.find(", ", at)
        end = len(text) if end < 0 else end
        parts.append(text[at:end])
        at = end + 2
    return parts


def picked_labels(answer, question):
    """The options of question an answer picked (by their labels)."""
    labels = [o["label"] for o in question["options"]]
    if answer in labels:
        return [answer]
    return [p for p in split_answer(answer) if p in labels] if question["multiSelect"] else []


def plan_title(text):
    for line in text.splitlines():
        line = line.strip().lstrip("#").strip()
        if line:
            return cs.short_text(line, 100)
    return ""


def asked_of(name, inp):
    """What a question or a plan asks, for the chat to show as Claude's
    (the tool item's "asked"): {"questions": question_view's, each with
    "picked" (the labels you chose)} or {"plan" (Markdown), "title"}, with
    "state" (how you answered: "open" till then)."""
    if name == cs.ASK_TOOL:
        return {"questions": [dict(q, picked=[]) for q in cs.question_view(inp)], "state": "open"}
    text = inp.get("plan") if isinstance(inp.get("plan"), str) else ""
    return {"plan": clip(text, TEXT_CHARS, 10 ** 6), "title": plan_title(text), "state": "open"}


ASKED_SUMMARY = {"answered": "Answered", "declined": "Declined", "chat": "Chat about this",
                 "approved": "Approved", "keep": "Keep planning", "denied": "Denied"}


def your_answer(item, entry, output, error, result):
    """Your answer to the tool call item, now that it has its result (output,
    error; result: the entry's toolUseResult when it's this call's): sets
    the item's "asked" state, and gives your answer as an item of yours
    ({"kind": "you", "key": "<tool id>/answer", "text", "answered":
    "question" | "plan" | "permission"}, a question's with "answers":
    [{"header", "question", "answer", "notes"}]), or None."""
    asked = item.get("asked")
    note = rejection(entry, output, error)
    text, answered, extra = "", "", {}
    if asked is not None and "questions" in asked:
        answered = "question"
        given = result.get("answers") if isinstance(result, dict) else None
        if note is not None:
            asked["state"] = "chat" if note.startswith(CLARIFY) else "declined"
            text = note if asked["state"] == "declined" else ""
        elif isinstance(given, dict) and given:
            asked["state"] = "answered"
            notes = result.get("annotations") if isinstance(result.get("annotations"), dict) else {}
            asked_now = [dict(q, picked=[]) for q in cs.question_view(result)] or asked["questions"]
            answers = []
            for q in asked_now:
                answer = given.get(q["question"])
                if not isinstance(answer, str):
                    continue
                q["picked"] = picked_labels(answer, q)
                said = notes.get(q["question"]).get("notes") if isinstance(notes.get(q["question"]), dict) else None
                answers.append({"header": q["header"], "question": q["question"], "answer": answer,
                                "notes": said.strip() if isinstance(said, str) else ""})
            asked["questions"] = asked_now
            several = len(answers) > 1
            text = "\n".join((f"{a['header'] or a['question']}: " if several else "") + a["answer"]
                             + ("\n" + a["notes"] if a["notes"] else "") for a in answers)
            extra = {"answers": answers}
        else:   # (no answers, "The user did not answer the questions."; or it failed)
            asked["state"] = "failed" if error else "declined"
    elif asked is not None:
        answered = "plan"
        if note is not None:
            asked["state"] = "keep"
            text = "Keep planning" + ("\n" + note if note else "")
        elif not error:   # (approved: toolUseResult has the plan, as it was approved)
            asked["state"] = "approved"
            text = "Approved the plan"
            plan = result.get("plan") if isinstance(result, dict) else None
            if not asked["plan"].strip() and isinstance(plan, str) and plan.strip():
                asked["plan"], asked["title"] = clip(plan, TEXT_CHARS, 10 ** 6), plan_title(plan)
        else:
            asked["state"] = "failed"
    elif note:
        answered = "permission"
        item["asked"] = {"state": "denied"}
        text = note
    if item.get("asked"):
        item["summary"] = ASKED_SUMMARY.get(item["asked"]["state"], item["summary"])
    if not text:
        return None
    return dict({"kind": "you", "key": item["key"] + "/answer", "text": clip(text, TEXT_CHARS, 10 ** 6),
                 "answered": answered}, **extra)


PICTURE_NAMED = re.compile(r"\[Image: (/[^\]\n]+)\]")
PICTURE_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif"}
PICTURE_MAX = 20 << 20  # bytes of one pasted picture saved for the pane


def regular_file(path):
    """Whether path is a regular file (or a link to one): only such a picture
    is read for a thumbnail (a pty or a pipe named [Image: /dev/ptmx] never
    answers, and every later picture of plasmashell waits on it for good)."""
    try:
        return stat.S_ISREG(os.stat(path).st_mode)
    except (OSError, ValueError):
        return False


def file_pictures(items):
    """items with only the pictures that are a regular file (regular_file):
    looked at for the items sent, one stat each."""
    for item in items:
        if item.get("pictures"):
            item["pictures"] = [p for p in item["pictures"] if regular_file(p)]
            if not item["pictures"]:
                del item["pictures"]
    return items


def pictures_here(items):
    """A host's chat names its pictures by their paths there, and the pane
    shows each from this computer: the copy of one you pasted, else the file
    of that path here, read only when it's a regular file here (each item's
    "here", regular_file)."""
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict) and isinstance(item.get("pictures"), list):
            item["here"] = [p for p in item["pictures"] if isinstance(p, str) and p.startswith("/") and regular_file(p)]
    return items


def prompt_pictures(text, blocks, uid, folder):
    """The pictures a prompt of yours has, for the pane's thumbnails: the
    files it names ([Image: /path], a picture pasted in the pane), then
    those pasted into it in Claude's terminal or panel (its image blocks),
    each saved once in folder (cs.images_dir, kept as long as the pane's own,
    IMAGES_KEEP_DAYS), named after its entry. folder None (an SSH host's
    chat): the files it names only (conversation keeps the regular files)."""
    out = []
    for path in PICTURE_NAMED.findall(text or ""):
        if path not in out:
            out.append(path)
    if folder is None:
        return out
    n = 0
    for c in blocks:
        if c.get("type") != "image":
            continue
        n += 1
        src = c.get("source") if isinstance(c.get("source"), dict) else {}
        ext, data = PICTURE_TYPES.get(src.get("media_type")), src.get("data")
        if src.get("type") != "base64" or ext is None or not isinstance(data, str) or len(data) > PICTURE_MAX * 4 // 3 + 4:
            continue
        path = Path(folder) / f"chat-{re.sub(r'[^0-9A-Za-z-]', '', str(uid))[:64]}-{n}{ext}"
        if not path.exists():
            try:
                picture = base64.b64decode(data, validate=True)
                Path(folder).mkdir(parents=True, exist_ok=True)
                os.chmod(folder, 0o700)  # (a screenshot can show anything)
                part = path.with_name(path.name + ".part")
                with open(os.open(str(part), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb") as f:
                    f.write(picture)
                os.replace(part, path)
            except (ValueError, OSError):
                continue
        out.append(str(path))
    return out


QUESTION_END = re.compile(r"[?？؟](?:\s|$)")
REPLY_TAIL = 4000   # of Claude's last words: what tells how its turn ended, and its question
REPLY_KEPT = 1500   # of them, kept between reads of a transcript (whether its last paragraph asks)


def ends_with_question(text):
    """Claude's reply asks something: its last paragraph has a sentence that
    ends with a question mark (any script's)."""
    paras = [p for p in re.split(r"\n\s*\n", (text or "").strip()) if p.strip()]
    return bool(paras) and bool(QUESTION_END.search(re.sub(r"[*_`)\]]+", "", paras[-1]).strip()))


class TurnEnd:
    """How Claude's turn ended, followed entry by entry: what ended it
    (turn: "api:<its message>", "interrupted", "tool_error", "stopped" or
    None), Claude's last words since your prompt (reply, its message id), a
    tool call after them (tool), and what the last entry was (last:
    "prompt", "step" (a tool call or its result, mid-turn), "tool_error",
    "open" (a reply with no stop reason), "end" (Claude's turn is over:
    its stop reason, or Claude Code's stand-in reply), "error" (an API
    error: a usage limit…) or "interrupted"). As the offline check on real
    chats: a turn's end state is what Talpy Chat's chips go by."""
    __slots__ = ("turn", "reply", "reply_id", "tool", "started", "last")

    def __init__(self, kept=None):
        self.turn, self.reply, self.reply_id, self.tool, self.started, self.last = None, "", None, False, False, None
        if isinstance(kept, list) and len(kept) == 6:
            self.turn, self.reply, self.reply_id, self.tool, self.started, self.last = kept

    def kept(self):   # (to go on reading later: of Claude's words, the end that tells whether it asked)
        return [self.turn, self.reply[-REPLY_KEPT:], self.reply_id, self.tool, self.started, self.last]

    def prompt(self):
        self.reply, self.reply_id, self.turn, self.tool, self.started, self.last = "", None, None, False, True, "prompt"

    def tool_result(self, error):
        self.turn, self.started, self.last = ("tool_error", True, "tool_error") if error else (None, True, "step")

    def interrupted(self):
        self.turn, self.started, self.last = "interrupted", True, "interrupted"

    def assistant(self, e, msg, blocks):
        self.started = True
        if e.get("isApiErrorMessage"):
            self.turn, self.last = "api:" + " ".join(cs.message_text(msg).split())[:200], "error"
            return
        if msg.get("model") == "<synthetic>":   # (Claude Code's "No response requested." for a chat it stopped)
            self.reply, self.reply_id, self.tool = cs.message_text(msg).strip()[-REPLY_TAIL:], msg.get("id"), False
            self.turn, self.last = "stopped", "end"
            return
        mid = msg.get("id")
        updates = e.get("thinkingDisplay") == "updates"
        calls = False
        for c in blocks:
            said = c.get("text") if c.get("type") == "text" else c.get("thinking") if c.get("type") == "thinking" and updates else None
            if isinstance(said, str) and said.strip():
                both = mid is not None and mid == self.reply_id and not self.tool
                self.reply = (self.reply + "\n\n" + said.strip() if both else said.strip())[-REPLY_TAIL:]
                self.reply_id, self.tool, self.turn = mid, False, None
            elif c.get("type") == "tool_use":
                self.tool, self.turn, calls = True, None, True
        stop = msg.get("stop_reason")
        # (a tool call never ends a turn: its result comes, and Claude goes on)
        self.last = "step" if calls or stop in ("tool_use", "pause_turn") else "open" if stop is None else "end"

    def state(self):
        """asked | finished | limit (a usage limit) | interrupted | failed (an API error, or a tool
        call that failed last) | stopped (Claude Code's stand-in reply, or no reply at all)"""
        turn = self.turn or ""
        if turn.startswith("api:"):
            return "limit" if turn[4:].startswith(cs.LIMIT_STARTS + cs.OUT_OF_USAGE) else "failed"
        if turn == "interrupted":
            return "interrupted"
        if turn == "stopped" or not self.reply:
            return "stopped"
        if turn == "tool_error" and self.tool:
            return "failed"
        return "asked" if ends_with_question(self.reply) else "finished"

    def result(self, waiting=False):
        """(ended, over): how the last turn ended (state), None mid-turn or
        with a message of yours waiting in Claude's queue; over: the
        transcript itself says the turn is over (else the chat's state does:
        your prompt with no reply yet, a reply with no stop reason)."""
        if not self.started or waiting or self.last == "step":
            return None, False
        return self.state(), self.last in ("end", "error", "interrupted")


def conversation_items(lines, pictures=None, ends=None):
    """The pane's items from transcript lines (oldest first): {"kind": "you",
    "text"} for a prompt of yours (one sent while Claude works shows when you
    send it, not once Claude takes it in), {"kind": "claude", "text"} for Claude's
    reply (markdown), {"kind": "tool", "name", "line", "status":
    "ok"|"error"|"open", "input", "output", "summary" (what came of it, in a
    line), "diff" (an edit's: edit_lines)} for a tool call and {"kind":
    "note", "text"} for an interruption, a usage limit or a compaction;
    each with "at" (ms) and "key" (the same in the next answer, as long as
    the item is listed); a prompt of yours with pictures has "pictures"
    (their files: prompt_pictures, saved in the folder pictures). A
    question or a plan Claude asked has "asked" (asked_of), and your answer
    to it, or your note to a No, comes after it as yours (your_answer).
    Entries of subagents (sidechains) aren't in it. ends: a dict given gets
    how the last turn ended (TurnEnd.result)."""
    items, tools = [], {}
    end = TurnEnd()
    # Messages sent while Claude works: the transcript has each one when it's
    # sent (queue-operation enqueue) and again once Claude takes it in, after
    # its next tool result (an attachment, queued_command), which can be long
    # after. waiting: those not taken in yet, listed last with "queued": True
    # (Claude's terminal shows them under the conversation, as queued); one
    # taken in goes where Claude took it, with the same key; taken: the ids of
    # those that were; due: those made the chat's own prompts (dequeue), in turn
    waiting, taken, due = [], set(), []

    def you(key, text, at, content):
        """A prompt of yours as an item (content: its message's, for the pictures in it)"""
        item = {"kind": "you", "key": key, "text": clip(text, TEXT_CHARS, 10 ** 6), "at": at}
        blocks = [c for c in content if isinstance(c, dict)] if isinstance(content, list) else []
        shown = prompt_pictures(text, blocks, key, pictures)
        if shown:
            item["pictures"] = shown
        return item

    def find_waiting(text):
        return next((w for w in waiting if same_text(w["text"], text)), None)

    for line in lines:
        if not PANE_LINE.search(line):
            continue
        try:
            e = json.loads(line)
        except (ValueError, RecursionError):
            continue
        if not isinstance(e, dict) or e.get("isSidechain"):
            continue
        kind, at = e.get("type"), cs.to_ms(e.get("timestamp"))
        uid = e["uuid"] if isinstance(e.get("uuid"), str) else f"{kind}-{at}-{len(items)}"
        if kind == "queue-operation":
            op, text = e.get("operation"), typed_text(e.get("content"))
            if op == "enqueue" and text:
                waiting.append(you(f"queued-{at}", text, at, e.get("content")))
            elif op == "remove" and text:
                item = find_waiting(text)
                if item is not None:
                    waiting.remove(item)
                    items.append(item)
                    taken.add(e.get("commandUuid"))
            elif op == "popAll":  # (back in your input box: not sent)
                for item in [w for w in waiting if not text or same_text(w["text"], text)]:
                    waiting.remove(item)
            elif op == "dequeue" and waiting:
                due.append(waiting.pop(0))  # (the next prompt is this one)
            continue
        if kind == "attachment":
            a = e.get("attachment")
            origin = a.get("origin") if isinstance(a, dict) else None
            if not isinstance(a, dict) or a.get("type") != "queued_command" or a.get("commandMode") != "prompt" \
                    or (isinstance(origin, dict) and origin.get("kind") != "human"):
                continue
            text = typed_text(a.get("prompt"))
            item = find_waiting(text) if text else None
            if item is not None:
                waiting.remove(item)
                items.append(item)
            elif text and a.get("source_uuid") not in taken:
                items.append(you(uid, text, at, a.get("prompt")))
            continue
        if kind == "system":
            if e.get("subtype") == "compact_boundary":
                items.append({"kind": "note", "key": uid, "text": "The conversation was compacted", "at": at})
            continue
        msg, blocks = cs.blocks_of(e)
        if kind == "user":
            if e.get("isCompactSummary") or e.get("isMeta"):
                continue
            results = [c for c in blocks if c.get("type") == "tool_result"]
            for c in results:
                end.tool_result(c.get("is_error"))
                if c.get("tool_use_id") in tools:
                    item, inp = tools.pop(c["tool_use_id"])
                    output = result_text(c)
                    item["status"] = "error" if c.get("is_error") else "ok"
                    item["output"] = clip(output)
                    item["summary"] = tool_summary(item["name"], inp, output, bool(c.get("is_error")))
                    if item["name"] in EDITS and c.get("is_error"):
                        item["diff"] = []
                    elif item["name"] in EDITS:  # (what came back is the entry's, when it has one result)
                        full = edit_lines(item["name"], inp, e.get("toolUseResult") if len(results) == 1 else None)
                        item["diff"] = capped(full)
                        if full:
                            item["summary"] = change_summary(item["name"], full, item["summary"])
                    said = your_answer(item, e, output, bool(c.get("is_error")),
                                       e.get("toolUseResult") if len(results) == 1 else None)
                    if said is not None:
                        said["at"] = at
                        items.append(said)
            prompt = cs.human_prompt(e)
            if prompt is not None:
                end.prompt()
                if due:
                    shown = due.pop(0)
                    if same_text(shown["text"], prompt):
                        items.append(shown)   # (its key as it was while it waited)
                        continue
                    # (not what was sent: it was put together with others, this prompt shows them)
                items.append(you(uid, prompt, at, blocks))
                continue
            text = cs.message_text(msg).strip()
            if text.startswith(INTERRUPTED):
                end.interrupted()
                items.append({"kind": "note", "key": uid, "text": "Interrupted", "at": at})
            continue
        if kind != "assistant":
            continue
        end.assistant(e, msg, blocks)
        if e.get("isApiErrorMessage"):
            text = " ".join(cs.message_text(msg).split())
            if text:
                items.append({"kind": "note", "key": uid, "text": cs.short_text(text, 300), "at": at, "error": True})
            continue
        mid = msg.get("id") if isinstance(msg.get("id"), str) else None
        # (thinking shown as updates: Claude Code shows a thinking block's text
        # as a reply then, what Claude tells you as it works; thinking it keeps
        # to itself comes without text)
        updates = e.get("thinkingDisplay") == "updates"
        for c in blocks:
            said = c.get("text") if c.get("type") == "text" else c.get("thinking") if c.get("type") == "thinking" and updates else None
            if isinstance(said, str) and said.strip():
                last = items[-1] if items else None
                if last is not None and last["kind"] == "claude" and mid is not None and last["key"] == mid:
                    last["text"] = clip(last["text"] + "\n\n" + said.strip(), TEXT_CHARS, 10 ** 6)
                else:
                    items.append({"kind": "claude", "key": mid or uid, "text": clip(said.strip(), TEXT_CHARS, 10 ** 6),
                                  "at": at})
            elif c.get("type") == "tool_use" and isinstance(c.get("id"), str):
                inp = c.get("input") if isinstance(c.get("input"), dict) else {}
                item = {"kind": "tool", "key": c["id"], "name": c.get("name") or "tool", "line": cs.describe_tool(c),
                        "status": "open", "input": clip(tool_input_text(c)), "output": "", "summary": "", "at": at,
                        "diff": capped(edit_lines(c.get("name"), inp, None)) if c.get("name") in EDITS else []}
                if c.get("name") in (cs.ASK_TOOL, cs.PLAN_TOOL):
                    item["asked"] = asked_of(c["name"], inp)
                tools[c["id"]] = (item, inp)
                items.append(item)
    items.extend(due)  # (taken as prompts that aren't written yet)
    for item in waiting:  # (still queued: last, as Claude's terminal shows them)
        item["queued"] = True
        items.append(item)
    for item, inp in tools.values():  # (an edit not made yet: at the file's line numbers)
        path = inp.get("file_path")
        if item["name"] == "Edit" and isinstance(path, str) and path.startswith("/"):
            try:
                data = read_bytes(path) if os.path.getsize(path) < (2 << 20) else None
            except OSError:
                data = None
            if data is not None:
                item["diff"] = capped(edit_lines("Edit", inp, None, data.decode("utf-8", "replace")))
    if ends is not None:
        ends["ended"], ends["over"] = end.result(bool(waiting or due))
        ends["reply"] = end.reply
    return items


def within_budget(items):
    """The edits' diffs cut to DIFF_BUDGET lines in all, the newest whole:
    an older one keeps its first DIFF_GLIMPSE lines (and says how many more)."""
    left = DIFF_BUDGET
    for item in reversed(items):
        diff = item.get("diff")
        if not diff:
            continue
        if len(diff) > left:
            keep = min(len(diff), max(left, DIFF_GLIMPSE))
            more = sum(1 for l in diff[keep:] if not l.startswith("@@"))
            item["diff"] = diff[:keep] + ([f"… ({more} more lines)"] if more else [])
        left = max(0, left - len(diff))
    return items


def tail_lines(path, size, nbytes):
    """The whole lines in the last nbytes of a file (its first, cut, one
    dropped), and whether they start at the file's start."""
    with open(path, "rb") as f:
        f.seek(max(0, size - nbytes))
        lines = f.read(min(size, nbytes)).split(b"\n")
    whole = size <= nbytes
    if not whole:
        lines = lines[1:]
    return lines, whole


def conversation(path, limit=PANE_ITEMS, pictures=None, ends=None):
    """(items, more) of a chat: its newest limit items (conversation_items,
    pasted pictures saved in pictures; ends: how its last turn ended), and
    whether there are older ones."""
    size = path.stat().st_size
    nbytes = PANE_TAIL_BYTES
    while True:
        lines, whole = tail_lines(path, size, nbytes)
        items = conversation_items(lines, pictures, ends)
        if whole or len(items) > limit or nbytes >= PANE_TAIL_MAX:
            return within_budget(file_pictures(items[-limit:])), len(items) > limit or not whole
        nbytes *= 4


def stamp_of(path):
    st = path.stat()
    return f"{st.st_size}:{st.st_mtime_ns}"


WAIT_MAX_S = 55  # (the pane gives up on a run after 70 s, hub/Exec.qml's staleMs, VS Code after 70 s)
WAIT_GATHER_S = 0.04  # after a change: what Claude writes with it (a prompt and its attachments)
# inotify: IN_MODIFY | IN_ATTRIB | IN_CLOSE_WRITE | IN_DELETE_SELF | IN_MOVE_SELF (a line added, the file
# replaced or moved: Claude moves a chat's transcript when it goes into a worktree)
WAIT_MASK = 0x2 | 0x4 | 0x8 | 0x400 | 0x800


def wait_for_change(path, stamp, seconds, clock=time.time):
    """Wait up to seconds for the transcript at path to be other than stamp
    (stamp_of): whether it is. inotify on the file (elsewhere: a look every
    half second); it ends as soon as whoever started it is gone."""
    import live  # (its Watch: the same inotify the widget's watcher uses)
    watch = live.Watch([str(path)], WAIT_MASK)  # (watching first: nothing between the look and the wait is missed)
    parent, end = os.getppid(), clock() + max(0.0, seconds)
    try:
        while True:
            try:
                if stamp_of(path) != stamp:
                    return True
            except OSError:
                return True  # (gone: the read says so)
            left = end - clock()
            if left <= 0 or os.getppid() != parent:
                return False
            if watch.wait(min(left, 1.0)):
                time.sleep(WAIT_GATHER_S)
                watch.drain()
    finally:
        watch.close()


def find_transcript(home, extra_dirs, chat_id, profile_key=None):
    """(profile, transcript) of a chat: under the profile named first, else any that has it."""
    profiles = cs.discover_profiles(home, extra_dirs)
    ordered = sorted(profiles, key=lambda p: not (profile_key and cs.matches_profile(p, profile_key)))
    for p in ordered:
        path = cs.transcript_path(p, chat_id)
        if path is not None:
            return p, path
    return None, None


def chat_conversation(home, extra_dirs, chat_id, profile_key=None, limit=PANE_ITEMS, if_changed=None, wait=0, pictures=None,
                      suggest=False):
    """--conversation. suggest (Suggest replies on): how its last turn ended,
    "ended" and "over" (TurnEnd.result), and the question it ends with as
    chips, "asks" (asks_of)."""
    if not cs.valid_id(chat_id):
        return {"ok": False, "message": f"Not a chat: {chat_id}"}
    profile, path = find_transcript(home, extra_dirs, chat_id, profile_key)
    if path is None:
        return {"ok": False, "missing": True, "message": NO_CHAT}
    stamp = stamp_of(path)
    if if_changed and if_changed == f"{stamp}/{limit}":
        if not (wait > 0 and wait_for_change(path, stamp, min(wait, WAIT_MAX_S))):
            return {"ok": True, "unchanged": True}
        if not path.exists():  # (moved: where it is now)
            profile, path = find_transcript(home, extra_dirs, chat_id, profile_key)
        try:
            stamp = stamp_of(path)  # (before it's read: what's written meanwhile is a change the next time)
        except (OSError, AttributeError):
            return {"ok": False, "missing": True, "message": NO_CHAT}
    ends = {} if suggest else None
    items, more = conversation(path, max(1, min(PANE_ITEMS_MAX, limit)), pictures, ends)
    name, cwd, _ = cs.read_chat_info(path, path.stat().st_size)
    peek = cs.chat_peek(path) or {}
    result = {"ok": True, "chatId": chat_id, "profileDir": profile.key, "name": name, "cwd": cwd or cs.chat_folder(path) or "",
              "items": items, "more": more, "stamp": f"{stamp}/{limit}", "mode": peek.get("mode"),
              "permission": cs.pending_permission(path, cwd)}
    if suggest:
        ended = ends.get("ended")
        result.update(ended=ended, over=bool(ends.get("over")), asks=asks_of(ends.get("reply")) if ended == "asked" else None)
    return result


# ---------------------------------------------------------------- permission requests the hook relays

DECISIONS = ("allow", "always", "deny", "answer")
PLAN_DECISIONS = ("approve", "approve-edits", "keep")   # a plan's (ExitPlanMode)


def answer_text(values, multi):
    """One question's answer as Claude's dialog sends it: the option chosen
    (or what you typed); several, comma-separated (one with ", " or a quote
    in it quoted, as Claude quotes it)."""
    values = [v.strip() for v in values if isinstance(v, str) and v.strip()]
    if not multi:
        return values[0] if values else ""
    return ", ".join(json.dumps(v, ensure_ascii=False) if ", " in v or '"' in v else v for v in values)


def question_answers(inp, answers):
    """{question: answer text} for the AskUserQuestion call inp, from
    answers {question: [labels or text]}: the questions it asks only."""
    out = {}
    for q in cs.question_view(inp):
        given = answers.get(q["question"]) if isinstance(answers, dict) else None
        text = answer_text(given if isinstance(given, list) else [given], q["multiSelect"])
        if text:
            out[q["question"]] = text
    return out


def decision_of(decision, note, suggestions, inp=None, answers=None):
    """The hook's answer to Claude (its "decision") for the widget's button
    (a question's: the call's input with the answers in it)."""
    question = isinstance(inp, dict) and answers is not None
    if decision == "deny":
        note = (note or "").strip()
        if note:  # (said as yours: Claude reads it in the tool's result)
            said = "didn't answer" if question else "denied this"
            return {"behavior": "deny", "message": f"The user {said} and said: {note}"}
        return {"behavior": "deny", "message": "The user didn't answer." if question else "The user denied this.",
                "interrupt": True}
    out = {"behavior": "allow"}
    if question:
        out["updatedInput"] = dict(inp, answers=answers)
    elif decision == "always" and cs.always_allow(suggestions)[0]:
        out["updatedPermissions"] = cs.always_allow(suggestions)[0]  # (what its label says: no more)
    return out


def plan_decision(decision, note, inp):
    """The hook's answer to a plan (ExitPlanMode): approve it (an allow
    with the call's input; accept edits from then on: a setMode), or keep
    planning with what to change (a deny: its message is the feedback)."""
    if decision == "keep":
        note = (note or "").strip()
        return {"behavior": "deny", "message": f"The user wants to keep planning and said: {note}" if note
                else "The user wants to keep planning: don't start yet, work more on the plan and present it again."}
    out = {"behavior": "allow", "updatedInput": dict(inp)}
    if decision == "approve-edits":
        out["updatedPermissions"] = [{"type": "setMode", "mode": "acceptEdits", "destination": "session"}]
    return out


NOT_ASKING = "It isn't asking any more (answered in the chat?)"


def answer_request(cache_root, request_id, decision, note="", answers=None):
    """Answer a relayed request: (ok, message). A question takes "answer"
    (answers: {question: [labels or text]}) or "deny". One that's gone:
    (False, NOT_ASKING); one its chat asked again after: (False, ASKS_ELSE)."""
    if decision not in DECISIONS + PLAN_DECISIONS:
        return False, f"Not an answer: {decision}"
    if not re.fullmatch(r"[0-9]+-[0-9a-f]{8}", request_id or ""):
        return False, f"Not a request: {request_id}"
    folder = next((d for d in cs.request_dirs(cache_root) if os.path.isfile(d / (request_id + ".json"))),
                  cs.requests_dir(cache_root))  # (where its hook waits for the answer)
    req = cs.read_json(folder / (request_id + ".json"))
    if not isinstance(req, dict) or not cs.pid_alive(req.get("hookPid")):
        return False, NOT_ASKING
    now = cs.permission_requests(cache_root).get(req.get("sessionId"))
    if now is not None and now.get("id") != request_id:
        return False, ASKS_ELSE   # (it asked again since: that one was answered in the chat)
    inp, given = None, None
    plan = req.get("tool") == cs.PLAN_TOOL
    if plan != (decision in PLAN_DECISIONS) and not (plan and decision == "deny"):
        return False, "Approve the plan or keep planning" if plan else "It asks for a permission, not about a plan"
    if plan:
        inp = req.get("input") if isinstance(req.get("input"), dict) else {}
        answer = plan_decision("keep" if decision == "deny" else decision, note, inp)
    elif req.get("tool") == cs.ASK_TOOL:
        inp = req.get("input") if isinstance(req.get("input"), dict) else {}
        if decision in ("allow", "always"):
            return False, "Choose your answers first"
        given = question_answers(inp, answers) if decision == "answer" else {}
        if decision == "answer" and not given:
            return False, "Choose your answers first"
    elif decision == "answer":
        return False, "It asks for a permission, not a question"
    if not plan:
        answer = decision_of(decision, note, req.get("suggestions") or [], inp, given)
    cs.write_json_atomic(folder / (request_id + ".answer.json"), answer)
    deadline = time.time() + 5
    while (folder / (request_id + ".json")).exists() and time.time() < deadline:
        time.sleep(0.1)
    if (folder / (request_id + ".json")).exists():
        return False, "The chat didn't take the answer: answer it there"
    if plan:
        return True, {"approve": "Approved: it starts", "approve-edits": "Approved: it starts, accepting edits"}.get(
            decision, "It keeps planning" + (" with your note" if (note or "").strip() else ""))
    if inp is not None:
        return True, "Answered" if decision == "answer" else "Declined"
    return True, {"allow": "Allowed", "always": "Allowed, and from now on", "deny": "Denied"}[decision]


# ---------------------------------------------------------------- what the reply box offers
#
# Claude's own commands (as of Claude Code 2.1.311, the ones that make sense
# typed into a chat), your commands and skills (the profile's commands/ and
# skills/), the project's (.claude/commands, .claude/skills), its files (git
# ls-files, else a walk) and your past prompts there (history.jsonl).

BUILTIN_COMMANDS = (
    ("add-dir", "Add a new working directory"), ("agents", "Manage subagents"), ("branch", "Branch the conversation here"),
    ("btw", "Ask a quick side question without interrupting"), ("clear", "Start a new chat with empty context"),
    ("compact", "Free up context by summarizing the conversation so far"), ("config", "Open settings"),
    ("context", "Show how full the context is"), ("copy", "Copy Claude's last response"), ("cost", "Show what this chat cost"),
    ("doctor", "Check Claude Code's installation"), ("effort", "Set the effort level"), ("export", "Export the conversation"),
    ("fork", "Copy this conversation into a new background chat"), ("goal", "Set a goal Claude checks before stopping"),
    ("help", "Show help and the commands"), ("hooks", "Show the hooks"), ("init", "Write a CLAUDE.md for this project"),
    ("insights", "A report about your Claude Code chats"), ("mcp", "Manage MCP servers"), ("memory", "Edit CLAUDE.md and memory"),
    ("model", "Set the model"), ("permissions", "Manage what Claude may do without asking"),
    ("plan", "Plan mode, or the chat's plan"), ("pr-comments", "Get the comments of a pull request"),
    ("recap", "A one-line recap of the chat"), ("resume", "Resume another conversation"), ("review", "Review a pull request"),
    ("rewind", "Go back to an earlier point"), ("security-review", "Review the pending changes for security"),
    ("skills", "List the skills"), ("status", "Version, model, account and connections"),
    ("subtask", "Send a subagent off with your full context"), ("todos", "Show the task list"), ("usage", "Show plan usage"),
)
COMPLETE_FILES_MAX = 20000
COMPLETE_HISTORY_MAX = 200
COMMAND_FILES_MAX = 500
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache", "dist", "build", ".tox",
             ".cache", "target", ".gradle", ".idea"}


def front_matter(text):
    """{key: value} of a Markdown file's front matter (--- … ---), and its first line of text after it."""
    lines, meta, first = text.splitlines(), {}, ""
    i = 0
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                break
            key, sep, value = lines[i].partition(":")
            if sep and key.strip():
                meta[key.strip().lower()] = value.strip().strip("'\"")
        i += 1
    for line in lines[i:]:
        line = line.strip().lstrip("#").strip()
        if line:
            first = line
            break
    return meta, first


def command_files(folder, scope):
    """Commands in a commands/ folder: [{name, about, kind}] (a file in a subfolder: dir:name)."""
    out = []
    try:
        files = sorted(folder.rglob("*.md"))[:COMMAND_FILES_MAX]
    except OSError:
        return out
    for f in files:
        head = cs.read_plain(f, 4000, head=True)  # (only its start: a plain file, a repository's link to a device isn't read)
        if head is None:
            continue
        meta, first = front_matter(head.decode("utf-8", "replace"))
        name = ":".join(f.relative_to(folder).with_suffix("").parts)
        out.append({"name": "/" + name, "about": cs.short_text(meta.get("description") or first, 100), "kind": scope})
    return out


def skill_dirs(folder, scope):
    """Skills in a skills/ folder (each its SKILL.md): [{name, about, kind}]."""
    out = []
    try:
        dirs = sorted(d for d in folder.iterdir() if d.is_dir())[:COMMAND_FILES_MAX]
    except OSError:
        return out
    for d in dirs:
        head = cs.read_plain(d / "SKILL.md", 4000, head=True)
        if head is None:
            continue
        meta, first = front_matter(head.decode("utf-8", "replace"))
        out.append({"name": "/" + (meta.get("name") or d.name), "about": cs.short_text(meta.get("description") or first, 100),
                    "kind": scope + " skill"})
    return out


def project_files(cwd):
    """The project's files, relative to cwd (git ls-files: tracked and new, not ignored; else a walk
    that leaves out dependencies and build output), at most COMPLETE_FILES_MAX: (files, cut)."""
    git = shutil.which("git")
    if git and cwd:
        try:
            r = subprocess.run([git, "-C", cwd, "ls-files", "-co", "--exclude-standard", "-z"], stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, timeout=10)
            if r.returncode == 0:
                files = [f for f in r.stdout.decode("utf-8", "replace").split("\0") if f]
                return files[:COMPLETE_FILES_MAX], len(files) > COMPLETE_FILES_MAX
        except (OSError, subprocess.TimeoutExpired):
            pass
    files = []
    if not cwd or not os.path.isdir(cwd) or os.path.realpath(cwd) == str(Path.home()):
        return files, False   # (not all of your home)
    for top, dirs, names in os.walk(cwd):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
        rel = os.path.relpath(top, cwd)
        for n in sorted(names):
            files.append(n if rel == "." else os.path.join(rel, n))
            if len(files) >= COMPLETE_FILES_MAX:
                return files, True
    return files, False


def past_prompts(profile, cwd):
    """Your prompts in that folder (or the one it's in: a chat that started
    there and went into it), newest first, each once (history.jsonl)."""
    out, seen = [], set()
    for e in reversed(cs.history_tail(profile)):
        text, project = e.get("display"), e.get("project")
        if not isinstance(text, str) or not text.strip() or text in seen:
            continue
        if cwd and not (isinstance(project, str) and (cwd == project or cwd.startswith(project.rstrip("/") + "/"))):
            continue
        seen.add(text)
        out.append(text)
        if len(out) >= COMPLETE_HISTORY_MAX:
            break
    return out


def completions(home, extra_dirs, chat_id, profile_key=None, cwd=None):
    """What the reply box offers (--complete). chat_id "-" with cwd: a new
    chat's in Talpy Chat, in that folder on the profile profile_key."""
    if chat_id == "-" and cwd:
        profile = next((p for p in cs.discover_profiles(home, extra_dirs) if cs.matches_profile(p, profile_key)), None)
        if profile is None:
            return {"ok": False, "message": f"No Claude profile called {profile_key}"}
        cwd = os.path.expanduser(cwd)
    elif not cs.valid_id(chat_id):
        return {"ok": False, "message": f"Not a chat: {chat_id}"}
    else:
        profile, path = find_transcript(home, extra_dirs, chat_id, profile_key)
        if path is None:
            return {"ok": False, "message": NO_CHAT}
        _, cwd, _ = cs.read_chat_info(path, path.stat().st_size)
        cwd = cwd or cs.chat_folder(path) or ""
    commands = [{"name": "/" + n, "about": a, "kind": "Claude"} for n, a in BUILTIN_COMMANDS]
    commands += command_files(profile.path / "commands", "yours") + skill_dirs(profile.path / "skills", "your")
    if cwd:
        commands += command_files(Path(cwd) / ".claude" / "commands", "project")
        commands += skill_dirs(Path(cwd) / ".claude" / "skills", "project")
    seen, unique = set(), []
    for c in reversed(commands):   # (yours and the project's before Claude's of the same name)
        if c["name"] not in seen:
            seen.add(c["name"])
            unique.append(c)
    files, cut = project_files(cwd)
    return {"ok": True, "cwd": cwd, "commands": sorted(unique, key=lambda c: c["name"]), "files": files, "filesCut": cut,
            "history": past_prompts(profile, cwd)}


# ---------------------------------------------------------------- suggested replies
#
# Talpy Chat's chips under a turn that's over, each sent only with a click:
# - Claude's question, by its shape (asks_of): the options of a short list
#   before the one question it ends with, the two halves of an either/or, or
#   Yes and No. Any language: the few words it looks at are a table per
#   language in reply_words.py.
# - Your usual replies (usual_replies, --replies): what you sent in your
#   chats on that account after a turn that ended the same way (a usage
#   limit, a chat Claude stopped, a question…), each counted once a chat,
#   older uses less, this project's more; a chip only when one reply is a
#   good share of what you sent then. Read from the transcripts (every
#   message, however it was sent), what's read kept per transcript by its
#   size and time, so a transcript is read once, and from where it was left
#   once it grows. The same list completes what you type.
# The rules and weights were measured on real chats (753 turn ends): a
# yes/no question wins over a list before it (lists of what was done aren't
# options); history alone was wrong 93% of the time, with the share rule
# right 43% of the times it shows.

ASK_LIST_ITEM = re.compile(r"^\s{0,3}(?:[-*•+]|\(?(\d{1,2}|[a-hA-H])[.)])\s+(.*)$")
ASK_BOLD_NUM = re.compile(r"^\s{0,3}\*\*(\d{1,2})[.)]?\s*(.*)$")
ASK_SENTENCE = re.compile(r"(?<=[.!?？؟。])\s+")
ASK_LABEL_CUT = re.compile(r"\s[—–-]\s|:\s|\s\(")
QMARK = re.compile(r"[?？؟]")
ASK_TAIL = 8000            # of a reply: its end is where its question is
ASK_OPTIONS_MAX = 6        # options: 2 to 6 items…
ASK_OPTION_WORDS = 20      # …the middle one at most this many words (a list of what was done is longer)
ASK_SHORT_QUESTION = 8     # "Merge to main and install?": a question of a few words, with no question word, is a yes/no one
ASK_HALF_WORDS = 10        # an either/or's halves: at most this many words each
ASK_LABEL_CHARS = 60       # of a chip's words (it sends them all, up to ASK_SEND_CHARS)
ASK_SEND_CHARS = 300
RECOMMEND_SAID = re.compile(r"\b(?:recommend(?:ed)?|i['’]?d (?:go with|pick|suggest|lean)|my (?:pick|vote|suggestion)|suggest(?:ed)?)\b",
                            re.I)
RECOMMEND_NUM = re.compile(r"(?:option|#|number)\s*([1-9a-h])\b|\b([1-9])\b(?=[^.?!]*\b(?:recommend|i['’]d go|my pick))", re.I)
_ASK_RULES = {}


def ask_rules():
    """reply_words.py's tables as patterns (made once): each language's
    yes/no starts and verbs, and every language's question words, or-words,
    either/or starts, lead words and recommended marks together."""
    if not _ASK_RULES:
        import reply_words
        langs = reply_words.WORDS

        def every(key):
            return list(dict.fromkeys(w for t in langs.values() for w in t.get(key, ())))

        def alt(words):
            return "|".join(re.escape(w) for w in sorted(set(words), key=len, reverse=True))
        _ASK_RULES.update(
            langs=langs,
            starts=[(code, tuple(s if s.endswith("?") else s + " " for s in t.get("yesno", ()))) for code, t in langs.items()],
            verbs=[(code, re.compile(r"^¿?(?:%s)\b" % alt(t["verbs"]))) for code, t in langs.items() if t.get("verbs")],
            wh=re.compile(r"^¿?(?:%s)\b" % alt(every("wh"))),
            ors=[" %s " % w for w in every("or")],
            or_not=re.compile(r"\b(?:%s) (?:%s)\b" % (alt(every("or")), alt(every("or_not")))),
            either=re.compile(r"^¿?(?:%s)\s+" % alt(every("either")), re.I),
            lead=re.compile(r"^(?:%s)[,:]?\s+" % alt(every("lead")), re.I),
            recommended=re.compile(r"\b(?:%s)\b" % alt(every("recommended")), re.I),
            common={code: set(t.get("common", ())) for code, t in langs.items()})
    return _ASK_RULES


def plain_md(text):
    """Markdown's marks (code, bold, links) out of a line of text, its spaces squeezed."""
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\*\*|\*|(?<!\w)__?|__?(?!\w)", "", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    return " ".join(text.split())


def final_block(reply):
    """(the lines of a reply's last paragraph, the list items just before it:
    [(its number or letter, or None for a bullet; its text)])."""
    lines = [line.rstrip() for line in reply.strip().splitlines()]
    i, last = len(lines), []
    while i > 0 and lines[i - 1].strip() and not ASK_LIST_ITEM.match(lines[i - 1]) and not ASK_BOLD_NUM.match(lines[i - 1]):
        i -= 1
        last.insert(0, lines[i])
    while i > 0 and not lines[i - 1].strip():
        i -= 1
    items = []
    while i > 0:
        line = lines[i - 1]
        m = ASK_LIST_ITEM.match(line) or ASK_BOLD_NUM.match(line)
        if m:
            items.insert(0, (m.group(1), m.group(2)))
        elif line.strip() and line.startswith(("  ", "\t")):
            pass   # (an item's next line)
        elif not line.strip() and i > 1 and (ASK_LIST_ITEM.match(lines[i - 2]) or lines[i - 2].startswith("  ")):
            pass   # (a loose list)
        else:
            break
        i -= 1
    return last, items


def yesno_langs(ql, rules):
    """The languages whose yes/no start, else verb, the question (lowercase) starts with."""
    found = [code for code, starts in rules["starts"] if ql.startswith(starts)]
    return found or [code for code, verb in rules["verbs"] if verb.match(ql)]


def is_yesno(ql, rules):
    return bool(yesno_langs(ql, rules)) or (len(ql.split()) <= ASK_SHORT_QUESTION and not rules["wh"].match(ql))


def ask_lang(ql, par, rules):
    """The language of a yes/no question: its start's, else the one of most of
    its paragraph's common words (the first table's when none tells)."""
    found = yesno_langs(ql, rules)
    if len(found) == 1:
        return found[0]
    words = re.findall(r"[^\W\d_]+", par.lower())
    pool = found or list(rules["langs"])
    return max(pool, key=lambda code: (sum(1 for w in words if w in rules["common"][code]), -pool.index(code)))


def short_label(text, chars=ASK_LABEL_CHARS):
    """text as a chip shows it: at most chars characters, cut after a whole word (…)."""
    if len(text) <= chars:
        return text
    cut = text[:chars - 1].rsplit(" ", 1)[0] if " " in text[:chars - 1] else text[:chars - 1]
    return cut.rstrip(" ,.;:") + "…"


def chip(label, send=None, recommended=False):
    return {"label": label, "send": label if send is None else send, "recommended": recommended}


def first_up(text):
    return text[:1].upper() + text[1:]


def asks_of(reply):
    """The question Claude's reply ends with, as chips: {"kind": "options"
    (a short list before it: one chip each, "1 · its words", sending "1. its
    words"; recommended: marked so, or the one Claude says it would take),
    "either" (two short halves of an either/or), or "yesno" (Yes and No in
    its language), "choices": [{"label", "send", "recommended"}]}. None:
    no question, several (one click can't answer them), an open one, or
    unsure."""
    if not isinstance(reply, str) or not reply.strip():
        return None
    rules = ask_rules()
    last, items = final_block(reply[-ASK_TAIL:])
    par = plain_md(" ".join(line.strip() for line in last))
    if not par or not QMARK.search(par):
        return None
    sents = [s.strip() for s in ASK_SENTENCE.split(par) if s.strip()]
    questions = [s for s in sents if QMARK.search(s)]
    if len(questions) != 1:
        return None
    q = rules["lead"].sub("", questions[0]).strip()
    ql = q.lower()
    ors = [w for w in rules["ors"] if w in ql]
    # (a yes/no question wins over a list before it, unless it asks either/or; long items are what was done)
    if 2 <= len(items) <= ASK_OPTIONS_MAX and (ors or not is_yesno(ql, rules)):
        words = sorted(len(plain_md(text).split()) for _, text in items)
        if words[len(words) // 2] <= ASK_OPTION_WORDS:
            said = " ".join(sents)
            m = RECOMMEND_NUM.search(said)
            named = (m.group(1) or m.group(2)).lower() if m and RECOMMEND_SAID.search(said) else None
            choices = []
            for n, (num, text) in enumerate(items, 1):
                said = ASK_LABEL_CUT.split(plain_md(text), 1)[0].strip()[:ASK_SEND_CHARS]
                label = short_label(said)
                marked = bool(rules["recommended"].search(text)) or (num or str(n)).lower() == named
                choices.append(chip("%s · %s" % (num, label), "%s. %s" % (num, said), marked) if num else chip(label, said, marked))
            return {"kind": "options", "choices": choices}
    for w in ors:
        if rules["or_not"].search(ql):
            break
        at = list(re.finditer(r"\s%s\s" % re.escape(w.strip()), q, re.I))[-1]
        left = rules["either"].sub("", q[:at.start()].strip())
        if len(left.split()) > ASK_HALF_WORDS:
            left = re.split(r",\s*", left)[-1]
        left, right = left.strip(" ,."), QMARK.sub("", q[at.end():]).strip(" ,.")
        if not (1 <= len(left.split()) <= ASK_HALF_WORDS and 1 <= len(right.split()) <= ASK_HALF_WORDS):
            return None   # (a long either/or)
        return {"kind": "either", "choices": [chip(short_label(first_up(half)), first_up(half)) for half in (left, right)]}
    if rules["wh"].match(ql) or not is_yesno(ql, rules):
        return None
    words = rules["langs"][ask_lang(ql, par, rules)]
    return {"kind": "yesno", "choices": [chip(words["yes"]), chip(words["no"])]}


REPLY_CHARS = 40             # a usual reply: one line you typed, at most this many characters…
REPLY_PATH = re.compile(r"""(?:^|[\s("'`])(?:~|\.{1,2})?/[\w.~-]|\b[\w.-]+/[\w.-]+|(?:^|\s)@\S"""
                        r"""|\b\w+\.(?:py|js|ts|qml|md|json|sh|txt|html|css|mjs|yml|yaml|toml|cfg|ini)\b""")   # …with no path or file
REPLY_DAYS = 60              # what you sent this long ago counts (older uses weigh under 1/16 by then)
REPLY_HALF_LIFE_DAYS = 14.0
REPLY_PROJECT_BOOST = 2.0    # used in this chat's project: counts twice
REPLY_SHARE = 0.2            # a chip: at least this share of what you sent after turns that ended the same way…
REPLY_MIN_CHATS = 2          # …in at least this many chats
REPLY_CHIPS = 4
REPLY_RANKED = 200           # the ones completing what you type
REPLY_BIG_READ = 32 << 20    # a first read this big runs at a low priority
REPLY_CACHE_VERSION = 1
REPLY_USER_LINE = re.compile(rb'"type":\s*"user"')
REPLY_ASSISTANT_LINE = re.compile(rb'"type":\s*"assistant"')
REPLY_STOP = re.compile(rb'"stop_reason":\s*(?:null|"(\w+)")')
REPLY_SIDECHAIN = re.compile(rb'"isSidechain":\s*true')
REPLY_META = re.compile(rb'"isMeta":\s*true')
REPLY_FAILED = re.compile(rb'"is_error":\s*true')
REPLY_WORDS = re.compile(rb'"type":\s*"text"|"thinkingDisplay":\s*"updates"|"isApiErrorMessage"|<synthetic>')
REPLY_CALL = re.compile(rb'"type":\s*"tool_use"')
REPLY_END = re.compile(r"[\s.!?,;:…。！？]+$")
DAY_MS = 86400000


def usual_reply(text, picture=False):
    """A prompt of yours that can be a usual reply: one short line you typed,
    with no picture, path or file, not a / or ! command, nor pasted text, nor
    what Talpy Den sends to keep a chat going."""
    return (len(text) <= REPLY_CHARS and "\n" not in text and not picture and not text.startswith(("/", "!"))
            and "[Pasted text" not in text and "[Image" not in text and text not in (cs.CONTINUE_PROMPT, cs.RETRY_PROMPT)
            and not REPLY_PATH.search(text))


def reply_key(text):
    """A reply as replies are compared: case, outer quotes, final
    punctuation and extra spaces left out."""
    import unicodedata
    t = unicodedata.normalize("NFKC", text).casefold().strip().strip("\"'`“”‘’")
    return " ".join(REPLY_END.sub("", t).split())


def typos_apart(a, b, cap):
    """Damerau (optimal string alignment) distance of a and b, stopping above cap."""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    before, prev = None, list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        best = i
        for j in range(1, len(b) + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] != b[j - 1]))
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], before[j - 2] + 1)
            best = min(best, cur[j])
        if best > cap:
            return cap + 1
        before, prev = prev, cur
    return prev[-1]


def same_reply(a, b):
    """Two spellings of one reply (reply_key'd): a few typos apart, more for
    a longer one; words under 5 letters only as they are."""
    if a == b:
        return True
    n = min(len(a), len(b))
    if n < 5:
        return False
    allowed = 1 if n < 12 else 2 if n < 25 else 3
    return typos_apart(a, b, allowed) <= allowed


def project_of(folder):
    """The repository a chat's folder belongs to (a worktree's is its repository's)."""
    p = re.sub(r"/\.claude/worktrees/[^/]+.*$", "", folder or "")
    return re.sub(r"/\.git/.*$", "", p)


def reply_records(path, start, kept):
    """Your prompts that can be usual replies in a transcript, from byte
    start on: ([[at ms, chat, how the turn before it ended (TurnEnd.state),
    the text, its entry's id, its project]], where it was read to (after its
    last whole line), the turn there (TurnEnd.kept), for the next read).
    Only what tells a turn's end is read: a tool call's or result's line
    isn't parsed."""
    with open(path, "rb") as f:
        f.seek(start)
        data = f.read()
    whole = data.rfind(b"\n") + 1
    end, out = TurnEnd(kept), []
    for line in data[:whole].split(b"\n"):
        user = REPLY_USER_LINE.search(line) is not None
        if not user and not REPLY_ASSISTANT_LINE.search(line):
            continue
        if REPLY_SIDECHAIN.search(line):
            continue
        if user and b'"tool_result"' in line and not REPLY_META.search(line):
            end.tool_result(REPLY_FAILED.search(line) is not None)
            continue
        if not user and not REPLY_WORDS.search(line):
            # (a tool call or a thinking block with no words for you: none of Claude's words)
            calls = REPLY_CALL.search(line) is not None
            stop = REPLY_STOP.search(line)
            reason = stop.group(1).decode() if stop and stop.group(1) else None
            end.started = True
            if calls:
                end.tool, end.turn = True, None
            end.last = "step" if calls or reason in ("tool_use", "pause_turn") else "open" if reason is None else "end"
            continue
        try:
            e = json.loads(line)
        except (ValueError, RecursionError):
            continue
        if not isinstance(e, dict) or e.get("isSidechain"):
            continue
        msg, blocks = cs.blocks_of(e)
        if not user:
            end.assistant(e, msg, blocks)
            continue
        if e.get("isCompactSummary") or e.get("isMeta"):
            continue
        if any(c.get("type") == "tool_result" for c in blocks):
            end.tool_result(any(c.get("type") == "tool_result" and c.get("is_error") for c in blocks))
            continue
        text = cs.human_prompt(e)
        if text is None:
            if cs.message_text(msg).strip().startswith(INTERRUPTED):
                end.interrupted()
            continue
        if end.started and usual_reply(text, any(c.get("type") == "image" for c in blocks)):
            cwd = e.get("cwd") if isinstance(e.get("cwd"), str) else ""
            out.append([cs.to_ms(e.get("timestamp")), e.get("sessionId") if isinstance(e.get("sessionId"), str) else path.stem,
                        end.state(), text, e.get("uuid") if isinstance(e.get("uuid"), str) else "", project_of(cwd)])
        end.prompt()
    return out, start + whole, end.kept()


def lower_priority():
    """This run, nice'd and at idle I/O (a long first read: nothing else waits on it)."""
    try:
        os.nice(10)
    except OSError:
        pass
    ionice = shutil.which("ionice")
    if ionice:
        try:
            subprocess.run([ionice, "-c3", "-p", str(os.getpid())], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        except (OSError, subprocess.SubprocessError):
            pass


def reply_history(cache_root, profile, now=None):
    """The usual-reply prompts of a profile's chats of the last REPLY_DAYS
    (reply_records), each once (a resumed copy repeats its chat's entries).
    What each transcript gave is kept in the cache folder (replies/, only
    yours to read) by its size and time: one that grew is read from where
    it was left, one that changed otherwise is read again."""
    now = time.time() if now is None else now
    since = now - REPLY_DAYS * 86400
    kept_path = Path(cache_root) / "replies" / ("%s.json" % cs.short_id(str(profile.path)))
    kept = cs.read_json(kept_path)
    files = kept.get("files") if isinstance(kept, dict) and kept.get("version") == REPLY_CACHE_VERSION else None
    files = files if isinstance(files, dict) else {}
    found = {}
    try:
        folders = [d for d in os.scandir(str(profile.path / "projects")) if d.is_dir(follow_symlinks=False)]
    except OSError:
        folders = []
    for d in folders:
        try:
            for f in os.scandir(d.path):
                if f.name.endswith(".jsonl") and f.is_file(follow_symlinks=False):
                    st = f.stat(follow_symlinks=False)
                    if st.st_mtime >= since:
                        found[f.path] = st
        except OSError:
            continue
    todo = []
    for name, st in found.items():
        was = files.get(name)
        if not isinstance(was, dict) or was.get("ino") != st.st_ino or st.st_size < was.get("offset", 0) \
                or (st.st_size == was.get("size") and st.st_mtime_ns != was.get("mtime")):
            todo.append((name, st, 0, None, []))   # (new, or written again)
        elif st.st_size != was.get("size") or st.st_mtime_ns != was.get("mtime"):
            todo.append((name, st, was.get("offset", 0), was.get("turn"), was.get("records") or []))
    if sum(st.st_size - start for _, st, start, _, _ in todo) > REPLY_BIG_READ:
        lower_priority()
    changed = len(files) != len(found) or bool(todo)
    files = {name: was for name, was in files.items() if name in found}
    for name, st, start, turn, records in todo:
        try:
            more, offset, turn = reply_records(Path(name), start, turn)
        except OSError:
            files.pop(name, None)
            continue
        files[name] = {"ino": st.st_ino, "size": st.st_size, "mtime": st.st_mtime_ns, "offset": offset, "turn": turn,
                       "records": records + more}
    if changed:
        try:
            cs.private_dir(kept_path.parent)
            cs.write_json_atomic(kept_path, {"version": REPLY_CACHE_VERSION, "files": files}, private=True)
        except OSError:
            pass
    seen, out = set(), []
    for was in files.values():
        for r in was.get("records") or []:
            if not (isinstance(r, list) and len(r) == 6) or r[0] < since * 1000 or (r[4] and r[4] in seen):
                continue
            seen.add(r[4])
            out.append(r)
    out.sort(key=lambda r: r[0])
    return out


def usual_replies(records, now_ms, project, hidden=()):
    """Your usual replies from records (reply_history, oldest first) at
    now_ms, for a chat in project: {"chips": {how a turn ended: [the replies
    to show after one, the most used first]}, "ranked": [every reply, the most
    used first: what you type is completed from them]}. A reply weighs, in
    each chat it was sent in, its last use there, halved every
    REPLY_HALF_LIFE_DAYS, twice in this project; near-identical spellings are
    one reply, shown as you usually type it. A chip: sent after turns that
    ended that way in REPLY_MIN_CHATS chats or more, and at least REPLY_SHARE
    of all that was sent then. hidden: replies you don't want suggested."""
    merged, keys = {}, []        # reply_key -> its reply's key; the keys, oldest first
    per, pooled, spellings = {}, {}, {}
    for at, chat, state, text, _, where in records:
        k = reply_key(text)
        if k not in merged:
            merged[k] = next((key for key in keys if same_reply(k, key)), k)
            if merged[k] == k:
                keys.append(k)
        key = merged[k]
        w = 0.5 ** (max(0, now_ms - at) / DAY_MS / REPLY_HALF_LIFE_DAYS) * (REPLY_PROJECT_BOOST if where == project else 1.0)
        for table, slot in ((per, (state, key)), (pooled, key)):
            chats = table.setdefault(slot, {})
            chats[chat] = max(chats.get(chat, 0.0), w)
        spellings.setdefault(key, {})
        spellings[key][text] = spellings[key].get(text, 0) + 1

    def shown(key):
        said = spellings[key]
        return max(said, key=lambda t: said[t])   # (the usual spelling; the first one of those as often)

    def allowed(key):
        return key not in hidden and reply_key(shown(key)) not in hidden
    totals = {}
    for (state, key), chats in per.items():
        totals[state] = totals.get(state, 0.0) + sum(chats.values())
    found = {}
    for (state, key), chats in per.items():
        score = sum(chats.values())
        if len(chats) >= REPLY_MIN_CHATS and totals[state] and score / totals[state] >= REPLY_SHARE and allowed(key):
            found.setdefault(state, []).append((score, key))
    chips = {state: [shown(key) for _, key in sorted(got, key=lambda s: -s[0])[:REPLY_CHIPS]] for state, got in found.items()}
    ranked = sorted(pooled, key=lambda key: -sum(pooled[key].values()))
    return {"chips": chips, "ranked": [shown(key) for key in ranked if allowed(key)][:REPLY_RANKED]}


def hidden_path(cache_root):
    return cs.state_dir(cache_root) / "replies-hidden.json"


def hidden_replies(cache_root):
    data = cs.read_json(hidden_path(cache_root), 1 << 20)
    return {h for h in data.get("hidden", []) if isinstance(h, str)} if isinstance(data, dict) else set()


def hide_reply(cache_root, text, on=True):
    """Don't suggest text again (on), or do again ("-": all of them). Kept
    for this computer, beside its other settings."""
    hidden = hidden_replies(cache_root)
    key = reply_key(text or "")
    if on and not key:
        return False, "Nothing to hide"
    if on:
        hidden.add(key)
    elif text == "-":
        hidden = set()
    else:
        hidden.discard(key)
    path = hidden_path(cache_root)
    cs.private_dir(path.parent)
    cs.write_json_atomic(path, {"version": 1, "hidden": sorted(hidden)}, private=True)
    return True, ("It won't be suggested again" if on else "Suggested again")


def chat_replies(home, extra_dirs, cache_root, chat_id, profile_key=None, cwd=None, now=None):
    """--replies: your usual replies for a chat (usual_replies), from the
    chats on its account. chat_id "-" with cwd: a new chat's, in that folder
    on the profile profile_key."""
    if chat_id == "-" and cwd:
        profile = next((p for p in cs.discover_profiles(home, extra_dirs) if cs.matches_profile(p, profile_key)), None)
        if profile is None:
            return {"ok": False, "message": f"No Claude profile called {profile_key}"}
        cwd = os.path.expanduser(cwd)
    elif not cs.valid_id(chat_id):
        return {"ok": False, "message": f"Not a chat: {chat_id}"}
    else:
        profile, path = find_transcript(home, extra_dirs, chat_id, profile_key)
        if path is None:
            return {"ok": False, "message": NO_CHAT}
        _, cwd, _ = cs.read_chat_info(path, path.stat().st_size)
        cwd = cwd or cs.chat_folder(path) or ""
    now = time.time() if now is None else now
    found = usual_replies(reply_history(cache_root, profile, now), now * 1000, project_of(cwd), hidden_replies(cache_root))
    return dict(ok=True, **found)


# ---------------------------------------------------------------- keyboard answers
#
# Two global shortcuts answer the oldest prompt a chat waits on (relayed by
# the hook): Allow once (a plan: Approve) and Deny (a plan: Keep planning),
# then a note on screen says what was answered (Plasma's on-screen display,
# else a notification). --shortcuts on puts a desktop file with the two
# actions in ~/.local/share/kglobalaccel (Plasma loads those at login, and
# runs an action's command when its keys are pressed) and registers them
# with kglobalaccel right away over D-Bus, with Meta+Alt+Y and Meta+Alt+N
# where no other shortcut has them (else none: you pick them in System
# Settings → Shortcuts → Talpy Den). --shortcuts off takes them out.

SHORTCUTS_COMPONENT = "org.wzaielamri.talpyden.answers.desktop"
SHORTCUT_ACTIONS = (  # (action, its name, default keys, the same as Qt's key code)
    ("allow", "Allow the oldest prompt", "Meta+Alt+Y", 0x10000000 | 0x08000000 | 0x59),
    ("deny", "Deny the oldest prompt", "Meta+Alt+N", 0x10000000 | 0x08000000 | 0x4E),
)
KGLOBALACCEL = ("--dest", "org.kde.kglobalaccel", "--object-path", "/kglobalaccel")


def oldest_request(cache_root):
    """The oldest relayed request a key can answer (not a question: those
    take answers), and whether a question waits too."""
    requests = list(cs.permission_requests(cache_root).values())
    usable = [r for r in requests if r.get("tool") != cs.ASK_TOOL]
    oldest = min(usable, key=lambda r: r.get("at") or 0) if usable else None
    return oldest, len(usable) < len(requests)


def chat_name(req):
    path = req.get("transcript")
    try:
        name, _, _ = cs.read_chat_info(Path(path), Path(path).stat().st_size) if isinstance(path, str) else ("", "", "")
    except (OSError, ValueError, TypeError):
        name = ""
    return name or "A chat"


def answer_oldest(cache_root, decision):
    """Allow (a plan: approve) or deny (a plan: keep planning) the oldest
    prompt: (ok, what to say)."""
    if decision not in ("allow", "deny"):
        return False, f"Not an answer: {decision}"
    req, question = oldest_request(cache_root)
    if req is None:
        return False, "A question waits: answer it in the panel" if question else "No chat waits for a permission"
    plan = req.get("tool") == cs.PLAN_TOOL
    ok, said = answer_request(cache_root, req["id"], ("approve" if decision == "allow" else "keep") if plan else decision)
    if not ok:
        return False, said
    return True, f"{chat_name(req)}: {said} · {cs.request_view(req)['line']}"


def show_note(text, ok):
    """A note on screen: Plasma's on-screen display, else a notification."""
    icon = "dialog-ok-apply" if ok else "dialog-information"
    gdbus = shutil.which("gdbus")
    tries = [[gdbus, "call", "--session", "--dest", "org.kde.plasmashell", "--object-path", "/org/kde/osdService",
              "--method", "org.kde.osdService.showText", icon, text]] if gdbus else []
    if shutil.which("notify-send"):
        tries.append(["notify-send", "--app-name=Talpy Den", f"--icon={icon}", "--expire-time=4000", "Talpy Den", text])
    for cmd in tries:
        try:
            if subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5).returncode == 0:
                return True
        except (OSError, subprocess.TimeoutExpired):
            continue
    return False


def shortcuts_file(home):
    data = Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share")
    return data / "kglobalaccel" / SHORTCUTS_COMPONENT


def desktop_quote(arg):
    """An argument of a desktop file's Exec (its quoting rules)."""
    if re.fullmatch(r"[\w@%+=:,./-]+", arg):
        return arg
    return '"' + re.sub(r'(["`$\\])', r"\\\1", arg) + '"'


def shortcuts_desktop(script, free=None):
    """The desktop file with the two actions (script: this pane.py); keys
    only for the actions in free (None: all)."""
    run = lambda action: " ".join(desktop_quote(a) for a in ("python3", "-I", str(script), "--oldest", action, "--osd"))
    lines = ["[Desktop Entry]", "Type=Application", "Name=Talpy Den",
             "Comment=Answer the oldest permission prompt of your Claude chats", "Icon=dialog-question", "NoDisplay=true",
             "Exec=true", "Actions=" + "".join(a + ";" for a, _, _, _ in SHORTCUT_ACTIONS), ""]
    for action, name, keys, _ in SHORTCUT_ACTIONS:
        given = keys if free is None or action in free else ""
        lines += [f"[Desktop Action {action}]", f"Name={name}", f"Exec={run(action)}", f"X-KDE-Shortcuts={given}", ""]
    return "\n".join(lines)


def kglobalaccel(method, *args):
    """Call kglobalaccel over D-Bus: (ok, its answer)."""
    gdbus = shutil.which("gdbus")
    if gdbus is None:
        return False, "gdbus isn't installed"
    try:
        r = subprocess.run([gdbus, "call", "--session", *KGLOBALACCEL, "--method", "org.kde.KGlobalAccel." + method, *args],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    return r.returncode == 0, (r.stdout if r.returncode == 0 else r.stderr).decode(errors="replace").strip()


def gv_strings(items):
    return "[" + ", ".join(json.dumps(i) for i in items) + "]"


def key_owners(code):
    """The components that have key code (Qt's) as a global shortcut, or None
    (kglobalaccel didn't answer)."""
    ok, out = kglobalaccel("getGlobalShortcutsByKey", str(code))
    return re.findall(r"\('([^']*)'", out) if ok else None


def shortcuts(home, on, script=None):
    """Keyboard answers on or off (or, on None, whether they're on): (ok, message)."""
    path = shortcuts_file(home)
    if on is None:
        return True, "on" if path.is_file() else "off"
    if not on:
        for action, _, _, _ in SHORTCUT_ACTIONS:
            kglobalaccel("unregister", json.dumps(SHORTCUTS_COMPONENT), json.dumps(action))
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return True, "Keyboard answers are off"
    # (a key another shortcut has stays its: that action gets none)
    owners = {action: key_owners(code) for action, _, _, code in SHORTCUT_ACTIONS}
    free = {a for a, o in owners.items() if not o or set(o) <= {SHORTCUTS_COMPONENT}}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(shortcuts_desktop(script or Path(__file__).resolve(), free), encoding="utf-8")
    os.replace(tmp, path)
    for action, name, keys, code in SHORTCUT_ACTIONS:
        ids = gv_strings([SHORTCUTS_COMPONENT, action, "Talpy Den", name])
        ok, out = kglobalaccel("doRegister", ids)
        if not ok:
            return True, "Keyboard answers are set up for your next login (Plasma's shortcuts didn't answer: " + out + ")"
        keys_now = f"[([{code}],)]" if action in free else "@a(ai) []"
        kglobalaccel("setShortcutKeys", ids, keys_now, "1")   # (its default)
        kglobalaccel("setShortcutKeys", ids, keys_now, "6")   # (and now: SetPresent, NoAutoloading)
    taken = [keys for action, _, keys, _ in SHORTCUT_ACTIONS if action not in free]
    if taken:
        return True, ("Keyboard answers are on; " + " and ".join(taken) + (" is" if len(taken) == 1 else " are")
                      + " another shortcut's: pick yours in System Settings → Shortcuts → Talpy Den")
    return True, "Keyboard answers are on: Meta+Alt+Y allows the oldest prompt, Meta+Alt+N denies it"


# ---------------------------------------------------------------- answering in tmux with keys

def tmux_base(entry):
    tmux = shutil.which("tmux", path=os.pathsep.join([os.environ.get("PATH", ""), "/usr/bin", "/usr/local/bin", "/bin"]))
    pane = entry.get("tmux") if isinstance(entry, dict) else None
    if tmux is None or not isinstance(pane, str) or not pane:
        return None, None
    socket = cs.tmux_socket(entry["pid"])
    target = pane.rsplit(".", 1)[-1] if "." in pane else pane  # its pane id, e.g. %3
    return [tmux, *(["-S", socket] if socket else [])], target


def tmux_run(base, args, data=None):
    try:
        r = subprocess.run(base + args, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"tmux didn't answer: {exc}"
    if r.returncode != 0:
        return False, "tmux: " + (r.stderr.decode(errors="replace").strip() or f"exit {r.returncode}")
    return True, r.stdout.decode(errors="replace")


_pastes = [0]
TYPED_OUT = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def as_typed(text):
    """text to paste into a chat's terminal: its control characters left out
    (but tabs and new lines; a CR is one), so nothing in it ends the paste
    early and presses keys (an ESC[201~ in a plan's line, then Ctrl+C and a
    !command); as VS Code's asPaste"""
    return TYPED_OUT.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))


def tmux_type(entry, text):
    """Paste text into a chat's tmux pane and send it (Enter): (ok, message)."""
    base, target = tmux_base(entry)
    if base is None:
        return False, "It doesn't run in tmux (or tmux isn't installed)"
    # a buffer of its own: a reply typed meanwhile (each runs in its own
    # process) would else paste this text into its chat, or take it away
    _pastes[0] += 1
    buffer = f"talpy-den-{os.getpid()}-{_pastes[0]}"
    for args, data in ((["load-buffer", "-b", buffer, "-"], as_typed(text).encode()),
                       (["paste-buffer", "-p", "-d", "-b", buffer, "-t", target], None),
                       (["send-keys", "-t", target, "Enter"], None)):
        if args[0] == "send-keys":
            time.sleep(0.3)  # (Claude takes the paste in first)
        ok, out = tmux_run(base, args, data)
        if not ok:
            if args[0] == "paste-buffer":
                tmux_run(base, ["delete-buffer", "-b", buffer])
            return False, out
    return True, ""


DIALOG_OPTION = re.compile(r"^\s*(?:❯\s*)?(\d)\.\s+(.*)$")


def dialog_options(screen):
    """{number: text} of the permission dialog on a chat's screen, if it shows one."""
    if "Do you want to" not in screen:
        return {}
    options = {}
    for line in screen.splitlines():
        m = DIALOG_OPTION.match(line)
        if m:
            options[m.group(1)] = m.group(2).strip()
    return options


ASKS_ELSE = "It asks something else now"


def answer_with_keys(entry, decision, note="", still=None):
    """Answer the permission dialog of a chat in tmux by pressing its option's
    number (Deny with a note: No, then the note as your next message). still:
    a check, made just before a key is pressed, that the chat still asks what
    you answered (else nothing is pressed: (False, ASKS_ELSE))."""
    if decision not in DECISIONS:
        return False, f"Not an answer: {decision}"
    if decision == "answer":
        return False, "Answer its questions in the chat"
    base, target = tmux_base(entry)
    if base is None:
        return False, "It doesn't run in tmux: answer it in the chat"
    ok, screen = tmux_run(base, ["capture-pane", "-p", "-t", target])
    if not ok:
        return False, screen
    options = dialog_options(screen)
    if not options:
        return False, "Its screen shows no permission question now"
    if decision == "allow":
        key = next((n for n, t in sorted(options.items()) if t.startswith("Yes")), None)
    elif decision == "always":  # (a command's "and don't ask again for …", an edit's "allow all edits during this session")
        key = next((n for n, t in sorted(options.items()) if t.startswith(("Yes, and don", "Yes, allow "))), None)
    else:
        key = next((n for n, t in sorted(options.items()) if t == "No" or t.startswith("No,") or t.startswith("No ")), None)
    if key is None:
        return False, "That answer isn't one of the choices it shows"
    if still is not None and not still():
        return False, ASKS_ELSE
    ok, out = tmux_run(base, ["send-keys", "-t", target, key])
    if not ok:
        return False, out
    if decision == "deny" and (note or "").strip():
        time.sleep(0.6)  # ("What should Claude do instead?")
        ok, out = tmux_type(entry, note.strip())
        if not ok:
            return False, "Denied, but the note didn't go in: " + out
        return True, "Denied, and your note went to the chat"
    return True, {"allow": "Allowed", "always": "Allowed, and from now on", "deny": "Denied"}[decision]


# ---------------------------------------------------------------- sending a message

HOWS = ("auto", "background", "copy", "enter")


def vscode_prompt_link(session_id, text):
    """Encoded twice, as jump.link_query does: VS Code decodes the query once
    before the extension's URLSearchParams decodes it again (else an & ends
    the message there and a + becomes a space)."""
    from urllib.parse import urlencode
    return "vscode://anthropic.claude-code/open?" + urlencode({"session": session_id, "prompt": text}).replace("%", "%25")


def host_vscode_link(answer, ids, text):
    """An SSH host's answer to --send that the chat is in VS Code: its link
    made here from what was asked (the chat's id the host found it by, of
    ids, else the first, and your text), never one the host chose, which
    would be opened on this computer. No link when no id is a chat's."""
    if answer.get("how") != "vscode":
        return answer
    links = [vscode_prompt_link(i, (text or "").strip()) for i in ids if cs.valid_id(i or "")]
    if links:
        answer["link"] = answer.get("link") if answer.get("link") in links else links[0]
    else:
        answer.pop("link", None)
    return answer


def go_on_in_background(home, extra_dirs, profile, chat_id, text, claude, scoped=True, hook=None):
    """claude --bg --resume with your message. scoped: in a systemd scope of
    its own (jump.scope_prefix), as the widget's go-ons and tasks start: run
    from the widget, Claude's background service would be in plasmashell's
    group of processes, and a restart of plasmashell (by hand, after an update,
    a crash) would end it, and every background chat it runs, mid-turn. Not on
    an SSH host (--remote). hook: the permission hook it goes on with
    (chat_hook: a background chat has no terminal to ask in)."""
    prefix = []
    if scoped:
        import jump
        prefix = jump.scope_prefix("claude")
    answer = cs.continue_chat(home, extra_dirs, profile.key, chat_id, text=text, claude=claude, prefix=prefix,
                              force=True, settings=hook)
    if answer.get("ok"):
        answer["message"] = "Sent: the chat goes on with it in the background" + (
            f" ({answer['id']})" if answer.get("id") else "")
    return answer


def send(home, extra_dirs, profile_key, chat_id, text, session_id=None, how="auto", claude=None, scoped=True):
    """Send your message to a chat the way it takes one (cs.reply_route):
    {"ok", "message", "how": "typed"|"background"|"vscode"|"copy"|"ask",
    "link" (vscode), "copied" (copy)}. how "ask": the chat runs in a
    terminal that takes no text from outside, and you choose (how
    background or copy). scoped: a chat it wakes in the background in a
    systemd scope of its own (go_on_in_background), with the permission hook
    for it (chat_hook); not on an SSH host, where Talpy Den has no hook of
    its own."""
    text = (text or "").strip()
    if not text:
        return {"ok": False, "message": "Write your message first"}
    if how not in HOWS:
        return {"ok": False, "message": f"Not a way to send: {how}"}
    if not cs.valid_id(chat_id):
        return {"ok": False, "message": f"Not a chat: {chat_id}"}
    profiles = cs.discover_profiles(home, extra_dirs)
    profile, path = find_transcript(home, extra_dirs, chat_id, profile_key)
    if path is None:
        return {"ok": False, "message": NO_CHAT}
    if how == "copy":
        return copy_answer(text)
    entry = None
    for sid in (session_id, chat_id):
        if cs.valid_id(sid or ""):
            entry = cs.find_chat_entry(home, extra_dirs, sid)
            if entry is not None:
                break
    row = {"pid": entry.get("pid") if entry else None, "kind": entry.get("kind") if entry else None,
           "entrypoint": entry.get("entrypoint") if entry else "", "tmux": bool(entry and entry.get("tmux"))}
    route = cs.reply_route(row)
    state = cs.session_state(entry) if entry else "done"
    if route == "tmux":
        if state == "waiting":
            return {"ok": False, "message": "It's asking you something: answer that first"}
        ok, message = tmux_type(entry, text)
        return {"ok": ok, "how": "typed", "message": "Sent (typed into its tmux pane)" if ok else message}
    if route == "vscode":
        return {"ok": True, "how": "vscode", "link": vscode_prompt_link(entry["sessionId"], text),
                "message": "Your message is in the chat's input in VS Code: press Enter there"}
    if route == "terminal" and how != "background":
        return {"ok": True, "how": "ask", "message": "Its terminal takes no text from outside: send it, and the chat "
                "goes on in the background, or copy it and open its tab"}
    claude = claude or cs.find_claude(home, ask_shell=True)
    if claude is None:
        return {"ok": False, "message": "No claude command found"}
    if entry is not None and entry.get("kind") == "bg":
        job_id = entry.get("jobId")
        if not cs.valid_id(job_id or ""):
            return {"ok": False, "message": "It runs in a background chat Talpy Den can't stop"}
        # (one that asks you something isn't stopped for it: typed in, it would land in its question,
        # so that's answered first; the pane's reply answers it, through its prompt's request)
        if state == "waiting":
            return {"ok": False, "message": "It's asking you something: answer that first"}
        runs_on = next((p for p in profiles if cs.matches_profile(p, profile_key)), profile)
        # (its session takes it in where it is, as `claude agents` answers one, queued while it works: no
        # stop, so a terminal that shows it stays on it)
        if cs.reply_to_background(runs_on, job_id, text)[0]:
            return {"ok": True, "how": "typed", "message": "Sent (typed into the background chat)"}
        ok, message = cs.stop_background(runs_on, job_id, cs.read_job([runs_on], job_id), home, claude)
        if not ok:
            return {"ok": False, "message": message}
    elif entry is not None:
        if state != "idle":
            return {"ok": False, "message": "It's at work: send it when this turn ends"}
        ok, message = cs.stop_chat(entry)
        if not ok:
            return {"ok": False, "message": message}
    hook = chat_hook(home, next((p for p in profiles if cs.matches_profile(p, profile_key)), profile)) if scoped else None
    answer = go_on_in_background(home, extra_dirs, profile, chat_id, text, claude, scoped, hook)
    answer["how"] = "background"
    return answer


def interrupt(home, extra_dirs, profile_key, chat_id, session_id=None):
    """Talpy Chat's Stop for a chat at work (cs.interrupt_chat_by_id: Ctrl+C
    in its tmux pane, Esc into a background session), found by the session
    that has it open (session_id) or its chat id: (ok, message)."""
    ids = [i for i in dict.fromkeys((session_id, chat_id)) if cs.valid_id(i or "")]
    if not ids:
        return False, f"Not a chat: {chat_id}"
    for sid in ids:
        found = cs.find_chat_live(home, extra_dirs, sid, profile_key)
        if found is not None:
            return cs.interrupt_live(*found)
    return False, "That chat isn't running any more"


def start_chat(home, extra_dirs, profile_key, folder, text, model=None, effort=None, mode=None, plan=None,
               plan_profile=None, claude=None, scoped=True):
    """A new chat Talpy Chat starts with your first message (text; or a
    plan's, with what you add): in the background on the profile, in folder
    (claude --bg, in a systemd scope of its own: go_on_in_background), with
    that model, effort and permission mode, and the permission hook for it
    alone (chat_hook), so what it asks is answered in Talpy Chat. Only in a
    folder Claude trusts (a background chat can't ask). {"ok", "message",
    "how": "background", "id": its job's short id, "chat": its chat id
    (from its job's record), "profileDir"}."""
    text = (text or "").strip()
    if not text and not plan:
        return {"ok": False, "message": "Write your message first"}
    profiles = cs.discover_profiles(home, extra_dirs)
    profile = next((p for p in profiles if cs.matches_profile(p, profile_key)), None)
    if profile is None:
        return {"ok": False, "message": f"No Claude profile called {profile_key}"}
    try:
        options = cs.chat_options(model, effort, mode)
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}
    plan_path = None
    if plan:
        plan_path = cs.find_plan(profiles, plan, plan_profile, home)
        if plan_path is None:
            return {"ok": False, "message": "That plan isn't there any more"}
    claude = claude or cs.find_claude(home, ask_shell=True)
    if claude is None:
        return {"ok": False, "message": "No claude command found"}
    hook = chat_hook(home, profile) if scoped else None
    options = (["--settings", hook] if hook else []) + options + cs.picture_options(home, text)
    prefix = []
    if scoped:
        import jump
        prefix = jump.scope_prefix("claude")
    folder = os.path.expanduser(folder) if isinstance(folder, str) and folder.strip() else str(home)
    ok, message, job = cs.start_background(profile, folder, cs.task_prompt(text, plan_path, home), home, claude,
                                           prefix=prefix, options=options)
    if not ok:
        return {"ok": False, "message": message}
    chat = job_chat(profile, job)
    if chat is None:
        return {"ok": False, "message": f"It started ({job}), but its chat isn't there to show: find it in the list"}
    return {"ok": True, "how": "background", "id": job, "chat": chat, "profileDir": profile.key,
            "message": "Started in the background on " + profile.label}


JOB_RECORD_WAIT_S = 2.0


def job_chat(profile, job, wait=JOB_RECORD_WAIT_S):
    """The chat id of a background job claude --bg started (its record,
    jobs/<job>/state.json, names it; claude writes it before it answers, so
    a moment's wait at the most)."""
    if not cs.valid_id(job or ""):
        return None
    deadline = time.time() + wait
    while True:
        record = cs.read_json(profile.path / "jobs" / job / "state.json")
        chat = record.get("sessionId") if isinstance(record, dict) else None
        if isinstance(chat, str) and cs.valid_id(chat) and chat.startswith(job):
            return chat
        if time.time() >= deadline:
            return None
        time.sleep(0.1)


def send_later(home, extra_dirs, profile_key, chat_id, text, session_id=None, how="auto", host="", name=""):
    """Queue a message for when the chat's turn ends (the widget sends it then: jump.py --start-queued)."""
    text = (text or "").strip()
    if not text:
        return False, "Write your message first"
    if how not in HOWS:
        return False, f"Not a way to send: {how}"
    entry = cs.queue_entry(profile_key, "", text, int(time.time() * 1000), host, chat=chat_id, name=name)
    entry.update(afterTurn=True, how=how, session=session_id if cs.valid_id(session_id or "") else None)
    cache_root = cs.cache_dir(home)
    for old in cs.load_queue(cache_root):  # (one message waits per chat: the new one replaces it)
        if old.get("afterTurn") and old.get("chat") == chat_id and (old.get("host") or "") == (host or ""):
            cs.change_queue(cache_root, take=old["id"])
    cs.change_queue(cache_root, add=entry)
    return True, "It's sent when this turn ends"


ENTER_COPIES = "Its terminal takes no text from outside, so "


def copy_answer(text, why=""):
    """Your message on the clipboard, for you to paste into the chat (why: what comes first)."""
    copied = copy_to_clipboard(text)
    said = why + "your message is in the clipboard: paste it there" if why \
        else "Your message is in the clipboard: paste it into the chat"
    return {"ok": True, "how": "copy", "copied": copied, "text": "" if copied else text,
            "message": said if copied else "Couldn't use the clipboard here"}


def copy_to_clipboard(text):
    """Put text on the clipboard (wl-copy on Wayland, else xclip or xsel): whether it worked."""
    tools = ([["wl-copy"]] if os.environ.get("WAYLAND_DISPLAY") else []) \
        + [["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]]
    for args in tools:
        exe = shutil.which(args[0])
        if exe is None:
            continue
        try:  # (they stay on to hand it out: not with our output, which the widget waits for)
            r = subprocess.run([exe, *args[1:]], input=text.encode(), stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if r.returncode == 0:
            return True
    return False


# ---------------------------------------------------------------- review: what a chat changed

def read_bytes(path):
    """A plain file's content, else None (a pipe put there isn't waited for)."""
    return cs.bytes_to_compare(path, None)[0]


def git(folder, *args, data=None, timeout=20, literal=True):
    """(ok, stdout, stderr) of git in folder. Paths are names, not patterns
    (else a chat's a[1].txt would take your a1.txt along; literal=False for
    a command that takes no patterns and refuses the option: check-ignore)."""
    if not shutil.which("git"):
        return False, "", "git isn't installed"
    try:
        r = subprocess.run(["git", *(["--literal-pathspecs"] if literal else []), "-C", folder, *args], input=data,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, "", str(exc)
    return r.returncode == 0, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")


def git_root(folder):
    ok, out, _ = git(folder, "rev-parse", "--show-toplevel", timeout=5) if os.path.isdir(folder) else (False, "", "")
    return out.strip() if ok and out.strip() else None


def git_original(path, missing=b""):
    """A file's content as of git's HEAD: missing (b"": new since) for a
    file git doesn't have there, None outside a git repository."""
    root = git_root(os.path.dirname(path))
    if root is None:
        return None
    rel = os.path.relpath(os.path.realpath(path), os.path.realpath(root))
    try:
        r = subprocess.run(["git", "-C", root, "show", f"HEAD:{rel}"], stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else missing


def git_executable(path):
    """Does git's last commit have path as an executable file?"""
    folder = os.path.dirname(path)
    while folder and not os.path.isdir(folder):
        folder = os.path.dirname(folder)
    root = git_root(folder) if folder else None
    if root is None:
        return False
    ok, out, _ = git(root, "ls-tree", "HEAD", "--", os.path.relpath(os.path.realpath(path), os.path.realpath(root)),
                     timeout=5)
    return ok and out.startswith("100755 ")


def backup_content(profiles, sessions, name):
    """A file-history backup's content, from the folder of a session that wrote the chat."""
    for p in profiles:
        for sid in sessions:
            data = read_bytes(p.path / "file-history" / sid / name)
            if data is not None:
                return data
    return None


def tool_originals(transcripts, wanted):
    """{file: (its content before the chat's first Edit or Write of it,
    whether that call made it (then b""))} for the files in wanted, from what
    those calls gave back (toolUseResult: type "create", else originalFile),
    oldest first. A first call that gave neither leaves the file out."""
    found, seen = {}, set()
    for t in transcripts:
        try:
            f = open(t, "rb")
        except OSError:
            continue
        with f:
            for line in f:
                if b'"toolUseResult"' not in line or b'"filePath"' not in line:
                    continue
                try:
                    e = json.loads(line)
                except (ValueError, RecursionError):
                    continue
                r = e.get("toolUseResult") if isinstance(e, dict) else None
                if not isinstance(r, dict) or not isinstance(r.get("filePath"), str) or not r["filePath"].startswith("/"):
                    continue
                full = os.path.normpath(r["filePath"])
                if full not in wanted or full in seen:
                    continue
                seen.add(full)
                if r.get("type") == "create":
                    found[full] = (b"", True)
                elif isinstance(r.get("originalFile"), str):
                    found[full] = (r["originalFile"].encode("utf-8"), False)  # ("": it was there, empty)
    return found


def originals(profiles, path, cwd):
    """[(file, its content before the chat (b"" if it didn't exist; None if
    unknown), created)] of each file the chat changed (outside Claude's own
    folders), from Claude's backups, else what its Edit or Write calls gave
    back (a file outside the chat's folder has no backups), else git's last
    commit."""
    rec = cs.chat_edits(path)
    skip = cs.own_folders(profiles)
    unbacked = {cs.absolute_path(key, cwd) for key, first in rec["files"].items() if first[0] is False}
    told = tool_originals([path, *cs.subagent_transcripts(path)], unbacked) if unbacked else {}
    out = {}
    for key, first in rec["files"].items():
        full = cs.absolute_path(key, cwd)
        if not cs.project_file(full, skip) or full in out:
            continue
        backup = first[0]
        if backup is None:
            original, created = b"", True  # it didn't exist yet
        elif backup is False:  # no backup on record: what its first call gave back, else git's last commit
            # (a file git doesn't have may have been there before the chat:
            # unknown, not new, so Undo never deletes it; one git has empty
            # was there, empty)
            original, created = told[full] if full in told else (git_original(full, missing=None), False)
        else:
            original, created = backup_content(profiles, rec["sessions"], backup), False
            if original is None:  # Claude removed the backup since
                original = git_original(full, missing=None)
        out[full] = (original, created)
    return [(f, o, c) for f, (o, c) in sorted(out.items())]


def is_text(data):
    return data is not None and b"\0" not in data[:8192]


def text_lines(data):
    """A text file's first lines (as many as a diff shows), [] for a binary one."""
    if not is_text(data):
        return []
    lines = data.decode("utf-8", "replace").splitlines()
    shown, size = [], 0
    for l in lines:
        if len(shown) >= cs.DIFF_LINES or size > cs.DIFF_CHARS:
            shown.append(f"… ({len(lines) - len(shown)} more lines)")
            break
        shown.append(l[:500])
        size += len(shown[-1])
    return shown


def file_diff(original, current, label):
    """(added, removed, diff lines) between two versions of a file; (None,
    None, []) for a binary one."""
    if not (is_text(original or b"") and is_text(current or b"")):
        return None, None, []
    old = (original or b"").decode("utf-8", "replace").splitlines()
    new = (current or b"").decode("utf-8", "replace").splitlines()
    # (difflib's time grows with the square of what it compares: in a long
    # file only the lines between those both start and end with are, with
    # the 3 around them it shows; a longer change shows its new lines, as
    # cs.edit_diff)
    top, a, b = 0, old, new
    if len(old) + len(new) > cs.DIFF_COMPARE_LINES:
        head, most = 0, min(len(old), len(new))
        while head < most and old[head] == new[head]:
            head += 1
        tail = 0
        while tail < most - head and old[-1 - tail] == new[-1 - tail]:
            tail += 1
        top, cut = max(0, head - 3), max(0, tail - 3)
        a, b = old[top:len(old) - cut], new[top:len(new) - cut]
    long = len(a) + len(b) > cs.DIFF_COMPARE_LINES
    if long:
        def span(n):  # (as difflib writes it)
            return "%d" % (top + 1) if n == 1 else "%d,%d" % (top + (n > 0), n)
        note = ["Too long to compare here: %d new lines in place of %d" % (len(b), len(a))] if a and b else []
        diff = itertools.chain(["@@ -%s +%s @@" % (span(len(a)), span(len(b)))] + note, ("+" + line for line in b))
    else:
        diff = difflib.unified_diff(a, b, f"a/{label}", f"b/{label}", lineterm="", n=3)
        next(diff, None), next(diff, None)  # (its --- and +++ lines)
    added = removed = more = size = 0
    shown = []
    for l in diff:
        if l.startswith("@@"):
            if top and not long:  # (at the file's line numbers)
                m = cs.HUNK_LINE.match(l)
                l = "@@ -%d%s +%d%s @@" % (int(m.group(1)) + top, m.group(2) or "", int(m.group(3)) + top, m.group(4) or "")
        elif l.startswith("+"):
            added += 1
        elif l.startswith("-"):
            removed += 1
        if len(shown) >= cs.DIFF_LINES or size > cs.DIFF_CHARS:
            more += 1
            continue
        shown.append(l[:500])
        size += len(shown[-1])
    if more:
        shown.append(f"… ({more} more lines)")
    if long:
        removed = len(a)
    return added, removed, shown


def commit_message(name, recap, reply):
    """A commit message from the chat's name and Claude's recap of it (else its last reply's first lines)."""
    title = cs.short_text(name or "Changes from a Claude chat", 72)
    body = (recap or {}).get("text") if isinstance(recap, dict) else ""
    if not body and reply:
        body = "\n".join(reply.strip().split("\n\n")[:2])
    body = cs.tidy_text(body or "", 1500)
    return title + ("\n\n" + body if body else "")


def chat_review(home, extra_dirs, chat_id, profile_key=None, reviewed_at=None):
    """{"ok", "files": [{"label", "path", "added", "removed", "diff",
    "created", "deleted", "binary", "unknown", "now" (with no earlier
    version kept: its first lines as they are now)}], "tests", "editedAt",
    "message" (a commit message), "repos" (git roots of the files), "cwd",
    "name"} of what a chat changed, against the files before the chat."""
    if not cs.valid_id(chat_id):
        return {"ok": False, "message": f"Not a chat: {chat_id}"}
    profiles = cs.discover_profiles(home, extra_dirs)
    profile, path = find_transcript(home, extra_dirs, chat_id, profile_key)
    if path is None:
        return {"ok": False, "message": NO_CHAT}
    name, cwd, _ = cs.read_chat_info(path, path.stat().st_size)
    cwd = cwd or cs.chat_folder(path) or ""
    files, repos = [], set()
    for full, original, created in originals(profiles, path, cwd):
        current, other = cs.bytes_to_compare(full, cs.DIFF_FILE_MAX)
        gone = current is None and other in ("", cs.NOT_PLAIN)
        big = "" if current is not None or gone else other  # ("a file of 18 MB": not read, nor compared)
        if not big and original is not None and len(original) > cs.DIFF_FILE_MAX:
            big = "a file of %d MB before the chat" % max(1, round(len(original) / (1 << 20)))
        if not big and original is not None and (current == original or (gone and original == b"" and created)):
            continue  # unchanged (or made and removed again)
        label = cs.file_label(full, cwd, home)
        item = {"label": label, "path": full, "created": created, "deleted": gone,
                "unknown": original is None, "binary": False, "added": None, "removed": None, "diff": []}
        if big:
            item.update(diff=["Not compared here: %s" % big])
        elif original is not None:
            added, removed, diff = file_diff(original, current, label)
            item.update(added=added, removed=removed, diff=diff, binary=added is None)
        elif current is not None:  # (no earlier version: how it is now)
            item.update(now=text_lines(current), binary=not is_text(current))
        files.append(item)
        root = git_root(os.path.dirname(full) if os.path.isdir(os.path.dirname(full)) else cwd)
        if root:
            repos.add(root)
    tests = cs.chat_tests(path)
    peek = cs.chat_peek(path) or {}
    return {"ok": True, "chatId": chat_id, "profileDir": profile.key, "name": name, "cwd": cwd, "files": files,
            "tests": tests["run"], "editedAt": tests["editAt"], "repos": sorted(repos),
            "message": commit_message(name, peek.get("recap"), peek.get("reply")),
            "reviewedAt": reviewed_at}


def chosen(files, wanted):
    return [f for f in files if not wanted or f["path"] in wanted]


USER_UMASK = [None]  # your umask, before main() made this run's files private


def undo(home, extra_dirs, chat_id, profile_key=None, wanted=()):
    """Put the files a chat changed (all, or those in wanted) back as they
    were before it: (ok, message). A file it made is removed, one it
    removed comes back; one whose earlier version isn't known stays."""
    profiles = cs.discover_profiles(home, extra_dirs)
    profile, path = find_transcript(home, extra_dirs, chat_id, profile_key)
    if path is None:
        return False, NO_CHAT
    for entry, _, _ in cs.live_entries_all(profiles):
        if entry.get("sessionId") == chat_id and cs.session_state(entry) == "working":
            return False, "It's at work: undo once its turn has ended"
    _, cwd, _ = cs.read_chat_info(path, path.stat().st_size)
    cwd = cwd or cs.chat_folder(path) or ""
    done, unknown, failed = 0, 0, []
    for full, original, created in originals(profiles, path, cwd):
        if wanted and full not in wanted:
            continue
        if original is None:
            unknown += 1
            continue
        current = read_bytes(full)
        # (through a link, e.g. a dotfile kept elsewhere: the file it points
        # to is the one the chat changed, and the link stays)
        real = os.path.realpath(full)
        try:
            if original == b"" and created:
                if current is not None:
                    os.unlink(real)
                    done += 1
            elif current != original:
                # (with your umask, not this run's private one: a file or
                # folder it brings back is as you'd have made it)
                mask = os.umask(USER_UMASK[0]) if USER_UMASK[0] is not None else None
                try:
                    os.makedirs(os.path.dirname(real), exist_ok=True)
                    mode = None  # (as the file is now, else as you'd make it)
                    if current is None and git_executable(full):  # (a script it removed runs again)
                        own = os.umask(0o077)
                        os.umask(own)
                        mode = 0o666 & ~own
                        mode |= (mode & 0o444) >> 2
                    # (through a new file of a name no one could put a link at: the repo is the chat's)
                    cs.write_atomic(real, original, mode)
                finally:
                    if mask is not None:
                        os.umask(mask)
                done += 1
        except OSError as exc:
            failed.append(f"{cs.file_label(full, cwd, home)}: {exc.strerror or exc}")
    if failed:
        return False, "Couldn't put back " + "; ".join(failed[:3])
    message = f"Put back {done} file{'s' if done != 1 else ''} as before the chat" if done else "Nothing to put back"
    if unknown:
        message += f" ({unknown} with no earlier version kept)"
    return True, message


def commit(home, extra_dirs, chat_id, message, profile_key=None, wanted=()):
    """Commit only the files a chat changed (or those in wanted), in each
    git repository they're in, with message: (ok, what happened)."""
    message = (message or "").strip()
    if not message:
        return False, "Write a commit message first"
    review = chat_review(home, extra_dirs, chat_id, profile_key)
    if not review.get("ok"):
        return False, review.get("message") or "Can't read the chat"
    by_repo = {}
    for f in chosen(review["files"], set(wanted)):
        folder = os.path.dirname(f["path"])
        while folder and not os.path.isdir(folder):
            folder = os.path.dirname(folder)
        root = git_root(folder) if folder else None
        if root:
            by_repo.setdefault(root, []).append(os.path.relpath(f["path"], root))
    if not by_repo:
        return False, "None of its files is in a git repository"
    done, ignored = [], 0
    for root, paths in sorted(by_repo.items()):
        # (git refuses to add a file it ignores, a .env say: those are left out)
        _, out, _ = git(root, "check-ignore", "-z", "--stdin", data="\0".join(paths).encode(), literal=False)
        left_out = set(out.split("\0")) - {""}
        ignored += len(left_out)
        paths[:] = [p for p in paths if p not in left_out]
        if not paths:
            continue
        ok, _, err = git(root, "add", "-A", "--", *paths)
        if not ok:
            return False, f"git add in {cs.short_path(root, home)}: {last_line(err)}"
        ok, out, err = git(root, "commit", "-q", "-F", "-", "--only", "--", *paths, data=message.encode(), timeout=120)
        if not ok:
            return False, f"git commit in {cs.short_path(root, home)}: {last_line(err or out)}"
        ok, head, _ = git(root, "rev-parse", "--short", "HEAD")
        done.append(f"{cs.short_path(root, home)} ({head.strip()})" if ok else cs.short_path(root, home))
    if not done:
        return False, "Nothing to commit: git ignores " + ("its file" if ignored == 1 else f"all {ignored} of its files")
    n = sum(len(p) for p in by_repo.values())
    left = f" (left out {ignored} file{'s' if ignored != 1 else ''} git ignores)" if ignored else ""
    return True, f"Committed {n} file{'s' if n != 1 else ''} in " + ", ".join(done) + left


def last_line(text):
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    return lines[-1] if lines else "failed"


# ---------------------------------------------------------------- marked reviewed

def mark_reviewed(cache_root, chat_id, host="", on=True, now_ms=None):
    """Mark a chat (of host) reviewed now, or not reviewed (0: also if it
    changed its files before cs.reviewed_since)."""
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    cs.private_dir(cache_root)
    with open(cache_root / "reviewed.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        since = cs.reviewed_since(cache_root, now_ms)
        chats = {k: v for k, v in cs.load_reviewed(cache_root).items() if v == 0 or now_ms - v < cs.REVIEWED_KEEP_MS}
        chats[cs.review_key(chat_id, host)] = now_ms if on else 0
        cs.write_json_atomic(cache_root / cs.REVIEWED, {"since": since, "chats": chats})


# ---------------------------------------------------------------- the hooks in Claude's settings
#
# Two hooks the widget can put in each Claude profile's settings.json, and
# take out again: the permission hook (--relay: permission prompts and
# Claude's questions answered from the widget) and the live hook (--live:
# each step of each chat as it happens). Each runs from a copy in
# ~/.local/share/talpy-den, named in the hook list of each of its events.

HOOK_FILE = cs.PERMISSION_HOOK_FILE
HOOK_TIMEOUT_S = 86400
# the events the live hook folds (live_hook.py); Claude doesn't wait for it (async)
LIVE_EVENTS = ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PostToolUseFailure",
               "PermissionRequest", "Notification", "Stop", "StopFailure", "SubagentStart", "SubagentStop",
               "PreCompact", "SessionEnd")
TOOL_EVENTS = ("PreToolUse", "PostToolUse", "PostToolUseFailure", "PermissionRequest")
HOOKS = {
    "relay": {"file": HOOK_FILE, "source": "permission_hook.py", "events": ("PermissionRequest",),
              "python": "-I", "entry": {"timeout": HOOK_TIMEOUT_S}},
    "live": {"file": cs.LIVE_HOOK_FILE, "source": "live_hook.py", "events": LIVE_EVENTS,
             "python": "-I -S", "entry": {"async": True, "timeout": 10}},
}


def hook_command(path, kind="relay"):
    """The hook's command in settings.json. Claude runs it with sh -c: exec
    has the shell give way to the hook, so Claude is the hook's parent (dash,
    Debian's and Ubuntu's sh, would stay in between); the path is quoted (a
    folder name may have a space). A copy that isn't there any more (its
    folder cleaned up by hand) is no answer: the command ends with status 0
    and Claude asks as it would without the hook (python3 would end with 2,
    which Claude takes as a refusal). An entry written before (python3 …
    PATH, no exec, no quotes, no check) is still the hook's (is_ours):
    upgrade_hooks, or turning it on again, replaces it."""
    path = shlex.quote(str(path))
    return f"[ -f {path} {cs.HOOK_GUARD} exec python3 {HOOKS[kind]['python']} {path}"


def settings_files(home, extra_dirs):
    """Each Claude profile's settings.json, once per real file (also of a
    ~/.claude that Claude has had no chat in yet)."""
    seen, out = set(), []
    folders = [p.path for p in cs.discover_profiles(home, extra_dirs)]
    if (home / ".claude").is_dir():
        folders.append(home / ".claude")
    for folder in folders:
        path = folder / "settings.json"
        real = os.path.realpath(path)
        if real not in seen:
            seen.add(real)
            out.append(Path(real))
    return out


def is_ours(hook, kind="relay"):
    command = str(hook.get("command") or "") if isinstance(hook, dict) else ""
    # (also the copy an earlier version put in its first folder, claude-widget)
    return HOOKS[kind]["file"] in command and ("talpy-den" in command or "claude-widget" in command)


def has_hook(settings, kind="relay"):
    """Whether settings name the hook, in each of its events."""
    hooks = settings.get("hooks") if isinstance(settings, dict) else None
    if not isinstance(hooks, dict):
        return False
    return all(any(is_ours(h, kind) for g in hooks.get(event) or [] if isinstance(g, dict) for h in g.get("hooks") or [])
               for event in HOOKS[kind]["events"])


def set_hook(settings, command, on, kind="relay"):
    """settings with the widget's hook in each of its events (on) or out of them."""
    hooks = settings.setdefault("hooks", {}) if on else settings.get("hooks") or {}
    for event in HOOKS[kind]["events"]:
        kept = []
        for g in hooks.get(event) or []:
            if not isinstance(g, dict):
                continue
            rest = [h for h in g.get("hooks") or [] if not is_ours(h, kind)]
            if rest:
                kept.append(dict(g, hooks=rest))
        if on:
            entry = dict({"type": "command", "command": command}, **HOOKS[kind]["entry"])
            kept.append(dict({"matcher": "*"} if event in TOOL_EVENTS else {}, hooks=[entry]))
        if kept:
            hooks[event] = kept
        else:
            hooks.pop(event, None)
    if not hooks and "hooks" in settings:
        settings.pop("hooks")
    return settings


def hook_path(home, kind="relay"):
    return Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share") / "talpy-den" / HOOKS[kind]["file"]


def write_settings(path, data):
    """Write a settings.json (through a link, keeping its mode)."""
    tmp = path.with_name(path.name + ".talpy-den.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if path.exists():
        shutil.copymode(path, tmp)
    os.replace(tmp, path)


def upgrade_hooks(home, extra_dirs=()):
    """Settings that name a hook with the command an older version wrote get
    today's (hook_command) in each of its events, as turning it on again
    would do: how many files changed."""
    changed = 0
    for path in settings_files(home, extra_dirs):
        data = cs.read_json(path)
        if not isinstance(data, dict):
            continue
        hooks = data.get("hooks") if isinstance(data.get("hooks"), dict) else {}
        before = json.dumps(data, sort_keys=True)
        for kind in HOOKS:
            command = hook_command(hook_path(home, kind), kind)
            if any(is_ours(h, kind) and h.get("command") != command for event in HOOKS[kind]["events"]
                   for g in hooks.get(event) or [] if isinstance(g, dict) for h in g.get("hooks") or []):
                set_hook(data, command, True, kind)
        if json.dumps(data, sort_keys=True) != before:
            write_settings(path, data)
            changed += 1
    return changed


def install_hook(home, extra_dirs, on, kind, source=None):
    """Put the hook in each profile's settings (on) or take it out: how many
    settings files changed (ValueError: one isn't JSON). source: the hook's
    code (else its file next to this one)."""
    target = hook_path(home, kind)
    if on:
        if source is None:
            source = (Path(__file__).resolve().parent / HOOKS[kind]["source"]).read_text(encoding="utf-8")
        target.parent.mkdir(parents=True, exist_ok=True)
        if read_bytes(target) != source.encode():
            tmp = target.with_name(target.name + ".tmp")
            tmp.write_text(source, encoding="utf-8")
            os.replace(tmp, target)
    changed = 0
    for path in settings_files(home, extra_dirs):
        data = cs.read_json(path)
        if data is None and not path.exists():
            if not on:
                continue
            data = {}
        if not isinstance(data, dict):
            raise ValueError(f"{cs.short_path(str(path), home)} isn't JSON Talpy Den can change")
        before = json.dumps(data, sort_keys=True)
        set_hook(data, hook_command(target, kind), on, kind)
        if json.dumps(data, sort_keys=True) == before:
            continue  # (as it was: the file isn't touched)
        write_settings(path, data)
        changed += 1
    if not on:
        try:
            target.unlink()
        except OSError:
            pass
    return changed


def relay(home, extra_dirs, on, source=None):
    """Put the permission hook in each profile's settings (on) or take it
    out: (ok, message). source: the hook's code (else permission_hook.py
    next to this file)."""
    try:
        changed = install_hook(home, extra_dirs, on, "relay", source)
    except ValueError as exc:
        return False, str(exc)
    if on:
        return True, "Permission prompts can be answered from Talpy Den" + ("" if changed else " (they could already)")
    return True, "Permission prompts are answered in the chats only"


def live(home, extra_dirs, on, source=None):
    """Live mode: the live hook in each profile's settings (on) or out of
    them: (ok, message)."""
    try:
        changed = install_hook(home, extra_dirs, on, "live", source)
    except ValueError as exc:
        return False, str(exc)
    if on:
        return True, "Chats show each step as it happens" + ("" if changed else " (they did already)")
    return True, "Chats show their steps at each check"


def hook_copy(home, kind="relay"):
    """The hook's copy in Talpy Den's data folder, put there if it isn't (a
    chat Talpy Chat starts names it in settings of its own, while the
    setting for every chat may be off; a status check brings it up to date,
    talpy_den.refresh_hooks): its path, or None (no hook here to copy)."""
    target = hook_path(home, kind)
    if target.is_file():
        return target
    try:
        data = (Path(__file__).resolve().parent / HOOKS[kind]["source"]).read_bytes()
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, target)
    except (OSError, NameError):
        return None
    return target


def chat_hook(home, profile):
    """The permission hook for one chat, as claude --settings takes it
    (JSON: the same entry --relay on writes), so a background chat Talpy
    Chat starts or wakes asks its permission prompts and questions where
    Talpy Chat answers them: it has no terminal to ask in. None when the
    profile's own settings have the hook (on for every chat: it would run
    twice), or managed settings let only their own hooks run."""
    if cs.managed_hooks_only() or has_hook(cs.read_json(profile.path / "settings.json") or {}):
        return None
    target = hook_copy(home)
    if target is None:
        return None
    return json.dumps(set_hook({}, hook_command(target), True), separators=(",", ":"))


def relay_status(home, extra_dirs, kind="relay"):
    files = settings_files(home, extra_dirs)
    on = [has_hook(cs.read_json(p) or {}, kind) for p in files]
    return {"ok": True, "on": bool(on) and all(on), "some": any(on), "settings": [str(p) for p in files]}


# ---------------------------------------------------------------- command line

# ---------------------------------------------------------------- your terminal's font
#
# The chat pane shows the conversation in it, as Claude's own terminal does:
# the terminal the widget opens chats in (System Settings > Default
# Applications, else Konsole), from its own settings. "" when it says none
# (Konsole's built-in profile: the desktop's fixed-width font, which the
# pane takes then, if it is one).

TERMINAL_FILE_MAX = 1 << 20


def read_small(path):
    try:
        if os.path.getsize(path) > TERMINAL_FILE_MAX:
            return ""
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def ini_value(text, group, key):
    """key's value in [group] of an INI-like file (None: no such line)."""
    current = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("["):
            current = line
        elif current == group and "=" in line and line.split("=", 1)[0].strip() == key:
            return line.split("=", 1)[1].strip()
    return None


def config_home(home):
    return Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")


def konsole_font(home):
    """Konsole's default profile's font family (Yakuake's too, it uses Konsole's profiles)."""
    for rc in ("konsolerc", "yakuakerc"):
        name = ini_value(read_small(config_home(home) / rc), "[Desktop Entry]", "DefaultProfile")
        if not name or "/" in name:
            continue
        data_dirs = [os.environ.get("XDG_DATA_HOME") or str(home / ".local/share")] \
            + (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":")
        for d in data_dirs:
            font = ini_value(read_small(Path(d) / "konsole" / name), "[Appearance]", "Font")
            if font:
                return font.split(",", 1)[0].strip()
    return ""


def first_match(text, pattern):
    m = re.search(pattern, text, re.M)
    return m.group(1).strip().strip("\"'") if m else ""


def other_terminal_font(home, name):
    """The font family a terminal other than Konsole is set to, from its own settings ("" if none)."""
    cfg = config_home(home)
    if name == "kitty":
        value = first_match(read_small(cfg / "kitty/kitty.conf"), r"^\s*font_family\s+(.+?)\s*$")
        if value.startswith("family="):  # (kitty 0.36: font_family family="X" style=…)
            value = first_match(value, r"family=(\"[^\"]+\"|'[^']+'|\S+)")
        return "" if value == "monospace" else value
    if name == "alacritty":
        text = read_small(cfg / "alacritty/alacritty.toml") or read_small(cfg / "alacritty/alacritty.yml")
        return first_match(text, r"family\s*[=:]\s*(\"[^\"]+\"|'[^']+'|[^\s#]+)")
    if name in ("foot", "footclient"):
        value = ini_value(read_small(cfg / "foot/foot.ini"), "[main]", "font") \
            or first_match(read_small(cfg / "foot/foot.ini"), r"^\s*font\s*=\s*(.+)$")
        return re.split(r"[:,]", value or "", maxsplit=1)[0].strip()
    if name == "ghostty":
        return first_match(read_small(cfg / "ghostty/config"), r"^\s*font-family\s*=\s*(.+?)\s*$")
    if name == "wezterm":
        text = read_small(cfg / "wezterm/wezterm.lua") or read_small(home / ".wezterm.lua")
        return first_match(text, r"wezterm\.font(?:_with_fallback)?\s*\(\s*\{?\s*(?:family\s*=\s*)?(\"[^\"]+\"|'[^']+')")
    if name == "xfce4-terminal":
        text = read_small(cfg / "xfce4/terminal/terminalrc")
        if (ini_value(text, "[Configuration]", "FontUseSystem") or "").upper() == "TRUE":
            return ""
        return re.sub(r"\s+\d+(\.\d+)?$", "", ini_value(text, "[Configuration]", "FontName") or "")
    return ""


def terminal_font(home):
    """{"ok", "family", "terminal"}: your terminal's font family ("" when it names none)."""
    chosen = ini_value(read_small(config_home(home) / "kdeglobals"), "[General]", "TerminalApplication")
    try:
        name = Path(shlex.split(chosen)[0]).name if chosen else ""
    except ValueError:
        name = ""
    if name and name not in ("konsole", "yakuake"):
        return {"ok": True, "family": other_terminal_font(home, name), "terminal": name}
    return {"ok": True, "family": konsole_font(home), "terminal": "konsole"}


def take_text(cache_root, name):
    """The message in a file of the cache (text-*.txt), which goes once read
    (one command-line argument holds 128 KiB at most); None if it isn't one."""
    f = Path(os.path.abspath(name))
    if f.parent != Path(os.path.abspath(str(cache_root))) or not (f.name.startswith("text-") and f.name.endswith(".txt")):
        return None
    try:
        return f.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None
    finally:
        try:
            f.unlink()
        except OSError:
            pass


def forward(host, args):
    """Run this file on an SSH host with args: its answer."""
    import remote
    return remote.host_answer(host, args, name="pane.py", also=("reply_words.py",))   # (its words for Claude's questions)


def main(argv=None):
    args = sys.argv[1:] if argv is None else list(argv)
    rest, host, i = [], "", 0  # rest: the arguments as a host gets them (no --host, --remote, --pretty)
    while i < len(args):
        if args[i] == "--host" and i + 1 < len(args):
            host, i = args[i + 1], i + 2
            continue
        if args[i] == "--wait" and i + 1 < len(args):  # (not over ssh: a host's chat is looked at again instead)
            i += 2
            continue
        if args[i] not in ("--remote", "--pretty"):
            rest.append(args[i])
        i += 1
    action, target = None, None
    profile, how, note, decision, message, name = None, "auto", "", None, "", ""
    session, text, stamp, limit, files, config_dirs, answers = None, None, None, PANE_ITEMS, [], [], None
    after, off, remote, pretty, source, expect, text_file, wait = False, False, False, False, None, None, None, 0.0
    actions = ("--conversation", "--send", "--answer", "--keys", "--review", "--undo", "--commit", "--reviewed",
               "--relay", "--live", "--oldest", "--shortcuts", "--complete", "--start", "--interrupt", "--replies",
               "--hide-reply")
    osd, suggest = False, False
    cwd, model, effort, mode, plan, plan_profile = None, None, None, None, None, None
    while args:
        arg = args.pop(0)
        if arg in actions and args and action is None:
            action, target = arg, args.pop(0)
        elif arg == "--host" and args:
            args.pop(0)
        elif arg == "--profile" and args:
            profile = args.pop(0)
        elif arg == "--session" and args:
            session = args.pop(0)
        elif arg == "--text" and args:
            text = args.pop(0)
        elif arg == "--text-file" and args:
            text_file = args.pop(0)
        elif arg == "--how" and args:
            how = args.pop(0)
        elif arg == "--note" and args:
            note = args.pop(0)
        elif arg == "--decision" and args:
            decision = args.pop(0)
        elif arg == "--expect" and args:
            expect = args.pop(0)
        elif arg == "--answers" and args:
            try:
                answers = json.loads(args.pop(0))
            except ValueError:
                answers = None
        elif arg == "--message" and args:
            message = args.pop(0)
        elif arg == "--cwd" and args:
            cwd = args.pop(0)
        elif arg == "--model" and args:
            model = args.pop(0)
        elif arg == "--effort" and args:
            effort = args.pop(0)
        elif arg == "--permission-mode" and args:
            mode = args.pop(0)
        elif arg == "--plan" and args:
            plan = args.pop(0)
        elif arg == "--plan-profile" and args:
            plan_profile = args.pop(0)
        elif arg == "--name" and args:
            name = args.pop(0)
        elif arg == "--file" and args:
            files.append(args.pop(0))
        elif arg == "--if-changed" and args:
            stamp = args.pop(0)
        elif arg == "--limit" and args and args[0].isdigit():
            limit = int(args.pop(0))
        elif arg == "--wait" and args:
            try:
                wait = max(0.0, float(args.pop(0)))
            except ValueError:
                wait = 0.0
        elif arg == "--config-dir" and args:
            config_dirs.append(args.pop(0))
        elif arg == "--hook-source" and args:
            source = base64.b64decode(args.pop(0)).decode("utf-8")
        elif arg == "--terminal-font" and action is None:
            action, target = arg, ""
        elif arg == "--after-turn":
            after = True
        elif arg == "--osd":
            osd = True
        elif arg == "--suggest":
            suggest = True
        elif arg == "--off":
            off = True
        elif arg == "--remote":
            remote = True
        elif arg == "--pretty":
            pretty = True
        else:
            sys.exit(__doc__)
    if action is None:
        sys.exit(__doc__)
    USER_UMASK[0] = os.umask(0o077)
    home = Path.home()
    cs.adopt_legacy_dirs(home)
    cache_root = cs.cache_dir(home)

    def emit(result):
        out = json.dumps(result, indent=2 if pretty and not remote else None)
        sys.stdout.write(("\n" + cs.REMOTE_MARK + " " if remote else "") + out + "\n")

    if text_file is not None:  # (a long message: VS Code's)
        text = take_text(cache_root, text_file)
        if text is None:
            return emit({"ok": False, "message": "Couldn't read your message"})
        i = rest.index("--text-file")
        rest[i:i + 2] = ["--text", text]  # (a host gets the text: remote.host_answer takes it there)
    try:
        if host and action == "--reviewed":  # (kept here, as stars are)
            mark_reviewed(cache_root, target, host, on=not off)
            return emit({"ok": True, "message": "Marked reviewed" if not off else "Not marked reviewed"})
        if host and action == "--send" and how == "copy":  # (the clipboard is this computer's)
            return emit(copy_answer((text or "").strip()))
        if host and action == "--send" and after:  # (queued here: the widget here sends it then)
            ok, said = send_later(home, config_dirs, profile, target, text, session, how, host, name)
            return emit({"ok": ok, "message": said})
        if host and action == "--start":  # (a host's prompts can't reach Talpy Chat yet)
            return emit({"ok": False, "message": "Talpy Chat starts chats on this computer only, for now"})
        if host:
            if action in ("--relay", "--live") and target == "on" and source is None:
                path = Path(__file__).resolve().parent / HOOKS[action[2:]]["source"]
                rest += ["--hook-source", base64.b64encode(path.read_bytes()).decode()]
            answer = forward(host, rest)
            if action == "--review" and answer.get("ok"):
                answer["reviewedAt"] = cs.load_reviewed(cache_root).get(cs.review_key(target, host))
            if action == "--conversation" and answer.get("ok"):
                pictures_here(answer.get("items"))
            if action == "--send":
                answer = host_vscode_link(answer, (session, target), text)
            if action == "--send" and how == "enter" and answer.get("how") == "ask":
                answer = copy_answer((text or "").strip(), ENTER_COPIES)  # (here, as above)
            return emit(answer)
        if action == "--conversation":
            # (pasted pictures saved for the thumbnails: not on an SSH host, where the pane doesn't look)
            result = chat_conversation(home, config_dirs, target, profile, limit, stamp, wait,
                                       None if remote else cs.images_dir(home), suggest)
        elif action == "--send":
            if after:
                ok, said = send_later(home, config_dirs, profile, target, text, session, how, "", name)
                result = {"ok": ok, "message": said}
            else:
                result = send(home, config_dirs, profile, target, text, session, how, scoped=not remote)
                if how == "enter" and result.get("how") == "ask" and not remote:  # (on a host: copied here, above)
                    result = copy_answer((text or "").strip(), ENTER_COPIES)
        elif action == "--start":
            result = start_chat(home, config_dirs, target, cwd, text, model, effort, mode, plan, plan_profile,
                                scoped=not remote)
        elif action == "--interrupt":
            ok, said = interrupt(home, config_dirs, profile, target, session)
            result = {"ok": ok, "message": said}
        elif action == "--answer":
            ok, said = answer_request(cache_root, target, decision, note, answers)
            # (changed: the request you answered is gone; the chat may ask something else now)
            result = {"ok": ok, "message": said, **({"changed": True} if not ok and said in (NOT_ASKING, ASKS_ELSE) else {})}
        elif action == "--complete":
            result = completions(home, config_dirs, target, profile, cwd)
        elif action == "--replies":
            result = chat_replies(home, config_dirs, cache_root, target, profile, cwd)
        elif action == "--hide-reply":
            ok, said = hide_reply(cache_root, target, on=not off)
            result = {"ok": ok, "message": said}
        elif action == "--terminal-font":
            result = terminal_font(home)
        elif action == "--oldest":
            ok, said = answer_oldest(cache_root, target)
            if osd:
                show_note(said, ok)
            result = {"ok": ok, "message": said}
        elif action == "--shortcuts":
            ok, said = shortcuts(home, {"on": True, "off": False}.get(target))
            result = {"ok": ok, "message": said} if target != "status" else {"ok": ok, "on": said == "on"}
        elif action == "--keys":
            entry = cs.find_chat_entry(home, config_dirs, target, profile)
            # (--expect: the tool call the prompt you answered was about; it
            # may have been answered in the chat since, and another one asks)
            still = (lambda: cs.chat_tool_use(home, config_dirs, target, profile) == expect) if expect else None
            ok, said = answer_with_keys(entry, decision, note, still) if entry \
                else (False, "That chat isn't running any more")
            result = {"ok": ok, "message": said, **({"changed": True} if not ok and said == ASKS_ELSE else {})}
        elif action == "--review":
            result = chat_review(home, config_dirs, target, profile,
                                 cs.load_reviewed(cache_root).get(cs.review_key(target)) if not remote else None)
        elif action == "--undo":
            ok, said = undo(home, config_dirs, target, profile, set(files))
            result = {"ok": ok, "message": said}
        elif action == "--commit":
            ok, said = commit(home, config_dirs, target, message, profile, set(files))
            result = {"ok": ok, "message": said}
        elif action == "--reviewed":
            mark_reviewed(cache_root, target, "", on=not off)
            result = {"ok": True, "message": "Marked reviewed" if not off else "Not marked reviewed"}
        elif action in ("--relay", "--live"):
            kind = action[2:]
            if target == "status":
                result = relay_status(home, config_dirs, kind)
            elif target in ("on", "off"):
                ok, said = (relay if kind == "relay" else live)(home, config_dirs, target == "on", source)
                result = {"ok": ok, "message": said}
            else:
                sys.exit(__doc__)
        else:
            sys.exit(__doc__)
    except Exception as exc:  # the widget must always get parseable output
        result = {"ok": False, "message": f"{type(exc).__name__}: {exc}"}
    emit(result)


if __name__ == "__main__":
    main()
