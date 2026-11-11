#!/usr/bin/env python3
"""The chat pane of Talpy Den: one chat's conversation, a reply to it,
its permission prompt and its review.

    python3 -I pane.py ACTION [--host HOST] [--config-dir DIR]... [--remote] [--pretty]

  --conversation CHAT [--profile P] [--limit N] [--if-changed STAMP [--wait S]] [--suggest] [--reach KEY] [--seen MS] [--away]
        the chat as the pane shows it: your prompts, Claude's replies
        (markdown), each tool call as one line with how it went, and notes
        (a usage limit, an interruption); the newest N items. STAMP: the
        "stamp" of the last answer; while the transcript is as it was then,
        the answer is only {"ok", "unchanged"}. --wait: while it's as it was,
        wait up to S seconds (at most WAIT_MAX_S) for it to change, and answer
        the moment it does (the pane's watcher: what Claude writes shows at
        once, not at the next look). Not on an SSH host (it's left out there).
        Also how full its context is, "context" (turns.context_left), and
        Claude's turn so far while it's going on, "turn": {"startedAt",
        "steps"} (turns.TurnSoFar); its bookmarks, "bookmarks" and
        "bookmarksV", once it has had one (kept here for a host's chat too).
        --suggest (Suggest replies): how its last turn ended, "ended" and
        "over", and the question it ends with as chips, "asks" (replies.asks_of)
        --reach KEY (a bookmark further back than what's shown): enough
        items to show the message with that key and a few above it, the
        limit grown as Show earlier grows it ("limit"; STAMP isn't looked
        at), and "reached": "here", "far" (further back than PANE_ITEMS_MAX
        items) or "gone" (not in the chat any more)
        --seen MS (a Talpy Chat window shows it): the time of the newest of
        its items that window shows (what it took of the answers before),
        kept as how far a window showed it (talpy_den.mark_seen; a host's
        chat's here, never sent there), before the read and its wait. --away
        (that window shows it again, or for the first time): what it did
        since what a window last showed of it (the mark before this read's),
        or since your last message, "away" (turns.Away.result: its steps,
        the files it changed, its newest test run, what it waits for; null:
        nothing to tell)
  --bookmark CHAT --key KEY [--off] [--kind you|claude] [--at MS] [--text TEXT] [--host HOST]
        bookmark the message with that key (yours or Claude's reply, written
        at MS, its first words TEXT), or not any more (--off); kept on this
        computer, a host's chat's too (talpy_den.change_bookmark). {"ok",
        "message", "bookmarks": the chat's now, "bookmarksV"}
  --replies CHAT [--profile P]
        your usual replies for the chat (replies.usual_replies): {"ok", "chips": {how
        a turn ended: [replies]}, "ranked": [replies, to complete what you
        type]}; CHAT "-" with --cwd FOLDER --profile P: a new chat's
  --hide-reply TEXT [--off]
        don't suggest TEXT again (--off: do again; "-" --off: all of them)
  --reply-text CHAT --key KEY [--profile P]
        Copy's text of a reply (or a prompt of yours) the conversation shows
        cut at TEXT_CHARS: all of it, from the transcript (replies.whole_text).
        {"ok", "text"}
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
  --set-options CHAT --profile P [--model M] [--effort E]
        the chat's own model and effort, picked in Talpy Chat (/model,
        /effort; "" or "default": Claude's), for it alone, never your
        settings (chatpick.py): a background chat's saved options, one open
        idle stopped and woken again with them; one with no job kept for its
        next wake from here. {"ok", "message", "how": "now"|"next"|"terminal",
        "model", "effort"}
  --made CHAT --path PATH [--step ID] [--profile P] [--as-file]
        a picture, a plan or a page the chat made, as Talpy Chat shows it
        unfolded (made.py show: only one its transcript names, capped): a
        picture's bytes ("data", base64, "mime"), a plan's or a page's first
        lines ("text", "cut"). --step (a Read's tool call): the picture Claude
        saw there, from the transcript. --as-file (Plasma's): a picture as a
        file here ("file", in place of the bytes): this computer's own once
        it's known to be a plain file, an SSH host's or one Claude saw a copy
  --type-in CHAT --text T [--session ID] [--profile P] [--no-copy]
        a command that needs Claude's own panel (commands.py), put in the
        chat's own prompt for you to press Enter there: typed into its tmux
        pane (not sent), its VS Code panel's input (link), else the clipboard
        ("how": "typed", "vscode" or "copy"; --no-copy: the caller copies it);
        the caller opens its terminal
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
  --relay on|off|status|forget [--keep-copy]
        the permission hook in each Claude profile's settings.json (status: also
        "hooked", the chats Talpy Chat started that answer their prompts with
        a hook of their own; off --keep-copy: they keep it). forget (with
        --host: a host taken off the list): the hook's copy Talpy Chat put
        there and its requests go, unless a chat it started there still runs
        or the hook is on for every chat there (forget_hook)
  --live on|off|status
        live mode: the live hook (live_hook.py) in each Claude profile's
        settings.json, so the widget shows each step of each chat as it happens
  --complete CHAT [--profile P]
        what the reply box offers as you type: / commands (Claude's own, yours
        and the project's) and skills, each with how Talpy Chat runs it
        (commands.py: "run" here, a page of Talpy Den's or the terminal), the
        project's files for @, and your past prompts in its folder (newest
        first) for ↑. CHAT "-" with --cwd FOLDER --profile P: a new chat's
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
import zlib
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
THOUGHT = "/thinking"   # (a thinking line's key: its message's id and this; replies.THOUGHT)
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
    text = cs.typed_part(cs.message_text({"content": content})).strip()  # (the Claude Code panel's: after its editor's notes)
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


def turn_end(wanted):
    """What follows how the turn ended (replies.TurnEnd), or None when nobody asks (Suggest
    replies off): nothing is followed, and replies.py isn't even read."""
    if not wanted:
        return None
    import replies   # (a module of its own: compiled once and kept, where this script is compiled at every call)
    return replies.TurnEnd()


COMMAND_TAGS = ("<command-", "<local-command-", "<bash-")   # (a command you ran, what it printed: commands.py)
UNKNOWN_COMMAND = ("Unknown command: /", "Unknown skill: /")


def commands_of(items, due, end):
    """What follows the commands you ran (commands.Commands), read only for a chat that has one."""
    import commands   # (a module of its own, as replies.py: compiled once and kept)
    return commands.Commands(items, due, end)


