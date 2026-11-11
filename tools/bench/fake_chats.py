#!/usr/bin/env python3
"""Made-up Claude Code chats for Talpy Chat's budgets (tools/bench/bench.py):
a home folder with one account (~/.claude) and a few transcripts of
made-up work, the same each time (a fixed seed), so a step's numbers can be
compared with the ones before it. Nothing here is real data.

    python3 fake_chats.py HOME            the chats (bench.py makes HOME)
    python3 fake_chats.py --turn PATH N   one more turn, at once (a check)

Each chat's id is in CHATS. bench.py's turn test appends turn() to TURN's
transcript line by line, as Claude writes them. The long chat has 100
bookmarks (Talpy Chat's, kept in ~/.cache/talpy-den/bookmarks: every other
one of your messages and Claude's replies, from its end); the others none.
"""

import calendar
import json
import os
import random
import sys
import time
from pathlib import Path

# id -> (name, turns): a turn is a prompt, a few tool calls and a reply
CHATS = {
    "b0000000-0000-4000-8000-000000000001": ("Bench short chat", 2),
    "b0000000-0000-4000-8000-000000000002": ("Bench long chat", 70),
    "b0000000-0000-4000-8000-000000000003": ("Bench turn chat", 2),
}
SHORT, LONG, TURN = list(CHATS)
FOLDS = "b0000000-0000-4000-8000-000000000004"   # (only for bench.py's find: long replies and messages, make_folds)
FOLDER = "repos/bench-app"
BOOKMARKED = 100   # (the long chat's bookmarks)
MODEL = "claude-opus-5-5"

WORDS = ("parser config cache request handler schema token buffer worker queue index session route "
         "payload module fixture adapter loader record field value client server limit retry timeout "
         "build test release version branch commit patch window list item frame layout").split()
FILES = ["src/parse.ts", "src/cache.py", "src/routes/api.ts", "tests/test_cache.py", "docs/usage.md",
         "src/worker/queue.rs", "package.json", "src/config/schema.json"]


def iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + ".%03dZ" % int((t % 1) * 1000)


