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
import uuid

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
            "request": {"subtype": "side_question", "question": question,
                        "history": [{"question": h["question"], "response": h["response"]} for h in history]}}


def same_part(history, part):
    """The earlier answers a question goes with: those about the same part of the chat (talpy_den.side_history
    gives each its part's key, "" for all of it), so a follow-up never mixes parts."""
    key = part["key"] if part else ""
    return [h for h in history if (h.get("part") or "") == key]


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


def read_answer(proc, deadline, clock=time.monotonic, loaded=None):
    """The control response to our request, from claude's stdout: (answer
    dict, None, "") or (None, why not, the end of what it wrote on stderr).
    Reads line by line till the deadline; stderr is read as it comes (a
    full pipe would stop claude). loaded(): called once claude has read the
    chat (it said the side question started, or answered)."""
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
            if loaded is not None and isinstance(msg, dict) and (
                    msg.get("type") == "control_response" or msg.get("subtype") == "control_request_progress"):
                loaded()
                loaded = None
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


# ---------------------------------------------------------------- a copy from a message on
#
# "Ask from here" and Explain this: the copy gets the chat from the start of
# the turn you point at (your message that started it) to its end, not all of
# it, so a long chat's question costs what that part costs. Claude Code reads
# a chat from its newest compact_boundary on (what /compact writes: a system
# entry with no parent, then its summary), so the part is a transcript of its
# own: such a boundary, a note that what's before is left out, and the
# chat's entries from that message on, the first one under the note. It's
# written beside the chat (claude --resume finds a chat only in the project
# folder of the folder it runs in), under an id Talpy Den's readers skip
# (cs.side_copy), and deleted once the copy has read it. Live-checked on
# Claude Code 2.1.325: a 537k-token chat's part from a message 30 entries
# back answered from ~48k tokens, and knew it starts partway.

COPY_NOTE = ("This copy of the conversation starts partway through: everything before the next message is "
             "left out of it.")
COPY_TYPES = ("user", "assistant", "system", "attachment")   # (what a chat is read as; not its metadata lines)
COPY_STALE_S = 600   # (one a copy that ended badly left: deleted at the next one there)


def copy_id():
    """An id for a part's transcript: a UUID that starts as cs.SIDE_COPY_PREFIX says."""
    r = os.urandom(9).hex()
    return f"{cs.SIDE_COPY_PREFIX}{r[:3]}-8{r[3:6]}-{r[6:18]}"


def entry_keys(e):
    """The keys Talpy Chat gives what this entry shows (pane.py's items): your message's uuid, Claude's
    reply's message id (and its thinking's), a tool call's id."""
    keys = {e.get("uuid")}
    msg = e.get("message") if isinstance(e.get("message"), dict) else {}
    if isinstance(msg.get("id"), str):
        keys.add(msg["id"])
    for c in msg.get("content") if isinstance(msg.get("content"), list) else ():
        if isinstance(c, dict) and isinstance(c.get("id"), str):
            keys.add(c["id"])
    return {k for k in keys if isinstance(k, str) and k}


def turn_start(e):
    """Whether this entry is your message that starts one of Claude's turns (turns.turn_prompt_at's rule)."""
    if e.get("type") != "user" or e.get("isMeta") or e.get("isSidechain") or e.get("isCompactSummary"):
        return False
    if cs.human_prompt(e) is not None:
        return True
    return cs.message_text(cs.blocks_of(e)[0]).lstrip().startswith("<command-message>")


def read_entries(path):
    """A transcript's entries (malformed lines left out)."""
    out = []
    with open(path, "rb") as f:
        for line in f:
            try:
                e = json.loads(line)
            except (ValueError, RecursionError):
                continue
            if isinstance(e, dict):
                out.append(e)
    return out


def queued_text(content):
    """What a message you sent while Claude worked says (pane.py typed_text)."""
    text = cs.typed_part(cs.message_text({"content": content})).strip()
    return "" if text.startswith("<") else text


def same_text(a, b):
    return " ".join(a.split()) == " ".join(b.split())


def enqueued(e):
    """Whether this entry is Claude queueing a message of yours (pane.py's key for it: queued-<its ms>)."""
    return e.get("type") == "queue-operation" and e.get("operation") == "enqueue"


