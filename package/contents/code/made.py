"""What Claude made, in Talpy Chat (pane.py): the pictures, plans and pages a
chat's steps wrote, edited or read, and the pictures its replies and its
commands name, each a line of its own under the step or the reply, folded:
"icon.svg · 2 KB", "Plan: …", "page.html". All of it comes from the
transcript, so nothing is added to what Claude reads, and it's there for chats
started anywhere:

- Write, Edit, MultiEdit and NotebookEdit of a picture (png, jpg, gif, webp,
  svg), a page (html) or a plan (Markdown in a plans folder: Claude's own
  <config>/plans, a project's .claude/plans);
- Read results that carry an image: the picture Claude saw, which the
  transcript keeps (a screenshot in a folder long emptied, a file written
  again since); a PDF's: a file, opened only;
- a Bash step whose output names a picture file that's there and newer than
  the turn;
- picture paths a reply names that are there.

(ExitPlanMode's plan is A11's card: AskedCard, already shown in the Chat tab.)

Folded, only a name and a size are known: from the transcript, else one stat
per file at each read (Collector.place; the same file once). Unfolded, the
front end shows a picture of this computer from its file itself (loaded
asynchronously, scaled down), and asks show() (pane.py --made) for what Claude
saw, a page's or a plan's first lines and an SSH host's picture: one file the
chat's transcript names, of those types, a plain file, capped in size.

A module of its own, as replies.py: compiled once and kept, where pane.py, run
as a script, is compiled at every call. Python 3.7+ and the standard library
only (the SSH host backend too).
"""
import base64
import hashlib
import json
import mmap
import os
import re
import stat

import talpy_den as cs

PICTURES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
            ".webp": "image/webp", ".svg": "image/svg+xml"}
PICTURE_MIMES = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp"}   # (as Claude sees them)
STEP_ID = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
PAGES = (".html", ".htm")
PLANS = (".md", ".markdown")
FILES = {".pdf": "application/pdf"}   # (a Read result's document: opened only, never read here)
STEP_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")

# A picture's name in a text: a quick look first (most texts have none), then each path, up
# to NAMED_MAX of them (a word of the text that ends with a picture's extension: absolute,
# ~/…, or relative to the chat's folder; "https://…" and globs left out)
PICTURE_IN = re.compile(r"\.(?:png|jpe?g|gif|webp|svg)(?![\w-])", re.I)
PICTURE_PATH = re.compile(r"[^\s`'\"()\[\]<>{}|,;:=*?]+\.(?:png|jpe?g|gif|webp|svg)(?![\w-])", re.I)
NAMED_MAX = 12
NEW_SLACK_MS = 2000   # (a file a little older than the turn's start: the clocks of the write and the transcript)

PICTURE_SHOW_MAX = 8 << 20   # bytes of a picture shown unfolded (an SVG: SVG_SHOW_MAX; base64, an SSH host's answer stays under remote.ANSWER_MAX)
SVG_SHOW_MAX = 2 << 20
TEXT_SHOW_BYTES = 256 << 10   # of a page's or a plan's text
PLAN_LINES = 3000
SOURCE_LINES = 400
TRANSCRIPT_LOOK_MAX = 512 << 20   # (a transcript bigger than this isn't searched for the name: refused)


def in_plans(path):
    """Is it in a plans folder (Claude's <config>/plans, a project's .claude/plans, or below one)?"""
    return "plans" in path.split("/")[:-1]


def type_of(path, plans=True):
    """What a file is to Talpy Chat: "picture", "page", "plan" (plans: Markdown in a plans folder)
    or None."""
    ext = os.path.splitext(path)[1].lower()
    if ext in PICTURES:
        return "picture"
    if ext in PAGES:
        return "page"
    if plans and ext in PLANS and in_plans(path):
        return "plan"
    return None


def heading(text):
    """A Markdown text's title: its first heading's words, else None."""
    for line in (text or "").split("\n", 200)[:200]:
        s = line.strip()
        if s.startswith("#"):
            title = s.lstrip("#").strip()
            if title:
                return cs.short_text(title, 80)
    return None


