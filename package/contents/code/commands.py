"""Commands in Talpy Chat, for pane.py (a module of its own: compiled once and
kept, as talpy_den.py is, where pane.py, run as a script, is compiled at
every call; read only for a chat that has a command in it, and for the
reply box's / list):

- Commands: a command you ran in a chat (/compact, /model sonnet, a skill,
  !ls), wherever you ran it, followed entry by entry in pane.py's
  conversation_items: one item of yours with what it printed;
- BUILTIN_COMMANDS: Claude's own commands the / list offers, each with how
  Talpy Chat runs it (its kind): "here" (sent as it is: it runs and prints
  in the chat), "page" (Talpy Den has its own page for it), "picker" (Talpy
  Chat's own list: /model and /effort, for that chat alone, chatpick.py) or
  "terminal" (it needs Claude's own panel or dialog: opened in the chat's
  terminal, typed in there; a background chat would sit in it unseen);
- completions: what the reply box offers as you type (pane.py --complete).

Python 3.7+ and the standard library only (the SSH host backend too).
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

import talpy_den as cs

# ---------------------------------------------------------------- Claude's own commands
#
# As of Claude Code 2.1.318 (each one's kind checked live on a tmux chat, a
# running background chat and one woken with claude --bg --resume, or read in
# its code: a panel or a dialog is "terminal"): (name, what it does, kind,
# kind with an argument (None: the same), why it opens in a terminal).
# /model and /effort save what you pick as your default for every new chat
# (Claude writes them into your own settings, whatever the chat was started
# with): Talpy Chat's own list sets them for the chat alone (a background or
# closed one: pane.py --set-options); a chat in a terminal opens them there,
# where Claude says so too (their why).

BUILTIN_COMMANDS = (
    ("add-dir", "Add a working folder", "terminal", None, "asks first for a folder outside the chat's"),
    ("branch", "Branch the conversation here", "terminal", None, "goes on in a new chat"),
    ("btw", "Ask a quick side question", "terminal", None, "answers in a box over Claude's screen, not in the chat"),
    ("clear", "Start a new chat with empty context", "terminal", None, "goes on in a new chat"),
    ("code-review", "Review the changes or a pull request for bugs", "here", None, ""),
    ("compact", "Free up context by summarizing the conversation so far", "here", None, ""),
    ("config", "Open settings", "terminal", None, "opens Claude's settings panel"),
    ("context", "Show how full the context is", "here", None, ""),
    ("copy", "Copy Claude's last response", "terminal", None, "copies where Claude runs"),
    ("debug", "Turn on debug logging and look into a problem", "here", None, ""),
    ("diff", "Show the changes, turn by turn", "terminal", None, "opens Claude's changes panel"),
    ("doctor", "Check Claude Code's setup and fix issues", "here", None, ""),
    ("effort", "Set the effort level", "picker", None, "saves it as your default effort for every new chat"),
    ("export", "Export the conversation (a file name: to that file)", "terminal", "here", "asks where to"),
    ("fork", "Copy this conversation into a new background chat", "here", None, ""),
    ("goal", "Set a goal Claude checks before stopping", "terminal", "here", "shows the goal in a box till you close it"),
    ("help", "Show help and the commands", "terminal", None, "opens Claude's help panel"),
    ("hooks", "Show the hooks", "terminal", None, "opens Claude's hooks panel"),
    ("init", "Write a CLAUDE.md for this project", "here", None, ""),
    ("insights", "A report about your Claude Code chats", "here", None, ""),
    ("mcp", "Manage MCP servers", "terminal", None, "opens Claude's MCP panel"),
    ("memory", "Edit CLAUDE.md and memory", "terminal", None, "opens Claude's memory panel"),
    ("model", "Set the model", "picker", None, "saves it as your default model for every new chat"),
    ("permissions", "What Claude may do without asking", "page", None, ""),
    ("plan", "Plan mode, or the chat's plan", "here", None, ""),
    ("recap", "A one-line recap of the chat", "here", None, ""),
    ("rename", "Rename the chat (no name: Claude picks one)", "here", None, ""),
    ("resume", "Resume another conversation", "terminal", None, "opens Claude's list of chats"),
    ("rewind", "Go back to an earlier point", "terminal", None, "opens Claude's list of earlier points"),
    ("security-review", "Review the pending changes for security", "here", None, ""),
    ("simplify", "Clean up the changed code without changing what it does", "here", None, ""),
    ("skills", "List the skills", "terminal", None, "opens Claude's skills panel"),
    ("status", "Version, model, account and connections", "terminal", None, "opens Claude's status panel"),
    ("subtask", "Send a subagent off with your full context", "here", None, ""),
    ("tasks", "What runs in the background", "terminal", None, "opens Claude's tasks panel"),
    ("usage", "Plan usage and what this chat cost", "terminal", None, "opens Claude's usage panel"),
)
# Not in the list, typed: other names of those (aliases), and Claude's other
# commands that open a panel or a dialog, or act on its terminal
TYPED = {
    "settings": "config", "allowed-tools": "permissions", "cost": "usage", "stats": "usage", "bashes": "tasks",
    "checkpoint": "rewind", "undo": "rewind", "continue": "resume", "reset": "clear", "new": "clear",
    "review": "code-review", "name": "rename", "checkup": "doctor",
}
PANELS = ("advisor", "agents", "artifacts", "autocompact", "background", "bg", "brief", "bug", "cd", "color", "daemon",
          "desktop", "exit", "extra-usage", "fast", "feedback", "focus", "ide", "import", "install-github-app", "keybindings",
          "login", "logout", "loops", "mobile", "output-style", "passes", "plugin", "plugins", "powerup",
          "privacy-settings", "quit", "rc", "release-notes", "remote-control", "remote-env", "scroll-speed", "session",
          "skill-doctor", "stop", "teleport", "terminal-setup", "theme", "tp", "tui", "upgrade", "usage-credits",
          "web-setup", "wellbeing", "workflows")
# Run by Claude Code on its own (at a usage limit): not yours, not shown
AUTO = ("rate-limit-options",)


def builtin_offers():
    """Claude's commands as the / list offers them: [{name, about, kind:
    "Claude", run, runArgs (with an argument, when other), why}]."""
    out = []
    for name, about, run, run_args, why in BUILTIN_COMMANDS:
        c = {"name": "/" + name, "about": about, "kind": "Claude", "run": run}
        if run_args:
            c["runArgs"] = run_args
        if why:
            c["why"] = why
        out.append(c)
    return out


def typed_kinds():
    """{name: its command's run (or "terminal")}: the names not listed."""
    runs = {name: (run, run_args, why) for name, _, run, run_args, why in BUILTIN_COMMANDS}
    out = {}
    for alias, name in TYPED.items():
        run, run_args, why = runs[name]
        out[alias] = dict({"run": run, "of": "/" + name}, **({"runArgs": run_args} if run_args else {}),
                          **({"why": why} if why else {}))
    for name in PANELS:
        out[name] = {"run": "terminal", "why": "uses Claude's own screen"}
    return out


# ---------------------------------------------------------------- what the reply box offers
#
# Claude's own commands (above), your commands and skills (the profile's
# commands/ and skills/), the project's (.claude/commands, .claude/skills),
# its files (git ls-files, else a walk) and your past prompts there
# (history.jsonl). Yours and the project's are prompts: they run from here.

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
    """Commands in a commands/ folder: [{name, about, kind, run}] (a file in a subfolder: dir:name)."""
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
        out.append({"name": "/" + name, "about": cs.short_text(meta.get("description") or first, 100), "kind": scope,
                    "run": "here"})
    return out


def skill_dirs(folder, scope):
    """Skills in a skills/ folder (each its SKILL.md): [{name, about, kind, run}]."""
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
                    "kind": scope + " skill", "run": "here"})
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


