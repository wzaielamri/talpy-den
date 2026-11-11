#!/usr/bin/env python3
"""Status backend for the Talpy Den Plasma widget.

Prints one JSON object describing every local Claude Code session (working,
waiting for input, idle), the plan-limit usage captured by the status line,
and token totals parsed from transcripts. Standard library only; the widget
runs it as `python3 -I talpy_den.py` every couple of seconds.

Data sources (per Claude config dir, e.g. ~/.claude, ~/.claude-work):
  <cfg>/sessions/<pid>.json       live session registry kept by Claude Code
  <cfg>/jobs/<id>/state.json      background jobs (also ones with no process)
  <cfg>/projects/**/*.jsonl       transcripts (token usage per message, and
                                  which chat a session shows: shared chats are
                                  hard-linked into several profiles)
  <cfg>/history.jsonl             prompt history (recent folders, last use)
  <account file>                  oauthAccount.accountUuid / organizationType /
                                  displayName, cachedUsageUtilization (Claude
                                  Code's own plan usage) and each folder's
                                  trust flag only
  ~/.cache/talpy-den/statusline/<cfg dirname>/<session_id>.json
                                  status-line input snapshots (rate limits,
                                  context window), written by statusline-snippet.sh
  ~/.cache/talpy-den/accounts.json
                                  profiles accounts.py logged out of

When an account's plan usage is old while one of its chats works (Claude's
VS Code panel runs no status line), it has Claude Code fetch it, the way
/usage does (refresh_usage; ~/.cache/talpy-den/usage-check.json notes when).
"""

import contextlib
import fcntl
import hashlib
import json
import math
import mmap
import os
import re
import shlex
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

SNAPSHOT_MAX_AGE = 8 * 86400  # seconds a status-line snapshot is kept
TOKEN_SCAN_INTERVAL = 60  # seconds between transcript scans
TOKEN_DAYS = 8  # days of per-message token records kept in the cache
STATS_DAYS = 30  # days of per-day sums kept for the stats (token_stats)
STATS_SHOWN_DAYS = 14  # days the stats show
CACHE_VERSION = 3  # token cache; 3 = keyed by the real profile folder, linked folders followed
# (the stats' history, prompts and chatFolders were added without a new version: older
# copies of this script, e.g. a VS Code extension not updated yet, keep them as they are)

PLAN_NAMES = {
    "claude_free": "Free",
    "claude_pro": "Pro",
    "claude_max": "Max",
    "claude_team": "Team",
    "claude_enterprise": "Enterprise",
}
WINDOW_LABELS = {
    "five_hour": "5h",
    "seven_day": "7d",
    "seven_day_opus": "7d Opus",
    "seven_day_sonnet": "7d Sonnet",
    "spend_limit": "Spend",
}
WINDOW_ORDER = ["five_hour", "seven_day", "seven_day_opus", "seven_day_sonnet"]
STATE_ORDER = {"waiting": 0, "working": 1, "idle": 2, "done": 3}
# Why a session reports status "waiting" (Claude Code's waitingFor values) ->
# what it waits for. "dialog open" is left out on purpose: that is a dialog you
# opened yourself (/model, /effort, ...), and Claude Code's own terminal status
# doesn't count it as blocked either.
WAITING_REASONS = {
    "permission prompt": "permission",
    "goal proposal": "goal approval",
    "sandbox request": "network access",
    "worker request": "worker request",
    "input needed": "question",
}
FINISHED_JOB_STATES = ("done", "failed", "stopped")
SESSION_KINDS = ("interactive", "bg")  # not the daemon's own processes
# Everything Claude Code writes into these fields of its session and job files
# (read from the 2.1.304 binary). A value outside them is new: an unknown
# status counts as idle, an unknown kind isn't listed, so the check says so
# (unknown_values_text) instead of quietly showing chats wrong. (A new
# waitingFor shows as it is, with the chat waiting: you'd see that.)
KNOWN_VALUES = {
    "chat kind": ("interactive", "bg", "daemon", "daemon-worker"),
    "chat status": ("busy", "shell", "idle", "waiting"),
    "job state": ("working", "running", "blocked") + FINISHED_JOB_STATES,
    "job tempo": ("active", "blocked", "idle"),
}
NOT_STARTED = "send a prompt to start"  # needs of a background session given no prompt yet
RECENT_JOB_MS = 5000
KEEP_DONE_HOURS = 24  # finished background jobs stay listed this long
SETTINGS_MAX = 4 << 20  # bytes of a settings file read at most (a project's is its repository's: a bigger one is skipped)


# ---------------------------------------------------------------- helpers


def read_json(path, limit=None):
    """path's JSON, or None: not there, not JSON (or nested deeper than json
    reads), or not a plain file of at most limit bytes (read_plain: a link
    to a device or a pipe is never read)."""
    data = read_plain(path, limit)
    if data is None:
        return None
    try:
        return json.loads(data.decode("utf-8"))
    except (ValueError, RecursionError):  # (ValueError: not UTF-8 either)
        return None


def read_text(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (OSError, ValueError):  # ValueError: not UTF-8
        return None


def short_id(value):
    """Stable one-way id, so account UUIDs and paths never appear in the output."""
    return hashlib.sha256(value.encode()).hexdigest()[:12]


def private_dir(path):
    """Create the cache dir readable only by the user: it holds project paths."""
    path.mkdir(parents=True, exist_ok=True)
    if path.stat().st_mode & 0o077:
        os.chmod(path, 0o700)


def write_json_atomic(path, data, private=False):
    """Write path in one go (a new file, renamed over it); private: only you can read it, whatever the umask."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with (os.fdopen(os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8")
              if private else open(tmp, "w", encoding="utf-8")) as f:
            json.dump(data, f, separators=(",", ":"))
        os.replace(tmp, path)
    except BaseException:
        # (on a full disk every check, a new process, would leave one)
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def claude_settings_files(home, profiles):
    """Each Claude profile's settings.json, once per real file (also of a
    ~/.claude that Claude has had no chat in yet): the files Talpy Den
    changes (pane.py's hooks, cleanup.py's cleanupPeriodDays)."""
    seen, out = set(), []
    folders = [p.path for p in profiles]
    if (Path(home) / ".claude").is_dir():
        folders.append(Path(home) / ".claude")
    for folder in folders:
        real = os.path.realpath(str(folder / "settings.json"))
        if real not in seen:
            seen.add(real)
            out.append(Path(real))
    return out


class claude_settings_lock:
    """Held while a helper reads, changes and writes Claude's settings
    (with): a hook turned on while the cleanup writes cleanupPeriodDays
    mustn't lose either change."""

    def __init__(self, home):
        self.path = cache_dir(Path(home)) / "claude-settings.lock"
        self.file = None

    def __enter__(self):
        private_dir(self.path.parent)
        self.file = open(str(self.path), "a")
        fcntl.flock(self.file, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        self.file.close()  # (the lock goes with it)
        return False


def write_claude_settings(path, data):
    """Write one of Claude's settings.json in one go (the real file, not a
    link to it: what it points to stays one), keeping its mode; its folder
    made if it isn't there. Under claude_settings_lock, read to written."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.talpy-den.tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if path.exists():
            import shutil
            shutil.copymode(str(path), str(tmp))
        os.replace(str(tmp), str(path))
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def write_atomic(path, data, mode=None, times=None, new=False):
    """Write data (bytes) as path in one go, safely in a folder whose content
    isn't yours alone (a project, a repository: it can ship links): through
    a new file beside it (tempfile.mkstemp: a random name, made by this call,
    never one a link was put at), renamed over path (new: linked as path,
    which mustn't be there: FileExistsError). mode: its permission bits
    (None: path's own, else 0o666 less the umask); times: its (atime_ns,
    mtime_ns)."""
    import tempfile
    path = str(path)
    folder, name = os.path.split(path)
    if mode is None:
        try:
            mode = os.stat(path).st_mode & 0o7777
        except OSError:
            mask = os.umask(0o077)
            os.umask(mask)
            mode = 0o666 & ~mask
    fd, tmp = tempfile.mkstemp(prefix=f".{name}.", suffix=".tmp", dir=folder or ".")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()  # (before the times: a write at close would change them)
            os.fchmod(f.fileno(), mode)
            if times is not None:
                os.utime(f.fileno(), ns=times)
        if new:
            os.link(tmp, path)
            os.unlink(tmp)
        else:
            os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def to_ms(value):
    """Epoch seconds, epoch milliseconds or an ISO-8601 string -> epoch ms."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value if value > 1e12 else value * 1000) if math.isfinite(value) else None
    if isinstance(value, str):
        try:
            return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)
        except ValueError:
            return None
    return None


def local_day(timestamp):
    """ISO timestamp from a transcript -> local YYYY-MM-DD, or None."""
    ms = to_ms(timestamp)
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000).date().isoformat()
    except (OverflowError, OSError, ValueError):  # a date out of range
        return None


def short_path(path, home):
    if not path:
        return ""
    p, h = str(path), str(home)
    if p == h:
        return "~"
    if p.startswith(h + "/"):
        p = "~/" + p[len(h) + 1 :]
    parts = p.split("/")
    if len(parts) > 4:
        p = "…/" + "/".join(parts[-2:])
    return p


def strip_prefix(text, prefix):  # str.removeprefix needs Python 3.9; remote hosts may be older
    return text[len(prefix):] if text.startswith(prefix) else text


def number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


# ---------------------------------------------------------------- profiles


class Profile:
    """One Claude Code config dir (what CLAUDE_CONFIG_DIR points at)."""

    def __init__(self, path, home, aliases=()):
        self.path = path
        self.dirname = path.name
        try:
            self.real = path.resolve()
        except (OSError, RuntimeError):
            self.real = path
        # Rows and caches are keyed by the real folder: a link like ~/.claude
        # can be switched to another profile at any time.
        self.key = self.real.name
        # Other names of the same dir (e.g. ~/.claude linked to ~/.claude-personal):
        # status-line snapshots are filed under whichever name a session used.
        # A snapshot filed under a link's name only counts if it's newer than
        # the link itself: before the link was last switched, that name meant
        # another profile.
        names = [path, *(a if isinstance(a, Path) else home / a for a in aliases), self.real]
        self.snapshot_sources = {}
        for p in names:
            try:
                since = p.lstat().st_mtime if p.is_symlink() else 0.0
            except OSError:
                since = 0.0
            self.snapshot_sources[p.name] = max(since, self.snapshot_sources.get(p.name, 0.0))
        self.snapshot_dirs = list(self.snapshot_sources)
        is_default = path == home / ".claude"
        name = (read_text(path / ".profile-name") or "").strip()
        self.custom_name = bool(name)
        if not name:
            # (~/.claude: "main", not "default", which marks the default account)
            name = "main" if is_default else strip_prefix(path.name, ".claude-").lstrip(".") or path.name
        self.label = name
        # Claude Code keeps account info in $CLAUDE_CONFIG_DIR/.claude.json, or
        # ~/.claude.json when running with the default config dir.
        data = read_json(path / ".claude.json")
        if is_default and not (isinstance(data, dict) and data.get("oauthAccount")):
            data = read_json(home / ".claude.json")
        data = data if isinstance(data, dict) else {}
        account = data.get("oauthAccount") if isinstance(data.get("oauthAccount"), dict) else {}
        self.account_id = account.get("accountUuid")
        # and its own cache of the plan usage (what /usage fetches; for the
        # VS Code panel's chats refresh_usage has it fetched): for an account
        # whose status line hasn't run lately
        cache = data.get("cachedUsageUtilization")
        self.usage_cache = cache if isinstance(cache, dict) and cache.get("accountUuid") in (None, self.account_id) else None
        # and the folders Claude ran in (its "projects"), which it keeps when
        # it deletes their chats (cleanupPeriodDays): plan_folders
        projects = data.get("projects")
        self.project_folders = [f for f in projects if isinstance(f, str) and f.startswith("/")] \
            if isinstance(projects, dict) else []
        self.display_name = clean_text(account.get("displayName"), 40) or None
        org_type = account.get("organizationType") or ""
        self.plan = PLAN_NAMES.get(org_type) or (
            strip_prefix(org_type, "claude_").replace("_", " ").title() if org_type else None
        )
        self.plan_detail = plan_detail(self.plan, account)
        self.is_default = is_default


TIER_TIMES = re.compile(r"(?:^|_)(\d{1,3})x(?:$|_)")  # Max's "…_max_20x": 20 times Pro's usage


def plan_detail(plan, account):
    """The plan with its tier, as its limits differ by it: "Max 20×" (the
    rate-limit tier), "Team · standard seat" (the seat); else the plan."""
    if not plan:
        return None
    if plan == "Max":
        for field in ("organizationRateLimitTier", "userRateLimitTier"):
            m = TIER_TIMES.search(str(account.get(field) or ""))
            if m:
                return "Max %s×" % m.group(1)
    seat = str(account.get("seatTier") or "")
    for kind in ("premium", "standard"):
        if kind in seat:
            return "%s · %s seat" % (plan, kind)
    return plan


def is_profile_dir(path):
    """A Claude config folder: one Claude has run in, or a new one (made by
    accounts.py or another profile tool: .profile-name; Claude's .claude.json once
    you've started to log in)."""
    return is_dir(path) and (is_dir(path / "sessions") or is_dir(path / "projects")
                             or os.path.isfile(str(path / ".profile-name")) or os.path.isfile(str(path / ".claude.json")))


def discover_profiles(home, extra_dirs=()):
    candidates = [home / ".claude", *sorted(home.glob(".claude-*"))]
    found = []
    for d in candidates:
        if is_profile_dir(d):
            found.append(d)
    for e in extra_dirs:
        d = Path(e).expanduser()
        if is_dir(d):
            found.append(d)
    by_real = {}
    for d in found:
        by_real.setdefault(d.resolve(), []).append(d)
    # A folder found as itself and through a link (~/.claude) is named after
    # itself: the link can be switched to another profile at any time
    profiles = [Profile(dirs[0], home, dirs[1:])
                for dirs in (sorted(ds, key=lambda d: d.is_symlink()) for ds in by_real.values())]
    keys = set()
    for p in profiles:  # two folders of the same name (e.g. --config-dir /data/.claude): told apart
        if p.key in keys:
            p.key = f"{p.key}-{short_id(str(p.real))[:6]}"
        keys.add(p.key)
    # A lone ~/.claude isn't the "main" one of anything: name it the way Claude
    # knows you (the account's display name), unless .profile-name says otherwise.
    if len(profiles) == 1 and profiles[0].is_default and not profiles[0].custom_name:
        profiles[0].label = profiles[0].display_name or "Claude"
    return profiles


def matches_profile(profile, name):
    """Is name (a folder name like .claude-work, or a path) this profile?
    None or "" (no profile named) is none."""
    if not isinstance(name, str) or not name:
        return False
    if name in (profile.dirname, profile.key, *profile.snapshot_dirs):
        return True
    try:
        return Path(name).expanduser().resolve() == profile.real
    except (OSError, RuntimeError):
        return False


def is_dir(path):
    """Path.is_dir, also on Python 3.7-3.11 (an SSH host's), where a folder
    you may not read raises instead of saying no."""
    try:
        return path.is_dir()
    except OSError:
        return False


def logged_out_notes(cache_root):
    """Real folders of the profiles accounts.py logged out of: {path: ms}."""
    data = read_json(cache_root / "accounts.json")
    notes = data.get("loggedOut") if isinstance(data, dict) else None
    return notes if isinstance(notes, dict) else {}


def needs_login(profile, logged_out=()):
    """Isn't this profile logged in to a Claude account? Claude's logout
    takes oauthAccount out of its .claude.json. Without it, a profile may
    still use an API key (which the widget can't see), so only a new one
    (.profile-name, no chats yet) or one logged out here counts."""
    if profile.account_id is not None:
        return False
    return profile.custom_name or not is_dir(profile.path / "projects") or str(profile.real) in logged_out


def group_profiles(profiles):
    """Profiles logged into the same account share plan limits -> one group."""
    groups = {}
    for p in profiles:
        groups.setdefault(p.account_id or f"dir:{p.path}", []).append(p)
    return list(groups.items())


# ---------------------------------------------------------------- sessions


def proc_start_time(pid):
    """Field 22 (starttime) of /proc/<pid>/stat, as Claude stores in procStart."""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as f:
            stat = f.read()
    except OSError:
        return None
    fields = stat[stat.rfind(")") + 2 :].split()  # comm may contain spaces
    return fields[19] if len(fields) > 19 else None


def is_alive(entry):
    pid = entry.get("pid")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    start = proc_start_time(pid)
    if start is None:
        return False
    expected = entry.get("procStart")
    return expected is None or str(expected) == start  # guards against PID reuse


def is_recurring(job):
    """Routines, self-waking jobs and /loop jobs finish a run without being done
    (Claude Code 2.1.300: GY + Vat)."""
    in_flight = job.get("inFlight") if isinstance(job.get("inFlight"), dict) else {}
    looped = any(isinstance(job.get(k), str) and job[k].strip().lower().startswith("/loop")
                 for k in ("intent", "initialPrompt"))
    return (job.get("routine") is not None or job.get("selfWake") is True
            or "session_cron" in (in_flight.get("kinds") or []) or looped)


def job_finished(job):
    return job.get("state") in FINISHED_JOB_STATES and job.get("tempo") != "active"


def note_unknown(ctx, record, job=False):
    """Note what a session entry (or a job's state.json) holds that Claude Code
    didn't write before (KNOWN_VALUES), for unknown_values_text."""
    unknown = getattr(ctx, "unknown", None)
    if unknown is None or not isinstance(record, dict):
        return
    if job:
        fields, version = [("job state", "state"), ("job tempo", "tempo")], record.get("cliVersion")
    else:
        fields, version = [("chat kind", "kind"), ("chat status", "status")], record.get("version")
    for what, key in fields:
        value = record.get(key)
        if value is not None and value not in KNOWN_VALUES[what]:
            unknown.setdefault((what, clean_text(str(value), 40)), version if isinstance(version, str) else "")


def unknown_values_text(unknown):
    """One line for the popup about the new values, or None."""
    if not unknown:
        return None
    versions = sorted({v for v in unknown.values() if v}, key=version_key)
    found = ", ".join(f'{what} "{value}"' for what, value in sorted(unknown))
    return (f"{'Claude Code ' + versions[-1] if versions else 'Claude Code'} writes something Talpy Den "
            f"doesn't know yet ({found}): some chats may show the wrong state until Talpy Den is updated.")


def session_state(entry, job=None):
    """Map a session (and its background-job record) to waiting/working/idle/done.

    Mirrors Claude Code 2.1: the `claude agents` rules for background jobs and
    the terminal status (OSC 7501) rules for interactive sessions.
    """
    status = entry.get("status")
    waiting = status == "waiting" and entry.get("waitingFor") != "dialog open"
    if status == "busy":
        return "working"
    if job is None:
        if status == "shell":  # turn over, but a background shell still runs
            return "working"
        return "waiting" if waiting else "idle"
    # Background job. The live status above wins over the job record, whose
    # state can lag behind (e.g. still "blocked" after you answered); a job
    # needs you only when its tempo says so or the session itself waits.
    if job_finished(job) and not (job.get("state") == "done" and is_recurring(job)):
        return "done"
    if job.get("needs") == NOT_STARTED and job.get("tempo") == "blocked":
        return "idle"  # dispatched without a prompt: nothing for Claude to do yet
    if job.get("tempo") == "blocked" or waiting:
        return "waiting"
    # Its turn is over: the session is idle and its job's tempo went idle as the turn ended. Claude
    # writes the tempo at every turn's end, but the outcome (state) only for a turn that ended by
    # itself, and not always "done": a turn you stopped keeps "working" (stopped while it thought,
    # nothing is written at all), and so does one whose summary says it goes on. A background task
    # that just ended leaves the session idle for 15–100 ms before its notification wakes it, still
    # counted in inFlight then; a recurring job between runs stays as it was.
    in_flight = job.get("inFlight") if isinstance(job.get("inFlight"), dict) else {}
    if status == "idle" and job.get("tempo") == "idle" and not (in_flight.get("tasks") or 0) \
            and not is_recurring(job):
        return "idle"
    return "working"


def parked_job_state(job, present, now_ms, keep_done_ms=0):
    """(state, reason) of a job record whose session process is gone, or None to hide it.

    Mirrors `claude agents --all`: the daemon retires idle workers, including
    jobs blocked on you, so a job can need input with no process running.
    Finished jobs (and jobs whose process died) stay listed for keep_done_ms.
    """
    if job.get("needs") == NOT_STARTED:
        return None
    updated = to_ms(job.get("updatedAt"))
    recent_end = bool(keep_done_ms) and updated is not None and now_ms - updated <= keep_done_ms
    if job_finished(job):
        if not (job.get("state") == "done" and is_recurring(job)):
            return ("done", "" if job.get("state") == "done" else job["state"]) if recent_end else None
        # A recurring job between two runs isn't done (`claude agents` too)
        return ("waiting" if job.get("tempo") == "blocked" else "working"), ""
    created = to_ms(job.get("createdAt"))
    if not present and not (created is not None and now_ms - created < RECENT_JOB_MS):
        exec_job = job.get("template") == "exec" and not job.get("respawnFlags")
        # (state "blocked" stays after you answer: with tempo "active" again,
        # the job went on working and its process died mid-task)
        if job.get("state") == "blocked" and job.get("tempo") != "active" and not exec_job:
            return "waiting", ""
        # its turn ended (tempo idle: stopped, or a summary that says it goes on) and the service let
        # its process go: settled, not died mid-task (a worker that dies mid-turn keeps tempo "active")
        if job.get("tempo") == "idle" and not exec_job:
            return ("done", "") if recent_end else None
        return ("done", "failed") if recent_end else None  # its process died mid-task
    return ("waiting" if job.get("tempo") == "blocked" else "working"), ""


def clean_text(value, limit=200):
    return " ".join(value.split())[:limit] if isinstance(value, str) else ""


def mtime(path):
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def valid_id(value):
    # (nor a word that is a flag, "--screenshot": ids go on as words of jump.py's and remote.py's command lines)
    return isinstance(value, str) and value != "" and "/" not in value and value not in (".", "..") \
        and not value.startswith("-")


# The Claude folder a status-line snapshot is of (statusline-snippet.sh
# writes it into each one): snapshots are filed under the folder's name, which
# two folders can share (~/.claude and /data/.claude).
SNAPSHOT_FOLDER = "talpyDenConfigDir"


def snapshot_of(snap, reals):
    """Is a status-line snapshot one of these (real) Claude folders'? One of a
    folder of the same name isn't; one an older snippet wrote names no folder
    and counts, as it always did."""
    folder = snap.get(SNAPSHOT_FOLDER) if isinstance(snap, dict) else None
    if not isinstance(folder, str) or not folder.startswith("/"):
        return True
    return os.path.realpath(folder) in {str(r) for r in reals}


def snapshot_paths(snapshot_root, profile, ids):
    """(mtime, path) of this profile's status-line snapshots of these session
    ids, newest first, leaving out ones filed under a link's name before the
    link was last switched, and those of another folder of the same name."""
    found = []
    for name, since in profile.snapshot_sources.items():
        for sid in ids:
            if not valid_id(sid):
                continue
            path = snapshot_root / name / f"{sid}.json"
            t = mtime(path)
            if t is not None and t >= since and snapshot_of(read_json(path), [profile.real]):
                found.append((t, path))
    found.sort(reverse=True)
    return found


# ---------------------------------------------------------------- context left

# The context window of each model Claude Code knows (its own table, 2.1.318), by the name a
# transcript gives it ("claude-opus-5-5"; a date, a provider's prefix or "[1m]" around it: model_key)
CONTEXT_1M = 1000000
CONTEXT_WINDOWS = dict(
    {m: CONTEXT_1M for m in ("claude-opus-4-7", "claude-opus-4-8", "claude-opus-5", "claude-opus-5-5", "claude-sonnet-5",
                             "claude-sonnet-5-5", "claude-haiku-5-5", "claude-fable-5", "claude-fable-5-1")},
    # (200k, or 1M where it's chosen: "sonnet[1m]")
    **{m: 200000 for m in ("claude-opus-4", "claude-opus-4-1", "claude-opus-4-5", "claude-opus-4-6", "claude-sonnet-4",
                           "claude-sonnet-4-5", "claude-sonnet-4-6", "claude-haiku-4-5")})
# Claude Code compacts a chat on its own (auto-compact) at its window less the room it keeps for
# Claude's reply (the model's most output, at most 20k: every model above has more) and 13k more,
# and says it's close from 20k before that (2.1.318)
COMPACT_ROOM = 20000 + 13000
COMPACT_CLOSE = 20000
USAGE_READ = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
# The auto-compact window you can set (Claude Code 2.1.318): CLAUDE_CODE_AUTO_COMPACT_WINDOW
# ("200k", "1M", 200000) first, else autoCompactWindow in settings (modelSettings' for the model
# first; "auto": the model's own), from 100k to 1M; Claude compacts by it where it's below the
# model's window
COMPACT_WINDOW_ENV = "CLAUDE_CODE_AUTO_COMPACT_WINDOW"
COMPACT_WINDOW_MIN, COMPACT_WINDOW_MAX = 100000, 1000000


def model_key(model):
    """The name Claude Code's table gives a model ("claude-opus-4-1") from the
    one a transcript or a provider gives it ("claude-opus-4-1-20250805",
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0", "claude-sonnet-4-6[1m]"):
    family, version and minor version, no date; None for no Claude model."""
    i = model.find("claude-") if isinstance(model, str) else -1
    if i < 0:
        return None
    words = model[i:].split("[")[0].replace("@", "-").split("-")[:4]
    if len(words) < 3 or not words[2].isdigit():
        return None
    minor = words[3] if len(words) > 3 and words[3].isdigit() and len(words[3]) <= 2 else None
    return "-".join(words[:3]) + ("-" + minor if minor else "")


def context_window(model, used=0, told=None):
    """The context window of a chat on this model (tokens), None when it isn't
    known. told(): the window its status line gives (status_window), else
    Claude Code's table; 1M where that's chosen ([1m]) or the chat is past its
    model's own window already."""
    said = told() if told is not None else None
    if isinstance(said, int) and said > 0:
        return said
    window = CONTEXT_WINDOWS.get(model_key(model))
    if window is not None and window < CONTEXT_1M and ("[1m]" in model.lower() or used > window):
        return CONTEXT_1M
    return window


def context_left(usage, model, told=None, compact=None):
    """How full a chat's context is, from the token counts of Claude's last
    message (usage: all it read, cached or not, which its next one starts
    from): {"used", "window", "compactAt": where Claude compacts the chat,
    "left": % of it till then, "near": Claude Code says it's close}, or None
    when it can't be known (no counts, a model not known: context_window).
    compact: the auto-compact window you set (compact_window), when it's
    below the model's window."""
    if not isinstance(usage, dict):
        return None
    used = sum(n for n in (usage.get(k) for k in USAGE_READ) if isinstance(n, int) and not isinstance(n, bool) and n > 0)
    window = context_window(model, used, told) if used else None
    if window is not None and isinstance(compact, int) and 0 < compact < window:
        window = compact
    if window is None or window <= COMPACT_ROOM:
        return None
    at = window - COMPACT_ROOM
    return {"used": used, "window": window, "compactAt": at, "left": max(0, int((at - used) * 100 / at + 0.5)),
            "near": used >= at - COMPACT_CLOSE}


def compact_tokens(value):
    """An auto-compact window as Claude Code reads it ("200k", "1M", 200000;
    a bare 100 to 1000 in the env is thousands), kept from 100k to 1M; None
    for none or one it ignores."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        tokens = float(value)
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        unit = {"m": 1e6, "k": 1e3}.get(text[-1].lower())
        try:
            tokens = float(text[:-1]) * unit if unit else float(text)
        except ValueError:
            return None
        if unit is None and 100 <= tokens <= 1000:
            tokens *= 1000
    else:
        return None
    if tokens != tokens or tokens < 1:  # (NaN)
        return None
    return int(round(min(COMPACT_WINDOW_MAX, max(COMPACT_WINDOW_MIN, tokens))))


# settings.json path -> ((mtime_ns, size), its env value, its setting, its modelSettings, whether it names the
# permission hook)
_COMPACT_SETTINGS = {}


def profile_settings(profile_path):
    """What the status reads of an account's settings.json, once a run per
    file and change: (CLAUDE_CODE_AUTO_COMPACT_WINDOW in its env,
    autoCompactWindow, modelSettings, whether its PermissionRequest hooks
    name Talpy Den's permission hook), or None (no settings)."""
    path = os.path.join(str(profile_path), "settings.json")
    try:
        st = os.stat(path)
    except OSError:
        return None
    stamp = (st.st_mtime_ns, st.st_size)
    kept = _COMPACT_SETTINGS.get(path)
    if kept is None or kept[0] != stamp:
        data = read_json(Path(path))
        data = data if isinstance(data, dict) else {}
        env = data.get("env") if isinstance(data.get("env"), dict) else {}
        models = data.get("modelSettings") if isinstance(data.get("modelSettings"), dict) else {}
        hooks = data.get("hooks") if isinstance(data.get("hooks"), dict) else {}
        relay = PERMISSION_HOOK_FILE in json.dumps(hooks.get("PermissionRequest") or [])
        kept = _COMPACT_SETTINGS[path] = (stamp, env.get(COMPACT_WINDOW_ENV), data.get("autoCompactWindow"), models, relay)
    return kept[1:]


def relay_in_settings(profile_path):
    """Whether the account's settings have Talpy Den's permission hook (on
    for every chat: "Answer permission prompts from Talpy Den")."""
    kept = profile_settings(profile_path)
    return bool(kept and kept[3])


def compact_window(profile_path, model):
    """The auto-compact window you set for a chat on this model in the
    account's settings (its env's CLAUDE_CODE_AUTO_COMPACT_WINDOW, else
    autoCompactWindow: the model's in modelSettings first), or None (Claude's
    own: the model's window). Read once a run per file and change."""
    kept = profile_settings(profile_path)
    if kept is None:
        return None
    env_value, setting, models, _relay = kept
    tokens = compact_tokens(env_value)
    if tokens is not None:
        return tokens
    key = model_key(model)
    own = next((v.get("autoCompactWindow") for k, v in models.items()
                if isinstance(v, dict) and "autoCompactWindow" in v and model_key(k if k.startswith("claude-") else "claude-" + k) == key),
               None) if key else None
    value = own if own is not None else setting
    return None if value == "auto" else compact_tokens(value) if not isinstance(value, str) else None


def attach_snapshot(session, snapshot_root, profile, ids=None, since=None):
    """Add model, context fill and cost from the session's newest status-line
    snapshot; with since (ms), only one written since then: a run with no
    status line (VS Code's panel, a background session) shows nothing of an
    earlier run's."""
    ids = dict.fromkeys(ids or [session["sessionId"]])
    for t, path in snapshot_paths(snapshot_root, profile, ids):
        if since is not None and t * 1000 < since:
            return
        snap = read_json(path)
        if isinstance(snap, dict):
            part = lambda key: snap.get(key) if isinstance(snap.get(key), dict) else {}
            session["context"] = number(part("context_window").get("used_percentage"))
            # (what's left before Claude compacts it, as Talpy Chat's header says it: context_left)
            size = part("context_window").get("context_window_size")
            left = context_left(part("context_window").get("current_usage"), part("model").get("id"),
                                (lambda: size) if isinstance(size, int) and not isinstance(size, bool) else None,
                                compact_window(profile.path, part("model").get("id")))
            session["contextLeft"] = left["left"] if left else None
            session["contextNear"] = bool(left and left["near"])
            model = part("model").get("display_name")
            session["model"] = model if isinstance(model, str) and model else None
            effort = part("effort").get("level")
            session["effort"] = effort if isinstance(effort, str) and effort else None
            session["costUsd"] = number(part("cost").get("total_cost_usd"))
            return


def make_session(profile, home, *, sid, pid, name, cwd, kind, entrypoint, state, reason,
                 waiting_for, detail, since, started_at):
    return {
        # A shared chat can be listed under two profiles with the same id, so
        # rows are told apart by profile + id + live/background-record.
        "key": f"{profile.key}/{sid}/{'live' if pid else 'job'}",
        "profileDir": profile.key,
        "sessionId": sid,
        "chatId": sid,
        "pid": pid,
        "name": name or os.path.basename(cwd) or sid[:8],
        "cwd": cwd,
        "cwdShort": short_path(cwd, home),
        "profile": profile.label,
        "kind": kind,
        "entrypoint": entrypoint,
        "state": state,
        "reason": reason,
        "waitingFor": waiting_for,
        "detail": detail,
        "since": since,
        "startedAt": started_at,
        "context": None,
        "contextLeft": None,  # % left before Claude compacts it (context_left), as Talpy Chat's header says it
        "contextNear": False,
        "model": None,
        "effort": None,  # the reasoning effort, from the status line (low … max)
        "costUsd": None,
        "agents": None,
        "shared": None,
        "tmux": False,  # runs in a tmux pane: it can be interrupted (Esc)
        "bgStop": False,  # a live background session Talpy Chat's Stop can interrupt (interrupt_background)
        "hooked": False,  # a background chat whose prompts Talpy Den's permission hook answers (finish_row)
        "terminalApp": None,  # the terminal it runs in otherwise, by name (Konsole, kitty…): terminal_name
        "attached": None,  # a background session shown in a terminal (claude attach): {"in", "app"} (attached_in)
        "peek": None,  # what it's doing, your last prompt, Claude's last reply (chat_peek)
        "changes": None,  # the files it changed: {"count", "files"} (ChatCache.changes)
        "tasks": None,  # its task list: {"done", "total", "current", "items"} (task_progress)
        "stats": None,  # its recap: prompts, tool calls, tokens, time worked (stats_summary)
        "plan": None,  # the plan it made: {"slug", "title", "path", "updatedAt"} (plan_of)
        # other chats with a process that changed some of the same files (note_overlaps)
        "overlaps": None,
        "stopped": None,  # what stopped it: a usage limit or an expired login (stopped_by, limit_stop)
        "reply": "background",  # how it takes a message from the chat pane (reply_route)
        "review": None,  # a chat that changed files: {"editedAt", "tests"} (TestsCache.review)
        "permission": None,  # what it asks while it waits for a permission (note_permissions)
        "live": None,  # what it does now, step by step, from the live hook (note_live)
    }


def process_config_dir(pid):
    """The Claude config dir a running process uses right now (its
    CLAUDE_CONFIG_DIR, else ~/.claude of its HOME), with links resolved."""
    try:
        with open(f"/proc/{pid}/environ", "rb") as f:
            env = f.read().split(b"\0")
    except OSError:
        return None
    values = {}
    for item in env:
        key, sep, value = item.partition(b"=")
        if sep and key in (b"CLAUDE_CONFIG_DIR", b"HOME"):
            values[key] = value.decode(errors="replace")
    folder = values.get(b"CLAUDE_CONFIG_DIR") or (values[b"HOME"] + "/.claude" if values.get(b"HOME") else None)
    if not folder:
        return None
    try:
        return Path(folder).expanduser().resolve()
    except (OSError, RuntimeError):
        return None


def live_entries_all(profiles):
    """[(entry, profile it runs on, profile whose sessions/ holds the entry)]
    of every live session process.

    A process started with a link name (CLAUDE_CONFIG_DIR=~/.claude) follows
    the link when it's switched to another profile: its next status write
    lands in the other profile's sessions/, and the old file stays behind
    until the process exits. So the same process (same pid, start time and
    file name) can show up in two profiles: keep its newest entry, under the
    profile its config dir points to now.
    """
    by_real = {p.real: p for p in profiles}
    best, order = {}, []
    for p in profiles:
        try:
            files = sorted((p.path / "sessions").glob("*.json"))
        except OSError:
            continue
        for f in files:
            entry = read_json(f)
            if not isinstance(entry, dict) or not is_alive(entry):
                continue
            key = (entry.get("pid"), str(entry.get("procStart")), f.stem)
            stamp = max(number(entry.get("statusUpdatedAt")) or 0, number(entry.get("updatedAt")) or 0,
                        int((mtime(f) or 0) * 1000))
            if key not in best:
                order.append(key)
            if key not in best or stamp > best[key][2]:
                best[key] = (entry, p, stamp)
    result = []
    for key in order:
        entry, holder, _ = best[key]
        runs_on = by_real.get(process_config_dir(entry["pid"]))
        result.append((entry, runs_on or holder, holder))
    return result


def read_job(profiles, job_id):
    """A job's state.json, from the first of profiles that has it (newest wins
    when several do: a job written through a switched link can leave a copy)."""
    if not valid_id(job_id):
        return None
    best = None
    for p in profiles:
        job = read_json(p.path / "jobs" / job_id / "state.json")
        if isinstance(job, dict) and (best is None or (to_ms(job.get("updatedAt")) or 0) > (to_ms(best.get("updatedAt")) or 0)):
            best = job
    return best


def live_row(entry, profile, holder, home, ctx):
    """The row of a live session process, or None for processes that aren't sessions."""
    # Pre-warmed spares, terminals parked on a background job and the daemon's
    # own processes are not sessions (`claude agents` hides them).
    if entry.get("spare") or entry.get("parkedJobId") or entry.get("kind") not in SESSION_KINDS:
        return None
    # nor is the widget's own fetch of the plan usage (refresh_usage)
    if is_usage_check(entry.get("cwd"), getattr(ctx, "usage_check", None)):
        return None
    job_id = entry.get("jobId") if valid_id(entry.get("jobId")) else None
    # Background jobs keep their lifecycle (state, tempo, what they need, a
    # one-line detail) in jobs/<jobId>/state.json; some sessions write the same
    # fields into their own entry.
    job = read_job(dict.fromkeys([profile, holder]), job_id) if job_id else None
    own = {k: entry[k] for k in ("state", "tempo", "needs", "detail") if k in entry}
    if own:
        job = {**(job or {}), **own}
    note_unknown(ctx, job, job=True)
    state = session_state(entry, job)
    waiting_for = entry.get("waitingFor") if entry.get("status") == "waiting" else None
    if state == "waiting":
        reason = WAITING_REASONS.get(waiting_for, waiting_for or "")
        detail = clean_text((job or {}).get("needs"))
    elif state == "done":
        outcome = (job or {}).get("state")
        reason = outcome if outcome in ("failed", "stopped") else ""
        detail = clean_text((job or {}).get("detail"))
    else:
        reason = "background shell" if entry.get("status") == "shell" else ""
        detail = ""
    cwd = entry.get("cwd") if isinstance(entry.get("cwd"), str) else ""
    sid = entry.get("sessionId") if valid_id(entry.get("sessionId")) else ""
    row = make_session(
        profile, home, sid=sid, pid=entry.get("pid"), name=entry.get("name"),
        cwd=cwd, kind=entry.get("kind"), entrypoint=entry.get("entrypoint") or "", state=state,
        reason=reason, waiting_for=waiting_for or "", detail=detail,
        since=number(entry.get("statusUpdatedAt")) or number(entry.get("startedAt")),
        started_at=number(entry.get("startedAt")))
    row["tmux"] = isinstance(entry.get("tmux"), str) and bool(entry["tmux"])
    row["bgStop"] = row["kind"] == "bg" and job_id is not None and bg_stop_known(entry.get("version"))
    if not row["tmux"] and row["entrypoint"] != "claude-vscode" and row["kind"] != "bg":
        row["terminalApp"] = terminal_name(row["pid"]) or None
    return finish_row(row, job, job_id, profile, ctx, alive=True)


def job_dirs(profile):
    try:
        return sorted(d for d in (profile.path / "jobs").iterdir() if d.is_dir())
    except OSError:
        return []


def newest_job_records(profiles):
    """{job id: real folder of the profile with the job's newest record}. A
    job written through a switched link leaves a copy of its record in the
    other profile; only the newest one counts, even when it's too old to be
    listed (else the stale copy, e.g. still "blocked", would be)."""
    newest = {}
    for p in profiles:
        for d in job_dirs(p):
            job = read_json(d / "state.json")
            if isinstance(job, dict):
                t = to_ms(job.get("updatedAt")) or 0
                if d.name not in newest or t > newest[d.name][0]:
                    newest[d.name] = (t, p.real)
    return {job_id: real for job_id, (_, real) in newest.items()}


def parked_rows(profile, home, live_jobs, ctx, newest=None):
    """Background jobs with no session process: blocked on you, or recently finished."""
    status = read_json(profile.path / "daemon.status.json")
    roster = status.get("workers") if isinstance(status, dict) else None
    roster = roster if isinstance(roster, dict) else {}
    rows = []
    for d in job_dirs(profile):
        if d.name in live_jobs or (newest is not None and newest.get(d.name, profile.real) != profile.real):
            continue
        job = read_json(d / "state.json")
        if not isinstance(job, dict):
            continue
        note_unknown(ctx, job, job=True)
        try:
            row = parked_row(profile, home, ctx, d, job, roster)
        except Exception as exc:  # one odd record mustn't hide the others
            getattr(ctx, "errors", []).append(f"{profile.label}: job {d.name}: {type(exc).__name__}: {exc}")
            continue
        if row is not None:
            rows.append(row)
    return rows


def parked_row(profile, home, ctx, d, job, roster):
    """The row of one background job with no session process, or None."""
    worker = roster.get(d.name)
    parked = parked_job_state(job, isinstance(worker, dict) and is_alive(worker), ctx.now_ms, ctx.keep_done_ms)
    if parked is None:
        return None
    state, reason = parked
    name = next((job[k] for k in ("name", "displayIntent", "intent")
                 if isinstance(job.get(k), str) and job[k].strip()), "")
    row = make_session(
        profile, home, sid=job["sessionId"] if valid_id(job.get("sessionId")) else d.name,
        pid=None, name=clean_text(name, 80), cwd=job.get("cwd") if isinstance(job.get("cwd"), str) else "",
        kind="bg", entrypoint="", state=state, reason=reason, waiting_for="",
        detail=clean_text(job.get("needs") if state == "waiting" else job.get("detail") if state == "done" else ""),
        since=to_ms(job.get("updatedAt")), started_at=to_ms(job.get("createdAt")))
    row = finish_row(row, job, d.name, profile, ctx, alive=False)
    if state == "done" and job.get("linkScanPath") and not any(
            transcript_path(p, i) is not None for p in ctx.profiles for i in dict.fromkeys((row["chatId"], row["sessionId"]))):
        return None  # (a finished one whose chat had a transcript and it's gone, deleted say: nothing to show)
    return None if handed_over(profile, row["chatId"], ctx.profiles) else row


def finish_row(row, job, job_id, profile, ctx, alive):
    """Which conversation the row shows, whether it's shared, its status-line
    snapshot and its subagents."""
    row["jobId"] = job_id
    row["reply"] = reply_route(row)
    row["jobSessionId"] = job["sessionId"] if isinstance(job, dict) and valid_id(job.get("sessionId")) else None
    # (a background chat whose prompts Talpy Den answers: the hook Talpy Chat gave it, in what Claude wakes it
    # with, or the one for every chat in its account's settings; it has no terminal of its own to ask in)
    row["hooked"] = row["kind"] == "bg" and (
        bool(isinstance(job, dict) and hook_settings(job.get("respawnFlags"))) or relay_in_settings(profile.path))
    row["chatId"], row["shared"] = chat_link(row, job, profile, ctx)
    # (only the run that's going on now: a chat resumed or gone on keeps its id)
    attach_snapshot(row, ctx.snapshot_root, profile, [row["sessionId"], row["chatId"], row["jobSessionId"]],
                    since=row["startedAt"])
    if ctx.agents is not None:  # a session continuing a chat shows that chat's agents
        row["agents"] = ctx.agents.session_agents(profile, row["chatId"], alive=alive,
                                                  since=row["startedAt"] if alive else None)
    chats = getattr(ctx, "chats", None)
    if chats is not None:
        path = transcript_path(profile, row["chatId"])
        row["peek"] = chats.peek(path)
        if row["peek"] and not (row["peek"].get("mode") and row["peek"].get("ultracode")) and path is not None:
            # (its newest entries name none: a chat in the Claude Code panel names its mode at its first
            # prompt only, and Claude notes ultracode again only every few prompts)
            rec = chats.edits(path)
            if rec.get("mode") and not row["peek"].get("mode"):
                row["peek"] = dict(row["peek"], mode=rec["mode"])
            if rec.get("ultra") and not row["peek"].get("ultracode"):
                row["peek"] = dict(row["peek"], ultracode=True)
        peek = row["peek"] or {}
        if row["model"] is None:  # (no status line in this run: the model of its newest reply)
            row["model"] = peek.get("model")
        row["plan"] = plan_of(profile, peek.get("slug"), ctx)
        went_on = (CONTINUE_PROMPT[:30], RETRY_PROMPT[:30])
        if row["name"].startswith(went_on) and path is not None and getattr(ctx, "links", None) is not None:
            # a chat that went on by itself is named after that message: its own name instead
            try:
                own = ctx.links.chat_info(path, path.stat())[0]
            except OSError:
                own = ""
            if own and not own.startswith(went_on):
                row["name"] = clean_text(own, 80)
        if row["plan"] is not None:
            row["plan"]["edited"] = plan_edited(row["plan"]["updatedAt"], mtime(path) if path is not None else None)
        if peek.get("stopped") and row["state"] == "waiting" and not row["waitingFor"] \
                and isinstance(job, dict) and job.get("tempo") == "blocked":
            # a background session a usage limit stopped is "blocked" ("rate
            # limited — wait and retry"): it waits for the limit, not for you
            row["state"], row["reason"], row["detail"] = "idle", "", ""
        # (one that works again, or waits for you, got past it)
        row["stopped"] = dict(peek["stopped"]) if peek.get("stopped") and row["state"] in ("idle", "done") else None
        files = chats.changed_files(path, row["cwd"], ctx.own_folders)
        row["changes"] = chats.changes(path, row["cwd"], ctx.home, ctx.own_folders, files)
        tests = getattr(ctx, "tests", None)
        row["review"] = tests.review(path) if files and tests is not None else None
        if files and isinstance(getattr(ctx, "changed", None), dict):
            ctx.changed[row["key"]] = set(files)
        row["tasks"] = task_progress(ctx.profiles, [row["sessionId"], row["chatId"], row.get("jobSessionId")])
        row["stats"] = chats.stats(path)
        if row["agents"] and path is not None:
            subs = {sub.name[len("agent-"):-len(".jsonl")]: sub for sub in subagent_transcripts(path)}
            for agent in row["agents"]["tree"]:
                st = chats.edits(subs[agent["id"]])["stats"] if agent["id"] in subs else None
                summary = stats_summary(st) if st else None
                if summary:
                    agent["toolCalls"] = sum(n for name, n in st["tools"].items() if name != "SubagentHandback")
                    agent["tokens"] = summary["tokens"]["total"]
    return row


# ---------------------------------------------------------------- subagents

AGENT_TAIL_BYTES = 65536
AGENT_TAIL_ENTRIES = 40  # conversation entries read from the end (its status needs the last few, its steps more)
AGENT_TAIL_MIN = 8  # read further back (up to PEEK_TAIL_MAX) until this many are found
AGENT_CACHE_VERSION = 3  # bump when agent_progress() reads transcripts differently (3: the model)
AGENT_TREE_LIMIT = 30
AGENT_STEPS = 6  # its last tool calls a row shows
AGENT_TASK_CHARS = 600
AGENT_REPORT_CHARS = 1500
FORK_BOILERPLATE_END = "</fork-boilerplate>"  # a fork's first prompt: Claude's rules for forks, then its directive


def short_text(value, limit=70):
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def describe_tool(block):
    """What a tool call is doing, in a few words: "Bash: npm test", "Edit: parser.py"."""
    name = block.get("name") or "tool"
    inp = block.get("input") if isinstance(block.get("input"), dict) else {}
    if name.startswith("mcp__"):
        parts = name.split("__")
        name = f"{parts[1]}: {parts[2]}" if len(parts) >= 3 else name
    if name == "Bash" and inp.get("command"):
        return f"Bash: {short_text(inp['command'], 60)}"
    for key in ("file_path", "notebook_path", "path"):
        if inp.get(key):
            return f"{name}: {os.path.basename(str(inp[key]).rstrip('/')) or inp[key]}"
    for key in ("description", "pattern", "query", "url", "skill", "prompt"):
        if inp.get(key):
            return f"{name}: {short_text(inp[key], 60)}"
    return name


def report_line(text, limit=90):
    """First line of an agent's report, without markdown decoration."""
    for line in (text or "").splitlines():
        line = line.replace("**", "").strip().lstrip("#*>-| ").strip()
        if line:
            return short_text(line, limit)
    return "finished"


def model_label(model):
    """claude-opus-5-5 -> "Opus 5.5", claude-haiku-4-5-20251001 -> "Haiku 4.5"
    (a model id as transcripts record it); None for none or a stand-in."""
    if not isinstance(model, str) or not model.startswith("claude"):
        return None
    words = [w for w in re.split(r"[-_]", model.split("[")[0])[1:] if not (w.isdigit() and len(w) >= 6)]
    family = next((w for w in words if w.isalpha()), None)
    version = ".".join(w for w in words if w.isdigit())
    if family is None:
        return model
    return f"{family.capitalize()} {version}".strip()


def transcript_model(entries):
    """The model of the newest assistant entry (not a stand-in like <synthetic>)."""
    for e in entries:
        msg = e.get("message") if isinstance(e.get("message"), dict) else {}
        label = model_label(msg.get("model")) if e.get("type") == "assistant" else None
        if label:
            return label
    return None


def agent_progress(path, finished=False):
    """(status, activity, last timestamp ms, model, {"steps", "report"}) from
    the end of a subagent transcript.

    Done = it handed its report back (a SubagentHandback call) or its last entry
    is a final answer (end_turn); failed = it ended on an API error (e.g. a
    usage limit); stopped = interrupted. Otherwise it's still working: on a
    tool call (shown) or thinking about tool results, unless Claude says it
    finished (finished: its meta.json). Steps are its last tool calls
    ("Bash: npm test"), oldest first; the report is what it handed back, as
    plain text ("" until it's done).
    """
    status, activity, ts, recent, report = agent_status(path, finished)
    detail = {"steps": agent_steps(recent), "report": tidy_text(plain_text(report), AGENT_REPORT_CHARS)}
    return status, activity, ts, transcript_model(recent), detail


def agent_status(path, finished=False):
    """agent_progress without the model and steps, plus the entries it
    looked at (newest first) and the report in full."""
    status, activity, ts, recent, report = agent_end(path)
    if status == "running" and finished:  # an end it doesn't know (e.g. out of output tokens)
        return "done", report_line(report) if report else "finished", ts, recent, report
    return status, activity, ts, recent, report


def agent_end(path):
    """agent_status, without what Claude says about it."""
    try:
        size = path.stat().st_size
    except OSError:
        return "running", "", None, [], ""
    nbytes = AGENT_TAIL_BYTES
    while True:  # more of it while big tool results fill the end
        entries = [e for e in tail_entries(path, size, nbytes) if e["type"] != "last-prompt"]
        recent = entries[:AGENT_TAIL_ENTRIES]
        if len(recent) >= AGENT_TAIL_MIN or nbytes >= size or nbytes >= PEEK_TAIL_MAX:
            break
        nbytes *= 4
    if nbytes >= size and len(entries) <= AGENT_TAIL_ENTRIES:
        # the whole run: what came before its first user entry is a fork's
        # copy of the call that started it, not something it did
        users = [i for i, e in enumerate(recent) if e["type"] == "user"]
        recent = recent[:users[-1] + 1] if users else []
    if not recent:
        return "running", "starting…", None, recent, ""
    ts = to_ms(recent[0].get("timestamp"))
    newest = recent[0]
    if newest["type"] == "user":
        text = message_text(newest.get("message")).strip()
        if text.startswith("[Request interrupted"):
            return "stopped", "interrupted", ts, recent, ""
        origin = newest.get("origin") if isinstance(newest.get("origin"), dict) else {}
        if origin.get("kind") == "coordinator" and text:  # the main chat sent it more to do
            return "running", "reading a message from its chat…", ts, recent, ""
    for e in recent:
        msg, content = blocks_of(e)
        if e["type"] == "user":
            if e is recent[0]:
                continue  # tool results just came back; look at what it ran
            return "running", "thinking…", ts, recent, ""
        if e.get("isApiErrorMessage") is True:
            return "failed", short_text(message_text(msg) or "API error", 90), ts, recent, ""
        uses = [c for c in content if c.get("type") == "tool_use"]
        if uses and uses[-1].get("name") == "SubagentHandback":
            report = (uses[-1].get("input") or {}).get("message")
            report = report if isinstance(report, str) else ""
            return "done", report_line(report), ts, recent, report
        if uses:
            label = describe_tool(uses[-1])
            return "running", (label if e is recent[0] else f"{label} (thinking about the result)"), ts, recent, ""
        if msg.get("stop_reason") == "end_turn":
            report = final_answer(recent, e)
            return "done", report_line(report), ts, recent, report
        return "running", "writing…", ts, recent, ""
    return "running", "thinking…", ts, recent, ""


def final_answer(recent, last):
    """The text of an agent's final answer: every text block of the reply
    that ends with entry last (each block is an entry of its own)."""
    msg_id = (last.get("message") or {}).get("id")
    parts = []
    for e in recent[next(i for i, e in enumerate(recent) if e is last):]:
        msg, blocks = blocks_of(e)
        if e["type"] != "assistant" or (e is not last and (msg_id is None or msg.get("id") != msg_id)):
            break
        parts[:0] = [c["text"] for c in blocks if c.get("type") == "text" and isinstance(c.get("text"), str)]
    return "\n\n".join(p for p in parts if p.strip())


def agent_steps(recent):
    """The last AGENT_STEPS tool calls among recent (newest first), oldest first."""
    steps = []
    for e in recent:
        if e["type"] == "assistant":
            steps += [describe_tool(c) for c in reversed(blocks_of(e)[1])
                      if c.get("type") == "tool_use" and c.get("name") != "SubagentHandback"]
            if len(steps) >= AGENT_STEPS:
                break
    return steps[:AGENT_STEPS][::-1]


def agent_task(path):
    """The task an agent was given: its transcript's first prompt (for a
    fork, the directive after Claude's rules for forks), or ""."""
    try:
        with open(path, "rb") as f:
            for n, line in enumerate(f):
                if n >= 50:
                    break
                if not USER_LINE.search(line):
                    continue
                try:
                    e = json.loads(line)
                except (ValueError, RecursionError):
                    continue
                if not isinstance(e, dict) or e.get("type") != "user":
                    continue
                text = message_text(e.get("message"))
                if FORK_BOILERPLATE_END in text:
                    text = re.sub(r"^\s*Your directive:\s*", "", text.split(FORK_BOILERPLATE_END, 1)[1])
                return text.strip()
    except OSError:
        pass
    return ""


def agent_started(path):
    """Timestamp (ms) of the first entry of a subagent transcript."""
    try:
        with open(path, "rb") as f:
            for line in f:
                try:
                    ts = to_ms(json.loads(line).get("timestamp"))
                except (ValueError, AttributeError, RecursionError):
                    continue
                if ts is not None:
                    return ts
    except OSError:
        pass
    return None


class AgentCache:
    """Remembers each subagent transcript's progress by (size, mtime) between polls,
    so only transcripts that changed are read again."""

    PARENT_RETRY_S = 60  # how soon to look again for a nested agent's parent that wasn't found

    def __init__(self, path):
        self.path = path
        data = read_json(path)
        ok = isinstance(data, dict) and data.get("version") == AGENT_CACHE_VERSION
        self.old = data if ok else {}
        self.old_files = data.get("files", {}) if ok else {}
        self.old_parents = data.get("parents", {}) if ok else {}
        self.files, self.parents, self.changed = {}, {}, not ok
        # Parents looked for in vain (agent id: when), so their siblings'
        # transcripts aren't all read again on every check
        misses = data.get("misses") if ok else None
        self.misses = {k: t for k, t in misses.items() if isinstance(t, (int, float))} if isinstance(misses, dict) else {}
        # What an unfolded agent shows (its task, last steps and report) is
        # kept in a file of its own: older copies of this script (a VS Code
        # extension not updated yet) rewrite agents.json without it.
        self.details_path = path.with_name("agent-details.json")
        details = read_json(self.details_path)
        ok = isinstance(details, dict) and details.get("version") == 1
        self.old_details_data = details if ok else {}
        self.old_details = details.get("files", {}) if ok else {}
        self.details, self.details_changed = {}, not ok

    def progress(self, transcript, finished=False):
        """(status, activity, last ts, started ts, model, {"task", "steps",
        "report"}) of a subagent transcript (finished: Claude says it is)."""
        try:
            st = transcript.stat()
        except OSError:
            return "running", "starting…", None, None, None, {"task": "", "steps": [], "report": ""}
        key = str(transcript)
        old, old_detail = self.old_files.get(key), self.old_details.get(key)
        fresh = lambda rec, n: isinstance(rec, list) and len(rec) == n and rec[0] == st.st_size and rec[1] == st.st_mtime_ns
        # "running" from before it finished (or from an older copy of this
        # script, which took an agent that died on an API error for one at
        # work) is read again once
        if fresh(old, 7) and fresh(old_detail, 3) and not (finished and old[2] == "running"):
            self.files[key], self.details[key] = old, old_detail
            return (*old[2:], old_detail[2])
        status, activity, ts, model, detail = agent_progress(transcript, finished)
        if model is None and old and len(old) == 7:
            model = old[6]  # its newest entries are tool results; the model came earlier
        started = old[5] if old and len(old) == 7 and old[5] is not None else agent_started(transcript)
        known = old_detail[2] if isinstance(old_detail, list) and len(old_detail) == 3 and isinstance(old_detail[2], dict) else {}
        # read again while empty: the first look may come before its first prompt is written
        task = known["task"] if isinstance(known.get("task"), str) and known["task"] else \
            tidy_text(plain_text(agent_task(transcript)), AGENT_TASK_CHARS)
        detail = {"task": task, **detail}
        entry = [st.st_size, st.st_mtime_ns, status, activity, ts, started, model]
        self.changed = self.changed or entry != old
        self.files[key], self.details[key] = entry, [st.st_size, st.st_mtime_ns, detail]
        self.details_changed = True
        return status, activity, ts, started, model, detail

    def parent(self, agent_dir, agent_id, tool_use_id):
        """Which other agent of the session started this one (nested agents), if any."""
        if agent_id in self.old_parents:
            self.parents[agent_id] = self.old_parents[agent_id]
            return self.parents[agent_id]
        now = time.time()
        if 0 <= now - self.misses.get(agent_id, 0) < self.PARENT_RETRY_S:
            return None
        needle = f'"{tool_use_id}"'.encode()
        for other in agent_dir.glob("agent-*.jsonl"):
            other_id = other.name[len("agent-"):-len(".jsonl")]
            if other_id == agent_id:
                continue
            try:
                if needle in other.read_bytes():
                    self.parents[agent_id] = other_id
                    self.misses.pop(agent_id, None)
                    self.changed = True
                    return other_id
            except OSError:
                continue
        self.misses[agent_id] = int(now)
        self.changed = True
        return None

    def session_agents(self, profile, session_id, alive, since=None):
        """Subagents of one session as counts plus a display-ordered tree, or
        None. since: when the session's process started (ms), if it runs."""
        if not session_id or "/" in session_id:
            return None
        agents = []
        for agent_dir in (profile.path / "projects").glob(f"*/{session_id}/subagents"):
            for meta_path in agent_dir.glob("agent-*.meta.json"):
                meta = read_json(meta_path)
                if not isinstance(meta, dict):
                    continue
                agent_id = meta_path.name[len("agent-"):-len(".meta.json")]
                status, activity, ts, started, model, detail = self.progress(agent_dir / f"agent-{agent_id}.jsonl",
                                                                              meta.get("finished") is True)
                # its session ended before it finished, or the process that ran
                # it did (a resumed chat keeps its id, and its agents' folder)
                if status == "running" and (not alive or (since and ts is not None and ts < since)):
                    status = "stopped"
                depth = meta.get("spawnDepth") if isinstance(meta.get("spawnDepth"), int) else 1
                parent = None
                if depth > 1 and isinstance(meta.get("toolUseId"), str):
                    parent = self.parent(agent_dir, agent_id, meta["toolUseId"])
                if started is None:
                    try:
                        started = int(meta_path.stat().st_mtime * 1000)
                    except OSError:
                        pass
                agents.append({
                    "id": agent_id,
                    "parent": parent,
                    "type": str(meta.get("agentType") or "agent"),
                    "description": short_text(meta.get("description") or "", 80),
                    "background": meta.get("requestShape") == "background",
                    "status": status,
                    "activity": activity,
                    "started": started,
                    "updated": ts,
                    "model": model,  # e.g. "Haiku 4.5", from its replies
                    "task": detail["task"],  # what it was asked to do
                    "steps": detail["steps"],  # its last tool calls, oldest first
                    "report": detail["report"] if status == "done" else "",  # what it handed back
                    "toolCalls": None,  # how many tool calls and tokens so far (finish_row)
                    "tokens": None,
                })
        if not agents:
            return None
        counts = {k: sum(a["status"] == k for a in agents) for k in ("running", "done", "stopped", "failed")}
        # Display order: depth-first from the session's own agents, oldest first.
        children = {}
        ids = {a["id"] for a in agents}
        for a in sorted(agents, key=lambda a: (a["started"] or 0, a["id"])):
            children.setdefault(a["parent"] if a["parent"] in ids else None, []).append(a)
        tree = []

        def walk(parent, depth):
            for a in children.get(parent, []):
                tree.append({**a, "depth": depth})
                walk(a["id"], depth + 1)
        walk(None, 0)
        if len(tree) > AGENT_TREE_LIMIT:  # keep every running one, then the newest
            keep = {a["id"] for a in tree if a["status"] == "running"}
            for a in sorted(tree, key=lambda a: -(a["started"] or 0)):
                if len(keep) >= AGENT_TREE_LIMIT:
                    break
                keep.add(a["id"])
            tree = [a for a in tree if a["id"] in keep]
        return {**counts, "total": len(agents), "tree": tree}

    def save(self):
        now = time.time()
        data = {"version": AGENT_CACHE_VERSION, "files": self.files, "parents": self.parents,
                "misses": {k: t for k, t in self.misses.items() if 0 <= now - t < CACHE_KEEP_S}}
        kept = keep_unused(self.old, data, ("files", "parents"), now)
        if self.changed or kept or set(self.files) != set(self.old_files):
            try:
                write_json_atomic(self.path, data)
            except OSError:
                pass
        details = {"version": 1, "files": self.details}
        kept = keep_unused(self.old_details_data, details, ("files",), now)
        if self.details_changed or kept or set(self.details) != set(self.old_details):
            try:
                write_json_atomic(self.details_path, details)
            except OSError:
                pass


# ---------------------------------------------------------------- a subagent's whole run, to read
#
# Claude Code has no way to open a subagent from outside (its terminal shows
# an agent's run when you pick it with the keys, VS Code's link only opens
# chats), and a subagent isn't a chat you can resume. So the widget renders
# its transcript as Markdown: the task, every step (its text, each tool call
# with its input and the start of its result, messages the main chat sent it)
# and its report.

AGENT_ID = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
RUN_RESULT_LINES = 25
RUN_RESULT_CHARS = 2500
RUN_INPUT_LINES = 40
RUN_INPUT_CHARS = 4000
RUN_THINKING_CHARS = 2000


def fenced(text, lang=""):
    """text as a fenced code block, with a fence longer than any run of backticks in it."""
    longest = max([len(m) for m in re.findall(r"`{3,}", text)] + [2])
    mark = "`" * (longest + 1)
    return f"{mark}{lang}\n{text.rstrip()}\n{mark}"


def code_span(text):
    """text as inline code, with more backticks around it than in it."""
    text = str(text)
    ticks = "`" * (max([len(m) for m in re.findall(r"`+", text)] + [0]) + 1)
    pad = " " if text.startswith("`") or text.endswith("`") else ""
    return f"{ticks}{pad}{text}{pad}{ticks}"


FENCE_LINE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def closed_fences(markdown):
    """Claude's Markdown with a code block it left open closed at its end (a
    reply cut off mid-block), so the rest of the page stays Markdown."""
    open_fence = None
    for line in markdown.splitlines():
        m = FENCE_LINE.match(line)
        if not m:
            continue
        mark = m.group(1)
        if open_fence is None:
            open_fence = mark
        elif mark[0] == open_fence[0] and len(mark) >= len(open_fence) and not line.strip()[len(mark):].strip():
            open_fence = None
    return markdown if open_fence is None else f"{markdown}\n{open_fence}"


def clipped(text, lines, chars):
    """(the start of text: at most lines lines and chars characters, a note
    on what was left out or "")."""
    text = text.rstrip()
    all_lines = text.splitlines()
    kept = "\n".join(all_lines[:lines])[:chars].rstrip()
    if len(kept) >= len(text):
        return text, ""
    rest = len(all_lines) - len(kept.splitlines())
    return kept, (f"… {rest} more line{'s' if rest != 1 else ''}" if rest > 0 else "… cut short")


def clipped_block(text, lines, chars, lang=""):
    kept, note = clipped(text, lines, chars)
    return fenced(kept, lang) + (f"\n*{note}*" if note else "")


def quoted(text):
    return "\n".join("> " + line if line.strip() else ">" for line in text.strip().splitlines())


def clock(ms, with_day=False):
    if ms is None:
        return ""
    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M" if with_day else "%H:%M:%S")


def spoken_duration(ms):
    """2h 5m, 3m 12s, 40s"""
    s = max(0, int(ms // 1000))
    if s >= 3600:
        return f"{s // 3600}h {s % 3600 // 60}m"
    return f"{s // 60}m {s % 60}s" if s >= 60 else f"{s}s"


def token_count(n):
    """45.2k, 1.3M (by what it rounds to: 999,960 is 1.0M, not 1000.0k)"""
    return f"{n / 1e6:.1f}M" if n >= 999_950 else f"{n / 1e3:.1f}k" if n >= 1e3 else str(n)


def tool_call_md(block):
    """A tool call: its name and what it was asked, in Markdown."""
    name = block.get("name") or "tool"
    inp = block.get("input") if isinstance(block.get("input"), dict) else {}
    shown = name.split("__", 2)[-1] if name.startswith("mcp__") else name
    head = f"**▸ {shown}**"
    if name == "Bash":
        desc = f" · {inp['description']}" if isinstance(inp.get("description"), str) else ""
        return f"{head}{desc}\n\n" + clipped_block(str(inp.get("command", "")), RUN_INPUT_LINES, RUN_INPUT_CHARS, "bash")
    path = next((inp[k] for k in ("file_path", "notebook_path") if isinstance(inp.get(k), str)), None)
    if name in ("Edit", "MultiEdit") and path:
        edits = inp.get("edits") if isinstance(inp.get("edits"), list) else [inp]
        diff = "\n\n".join(
            "\n".join(["- " + l for l in str(e.get("old_string", "")).splitlines()]
                      + ["+ " + l for l in str(e.get("new_string", "")).splitlines()])
            for e in edits if isinstance(e, dict))
        return f"{head} {code_span(path)}\n\n" + clipped_block(diff, RUN_INPUT_LINES, RUN_INPUT_CHARS, "diff")
    if name == "Write" and path:
        return f"{head} {code_span(path)}\n\n" + clipped_block(str(inp.get("content", "")), RUN_INPUT_LINES, RUN_INPUT_CHARS)
    if name == "Agent":
        what = " · ".join(str(inp[k]) for k in ("subagent_type", "description") if isinstance(inp.get(k), str))
        prompt = clipped(str(inp.get("prompt", "")), RUN_INPUT_LINES, RUN_INPUT_CHARS)
        return f"{head}{' · ' + what if what else ''}\n\n" + quoted(prompt[0] + (f"\n\n*{prompt[1]}*" if prompt[1] else ""))
    if path:
        return f"{head} {code_span(path)}"
    simple = {k: v for k, v in inp.items() if isinstance(v, (str, int, float, bool))}
    if len(simple) == len(inp) and len(inp) <= 3 and all(len(str(v)) <= 120 and "\n" not in str(v) for v in inp.values()):
        return head + "".join(f" · {k}: {code_span(v)}" for k, v in inp.items())
    return f"{head}\n\n" + clipped_block(json.dumps(inp, indent=2, ensure_ascii=False), RUN_INPUT_LINES, RUN_INPUT_CHARS, "json")


def tool_result_md(block):
    """A tool's result (the start of it), in Markdown."""
    content = block.get("content")
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict) and c.get("type") == "text" and isinstance(c.get("text"), str):
                parts.append(c["text"])
            elif isinstance(c, dict) and c.get("type") == "image":
                parts.append("(an image)")
        content = "\n".join(parts)
    text = content if isinstance(content, str) else ""
    label = "Error" if block.get("is_error") else "Result"
    if not text.strip():
        return f"*{label}: nothing*"
    return f"*{label}:*\n\n" + clipped_block(text, RUN_RESULT_LINES, RUN_RESULT_CHARS)


def agent_run_markdown(path, meta, parent_name="", cwd="", home=None):
    """(title, Markdown) of a subagent's whole run, from its transcript."""
    status, activity, last_ts, recent, report = agent_status(path, meta.get("finished") is True)
    title = short_text(meta.get("description") or meta.get("agentType") or "Subagent", 80)
    steps, task, tools, started, model = [], None, 0, None, transcript_model(recent)
    tokens = new_stats()
    try:
        f = open(path, "rb")
    except OSError:
        return title, f"# {title}\n\nIts transcript can't be read."
    with f:
        for line in f:
            if not (USER_LINE.search(line) or ASSISTANT_LINE.search(line)):
                continue
            try:
                e = json.loads(line)
            except (ValueError, RecursionError):
                continue
            if not isinstance(e, dict) or e.get("type") not in ("user", "assistant"):
                continue
            if task is None and e["type"] == "assistant":
                continue  # a fork's copy of the call that started it
            fold_stats(tokens, e)
            ts = to_ms(e.get("timestamp"))
            started = started if started is not None else ts
            msg, blocks = blocks_of(e)
            if e["type"] == "user":
                if task is None:  # its first prompt: the task
                    task = message_text(msg)
                    if FORK_BOILERPLATE_END in task:
                        task = re.sub(r"^\s*Your directive:\s*", "", task.split(FORK_BOILERPLATE_END, 1)[1])
                    continue
                for c in blocks:
                    if c.get("type") == "tool_result":
                        steps.append(tool_result_md(c))
                text = message_text(msg).strip()
                origin = e.get("origin") if isinstance(e.get("origin"), dict) else {}
                if text and (origin.get("kind") == "coordinator" or not (e.get("isMeta") or text.startswith("<"))):
                    steps.append(f"**{clock(ts)} · Message from the main chat**\n\n" + quoted(text))
                continue
            for c in blocks:
                kind = c.get("type")
                if kind == "text" and isinstance(c.get("text"), str) and c["text"].strip():
                    steps.append(f"**{clock(ts)} · Claude**\n\n{closed_fences(c['text'].strip())}")
                elif kind == "thinking" and isinstance(c.get("thinking"), str) and c["thinking"].strip():
                    thought, note = clipped(c["thinking"], 10 ** 6, RUN_THINKING_CHARS)
                    steps.append(quoted(f"*Thinking:* {thought}" + (f" *{note}*" if note else "")))
                elif kind == "tool_use" and c.get("name") != "SubagentHandback":
                    tools += 1
                    steps.append(f"{clock(ts)} " + tool_call_md(c))
    summary = stats_summary(tokens)
    facts = [f"{meta.get('agentType') or 'agent'} agent"]
    if model:
        facts.append(model)
    if meta.get("requestShape") == "background":
        facts.append("in the background")
    if status == "done":
        facts.append(f"done after {spoken_duration((last_ts or 0) - (started or 0))}" if started and last_ts else "done")
    elif status == "failed":
        facts.append(f"failed: {activity}")
    elif status == "stopped":
        facts.append("stopped")
    else:
        facts.append(f"not finished · last step: {activity}" if activity else "not finished")
    facts.append(f"{tools} tool call{'s' if tools != 1 else ''}")
    if summary and summary["tokens"]["total"]:
        facts.append(f"{token_count(summary['tokens']['total'])} tokens")
    where = [f"A subagent of “{parent_name}”" if parent_name else "A subagent"]
    if cwd:
        where.append(f"in {short_path(cwd, home) if home else cwd}")
    if started:
        where.append(f"started {clock(started, with_day=True)}")
    out = [f"# {title}", " · ".join(facts), " · ".join(where),
           "## Task", (task or "").strip() or "*(none recorded)*", "## Steps"]
    out += steps or ["*None yet.*"]
    out.append("## Report")
    if status == "done":
        out.append(closed_fences(report.strip()) or "*It finished without a report.*")
    elif status in ("failed", "stopped"):
        out.append("*None: it " + ("ended on an error" if status == "failed" else "was interrupted") + " before it had one.*")
    else:
        out.append(f"*None yet: it hadn't finished at {clock(int(time.time() * 1000))} (or its chat stopped it). "
                   "Open it again for what it has done since.*")
    out.append(f"---\n*Transcript: {code_span(path)}*")
    return title, "\n\n".join(part for part in out if part) + "\n"


def find_agent_transcript(profiles, chat_id, agent_id, profile_key=None):
    """(profile, transcript) of a chat's subagent, or (None, None)."""
    if not (isinstance(chat_id, str) and AGENT_ID.match(chat_id) and isinstance(agent_id, str) and AGENT_ID.match(agent_id)):
        return None, None
    for p in sorted(profiles, key=lambda p: p.key != profile_key):
        for path in p.path.glob(f"projects/*/{chat_id}/subagents/agent-{agent_id}.jsonl"):
            return p, path
    return None, None


def agent_run(home, extra_dirs, chat_id, agent_id, profile_key=None):
    """(ok, message, title, Markdown) of a chat's subagent (agent_run_markdown)."""
    profiles = discover_profiles(home, extra_dirs)
    profile, path = find_agent_transcript(profiles, chat_id, agent_id, profile_key)
    if path is None:
        return False, "Can't find that subagent's transcript", None, None
    meta = read_json(path.with_name(f"agent-{agent_id}.meta.json"))
    parent = path.parent.parent.parent / f"{chat_id}.jsonl"
    try:
        name, cwd, _ = read_chat_info(parent, parent.stat().st_size)
    except OSError:
        name, cwd = "", ""
    title, markdown = agent_run_markdown(path, meta if isinstance(meta, dict) else {}, name, cwd, home)
    return True, f"The run of “{title}”", title, markdown


# ---------------------------------------------------------------- what a chat is doing, and what it changed
#
# A peek at a chat without switching to it, from the end of its transcript:
# its newest step (a tool call, thinking, writing), your last prompt and
# Claude's last reply. Each content block of a reply is an entry of its own,
# all with the reply's message id. Also from there (as Claude Code 2.1.304
# writes them):
#   - Claude's recap of the chat: a `system` record of subtype `away_summary`,
#     written when you come back to a chat after a while ("You asked …; Next
#     step: …"; /config turns them off). It counts while nothing was said
#     after it.
#   - the permission mode (default, plan, auto, acceptEdits, …): the newest
#     `permission-mode` record, or the one your last prompt carries.
#   - whether ultracode is on (2.1.312: /effort's ultracode, /ultracode on):
#     the newest `attachment` record of type ultra_effort_enter (on) or
#     ultra_effort_exit (off), which Claude adds with your next prompt.
#   - the chat's slug: its plan, if it made one, is <cfg>/plans/<slug>.md.
#   - what stopped it: a reply that is an API error saying a usage limit was
#     hit ("You've hit your session limit · resets 7:10pm (Europe/Berlin)",
#     the limit named as Claude names each plan window) or the login expired.
#
# The files it changed: before a chat first edits a file, Claude backs it up
# as <cfg>/file-history/<session id>/<name>@v<n> and records that in the
# transcript (a `file-history-delta`, or in older versions a
# `file-history-snapshot` update); a backup name of null means the file
# didn't exist yet. Each of your prompts gets a `file-history-snapshot` with
# every tracked file's backup as of that prompt, which is where the last turn
# started. Changes made with Bash (sed, scripts) aren't tracked, and a file a
# chat edited with no backup on record (e.g. in a subagent) is compared with
# git's HEAD (jump.py --changes).

PEEK_TAIL_BYTES = 262144
PEEK_TAIL_MAX = 4 << 20  # the last lines can be big tool results
PEEK_REPLY_CHARS = 1500
PEEK_PROMPT_CHARS = 300
PEEK_LINE = re.compile(rb'"type":\s*"(?:user|assistant|last-prompt)"')
PEEK_MORE_LINE = re.compile(rb'"type":\s*"(?:user|assistant|last-prompt|system|permission-mode)"')
ULTRA_LINE = re.compile(rb'"type":\s*"ultra_effort_(?:enter|exit)"')  # (of all attachments, only these are read)
PEEK_ADDED = ("recap", "mode", "slug", "stopped", "ultracode", "model")  # a cached peek without them (an older copy's) is read again
RECAP_NOTE = re.compile(r"\s*\(disable recaps in /config\)\s*$")
# Claude's names for the plan windows in "You've hit your … limit" (its
# rate-limit types: five_hour is the session limit, the 5-hour limit since
# Claude Code 2.1.312)
LIMIT_NAMES = (("session limit", "five_hour"), ("5-hour limit", "five_hour"), ("weekly limit", "seven_day"),
               ("Opus limit", "seven_day_opus"), ("Sonnet limit", "seven_day_sonnet"),
               ("Fable limit", "seven_day_overage_included"))
LIMIT_STARTS = ("You've hit your ", "You've reached your ")
OUT_OF_USAGE = ("You're out of usage credits", "Your org is out of usage")
LOGIN_ENDED = ("Login expired", "OAuth token revoked", "Anthropic profile login expired")
PLAN_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")  # a plan's file name (<slug>.md)
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
EDIT_LINE = re.compile(rb'"name":\s*"(?:Edit|Write|MultiEdit|NotebookEdit)"')
SESSION_ID_FIELD = re.compile(rb'"sessionId":\s*"([0-9A-Za-z_-]{1,80})"')
CHANGES_LISTED = 12  # file names a row carries (its tooltip lists them)
CHAT_CACHE_VERSION = 1  # its records got "stats" without a new version (older copies keep them); one without is read again
USER_LINE = re.compile(rb'"type":\s*"user"')
ASSISTANT_LINE = re.compile(rb'"type":\s*"assistant"')


def message_text(msg):
    """The text of a transcript message: a string, or its text blocks."""
    content = msg.get("content") if isinstance(msg, dict) else None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(c["text"] for c in content
                         if isinstance(c, dict) and c.get("type") == "text" and isinstance(c.get("text"), str))
    return ""


def human_prompt(e):
    """What you typed, if this transcript entry is a prompt of yours (not a
    tool result, a command's output or a note of Claude Code's own)."""
    if e.get("type") != "user" or e.get("isMeta") or e.get("isCompactSummary") or e.get("isSidechain"):
        return None
    msg = e.get("message") if isinstance(e.get("message"), dict) else {}
    if isinstance(msg.get("content"), list) and any(
            isinstance(c, dict) and c.get("type") == "tool_result" for c in msg["content"]):
        return None
    text = message_text(msg).strip()
    if not text or text.startswith("<") or text.startswith("[Request interrupted"):
        return None
    return text


def blocks_of(e):
    msg = e.get("message") if isinstance(e.get("message"), dict) else {}
    content = msg.get("content")
    return msg, [c for c in content if isinstance(c, dict)] if isinstance(content, list) else []


def tail_entries(path, size, nbytes, more=False):
    """Conversation entries (and last-prompt records) from the last nbytes
    of a transcript, newest first; more: system and permission-mode records
    too, and ultracode's attachments."""
    try:
        with open(path, "rb") as f:
            f.seek(max(0, size - nbytes))
            lines = f.read(min(size, nbytes)).splitlines()
    except OSError:
        return []
    if size > nbytes:
        lines = lines[1:]  # probably cut in the middle
    pattern = PEEK_MORE_LINE if more else PEEK_LINE
    kinds = ("user", "assistant", "last-prompt") + (("system", "permission-mode", "attachment") if more else ())
    entries = []
    for line in reversed(lines):
        if not pattern.search(line) and not (more and ULTRA_LINE.search(line)):
            continue
        try:
            e = json.loads(line)
        except (ValueError, RecursionError):
            continue
        if isinstance(e, dict) and e.get("type") in kinds:
            entries.append(e)
    return entries


def step_text(convo):
    """What the chat is doing, from its newest entry: "Bash: npm test",
    "thinking…", "writing…"; "" once its reply is finished."""
    newest = convo[0]
    msg, blocks = blocks_of(newest)
    if newest["type"] == "user":
        if human_prompt(newest) is None:  # tool results came back: what it ran
            prev = next((e for e in convo[1:] if e["type"] == "assistant"), None)
            uses = [c for c in blocks_of(prev)[1] if c.get("type") == "tool_use"] if prev else []
            if uses:
                return f"{describe_tool(uses[-1])} (thinking about the result)"
        return "thinking…"
    uses = [c for c in blocks if c.get("type") == "tool_use"]
    if uses:
        return describe_tool(uses[-1])
    if isinstance(msg.get("stop_reason"), str):
        return ""
    return "writing…" if any(c.get("type") == "text" for c in blocks) else "thinking…"


MARKDOWN_EMPHASIS = re.compile(r"(\*\*|__|`)(.+?)\1")


def plain_text(markdown):
    """Claude's markdown, readable as plain text: no heading marks, code
    fences or emphasis markers; bullets as •."""
    out = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            continue
        line = re.sub(r"^(\s*)#{1,6}\s+", r"\1", line)
        line = re.sub(r"^(\s*)[-*]\s+", r"\1• ", line)
        out.append(MARKDOWN_EMPHASIS.sub(r"\2", line))
    return "\n".join(out)


def tidy_text(text, limit):
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(line.rstrip() for line in text.strip().splitlines()))
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def peek_from(entries):
    """(peek, whether it's complete) from transcript entries, newest first:
    complete once your last prompt is among them, or Claude's reply since it
    plus the last-prompt record."""
    convo = [e for e in entries if e["type"] in ("user", "assistant") and not e.get("isSidechain")]
    last_prompt = next((e["lastPrompt"] for e in entries
                        if e["type"] == "last-prompt" and isinstance(e.get("lastPrompt"), str)), "")
    reply_id, parts, prompt = None, [], None
    for e in convo:
        prompt = human_prompt(e)
        if prompt is not None:
            break
        if e["type"] != "assistant":
            continue
        msg, blocks = blocks_of(e)
        texts = [c["text"] for c in blocks
                 if c.get("type") == "text" and isinstance(c.get("text"), str) and c["text"].strip()]
        if not texts:
            continue
        mid = msg.get("id") if isinstance(msg.get("id"), str) else id(e)
        if reply_id is None:
            reply_id = mid
        if mid == reply_id:
            parts[:0] = texts  # older blocks of the same reply come first
    reply = tidy_text(plain_text("\n\n".join(parts)), PEEK_REPLY_CHARS)
    asked = prompt if prompt is not None else last_prompt
    # The newest turn: a prompt of yours or a reply (not tool results or notes)
    turn = next((e for e in convo if e["type"] == "assistant" or human_prompt(e) is not None), None)
    peek = {
        "activity": step_text(convo) if convo else "",
        "prompt": short_text(asked, PEEK_PROMPT_CHARS) if asked.strip() else "",
        "reply": reply,
        "replyLine": report_line(reply, 160) if reply else "",
        "at": to_ms(convo[0].get("timestamp")) if convo else None,
        "recap": recap_of(entries),
        "mode": mode_of(entries),
        "ultracode": ultracode_of(entries),
        "slug": next((e["slug"] for e in entries if isinstance(e.get("slug"), str) and PLAN_SLUG.match(e["slug"])), None),
        "stopped": stopped_by(turn) if turn is not None else None,
        "model": transcript_model(convo),
    }
    return peek, prompt is not None or (bool(parts) and bool(last_prompt))


def names_mode(e):
    """The permission mode an entry names: a mode change, or an entry of
    yours (a prompt, also one VS Code's panel begins with a note of the file
    open there), or None."""
    if e.get("type") not in ("permission-mode", "user") or e.get("isSidechain") or e.get("isMeta"):
        return None
    mode = e.get("permissionMode")
    return mode if isinstance(mode, str) and mode else None


def mode_of(entries):
    """The chat's permission mode (newest first entries), e.g. "plan", or None."""
    return next((m for m in map(names_mode, entries) if m), None)


def ultracode_of(entries):
    """Whether ultracode is on in the chat (newest first entries), as Claude
    noted it with your last prompt since it changed."""
    for e in entries:
        kind = e.get("attachment").get("type") if e["type"] == "attachment" and isinstance(e.get("attachment"), dict) else None
        if kind in ("ultra_effort_enter", "ultra_effort_exit"):
            return kind == "ultra_effort_enter"
    return False


def recap_of(entries):
    """{"text", "at"} of Claude's recap of the chat (newest first entries), if
    nothing was said after it: a prompt of yours or a reply makes it old."""
    for e in entries:
        if e["type"] == "system" and e.get("subtype") == "away_summary":
            text = RECAP_NOTE.sub("", e["content"]).strip() if isinstance(e.get("content"), str) else ""
            return {"text": tidy_text(text, PEEK_REPLY_CHARS), "at": to_ms(e.get("timestamp"))} if text else None
        if (e["type"] == "assistant" and not e.get("isSidechain")) or human_prompt(e) is not None:
            return None
    return None


def stopped_by(e):
    """What stopped a chat whose newest turn is the entry e: {"kind": "limit"
    (a usage limit; window: the plan window, e.g. "five_hour", if Claude
    named it) or "login" (it expired), "text": Claude's message, "at", and
    "resets": when that limit resets, if Claude noted it}, or None."""
    if e.get("type") != "assistant" or e.get("isApiErrorMessage") is not True:
        return None
    text = " ".join(message_text(e.get("message")).split())
    kind, window = None, None
    start = next((s for s in LIMIT_STARTS if text.startswith(s)), None)
    if start is not None:
        rest = text[len(start):]
        kind, window = "limit", next((w for name, w in LIMIT_NAMES if rest.startswith(name)), None)
    elif text.startswith(OUT_OF_USAGE):
        kind = "limit"
    elif text.startswith(LOGIN_ENDED):
        kind = "login"
    if kind is None:
        return None
    stop = {"kind": kind, "window": window, "text": short_text(text, 160), "at": to_ms(e.get("timestamp"))}
    # (the error notes the account's limit it hit: its rate-limit type and when it resets)
    quota = e.get("quotaLimits") if kind == "limit" and isinstance(e.get("quotaLimits"), dict) else {}
    if window is None and quota.get("rateLimitType") in {w for _, w in LIMIT_NAMES}:
        stop["window"] = quota["rateLimitType"]
    resets = to_ms(quota.get("resetsAt"))
    if resets:
        stop["resets"] = resets
    return stop


def chat_peek(path):
    """{"activity", "prompt", "reply", "replyLine", "at", "recap", "mode", "ultracode",
    "slug", "stopped", "model"} of a chat, read from the end of its transcript (more
    of it while that isn't enough)."""
    try:
        size = path.stat().st_size
    except (OSError, AttributeError):
        return None
    nbytes = PEEK_TAIL_BYTES
    while True:
        peek, complete = peek_from(tail_entries(path, size, nbytes, more=True))
        if complete or nbytes >= size or nbytes >= PEEK_TAIL_MAX:
            return peek
        nbytes *= 4


def new_edits():
    """What a chat changed so far (fold_edits):
    files: {path: [backup name, version]} with each file's first backup; the
        name is None for a file the chat created, False when no backup is on
        record (an edit tool call is all there is);
    snap: id of your newest prompt's snapshot; snapFiles: {path: backup name}
        as of that prompt; turn: {path: backup name} of files first backed up
        since then;
    sessions: session ids whose file-history folders hold its backups;
    stats: what the chat did (fold_stats);
    mode: its permission mode, the newest one named (fold_mode);
    ultra: whether ultracode is on, as the newest note of it says (fold_ultra; None: none)."""
    return {"files": {}, "snap": None, "snapFiles": {}, "turn": {}, "sessions": [], "stats": new_stats(), "mode": None,
            "ultra": None}


def new_stats():
    """A chat's numbers so far: your prompts, its tool calls by name, tokens
    [input, output, cacheRead, cacheWrite] (cur: the reply being read, whose
    blocks repeat its usage), first and last entry (ms), and how long Claude
    worked: each turn from your prompt to its last step (busyMs, plus the turn
    open now: turnStart … turnLast)."""
    return {"prompts": 0, "tools": {}, "tokens": [0, 0, 0, 0], "cur": None, "first": None, "last": None,
            "busyMs": 0, "turnStart": None, "turnLast": None, "started": False}


def fold_stats(st, e):
    """Fold one transcript entry into a chat's numbers (new_stats). What
    comes before its first user entry isn't its own: a fork starts with a
    copy of the call that started it (the parent's reply, usage and all)."""
    if not st.get("started", True):  # (numbers kept from before this rule: started)
        if e.get("type") != "user":
            return
        st["started"] = True
    ts = to_ms(e.get("timestamp"))
    if ts is not None:
        st["first"] = ts if st["first"] is None else min(st["first"], ts)
        st["last"] = ts if st["last"] is None else max(st["last"], ts)
    if human_prompt(e) is not None:
        st["prompts"] += 1
        if st["turnStart"] is not None and st["turnLast"] is not None and st["turnLast"] > st["turnStart"]:
            st["busyMs"] += st["turnLast"] - st["turnStart"]
        st["turnStart"], st["turnLast"] = ts, None
        return
    if e.get("type") != "assistant":
        return
    msg, blocks = blocks_of(e)
    if ts is not None and st["turnStart"] is not None:
        st["turnLast"] = ts
    for c in blocks:
        if c.get("type") == "tool_use" and isinstance(c.get("name"), str):
            name = c["name"].split("__")[-1] if c["name"].startswith("mcp__") else c["name"]
            st["tools"][name] = st["tools"].get(name, 0) + 1
    u = msg.get("usage")
    if not isinstance(u, dict):
        return
    vals = [int(number(u.get(k)) or 0) for k in (
        "input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")]
    mid = msg.get("id") or e.get("requestId") or e.get("uuid")
    if st["cur"] and st["cur"][0] == mid:
        st["cur"] = [mid] + [max(a, b) for a, b in zip(st["cur"][1:], vals)]
    else:
        if st["cur"]:
            st["tokens"] = [a + b for a, b in zip(st["tokens"], st["cur"][1:])]
        st["cur"] = [mid] + vals


def stats_summary(main, others=()):
    """A chat's recap, for its row: {"prompts", "toolCalls", "tools": [[name,
    count]] most used first, "tokens": {"input", "output", "cacheRead",
    "cacheWrite", "total"}, "workedMs", "startedAt", "lastAt"}; its subagents'
    (others) tool calls and tokens included."""
    tokens, tools = [0, 0, 0, 0], {}
    for st in (main,) + tuple(others):
        cur = st["cur"][1:] if st.get("cur") else [0, 0, 0, 0]
        tokens = [a + b + c for a, b, c in zip(tokens, st["tokens"], cur)]
        for name, n in st["tools"].items():
            tools[name] = tools.get(name, 0) + n
    worked = main["busyMs"]
    if main["turnStart"] is not None and main["turnLast"] is not None and main["turnLast"] > main["turnStart"]:
        worked += main["turnLast"] - main["turnStart"]
    if not (main["prompts"] or sum(tokens) or tools):
        return None
    keys = ("input", "output", "cacheRead", "cacheWrite")
    return {
        "prompts": main["prompts"],
        "toolCalls": sum(tools.values()),
        "tools": sorted(([n, c] for n, c in tools.items()), key=lambda nc: (-nc[1], nc[0]))[:5],
        "tokens": dict(zip(keys, tokens), total=sum(tokens)),
        "workedMs": worked,
        "startedAt": main["first"],
        "lastAt": main["last"],
    }


def backup_target(key, backup):
    """The file a backup record is about (absolute, or relative to the chat's folder)."""
    if not isinstance(key, str) or not key:
        return None
    parent = backup.get("realParentDir") if isinstance(backup, dict) else None
    if isinstance(parent, str) and parent.startswith("/"):
        return os.path.join(parent, os.path.basename(key))
    return key


def backup_name(backup):
    name = backup.get("backupFileName") if isinstance(backup, dict) else None
    return name if isinstance(name, str) and valid_id(name) else None


def note_backup(rec, path, backup):
    version = backup.get("version") if isinstance(backup, dict) and isinstance(backup.get("version"), int) else 0
    first = rec["files"].get(path)
    if first is None or first[0] is False or version < first[1]:
        rec["files"][path] = [backup_name(backup), version]


def fold_edits(rec, e):
    """Fold one transcript entry into rec (new_edits)."""
    kind = e.get("type")
    if kind == "file-history-snapshot":
        snap = e.get("snapshot") if isinstance(e.get("snapshot"), dict) else {}
        tracked = snap.get("trackedFileBackups") if isinstance(snap.get("trackedFileBackups"), dict) else {}
        found = {}
        for key, backup in tracked.items():
            path = backup_target(key, backup)
            if path:
                found[path] = backup
        mid = e.get("messageId") or snap.get("messageId")
        if not e.get("isSnapshotUpdate"):
            rec["snap"], rec["snapFiles"], rec["turn"] = mid, {p: backup_name(b) for p, b in found.items()}, {}
        elif mid == rec["snap"]:
            for path, backup in found.items():
                if path not in rec["snapFiles"] and path not in rec["turn"]:
                    rec["turn"][path] = backup_name(backup)
        for path, backup in found.items():
            note_backup(rec, path, backup)
    elif kind == "file-history-delta":
        path = backup_target(e.get("trackingPath"), e.get("backup"))
        if path:
            if rec["snap"] is not None and e.get("snapshotMessageId") == rec["snap"] and path not in rec["turn"]:
                rec["turn"][path] = backup_name(e.get("backup"))
            note_backup(rec, path, e.get("backup"))
    elif kind == "assistant":
        for c in blocks_of(e)[1]:
            if c.get("type") == "tool_use" and c.get("name") in EDIT_TOOLS and isinstance(c.get("input"), dict):
                path = c["input"].get("file_path") or c["input"].get("notebook_path")
                if isinstance(path, str) and path.startswith("/"):
                    rec["files"].setdefault(os.path.normpath(path), [False, 0])


def fold_mode(rec, e):
    """The permission mode an entry names (names_mode; a chat in VS Code's
    Claude Code panel names it at its first prompt only)."""
    mode = names_mode(e)
    if mode:
        rec["mode"] = mode


def fold_ultra(rec, e):
    """Whether ultracode is on, if the entry notes it (ultracode_of; Claude
    notes it again only every few prompts, so the end of a transcript may not)."""
    kind = e["attachment"].get("type") if e.get("type") == "attachment" and isinstance(e.get("attachment"), dict) else None
    if kind in ("ultra_effort_enter", "ultra_effort_exit"):
        rec["ultra"] = kind == "ultra_effort_enter"


def scan_mode(path, end):
    """The newest permission mode the transcript names up to byte offset end, or None."""
    return scan_named(path, end)["mode"]


def scan_named(path, end):
    """{"mode", "ultra"}: the newest permission mode and ultracode note the
    transcript has up to byte offset end (fold_mode, fold_ultra; None: none)."""
    rec = {"mode": None, "ultra": None}
    try:
        with open(path, "rb") as f:
            read = 0
            for line in f:
                read += len(line)
                if read > end:
                    break
                mode, ultra = b'"permissionMode"' in line, ULTRA_LINE.search(line)
                if mode or ultra:
                    try:
                        e = json.loads(line)
                    except (ValueError, RecursionError):
                        continue
                    if isinstance(e, dict):
                        fold_mode(rec, e)
                        fold_ultra(rec, e)
    except OSError:
        pass
    return rec


def scan_edits(path, rec, start=0, sessions=None):
    """Fold the transcript's lines from byte offset start into rec; returns
    the offset read up to (a half-written last line is left for next time).
    With a sessions set, the session ids its entries name are added to it."""
    offset = start
    try:
        with open(path, "rb") as f:
            f.seek(start)
            for line in f:
                if not line.endswith(b"\n"):
                    break
                if sessions is not None:
                    m = SESSION_ID_FIELD.search(line)
                    if m:
                        sessions.add(m.group(1).decode())
                edits = b'"file-history-' in line or EDIT_LINE.search(line)
                talk = ASSISTANT_LINE.search(line) or (USER_LINE.search(line) and b'"tool_result"' not in line)
                mode = b'"permissionMode"' in line
                ultra = ULTRA_LINE.search(line)
                if not talk and not rec["stats"].get("started", True) and USER_LINE.search(line):
                    rec["stats"]["started"] = True  # a fork's first entry: tool results, then its directive
                if edits or talk or mode or ultra:
                    try:
                        e = json.loads(line)
                    except (ValueError, RecursionError):
                        e = None
                    if isinstance(e, dict):
                        if edits:
                            fold_edits(rec, e)
                        if edits or talk:
                            fold_stats(rec["stats"], e)
                        if mode:
                            fold_mode(rec, e)
                        if ultra:
                            fold_ultra(rec, e)
                offset += len(line)
    except OSError:
        pass
    return offset


def merge_edits(rec, other):
    """Add the files another transcript (a subagent's) changed to rec's."""
    for path, first in other["files"].items():
        mine = rec["files"].get(path)
        if mine is None or (mine[0] is False and first[0] is not False):
            rec["files"][path] = list(first)


def subagent_transcripts(path):
    """A chat's subagent transcripts: projects/<proj>/<id>/subagents/agent-*.jsonl."""
    try:
        return sorted((path.parent / path.stem / "subagents").glob("agent-*.jsonl"))
    except OSError:
        return []


def chat_edits(path):
    """Everything a chat changed (new_edits), subagents included, read in full."""
    rec, sessions = new_edits(), {path.stem}
    scan_edits(path, rec, 0, sessions)
    for sub in subagent_transcripts(path):
        other = new_edits()
        scan_edits(sub, other)
        merge_edits(rec, other)
    rec["sessions"] = sorted(s for s in sessions if valid_id(s))
    return rec


def file_label(path, cwd, home):
    """A changed file's name as a row shows it: relative to the chat's folder, else ~/…"""
    if cwd and (path + "/").startswith(cwd.rstrip("/") + "/") and path != cwd:
        return path[len(cwd.rstrip("/")) + 1:]
    return short_path(path, home)


def absolute_path(path, cwd):
    """A path from a backup record, made absolute (they can be relative to the chat's folder)."""
    if path.startswith("/"):
        return path
    return os.path.normpath(os.path.join(cwd, path)) if cwd else None


def project_file(path, skip):
    """Is this changed file part of the chat's work, not in one of Claude's own folders (skip)?"""
    return path is not None and not any(path == s or path.startswith(s + "/") for s in skip)


def changed_paths(rec, cwd, skip):
    """The absolute paths of the files in rec, minus those in Claude's own folders."""
    return sorted({a for a in (absolute_path(p, cwd) for p in rec["files"]) if project_file(a, skip)})


TASKS_LISTED = 20


def task_number(task):
    try:
        return (0, int(task.get("id")))
    except (TypeError, ValueError):
        return (1, str(task.get("id")))


def task_progress(profiles, ids):
    """A chat's task list (Claude's TaskCreate/TaskUpdate keep it as
    <cfg>/tasks/<session id>/<n>.json), or None: {"done", "total", "current"
    (what it's on, e.g. "Running the tests"), "items": [{"subject", "status"}]},
    status being pending, in_progress or completed."""
    for sid in dict.fromkeys(i for i in ids if valid_id(i)):
        for p in profiles:
            try:
                files = sorted((p.path / "tasks" / sid).glob("*.json"))
            except OSError:
                continue
            tasks = [t for t in map(read_json, files)
                     if isinstance(t, dict) and isinstance(t.get("subject"), str) and t.get("status") != "deleted"]
            if not tasks:
                continue
            tasks.sort(key=task_number)
            current = next((t for t in tasks if t.get("status") == "in_progress"), None)
            return {
                "done": sum(t.get("status") == "completed" for t in tasks),
                "total": len(tasks),
                "current": clean_text((current.get("activeForm") or current["subject"]) if current else "", 120),
                "items": [{"subject": clean_text(t["subject"], 120), "status": str(t.get("status") or "pending")}
                          for t in tasks[:TASKS_LISTED]],
            }
    return None


def own_folders(profiles):
    """Folders a chat writes to that aren't its project: Claude's config
    folders (plans, memory) and its scratchpads (/tmp/claude-<uid>)."""
    skip = {f"/tmp/claude-{os.getuid()}"}
    for p in profiles:
        skip.update((str(p.path).rstrip("/"), str(p.real).rstrip("/")))
    return sorted(skip)


CACHE_KEEP_S = 2 * 86400  # a cache entry no copy of this script used for this long is dropped
SEEN_EVERY_S = 3600  # how often an entry's last use is written down


def keep_unused(old, new, sections, now):
    """Put the entries of the cache old that this copy didn't use into new.

    Other copies of this script share the cache file but may list other
    chats (a widget with other settings, the VS Code extension, a poll from
    another computer): when each saved only the entries it used, they kept
    reading each other's transcripts from the start. new["seen"] notes when
    each entry was last used (in whole hours or so); one that no copy used
    for CACHE_KEEP_S is dropped. Whether that changed anything to save."""
    seen_old = old.get("seen") if isinstance(old.get("seen"), dict) else {}
    seen, changed = {}, False
    for section in sections:
        old_entries = old.get(section) if isinstance(old.get(section), dict) else {}
        was = seen_old.get(section) if isinstance(seen_old.get(section), dict) else {}
        noted = seen[section] = {}
        for key in new[section]:
            t = was.get(key)
            if isinstance(t, (int, float)) and 0 <= now - t < SEEN_EVERY_S:
                noted[key] = t
            else:
                noted[key] = int(now)
                changed = True
        for key, value in old_entries.items():
            if key in new[section]:
                continue
            t = was.get(key)
            t = t if isinstance(t, (int, float)) else now  # from a copy that doesn't note it
            if now - t < CACHE_KEEP_S:
                new[section][key] = value
                noted[key] = int(t)
            else:
                changed = True
    new["seen"] = seen
    return changed


class ChatCache:
    """What the widget read from the listed chats' transcripts, kept between
    polls in chats.json: each one's peek (read again when the file changed)
    and the files it changed (only what was appended is read)."""

    def __init__(self, path):
        self.path = path
        data = read_json(path)
        ok = isinstance(data, dict) and data.get("version") == CHAT_CACHE_VERSION
        self.old = data if ok else {}
        self.data = {"version": CHAT_CACHE_VERSION, "peeks": {}, "edits": {}}
        self.changed = not ok

    def _old(self, section, key):
        return self.data[section].get(key) or self.old.get(section, {}).get(key)

    def peek(self, path):
        try:
            st = path.stat()
        except (OSError, AttributeError):
            return None
        key = file_key(st)
        old = self._old("peeks", key)
        # (an older copy of this script reads no recap, mode, slug or stop: read it again)
        if isinstance(old, list) and len(old) == 3 and old[0] == st.st_size and old[1] == st.st_mtime_ns \
                and (not isinstance(old[2], dict) or all(k in old[2] for k in PEEK_ADDED)):
            self.data["peeks"][key] = old
            return old[2]
        peek = chat_peek(path)
        self.data["peeks"][key] = [st.st_size, st.st_mtime_ns, peek]
        self.changed = True
        return peek

    def edits(self, path):
        """new_edits of one transcript, reading only what was appended since last time."""
        try:
            st = path.stat()
        except OSError:
            return new_edits()
        key = file_key(st)
        old = self._old("edits", key)
        if isinstance(old, dict) and isinstance(old.get("size"), int) and old["size"] <= st.st_size \
                and isinstance(old.get("rec"), dict) and isinstance(old["rec"].get("stats"), dict):
            size, rec = old["size"], old["rec"]
            # An older copy of this script (1.8 and before) reads on without
            # counting what "stats" counts, but keeps the key: count from
            # where it was counted last (reading the edits again is harmless)
            counted = rec.get("statsAt")
            if isinstance(counted, int) and 0 <= counted < size:
                size = counted
        else:
            size, rec = 0, new_edits()
        if "mode" not in rec or "ultra" not in rec:   # (kept by an older copy of this script: from what was read, once)
            rec = json.loads(json.dumps(rec))
            rec.update(scan_named(path, size))
            self.changed = True
        if size < st.st_size:
            rec = json.loads(json.dumps(rec))  # a copy: the old one may be kept as is
            size = scan_edits(path, rec, size)
            rec["statsAt"] = size
            self.changed = True
        self.data["edits"][key] = {"size": size, "rec": rec}
        return rec

    def stats(self, path):
        """The chat's recap (stats_summary), subagents included, or None."""
        if path is None:
            return None
        main = self.edits(path).get("stats") or new_stats()
        return stats_summary(main, [self.edits(sub).get("stats") or new_stats() for sub in subagent_transcripts(path)])

    def changed_files(self, path, cwd, skip):
        """The absolute paths of the files a chat changed, subagents included."""
        if path is None:
            return []
        rec = new_edits()
        merge_edits(rec, self.edits(path))
        for sub in subagent_transcripts(path):
            merge_edits(rec, self.edits(sub))
        return changed_paths(rec, cwd, skip)

    def changes(self, path, cwd, home, skip, paths=None):
        """{"count", "files"} of the files a chat changed (paths: changed_files,
        if known), or None."""
        paths = self.changed_files(path, cwd, skip) if paths is None else paths
        if not paths:
            return None
        labels = sorted(file_label(p, cwd, home) for p in paths)
        return {"count": len(paths), "files": labels[:CHANGES_LISTED]}

    def save(self):
        sections = ("peeks", "edits")
        kept = keep_unused(self.old, self.data, sections, time.time())
        if self.changed or kept or any(set(self.data[s]) != set(self.old.get(s, {})) for s in sections):
            try:
                write_json_atomic(self.path, self.data)
            except OSError:
                pass


# ---------------------------------------------------------------- permission prompts
#
# A chat waiting for a permission shows what it asks (the command, the file
# and the change) and, where the widget can answer, Allow once, Always allow
# and Deny. Without the hook, what it asks comes from the transcript: its
# oldest tool call without a result (pending_tool), and a chat in tmux can be
# answered with keys (pane.py --keys). With the hook (permission_hook.py,
# pane.py --relay on), each request is in the cache (permission_requests)
# and the widget's answer goes back through it (pane.py --answer).
#
# Claude's multiple-choice questions (its AskUserQuestion tool) ask for a
# permission the same way, and the hook gets them too: the chat waits for
# "input needed" then, and its "questions" can be answered through the hook
# only (an allow that carries the answers, as Claude's own dialog sends them).

DIFF_LINES = 400  # of one file's diff, in the review (and of an edit a prompt asks for)
DIFF_CHARS = 60000
DIFF_FILE_MAX = 2 << 20  # a file a prompt's change is compared with, at most (bigger: not read)
DIFF_COMPARE_LINES = 4000  # of a change, compared line by line (difflib's time grows with their square)
PERMISSIONS = "permissions"
REQUEST_MAX_AGE_MS = 86400_000
ASK_TOOL = "AskUserQuestion"
QUESTION_CHARS = 2000  # of a question, an option's label or its description
# A chat leaving plan mode (its ExitPlanMode call) asks the same way, with
# its plan: approve it (and maybe accept edits from then on) or keep
# planning, with what to change (pane.py --decision approve|approve-edits|keep;
# verified on Claude Code 2.1.311: an allow must carry the call's input, a
# setMode in updatedPermissions sets the mode, a deny's message is the feedback)
PLAN_TOOL = "ExitPlanMode"
PLAN_CHARS = 60000  # of a plan, in the row
ARG_CHARS, ARG_KEYS = 1200, 24  # of what a prompt with no command or change asks with ("args"; the pane's tool details' caps)


def file_size(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


NOT_PLAIN = "something that isn't a plain file"


def bytes_to_compare(path, limit, head=False):
    """A file a change is shown against: (its content, "") when it's a
    plain file of at most limit bytes (None: any size; head: a bigger one's
    first limit bytes), else (None, what it is: "a file of 18 MB",
    "something that isn't a plain file"); (None, "") when there's none.
    (Opened without waiting, so a pipe put there is never read.)"""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOCTTY", 0))
    except (OSError, ValueError):  # (ValueError: a NUL in the path)
        return None, ""
    try:
        st = os.fstat(fd)
    except OSError:
        st = None
    if st is None or st.st_mode & 0o170000 != 0o100000:  # (stat.S_ISREG; a folder: fdopen would refuse it)
        os.close(fd)
        return None, "" if st is None else NOT_PLAIN
    with os.fdopen(fd, "rb") as f:
        try:
            if limit is None:
                return f.read(), ""
            if head:
                return f.read(limit), ""
            data = f.read(st.st_size + 1) if st.st_size <= limit else b""  # (not a buffer of limit: sized as the file)
            if st.st_size < len(data) <= limit:  # (it grew meanwhile)
                data += f.read(limit + 1 - len(data))
        except OSError:
            return None, ""
        if st.st_size > limit or len(data) > limit:
            return None, "a file of %d MB" % max(1, round(max(st.st_size, len(data)) / (1 << 20)))
        return data, ""


def read_plain(path, limit=None, head=False):
    """path's content when it's a plain file (or a link to one) of at most
    limit bytes (None: any size; head: a bigger one's first limit bytes),
    else None: the reader of every file a repository, a chat or a host can
    name, so a link to a device, a pipe or a socket is never read nor
    waited for (bytes_to_compare)."""
    return bytes_to_compare(path, limit, head)[0]


def text_to_compare(path):
    """bytes_to_compare of a file a prompt's change is shown against (at most DIFF_FILE_MAX), as text."""
    data, other = bytes_to_compare(path, DIFF_FILE_MAX)
    return (None, other) if data is None else (data.decode("utf-8", "replace"), "")


HUNK_LINE = re.compile(r"^@@ -(\d+)(,\d+)? \+(\d+)(,\d+)? @@")


def edit_diff(name, inp, current, limit=DIFF_LINES):
    """The lines of a unified diff of the change an Edit, MultiEdit, Write or
    NotebookEdit call asks for (current: the file's text now, for Write and
    for an Edit's line numbers); the first limit of them (None: all)."""
    import difflib
    import itertools
    if name == "Edit":
        old, new = inp.get("old_string"), inp.get("new_string")
        pairs = [(old, new)] if isinstance(old, str) and isinstance(new, str) else []
    elif name == "MultiEdit":
        pairs = [(e.get("old_string"), e.get("new_string")) for e in inp.get("edits") or []
                 if isinstance(e, dict) and isinstance(e.get("old_string"), str) and isinstance(e.get("new_string"), str)]
    elif name == "Write":
        pairs = [(current or "", inp.get("content"))] if isinstance(inp.get("content"), str) else []
    elif name == "NotebookEdit":
        pairs = [("", inp.get("new_source"))] if isinstance(inp.get("new_source"), str) else []
    else:
        pairs = []
    out = []
    for old, new in pairs:
        # (difflib's time grows with the square of what it compares: only the
        # lines between those both start and end with are, and 2 of those
        # around them; a change longer than DIFF_COMPARE_LINES shows its new
        # lines, with a note)
        a, b = old.splitlines(), new.splitlines()
        head, most = 0, min(len(a), len(b))
        while head < most and a[head] == b[head]:
            head += 1
        tail = 0
        while tail < most - head and a[-1 - tail] == b[-1 - tail]:
            tail += 1
        top, cut = max(0, head - 2), max(0, tail - 2)
        a, b = a[top:len(a) - cut], b[top:len(b) - cut]
        if not a or not b or len(a) + len(b) > DIFF_COMPARE_LINES:
            def span(n):
                return "1" if n == 1 else "%d,%d" % (n > 0, n)  # (as difflib writes it)
            note = ["Too long to compare here: %d new lines in place of %d" % (len(b), len(a))] if a and b else []
            diff = itertools.chain(["@@ -%s +%s @@" % (span(len(a)), span(len(b)))] + note if a or b else [],
                                   ("-" + line for line in a if not b), ("+" + line for line in b))
        else:
            diff = difflib.unified_diff(a, b, lineterm="", n=2)
            next(diff, None), next(diff, None)  # (its --- and +++ lines)
        # The @@ lines at the file's line numbers: a Write's are; an Edit's
        # are the change's own, moved to where its text is in the file
        # (current), else left out ("@@ @@")
        shift = top if name == "Write" else None
        if name == "Edit" and current and old and old in current:
            shift = current[:current.index(old)].count("\n") + top
        for line in diff:
            if limit is not None and len(out) >= limit:
                return out
            m = HUNK_LINE.match(line)
            if m:
                line = "@@ @@" if shift is None else "@@ -%d%s +%d%s @@" % (
                    int(m.group(1)) + shift, m.group(2) or "", int(m.group(3)) + shift, m.group(4) or "")
            out.append(line)
    return out


def question_view(inp):
    """The questions of an AskUserQuestion call: [{"question", "header",
    "multiSelect", "options": [{"label", "description"}]}]."""
    def text(value):
        return value[:QUESTION_CHARS] if isinstance(value, str) else ""
    out = []
    for q in inp.get("questions") or [] if isinstance(inp, dict) else []:
        if not isinstance(q, dict) or not text(q.get("question")):
            continue
        options = [{"label": text(o.get("label")), "description": text(o.get("description"))}
                   for o in q.get("options") or [] if isinstance(o, dict) and text(o.get("label"))]
        out.append({"question": text(q["question"]), "header": text(q.get("header")),
                    "multiSelect": q.get("multiSelect") is True, "options": options})
    return out


def permission_view(tool, inp, cwd, suggestions=()):
    """What a permission prompt asks, as the pane and the row show it:
    {"tool", "line" (one line), "command" (a Bash command), "file", "diff"
    (lines), "args" (the rest of what it asks with, "key: value", when there's
    no command or change to show: an MCP tool's, a page's), "always" (what
    Always allow lets through, or ""), "questions" (Claude's multiple-choice
    questions: question_view)}."""
    inp = inp if isinstance(inp, dict) else {}
    view = {"tool": tool or "", "line": describe_tool({"name": tool, "input": inp}), "command": "", "file": "",
            "diff": [], "args": [], "always": "", "questions": [], "plan": None}
    if tool == PLAN_TOOL:
        view["plan"] = plan_view(inp)
        view["line"] = "Plan: " + view["plan"]["title"] if view["plan"]["title"] else "A plan, ready to start"
        return view
    if tool == ASK_TOOL:
        view["questions"] = question_view(inp)
        if view["questions"]:
            view["line"] = short_text(view["questions"][0]["question"], 120)
        return view
    if tool == "Bash" and isinstance(inp.get("command"), str):
        view["command"] = inp["command"]
    path = inp.get("file_path") or inp.get("notebook_path")
    if isinstance(path, str) and path:
        view["file"] = file_label(path, cwd or "", Path.home())
        current, other = None, ""
        if tool in ("Write", "Edit"):
            current, other = text_to_compare(path)
        view["diff"] = edit_diff(tool, inp, current or "")
        if tool == "Write" and other and view["diff"]:
            # (its new text: under the @@ line, so a row's few lines show it)
            view["diff"].insert(1, "Replaces %s, not compared here: the new text" % other)
            del view["diff"][DIFF_LINES:]
    if not view["command"] and not view["diff"]:
        view["args"] = tool_args(inp, skip=("file_path", "notebook_path") if view["file"] else ())
    view["always"] = always_allow(suggestions)[1]
    return view


def tool_args(inp, skip=()):
    """A tool call's input as "key: value" lines (a list or an object as
    JSON), each value cut at ARG_CHARS, the first ARG_KEYS of them; the last
    says how many more there are."""
    out = []
    for key, value in inp.items():
        if key in skip or value is None or value == "":
            continue
        if len(out) == ARG_KEYS:
            out.append("… %d more" % (sum(1 for k, v in inp.items() if k not in skip and v not in (None, "")) - ARG_KEYS))
            break
        if not isinstance(value, str):
            try:
                value = json.dumps(value, ensure_ascii=False)
            except (TypeError, ValueError):
                value = str(value)
        out.append("%s: %s" % (key, value if len(value) <= ARG_CHARS else value[:ARG_CHARS - 1] + "…"))
    return out


# What Always allow lets through, by what Claude suggests: the kinds Talpy
# Den says in words (a mode that lets more through; a rule that allows, a
# folder), and where each goes (a suggestion for anywhere else isn't sent)
ALWAYS_MODES = {"acceptEdits": "all edits (accept edits mode)", "bypassPermissions": "everything (bypass permissions mode)",
                "auto": "what auto mode finds safe"}
ALWAYS_WHERE = {"session": "in this chat", "cliArg": "in this chat",
                "localSettings": "in this project (.claude/settings.local.json)",
                "projectSettings": "in this project (.claude/settings.json, shared through git)",
                "userSettings": "in every project (your user settings)"}


def always_allow(suggestions):
    """(the suggestions Always allow sends, what they let through in words:
    "all edits (accept edits mode) and access to ~/other, in this chat",
    "Bash(git push:*) in this project (.claude/settings.local.json)"; ""
    when there's none). Only those the words name are sent (pane.py
    decision_of), so the button says all it does."""
    kept, groups = [], {}
    for s in suggestions or ():
        if not isinstance(s, dict) or s.get("destination") not in ALWAYS_WHERE:
            continue
        if s.get("type") == "setMode" and s.get("mode") in ALWAYS_MODES:
            words = [ALWAYS_MODES[s["mode"]]]
        elif s.get("type") == "addRules" and s.get("behavior") == "allow":
            rules = [r for r in s.get("rules") or () if isinstance(r, dict) and isinstance(r.get("toolName"), str)
                     and r["toolName"] and isinstance(r.get("ruleContent") or "", str)]
            s = dict(s, rules=rules)
            words = [short_text("%s(%s)" % (r["toolName"], r["ruleContent"]) if r.get("ruleContent") else r["toolName"], 120)
                     for r in rules]
        elif s.get("type") == "addDirectories":
            s = dict(s, directories=[d for d in s.get("directories") or () if isinstance(d, str) and d])
            home = str(Path.home())  # (the folder whole, from ~ on: which one must be clear)
            words = ["access to " + short_text("~" + d[len(home):] if d == home or d.startswith(home + "/") else d, 200)
                     for d in s["directories"]]
        else:
            continue
        if words:
            kept.append(s)
            groups.setdefault(ALWAYS_WHERE[s["destination"]], []).extend(words)
    text = []
    for where, words in groups.items():
        what = words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1] + ","
        text.append("%s %s" % (what, where))
    return kept, "; ".join(text)


def plan_view(inp):
    """The plan of an ExitPlanMode call: {"text" (Markdown), "cut" (longer
    than PLAN_CHARS), "file" (its plan file), "title" (its first heading or
    line)}; the text from the plan file when the call doesn't carry it."""
    text = inp.get("plan") if isinstance(inp.get("plan"), str) else ""
    path = inp.get("planFilePath") if isinstance(inp.get("planFilePath"), str) else ""
    if not text.strip() and path:
        # (its start only, from a plain file: enough to tell it's longer than PLAN_CHARS)
        data = read_plain(path, PLAN_CHARS * 4 + 4, head=True)
        text = data.decode("utf-8", "replace") if data is not None else ""
    title = ""
    for line in text.splitlines():
        line = line.strip().lstrip("#").strip()
        if line:
            title = short_text(line, 100)
            break
    return {"text": text[:PLAN_CHARS], "cut": len(text) > PLAN_CHARS, "file": path, "title": title}


def pending_tool(path):
    """The oldest tool call of a chat's last turn that has no result yet
    (the one a permission prompt is about while the chat waits: open_tools),
    or None."""
    calls = open_tools(path)
    return calls[0] if calls else None


def open_tools(path):
    """The tool calls of a chat's last turn that have no result yet, oldest
    first (several when Claude made them in one reply: which of them a
    permission prompt is about isn't written down). Claude Code (2.1.314)
    runs a reply's calls in their order, one that may change something only
    once every call before it is done and alone (its tool queue's
    canExecuteTool and processQueue); calls that only read (Read, Grep, …)
    can run, and ask, together. So the oldest open call is the one that
    asks, unless reads run side by side."""
    try:
        size = path.stat().st_size
        with open(path, "rb") as f:
            f.seek(max(0, size - PEEK_TAIL_BYTES))
            lines = f.read(min(size, PEEK_TAIL_BYTES)).split(b"\n")
    except (OSError, AttributeError):
        return []
    if size > PEEK_TAIL_BYTES:
        lines = lines[1:]
    answered, calls = set(), []
    for line in reversed(lines):
        if not PEEK_LINE.search(line):
            continue
        try:
            e = json.loads(line)
        except (ValueError, RecursionError):
            continue
        if not isinstance(e, dict) or e.get("isSidechain") or e.get("type") not in ("user", "assistant"):
            continue
        _, blocks = blocks_of(e)
        if e["type"] == "user":
            if human_prompt(e) is not None:
                break
            answered.update(c.get("tool_use_id") for c in blocks if c.get("type") == "tool_result")
            continue
        calls += [c for c in reversed(blocks) if c.get("type") == "tool_use" and c.get("id") not in answered]
    return calls[::-1]


def tool_use_id(value):
    """A tool call's id (a tool_use block's, or one a request names), or None."""
    return value if isinstance(value, str) and value else None


def pending_permission(path, cwd):
    """permission_view of what a waiting chat asks, from its transcript, or
    None; "toolUse": the id of the tool call it's about; "sure": whether
    that's certain (the only call open, and not a subagent's: what one of
    those asks is in its own transcript)."""
    calls = open_tools(path) if path is not None else []
    if not calls:
        return None
    use = calls[0]
    return dict(permission_view(use.get("name"), use.get("input"), cwd), toolUse=tool_use_id(use.get("id")),
                sure=len(calls) == 1 and use.get("name") not in SUBAGENT_TOOLS)


def chat_tool_use(home, extra_dirs, session_id, profile_key=None):
    """The id of the tool call a running chat asks about now: pending_tool of
    the transcript its row shows (finish_row's chatId, which note_permissions
    reads), found as find_chat_entry finds the chat; None when it asks
    nothing (or isn't running)."""
    profiles = discover_profiles(home, extra_dirs)
    for entry, runs_on, holder in live_entries_all(profiles):
        if entry.get("sessionId") != session_id or entry.get("kind") not in SESSION_KINDS \
                or entry.get("spare") or entry.get("parkedJobId"):
            continue
        if profile_key and profile_key not in (runs_on.key, holder.key):
            continue
        job_id = entry.get("jobId") if valid_id(entry.get("jobId")) else None
        job = read_job(dict.fromkeys([runs_on, holder]), job_id) if job_id else None
        row = {"sessionId": session_id, "cwd": entry.get("cwd") if isinstance(entry.get("cwd"), str) else ""}
        ctx = Context(profiles=profiles, links=LinkCache(cache_dir(home) / "links.json"))
        chat, _ = chat_link(row, job, runs_on, ctx)
        use = pending_tool(transcript_path(runs_on, chat))
        return tool_use_id(use.get("id")) if use else None
    return None


def requests_dir(cache_root):
    """Where the permission hook writes its requests and reads your answers:
    the state folder (state_dir), never the cache."""
    return state_dir(cache_root) / PERMISSIONS


def names_in(folder):
    """os.listdir(folder), [] when there's none."""
    try:
        return os.listdir(folder)
    except OSError:
        return []


def request_dirs(cache_root):
    """requests_dir, then the cache's permissions/, where a copy of the hook
    older than this one still writes (on an SSH host, until it's turned on
    again there): what it asks still shows, and your answer goes beside it."""
    return [requests_dir(cache_root), Path(cache_root) / PERMISSIONS]


def pid_alive(pid):
    if not isinstance(pid, int) or pid <= 1:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def permission_requests(cache_root, now_ms=None):
    """{session id: its newest open request} of the requests the hook wrote
    (relayed), whose hook still waits; the files of the others are removed.
    The newest: a prompt answered in the chat leaves its hook waiting until
    the chat stops waiting, so when the chat asks again at once, the older
    request is one it doesn't show any more."""
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    out = {}
    for folder, name in [(d, n) for d in request_dirs(cache_root) for n in sorted(names_in(d))]:
        if not name.endswith(".json") or name.endswith(".answer.json"):
            continue
        path = folder / name
        req = read_json(path)
        stale = not isinstance(req, dict) or not pid_alive(req.get("hookPid")) \
            or now_ms - (req.get("at") or 0) > REQUEST_MAX_AGE_MS
        if stale:
            for p in (path, folder / (name[:-5] + ".answer.json")):
                try:
                    p.unlink()
                except OSError:
                    pass
            continue
        sid = req.get("sessionId")
        if valid_id(sid or "") and (sid not in out or req.get("at", 0) >= out[sid].get("at", 0)):
            out[sid] = req
    return out


def request_view(req):
    """A relayed request as a row carries it: permission_view plus its id."""
    view = permission_view(req.get("tool"), req.get("input"), req.get("cwd") or "", req.get("suggestions"))
    view["request"] = req.get("id")
    view["toolUse"] = tool_use_id(req.get("toolUse"))  # (if Claude named the call: 2.1.311 doesn't)
    return view


def note_permissions(groups, ctx, requests):
    """A chat waiting for a permission (or with a question for you) gets
    "permission": what it asks (request_view, or pending_permission without
    the hook), "answer": how the widget can answer it ("hook", "keys" in
    tmux, or ""; a question: "hook" or "") and "toolUse": the id of the tool
    call it's about, or None (pane.py --keys --expect checks it's still the
    one asked about before it presses a key)."""
    for g in groups:
        for s in g["sessions"]:
            s["permission"] = None
            wait = s.get("waitingFor")
            if s["state"] != "waiting" or wait not in PERMISSION_WAITS:
                continue
            req = requests.get(s["sessionId"])
            if req is not None:
                if wait != QUESTION_WAIT or req.get("tool") == ASK_TOOL:
                    view = request_view(req)
                    s["permission"] = dict(view, answer="hook", toolUse=view.get("toolUse"))
                continue
            profile = next((p for p in ctx.profiles if p.key == s.get("profileDir")), None)
            path = transcript_path(profile, s.get("chatId") or s["sessionId"]) if profile is not None else None
            view = pending_permission(path, s.get("cwd") or "")
            if view is not None and (wait != QUESTION_WAIT or view["tool"] == ASK_TOOL):
                question, sure = view["tool"] == ASK_TOOL, view.pop("sure", False)
                # (not a plan: its dialog differs by account; nor a call that may not be the one asked
                # about: the keys would answer whatever Claude shows)
                keys = s.get("tmux") and not question and view["tool"] != PLAN_TOOL and sure
                s["permission"] = dict(view, request=None, answer="keys" if keys else "", toolUse=view.get("toolUse"))


QUESTION_WAIT = "input needed"  # (also an MCP server's question: only AskUserQuestion's count)
SUBAGENT_TOOLS = ("Agent", "Task")  # (a subagent's call: "Task" in older Claude Code)
PERMISSION_WAITS = ("permission prompt", QUESTION_WAIT)


# ---------------------------------------------------------------- live mode
#
# The live hook (live_hook.py, which pane.py --live on puts in Claude's
# settings) folds each chat's events into its live file,
# ~/.cache/talpy-den/live/<session id>.json, as they happen: what the
# chat does now, its last steps, its running subagents, what it said last.
# A running chat's row carries it ("live"), and the widget follows the files
# between two checks (live.py --wait; the VS Code extension: fs.watch).

LIVE = "live"
LIVE_HOOK_FILE = "live-hook.py"
PERMISSION_HOOK_FILE = "permission-hook.py"
LIVE_FIELDS = ("state", "doing", "asks", "at", "turnAt", "steps", "agents", "said", "saidAt", "failed")
# The hooks' copies (pane.py --relay/--live on) and the files they're copies of
HOOK_SOURCES = {PERMISSION_HOOK_FILE: "permission_hook.py", LIVE_HOOK_FILE: "live_hook.py"}
HOOK_REVISION = re.compile(rb"^HOOK_REVISION = ([0-9]+)", re.M)
HOOK_GUARD = "] || exit 0;"  # (in the hooks' commands, once each: pane.hook_command)


# Where an organization's managed settings are (Linux, macOS): claude reads
# managed-settings.json there, and each .json file of managed-settings.d
MANAGED_SETTINGS_DIRS = ("/etc/claude-code", "/Library/Application Support/ClaudeCode")


def managed_hooks_only(dirs=None):
    """Do managed settings let only their own hooks run (allowManagedHooksOnly),
    or none (disableAllHooks)? Then a hook Talpy Den gives one chat (claude
    --settings: Talpy Chat's permission hook) doesn't run, so Talpy Chat
    can't answer what a background chat it started asks."""
    for folder in MANAGED_SETTINGS_DIRS if dirs is None else dirs:
        if not os.path.isdir(folder):
            continue
        files = [os.path.join(folder, "managed-settings.json")]
        drop_ins = os.path.join(folder, "managed-settings.d")
        try:
            files += sorted(os.path.join(drop_ins, n) for n in os.listdir(drop_ins) if n.endswith(".json"))
        except OSError:
            pass
        for name in files:
            data = read_json(Path(name))
            if isinstance(data, dict) and (data.get("allowManagedHooksOnly") is True or data.get("disableAllHooks") is True):
                return True
    return False


def hooks_dir(home):
    """Where pane.py --relay/--live on keeps the hooks' copies that Claude's settings name."""
    return Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share") / "talpy-den"


def safe_folder(folder):
    """Make folder (0700, with its parents) for a file Claude runs as you (a
    hook's copy) or one that answers for you (a request's answer), and say
    whether it's safe there: a folder of yours, not a link, that nobody else
    may write in (an XDG_DATA_HOME or XDG_STATE_HOME on shared space, as
    some sites set them: anyone's file there would run, or answer, as you).
    One of yours that others may write in (made under a looser umask) is
    made 0700; what's in it is checked by whoever reads it (place_hook).
    None when it is, else why not."""
    import stat
    try:
        Path(folder).mkdir(mode=0o700, parents=True, exist_ok=True)
        st = os.lstat(str(folder))
    except OSError as exc:
        return f"couldn't make {folder}: {exc.strerror or exc}"
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid():
        return f"{folder} isn't a folder of yours"
    if st.st_mode & 0o077:
        try:
            os.chmod(str(folder), 0o700)
        except OSError as exc:
            return f"others may write in {folder}: {exc.strerror or exc}" if st.st_mode & 0o022 else None
    return None


def own_file(path):
    """Whether path is a plain file of yours that nobody else may write (not
    a link): one put in a folder others could write in before is not."""
    import stat
    try:
        st = os.lstat(str(path))
    except OSError:
        return False
    return stat.S_ISREG(st.st_mode) and st.st_uid == os.getuid() and not st.st_mode & 0o022


def home_id(home):
    """Which home folder this is, on which running system, in 12 characters
    (no path in it): the same in a container that shares your home (a
    Toolbox, a Distrobox, a folder bind-mounted) as here, whose ~/.claude*,
    hook copies and requests are this computer's. "" when unknown."""
    try:
        with open("/proc/sys/kernel/random/boot_id", encoding="ascii") as f:
            boot = f.read().strip()
        st = os.stat(str(home))
    except (OSError, ValueError):
        return ""
    return hashlib.sha1(f"{boot}:{st.st_dev}:{st.st_ino}".encode()).hexdigest()[:12]


def live_hook_on(home):
    """Whether the live hook is on (pane.py --live on keeps its copy here)."""
    return (hooks_dir(home) / LIVE_HOOK_FILE).is_file()


def hook_revision(code):
    """A hook's version (its HOOK_REVISION line; 1 for one from before that line)."""
    m = HOOK_REVISION.search(code)
    return int(m.group(1)) if m else 1


def refresh_hooks(home, code_dir=None):
    """Bring the hooks that are on up to date: a copy older than the hook
    next to this file (code_dir) is replaced by it, so what a new version of
    a hook fixes reaches the settings that already name it. Only ever newer
    (several front ends of other versions may run this), never one that's
    off. The names of the copies that changed."""
    if code_dir is None:
        here = globals().get("__file__")
        if not here or not os.path.isfile(here):
            return []  # (on an SSH host this file comes on stdin, without the hooks)
        code_dir = Path(here).resolve().parent
    changed = []
    for name, source in HOOK_SOURCES.items():
        target = hooks_dir(home) / name
        try:
            with open(target, "rb") as f:
                installed = f.read()
                mode = os.fstat(f.fileno()).st_mode & 0o777
            with open(Path(code_dir) / source, "rb") as f:
                new = f.read()
        except OSError:
            continue  # off (no copy), or no hook here to take it from
        if hook_revision(new) <= hook_revision(installed):
            continue
        tmp = target.with_name(f".{name}.{os.getpid()}.tmp")
        try:
            with open(tmp, "wb") as f:
                f.write(new)
            os.chmod(tmp, mode)
            os.replace(tmp, target)
            changed.append(name)
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass
    return changed


def upgrade_hook_settings(home, extra_dirs=()):
    """Settings whose hook commands an older version wrote (with no check that
    the hook's copy is there: pane.hook_command) get today's
    (pane.upgrade_hooks). Looked for cheaply first: today's command names
    its copy twice and HOOK_GUARD once."""
    here = globals().get("__file__")
    if not here or not os.path.isfile(here):
        return 0  # (on an SSH host this file comes on stdin, without pane.py)
    names = [n.encode() for n in HOOK_SOURCES]
    for folder in [p.path for p in discover_profiles(home, extra_dirs)] + [home / ".claude"]:
        try:
            with open(folder / "settings.json", "rb") as f:
                text = f.read()
        except OSError:
            continue
        hooks = sum(text.count(n) for n in names)
        if hooks and hooks != 2 * text.count(HOOK_GUARD.encode()):
            code = str(Path(here).resolve().parent)
            if code not in sys.path:
                sys.path.insert(0, code)
            import pane
            return pane.upgrade_hooks(home, extra_dirs)
    return 0


def live_view(cache_root, sid, pid):
    """A running chat's live file as its row carries it, or None (none, or
    another process's: the chat went on in another one)."""
    if not valid_id(sid or "") or not pid:
        return None
    view = read_json(cache_root / LIVE / (sid + ".json"))
    if not isinstance(view, dict) or view.get("state") == "ended" or view.get("pid") not in (None, pid):
        return None
    return {k: view.get(k) for k in LIVE_FIELDS}


def note_live(groups, cache_root):
    for g in groups:
        for s in g["sessions"]:
            s["live"] = live_view(cache_root, s["sessionId"], s["pid"])


def reply_route(row):
    """How a chat takes a message: "tmux" (typed into its pane), "vscode"
    (its VS Code tab's input), "background" (a live background session
    takes it in through Claude's service, reply_to_background; else claude
    --bg --resume: a chat with no process) or "terminal" (a terminal
    that takes no text from outside: going on in the background or the
    clipboard)."""
    if not row.get("pid") or row.get("kind") == "bg":
        return "background"
    if row.get("entrypoint") == "claude-vscode":
        return "vscode"
    return "tmux" if row.get("tmux") else "terminal"


# ---------------------------------------------------------------- tests after the last edit, reviewed chats
#
# A finished chat that changed files is "to review" until you mark it
# reviewed (reviewed.json: {"chats": {"[host|]chat id": when}}), or again
# once it changes files after that. Its row says whether tests ran after its
# last edit and how they went: a Bash command that looks like a test run
# (is_test_run), and its result (an exit code other than 0 is an error).

REVIEWED = "reviewed.json"
REVIEWED_KEEP_MS = 60 * 86400_000
TESTS_CACHE_VERSION = 1
# A test tool run as the command (not one installed, looked up or named):
# the tool, a tool's test verb ("go test"), a build tool's test target, a
# package's test script; after cd …&&, env, timeout, uv run, npx, python -m…
TEST_TOOLS = frozenset(("pytest", "py.test", "unittest", "nose2", "tox", "nox", "jest", "vitest", "mocha", "ava",
                        "karma", "rspec", "phpunit", "ctest", "bats"))
TEST_VERBS = {"go": ("test",), "cargo": ("test", "nextest"), "deno": ("test",), "bun": ("test",), "node": ("--test",),
              "dotnet": ("test",), "mix": ("test",), "swift": ("test",), "meson": ("test",), "ninja": ("test",),
              "playwright": ("test",), "cypress": ("run",)}
TEST_TARGETS = frozenset(("make", "zig", "mvn", "mvnw", "gradle", "gradlew"))
TEST_WRAPPERS = frozenset(("env", "time", "timeout", "nice", "nohup", "sudo", "command", "exec", "xvfb-run",
                           "dbus-run-session", "stdbuf", "npx", "bunx", "pnpx", "uvx", "if", "then", "else", "do",
                           "while", "until", "!"))
TEST_LAUNCHERS = frozenset((("uv", "run"), ("poetry", "run"), ("pipenv", "run"), ("pdm", "run"), ("hatch", "run"),
                            ("rye", "run"), ("conda", "run"), ("npm", "exec"), ("pnpm", "exec"), ("pnpm", "dlx"),
                            ("yarn", "exec"), ("yarn", "dlx"), ("bundle", "exec")))
# ... or a test file run directly: ./run-tests.sh, python3 tests/test_week.py, gjs -m tests/test_logic.js
SCRIPT_RUNNER = re.compile(r"(?:python|pypy)[\d.]*|nodejs|node|gjs|bash|sh|zsh|dash|ksh|ruby|perl|php|tsx|ts-node")
SOURCE_FILE = re.compile(r"\.(?:py|[cm]?js|[cm]?ts|sh|bash|rb|pl|php)$")
INFO_ONLY = frozenset(("--version", "-V", "--help", "-h"))
SHELL_SPLIT = re.compile(r"&&|\|\||\$\(|[;|&()`]")
REDIRECT = re.compile(r"\d*[<>]&\d*-?")
ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
BASH_LINE = re.compile(rb'"name":\s*"Bash"')


def review_key(chat_id, host=""):
    return f"{host}|{chat_id}" if host else chat_id


def load_reviewed(cache_root):
    """{review_key: when} of the chats marked reviewed (0: marked not
    reviewed, also if their last edit came before reviewed_since)."""
    data = read_json(cache_root / REVIEWED)
    chats = data.get("chats") if isinstance(data, dict) else None
    return {k: v for k, v in chats.items() if isinstance(v, (int, float))} if isinstance(chats, dict) else {}


def reviewed_since(cache_root, now_ms):
    """Since when chats are to review: what they changed before the widget
    first looked isn't (else every chat that ever changed a file would be)."""
    data = read_json(cache_root / REVIEWED)
    if isinstance(data, dict) and isinstance(data.get("since"), (int, float)):
        return data["since"]
    try:
        private_dir(cache_root)
        write_json_atomic(cache_root / REVIEWED, {"since": now_ms, "chats": load_reviewed(cache_root)})
    except OSError:
        pass
    return now_ms


def new_tests():
    """A transcript's last edit (editAt, ms) and its newest test run
    ({"command", "ok": True/False, "at"}), with the test runs that have no
    result yet (pending: {tool id: [command, at]})."""
    return {"editAt": None, "run": None, "pending": {}}


QUOTED = re.compile(r"'[^']*'|\"(?:[^\"\\\\]|\\\\.)*\"")


def is_test_run(command):
    """Does a Bash command run tests? Its first line, quotes left out (not
    a script it pipes in, nor a commit message that names a test tool), each
    command of it."""
    if not isinstance(command, str):
        return False
    line = REDIRECT.sub(" ", QUOTED.sub("''", command.split("\n", 1)[0]))
    return any(runs_tests(part.split()) for part in SHELL_SPLIT.split(line))


def test_file(path):
    name = path.rsplit("/", 1)[-1].lower()
    return "test" in name and name != "test"  # (not the shell's test)


def runs_tests(words):
    """Do these words (one command) run tests (is_test_run)?"""
    i = 0
    while i < len(words):  # past VAR=… and what runs the command
        name = words[i].rsplit("/", 1)[-1]
        if ASSIGNMENT.match(words[i]):
            i += 1
        elif name in TEST_WRAPPERS or tuple(words[i:i + 2]) in TEST_LAUNCHERS:
            i += 1 if name in TEST_WRAPPERS else 2
            while i < len(words) and (words[i].startswith("-") or ASSIGNMENT.match(words[i])
                                      or (name == "timeout" and words[i][:1].isdigit())):
                i += 1
        else:
            break
    if i >= len(words):
        return False
    name, args = words[i].rsplit("/", 1)[-1], words[i + 1:]
    if args and set(args) <= INFO_ONLY:  # (pytest --version)
        return False
    if name in TEST_TOOLS or (args and args[0] in TEST_VERBS.get(name, ())):
        return True
    if name in ("npm", "pnpm", "yarn", "bun"):
        script = args[1:] if args[:1] == ["run"] else args
        return bool(script) and (script[0].startswith("test") or (name in ("pnpm", "yarn") and script[0] in TEST_TOOLS))
    if name in TEST_TARGETS:
        return any(a == "test" or a.endswith(":test") or (name == "make" and re.match(r"(?:test|check)\b", a))
                   for a in args if not a.startswith("-"))
    if SCRIPT_RUNNER.fullmatch(name):
        if name.startswith(("python", "pypy")) and "-c" in args:
            return False
        if name.startswith(("python", "pypy")) and "-m" in args:
            j = args.index("-m")
            module = args[j + 1] if j + 1 < len(args) else ""
            return "test" in module.rsplit(".", 1)[-1] or module in TEST_TOOLS
        script = next((a for a in args if not a.startswith("-") and ("/" in a or SOURCE_FILE.search(a))), None)
        return script is not None and test_file(script)
    return "/" in words[i] and test_file(words[i])


def fold_tests(rec, e):
    kind = e.get("type")
    at = to_ms(e.get("timestamp"))
    if kind == "assistant":
        for c in blocks_of(e)[1]:
            if c.get("type") != "tool_use" or not isinstance(c.get("input"), dict):
                continue
            if c.get("name") in EDIT_TOOLS:
                rec["editAt"] = at if rec["editAt"] is None or (at or 0) >= rec["editAt"] else rec["editAt"]
            elif c.get("name") == "Bash" and is_test_run(c["input"].get("command")) and isinstance(c.get("id"), str):
                rec["pending"][c["id"]] = [short_text(c["input"]["command"].split("\n", 1)[0], 120), at]
    elif kind == "user":
        for c in blocks_of(e)[1]:
            if c.get("type") == "tool_result" and c.get("tool_use_id") in rec["pending"]:
                command, started = rec["pending"].pop(c["tool_use_id"])
                rec["run"] = {"command": command, "ok": not c.get("is_error"), "at": at or started}


def scan_tests(path, rec, start=0):
    """Fold a transcript's lines from byte offset start into rec (new_tests);
    returns the offset read up to."""
    offset = start
    try:
        with open(path, "rb") as f:
            f.seek(start)
            for line in f:
                if not line.endswith(b"\n"):
                    break
                offset += len(line)
                wanted = (ASSISTANT_LINE.search(line) and (EDIT_LINE.search(line) or BASH_LINE.search(line))) or (
                    rec["pending"] and b'"tool_result"' in line
                    and any(i.encode() in line for i in rec["pending"]))
                if not wanted:
                    continue
                try:
                    e = json.loads(line)
                except (ValueError, RecursionError):
                    continue
                if isinstance(e, dict) and not e.get("isSidechain"):
                    fold_tests(rec, e)
    except OSError:
        pass
    return offset


def merge_tests(recs):
    """{"editAt", "run"} of a chat from its transcript's and its subagents'
    (newest edit; newest run), run None if it came before the last edit."""
    edit = max((r["editAt"] for r in recs if r["editAt"] is not None), default=None)
    runs = [r["run"] for r in recs if r["run"]]
    run = max(runs, key=lambda r: r.get("at") or 0) if runs else None
    if run is not None and edit is not None and (run.get("at") or 0) < edit:
        run = None
    return {"editAt": edit, "run": run}


def chat_tests(path):
    """merge_tests of a chat, read in full (pane.py --review)."""
    recs = []
    for p in [path] + subagent_transcripts(path):
        rec = new_tests()
        scan_tests(p, rec)
        recs.append(rec)
    return merge_tests(recs)


class TestsCache:
    """new_tests of the transcripts of listed and recent chats that changed
    files, kept between polls in tests.json (only what was appended is read)."""

    def __init__(self, path):
        self.path = path
        data = read_json(path)
        ok = isinstance(data, dict) and data.get("version") == TESTS_CACHE_VERSION
        self.old = data if ok and isinstance(data.get("files"), dict) else {}
        self.data = {"version": TESTS_CACHE_VERSION, "files": {}}
        self.changed = not ok

    def rec(self, path):
        try:
            st = path.stat()
        except OSError:
            return new_tests()
        key = file_key(st)
        old = self.data["files"].get(key) or self.old.get("files", {}).get(key)
        if isinstance(old, list) and len(old) == 2 and isinstance(old[0], int) and old[0] <= st.st_size \
                and isinstance(old[1], dict) and all(k in old[1] for k in ("editAt", "run", "pending")):
            size, rec = old
        else:
            size, rec = 0, new_tests()
        if size < st.st_size:
            rec = json.loads(json.dumps(rec))
            size = scan_tests(path, rec, size)
            self.changed = True
        self.data["files"][key] = [size, rec]
        return rec

    def review(self, path):
        """{"editedAt", "tests"} of a chat (merge_tests), or None."""
        if path is None:
            return None
        merged = merge_tests([self.rec(p) for p in [path] + subagent_transcripts(path)])
        return {"editedAt": merged["editAt"], "tests": merged["run"]} if merged["editAt"] is not None else None

    def save(self):
        kept = keep_unused(self.old, self.data, ("files",), time.time())
        if self.changed or kept or set(self.data["files"]) != set(self.old.get("files", {})):
            try:
                write_json_atomic(self.path, self.data)
            except OSError:
                pass


# ---------------------------------------------------------------- shared chats
#
# A chat shared across profiles is one transcript file hard-linked into each
# profile's projects/ folder (as sharing.py does). Every row knows which
# conversation it shows (chatId: the transcript it writes) and how that
# relates to a shared chat:
#   - the shared chat itself, maybe through a background session of its own
#     whose own file holds no messages (`continues`);
#   - a copy: Claude forked the shared chat into a transcript of its own, which
#     starts with the shared chat's history (`forkOf`);
#   - nothing to do with it (a new conversation).


def transcript_path(profile, session_id):
    if not valid_id(session_id):
        return None
    return next(iter(profile.path.glob(f"projects/*/{session_id}.jsonl")), None)


def chat_folder(path):
    """The folder a chat last ran in (the last "cwd" in its transcript),
    read from the end (further back while the last lines are huge ones)."""
    try:
        size = path.stat().st_size
    except OSError:
        return None
    nbytes = PEEK_TAIL_BYTES
    while True:
        try:
            with open(path, "rb") as f:
                f.seek(max(0, size - nbytes))
                lines = f.read(min(size, nbytes)).splitlines()
        except OSError:
            return None
        for line in reversed(lines[1:] if size > nbytes else lines):  # the first may be cut
            if b'"cwd"' not in line:
                continue
            try:
                cwd = json.loads(line).get("cwd")
            except (ValueError, AttributeError, RecursionError):
                continue
            if isinstance(cwd, str) and cwd.startswith("/"):
                return cwd
        if nbytes >= size or nbytes >= PEEK_TAIL_MAX:
            return None
        nbytes *= 4


def start_folder(path):
    """The folder a chat started in (its first "cwd"), when Claude Code files
    it under that folder (projects/<the folder, mangled>); later ones follow
    Claude's `cd`s."""
    try:
        with open(path, "rb") as f:
            head = f.read(PEEK_TAIL_BYTES)
    except OSError:
        return None
    for line in head.splitlines():  # (a cut last line doesn't parse)
        if b'"cwd"' not in line:
            continue
        try:
            cwd = json.loads(line).get("cwd")
        except (ValueError, AttributeError, RecursionError):
            continue
        if isinstance(cwd, str) and cwd.startswith("/"):
            return cwd if mangle(cwd) == path.parent.name else None
    return None


def shared_info(session_id, profile, all_profiles):
    """Is this chat shared across profiles? Returns {"profiles": [labels],
    "openIn": label holding it open or None}, or None."""
    own = transcript_path(profile, session_id)
    try:
        st = own.stat() if own else None
    except OSError:
        return None
    if st is None or st.st_nlink < 2:
        return None
    labels = [profile.label]
    for other in all_profiles:
        if other is profile:
            continue
        for t in other.path.glob(f"projects/*/{session_id}.jsonl"):
            try:
                o = t.stat()
            except OSError:
                continue
            if (o.st_dev, o.st_ino) == (st.st_dev, st.st_ino) and other.label not in labels:
                labels.append(other.label)
    if len(labels) < 2:
        return None
    return {"profiles": labels, "openIn": shared_holder(session_id, all_profiles)}


MESSAGE_LINE = re.compile(rb'"type":\s*"(?:user|assistant)"')


def has_own_messages(profile, session_id):
    """Does this session's own transcript hold any conversation?"""
    path = transcript_path(profile, session_id)
    if path is None:
        return False
    try:
        with open(path, "rb") as f:
            return any(MESSAGE_LINE.search(line) for line in f)
    except OSError:
        return False


def file_key(st):
    return f"{st.st_dev}:{st.st_ino}"


class LinkCache:
    """What the widget learned about transcripts, kept between polls in
    links.json, so big shared transcripts are only read where they grew:

    - for each shared transcript: its `continued-in` records (Claude writes one
      when the chat moves on to another session) and where its last finished
      reply is, which tells whether the chat moved on (Claude's own rule);
    - for each other transcript: the uuid of its first entry, and whether a
      shared transcript holds that entry (then it's a copy of that chat);
    - for each transcript: the chat it continues, when Claude moved that one
      to the background under a new id (moved_from).
    """

    VERSION = 2

    def __init__(self, path):
        self.path = path
        data = read_json(path)
        ok = isinstance(data, dict) and data.get("version") == self.VERSION
        self.old = data if ok else {}
        self.data = {"version": self.VERSION, "transcripts": {}, "firstUuid": {}, "holds": {}, "chats": {}, "moved": {}}
        self.changed = not ok

    def _keep(self, section, key, value):
        if self.old.get(section, {}).get(key) != value:
            self.changed = True
        self.data[section][key] = value

    def transcript(self, path):
        """{"size", "conts": [[session id, offset]], "final": offset} of a
        shared transcript, scanning only what was appended since last time."""
        try:
            st = path.stat()
        except OSError:
            return None
        key = file_key(st)
        rec = self.data["transcripts"].get(key) or self.old.get("transcripts", {}).get(key)
        if not (isinstance(rec, dict) and isinstance(rec.get("size"), int) and rec["size"] <= st.st_size):
            rec = {"size": 0, "conts": [], "final": -1}
        if rec["size"] < st.st_size:
            rec = dict(rec, conts=list(rec["conts"]))
            try:
                with open(path, "rb") as f:
                    f.seek(rec["size"])
                    chunk = f.read(st.st_size - rec["size"])
            except OSError:
                chunk = b""
            end = chunk.rfind(b"\n")  # never consume a half-written last line
            if end >= 0:
                offset = rec["size"]
                for line in chunk[:end + 1].splitlines(keepends=True):
                    if b'"continued-in"' in line or b'"stop_reason":"' in line:
                        try:
                            e = json.loads(line)
                        except (ValueError, RecursionError):
                            e = None
                        if isinstance(e, dict):
                            if e.get("type") == "continued-in" and valid_id(e.get("continuedInSessionId")):
                                rec["conts"].append([e["continuedInSessionId"], offset])
                            elif finished_reply(e):
                                rec["final"] = offset
                    offset += len(line)
                rec["size"] = offset
        self._keep("transcripts", key, rec)
        return rec

    def first_uuid(self, path, st=None):
        """uuid of the first entry that has one ('' if none in the first 256 KB)."""
        try:
            st = path.stat() if st is None else st
        except OSError:
            return ""
        key = file_key(st)
        cached = self.data["firstUuid"].get(key, self.old.get("firstUuid", {}).get(key))
        if isinstance(cached, str) and cached:
            self._keep("firstUuid", key, cached)
            return cached
        found = ""
        try:
            with open(path, "rb") as f:
                head = f.read(262144)
        except OSError:
            head = b""
        for line in head.splitlines()[:-1] if not head.endswith(b"\n") else head.splitlines():
            if b'"uuid"' not in line:
                continue
            try:
                e = json.loads(line)
            except (ValueError, RecursionError):
                continue
            if isinstance(e, dict) and isinstance(e.get("uuid"), str) and e["uuid"]:
                found = e["uuid"]
                break
        self._keep("firstUuid", key, found)
        return found

    def holds(self, shared_path, uuid):
        """Does this shared transcript contain the entry with this uuid? Once
        known it stays true; a copy's first entry is in the chat before the
        copy exists, so a no stays a no too (per file)."""
        try:
            st = shared_path.stat()
        except OSError:
            return False
        key = f"{uuid}|{file_key(st)}"
        cached = self.data["holds"].get(key, self.old.get("holds", {}).get(key))
        if isinstance(cached, bool):
            self._keep("holds", key, cached)
            return cached
        found = False
        try:
            with open(shared_path, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as m:
                found = m.find(f'"uuid":"{uuid}"'.encode()) >= 0
        except (OSError, ValueError):
            pass
        self._keep("holds", key, found)
        return found

    def moved_from(self, path, st=None):
        """The chat this transcript continues, or "": closing a chat's terminal
        makes Claude move it to the background under a new id, its transcript
        a copy of the chat's history whose entries keep the old id in
        `session_id` (snake case; `sessionId` is the new one). The copy is at
        its top: the first entry with a `session_id` names another chat, and
        the last such entry before its own entries the chat it moved from
        (a chat moved twice carries both). Read once (and then only what
        was added while it's all copied entries): no `session_id` in its
        first MOVED_HEAD_LINES lines, or its own first, isn't a moved chat.
        Nor is one whose first such entry isn't in the chat it names, when
        that one's transcript is there: `session_id` is the id the process
        that wrote an entry started with, so after /clear (or /resume) in a
        chat the new conversation's entries carry the old id too, but they
        are new, not copied."""
        try:
            st = path.stat() if st is None else st
        except OSError:
            return ""
        key = file_key(st)
        rec = self.data["moved"].get(key) or self.old.get("moved", {}).get(key)
        if not (isinstance(rec, dict) and isinstance(rec.get("size"), int) and rec["size"] <= st.st_size
                and isinstance(rec.get("from"), str) and rec.get("copied") is not None):
            rec = {"size": 0, "lines": 0, "from": "", "done": False, "copied": False}
        if not rec.get("done") and rec["size"] < st.st_size:
            rec = dict(rec)
            own = path.stem
            try:
                with open(path, "rb") as f:
                    f.seek(rec["size"])
                    for line in f:
                        if not line.endswith(b"\n"):
                            break  # (never a half-written last line)
                        rec["size"] += len(line)
                        rec["lines"] += 1
                        if b'"session_id"' in line:
                            try:
                                e = json.loads(line)
                            except (ValueError, RecursionError):
                                e = None
                            sid = e.get("session_id") if isinstance(e, dict) else None
                            if valid_id(sid) and sid == own:
                                rec["done"] = True  # its own entries begin (or it never moved)
                            elif valid_id(sid) and not rec["copied"] and not self.copied(path, sid, e.get("uuid")):
                                rec["from"], rec["done"] = "", True  # (new entries: /clear, /resume)
                            elif valid_id(sid):
                                rec["from"], rec["copied"] = sid, True
                        if not rec["done"] and not rec["from"] and rec["lines"] >= MOVED_HEAD_LINES:
                            rec["done"] = True  # (no copied entries at its top)
                        if rec["done"]:
                            break
            except OSError:
                pass
        self._keep("moved", key, rec)
        return rec["from"]

    def copied(self, path, chat, uuid):
        """Can this entry of a transcript be a copy of the chat's: it's in
        that chat's transcript (in the same folder, else another one of the
        account's: Claude moves a transcript when its chat changes folder),
        or that's gone, so it can't be told."""
        source = path.with_name(f"{chat}.jsonl")
        if not source.exists():
            try:
                source = next(path.parent.parent.glob(f"*/{chat}.jsonl"), None)
            except OSError:
                source = None
            if source is None:
                return True
        return isinstance(uuid, str) and bool(uuid) and self.holds(source, uuid)

    def chat_info(self, path, st):
        """(name, cwd, has messages) of a transcript, read again only when it grew."""
        key = file_key(st)
        cached = self.data["chats"].get(key, self.old.get("chats", {}).get(key))
        if isinstance(cached, list) and len(cached) == 4 and cached[0] == st.st_size:
            self._keep("chats", key, cached)
            return cached[1], cached[2], cached[3]
        name, cwd, messages = read_chat_info(path, st.st_size)
        self._keep("chats", key, [st.st_size, name, cwd, messages])
        return name, cwd, messages

    def save(self):
        sections = ("transcripts", "firstUuid", "holds", "chats", "moved")
        kept = keep_unused(self.old, self.data, sections, time.time())
        if self.changed or kept or any(set(self.data[s]) != set(self.old.get(s, {})) for s in sections):
            try:
                write_json_atomic(self.path, self.data)
            except OSError:
                pass


MOVED_HEAD_LINES = 400  # a moved chat's copied entries are at its top (LinkCache.moved_from)
MOVED_SCAN_DAYS = 14  # transcripts changed this long ago aren't read for it (chat_moves)


def chat_moves(ctx):
    """{chat id: the id it moved to}, of the chats Claude moved to the
    background under a new id (LinkCache.moved_from), the newest move of
    each; read from the transcripts changed in the last MOVED_SCAN_DAYS,
    once per check."""
    found = getattr(ctx, "moves", None)
    if found is not None:
        return found
    moves = {}
    since = ctx.now_ms / 1000 - MOVED_SCAN_DAYS * 86400
    for t, _p, f, st in all_transcripts(ctx):  # (newest first)
        if t < since:
            break
        old = ctx.links.moved_from(f, st)
        if old and old != f.stem and old not in moves:
            moves[old] = f.stem
    ctx.moves = moves
    return moves


def moved_chat(chat, moves):
    """The id a chat goes on under now: where it moved to, and on (chat_moves)."""
    seen = {chat}
    while chat in moves and moves[chat] not in seen:
        chat = moves[chat]
        seen.add(chat)
    return chat


def continuation(home, extra_dirs, profile_key, chat):
    """The id a chat of this computer goes on under now (moved_chat), read
    from the transcripts in its folder (and links.json, where the status
    checks keep what they read of them), or chat itself."""
    profiles = discover_profiles(home, extra_dirs)
    profile = next((p for p in profiles if matches_profile(p, profile_key)), None) if profile_key else None
    folders = []
    for p in ([profile] if profile is not None else []) + profiles:
        path = transcript_path(p, chat)
        if path is not None and path.parent not in folders:
            folders.append(path.parent)
    if not folders:
        return chat
    links = LinkCache(cache_dir(home) / "links.json")
    since = time.time() - MOVED_SCAN_DAYS * 86400
    moves, found = {}, []
    for folder in folders:
        try:
            files = list(folder.glob("*.jsonl"))
        except OSError:
            continue
        for f in files:
            try:
                st = f.stat()
            except OSError:
                continue
            if valid_id(f.stem) and st.st_mtime >= since:
                found.append((st.st_mtime, f, st))
    for _, f, st in sorted(found, key=lambda c: -c[0]):
        old = links.moved_from(f, st)
        if old and old != f.stem and old not in moves:
            moves[old] = f.stem
    return moved_chat(chat, moves)


def finished_reply(e):
    """Claude's test for a finished assistant reply (its transcript `I()`)."""
    msg = e.get("message")
    return (e.get("type") == "assistant" and e.get("isApiErrorMessage") is not True
            and isinstance(msg, dict) and isinstance(msg.get("stop_reason"), str))


def shared_transcripts(folder, ctx):
    """Shared (hard-linked) transcripts in a project folder, by name. A status
    check takes them from its list of every transcript (all_transcripts, made
    before its rows), once per check; else the folder is read."""
    listed = getattr(ctx, "transcripts", None)
    if listed is not None:
        by_folder = getattr(ctx, "shared_files", None)
        if by_folder is None:
            by_folder = ctx.shared_files = {}
            for _t, _p, f, st in listed:
                if st.st_nlink > 1:
                    by_folder.setdefault(f.parent, []).append(f)
            for files in by_folder.values():
                files.sort()
        return by_folder.get(folder, [])
    try:
        files = sorted(folder.glob("*.jsonl"))
    except OSError:
        return []
    out = []
    for t in files:
        try:
            if t.stat().st_nlink > 1:
                out.append(t)
        except OSError:
            continue
    return out


def project_folders(profile, ids, cwd):
    """Project folders (projects/<key>) a session's transcripts can be in."""
    folders = []
    for sid in ids:
        path = transcript_path(profile, sid)
        if path is not None:
            folders.append(path.parent)
    if cwd:
        folders.append(profile.path / "projects" / re.sub(r"[^A-Za-z0-9]", "-", cwd))
    return list(dict.fromkeys(f for f in folders if f.is_dir()))


def continued_from(profile, ids, cwd, ctx):
    """The shared chat whose `continued-in` record names one of these ids (a
    background session that took the chat over gets an id of its own)."""
    wanted = {i for i in ids if valid_id(i)}
    for folder in project_folders(profile, ids, cwd):
        for t in shared_transcripts(folder, ctx):
            rec = ctx.links.transcript(t)
            if rec and any(c[0] in wanted for c in rec["conts"]) and t.stem not in wanted:
                return t.stem
    return None


def copied_from(profile, session_id, ctx):
    """The shared chat this session's transcript is a copy of: Claude forked it
    and the copy starts with the chat's history (its first entry's uuid is in
    the shared transcript)."""
    path = transcript_path(profile, session_id)
    if path is None:
        return None
    uuid = ctx.links.first_uuid(path)
    if not uuid:
        return None
    for t in shared_transcripts(path.parent, ctx):
        if t != path and ctx.links.holds(t, uuid):
            return t.stem
    return None


def chat_link(row, job, profile, ctx):
    """(chatId, shared info or None) of a row.

    chatId is the conversation the row shows: its own transcript, or, when its
    own file holds no messages, the chat it took over (the job's
    resumeSessionId, else the chat whose `continued-in` record names it).
    """
    own = row["sessionId"]
    job = job if isinstance(job, dict) else {}
    chat, continues = own, None
    if not has_own_messages(profile, own):
        target = job.get("resumeSessionId") if valid_id(job.get("resumeSessionId")) else None
        if target == own:
            target = None
        if target is None:
            target = continued_from(profile, [own, job.get("sessionId")], row["cwd"], ctx)
        if target is not None:
            chat, continues = target, target
    info = shared_info(chat, profile, ctx.profiles)
    if info:
        if continues:
            info["continues"] = continues
        return chat, info
    # Not shared itself: a copy of a shared chat? The job may name it; else
    # its history gives it away.
    origin = None
    for k in ("forkParentSessionId", "resumeSessionId"):
        candidate = job.get(k)
        if valid_id(candidate) and candidate != chat and transcript_path(profile, candidate) is not None:
            origin = candidate
            break
    if origin is None or not shared_info(origin, profile, ctx.profiles):
        origin = copied_from(profile, chat, ctx)
    if origin is not None:
        info = next((i for i in (shared_info(origin, p, ctx.profiles) for p in ctx.profiles) if i), None)
        if info:
            return chat, {**info, "forkOf": origin, "forkOn": profile.label}
    return chat, None


def handed_over(profile, chat, profiles):
    """The chat isn't this profile's any more: it has no transcript of it, and
    another profile has (a shared chat kept only there, sharing.py's
    --unshare). A background record of it left here is stale."""
    if transcript_path(profile, chat) is not None:
        return False
    return any(p.real != profile.real and transcript_path(p, chat) is not None for p in profiles)


def chat_id(session):
    """The conversation a row shows (a background session that took a chat
    over has an id of its own but is that chat)."""
    return session.get("chatId") or session["sessionId"]


def moved_to(chat, ctx):
    """Session id a chat moved on to, by Claude's own rule: its transcript's
    last `continued-in` record comes after its last finished reply."""
    for p in ctx.profiles:
        path = transcript_path(p, chat)
        if path is None:
            continue
        rec = ctx.links.transcript(path)
        if rec:
            after = [c[0] for c in rec["conts"] if c[1] > rec["final"]]
            return after[-1] if after else None
    return None


def chat_activity(chat, ids, ctx):
    """{profile: last time (ms) this chat was used there}, from the status-line
    snapshots, the prompt history and a sharing hook's lock."""
    seen = {}
    ids = [i for i in dict.fromkeys([chat, *ids]) if valid_id(i)]
    for p in ctx.profiles:
        snaps = snapshot_paths(ctx.snapshot_root, p, ids)
        times = [int(snaps[0][0] * 1000)] if snaps else []
        last_prompt = max((ctx.prompts.get(p.real, {}).get(i, 0) for i in ids), default=0)
        if last_prompt:
            times.append(last_prompt)
        if times:
            seen[p] = max(times)
    holder = lock_holder(chat, ctx.profiles)
    if holder is not None:
        p, when = holder
        seen[p] = max(seen.get(p, 0), when)
    return seen


REHOME_SLACK_MS = 60_000


def place_chats(groups, ctx):
    """List each conversation once.

    - A chat that moved on to a copy of itself (Claude's `continued-in` rule)
      isn't listed: the copy is, and accounts sharing the chat get a link to it.
    - A chat that runs somewhere is listed there; its finished background
      records elsewhere are left out (the row notes them as stopped copies).
    - A finished shared chat is listed under the account it was used on last.
      If that account has no record of it (e.g. you used it in a terminal
      there), the newest record moves there as a finished chat ("chat").
    """
    by_profile = {p.key: p for p in ctx.profiles}
    group_of = {key: g for g in groups for key in g["profileKeys"]}
    ctx.moved_on = set()
    rows = {}
    for g in groups:
        for s in g["sessions"]:
            rows.setdefault(chat_id(s) or s["key"], []).append((g, s))

    def is_record(s):  # a finished background record with no process
        return s["state"] == "done" and s["pid"] is None

    def note_stopped(keep, gone):
        for _, k in keep:
            for _, s in gone:
                if s["kind"] == "bg" and s["profile"] != k["profile"]:
                    if k["shared"] is not None:
                        stopped = k["shared"].setdefault("stoppedCopies", [])
                        if s["profile"] not in stopped:
                            stopped.append(s["profile"])

    def drop(entries):
        for g, s in entries:
            if g is not None:
                g["sessions"] = [x for x in g["sessions"] if x is not s]

    # A shared chat that moved on to a listed copy of itself
    forks = {}
    for g in groups:
        for s in g["sessions"]:
            if s["shared"] and s["shared"].get("forkOf"):
                forks.setdefault(s["shared"]["forkOf"], []).append(s)
    for chat, entries in list(rows.items()):
        if not any(s["shared"] and not s["shared"].get("forkOf") for _, s in entries) or chat not in forks:
            continue
        target = moved_to(chat, ctx)
        if target is None:  # it didn't move on (a fork's jobSessionId is often None too)
            continue
        copy = next((f for f in forks[chat] if target in (f["sessionId"], f.get("jobSessionId"))), None)
        if copy is None:
            continue
        if all(is_record(s) for _, s in entries):
            copy["shared"]["movedHere"] = True
            ctx.moved_on.add(chat)
            drop(entries)
            note_stopped([(None, copy)], entries)
            del rows[chat]

    # A finished shared chat that moved on to a chat listed anyway: its copy
    # was shared too, so it's a shared chat of its own rather than a copy
    listed = {i: s for g in groups for s in g["sessions"]
              for i in (s["sessionId"], s.get("jobSessionId"), chat_id(s)) if i}
    for chat, entries in list(rows.items()):
        if not any(s["shared"] for _, s in entries) or not all(is_record(s) for _, s in entries):
            continue
        target = moved_to(chat, ctx)
        if target is None or target == chat or target not in listed or chat_id(listed[target]) == chat:
            continue
        ctx.moved_on.add(chat)
        drop(entries)
        del rows[chat]

    for chat, entries in rows.items():
        shared = next((s["shared"] for _, s in entries if s["shared"] and not s["shared"].get("forkOf")), None)
        active = [(g, s) for g, s in entries if not is_record(s)]
        if shared is not None and any(s["pid"] is not None or s["state"] == "working" for _, s in active):
            # A shared chat that runs in a session on one account isn't also
            # listed for a background job on another that has stopped (at its
            # usage limit, say) and has no process now: that's the chat's old copy
            active = [(g, s) for g, s in active if s["pid"] is not None or s["kind"] != "bg" or s["state"] == "working"]
        if active:
            stale = [(g, s) for g, s in entries if not any(s is t for _, t in active)]
            drop(stale)
            note_stopped(active, stale)
            continue
        entries = sorted(entries, key=lambda e: -(e[1]["since"] or 0))
        newest_g, newest = entries[0]
        if shared is None:
            drop(entries[1:])
            continue
        # Finished everywhere: which account used it last?
        seen = chat_activity(chat, [i for _, s in entries for i in (s["sessionId"], s.get("jobSessionId"))], ctx)
        for g, s in entries:
            p = by_profile.get(s["profileDir"])
            if p is not None:
                seen[p] = max(seen.get(p, 0), s["since"] or 0)
        listed = {by_profile.get(s["profileDir"]) for _, s in entries}
        home = max(seen, key=lambda p: seen[p]) if seen else None
        if home is None or home in listed or home.key not in group_of \
                or seen[home] - max((seen.get(p, 0) for p in listed if p is not None), default=0) < REHOME_SLACK_MS:
            keep_p = home if home in listed else by_profile.get(newest["profileDir"])
            keep = next(((g, s) for g, s in entries if s["profileDir"] == getattr(keep_p, "key", None)), entries[0])
            gone = [e for e in entries if e[1] is not keep[1]]
            drop(gone)
            note_stopped([keep], gone)
            continue
        # Last used on an account with no record of it: list it there
        moved = dict(newest, shared=dict(newest["shared"]) if newest["shared"] else None)
        moved.update({
            "key": f"{home.key}/{chat}/chat", "profileDir": home.key, "profile": home.label,
            "sessionId": chat, "chatId": chat, "pid": None, "kind": "chat", "entrypoint": "",
            "state": "done", "reason": "", "waitingFor": "", "detail": "", "since": seen[home],
            "startedAt": None, "jobId": None, "jobSessionId": None,
            "context": None, "contextLeft": None, "contextNear": False, "model": None, "costUsd": None,
            "formerIds": [i for _, s in entries for i in (s["sessionId"], s.get("jobSessionId")) if i],
        })
        attach_snapshot(moved, ctx.snapshot_root, home, [chat, *(i for _, s in entries for i in (s["sessionId"], s.get("jobSessionId")))])
        drop(entries)
        if moved["shared"] is not None:
            moved["shared"].pop("stoppedCopies", None)
        note_stopped([(None, moved)], entries)
        group_of[home.key]["sessions"].append(moved)


def follow_moved(groups, ctx):
    """A chat Claude moved to the background under a new id (chat_moves) is
    that one now: a row of its old id with no process isn't listed (a
    process still on the old id is a chat at work, and stays), nor is the
    old id among the recent chats."""
    moves = chat_moves(ctx)
    if not moves:
        return
    for g in groups:
        g["sessions"] = [s for s in g["sessions"] if s["pid"] is not None or chat_id(s) not in moves]
    ctx.moved_on = set(getattr(ctx, "moved_on", None) or ()) | set(moves)


def note_moved(groups, ctx):
    """The row of a chat Claude moved to the background under a new id
    (chat_moves) says so: "movedFrom": {"id": the id it had, "at": when
    (ms; its background job's start, else None)}."""
    back = {new: old for old, new in chat_moves(ctx).items()}
    if not back:
        return
    for g in groups:
        for s in g["sessions"]:
            cid = chat_id(s)
            if cid not in back:
                continue
            job = read_job(ctx.profiles, cid[:8])
            at = to_ms(job.get("createdAt")) if isinstance(job, dict) and job.get("sessionId") == cid else None
            s["movedFrom"] = {"id": back[cid], "at": at}


def list_kept(groups, ctx, kept):
    """A chat that keeps going (kept: keep.json's entries) stays listed until
    it's let go, with or without a process, as a background one: one whose
    terminal was closed has no row of its own, so it gets one (kind "chat",
    under the id it goes on under now), with what stopped it."""
    moves = chat_moves(ctx)
    listed = {i for g in groups for s in g["sessions"] for i in (s["sessionId"], s.get("chatId"), s.get("jobSessionId")) if i}
    group_of = {key: g for g in groups for key in g["profileKeys"]}
    for k in kept:
        chat = moved_chat(k["chat"], moves)
        if chat in listed:
            continue
        mine = [p for p in ctx.profiles if matches_profile(p, k["profile"])]
        profile, path = next(((p, transcript_path(p, chat)) for p in mine + ctx.profiles
                              if p.key in group_of and transcript_path(p, chat) is not None), (None, None))
        if path is None:
            continue
        try:
            st = path.stat()
        except OSError:
            continue
        name, cwd, _ = ctx.links.chat_info(path, st)
        cwd = cwd or (k.get("folder") if isinstance(k.get("folder"), str) else "")
        row = make_session(profile, ctx.home, sid=chat, pid=None, name=clean_text(name or k.get("name") or "", 80),
                           cwd=cwd, kind="chat", entrypoint="", state="done", reason="", waiting_for="", detail="",
                           since=int(st.st_mtime * 1000), started_at=None)
        row["key"] = f"{profile.key}/{chat}/chat"
        group_of[profile.key]["sessions"].append(finish_row(row, None, None, profile, ctx, alive=False))
        listed.add(chat)


def kept_turns(home, extra_dirs, kept, moves):
    """How each chat here that keeps going from the computer that asks
    stands (an SSH host's or a container's run, --kept-chats): {its id (as
    it goes on now, moves): {"turn": last_turn} or {"gone": True}}."""
    profiles = discover_profiles(home, extra_dirs)
    out = {}
    for k in kept:
        chat = moved_chat(k["chat"], moves)
        mine = [p for p in profiles if matches_profile(p, k["profile"])]
        path = next((t for t in (transcript_path(p, chat) for p in mine + profiles) if t is not None), None)
        out[chat] = {"turn": last_turn(path)} if path is not None else {"gone": True}
    return out


def link_shared_elsewhere(groups):
    """A shared chat is listed once. Give every other account it's shared with
    a pointer to it (`sharedHere`), unless that account lists the chat itself
    or a copy of it. A chat that moved on to a copy points to the copy."""
    for g in groups:
        g["sharedHere"] = []
    listed = {chat_id(s) for g in groups for s in g["sessions"]}
    pointed = set()  # (account, chat): a chat listed twice (open on two accounts) gets one pointer
    for g in groups:
        for s in g["sessions"]:
            info = s["shared"]
            if not info:
                continue
            copy = bool(info.get("forkOf"))
            if copy and not (info.get("movedHere") and info["forkOf"] not in listed):
                continue
            chat = info["forkOf"] if copy else chat_id(s)
            for h in groups:
                if h is g or not set(h["profiles"]) & set(info["profiles"]):
                    continue
                if any(chat_id(t) == chat or (t["shared"] or {}).get("forkOf") == chat for t in h["sessions"]):
                    continue
                if (id(h), chat) in pointed:
                    continue
                pointed.add((id(h), chat))
                h["sharedHere"].append({
                    "key": f"{s['key']}/shared",
                    "sessionId": s["sessionId"],
                    "name": s["name"],
                    "cwdShort": s["cwdShort"],
                    "state": s["state"],
                    "reason": s["reason"],
                    "since": s["since"],
                    "profile": s["profile"],
                    "profileDir": s["profileDir"],
                    "copy": copy,
                    "stoppedHere": any(p in h["profiles"] for p in info.get("stoppedCopies", [])),
                })


# Hooks can hold a shared chat to one session at a time: the session using it
# writes ~/.local/state/claude-shared-chats/lock-<id> on each prompt and tool
# call. The widget doesn't install such hooks; where they are set up, their
# lock tells it who has the chat open and where it was used last.


def lock_path(session_id):
    state = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "claude-shared-chats"
    return state / f"lock-{session_id}"


def read_lock(session_id):
    """(pid, start, config dir, mtime) from a shared chat's lock
    (`<pid>-<start> <config dir>`), or None."""
    if not valid_id(session_id):
        return None
    path = lock_path(session_id)
    text = read_text(path)
    if not text:
        return None
    holder, _, folder = text.strip().partition(" ")
    pid, _, start = holder.partition("-")
    if not pid.isdigit() or not folder:
        return None
    return int(pid), start or None, folder, mtime(path)


def profile_of(folder, all_profiles):
    try:
        real = Path(folder).resolve()
    except (OSError, RuntimeError):
        return None
    return next((p for p in all_profiles if p.real == real), None)


def shared_holder(session_id, all_profiles):
    """Profile whose session holds a shared chat open, from its lock, if that
    process is still alive."""
    lock = read_lock(session_id)
    if lock is None or not is_alive({"pid": lock[0], "procStart": lock[1]}):
        return None
    p = profile_of(lock[2], all_profiles)
    return p.label if p else None


def lock_holder(session_id, all_profiles):
    """(profile, ms) of the last session that used a shared chat: the lock is
    rewritten on each prompt and tool call, and stays after the session ends."""
    lock = read_lock(session_id)
    if lock is None or lock[3] is None:
        return None
    p = profile_of(lock[2], all_profiles)
    return (p, int(lock[3] * 1000)) if p else None


# ---------------------------------------------------------------- recent chats

RECENT_CHATS = 5
RECENT_CHECKED = 200  # past an account's first page, how many more of its chats are counted one by one (then by file)
TITLE_READ_BYTES = 65536
TITLE_KINDS = (("custom-title", "customTitle"), ("agent-name", "agentName"), ("ai-title", "aiTitle"),
               ("summary", "summary"))


def read_chat_info(path, size):
    """(name, cwd, has messages) of a transcript, from its first and last 64 KB.
    The name is what you renamed the chat to, else its session name, else
    Claude's title for it, else its first prompt."""
    try:
        with open(path, "rb") as f:
            head = f.read(TITLE_READ_BYTES)
            if size > 2 * TITLE_READ_BYTES:
                f.seek(size - TITLE_READ_BYTES)
            tail = f.read() if size > TITLE_READ_BYTES else b""
    except OSError:
        return "", "", False
    lines = head.splitlines()[:-1 if len(head) == TITLE_READ_BYTES else None]
    if tail:
        lines += tail.splitlines()[1:]
    found, cwd, first_prompt, messages = {}, "", "", False
    for line in lines:
        if not line.startswith(b"{"):
            continue
        try:
            e = json.loads(line)
        except (ValueError, RecursionError):
            continue
        if not isinstance(e, dict):
            continue
        kind = e.get("type")
        for name, field in TITLE_KINDS:
            if kind == name and isinstance(e.get(field), str) and e[field].strip():
                found[name] = e[field]
        if kind in ("user", "assistant"):
            messages = True
            if isinstance(e.get("cwd"), str) and e["cwd"].startswith("/"):
                cwd = e["cwd"]
            if kind == "user" and not first_prompt and not e.get("isMeta"):
                content = e["message"].get("content") if isinstance(e.get("message"), dict) else None
                if isinstance(content, list):
                    content = next((c.get("text") for c in content if isinstance(c, dict) and c.get("type") == "text"), "")
                if isinstance(content, str) and content.strip() and not content.lstrip().startswith("<"):
                    first_prompt = content
    name = next((found[k] for k, _ in TITLE_KINDS if k in found), first_prompt)
    return clean_text(name, 80), cwd, messages


def recent_chats(groups, ctx, limit=RECENT_CHATS, starred=frozenset()):
    """Each account's latest chats that aren't listed as a session already
    (group["recent"]: the first limit of them; group["recentCount"]: how many
    there are, for "Show N more"), and of those its starred ones (ids in
    starred), however old (group["starred"]). A chat shared across accounts
    shows up under the one it was used on last; of a chat and its copies
    (same first entry), only the newest (a starred older one under Starred
    only); a shared chat that moved on to a
    listed copy, not at all. Past the first limit the chats are only
    counted: the next RECENT_CHECKED of an account by the same rules (what's
    read of them is kept in links.json), the ones after those by their
    files, so a check stays as quick with thousands of chats (the count of
    an account with that many may only be a little high)."""
    listed = {i for g in groups for s in g["sessions"] for i in (s["sessionId"], s.get("chatId"), s.get("jobSessionId")) if i}
    listed |= getattr(ctx, "moved_on", set())
    by_key = {p.key: p for p in ctx.profiles}
    group_of = {key: g for g in groups for key in g["profileKeys"]}
    # (each one's id once: past the first page, every bit of work per chat counts)
    candidates = [(t, p, f, st, sid) for t, p, f, st in all_transcripts(ctx)
                  for sid in (f.stem,) if p.key in group_of and sid not in listed]
    for g in groups:
        g["recent"], g["starred"], g["recentCount"] = [], [], 0
    wanted = set(starred)  # (starred chats not found yet)
    if limit <= 0 and not wanted:
        return
    seen, firsts = set(), set()
    checked = {id(g): limit + RECENT_CHECKED for g in groups}
    # A listed chat's older copies (they start with the same entry) are that
    # chat, e.g. one that moved on to a background session listed now
    for g in groups:
        for s in g["sessions"]:
            p = by_key.get(s.get("profileDir"))
            path = transcript_path(p, chat_id(s)) if p is not None else None
            first = ctx.links.first_uuid(path) if path is not None else ""
            if first:
                firsts.add(first)
    for t, p, f, st, sid in candidates:
        star = sid in wanted
        if limit <= 0 and not star:
            continue
        inode = (st.st_dev, st.st_ino)
        if inode in seen:
            continue
        seen.add(inode)
        if not star and group_of[p.key]["recentCount"] >= checked[id(group_of[p.key])]:
            group_of[p.key]["recentCount"] += 1  # (by its file)
            continue
        name, cwd, messages = ctx.links.chat_info(f, st)
        if not messages:
            continue
        first = ctx.links.first_uuid(f, st)
        copy = bool(first) and first in firsts  # an older copy of a chat already listed: only under Starred, if starred
        if copy and not star:
            continue
        firsts.add(first)
        shared = st.st_nlink > 1 and shared_info(sid, p, ctx.profiles)
        if shared and moved_to(sid, ctx) in listed:
            continue  # it moved on to a session listed already
        home = p
        if shared:  # under the account that used it last
            seen_at = chat_activity(sid, [], ctx)
            if seen_at:
                home = max(seen_at, key=lambda q: seen_at[q])
                if home.key not in group_of:
                    home = p
        g = group_of[home.key]
        if limit > 0 and not copy:
            g["recentCount"] += 1
        room = len(g["recent"]) < limit and not copy
        if not room and not star:
            continue
        chat = {
            "key": f"{home.key}/{sid}/recent",
            "sessionId": sid,
            "name": name or sid[:8],
            "cwd": cwd,
            "cwdShort": short_path(cwd, ctx.home),
            "lastActive": int(t * 1000),
            "profile": home.label,
            "profileDir": home.key,
            "shared": bool(shared),
            "starred": star,
            **recent_extras(ctx, f, g, cwd),
        }
        if room:
            g["recent"].append(chat)
        if star:
            wanted.discard(sid)
            g["starred"].append(dict(chat, key=f"{home.key}/{sid}/starred"))


def recent_extras(ctx, path, group, cwd=""):
    """A recent chat's recap and what stopped it, from the end of its
    transcript; the files it changed and its review (TestsCache.review)."""
    chats = getattr(ctx, "chats", None)
    peek = (chats.peek(path) if chats is not None else None) or {}
    stopped = peek.get("stopped")
    files = chats.changed_files(path, cwd, ctx.own_folders) if chats is not None else []
    tests = getattr(ctx, "tests", None)
    return {"recap": peek.get("recap"),
            "stopped": limit_stop(stopped, group.get("limits"), ctx.now_ms) if stopped else None,
            "changes": chats.changes(path, cwd, ctx.home, ctx.own_folders, files) if files else None,
            "review": tests.review(path) if files and tests is not None else None}


# ---------------------------------------------------------------- usage limits that stopped chats


# (a reset more than a day out comes with its day: "resets Oct 30, 7pm", and
# its year when that isn't this one: "resets Jan 2, 2027, 9am")
RESET_IN_TEXT = re.compile(r"\bresets (?:([A-Z][a-z]{2}) (\d{1,2}),(?: (\d{4}),)? )?(\d{1,2})(?::(\d{2}))?\s*([ap]m)\b",
                           re.IGNORECASE)
MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")


def reset_from_text(text, at_ms):
    """When "… · resets 7:10pm (Europe/Berlin)" (or "resets Oct 30, 7pm") in
    Claude's message is (taken as this machine's local time), after at_ms
    when it names no day; None if it names no time of day."""
    m = RESET_IN_TEXT.search(text or "")
    if not m or not at_ms:
        return None
    month, day, year = m.group(1), m.group(2), m.group(3)
    hour = int(m.group(4)) % 12 + (12 if m.group(6).lower() == "pm" else 0)
    minute = int(m.group(5) or 0)
    if minute > 59 or (month and month.lower() not in MONTHS):
        return None
    then = datetime.fromtimestamp(at_ms / 1000)
    try:
        reset = then.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if month:
            reset = reset.replace(year=int(year or then.year), month=MONTHS.index(month.lower()) + 1, day=int(day))
    except ValueError:  # (no such day)
        return None
    if reset <= then and not month:
        reset += timedelta(days=1)
    return int(reset.timestamp() * 1000)


def limit_stop(stopped, limits, now_ms):
    """A copy of what stopped a chat (stopped_by), with when the usage limit
    it hit resets ("resetsAt") or whether it has since ("over"): from the
    account's plan window of that limit (a window that started after the
    chat stopped is a new one), else from the time in Claude's message.
    When it resets as Claude noted it with the stop ("resets") comes first:
    that is the window of the account the chat ran on then."""
    s = dict(stopped, resetsAt=None, over=False)
    if s.get("kind") != "limit":
        return s
    if isinstance(s.get("resets"), int):
        s["over"] = s["resets"] <= now_ms
        s["resetsAt"] = None if s["over"] else s["resets"]
        return s
    at = s.get("at") or 0
    w = next((w for w in (limits or {}).get("windows", []) if w.get("key") == s.get("window")), None) \
        if s.get("window") else None
    known = False
    if w is not None and w.get("reset"):
        ended = w.get("endedAt")
        if ended is None or at < ended:  # (else that window was over before the chat stopped: says nothing)
            s["over"], known = True, True
    elif w is not None and w.get("resetsAt"):
        hours = window_hours(w["key"])
        if hours and at < w["resetsAt"] - hours * 3600_000:
            s["over"] = True
        else:
            s["resetsAt"] = w["resetsAt"]
        known = True
    if not known:
        guess = reset_from_text(s.get("text"), at)
        if guess is not None:
            s["over"] = guess <= now_ms
            s["resetsAt"] = None if s["over"] else guess
    return s


def note_limit_stops(group, now_ms):
    """The account's chats that a usage limit stopped: when it resets."""
    for s in group["sessions"]:
        if s.get("stopped"):
            s["stopped"] = limit_stop(s["stopped"], group.get("limits"), now_ms)


def note_limit_hits(group):
    """A plan window one of the account's chats hit the limit of after its
    usage was last read is full, whatever that read said (VS Code's panel
    runs no status line: its chats use up a window with no new numbers)."""
    limits = group.get("limits")
    if not limits:
        return
    for s in group["sessions"] + group.get("recent", []):
        stopped = s.get("stopped") or {}
        at = stopped.get("at")
        if stopped.get("kind") != "limit" or not at or at <= limits["updatedAt"]:
            continue
        if s.get("shared") and s.get("startedAt") and at < s["startedAt"]:
            continue  # (a shared chat, or a copy, may have hit another account's limit before it came here)
        for w in limits["windows"]:
            hours = window_hours(w["key"])
            if w["key"] != stopped.get("window") or w["reset"] or not w["resetsAt"] or not hours \
                    or not w["resetsAt"] - hours * 3600_000 <= at < w["resetsAt"]:
                continue  # (a limit of a window that's over since)
            if stopped.get("resets") and not same_window(stopped["resets"], w["resetsAt"]):
                continue  # (another account's window: a shared chat that ran there then)
            w["pct"] = max(w["pct"], 100.0)
            if w.get("forecast"):
                w["forecast"] = dict(w["forecast"], fullAt=None, atReset=max(w["forecast"]["atReset"], w["pct"]))


# ---------------------------------------------------------------- chats changing the same files
#
# Two chats that can still change files (each has a process) and changed
# some of the same ones may overwrite each other's work: each row names the
# other chat and those files (from what the widget reads of what a chat
# changed: Claude's backups and its edit tool calls, subagents included).

OVERLAP_FILES = 8  # file names a row carries per other chat


def note_overlaps(groups, changed, home):
    """Set "overlaps" on the rows of chats with a process that changed the
    same files as another such chat: [{"key", "name", "sessionId", "chatId",
    "profileDir", "count", "files"}]. changed: row key -> absolute paths."""
    rows = [s for g in groups for s in g["sessions"] if s.get("pid") is not None and changed.get(s["key"])]
    named = {}  # row key -> the chats it names (one listed twice, once)
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            if (a.get("chatId") or a["sessionId"]) == (b.get("chatId") or b["sessionId"]):
                continue  # one chat listed twice
            both = changed[a["key"]] & changed[b["key"]]
            if not both:
                continue
            for row, other in ((a, b), (b, a)):
                chat = other.get("chatId") or other["sessionId"]
                if chat in named.setdefault(row["key"], set()):
                    continue
                named[row["key"]].add(chat)
                row["overlaps"] = (row.get("overlaps") or []) + [{
                    "key": other["key"], "name": other["name"], "sessionId": other["sessionId"], "chatId": chat,
                    "profileDir": other["profileDir"], "count": len(both),
                    "files": sorted(file_label(p, row["cwd"], home) for p in both)[:OVERLAP_FILES],
                }]


# ---------------------------------------------------------------- tasks waiting for a usage limit
#
# A task for a background session can wait until the usage limit of its
# account resets: it's kept in ~/.cache/talpy-den/queue.json (an SSH
# host's too: they start from here, over ssh), and every status lists it
# ("due" once its time has come). A widget (or the VS Code extension) then
# starts it with jump.py --start-queued, which takes it out of the queue
# first, so of several copies only one starts it.

QUEUE_PROMPT_MAX = 100_000


def load_queue(cache_root):
    data = read_json(state_dir(cache_root) / "queue.json")
    tasks = data.get("tasks") if isinstance(data, dict) else None
    return [t for t in tasks if isinstance(t, dict) and valid_id(t.get("id"))] if isinstance(tasks, list) else []


def change_queue(cache_root, add=None, take=None, put_back=None, once=False, edit=None):
    """Change queue.json under a lock: add a task (once: unless a go-on of
    the same chat is queued already), take one out by its id (returned), or
    put one back (e.g. with the error it got); edit(tasks) changes the
    tasks in place and says whether it did. The task taken out, or None."""
    state = state_dir(cache_root)
    private_dir(state)
    with open(state / "queue.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        tasks = load_queue(cache_root)
        taken = None
        if edit is not None and edit(tasks):
            write_json_atomic(state / "queue.json", {"tasks": tasks})
        if take is not None:
            taken = next((t for t in tasks if t["id"] == take), None)
            tasks = [t for t in tasks if t["id"] != take]
        if put_back is not None:
            tasks = [t for t in tasks if t["id"] != put_back["id"]] + [put_back]
        if add is not None and once and add.get("chat") and any(
                t.get("chat") == add["chat"] and (t.get("host") or "") == (add.get("host") or "") for t in tasks):
            add = None
        if add is not None:
            tasks.append(add)
        if add is not None or taken is not None or put_back is not None:
            write_json_atomic(state / "queue.json", {"tasks": tasks})
        return taken


def queue_entry(profile, folder, prompt, start_at, host="", account="", plan=None, plan_profile=None,
                plan_title="", now_ms=None, chat=None, name="", scheduled=False, why="", model=None, effort=None,
                mode=None):
    """A task to queue (checked), or ValueError. With chat (its id), it goes
    on with that chat (one a usage limit stopped: continue_chat), named name;
    why: "retry" (its turn broke off) or "cap" (stopped at the usage cap) goes
    on whatever its newest turn is (keep_going). scheduled: it starts at a
    time you picked, not when a limit resets. model, effort, mode: a new
    chat's (chat_options)."""
    chat_options(model, effort, mode)  # (checked)
    if not isinstance(profile, str) or not profile or not isinstance(folder, str):
        raise ValueError("A queued task needs an account and a folder")
    if chat is not None and not valid_id(chat):
        raise ValueError(f"Not a chat id: {chat}")
    if not (prompt or "").strip() and not plan and chat is None:
        raise ValueError("Write what Claude should do first")
    if len(prompt or "") > QUEUE_PROMPT_MAX:
        raise ValueError("That task is too long")
    if plan is not None and not PLAN_SLUG.match(plan):
        raise ValueError(f"Not a plan name: {plan}")
    if not isinstance(start_at, int) or start_at <= 0:
        raise ValueError("A queued task needs the time it starts at")
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    return {
        "id": os.urandom(4).hex(), "host": host or "", "profile": profile, "account": account or profile,
        "folder": folder, "prompt": (prompt or "").strip(), "plan": plan, "planProfile": plan_profile,
        "planTitle": plan_title or "", "startAt": start_at, "createdAt": now_ms, "error": "",
        "chat": chat, "name": clean_text(name, 80) if chat else "", "scheduled": bool(scheduled) and chat is None,
        "why": why if chat and why in ("retry", "cap") else "",
        "model": (model or None) if chat is None else None, "effort": (effort or None) if chat is None else None,
        "mode": (mode or None) if chat is None else None,
    }


def queued_tasks(cache_root, now_ms):
    """The queued tasks as the status lists them: each with "due" (its time
    has come, and it didn't fail to start) and "folderShort"."""
    out = []
    for t in load_queue(cache_root):
        t = {"chat": None, "name": "", "scheduled": False, **t}
        t["due"] = not t.get("error") and isinstance(t.get("startAt"), (int, float)) and t["startAt"] <= now_ms
        if t.get("afterTurn"):  # (a message for when its turn ends: the widget sees that, and sends it)
            t["due"] = False
        t["folderShort"] = short_path(t["folder"], Path.home()) if not t.get("host") else t.get("folder") or "~"
        out.append(t)
    return out


# ---------------------------------------------------------------- chats that keep going
#
# A chat can keep going until it's done: whenever a usage limit stops it, it
# goes on a minute after the limit resets, as often as that takes. Such chats
# are kept in ~/.cache/talpy-den/keep.json (an SSH host's and a container's
# too, with their "host": they go on from here, over ssh, as queued tasks
# there do), and the status run of the copy that notifies looks after them
# (look_after_kept; a host's chats from its last answer, see
# look_after_host_kept): it
# queues each go-on (started like one you queued), tries again after a pause
# when one didn't take (nothing new in the chat a while after it went on) or
# when the turn broke off on an API error that isn't a limit (the connection
# lost), a few times with longer pauses, and lets the chat go once a turn of
# it has ended by itself. One you interrupted has ended too: you took over.
#
# With a usage cap (--usage-cap N), it also stops what an account has at work
# once one of its plan windows reaches N%, once in that window: the chats
# that keep going go on after the window resets, and queued tasks wait for it.

KEEP_TAKE_MS = 5 * 60_000  # a go-on that leaves nothing new in its chat after this long didn't take
KEEP_RETRY_MINUTES = (2, 5, 15, 30, 60)  # the pauses before each try again; then it gives up
KEEP_IDLE_MS = 7 * 86400_000  # a chat kept this long with nothing new is let go
TURN_ENDS = ("end_turn", "stop_sequence", "max_tokens")  # a reply's stop_reason that ends its turn
RETRY_PROMPT = "Your last turn broke off (an API error): go on where you stopped."
# An SSH host's or a container's id (remote.py's HOST_NAME: ENGINE:NAME[@HOST] for a container)
HOST_IDENT = re.compile(r"^[A-Za-z0-9_.@][A-Za-z0-9_.@:-]*$")
# A host's last answer older than this says too little about its chats that keep going
KEEP_HOST_STALE_MS = 15 * 60_000


def load_keep(cache_root):
    """{"chats": the chats that keep going, "capped": {account|window: when
    that window resets}, for the windows the usage cap stopped chats in}."""
    data = read_json(state_dir(cache_root) / "keep.json")
    data = data if isinstance(data, dict) else {}
    chats = data.get("chats") if isinstance(data.get("chats"), list) else []
    capped = data.get("capped") if isinstance(data.get("capped"), dict) else {}
    chats = [k for k in chats if isinstance(k, dict) and valid_id(k.get("chat"))
             and isinstance(k.get("profile"), str) and k["profile"]
             and (not k.get("host") or (isinstance(k["host"], str) and HOST_IDENT.match(k["host"])))]
    for k in chats:
        k["host"] = k.get("host") or ""  # (this computer's)
    return {"chats": chats,
            "capped": {w: at for w, at in capped.items() if isinstance(w, str) and number(at) is not None}}


def change_keep(cache_root, change, wait=True):
    """Change keep.json under a lock: change(data) changes it in place and
    says whether it did. False (nothing done) when another copy has the lock
    and wait is False: it looks after the chats right now."""
    state = state_dir(cache_root)
    private_dir(state)
    with open(state / "keep.lock", "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
        except BlockingIOError:
            return False
        data = load_keep(cache_root)
        if change(data):
            write_json_atomic(state / "keep.json", data)
        return True


def keep_chat(cache_root, profile_key, chat_id, name="", folder="", on=True, now_ms=None, host=""):
    """Have a chat of this computer (or of host: an SSH host or a
    container) keep going, or (not on) not any more."""
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    host = host or ""
    if host and not HOST_IDENT.match(host):
        raise ValueError(f"Not a host: {host!r}")

    def change(data):
        had = any(k["chat"] == chat_id and k["host"] == host for k in data["chats"])
        if on and had:
            return False
        data["chats"] = [k for k in data["chats"] if not (k["chat"] == chat_id and k["host"] == host)]
        if on:
            data["chats"].append({"chat": chat_id, "profile": profile_key, "host": host, "name": clean_text(name, 80),
                                  "folder": folder or "", "since": now_ms, "wentOnAt": None, "tries": 0,
                                  "note": "", "error": "", "errorAt": None, "cappedUntil": None})
        return on or had
    change_keep(cache_root, change)


def note_went_on(cache_root, chat_id, now_ms=None, host=""):
    """A go-on of a chat that keeps going (of host's) has started: something
    new should show in it soon (look_after_kept checks). Its wentOnAt
    before (None when it isn't kept, or never went on), for went_on_undone."""
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    was = []

    def change(data):
        k = next((k for k in data["chats"] if k["chat"] == chat_id and k["host"] == (host or "")), None)
        if k is None:
            return False
        was.append(k.get("wentOnAt"))
        k.update(wentOnAt=now_ms, note="", cappedUntil=None)
        return True
    change_keep(cache_root, change)
    return was[0] if was else None


def went_on_undone(cache_root, chat_id, noted, was, host=""):
    """A go-on noted at noted (note_went_on) didn't go on after all: it waits
    for the chat's background commands, or the chat went on by itself. Its
    wentOnAt goes back to was, unless a later go-on noted another time: a
    go-on noted that never started would count as one that didn't take."""
    def change(data):
        k = next((k for k in data["chats"] if k["chat"] == chat_id and k["host"] == (host or "")), None)
        if k is None or k.get("wentOnAt") != noted:
            return False
        k["wentOnAt"] = was
        return True
    change_keep(cache_root, change)


def kept_chats(cache_root, moves=None):
    """The chats that keep going, as the status lists them (this computer's
    each under the id it goes on under now: moves, chat_moves; a host's
    follow theirs as its answers say, look_after_host_kept)."""
    return [dict({f: k.get(f) for f in ("chat", "profile", "host", "name", "since", "wentOnAt", "tries", "note", "error")},
                 chat=k["chat"] if k["host"] else moved_chat(k["chat"], moves or {}))
            for k in load_keep(cache_root)["chats"]]


def keep_moved(cache_root, old, new, host=""):
    """A chat that keeps going (host's) goes on under a new id (Claude moved
    it to the background): keep.json follows it (once, if both are kept)."""
    def change(data):
        k = next((k for k in data["chats"] if k["chat"] == old and k["host"] == host), None)
        if k is None or old == new:
            return False
        if any(x["chat"] == new and x["host"] == host for x in data["chats"]):
            data["chats"].remove(k)
        else:
            k["chat"] = new
        return True
    change_keep(cache_root, change)


def follow_queue(cache_root, moves, names):
    """This computer's queued go-ons follow their chats: one Claude moved
    to the background goes on under its new id (moves), and each is named
    as its chat is now (names: {chat id: name})."""
    def edit(tasks):
        changed = False
        for t in tasks:
            if not t.get("chat") or t.get("host"):
                continue
            chat = moved_chat(t["chat"], moves)
            name = clean_text(names.get(chat) or "", 80) or t.get("name") or ""
            if (chat, name) != (t["chat"], t.get("name") or ""):
                t["chat"], t["name"] = chat, name
                changed = True
        return changed
    change_queue(cache_root, edit=edit)


def follow_host_moves(cache_root, host, moved, starred, kept):
    """An SSH host's (or a container's) chats Claude moved to the background
    there under a new id (its answer's "moved": {old id: new id}): what's
    kept of them here follows them, as this computer's do (collect,
    look_after_kept), their stars, bookmarks, keeping going and queued
    go-ons and replies. starred, kept: that host's (starred_of, keep.json's
    entries), as read for the check. Once per answer, and only when one of
    them moved."""
    moved = {old: new for old, new in moved.items() if valid_id(old) and valid_id(new) and old != new} \
        if isinstance(moved, dict) else {}
    if not moved:
        return
    try:  # (one listing of its folder; a bookmark file that couldn't move yet does at the next answer)
        bookmarks_moved(cache_root, moved, host)
    except OSError:
        pass
    for old in [c for c in starred["chats"] if c in moved]:
        change_stars(cache_root, "chats", moved_chat(old, moved), host, on=True)
        change_stars(cache_root, "chats", old, host, on=False)
    for k in [k for k in kept if k["chat"] in moved]:
        keep_moved(cache_root, k["chat"], moved_chat(k["chat"], moved), host)

    def edit(tasks):
        mine = [t for t in tasks if (t.get("host") or "") == host and t.get("chat")]
        changed = False
        for t in [t for t in mine if t["chat"] in moved]:
            t["chat"] = moved_chat(t["chat"], moved)
            changed = True
            if not t.get("afterTurn") and any(x is not t and x["chat"] == t["chat"] and not x.get("afterTurn") for x in mine):
                tasks.remove(t)  # (a go-on of it under its new id is queued already)
                mine.remove(t)
        return changed
    change_queue(cache_root, edit=edit)


def last_turn(path):
    """How a chat's newest turn (a prompt of yours or a reply; not tool
    results or notes) stands, from the end of its transcript: {"kind":
    "prompt" (no reply yet), "reply", "limit", "login" (stopped_by), "error"
    (an API error that isn't a limit: the connection lost, say) or
    "interrupted" (Claude's note that you interrupted it), "at", "ended":
    whether the turn is over}, or None."""
    try:
        size = path.stat().st_size
    except (OSError, AttributeError):
        return None
    nbytes = PEEK_TAIL_BYTES
    while True:
        turn = next((e for e in tail_entries(path, size, nbytes) if not e.get("isSidechain")
                     and (e["type"] == "assistant" or human_prompt(e) is not None or interrupted_note(e))), None)
        if turn is not None or nbytes >= size or nbytes >= PEEK_TAIL_MAX:
            break
        nbytes *= 4
    if turn is None:
        return None
    at = to_ms(turn.get("timestamp")) or 0
    if turn["type"] != "assistant":
        if human_prompt(turn) is None:  # (you pressed Esc: the turn is over, you took over)
            return {"kind": "interrupted", "at": at, "ended": True}
        return {"kind": "prompt", "at": at, "ended": False}
    stop = stopped_by(turn)
    if stop is not None:
        return dict(stop, at=stop.get("at") or at, ended=True)
    msg = turn.get("message") if isinstance(turn.get("message"), dict) else {}
    if turn.get("isApiErrorMessage") is True:
        return {"kind": "error", "at": at, "text": short_text(" ".join(message_text(msg).split()), 160), "ended": True}
    return {"kind": "reply", "at": at, "ended": msg.get("stop_reason") in TURN_ENDS}


def interrupted_note(e):
    """Is this entry Claude's note that you interrupted the turn ("[Request
    interrupted by user]", "… for tool use]")?"""
    return (e.get("type") == "user" and not e.get("isMeta")
            and message_text(e.get("message")).lstrip().startswith("[Request interrupted"))


def kept_step(k, turn, row, queued, limits, now_ms):
    """What to do now about the chat that keeps going k (keep.json's entry,
    changed in place: tries, note, error), whose newest turn is turn
    (last_turn), whose row in the status (its process) is row, and whose
    account's plan limits are limits: ("go on", when, why, prompt) to queue
    its go-on, "done" to let it go, or None (nothing for now)."""
    k["note"] = ""
    if queued:
        return None  # its go-on waits (or couldn't start, and says why)
    if row is not None and row.get("state") in ("working", "waiting"):
        return None  # at work, or waiting for you
    live = row is not None and row.get("pid") is not None
    # (open in a Claude Code panel, or in a session it was resumed in: ending that isn't up to the widget)
    in_tab = live and (row.get("entrypoint") == "claude-vscode" or row.get("sessionId") != row.get("chatId"))

    def go(start, why="", prompt=""):
        if in_tab:
            k["note"] = ("It's open in a Claude Code panel: it can't go on by itself while that's open"
                         if row.get("entrypoint") == "claude-vscode" else
                         "It's open in a chat it was resumed in: it can't go on by itself while that one is open")
            return None
        return "go on", int(start), why, prompt

    def again(why, prompt="", retry="retry"):
        tries = k.get("tries") or 0
        if in_tab:
            return go(now_ms)  # (says why it can't)
        if tries >= len(KEEP_RETRY_MINUTES):
            k.update(error=f"Gave up after {tries} tries: {why}", errorAt=now_ms)
            return None
        k["tries"] = tries + 1
        return go(now_ms + KEEP_RETRY_MINUTES[tries] * 60_000, retry, prompt)

    if k.get("cappedUntil"):  # the usage cap stopped it: on once that window resets
        return go(max(k["cappedUntil"] + 60_000, now_ms), "cap")
    if turn is None:
        return None
    at, went = turn["at"], k.get("wentOnAt") or 0
    if k.get("error"):
        if at <= (k.get("errorAt") or 0):
            return None  # it gave up; something new in the chat starts it over
        k.update(error="", errorAt=None, tries=0)
    if turn["kind"] == "limit" and at > went:
        s = limit_stop(turn, limits, now_ms)
        if not s.get("resetsAt") and not s.get("over"):
            # when it resets isn't known (out of usage credits, a limit with no
            # window on record): on after a pause, longer each time it hits it
            return again(turn.get("text") or "a usage limit", retry="")
        k["tries"] = 0
        return go(s["resetsAt"] + 60_000 if not s["over"] else now_ms)
    if turn["kind"] == "login":
        k["note"] = "Its account's login has expired: log in again, then it can go on"
        return None
    if turn["kind"] == "error" and at > went:
        return again(turn.get("text") or "an API error", RETRY_PROMPT)
    if went and at <= went:
        # nothing new since it went on: that didn't take
        return again("it didn't go on") if now_ms - went > KEEP_TAKE_MS else None
    if not turn["ended"] and not live:
        # a turn with no process to finish it: it broke off (its process ended in it)
        return again("its turn broke off") if now_ms - at > KEEP_TAKE_MS else None
    if turn["ended"] and at > max(went, k.get("since") or 0):
        return "done"
    if now_ms - max(at, went, k.get("since") or 0) > KEEP_IDLE_MS:
        return "done"  # (nothing new for days: let it go)
    return None


def cap_window(group, cap, now_ms):
    """The account's plan window that's at or past cap percent (of several,
    the one that resets last), or None."""
    best = None
    for w in ((group.get("limits") or group.get("accountLimits") or {}).get("windows") or []):
        pct, at = number(w.get("pct")), number(w.get("resetsAt"))
        if pct is not None and pct >= cap and at and at > now_ms and not w.get("reset") \
                and (best is None or at > best["resetsAt"]):
            best = w
    return best


def note_caps(groups, cap, now_ms):
    """Mark each account whose plan window is at the usage cap: group["cap"]
    = {"pct", "label", "key", "resetsAt"} (queued tasks wait for it), else None."""
    for g in groups:
        w = cap_window(g, cap, now_ms) if cap else None
        g["cap"] = {"pct": cap, "label": w.get("label") or "", "key": w.get("key") or "", "resetsAt": int(w["resetsAt"])} \
            if w else None


def look_after_kept(home, cache_root, extra_dirs, groups, now_ms, cap=0, moves=None):
    """Look after the chats that keep going, and stop the chats at work at
    the usage cap (see above). groups: this computer's accounts, as the
    status lists them. moves: the chats Claude moved to the background
    under a new id (chat_moves): a kept chat and its queued go-on follow
    it there, and each keeps the name its chat has now. Nothing when
    another copy is at it right now."""
    moves = moves or {}
    requeue_reached(cache_root)
    profiles = discover_profiles(home, extra_dirs)
    rows = {}
    for g in groups:
        for s in g.get("sessions", []):
            for i in (s.get("sessionId"), s.get("chatId")):
                if i and (i not in rows or s.get("pid") is not None):
                    rows[i] = s
    names = {i: s["name"] for i, s in rows.items() if isinstance(s.get("name"), str) and s["name"].strip()}
    follow_queue(cache_root, moves, names)
    queued = {(t.get("host") or "", t["chat"]) for t in load_queue(cache_root) if t.get("chat")}
    # (each host with chats that keep going: its last answer, read once)
    answers = {k["host"]: host_answer_for_keep(cache_root, k["host"]) for k in load_keep(cache_root)["chats"] if k["host"]}
    adds, stops = [], []

    def change(data):
        changed = False
        for mark, at in list(data["capped"].items()):
            if at <= now_ms:  # (that window is over)
                del data["capped"][mark]
                changed = True
        for g in groups:
            w = g.get("cap")
            mark = "|".join(g.get("profileKeys") or []) + "|" + (w["key"] if w else "")
            if not w or mark in data["capped"]:
                continue
            data["capped"][mark] = w["resetsAt"]
            changed = True
            for s in g.get("sessions", []):
                if s.get("pid") is not None and s.get("state") == "working":
                    stops.append(s)
                    for k in data["chats"]:
                        if k["chat"] in (s.get("chatId"), s.get("sessionId")):
                            k["cappedUntil"] = w["resetsAt"]
        for k in list(data["chats"]):
            if k["host"]:  # (an SSH host's or a container's)
                changed = look_after_host_kept(data, k, answers.get(k["host"]), queued, adds, now_ms) or changed
                continue
            before = dict(k)
            chat = moved_chat(k["chat"], moves)
            if chat != k["chat"]:  # (Claude moved it to the background under a new id: it keeps going there)
                if any(x is not k and x["chat"] == chat for x in data["chats"]):
                    data["chats"].remove(k)
                    changed = True
                    continue
                k["chat"] = chat
            if names.get(chat) and names[chat] != k.get("name"):
                k["name"] = clean_text(names[chat], 80)  # (as it's called now)
            profile = next((p for p in profiles if matches_profile(p, k["profile"])), None)
            path = transcript_path(profile, k["chat"]) if profile is not None else None
            g = next((g for g in groups if k["profile"] in (g.get("profileKeys") or [])), None)
            step = None if path is None else kept_step(
                k, last_turn(path), rows.get(k["chat"]), ("", k["chat"]) in queued,
                (g.get("limits") or g.get("accountLimits")) if g else None, now_ms)
            if path is None or step == "done":
                data["chats"].remove(k)
                changed = True
            elif step is not None:
                _, start, why, prompt = step
                adds.append(queue_entry(k["profile"], k.get("folder") or "", prompt, int(start), chat=k["chat"],
                                        account=(g.get("title") or "") if g else "", name=k.get("name") or "",
                                        why=why, now_ms=now_ms))
                k["cappedUntil"] = None
            changed = changed or k != before
        return changed

    if not change_keep(cache_root, change, wait=False):
        return
    for entry in adds:
        change_queue(cache_root, add=entry, once=True)
    if stops:
        in_background(lambda: stop_all(home, extra_dirs, stops))


def requeue_reached(cache_root):
    """A queued go-on (or task) of an SSH host or a container that couldn't
    start because that couldn't be reached ("unreachable": when; jump.py
    --start-queued) starts by itself once it has answered since (its last
    answer, host_answer_for_keep, is newer): its error goes, so it's due."""
    waiting = [t for t in load_queue(cache_root) if t.get("host") and number(t.get("unreachable"))]
    if not waiting:
        return
    answers = {h: host_answer_for_keep(cache_root, h) for h in {t["host"] for t in waiting}}

    def edit(tasks):
        changed = False
        for t in tasks:
            seen = answers.get(t.get("host") or "")
            if number(t.get("unreachable")) and seen and seen["at"] > t["unreachable"]:
                t.pop("unreachable")
                t["error"] = ""
                changed = True
        return changed
    change_queue(cache_root, edit=edit)


def host_answer_for_keep(cache_root, host):
    """host's last status answer, as remote.py keeps it (hosts/<host>.json,
    whichever copy of the widget asked): {"at": when it came, on this
    computer's clock; "offset": what to add to the host's times for this
    computer's; "result": the status there}, or None."""
    if not HOST_IDENT.match(host or ""):
        return None
    try:
        saved = read_json(cache_root / "hosts" / (host + ".json"))
    except (OSError, ValueError):
        return None
    answer = saved.get("answer") if isinstance(saved, dict) else None
    result = answer.get("result") if isinstance(answer, dict) and answer.get("ok") else None
    if not isinstance(result, dict) or not isinstance(result.get("groups"), list):
        return None
    return {"at": int(number(saved.get("at")) or 0), "offset": int(number(saved.get("offset")) or 0), "result": result}


def host_words(host):
    """How a note names an SSH host or a container (as remote.py's label)."""
    m = re.match(r"^(?:docker|podman|nerdctl):([^@]+)(?:@(.+))?$", host)
    return host if not m else (f"{m.group(1)} on {m.group(2)}" if m.group(2) else m.group(1))


def shifted(turn_or_limits, offset):
    """A host's last turn (last_turn) or plan limits with their times on
    this computer's clock (offset: answer's "offset")."""
    if not isinstance(turn_or_limits, dict) or not offset:
        return turn_or_limits
    out = dict(turn_or_limits)
    for f in ("at", "resets"):
        if isinstance(out.get(f), (int, float)) and not isinstance(out.get(f), bool) and out[f]:
            out[f] = int(out[f] + offset)
    if isinstance(out.get("windows"), list):
        out["windows"] = [dict(w, **{f: int(w[f] + offset) for f in ("resetsAt", "endedAt")
                                     if isinstance(w.get(f), (int, float)) and not isinstance(w.get(f), bool) and w[f]})
                          for w in out["windows"] if isinstance(w, dict)]
    return out


def look_after_host_kept(data, k, seen, queued, adds, now_ms):
    """look_after_kept for k, a chat of an SSH host or a container that
    keeps going: as its last answer (seen: host_answer_for_keep) says it
    stands. The host's status run looks up how each of its chats that keep
    going stands (--kept-chats: "keptTurns", kept_turns) and lists them
    while they keep going; all is judged as of when that answer came, so an
    answer from before a go-on never counts as one that didn't take. A go-on
    goes in the queue for host (adds), as one you queue there. Changes keep.json's
    data in place; whether it did."""
    before = dict(k)
    if seen is None or now_ms - seen["at"] > KEEP_HOST_STALE_MS:
        k["note"] = (f"Talpy Den hasn't heard from {host_words(k['host'])} for a while: "
                     "it can go on once that answers again")
        return k != before
    result = seen["result"]
    old = k["chat"]
    chat = moved_chat(old, result.get("moved") if isinstance(result.get("moved"), dict) else {})
    if chat != k["chat"]:  # (Claude moved it to the background there under a new id: it keeps going there)
        if any(x is not k and x["chat"] == chat and x["host"] == k["host"] for x in data["chats"]):
            data["chats"].remove(k)
            return True
        k["chat"] = chat
    turns = result.get("keptTurns") if isinstance(result.get("keptTurns"), dict) else {}
    if not isinstance(turns.get(chat), dict):
        return k != before  # (an answer from before it was kept: no word on it yet)
    if turns[chat].get("gone"):  # (its transcript is gone there)
        data["chats"].remove(k)
        return True
    groups = [g for g in result["groups"] if isinstance(g, dict)]
    rows = {}
    for s in (s for g in groups for s in g.get("sessions") or [] if isinstance(s, dict)):
        for i in (s.get("sessionId"), s.get("chatId")):
            if i and (i not in rows or s.get("pid") is not None):
                rows[i] = s
    g = next((g for g in groups if k["profile"] in (g.get("profileKeys") or [])), None)
    if rows.get(chat) and isinstance(rows[chat].get("name"), str) and rows[chat]["name"].strip():
        k["name"] = clean_text(rows[chat]["name"], 80)  # (as it's called now)
    offset = seen["offset"]
    limits = (g.get("limits") or g.get("accountLimits")) if g else None
    # (its go-on queued under the id it had counts too, until remote.py's check follows it: follow_host_moves)
    step = kept_step(k, shifted(turns[chat].get("turn"), offset), rows.get(chat),
                     (k["host"], chat) in queued or (k["host"], old) in queued, shifted(limits, offset), seen["at"])
    if step == "done":
        data["chats"].remove(k)
        return True
    if step is not None:
        _, start, why, prompt = step
        adds.append(queue_entry(k["profile"], k.get("folder") or "", prompt, int(start), host=k["host"],
                                account=(g.get("title") or "") if g else "", chat=chat, name=k.get("name") or "",
                                why=why, now_ms=now_ms))
    return k != before


def stop_all(home, extra_dirs, sessions):
    """Stop these chats at work, as the stop button does where they run (an
    interrupt in tmux: the chat stays open there)."""
    profiles = discover_profiles(home, extra_dirs)
    for s in sessions:
        try:
            if s.get("kind") == "bg" and valid_id(s.get("jobId")):
                profile = next((p for p in profiles if matches_profile(p, s.get("profileDir") or "")), None)
                if profile is not None:
                    stop_background(profile, s["jobId"], read_job([profile], s["jobId"]), home)
            elif s.get("tmux"):
                interrupt_chat_by_id(home, extra_dirs, s["sessionId"], s.get("profileDir"))
            else:
                stop_chat_by_id(home, extra_dirs, s["sessionId"], s.get("profileDir"), busy_ok=True)
        except Exception:  # (on with the others)
            pass


def in_background(task):
    """Run task in a process of its own once this one has answered (the
    widget waits until the status's output ends: it mustn't inherit it)."""
    try:
        pid = os.fork()
    except OSError:
        return
    if pid:
        return
    try:
        os.setsid()
        devnull = os.open(os.devnull, os.O_RDWR)
        for fd in (0, 1, 2):
            os.dup2(devnull, fd)
        task()
    except Exception:
        pass
    finally:
        os._exit(0)


# ---------------------------------------------------------------- plans
#
# A chat in plan mode writes its plan to <cfg>/plans/<slug>.md, the slug
# being the chat's (its transcript's entries carry it). Claude writes the
# file in place, so a plan hard-linked into several profiles (shared, like a
# chat: sharing.py) stays one file. Each account lists its plans, newest
# first, with the chat that made each one where it's still there.

PLANS_LISTED = 8
PLAN_TITLE_BYTES = 4096


def plan_path(profile, slug):
    return profile.path / "plans" / f"{slug}.md" if isinstance(slug, str) and PLAN_SLUG.match(slug) else None


def plan_title(path):
    """A plan's first heading (in its first 4 KB), else ''."""
    try:
        with open(path, "rb") as f:
            head = f.read(PLAN_TITLE_BYTES)
    except OSError:
        return ""
    for line in head.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if line.startswith("#"):
            return clean_text(line.lstrip("#").strip(), 120)
    return ""


def project_wins(project_path, account_path):
    """Whether a project's plan counts over an account's of the same name:
    two files of one name are one plan, the newer one (a chat that wrote its
    plan in the account's plans/ writes it into its project's plans folder
    once the project names one, and the old file stays). A tie goes to the
    account's (as before projects' plans were listed); a missing file loses."""
    ours, theirs = mtime(Path(project_path)) if project_path else None, mtime(Path(account_path)) if account_path else None
    return ours is not None and (theirs is None or ours > theirs)


def plan_of(profile, slug, ctx=None):
    """{"slug", "title", "path", "updatedAt", "inProject"} of the plan a chat
    made on this profile (with ctx: the one in a project's plans folder
    where there's none here or it's newer: project_wins), or None."""
    path, folder = plan_path(profile, slug), None
    if path is not None and ctx is not None:
        found, where = project_plan_of(ctx, slug)
        if found is not None and project_wins(found, path):
            path, folder = found, where
    try:
        st = path.stat() if path is not None else None
    except OSError:
        st = None
    if st is None or not path.is_file():
        return None
    return {"slug": slug, "title": plan_title(path) or slug, "path": str(path), "updatedAt": int(st.st_mtime * 1000),
            "inProject": folder is not None}


def plan_edited(plan_ms, transcript_mtime):
    """Was the plan changed after its chat last did anything (so not by
    Claude: by you, e.g. with the widget's edit button)?"""
    return isinstance(transcript_mtime, (int, float)) and plan_ms / 1000 > transcript_mtime + 2


class SlugCache:
    """Each transcript's slug (the name of the plan it would write), read from
    its end and kept in plans.json until the transcript grows."""

    VERSION = 1

    def __init__(self, path):
        self.path = path
        data = read_json(path)
        ok = isinstance(data, dict) and data.get("version") == self.VERSION
        self.old = data if ok else {}
        self.data = {"version": self.VERSION, "slugs": {}}
        self.changed = not ok

    def slug(self, path, st):
        """The transcript's newest slug, reading only what was appended since last time."""
        key = file_key(st)
        cached = self.data["slugs"].get(key, self.old.get("slugs", {}).get(key))
        size, slug = 0, ""
        if isinstance(cached, list) and len(cached) == 2 and isinstance(cached[0], int) \
                and 0 <= cached[0] <= st.st_size and isinstance(cached[1], str):
            size, slug = cached
        if size < st.st_size:
            slug = transcript_slug(path, st.st_size, size) or slug
            self.changed = True
        self.data["slugs"][key] = [st.st_size, slug]
        return slug or None

    def cached(self, st):
        """The slug noted for this transcript as it is, without reading it; None if there's none."""
        key = file_key(st)
        cached = self.data["slugs"].get(key, self.old.get("slugs", {}).get(key))
        if not (isinstance(cached, list) and len(cached) == 2 and cached[0] == st.st_size and isinstance(cached[1], str)):
            return None
        self.data["slugs"][key] = cached
        return cached[1] or None

    def save(self):
        kept = keep_unused(self.old, self.data, ("slugs",), time.time())
        if self.changed or kept or set(self.data["slugs"]) != set(self.old.get("slugs", {})):
            try:
                write_json_atomic(self.path, self.data)
            except OSError:
                pass


SLUG_LINE = re.compile(rb'"slug":\s*"([A-Za-z0-9][A-Za-z0-9_-]{0,127})"')


def transcript_slug(path, size, start=0):
    """The newest slug in a transcript's lines after byte start, looking at
    its last 64 KB first, then more (up to 1 MB) while there's none; None if
    there's none."""
    nbytes = 65536
    while True:
        begin = max(start, size - nbytes)
        try:
            with open(path, "rb") as f:
                f.seek(begin)
                chunk = f.read(size - begin)
        except OSError:
            return None
        found = SLUG_LINE.findall(chunk)
        if found:
            return found[-1].decode()
        if begin <= start or nbytes >= 1 << 20:
            return None
        nbytes *= 4


# A plan file a chat wrote itself (a progress log it was asked to keep in
# ~/.claude/plans, say) has no slug in any transcript. Its chat is the newest
# one that wrote the file (itself or by its subagents): the file_path of its
# Write, Edit or MultiEdit call, or what >, >> or tee writes to in its Bash
# call, by its full path (/home/you/.claude/plans/x.md, ~/.claude/plans/x.md,
# $HOME/...). A chat that only reads the file or names it, or quotes such a
# call in a tool's output (its quotes are escaped there), isn't its chat.
# It's looked for only by the Projects tab (week.py --projects: PlanWrites
# in its context) and only for the plans no slug matched and no project was
# noted for, in every transcript (you may have changed the file since its
# chat last did anything), the newest first. Each is read once, then only
# where it grew, at most PLAN_WRITES_BUDGET bytes in all at a time (the
# rest the next time: a first look at a long history stays quick). Once
# found, the chat is noted as a slug's would be.

PLAN_FILE = re.compile(rb"/plans/([A-Za-z0-9][A-Za-z0-9_-]{0,127})\.md(?![A-Za-z0-9_-])")
PATH_STOPS = frozenset(b" \t\r\n\"'`<>|;&()[],=*?\\:")  # (what ends a path in a command or a JSON string)
WRITE_CALL = re.compile(rb'"name"\s*:\s*"(?:Write|Edit|MultiEdit)"\s*,\s*"input"\s*:\s*\{')
BASH_CALL = re.compile(rb'"name"\s*:\s*"Bash"\s*,\s*"input"\s*:\s*\{')
FILE_PATH_VALUE = re.compile(rb'"file_path"\s*:\s*"$')
COMMAND_VALUE = re.compile(rb'"command"\s*:\s*"')
TO_FILE = re.compile(rb"(?:>|[\s|]tee(?:\s+-a)?)\s*(?:\\\"|')?$")  # (a shell command's end before the file it writes, "quoted" or 'quoted')
PLAN_FOLDER_BYTES = 1024  # the longest folder before /plans/ that counts
WRITE_CALL_BYTES = 61440  # how far before the file its Bash call may start
PLAN_WRITES_CHUNK = 1 << 20  # a transcript is read 1 MB at a time
PLAN_WRITES_OVERLAP = 65536  # read again before where a read ended (a call it cut)
PLAN_WRITES_KEPT = 100  # a transcript's last ones kept
PLAN_WRITES_BUDGET = 512 << 20  # the most a look reads (the rest: the next one)


def unescaped_quote(b, start):
    """Whether the bytes b have a " after start that no backslash escapes
    (the end of the JSON string they're in)."""
    q = b.find(b'"', start)
    while q >= 0:
        n = 0
        while q - n > start and b[q - n - 1] == 0x5C:
            n += 1
        if n % 2 == 0:
            return True
        q = b.find(b'"', q + 1)
    return False


def written_plan(buf, m, whole, home):
    """The full path of the plan file that a tool call in the bytes buf
    writes at the match m (PLAN_FILE), or None (home: the home folder,
    bytes). whole: buf starts where its file does (else a folder cut at its
    start is none)."""
    i = m.start()
    lo, j = max(0, i - PLAN_FOLDER_BYTES), i
    while j > lo and buf[j - 1] not in PATH_STOPS:
        j -= 1
    if j == lo and (lo > 0 or not whole):
        return None
    folder = buf[j:i]
    for prefix in (b"${HOME}", b"$HOME", b"~"):
        if folder == prefix or folder.startswith(prefix + b"/"):
            folder = home + folder[len(prefix):]
            break
    if not folder.startswith(b"/"):
        return None
    start = max(0, j - WRITE_CALL_BYTES)
    before = buf[buf.rfind(b"\n", start, j) + 1 or start:j]  # (the call's own line: a transcript's entry)
    k = before.rfind(b'"name"')  # (the nearest tool call's name: one quoted in a string has its quotes escaped)
    if k < 0:
        wrote = False
    elif FILE_PATH_VALUE.search(before[-64:]):
        wrote = WRITE_CALL.match(before, k) is not None
    elif TO_FILE.search(before[-24:]) and BASH_CALL.match(before, k):
        c = COMMAND_VALUE.search(before, k)
        wrote = c is not None and not unescaped_quote(before, c.end())
    else:
        wrote = False
    return os.path.normpath(folder.decode("utf-8", "replace") + "/plans/" + m.group(1).decode("ascii") + ".md") \
        if wrote else None


def plan_writes(path, start, end, home, found=()):
    """found, then the plan files a transcript's tool calls write
    (written_plan) in its bytes start..end, read PLAN_WRITES_CHUNK at a
    time (from a little before start: a call the last read cut): [path],
    each once, the one written last at the end, at most the last
    PLAN_WRITES_KEPT. None if it can't be read."""
    out = dict.fromkeys(found)
    pos = max(0, start - PLAN_WRITES_OVERLAP)
    try:
        with open(path, "rb") as f:
            f.seek(pos)
            tail = b""
            while pos < end:
                chunk = f.read(min(PLAN_WRITES_CHUNK, end - pos))
                if not chunk:
                    break
                buf = tail + chunk
                whole = pos - len(tail) == 0
                for m in PLAN_FILE.finditer(buf):
                    wrote = written_plan(buf, m, whole, home)
                    if wrote is not None:
                        out.pop(wrote, None)
                        out[wrote] = None
                pos += len(chunk)
                tail = buf[-PLAN_WRITES_OVERLAP:]
    except OSError:
        return None
    return list(out)[-PLAN_WRITES_KEPT:]


class PlanWrites:
    """The plan files each transcript's tool calls write (plan_writes), kept
    in plan-writes.json so a transcript is read once, then only where it
    grew, at most PLAN_WRITES_BUDGET bytes in all (budget) for one look:
    {file key: [bytes read, [paths]]}, a few dozen bytes for each
    transcript Claude keeps; an entry no look used for CACHE_KEEP_S (its
    transcript deleted, or no plan to look for) is dropped (keep_unused)."""

    VERSION = 1

    def __init__(self, path, home):
        self.path, self.home = path, os.fsencode(str(home))
        data = read_json(path)
        ok = isinstance(data, dict) and data.get("version") == self.VERSION and isinstance(data.get("files"), dict)
        self.old = data if ok else {}
        self.data = {"version": self.VERSION, "files": {}}
        self.changed = not ok
        self.budget = PLAN_WRITES_BUDGET

    def paths(self, f, st):
        """The plan files the transcript f (its stat st) writes (as far as
        it was read, once the budget is spent)."""
        key = file_key(st)
        cached = self.data["files"].get(key) or self.old.get("files", {}).get(key)
        size, found = 0, []
        if isinstance(cached, list) and len(cached) == 2 and isinstance(cached[0], int) \
                and 0 <= cached[0] <= st.st_size and isinstance(cached[1], list) \
                and all(isinstance(p, str) for p in cached[1]):
            size, found = cached
        if size < st.st_size and self.budget > 0:
            self.budget -= st.st_size - size
            more = plan_writes(f, size, st.st_size, self.home, found)
            if more is not None:
                size, found = st.st_size, more
                self.changed = True
        self.data["files"][key] = [size, found]
        return found

    def save(self):
        kept = keep_unused(self.old, self.data, ("files",), time.time())
        if self.changed or kept or set(self.data["files"]) != set(self.old.get("files", {})):
            try:
                write_json_atomic(self.path, self.data, private=True)
            except OSError:
                pass


def all_transcripts(ctx):
    """[(mtime, profile, path, stat)] of every chat transcript, newest first
    (once per check)."""
    found = getattr(ctx, "transcripts", None)
    if found is not None:
        return found
    found = []
    for p in ctx.profiles:
        try:
            files = list(p.path.glob("projects/*/*.jsonl"))
        except OSError:
            continue
        for f in files:
            if not valid_id(f.stem) or "." in f.stem:
                continue
            try:
                st = f.stat()
            except OSError:
                continue
            found.append((st.st_mtime, p, f, st))
    found.sort(key=lambda c: -c[0])
    ctx.transcripts = found
    return found


def account_plans(group, ctx, limit=PLANS_LISTED, starred=frozenset(), hidden=frozenset(), left_out=None):
    """The plans of an account's profiles, newest first: [{"key", "slug",
    "title", "path", "profileDir", "profile", "updatedAt", "shared", "chatId",
    "cwd", "cwdShort", "starred", "inProject", "projectFolder"}], the chat
    being the one that made it (where it's still there; None else), cwd its
    folder (else the one noted while it was there; "": no project known),
    projectFolder the folder that chat started in. With the plans in the
    projects' plans folders listed under this account (project_plan_owner):
    inProject, their project's folder as cwd, not shared (every account
    reads them). The first limit of them, then the starred ones (slugs in
    starred) that are older. The ones you hid (slugs in hidden) are left
    out, their slugs added to the set left_out."""
    by_key = {p.key: p for p in ctx.profiles}
    found, seen = [], set()
    for key in group["profileKeys"]:
        p = by_key.get(key)
        try:
            files = list(p.path.glob("plans/*.md")) if p is not None else []
        except OSError:
            continue
        for f in files:
            try:
                st = f.stat()
            except OSError:
                continue
            if not PLAN_SLUG.match(f.stem) or not f.is_file() or (st.st_dev, st.st_ino) in seen:
                continue
            seen.add((st.st_dev, st.st_ino))
            found.append((st.st_mtime, p, f, st, None))
    keys = set(group["profileKeys"])
    link_project_plans(ctx, None if limit > 0 else set(starred))
    found = [c for c in found if not counted_elsewhere(ctx, c[2], None)]
    for t, folder, f, st in project_plan_files(ctx):
        owner = project_plan_owner(ctx, f.stem, folder)
        if owner in keys and owner in by_key and not counted_elsewhere(ctx, f, folder):
            found.append((t, by_key[owner], f, st, folder))
    found.sort(key=lambda c: -c[0])
    if left_out is not None:
        left_out.update(c[2].stem for c in found if c[2].stem in hidden)
    found = [c for c in found if c[2].stem not in hidden]
    found = [c for i, c in enumerate(found) if i < limit or c[2].stem in starred]
    plans = []
    for t, p, f, st, folder in found:
        plans.append({
            "key": f"{p.key}/{f.stem}/project/plan" if folder else f"{p.key}/{f.stem}/plan",
            "slug": f.stem,
            "title": plan_title(f) or f.stem,
            "path": str(f),
            "profileDir": p.key,
            "profile": p.label,
            "updatedAt": int(t * 1000),
            # linked into another profile's plans too (sharing.py)
            "shared": folder is None and st.st_nlink > 1
                      and any(q.real != p.real and same_file(plan_path(q, f.stem), st) for q in ctx.profiles),
            "chatId": None, "chatProfileDir": None, "cwd": "", "cwdShort": "", "edited": False,
            "starred": f.stem in starred,
            "inProject": folder is not None,  # (in a project's plans folder: every account reads it)
            "projectFolder": folder or "",
        })
    if plans:
        find_plan_chats(plans, ctx)
    for pl in plans:
        if pl["inProject"]:  # (its project is where it is)
            pl["cwd"], pl["cwdShort"] = pl["projectFolder"], short_path(pl["projectFolder"], ctx.home)
    return plans


def counted_elsewhere(ctx, path, folder):
    """Whether another file of the plan's name is the one that counts
    (project_wins): an account's plan (folder None) a project's newer one
    of that name, a project's plan another project's newer one or an
    account's newer one. Two files of one name are one plan: one line,
    and every action takes the file it shows."""
    slug = path.stem
    project, where = project_plan_of(ctx, slug)
    if folder is None:
        return project is not None and project_wins(project, path)
    if project is not None and project != path:
        return True
    return any(not project_wins(path, plan_path(p, slug)) for p in ctx.profiles)


def same_file(path, st):
    try:
        other = path.stat() if path is not None else None
    except OSError:
        return False
    return other is not None and (other.st_dev, other.st_ino) == (st.st_dev, st.st_ino)


def find_plan_chats(plans, ctx):
    """The chat that made each plan: the newest transcript with its slug. It
    was active when the plan was written, so only transcripts changed since
    the oldest plan's time are read; older ones count with the slug noted
    for them then (a plan you changed since is newer than its chat). With
    the context's PlanWrites (the Projects tab), a plan (with its "path")
    no slug matched and no project was noted for has the chat that wrote
    its file (find_written_plan_chats)."""
    slugs = getattr(ctx, "slugs", None)
    if slugs is None:
        return
    noted, dirs = plan_projects_of(ctx), getattr(ctx, "plan_dirs", None)

    def found(pl, t, p, f, st):
        _, cwd, _ = ctx.links.chat_info(f, st)
        start = dirs.start_folder(f"{p.key}/{f.parent.name}", f) if dirs is not None else ""
        pl["chatId"], pl["chatProfileDir"] = f.stem, p.key
        pl["cwd"], pl["cwdShort"] = cwd, short_path(cwd, ctx.home) if cwd else ""
        pl["projectFolder"] = start or cwd
        pl["edited"] = plan_edited(pl["updatedAt"], t)
        noted.note(pl["slug"], cwd, start or cwd, f.stem, p.key)  # (it keeps its project once the chat is gone)

    wanted = {pl["slug"]: pl for pl in plans}
    oldest = min(pl["updatedAt"] for pl in plans) / 1000 - 60
    for t, p, f, st in all_transcripts(ctx):
        if not wanted:
            break
        slug = slugs.slug(f, st) if t >= oldest else slugs.cached(st)
        pl = wanted.pop(slug, None) if slug else None
        if pl is not None:
            found(pl, t, p, f, st)
    # The ones whose chat wasn't found: the folder noted while it was there,
    # and that chat if it's still there (a plan moved under another name)
    by_id, unknown = None, []
    for pl in wanted.values():
        e = noted.get(pl["slug"])
        if e is None:
            unknown.append(pl)
            continue
        pl["cwd"], pl["cwdShort"] = e["cwd"], short_path(e["cwd"], ctx.home)
        pl["projectFolder"] = e.get("project") or e["cwd"]
        if valid_id(e.get("chat")):
            if by_id is None:
                by_id = {f.stem: (t, p) for t, p, f, _st in reversed(all_transcripts(ctx))}
            t, p = by_id.get(e["chat"], (None, None))
            if p is not None:
                pl["chatId"], pl["chatProfileDir"] = e["chat"], p.key
                pl["edited"] = plan_edited(pl["updatedAt"], t)
    writes = getattr(ctx, "plan_writes", None)
    if unknown and writes is not None:
        find_written_plan_chats(unknown, ctx, writes, found)


def find_written_plan_chats(plans, ctx, writes, found):
    """The chat of each plan (with its "path") that no slug matched: the
    newest one that wrote its file (PlanWrites: by its own calls or its
    subagents'; the same file, whichever link or name it's written by).
    found(plan, mtime, profile, transcript, stat) takes it."""
    by_file = {}
    for pl in plans:
        try:
            st = os.stat(pl["path"]) if pl.get("path") else None
        except OSError:
            st = None
        if st is not None:
            by_file[(st.st_dev, st.st_ino)] = pl
    named = {}  # (each path written: its file, stat once)
    for t, p, f, st in all_transcripts(ctx):  # (newest first)
        if not by_file:
            break
        for g in [f] + subagent_transcripts(f):
            try:
                g_st = st if g is f else g.stat()
            except OSError:
                continue
            for path in writes.paths(g, g_st):
                key = named.get(path, 0)
                if key == 0:
                    try:
                        s = os.stat(path)
                        key = (s.st_dev, s.st_ino)
                    except OSError:
                        key = None
                    named[path] = key
                pl = by_file.pop(key, None) if key is not None else None
                if pl is not None:
                    found(pl, t, p, f, st)


# ---------------------------------------------------------------- plans in projects
#
# Claude writes a plan to <cfg>/plans/<slug>.md unless the setting
# plansDirectory names a folder inside the project (relative to the folder
# the chat started in; one that leads out of it counts as none). It takes
# the setting from the project's .claude/settings.local.json (in a git
# repository, the one in the repository's main folder: Claude reads it
# there), else the project's .claude/settings.json, else the account's
# settings.json (then it's for every project). Talpy Den lists the plans in
# that folder of each project chats started in (and of each folder Claude
# keeps in its list of projects, once their chats are deleted:
# plan_folders), and in the project's .claude/plans (where Move to project
# puts a plan when the project names no folder), each once: under the
# account whose chat made it, else the one with the newest chat there, with
# the project's folder. What it read of
# each project (the folder each projects/ folder is for, its git
# repository, its settings, its plan folders) is kept in plan-dirs.json:
# Claude writes a plan while a chat runs, so a check looks again at the
# projects with a chat in the last hour (and one a plan was just noted or
# moved to), the others every 10 minutes; it lists the plan folders that
# are there each time.
#
# A plan keeps its project once its chat is deleted: the folder of the chat
# that made it is noted the first time they're matched (plan-projects.json).

PLANS_SETTING = "plansDirectory"
PROJECT_PLANS_DIR = os.path.join(".claude", "plans")  # (Move to project, where the project names no folder)
LOCAL_SETTINGS = os.path.join(".claude", "settings.local.json")
PROJECT_SETTINGS = os.path.join(".claude", "settings.json")
PLAN_DIRS_CHECK_S = 3600  # the folder a plansDirectory value names is looked up again after this long
PROJECT_RECHECK_S = 600  # a project with no chat lately: its settings and folders are looked at again after this long
PROJECT_ACTIVE_S = 3600  # one with a chat this recent: at each check
START_FOLDER_BYTES = 262144


def inside(path, folder):
    """Is path folder or inside it (both normalised)?"""
    return path == folder or path.startswith(folder.rstrip("/") + "/")


def stat_inside(path, folder):
    """When path (folder or a place inside it, both normalised) stays inside
    folder once the links on its way are followed: its os.stat, or None
    where it isn't there (what's made there is a folder of its own); False
    when it leads out. An lstat for each part below folder (the last is its
    stat), the real paths only when one of them is a link."""
    if not inside(path, folder):
        return False
    there, st = folder, None
    for part in path[len(folder):].split("/"):
        if not part:
            continue
        there = os.path.join(there, part)
        try:
            st = os.lstat(there)
        except OSError:
            return None
        if st.st_mode & 0o170000 == 0o120000:  # (stat.S_ISLNK)
            if not inside(os.path.realpath(path), os.path.realpath(folder)):
                return False
            st = None
            break
    if st is None:
        try:
            return os.stat(path)
        except OSError:
            return None
    return st


def plans_dir_in(project, value):
    """The folder (absolute) a plansDirectory value names for the project
    folder, or None where Claude takes the account's plans/ instead: empty,
    not text, a backslash in it, or out of the project, also through a link
    (Claude's own check: the nearest part of it that is there, followed,
    stays inside the project)."""
    if not isinstance(value, str) or not value or "\\" in value or not project.startswith("/"):
        return None
    root = os.path.normpath(project)
    target = os.path.normpath(os.path.join(root, value))
    if not inside(target, root):
        return None
    real_root = os.path.realpath(root)
    there = target
    while not os.path.exists(there):
        up = os.path.dirname(there)
        if up == there:
            return None
        there = up
    return target if inside(os.path.realpath(there), real_root) else None


def canonical_git_root(folder):
    """The main folder of the git repository folder is in (of a worktree:
    its repository's), or "" outside one."""
    d = os.path.normpath(folder)
    while True:
        git = os.path.join(d, ".git")
        if os.path.isdir(git):
            return d
        if os.path.isfile(git):
            line = git_line(git) or ""
            gitdir = os.path.join(d, line[len("gitdir:"):].strip()) if line.startswith("gitdir:") else ""
            back = git_line(os.path.join(gitdir, "commondir")) if gitdir else None
            if back is None:
                return d  # (a submodule, or a worktree whose repository went)
            common = os.path.normpath(os.path.join(gitdir, back))
            return os.path.dirname(common) if os.path.basename(common) == ".git" else d
        up = os.path.dirname(d)
        if up == d:
            return ""
        d = up


def first_cwd(path):
    """The folder a chat started in: its transcript's first cwd (in its first 256 KB), or ''."""
    try:
        with open(path, "rb") as f:
            head = f.read(START_FOLDER_BYTES)
    except OSError:
        return ""
    for line in head.splitlines():
        if b'"cwd"' not in line:
            continue
        try:
            e = json.loads(line)
        except (ValueError, RecursionError):
            continue
        cwd = e.get("cwd") if isinstance(e, dict) else None
        if isinstance(cwd, str) and cwd.startswith("/"):
            return cwd
    return ""


class PlanDirs:
    """What the checks learned about the projects' plan folders, kept in
    plan-dirs.json: the folder each projects/<name> folder is for (its
    chats' first cwd), each project's plan folders (project_dirs), the
    folders its plansDirectory values name (looked up again after
    PLAN_DIRS_CHECK_S), and plansDirectory of each settings file (read
    again once the file changed). save=False: read it, never write it (the
    actions)."""

    VERSION = 1
    SECTIONS = ("folders", "dirs", "settings", "projects")

    def __init__(self, path, save=True):
        self.path, self.saving = path, save
        data = read_json(path)
        ok = isinstance(data, dict) and data.get("version") == self.VERSION \
            and all(isinstance(data.get(s), dict) for s in self.SECTIONS)
        self.old = data if ok else {}
        self.data = {"version": self.VERSION, **{s: {} for s in self.SECTIONS}}
        self.changed = not ok
        self.users = {}  # (a profile's own settings.json: read once per check)

    def _get(self, section, key):
        value = self.data[section].get(key)
        return self.old.get(section, {}).get(key) if value is None else value

    def _keep(self, section, key, value):
        if self.old.get(section, {}).get(key) != value:
            self.changed = True
        self.data[section][key] = value

    def start_folder(self, key, transcript):
        """The folder projects/<name> is for (key: "<profile key>/<name>"), from one of its transcripts."""
        cached = self._get("folders", key)
        folder = cached if isinstance(cached, str) and cached else first_cwd(transcript)
        if folder:
            self._keep("folders", key, folder)
        return folder

    def _checked(self, section, key, now, look):
        cached = self._get(section, key)
        if isinstance(cached, list) and len(cached) == 2 and isinstance(cached[0], str) \
                and isinstance(cached[1], (int, float)) and 0 <= now - cached[1] < PLAN_DIRS_CHECK_S:
            self._keep(section, key, cached)
            return cached[0]
        found = look()
        self._keep(section, key, [found, int(now)])
        return found

    def project_dirs(self, folder, now, again, look):
        """A project's plan folders (look(): project_plan_dirs), as last
        looked up unless that's PROJECT_RECHECK_S old, or again."""
        cached = self._get("projects", folder)
        ok = isinstance(cached, list) and len(cached) == 2 and isinstance(cached[0], list) \
            and all(isinstance(d, str) for d in cached[0]) and isinstance(cached[1], (int, float))
        if ok and not again and 0 <= now - cached[1] < PROJECT_RECHECK_S:
            self._keep("projects", folder, cached)
            return cached[0]
        found = look()
        # (the same as before: kept as it was, so a project at work doesn't make each check write the file)
        self._keep("projects", folder, cached if ok and again and cached[0] == found else [found, int(now)])
        return found

    def plans_dir(self, folder, value, now):
        """plans_dir_in(folder, value), or None."""
        if not isinstance(value, str) or not value:
            return None
        return self._checked("dirs", f"{folder}\n{value}", now, lambda: plans_dir_in(folder, value) or "") or None

    def setting(self, path):
        """(whether it's there, its value) of plansDirectory in a settings file."""
        try:
            st = os.stat(path)
        except OSError:
            return False, None
        stamp = [st.st_mtime_ns, st.st_size]
        cached = self._get("settings", path)
        if not (isinstance(cached, list) and len(cached) == 4 and cached[:2] == stamp):
            data = read_json(path, SETTINGS_MAX)
            there = isinstance(data, dict) and PLANS_SETTING in data
            value = data[PLANS_SETTING] if there and isinstance(data[PLANS_SETTING], str) else None
            cached = stamp + [there, value]
        self._keep("settings", path, cached)
        return bool(cached[2]), cached[3] if isinstance(cached[3], str) else None

    def user_setting(self, profile):
        if profile.key not in self.users:
            self.users[profile.key] = self.setting(str(profile.path / "settings.json"))
        return self.users[profile.key]

    def save(self):
        if not self.saving:
            return
        kept = keep_unused(self.old, self.data, self.SECTIONS, time.time())
        if self.changed or kept or any(set(self.data[s]) != set(self.old.get(s, {})) for s in self.SECTIONS):
            try:
                write_json_atomic(self.path, self.data, private=True)
            except OSError:
                pass


def plan_dirs_of(ctx):
    """The context's PlanDirs (one that's only read, where it has none)."""
    dirs = getattr(ctx, "plan_dirs", None)
    if dirs is None:
        dirs = ctx.plan_dirs = PlanDirs(cache_dir(ctx.home) / "plan-dirs.json", save=False)
    return dirs


def folder_settings(ctx, folder, has_claude=None):
    """[(where it comes from: "local" or "project", its value)] of the
    plansDirectory a project folder's own settings set, the one Claude takes
    first: its settings.local.json (in a git repository's main folder: Claude
    reads it there), its settings.json. has_claude False: the folder has no
    .claude (its own files aren't looked for)."""
    dirs = plan_dirs_of(ctx)
    if has_claude is None:
        has_claude = os.path.isdir(os.path.join(folder, ".claude"))
    root = canonical_git_root(folder)
    base = root if root and root != os.path.normpath(str(ctx.home)) else folder
    out = []
    if has_claude or base != folder:
        there, value = dirs.setting(os.path.join(base, LOCAL_SETTINGS))
        if there:
            out.append(("local", value))
    if has_claude:
        there, value = dirs.setting(os.path.join(folder, PROJECT_SETTINGS))
        if there:
            out.append(("project", value))
    return out


def project_settings(ctx, folder, profile):
    """(where it comes from: "local", "project", "user" or "", its value) of
    plansDirectory for the account's chats in the project folder, as Claude
    reads it: the project's settings.local.json, else its settings.json,
    else the account's own."""
    own = folder_settings(ctx, folder)
    if own:
        return own[0]
    there, value = plan_dirs_of(ctx).user_setting(profile)
    return ("user", value) if there else ("", None)


def linked_settings(path, project, home, doing="change a rule"):
    """Why Talpy Den won't change project's settings.local.json (path): it,
    or its .claude folder, is a link to somewhere else (a repo can ship one:
    the change would land in what it points to, an account's settings.json,
    say); None when it's the folder's own file."""
    if os.path.realpath(str(path)) == os.path.join(os.path.realpath(str(project)), ".claude", "settings.local.json"):
        return None
    return "%s is a link to another file: Talpy Den doesn't %s through a link" % (short_folder(str(path), home), doing)


def local_settings_file(ctx, folder):
    """The project's .claude/settings.local.json that Claude reads (in a git
    repository: the one in its main folder)."""
    root = canonical_git_root(folder)
    return os.path.join(root if root and root != os.path.normpath(str(ctx.home)) else folder, LOCAL_SETTINGS)


def project_plan_dirs(ctx, folder, keys=None):
    """[plans folder] of a project: where its plansDirectory puts the plans
    of the chats there of each account (of the profile keys; None: all),
    and its .claude/plans (not the home folder's: there it's ~/.claude's
    own). A project without a .claude costs a stat, or two in a git
    repository's subfolder."""
    dirs, now = plan_dirs_of(ctx), time.time()
    try:
        os.stat(os.path.join(folder, ".claude"))
        has_claude = True
    except OSError:
        has_claude = False
    own = folder_settings(ctx, folder, has_claude)
    values = [own[0][1]] if own else [v for there, v in (dirs.user_setting(p) for p in ctx.profiles
                                                          if keys is None or p.key in keys) if there]
    out = []
    for value in values:
        d = dirs.plans_dir(folder, value, now)
        if d and d not in out:
            out.append(d)
    if has_claude and os.path.normpath(folder) != os.path.normpath(str(ctx.home)):
        d = os.path.join(folder, PROJECT_PLANS_DIR)
        if d not in out:
            out.append(d)
    return out


def start_folders(ctx):
    """{folder: (when its newest chat changed, that chat's profile, the
    profile keys of its chats)} of the folders chats started in, but
    Claude's own and Talpy Den's (once per check)."""
    found = getattr(ctx, "start_folders", None)
    if found is not None:
        return found
    dirs, newest = plan_dirs_of(ctx), {}
    for t, p, f, _st in all_transcripts(ctx):  # (newest first)
        path = str(f)
        folder = path[:path.rfind("/")]
        key = (p.key, folder)
        if key not in newest:
            newest[key] = (t, p, f, folder[folder.rfind("/") + 1:])
    skip = not_projects(ctx)
    found = {}
    for (key, _d), (t, p, f, name) in newest.items():
        folder = dirs.start_folder(f"{key}/{name}", f)
        if not folder or any(inside(folder, s) for s in skip):
            continue
        if folder not in found:
            found[folder] = (t, p, {p.key})
        else:
            keys = found[folder][2] | {p.key}
            found[folder] = (t, p, keys) if t > found[folder][0] else found[folder][:2] + (keys,)
    ctx.start_folders = found
    return found


def not_projects(ctx):
    """Folders a chat runs in that aren't projects: Claude's own and Talpy Den's."""
    skip = list(getattr(ctx, "own_folders", None) or own_folders(ctx.profiles))
    if getattr(ctx, "usage_check", None):
        skip.append(ctx.usage_check)
    return skip


def plan_folders(ctx):
    """start_folders, and the folders Claude ran in that no chat here
    started in any more: Claude deletes a chat after cleanupPeriodDays (30
    by default) but keeps the folder in its list of projects (.claude.json's
    "projects": Profile.project_folders), so a project's plans folder is
    still read once its chats are gone. {folder: (when its newest chat
    changed (0: there's none), a profile that ran there, the profile keys
    that did)}, once per check; nothing more is read than the profiles'
    .claude.json, which every check reads anyway."""
    found = getattr(ctx, "plan_folders_found", None)
    if found is not None:
        return found
    found = dict(start_folders(ctx))
    known, more = {os.path.normpath(f) for f in found}, {}
    for p in ctx.profiles:
        for folder in getattr(p, "project_folders", ()):
            folder = os.path.normpath(folder)
            if folder in more:
                more[folder][2].add(p.key)
            elif folder not in known:
                more[folder] = (0, p, {p.key})
    if more:
        skip = not_projects(ctx)
        found.update((f, v) for f, v in more.items() if not any(inside(f, s) for s in skip))
    ctx.plan_folders_found = found
    return found


def project_plan_files(ctx):
    """[(mtime, project folder, path, stat)] of the plans in the projects'
    plan folders (project_plan_dirs of plan_folders), newest first, each
    file once; never an account's own plans/, a folder that leads out of
    its project through a link, nor a plan that is a link (a repo can ship
    them: to ~/.claude, a private key) (once per check)."""
    found = getattr(ctx, "project_plan_files", None)
    if found is not None:
        return found
    found, dirs_seen, seen, accounts = [], set(), set(), set()
    for p in ctx.profiles:
        try:
            st = os.stat(str(p.real / "plans"))
            accounts.add((st.st_dev, st.st_ino))
        except OSError:
            pass
    dirs, now = plan_dirs_of(ctx), time.time()
    noted = {}  # (a project a plan was noted for or moved to lately: looked at again)
    for e in list(plan_projects_of(ctx).plans.values()) + list(plan_projects_of(ctx).new.values()):
        if isinstance(e.get("at"), (int, float)) and e["at"] / 1000 > noted.get(e.get("project"), 0):
            noted[e.get("project")] = e["at"] / 1000
    for folder, (t, _p, keys) in sorted(plan_folders(ctx).items()):  # (a project before the ones inside it)
        again = t >= now - PROJECT_ACTIVE_S or noted.get(folder, 0) >= now - PROJECT_RECHECK_S
        for d in dirs.project_dirs(folder, now, again, lambda: project_plan_dirs(ctx, folder, keys)):
            if d in dirs_seen:
                continue
            dirs_seen.add(d)
            try:
                st = stat_inside(os.path.normpath(d), os.path.normpath(folder))  # (not one that leads out through a link)
                if not st or (st.st_dev, st.st_ino) in accounts:
                    continue
                entries = list(os.scandir(d))
            except OSError:
                continue
            for e in entries:
                if not e.name.endswith(".md") or not PLAN_SLUG.match(e.name[:-3]):
                    continue
                try:
                    if e.is_symlink():
                        continue
                    st = e.stat()
                except OSError:
                    continue
                if not stat_is_file(st) or (st.st_dev, st.st_ino) in seen:
                    continue
                seen.add((st.st_dev, st.st_ino))
                found.append((st.st_mtime, folder, Path(e.path), st))
    found.sort(key=lambda c: -c[0])
    ctx.project_plan_files = found
    return found


def stat_is_file(st):
    return st.st_mode & 0o170000 == 0o100000  # (stat.S_ISREG)


def project_plan_of(ctx, slug, folder=None):
    """(path, project folder) of the newest plan called slug in a project's
    plans folder (in folder's, if one is there), or (None, None)."""
    if folder is None:  # (the newest of each name, once per check)
        newest = getattr(ctx, "project_plan_newest", None)
        if newest is None:
            newest = {}
            for _t, d, f, _st in project_plan_files(ctx):
                newest.setdefault(f.stem, (f, d))
            ctx.project_plan_newest = newest
        return newest.get(slug, (None, None))
    hits = [(f, d) for _t, d, f, _st in project_plan_files(ctx) if f.stem == slug]
    return next(((f, d) for f, d in hits if d == folder), hits[0] if hits else (None, None))


def project_plan_owner(ctx, slug, folder):
    """The profile key a project's plan is listed under: of the chat that
    made it (as noted), else of the newest chat in the project, else of an
    account that ran there (plan_folders)."""
    keys = {p.key for p in ctx.profiles}
    noted = plan_projects_of(ctx).get(slug)
    if noted and noted.get("profile") in keys:
        return noted["profile"]
    _t, p, _keys = plan_folders(ctx).get(folder, (0, None, ()))
    return p.key if p is not None else ctx.profiles[0].key


class PlanProjects:
    """The folder of the chat that made each plan, noted when they're
    matched (plan-projects.json, changed under a lock: every copy of Talpy
    Den writes it), so a plan keeps its project once its chat is deleted:
    {slug: {"cwd": the chat's folder, "project": the folder it started in,
    "chat": its id, "profile": its profile key, "at": when}}."""

    FILE = "plan-projects.json"

    def __init__(self, cache_root, save=True):
        self.root, self.saving = cache_root, save
        self.plans = load_plan_projects(cache_root)
        self.new = {}

    def get(self, slug):
        return self.new.get(slug) or self.plans.get(slug)

    def note(self, slug, cwd, project, chat, profile):
        if not cwd:
            return
        entry = {"cwd": cwd, "project": project or cwd, "chat": chat or "", "profile": profile or ""}
        old = self.get(slug)
        if old is None or any(old.get(k) != v for k, v in entry.items()):
            self.new[slug] = dict(entry, at=int(time.time() * 1000))

    def save(self):
        if self.new and self.saving:
            try:
                change_plan_projects(self.root, put=self.new)
            except OSError:
                pass
        self.plans.update(self.new)
        self.new = {}


def plan_projects_of(ctx):
    found = getattr(ctx, "plan_projects", None)
    if found is None:
        found = ctx.plan_projects = PlanProjects(cache_dir(ctx.home), save=False)
    return found


def load_plan_projects(cache_root):
    data = read_json(cache_root / PlanProjects.FILE)
    plans = data.get("plans") if isinstance(data, dict) else None
    if not isinstance(plans, dict):
        return {}
    return {s: e for s, e in plans.items() if isinstance(s, str) and PLAN_SLUG.match(s) and isinstance(e, dict)
            and isinstance(e.get("cwd"), str) and e["cwd"].startswith("/")}


def change_plan_projects(cache_root, put=None, forget=(), rename=None):
    """Note plans' projects (put: {slug: entry}), forget some, or carry one
    over to another name (rename: (old, new)), under a lock."""
    private_dir(cache_root)
    with open(cache_root / "plan-projects.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        plans = load_plan_projects(cache_root)
        before = dict(plans)
        plans.update(put or {})
        for slug in forget:
            plans.pop(slug, None)
        if rename and rename[0] in plans:
            plans[rename[1]] = plans.pop(rename[0])
        if plans != before:
            write_json_atomic(cache_root / PlanProjects.FILE, {"plans": plans}, private=True)


def link_project_plans(ctx, wanted=None):
    """Match the projects' plans (of the slugs wanted; None: all) that have
    no noted project to the chats that made them, once per check: then each
    is listed under its chat's account (project_plan_owner)."""
    done = getattr(ctx, "project_plans_linked", None)
    if done is None:
        done = ctx.project_plans_linked = set()
    noted = plan_projects_of(ctx)
    todo = [{"slug": f.stem, "updatedAt": int(t * 1000), "chatId": None, "path": str(f)}
            for t, _d, f, _st in project_plan_files(ctx)
            if f.stem not in done and (wanted is None or f.stem in wanted) and noted.get(f.stem) is None]
    done.update(pl["slug"] for pl in todo)
    if todo:
        find_plan_chats(todo, ctx)


def find_project_plan(profiles, slug, home, cache_root=None, every=False):
    """(path, project folder) of a plan in a project's plans folder, for an
    action (the caches only read), or (None, None); every: [(path, project
    folder)] of each file of that name in one, newest first."""
    if not (isinstance(slug, str) and PLAN_SLUG.match(slug)) or home is None:
        return [] if every else (None, None)
    root = cache_dir(home) if cache_root is None else cache_root
    ctx = Context(home=home, profiles=profiles, plan_dirs=PlanDirs(root / "plan-dirs.json", save=False),
                  plan_projects=PlanProjects(root, save=False))
    if every:
        return [(f, d) for _t, d, f, _st in project_plan_files(ctx) if f.stem == slug]
    return project_plan_of(ctx, slug)


# ---------------------------------------------------------------- memories
#
# Claude keeps what it learns about you and your projects as memories: one
# Markdown file each, in <cfg>/projects/<folder>/memory/ (MEMORY.md is their
# index), with a name, a description and a type (user, feedback, project,
# reference) at the top. Each account lists its memories, newest first,
# after its own CLAUDE.md: your instructions for every chat on it (type
# "account"; often one file linked into each account's folder).

MEMORIES_LISTED = 30
MEMORY_HEAD_BYTES = 2048
MEMORY_FIELD = re.compile(r"^\s*(name|description|type):\s*(.*?)\s*$")


def memory_head(path):
    """{"name", "description", "type"} from the top of a memory file."""
    try:
        with open(path, "rb") as f:
            head = f.read(MEMORY_HEAD_BYTES).decode("utf-8", "replace")
    except OSError:
        return {}
    lines = head.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    out = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        m = MEMORY_FIELD.match(line)
        if m and m.group(1) not in out:
            value = m.group(2)
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
            out[m.group(1)] = value
    return out


def project_folder_of(project):
    """The folder a projects/<key> folder is for: Claude names it after the
    folder, every character but letters and digits made a "-", so it's
    found step by step on disk (the longest name that fits first); "" when
    it isn't there any more."""
    rest, path = project.name[1:] if project.name.startswith("-") else project.name, "/"
    while rest:
        try:
            names = sorted(os.listdir(path), key=len, reverse=True)
        except OSError:
            return ""
        step = next((n for n in names if (rest == mangle(n) or rest.startswith(mangle(n) + "-"))
                     and os.path.isdir(os.path.join(path, n))), None)
        if step is None:
            return ""
        path, rest = os.path.join(path, step), rest[len(mangle(step)) + 1:]
    return path


def mangle(name):
    return re.sub(r"[^A-Za-z0-9]", "-", name)


MEMORY_CWD_BYTES = 65536  # read of a transcript's first lines for the folder its chat ran in
MEMORY_CWD_FILES = 3


def memory_folder(project):
    """(folder, gone) of the memories in a projects/<key> folder: the folder
    it's for on disk (project_folder_of), else, when that was renamed, moved
    or deleted (gone), the one a chat filed there ran in, as the first lines
    of its transcript name it, else the key read back ("-" as "/")."""
    folder = project_folder_of(project)
    if folder:
        return folder, False
    try:
        transcripts = sorted(project.glob("*.jsonl"))[:MEMORY_CWD_FILES]
    except OSError:
        transcripts = []
    for path in transcripts:
        try:
            with open(path, "rb") as f:
                read = 0
                while read < MEMORY_CWD_BYTES:
                    line = f.readline(MEMORY_CWD_BYTES - read)
                    if not line:
                        break
                    read += len(line)
                    if b'"cwd"' not in line:
                        continue
                    try:
                        e = json.loads(line)
                    except (ValueError, RecursionError):
                        continue
                    cwd = e.get("cwd") if isinstance(e, dict) else None
                    if isinstance(cwd, str) and cwd.startswith("/") and mangle(cwd) == project.name:
                        return cwd, True
        except OSError:
            continue
    return "/" + (project.name[1:] if project.name.startswith("-") else project.name).replace("-", "/"), True


def memory_key(profile, path):
    """The key a memory file is listed by: <profile>/<project>/<name>/memory."""
    return f"{profile.key}/{path.parent.parent.name}/{path.stem}/memory"


def memory_via_link(path):
    """Whether a projects/<folder>/memory/<name>.md is reached through a link
    (the file, its memory/ or its projects/<folder>)."""
    try:
        return any(x.is_symlink() for x in (path, path.parent, path.parent.parent))
    except OSError:
        return False


def account_memories(group, ctx, limit=MEMORIES_LISTED, hidden=frozenset(), left_out=None):
    """The memories of an account's profiles, newest first: [{"key", "name",
    "description", "type", "path", "folder", "folderShort", "folderGone"
    (that folder isn't there any more: memory_folder), "profileDir",
    "profile", "updatedAt"}]. The ones you hid (keys in hidden) are left
    out, their keys added to the set left_out."""
    by_key = {p.key: p for p in ctx.profiles}
    ways = {}   # {(device, inode): [(mtime, profile, path)]}: each file, the ways it's reached
    for key in group["profileKeys"]:
        p = by_key.get(key)
        try:
            files = list(p.path.glob("projects/*/memory/*.md")) if p is not None else []
        except OSError:
            continue
        for f in files:
            try:
                st = f.stat()
            except OSError:
                continue
            if f.name != "MEMORY.md" and f.is_file():
                ways.setdefault((st.st_dev, st.st_ino), []).append((st.st_mtime, p, f))
    folders = {}

    def folder_of(project):
        if project not in folders:
            folders[project] = memory_folder(project)
        return folders[project]

    # A file reached more than one way (one projects/<folder>'s memory/ linked
    # to another's, either way round: kept for the chats of a folder that was
    # renamed, or shared by two) is listed once: by a folder that's still there,
    # else by the way that isn't through a link
    found = [min(c, key=lambda w: (folder_of(w[2].parent.parent)[1], memory_via_link(w[2]))) if len(c) > 1 else c[0]
             for c in ways.values()]
    found.sort(key=lambda c: -c[0])
    out = account_instructions(group, ctx)
    if hidden:
        hid = {m["key"] for m in out if m["key"] in hidden} | {memory_key(p, f) for _, p, f in found
                                                                  if memory_key(p, f) in hidden}
        if left_out is not None:
            left_out.update(hid)
        out = [m for m in out if m["key"] not in hid]
        found = [c for c in found if memory_key(c[1], c[2]) not in hid]
    for t, p, f in found[:limit]:
        head = memory_head(f)
        folder, gone = folder_of(f.parent.parent)
        out.append({
            "key": memory_key(p, f),
            "name": clean_text(head.get("name") or f.stem, 120),
            "description": clean_text(head.get("description"), 300),
            "type": head.get("type") if head.get("type") in ("user", "feedback", "project", "reference") else "",
            "path": str(f),
            "folder": folder,
            "folderShort": short_path(folder, ctx.home) if folder else "",
            "folderGone": gone,
            "profileDir": p.key,
            "profile": p.label,
            "updatedAt": int(t * 1000),
        })
    return out


def account_instructions(group, ctx):
    """The account's CLAUDE.md (each of its profiles', once), as memories."""
    by_key = {p.key: p for p in ctx.profiles}
    out, seen = [], set()
    for key in group["profileKeys"]:
        p = by_key.get(key)
        f = p.path / "CLAUDE.md" if p is not None else None
        try:
            st = f.stat() if f is not None else None
        except OSError:
            st = None
        if st is None or not f.is_file() or (st.st_dev, st.st_ino) in seen:
            continue
        seen.add((st.st_dev, st.st_ino))
        # (linked to a file outside the account's folder, or into another's: shared)
        shared = f.is_symlink() or st.st_nlink > 1
        out.append({
            "key": f"{p.key}/CLAUDE.md/memory", "name": "CLAUDE.md",
            "description": "Your instructions for every chat on this account" + (" (shared with other accounts)" if shared else ""),
            "type": "account", "path": str(f), "folder": "", "folderShort": "", "folderGone": False, "profileDir": p.key,
            "profile": p.label, "updatedAt": int(st.st_mtime * 1000),
        })
    return out


def memory_file(profiles, path):
    """path, when it's a memory file of one of the profiles (projects/*/memory/*.md,
    or its CLAUDE.md), else None."""
    try:
        real = Path(path).resolve()
    except (OSError, RuntimeError):
        return None
    if real.suffix != ".md" or not real.is_file():
        return None
    for p in profiles:
        projects = p.real / "projects"
        try:
            projects = projects.resolve()  # (it may be a link to a folder elsewhere, e.g. on another disk)
        except (OSError, RuntimeError):
            pass
        if real.parent.name == "memory" and real.parent.parent.parent == projects:
            return real
        if Path(path) in (p.path / "CLAUDE.md", p.real / "CLAUDE.md"):
            return Path(path)  # (by its own name: it may be a link to a shared file)
    return None


# ---------------------------------------------------------------- feedback on a plan
#
# You change a plan (its file) or comment on its lines (VS Code), then send
# that to the chat that made it, which revises the plan in plan mode. What
# you changed is told apart from what Claude wrote by Claude's own version
# of the plan, rebuilt from the chat's transcript (claude_plan): what it
# last wrote to the file (Write), with its edits since (Edit, MultiEdit),
# or the plan it presented (ExitPlanMode's "plan"), counting only the tool
# calls that went through.

PLAN_FEEDBACK_MAX = 90_000  # characters of a message
# ...and bytes of it once shell-quoted: the command that reopens its chat has
# it in one argument, of 128 KB at most (a character can take 3 bytes or 4)
PLAN_FEEDBACK_BYTES = 120_000
PLAN_TOOLS = ("Write", "Edit", "MultiEdit", "ExitPlanMode")


def claude_plan(transcript, slug):
    """The plan <slug>.md as Claude last wrote it, from its transcript; None
    when that can't be told (no full version, or an edit that doesn't fit)."""
    text, pending = None, {}
    name_end = f"/{slug}.md"  # (in <cfg>/plans, or a project's plansDirectory)
    try:
        with open(transcript, encoding="utf-8", errors="replace") as f:
            for line in f:
                if name_end not in line and not any(i in line for i in pending):
                    continue
                try:
                    e = json.loads(line)
                except (ValueError, RecursionError):
                    continue
                content = (e.get("message") or {}).get("content") if isinstance(e.get("message"), dict) else None
                for c in content if isinstance(content, list) else []:
                    if not isinstance(c, dict):
                        continue
                    if c.get("type") == "tool_use" and c.get("name") in PLAN_TOOLS and isinstance(c.get("input"), dict):
                        inp = c["input"]
                        where = inp.get("planFilePath") if c["name"] == "ExitPlanMode" else inp.get("file_path")
                        if isinstance(where, str) and where.endswith(name_end) and isinstance(c.get("id"), str):
                            pending[c["id"]] = (c["name"], inp)
                    elif c.get("type") == "tool_result" and c.get("tool_use_id") in pending:
                        name, inp = pending.pop(c["tool_use_id"])
                        if c.get("is_error") and name != "ExitPlanMode":
                            continue  # (refused: the file didn't change; a plan you didn't approve still is the file)
                        text = apply_plan_tool(text, name, inp)
    except OSError:
        return None
    return text


def plan_chat(profiles, slug, limit=2000):
    """(profile, transcript) of the chat that made a plan: the newest chat
    with its slug at its end (entries carry it), else (None, None)."""
    found = []
    for p in profiles:
        try:
            files = list(p.path.glob("projects/*/*.jsonl"))
        except OSError:
            continue
        for f in files:
            if not valid_id(f.stem):
                continue
            try:
                found.append((f.stat().st_mtime, p, f))
            except OSError:
                pass
    found.sort(key=lambda c: -c[0])
    needle = re.compile(rb'"slug":\s*"' + re.escape(slug.encode()) + rb'"')
    for _, p, f in found[:limit]:
        try:
            with open(f, "rb") as fh:
                fh.seek(max(0, fh.seek(0, 2) - 65536))
                if needle.search(fh.read()):
                    return p, f
        except OSError:
            continue
    return None, None


def apply_plan_tool(text, name, inp):
    """The plan after one of Claude's tool calls on it (None: lost track)."""
    if name == "ExitPlanMode":
        return inp["plan"] if isinstance(inp.get("plan"), str) and inp["plan"].strip() else text
    if name == "Write":
        return inp["content"] if isinstance(inp.get("content"), str) else None
    edits = inp.get("edits") if name == "MultiEdit" else [inp]
    for ed in edits if isinstance(edits, list) else [None]:
        old, new = (ed or {}).get("old_string"), (ed or {}).get("new_string")
        if text is None or not isinstance(old, str) or not isinstance(new, str) or old not in text:
            return None
        if new == "" and not old.endswith("\n") and old + "\n" in text:
            old += "\n"  # (as Claude's Edit does: what it takes out goes with the end of its line)
        text = text.replace(old, new) if ed.get("replace_all") else text.replace(old, new, 1)
    return text


def plan_feedback(plan, original, comments=(), home=None):
    """The message that gives Claude your feedback on a plan (a path): what
    you changed in it (a diff from original, Claude's version; None when that
    isn't known) and your comments [{"from", "to", "quote", "text"}] on its
    lines; "" when there's nothing to say."""
    import difflib

    def size(text):
        return len(shlex.quote(text).encode("utf-8", "replace"))

    with open(plan, encoding="utf-8", errors="replace") as f:
        current = f.read()
    where = short_folder(str(plan), home)
    parts = []
    if original is not None and original != current:
        diff = "".join(difflib.unified_diff(original.splitlines(True), current.splitlines(True),
                                            "the plan as you wrote it", "the plan as I changed it", n=2))
        if len(diff) > PLAN_FEEDBACK_MAX // 2 or size(diff) > PLAN_FEEDBACK_BYTES // 2:
            diff = diff[:PLAN_FEEDBACK_MAX // 2]
            while size(diff) > PLAN_FEEDBACK_BYTES // 2:
                diff = diff[:len(diff) * 9 // 10]
            diff += "\n… (more changes: read the file)\n"
        parts.append(f"I changed the plan file. My changes:\n\n```diff\n{diff.rstrip()}\n```")
    elif original is None:
        parts.append(f"I changed the plan file: read {where} again for my changes.")
    for i, c in enumerate(c for c in comments if isinstance(c, dict) and str(c.get("text") or "").strip()):
        first, last = c.get("from"), c.get("to")
        lines = (f"line {first}" if first == last else f"lines {first}–{last}") if isinstance(first, int) else "the plan"
        quote = "\n".join("> " + l for l in str(c.get("quote") or "").strip("\n").splitlines()[:12])
        parts.append(f"Comment {i + 1}, on {lines}:\n" + (quote + "\n" if quote else "") + str(c["text"]).strip())
    if not parts:
        return ""
    head = (f"Here is my feedback on your plan ({where}). Revise the plan with it, and stay in plan mode: "
            "show me the revised plan before you change anything else.")
    message = (head + "\n\n" + "\n\n".join(parts))[:PLAN_FEEDBACK_MAX]
    while size(message) > PLAN_FEEDBACK_BYTES:
        message = message[:len(message) * 9 // 10]
    return message


# ---------------------------------------------------------------- finding a chat
#
# Every chat whose name, folder or one of your prompts (history.jsonl) has
# all the words you look for, newest first. Transcripts are only read for
# their names (kept in links.json), so this is quick after the first time.

FIND_LIMIT = 30
HISTORY_ALL_BYTES = 16 << 20
SNIPPET_CHARS = 140


def history_all(profile):
    """The entries of a profile's prompt history (its last 16 MB)."""
    path = profile.path / "history.jsonl"
    try:
        size = path.stat().st_size
        with open(path, "rb") as f:
            f.seek(max(0, size - HISTORY_ALL_BYTES))
            lines = f.read().splitlines()
    except OSError:
        return []
    if size > HISTORY_ALL_BYTES:
        lines = lines[1:]
    entries = []
    for line in lines:
        try:
            e = json.loads(line)
        except (ValueError, RecursionError):
            continue
        if isinstance(e, dict):
            entries.append(e)
    return entries


def snippet(text, words):
    """The part of text around the first of words it has, on one line."""
    flat = " ".join(text.split())
    low = flat.casefold()
    at = min((i for i in (low.find(w) for w in words) if i >= 0), default=0)
    start = max(0, at - SNIPPET_CHARS // 3)
    part = flat[start:start + SNIPPET_CHARS]
    return ("…" if start > 0 else "") + part + ("…" if start + SNIPPET_CHARS < len(flat) else "")


def find_chats(home, cache_root, extra_dirs, query, limit=FIND_LIMIT):
    """{"ok", "results": [...], "more", "projects", "plans", "memories"}: the
    chats with every word of query in their name, folder or one of your
    prompts, newest first; and the project folders, plans and memories with
    them (find_more)."""
    words = [w.casefold() for w in query.split()]
    if not words:
        return {"ok": True, "results": [], "more": False}
    profiles = discover_profiles(home, extra_dirs)
    ctx = Context(home=home, profiles=profiles, links=LinkCache(cache_root / "links.json"),
                  plan_dirs=PlanDirs(cache_root / "plan-dirs.json"), plan_projects=PlanProjects(cache_root, save=False))
    prompts, used = {}, {}
    for p in profiles:
        for e in history_all(p):
            sid, text = e.get("sessionId"), e.get("display")
            if valid_id(sid) and isinstance(text, str) and text.strip():
                prompts.setdefault(sid, []).append(text)
                used[(p.real, sid)] = max(used.get((p.real, sid), 0), number(e.get("timestamp")) or 0)
    accounts = {}
    for gid, members in group_profiles(profiles):
        named = next((p for p in members if not p.is_default), members[0])
        plan = next((p.plan for p in members if p.plan), None)
        for p in members:
            accounts[p.key] = (short_id(gid), f"{named.label} · {plan}" if plan else named.label)
    results, seen, firsts, more = [], set(), set(), False
    for t, p, f, st in all_transcripts(ctx):
        inode = (st.st_dev, st.st_ino)
        if inode in seen:
            continue
        seen.add(inode)
        sid = f.stem
        said = prompts.get(sid, [])
        name, cwd, messages = ctx.links.chat_info(f, st)
        if not messages or not all(w in "\n".join([name, cwd, *said]).casefold() for w in words):
            continue
        # of a chat and its copies (Claude's forks start with its entries), the newest
        first = ctx.links.first_uuid(f)
        if first and first in firsts:
            continue
        firsts.add(first)
        if len(results) >= limit:
            more = True
            break
        home_p = p
        if st.st_nlink > 1:  # a shared chat: under the account it was used on last
            holders = [q for q in profiles if same_file(transcript_path(q, sid), st)]
            home_p = max(holders or [p], key=lambda q: used.get((q.real, sid), 0))
        hit = next((s for s in reversed(said) if all(w in s.casefold() for w in words)), None) \
            or next((s for s in reversed(said) if any(w in s.casefold() for w in words)), None)
        gid, account = accounts.get(home_p.key, ("", home_p.label))
        results.append({
            "key": f"{home_p.key}/{sid}/found",
            "sessionId": sid,
            "name": name or sid[:8],
            "cwd": cwd,
            "cwdShort": short_path(cwd, home),
            "lastActive": int(t * 1000),
            "profile": home_p.label,
            "profileDir": home_p.key,
            "groupId": gid,
            "account": account,
            "shared": st.st_nlink > 1,
            "match": snippet(hit, words) if hit and hit.strip() != name.strip() else "",
        })
    # (generatedAt: an SSH host's times go on the asking computer's clock)
    found = {"ok": True, "results": results, "more": more, "generatedAt": int(time.time() * 1000),
             **find_more(ctx, words, accounts)}
    ctx.links.save()
    ctx.plan_dirs.save()
    return found


FIND_MORE_LIMIT = 10
FIND_TEXT_BYTES = 200_000


def find_more(ctx, words, accounts):
    """{"projects", "plans", "memories"} with every word: the folders chats
    ran in (by their path; the newest chat's account), the plans (title or
    text) and Claude's memories (name, description or text), newest first."""
    def has(*texts):
        text = "\n".join(t for t in texts if t).casefold()
        return all(w in text for w in words)

    def body(path):
        try:
            with open(path, "rb") as f:
                return f.read(FIND_TEXT_BYTES).decode("utf-8", "replace")
        except OSError:
            return ""

    folders, seen = {}, set()
    for t, p, f, st in all_transcripts(ctx):
        if (st.st_dev, st.st_ino) in seen:  # (a chat shared between accounts: once)
            continue
        seen.add((st.st_dev, st.st_ino))
        _, cwd, messages = ctx.links.chat_info(f, st)
        if not cwd or not messages:
            continue
        entry = folders.get(cwd)
        if entry is None:
            if not has(short_path(cwd, ctx.home), cwd):
                folders[cwd] = None
                continue
            gid, account = accounts.get(p.key, ("", p.label))
            folders[cwd] = {"folder": cwd, "folderShort": short_path(cwd, ctx.home), "lastActive": int(t * 1000),
                            "chats": 0, "profileDir": p.key, "profile": p.label, "groupId": gid, "account": account}
        if folders[cwd] is not None:
            folders[cwd]["chats"] += 1
    projects = [e for e in folders.values() if e is not None][:FIND_MORE_LIMIT]

    plans, seen, by_key = [], set(), {p.key: p for p in ctx.profiles}
    files = []
    for p in ctx.profiles:
        try:
            files += [(p, f, None) for f in p.path.glob("plans/*.md")]
        except OSError:
            continue
    # (a project's: under the account its chat was on, else its newest chat's)
    files += [(by_key.get(project_plan_owner(ctx, f.stem, d)), f, d) for _t, d, f, _st in project_plan_files(ctx)]
    for p, f, folder in files:
        try:
            st = f.stat()
        except OSError:
            continue
        if p is None or not PLAN_SLUG.match(f.stem) or (st.st_dev, st.st_ino) in seen \
                or counted_elsewhere(ctx, f, folder):
            continue
        seen.add((st.st_dev, st.st_ino))
        title = plan_title(f) or f.stem
        if has(title, body(f)):
            gid, account = accounts.get(p.key, ("", p.label))
            plans.append({"key": f"{p.key}/{f.stem}/project/plan" if folder else f"{p.key}/{f.stem}/plan",
                          "slug": f.stem, "title": title, "path": str(f),
                          "profileDir": p.key, "profile": p.label, "groupId": gid, "account": account,
                          "updatedAt": int(st.st_mtime * 1000), "inProject": folder is not None,
                          "cwd": folder or "", "cwdShort": short_path(folder, ctx.home) if folder else ""})
    plans.sort(key=lambda x: -x["updatedAt"])

    memories = []
    for gid, members in group_profiles(ctx.profiles):
        for m in account_memories({"profileKeys": [p.key for p in members]}, ctx, limit=1000):
            if has(m["name"], m["description"], body(m["path"])):
                memories.append({**m, "groupId": short_id(gid), "account": accounts.get(m["profileDir"], ("", m["profile"]))[1]})
    memories.sort(key=lambda x: -x["updatedAt"])
    return {"projects": projects, "plans": plans[:FIND_MORE_LIMIT], "memories": memories[:FIND_MORE_LIMIT]}


# ---------------------------------------------------------------- opening sessions
#
# Shell commands that reopen, stop or start a chat with the right
# CLAUDE_CONFIG_DIR (used by jump.py here and by the widget for remote hosts).


def service_config_dir(profile):
    """CLAUDE_CONFIG_DIR value of the background service running for this profile, if any.

    The service is keyed by the config-dir *path* (its socket lives in
    /tmp/cc-daemon-<uid>/<sha256(path)[:8]>) but locks the real folder. When a
    folder has two names (~/.claude linked to ~/.claude-personal), a client
    using the other name waits forever at "Starting background service...".
    """
    status = read_json(profile.path / "daemon.status.json")
    if not isinstance(status, dict):
        return None
    pid = status.get("supervisorPid")
    if not is_alive({"pid": pid, "procStart": status.get("supervisorProcStart")}):
        return None
    try:
        env = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
    except OSError:
        return None
    value = next((e[len(b"CLAUDE_CONFIG_DIR="):].decode(errors="replace") for e in env
                  if e.startswith(b"CLAUDE_CONFIG_DIR=")), None)
    return value or str(Path.home() / ".claude")  # unset means the default path


def job_config_dir(profile, job):
    """The CLAUDE_CONFIG_DIR a background job was started with (its state.json
    providerEnv), if that is a name of this profile's folder."""
    env = (job or {}).get("providerEnv")
    value = env.get("CLAUDE_CONFIG_DIR") if isinstance(env, dict) else None
    if not isinstance(value, str) or not value:
        return None
    try:
        return value if Path(value).resolve() == profile.path.resolve() else None
    except OSError:
        return None


def names_profile(value, profile):
    """Does the config dir name value lead to this profile's folder now?"""
    try:
        return Path(value).expanduser().resolve() == profile.path.resolve()
    except (OSError, RuntimeError):
        return False


def config_dir_value(profile, home=None, job=None, for_job=False):
    """CLAUDE_CONFIG_DIR to run claude with for this profile, or None to unset it.

    Always named explicitly (a terminal's shell may export another one): the
    running service's own name if one runs, else the name the job was started
    with (a service started under another name of the folder leaves the job's
    worker and the service apart), else ~/.claude when it links to this
    profile (what terminals and VS Code use with linked profiles), else the
    profile's folder. Only a plain (unlinked) ~/.claude runs without the
    variable: its account file is ~/.claude.json, which Claude reads only
    when CLAUDE_CONFIG_DIR is unset.

    A service started as ~/.claude keeps that name after you switch the link
    to another profile. Attaching to or stopping one of its jobs (for_job)
    still goes through it; a new or resumed chat is this profile's, so it
    gets a name that still leads here (else it would open on the account the
    link points to now).
    """
    default = (home or Path.home()) / ".claude"
    if profile.is_default and not profile.path.is_symlink():
        return None
    service = service_config_dir(profile)
    if service is not None and not for_job and not names_profile(service, profile):
        service = None
    path = service or job_config_dir(profile, job)
    if path is None:
        linked_here = default.is_symlink() and default.resolve() == profile.path.resolve()
        path = str(default if linked_here else profile.path.resolve())
    return path


def trusted_folders(profile, home=None):
    """The folders Claude's "do you trust this folder?" question was answered
    yes for (in this profile's account file)."""
    home = home or Path.home()
    data = read_json(profile.path / ".claude.json")
    if profile.is_default and not profile.path.is_symlink() and not (data or {}).get("projects"):
        data = read_json(home / ".claude.json")
    projects = (data or {}).get("projects")
    if not isinstance(projects, dict):
        return set()
    return {k for k, v in projects.items() if isinstance(v, dict) and v.get("hasTrustDialogAccepted") is True}


def git_root(folder):
    for q in (folder, *folder.parents):
        if (q / ".git").exists():
            return q
    return None


def main_repository(root):
    """The folder Claude keeps a git repository's settings and trust under:
    for a worktree of another repository (its .git a file naming a folder in
    that one's .git/worktrees, which names it back) that repository's, else
    root itself."""
    text = git_line(root / ".git")  # (a repository's own .git is a folder: None)
    if not text or not text.startswith("gitdir:"):
        return root
    try:
        gitdir = Path(os.path.normpath(root / text[7:].strip()))
        common, back = git_line(gitdir / "commondir"), git_line(gitdir / "gitdir")
        if common is None or back is None:
            return root
        common, back = Path(os.path.normpath(gitdir / common)), Path(os.path.normpath(gitdir / back))
        if gitdir.parent != common / "worktrees" or back.resolve() != root.resolve() / ".git":
            return root
        return common.parent if common.name == ".git" else common
    except (OSError, ValueError):  # (ValueError: a NUL in a path)
        return root


def git_line(path):
    """What a git file (.git, commondir, gitdir) says, from its start; None
    when it isn't a plain file (a project unpacked from an archive can link
    one to a device or a pipe: never read)."""
    data = read_plain(path, 4096, head=True)
    return data.decode("utf-8", "replace").strip() if data is not None else None


def folder_trusted(profile, folder, home=None, trusted=None):
    """Has Claude's trust question been answered yes for folder, or (as
    Claude looks) for a folder above it, within its git repository if it's in
    one, or for the repository a worktree belongs to (Claude asks once for a
    repository and its worktrees: a chat that went on in one of its own, in
    .claude/worktrees, is trusted there)? Claude never saves it for the home
    folder, so it asks there every time. trusted: trusted_folders(profile),
    if read already."""
    trusted = trusted_folders(profile, home) if trusted is None else trusted
    if not trusted or not isinstance(folder, str) or not folder.startswith("/"):
        return False
    path = Path(folder)
    if path == (home or Path.home()):
        return False
    root = git_root(path)
    if root is not None and root != (home or Path.home()) and str(main_repository(root)) in trusted:
        return True
    for q in (path, *path.parents):
        if str(q) in trusted:
            return True
        if q == root:
            return False
    return False


# Claude refuses attach, stop, logs, rm and --bg ("'attach' is disabled by
# CLAUDE_CODE_DISABLE_AGENT_VIEW") while this is set: a desktop may have it
# for every program, and new chats in terminals get it (new_chat_command)
NO_AGENT_VIEW = "CLAUDE_CODE_DISABLE_AGENT_VIEW"


def config_env(profile, home=None, job=None, for_job=False):
    """Shell words that set (or unset) CLAUDE_CONFIG_DIR for this profile;
    for a background session's command (for_job), without NO_AGENT_VIEW."""
    value = config_dir_value(profile, home, job, for_job)
    if for_job:
        return f"env -u {NO_AGENT_VIEW} " + ("-u CLAUDE_CONFIG_DIR" if value is None else f"CLAUDE_CONFIG_DIR={shlex.quote(value)}")
    return "env -u CLAUDE_CONFIG_DIR" if value is None else f"CLAUDE_CONFIG_DIR={shlex.quote(value)}"


def claude_words(claude):
    """Shell words that run claude: its name or path, with its folder first on
    PATH when Node lives there too (an npm install under nvm runs
    `#!/usr/bin/env node`, and a terminal's shell may not have that folder)."""
    folder = os.path.dirname(claude)
    if folder and os.path.isfile(os.path.join(folder, "node")):
        return f'PATH={shlex.quote(folder)}:"$PATH" {shlex.quote(claude)}'
    return shlex.quote(claude)


def claude_command(profile, args, home=None, job=None, folder=None, claude="claude", for_job=False):
    """Shell command running claude with args on this profile, in folder."""
    command = (f"{config_env(profile, home, job, for_job)} {claude_words(claude)} "
               f"{' '.join(shlex.quote(a) for a in args)}")
    if isinstance(folder, str) and folder and not folder_trusted(profile, folder, home):
        # The question that comes up has "No, exit" preselected: say what it is
        note = (f"Claude will ask whether you trust {short_folder(folder, home)} before it reopens this chat. "
                "Choose \"Yes, I trust this folder\" to continue; \"No, exit\" (preselected) closes it.")
        command = f"printf '%s\\n\\n' {shlex.quote(note)}; {command}"
    return command


def attach_command(profile, job_id, home=None, job=None, claude="claude"):
    """Shell command that attaches to a background job of this profile."""
    return claude_command(profile, ["attach", job_id], home, job, (job or {}).get("cwd"), claude, for_job=True)


def resume_command(profile, session_id, home=None, folder=None, claude="claude"):
    """Shell command that reopens a finished chat on this profile."""
    return claude_command(profile, ["--resume", session_id], home, None, folder, claude)


MODEL_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9._\[\]-]{0,79}$")  # an alias (opus, sonnet, fable) or a model's full name
EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")
# claude --effort ultracode: xhigh with ultracode on (Claude Code 2.1.312+; a
# chat woken with it notes ultra_effort_enter at its next message, and one
# woken with --effort xhigh after it ultra_effort_exit: live-checked, 2.1.318)
ULTRACODE = "ultracode"
# claude --permission-mode's ("manual" is newer Claude's name for "default",
# which older ones on SSH hosts know only by that)
PERMISSION_MODES = ("default", "acceptEdits", "plan", "auto", "dontAsk", "bypassPermissions")


def chat_options(model=None, effort=None, mode=None):
    """claude's options for a new chat's model, reasoning effort and
    permission mode (none for Claude's own defaults); ValueError for one
    that isn't."""
    words = []
    if model:
        if not MODEL_NAME.match(model):
            raise ValueError(f"Not a model name: {model}")
        words += ["--model", model]
    if effort:
        if effort not in EFFORT_LEVELS + (ULTRACODE,):
            raise ValueError(f"Not an effort level: {effort} (it's low, medium, high, xhigh, max or ultracode)")
        words += ["--effort", effort]
    if mode:
        mode = "default" if mode == "manual" else mode
        if mode not in PERMISSION_MODES:
            raise ValueError(f"Not a permission mode: {mode} (it's {', '.join(PERMISSION_MODES)})")
        words += ["--permission-mode", mode]
    return words


# A picture pasted into a new chat's task is saved in the cache's images/
# (jump.py --paste-image; an SSH host's chat gets a copy in the host's,
# remote.py --put-image), and the task names it: [Image: /…/images/NAME.png].
# Outside the chat's folder, Claude would ask before it opens it: a chat whose
# task names one starts with that folder added. Pictures go after
# IMAGES_KEEP_DAYS, by when their chats have long read them (a task waits a
# week at most).
IMAGES_KEEP_DAYS = 30


def images_dir(home):
    return cache_dir(home) / "images"


def picture_options(home, text):
    """claude's options for a chat whose task names a pasted picture: its
    folder (one word: --add-dir FOLDER would take the prompt as a second folder)."""
    folder = str(images_dir(home))
    return [f"--add-dir={folder}"] if folder + os.sep in (text or "") else []


def new_chat_command(profile, home=None, claude="claude", options=()):
    """Shell command starting a new chat on this profile (options: claude's,
    e.g. chat_options'). With background sessions around, plain `claude` opens
    the agent view (where a task becomes a new background session): ask for a
    normal chat."""
    return (f"CLAUDE_CODE_DISABLE_AGENT_VIEW=1 {config_env(profile, home)} {claude_words(claude)}"
            + "".join(" " + shlex.quote(w) for w in options))


def login_command(profile, home=None, claude="claude"):
    """Shell command logging this profile in to a Claude account: Claude's
    own `claude auth login`, which keeps the login in the profile's folder."""
    note = (f"Log in to Claude for {profile.label} ({short_folder(str(profile.path), home)}): sign in with the "
            "account this folder is for. Claude opens your browser; where it can't (over ssh), open the address "
            "it shows and paste the code you get back here.")
    return f"printf '%s\\n\\n' {shlex.quote(note)}; {config_env(profile, home)} {claude_words(claude)} auth login"


def stop_command(profile, job_id, home=None, job=None, claude="claude"):
    """Shell command stopping a background job (its conversation is kept)."""
    return f"{config_env(profile, home, job, for_job=True)} {claude_words(claude)} stop {shlex.quote(job_id)}"


def short_folder(folder, home=None):
    home = str(home or Path.home())
    return "~" + folder[len(home):] if folder == home or folder.startswith(home + "/") else folder


# ---------------------------------------------------------------- starting a task
#
# A new chat can start with a task, its first prompt (maybe about one of the
# account's plans): in a terminal (`claude "<task>"`, which sends it at once),
# or in the background (`claude --bg "<task>"`: Claude's background service
# runs it and it's listed right away). The background needs the folder
# trusted already: Claude refuses otherwise ("Workspace not trusted"), and
# always in the home folder.

TASK_PLAN_MAX = 100_000  # bytes of a plan that go into a prompt
# ...as long as the prompt fits in one argument (128 KB) once quoted for an
# SSH host's terminal: in the host's command, its sh -c (posix) and the ssh line
TASK_ARG_MAX = 120_000
TASK_PLAN_CUT = "\n\n(The plan goes on in that file.)"
BACKGROUND_WAIT = 60  # seconds `claude --bg` gets (it may start Claude's background service first)
# What a Claude session puts into the environment of what it runs: a claude
# started with them would count as part of that session
SESSION_ENV = ("CLAUDECODE", "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_EXECPATH",
               "CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN", "CLAUDE_CODE_SESSION_ATTENDED",
               "CLAUDE_CODE_SESSION_ID", "CLAUDE_EFFORT", "CLAUDE_PID", "CLAUDE_JOB_DIR")
SHORT_ID = re.compile(r"\b([0-9a-f]{8})\b")
ONE_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")


def find_plan(profiles, slug, profile_key=None, home=None):
    """The plan file <cfg>/plans/<slug>.md (on the profile profile_key, else
    any), or (with home) the one called slug in a project's plans folder
    (find_project_plan) where there's none or it's newer (project_wins: the
    one the plan's line shows), or None."""
    found = None
    for p in profiles:
        if profile_key and not matches_profile(p, profile_key):
            continue
        path = plan_path(p, slug)
        if path is not None and path.is_file():
            found = path
            break
    project = find_project_plan(profiles, slug, home)[0] if home is not None else None
    return project if project is not None and project_wins(project, found) else found


def task_prompt(text, plan=None, home=None, fits=None):
    """A task's first prompt: what you wrote, and the plan (a path) it's
    about, cut until fits(prompt) (fits_in_a_terminal by default)."""
    text = (text or "").strip()
    if plan is None:
        return text
    with open(plan, "rb") as f:
        data = f.read(TASK_PLAN_MAX + 1)
    body, where = data[:TASK_PLAN_MAX].decode("utf-8", "replace"), short_folder(str(plan), home)
    return fitting_plan_prompt(text, body, where, fits or fits_in_a_terminal, len(data) > TASK_PLAN_MAX)


def fits_in_a_terminal(prompt):
    """Does prompt fit in one argument once quoted for an SSH host's terminal?"""
    quoted = shlex.quote(posix(prompt_word(prompt)))  # (each quote makes a ' 4 more characters, and posix more)
    return len(quoted.encode("utf-8", "replace")) <= TASK_ARG_MAX


def fitting_plan_prompt(text, body, where, fits, cut=False):
    """plan_prompt, with the plan cut at a line's end (and saying so) until fits(prompt)."""
    while True:
        prompt = plan_prompt(text, body.rstrip() + TASK_PLAN_CUT if cut else body, where)
        if fits(prompt) or not body:
            return prompt
        shorter = body[:len(body) * 9 // 10]
        body, cut = shorter[:shorter.rfind("\n") + 1] or shorter, True  # at a line's end


def plan_prompt(text, body, where):
    """A first prompt about a plan: your text (else "Implement this plan."),
    then the plan, which is saved as where."""
    return f"{(text or '').strip() or 'Implement this plan.'}\n\nThe plan (saved as {where}):\n\n{body.strip()}\n"


def prompt_arg(prompt):
    """The prompt as an argument claude takes as its prompt, not an option
    nor, one word alone, one of its commands (`claude update`, `claude doctor`)."""
    return " " + prompt if prompt.startswith("-") or ONE_WORD.fullmatch(prompt) else prompt


def prompt_word(prompt):
    return shlex.quote(prompt_arg(prompt))


# What every login shell (sh, bash, zsh, fish, csh, tcsh) leaves as it is in
# a single-quoted word, and sh in a double-quoted one
POSIX_PLAIN = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 +,-./:;=?@_^~#&|<>()[]{}*")


def posix(command):
    """command for an SSH host's login shell, run by sh: the commands the
    widget builds (`cd … 2>/dev/null; VAR=… claude …`) are POSIX shell, and
    the login shell may be fish or csh, which read a single-quoted word their
    own way (fish: a backslash before another or a '; csh: no newline,
    !history). So it goes as one word with none of that in it: sh's printf
    makes the characters other than POSIX_PLAIN from octal escapes."""
    data = command.encode()
    if all(chr(b) in POSIX_PLAIN for b in data) and not command.startswith("-"):
        return "sh -c " + shlex.quote(command)
    escaped = "".join(chr(b) if chr(b) in POSIX_PLAIN and (i or b != ord("-")) else "\\%03o" % b
                      for i, b in enumerate(data))
    return "sh -c " + shlex.quote('eval "$(printf "%s")"' % escaped)


def task_command(profile, prompt, home=None, claude="claude", options=()):
    """Shell command starting a chat on this profile with prompt sent as its first message."""
    return f"{new_chat_command(profile, home, claude, options)} {prompt_word(prompt)}"


UNTRUSTED = "Claude doesn't trust "   # (how start_background says it: a folder Claude hasn't been told it may trust)


def start_background(profile, folder, prompt, home=None, claude="claude", wait=BACKGROUND_WAIT, prefix=(),
                     resume=None, options=(), notes=None):
    """Start a background session on this profile in folder, with prompt:
    (ok, message, its short id or None). prefix: words claude runs behind,
    e.g. systemd-run's, so a background service it starts lives on its own
    (not in the widget's group of processes, which a restart of the desktop
    shell ends: jump.scope_prefix). resume: the id of a chat it goes on
    with (claude --bg --resume: the same chat, if nothing has it open).
    options: claude's, e.g. chat_options' (going on with a chat: only
    go_on_options', else Claude would start a copy of it). notes: a list
    that gets the notes claude printed (say, that it started a copy).
    prompt None, going on with a chat (resume): woken with no message, idle
    till one comes (Claude 2.1.318: "idle — send a prompt to start")."""
    import subprocess
    home = home or Path.home()
    if prompt is None and not resume or prompt is not None and not prompt.strip():
        return False, "Write what Claude should do first", None
    if not os.path.isdir(folder):
        return False, f"The folder {short_folder(folder, home)} isn't there", None
    if not folder_trusted(profile, folder, home):
        where = "your home folder" if Path(folder) == home else short_folder(folder, home)
        return False, (f"{UNTRUSTED}{where} yet, and a background chat can't ask: start a chat there "
                       "in a terminal once (Claude asks whether you trust it), or pick a project folder"), None
    env = {k: v for k, v in os.environ.items() if k not in SESSION_ENV and k != NO_AGENT_VIEW}
    value = config_dir_value(profile, home, for_job=True)  # through the service's own name
    if value is None:
        env.pop("CLAUDE_CONFIG_DIR", None)
    else:
        env["CLAUDE_CONFIG_DIR"] = value
    folder_bin = os.path.dirname(claude)
    if folder_bin and os.path.isfile(os.path.join(folder_bin, "node")):
        env["PATH"] = folder_bin + os.pathsep + env.get("PATH", "")
    argv = [*prefix, claude, "--bg", *(["--resume", resume] if resume else []), *options,
            *([prompt_arg(prompt)] if prompt is not None else [])]
    try:
        r = subprocess.run(argv, cwd=folder, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=wait)
    except OSError as exc:
        return False, f"Couldn't run claude: {exc}", None
    except subprocess.TimeoutExpired:
        return False, f"claude --bg didn't answer within {wait} s", None
    out = (r.stdout or b"").decode("utf-8", "replace")
    err = (r.stderr or b"").decode("utf-8", "replace")
    if r.returncode != 0:
        lines = [l.strip() for l in (err + "\n" + out).splitlines() if l.strip()]
        return False, lines[-1] if lines else f"claude --bg failed (exit code {r.returncode})", None
    found = SHORT_ID.findall(out)
    job = found[-1] if found else None
    if notes is not None:
        notes.extend(l.strip() for l in err.splitlines() if l.strip().startswith("note:"))
    return True, (f"Started in the background on {profile.label}" + (f" ({job})" if job else "")), job


def run_task(home, extra_dirs, background, folder, profile_key, text, plan_slug=None, plan_profile=None,
             claude=None, model=None, effort=None, mode=None):
    """A task on the profile profile_key in folder (here or on an SSH host,
    --start-task / --task-command), with that model, effort and permission
    mode: started in
    the background, or the shell command that starts it in a terminal.
    {"ok", "message", "id" | "command"}."""
    profiles = discover_profiles(home, extra_dirs)
    profile = next((p for p in profiles if matches_profile(p, profile_key)), None)
    if profile is None:
        return {"ok": False, "message": f"No Claude profile called {profile_key}"}
    options = chat_options(model, effort, mode) + picture_options(home, text)
    plan = None
    if plan_slug:
        plan = find_plan(profiles, plan_slug, plan_profile, home)
        if plan is None:
            return {"ok": False, "message": "That plan isn't there any more"}
    prompt = task_prompt(text, plan, home)
    folder = folder if isinstance(folder, str) and folder.startswith("/") else str(home)
    claude = claude or find_claude(home, ask_shell=True)
    if background:
        ok, message, job = start_background(profile, folder, prompt, home, claude, options=options)
        return {"ok": ok, "message": message, "id": job}
    command = (task_command(profile, prompt, home, claude, options) if prompt
               else new_chat_command(profile, home, claude, options))
    return {"ok": True, "message": "", "command": in_folder(folder, command)}


CONTINUE_PROMPT = "The usage limit has reset: go on where you stopped."
# The permission modes a chat goes on in, as it was. Not bypassPermissions:
# Claude refuses to start a background session in it unless you accepted it
# in a way it counts (and a go-on that doesn't start is worse than one that
# asks before it acts).
GO_ON_MODES = ("default", "manual", "acceptEdits", "plan", "auto", "dontAsk")


def go_on_options(mode, model=None, effort=None):
    """claude's options for going on with a chat in the background (claude
    --bg --resume) as a background session of its own: its permission mode,
    model and reasoning effort (None: not known), so that session saves them
    (respawnFlags) and goes on with them each time it's woken. With none,
    the first go-on keeps the chat's mode, but the session saves only the
    model the account's settings name, and a later wake comes back in
    Claude's default mode and effort. Not for a background session of it
    that's there and settled: Claude wakes that one with the options it
    saved, and any given here would start a copy of it."""
    mode = "default" if mode == "manual" else mode
    return (["--permission-mode", mode] if mode in GO_ON_MODES else []) + chat_options(model, effort)


SAVED_OPTIONS = {"--permission-mode": "mode", "--model": "model", "-m": "model", "--effort": "effort"}


def saved_flags(flags):
    """{"mode", "model", "effort"}: those a background job's saved options
    (its state.json's respawnFlags, what Claude wakes it with) name."""
    found = {}
    if not isinstance(flags, list):
        return found
    for i, flag in enumerate(flags):
        name, eq, value = flag.partition("=") if isinstance(flag, str) else ("", "", "")
        if name not in SAVED_OPTIONS:
            continue
        if not eq:
            value = flags[i + 1] if i + 1 < len(flags) and isinstance(flags[i + 1], str) else ""
        if value and not value.startswith("-"):
            found[SAVED_OPTIONS[name]] = value
    return found


def chat_model(home, profile, chat_id, path=None):
    """(model, effort) a chat last ran on, each None when not known: the
    model of its last reply (path: its transcript), e.g. "claude-opus-5-5",
    as its newest status-line snapshot names it if that's the same model (it
    may say which context window, [1m]); the effort as that snapshot names
    it (where its row's tag takes it from: attach_snapshot)."""
    model, effort = last_model(path) if path is not None else None, None
    for _, snap_path in snapshot_paths(cache_dir(home) / "statusline", profile, [chat_id]):
        snap = read_json(snap_path)
        if isinstance(snap, dict):
            part = lambda key: snap.get(key) if isinstance(snap.get(key), dict) else {}
            named, effort = part("model").get("id"), part("effort").get("level")
            if isinstance(named, str) and (model is None or named.split("[")[0] == model):
                model = named
            break
    return (model if isinstance(model, str) and MODEL_NAME.match(model) else None,
            effort if effort in EFFORT_LEVELS else None)


def last_model(path):
    """The model of a chat's last reply (not a stand-in like <synthetic>), or None."""
    try:
        size = path.stat().st_size
    except (OSError, AttributeError):
        return None
    nbytes = PEEK_TAIL_BYTES
    while True:
        for e in tail_entries(path, size, nbytes):
            msg = e.get("message") if isinstance(e.get("message"), dict) else {}
            if e["type"] == "assistant" and not e.get("isSidechain") and model_label(msg.get("model")):
                return msg["model"]
        if nbytes >= size or nbytes >= PEEK_TAIL_MAX:
            return None
        nbytes *= 4


def replace_options(flags, model=None, effort=None):
    """claude's options (a job's respawnFlags) with the model and effort
    given in place of the ones they name (None: as they are; "": none, so
    Claude's default)."""
    drop = ({"--model", "-m"} if model is not None else set()) | ({"--effort"} if effort is not None else set())
    out, i = [], 0
    while i < len(flags):
        name = flags[i].partition("=")[0] if isinstance(flags[i], str) else ""
        if name in drop:
            i += 1 if "=" in flags[i] else 2
            continue
        out.append(flags[i])
        i += 1
    return out + chat_options(model or None, effort or None)


# A model or effort picked in Talpy Chat for a chat with no background job of
# its own (it last ran in a terminal, now closed: chatpick.py): its next wake
# from here goes on with them (go_on_with), and its job has them from then on
PICKED_FILE = "chat-options.json"


def picked_options(home, chat_id):
    """{"model"?, "effort"?} picked in Talpy Chat for a chat's next wake, or {}."""
    data = read_json(state_dir(cache_dir(home)) / PICKED_FILE)
    got = data.get(chat_id) if isinstance(data, dict) else None
    return {k: v for k, v in got.items() if k in ("model", "effort") and isinstance(v, str)} \
        if isinstance(got, dict) else {}


def keep_picked(home, chat_id, model=None, effort=None, drop=False):
    """Keep a chat's picked model and effort (None: as they are; "": Claude's
    default) for its next wake, or drop them (it woke with them)."""
    path = state_dir(cache_dir(home)) / PICKED_FILE
    data = read_json(path)
    data = data if isinstance(data, dict) else {}
    if drop:
        if chat_id not in data:
            return
        data.pop(chat_id)
    else:
        now = dict(data[chat_id]) if isinstance(data.get(chat_id), dict) else {}
        now.update({k: v for k, v in (("model", model), ("effort", effort)) if v is not None})
        data[chat_id] = dict(now, at=int(time.time() * 1000))
    write_json_atomic(path, data, private=True)


def has_settings_flag(flags):
    """Do claude's options name settings of their own (--settings)?"""
    return any(f == "--settings" or f.startswith("--settings=") for f in flags if isinstance(f, str))


def hook_settings(flags):
    """The settings of its own (--settings) a background job's saved options
    (respawnFlags) give it when they're Talpy Chat's permission hook for it
    (they name PERMISSION_HOOK_FILE), or None: a copy Claude makes of that
    chat is given them too, so its prompts still reach Talpy Chat. Settings
    of your own aren't carried."""
    if not isinstance(flags, list):
        return None
    for i, flag in enumerate(flags):
        if not isinstance(flag, str):
            continue
        name, eq, value = flag.partition("=")
        if name != "--settings":
            continue
        if not eq:
            value = flags[i + 1] if i + 1 < len(flags) and isinstance(flags[i + 1], str) else ""
        if PERMISSION_HOOK_FILE in value:
            return value
    return None


def saved_options(state_path, chat_id, mode, model, effort, settings=None):
    """Have a chat's background job (its state.json) wake in its permission
    mode, on its model and effort: those its saved options (respawnFlags)
    lack are added (a copy Claude made of a chat saves only the model its
    account's settings name, though it runs in the chat's mode), as Claude
    adds them itself on a mode change, /model and /effort in it; the ones it
    has are its own and stay. settings: settings of its own (claude
    --settings, JSON: Talpy Chat's permission hook for it), added when it has
    none. Only while it's settled (no process has it) and in the shape it
    should have. Whether its options carry them now."""
    import shutil
    job = read_json(state_path)
    flags = job.get("respawnFlags") if isinstance(job, dict) and job.get("sessionId") == chat_id else None
    if not isinstance(flags, list) or not all(isinstance(f, str) for f in flags):
        return False
    have = saved_flags(flags)
    mode = "default" if mode == "manual" else mode
    add = (["--permission-mode", mode] if mode in GO_ON_MODES and "mode" not in have else []) \
        + chat_options(None if "model" in have else model, None if "effort" in have else effort) \
        + (["--settings", settings] if settings and not has_settings_flag(flags) else [])
    if add:
        tmp = state_path.with_name(f".{state_path.name}.{os.getpid()}.tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(dict(job, respawnFlags=flags + add), f)
            shutil.copymode(state_path, tmp)
            os.replace(tmp, state_path)
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            return False
    return True


WAKE_WAIT = 8  # seconds a wake that waited for another one gives that one's session to show
_WAKES = {}  # (chat id, thread) -> how many times that thread holds wake_lock for it


@contextlib.contextmanager
def wake_lock(home, chat_id):
    """One wake of a chat at a time: claude --bg --resume while another
    wake's session isn't listed yet, or is held by Claude's background
    service, starts a copy (Talpy Chat's window in Plasma and its tab in VS
    Code sending to one stopped chat within a second or two, Keep going, a
    queued go-on). An flock on <state>/wake-<chat id>.lock around the wake
    (pane.py send, continue_chat), which the thread holding it takes again
    without waiting (send's continue_chat). Yields whether it waited for
    another: that one may just have woken the chat, so the caller looks for
    its session first (wake_settle) and replies to it. No lock (nothing
    waits) when its file can't be made, or for what isn't a chat id."""
    import threading
    key = (chat_id, threading.get_ident())
    if _WAKES.get(key) or not valid_id(chat_id or "") or len(chat_id) < 36:
        _WAKES[key] = _WAKES.get(key, 0) + 1
        try:
            yield False
        finally:
            _WAKES[key] -= 1
            if not _WAKES[key]:
                del _WAKES[key]
        return
    fd = None
    try:
        state = state_dir(cache_dir(home))
        private_dir(state)
        fd = os.open(str(state / f"wake-{chat_id}.lock"), os.O_CREAT | os.O_RDWR | getattr(os, "O_CLOEXEC", 0), 0o600)
    except OSError:
        pass
    waited = False
    if fd is not None:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            waited = True
            fcntl.flock(fd, fcntl.LOCK_EX)
    _WAKES[key] = 1
    try:
        yield waited
    finally:
        del _WAKES[key]
        if fd is not None:
            os.close(fd)  # (lets go of the lock; the file stays, a few bytes a chat, as the hook's requests do)


def wake_settle(home, extra_dirs, chat_id, wait=WAKE_WAIT):
    """After waiting for another wake of a chat (wake_lock): wait (at most
    wait seconds) for a session that has it open to be listed, as Claude
    lists a chat it just woke a moment after claude --bg answers. Whether
    one is."""
    deadline = time.time() + wait
    profiles = discover_profiles(home, extra_dirs)
    while True:
        if any(e.get("sessionId") == chat_id and not e.get("spare") for e, _, _ in live_entries_all(profiles)):
            return True
        if time.time() >= deadline:
            return False
        time.sleep(0.1)


def continue_chat(home, extra_dirs, profile_key, chat_id, folder=None, text="", claude=None, prefix=(),
                  wait=None, force=False, ends_at=None, settings=None):
    """Go on with a chat a usage limit stopped, now that the limit has reset
    (a queued one: jump.py --start-queued; here or on an SSH host,
    --continue-chat): in the background on its account, with text (else
    CONTINUE_PROMPT) as your next message, in its permission mode, on its
    model and effort (go_on_options). A background session that has it
    open idle (or whose turn the limit ended, at work on its background
    commands alone) takes the message in where it is (reply_to_background):
    a terminal that shows it stays on it. Else a session that has it open
    idle ends first (end_for_handover), then claude --bg --resume goes on
    with the same chat, once Claude's background service has let go of it.
    {"ok", "message", "id"}; ok with no message when it went on
    already (its newest turn isn't the limit's any more): nothing to do.
    force: go on whatever its newest turn (a chat that keeps going whose turn
    broke off, or that the usage cap stopped).
    ends_at (ms): a session whose turn the limit ended but that's at work on
    its background commands (background_work) is waited for until then:
    {"ok": False, "waits": True, "commands", "endsAt"}; from then on they're
    ended first (end_background_work), and its answer names them ("ended").
    settings: settings of its own it goes on with (claude --settings, JSON:
    Talpy Chat's permission hook for it), unless its background job has some
    already: written into the job's saved options when it's woken (any
    option given would start a copy), else given. None given, a copy Claude
    makes of it gets the hook its job saved (hook_settings).
    One wake of a chat at a time (wake_lock): one that came while another
    woke it waits for that one's session (wake_settle), and takes the
    message in there or leaves it at work."""
    with wake_lock(home, chat_id) as waited:
        if waited:
            wake_settle(home, extra_dirs, chat_id)
        return go_on_with(home, extra_dirs, profile_key, chat_id, folder, text, claude, prefix, wait, force,
                          ends_at, settings)


def go_on_with(home, extra_dirs, profile_key, chat_id, folder, text, claude, prefix, wait, force, ends_at,
               settings):
    """continue_chat's go-on, under its lock."""
    profiles = discover_profiles(home, extra_dirs)
    profile = next((p for p in profiles if matches_profile(p, profile_key)), None)
    if profile is None:
        return {"ok": False, "message": f"No Claude profile called {profile_key}"}
    # (Claude moved it to the background under a new id: it goes on there, never as the old id
    # again, which would be a second copy of the conversation at work)
    now_id = continuation(home, extra_dirs, profile.key, chat_id)
    moved, chat_id = now_id != chat_id, now_id
    if moved:
        profile = next((p for p in [profile] + profiles if transcript_path(p, chat_id) is not None), profile)
    path = transcript_path(profile, chat_id)
    if path is None:
        return {"ok": False, "message": "That chat isn't on this account any more"}
    peek = chat_peek(path) or {}
    limited = (peek.get("stopped") or {}).get("kind") == "limit"
    if not force and not limited:
        return {"ok": True, "message": ""}
    if moved and not limited and any(
            e.get("sessionId") == chat_id and session_state(e) in ("working", "waiting") for e, _, _ in live_entries_all(profiles)):
        return {"ok": True, "message": ""}  # (where it moved to, it's at work: nothing to do)
    # (its newest entries name none: a chat in the Claude Code panel names it at its first prompt only)
    mode = peek.get("mode") or scan_mode(path, file_size(path))
    if not (isinstance(folder, str) and os.path.isdir(folder)):
        folder = chat_folder(path) or str(home)
    claude = claude or find_claude(home, ask_shell=True)
    prompt = (text or "").strip() or CONTINUE_PROMPT
    # (a background session that has it open takes the message in, as `claude agents` answers one: it goes
    # on where it is, its background commands too, and a terminal attached to it isn't ended. Not one
    # that asks you something, or at work on more than the background commands a limit left running)
    live = live_background(profiles, chat_id)
    if live is not None and (session_state(live[0]) == "idle" or limited and session_state(live[0]) == "working"):
        entry, runs_on = live
        ok, _ = reply_to_background(runs_on, entry["jobId"], prompt)
        if ok:
            return {"ok": True, "message": f"Went on in its background chat on {runs_on.label} ({entry['jobId']})",
                    "id": entry["jobId"]}
    busy = background_work(profiles, chat_id) if limited and ends_at is not None else None
    if busy is not None:
        entry, runs_on, commands = busy
        if time.time() * 1000 < ends_at:
            return {"ok": False, "waits": True, "commands": commands, "endsAt": int(ends_at),
                    "message": "It waits for its background commands to finish"}
        ok, message = end_background_work(home, entry, runs_on, claude)
        if not ok:
            return {"ok": False, "message": f"Couldn't end its background commands: {message}"}
    else:
        ok, message = end_for_handover(home, profiles, chat_id, claude)
        if not ok:
            return {"ok": False, "message": message}
    # (claude --bg --resume starts a copy while a process still has the chat open, or while Claude's
    # background service still holds its session: the one it would wake, and the one that was stopped)
    state = profile.path / "jobs" / chat_id[:8] / "state.json"
    record = read_json(state)
    saved = record.get("daemonShort") if isinstance(record, dict) else None
    shorts = {chat_id[:8]} | {s for s in (saved, live[0]["jobId"] if live else None) if valid_id(s)}
    services = [profile] + ([live[1]] if live and live[1] is not profile else [])
    held = lambda: any(e.get("sessionId") == chat_id for e, _, _ in live_entries_all(profiles)) \
        or daemon_holds(services, sorted(shorts))
    deadline = time.time() + (END_WAIT if wait is None else wait)
    holding = held()
    while holding and time.time() < deadline:
        time.sleep(0.2)
        holding = held()
    settled = not holding
    # The options a background job of it saved (respawnFlags) are its own (Claude rewrites them on
    # a mode change, /model and /effort in it): they win, and its transcript and status line only
    # fill in what they lack. A job of it that's settled is woken with them, given none here (any
    # would start a copy), once what they lack is added to them (saved_options: a copy Claude made
    # saved only the model the settings name, and woken with that it comes back in the default
    # mode and effort). One still held after the wait, or another chat's under its short id, is
    # copied by Claude whatever is given: the copy is given the job's own (and a picture your
    # message names can be opened then).
    guess_model, guess_effort = chat_model(home, profile, chat_id, path)
    own_job = isinstance(record, dict) and record.get("sessionId") == chat_id
    flags = saved_flags(record.get("respawnFlags")) if own_job else {}
    mode = flags.get("mode") or mode
    model, effort = flags.get("model") or guess_model, flags.get("effort") or guess_effort
    # (a model or effort you picked in Talpy Chat for it while it had no job of its own: "" is Claude's default)
    picked = picked_options(home, chat_id)
    if "model" in picked:
        model = picked["model"] or None
    if "effort" in picked:
        effort = picked["effort"] or None
    wakes = own_job and settled
    if settings is None and own_job and not wakes:
        settings = hook_settings(record.get("respawnFlags"))   # (a copy of a chat Talpy Chat hooked keeps the hook)
    carried = not wakes or not (mode or model or effort or settings) \
        or saved_options(state, chat_id, mode, model, effort, settings)
    options = [] if wakes else go_on_options(mode, model, effort) + (["--settings", settings] if settings else []) \
        + picture_options(home, text)
    notes = []
    ok, message, job = start_background(profile, folder, prompt, home, claude, prefix=prefix, resume=chat_id,
                                        options=options, notes=notes)
    if ok and picked:
        keep_picked(home, chat_id, drop=True)   # (they're in its job now)
    if ok:
        named = (model_label(model) or (model.capitalize() if model.isalpha() else model)) if model else None
        how = " · ".join(w for w in (named, effort) if w) if carried else ""
        message = f"Went on in the background on {profile.label}" + (f" ({how})" if how else f" ({job})" if job else "")
        if not carried:
            message += ", with the model and effort Claude saved for it"
        if job and any("started a copy" in n for n in notes):
            # (still held after the wait, or its job ended a moment too late: the latter's copy runs
            # in its mode, but saved only the model; its next go-on adds the rest, saved_options)
            message += f", as a copy ({job})"
    answer = {"ok": ok, "message": message, "id": job}
    if busy is not None:
        answer["ended"] = busy[2]
    return answer


def plan_markdown(home, extra_dirs, slug, profile_key=None):
    """{"ok", "title", "markdown", "path"} of a plan (--plan-text, for an SSH
    host's plan opened here)."""
    path = find_plan(discover_profiles(home, extra_dirs), slug, profile_key, home)
    if path is None:
        return {"ok": False, "message": "That plan isn't there any more"}
    with open(path, "rb") as f:
        markdown = f.read(TASK_PLAN_MAX * 10).decode("utf-8", "replace")
    return {"ok": True, "message": "", "title": plan_title(path) or slug, "markdown": markdown, "path": str(path),
            "where": short_folder(str(path), home)}


# ---------------------------------------------------------------- stopping and interrupting chats
#
# A chat with a process of its own (in a terminal, or in VS Code's Claude
# panel) can be stopped from the widget, whatever it's doing; one in tmux can
# be interrupted too.
#
# Stopping: Claude gets the signal its own host would send and shuts down
# cleanly. In a terminal that's SIGTERM, as when the terminal closes: the
# current step is cut off, the terminal stays open, and `claude --resume`
# reopens the chat. VS Code's panel runs Claude in print mode, where SIGINT
# cancels the turn and exits with code 0: the panel takes that like its own
# stop button (the tab says "Interrupted") and starts Claude again with the
# next message; SIGTERM would show an error there. Commands it was running
# that outlive it are ended too (the panel's Claude leaves them behind), and
# a Claude that hangs on is killed after END_WAIT seconds.
#
# Interrupting (tmux only): Ctrl+C, sent to its pane as if pressed there,
# which does what the stop button of VS Code's Claude tab does: the turn stops
# and so do its subagents, background ones too (Esc would leave those
# running), while the chat stays open, a draft you typed included. Other
# terminals take no input from outside.

END_WAIT = 10  # seconds Claude gets to shut down before it's killed
LEFTOVER_WAIT = 3  # seconds its leftover commands get after SIGTERM


def process_gone(entry):
    """Has the session's process exited (an unreaped zombie counts)?"""
    if not is_alive(entry):
        return True
    try:
        with open(f"/proc/{entry['pid']}/stat", encoding="utf-8", errors="replace") as f:
            stat = f.read()
    except OSError:
        return True
    return stat[stat.rfind(")") + 2:][:1] in ("Z", "X")


def process_tree(pid):
    """[(pid, start time)] of every process below pid."""
    children = {}
    try:
        names = [n for n in os.listdir("/proc") if n.isdigit()]
    except OSError:
        return []
    for name in names:
        try:
            with open(f"/proc/{name}/stat", encoding="utf-8", errors="replace") as f:
                stat = f.read()
            fields = stat[stat.rfind(")") + 2:].split()
            children.setdefault(int(fields[1]), []).append((int(name), fields[19]))
        except (OSError, ValueError, IndexError):
            continue
    found, todo = [], [pid]
    while todo:
        for child in children.get(todo.pop(), []):
            found.append(child)
            todo.append(child[0])
    return found


def end_leftovers(tree, wait=LEFTOVER_WAIT):
    """End what's left of a stopped chat's processes (same pid and start time
    as before, so never a newcomer with a reused pid): SIGTERM, then SIGKILL.
    Returns how many were still running."""
    import signal
    alive = lambda: [p for p in tree if not process_gone({"pid": p[0], "procStart": p[1]})]
    left = alive()
    for pid, _ in left:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    deadline = time.time() + wait
    while alive() and time.time() < deadline:
        time.sleep(0.1)
    for pid, _ in alive():
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    return len(left)


def stop_chat(entry, busy_ok=False, wait=END_WAIT):
    """Stop the process of a chat (see above): (ok, message). Unless busy_ok
    (you were told it's working or waiting), only an idle one: a chat that got
    back to work since you asked isn't touched."""
    import signal
    if entry.get("kind") != "interactive":
        return False, "Only chats in a terminal or in VS Code can be stopped this way"
    state = session_state(entry)
    if not busy_ok and state != "idle":
        return False, ("It's working again" if state == "working" else "It's waiting for you now") + ", so it wasn't stopped"
    if process_gone(entry):
        return True, "It had quit already"
    tree = process_tree(entry["pid"])
    sig = signal.SIGINT if entry.get("entrypoint") == "claude-vscode" else signal.SIGTERM
    try:
        os.kill(entry["pid"], sig)
    except ProcessLookupError:
        return True, "It had quit already"
    except OSError as exc:
        return False, f"Couldn't stop it: {exc}"
    deadline = time.time() + wait
    while not process_gone(entry) and time.time() < deadline:
        time.sleep(0.1)
    killed = not process_gone(entry)
    if killed:  # checked again just before: the pid mustn't be someone else's by now
        try:
            os.kill(entry["pid"], signal.SIGKILL)
        except OSError:
            pass
    leftovers = end_leftovers(tree)
    message = (f"It hadn't quit after {wait} s, so it was killed; the chat is kept" if killed
               else "Stopped; the chat is kept")
    if leftovers:
        message += f" (and {leftovers} command{'s' if leftovers > 1 else ''} it was running ended)"
    return True, message


def tmux_socket(pid):
    """The socket of the tmux server a process runs under ($TMUX), or None."""
    try:
        with open(f"/proc/{pid}/environ", "rb") as f:
            env = f.read().split(b"\0")
    except OSError:
        return None
    value = next((e[5:].decode(errors="replace") for e in env if e.startswith(b"TMUX=")), "")
    socket = value.split(",", 1)[0]
    return socket if socket.startswith("/") else None


def parent_pid(pid):
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as f:
            stat = f.read()
        return int(stat[stat.rfind(")") + 2:].split()[1])
    except (OSError, ValueError, IndexError):
        return 0


def is_vscode_terminal_host(pid):
    """Is pid VS Code's terminal host: one of VS Code's own processes on a
    desktop, `node … --type=ptyHost` in the VS Code server of a host that a
    Remote-SSH window works on?"""
    try:
        with open(f"/proc/{pid}/comm", encoding="utf-8", errors="replace") as f:
            if f.read().strip() in {c for c, _ in VSCODE_APPS}:
                return True
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return b"--type=ptyHost" in f.read().split(b"\0")
    except OSError:
        return False


def vscode_terminal(pid):
    """The process a VS Code terminal started, that pid runs under, or None
    when it runs in no VS Code terminal. VS Code's extensions know a terminal
    by that process (its processId), so the Talpy Den extension can bring
    the chat's terminal up, even with the panel closed."""
    child, seen = None, set()
    while isinstance(pid, int) and pid > 1 and pid not in seen and len(seen) < 64:
        if child is not None and is_vscode_terminal_host(pid):
            return child
        seen.add(pid)
        child, pid = pid, parent_pid(pid)
    return None


# The terminal a chat runs in, by name (the chat pane's tag says it): its
# process name (the first 15 characters) -> its name
TERMINAL_NAMES = {
    "konsole": "Konsole", "yakuake": "Yakuake", "kitty": "kitty", "wezterm-gui": "WezTerm", "wezterm-mux-ser": "WezTerm",
    "gnome-terminal-": "GNOME Terminal", "ptyxis-agent": "Ptyxis", "ptyxis": "Ptyxis", "kgx": "Console",
    "alacritty": "Alacritty", "foot": "foot", "footclient": "foot", "ghostty": "Ghostty", "xterm": "xterm",
    "uxterm": "xterm", "urxvt": "urxvt", "urxvtd": "urxvt", "rxvt": "rxvt", "st": "st", "tilix": "Tilix",
    "terminator": "Terminator", "xfce4-terminal": "Xfce Terminal", "mate-terminal": "MATE Terminal",
    "lxterminal": "LXTerminal", "qterminal": "QTerminal", "terminology": "Terminology", "deepin-terminal": "Deepin Terminal",
    "cool-retro-term": "Cool Retro Term", "tabby": "Tabby", "hyper": "Hyper", "rio": "Rio", "contour": "Contour",
    "warp": "Warp", "blackbox": "Black Box", "screen": "GNU screen", "zellij": "Zellij",
}


def process_name(pid):
    try:
        with open(f"/proc/{pid}/comm", encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except OSError:
        return ""


def terminal_name(pid):
    """The name of the terminal pid runs in (Konsole, kitty, GNOME Terminal…;
    "VS Code" for a terminal of VS Code), from the processes it runs under, or
    "": none known (tmux, over SSH, a service)."""
    child, seen = None, set()
    while isinstance(pid, int) and pid > 1 and pid not in seen and len(seen) < 64:
        if child is not None and is_vscode_terminal_host(pid):
            return "VS Code"
        comm = process_name(pid)
        if not comm:
            return ""
        if comm.startswith("tmux") or comm in ("sshd", "sshd-session"):
            return ""
        if child is not None and comm in TERMINAL_NAMES:
            return TERMINAL_NAMES[comm]
        seen.add(pid)
        child, pid = pid, parent_pid(pid)
    return ""


_attaching = [0.0, []]   # (when looked for, [(pid, what it attaches to)]): once a check


def attach_clients():
    """The terminals that show a background session on this machine: [(pid,
    the session it was opened for: its id or name, or "", the title of its
    tab, or "")], looked for once a second at most. One shows it as `claude
    attach <id>`, which runs on as the agent view (`claude agents`, the
    session it was opened for in CLAUDE_AGENTS_SELECT), or as a plain
    `claude` with no session of its own (the agent view too). An agent view
    can switch to another session: where the terminal says its tab's title
    (Konsole, Yakuake, tmux), Claude Code titles the tab with that session's
    name (shown_row)."""
    if time.monotonic() - _attaching[0] < 1:
        return _attaching[1]
    found = []
    try:
        names = os.listdir("/proc")
    except OSError:
        names = []
    for name in names:
        if not name.isdigit() or process_name(int(name)) != "claude":
            continue
        pid = int(name)
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                argv = [a.decode(errors="replace") for a in f.read().split(b"\0")]
        except OSError:
            continue
        sub = argv[1] if len(argv) > 1 else ""
        if sub == "attach" and len(argv) >= 3 and argv[2]:
            opened = argv[2]
        elif sub == "agents" or (sub in ("", "--continue") and not own_session(pid)):
            opened = process_environ_value(pid, "CLAUDE_AGENTS_SELECT")
        else:
            continue
        title = tab_title(pid)
        if title or opened:
            found.append((pid, opened, title))
    _attaching[0], _attaching[1] = time.monotonic(), found
    return found


def own_session(pid):
    """Is pid a chat of its own (a session file under its config folder)?"""
    folder = process_config_dir(pid)
    return bool(folder) and os.path.isfile(os.path.join(folder, "sessions", f"{pid}.json"))


TITLE_MARKS = re.compile(r"^[^\w(\[]+")   # (what Claude and the terminal put before the title: a spinner, a state, an icon)


def tab_title(pid):
    """The title of the terminal tab pid runs in, where the terminal says it
    (Konsole and Yakuake over D-Bus, tmux), without the marks before it, or ""."""
    service, session = process_environ_value(pid, "KONSOLE_DBUS_SERVICE"), process_environ_value(pid, "KONSOLE_DBUS_SESSION")
    title = ""
    try:
        import shutil
        import subprocess
        if re.fullmatch(r"[:\w.-]+", service) and re.fullmatch(r"/Sessions/\d+", session) and shutil.which("busctl"):
            r = subprocess.run(["busctl", "--user", "--json=short", "call", service, session, "org.kde.konsole.Session",
                                "title", "i", "1"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=2)
            if r.returncode == 0:
                title = json.loads(r.stdout.decode("utf-8", "replace"))["data"][0]
        elif tmux_socket(pid) and process_environ_value(pid, "TMUX_PANE") and shutil.which("tmux"):
            r = subprocess.run(["tmux", "-S", tmux_socket(pid), "display-message", "-p", "-t",
                                process_environ_value(pid, "TMUX_PANE"), "#{pane_title}"],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=2)
            if r.returncode == 0:
                title = r.stdout.decode("utf-8", "replace").strip()
    except (OSError, ValueError, KeyError, IndexError, TypeError, subprocess.TimeoutExpired):
        return ""
    return TITLE_MARKS.sub("", title if isinstance(title, str) else "").strip()


def process_environ_value(pid, key):
    """One variable of a process's environment (as it started), or ""."""
    try:
        with open(f"/proc/{pid}/environ", "rb") as f:
            data = f.read()
    except OSError:
        return ""
    prefix = key.encode() + b"="
    return next((e[len(prefix):].decode(errors="replace") for e in data.split(b"\0") if e.startswith(prefix)), "")


def shown_row(pid, opened, title, rows, reals):
    """The background session (of rows) a terminal shows (attach_clients),
    or None. The one it was opened for: by its id, else by its name on the
    profile it runs on (reals: profile key -> its real folder). Its tab's
    title says which one the agent view switched to, whichever profile, when
    exactly one is called that; of several with that name, the one it was
    opened for if it's one of them (else none: no guess); a title no session
    has (the terminal's own, e.g. Konsole's "%d : %n") leaves the one it was
    opened for."""
    first = None
    if opened:
        found = [r for r in rows if opened in (r.get("jobId"), r.get("sessionId"), r.get("chatId"))]
        if not found:
            here = process_config_dir(pid)
            found = [r for r in rows if r["name"] == opened and here is not None and reals.get(r["profileDir"]) == here]
        first = found[0] if len(found) == 1 else None
    named = [r for r in rows if title and r["name"] == title]
    if len(named) == 1:
        return named[0]
    if named:
        return first if any(r is first for r in named) else None
    return first


def attached_in(row, rows, clients, reals):
    """Where a background session (row, one of rows) is shown: {"in": "tmux",
    "vscode" (a VS Code terminal) or "terminal", "app": the terminal's name or
    ""}, or None: nowhere."""
    for pid, opened, title in clients:
        if shown_row(pid, opened, title, rows, reals) is not row:
            continue
        if tmux_socket(pid):
            return {"in": "tmux", "app": ""}
        app = terminal_name(pid)
        return {"in": "vscode", "app": ""} if app == "VS Code" else {"in": "terminal", "app": app}
    return None


def note_attached(groups, profiles):
    """Each running background session's "attached" (attached_in), once all
    of them are listed: a tab's title is looked up among them all."""
    rows = [s for g in groups for s in g["sessions"] if s.get("kind") == "bg"]
    if not any(s["pid"] for s in rows):
        return
    clients = attach_clients()
    reals = {p.key: p.real for p in profiles}
    for s in rows:
        if s["pid"] and clients:
            s["attached"] = attached_in(s, rows, clients, reals)


def interrupt_chat(entry):
    """Interrupt a working or waiting chat in tmux: Ctrl+C in its pane, as if
    you pressed it there (the turn and its subagents stop; the chat stays).
    Only while it works: at an idle prompt a second Ctrl+C would end Claude.
    (ok, message)"""
    import shutil
    import subprocess
    pane = entry.get("tmux")
    if not isinstance(pane, str) or not pane:
        return False, "It doesn't run in tmux, so it can't be interrupted from here; stop it instead"
    state = session_state(entry)
    if state not in ("working", "waiting"):
        return False, "It isn't working any more, so there's nothing to interrupt"
    if entry.get("status") == "shell":  # its turn is over: Claude is at its prompt
        return False, "Its turn is over (only a background command still runs), so a Ctrl+C would land at its prompt"
    tmux = shutil.which("tmux", path=os.pathsep.join([os.environ.get("PATH", ""), "/usr/bin", "/usr/local/bin", "/bin"]))
    if tmux is None:
        return False, "tmux isn't installed here"
    socket = tmux_socket(entry["pid"])
    target = pane.rsplit(".", 1)[-1] if "." in pane else pane  # its pane id, e.g. %3
    try:
        r = subprocess.run([tmux, *(["-S", socket] if socket else []), "send-keys", "-t", target, "C-c"],
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"tmux didn't answer: {exc}"
    if r.returncode != 0:
        lines = [l for l in (r.stderr + "\n" + r.stdout).splitlines() if l.strip()]
        return False, f"tmux: {lines[-1].strip() if lines else f'exit {r.returncode}'}"
    return True, "Interrupted (Ctrl+C in its tmux pane); the chat stays open there"


def find_chat_entry(home, extra_dirs, session_id, profile_key=None):
    """The live session entry of a chat with a process (terminal or VS Code),
    found by its session id and the profile it's listed under (a shared chat
    can run on two), or None."""
    found = find_chat_live(home, extra_dirs, session_id, profile_key)
    return found[0] if found else None


def find_chat_live(home, extra_dirs, session_id, profile_key=None):
    """find_chat_entry's entry, with the profile it runs on: (entry, profile), or None."""
    for entry, runs_on, holder in live_entries_all(discover_profiles(home, extra_dirs)):
        if entry.get("sessionId") != session_id or entry.get("kind") not in SESSION_KINDS \
                or entry.get("spare") or entry.get("parkedJobId"):
            continue
        if profile_key and profile_key not in (runs_on.key, holder.key):
            continue
        return entry, runs_on
    return None


def stop_chat_by_id(home, extra_dirs, session_id, profile_key=None, busy_ok=False, wait=END_WAIT):
    entry = find_chat_entry(home, extra_dirs, session_id, profile_key)
    return stop_chat(entry, busy_ok, wait) if entry else (False, "That chat isn't running any more")


def interrupt_chat_by_id(home, extra_dirs, session_id, profile_key=None):
    """Interrupt a working chat: Ctrl+C in its tmux pane (interrupt_chat), or
    Esc into a background session (interrupt_background)."""
    found = find_chat_live(home, extra_dirs, session_id, profile_key)
    return interrupt_live(*found) if found else (False, "That chat isn't running any more")


def interrupt_live(entry, runs_on):
    """interrupt_chat_by_id for a live session's entry, on the profile it runs on."""
    return interrupt_background(runs_on, entry) if entry.get("kind") == "bg" else interrupt_chat(entry)


# ---------------------------------------------------------------- Claude's background service
#
# Claude runs the background sessions of a Claude folder under one service,
# which answers on a Unix socket, /tmp/cc-daemon-<uid>/<sha256(the
# CLAUDE_CONFIG_DIR it runs with)[:8]>/control.sock: a JSON request a line,
# a JSON answer a line (Claude 2.1.316, read from its own client). Talpy Den
# asks it two things, as Claude's own commands do:
# - "has": does it still hold a session? claude --bg --resume asks it, and
#   starts a copy of the chat (a new id, without the options its session
#   saved) while it does, which it still can a moment after claude stop;
# - "reply": a message into a live background session, the way `claude
#   agents` answers one (typed in at its prompt; queued while it works). The
#   session goes on where it is: the same id, its options, its background
#   commands, and a terminal that shows it (claude attach) stays on it, where
#   claude stop would end that terminal's attach. A reply shows the
#   service's key, daemon/control.key in the Claude folder.
# Neither is documented: a service that doesn't answer as these expect
# leaves Talpy Den doing what it did before (claude stop, then claude --bg
# --resume).

DAEMON_TMP = Path("/tmp")
DAEMON_PROTO = 1
DAEMON_WAIT = 5  # seconds the service gets to answer
DAEMON_ANSWER_MAX = 1 << 20
DAEMON_KEY_MAX = 4096
# a reply refused for a moment (a session starting or restarting) is tried again, as Claude does
DAEMON_RETRY_CODES = ("ESTARTING", "ENOREPLY", "ERESPAWNING")
DAEMON_RETRIES = 10
DAEMON_RETRY_GAP = 0.2


def daemon_socket(profile):
    """The control socket of the background service running for this profile, or None."""
    value = service_config_dir(profile)
    if not value:
        return None
    return DAEMON_TMP / f"cc-daemon-{os.getuid()}" / hashlib.sha256(value.encode()).hexdigest()[:8] / "control.sock"


def peer_uid(sock):
    """The user id of the process at the other end of a connected Unix
    socket (SO_PEERCRED), or None where the system can't say."""
    import socket
    import struct
    opt = getattr(socket, "SO_PEERCRED", None)
    if opt is None:
        return None
    try:
        return struct.unpack("iII", sock.getsockopt(socket.SOL_SOCKET, opt, struct.calcsize("iII")))[1]
    except (OSError, struct.error):
        return None


def daemon_ask(profile, request, wait=DAEMON_WAIT):
    """The answer (a dict) of this profile's background service to request,
    or None when no service answers. Only a service of yours is asked: the
    socket's folder is in the shared /tmp, where another user could have
    made it first (your message and the service's key go in the request)."""
    import socket
    path = daemon_socket(profile)
    if path is None:
        return None
    data = b""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(wait)
            s.connect(str(path))
            uid = peer_uid(s)
            if (os.lstat(str(path)).st_uid if uid is None else uid) != os.getuid():
                return None
            s.sendall((json.dumps(dict(request, proto=DAEMON_PROTO)) + "\n").encode())
            while b"\n" not in data and len(data) < DAEMON_ANSWER_MAX:
                chunk = s.recv(65536)
                if not chunk:
                    break
                data += chunk
    except OSError:
        return None
    try:
        answer = json.loads(data.split(b"\n", 1)[0].decode("utf-8", "replace"))
    except ValueError:
        return None
    return answer if isinstance(answer, dict) else None


def daemon_holds(profiles, shorts):
    """Does the background service of one of profiles still hold a session
    of one of these short ids (its "has": there, or restarting)? False
    when none answers."""
    for profile in profiles:
        for short in shorts:
            answer = daemon_ask(profile, {"op": "has", "short": short})
            if answer and answer.get("ok") and answer.get("op") == "has" \
                    and (answer.get("present") or answer.get("alive")):
                return True
    return False


def daemon_key(profile):
    """The key of this profile's background service (daemon/control.key in
    the Claude folder): "" when there's none, None when it isn't one Talpy
    Den knows (too long)."""
    key_path = profile.path / "daemon" / "control.key"
    try:
        if key_path.stat().st_size > DAEMON_KEY_MAX:
            return None
        return key_path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def reply_to_background(profile, job_id, text):
    """Your message into a live background session (job_id: its short id),
    through its service's reply: (ok, message). Not ok when the service
    isn't there, doesn't answer within DAEMON_WAIT or won't take it (it
    says why)."""
    key = daemon_key(profile)
    if key is None:
        return False, "Claude's background service has a key Talpy Den doesn't know"
    if not key or not valid_id(job_id) or not (text or "").strip():
        return False, "Claude's background service can't be asked"
    answer = None
    for attempt in range(DAEMON_RETRIES):
        if attempt:
            time.sleep(DAEMON_RETRY_GAP)
        answer = daemon_ask(profile, {"op": "reply", "short": job_id, "text": text, "auth": key})
        if answer is None:
            return False, "Claude's background service didn't answer"
        if answer.get("ok") and answer.get("op") == "reply":
            return True, "Sent"
        if answer.get("code") not in DAEMON_RETRY_CODES:
            break
    error = answer.get("error") if isinstance(answer, dict) else None
    return False, f"Claude's background service didn't take it: {error}" if isinstance(error, str) and error \
        else "Claude's background service didn't take it"


# ---------------------------------------------------------------- Stop in a background chat
#
# Talpy Chat's Stop for a background session: what Claude does now stops,
# as when Esc is pressed in its terminal ("[Request interrupted by user]";
# the chat stays and takes your next message). The service has no interrupt
# of its own, so Talpy Den attaches to the session for a moment, as `claude
# attach` does (its "attach" request; after the service's answer, every byte
# goes into the session as typed), types one Esc and lets go. It attaches at
# the size the session's terminal has now (read from the worker's tty), so
# a terminal attached to it isn't resized; once it lets go, the service gives
# that terminal back what it had (Claude 2.1.318, checked live and in its
# code). Undocumented: only on the Claude Code versions it was checked on
# (BG_STOP_FROM up to BG_STOP_BEFORE: a row's "bgStop", or no Stop button),
# and nothing is typed unless the service answers as expected.

BG_STOP_FROM = (2, 1, 318)
BG_STOP_BEFORE = (2, 2)
BG_STOP_ACK_WAIT = 3  # seconds the service gets to answer the attach
BG_STOP_FRAME_WAIT = 0.5  # for the session's first output (Claude's own client types only after it)
BG_STOP_LINGER = 0.2  # after the Esc, before letting go
# One Stop at a time a chat: two Esc in a row open Claude's rewind menu, where
# a background chat would sit with nobody to see it (two front ends, say)
BG_STOP_GAP = 2  # seconds
# What Talpy Den says it is as a terminal: true colour, no theme of its own
# (the session keeps its own), no browser (Claude 2.1.318 drops the session's
# BROWSER while it's attached, and gives it back as it lets go)
BG_STOP_CAPS = {"imark": False, "terminal": None, "mux": None, "ssh": False, "colorLevel": 3}


def bg_stop_known(version):
    """Is version ("2.1.318": a session's, or its job's) one of the Claude
    Code versions Talpy Chat's Stop was checked on?"""
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        return False
    return BG_STOP_FROM <= version_key(version) < BG_STOP_BEFORE


def tty_size(pid):
    """(columns, rows) of the terminal a process reads from (its pty), or
    None: read with TIOCGWINSZ, nothing goes through it."""
    import struct
    import termios
    try:
        fd = os.open(f"/proc/{int(pid)}/fd/0", os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
    except (OSError, TypeError, ValueError):
        return None
    try:
        if not os.isatty(fd):
            return None
        rows, cols = struct.unpack("HHHH", fcntl.ioctl(fd, termios.TIOCGWINSZ, b"\0" * 8))[:2]
    except (OSError, struct.error):
        return None
    finally:
        os.close(fd)
    return (cols, rows) if cols > 0 and rows > 0 else None


def stop_turn(job_id, now=None, forget=False):
    """May a Stop type its Esc into this job now (none did in the last
    BG_STOP_GAP s)? Noted for the next one, in the cache folder (stops: the
    last few, locked while read and written); True where it can't be kept.
    forget: one that typed nothing after all is forgotten."""
    now = time.time() if now is None else now
    path = cache_dir(Path.home()) / "stops.json"
    try:
        private_dir(path.parent)
        f = os.fdopen(os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600), "r+", encoding="utf-8")
    except OSError:
        return True
    with f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                seen = json.loads(f.read() or "{}")
            except ValueError:
                seen = {}
            seen = {k: t for k, t in (seen.items() if isinstance(seen, dict) else ())
                    if isinstance(t, (int, float)) and 0 <= now - t < BG_STOP_GAP}
            if forget:
                seen.pop(job_id, None)
            elif job_id in seen:
                return False
            else:
                seen[job_id] = now
            f.seek(0)
            f.truncate()
            f.write(json.dumps(seen))
        except OSError:
            return True
    return True


def interrupt_background(profile, entry):
    """Talpy Chat's Stop for a live background session (entry: its session
    file's, profile: the one it runs on): one Esc typed into it through a
    moment's attach (above). (ok, message)"""
    job_id, version = entry.get("jobId"), entry.get("version")
    if not valid_id(job_id):
        return False, "Talpy Den can't stop this background chat: stop it in a terminal (Esc)"
    if not bg_stop_known(version):
        which = f"Claude Code {version}" if isinstance(version, str) and version else "this Claude Code"
        return False, f"Talpy Den can't stop a background chat of {which} yet: open it in a terminal and press Esc there"
    if entry.get("status") == "shell":
        return False, "Its turn is over (only a background command still runs), so there's nothing to stop"
    if session_state(entry) != "working":
        return False, "It isn't working any more, so there's nothing to stop"
    size = tty_size(entry.get("pid"))
    if size is None:
        return False, ("Talpy Den can't read the size of its terminal (a terminal that shows it would be resized): "
                       "open it in a terminal and press Esc there")
    key, path = daemon_key(profile), daemon_socket(profile)
    if not key or path is None:
        return False, "Claude's background service can't be asked"
    if not stop_turn(job_id):
        return False, "It was stopped a moment ago"
    ok, said = esc_through_attach(path, key, job_id, size)
    if not ok:
        stop_turn(job_id, forget=True)   # (nothing typed: the next Stop may go at once)
    return ok, said


def esc_through_attach(path, key, job_id, size):
    """interrupt_background's attach (path: the service's socket): (ok, message)."""
    import socket
    import uuid
    request = {"proto": DAEMON_PROTO, "op": "attach", "short": job_id, "auth": key, "cols": size[0], "rows": size[1],
               "attachId": str(uuid.uuid4()), "caps": dict(BG_STOP_CAPS)}
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(BG_STOP_ACK_WAIT)
            s.connect(str(path))
            uid = peer_uid(s)  # (only a service of yours: it gets the key)
            if (os.lstat(str(path)).st_uid if uid is None else uid) != os.getuid():
                return False, "Claude's background service didn't answer"
            s.sendall((json.dumps(request) + "\n").encode())
            data = b""
            while b"\n" not in data and len(data) < DAEMON_ANSWER_MAX:
                chunk = s.recv(65536)
                if not chunk:
                    break
                data += chunk
            line, _, shown = data.partition(b"\n")
            try:
                answer = json.loads(line.decode("utf-8", "replace"))
            except ValueError:
                answer = None
            if not isinstance(answer, dict) or answer.get("ok") is not True or answer.get("op") != "attach":
                error = answer.get("error") if isinstance(answer, dict) else None
                return False, (f"Claude's background service didn't take it: {error}" if isinstance(error, str) and error
                               else "Claude's background service didn't take it")
            worker = answer.get("workerCliVersion")
            if worker and not bg_stop_known(worker):
                return False, f"Talpy Den can't stop a background chat of Claude Code {worker} yet: open it in a terminal and press Esc there"
            if answer.get("booting"):
                return False, "It's starting: stop it in a moment"
            if not shown:  # (what the session shows first, as `claude attach` waits for it)
                s.settimeout(BG_STOP_FRAME_WAIT)
                try:
                    s.recv(65536)
                except socket.timeout:
                    pass
            s.sendall(b"\x1b")
            # (a moment for it to go in, then let go: the service gives an attached terminal back its own)
            end = time.monotonic() + BG_STOP_LINGER
            try:
                while time.monotonic() < end:
                    s.settimeout(max(0.01, end - time.monotonic()))
                    if not s.recv(65536):
                        break
            except OSError:
                pass
    except OSError:
        return False, "Claude's background service didn't answer"
    return True, "Stopped (Esc in the background chat): it takes your next message"


def live_background(profiles, chat_id):
    """(entry, profile it runs on) of the background session that has a chat
    open now, or None."""
    for entry, runs_on, _holder in live_entries_all(profiles):
        if entry.get("sessionId") == chat_id and entry.get("kind") == "bg" and valid_id(entry.get("jobId")) \
                and not entry.get("spare") and not entry.get("parkedJobId"):
            return entry, runs_on
    return None


def stop_background(profile, job_id, job=None, home=None, claude=None):
    """Stop a background session with `claude stop` (its conversation is
    kept): (ok, message)."""
    import subprocess
    home = home or Path.home()
    claude = claude or find_claude(home, ask_shell=True)
    env = {k: v for k, v in os.environ.items() if k != NO_AGENT_VIEW}
    value = config_dir_value(profile, home, job, for_job=True)
    if value is None:
        env.pop("CLAUDE_CONFIG_DIR", None)
    else:
        env["CLAUDE_CONFIG_DIR"] = value
    folder = os.path.dirname(claude)
    if folder and os.path.isfile(os.path.join(folder, "node")):  # an npm install under nvm needs its node
        env["PATH"] = os.pathsep.join([folder, env.get("PATH", "")])
    try:
        r = subprocess.run([claude, "stop", job_id], env=env, cwd=str(home), stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"claude stop didn't finish: {exc}"
    lines = [l.strip() for l in (r.stdout + "\n" + r.stderr).splitlines() if l.strip()]
    if r.returncode != 0:
        return False, lines[-1] if lines else f"claude stop failed (exit {r.returncode})"
    return True, lines[-1] if lines else "Stopped"


def end_for_handover(home, profiles, chat_id, claude=None):
    """Before a chat continues on another account (say a usage limit stopped
    it here): end the session that has it open, if it's idle. A chat in a
    terminal quits as with the stop button, a background session is stopped
    (claude stop); one in VS Code's Claude isn't touched (its tab would start
    it again with your next message). (ok, message); ok if none has it open."""
    for entry, runs_on, _holder in live_entries_all(profiles):
        if entry.get("sessionId") != chat_id or entry.get("kind") not in SESSION_KINDS or entry.get("spare"):
            continue
        if entry.get("entrypoint") == "claude-vscode":
            return False, "It's open in VS Code's Claude: close its tab there first"
        if session_state(entry) != "idle":
            return False, "It's at work again, so it stays where it is"
        job_id = entry.get("jobId")
        if entry.get("kind") == "bg" and valid_id(job_id):
            return stop_background(runs_on, job_id, read_job([runs_on], job_id), home, claude)
        if entry.get("kind") == "interactive":
            return stop_chat(entry)
        return False, "It's open where Talpy Den can't end it"
    return True, "Nothing had it open"


# ---------------------------------------------------------------- a go-on kept waiting by background commands
#
# A chat a usage limit stopped can still look at work: Claude counts the
# commands it runs in the background (a server it started, say) as work, so
# its session says busy until they end, though its turn ended at the limit.
# A background session takes the go-on in all the same (reply_to_background),
# and they run on. A chat in a terminal can't take a message from outside,
# nor a background session whose service won't (nor claude --bg --resume a
# chat whose session is live), and ending it would end them: such a go-on
# waits for them (the queue tries again each minute), and GO_ON_WAIT_MS
# after its time ends them and goes on.

GO_ON_WAIT_MS = 15 * 60_000  # how long a go-on waits for a chat's background commands, then ends them
GO_ON_LOG_LINES = 200  # cache_dir/go-on.log keeps this many lines


def claude_shell_command(argv):
    """The command a shell that Claude started runs (bash -c 'source
    <snapshot> … && eval '<command>' …'), from its argv, or None."""
    script = argv[-1] if len(argv) >= 3 and "-c" in argv[1:-1] else ""
    at = script.find("eval ")
    if "shell-snapshots" not in script or at < 0:
        return None
    lexer = shlex.shlex(script[at + 5:], posix=True)
    lexer.whitespace_split = True
    try:
        command = lexer.get_token()
    except ValueError:
        return None
    return command or None


def background_commands(entry, profile):
    """The commands a chat's session runs in the background, named short: a
    background session's from its job (state.json's fan: its shells not
    done yet), else the shells Claude started below its process."""
    names = []
    job_id = entry.get("jobId")
    if entry.get("kind") == "bg" and valid_id(job_id):
        job = read_job([profile], job_id) or {}
        fan = job.get("fan") if isinstance(job.get("fan"), list) else []
        names = [f["label"] for f in fan if isinstance(f, dict) and f.get("kind") == "shell" and not f.get("doneAt")
                 and isinstance(f.get("label"), str) and f["label"].strip()]
    if not names and isinstance(entry.get("pid"), int) and is_alive(entry):
        for pid, _ in process_tree(entry["pid"]):
            try:
                with open(f"/proc/{pid}/cmdline", "rb") as f:
                    argv = [a.decode("utf-8", "replace") for a in f.read().split(b"\0") if a]
            except OSError:
                continue
            command = claude_shell_command(argv)
            if command:
                names.append(command)
    return [short_text(next((l for l in n.splitlines() if l.strip()), n), 60) for n in names]


def background_work(profiles, chat_id):
    """The session that has a chat open and is at work, as one whose turn a
    usage limit ended is on its background commands alone: (entry, profile
    it runs on, [its commands, named short]), or None. Not one in VS Code's
    Claude (its tab isn't Talpy Den's to end)."""
    for entry, runs_on, _holder in live_entries_all(profiles):
        if entry.get("sessionId") != chat_id or entry.get("kind") not in SESSION_KINDS or entry.get("spare") \
                or entry.get("parkedJobId") or entry.get("entrypoint") == "claude-vscode":
            continue
        if session_state(entry) == "working":
            return entry, runs_on, background_commands(entry, runs_on)
    return None


def end_background_work(home, entry, profile, claude=None):
    """End a chat's session and the commands it runs in the background: a
    background session is stopped (claude stop), a chat in a terminal quits
    as with the stop button; what's left of its commands after that is
    ended too (end_leftovers). (ok, message)."""
    tree = process_tree(entry["pid"]) if isinstance(entry.get("pid"), int) and is_alive(entry) else []
    job_id = entry.get("jobId")
    if entry.get("kind") == "bg" and valid_id(job_id):
        ok, message = stop_background(profile, job_id, read_job([profile], job_id), home, claude)
        if ok:
            deadline = time.time() + END_WAIT
            while not process_gone(entry) and time.time() < deadline:
                time.sleep(0.2)
            end_leftovers(tree)
        return ok, message
    if entry.get("kind") == "interactive":
        return stop_chat(entry, busy_ok=True)
    return False, "It's open where Talpy Den can't end it"


def log_go_on(cache_root, text, now=None):
    """A dated line in cache_dir/go-on.log, of the go-ons that waited for a
    chat's background commands (the last GO_ON_LOG_LINES lines are kept)."""
    stamp = datetime.fromtimestamp(time.time() if now is None else now).strftime("%Y-%m-%d %H:%M:%S")
    path = cache_root / "go-on.log"
    private_dir(cache_root)
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            old = f.read().splitlines()
    except OSError:
        old = []
    keep = old[-(GO_ON_LOG_LINES - 1):] + [f"{stamp}  {' '.join(text.split())}"]
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("\n".join(keep) + "\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass


# ---------------------------------------------------------------- several widgets at once
#
# The Plasma widget can run twice, e.g. on a panel and in the system tray.
# Each copy says it's there on every status check (--instance). The copy
# that has been running longest sends the notifications and plays the sounds,
# so they come once. Settings are shared: a copy saves them on every change
# (jump.py --save-settings) and the others take them over at their next check;
# a new copy takes over what the others use.

INSTANCE_GRACE_MS = 15000  # a copy not heard from for 3 of its check intervals plus this has gone


def elect_notifier(cache_root, instance, interval_ms, now_ms):
    """Note that this copy of the widget is running; is it the one that notifies?"""
    path = cache_root / "instances.json"
    private_dir(cache_root)
    with open(cache_root / "instances.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = read_json(path)
        seen = {}
        for key, v in (data.items() if isinstance(data, dict) else []):
            # (a copy noted "in the future" was noted before the clock was set back: it counts as gone, too,
            # or a copy that has closed would stay the one that notifies until the clock catches up)
            if isinstance(v, dict) and number(v.get("seen")) is not None and number(v.get("since")) is not None \
                    and abs(now_ms - v["seen"]) <= 3 * (number(v.get("interval")) or 2000) + INSTANCE_GRACE_MS:
                seen[key] = v
        me = seen.get(instance)
        seen[instance] = {"since": me["since"] if me else now_ms, "seen": now_ms, "interval": interval_ms}
        write_json_atomic(path, seen)
    first = min(seen.items(), key=lambda kv: (kv[1]["since"], kv[0]))[0]
    return first == instance


# ---------------------------------------------------------------- the jobs file
#
# The chats and their states, for other programs: a status bar, a desk
# display, a script (docs/how-it-works.md#the-jobs-file). Each check writes
# its own machine's: the copy that does the once-a-computer work (it notifies,
# or VS Code's leading window, or GNOME's copy) this computer's after its
# check, each SSH host's and container's check (remote.py --status) that
# place's, or takes them out when it couldn't reach it. Under a lock, as two
# checks can end at once; only when something changed, and in one go (a new
# file renamed over it): whoever reads it always gets a whole one, and can wait
# for that rename (inotify's IN_MOVED_TO on its folder) instead of reading it
# again and again.

JOBS_FILE_VERSION = 1
JOBS_HOST_FRESH_MS = 15 * 60_000  # a place nothing checks any more: its chats go once its last answer is this old


def jobs_file_path(home, cache_root):
    """$XDG_RUNTIME_DIR/talpy-den/jobs.json: private, in memory, gone when you log out. The runtime folder is
    your login's, so a check for another home than your account's (a sandbox, the tests) keeps its file in
    its own cache folder, as does a system without that folder."""
    import pwd
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    try:
        own_home = Path(pwd.getpwuid(os.getuid()).pw_dir).resolve() == Path(home).resolve()
    except (KeyError, OSError):
        own_home = False
    if runtime and own_home and os.path.isdir(runtime):
        return Path(runtime) / "talpy-den" / "jobs.json"
    return cache_root / "jobs.json"


def place_jobs(groups, host="", where="local", offset_ms=0):
    """The jobs file's entries for the chats of groups (a status check's): of this computer (host ""), else
    of the SSH host or container host (where: "ssh", or its engine), their times put on this computer's
    clock (offset_ms: how far its clock is from this one's). Only what a status shows: no prompts, replies
    or what a chat asks."""
    jobs = []
    for g in groups if isinstance(groups, list) else []:
        for s in g.get("sessions") or [] if isinstance(g, dict) else []:
            if not isinstance(s, dict) or s.get("state") not in STATE_ORDER:
                continue
            since = number(s.get("since"))
            jobs.append({"id": (host + ":" if host else "") + str(s.get("key") or ""), "name": s.get("name") or "",
                         "state": s["state"], "since": int(since + offset_ms) if since is not None else None,
                         "account": g.get("name") or "", "folder": s.get("cwdShort") or "",
                         "host": host, "where": where})
    return jobs


def place_accounts(groups, host="", where="local", offset_ms=0):
    """The jobs file's accounts of groups (a status check's), each with its plan's usage: the windows as the
    widget shows them (one past its reset at 0%), their resets on this computer's clock. Its id is the
    account's (a one-way hash), the same on every machine it's logged in on."""
    accounts = []
    for g in groups if isinstance(groups, list) else []:
        if not isinstance(g, dict):
            continue
        limits = g.get("limits") if isinstance(g.get("limits"), dict) else {}
        windows = []
        for w in limits.get("windows") or []:
            if isinstance(w, dict) and isinstance(w.get("key"), str) and number(w.get("pct")) is not None:
                resets = number(w.get("resetsAt"))
                windows.append({"key": w["key"], "label": w.get("label") or w["key"], "pct": w["pct"],
                                "resetsAt": int(resets + offset_ms) if resets is not None else None})
        accounts.append({"id": str(g.get("id") or ""), "name": g.get("name") or "", "plan": g.get("plan") or "",
                         "host": host, "where": where, "windows": windows})
    return accounts


def place_fresh(cache_root, host, now_ms):
    """Whether the place's chats stay in the jobs file: this computer's always (its own check takes them
    out), an SSH host's or container's while its last answer (remote.py's, hosts/<host>.json) is fresh."""
    if not host:
        return True
    if not isinstance(host, str) or "/" in host or host.startswith("."):
        return False
    try:
        return now_ms - (cache_root / "hosts" / (host + ".json")).stat().st_mtime * 1000 <= JOBS_HOST_FRESH_MS
    except OSError:
        return False


def publish_jobs(path, cache_root, host, jobs, now_ms, accounts=None):
    """Put host's jobs and accounts (place_jobs' and place_accounts'; host "" for this computer; None: none,
    as its check failed) in the jobs file in place of its last ones, keeping the other places' while they're
    fresh, and write it if anything changed; True when it wrote. This computer's come first, then each
    place's by its name."""
    private_dir(cache_root)
    with open(cache_root / "jobs.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        old = read_json(path)
        old = old if isinstance(old, dict) and old.get("version") == JOBS_FILE_VERSION else None

        def merged(key, mine):
            last = old.get(key) if old is not None else None
            last = last if isinstance(last, list) else []
            others = [e for e in last if isinstance(e, dict) and e.get("host", "") != host
                      and place_fresh(cache_root, e.get("host", ""), now_ms)]
            return last, sorted(list(mine or []) + others, key=lambda e: (e.get("host", "") != "", e.get("host", "")))
        last_jobs, new_jobs = merged("jobs", jobs)
        last_accounts, new_accounts = merged("accounts", accounts)
        if old is not None and "accounts" in old and new_jobs == last_jobs and new_accounts == last_accounts:
            return False
        private_dir(path.parent)
        write_json_atomic(path, {"version": JOBS_FILE_VERSION, "updatedAt": now_ms, "jobs": new_jobs,
                                 "accounts": new_accounts}, private=True)
        return True


def config_defaults(main_xml=None):
    """{key: default} of the widget's settings (contents/config/main.xml)."""
    import xml.etree.ElementTree as ET
    path = main_xml or Path(__file__).resolve().parent.parent / "config" / "main.xml"
    try:
        root = ET.parse(str(path)).getroot()
    except (OSError, ET.ParseError):
        return {}
    ns = {"k": "http://www.kde.org/standards/kcfg/1.0"}
    defaults = {}
    for entry in root.iterfind(".//k:entry", ns):
        kind, text = entry.get("type"), (entry.findtext("k:default", "", ns) or "").strip()
        defaults[entry.get("name")] = (text == "true" if kind == "Bool" else int(text) if kind == "Int" and text
                                       else 0 if kind == "Int" else text)
    return defaults


def shared_settings(cache_root):
    """The settings the widgets share: {"at", "by", "values"}, or None."""
    data = read_json(state_dir(cache_root) / "settings.json")
    if not isinstance(data, dict) or not isinstance(data.get("values"), dict) or number(data.get("at")) is None:
        return None
    return {"at": data["at"], "by": str(data.get("by") or ""), "values": data["values"]}


def save_shared_settings(cache_root, by, values, now_ms, unless_default=False):
    """Save a widget's settings for the others (only known keys). With
    unless_default, settings that are all defaults (a widget nobody set up
    yet) aren't saved: they mustn't replace what another one uses."""
    defaults = config_defaults()
    values = {k: v for k, v in values.items() if k in defaults} if defaults else dict(values)
    if unless_default and defaults and all(values.get(k, d) == d for k, d in defaults.items()):
        return False, "Nothing set up yet"
    state = state_dir(cache_root)
    private_dir(state)
    write_json_atomic(state / "settings.json", {"at": now_ms, "by": by, "values": values}, private=True)  # (your SSH hosts are in it)
    return True, "Settings saved"


# ---------------------------------------------------------------- old chats
# Who deletes old chats and plans: Claude Code's own cleanup (its
# cleanupPeriodDays), or Talpy Den's in its place, which keeps what you
# starred (cleanup.py). One copy asks whether Talpy Den's daily run is due,
# in its status check: the one that notifies (--instance elected it, VS
# Code's --keep-going window) or GNOME's (--cleanup-check). Most checks
# that's two stats; a due run starts on its own, in the background, and
# the check doesn't wait for it.

CLEANUP_SETTING_FILE = "cleanup.json"  # (in the state folder: what's deleted is decided there, never in the cache)
CLEANUP_STAMP = "cleanup-ran"  # (in the cache: touched as a run starts)
CLEANUP_EVERY_S = 86400


def cleanup_due(cache_root, now):
    """Is a run of cleanup.py due: the setting changed since the last one,
    or a day went by while Talpy Den cleans (or still has Claude Code's own
    cleanup to put back somewhere: "pending")? Never set: never."""
    try:
        changed = os.stat(str(state_dir(cache_root) / CLEANUP_SETTING_FILE)).st_mtime
    except OSError:
        return False
    stamp = Path(cache_root) / CLEANUP_STAMP
    try:
        ran = os.stat(str(stamp)).st_mtime
    except OSError:
        ran = 0.0
    if ran >= changed and abs(now - ran) < CLEANUP_EVERY_S:  # (a clock set back doesn't hold it off for long)
        return False
    data = read_json(state_dir(cache_root) / CLEANUP_SETTING_FILE)
    due = isinstance(data, dict) and (data.get("mode") == "talpy" or data.get("pending") is True)
    try:  # (asked again in a day, or once the setting changes)
        private_dir(Path(cache_root))
        os.close(os.open(str(stamp), os.O_CREAT | os.O_WRONLY, 0o600))
        os.utime(str(stamp), (now, now))
    except OSError:
        return False  # (it would be asked every check)
    return due


def start_cleanup(cache_root, extra_dirs=()):
    """Start cleanup.py --run in the background, on its own (not a child the
    check waits for): whether it started. The stamp first, so a check right
    after a change of the setting doesn't start another. Not on an SSH host,
    where this file comes on stdin: the computer that asks runs it there."""
    here = globals().get("__file__")
    script = os.path.join(os.path.dirname(os.path.abspath(here)), "cleanup.py") if here else ""
    if not script or not os.path.isfile(script):
        return False
    stamp = Path(cache_root) / CLEANUP_STAMP
    try:
        private_dir(Path(cache_root))
        os.close(os.open(str(stamp), os.O_CREAT | os.O_WRONLY, 0o600))
        os.utime(str(stamp), None)
    except OSError:
        pass
    import subprocess
    subprocess.Popen([sys.executable or "python3", "-I", script, "--run", *("--config-dir=" + str(d) for d in extra_dirs)],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True, close_fds=True, cwd=str(Path.home()))
    return True


# ---------------------------------------------------------------- prompt history

RECENT_PROJECTS = 6
HISTORY_TAIL_BYTES = 65536


def history_tail(profile):
    """Entries at the end of a profile's prompt history (history.jsonl)."""
    path = profile.path / "history.jsonl"
    try:
        size = path.stat().st_size
        with open(path, "rb") as f:
            f.seek(max(0, size - HISTORY_TAIL_BYTES))
            lines = f.read().splitlines()
    except OSError:
        return []
    if size > HISTORY_TAIL_BYTES:
        lines = lines[1:]  # probably cut in the middle
    entries = []
    for line in lines:
        try:
            e = json.loads(line)
        except (ValueError, RecursionError):
            continue
        if isinstance(e, dict):
            entries.append(e)
    return entries


def last_prompts(entries):
    """{session id: when you last sent it a prompt (ms)}."""
    last = {}
    for e in entries:
        sid, ts = e.get("sessionId"), number(e.get("timestamp"))
        if valid_id(sid) and ts:
            last[sid] = max(last.get(sid, 0), int(ts))
    return last


def recent_projects(histories, home):
    """Folders recently chatted in, newest first, from the profiles' prompt
    history (for "new chat in…"). Skips folders that are gone and scratch
    folders inside Claude's own config dirs."""
    last_used = {}
    for entries in histories:
        for e in entries:
            folder, ts = e.get("project"), number(e.get("timestamp"))
            if isinstance(folder, str) and folder.startswith("/") and ts:
                last_used[folder] = max(last_used.get(folder, 0), ts)
    result = []
    for folder in sorted(last_used, key=lambda f: -last_used[f]):
        if any(part.startswith(".claude") for part in Path(folder).parts) or not os.path.isdir(folder):
            continue
        result.append({"path": folder, "short": short_path(folder, home)})
        if len(result) >= RECENT_PROJECTS:
            break
    return result


# ---------------------------------------------------------------- plan limits

CACHE_TTL_UNITS = {"s": 1000, "m": 60_000, "h": 3600_000}


def cache_ttl_ms(ttl):
    """A prompt cache's ttl as the status line gives it ("5m", "1h") in ms, or None."""
    if isinstance(ttl, str) and len(ttl) > 1 and ttl[-1] in CACHE_TTL_UNITS and ttl[:-1].isdigit():
        return int(ttl[:-1]) * CACHE_TTL_UNITS[ttl[-1]]
    return None


def limits_read_at(snap, mtime_ms):
    """When a status-line snapshot's plan usage (rate_limits) was read, in ms.
    Claude Code has it from the chat's last reply, and draws the status line
    again later with the same numbers: an idle chat's an hour after that
    reply, when its prompt cache goes cold. The snapshot written then is new,
    its numbers aren't (one at 32% after another chat's 100%). Its
    prompt_cache says when the last request went: expires_at less its ttl;
    without that (an older Claude Code), when the snapshot was written."""
    cache = snap.get("prompt_cache") if isinstance(snap, dict) else None
    if isinstance(cache, dict):
        expires, ttl = to_ms(number(cache.get("expires_at"))), cache_ttl_ms(cache.get("ttl"))
        if expires is not None and ttl is not None:
            return min(mtime_ms, expires - ttl)
    return mtime_ms


def snapshot_files(snapshot_root, profiles):
    """(mtime, path) of these profiles' status-line snapshots, newest first,
    leaving out ones filed under a link's name before the link was switched."""
    since = {}
    for p in profiles:
        for name, t in p.snapshot_sources.items():
            since[name] = max(t, since.get(name, t))
    files = []
    for name, t0 in since.items():
        try:
            with os.scandir(snapshot_root / name) as it:
                for e in it:
                    if e.name.endswith(".json") and not e.name.startswith("."):
                        try:
                            t = e.stat().st_mtime
                        except OSError:  # gone since it was listed (pruned by another copy): not the rest of the folder
                            continue
                        if t >= t0:
                            files.append((t, Path(e.path)))
        except OSError:
            continue
    files.sort(reverse=True)
    return files


def prune_snapshots(snapshot_root, now):
    try:
        dirs = list(snapshot_root.iterdir())
    except OSError:
        return
    for d in dirs:
        try:
            for f in d.iterdir():
                if now - f.stat().st_mtime > SNAPSHOT_MAX_AGE:
                    try:
                        f.unlink()
                    except FileNotFoundError:  # unlink(missing_ok=True) needs Python 3.8
                        pass
        except OSError:
            continue


ENDED_WINDOWS_LOOKBACK = 12  # readings looked through for a window the newest one lacks


def limit_window(key, pct, resets_at, now_ms):
    """A plan window as the widget shows it; one past its reset is at 0%."""
    resets = to_ms(resets_at)
    reset = resets is not None and resets <= now_ms
    return {
        "key": key,
        "label": WINDOW_LABELS.get(key, key.replace("_", " ")),
        "pct": 0.0 if reset else float(pct),
        "resetsAt": None if reset else resets,
        "reset": reset,
        "endedAt": resets if reset else None,  # when the window that's over ended
    }


def in_window_order(windows):
    rank = {k: i for i, k in enumerate(WINDOW_ORDER)}
    return sorted(windows, key=lambda w: rank.get(w["key"], len(rank)))


def cached_usage_limits(profiles, now_ms):
    """The group's plan windows from Claude Code's own usage cache (the newest
    of its profiles'), or None."""
    best = None
    for p in profiles:
        cache = getattr(p, "usage_cache", None)
        at = number(cache.get("fetchedAtMs")) if isinstance(cache, dict) else None
        usage = cache.get("utilization") if at is not None else None
        if not isinstance(usage, dict) or (best is not None and at <= best["updatedAt"]):
            continue
        windows = [limit_window(key, usage[key]["utilization"], usage[key].get("resets_at"), now_ms)
                   for key in WINDOW_ORDER
                   if isinstance(usage.get(key), dict) and number(usage[key].get("utilization")) is not None]
        if windows:
            best = {"updatedAt": int(at), "windows": in_window_order(windows)}
    return best


def with_ended_windows(limits, older, now_ms):
    """Claude Code reports a weekly window only once there's usage in it, so
    the first replies after a reset come without it. A window the newest
    reading leaves out, that an older one had and that has ended since (within
    its own length), is shown as reset: at 0%, not gone."""
    have = {w["key"] for w in limits["windows"]}
    extra = []
    for windows in older:
        for w in windows:
            hours = window_hours(w["key"])
            if w["reset"] and w["key"] not in have and hours and now_ms - w["endedAt"] < hours * 3600_000:
                have.add(w["key"])
                extra.append(w)
    if not extra:
        return limits
    return {**limits, "windows": in_window_order(limits["windows"] + extra)}


def plan_limits(snapshot_root, profiles, now_ms):
    """Rate-limit windows of the group: from its newest reading, a status-line
    snapshot's (as of when it was read: limits_read_at, not when the snapshot
    was written) or Claude Code's own usage cache's. (An account used only in
    VS Code's panel, which runs no status line, had numbers from the last
    time a terminal chat ran on it.)"""
    cached = cached_usage_limits(profiles, now_ms)
    cached_at = cached["updatedAt"] if cached is not None else None
    readings = []  # [(when read, windows)], as the snapshots come (newest written first)
    newest = None
    for mtime, path in snapshot_files(snapshot_root, profiles):
        t = int(mtime * 1000)  # (a snapshot's numbers were read when it was written, or before)
        if cached_at is not None and t <= cached_at and (newest is None or newest <= cached_at):
            break  # (the cache's are newer than all the rest)
        if newest is not None and t <= newest and len(readings) > ENDED_WINDOWS_LOOKBACK:
            break  # (none of the rest is newer, and with_ended_windows has enough)
        snap = read_json(path)
        limits = snap.get("rate_limits") if isinstance(snap, dict) else None
        if not isinstance(limits, dict) or not limits or not snapshot_of(snap, [p.real for p in profiles]):
            continue  # (no plan usage in it, or another account's folder of the same name)
        windows = [limit_window(key, w["used_percentage"], w.get("resets_at"), now_ms)
                   for key, w in limits.items()
                   if isinstance(w, dict) and number(w.get("used_percentage")) is not None]
        if not windows:
            continue
        at = limits_read_at(snap, t)
        readings.append((at, windows))
        newest = at if newest is None else max(newest, at)
    readings.sort(key=lambda r: -r[0])  # (stable: of two read at once, the one written last first)
    if not readings or (cached_at is not None and cached_at >= readings[0][0]):
        return cached
    found = {"updatedAt": readings[0][0], "windows": in_window_order(readings[0][1])}
    older = [windows for _, windows in readings[1:ENDED_WINDOWS_LOOKBACK + 1]]
    if cached is not None:
        older.append(cached["windows"])
    return with_ended_windows(found, older, now_ms)


# ---------------------------------------------------------------- usage forecast
#
# Where a plan window's usage is heading at your pace. The status line only
# says how much is used now, so the checks keep a few points of each window
# (usage.json); the pace is the last hour's in the 5-hour window, and the
# window's so far in the weekly ones (or while there's no hour on record).

WINDOW_HOURS = {"five_hour": 5, "seven_day": 168, "seven_day_opus": 168, "seven_day_sonnet": 168}
PACE_LOOKBACK_MS = {"five_hour": 3600_000}
FORECAST_MIN_MS = 15 * 60_000  # too early in a window to tell its pace
USAGE_POINT_EVERY_MS = 10 * 60_000  # an unchanged value is still noted this often
USAGE_POINTS_KEPT = 300
USAGE_HISTORY_VERSION = 1
# The windows that ended are kept a while longer (usage-past.json), for looking
# back at how your limits went: thinned to a point per step of their usage
# (the time each step was first seen), and only while the Recap keeps its
# history (history.json, the setting "Keep a history beyond Claude's 30 days")
USAGE_PAST_FILE = "usage-past.json"
USAGE_PAST_VERSION = 1
USAGE_PAST_DAYS = 90
USAGE_PAST_STEP = {"five_hour": 5}  # percent; 1 in the weekly windows
# {"keep": false} once you turn the history off (week.py); "since": when it was
# last turned on or off or deleted (ms), for the SSH hosts and containers (history_setting)
HISTORY_SETTING_FILE = "history.json"


def history_file(cache_root):
    """history.json, in the state folder (state_dir): it reaches the SSH hosts
    and containers, which delete their plan's windows by it, so what's in the
    cache mustn't decide it. One an older version kept in the cache moves
    there the first time (.moved-history notes it, as move_to_state does)."""
    state = state_dir(cache_root)
    path = state / HISTORY_SETTING_FILE
    mark = state / ".moved-history"
    if not os.path.exists(mark):
        old = Path(cache_root) / HISTORY_SETTING_FILE
        try:
            private_dir(state)
            if os.path.lexists(old):
                if not os.path.lexists(path):
                    data = read_plain(old)  # (a plain file only, as ours is)
                    if data is not None:
                        write_atomic(path, data, 0o600, new=True)
                os.unlink(old)
            os.close(os.open(str(mark), os.O_CREAT | os.O_WRONLY, 0o600))
        except OSError:
            pass
    return path


def history_kept(cache_root):
    """Does the Recap keep its history (the setting is on unless turned off)?"""
    data = read_json(history_file(cache_root))
    return not (isinstance(data, dict) and data.get("keep") is False)


def history_setting(cache_root):
    """(keep, since): history_kept, and when it was last turned on or off or
    deleted (ms; None: never), what came before going with it."""
    data = read_json(history_file(cache_root))
    data = data if isinstance(data, dict) else {}
    since = data.get("since")
    return data.get("keep") is not False, since if isinstance(since, int) and since > 0 else None


def follow_history(cache_root, history):
    """An SSH host's or a container's usage-past.json follows the history
    setting of the computer that asks (history: its (keep, since), sent with
    the status check): off, it goes; written before since, it holds only
    windows from before then, and goes too (save_usage_past keeps none of those)."""
    keep, since = history
    path = cache_root / USAGE_PAST_FILE
    t = mtime(path)
    if t is not None and (not keep or (since is not None and t * 1000 < since)):
        try:
            path.unlink()
        except OSError:
            pass


def trimmed_points(points):
    """A window's points down to USAGE_POINTS_KEPT: first the repeats inside a
    run of one value (the run's first and last point stay, so it draws the
    same), then the oldest. Only a weekly window gets this long, and its
    pace doesn't use the points."""
    if len(points) <= USAGE_POINTS_KEPT:
        return points
    kept = [p for i, p in enumerate(points)
            if i == 0 or i == len(points) - 1 or not (points[i - 1][1] == p[1] == points[i + 1][1])]
    return kept[-USAGE_POINTS_KEPT:]


def past_points(key, points):
    """An ended window's points as usage-past.json keeps them: the first, the
    first one at each step up (5% in the 5-hour window, 1% in the weekly
    ones), any that went down, and the last value it reached."""
    step = USAGE_PAST_STEP.get(key, 1)
    kept = []
    for p in points:
        if not kept or p[1] >= kept[-1][1] + step or p[1] < kept[-1][1]:
            kept.append(p)
    if kept and points[-1][1] != kept[-1][1]:
        kept.append(points[-1])
    return kept


def save_usage_past(cache_root, ended, now_ms, history=None):
    """Add the windows that ended to usage-past.json and drop the ones older
    than USAGE_PAST_DAYS; with the history off there's none (the file goes).
    history: (keep, since) of the computer that asks (follow_history), else
    this one's setting."""
    path = cache_root / USAGE_PAST_FILE
    keep, since = history if history is not None else (history_kept(cache_root), None)
    if not keep:
        try:
            path.unlink()
        except OSError:
            pass
        return
    data = read_json(path)
    past = data.get("windows") if isinstance(data, dict) and data.get("version") == USAGE_PAST_VERSION else None
    past = [w for w in past if isinstance(w, dict) and isinstance(w.get("resetsAt"), (int, float))] \
        if isinstance(past, list) else []
    have = {(w.get("group"), w.get("key"), round(w["resetsAt"] / 120_000)): w for w in past}
    for w in ended:
        k = (w["group"], w["key"], round(w["resetsAt"] / 120_000))
        kept = have.get(k)
        if kept is None:
            have[k] = w
            past.append(w)
            continue
        # (one ended again, as when its reset time was off for a moment: its
        # readings joined, the plan it was first kept with stays)
        points = {p[0]: p[1] for p in (kept.get("points") or []) + w["points"]
                  if isinstance(p, list) and len(p) == 2}
        kept["points"] = past_points(w["key"], [[t, points[t]] for t in sorted(points)])
        kept["plan"] = kept.get("plan") or w.get("plan")
    cutoff = max(now_ms - USAGE_PAST_DAYS * 86400_000, since or 0)
    past = sorted((w for w in past if w["resetsAt"] >= cutoff), key=lambda w: w["resetsAt"])
    write_json_atomic(path, {"version": USAGE_PAST_VERSION, "windows": past}, private=True)


def window_hours(key):
    return WINDOW_HOURS.get(key) or (168 if str(key).startswith("seven_day") else None)


def same_window(a, b):
    """Two resets_at of the same window (they may differ by a few seconds)."""
    return isinstance(a, (int, float)) and isinstance(b, (int, float)) and abs(a - b) < 120_000


class UsageHistory:
    """Each account's plan usage over its current windows: {group id:
    {window key: {"resetsAt", "points": [[ms, percent], …]}}}, in usage.json.
    A window that ends goes on to usage-past.json: {"windows": [{"group",
    "key", "plan", "resetsAt", "points"}]}, oldest first."""

    def __init__(self, path):
        self.path = path
        data = read_json(path)
        ok = isinstance(data, dict) and data.get("version") == USAGE_HISTORY_VERSION and isinstance(data.get("groups"), dict)
        self.groups = data["groups"] if ok else {}
        self.changed = False
        self.ended = []  # the windows that ended in this check, for usage-past.json
        self.now_ms = None
        self.history = None  # (keep, since) from the computer that asks (save_usage_past)

    def end(self, gid, key, rec, plan):
        """A window that's over (a new one began, or it reset a day ago)."""
        if not isinstance(rec, dict) or not isinstance(rec.get("resetsAt"), (int, float)) or not window_hours(key):
            return
        points = [p for p in rec.get("points") or [] if isinstance(p, list) and len(p) == 2
                  and isinstance(p[0], (int, float)) and isinstance(p[1], (int, float))]
        if points:
            self.ended.append({"group": gid, "key": key, "plan": plan, "resetsAt": rec["resetsAt"],
                               "points": past_points(key, points)})

    def points(self, gid, window):
        rec = (self.groups.get(gid) or {}).get(window["key"])
        if not isinstance(rec, dict) or not same_window(rec.get("resetsAt"), window.get("resetsAt")):
            return []
        return [p for p in rec.get("points") or [] if isinstance(p, list) and len(p) == 2]

    def record(self, gid, limits, now_ms, plan=None):
        """Note the group's usage as of its newest status-line snapshot (plan:
        its plan's name, kept with the windows that end)."""
        t = limits["updatedAt"]
        self.now_ms = now_ms
        if not isinstance(self.groups.get(gid), dict):
            self.groups[gid] = {}
        group = self.groups[gid]
        for w in limits["windows"]:
            if w["reset"] or not w["resetsAt"] or not window_hours(w["key"]):
                continue
            rec = group.get(w["key"])
            if not isinstance(rec, dict) or not same_window(rec.get("resetsAt"), w["resetsAt"]) \
                    or not isinstance(rec.get("points"), list):
                self.end(gid, w["key"], rec, plan)  # (the window before, if there was one)
                rec = {"resetsAt": w["resetsAt"], "points": []}
            points = rec["points"]
            if points and t < points[-1][0] - 60_000:  # the clock was set back: those points are "from the future"
                points[:] = [p for p in points if p[0] <= t]
            last = points[-1] if points else None
            if last is None or (t > last[0] and (w["pct"] != last[1] or t - last[0] >= USAGE_POINT_EVERY_MS)):
                points.append([t, w["pct"]])
                points[:] = trimmed_points(points)
                group[w["key"]] = rec
                self.changed = True
        for key in [k for k, rec in group.items() if not isinstance(rec, dict)
                    or not isinstance(rec.get("resetsAt"), (int, float)) or rec["resetsAt"] < now_ms - 86400_000]:
            self.end(gid, key, group[key], plan)
            del group[key]  # a window that ended a day ago
            self.changed = True

    def save(self):
        if self.changed:
            try:
                write_json_atomic(self.path, {"version": USAGE_HISTORY_VERSION, "groups": self.groups})
            except OSError:
                pass
        if self.ended:
            try:
                save_usage_past(self.path.parent, self.ended, self.now_ms or int(time.time() * 1000), self.history)
            except OSError:
                pass
            self.ended = []


def usage_forecast(window, points, now_ms):
    """Where a plan window is heading at your pace, or None while that can't be told:
    evenPct: where an even pace through the window would be by now;
    rate: percent per hour; atReset: where it would be when the window resets;
    fullAt: when it would run out (ms), if that's before it resets;
    basis: "hour" (the last hour's pace) or "window" (the window's so far)."""
    hours = window_hours(window["key"])
    resets = window.get("resetsAt")
    if not hours or not resets or window.get("reset") or resets <= now_ms:
        return None
    length = hours * 3600_000
    start = resets - length
    elapsed = now_ms - start
    if elapsed < FORECAST_MIN_MS:
        return None
    pct = window["pct"]
    rate, basis = pct / (elapsed / 3600_000), "window"
    look = PACE_LOOKBACK_MS.get(window["key"])
    if look and now_ms - look > start:
        before = [p for p in points if p[0] <= now_ms - look]
        if before and now_ms > before[-1][0]:  # its pace since then (the point may be older than an hour)
            rate, basis = max(0.0, (pct - before[-1][1]) / ((now_ms - before[-1][0]) / 3600_000)), "hour"
    full_at = None
    if pct >= 100:
        at_reset = pct
    else:
        at_reset = pct + rate * (resets - now_ms) / 3600_000
        if rate > 0:
            when = now_ms + (100 - pct) / rate * 3600_000
            if when < resets:
                full_at = int(when)
    return {"evenPct": round(min(100.0, 100.0 * elapsed / length), 1), "rate": round(rate, 2),
            "atReset": round(min(at_reset, 999.0), 1), "fullAt": full_at, "basis": basis}


# ---------------------------------------------------------------- plan usage, fetched
#
# Claude's VS Code panel runs no status line, and Claude Code refreshes its
# own copy of the plan usage (cachedUsageUtilization) only when /usage runs:
# an account used only in the panel kept the numbers of its last terminal
# chat for days. So while one of its chats works (or ended a turn lately) and
# its newest numbers are older than the interval you set (--usage-refresh N
# minutes, 5 unless you set it; 0: never), a check has Claude Code fetch them,
# the way /usage does: `claude -p /usage` uses no tokens and saves no chat.
# Its hooks are off (the live hook would note it as a chat), and it runs in a
# folder of its own, whose session isn't listed (live_row), reading only your
# own settings: none of a folder's (-p skips the trust question, so settings
# put there, an apiKeyHelper or env, would apply), and no MCP server. At most
# once per interval per profile, whichever copy of the widget checks
# (usage-check.json).

USAGE_REFRESH_MINUTES = 5  # the interval unless you set one
USAGE_REFRESH_MAX_MINUTES = 60
# A chat whose turn ended up to the interval and this much ago still counts
# as at work: its last turn's usage is fetched once after the turn
USAGE_ACTIVE_MARGIN_MS = 5 * 60_000
USAGE_REFRESH_LIMIT = 60  # seconds the fetch may take (then it's ended)
# Refresh (--fetch-usage): an account's plan usage older than this is
# fetched now, chat at work or not, at most this often
USAGE_NOW_MS = 60_000
USAGE_CHECK_DIR = "usage-check"  # the folder it runs in, in the cache
USAGE_CHECK_SETTINGS = '{"disableAllHooks":true}'
# After the fetch: the empty projects/<folder>/memory/ Claude makes for the
# folder it runs in goes again ($1: that projects/<folder>; then the command)
USAGE_CHECK_SCRIPT = 'd=$1; shift; "$@"; rmdir "$d/memory" "$d" 2>/dev/null; exit 0'


def is_usage_check(cwd, folder=None):
    """Is cwd the folder the plan-usage fetches run in (folder: this
    computer's; another copy's cache may be elsewhere, but its folder has
    the same names)?"""
    if not isinstance(cwd, str) or not cwd:
        return False
    cwd = os.path.normpath(cwd)
    return cwd == (str(folder) if folder else None) or cwd.endswith("/talpy-den/" + USAGE_CHECK_DIR)


def chat_at_work(row, now_ms, every_ms):
    """Does a chat use the plan now: a process at work (not one whose turn
    is over while a background shell runs), or one whose turn ended in the
    last every_ms (the interval) + USAGE_ACTIVE_MARGIN_MS?"""
    if row.get("pid") is None:
        return False
    if row["state"] == "working" and row.get("reason") != "background shell":
        return True
    return now_ms - (row.get("since") or 0) < every_ms + USAGE_ACTIVE_MARGIN_MS


def usage_refresh_profile(members, limits, rows, now_ms, every_ms):
    """The profile of an account (members) whose plan usage Claude Code
    should fetch now, or None: when its newest numbers (limits, as
    plan_limits gives them) are older than every_ms (the interval), or there
    are none, the first of its profiles with a chat at work (rows: {real
    folder: its rows}). Only a profile logged in to a Claude account counts:
    its oauthAccount, and its login in .credentials.json (which isn't opened)."""
    if limits and now_ms - limits["updatedAt"] < every_ms:
        return None
    for p in members:
        if p.account_id is None or not os.path.isfile(str(p.path / ".credentials.json")):
            continue
        if any(chat_at_work(s, now_ms, every_ms) for s in rows.get(p.real, ())):
            return p
    return None


def usage_now_profile(members, limits, now_ms):
    """Refresh: the profile of an account whose plan usage Claude Code should
    fetch now, chat at work or not (its numbers are older than USAGE_NOW_MS,
    or there are none), or None: its first profile logged in to a Claude
    account."""
    if limits and now_ms - limits["updatedAt"] < USAGE_NOW_MS:
        return None
    return next((p for p in members if p.account_id is not None
                 and os.path.isfile(str(p.path / ".credentials.json"))), None)


def fetch_usage_now(home, cache_root, extra_dirs=(), now=None):
    """Refresh: have Claude Code fetch the plan usage of every account logged
    in whose numbers are older than USAGE_NOW_MS, chat at work or not:
    {"ok", "started": the profiles it was started for}."""
    now_ms = int((time.time() if now is None else now) * 1000)
    profiles = discover_profiles(home, extra_dirs)
    logged_out = logged_out_notes(cache_root)
    due = []
    for _gid, members in group_profiles(profiles):
        if all(needs_login(p, logged_out) for p in members):
            continue
        asked = usage_now_profile(members, plan_limits(cache_root / "statusline", members, now_ms), now_ms)
        if asked is not None:
            due.append(asked)
    return {"ok": True, "started": [p.label for p in refresh_usage(home, cache_root, due, now_ms, USAGE_NOW_MS)]}


def usage_fetches(cache_root):
    """{profile key (its real folder): when a fetch of its plan usage started}."""
    data = read_json(cache_root / "usage-check.json")
    started = data.get("started") if isinstance(data, dict) else None
    return {k: t for k, t in started.items() if number(t) is not None} if isinstance(started, dict) else {}


def claim_usage_refresh(cache_root, key, now_ms, every_ms):
    """Is it this check's turn to fetch the plan usage of the profile key (its
    real folder)? Not when any copy of the widget did in the last every_ms
    (the interval), or when another one is deciding right now; when it is,
    it's noted."""
    private_dir(cache_root)
    with open(cache_root / "usage-check.lock", "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        data = read_json(cache_root / "usage-check.json")
        started = data.get("started") if isinstance(data, dict) else None
        started = {k: t for k, t in (started.items() if isinstance(started, dict) else ())
                   if number(t) is not None and now_ms - t < 86400_000}  # (a day on, forgotten)
        last = started.get(key)
        if last is not None and 0 <= now_ms - last < every_ms:  # (the clock set back: not)
            return False
        started[key] = now_ms
        write_json_atomic(cache_root / "usage-check.json", {"started": started})
        return True


def usage_refresh_command(profile, home, claude, folder):
    """(argv, env) of the command that has Claude Code fetch this profile's
    plan usage, run in folder: `claude -p /usage`, without hooks or a saved
    chat, ended after USAGE_REFRESH_LIMIT seconds (with timeout, if there is
    one); the empty memory folder Claude makes for folder goes after it."""
    import shutil
    env = {k: v for k, v in os.environ.items() if k not in SESSION_ENV}
    value = config_dir_value(profile, home)
    if value is None:
        env.pop("CLAUDE_CONFIG_DIR", None)
    else:
        env["CLAUDE_CONFIG_DIR"] = value
    folder_bin = os.path.dirname(claude)
    if folder_bin and os.path.isfile(os.path.join(folder_bin, "node")):
        env["PATH"] = folder_bin + os.pathsep + env.get("PATH", "")
    timeout = shutil.which("timeout")
    limit = [timeout, "-k", "10", str(USAGE_REFRESH_LIMIT)] if timeout else []
    projects = profile.path / "projects" / mangle(str(folder))
    argv = ["/bin/sh", "-c", USAGE_CHECK_SCRIPT, "sh", str(projects), *limit,
            claude, "-p", "/usage", "--no-session-persistence", "--setting-sources", "user", "--strict-mcp-config",
            "--settings", USAGE_CHECK_SETTINGS, "--output-format", "json"]
    return argv, env


def spawn_detached(argv, cwd, env):
    """Start argv on its own, not waited for (the check answers at once):
    nothing of ours open in it, in a session of its own. A check is a short
    process, so once it's gone, init takes it over and reaps it."""
    import subprocess
    return subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=True)


def refresh_usage(home, cache_root, due, now_ms, every_ms):
    """Have Claude Code fetch the plan usage of the profiles due
    (usage_refresh_profile's), each unless another check did in the last
    every_ms: the profiles it was started for. Nothing without a claude
    command."""
    if not due:
        return []
    claude = find_claude(home)
    if claude == "claude":  # (not found)
        return []
    folder = cache_root / USAGE_CHECK_DIR
    private_dir(folder)
    started = []
    for p in due:
        if not claim_usage_refresh(cache_root, str(p.real), now_ms, every_ms):
            continue
        argv, env = usage_refresh_command(p, home, claude, folder)
        spawn_detached(argv, str(folder), env)
        started.append(p)
    return started


# ---------------------------------------------------------------- token totals


def empty_token_cache():
    return {"version": CACHE_VERSION, "scannedAt": 0, "files": {}, "messages": {}}


def transcript_files(profile):
    """(path, reached through a linked folder) of every transcript under the
    profile's projects/. Linked folders are followed: a shared chat's folder
    (its subagents) is a link into the shared store."""
    out, seen, stack = [], set(), [(profile.real / "projects", False)]
    while stack:
        folder, linked = stack.pop()
        try:
            real = os.path.realpath(folder)
            if real in seen:
                continue
            seen.add(real)
            with os.scandir(folder) as it:
                entries = list(it)
        except OSError:
            continue
        for e in entries:
            try:
                if e.is_dir():
                    stack.append((Path(e.path), linked or e.is_symlink()))
                elif e.name.endswith(".jsonl") and e.is_file():
                    out.append((Path(e.path), linked))
            except OSError:
                continue
    return out


def token_cache_path(cache_root, profile):
    # Named after the real folder: ~/.claude can be switched between profiles
    return cache_root / f"tokens-{profile.key}-{short_id(str(profile.real))[:8]}.json"


TOKEN_CACHE_KEEP_S = 7 * 86400  # another profile's token cache, not updated for this long, goes
TOKEN_CACHE_NAME = re.compile(r"^tokens-.+-[0-9a-f]{8}\.json$")  # token_cache_path's names


def prune_token_caches(cache_root, profiles, now=None):
    """Delete token caches of profiles that are gone (or of an older format).
    Another copy of this script may watch other profiles (its own extra
    config dirs), so a cache this copy doesn't know is only deleted once no
    copy has updated it for a while."""
    keep = {token_cache_path(cache_root, p).name for p in profiles}
    now = time.time() if now is None else now
    try:
        files = list(cache_root.glob("tokens-*.json"))
    except OSError:
        return
    for f in files:
        older_format = not TOKEN_CACHE_NAME.match(f.name)
        if f.name not in keep and (older_format or now - (mtime(f) or now) > TOKEN_CACHE_KEEP_S):
            try:
                f.unlink()
            except OSError:
                pass


def scan_transcripts(profile, cache, now):
    """Incrementally read new transcript lines into cache["messages"].

    messages: {message id: [day, model, input, output, cacheRead, cacheWrite,
    shared, project folder, chat id]}, shared = 1 when the transcript is
    hard-linked elsewhere or sits in a linked folder (a chat shared with
    another profile: it counts on both accounts). Claude writes one line per
    content block, each repeating the message's usage (the last one sometimes
    with the final output count), so lines are merged by message id with an
    element-wise max. Messages are kept TOKEN_DAYS; their per-day sums
    (history, for the stats) STATS_DAYS, read back that far on a cache's first scan.
    """
    days_back = TOKEN_DAYS if "history" in cache else STATS_DAYS
    cutoff_day = (date.fromtimestamp(now) - timedelta(days=days_back - 1)).isoformat()
    cutoff_mtime = now - days_back * 86400
    if "history" in cache:
        messages, old_files = {k: v for k, v in cache["messages"].items() if v[0] >= cutoff_day}, cache["files"]
    else:  # a cache from before the stats: read everything again, STATS_DAYS back
        messages, old_files = {}, {}
    files = {}
    # each chat's tokens count for the folder it started in (Claude may cd elsewhere)
    started_in = cache.get("chatFolders") if isinstance(cache.get("chatFolders"), dict) else {}

    def add(line, shared, chat):
        if b'"usage"' not in line:
            return
        try:
            e = json.loads(line)
        except (ValueError, RecursionError):
            return
        if not isinstance(e, dict) or e.get("type") != "assistant" or not isinstance(e.get("message"), dict):
            return
        m = e["message"]
        u = m.get("usage")
        if not isinstance(u, dict):
            return
        day = local_day(e.get("timestamp"))
        if day is None or day < cutoff_day:
            return
        vals = [int(number(u.get(k)) or 0) for k in (
            "input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")]
        if not any(vals):
            return
        key = m.get("id") or e.get("requestId") or e.get("uuid")
        if not isinstance(key, str) or not key:
            return
        prev = messages.get(key)
        cwd = e.get("cwd") if isinstance(e.get("cwd"), str) else ""
        if cwd:
            cwd = started_in.setdefault(chat, cwd)
        if prev:
            vals = [max(a, b) for a, b in zip(prev[2:6], vals)]
            day = prev[0]
            shared = shared or bool(prev[6])
            cwd = cwd or (prev[7] if len(prev) > 7 else "")
        model = m.get("model") if isinstance(m.get("model"), str) and m.get("model") else "unknown"
        messages[key] = [day, model, *vals, int(shared), cwd, chat]

    shared_chats = set()  # the chats whose transcripts are shared now
    for path, linked in transcript_files(profile):
        try:
            st = path.stat()
        except OSError:
            continue
        chat = path.stem if path.parent.name != "subagents" else path.parent.parent.name
        if st.st_nlink > 1 or linked:
            shared_chats.add(chat)
        rec = old_files.get(str(path))
        offset = 0
        if rec and rec.get("ino") == st.st_ino and rec.get("offset", 0) <= st.st_size:
            offset = rec["offset"]
        if offset == 0 and st.st_mtime < cutoff_mtime:
            offset = st.st_size  # untouched for longer than we keep data
        elif offset < st.st_size:
            try:
                with open(path, "rb") as f:  # line by line: a first scan can be 50 MB
                    f.seek(offset)
                    for line in f:
                        if not line.endswith(b"\n"):
                            break  # never consume a half-written last line
                        add(line, st.st_nlink > 1 or linked, chat)
                        offset += len(line)
            except OSError:
                pass
        files[str(path)] = {"offset": offset, "ino": st.st_ino}

    for v in messages.values():  # shared after its messages were read: the other account counts them all, too
        if len(v) > 8 and not v[6] and v[8] in shared_chats:
            v[6] = 1

    stats_from = (date.fromtimestamp(now) - timedelta(days=STATS_DAYS - 1)).isoformat()
    history = {d: v for d, v in (cache.get("history") or {}).items() if d >= stats_from}
    history.update(day_history(messages))  # days still in messages: summed again
    keep_from = (date.fromtimestamp(now) - timedelta(days=TOKEN_DAYS - 1)).isoformat()
    messages = {k: v for k, v in messages.items() if v[0] >= keep_from}
    cache["files"], cache["messages"], cache["scannedAt"], cache["history"] = files, messages, now, history
    listed = {v[8] for v in messages.values() if len(v) > 8} | {c for h in history.values() for c in h.get("chats", [])}
    cache["chatFolders"] = {c: f for c, f in started_in.items() if c in listed}
    cache["days"], cache["daysAt"] = day_totals(messages), now
    cache["prompts"] = scan_prompts(profile, cache.get("prompts"), stats_from)
    return cache


def day_history(messages):
    """Messages summed per day for the stats: {day: {"models": {model:
    [input, output, cacheRead, cacheWrite, messages]}, "projects": {folder:
    [tokens, output]}, "chats": [chat ids], "shared": {chat id: {"models",
    "projects"}}: the part of those in chats shared with other profiles, so
    the stats count them once when the messages are gone (count_once)}}."""
    out = {}
    for day, model, *rest in messages.values():
        vals = rest[:4]
        shared = len(rest) > 4 and bool(rest[4])
        project = rest[5] if len(rest) > 5 else ""
        chat = rest[6] if len(rest) > 6 else ""
        h = out.setdefault(day, {"models": {}, "projects": {}, "chats": [], "shared": {}})
        for sums in [h] + ([h["shared"].setdefault(chat, {"models": {}, "projects": {}})] if shared and chat else []):
            row = sums["models"].setdefault(model, [0, 0, 0, 0, 0])
            for i, v in enumerate(vals):
                row[i] += v
            row[4] += 1
            if project:
                pr = sums["projects"].setdefault(project, [0, 0])
                pr[0] += sum(vals)
                pr[1] += vals[1]
        if chat and chat not in h["chats"]:
            h["chats"].append(chat)
    return out


def count_once(histories):
    """Several profiles' day_history with each chat counted once on each day:
    a chat that more than one of them has on a day (one transcript linked
    into each) is taken out of all but one, by its sums kept apart ("shared";
    one with none kept apart, e.g. read before the chat was shared, is the
    one that counts it)."""
    out = [dict(h) for h in histories]
    for day in {d for h in histories for d in h}:
        holders = {}
        for i, h in enumerate(histories):
            if isinstance(h.get(day), dict):
                for chat in h[day].get("chats") or []:
                    holders.setdefault(chat, []).append(i)
        for chat, held in holders.items():
            apart = [i for i in held if isinstance((histories[i][day].get("shared") or {}).get(chat), dict)]
            if len(held) < 2 or not apart:
                continue
            keep = next((i for i in held if i not in apart), apart[0])
            for i in apart:
                if i != keep:
                    out[i][day] = without(out[i][day], histories[i][day]["shared"][chat])
    return out


def without(h, part):
    """A day of day_history with the sums of part (its "shared" of a chat) taken out."""
    h = dict(h, models=dict(h.get("models") or {}), projects=dict(h.get("projects") or {}))
    for section, size in (("models", 5), ("projects", 2)):
        for key, row in (part.get(section) or {}).items():
            have = h[section].get(key)
            if isinstance(have, list) and len(have) == size and isinstance(row, list) and len(row) == size:
                h[section][key] = [max(0, a - b) for a, b in zip(have, row)]
    return h


def scan_prompts(profile, rec, stats_from):
    """Your prompts per day and folder, from the profile's history.jsonl
    (read where it grew): {"offset", "ino", "days": {day: {folder: count}}}."""
    path = profile.real / "history.jsonl"
    rec = rec if isinstance(rec, dict) and isinstance(rec.get("days"), dict) else {"offset": 0, "ino": None, "days": {}}
    try:
        st = path.stat()
    except OSError:
        return {"offset": 0, "ino": None, "days": {}}
    offset = rec.get("offset", 0) if rec.get("ino") == st.st_ino and rec.get("offset", 0) <= st.st_size else 0
    days = {d: v for d, v in rec["days"].items() if d >= stats_from} if offset else {}
    if offset < st.st_size:
        try:
            with open(path, "rb") as f:
                f.seek(offset)
                chunk = f.read()
        except OSError:
            chunk = b""
        end = chunk.rfind(b"\n")
        if end >= 0:
            for line in chunk[:end].splitlines():
                try:
                    e = json.loads(line)
                except (ValueError, RecursionError):
                    continue
                day = local_day(e.get("timestamp")) if isinstance(e, dict) else None
                if day is None or day < stats_from:
                    continue
                folder = e.get("project") if isinstance(e.get("project"), str) else ""
                by_folder = days.setdefault(day, {})
                by_folder[folder] = by_folder.get(folder, 0) + 1
            offset += end + 1
    return {"offset": offset, "ino": st.st_ino, "days": days}


def token_stats(caches, now, home, shown=STATS_SHOWN_DAYS):
    """The last days of an account, for its stats: {"days": [{"day", "total",
    "output", "messages", "chats", "prompts"}] oldest first, "projects":
    [{"name", "path", "total", "output", "prompts"}] busiest first, "models":
    [{"model", "total"}], "sum": {"total", "output", "chats", "prompts",
    "activeDays"}}, or None before any history is kept."""
    if not any(isinstance(c.get("history"), dict) for c in caches):
        return None
    today = date.fromtimestamp(now)
    names = [(today - timedelta(days=i)).isoformat() for i in range(shown - 1, -1, -1)]
    first = names[0]
    days = {d: {"day": d, "total": 0, "output": 0, "messages": 0, "chats": set(), "prompts": 0} for d in names}
    projects, models = {}, {}
    histories = [cache.get("history") or {} for cache in caches]
    if len(caches) > 1:  # the days the caches still have messages of: each message once
        recent = day_history(merged_messages(caches))
        histories = count_once([{d: h for d, h in history.items() if d not in recent} for history in histories])
        histories.append(recent)
    for history in histories:
        for day, h in history.items():
            if day < first or day not in days or not isinstance(h, dict):
                continue
            d = days[day]
            for model, row in (h.get("models") or {}).items():
                if isinstance(row, list) and len(row) == 5:
                    d["total"] += sum(row[:4])
                    d["output"] += row[1]
                    d["messages"] += row[4]
                    models[model] = models.get(model, 0) + sum(row[:4])
            for folder, sums in (h.get("projects") or {}).items():
                if isinstance(sums, list) and len(sums) == 2:
                    p = projects.setdefault(folder, {"total": 0, "output": 0, "prompts": 0})
                    p["total"] += sums[0]
                    p["output"] += sums[1]
            d["chats"].update(h.get("chats") or [])
    for cache in caches:  # each profile's own prompts (its history.jsonl)
        for day, by_folder in ((cache.get("prompts") or {}).get("days") or {}).items():
            if day in days and isinstance(by_folder, dict):
                for folder, n in by_folder.items():
                    days[day]["prompts"] += n
                    projects.setdefault(folder, {"total": 0, "output": 0, "prompts": 0})["prompts"] += n
    chats = set()
    for d in days.values():
        chats |= d["chats"]
        d["chats"] = len(d["chats"])
    rows = [days[n] for n in names]
    top = sorted(((f, p) for f, p in projects.items() if f and p["total"]), key=lambda fp: (-fp[1]["total"], -fp[1]["prompts"]))
    return {
        "days": rows,
        "projects": [{"name": "~" if short_path(f, home) == "~" else os.path.basename(f.rstrip("/")) or f,
                      "path": short_path(f, home), **p} for f, p in top[:6]],
        "models": [{"model": model_label(m) or m, "total": t}
                   for m, t in sorted(models.items(), key=lambda mt: -mt[1]) if t],
        "sum": {"total": sum(d["total"] for d in rows), "output": sum(d["output"] for d in rows),
                "chats": len(chats), "prompts": sum(d["prompts"] for d in rows),
                "activeDays": sum(1 for d in rows if d["messages"] or d["prompts"])},
    }


def day_totals(messages):
    """The messages summed per day and model: {day: {model: [input, output,
    cacheRead, cacheWrite, messages, shared tokens]}}. Kept with the cache, so
    a status check (every 2 s) adds up a few rows, not every message of the
    week (thousands for a busy week)."""
    days = {}
    for day, model, *rest in messages.values():
        vals, shared = rest[:4], bool(rest[4]) if len(rest) > 4 else False
        row = days.setdefault(day, {}).setdefault(model, [0, 0, 0, 0, 0, 0])
        for i, v in enumerate(vals):
            row[i] += v
        row[4] += 1
        if shared:
            row[5] += sum(vals)
    return days


def load_token_cache(cache_root, profile, now, lock_held):
    path = token_cache_path(cache_root, profile)
    cache = read_json(path)
    if not isinstance(cache, dict) or cache.get("version") != CACHE_VERSION:
        cache = empty_token_cache()
    since = now - (number(cache.get("scannedAt")) or 0)
    # a scan "from the future" (the clock was set back since) is due too
    if lock_held and (since >= TOKEN_SCAN_INTERVAL or since < -TOKEN_SCAN_INTERVAL):
        cache = scan_transcripts(profile, cache, now)
        try:
            write_json_atomic(path, cache)
        except OSError:
            pass
    return cache


def merged_messages(caches):
    """The messages of several profiles' caches, each once: profiles logged
    into one account can hold the same message (a chat shared between them,
    or a copy of one)."""
    merged = {}
    for cache in caches:
        for key, value in (cache.get("messages") or {}).items():
            merged.setdefault(key, value)
    return merged


def token_totals(caches, now):
    today = date.fromtimestamp(now).isoformat()
    week_start = (date.fromtimestamp(now) - timedelta(days=6)).isoformat()
    keys = ("input", "output", "cacheRead", "cacheWrite")

    def zero():
        return dict(dict.fromkeys(keys, 0), total=0, messages=0, shared=0)

    totals = {"today": zero(), "week": zero()}
    models = {}
    if len(caches) > 1:
        sums = [day_totals(merged_messages(caches))]
    else:
        sums = []
        for cache in caches:
            days = cache.get("days")
            if not isinstance(days, dict) or cache.get("daysAt") != cache.get("scannedAt"):
                # saved before the sums were kept, or rescanned by an older version
                days = day_totals(cache["messages"])
            sums.append(days)
    for days in sums:
        for day, by_model in days.items():
            if day < week_start or not isinstance(by_model, dict):
                continue
            buckets = [totals["week"]] + ([totals["today"]] if day == today else [])
            for model, row in by_model.items():
                if not isinstance(row, list) or len(row) != 6:
                    continue
                vals, count, shared = row[:4], row[4], row[5]
                for b in buckets:
                    for k, v in zip(keys, vals):
                        b[k] += v
                    b["total"] += sum(vals)
                    b["messages"] += count
                    b["shared"] += shared
                models[model] = models.get(model, 0) + sum(vals)
    totals["models"] = [{"model": m, "total": t} for m, t in sorted(models.items(), key=lambda x: -x[1])]
    return totals


class ScanLock:
    """Non-blocking lock so overlapping polls don't scan transcripts twice."""

    def __init__(self, path):
        self.path, self.fd, self.held = path, None, False

    def __enter__(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.held = True
        except OSError:
            self.held = False
        return self

    def __exit__(self, *exc):
        if self.fd is not None:
            os.close(self.fd)


# ---------------------------------------------------------------- dismissed sessions


def cache_dir(home):
    return Path(os.environ.get("XDG_CACHE_HOME") or home / ".cache") / "talpy-den"


# What Talpy Den acts on by itself is kept apart from the cache: other
# programs are sometimes given ~/.cache (a container sharing pip's
# downloads), and must not be able to queue a task, keep a chat going, change
# the settings every copy takes over, the rules the Permissions tab undoes,
# which user Talpy Den works as in a container or the containers VS Code may
# attach to, nor answer a permission prompt.
STATE_FILES = ("queue.json", "keep.json", "settings.json", "rules.json", "containers.json")
_STATE = {}  # (state_dir's answers)


def state_dir(cache_root):
    """The folder of what Talpy Den acts on (STATE_FILES, the permission
    hook's requests), beside the cache folder: $XDG_STATE_HOME/talpy-den for
    the usual cache when that's set, else ~/.local/state/talpy-den for
    ~/.cache/talpy-den (<home>/.local/state/<name> for any <home>/.cache/<name>),
    state/<name> in the folder of any other cache folder <name> (as the
    permission hook finds it). What an older version kept in the cache moves
    there the first time (move_to_state)."""
    key = (str(cache_root), os.environ.get("XDG_CACHE_HOME"), os.environ.get("XDG_STATE_HOME"), os.environ.get("HOME"))
    state = _STATE.get(key)  # (worked out once a run)
    if state is None:
        cache_root = Path(cache_root)
        usual = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "talpy-den"
        if os.environ.get("XDG_STATE_HOME") and cache_root == usual:
            state = Path(os.environ["XDG_STATE_HOME"]) / "talpy-den"
        elif cache_root.parent.name == ".cache":
            state = cache_root.parent.parent / ".local" / "state" / cache_root.name
        else:
            state = cache_root.parent / "state" / cache_root.name
        _STATE[key] = state
        if not os.path.exists(state / ".moved"):
            move_to_state(cache_root, state)
    return state


def move_to_state(cache_root, state):
    """STATE_FILES an older version kept in the cache move to state, at the
    first check (.moved notes it, so one put in the cache later is never
    taken): under a lock, so two checks starting at once move them once and
    anything else needing them waits until they're there. A file already in
    state stays; the cache's copy goes either way."""
    there = [n for n in STATE_FILES if os.path.lexists(cache_root / n)]
    try:  # (made now, with nothing to move too: only what an older version left is ever taken)
        private_dir(state)
        fd = os.open(str(state / ".moved.lock"), os.O_CREAT | os.O_RDWR | getattr(os, "O_CLOEXEC", 0), 0o600)
    except OSError:
        return
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        if os.path.exists(state / ".moved"):
            return
        for name in there:
            old, new = cache_root / name, state / name
            try:
                if not os.path.lexists(new):
                    data = read_plain(old)  # (a plain file only, as one of ours is)
                    if data is not None:
                        try:
                            os.rename(old, new)  # (in one go; another disk: a copy)
                            continue
                        except OSError:
                            write_atomic(new, data, 0o600, new=True)
                os.unlink(old)
            except OSError:
                pass
        for name in ("queue.lock", "keep.lock", ".containers.lock"):  # (theirs: unused now)
            try:
                os.unlink(cache_root / name)
            except OSError:
                pass
        os.close(os.open(str(state / ".moved"), os.O_CREAT | os.O_WRONLY, 0o600))
    except OSError:
        pass
    finally:
        os.close(fd)


def adopt_legacy_dirs(home):
    """The folders an earlier version kept under its first name, claude-widget
    (in the cache and in ~/.local/share), move to talpy-den. A link stays under
    the old name: Claude's settings (the hooks) and the status-line snippet
    still name it until the next ./install.sh brings them up to date."""
    for base in (Path(os.environ.get("XDG_CACHE_HOME") or home / ".cache"),
                 Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share")):
        old, new = base / "claude-widget", base / "talpy-den"
        try:
            if old.is_symlink() or not old.is_dir():
                continue
            new.mkdir(parents=True, exist_ok=True)
            os.chmod(new, 0o700)
            for child in list(old.iterdir()):
                if not os.path.lexists(new / child.name):
                    os.rename(child, new / child.name)
            old.rmdir()  # (not while something is left in it: then it stays as it was)
            os.symlink(new, old)
        except OSError:
            continue


# ---------------------------------------------------------------- starred chats and plans
#
# Chats and plans you starred stay at hand: each account lists its starred
# ones however old they are (group["starred"], group["starredPlans"]). The
# stars are this computer's (stars.json in the widget's cache, an SSH host's
# under its name): the status run on a host gets that host's from here
# (remote.status: --starred-chats, --starred-plans).

STAR_KINDS = ("chats", "plans")


def load_stars(cache_root):
    """{"chats": [{"id", "host"}], "plans": [{"id", "host"}]}: what you
    starred, in the order you did ("host": "" for this computer's)."""
    data = read_json(cache_root / "stars.json")
    data = data if isinstance(data, dict) else {}
    valid = {"chats": valid_id, "plans": lambda v: isinstance(v, str) and bool(PLAN_SLUG.match(v))}
    out = {}
    for kind in STAR_KINDS:
        items = data.get(kind) if isinstance(data.get(kind), list) else []
        out[kind] = [{"id": i["id"], "host": i.get("host") or ""} for i in items
                     if isinstance(i, dict) and valid[kind](i.get("id")) and isinstance(i.get("host") or "", str)]
    return out


def change_stars(cache_root, kind, item_id, host="", on=True):
    """Star a chat or a plan (kind "chats" or "plans"), or (not on) not any
    more, under a lock: every copy of the widget writes stars.json."""
    private_dir(cache_root)
    with open(cache_root / "stars.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        stars = load_stars(cache_root)
        items = [i for i in stars[kind] if (i["id"], i["host"]) != (item_id, host or "")]
        if on:
            items.append({"id": item_id, "host": host or ""})
        if items != stars[kind]:
            stars[kind] = items
            write_json_atomic(cache_root / "stars.json", stars)


def starred_of(stars, host=""):
    """{"chats": ids, "plans": slugs} starred of this computer (or of host)."""
    return {kind: {i["id"] for i in stars[kind] if i["host"] == (host or "")} for kind in STAR_KINDS}


# ---------------------------------------------------------------- bookmarked messages
#
# Talpy Chat's bookmarks: the messages of a chat you bookmarked, listed on its
# side to go back to. A chat's are a file of their own in the widget's cache
# (bookmarks/<chat>.json; an SSH host's or a container's chat's under
# host-<short_id(host)>/, kept here as stars are), each with its message's key
# (pane.py's item key), when it was written and its first BOOKMARK_TEXT
# characters, so the list can show one before it's loaded. v grows with every
# change, so a front end can tell a newer list from an older one.

BOOKMARKS_DIR = "bookmarks"
BOOKMARKS_MAX = 100  # a chat's bookmarks at most
BOOKMARK_TEXT = 140  # characters of a message's text kept with its bookmark
BOOKMARK_KEY = re.compile(r"^[A-Za-z0-9_.:@-]{1,200}$")  # (matched whole: fullmatch, as $ lets a last \n by)
BOOKMARKS_READ = 256 << 10  # bytes of a file read at most (100 of the longest keys and texts, written as JSON escapes)
BOOKMARK_KINDS = ("you", "claude")
BOOKMARK_FULL = "A chat keeps up to %d bookmarks: remove one first" % BOOKMARKS_MAX


def bookmark_key_ok(key):
    """A message's key a bookmark can be of: never a message on its way (pending-N) nor a word that is a flag."""
    return isinstance(key, str) and bool(BOOKMARK_KEY.fullmatch(key)) and not key.startswith(("pending-", "-"))


def bookmark_text(text):
    """A message's text as its bookmark keeps it: on one line, its first BOOKMARK_TEXT characters (… where cut)."""
    text = " ".join(text.split()) if isinstance(text, str) else ""
    return text if len(text) <= BOOKMARK_TEXT else text[:BOOKMARK_TEXT - 1].rstrip() + "…"


def bookmarks_folder(cache_root, host=""):
    """Where a computer's bookmark files are: a host's under the hash of its name, never the name itself."""
    folder = Path(cache_root) / BOOKMARKS_DIR
    return folder / ("host-" + short_id(host)) if host else folder


def bookmarks_path(cache_root, chat, host=""):
    """A chat's bookmark file, or None for something that isn't a chat id."""
    if not valid_id(chat) or "\0" in chat:
        return None
    return bookmarks_folder(cache_root, host) / (chat + ".json")


def whole_ms(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def load_bookmarks(cache_root, chat, host=""):
    """(marks, v): a chat's bookmarks, in the chat's order ((at, made)), each
    {"key", "kind", "at", "text", "made"}, and its file's version; ([], 0)
    when it has none (no file: one failed open). Malformed ones are left out."""
    path = bookmarks_path(cache_root, chat, host)
    data = read_json(path, BOOKMARKS_READ) if path is not None else None
    if not isinstance(data, dict):
        return [], 0
    marks, seen, key_ok = [], set(), BOOKMARK_KEY.fullmatch
    for m in data.get("marks") if isinstance(data.get("marks"), list) else ():  # (read at every look at the chat)
        key = m.get("key") if type(m) is dict else None
        if type(key) is not str or key in seen or not key_ok(key) or key[0] == "-" or key.startswith("pending-") \
                or m.get("kind") not in BOOKMARK_KINDS:
            continue
        seen.add(key)
        at, made, text = m.get("at"), m.get("made"), m.get("text")
        marks.append({"key": key, "kind": m["kind"], "at": at if type(at) is int and at > 0 else 0,
                      "text": text if type(text) is str and len(text) <= BOOKMARK_TEXT and "\n" not in text
                      else bookmark_text(text), "made": made if type(made) is int and made > 0 else 0})
        if len(marks) == BOOKMARKS_MAX:
            break
    marks.sort(key=lambda m: (m["at"], m["made"]))
    return marks, whole_ms(data.get("v")) or 1


def save_bookmarks(cache_root, chat, host, marks, v):
    """Write a chat's bookmark file (in folders only you can open, a file only you can read; in one go)."""
    private_dir(Path(cache_root) / BOOKMARKS_DIR)
    if host:
        private_dir(bookmarks_folder(cache_root, host))
    data = {"chat": chat, "host": host or "", "v": v, "marks": marks}
    write_json_atomic(bookmarks_path(cache_root, chat, host), data, private=True)


@contextlib.contextmanager
def bookmarks_lock(cache_root):
    """Every copy of pane.py and of the status check changes bookmark files under it."""
    private_dir(Path(cache_root))
    with open(Path(cache_root) / "bookmarks.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def change_bookmark(cache_root, chat, host, key, on, kind="", at=0, text="", now_ms=None):
    """Bookmark a chat's message (on: of kind "you" or "claude", written at
    at ms, its text), or not any more: (ok, what went wrong, the chat's
    bookmarks now, their v). Adding one twice keeps one, removing one that
    isn't there is done. A file whose last bookmark went stays (v only ever
    grows: forget_bookmarks alone deletes it)."""
    if bookmarks_path(cache_root, chat, host) is None:
        return False, f"Not a chat: {chat}", [], 0
    if not bookmark_key_ok(key) or (on and kind not in BOOKMARK_KINDS):
        return (False, "Which message?") + load_bookmarks(cache_root, chat, host)
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    with bookmarks_lock(cache_root):
        marks, v = load_bookmarks(cache_root, chat, host)
        if bool(on) == any(m["key"] == key for m in marks):
            return True, "", marks, v
        if on and len(marks) >= BOOKMARKS_MAX:
            return False, BOOKMARK_FULL, marks, v
        new = [m for m in marks if m["key"] != key]
        if on:
            new.append({"key": key, "kind": kind, "at": whole_ms(at), "text": bookmark_text(text), "made": now_ms})
            new.sort(key=lambda m: (m["at"], m["made"]))
        try:
            save_bookmarks(cache_root, chat, host, new, max(v + 1, now_ms))
        except OSError as exc:
            return False, exc.strerror or str(exc), marks, v
        return True, "", new, max(v + 1, now_ms)


def bookmarks_answer(result, cache_root, chat, host=""):
    """Add a chat's bookmarks to pane.py's answer (bookmarks, bookmarksV) when it has a bookmark file."""
    marks, v = load_bookmarks(cache_root, chat, host)
    if v > 0:
        result["bookmarks"] = marks
        result["bookmarksV"] = v
    return result


def bookmarks_moved(cache_root, moves, host=""):
    """The bookmarks of chats Claude moved to the background under a new id
    (moves: chat_moves, or a host's) go with them: merged into the file of
    the id each goes on under (moved_chat; its own bookmarks win), the old
    file deleted. One listing of the folder when none moved."""
    try:
        names = set(os.listdir(bookmarks_folder(cache_root, host)))
    except OSError:
        return
    olds = [(old, moved_chat(old, moves)) for old in moves if old + ".json" in names]
    olds = [(old, new) for old, new in olds if new != old and bookmarks_path(cache_root, old, host) is not None
            and bookmarks_path(cache_root, new, host) is not None]
    if not olds:
        return
    now_ms = int(time.time() * 1000)
    with bookmarks_lock(cache_root):
        for old, new in olds:
            old_marks, old_v = load_bookmarks(cache_root, old, host)
            if old_v:
                marks, v = load_bookmarks(cache_root, new, host)
                keep = {m["key"]: m for m in marks}
                for m in sorted(old_marks, key=lambda m: -m["made"]):  # (the newest first, up to the cap)
                    if len(keep) >= BOOKMARKS_MAX:
                        break
                    keep.setdefault(m["key"], m)
                merged = sorted(keep.values(), key=lambda m: (m["at"], m["made"]))
                save_bookmarks(cache_root, new, host, merged, max(max(v, old_v) + 1, now_ms))
            forget_bookmarks(cache_root, old, host)


def forget_bookmarks(cache_root, chat, host=""):
    """A deleted chat's bookmarks go (its file)."""
    path = bookmarks_path(cache_root, chat, host)
    if path is None:
        return
    try:
        os.unlink(path)
    except OSError:  # (none: Python 3.7 has no missing_ok; nor anything else, a delete goes on)
        pass


def load_dismissed(cache_root):
    """Finished sessions the user removed from the widget's list: {session id: when}."""
    data = read_json(cache_root / "dismissed.json")
    sessions = data.get("sessions") if isinstance(data, dict) else None
    return dict(sessions) if isinstance(sessions, dict) else {}


def save_dismissed(cache_root, sessions):
    write_json_atomic(cache_root / "dismissed.json", {"sessions": sessions})


DISMISSED_KEEP_MS = 30 * 86400_000  # a removed session not seen again for this long is forgotten


def change_dismissed(cache_root, add=None, forget=(), clear=False, now_ms=None):
    """Change dismissed.json (add a session id, forget some, or clear it)
    under a lock: every copy of this script and jump.py write it. The
    sessions removed now."""
    private_dir(cache_root)
    with open(cache_root / "dismissed.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        sessions = load_dismissed(cache_root)
        before = dict(sessions)
        if clear:
            sessions = {}
        for i in forget:
            sessions.pop(i, None)
        if add is not None:
            sessions[add] = int(time.time() * 1000) if now_ms is None else now_ms
        if sessions != before or not (cache_root / "dismissed.json").exists():
            save_dismissed(cache_root, sessions)
        return sessions


# ---------------------------------------------------------------- hidden plans, memories and projects
#
# Hide (the × on a line) leaves a chat, a plan, a memory or a project out of
# its list, on this computer (an SSH host's on that host: remote.py --hide);
# Show Hidden … Again brings that kind back. Chats are kept in dismissed.json
# (above), the others in hidden.json: a plan by its slug, a memory by its
# key, a project by its folder. Nothing of Claude's is touched.

HIDE_KINDS = ("chats", "plans", "memories", "projects")
HIDE_WORDS = {"chats": ("chat", "chats"), "plans": ("plan", "plans"), "memories": ("memory", "memories"),
              "projects": ("project", "projects")}
HIDDEN_ID_MAX = 4096


def hidden_id_ok(kind, item_id):
    if kind == "chats":
        return valid_id(item_id)
    if kind == "plans":
        return isinstance(item_id, str) and bool(PLAN_SLUG.match(item_id))
    return (isinstance(item_id, str) and 0 < len(item_id) <= HIDDEN_ID_MAX and "\n" not in item_id
            and (kind != "projects" or item_id.startswith("/")))


def load_hidden(cache_root):
    """{"plans": {slug: when}, "memories": {key: when}, "projects": {folder: when}}: what you hid."""
    data = read_json(cache_root / "hidden.json")
    data = data if isinstance(data, dict) else {}
    out = {}
    for kind in HIDE_KINDS[1:]:
        items = data.get(kind) if isinstance(data.get(kind), dict) else {}
        out[kind] = {i: t for i, t in items.items() if hidden_id_ok(kind, i)}
    return out


def change_hidden(cache_root, kind, add=None, forget=(), clear=False, now_ms=None):
    """Change what's hidden of kind ("plans", "memories", "projects") under
    a lock: every copy of Talpy Den writes hidden.json. What's hidden of it now."""
    private_dir(cache_root)
    with open(cache_root / "hidden.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        hidden = load_hidden(cache_root)
        before = dict(hidden[kind])
        if clear:
            hidden[kind] = {}
        for i in forget:
            hidden[kind].pop(i, None)
        if add is not None:
            hidden[kind][add] = int(time.time() * 1000) if now_ms is None else now_ms
        if hidden[kind] != before:
            write_json_atomic(cache_root / "hidden.json", hidden)
        return hidden[kind]


def hide_item(cache_root, kind, item_id):
    """Hide a chat, a plan, a memory or a project (kind chats, plans,
    memories, projects): (ok, message)."""
    if kind not in HIDE_KINDS:
        return False, "Only chats, plans, memories and projects can be hidden"
    one = HIDE_WORDS[kind][0]
    if not hidden_id_ok(kind, item_id):
        return False, f"Not a {one}: {item_id}"
    if kind == "chats":
        change_dismissed(cache_root, add=item_id)
    else:
        change_hidden(cache_root, kind, add=item_id)
    return True, f"Hid this {one}"


def show_hidden(cache_root, kind):
    """Show the hidden chats (plans, memories, projects) again: (ok, message)."""
    if kind not in HIDE_KINDS:
        return False, "Only chats, plans, memories and projects can be hidden"
    one, many = HIDE_WORDS[kind]
    count = len(load_dismissed(cache_root) if kind == "chats" else load_hidden(cache_root)[kind])
    if not count:
        return True, f"No {one} was hidden"
    if kind == "chats":
        change_dismissed(cache_root, clear=True)
    else:
        change_hidden(cache_root, kind, clear=True)
    return True, f"Showing {count} hidden {one if count == 1 else many} again"


def queued_for_plan(cache_root, slug, host=""):
    """The queued tasks that carry out the plan slug (of host: the queue is kept here)."""
    return [t for t in load_queue(cache_root) if t.get("plan") == slug and (t.get("host") or "") == (host or "")]


def plan_tasks_go(tasks):
    """What Delete's question adds for a plan's queued tasks (queued_for_plan): they go with it."""
    if not tasks:
        return ""
    return " So does the task queued to carry it out." if len(tasks) == 1 else \
        f" So do the {len(tasks)} tasks queued to carry it out."


def forget_deleted(cache_root, kind, item_id, host=""):
    """A chat, a plan or a memory was deleted (sharing.delete_chat, …):
    the stars, a chat's bookmarks, the queue, keep going and what's hidden
    here forget it (of host: its stars, bookmarks, queued tasks and keep
    going, kept here; the rest is the host's). A plan's queued tasks go too,
    as a chat's go-ons (Delete's question says so: plan_tasks_go)."""
    if kind in ("chats", "plans"):
        change_stars(cache_root, kind, item_id, host, on=False)
    if kind == "plans" and queued_for_plan(cache_root, item_id, host):
        def drop(tasks):
            tasks[:] = [t for t in tasks if not (t.get("plan") == item_id and (t.get("host") or "") == (host or ""))]
            return True
        change_queue(cache_root, edit=drop)
    if kind == "chats":
        for t in load_queue(cache_root):
            if t.get("chat") == item_id and (t.get("host") or "") == (host or ""):
                change_queue(cache_root, take=t["id"])
        keep_chat(cache_root, "", item_id, on=False, host=host)
        forget_bookmarks(cache_root, item_id, host)
    if host:
        return
    if kind == "chats":
        change_dismissed(cache_root, forget=[item_id])
    else:
        change_hidden(cache_root, kind, forget=[item_id])
    if kind == "plans":
        change_plan_projects(cache_root, forget=[item_id])


# ---------------------------------------------------------------- main


class Context:
    """What one poll knows, handed to the row builders."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


def collect(home, cache_root, extra_dirs=(), with_tokens=True, now=None, keep_done_hours=KEEP_DONE_HOURS,
            recent=RECENT_CHATS, plans=PLANS_LISTED, usage_cap=0, starred=None, usage_refresh=0,
            memories=MEMORIES_LISTED, kept=None, history=None):
    """starred: {"chats", "plans"} starred here (starred_of), else this
    computer's from the cache. kept: chats here that keep going from the
    computer that asks (an SSH host's run: --kept-chats), listed as this
    computer's own (list_kept). history: the Recap's history setting
    (keep, since) of the computer that asks (--no-history, --history-since:
    the plan windows kept here follow it, follow_history), else this one's. usage_refresh: have Claude Code fetch the plan
    usage of an account whose numbers are older than this many minutes while
    one of its chats works, at most that often (refresh_usage; 0: never; the
    status check does)."""
    refresh_ms = max(0, usage_refresh) * 60_000
    now = time.time() if now is None else now
    now_ms = int(now * 1000)
    snapshot_root = cache_root / "statusline"
    profiles = discover_profiles(home, extra_dirs)
    counts = dict.fromkeys(STATE_ORDER, 0)
    errors, groups = [], []
    try:
        private_dir(cache_root)
    except OSError as exc:
        errors.append(f"cache: {exc}")

    histories = {p.real: history_tail(p) for p in profiles}
    ctx = Context(
        home=home, profiles=profiles, snapshot_root=snapshot_root, now_ms=now_ms,
        keep_done_ms=int(keep_done_hours * 3600_000),
        agents=AgentCache(cache_root / "agents.json"), links=LinkCache(cache_root / "links.json"),
        chats=ChatCache(cache_root / "chats.json"), slugs=SlugCache(cache_root / "plans.json"), changed={},
        tests=TestsCache(cache_root / "tests.json"),
        plan_dirs=PlanDirs(cache_root / "plan-dirs.json"), plan_projects=PlanProjects(cache_root),
        own_folders=own_folders(profiles),
        prompts={real: last_prompts(entries) for real, entries in histories.items()},
        errors=errors, unknown={}, usage_check=str(cache_root / USAGE_CHECK_DIR),
    )
    due = []  # the profiles whose plan usage Claude Code fetches now (refresh_usage)
    with ScanLock(cache_root / "tokens.lock") as lock:
        # read with the lock: the check holding it is the one that writes it
        usage = UsageHistory(cache_root / "usage.json")
        usage.history = history
        if lock.held:
            prune_snapshots(snapshot_root, now)
            if with_tokens:
                prune_token_caches(cache_root, profiles, now)

        all_transcripts(ctx)  # (once per check, now: the rows find shared chats in it, shared_transcripts)
        # Every live session process, under the profile it runs on now
        rows = {p.real: [] for p in profiles}
        live_jobs = set()
        try:
            live = live_entries_all(profiles)
        except Exception as exc:  # internal format: fail soft
            errors.append(f"sessions: {exc}")
            live = []
        for entry, profile, holder in live:
            note_unknown(ctx, entry)
            if valid_id(entry.get("jobId")):
                live_jobs.add(entry["jobId"])
            try:
                row = live_row(entry, profile, holder, home, ctx)
            except Exception as exc:
                errors.append(f"{profile.label}: chats: {exc}")
                continue
            if row is not None:
                rows[profile.real].append(row)
        # Background jobs with no process; a job held by two profiles (written
        # through a switched link) is listed once, from its newest record
        newest_job = {}
        newest = newest_job_records(profiles)
        for p in profiles:
            try:
                for row in parked_rows(p, home, live_jobs, ctx, newest):
                    prev = newest_job.get(row["jobId"])
                    if prev is None or (row["since"] or 0) > (prev[1]["since"] or 0):
                        newest_job[row["jobId"]] = (p, row)
            except Exception as exc:
                errors.append(f"{p.label}: background jobs: {exc}")
        for p, row in newest_job.values():
            rows[p.real].append(row)

        logged_out = logged_out_notes(cache_root)
        for gid, members in group_profiles(profiles):
            named = next((p for p in members if not p.is_default), members[0])
            plan = next((p.plan for p in members if p.plan), None)
            detail = next((p.plan_detail for p in members if p.plan), None)
            group = {
                # not logged in to an account: "Log in…" (accounts.py --login chatProfile)
                "loggedOut": all(needs_login(p, logged_out) for p in members),
                "id": short_id(gid),
                "name": named.label,
                "plan": plan,
                "planDetail": detail,  # with its tier: "Max 20×", "Team · standard seat"
                "title": f"{named.label} · {plan}" if plan else named.label,
                "profiles": [p.label for p in members],
                "profileKeys": [p.key for p in members],
                "sessions": [row for p in members for row in rows[p.real]],
                "limits": None,
                "tokens": None,
                "stats": None,  # the last days: per-day tokens, chats and prompts, busiest folders (token_stats)
                # for "new chat": the profile folder name jump.py --new-chat takes
                "chatProfile": named.key,
                # for sharing a chat with this account: the profile it goes to (jump.py --profile)
                "shareProfile": named.key,
                "projects": recent_projects([histories[p.real] for p in members], home),
            }
            # (a task can start in the background only where Claude trusts the folder)
            trusted = trusted_folders(named, home)
            for project in group["projects"]:
                project["trusted"] = folder_trusted(named, project["path"], home, trusted)
            try:
                # a logged-out account's last status lines are no one's plan usage now
                group["limits"] = None if group["loggedOut"] else plan_limits(snapshot_root, members, now_ms)
                stale = (usage_refresh_profile(members, group["limits"], rows, now_ms, refresh_ms)
                         if refresh_ms else None)
                if stale is not None and not group["loggedOut"]:
                    due.append(stale)
                if group["limits"]:
                    if lock.held:
                        usage.record(group["id"], group["limits"], now_ms, plan=detail)
                    for w in group["limits"]["windows"]:
                        w["forecast"] = usage_forecast(w, usage.points(group["id"], w), now_ms)
            except Exception as exc:
                errors.append(f"{group['title']}: limits: {exc}")
            if with_tokens:
                try:
                    caches = [load_token_cache(cache_root, p, now, lock.held) for p in members]
                    group["tokens"] = token_totals(caches, now)
                    group["stats"] = token_stats(caches, now, home)
                except Exception as exc:
                    errors.append(f"{group['title']}: tokens: {exc}")
            groups.append(group)
        usage.save()  # only this check noted anything (lock.held): others mustn't write it now
        if history is not None:
            follow_history(cache_root, history)

    try:
        refresh_usage(home, cache_root, due, now_ms, refresh_ms)
    except Exception as exc:
        errors.append(f"fetching plan usage: {exc}")
    # (an account's fetch on its way: its numbers say so until they come)
    fetches = usage_fetches(cache_root)
    for g in groups:
        # (claimed under whichever of its folders fetches: usage_refresh_profile, usage_now_profile)
        at = [fetches.get(str(p.real)) for p in profiles if p.key in g.get("profileKeys", ())]
        g["usageFetchAt"] = max((t for t in at if t is not None), default=None)
    try:
        place_chats(groups, ctx)
    except Exception as exc:
        errors.append(f"shared chats: {exc}")
    try:
        follow_moved(groups, ctx)
    except Exception as exc:
        errors.append(f"chats moved to the background: {exc}")
    try:
        list_kept(groups, ctx, [k for k in load_keep(cache_root)["chats"] if not k["host"]] + list(kept or []))
    except Exception as exc:
        errors.append(f"chats that keep going: {exc}")
    try:
        note_moved(groups, ctx)
    except Exception as exc:
        errors.append(f"chats moved to the background: {exc}")
    try:
        note_attached(groups, profiles)
    except Exception as exc:
        errors.append(f"background chats in terminals: {exc}")
    # Removed from the list by the user: hidden while finished; one that runs
    # again comes back (and is forgotten).
    dismissed = load_dismissed(cache_root)
    try:
        # (a chat you hid that Claude moved to the background under a new id: hidden there too)
        moves = chat_moves(ctx)
        for old in [i for i in dismissed if i in moves]:
            dismissed = change_dismissed(cache_root, add=moved_chat(old, moves), forget=[old], now_ms=dismissed[old])
    except Exception as exc:
        errors.append(f"hidden chats moved to the background: {exc}")
    try:
        # (a chat Claude moved to the background under a new id: its bookmarks go with it, in the check
        # whose answer tells a window it moved; one listing of a folder while a chat moved lately)
        moves = chat_moves(ctx)
        if moves:
            bookmarks_moved(cache_root, moves)
    except Exception as exc:
        errors.append(f"bookmarks of moved chats: {exc}")
    forget, dismissed_rows = set(), 0
    for g in groups:
        shown = []
        for s in g["sessions"]:
            # a record moved to the account the chat was used on last keeps
            # the ids it had where it was removed
            former = s.pop("formerIds", None) or []
            ids = [i for i in (s["sessionId"], s.get("chatId"), *former) if i in dismissed]
            if ids and s["state"] == "done":
                dismissed_rows += 1
            else:
                forget.update(ids)  # it runs again: it comes back (and is forgotten)
                shown.append(s)
        # The chats that need you first (the one asking longest first), the
        # others in the order they started, the newest last: a row (and its
        # pet) moves only when its chat starts or stops needing you
        g["sessions"] = sorted(shown, key=lambda s: (0, s["since"] or 0, s["key"]) if s["state"] == "waiting"
                               else (1, s.get("startedAt") or s["since"] or 0, s["key"]))
    # Only another copy of this script (with other settings) may list a
    # removed session now: forget it only after a long while
    forget.update(i for i, t in dismissed.items() if not isinstance(t, (int, float)) or now_ms - t > DISMISSED_KEEP_MS)
    link_shared_elsewhere(groups)
    for g in groups:  # (after place_chats: a row moved to another account goes by that one's limits)
        note_limit_stops(g, now_ms)
    try:
        note_overlaps(groups, ctx.changed, home)
    except Exception as exc:
        errors.append(f"chats changing the same files: {exc}")
    try:
        note_permissions(groups, ctx, permission_requests(cache_root, now_ms))
    except Exception as exc:
        errors.append(f"permission prompts: {exc}")
    try:
        note_live(groups, cache_root)
    except Exception as exc:
        errors.append(f"live mode: {exc}")
    try:
        if starred is None:
            starred = starred_of(load_stars(cache_root))
            # (a starred chat Claude moved to the background under a new id: the star follows it)
            for old in [c for c in starred["chats"] if c in chat_moves(ctx)]:
                change_stars(cache_root, "chats", moved_chat(old, ctx.moves), on=True)
                change_stars(cache_root, "chats", old, on=False)
        starred = dict(starred, chats={moved_chat(c, chat_moves(ctx)) for c in starred["chats"]})
    except Exception as exc:
        errors.append(f"starred chats and plans: {exc}")
        starred = {kind: set() for kind in STAR_KINDS}
    hidden = load_hidden(cache_root)  # (the plans, memories and projects you hid: left out)
    left_out = {"plans": set(), "memories": set()}
    try:
        # a finished session you removed from the list is still one of your
        # recent chats: it shows there
        recent_chats(groups, ctx, recent, starred["chats"])
    except Exception as exc:
        errors.append(f"recent chats: {exc}")
        for g in groups:
            g.setdefault("recent", [])
            g.setdefault("starred", [])
    for g in groups:
        for s in g["sessions"]:
            s["starred"] = (s.get("chatId") or s["sessionId"]) in starred["chats"]
        note_limit_hits(g)  # (of its listed chats and its recent ones)
        try:
            listed = account_plans(g, ctx, plans, starred["plans"], hidden["plans"], left_out["plans"])
            g["plans"] = listed[:max(0, plans)]
            g["starredPlans"] = [dict(pl, key=pl["key"][:-len("/plan")] + "/starred") for pl in listed if pl["starred"]]
        except Exception as exc:
            errors.append(f"{g['title']}: plans: {exc}")
            g["plans"], g["starredPlans"] = [], []
        try:
            g["memories"] = account_memories(g, ctx, memories, hidden["memories"], left_out["memories"])
            # its CLAUDE.md: your instructions for every chat on it (its own line, hidden or not)
            g["instructions"] = account_instructions(g, ctx)
        except Exception as exc:
            errors.append(f"{g['title']}: memories: {exc}")
            g["memories"], g["instructions"] = [], []
    for g in groups:
        for s in g["sessions"]:
            counts[s["state"]] += 1
    ctx.agents.save()
    ctx.links.save()
    ctx.chats.save()
    ctx.slugs.save()
    ctx.tests.save()
    ctx.plan_dirs.save()
    ctx.plan_projects.save()
    if forget:
        try:
            change_dismissed(cache_root, forget=forget)
        except OSError:
            pass
    new_values = unknown_values_text(ctx.unknown)
    if new_values:
        errors.append(new_values)
    if counts["waiting"]:
        overall = "waiting"
    elif counts["working"]:
        overall = "working"
    elif any(s["state"] in ("idle", "done") and s["pid"] is not None for g in groups for s in g["sessions"]):
        overall = "idle"
    else:
        overall = "none"  # finished jobs kept for the record don't count as running
    try:
        queue = queued_tasks(cache_root, now_ms)
    except (OSError, ValueError) as exc:
        errors.append(f"queued tasks: {exc}")
        queue = []
    note_caps(groups, usage_cap, now_ms)  # (an account at the usage cap: g["cap"])
    return {
        "ok": True,
        "generatedAt": now_ms,
        "overall": overall,
        "queue": queue,  # tasks waiting for a usage limit to reset (queued_tasks)
        "keep": [],  # the chats that keep going (kept_chats, after look_after_kept)
        # {chat id: the id it goes on under}: chats Claude moved to the background under a new id (chat_moves)
        "moved": {old: moved_chat(old, ctx.moves) for old in getattr(ctx, "moves", None) or {}},
        "counts": counts,
        "groups": groups,
        "dismissed": dismissed_rows,  # (the finished chats you hid: Show Hidden Chats Again)
        # what you hid of the others (Show Hidden Plans / Memories / Projects Again)
        "hiddenPlans": len(left_out["plans"]),
        "hiddenMemories": len(left_out["memories"]),
        "hiddenProjects": len(hidden["projects"]),  # (the Projects tab leaves them out: week.py --projects)
        "canShare": True,  # jump.py shares chats between this computer's profiles (sharing.py)
        "reviewed": load_reviewed(cache_root),  # {review_key: when}: chats marked reviewed (pane.py --reviewed)
        "reviewedSince": reviewed_since(cache_root, now_ms),  # (what chats changed before isn't to review)
        "liveHook": live_hook_on(home),  # rows' "live" follow each step (the widget then checks less often)
        "errors": errors,
    }


# ---------------------------------------------------------------- VS Code
#
# "New chat in VS Code" starts a chat in VS Code's Claude extension. The
# extension runs Claude with VS Code's environment plus its own
# claudeCode.environmentVariables setting, so those decide the account (the
# Claude config folder), not the widget: it only offers the button on the
# account VS Code will use.

VSCODE_APPS = (("code", "Code"), ("code-insiders", "Code - Insiders"), ("codium", "VSCodium"),
               ("code-oss", "Code - OSS"))


def vscode_app():
    """(command, settings folder name) of the installed VS Code, or (None, None)."""
    import shutil
    for command, folder in VSCODE_APPS:
        path = shutil.which(command)
        if path:
            return path, folder
    return None, None


def jsonc(text):
    """Parse a VS Code settings file: JSON with comments and trailing commas."""
    out, i, n = [], 1 if text.startswith("\ufeff") else 0, len(text)  # (after a byte order mark)
    while i < n:
        c = text[i]
        if c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            out.append(text[i:j + 1])
            i = j + 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
        elif c == ",":
            j = jsonc_skip(text, i + 1)
            if j >= n or text[j] not in "}]":  # (a trailing comma goes; one in a string stays)
                out.append(c)
            i += 1
        else:
            out.append(c)
            i += 1
    return json.loads("".join(out))


def jsonc_skip(text, i):
    """The index of text's next character from i that isn't space or a comment."""
    n = len(text)
    while i < n:
        if text[i] in " \t\r\n":
            i += 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j + 1
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
        else:
            break
    return i


def jsonc_string_end(text, i):
    """The end of the string that starts at text[i] (a quote)."""
    j = i + 1
    while j < len(text) and text[j] != '"':
        j += 2 if text[j] == "\\" else 1
    return j + 1


def jsonc_value_end(text, i):
    """The end of the value that starts at text[i]."""
    n, depth = len(text), 0
    while i < n:
        c = text[i]
        if c == '"':
            i = jsonc_string_end(text, i)
            if depth == 0:
                return i
            continue
        if text.startswith("//", i) or text.startswith("/*", i):
            if depth == 0:
                return i
            i = jsonc_skip(text, i)
            continue
        if c in "[{":
            depth += 1
        elif c in "]}":
            if depth == 0:
                return i
            depth -= 1
            if depth == 0:
                return i + 1
        elif depth == 0 and (c == "," or c in " \t\r\n"):
            return i
        i += 1
    return n


def jsonc_set(text, key, value):
    """text (a VS Code settings file: JSON with comments) with its top-level
    key set to value, and everything else (comments, order, layout) as it
    was: the edit VS Code makes when you change one setting."""
    n = len(text)
    eol = "\r\n" if "\r\n" in text else "\n"  # (new lines end as the file's do)
    i = jsonc_skip(text, 1 if text.startswith("\ufeff") else 0)  # (a byte order mark stays)
    if i >= n or text[i] != "{":
        raise ValueError("not a JSON object")
    i = jsonc_skip(text, i + 1)
    first, last_end = i, None
    while i < n and text[i] != "}":
        if text[i] != '"':
            raise ValueError(f"unexpected {text[i]!r} at {i}")
        key_end = jsonc_string_end(text, i)
        name = json.loads(text[i:key_end])
        colon = jsonc_skip(text, key_end)
        if colon >= n or text[colon] != ":":
            raise ValueError(f"no : after {name!r}")
        start = jsonc_skip(text, colon + 1)
        end = jsonc_value_end(text, start)
        if name == key:
            line_start = text.rfind("\n", 0, i) + 1
            indent = text[line_start:i] if not text[line_start:i].strip() else ""
            return text[:start] + json.dumps(value, indent=indent or 4).replace("\n", eol + indent) + text[end:]
        last_end = end
        i = jsonc_skip(text, end)
        if i < n and text[i] == ",":
            i = jsonc_skip(text, i + 1)
    if i >= n:
        raise ValueError("no closing }")
    # Not there yet: after the last setting, indented like the first one
    line_start = text.rfind("\n", 0, first) + 1
    indent = text[line_start:first] if last_end is not None and not text[line_start:first].strip() else "    "
    member = f'"{key}": ' + json.dumps(value, indent=indent).replace("\n", eol + indent)
    if last_end is None:
        return text[:i].rstrip() + eol + indent + member + eol + text[i:]
    after = jsonc_skip(text, last_end)
    if after < n and text[after] == ",":  # a trailing comma already
        return text[:after + 1] + eol + indent + member + text[after + 1:]
    return text[:last_end] + "," + eol + indent + member + text[last_end:]


def config_dir_in_settings(path):
    """CLAUDE_CONFIG_DIR from the Claude extension's environmentVariables
    setting in a VS Code settings file, or None."""
    try:
        settings = jsonc(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return None
    entries = settings.get("claudeCode.environmentVariables") if isinstance(settings, dict) else None
    for e in entries if isinstance(entries, list) else []:
        if isinstance(e, dict) and e.get("name") == "CLAUDE_CONFIG_DIR" and isinstance(e.get("value"), str) and e["value"]:
            return e["value"]
    return None


def vscode_setting_config_dir(home, settings_folder):
    """CLAUDE_CONFIG_DIR from VS Code's user settings, or None."""
    config = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    return config_dir_in_settings(config / settings_folder / "User" / "settings.json")


# On an SSH host, VS Code's server keeps the host's own settings ("Remote
# [SSH: host]"): the Claude extension's environmentVariables is a machine
# setting, so windows connected to the host read it there, never from the
# settings on your computer. Per VS Code app: its server's folder.
VSCODE_SERVERS = {"Code": ".vscode-server", "Code - Insiders": ".vscode-server-insiders", "VSCodium": ".vscodium-server"}


def vscode_server_settings(home, server):
    return home / server / "data" / "Machine" / "settings.json"


def vscode_server_config_dir(home):
    """CLAUDE_CONFIG_DIR VS Code's Claude runs with on this host (the first
    VS Code server whose settings set it), or None."""
    for server in VSCODE_SERVERS.values():
        value = config_dir_in_settings(vscode_server_settings(home, server))
        if value is not None:
            return value
    return None


def set_config_dir_setting(path, value, home):
    """claudeCode.environmentVariables in the VS Code settings file at path
    gets CLAUDE_CONFIG_DIR=value (None: none): (ok, why not). Only that entry
    changes; the file's comments, other settings and layout stay (jsonc_set),
    and its permissions too."""
    shown = short_path(str(path), home)
    try:
        with open(str(path), encoding="utf-8", newline="") as f:  # (its line ends as they are)
            text = f.read()
    except FileNotFoundError:
        text = ""
    except (OSError, ValueError) as exc:
        return False, f"Can't read {shown}: {exc}"
    try:
        settings = jsonc(text) if text.strip() else {}
        if not isinstance(settings, dict):
            raise ValueError("not a JSON object")
        old = settings.get("claudeCode.environmentVariables")
        entries = [e for e in (old if isinstance(old, list) else [])
                   if not (isinstance(e, dict) and e.get("name") == "CLAUDE_CONFIG_DIR")]
        if value:
            entries.append({"name": "CLAUDE_CONFIG_DIR", "value": value})
        new = jsonc_set(text if text.strip() else "{\n}\n", "claudeCode.environmentVariables", entries)
        # it says what it said before, but for this setting
        if jsonc(new) != {**settings, "claudeCode.environmentVariables": entries}:
            raise ValueError("the change came out wrong")
    except ValueError as exc:
        return False, f"{shown} couldn't be changed ({exc}): switch the account in VS Code"
    # a link (to your dotfiles, say) stays one: the file it points to changes
    target = Path(os.path.realpath(str(path)))
    tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        mode = target.stat().st_mode & 0o777 if target.exists() else 0o600
        with open(str(tmp), "w", encoding="utf-8", newline="") as f:
            f.write(new)
        os.chmod(str(tmp), mode)
        os.replace(str(tmp), str(target))
    except OSError as exc:
        try:
            tmp.unlink()  # (not left next to the settings)
        except OSError:
            pass
        return False, f"Can't write {shown}: {exc}"
    return True, ""


def set_vscode_server_config_dir(home, value, server=".vscode-server", extra_dirs=()):
    """Have VS Code's Claude on this host run with CLAUDE_CONFIG_DIR=value
    (None: without it, on a plain ~/.claude), in the settings of its VS Code
    server: (ok, message). Only one of this host's Claude folders. The Claude
    extension follows the change (new chats, its panels)."""
    if server not in VSCODE_SERVERS.values():
        return False, f"Not a VS Code server folder: {server}"
    profiles = discover_profiles(home, extra_dirs)
    try:
        real = (Path(value).expanduser() if value else home / ".claude").resolve()
    except (OSError, RuntimeError):
        real = None
    profile = next((p for p in profiles if p.real == real), None)
    if profile is None:
        return False, f"{value or '~/.claude'} isn't a Claude folder on this host"
    ok, why = set_config_dir_setting(vscode_server_settings(home, server), value, home)
    return (True, f"VS Code's Claude runs on {profile.label} here now") if ok else (False, why)


def set_vscode_user_config_dir(home, value):
    """Have VS Code's Claude on this computer run with CLAUDE_CONFIG_DIR=value
    (None: without it) from now on, in VS Code's user settings: (ok,
    message). The Claude extension starts new chats with it; a window's
    Claude Code panel follows once the window reloads."""
    command, folder = vscode_app()
    if command is None:
        return False, "VS Code isn't installed"
    config = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    return set_config_dir_setting(config / folder / "User" / "settings.json", value, home)


def vscode_running_config_dir():
    """(VS Code runs, CLAUDE_CONFIG_DIR in its environment or None). Only the
    main process counts: helpers run as node (ELECTRON_RUN_AS_NODE) inherit
    the extensions' environment."""
    names = {Path(c).name for c, _ in VSCODE_APPS}
    try:
        pids = [p for p in os.listdir("/proc") if p.isdigit()]
    except OSError:
        return False, None
    for pid in pids:
        try:
            if Path(f"/proc/{pid}/comm").read_text(encoding="utf-8", errors="replace").strip() not in names:
                continue
            argv = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
            env = dict(item.partition(b"=")[::2] for item in Path(f"/proc/{pid}/environ").read_bytes().split(b"\0") if item)
        except OSError:
            continue
        if any(a.startswith(b"--type=") for a in argv) or b"ELECTRON_RUN_AS_NODE" in env:
            continue
        value = env.get(b"CLAUDE_CONFIG_DIR")
        return True, value.decode(errors="replace") if value else None
    return False, None


VSCODE_CHECK_INTERVAL = 30  # seconds between looks at VS Code (see cached_vscode_lookup)


def vscode_lookup(home):
    """(VS Code installed, the CLAUDE_CONFIG_DIR its Claude would run with or None)."""
    command, settings_folder = vscode_app()
    if command is None:
        return False, None
    value = vscode_setting_config_dir(home, settings_folder)
    if value is None:
        running, env_value = vscode_running_config_dir()
        # not running: the widget starts it, with its own environment
        value = env_value if running else os.environ.get("CLAUDE_CONFIG_DIR")
    return True, value


def vscode_stamp(home):
    """When VS Code's settings files and the folders on PATH last changed: a
    new setting, or VS Code just installed, counts at once."""
    config = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    settings = [config / folder / "User" / "settings.json" for _, folder in VSCODE_APPS]
    folders = [Path(d) for d in os.environ.get("PATH", "").split(os.pathsep) if d]
    return [mtime(p) for p in settings + folders]


def cached_vscode_lookup(home, cache_root, now):
    """vscode_lookup, redone at most every VSCODE_CHECK_INTERVAL seconds or when
    VS Code's settings or the folders on PATH change: it searches PATH and
    maybe every process, too much to repeat in a status check every 2 s."""
    path = cache_root / "vscode.json"
    stamp = vscode_stamp(home)
    saved = read_json(path)
    if (isinstance(saved, dict) and saved.get("stamp") == stamp
            and 0 <= now - (number(saved.get("at")) or 0) < VSCODE_CHECK_INTERVAL):
        value = saved.get("value")
        return saved.get("installed") is True, value if isinstance(value, str) else None
    installed, value = vscode_lookup(home)
    try:
        private_dir(cache_root)
        write_json_atomic(path, {"at": now, "stamp": stamp, "installed": installed, "value": value})
    except OSError:
        pass
    return installed, value


def vscode_profile(home, profiles, remote=False, cache_root=None):
    """(VS Code installed, the profile a new chat in VS Code's Claude would
    use or None). On an SSH host (remote) the VS Code server's Claude uses what its
    server's settings say, else the host's ~/.claude; whether VS Code is
    installed is up to the other side."""
    installed, value = None, None
    if remote:
        value = vscode_server_config_dir(home)
    else:
        installed, value = (cached_vscode_lookup(home, cache_root, time.time()) if cache_root is not None
                            else vscode_lookup(home))
        if not installed:
            return False, None
    try:
        real = (Path(value).expanduser() if value else home / ".claude").resolve()
    except (OSError, RuntimeError):
        return installed, None
    return installed, next((p for p in profiles if p.real == real), None)


def plain_profile(home, profiles):
    """The profile plain `claude` runs on: ~/.claude, or the one it links to."""
    try:
        real = (home / ".claude").resolve()
    except (OSError, RuntimeError):
        return None
    return next((p for p in profiles if p.real == real), None)


def default_profile(home, profiles, remote=False, cache_root=None):
    """(VS Code installed, the profile VS Code's Claude runs on, plain
    claude's, the default account). The default is VS Code's Claude's where
    VS Code is (accounts.py --default points ~/.claude there too), else
    plain claude's: the same on every front end."""
    installed, vscode = vscode_profile(home, profiles, remote, cache_root)
    plain = plain_profile(home, profiles)
    return installed, vscode, plain, vscode or plain


def add_vscode(result, home, extra_dirs=(), remote=False, cache_root=None):
    """Which account a new chat in VS Code would be on (result["vscode"] =
    {installed, on (its label)}, each group's vscodeHere), plain claude's
    (plainHere) and the default account (defaultHere, default_profile),
    which is listed first."""
    installed, profile, plain, default = default_profile(home, discover_profiles(home, extra_dirs), remote, cache_root)
    result["vscode"] = {"installed": installed, "on": profile.label if profile else None}
    # (whether accounts.py --default can point anything elsewhere: VS Code's
    # Claude, or plain claude through a ~/.claude link)
    result["canDefault"] = bool(installed) or (home / ".claude").is_symlink()
    for g in result.get("groups", []):
        keys = g.get("profileKeys", [])
        g["vscodeHere"] = profile is not None and profile.key in keys
        g["plainHere"] = plain is not None and plain.key in keys
        g["defaultHere"] = default is not None and default.key in keys
    result.get("groups", []).sort(key=lambda g: not g["defaultHere"])  # (stable: the others keep their order)


# ---------------------------------------------------------------- containers
#
# Docker, Podman and nerdctl containers, shown like SSH hosts: remote.py
# lists this computer's with list_containers, and an SSH host's by running
# this file there (--list-containers). The running ones and those active in
# the last N days are listed. Talpy Den runs its checks inside one with the
# engine's exec (remote.py).

CONTAINER_DAYS = 30  # containers active this many days ago are still listed
# Engines with Docker's command line, the one listing the most first: a
# `docker` that's one of the others (Fedora's podman-docker, a link to
# nerdctl) is the same containers, listed once
CONTAINER_ENGINES = ("podman", "docker", "nerdctl")
ENGINE_TITLES = {"docker": "Docker", "podman": "Podman", "nerdctl": "nerdctl"}
CONTAINER_LIST_TIMEOUT = 6  # seconds an engine may take to list its containers
CONTAINER_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
CONTAINER_RUNNING = ("running", "paused", "restarting")
# One `docker container inspect` gives what the list shows: it takes a Go
# template. (The id goes in quotes as it is, a hex string: Podman takes .Id
# for its .ID only on its own, not in {{json .Id}}.)
CONTAINER_TEMPLATE = ('{"id":"{{.Id}}","name":{{json .Name}},"state":{{json .State.Status}},'
                      '"started":{{json .State.StartedAt}},"finished":{{json .State.FinishedAt}},'
                      '"created":{{json .Created}},"image":{{json .Config.Image}},"labels":{{json .Config.Labels}},'
                      '"mounts":[{{range $i, $m := .Mounts}}{{if $i}},{{end}}{{json $m.Destination}}{{end}}]}')
DEVCONTAINER_FOLDER = "devcontainer.local_folder"
DEVCONTAINER_CONFIG = "devcontainer.config_file"
# Containers made for you to work in, as you, with your home folder mounted
TOOLBOX_LABELS = (("manager", "distrobox"), ("com.github.containers.toolbox", "true"))


def container_time(value):
    """ms since the epoch of a container's time (seconds since the epoch, or
    Docker's RFC 3339 with nanoseconds), or None: none, or a broken one such
    as Docker's 0001-01-01 for never or a time in the future."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        seconds = float(value)
    elif isinstance(value, str) and value:
        m = re.match(r"(\d{4})-(\d\d)-(\d\d)[T ](\d\d):(\d\d):(\d\d)(\.\d+)?\s*(Z|[+-]\d\d:?\d\d)?", value)
        if not m:
            return None
        try:
            stamp = datetime(*(int(m.group(i)) for i in range(1, 7)))
        except ValueError:
            return None
        seconds = (stamp - datetime(1970, 1, 1)).total_seconds() + float(m.group(7) or 0)
        zone = m.group(8)
        if zone and zone != "Z":
            sign = -1 if zone[0] == "+" else 1
            seconds += sign * (int(zone[1:3]) * 3600 + int(zone[-2:]) * 60)
    else:
        return None
    if seconds < 31536000 or seconds > time.time() + 86400:  # (before 1971, or ahead of the clock)
        return None
    return int(seconds * 1000)


def short_image(image):
    """docker.io/library/ubuntu:22.04 -> ubuntu:22.04; an image id -> its first 12 digits."""
    image = image if isinstance(image, str) else ""
    if image.startswith("sha256:"):
        return image[7:19]
    if re.fullmatch(r"[0-9a-f]{64}", image):
        return image[:12]
    for prefix in ("docker.io/library/", "docker.io/", "localhost/"):
        if image.startswith(prefix):
            return image[len(prefix):]
    return image


def devcontainer_user(labels):
    """The user VS Code's Dev Containers works as in a container
    (remoteUser in its devcontainer.metadata label, the last one wins), or ""."""
    try:
        metadata = json.loads((labels or {}).get("devcontainer.metadata") or "[]")
    except (ValueError, RecursionError):
        return ""
    if isinstance(metadata, dict):
        metadata = [metadata]
    user = ""
    for part in metadata if isinstance(metadata, list) else []:
        if isinstance(part, dict) and isinstance(part.get("remoteUser"), str) and part["remoteUser"]:
            user = part["remoteUser"]
    return user


def root_user(user):
    """Whether a container's user (NAME, UID, NAME:GROUP or UID:GID) is root:
    "" (exec's default: root, unless the image says otherwise), root or 0."""
    name = user.split(":")[0].strip() if isinstance(user, str) else ""
    return name in ("", "root") or (name.isdigit() and int(name) == 0)


def container_user(labels, own="", you=None):
    """The user Talpy Den works as in a container, "" for its own (exec's
    default). Labels only ever drop root: a container whose own user (own,
    its Config.User) isn't root is worked in as that; one that runs as root
    as VS Code's Dev Containers' user in a dev container, or you (you: your
    login name, this computer's by default) in a Toolbox or Distrobox (made
    for you to work in, with your home folder); never as root from a label."""
    if not root_user(own):
        return ""
    labels = labels or {}
    user = devcontainer_user(labels)
    if not user and any(labels.get(k) == v for k, v in TOOLBOX_LABELS):
        if you is None:
            try:
                import pwd
                you = pwd.getpwuid(os.getuid()).pw_name
            except (ImportError, KeyError):
                you = ""
        user = you
    return "" if root_user(user) else user


def engine_clone(path, cache):
    """The engine a `docker` command really is ("podman" for Fedora's
    podman-docker or a link to podman, "nerdctl" likewise), or "docker".
    Asked once per version of the file (its path and time), kept in cache."""
    try:
        real = os.path.realpath(path)
        mtime = os.stat(real).st_mtime_ns
    except OSError:
        return "docker"
    base = os.path.basename(real)
    if base in CONTAINER_ENGINES and base != "docker":  # (a link to podman)
        return base
    known = cache.get(real)
    if isinstance(known, dict) and known.get("mtime") == mtime and known.get("engine") in CONTAINER_ENGINES:
        return known["engine"]
    engine = "docker"
    try:
        with open(real, "rb") as f:
            head = f.read(4096)
    except OSError:
        head = b""
    if head.startswith(b"#!"):  # (a script: Fedora's says exec /usr/bin/podman "$@")
        m = re.search(rb"\bexec\s+(?:\S*/)?(podman|nerdctl)\b", head)
        engine = m.group(1).decode() if m else "docker"
    else:
        import subprocess
        try:
            r = subprocess.run([path, "--version"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, timeout=CONTAINER_LIST_TIMEOUT)
            words = r.stdout.decode(errors="replace").lower()
            engine = next((e for e in ("podman", "nerdctl") if e in words), "docker")
        except (OSError, subprocess.SubprocessError):
            pass
    cache[real] = {"mtime": mtime, "engine": engine}
    return engine


def change_containers_file(cache_root, change):
    """change(saved) on cache_root's containers.json (the users in
    containers, the hosts' container lists, which engine `docker` is), under
    a lock: two checks at once don't lose each other's. Only you can read it
    (in the state folder: it says which user to work as in a container)."""
    state = state_dir(cache_root)
    path = state / "containers.json"
    private_dir(state)
    fd = os.open(str(state / ".containers.lock"), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        saved = read_json(path)
        saved = saved if isinstance(saved, dict) else {}
        change(saved)
        write_json_atomic(path, saved, private=True)
        os.chmod(str(path), 0o600)
    finally:
        os.close(fd)


def container_engines(cache_root):
    """({engine: its command} of the container engines installed here, each
    once; the engine the `docker` command really is, or ""): engine_clone,
    what it found is kept in containers.json."""
    import shutil
    found = {e: shutil.which(e) for e in CONTAINER_ENGINES}
    found = {e: p for e, p in found.items() if p}
    really = ""
    if "docker" in found:
        saved = read_json(state_dir(cache_root) / "containers.json")
        saved = saved if isinstance(saved, dict) else {}
        clones = saved.get("engines") if isinstance(saved.get("engines"), dict) else {}
        before = json.dumps(clones, sort_keys=True)
        really = engine_clone(found["docker"], clones)
        if json.dumps(clones, sort_keys=True) != before:
            def keep(saved):
                engines = saved.get("engines") if isinstance(saved.get("engines"), dict) else {}
                engines.update(clones)
                saved["engines"] = engines
            try:
                change_containers_file(cache_root, keep)
            except OSError:
                pass
        if really != "docker":
            del found["docker"]
            found.setdefault(really, found.get(really) or shutil.which(really) or "")
            found = {e: p for e, p in found.items() if p}
    return found, really


def engine_trouble(engine, text, timed_out=False):
    """Why an engine couldn't list its containers, in plain words."""
    title = ENGINE_TITLES.get(engine, engine)
    low = text.lower()
    if timed_out:
        return "%s didn't answer within %d s." % (title, CONTAINER_LIST_TIMEOUT)
    if "permission denied" in low and ("socket" in low or "daemon" in low):
        return "You can't use %s's socket: add yourself to its group (docker), then log in again." % title
    if "cannot connect to the docker daemon" in low or "is the docker daemon running" in low \
            or "cannot connect to podman" in low or "connection refused" in low:
        return "%s isn't running." % title
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "%s: %s" % (title, lines[-1][:200] if lines else "it couldn't list its containers")


def engine_containers(engine, command, home):
    """(the containers of one engine, a sentence when it couldn't list them).
    Podman lists everything in one call; Docker and nerdctl name them, then
    one inspect says the rest."""
    import subprocess

    def run(args):
        r = subprocess.run([command, *args], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=CONTAINER_LIST_TIMEOUT)
        return r.returncode, r.stdout.decode(errors="replace"), r.stderr.decode(errors="replace")

    out = []
    try:
        if engine == "podman":
            code, stdout, stderr = run(["ps", "-a", "--format", "json"])
            if code != 0:
                return [], engine_trouble(engine, stderr or stdout)
            for c in json.loads(stdout or "[]") or []:
                if not isinstance(c, dict) or c.get("IsInfra"):  # (a pod's own)
                    continue
                names = c.get("Names") or []
                out.append({"name": names[0] if isinstance(names, list) and names else "",
                            "cid": c.get("Id") or "", "state": (c.get("State") or "").lower(),
                            "image": c.get("Image") or "", "labels": c.get("Labels") or {},
                            "mounts": [m for m in c.get("Mounts") or [] if isinstance(m, str)],
                            "times": [c.get("StartedAt"), c.get("ExitedAt"), c.get("Created")]})
        else:
            code, stdout, stderr = run(["ps", "-a", "-q", "--no-trunc"])
            if code != 0:
                return [], engine_trouble(engine, stderr or stdout)
            ids = [i for i in stdout.split() if re.fullmatch(r"[0-9a-f]{12,64}", i)]
            if ids:
                code, stdout, stderr = run(["container", "inspect", "--format", CONTAINER_TEMPLATE, *ids])
                if code != 0 and not stdout.strip():
                    return [], engine_trouble(engine, stderr)
                for line in stdout.splitlines():
                    try:
                        c = json.loads(line)
                    except (ValueError, RecursionError):
                        continue
                    if not isinstance(c, dict):
                        continue
                    out.append({"name": (c.get("name") or "").lstrip("/"), "cid": c.get("id") or "",
                                "state": (c.get("state") or "").lower(), "image": c.get("image") or "",
                                "labels": c.get("labels") or {},
                                "mounts": [m for m in c.get("mounts") or [] if isinstance(m, str)],
                                "times": [c.get("started"), c.get("finished"), c.get("created")]})
    except subprocess.TimeoutExpired:
        return [], engine_trouble(engine, "", timed_out=True)
    except (OSError, ValueError) as exc:
        return [], engine_trouble(engine, str(exc))
    return out, None


def list_containers(cache_root, home, days=CONTAINER_DAYS, picked=(), now=None):
    """This computer's containers: {"containers": [...], "notes": [...]},
    the running ones first, then the newest. A stopped one is listed when it
    was active (started, stopped or made) in the last days days (0: only the
    running ones), and a picked one (a name, or engine:name) always. The
    engines are asked at once, each for at most CONTAINER_LIST_TIMEOUT s:
    one that hangs holds up only itself. notes: an engine that couldn't
    list them, and why ({"engine", "message"}). viaDocker: the `docker`
    command reaches it (Docker's, or Podman's for a docker that is Podman)."""
    import threading
    now = time.time() * 1000 if now is None else now
    picked = set(picked)
    engines, docker_is = container_engines(cache_root)
    answers = {}

    def ask(engine, command):
        answers[engine] = engine_containers(engine, command, home)

    threads = [threading.Thread(target=ask, args=item, daemon=True) for item in engines.items()]
    for t in threads:
        t.start()
    for t in threads:
        t.join(CONTAINER_LIST_TIMEOUT + 2)
    listed, notes, home_text = [], [], str(home)
    for engine in engines:
        found, trouble = answers.get(engine, ([], engine_trouble(engine, "", timed_out=True)))
        if trouble:
            notes.append({"engine": engine, "message": trouble})
        for c in found:
            name = c["name"]
            if not isinstance(name, str) or not CONTAINER_NAME.match(name):
                continue
            ident = engine + ":" + name
            running = c["state"] in CONTAINER_RUNNING
            active = max([t for t in (container_time(v) for v in c["times"]) if t is not None] or [0]) or None
            wanted = running or ident in picked or name in picked
            if not wanted and days > 0 and active is not None and active >= now - days * 86400000:
                wanted = True
            if not wanted:
                continue
            labels = c["labels"] if isinstance(c["labels"], dict) else {}
            folder = labels.get(DEVCONTAINER_FOLDER) if isinstance(labels.get(DEVCONTAINER_FOLDER), str) else ""
            config = labels.get(DEVCONTAINER_CONFIG) if isinstance(labels.get(DEVCONTAINER_CONFIG), str) else ""
            listed.append({
                "id": ident, "engine": engine, "name": name, "image": short_image(c["image"]),
                "state": c["state"] or "unknown", "running": running, "activeAt": active,
                "folder": folder, "folderShort": short_folder(folder, home) if folder else "",
                "devcontainer": bool(folder or config), "configFile": config,
                "viaDocker": engine == docker_is,
                "sharesHome": home_text in c["mounts"], "cid": c["cid"],
            })
    listed.sort(key=lambda c: (not c["running"], -(c["activeAt"] or 0), c["id"]))
    return {"containers": listed, "notes": notes}


# ---------------------------------------------------------------- remote hosts
#
# The widget runs this script on an SSH host (`ssh host python3 -I - --remote`
# with the script on stdin: nothing is installed there). In that mode every row
# also carries the shell command that opens it on the host, so the widget can
# run it in a local terminal as `ssh -t host <command>`.

REMOTE_MARK = "@@talpy-den@@"


# Each row a list shows gets a "rev": a short hash of what it says, so the
# widget's lists keep a row as it is while its rev stays (a check that changes
# one chat runs that row's bindings again, not every row's), and the answer
# a "stamp" first: a hash of it all but its time and the usage forecasts,
# which drift with it, so a check that says nothing new is known from its
# first line (the widget compared two copies of the whole answer).
ROW_LISTS = ("sessions", "recent", "starred", "starredPlans", "instructions")


def add_revs(result):
    for group in result.get("groups") or []:
        for name in ROW_LISTS:
            for row in group.get(name) or []:
                if isinstance(row, dict):
                    row.pop("rev", None)
                    try:
                        body = json.dumps(row, sort_keys=True)
                    except TypeError:   # (keys of mixed kinds can't be sorted: as they are)
                        body = json.dumps(row)
                    row["rev"] = hashlib.sha1(body.encode()).hexdigest()[:12]


STAMP_SKIP = (re.compile(r'"generatedAt": *\d+'), re.compile(r'"forecast": *\{[^{}]*\}'))


def stamped(text):
    """The answer's JSON text with "stamp" as its first key (an object's)."""
    if not text.startswith("{") or text.startswith("{}"):
        return text
    key = text
    for skip in STAMP_SKIP:
        key = skip.sub("", key)
    return '{"stamp": "%s", %s' % (hashlib.sha1(key.encode()).hexdigest()[:16], text[1:])
# Where claude is often installed besides PATH: Claude's installer, its old
# local install, npm, bun, ~/bin, Volta, pnpm, mise and asdf; then nvm's
# Node versions (newest first) and the system-wide places
CLAUDE_PLACES = (".local/bin", ".claude/local", ".npm-global/bin", ".bun/bin", "bin", ".volta/bin",
                 ".local/share/pnpm", ".local/share/mise/shims", ".asdf/shims")
SYSTEM_PLACES = ("/usr/local/bin", "/home/linuxbrew/.linuxbrew/bin", "/opt/homebrew/bin")  # check-public: ok (Homebrew's prefix)


def version_key(name):
    """v20.11.1 -> (20, 11, 1)"""
    return tuple(int(n) for n in re.findall(r"\d+", name))


def claude_places(home):
    nvm = sorted((home / ".nvm/versions/node").glob("*/bin"), key=lambda p: version_key(p.parent.name), reverse=True)
    return [str(home / d) for d in CLAUDE_PLACES] + [str(p) for p in nvm] + list(SYSTEM_PLACES)


def login_shell_path(home):
    """PATH as your login shell sets it up (from ~/.profile, ~/.bashrc,
    ~/.zshrc and the like, where installers add their folders), or "".
    `env` prints it the same way whatever the shell."""
    import subprocess
    shell = os.environ.get("SHELL") or "/bin/sh"
    try:
        r = subprocess.run([shell, "-l", "-i", "-c", "env"], cwd=str(home), stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10)
    except (OSError, ValueError, subprocess.SubprocessError):
        return ""
    lines = r.stdout.decode(errors="replace").splitlines()
    return next((line[len("PATH="):] for line in reversed(lines) if line.startswith("PATH=")), "")


def find_claude(home, ask_shell=False):
    """Absolute path of the claude command, or "claude" if it isn't found.

    The desktop session and commands run over ssh don't read the shell
    startup files that usually put claude's folder on PATH. So after PATH
    come the usual install places and, with ask_shell (it starts your login
    shell: only for a click, never for a status check), its PATH."""
    import shutil
    found = shutil.which("claude", path=os.pathsep.join([os.environ.get("PATH", ""), *claude_places(home)]))
    if not found and ask_shell:
        shell_path = login_shell_path(home)
        found = shutil.which("claude", path=shell_path) if shell_path else None
    return found or "claude"


CLAUDE_SHELL_CHECK_INTERVAL = 3600  # seconds between asking the login shell (see cached_find_claude)


def cached_find_claude(home, cache_root, now):
    """find_claude for a status check: the claude command's path, or None.
    When it's on neither PATH nor the usual places, your login shell's PATH
    is asked at most once an hour (it starts your shell); a find is checked
    again on every call (it may have been removed)."""
    found = find_claude(home)
    if found != "claude":
        return found
    path = cache_root / "claude.json"
    saved = read_json(path)
    if isinstance(saved, dict) and 0 <= now - (number(saved.get("at")) or 0) < CLAUDE_SHELL_CHECK_INTERVAL:
        found = saved.get("path")
        return found if isinstance(found, str) and os.access(found, os.X_OK) else None
    found = find_claude(home, ask_shell=True)
    found = None if found == "claude" else found
    try:
        private_dir(cache_root)
        write_json_atomic(path, {"at": now, "path": found})
    except OSError:
        pass
    return found


def in_folder(folder, command):
    """command, run in folder when it exists (ssh starts in the home folder)."""
    if isinstance(folder, str) and folder.startswith("/"):
        return f"cd {shlex.quote(folder)} 2>/dev/null; {command}"
    return command


def add_remote_commands(result, home, extra_dirs=(), claude=None):
    """Shell commands that open, stop or start chats on this host (claude:
    the claude command's path, if it's been looked for already)."""
    claude = claude or find_claude(home)
    profiles = {p.key: p for p in discover_profiles(home, extra_dirs)}
    result["claude"] = claude
    for g in result.get("groups", []):
        named = profiles.get(g.get("chatProfile"))
        # what VS Code's Claude there needs to run on this account (jump.py
        # --remote-new-vscode --account, the VS Code extension's switch)
        g["configDir"] = config_dir_value(named, home) if named is not None else None
        g["loginCommand"] = (in_folder(str(home), login_command(named, home, claude))
                             if named is not None and g.get("loggedOut") else None)
        if named is not None:
            chat = new_chat_command(named, home, claude)
            g["homeChatCommand"] = in_folder(str(home), chat)
            for project in g.get("projects", []):
                project["newChatCommand"] = in_folder(project["path"], chat)
        for s in g["sessions"]:
            p = profiles.get(s["profileDir"])
            s["openCommand"] = s["stopCommand"] = None
            # a chat in the terminal of a VS Code window connected to this
            # host: that window shows it (jump.py --remote-terminal --vscode-terminal)
            s["vscodeTerminal"] = (vscode_terminal(s["pid"]) if s["pid"] is not None
                                   and s["entrypoint"] != "claude-vscode" else None)
            if p is None:
                continue
            if s.get("jobId"):
                job = read_job([p], s["jobId"]) or {}
                s["openCommand"] = in_folder(job.get("cwd") or s["cwd"], attach_command(p, s["jobId"], home, job, claude))
                if s["pid"] is not None:
                    s["stopCommand"] = stop_command(p, s["jobId"], home, job, claude)
            elif s["kind"] == "chat":
                s["openCommand"] = in_folder(s["cwd"], resume_command(p, s["chatId"], home, s["cwd"], claude))
            elif s["entrypoint"] == "claude-vscode":  # (in a terminal there instead of VS Code)
                s["terminalCommand"] = in_folder(s["cwd"], resume_command(p, s["chatId"], home, s["cwd"], claude))
        for c in g.get("recent", []) + g.get("starred", []):  # (★ Starred: copies of their own)
            p = profiles.get(c["profileDir"])
            c["openCommand"] = in_folder(c["cwd"], resume_command(p, c["sessionId"], home, c["cwd"], claude)) if p else None
        for pl in g.get("plans", []) + g.get("starredPlans", []):  # its chat, reopened
            p = profiles.get(pl.get("chatProfileDir"))
            pl["openCommand"] = (in_folder(pl["cwd"], resume_command(p, pl["chatId"], home, pl["cwd"], claude))
                                 if p is not None and pl.get("chatId") else None)
    rows = {s["key"]: s for g in result.get("groups", []) for s in g["sessions"]}
    for g in result.get("groups", []):
        for h in g.get("sharedHere", []):  # a link opens the chat's own row
            target = rows.get(h["key"][:-len("/shared")]) if h["key"].endswith("/shared") else None
            h["openCommand"] = target["openCommand"] if target else None


def add_found_commands(result, home, extra_dirs=()):
    """The commands reopening the chats --find found on this host."""
    claude = find_claude(home)
    profiles = {p.key: p for p in discover_profiles(home, extra_dirs)}
    for c in result.get("results", []):
        p = profiles.get(c["profileDir"])
        c["openCommand"] = in_folder(c["cwd"], resume_command(p, c["sessionId"], home, c["cwd"], claude)) if p else None


USAGE = """usage: talpy_den.py [--config-dir DIR]... [--done-hours H] [--recent N] [--plans N] [--memories N] [--no-tokens] [--pretty] [--remote [--local]]
                    [--usage-refresh N] [--no-history | --history-since MS]
       talpy_den.py --fetch-usage [--config-dir DIR]...
       talpy_den.py --dismiss SESSION_ID | --undismiss-all
       talpy_den.py --hide chats|plans|memories|projects ID | --show-hidden chats|plans|memories|projects
       talpy_den.py --end SESSION_ID [--profile PROFILE] [--busy] [--config-dir DIR]...
       talpy_den.py --interrupt SESSION_ID [--profile PROFILE] [--config-dir DIR]...
       talpy_den.py --agent-run AGENT_ID --chat CHAT_ID [--profile PROFILE] [--config-dir DIR]...
       talpy_den.py --vscode-account CONFIG_DIR|- [--vscode-server FOLDER]
       talpy_den.py --find QUERY [--limit N] [--remote]
       talpy_den.py --start-task|--task-command FOLDER --profile PROFILE [--prompt TEXT]
                        [--plan SLUG [--plan-profile PROFILE]] [--model MODEL] [--effort LEVEL]
                        [--permission-mode MODE] [--remote]
       talpy_den.py --plan-text SLUG [--profile PROFILE] [--remote]
       talpy_den.py --continue-chat CHAT_ID --profile PROFILE [--folder F] [--prompt TEXT] [--remote]
       talpy_den.py --list-containers DAYS [--picked NAME,...] [--remote]
  --config-dir DIR  extra Claude config dir (repeatable)
  --done-hours H    keep finished background jobs listed for H hours (default 24, 0 = never)
  --recent N        list each account's N latest other chats (default 5, 0 = none) and count them all
  --plans N         list each account's N latest plans (default 8, 0 = none; the starred ones always)
  --memories N      list each account's N latest memories (default 30, 0 = none; its CLAUDE.md always,
                    as "instructions")
  --find QUERY      the chats with every word of QUERY in their name, folder or your prompts
  --start-task F    start a background session in folder F with the prompt (and plan)
  --task-command F  the shell command that starts a chat in folder F with the prompt (and plan)
  --plan-text SLUG  a plan's Markdown
  --continue-chat ID  go on with a chat a usage limit stopped, in the background (the limit has reset)
  --list-containers DAYS  the Docker, Podman and nerdctl containers here: the running ones and those
                    active in the last DAYS days (0: only the running ones), and the --picked ones always
  --ends-at MS      with --continue-chat: wait for the chat's background commands until MS, then end them
  --force           with --continue-chat: go on whatever its newest turn (a chat that keeps going: its
                    turn broke off)
  --kept-chats C/P,…  (an SSH host's status, asked from the computer that keeps them) these chats (id/
                    profile) keep going: they stay listed, and "keptTurns" says how each stands
  --no-tokens       skip transcript token totals
  --no-history, --history-since MS  (an SSH host's status, asked from the computer that keeps the
                    setting) the Recap keeps no history there, or kept none from before MS: the plan
                    windows that ended kept here (usage-past.json) follow it
  --pretty          indent the JSON output
  --remote          for the widget on another machine: add the shell commands that open
                    each chat here, and print the JSON after a marker line
  --local           with --remote: this computer's status for its VS Code extension (VS Code's
                    account is this computer's VS Code's, not a VS Code server's)
  --dismiss ID      hide a finished chat (--undismiss-all shows them again)
  --hide KIND ID    hide a chat, a plan (its slug), a memory (its key) or a project (its
                    folder) from its list (--show-hidden KIND shows that kind again)
  --end ID          stop a chat in a terminal or VS Code (it's kept); only an idle one
                    unless --busy (you were told it's working or waiting)
  --interrupt ID    interrupt a working chat in tmux (Ctrl+C in its pane), or a background one (Esc)
  --agent-run ID    a subagent's whole run (of the chat --chat), as Markdown in the JSON
  --vscode-account  VS Code's Claude on this host runs with that CLAUDE_CONFIG_DIR (- for
                    none: a plain ~/.claude), in its VS Code server's settings (on an SSH host)
  --instance ID     this copy of the widget (with --interval-ms N, how often it checks):
                    says whether it sends the notifications, and the shared settings; the
                    one that does looks after the chats that keep going (look_after_kept)
  --keep-going      look after the chats that keep going (the VS Code window that notifies); and,
                    as --cleanup-check, start Talpy Den's daily cleanup of old chats once it's due
  --cleanup-check   (GNOME's copy, which needs no electing) start that cleanup once it's due
  --usage-cap N     stop what an account has at work once one of its plan windows reaches N%
  --usage-refresh N while one of an account's chats works, have Claude Code fetch its plan usage
                    once it's more than N minutes old, at most every N minutes (default 5, 0 = never;
                    Claude's VS Code panel runs no status line)
  --fetch-usage     (Refresh) have Claude Code fetch the plan usage of every account whose numbers
                    are over a minute old, now, chat at work or not; prints {"ok", "started"}"""


def main(argv=None):
    # Hand-rolled instead of argparse, which alone costs ~10 ms of startup on
    # every poll.
    args = sys.argv[1:] if argv is None else list(argv)
    config_dirs, with_tokens, pretty, done_hours = [], True, False, KEEP_DONE_HOURS
    recent, remote, local, dismiss, undismiss = RECENT_CHATS, False, False, None, False
    hide_kind, hide_id, show_kind = None, None, None
    end, interrupt, profile_key, busy, instance, interval_ms = None, None, None, False, None, 2000
    agent_run_id, chat_id, plans, find, find_limit = None, None, PLANS_LISTED, None, FIND_LIMIT
    memories = MEMORIES_LISTED
    task_folder, task_action, prompt, plan_slug, plan_profile, plan_text = None, None, "", None, None, None
    continue_id, continue_folder, continue_ends_at = None, None, None
    vscode_account, vscode_server = None, VSCODE_SERVERS["Code"]
    keep_going, usage_cap, model, effort, mode = False, 0, None, None, None
    cleanup_check = False  # (--cleanup-check: GNOME's one copy asks whether Talpy Den's cleanup of old chats is due)
    usage_refresh = USAGE_REFRESH_MINUTES
    fetch_usage = False
    starred_chats, starred_plans = set(), set()
    kept_here, continue_force = [], False  # (--kept-chats: an SSH host's chats that keep going, from the computer that asks)
    history = None  # (--no-history, --history-since: the Recap's history setting, from the computer that asks)
    container_days, picked = None, []
    while args:
        arg = args.pop(0)
        if arg == "--config-dir" and args:
            config_dirs.append(args.pop(0))
        elif arg == "--end" and args:
            end = args.pop(0)
        elif arg == "--interrupt" and args:
            interrupt = args.pop(0)
        elif arg == "--agent-run" and args:
            agent_run_id = args.pop(0)
        elif arg == "--chat" and args:
            chat_id = args.pop(0)
        elif arg == "--find" and args:
            find = args.pop(0)
        elif arg in ("--start-task", "--task-command") and args:
            task_action, task_folder = arg, args.pop(0)
        elif arg == "--continue-chat" and args:
            continue_id = args.pop(0)
        elif arg == "--force":
            continue_force = True
        elif arg == "--kept-chats" and args:
            for item in args.pop(0).split(","):
                chat, _, profile = item.partition("/")
                if valid_id(chat) and profile:
                    kept_here.append({"chat": chat, "profile": profile, "host": "", "name": "", "folder": ""})
        elif arg == "--folder" and args:
            continue_folder = args.pop(0)
        elif arg == "--ends-at" and args:
            try:
                continue_ends_at = int(args.pop(0))
            except ValueError:
                sys.exit(USAGE)
        elif arg == "--prompt" and args:
            prompt = args.pop(0)
        elif arg == "--model" and args:
            model = args.pop(0)
        elif arg == "--effort" and args:
            effort = args.pop(0)
        elif arg == "--permission-mode" and args:
            mode = args.pop(0)
        elif arg == "--plan" and args:
            plan_slug = args.pop(0)
        elif arg == "--plan-profile" and args:
            plan_profile = args.pop(0)
        elif arg == "--plan-text" and args:
            plan_text = args.pop(0)
        elif arg == "--busy":
            busy = True
        elif arg == "--vscode-account" and args:
            vscode_account = args.pop(0)
        elif arg == "--vscode-server" and args:
            vscode_server = args.pop(0)
        elif arg == "--profile" and args:
            profile_key = args.pop(0)
        elif arg == "--instance" and args:
            instance = args.pop(0)
        elif arg == "--interval-ms" and args:
            try:
                interval_ms = max(1000, int(args.pop(0)))
            except ValueError:
                sys.exit(USAGE)
        elif arg == "--done-hours" and args:
            try:
                done_hours = max(0.0, float(args.pop(0)))
            except ValueError:
                sys.exit(USAGE)
        elif arg in ("--recent", "--plans", "--memories", "--limit") and args:
            try:
                n = max(0, int(args.pop(0)))
            except ValueError:
                sys.exit(USAGE)
            if arg == "--recent":
                recent = n
            elif arg == "--plans":
                plans = n
            elif arg == "--memories":
                memories = n
            else:
                find_limit = max(1, n)
        elif arg == "--remote":
            remote = True
        elif arg == "--local":
            local = True
        elif arg in ("--starred-chats", "--starred-plans") and args:
            (starred_chats if arg == "--starred-chats" else starred_plans).update(i for i in args.pop(0).split(",") if i)
        elif arg == "--dismiss" and args:
            dismiss = args.pop(0)
        elif arg == "--undismiss-all":
            undismiss = True
        elif arg == "--hide" and len(args) >= 2:
            hide_kind, hide_id = args.pop(0), args.pop(0)
        elif arg == "--show-hidden" and args:
            show_kind = args.pop(0)
        elif arg.startswith("--config-dir="):
            config_dirs.append(arg.partition("=")[2])
        elif arg == "--no-tokens":
            with_tokens = False
        elif arg == "--no-history":
            history = (False, None)
        elif arg == "--history-since" and args and args[0].isdigit():
            history = (True, int(args.pop(0)))
        elif arg == "--pretty":
            pretty = True
        elif arg == "--keep-going":
            keep_going = True
        elif arg == "--cleanup-check":
            cleanup_check = True
        elif arg == "--usage-cap" and args and args[0].isdigit():
            usage_cap = min(100, int(args.pop(0)))
        elif arg == "--usage-refresh" and args and args[0].isdigit():
            usage_refresh = min(USAGE_REFRESH_MAX_MINUTES, int(args.pop(0)))
        elif arg == "--fetch-usage":
            fetch_usage = True
        elif arg == "--list-containers" and args and args[0].isdigit():
            container_days = int(args.pop(0))
        elif arg == "--picked" and args:
            picked = [p for p in args.pop(0).split(",") if p]
        else:
            sys.exit(USAGE)
    os.umask(0o077)  # cache files are private to the user
    home = Path.home()
    adopt_legacy_dirs(home)
    cache_root = cache_dir(home)
    if (agent_run_id is None) != (chat_id is None):
        sys.exit(USAGE)
    if (task_action is not None or continue_id is not None) and not profile_key:
        sys.exit(USAGE)
    if container_days is not None:
        try:
            result = dict(list_containers(cache_root, home, container_days, picked), ok=True, message="")
        except Exception as exc:
            result = {"ok": False, "message": f"{type(exc).__name__}: {exc}"}
    elif fetch_usage:
        try:
            result = fetch_usage_now(home, cache_root, config_dirs)
        except Exception as exc:
            result = {"ok": False, "message": f"{type(exc).__name__}: {exc}"}
    elif find is not None:
        try:
            result = find_chats(home, cache_root, config_dirs, find, find_limit)
            if remote:
                add_found_commands(result, home, config_dirs)
        except Exception as exc:
            result = {"ok": False, "message": f"{type(exc).__name__}: {exc}"}
    elif plan_text is not None:
        try:
            result = plan_markdown(home, config_dirs, plan_text, profile_key)
        except Exception as exc:
            result = {"ok": False, "message": f"{type(exc).__name__}: {exc}"}
    elif continue_id is not None:
        try:
            result = continue_chat(home, config_dirs, profile_key, continue_id, continue_folder, prompt,
                                   force=continue_force, ends_at=continue_ends_at)
        except Exception as exc:
            result = {"ok": False, "message": f"{type(exc).__name__}: {exc}"}
    elif task_action is not None:
        try:
            result = run_task(home, config_dirs, task_action == "--start-task", task_folder, profile_key, prompt,
                              plan_slug, plan_profile, model=model, effort=effort, mode=mode)
        except Exception as exc:
            result = {"ok": False, "message": f"{type(exc).__name__}: {exc}"}
    elif agent_run_id is not None:
        try:
            ok, message, title, markdown = agent_run(home, config_dirs, chat_id, agent_run_id, profile_key)
        except Exception as exc:
            ok, message, title, markdown = False, f"{type(exc).__name__}: {exc}", None, None
        result = {"ok": ok, "message": message, "title": title, "markdown": markdown}
    elif end is not None or interrupt is not None:
        try:
            ok, message = (stop_chat_by_id(home, config_dirs, end, profile_key, busy) if end is not None
                           else interrupt_chat_by_id(home, config_dirs, interrupt, profile_key))
        except Exception as exc:
            ok, message = False, f"{type(exc).__name__}: {exc}"
        result = {"ok": ok, "message": message}
    elif vscode_account is not None:
        ok, message = set_vscode_server_config_dir(home, None if vscode_account == "-" else vscode_account,
                                                   vscode_server, config_dirs)
        result = {"ok": ok, "message": message}
    elif dismiss is not None or undismiss or hide_kind is not None or show_kind is not None:
        try:
            if dismiss is not None or hide_kind is not None:
                ok, message = hide_item(cache_root, "chats" if dismiss is not None else hide_kind,
                                        dismiss if dismiss is not None else hide_id)
            else:
                ok, message = show_hidden(cache_root, "chats" if undismiss else show_kind)
            result = {"ok": ok, "message": message}
        except OSError as exc:
            result = {"ok": False, "message": str(exc)}
    else:
        try:
            result = collect(home, cache_root, config_dirs, with_tokens=with_tokens, keep_done_hours=done_hours,
                             recent=recent, plans=plans, memories=memories,
                             usage_cap=usage_cap if not remote or local else 0,
                             # (on an SSH host: the host's stars, from the computer that asks)
                             starred={"chats": starred_chats, "plans": starred_plans} if remote and not local else None,
                             usage_refresh=usage_refresh, kept=kept_here if remote and not local else None,
                             history=history if remote and not local else None)
            try:
                add_vscode(result, home, config_dirs, remote and not local, cache_root)
            except Exception as exc:
                result["errors"].append(f"VS Code: {exc}")
            # Whether chats can open in a terminal here: the widget greys
            # that out when there's no claude command (and when unsure, doesn't)
            claude = None
            try:
                claude = cached_find_claude(home, cache_root, time.time())
                # (and whether a hook given to one chat runs: Talpy Chat answers a background chat through it)
                result["cli"] = {"installed": claude is not None, "hooks": not managed_hooks_only()}
            except Exception as exc:
                result["errors"].append(f"claude command: {exc}")
            result["homeId"] = home_id(home)
            if instance is not None:
                try:
                    result["notifier"] = elect_notifier(cache_root, instance, interval_ms, int(time.time() * 1000))
                    result["sharedSettings"] = shared_settings(cache_root)
                except (OSError, ValueError) as exc:
                    result["errors"].append(f"other widgets: {exc}")
            if not remote or local:  # (this computer's chats: an SSH host's keep going from here, not there)
                try:
                    if keep_going or result.get("notifier") is True:
                        look_after_kept(home, cache_root, config_dirs, result["groups"], int(time.time() * 1000),
                                        usage_cap, result.get("moved"))
                    result["keep"] = kept_chats(cache_root, result.get("moved"))
                except Exception as exc:
                    result["errors"].append(f"chats that keep going: {exc}")
            if (not remote or local) and (keep_going or cleanup_check or result.get("notifier") is True):
                try:  # (this computer's chats and accounts for other programs: the jobs file, when they changed)
                    publish_jobs(jobs_file_path(home, cache_root), cache_root, "", place_jobs(result["groups"]),
                                 int(time.time() * 1000), place_accounts(result["groups"]))
                except Exception as exc:
                    result["errors"].append(f"jobs file: {exc}")
                try:  # (old chats: Talpy Den's daily cleanup, when it's the one that cleans, cleanup.py)
                    if cleanup_due(cache_root, time.time()):
                        start_cleanup(cache_root, config_dirs)
                except Exception as exc:
                    result["errors"].append(f"old chats: {exc}")
            if remote and not local and kept_here:  # (how each stands: the computer that asks keeps them going)
                try:
                    result["keptTurns"] = kept_turns(home, config_dirs, kept_here, result.get("moved") or {})
                except Exception as exc:
                    result["errors"].append(f"chats that keep going: {exc}")
            if remote:
                result["host"] = os.uname().nodename
                add_remote_commands(result, home, config_dirs, claude)
            try:  # (a widget updated since the hooks went on: their copies too, and their commands)
                refresh_hooks(home)
                upgrade_hook_settings(home, config_dirs)
            except Exception as exc:
                result["errors"].append(f"hooks: {exc}")
        except Exception as exc:  # the widget must always get parseable output
            result = {"ok": False, "error": f"{type(exc).__name__}: {exc}", "generatedAt": int(time.time() * 1000)}
    # ASCII only: a lone surrogate (half an emoji cut off in a title) can't be
    # written as UTF-8, and a host's locale may not be UTF-8 at all
    try:
        if result.get("ok") and "groups" in result:
            add_revs(result)
        text = json.dumps(result, indent=2 if pretty and not remote else None)
        if not pretty and result.get("ok") and "groups" in result:
            text = stamped(text)
    except (TypeError, ValueError) as exc:
        text = json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}", "generatedAt": int(time.time() * 1000)})
    if remote:
        # Login scripts on the host may print things first: the JSON follows a marker
        sys.stdout.write("\n" + REMOTE_MARK + " ")
    sys.stdout.write(text + "\n")


if __name__ == "__main__":
    main()
