"""Talpy Chat's suggested replies, for pane.py (a module of its own: compiled once
and kept, as talpy_den.py is, where pane.py, run as a script, is compiled at
every call):

- TurnEnd: how Claude's turn ended, followed entry by entry (pane.py's
  conversation_items, and the reads below);
- asks_of: the question Claude's reply ends with, as chips, by its shape;
  the few words it looks at are a table per language in reply_words.py;
- usual_replies, from reply_history: what you usually reply after a turn
  that ended the same way, from your chats on that account;
- hide_reply: a reply you don't want suggested again;
- whole_text: a reply (or prompt) all of it, for Copy where the
  conversation shows it cut.

Python 3.7+ and the standard library only (the SSH host backend too).
"""
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import talpy_den as cs

INTERRUPTED = "[Request interrupted"   # (as pane.py's)


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
        # (the question's own start still there, as no either/or start took it: "Should the next file be named
        # alpha.txt or beta.txt?": the first half is as long as the second, at its end)
        if any(verb.match(left.lower()) for _, verb in rules["verbs"]) and len(left.split()) > len(right.split()):
            left = " ".join(left.split()[-len(right.split()):])
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


THOUGHT = "/thinking"   # (pane.THOUGHT)


def whole_text(path, key):
    """All of a reply of Claude's (key: its message's id, or its entry's uuid),
    joined as pane.py's conversation_items joins it, or of the thinking lines
    Claude Code wrote with it (thinking shown as updates; key: the reply's and
    THOUGHT), or of a prompt of yours (key: its entry's uuid), for Copy where
    Talpy Chat shows it cut; None if no entry has that key. Only the lines the
    key is in are parsed."""
    thought = key.endswith(THOUGHT)
    key = key[:-len(THOUGHT)] if thought else key
    needle = json.dumps(key)[1:-1].encode("utf-8")
    said, prompt = [], None
    try:
        with open(path, "rb") as f:
            for line in f:
                if needle not in line:
                    continue
                try:
                    e = json.loads(line)
                except (ValueError, RecursionError):
                    continue
                if not isinstance(e, dict) or e.get("isSidechain"):
                    continue
                msg, blocks = cs.blocks_of(e)
                if e.get("type") == "user" and e.get("uuid") == key:
                    prompt = cs.human_prompt(e)
                elif e.get("type") == "assistant" and not e.get("isApiErrorMessage") \
                        and (msg.get("id") == key or e.get("uuid") == key):
                    updates = e.get("thinkingDisplay") == "updates"
                    for c in blocks:
                        text = c.get("thinking") if thought and updates and c.get("type") == "thinking" \
                            else c.get("text") if not thought and c.get("type") == "text" else None
                        if isinstance(text, str) and text.strip():
                            said.append(text.strip())
    except OSError:
        return None
    return "\n\n".join(said) if said else prompt
