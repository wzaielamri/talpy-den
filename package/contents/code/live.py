#!/usr/bin/env python3
"""What changed in your chats, the moment it changes: the widget's watcher.

    python3 -I live.py --wait [--as NAME] [--timeout S] [--config-dir DIR]... [--requests] [--remote] [--opens]
    python3 -I live.py --take-open NAME

Waits until a chat changes, prints what changed and exits (the widget runs
it again at once). It watches two things:
  - each Claude profile's session files (<config dir>/sessions/<pid>.json),
    which Claude writes whenever a chat starts or ends, starts working,
    waits for you or ends its turn (also when you answer or interrupt it in
    its terminal);
  - the live files of the live hook (live_hook.py, ~/.cache/talpy-den/
    live/<session id>.json), with what each chat does now, step by step.

    {"ok": true, "at": ms, "sessions": bool, "urgent": bool, "live": [...],
     "timeout": bool[, "requests": bool, "changed": [session ids]][, "open": jobs file id, "request": NAME]}

sessions: a session file changed (the status is worth checking now);
urgent: that, or a live file says a turn started or ended, a chat asks for
something, or a session or subagent started or ended; live: the live files
that changed. A chat's steps alone (tool calls) come at most every
MIN_GAP_S, so a busy chat doesn't wake the widget all the time. After S
seconds (TIMEOUT_S) with nothing new it answers anyway (timeout true).

--requests: also the permission hook's requests (permission_hook.py, in
Talpy Den's state folder, and an older hook's in its cache): one that comes
or goes is "requests" true (urgent), and "changed" names the chats whose
session files or requests changed. --remote (on an SSH host or in a
container, sent there on python3's stdin by remote.py --watch): the answer
comes after the marker line, as every host answer does, the live files
aren't looked at (nothing there uses them), and it ends as soon as the
connection that asked is gone (its stdout hangs up), not only at its timeout.

--opens (the Plasma widget's): also another program's request that a chat be
brought up as a click on its row does (jump.py --job: Talpy Den Display's
tap), a file of its own in $XDG_RUNTIME_DIR/talpy-den/opens (only you can
write there). A fresh one naming a jobs file id is offered once, as "open"
(the id) and "request" (its file's NAME); the widget takes it with
--take-open NAME, which answers {"ok", "id"}, only if it lists that chat, and
only then brings the chat up. Anything else is dropped; nothing in a request
is ever run: the widget only looks the id up among the chats it lists.

NAME: who asks (the Plasma widget's copies in one plasmashell are one
NAME). What it was told last is kept in the live folder, so what changes
between two runs isn't missed, and the command line stays the same from
run to run (Plasma keeps every command's name; hub/Exec.qml).

Linux (inotify); elsewhere it looks every half second. Standard library
only, Python 3.7+.
"""
import errno
import hashlib
import json
import os
import re
import select
import stat
import sys
import time

TIMEOUT_S = 50
MIN_GAP_S = 0.4  # between two answers about steps alone
GATHER_S = 0.05  # after a change: what comes with it (a session file and a live file)
FRESH_S = 86400  # live files the first answer sends (younger than this)
SEEN_KEEP_S = 7 * 86400
# what a live file's last event must be to make an answer urgent (live_hook.py)
URGENT_EVENTS = {"UserPromptSubmit", "Stop", "StopFailure", "PermissionRequest", "Notification", "SessionStart",
                 "SessionEnd", "PreCompact", "SubagentStart", "SubagentStop"}
# inotify: IN_CLOSE_WRITE | IN_MOVED_FROM | IN_MOVED_TO | IN_DELETE
WATCH_MASK = 0x8 | 0x40 | 0x80 | 0x200
REMOTE_MARK = "@@talpy-den@@"  # (talpy_den.REMOTE_MARK: the line before a host's answer)
PERMISSIONS = "permissions"