def conversation_items(lines, pictures=None, ends=None, so_far=None, found=None, away=None):
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
    to it, or your note to a No, comes after it as yours (your_answer). A
    command you ran (/compact, !ls) is yours with "command" (commands.py:
    what it printed on it). A picture, a plan or a page a step made, or a
    picture a reply names, comes right after it as {"kind": "made"} (made.py).
    Entries of subagents (sidechains) aren't in it. ends: a dict given gets
    how the last turn ended (replies.TurnEnd.result); so_far: one given gets
    Claude's turn so far ("turn": turns.TurnSoFar, also how full its context is);
    away: a turns.Away given follows what it did (Since you last looked)."""
    items, tools = [], {}
    import turns   # (a module of its own, as replies.py: compiled once and kept)
    import made   # (the same)
    place = found is None   # (what Claude made: placed under its steps and replies at the end; found given: by the caller)
    found = made.Collector() if place else found
    ending = turn_end(ends is not None)
    end = turns.TurnSoFar(ending)
    # Messages sent while Claude works: the transcript has each one when it's
    # sent (queue-operation enqueue) and again once Claude takes it in, after
    # its next tool result (an attachment, queued_command), which can be long
    # after. waiting: those not taken in yet, listed last with "queued": True
    # (Claude's terminal shows them under the conversation, as queued); one
    # taken in goes where Claude took it, with the same key; taken: the ids of
    # those that were; due: those made the chat's own prompts (dequeue), in turn
    waiting, taken, due = [], set(), []
    ran = None   # the commands you ran in it (commands.Commands), once there's one

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
        if away is not None and away.first is None:
            away.entry(at)
        if kind == "queue-operation":
            op, text = e.get("operation"), typed_text(e.get("content"))
            if op == "enqueue" and text:
                waiting.append(you(f"queued-{at}", text, at, e.get("content")))
                if away is not None:   # (sent while Claude worked: you were there)
                    away.you(at)
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
            sub, content = e.get("subtype"), e.get("content")
            if sub == "compact_boundary":
                items.append({"kind": "note", "key": uid, "text": "The conversation was compacted", "at": at})
                end.compacted()
            elif sub == "local_command" and isinstance(content, str):
                ran = ran or commands_of(items, due, end)
                ran.entry(content, uid, at)
            elif sub == "informational" and isinstance(content, str) and content.startswith(UNKNOWN_COMMAND):
                ran = ran or commands_of(items, due, end)
                ran.unknown(content, uid, at)
            elif sub == "scheduled_task_fire":
                # (a wake-up Claude scheduled itself, ScheduleWakeup or /loop: its prompt isn't yours)
                said = e.get("prompt") if isinstance(e.get("prompt"), str) else ""
                items.append({"kind": "note", "key": uid, "at": at,
                              "text": "Claude woke itself up" + (": " + cs.short_text(" ".join(said.split()), 120) if said.strip() else "")})
            continue
        msg, blocks = cs.blocks_of(e)
        if kind == "user":
            if e.get("isMeta") and e.get("promptSource") == "system" and due \
                    and same_text(due[0]["text"], cs.message_text(msg) if msg else ""):
                due.pop(0)   # (a wake-up's prompt, queued and taken in as Claude's own: not yours, not shown)
                continue
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
                    if not c.get("is_error") and item["name"] in made.TOOLS:
                        found.step(item, inp, c, e.get("toolUseResult") if len(results) == 1 else None, output, e.get("cwd"))
                    if away is not None:
                        away.done(item["name"], inp, not c.get("is_error"), at, e.get("cwd"))
                    said = your_answer(item, e, output, bool(c.get("is_error")),
                                       e.get("toolUseResult") if len(results) == 1 else None)
                    if said is not None:
                        said["at"] = at
                        items.append(said)
            prompt = cs.human_prompt(e)
            if prompt is not None:
                end.prompt(at)
                if away is not None:
                    away.you(at)
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
            elif text.startswith(COMMAND_TAGS):
                ran = ran or commands_of(items, due, end)
                ran.entry(text, uid, at)
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
        # (thinking shown as updates: a thinking block's text is a line Claude
        # Code writes while Claude thinks, summing it up; not Claude's reply,
        # it can tell what Claude means to do as if it were done. An item of
        # its own, "thinking", shown dimmed in italics as Claude Code's
        # terminal shows it (after ∴); thinking Claude keeps to itself comes
        # without text)
        updates = e.get("thinkingDisplay") == "updates"
        for c in blocks:
            thought = updates and c.get("type") == "thinking"
            said = c.get("text") if c.get("type") == "text" else c.get("thinking") if thought else None
            if isinstance(said, str) and said.strip():
                key = (mid or uid) + THOUGHT if thought else mid or uid
                last = items[-1] if items else None
                if last is not None and last["kind"] == "claude" and mid is not None and last["key"] == key:
                    last["text"] = clip(last["text"] + "\n\n" + said.strip(), TEXT_CHARS, 10 ** 6)
                else:
                    item = {"kind": "claude", "key": key, "text": clip(said.strip(), TEXT_CHARS, 10 ** 6), "at": at}
                    if thought:
                        item["thinking"] = True
                    elif away is not None:
                        away.reply(at, key)
                    items.append(item)
                    if not thought:   # (a thinking line names nothing Claude made)
                        found.reply(item, e.get("cwd"))
            elif c.get("type") == "tool_use" and isinstance(c.get("id"), str):
                end.steps += 1
                if away is not None:
                    away.step(at, c["id"])
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
        ends["ended"], ends["over"] = ending.result(bool(waiting or due))
        ends["reply"] = ending.reply
    if so_far is not None:
        so_far["turn"] = end
    return found.place(items) if place else items


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
    dropped), whether they start at the file's start, and where they do."""
    start = max(0, size - nbytes)
    with open(path, "rb") as f:
        f.seek(start)
        lines = f.read(min(size, nbytes)).split(b"\n")
    whole = size <= nbytes
    if not whole:
        start += len(lines[0]) + 1
        lines = lines[1:]
    return lines, whole, start


REACH_ABOVE = 3  # items shown above a message --reach goes to


def reach_limit(limit, need):
    """The limit that shows need items: limit doubled as Show earlier doubles
    it (so the next Show earlier goes on from there), at most PANE_ITEMS_MAX."""
    n = max(limit, PANE_ITEMS)
    while n < need and n < PANE_ITEMS_MAX:
        n = min(PANE_ITEMS_MAX, n * 2)
    return n