def named_paths(text, cwd):
    """The picture files a text names (absolute, normalized), each once, at most NAMED_MAX;
    relative ones from cwd (none without it)."""
    out = []
    if not text or not PICTURE_IN.search(text):
        return out
    home = os.path.expanduser("~")
    for m in PICTURE_PATH.finditer(text):
        word = m.group(0)
        if word.startswith("//") and not word.startswith("///"):   # (a link's host: https://host/…)
            continue
        if word.startswith("~/"):
            path = home + word[1:]
        elif word.startswith("/"):
            path = word
        elif isinstance(cwd, str) and cwd.startswith("/"):
            path = os.path.join(cwd, word)
        else:
            continue
        path = os.path.normpath(path)
        if path not in out:
            out.append(path)
            if len(out) >= NAMED_MAX:
                break
    return out


def results_of(block, kind):
    """The blocks of a tool result's content of that kind ("image", "document")."""
    content = block.get("content")
    return [c for c in content if isinstance(c, dict) and c.get("type") == kind] if isinstance(content, list) else []


class Collector:
    """What a chat made, gathered as its conversation is read (pane.py
    conversation_items: step() at each tool result that went through, reply()
    at each reply), then placed under the steps and replies that made or
    named it (place)."""

    def __init__(self):
        self.steps = {}    # a step's key -> [(path, type, size from the transcript, how: "made"|"new")]
        self.titles = {}   # a plan's path -> its title (from a Write of it)
        self.folders = {}  # a reply's key -> the chat's folder then
        self.stats = {}    # path -> os.stat_result or None (one stat a file at each read)

    def step(self, item, inp, block, result, output, cwd):
        """A tool call that went through (item: its pane item; inp: what it was asked;
        block: its tool_result; result: the entry's toolUseResult when it's this call's;
        output: what came back, as text; cwd: the chat's folder then)."""
        name = item.get("name")
        made = None
        if name in STEP_TOOLS:
            path = inp.get("file_path") or inp.get("notebook_path")
            if isinstance(path, str) and path.startswith("/"):
                path = os.path.normpath(path)
                kind = type_of(path)
                if kind is not None:
                    content = inp.get("content") if name == "Write" and isinstance(inp.get("content"), str) else None
                    if kind == "plan" and content is not None:
                        self.titles[path] = heading(content) or self.titles.get(path)
                    made = [(path, kind, len(content.encode("utf-8", "replace")) if content is not None else None, "made")]
        elif name == "Read":
            path = inp.get("file_path")
            if isinstance(path, str) and path.startswith("/"):
                path = os.path.normpath(path)
                ext = os.path.splitext(path)[1].lower()
                file = result.get("file") if isinstance(result, dict) and isinstance(result.get("file"), dict) else {}
                size = file.get("originalSize") if isinstance(file.get("originalSize"), int) else None
                seen = [s.get("data") for s in (i.get("source") for i in results_of(block, "image"))
                        if isinstance(s, dict) and s.get("media_type") in PICTURE_MIMES and isinstance(s.get("data"), str)]
                if seen:   # (what Claude saw: the transcript has it, whatever became of the file)
                    made = [(path, "picture", size if size is not None else len(seen[0]) * 3 // 4 - seen[0][-2:].count("="),
                             ("seen", hash(seen[0])))]
                elif ext == ".svg" and output:
                    made = [(path, "picture", None, "made")]
                elif results_of(block, "document") and ext in FILES:
                    made = [(path, "file", size, "made")]
        elif name == "Bash" and output:
            made = [(p, "picture", None, "new") for p in named_paths(output, cwd)]
        if made:
            self.steps[item["key"]] = made

    def reply(self, item, cwd):
        """A reply of Claude's (its folder, for the pictures it names: place)."""
        if isinstance(cwd, str):
            self.folders[item["key"]] = cwd

    def stat(self, path):
        if path not in self.stats:
            try:
                st = os.stat(path)
                self.stats[path] = st if stat.S_ISREG(st.st_mode) else None
            except (OSError, ValueError):
                self.stats[path] = None
        return self.stats[path]

    def place(self, items):
        """items with what was made after each step and reply that made or named it: {"kind":
        "made", "key": "<its key>/made/<n>", "of": its key, "at", "text" (its name, or "Plan: "
        and its title), "made": {"path", "type", "name", "size" (bytes, or None), "gone" (made
        by a step, not there now), "step" (a Read's: what Claude saw is in the transcript,
        show(step=…))}}. A file shows once a turn, under the first that made or named it (a
        picture Claude read: each other picture it saw there); one a command or a reply names
        only when it's there (a command's, when it's newer than the turn)."""
        out, start, shown = [], None, set()
        for it in items:
            out.append(it)
            kind = it.get("kind")
            if kind == "you":
                if not it.get("answered") and not it.get("queued"):
                    start, shown = it.get("at"), set()   # (a turn of its own)
                continue
            if kind == "tool":
                found = self.steps.get(it.get("key"))
            elif kind == "claude" and PICTURE_IN.search(it.get("text") or ""):
                found = [(p, "picture", None, "named") for p in named_paths(it.get("text"), self.folders.get(it.get("key")))]
            else:
                continue
            for n, (path, what, size, how) in enumerate(found or ()):
                seen = isinstance(how, tuple)
                if (path, how[1]) in shown if seen else path in shown:
                    continue
                st = None if seen else self.stat(path)
                if how in ("new", "named"):
                    since = start if start is not None else it.get("at")
                    if st is None or (how == "new" and since and st.st_mtime_ns // 1000000 < since - NEW_SLACK_MS):
                        continue
                shown.add(path)   # (a reply that names a picture Claude read or made here: shown already)
                if seen:
                    shown.add((path, how[1]))
                name = os.path.basename(path)
                made = {"path": path, "type": what, "name": name, "size": st.st_size if st is not None else size}
                if seen:
                    made["step"] = it["key"]
                elif st is None:
                    made["gone"] = True
                title = (self.titles.get(path) or os.path.splitext(name)[0]) if what == "plan" else None
                out.append({"kind": "made", "key": f"{it['key']}/made/{n}", "of": it["key"], "at": it.get("at"),
                            "text": "Plan: " + title if title else name, "made": made})
        return out


# ---------------------------------------------------------------- unfolded (pane.py --made)

def lines_with(transcript, needle, most):
    """The transcript's lines (bytes) that have needle, the first most of them; [] for a
    transcript over TRANSCRIPT_LOOK_MAX or none."""
    out = []
    try:
        with open(transcript, "rb") as f:
            size = os.fstat(f.fileno()).st_size
            if not needle or size == 0 or size > TRANSCRIPT_LOOK_MAX:
                return out
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as m:
                at = m.find(needle)
                while at >= 0 and len(out) < most:
                    end = m.find(b"\n", at)
                    end = size if end < 0 else end
                    out.append(m[m.rfind(b"\n", 0, at) + 1:end])
                    at = m.find(needle, end)
    except (OSError, ValueError):
        return []
    return out


def named_in(transcript, path):
    """Does the transcript name the file (its name, as it's written there)?"""
    return bool(lines_with(transcript, json.dumps(os.path.basename(path), ensure_ascii=False)[1:-1].encode("utf-8"), 1))


def seen_in(transcript, step):
    """(mime, base64) of the picture a Read step got (what Claude saw), from the transcript; else None."""
    for line in lines_with(transcript, step.encode("ascii"), 8):
        try:
            e = json.loads(line)
        except (ValueError, RecursionError):
            continue
        content = e["message"].get("content") if isinstance(e, dict) and isinstance(e.get("message"), dict) else None
        for c in content if isinstance(content, list) else ():
            if isinstance(c, dict) and c.get("type") == "tool_result" and c.get("tool_use_id") == step:
                for s in (i.get("source") for i in results_of(c, "image")):
                    if isinstance(s, dict) and s.get("media_type") in PICTURE_MIMES and isinstance(s.get("data"), str):
                        return s["media_type"], s["data"]
    return None


def not_made():
    return {"ok": False, "message": "Not a file this chat made"}


def show(transcript, path, step=None):
    """--made: a file the chat made, unfolded. A picture: {"ok", "type": "picture", "mime",
    "data" (base64), "size"}; a page or a plan: {"ok", "type", "text" (its first lines),
    "cut" (there's more), "size"}. Only a picture, a page or a plan the transcript names,
    a plain file of at most PICTURE_SHOW_MAX (an SVG: SVG_SHOW_MAX; a text: its first
    TEXT_SHOW_BYTES); else {"ok": False, "message", "gone"|"big": True}. step (a Read's
    tool call): the picture Claude saw there, from the transcript, whatever became of the
    file since ("seen": True)."""
    if step is not None:
        found = seen_in(transcript, step) if isinstance(step, str) and STEP_ID.match(step) else None
        if found is None:
            return {"ok": False, "gone": True, "message": "It isn't in the chat's transcript any more"}
        if len(found[1]) > PICTURE_SHOW_MAX * 4 // 3 + 4:
            return {"ok": False, "big": True, "message": "It's too big to show here"}
        try:
            size = len(base64.b64decode(found[1], validate=True))
        except ValueError:
            return {"ok": False, "message": "It isn't whole in the chat's transcript"}
        return {"ok": True, "type": "picture", "mime": found[0], "data": found[1], "size": size, "seen": True}
    if not isinstance(path, str) or not path.startswith("/") or "\0" in path or os.path.normpath(path) != path:
        return not_made()
    what = type_of(path)
    if what is None or not named_in(transcript, path):
        return not_made()
    ext = os.path.splitext(path)[1].lower()
    if what == "picture":
        data, other = cs.bytes_to_compare(path, SVG_SHOW_MAX if ext == ".svg" else PICTURE_SHOW_MAX)
    else:
        data, other = cs.bytes_to_compare(path, TEXT_SHOW_BYTES, head=True)
    if data is None:
        if other == cs.NOT_PLAIN:
            return {"ok": False, "message": "It isn't a plain file"}
        if other:
            return {"ok": False, "big": True, "message": f"It's too big to show here ({other})"}
        return {"ok": False, "gone": True, "message": "It isn't there any more"}
    if what == "picture":
        return {"ok": True, "type": what, "mime": PICTURES[ext], "data": base64.b64encode(data).decode("ascii"),
                "size": len(data)}
    text = data.decode("utf-8", "replace")
    if len(data) >= TEXT_SHOW_BYTES:
        text = text.rsplit("\n", 1)[0]   # (no line cut in the middle)
    lines = text.split("\n")
    keep = PLAN_LINES if what == "plan" else SOURCE_LINES
    try:
        size = os.stat(path).st_size
    except OSError:
        size = len(data)
    return {"ok": True, "type": what, "text": "\n".join(lines[:keep]), "cut": len(lines) > keep or len(data) >= TEXT_SHOW_BYTES,
            "size": size}


def keep_copy(folder, key, answer):
    """A picture show() gave (an SSH host's, or one Claude saw) as a file here, for Plasma's
    Talpy Chat, named after key (the host, the chat, and the file or the step): in folder
    (cs.images_dir: the pictures there go after IMAGES_KEEP_DAYS), yours alone; the answer
    with "file" (its path here) in place of "data"."""
    ext = dict(PICTURE_MIMES, **{"image/svg+xml": ".svg"}).get(answer.get("mime"))
    if not answer.get("ok") or ext is None or not isinstance(answer.get("data"), str):
        return answer
    try:
        data = base64.b64decode(answer["data"], validate=True)
    except ValueError:
        return {"ok": False, "message": "The picture didn't come whole"}
    target = os.path.join(folder, "made-" + hashlib.sha256(key.encode("utf-8", "replace")).hexdigest()[:24] + ext)
    try:
        os.makedirs(folder, exist_ok=True)
        os.chmod(folder, 0o700)
        part = target + ".part"
        with open(os.open(part, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb") as f:
            f.write(data)
        os.replace(part, target)
    except OSError as exc:
        return {"ok": False, "message": f"Couldn't keep a copy of it here: {exc.strerror or exc}"}
    out = {k: v for k, v in answer.items() if k != "data"}
    out["file"] = target
    return out