def state_root(home):
    """Talpy Den's state folder, where the permission hook writes its
    requests (permission_hook.cache_root has it the same way)."""
    base = os.environ.get("XDG_STATE_HOME")
    if not base:
        cache = os.path.normpath(os.environ.get("XDG_CACHE_HOME") or os.path.join(home, ".cache"))
        base = (os.path.join(os.path.dirname(cache), ".local", "state") if os.path.basename(cache) == ".cache"
                else os.path.join(cache, "state"))
    return os.path.join(base, "talpy-den")


def request_dirs(home):
    """The permission hook's requests folders: the state folder's (made, 0700,
    so it can be watched before the first request; not one others may write
    in, which isn't watched), then the cache's, where an older hook writes."""
    state = os.path.join(state_root(home), PERMISSIONS)
    out = []
    try:
        os.makedirs(state, mode=0o700, exist_ok=True)
        st = os.lstat(state)
        if (st.st_mode & 0o170000) == 0o040000 and st.st_uid == os.getuid() and not st.st_mode & 0o022:
            out.append(state)
    except OSError:
        pass
    old = os.path.join(cache_root(home), PERMISSIONS)
    if os.path.isdir(old):
        out.append(old)
    return out


# Another program's request that a chat be brought up as a click on its row does (jump.py --job writes it:
# Talpy Den Display's tap): a file of its own each (req-<16 hex>.json: the chat's jobs file id and the time, nothing
# else) in $XDG_RUNTIME_DIR/talpy-den/opens (in memory, yours alone, gone when you log out). --opens tells the
# widget of one (an offer: read, not taken), once; the widget takes it (--take-open NAME) only if it lists that
# chat, and only then brings it up. Taken by renaming it away: of two takers one gets it, and jump.py, whose file
# it is, takes it back when nobody did, so no window pops up later. Only a fresh request naming a jobs file id
# (jump.py's JOB_ID) is ever offered; nothing in it is ever run. Its file's name is the one thing that goes on a
# command line (--take-open NAME) and into a path: jump.py makes it, and it's taken only if it's OPEN_NAME
# exactly (16 hex digits), checked by live.py, by the widget and again by --take-open: keep it that strict.
OPENS = "opens"
OPEN_NAME = re.compile(r"req-[0-9a-f]{16}\.json")
OPEN_MAX_AGE_S = 10   # a request older than this is dropped (a tap long ago mustn't open a window now)
OPEN_AHEAD_S = 2      # nor one from the future (more than a clock's slip)
OPEN_MAX_BYTES = 1024
OPEN_STALE_S = 60     # a writer's or a taker's file left behind (it was killed in between): swept after this
JOB_ID_MAX = 300
JOB_ID = re.compile(r"(?:[A-Za-z0-9_.@][A-Za-z0-9_.@:-]*:)?[A-Za-z0-9_.+-]+/[A-Za-z0-9_.-]+/(?:live|job|chat)(?:/shared)?")


def job_id_ok(job_id):
    """Whether job_id has a jobs file id's shape (the same rule as jump.py's job_id_ok)."""
    return (isinstance(job_id, str) and len(job_id) <= JOB_ID_MAX and JOB_ID.fullmatch(job_id) is not None
            and ".." not in job_id and not job_id.startswith("-"))


def _private_dir(path):
    st = os.lstat(path)
    return stat.S_ISDIR(st.st_mode) and st.st_uid == os.getuid() and not st.st_mode & 0o077


def open_dir():
    """$XDG_RUNTIME_DIR/talpy-den/opens (made, 0700), or None: no runtime folder, or it or the folders in it aren't
    folders of yours only you can use (then there are no requests). Leftovers are swept."""
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime or not os.path.isabs(runtime):
        return None
    folder = os.path.join(runtime, "talpy-den", OPENS)
    try:
        os.makedirs(folder, mode=0o700, exist_ok=True)
        if not (_private_dir(runtime) and _private_dir(os.path.dirname(folder)) and _private_dir(folder)):
            return None
        names = os.listdir(folder)
    except OSError:
        return None
    now = time.time()
    for name in names:   # (each on its own: a take's or a write's file comes and goes meanwhile)
        if name.startswith(("tmp-", "taken-")):
            path = os.path.join(folder, name)
            try:
                st = os.lstat(path)
                if now - st.st_mtime > OPEN_STALE_S and not stat.S_ISDIR(st.st_mode):
                    os.unlink(path)
            except OSError:
                pass
    return folder