def conversation(path, limit=PANE_ITEMS, pictures=None, ends=None, so_far=None, reach=None, away=None):
    """(items, more) of a chat: its newest limit items (conversation_items,
    pasted pictures saved in pictures; ends: how its last turn ended; so_far:
    its turn so far, and where the lines read start, "start"), and whether
    there are older ones. reach: the key of a message to show (--reach): read
    back until it's there, the limit grown to show it (so_far "limit"), and
    so_far "reached": "here", "far" (more than PANE_ITEMS_MAX items back, or
    further than PANE_TAIL_MAX bytes) or "gone"; so_far "whole": whether
    it read the transcript from its start. away: a turns.Away, followed in
    what was read (conversation_items)."""
    size = path.stat().st_size
    nbytes = PANE_TAIL_BYTES
    import made
    while True:
        lines, whole, start = tail_lines(path, size, nbytes)
        found = made.Collector()
        if away is not None:
            away.again()   # (read again from further back: followed again)
        items = conversation_items(lines, pictures, ends, so_far, found, away)
        if so_far is not None:
            so_far["start"], so_far["whole"] = start, whole
        if reach is not None:
            at = next((n for n, item in enumerate(items) if item.get("key") == reach), -1)
            if at < 0 and not whole and nbytes < PANE_TAIL_MAX:
                nbytes *= 4   # (as Show earlier reads further back)
                continue
            need = len(items) - at + REACH_ABOVE
            reached = "here" if at >= 0 and need <= PANE_ITEMS_MAX else "far" if at >= 0 or not whole else "gone"
            if reached == "here":
                limit = reach_limit(limit, need)
            if so_far is not None:
                so_far.update(reached=reached, **({"limit": limit} if reached == "here" else {}))
            reach = None
        if whole or len(items) > limit or nbytes >= PANE_TAIL_MAX:
            # (what was made, placed in the items listed only: their replies alone are looked at)
            shown = found.place(items, max(0, len(items) - limit))
            return within_budget(file_pictures(shown)), len(items) > limit or not whole
        nbytes *= 4


def stamp_of(path):
    st = path.stat()
    return f"{st.st_size}:{st.st_mtime_ns}"


WAIT_MAX_S = 55  # (the pane gives up on a run after 70 s, hub/Exec.qml's staleMs, VS Code after 70 s)
WAIT_GATHER_S = 0.04  # after a change: what Claude writes with it (a prompt and its attachments)
# inotify: IN_MODIFY | IN_ATTRIB | IN_CLOSE_WRITE | IN_DELETE_SELF | IN_MOVE_SELF (a line added, the file
# replaced or moved: Claude moves a chat's transcript when it goes into a worktree)
WAIT_MASK = 0x2 | 0x4 | 0x8 | 0x400 | 0x800


def wait_for_change(path, stamp, seconds, clock=time.time, look=stamp_of):
    """Wait up to seconds for the transcript at path to be other than stamp
    (look: stamp_of, or what else the answer depends on with it): whether it
    is. inotify on the file (elsewhere: a look every half second), and a look
    every second; it ends as soon as whoever started it is gone."""
    import live  # (its Watch: the same inotify the widget's watcher uses)
    watch = live.Watch([str(path)], WAIT_MASK)  # (watching first: nothing between the look and the wait is missed)
    parent, end = os.getppid(), clock() + max(0.0, seconds)
    try:
        while True:
            try:
                if look(path) != stamp:
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
                      suggest=False, reach=None, away=None):
    """--conversation. "options": the model and effort it uses now
    (chatpick.options_now). "context": how full its context is (turns.context_left),
    "turn": Claude's turn so far, while it's going on (turns.TurnSoFar.now:
    the start of a long one kept in the cache folder's turns/). suggest (Suggest
    replies on): how its last turn ended, "ended" and "over"
    (replies.TurnEnd.result), the question it ends with as chips, "asks"
    (replies.asks_of), and Claude's own predicted reply to it, "predicted"
    (predicted_reply: its background job writes it a few seconds after the
    turn's end, so the stamp says whether there is one). reach: the key of a
    message to show, if_changed not looked at (conversation): the answer has
    "limit" (the stamp's), "reach" and "reached". away (--away: a window that
    shows it again, or for the first time): when one last showed it (ms, 0:
    never); the answer has what it did since, "away" (turns.Away.result,
    None: nothing to tell)."""
    if not cs.valid_id(chat_id):
        return {"ok": False, "message": f"Not a chat: {chat_id}"}
    profile, path = find_transcript(home, extra_dirs, chat_id, profile_key)
    if path is None:
        return {"ok": False, "missing": True, "message": NO_CHAT}
    import chatpick

    def look(path):
        said = predicted_reply(chatpick.job_record(profile, chat_id)) if suggest else None
        return stamp_of(path) + (f"~{zlib.crc32(said.encode('utf-8')):08x}" if said else "")
    stamp = look(path)
    if if_changed and not reach and if_changed == f"{stamp}/{limit}":
        if not (wait > 0 and wait_for_change(path, stamp, min(wait, WAIT_MAX_S), look=look)):
            return {"ok": True, "unchanged": True}
        if not path.exists():  # (moved: where it is now)
            profile, path = find_transcript(home, extra_dirs, chat_id, profile_key)
        try:
            stamp = look(path)  # (before it's read: what's written meanwhile is a change the next time)
        except (OSError, AttributeError):
            return {"ok": False, "missing": True, "message": NO_CHAT}
    import turns
    ends, so_far = {} if suggest or away is not None else None, {}
    gone = turns.Away(away) if away is not None else None
    items, more = conversation(path, max(1, min(PANE_ITEMS_MAX, limit)), pictures, ends, so_far, reach or None, gone)
    limit = so_far.get("limit", limit)   # (grown to show what --reach goes to)
    name, cwd, _ = cs.read_chat_info(path, path.stat().st_size)
    peek = cs.chat_peek(path) or {}
    turn = so_far["turn"]
    result = {"ok": True, "chatId": chat_id, "profileDir": profile.key, "name": name, "cwd": cwd or cs.chat_folder(path) or "",
              "items": items, "more": more, "stamp": f"{stamp}/{limit}", "mode": peek.get("mode"),
              "recap": peek.get("recap"),   # (Claude's own recap, written when you came back to it: Since you last looked shows it)
              "permission": cs.pending_permission(path, cwd),
              "context": turns.context_left(turn.usage, turn.model, lambda: turns.status_window(home, profile, chat_id, turn.model),
                                            cs.compact_window(profile.path, turn.model)),
              "turn": turn.now(path, so_far["start"], cs.cache_dir(home) / "turns" / f"{chat_id}.json")}
    record = chatpick.job_record(profile, chat_id)   # (what /model and /effort's lists mark as what it uses now)
    result["options"] = chatpick.options_now(home, profile, chat_id, bool(peek.get("ultracode")), record)
    if reach:   # (the front end takes the limit before the stamp: an answer read for another limit isn't taken)
        result.update(limit=limit, reach=reach, reached=so_far.get("reached"))
    if gone is not None:
        if not gone.prompt and so_far.get("start"):   # (your message further back than what was read: a long turn's)
            before = turns.turn_before(path, so_far["start"], cs.cache_dir(home) / "turns" / f"{chat_id}.json")
            if before:
                gone.before(*before)
        # (what it waits for: a question its turn ended with; a prompt it waits on, the front ends know
        # from its row's state, as their ask box does: "permission" is any step not done yet)
        asks = "question" if ends.get("ended") == "asked" else ""
        result["away"] = gone.result(int(time.time() * 1000), so_far.get("whole", True), asks)
    if suggest:
        import replies
        ended = ends.get("ended")
        result.update(ended=ended, over=bool(ends.get("over")), asks=replies.asks_of(ends.get("reply")) if ended == "asked" else None,
                      predicted=predicted_reply(record) if ended == "asked" else None)
    return result