def queued_at(entries, ms):
    """Where the message you sent while Claude worked (or that went through
    Claude's queue: a background chat's, claude -p's) with Talpy Chat's key
    queued-<ms> is in the chat: your message that it became, or where Claude
    took it in during a turn (a queued_command), else its queueing (still
    waiting); None when there's no such queueing."""
    q = next((i for i, e in enumerate(entries) if enqueued(e) and cs.to_ms(e.get("timestamp")) == ms), None)
    if q is None:
        return None
    text = queued_text(entries[q].get("content"))
    if not text:
        return q
    for i in range(q + 1, len(entries)):
        e = entries[i]
        prompt = cs.human_prompt(e)
        if prompt is not None and same_text(prompt, text):
            return i
        a = e.get("attachment") if e.get("type") == "attachment" else None
        if isinstance(a, dict) and a.get("type") == "queued_command" and same_text(queued_text(a.get("prompt")), text):
            return i
    return q


def item_key(entries, start):
    """The key Talpy Chat's conversation gives your message at entries[start]
    (pane.py): queued-<ms> when it went through Claude's queue (queued since
    the turn before), else its uuid."""
    e = entries[start]
    text = cs.human_prompt(e)
    if text:
        for i in range(start - 1, -1, -1):
            if turn_start(entries[i]):
                break
            if enqueued(entries[i]) and same_text(queued_text(entries[i].get("content")), text):
                return "queued-%d" % (cs.to_ms(entries[i].get("timestamp")) or 0)
    return e.get("uuid") or ""


def cut_at(entries, key):
    """Where a part from the message with that key starts: the index of your
    message that started its turn, or None (the key isn't in the chat, or the
    chat was compacted after it: the chat as Claude reads it is that part)."""
    if not isinstance(key, str) or not key:
        return None
    key = key.split("/")[0]   # (an answer's key: its question's tool call)
    if key.startswith("queued-") and key[7:].isdigit():
        found = queued_at(entries, int(key[7:]))
    else:
        found = next((i for i in range(len(entries) - 1, -1, -1) if key in entry_keys(entries[i])), None)
    if found is None:
        return None
    start = next((i for i in range(found, -1, -1) if turn_start(entries[i])), None)
    if start is None:
        return None
    if any(e.get("type") == "system" and e.get("subtype") == "compact_boundary" for e in entries[start:]):
        return None
    return start


def read_size(e):
    """What Claude read for this reply and wrote (tokens): its context once it answered."""
    msg = e.get("message") if isinstance(e.get("message"), dict) else {}
    usage = msg.get("usage") if isinstance(msg.get("usage"), dict) else {}
    nums = [usage.get(k) for k in cs.USAGE_READ + ("output_tokens",)]
    return sum(n for n in nums if isinstance(n, int) and not isinstance(n, bool) and n > 0)


def part_size(entries, start):
    """(tokens of the chat from entries[start] on, tokens of all of it): what
    Claude read for its newest reply, less what it had read and written by the
    last reply before the part (Claude's own instructions, which every copy
    has, aren't counted)."""
    replies = [(i, read_size(e)) for i, e in enumerate(entries)
               if e.get("type") == "assistant" and not e.get("isSidechain") and read_size(e)]
    whole = replies[-1][1] if replies else 0
    before = [n for i, n in replies if i < start]
    return (max(0, whole - before[-1]) if before else whole), whole


def part_of(path, key):
    """Where a part from that message starts, for the front end's line and
    cost: {"key": your message's key, "text": its first words, "at": ms,
    "tokens", "of"}, or None (whole chat: cut_at)."""
    entries = read_entries(path)
    start = cut_at(entries, key)
    if start is None:
        return None
    tokens, whole = part_size(entries, start)
    e = entries[start]
    text = cs.human_prompt(e) or cs.message_text(cs.blocks_of(e)[0])
    return {"key": item_key(entries, start), "text": cs.short_text(" ".join(text.split()), 60),
            "at": cs.to_ms(e.get("timestamp")) or 0, "tokens": tokens, "of": whole}