def _read_request(path, now):
    """("ok", id) for a fresh request naming a jobs file id at path; ("drop", None) for one that never will be
    (stale; not a regular file of yours of at most OPEN_MAX_BYTES, or a link; not a request of the right shape);
    ("skip", None) for one that can't be told now (unreadable for a moment, or ahead of the clock: its writer
    takes it back). now: seconds."""
    data = b""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    except OSError as exc:
        return ("drop" if exc.errno == errno.ELOOP else "skip"), None   # (ELOOP: a link, never followed)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_size > OPEN_MAX_BYTES:
            return "drop", None
        data = os.read(fd, OPEN_MAX_BYTES + 1)
    except OSError:
        return "skip", None
    finally:
        os.close(fd)
    try:
        asked = json.loads(data.decode("utf-8"))
    except (ValueError, RecursionError):
        return "drop", None
    job, at = (asked.get("id"), asked.get("at")) if isinstance(asked, dict) else (None, None)
    if not job_id_ok(job) or not isinstance(at, int) or isinstance(at, bool) or at < now * 1000 - OPEN_MAX_AGE_S * 1000:
        return "drop", None
    if at > now * 1000 + OPEN_AHEAD_S * 1000:
        return "skip", None
    return "ok", job


def take_open(folder, name, now):
    """(taken, id): take the request file name (renamed away, then gone: once). taken False: there's none of that
    name (another took it); id None: it was taken but isn't a fresh request naming a jobs file id."""
    if not isinstance(name, str) or not OPEN_NAME.fullmatch(name):
        return False, None
    taken = os.path.join(folder, "taken-%d-%s.json" % (os.getpid(), os.urandom(4).hex()))
    try:
        os.rename(os.path.join(folder, name), taken)   # (atomic: of two takers one gets it; a link moves as a link)
    except OSError:
        return False, None
    try:
        verdict, job = _read_request(taken, now)
        return True, job if verdict == "ok" else None
    finally:
        try:
            os.unlink(taken)
        except OSError:
            pass


def pending_opens(folder, now):
    """[(name, id)] of the fresh requests in folder, the oldest first; one that never will be (stale, of a wrong
    shape, not a file) is taken and dropped, one that can't be told now is left (its writer takes it back)."""
    out = []
    try:
        names = [n for n in os.listdir(folder) if OPEN_NAME.fullmatch(n)]
    except OSError:
        return out
    dated = []
    for name in names:
        try:
            dated.append((os.lstat(os.path.join(folder, name)).st_mtime, name))
        except OSError:
            pass
    for _, name in sorted(dated):
        verdict, job = _read_request(os.path.join(folder, name), now)
        if verdict == "ok":
            out.append((name, job))
        elif verdict == "drop":
            take_open(folder, name, now)
    return out


def offered_path(home, name):
    """What NAME was offered (request names), so it's offered once: the widget runs live.py again at once."""
    return os.path.join(live_dir(home), ".offered-" + hashlib.sha1(name.encode()).hexdigest()[:12] + ".json")


def load_offered(path):
    try:
        with open(path, encoding="utf-8") as f:
            offered = json.load(f)
    except (OSError, ValueError, RecursionError):
        return {}
    return offered if isinstance(offered, dict) else {}


def save_offered(path, offered):
    tmp = "%s.%d.%s.tmp" % (path, os.getpid(), os.urandom(4).hex())
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(offered, f, separators=(",", ":"))
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def cache_root(home):
    return os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.join(home, ".cache"), "talpy-den")


def live_dir(home):
    return os.path.join(cache_root(home), "live")