PREDICTED_CHARS = 300


def predicted_reply(record):
    """Claude's predicted reply to what its background chat asks you (its
    job's suggestedReply: PREDICT_ENV), while it waits for it (tempo
    "blocked", not a permission prompt), or None."""
    said = record.get("suggestedReply") if isinstance(record, dict) else None
    if not isinstance(said, str) or not said.strip() or record.get("tempo") != "blocked" or record.get("block"):
        return None
    return " ".join(said.split())[:PREDICTED_CHARS]


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


NOT_ASKING = "It isn't asking any more: answered in the chat or another window"
ANSWERED_ELSEWHERE = "It was just answered from another window"


def answer_file(path, answer):
    """Write a request's answer, the first one only (two windows, Plasma's
    and VS Code's, answering one prompt a moment apart: the second gets
    False, not "Allowed" when it was denied). Linked into place in one go
    (cs.write_atomic new: the hook never reads half an answer, which it
    would remove); where the folder takes no hard links (some FUSE or
    shared-folder homes), replaced as before."""
    data = json.dumps(answer, separators=(",", ":")).encode("utf-8")
    try:
        cs.write_atomic(path, data, mode=0o600, new=True)
    except FileExistsError:
        return False
    except OSError as exc:
        import errno
        if exc.errno not in (errno.EPERM, errno.ENOTSUP, errno.EOPNOTSUPP, errno.EXDEV, errno.EMLINK):
            raise
        if path.exists():
            return False
        cs.write_atomic(path, data, mode=0o600)
    return True


def answer_request(cache_root, request_id, decision, note="", answers=None):
    """Answer a relayed request: (ok, message). A question takes "answer"
    (answers: {question: [labels or text]}) or "deny". One that's gone:
    (False, NOT_ASKING); one its chat asked again after: (False, ASKS_ELSE);
    one another window answered first: (False, ANSWERED_ELSEWHERE)."""
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
    answer_path = folder / (request_id + ".answer.json")
    if not answer_file(answer_path, answer):
        return False, ANSWERED_ELSEWHERE
    deadline = time.time() + 5
    while (folder / (request_id + ".json")).exists() and time.time() < deadline:
        time.sleep(0.1)
    if (folder / (request_id + ".json")).exists():
        return False, "The chat didn't take the answer: answer it there"
    # (its hook takes the answer and removes it with the request; one still there came after the hook had
    # left: another window's answer, or the chat's own, came first)
    grace = time.time() + 0.3
    while answer_path.exists() and time.time() < grace:
        time.sleep(0.05)
    if answer_path.exists():
        try:
            answer_path.unlink()
        except OSError:
            pass
        return False, NOT_ASKING
    if plan:
        return True, {"approve": "Approved: it starts", "approve-edits": "Approved: it starts, accepting edits"}.get(
            decision, "It keeps planning" + (" with your note" if (note or "").strip() else ""))
    if inp is not None:
        return True, "Answered" if decision == "answer" else "Declined"
    return True, {"allow": "Allowed", "always": "Allowed, and from now on", "deny": "Denied"}[decision]


# ---------------------------------------------------------------- what the reply box offers

def chat_place(home, extra_dirs, chat_id, profile_key=None, cwd=None):
    """(profile, folder) of a chat, or (None, its error answer). chat_id "-"
    with cwd: a new chat's, in that folder on the profile profile_key."""
    if chat_id == "-" and cwd:
        profile = next((p for p in cs.discover_profiles(home, extra_dirs) if cs.matches_profile(p, profile_key)), None)
        if profile is None:
            return None, {"ok": False, "message": f"No Claude profile called {profile_key}"}
        return profile, os.path.expanduser(cwd)
    if not cs.valid_id(chat_id):
        return None, {"ok": False, "message": f"Not a chat: {chat_id}"}
    profile, path = find_transcript(home, extra_dirs, chat_id, profile_key)
    if path is None:
        return None, {"ok": False, "message": NO_CHAT}
    _, cwd, _ = cs.read_chat_info(path, path.stat().st_size)
    return profile, cwd or cs.chat_folder(path) or ""


def completions(home, extra_dirs, chat_id, profile_key=None, cwd=None):
    """What the reply box offers (--complete: commands.completions)."""
    profile, place = chat_place(home, extra_dirs, chat_id, profile_key, cwd)
    if profile is None:
        return place
    import commands   # (a module of its own, as replies.py: compiled once and kept)
    return commands.completions(profile, place)


def chat_replies(home, extra_dirs, cache_root, chat_id, profile_key=None, cwd=None, now=None):
    """--replies: your usual replies for a chat (replies.usual_replies), from the
    chats on its account. chat_id "-" with cwd: a new chat's, in that folder
    on the profile profile_key."""
    profile, cwd = chat_place(home, extra_dirs, chat_id, profile_key, cwd)
    if profile is None:
        return cwd
    import replies
    now = time.time() if now is None else now
    found = replies.usual_replies(replies.reply_history(cache_root, profile, now), now * 1000, replies.project_of(cwd),
                                  replies.hidden_replies(cache_root))
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