def completions(profile, cwd):
    """--complete for a chat on profile in folder cwd: {"ok", "cwd",
    "commands" (Claude's, yours and the project's, sorted; each with its
    run), "typed" (typed_kinds), "files", "filesCut", "history"}."""
    commands = builtin_offers()
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
    return {"ok": True, "cwd": cwd, "commands": sorted(unique, key=lambda c: c["name"]), "typed": typed_kinds(),
            "files": files, "filesCut": cut, "history": past_prompts(profile, cwd)}


# ---------------------------------------------------------------- commands in the conversation
#
# Claude Code writes a command you ran as an entry of its own (a user entry,
# or a system "local_command" one): <command-name>/x</command-name>
# <command-message>x</command-message> <command-args>…</command-args>, and
# what it printed in the next one: <local-command-stdout>…</…> (ANSI colours
# in it) or <local-command-stderr>. A command that's a prompt (yours, a
# skill) has no output: Claude answers it. A shell command (! in Claude's
# prompt): <bash-input>ls</bash-input>, then <bash-stdout>…<bash-stderr>…;
# sent through Claude's queue (a background chat's reply) it's queued
# without its !. /compact writes a plain "/compact" prompt first, then the
# compaction, then its command entry. A command it doesn't know: a system
# "informational" entry, "Unknown command: /x" (and what it may have meant).

COMMAND_PART = re.compile(r"<(command-name|command-args|command-message)>(.*?)</\1>", re.S)
OUTPUT_PART = re.compile(r"<(local-command-stdout|local-command-stderr|bash-stdout|bash-stderr)>(.*?)</\1>", re.S)
BASH_INPUT = re.compile(r"^\s*<bash-input>(.*?)</bash-input>", re.S)
UNKNOWN = re.compile(r"^Unknown (?:command|skill): (/\S+?)(?:\.\s|\.?$)")
NO_OUTPUT = ("", "(no content)")
OUTPUT_LINES = 80    # of a command's output, in the chat
OUTPUT_CHARS = 8000
ANSI_TAIL = re.compile(r"\x1b(?:\[[0-9;?]*)?$")   # (an escape cut in two at the end)
SAID_ELSEWHERE = ("/compact",)   # (their note says it: "The conversation was compacted")