def session_dirs(home, extra=()):
    """Each Claude profile's sessions folder (~/.claude, ~/.claude-*, and
    the extra config dirs), once per real folder."""
    try:
        names = sorted(n for n in os.listdir(home) if n == ".claude" or n.startswith(".claude-"))
    except OSError:
        names = []
    seen, out = set(), []
    for folder in [os.path.join(home, n) for n in names] + [os.path.expanduser(d) for d in extra]:
        real = os.path.realpath(os.path.join(folder, "sessions"))
        if real not in seen and os.path.isdir(real):
            seen.add(real)
            out.append(real)
    return out


def listing(folder):
    """{name: mtime ns} of the .json files in a folder."""
    out = {}
    try:
        with os.scandir(folder) as it:
            for e in it:
                if e.name.endswith(".json") and not e.name.startswith("."):
                    try:
                        out[e.name] = e.stat().st_mtime_ns
                    except OSError:
                        pass
    except OSError:
        pass
    return out


def snapshot(live, sessions, requests=None):
    """{"live": {name: mtime}, "sessions": {path: mtime}} (live None: not
    looked at), and with requests (folders): "requests": {path: mtime}, an
    answer of yours and a file still being written left out."""
    snap = {"live": listing(live) if live else {},
            "sessions": {os.path.join(d, n): t for d in sessions for n, t in listing(d).items()}}
    if requests is not None:
        snap["requests"] = {os.path.join(d, n): t for d in requests for n, t in listing(d).items()
                            if not n.endswith(".answer.json")}
    return snap