def tmux_type(entry, text, enter=True):
    """Paste text into a chat's tmux pane and send it (Enter; not with enter
    False: it waits in Claude's prompt for yours): (ok, message)."""
    base, target = tmux_base(entry)
    if base is None:
        return False, "It doesn't run in tmux (or tmux isn't installed)"
    # a buffer of its own: a reply typed meanwhile (each runs in its own
    # process) would else paste this text into its chat, or take it away
    _pastes[0] += 1
    buffer = f"talpy-den-{os.getpid()}-{_pastes[0]}"
    for args, data in ((["load-buffer", "-b", buffer, "-"], as_typed(text).encode()),
                       (["paste-buffer", "-p", "-d", "-b", buffer, "-t", target], None),
                       (["send-keys", "-t", target, "Enter"], None))[:3 if enter else 2]:
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


def send(home, extra_dirs, profile_key, chat_id, text, session_id=None, how="auto", claude=None, scoped=True,
         hooked=True, hook_source=None, predict=False):
    """Send your message to a chat the way it takes one (cs.reply_route):
    {"ok", "message", "how": "typed"|"background"|"vscode"|"copy"|"ask",
    "link" (vscode), "copied" (copy); woken in the background: "hooked",
    "hookWhy" (chat_hook_of)}. how "ask": the chat runs in a terminal that
    takes no text from outside, and you choose (how background or copy).
    scoped: a chat it wakes in the background in a systemd scope of its own
    (go_on_in_background; not on an SSH host or in a container); hooked:
    with the permission hook for it (chat_hook_of; hook_source: its code,
    from the computer that asks, for a host's copy)."""
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
    # (one wake of a chat at a time: Talpy Chat's window and VS Code's tab sending to one stopped chat
    # within a second or two would make Claude start a copy; the second waits for the first's wake,
    # then finds its session and replies to it)
    with cs.wake_lock(home, chat_id) as waited:
        if waited:
            cs.wake_settle(home, extra_dirs, chat_id)
        return send_now(home, extra_dirs, profile_key, chat_id, text, session_id, how, claude, scoped, profiles, profile,
                        hooked, hook_source, predict)


def send_now(home, extra_dirs, profile_key, chat_id, text, session_id, how, claude, scoped, profiles, profile,
             hooked=True, hook_source=None, predict=False):
    """send's sending, under its lock."""
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
    hook = chat_hook_of(home, next((p for p in profiles if cs.matches_profile(p, profile_key)), profile), hook_source,
                        predict, hooked)
    answer = go_on_in_background(home, extra_dirs, profile, chat_id, text, claude, scoped, hook["settings"])
    answer["how"] = "background"
    if hooked and answer.get("ok"):
        answer.update(hooked=hook["hooked"], **({"hookWhy": hook["why"]} if hook["why"] else {}))
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


def type_in(home, extra_dirs, profile_key, chat_id, text, session_id=None, copy=True):
    """A command that needs Claude's own panel or dialog (commands.py: kind
    "terminal"), put where Claude's prompt is, for you to press Enter there:
    typed into its tmux pane (not sent), into its Claude Code panel's input
    (the link), else on the clipboard (copy False: not here, on an SSH host:
    the text comes back), and the caller opens the chat's terminal. {"ok",
    "how": "typed"|"vscode"|"copy", "message", "link", "copied", "text"}."""
    text = (text or "").strip()
    if not text:
        return {"ok": False, "message": "Write the command first"}
    if not cs.valid_id(chat_id):
        return {"ok": False, "message": f"Not a chat: {chat_id}"}
    entry = None
    for sid in (session_id, chat_id):
        if cs.valid_id(sid or ""):
            entry = cs.find_chat_entry(home, extra_dirs, sid, profile_key)
            if entry is not None:
                break
    asks = entry is not None and cs.session_state(entry) == "waiting"
    if entry is not None and entry.get("kind") == "interactive" and entry.get("tmux") and not asks:
        ok, message = tmux_type(entry, text, enter=False)
        if ok:
            return {"ok": True, "how": "typed", "message": "It's typed into its terminal: press Enter there"}
    if entry is not None and entry.get("entrypoint") == "claude-vscode":
        return {"ok": True, "how": "vscode", "link": vscode_prompt_link(entry["sessionId"], text),
                "message": "It's in the chat's input in VS Code: press Enter there"}
    copied = copy and copy_to_clipboard(text)
    first = "It's asking you something: answer that first, then paste it there" if asks else "Paste it into its terminal"
    return {"ok": True, "how": "copy", "copied": copied, "text": "" if copied else text,
            "message": ("It's in the clipboard. " + first) if copied else first}


def start_chat(home, extra_dirs, profile_key, folder, text, model=None, effort=None, mode=None, plan=None,
               plan_profile=None, claude=None, scoped=True, hook_source=None, predict=False):
    """A new chat Talpy Chat starts with your first message (text; or a
    plan's, with what you add): in the background on the profile, in folder
    (claude --bg, in a systemd scope of its own unless not scoped, as on an
    SSH host or in a container: go_on_in_background), with that model,
    effort and permission mode, and the permission hook for it alone
    (chat_hook_of; hook_source: its code, from the computer that asks, for a
    host's copy), so what it asks is answered in Talpy Chat. Only in a
    folder Claude trusts (a background chat can't ask: "untrusted" true).
    {"ok", "message", "how": "background", "id": its job's short id, "chat":
    its chat id (from its job's record), "profileDir", "hooked" (whether
    Talpy Chat answers what it asks), "hookWhy" (why not)}."""
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
    hook = chat_hook_of(home, profile, hook_source, predict)
    options = (["--settings", hook["settings"]] if hook["settings"] else []) + options + cs.picture_options(home, text)
    prefix = []
    if scoped:
        import jump
        prefix = jump.scope_prefix("claude")
    folder = os.path.expanduser(folder) if isinstance(folder, str) and folder.strip() else str(home)
    ok, message, job = cs.start_background(profile, folder, cs.task_prompt(text, plan_path, home), home, claude,
                                           prefix=prefix, options=options)
    if not ok:
        return {"ok": False, "message": message, **({"untrusted": True} if message.startswith(cs.UNTRUSTED) else {})}
    chat = job_chat(profile, job)
    if chat is None:
        return {"ok": False, "message": f"It started ({job}), but its chat isn't there to show: find it in the list"}
    return {"ok": True, "how": "background", "id": job, "chat": chat, "profileDir": profile.key,
            "message": "Started in the background on " + profile.label, "hooked": hook["hooked"],
            **({"hookWhy": hook["why"]} if hook["why"] else {})}


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
    ~/.claude that Claude has had no chat in yet): cs.claude_settings_files."""
    return cs.claude_settings_files(home, cs.discover_profiles(home, extra_dirs))


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
    """Write a settings.json (through a link, keeping its mode): one writer
    of Claude's settings for every helper (talpy_den.write_claude_settings)."""
    cs.write_claude_settings(path, data)