def same_text(a, b):
    return " ".join(a.split()) == " ".join(b.split())


def clip_output(text):
    """A command's output, its first OUTPUT_LINES lines (OUTPUT_CHARS at most), "…" after what's cut."""
    lines = text.split("\n")
    cut = len(lines) > OUTPUT_LINES or len(text) > OUTPUT_CHARS
    if cut:
        text = ANSI_TAIL.sub("", "\n".join(lines[:OUTPUT_LINES])[:OUTPUT_CHARS]) + "\x1b[0m\n…"
    return text


class Commands:
    """The commands in a conversation, entry by entry: each as an item of
    yours ({"kind": "you", "key", "text": as typed, "/model sonnet" or
    "!ls", "at", "command": {"shell"?, "output"?, "error"?}}), the one you
    sent where it was (in Claude's queue till then: due, its key kept; or
    /compact's own prompt), what it printed on it. items and due:
    conversation_items' lists, changed in place; end: its TurnEnd (a prompt
    command or a goal starts Claude's turn)."""

    def __init__(self, items, due, end):
        self.items, self.due, self.end = items, due, end
        self.last = None   # the command the next output entry is of
        self.skip = False  # (Claude Code's own: its output isn't shown either)

    def entry(self, text, uid, at):
        """A user entry's text (not meta), or a local_command entry's content."""
        shell = BASH_INPUT.match(text)
        if shell:
            line = shell.group(1).strip()
            if line:
                self.ran("!" + line, uid, at, shell=True)
            return
        parts = dict(COMMAND_PART.findall(text))
        name = parts.get("command-name", "").strip()
        if name:
            if not name.startswith("/") or name[1:] in AUTO:
                self.last, self.skip = None, name[1:] in AUTO   # (a skill Claude loaded, a limit's options)
                return
            args = parts.get("command-args", "").strip()
            self.ran(name + (" " + args if args else ""), uid, at, local=name[1:] in RUNS and RUNS[name[1:]] != "prompt")
        outputs = OUTPUT_PART.findall(text)
        if outputs:
            self.printed(outputs)

    def unknown(self, text, uid, at):
        """Claude Code's "Unknown command: /x…": on the command, as what it printed."""
        m = UNKNOWN.match(text.strip())
        if not m:
            return
        name = m.group(1).rstrip(".")
        item = self.take(lambda t: t == name or t.startswith(name + " "))
        if item is None:
            item = {"kind": "you", "key": uid, "text": name, "at": at}
            self.items.append(item)
        item["command"] = {"output": clip_output(text.strip()), "error": True}

    def take(self, matches):
        """Your message this command is, as it was sent (its key kept): in
        Claude's queue till now, or its own prompt just before (/compact's)."""
        for i, d in enumerate(self.due):
            if matches(" ".join(d["text"].split())):
                item = self.due.pop(i)
                self.items.append(item)
                return item
        for it in reversed(self.items):
            if it["kind"] == "note":
                continue   # (the compaction's)
            if it["kind"] == "you" and "command" not in it and not it.get("answered") and matches(" ".join(it["text"].split())):
                return it
            break
        return None

    def ran(self, line, uid, at, shell=False, local=True):
        bare = " ".join(line.split())
        # (a shell command went through the queue without its !)
        item = self.take(lambda t: t == bare or (shell and t == bare[1:].strip()))
        if item is None:
            item = {"kind": "you", "key": uid, "text": line, "at": at}
            self.items.append(item)
        else:
            item["text"] = line
        item["command"] = {"shell": True} if shell else {}
        self.last, self.skip = item, False
        if not local and not shell:
            self.end.prompt(at)   # (a prompt: Claude answers it)

    def printed(self, outputs):
        item, skip = self.last, self.skip
        self.last, self.skip = None, False
        if item is None or skip:
            return
        said, error = [], False
        for tag, body in outputs:
            body = body.strip("\n").rstrip()
            if body.strip() in NO_OUTPUT:
                continue
            said.append(body)
            error = error or tag.endswith("stderr")
        if not said or (item["text"] in SAID_ELSEWHERE and not error):
            return
        item["command"]["output"] = clip_output("\n".join(said))
        if error:
            item["command"]["error"] = True


# Claude's commands that are prompts (Claude answers them: a turn), and those that run in Claude Code
RUNS = dict({name: "local" for name, *_ in BUILTIN_COMMANDS},
            **{name: "prompt" for name in ("code-review", "debug", "doctor", "init", "insights", "security-review",
                                           "simplify", "review", "checkup")})