def session_of(path):
    """The session id a session file or a request names, or None."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    sid = data.get("sessionId") if isinstance(data, dict) else None
    return sid if isinstance(sid, str) and 0 < len(sid) <= 64 else None


def changed_chats(seen, snap):
    """The session ids whose session files or requests changed since what
    was told (one gone: the id it was told under, kept in "ids")."""
    told = seen if seen is not None else {}
    ids = told.get("ids") if isinstance(told.get("ids"), dict) else {}
    out, now_ids = set(), {}
    for kind in ("sessions", "requests"):
        before = told.get(kind) if isinstance(told.get(kind), dict) else {}
        after = snap.get(kind) or {}
        for path, t in after.items():
            sid = ids.get(path) if before.get(path) == t else session_of(path)
            if sid:
                now_ids[path] = sid
            if before.get(path) != t and sid:
                out.add(sid)
        for path in before:
            if path not in after and ids.get(path):
                out.add(ids[path])
    snap["ids"] = now_ids
    return sorted(out)


def read_view(path):
    try:
        with open(path, encoding="utf-8") as f:
            view = json.load(f)
    except (OSError, ValueError):
        return None
    return view if isinstance(view, dict) and isinstance(view.get("sessionId"), str) else None


def seen_path(home, name):
    return os.path.join(live_dir(home), ".seen-" + hashlib.sha1(name.encode()).hexdigest()[:12] + ".json")


def load_seen(path):
    try:
        with open(path, encoding="utf-8") as f:
            seen = json.load(f)
    except (OSError, ValueError):
        return None
    ok = isinstance(seen, dict) and isinstance(seen.get("live"), dict) and isinstance(seen.get("sessions"), dict)
    return seen if ok else None


def save_seen(path, snap, at):
    """Keep what NAME was told: whether it could be (a full disk, a quota)."""
    # (a new file of its own, never through a link someone put at its name: the cache may be shared)
    tmp = "%s.%d.%s.tmp" % (path, os.getpid(), os.urandom(4).hex())
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(dict(snap, at=at), f, separators=(",", ":"))
        os.replace(tmp, path)
        return True
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return False


def tidy_seen(home, now):
    """What other NAMEs were told (and offered) goes after a week without them."""
    folder = live_dir(home)
    try:
        names = [n for n in os.listdir(folder) if n.startswith((".seen-", ".offered-"))]
    except OSError:
        return
    for name in names:
        try:
            if now - os.stat(os.path.join(folder, name)).st_mtime > SEEN_KEEP_S:
                os.unlink(os.path.join(folder, name))
        except OSError:
            pass


def changes(seen, snap, live, now):
    """(sessions changed, [live views changed], requests changed) since what
    was told (seen; None: nothing was told yet; one told before requests
    were watched: none of them were)."""
    requests = "requests" in snap and (seen is None or seen.get("requests") != snap["requests"])
    if not live:
        return seen is None or seen["sessions"] != snap["sessions"], [], requests
    if seen is None:
        fresh = [n for n, t in snap["live"].items() if now - t / 1e9 < FRESH_S]
        return True, [v for v in (read_view(os.path.join(live, n)) for n in sorted(fresh)) if v], requests
    told = seen["live"]
    names = [n for n, t in snap["live"].items() if told.get(n) != t]
    views = [v for v in (read_view(os.path.join(live, n)) for n in sorted(names)) if v]
    return seen["sessions"] != snap["sessions"], views, requests


class Gone(Exception):
    """Whoever asked is gone: nobody reads the answer."""


class Watch:
    """inotify on the folders, or files (None: not on this system: look every half second)."""

    def __init__(self, folders, mask=WATCH_MASK):
        self.fd = None
        try:
            import ctypes   # (here: a Python without it, a slim image's, still looks every half second)
            libc = ctypes.CDLL("libc.so.6", use_errno=True)
            fd = libc.inotify_init1(0o4000 | 0o2000000)  # IN_NONBLOCK | IN_CLOEXEC
        except (OSError, AttributeError, ImportError):
            return
        if fd < 0:
            return
        added = [libc.inotify_add_watch(fd, f.encode(), mask) for f in folders]
        if not any(w >= 0 for w in added):
            os.close(fd)
            return
        self.fd = fd

    def wait(self, seconds, hangup=None):
        """Wait up to seconds for a change: whether one came. hangup: a file
        descriptor (stdout) whose other end going away ends the wait too
        (Gone)."""
        wait = min(seconds, 0.5) if self.fd is None else max(0.0, seconds)
        if self.fd is None and hangup is None:
            time.sleep(wait)
            return True  # (the caller looks again)
        poll = select.poll()
        if self.fd is not None:
            poll.register(self.fd, select.POLLIN)
        if hangup is not None:
            poll.register(hangup, 0)   # (a hang-up or an error is reported whatever is asked)
        events = poll.poll(int(wait * 1000))
        if any(fd == hangup and event & (select.POLLERR | select.POLLHUP | select.POLLNVAL) for fd, event in events):
            raise Gone()
        return True if self.fd is None else any(fd == self.fd for fd, _ in events)

    def drain(self):
        if self.fd is None:
            return
        try:
            while os.read(self.fd, 65536):
                pass
        except OSError:
            pass

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


def wait(home, extra=(), name="default", timeout=TIMEOUT_S, clock=time.time, requests=False, remote=False, hangup=None,
         opens=False):
    """The answer of --wait (see the top). requests: the permission hook's
    requests too; remote: no live files; hangup: stdout, whose other end
    going away ends it (Gone); opens: open requests too (taken, answered as
    "open")."""
    live = None if remote else live_dir(home)
    try:
        os.makedirs(live_dir(home), mode=0o700, exist_ok=True)   # (also where what NAME was told is kept)
    except OSError:
        pass
    sessions = session_dirs(home, extra)
    asks = request_dirs(home) if requests else None
    opening = open_dir() if opens and not remote else None
    offers = offered_path(home, name)
    # (watching first: nothing between the look and the wait is missed)
    watch = Watch(([live] if live else []) + sessions + (asks or []) + ([opening] if opening else []))
    path = seen_path(home, name)
    seen = load_seen(path)
    parent = os.getppid()
    start = clock()
    if seen is None or start - (seen.get("at") or 0) > SEEN_KEEP_S:
        tidy_seen(home, start)
    while True:
        if os.getppid() != parent:
            sys.exit(0)  # (the widget is gone)
        now = clock()
        pending = pending_opens(opening, now) if opening else []
        if pending:
            offered = load_offered(offers)
            new = [(n, j) for n, j in pending if n not in offered]
            if new:   # (at once, alone: what changed besides is told by the next run)
                save_offered(offers, dict({n: offered[n] for n, _ in pending if n in offered}, **{new[0][0]: now}))
                answer = {"ok": True, "at": int(now * 1000), "sessions": False, "urgent": False, "live": [],
                          "timeout": False, "open": new[0][1], "request": new[0][0]}
                if requests:
                    answer.update(requests=False, changed=[])
                return answer
        snap = snapshot(live, sessions, asks)
        moved, views, asked = changes(seen, snap, live, now)
        urgent = moved or asked or any(v.get("event") in URGENT_EVENTS for v in views)
        since = now - (seen.get("at") or 0) if seen is not None else MIN_GAP_S
        if views and not urgent and 0 <= since < MIN_GAP_S:
            # (steps alone, just after the last answer: a moment later, with
            # what comes meanwhile; a last answer later than now is one from
            # before the clock was set back)
            if watch.wait(MIN_GAP_S - since, hangup):
                time.sleep(GATHER_S)
                watch.drain()
            continue
        if moved or views or asked:
            answer = {"ok": True, "at": int(now * 1000), "sessions": moved, "urgent": urgent, "live": views,
                      "timeout": False}
            if requests:
                answer.update(requests=asked, changed=changed_chats(seen, snap))
            if not save_seen(path, snap, now) and seen is None and remote:
                # (what it was told can't be kept there: every run would answer at once, and the caller run
                # again at once, for good. It waits for a change from now on instead)
                seen = dict(snap, at=now)
                continue
            return answer
        left = timeout - abs(now - start)  # (the clock set back meanwhile: time's up)
        if left <= 0:
            answer = {"ok": True, "at": int(now * 1000), "sessions": False, "urgent": False, "live": [], "timeout": True}
            if requests:
                answer.update(requests=False, changed=[])
            return answer
        if watch.wait(min(left, 1.0), hangup):
            time.sleep(GATHER_S)
            watch.drain()


def main(argv=None):
    args = sys.argv[1:] if argv is None else list(argv)
    name, timeout, extra, waiting, requests, remote, opens = "default", TIMEOUT_S, [], False, False, False, False
    if args[:1] == ["--take-open"]:   # --take-open NAME, alone: the widget takes the request it was offered
        if len(args) != 2:
            sys.exit(__doc__)
        folder = open_dir()
        taken, job = take_open(folder, args[1], time.time()) if folder else (False, None)
        sys.stdout.write(json.dumps({"ok": bool(taken and job), "id": job or ""}, ensure_ascii=True) + "\n")
        return
    while args:
        arg = args.pop(0)
        if arg == "--wait":
            waiting = True
        elif arg == "--requests":
            requests = True
        elif arg == "--remote":
            remote = True
        elif arg == "--opens":
            opens = True
        elif arg == "--as" and args:
            name = args.pop(0)
        elif arg == "--timeout" and args:
            try:
                timeout = max(1.0, float(args.pop(0)))
            except ValueError:
                sys.exit(__doc__)
        elif arg == "--config-dir" and args:
            extra.append(args.pop(0))
        else:
            sys.exit(__doc__)
    if not waiting:
        sys.exit(__doc__)
    os.umask(0o077)
    try:
        answer = wait(os.path.expanduser("~"), extra, name, timeout, requests=requests, remote=remote,
                      hangup=sys.stdout.fileno() if remote else None, opens=opens)
    except Gone:
        return  # (nobody reads it: the connection that asked is gone)
    except Exception as exc:  # the widget must always get parseable output
        answer = {"ok": False, "message": "%s: %s" % (type(exc).__name__, exc)}
    sys.stdout.write(("\n" + REMOTE_MARK + " " if remote else "") + json.dumps(answer, ensure_ascii=True) + "\n")


if __name__ == "__main__":
    main()