def upgrade_hooks(home, extra_dirs=()):
    """Settings that name a hook with the command an older version wrote get
    today's (hook_command) in each of its events, as turning it on again
    would do: how many files changed."""
    changed = 0
    with cs.claude_settings_lock(home):  # (read to written: another helper's change isn't lost)
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


def install_hook(home, extra_dirs, on, kind, source=None, keep_copy=False):
    """Put the hook in each profile's settings (on) or take it out: how many
    settings files changed (ValueError: one isn't JSON). source: the hook's
    code (else its file next to this one): a copy that's there is replaced
    only by a newer one (place_hook). keep_copy: taken out, its copy stays
    (chats Talpy Chat started name it in settings of their own)."""
    target = hook_path(home, kind)
    if on:
        placed, why = place_hook(home, kind, source)
        if placed is None:
            raise ValueError("Talpy Den couldn't put its hook in place: " + why)
    changed = 0
    with cs.claude_settings_lock(home):  # (read to written: another helper's change isn't lost)
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
    if not on and not keep_copy:
        try:
            target.unlink()
        except OSError:
            pass
    return changed


def relay(home, extra_dirs, on, source=None, keep_copy=False):
    """Put the permission hook in each profile's settings (on) or take it
    out: (ok, message). source: the hook's code (else permission_hook.py
    next to this file). keep_copy: taken out, the chats Talpy Chat started
    keep theirs (hooked_chats: they still answer their prompts in Talpy
    Chat); else its copy goes, and they ask in their own prompt."""
    try:
        changed = install_hook(home, extra_dirs, on, "relay", source, keep_copy)
    except ValueError as exc:
        return False, str(exc)
    if on:
        return True, "Permission prompts can be answered from Talpy Den" + ("" if changed else " (they could already)")
    if keep_copy:
        return True, "Permission prompts are answered in the chats, but for the chats started from Talpy Chat"
    return True, "Permission prompts are answered in the chats only"


def hooked_chats(home, extra_dirs):
    """How many background chats answer their prompts in Talpy Chat with the
    hook of their own Talpy Chat gave them (their jobs' saved options name
    it: talpy_den.hook_settings), on each profile."""
    count = 0
    for profile in cs.discover_profiles(home, extra_dirs):
        try:
            jobs = list((profile.path / "jobs").iterdir())
        except OSError:
            continue
        for job in jobs:
            record = cs.read_json(job / "state.json")
            if isinstance(record, dict) and cs.hook_settings(record.get("respawnFlags")):
                count += 1
    return count


def forget_hook(home, extra_dirs):
    """An SSH host (or a container) taken off Talpy Den's list: the permission
    hook's copy Talpy Chat put there, and its requests folder, go, unless a
    chat Talpy Chat started there still runs (it would ask in its own prompt
    then) or the hook is on for every chat there (its settings name the copy).
    {"ok", "message", "kept": the chats that run with it, or "every"}."""
    if relay_status(home, extra_dirs)["some"]:
        return {"ok": True, "kept": "every", "message": "Its permission hook stays: it's on for every chat there"}
    running = 0
    for entry, runs_on, _holder in cs.live_entries_all(cs.discover_profiles(home, extra_dirs)):
        if entry.get("kind") == "bg" and cs.valid_id(entry.get("jobId") or "") and not entry.get("spare"):
            job = cs.read_job([runs_on], entry["jobId"])
            running += bool(isinstance(job, dict) and cs.hook_settings(job.get("respawnFlags")))
    if running:
        return {"ok": True, "kept": running, "message": plural(running, "chat") + " Talpy Chat started there still "
                + ("runs" if running == 1 else "run") + ": its permission hook stays there for them"}
    # (a request waiting there is a hook still waiting: a chat that runs where this one can't see it, as in a
    # home shared over the network; nothing goes then, and the folder only once it's empty)
    folder = cs.requests_dir(cs.cache_dir(home))
    if any(n.endswith(".json") and not n.endswith(".answer.json") for n in cs.names_in(folder)):
        return {"ok": True, "kept": "asking", "message": "A chat there is asking something through its permission hook: it stays"}
    gone = []
    target = hook_path(home)
    try:
        target.unlink()
        gone.append(target.name)
    except OSError:
        pass
    try:
        if folder.is_dir() and not folder.is_symlink():
            for name in cs.names_in(folder):   # (answers nobody took)
                (folder / name).unlink()
            folder.rmdir()
            gone.append(folder.name)
    except OSError:
        pass
    return {"ok": True, "message": "Talpy Den's permission hook and its requests are gone from there" if gone else "Nothing of Talpy Chat's there"}


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


def place_hook(home, kind="relay", source=None):
    """The hook's copy in Talpy Den's data folder (a chat Talpy Chat starts
    names it in settings of its own, while the setting for every chat may be
    off): (its path, or None and why not). One that's there stays, unless
    source (the hook's code, sent by the computer that asks: on an SSH host
    or in a container this file comes on stdin, without the hooks) is newer
    (its HOOK_REVISION, as talpy_den.refresh_hooks has it: front ends of
    other versions never make it older). With none there, it's written from
    source, else from the hook next to this file: in one go, 0600, in a
    folder only you may write in (cs.safe_folder: Claude runs it as you)."""
    target = hook_path(home, kind)
    why = cs.safe_folder(target.parent)
    if why:
        return None, why
    try:   # (a copy that isn't a plain file of yours alone is no copy: it's written anew)
        installed = target.read_bytes() if cs.own_file(target) else None
    except OSError:
        installed = None
    new = source.encode("utf-8") if isinstance(source, str) else None
    if installed is not None and (new is None or cs.hook_revision(new) <= cs.hook_revision(installed)):
        return target, ""
    if new is None:
        try:
            new = (Path(__file__).resolve().parent / HOOKS[kind]["source"]).read_bytes()
        except (OSError, NameError):
            return None, "its code isn't here to copy"
    try:
        cs.write_atomic(target, new, mode=0o600)
    except OSError as exc:
        return None, f"couldn't write {cs.short_path(str(target), home)}: {exc.strerror or exc}"
    return target, ""


# Claude's predicted next prompt (its grey suggestion in a terminal), for a
# chat Talpy Chat starts or wakes while Suggest replies is on: a background
# chat writes it into its job's record (suggestedReply) once a reply of
# Claude's ends asking you something, and Talpy Chat shows it as the first
# chip. Off by default for many accounts (a flag of Claude's own, and off
# near a usage limit): this turns it on for that chat alone (Claude Code
# 2.1.318, live-checked: research Q4)
PREDICT_ENV = {"CLAUDE_CODE_ENABLE_PROMPT_SUGGESTION": "true"}