class Writer:
    """Transcript entries of one chat, as Claude Code writes them."""

    def __init__(self, sid, cwd, seed, start):
        self.sid, self.cwd, self.rnd, self.t, self.n = sid, cwd, random.Random(seed), start, 0

    def base(self, kind, gap):
        self.t += gap
        self.n += 1
        return {"parentUuid": None, "isSidechain": False, "userType": "external", "cwd": self.cwd,
                "sessionId": self.sid, "version": "2.1.318", "gitBranch": "main", "type": kind,
                "uuid": "%s-%05d" % (self.sid, self.n), "timestamp": iso(self.t)}

    def words(self, n):
        return " ".join(self.rnd.choice(WORDS) for _ in range(n))

    def sentence(self):
        s = self.words(self.rnd.randint(6, 16))
        return s[0].upper() + s[1:] + "."

    def prompt(self, text=None):
        e = self.base("user", 20)
        e["message"] = {"role": "user", "content": text or " ".join(self.sentence() for _ in range(self.rnd.randint(1, 3)))}
        return e

    def assistant(self, content, stop):
        e = self.base("assistant", 4)
        e["message"] = {"id": "msg_bench_%05d" % self.n, "type": "message", "role": "assistant", "model": MODEL,
                        "content": content, "stop_reason": stop,
                        "usage": {"input_tokens": 6, "output_tokens": 420, "cache_read_input_tokens": 52000,
                                  "cache_creation_input_tokens": 1800}}
        return e

    def text(self, text, end=False):
        return self.assistant([{"type": "text", "text": text}], "end_turn" if end else None)

    def reply(self, marker=""):
        """A reply in markdown: paragraphs, a list, some code, now and then a table."""
        r = self.rnd
        parts = [" ".join(self.sentence() for _ in range(r.randint(2, 4))) + (" " + marker if marker else "")]
        parts.append("## " + self.words(3).capitalize())
        parts.append("\n".join("%d. **%s** in `%s`: %s" % (i + 1, self.words(2), r.choice(FILES), self.sentence())
                               for i in range(r.randint(2, 5))))
        if r.random() < 0.6:
            parts.append("```python\n" + "\n".join("def %s_%d(%s):\n    return %s(%s) + %d" % (
                r.choice(WORDS), i, r.choice(WORDS), r.choice(WORDS), r.choice(WORDS), r.randint(1, 99))
                for i in range(r.randint(1, 4))) + "\n```")
        if r.random() < 0.25:
            parts.append("| Case | Before | After |\n|---|---|---|\n" + "\n".join(
                "| %s | %d ms | %d ms |" % (self.words(2), r.randint(20, 900), r.randint(5, 300)) for _ in range(4)))
        parts.append(" ".join(self.sentence() for _ in range(r.randint(1, 3))))
        return "\n\n".join(parts)

    def tool(self, i):
        """A tool call and its result (two entries)."""
        r = self.rnd
        tid = "toolu_bench_%s_%05d" % (self.sid[-4:], self.n + 1)
        kind = r.choice(["Bash", "Bash", "Read", "Read", "Edit", "Grep", "Glob", "Write"])
        path = self.cwd + "/" + r.choice(FILES)
        if kind == "Bash":
            inp = {"command": r.choice(["npm test -- %s", "pytest -q tests/test_%s.py", "git diff --stat",
                                        "cargo build --release", "rg -n %s src"]).replace("%s", r.choice(WORDS)),
                   "description": self.words(4).capitalize()}
            out = "\n".join("%s ... %s" % (self.words(4), r.choice(["ok", "ok", "ok", "FAILED"])) for _ in range(r.randint(2, 30)))
        elif kind == "Read":
            inp = {"file_path": path}
            out = "\n".join("%6d\t%s = %s(%s)" % (k + 1, r.choice(WORDS), r.choice(WORDS), self.words(2).replace(" ", ", "))
                            for k in range(r.randint(10, 60)))
        elif kind in ("Edit", "Write"):
            old = "\n".join("    %s = %s(%s)" % (r.choice(WORDS), r.choice(WORDS), r.choice(WORDS)) for _ in range(r.randint(2, 6)))
            new = old + "\n" + "\n".join("    %s += %d" % (r.choice(WORDS), r.randint(1, 9)) for _ in range(r.randint(1, 4)))
            inp = {"file_path": path, "old_string": old, "new_string": new} if kind == "Edit" else {"file_path": path, "content": new}
            out = "The file %s has been updated." % path
        elif kind == "Grep":
            inp = {"pattern": r.choice(WORDS), "path": self.cwd + "/src", "output_mode": "content"}
            out = "\n".join("%s:%d:%s" % (r.choice(FILES), r.randint(1, 400), self.sentence()) for _ in range(r.randint(1, 12)))
        else:
            inp = {"pattern": "**/*.%s" % r.choice(["ts", "py", "rs"])}
            out = "\n".join(self.cwd + "/" + f for f in FILES[:r.randint(2, 8)])
        use = self.assistant([{"type": "tool_use", "id": tid, "name": kind, "input": inp}], "tool_use")
        res = self.base("user", r.uniform(0.5, 6))
        res["message"] = {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tid, "content": out,
                                                         "is_error": out.endswith("FAILED")}]}
        return [use, res]

    def turn(self, marker="", prompt=None, asks=""):
        """A whole turn: your prompt, Claude's first words, tool calls, its reply (end_turn; asks: the
        question it ends with)."""
        lines = [self.prompt(prompt), self.text(self.sentence())]
        for i in range(self.rnd.randint(2, 7)):
            lines += self.tool(i)
        lines.append(self.text(self.reply(marker) + ("\n\n" + asks if asks else ""), end=True))
        return lines