def write_part(path, entries, start):
    """The part's transcript beside the chat's (copy_id): its path and id."""
    folder = path.parent
    now = time.time()
    try:   # (one a copy that ended badly left behind)
        for name in os.listdir(folder):
            if cs.side_copy(name) and now - os.stat(folder / name).st_mtime > COPY_STALE_S:
                os.unlink(folder / name)
    except OSError:
        pass
    part_id = copy_id()
    first = entries[start]
    common = {k: first[k] for k in ("cwd", "version", "gitBranch", "userType", "entrypoint") if k in first}
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(now))
    boundary_id, note_id = str(uuid.uuid4()), str(uuid.uuid4())
    lines = [{"parentUuid": None, "logicalParentUuid": None, "isSidechain": False, "type": "system",
              "subtype": "compact_boundary", "content": "Conversation compacted", "level": "info",
              "compactMetadata": {"trigger": "manual"}, "uuid": boundary_id, "timestamp": stamp, **common,
              "sessionId": part_id},
             {"parentUuid": boundary_id, "isSidechain": False, "type": "user", "isVisibleInTranscriptOnly": True,
              "isCompactSummary": True, "uuid": note_id, "timestamp": stamp, **common, "sessionId": part_id,
              "message": {"role": "user", "content": COPY_NOTE}}]
    # (session_id too: entries that name another chat in it are how a chat Claude moved to the background
    # is told (talpy_den LinkCache.moved_from); kept, every copy of Talpy Den, an older one too, would take
    # the chat for moved to the part, and carry its side questions, stars and marks there)
    kept = [dict(e, sessionId=part_id, **({"session_id": part_id} if "session_id" in e else {}))
            for e in entries[start:] if e.get("type") in COPY_TYPES]
    kept[0]["parentUuid"] = note_id
    target = folder / (part_id + ".jsonl")
    fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        for e in lines + kept:
            f.write(json.dumps(e, separators=(",", ":")) + "\n")
    return target, part_id


def gone(path):
    try:
        os.unlink(path)
    except OSError:
        pass


def ask(home, extra_dirs, profile_key, chat_id, question, pick="", history=(), claude=None, wait=None, since=None):
    """Put a side question to a copy of the chat: {"ok", "answer", "model",
    "synthetic"} or {"ok": False, "message"}. pick: "" (the chat's own
    model, cs.chat_model) or one of cs.SIDE_PICKS. A chat Claude moved to
    the background goes on under its new id (cs.continuation): asked there.
    since: the key of a message (Ask from here): the copy gets
    the chat from the start of that message's turn on (write_part), and the
    answer says which part, "from" (part_of's); None there when it got all
    of it (the message isn't in the chat any more, or the chat was compacted
    after it)."""
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
    part, part_path, resume = None, None, chat_id
    if since:
        try:
            entries = read_entries(path)
            start = cut_at(entries, since)
            if start is not None:
                part_path, resume = write_part(path, entries, start)
                tokens, whole = part_size(entries, start)
                e = entries[start]
                text = cs.human_prompt(e) or cs.message_text(cs.blocks_of(e)[0])
                part = {"key": item_key(entries, start), "text": cs.short_text(" ".join(text.split()), 60),
                        "at": cs.to_ms(e.get("timestamp")) or 0, "tokens": tokens, "of": whole}
        except OSError as exc:
            return {"ok": False, "message": f"Couldn't make the copy: {exc.strerror or exc}"}
    try:
        proc = subprocess.Popen(command(claude, resume, model), cwd=folder, env=environment(profile, home, claude),
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                start_new_session=True)
    except OSError as exc:
        if part_path is not None:
            gone(part_path)
        return {"ok": False, "message": f"Couldn't run claude: {exc}"}
    try:
        try:
            proc.stdin.write((json.dumps(request(question, same_part(history, part))) + "\n").encode("utf-8"))
            proc.stdin.flush()
        except OSError:
            pass   # (it ended already: what it said is read below)
        wait = cs.SIDE_WAIT_S if wait is None else wait
        response, why, err = read_answer(proc, time.monotonic() + wait,
                                         loaded=(lambda: gone(part_path)) if part_path is not None else None)
    finally:
        stop(proc)
        if part_path is not None:
            gone(part_path)
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
    return {"ok": True, "answer": answer, "model": model, "synthetic": body.get("synthetic") is True,
            **({"from": part} if since else {})}