def hook_copy(home, kind="relay", source=None):
    """place_hook's path, or None (no hook here to copy, or nowhere safe to put it)."""
    return place_hook(home, kind, source)[0]


def chat_hook_of(home, profile, source=None, predict=False, hook=True):
    """Settings of its own for one chat, as claude --settings takes them
    (JSON). The permission hook (the same entry --relay on writes), so a
    background chat Talpy Chat starts or wakes asks its permission prompts
    and questions where Talpy Chat answers them: it has no terminal to ask
    in. Here, on an SSH host or in a container (source: the hook's code,
    from the computer that asks: place_hook). {"settings": that JSON or
    None, "hooked": whether Talpy Chat answers what the chat asks, "why":
    why not}. No hook of its own when the profile's own settings have the
    hook (on for every chat: it would run twice; hooked all the same), or
    managed settings let only their own hooks run (not hooked); none either
    with hook False. predict: Claude's predicted reply on too (PREDICT_ENV)."""
    settings, hooked, why = {}, False, ""
    if not hook:
        pass
    elif cs.managed_hooks_only():
        why = "managed settings let only their own hooks run"
    elif has_hook(cs.read_json(profile.path / "settings.json") or {}):
        hooked = True
    else:
        target, why = place_hook(home, source=source)
        if target is None:
            why = "Talpy Den couldn't put its permission hook in place: " + why
        else:
            settings, hooked, why = set_hook({}, hook_command(target), True), True, ""
    if predict:
        settings["env"] = dict(PREDICT_ENV)
    return {"settings": json.dumps(settings, separators=(",", ":")) if settings else None, "hooked": hooked, "why": why}


def chat_hook(home, profile, source=None, predict=False):
    """chat_hook_of's settings: the JSON, or None."""
    return chat_hook_of(home, profile, source, predict)["settings"]


def relay_status(home, extra_dirs, kind="relay"):
    """{"ok", "on", "some", "settings"; the permission hook's: "hooked", how many
    chats Talpy Chat started answer their prompts with a hook of their own}."""
    files = settings_files(home, extra_dirs)
    on = [has_hook(cs.read_json(p) or {}, kind) for p in files]
    out = {"ok": True, "on": bool(on) and all(on), "some": any(on), "settings": [str(p) for p in files]}
    if kind == "relay":
        out["hooked"] = hooked_chats(home, extra_dirs)
    return out


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


def reply_text(home, extra_dirs, chat_id, profile_key, key):
    """--reply-text: the whole text of the reply (or prompt) with that key."""
    if not cs.valid_id(chat_id) or not key:
        return {"ok": False, "message": f"Not a chat: {chat_id}" if not cs.valid_id(chat_id) else "Which message?"}
    _, path = find_transcript(home, extra_dirs, chat_id, profile_key)
    if path is None:
        return {"ok": False, "missing": True, "message": NO_CHAT}
    import replies
    text = replies.whole_text(path, key)
    return {"ok": True, "text": text} if text is not None else {"ok": False, "message": "That message isn't in the chat any more"}


# The modules each action imports, sent along with this file to an SSH host
# (each is ~10-40 ms more to send and compile there); any other action gets them all
ACTION_MODULES = {
    "--conversation": ("reply_words.py", "replies.py", "commands.py", "turns.py", "chatpick.py", "made.py"),
    "--made": ("made.py",), "--bookmark": (),
    "--complete": ("commands.py",), "--replies": ("reply_words.py", "replies.py"),
    "--reply-text": ("reply_words.py", "replies.py"), "--hide-reply": ("reply_words.py", "replies.py"),
    "--set-options": ("chatpick.py",),
    "--send": (), "--start": (), "--answer": (), "--interrupt": (), "--keys": (), "--type-in": (), "--relay": (),
    "--live": (), "--review": (), "--undo": (), "--commit": (),
}
# A start or a wake there may wait for claude's background service (60 s),
# after asking the login shell for claude: longer than other actions
HOST_START_TIMEOUT = 110
MAY_HAVE_STARTED = "{where} didn't answer in time: the chat may have started there, so look for it in the list before you send it again"


def forward(host, args, action=None):
    """Run this file on an SSH host (or in a container) with args: its answer."""
    import remote
    also = ACTION_MODULES.get(action, ("reply_words.py", "replies.py", "commands.py", "turns.py", "chatpick.py", "made.py"))
    long = action in ("--start", "--send")
    answer = remote.host_answer(host, args, name="pane.py", also=also,
                                timeout=HOST_START_TIMEOUT if long else remote.RUN_TIMEOUT)
    if long and answer.get("timedOut"):   # (it got there and took too long: sent again, it could start a second chat)
        answer = dict(answer, maybe=True, message=MAY_HAVE_STARTED.format(where=remote.place(host).label))
    return answer