def bookmarks(home, sid, entries, n):
    """n bookmarks of a chat (every other of your messages and Claude's replies, from its end), in
    its file of Talpy Chat's bookmarks (talpy_den.py save_bookmarks: the same fields)."""
    marks = []
    for e in entries:
        m = e.get("message") or {}
        if e.get("type") == "user" and isinstance(m.get("content"), str):
            mark = ("you", e["uuid"], m["content"])
        elif e.get("type") == "assistant" and m.get("content") and m["content"][0].get("type") == "text":
            mark = ("claude", m["id"], m["content"][0]["text"])
        else:
            continue
        at = calendar.timegm(time.strptime(e["timestamp"][:19], "%Y-%m-%dT%H:%M:%S")) * 1000 + int(e["timestamp"][20:23])
        text = " ".join(mark[2].split())
        marks.append({"key": mark[1], "kind": mark[0], "at": at,
                      "text": text if len(text) <= 140 else text[:139].rstrip() + "…", "made": at + 60000})
    marks = marks[::-1][::2][:n][::-1]
    folder = home / ".cache/talpy-den/bookmarks"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{sid}.json").write_text(json.dumps({"chat": sid, "host": "", "v": int(time.time() * 1000), "marks": marks}))


def dump(entries):
    return "".join(json.dumps(e, separators=(",", ":")) + "\n" for e in entries)


def transcript(home, sid):
    return home / ".claude/projects" / (str(home / FOLDER).replace("/", "-")) / f"{sid}.jsonl"


def make(home):
    home = Path(home)
    (home / FOLDER).mkdir(parents=True, exist_ok=True)
    profile = home / ".claude"
    (profile / "sessions").mkdir(parents=True, exist_ok=True)
    (profile / ".claude.json").write_text(json.dumps({"oauthAccount": {
        "accountUuid": "00000000-0000-4000-8000-00000000b001", "organizationType": "claude_max",
        "displayName": "Bench"}}))
    now = time.time()
    for k, (sid, (name, turns)) in enumerate(CHATS.items()):
        w = Writer(sid, str(home / FOLDER), seed=k + 1, start=now - 86400 + k * 600)
        lines = [{"type": "ai-title", "aiTitle": name, "sessionId": sid}]
        for _ in range(turns):
            lines += w.turn()
        path = transcript(home, sid)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dump(lines))
        t = now - 3600 * (len(CHATS) - k)
        os.utime(path, (t, t))
        if sid == LONG:
            bookmarks(home, sid, lines, BOOKMARKED)
    return home


def make_folds(home):
    """One more chat, for Talpy Chat's folds (bench.py find): 40 turns whose replies are long (60
    lines), every third prompt a pasted log (50 lines)."""
    home = Path(home)
    w = Writer(FOLDS, str(home / FOLDER), seed=44, start=time.time() - 2 * 86400)
    lines = [{"type": "ai-title", "aiTitle": "Bench folds chat", "sessionId": FOLDS}]
    for k in range(40):
        prompt = w.sentence() + ("\n" + "\n".join(w.sentence() for _ in range(50)) if k % 3 == 0 else "")
        lines += [w.prompt(prompt), w.text(w.sentence())]
        for i in range(w.rnd.randint(2, 5)):
            lines += w.tool(i)
        lines.append(w.text("## " + w.words(3).capitalize() + "\n\n" + "\n".join("- " + w.sentence() for _ in range(60)), end=True))
    path = transcript(home, FOLDS)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump(lines))
    t = time.time() - 7200
    os.utime(path, (t, t))
    return home


def turn_lines(home, n):
    """Turn n of the turn test (its reply says BENCH-END-n, and ends with a question): the lines, oldest first."""
    w = Writer(TURN, str(Path(home) / FOLDER), seed=1000 + n, start=time.time() - 90)
    w.n = 10000 * n   # (keys not used before)
    return [json.dumps(e, separators=(",", ":")) + "\n"
            for e in w.turn(marker="BENCH-END-%d" % n, prompt="Bench turn %d: %s" % (n, w.sentence()),
                            asks="Should I commit these changes?")]   # (Talpy Chat's chips: Yes, No)


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--turn":
        with open(sys.argv[2], "a") as f:
            f.writelines(turn_lines(Path(sys.argv[2]).parents[3], int(sys.argv[3])))
    elif len(sys.argv) == 2:
        make(sys.argv[1])
    else:
        sys.exit(__doc__)