def main(argv=None):
    args = sys.argv[1:] if argv is None else list(argv)
    rest, host, i = [], "", 0  # rest: the arguments as a host gets them (no --host, --remote, --pretty)
    while i < len(args):
        if args[i] == "--host" and i + 1 < len(args):
            host, i = args[i + 1], i + 2
            continue
        # (--wait: not over ssh, a host's chat is looked at again instead; --seen: kept here)
        if args[i] in ("--wait", "--seen") and i + 1 < len(args):
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
               "--hide-reply", "--type-in", "--reply-text", "--set-options", "--bookmark", "--made")
    osd, suggest, no_copy, keep_copy, as_file, made_path, step = False, False, False, False, False, None, None
    cwd, model, effort, mode, plan, plan_profile, key = None, None, None, None, None, None, None
    mark_kind, mark_at, reach = "", 0, None   # (--bookmark's --kind and --at; --conversation's --reach)
    seen, away, since = 0, False, None   # (--conversation's --seen MS, --away and, on a host, --since)
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
        elif arg == "--key" and args:
            key = args.pop(0)
        elif arg == "--path" and args:
            made_path = args.pop(0)
        elif arg == "--step" and args:
            step = args.pop(0)
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
        elif arg == "--kind" and args:
            mark_kind = args.pop(0)
        elif arg == "--at" and args and args[0].isdigit():
            mark_at = int(args.pop(0))
        elif arg == "--reach" and args:
            reach = args.pop(0)
        elif arg == "--since" and args and args[0].isdigit():
            since = int(args.pop(0))
        elif arg == "--seen" and args and args[0].isdigit():
            seen = int(args.pop(0))
        elif arg == "--away":
            away = True
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
        elif arg == "--no-copy":
            no_copy = True
        elif arg == "--keep-copy":
            keep_copy = True
        elif arg == "--as-file":
            as_file = True
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
        if action == "--bookmark":  # (kept here, a host's chat's too, as stars are: never forwarded)
            ok, said, marks, v = cs.change_bookmark(cache_root, target, host, key or "", not off, mark_kind, mark_at, text or "")
            return emit({"ok": ok, "message": said, "bookmarks": marks, "bookmarksV": v})
        if host and action == "--reviewed":  # (kept here, as stars are)
            mark_reviewed(cache_root, target, host, on=not off)
            return emit({"ok": True, "message": "Marked reviewed" if not off else "Not marked reviewed"})
        if host and action == "--send" and how == "copy":  # (the clipboard is this computer's)
            return emit(copy_answer((text or "").strip()))
        if host and action == "--send" and after:  # (queued here: the widget here sends it then)
            ok, said = send_later(home, config_dirs, profile, target, text, session, how, host, name)
            return emit({"ok": ok, "message": said})
        if host:
            # (the hook's code goes along, on stdin: its copy there, for the chats Talpy Chat starts or
            # wakes there, or for every chat; a copy there that's newer stays)
            hook_kind = action[2:] if action in ("--relay", "--live") and target == "on" else \
                "relay" if action in ("--start", "--send") else None
            if hook_kind and source is None:
                path = Path(__file__).resolve().parent / HOOKS[hook_kind]["source"]
                rest += ["--hook-source", base64.b64encode(path.read_bytes()).decode()]
            if action == "--conversation" and away and since is None:   # (how far a window here last showed it)
                rest += ["--since", str(cs.seen_mark(cache_root, target, host))]
            if action == "--conversation" and seen:   # (the host's times, kept here)
                cs.mark_seen(cache_root, target, host, seen)
            answer = forward(host, rest, action)
            if action == "--review" and answer.get("ok"):
                answer["reviewedAt"] = cs.load_reviewed(cache_root).get(cs.review_key(target, host))
            if action == "--conversation" and answer.get("ok"):
                pictures_here(answer.get("items"))
                if not answer.get("unchanged"):   # (--reach went with the rest: the host reads that far)
                    cs.bookmarks_answer(answer, cache_root, target, host)
            if action == "--made" and as_file:   # (its picture as a file here, for Plasma's Talpy Chat)
                import made
                answer = made.keep_copy(str(cs.images_dir(home)), f"{host}\0{target}\0{step or made_path}", answer)
            if action in ("--send", "--type-in"):
                answer = host_vscode_link(answer, (session, target), text)
            if action == "--send" and how == "enter" and answer.get("how") == "ask":
                answer = copy_answer((text or "").strip(), ENTER_COPIES)  # (here, as above)
            return emit(answer)
        if action == "--conversation":
            # (pasted pictures saved for the thumbnails: not on an SSH host, where the pane doesn't look)
            if away and since is None and not remote:
                since = cs.seen_mark(cache_root, target)
            if seen and not remote:   # (before the read: its wait can be long; a host's: kept by the computer asking)
                cs.mark_seen(cache_root, target, "", seen)
            result = chat_conversation(home, config_dirs, target, profile, limit, stamp, wait,
                                       None if remote else cs.images_dir(home), suggest, reach,
                                       (since or 0) if away else None)
            if not remote and result.get("ok") and not result.get("unchanged"):   # (a host's: kept here, above)
                cs.bookmarks_answer(result, cache_root, target)
        elif action == "--send":
            if after:
                ok, said = send_later(home, config_dirs, profile, target, text, session, how, "", name)
                result = {"ok": ok, "message": said}
            else:
                result = send(home, config_dirs, profile, target, text, session, how, scoped=not remote,
                              hook_source=source, predict=suggest)
                if how == "enter" and result.get("how") == "ask" and not remote:  # (on a host: copied here, above)
                    result = copy_answer((text or "").strip(), ENTER_COPIES)
        elif action == "--start":
            result = start_chat(home, config_dirs, target, cwd, text, model, effort, mode, plan, plan_profile,
                                scoped=not remote, hook_source=source, predict=suggest)
        elif action == "--interrupt":
            ok, said = interrupt(home, config_dirs, profile, target, session)
            result = {"ok": ok, "message": said}
        elif action == "--set-options":
            import chatpick   # (a module of its own, as replies.py: compiled once and kept)
            prefix = []
            if not remote:   # (a chat woken again here: in a systemd scope of its own, as go_on_in_background's)
                import jump
                prefix = jump.scope_prefix("claude")
            result = chatpick.set_options(home, config_dirs, profile, target, model, effort, prefix=prefix)
        elif action == "--made":
            import made   # (a module of its own, as replies.py: compiled once and kept)
            found = find_transcript(home, config_dirs, target, profile)[1] if cs.valid_id(target) else None
            result = made.show(found, made_path, step, as_file and not remote) if found is not None \
                else {"ok": False, "missing": True, "message": NO_CHAT}
            if as_file and not remote:   # (what Claude saw, as a file here, for Plasma's Talpy Chat)
                result = made.keep_copy(str(cs.images_dir(home)), f"\0{target}\0{step or made_path}", result)
        elif action == "--type-in":
            result = type_in(home, config_dirs, profile, target, text, session, copy=not (remote or no_copy))
        elif action == "--answer":
            ok, said = answer_request(cache_root, target, decision, note, answers)
            # (changed: the request you answered is gone; the chat may ask something else now)
            result = {"ok": ok, "message": said,
                      **({"changed": True} if not ok and said in (NOT_ASKING, ASKS_ELSE, ANSWERED_ELSEWHERE) else {})}
        elif action == "--complete":
            result = completions(home, config_dirs, target, profile, cwd)
        elif action == "--replies":
            result = chat_replies(home, config_dirs, cache_root, target, profile, cwd)
        elif action == "--reply-text":
            result = reply_text(home, config_dirs, target, profile, key)
        elif action == "--hide-reply":
            import replies
            ok, said = replies.hide_reply(cache_root, target, on=not off)
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
            elif target == "forget" and kind == "relay":   # (a host taken off the list: forget_hook, there)
                result = forget_hook(home, config_dirs)
            elif target in ("on", "off"):
                ok, said = relay(home, config_dirs, target == "on", source, keep_copy) if kind == "relay" \
                    else live(home, config_dirs, target == "on", source)
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
