#!/usr/bin/env python3
"""Old chats and plans: Claude Code's own cleanup, or Talpy Den's in its
place (Settings → Chats → Old chats).

Claude Code deletes what's older than its cleanupPeriodDays (30 by default)
when it starts, at most once a day: chats, the plans of an account's plans/
folder, undo history, finished background chats and its caches, by their
last change, starred or not, for good. Choosing Talpy Den's cleanup sets
cleanupPeriodDays to 3650 (Claude's own "~10 years") on every account, here
and on the SSH hosts and containers shown, and Talpy Den deletes once a day
what you haven't used for the days you picked, as Claude would (the same
files, by the same dates), but never:

  - a chat you starred, nor one that keeps going, has a go-on queued, or is
    open now (its process runs), nor one Claude Desktop still has (Claude's
    own exception);
  - a chat's undo history, files or folder while its chat stays;
  - a plan you starred, one a queued task carries out, nor one whose chat
    stays; an old plan goes to your Trash, not away for good;
  - a background chat that hasn't finished, or whose worker still runs.

Choosing Claude Code's cleanup again puts cleanupPeriodDays back as it was
on each account where Talpy Den changed it (cleanup-claude.json in the
state folder notes what it was), unless you changed it since.

The status check of one copy starts the daily run (talpy_den.cleanup_due,
start_cleanup): this computer first, then each SSH host and container that
answered a check in the last day, over ssh (its starred chats and plans are
kept here: they go with it). A chat it deletes takes its bookmarks in
Talpy Chat along (kept here, a host's chat's too). Plans of a project's own
folder, memories, CLAUDE.md and what Claude keeps outside an account's
folder aren't touched.

    cleanup.py --status [--days N] [--config-dir DIR]...
                                                the setting, the last runs, and what a run would
                                                delete here now, at N days (nothing is deleted)
    cleanup.py --setting                        only the choice (no run, dry or not)
    cleanup.py --set claude | --set talpy DAYS  choose; it takes effect at once
    cleanup.py --run [--config-dir DIR]...      the run: here, then the SSH hosts and containers
    cleanup.py --place claude|DAYS [--keep-chats IDS] [--keep-plans SLUGS] [--dry-run] [--remote]
                                                one computer's (an SSH host's: run there over ssh)
    cleanup.py --uninstall                      Claude Code's own cleanup again, here and on the
                                                hosts Talpy Den changed it on (install.sh --uninstall)
"""

import fcntl
import json
import os
import re
import shutil
import stat
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
if os.path.isfile(globals().get("__file__") or ""):  # (on an SSH host it comes on stdin, after talpy_den.py)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # -I leaves the script dir off sys.path
import talpy_den as cs  # noqa: E402

MODES = ("claude", "talpy")
DEFAULT_DAYS = 30  # (Claude Code's own)
MAX_DAYS = 3649
CLAUDE_KEEPS = 3650  # cleanupPeriodDays while Talpy Den cleans: Claude's "3650 for ~10 years"
SETTING_KEY = "cleanupPeriodDays"
CHANGED_FILE = "cleanup-claude.json"  # (state folder: the settings files changed, and what they said before)
RUNS_FILE = "cleanup-runs.json"  # (cache: each place's last run, "" this computer's, as the settings show it)
HOSTS_FILE = "cleanup-hosts.json"  # (state folder: the SSH hosts and containers it kept Claude's from cleaning on)
HOST_MODULES = ("accounts.py", "sharing.py")  # (loaded before this file on a host: the Trash, the shared chats' store)
HOST_TIMEOUT = 600  # s a host's run may take (a first one with much to delete: not cut off halfway at the usual 60)
LOCK_FILE = "cleanup.lock"
HOST_FRESH_S = 86400  # a host is cleaned when it answered a check in the last day
ERRORS_KEPT = 5
HEAD_BYTES = 16384  # read of a transcript's start, for its entrypoint
# A chat Claude Desktop keeps is Claude's own exception (entrypoint claude-desktop…, local-agent)
DESKTOP = re.compile(rb'"entrypoint"\s*:\s*"(?:claude-desktop[^"]*|local[-_]agent)"')
LEAD_ID = re.compile(r"^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})")
# A chat's id is a UUID: what else is in a project's folder (its memory/, …) is never taken for a chat
CHAT_ID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
# The account folders Claude empties of what's older than its cleanupPeriodDays, and Talpy Den in its
# place: (folder, whether its entries are folders). An entry named after a chat (a chat's undo history,
# its environment, pictures, tasks, todos, log) goes with its chat, and stays while its chat does.
AGED = (("file-history", True), ("session-env", True), ("image-cache", True), ("tasks", True), ("uploads", True),
        ("todos", False), ("debug", False), ("shell-snapshots", False), ("paste-cache", False))
COMPANIONS = (".ccr-tip.json", ".precompact.json")  # (beside a transcript: Claude deletes them with it)
# (on an SSH host this file comes on stdin after talpy_den.py: no __doc__ there)
USAGE = ("usage: cleanup.py --status [--days N] | --setting | --set claude | --set talpy DAYS | --run | --uninstall\n"
         "                  [--config-dir DIR]...\n"
         "       cleanup.py --place claude|DAYS [--keep-chats IDS] [--keep-plans SLUGS] [--dry-run] [--remote]")


# ---------------------------------------------------------------- the setting

def setting_path(cache_root):
    return cs.state_dir(cache_root) / cs.CLEANUP_SETTING_FILE


def load_setting(cache_root):
    """{"mode": "claude" | "talpy", "days", "pending" (Claude Code's own
    cleanup isn't back everywhere yet), "at"}: Claude Code's when it was
    never set."""
    data = cs.read_json(setting_path(cache_root))
    data = data if isinstance(data, dict) else {}
    days = data.get("days")
    ok_days = isinstance(days, int) and not isinstance(days, bool) and 1 <= days <= MAX_DAYS
    return {"mode": data.get("mode") if data.get("mode") in MODES else "claude",
            "days": days if ok_days else DEFAULT_DAYS, "pending": data.get("pending") is True,
            "at": int(cs.number(data.get("at")) or 0)}


def change_setting(cache_root, change, chosen=True):
    """Change the setting under a lock (every copy may write it): change(s)
    changes it in place, or returns False to leave it. The setting after;
    chosen: a choice of yours ("at" says when: a run going on runs again),
    not a run's own note ("pending" done)."""
    state = cs.state_dir(cache_root)
    cs.private_dir(state)
    with open(str(state / "cleanup-setting.lock"), "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        s = load_setting(cache_root)
        if change(s) is not False:
            if chosen:
                s["at"] = int(time.time() * 1000)
            cs.write_json_atomic(setting_path(cache_root), s, private=True)
        return s


# ---------------------------------------------------------------- Claude Code's own cleanupPeriodDays

def changed_path(cache_root):
    return cs.state_dir(cache_root) / CHANGED_FILE


def load_changed(cache_root):
    """{real settings.json path: {"had", "value", "made"}}: what each said before Talpy Den changed it."""
    data = cs.read_json(changed_path(cache_root))
    files = data.get("files") if isinstance(data, dict) else None
    return {k: v for k, v in files.items() if isinstance(k, str) and k.startswith("/") and isinstance(v, dict)} \
        if isinstance(files, dict) else {}


def save_changed(cache_root, files):
    cs.private_dir(cs.state_dir(cache_root))
    cs.write_json_atomic(changed_path(cache_root), {"files": files}, private=True)


settings_files = cs.claude_settings_files  # (each account's, once per real file: they often share one through links)


def read_settings(path):
    """(its JSON object, or None when it isn't one; whether the file is there)."""
    if not os.path.lexists(str(path)):
        return {}, False
    raw = cs.read_plain(path, cs.SETTINGS_MAX)
    try:
        text = raw.decode("utf-8") if raw is not None else None
        data = None if text is None else json.loads(text) if text.strip() else {}
    except (ValueError, RecursionError):
        data = None
    return (data if isinstance(data, dict) else None), True


write_settings = cs.write_claude_settings  # (the one writer of Claude's settings: pane.py's hooks use it too)


def keep_claude_from_cleaning(home, cache_root, profiles):
    """cleanupPeriodDays 3650 in every account's settings, noting what each
    said before: the problems (one that isn't JSON is left as it is: Claude
    keeps cleaning there)."""
    changed, problems = load_changed(cache_root), []
    with cs.claude_settings_lock(home):  # (read to written: a hook turned on meanwhile isn't lost)
        for path in settings_files(home, profiles):
            data, there = read_settings(path)
            if data is None:
                problems.append(f"{cs.short_path(str(path), str(home))} isn't a JSON object: Claude Code keeps cleaning up there")
                continue
            if data.get(SETTING_KEY) == CLAUDE_KEEPS:
                continue
            key = str(path)
            if key not in changed:
                changed[key] = {"had": SETTING_KEY in data, "value": data.get(SETTING_KEY), "made": not there}
                save_changed(cache_root, changed)  # (noted first: a write that half fails is still put back)
            data[SETTING_KEY] = CLAUDE_KEEPS
            try:
                write_settings(path, data)
            except OSError as exc:
                problems.append(f"{cs.short_path(str(path), str(home))}: {exc.strerror or exc}")
    return problems


def let_claude_clean(home, cache_root):
    """Put cleanupPeriodDays back where Talpy Den changed it (unless it was
    changed since): (problems, whether some are still left to put back)."""
    changed, left, problems = load_changed(cache_root), {}, []
    with cs.claude_settings_lock(home):
        for key, was in changed.items():
            put_back(home, key, was, left, problems)
    if left != changed:
        save_changed(cache_root, left)
    return problems, bool(left)


def put_back(home, key, was, left, problems):
    """One settings file's cleanupPeriodDays as it was, unless it went or
    was changed since (left: the ones still to put back)."""
    path = Path(key)
    data, there = read_settings(path)
    if not there:
        return
    if data is None:
        problems.append(f"{cs.short_path(key, str(home))} isn't a JSON object: put cleanupPeriodDays back yourself")
        left[key] = was
        return
    if data.get(SETTING_KEY) != CLAUDE_KEEPS:
        return  # (someone changed it since: theirs)
    if was.get("had"):
        data[SETTING_KEY] = was.get("value")
    else:
        data.pop(SETTING_KEY, None)
    try:
        if not data and was.get("made"):
            os.unlink(key)  # (Talpy Den made the file for it)
        else:
            write_settings(path, data)
    except OSError as exc:
        problems.append(f"{cs.short_path(key, str(home))}: {exc.strerror or exc}")
        left[key] = was


MANAGED_SETTINGS = "/etc/claude-code"  # (managed-settings.json and managed-settings.d/*.json: they win over every other)


def claude_overrides(home, profiles):
    """[{"path", "days"}]: the settings besides the accounts' own that set a
    cleanupPeriodDays under 3650, which Claude Code cleans up by when it runs
    there: a project's .claude/settings.json or settings.local.json (of the
    folders it ran in), a managed one. Talpy Den doesn't change those (a
    repository's, an administrator's): it says so."""
    paths = [os.path.join(MANAGED_SETTINGS, "managed-settings.json")]
    paths += sorted(e.path for e in entries(os.path.join(MANAGED_SETTINGS, "managed-settings.d")) if e.name.endswith(".json"))
    for p in profiles:
        for folder in getattr(p, "project_folders", ()):
            paths += [os.path.join(folder, ".claude", "settings.json"), os.path.join(folder, ".claude", "settings.local.json")]
    found, seen = [], set()
    for path in paths:
        if not os.path.isfile(path):
            continue
        real = os.path.realpath(path)
        if real in seen:
            continue
        seen.add(real)
        data, _there = read_settings(Path(real))
        days = (data or {}).get(SETTING_KEY)
        if isinstance(days, (int, float)) and not isinstance(days, bool) and days < CLAUDE_KEEPS:
            found.append({"path": cs.short_path(path, str(home)), "days": int(days)})
    return found


def claude_days(home, profiles):
    """[{"account", "days"}]: what Claude Code's own cleanup keeps on each account now."""
    out, seen = [], set()
    for p in profiles:
        real = os.path.realpath(str(p.path / "settings.json"))
        data, _there = read_settings(Path(real))
        days = (data or {}).get(SETTING_KEY)
        days = days if isinstance(days, (int, float)) and not isinstance(days, bool) and days >= 1 else DEFAULT_DAYS
        if (p.label, days) not in seen:
            seen.add((p.label, days))
            out.append({"account": p.label, "days": int(days)})
    return out


# ---------------------------------------------------------------- what stays

class Tally:
    """What a run did (or, dry, would do), as the settings show it."""

    def __init__(self):
        self.chats = self.jobs = self.files = self.plans = self.bytes = 0
        self.kept_chats = self.kept_plans = 0
        self.errors = []
        self.gone = []   # (the chats deleted: their bookmarks go too; not in what the settings show)

    def error(self, text):
        if len(self.errors) < ERRORS_KEPT:
            self.errors.append(text)

    def out(self):
        return {"chats": self.chats, "backgroundChats": self.jobs, "files": self.files, "plans": self.plans,
                "bytes": self.bytes, "keptChats": self.kept_chats, "keptPlans": self.kept_plans,
                "errors": self.errors, "goneChats": sorted(self.gone)}


def kept_here(cache_root, host=""):
    """(chat ids, plan slugs) that stay on host ("": this computer), as kept
    on this computer: starred, keeping going, a queued go-on or plan."""
    stars = cs.starred_of(cs.load_stars(cache_root), host)
    chats, plans = set(stars["chats"]), set(stars["plans"])
    chats |= {k["chat"] for k in cs.load_keep(cache_root)["chats"] if k["host"] == host}
    for t in cs.load_queue(cache_root):
        if (t.get("host") or "") != host:
            continue
        if cs.valid_id(t.get("chat") or ""):
            chats.add(t["chat"])
        if isinstance(t.get("plan"), str) and cs.PLAN_SLUG.match(t["plan"]):
            plans.add(t["plan"])
    return chats, plans


def running(profiles):
    """(the chat ids of the sessions running now, the background jobs whose
    worker runs), from their processes (Claude's sessions/ and its service's
    roster.json)."""
    chats, jobs = set(), set()
    for entry, _p, _h in cs.live_entries_all(profiles):
        if cs.valid_id(entry.get("sessionId") or ""):
            chats.add(entry["sessionId"])
        if isinstance(entry.get("jobId"), str):
            jobs.add(entry["jobId"])
    for p in profiles:
        roster = cs.read_json(p.path / "daemon" / "roster.json")
        workers = roster.get("workers") if isinstance(roster, dict) else None
        for job, w in (workers.items() if isinstance(workers, dict) else ()):
            if isinstance(w, dict) and isinstance(w.get("pid"), int) and cs.pid_alive(w["pid"]):
                jobs.add(job)
    return chats, jobs


def lead_id(name):
    m = LEAD_ID.match(name)
    return m.group(1).lower() if m else None


def from_desktop(path):
    """Does Claude Desktop keep this chat (its entrypoint, at its start)?"""
    try:
        with open(path, "rb") as f:
            return DESKTOP.search(f.read(HEAD_BYTES)) is not None
    except OSError:
        return True  # (unread: it stays)


def size_of(path):
    """Bytes of a file, or of a folder and what's in it (links not followed)."""
    try:
        st = os.lstat(path)
    except OSError:
        return 0
    if not stat.S_ISDIR(st.st_mode):
        return st.st_size
    total, stack = 0, [path]
    while stack:
        try:
            with os.scandir(stack.pop()) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                        else:
                            total += e.stat(follow_symlinks=False).st_size
                    except OSError:
                        pass
        except OSError:
            pass
    return total


def remove(path):
    """Delete a file, a link (never what it points to) or a folder; True when it went."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return False
    if stat.S_ISDIR(st.st_mode):
        shutil.rmtree(path)
    else:
        os.unlink(path)
    return True


def entries(folder):
    """A folder's entries (none when it isn't one, or is a link: Claude
    doesn't sweep through one either)."""
    try:
        if os.path.islink(folder):
            return []
        with os.scandir(folder) as it:
            return list(it)
    except OSError:
        return []


def mtime_of(e):
    try:
        return e.stat(follow_symlinks=False).st_mtime
    except OSError:
        return None


# ---------------------------------------------------------------- one computer's cleanup

def sweep(home, cache_root, profiles, days, keep_chats, keep_plans, now, dry=False):
    """Delete (dry: count) what Claude Code's cleanup would at days, but what
    stays (keep_chats, keep_plans: kept_here; and the module's list): a Tally.
    The accounts you hid (accounts.py --hide) are left as they are."""
    t = Tally()
    cutoff = now - days * 86400
    live_chats, live_jobs = running(profiles)  # (of every account: a chat shared with a hidden one stays too)
    profiles = cs.shown_profiles(profiles, cache_root)
    keep = set(keep_chats) | live_chats
    roots, seen = [], set()
    for p in profiles:
        real = str(p.real)
        if real not in seen and cs.is_dir(Path(real)):
            seen.add(real)
            roots.append(real)
    gone, stays = {}, set()  # chat id -> its project folder's name; the chats that stay
    for root in roots:
        sweep_chats(root, cutoff, keep, gone, stays, t, dry)
    sweep_shared(home, cutoff, keep, gone, stays, t, dry)
    for root in roots:
        sweep_jobs(root, cutoff, keep | stays, live_jobs, t, dry)  # (a background chat's folder stays with its chat)
        sweep_aged(root, cutoff, keep | stays, gone, t, dry)
    noted = cs.load_plan_projects(cache_root)  # (the chat that made each plan, as the status noted it)
    living = keep | stays  # (a plan stays while its chat does)
    plans = set(keep_plans) | {slug for slug, e in noted.items() if e.get("chat") in living}
    sweep_plans(home, roots, cutoff, plans, t, dry)
    if not dry:
        t.gone = [c for c in gone if c not in stays]   # (one an account still has stays, with its bookmarks)
    return t


def sweep_chats(root, cutoff, keep, gone, stays, t, dry):
    """An account's chats (projects/<project>/<id>.jsonl), with what's beside them."""
    for d in entries(os.path.join(root, "projects")):
        if not d.is_dir(follow_symlinks=False):
            continue
        listed = entries(d.path)
        names = {e.name for e in listed}
        went = False
        for e in listed:
            if e.name.endswith(".jsonl") and e.is_file(follow_symlinks=False):
                chat = e.name[:-6]
                if not CHAT_ID.match(chat):
                    continue
                when = mtime_of(e)
                if when is None or when >= cutoff or chat in keep or from_desktop(e.path):
                    stays.add(chat)
                    if when is not None and when < cutoff and chat in keep:
                        t.kept_chats += 1  # (old: it stays because it's starred, open, queued or keeps going)
                    continue
                parts = [e.path] + [os.path.join(d.path, chat + c) for c in COMPANIONS] + [os.path.join(d.path, chat)]
                size = sum(size_of(x) for x in parts)
                try:
                    if not dry:
                        for x in parts:
                            remove(x)
                    gone[chat] = d.name
                    went = True
                    t.chats += 1
                    t.bytes += size
                except OSError as exc:
                    t.error(f"chat {chat[:8]}: {exc.strerror or exc}")
            elif e.is_dir(follow_symlinks=False) and CHAT_ID.match(e.name) and e.name + ".jsonl" not in names:
                # (a chat's folder without its transcript: Claude's sweep goes by the folder's own date;
                # never memory/ nor any other folder that isn't named after a chat)
                when = mtime_of(e)
                if when is None or when >= cutoff or e.name in keep:
                    continue
                size = size_of(e.path)
                try:
                    if not dry:
                        remove(e.path)
                    t.files += 1
                    t.bytes += size
                except OSError as exc:
                    t.error(f"{e.name[:8]}: {exc.strerror or exc}")
        if not dry and went:
            try:
                os.rmdir(d.path)  # (a project folder this left empty: as Claude does)
            except OSError:
                pass


def sweep_shared(home, cutoff, keep, gone, stays, t, dry):
    """A chat shared between accounts (sharing.py) keeps its transcript's
    one more link and its folders in a store: they go with the chat, or once
    every account's copy is gone and they're old."""
    import sharing  # (on an SSH host it's loaded before this file)
    for d in entries(str(sharing.store_root(Path(home)))):
        if not d.is_dir(follow_symlinks=False):
            continue
        for e in entries(d.path):
            if not (e.name.endswith(".jsonl") and e.is_file(follow_symlinks=False)):
                continue
            chat = e.name[:-6]
            if not CHAT_ID.match(chat) or chat in keep or chat in stays:
                continue
            try:
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            if st.st_nlink > 1 or (chat not in gone and st.st_mtime >= cutoff):
                continue  # (an account still has it, or it's recent)
            parts = [e.path, os.path.join(d.path, chat), os.path.join(d.path, chat + ".file-history")]
            size = sum(size_of(x) for x in parts) if chat not in gone else 0  # (counted with its chat)
            try:
                if not dry:
                    for x in parts:
                        remove(x)
                if chat not in gone:
                    t.files += 1
                    t.bytes += size
            except OSError as exc:
                t.error(f"shared chat {chat[:8]}: {exc.strerror or exc}")


def sweep_jobs(root, cutoff, keep, live_jobs, t, dry):
    """Background chats' folders (jobs/<id>): one that finished, old, whose
    worker doesn't run and whose chat doesn't stay (Claude's rules)."""
    for e in entries(os.path.join(root, "jobs")):
        if not e.is_dir(follow_symlinks=False) or e.name in live_jobs:
            continue
        state = os.path.join(e.path, "state.json")
        try:  # (Claude's service may replace or remove it meanwhile: that job is looked at next time)
            when = max(mtime_of(e) or 0, os.stat(state).st_mtime)
        except OSError:
            continue
        if when >= cutoff:
            continue
        job = cs.read_json(Path(state))
        # (a routine, a self-waking or /loop job is "done" between its runs: it's never deleted, as Claude's isn't)
        if not isinstance(job, dict) or not cs.job_finished(job) or cs.is_recurring(job) or job.get("sessionId") in keep:
            continue
        size = size_of(e.path)
        try:
            if not dry:
                remove(e.path)
            t.jobs += 1
            t.bytes += size
        except OSError as exc:
            t.error(f"background chat {e.name}: {exc.strerror or exc}")


def sweep_aged(root, cutoff, stays, gone, t, dry):
    """The other folders Claude's cleanup empties (AGED): what's named after
    a chat goes with it and stays with it; the rest by its own date."""
    for name, folders in AGED:
        for e in entries(os.path.join(root, name)):
            if name == "debug" and e.name == "latest":
                continue
            chat = lead_id(e.name)
            if e.is_symlink():  # (a shared chat's undo history in the store: its link goes with the chat)
                if chat in gone and not dry:
                    try:
                        os.unlink(e.path)
                    except OSError:
                        pass
                continue
            if (e.is_dir(follow_symlinks=False) if folders else e.is_file(follow_symlinks=False)) is not True:
                continue
            if chat is not None and chat in stays:
                continue
            if chat not in gone:
                when = mtime_of(e)
                if when is None or when >= cutoff:
                    continue
            size = size_of(e.path)
            try:
                if not dry:
                    remove(e.path)
                t.files += 1
                t.bytes += size
            except OSError as exc:
                t.error(f"{name}/{e.name[:20]}: {exc.strerror or exc}")


def sweep_plans(home, roots, cutoff, keep, t, dry):
    """The accounts' own plans (plans/*.md) to the Trash, once each (a plan
    shared between accounts is one file, linked: the other links go)."""
    by_file, seen = {}, set()
    for root in roots:
        folder = os.path.join(root, "plans")
        real = os.path.realpath(folder)
        if real in seen:
            continue
        seen.add(real)
        for e in entries(real):
            if not e.is_file(follow_symlinks=False):
                continue
            when = mtime_of(e)
            if when is None or when >= cutoff:
                continue
            if ".md.tmp." in e.name:  # (one Claude left half written)
                try:
                    if not dry:
                        os.unlink(e.path)
                except OSError:
                    pass
                continue
            slug = e.name[:-3] if e.name.endswith(".md") else ""
            if not cs.PLAN_SLUG.match(slug):
                continue
            if slug in keep:
                t.kept_plans += 1  # (old: it stays because it's starred, queued or its chat stays)
                continue
            try:
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            by_file.setdefault((st.st_dev, st.st_ino), []).append(Path(e.path))
    for paths in by_file.values():
        if dry:
            t.plans += 1
            continue
        import accounts  # (the Trash: on an SSH host it's loaded before this file)
        why = accounts.trash_problem(paths[0], home)
        if why:
            t.error(f"plan {paths[0].stem}: {why}")
            continue
        try:
            accounts.move_to_trash(paths[0], home)
            for other in paths[1:]:
                os.unlink(str(other))
            t.plans += 1
        except (OSError, ValueError, accounts.subprocess.SubprocessError) as exc:
            t.error(f"plan {paths[0].stem}: {exc}")


def place(home, cache_root, profiles, mode, days, keep_chats, keep_plans, now, dry=False):
    """One computer's run: Talpy Den's cleanup (mode "talpy": Claude's kept
    from cleaning first), or Claude Code's own put back ("claude")."""
    out = {"ok": True, "at": int(now * 1000), "mode": mode, "days": days, "message": "", "dry": dry}
    if mode == "claude":
        problems, left = ([], bool(load_changed(cache_root))) if dry else let_claude_clean(home, cache_root)
        return dict(out, ok=not problems, raised=left, errors=problems, message="; ".join(problems))
    problems = [] if dry else keep_claude_from_cleaning(home, cache_root, profiles)
    t = sweep(home, cache_root, profiles, days, keep_chats, keep_plans, now, dry)
    for p in problems:
        t.error(p)
    return dict(out, ok=not t.errors, raised=bool(load_changed(cache_root)), overrides=claude_overrides(home, profiles),
                **t.out())


# ---------------------------------------------------------------- the run: here, then the hosts

def load_runs(cache_root):
    data = cs.read_json(Path(cache_root) / RUNS_FILE)
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, dict)} if isinstance(data, dict) else {}


def raised_hosts(cache_root):
    """The SSH hosts and containers where Talpy Den kept Claude's cleanup
    from cleaning (or may have: one is noted before it's asked), in the
    state folder: a cache cleared mustn't leave one so for good."""
    data = cs.read_json(cs.state_dir(cache_root) / HOSTS_FILE)
    hosts = data.get("hosts") if isinstance(data, dict) else None
    return {h for h in hosts if isinstance(h, str) and h} if isinstance(hosts, list) else set()


def save_raised_hosts(cache_root, hosts):
    cs.private_dir(cs.state_dir(cache_root))
    cs.write_json_atomic(cs.state_dir(cache_root) / HOSTS_FILE, {"hosts": sorted(hosts)}, private=True)


def hosts_to_visit(cache_root, mode, now):
    """The SSH hosts and containers a run goes to: those that answered a
    check in the last day (Talpy Den's cleanup), and those Talpy Den kept
    Claude's from cleaning on (Claude's: to put it back)."""
    import remote
    if mode != "talpy":
        return sorted(h for h in raised_hosts(cache_root) if remote.HOST_NAME.match(h))
    hosts = []
    for f in entries(os.path.join(str(cache_root), remote.ANSWERS_DIR)):
        host = f.name[:-5] if f.name.endswith(".json") else ""
        when = mtime_of(f)
        if host and remote.HOST_NAME.match(host) and when is not None and now - when < HOST_FRESH_S:
            hosts.append(host)
    return sorted(hosts)


def on_host(host, cache_root, mode, days, dry=False):
    """A host's run, over ssh (its starred chats and plans are kept here)."""
    import remote
    chats, plans = kept_here(cache_root, host)
    args = ["--place", "claude" if mode == "claude" else str(days)]
    if chats:
        args += ["--keep-chats", ",".join(sorted(chats))]
    if plans:
        args += ["--keep-plans", ",".join(sorted(plans))]
    if dry:
        args.append("--dry-run")
    return remote.host_answer(host, args, name="cleanup.py", also=HOST_MODULES, timeout=HOST_TIMEOUT)


def forget_bookmarks(cache_root, chats, host=""):
    """The bookmarks of the chats a run deleted (here, or on host: kept here) go too, as a deleted chat's do,
    and when a Talpy Chat window last showed them (talpy_den.forget_seen)."""
    chats = [c for c in chats if isinstance(c, str) and cs.valid_id(c)] if isinstance(chats, list) else []
    for chat in chats:
        cs.forget_bookmarks(cache_root, chat, host)
    cs.forget_seen(cache_root, chats, host)


def run(home, cache_root, extra_dirs=(), now=None, wait=False):
    """The run (one at a time: another that's running says so, unless wait):
    this computer, then the hosts; again when the setting changed meanwhile."""
    cs.private_dir(Path(cache_root))
    with open(str(Path(cache_root) / LOCK_FILE), "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
        except OSError:
            return {"ok": False, "message": "A cleanup is running already"}
        for _again in range(3):
            setting = load_setting(cache_root)
            at = now if now is not None else time.time()
            runs = load_runs(cache_root)
            profiles = cs.discover_profiles(home, extra_dirs)
            chats, plans = kept_here(cache_root)
            try:
                runs[""] = place(home, cache_root, profiles, setting["mode"], setting["days"], chats, plans, at)
                forget_bookmarks(cache_root, runs[""].pop("goneChats", None))
            except Exception as exc:  # (written down: the settings say why)
                runs[""] = {"ok": False, "at": int(at * 1000), "message": f"{type(exc).__name__}: {exc}",
                            "raised": bool(load_changed(cache_root))}
            raised = raised_hosts(cache_root)
            for host in hosts_to_visit(cache_root, setting["mode"], at):
                before = runs.get(host) or {}
                if setting["mode"] == "talpy" and host not in raised:
                    raised.add(host)  # (noted first: an answer lost on its way still gets it put back)
                    save_raised_hosts(cache_root, raised)
                answer = on_host(host, cache_root, setting["mode"], setting["days"])
                if isinstance(answer.get("raised"), bool):  # (it got there and says how Claude's stands)
                    (raised.add if answer["raised"] else raised.discard)(host)
                    save_raised_hosts(cache_root, raised)
                forget_bookmarks(cache_root, answer.pop("goneChats", None), host)
                if answer.get("ok") or "raised" in answer:
                    runs[host] = {k: v for k, v in answer.items() if k != "reached"}
                else:  # (not reached, or it failed there: what it did before stays known)
                    runs[host] = dict(before, ok=False, at=int(at * 1000), message=answer.get("message") or "no answer")
            cs.write_json_atomic(Path(cache_root) / RUNS_FILE, runs)
            if setting["mode"] == "claude" and setting["pending"] and not raised and not load_changed(cache_root):
                change_setting(cache_root, lambda s: s.update(pending=False) if s["at"] == setting["at"] else False,
                               chosen=False)
            if load_setting(cache_root)["at"] == setting["at"]:
                break
        return {"ok": all(r.get("ok") for r in runs.values()), "message": "", "runs": runs}


def set_mode(home, cache_root, extra_dirs, mode, days=None, start=True):
    """Choose who cleans: Claude's own cleanup is kept from cleaning (or put
    back) here at once, the rest in the background run."""
    if mode not in MODES:
        return {"ok": False, "message": f"Claude or Talpy Den, not {mode}"}
    if days is not None and not (isinstance(days, int) and 1 <= days <= MAX_DAYS):
        return {"ok": False, "message": f"Between 1 and {MAX_DAYS} days"}

    def change(s):
        s["mode"] = mode
        if days is not None:
            s["days"] = days
        s["pending"] = mode == "claude"
    s = change_setting(cache_root, change)
    profiles = cs.discover_profiles(home, extra_dirs)
    problems = keep_claude_from_cleaning(home, cache_root, profiles) if mode == "talpy" else let_claude_clean(home, cache_root)[0]
    if start:
        cs.start_cleanup(cache_root, extra_dirs)
    if mode == "talpy":
        message = ("Talpy Den cleans up from now on: chats you haven't used for %d days, and old plans to the Trash; "
                   "the starred ones stay" % s["days"])
    else:
        message = "Claude Code cleans up again, as before"
    return {"ok": not problems, "message": "; ".join(problems) if problems else message, "mode": s["mode"], "days": s["days"]}


def status(home, cache_root, extra_dirs=(), now=None, days=None):
    """The setting, the last runs, Claude Code's own setting on each account,
    and what a run would delete here now at the days set, or days ("preview",
    "previewDays"; nothing is deleted)."""
    now = now if now is not None else time.time()
    setting = load_setting(cache_root)
    profiles = cs.discover_profiles(home, extra_dirs)
    chats, plans = kept_here(cache_root)
    days = days if days is not None else setting["days"]
    preview = sweep(home, cache_root, profiles, days, chats, plans, now, dry=True).out()
    risk = None  # (Talpy Den's: what Claude Code's own cleanup would delete of what it keeps, if chosen again)
    if setting["mode"] == "talpy":
        back = claude_days_back(cache_root)
        at = preview if back == days else sweep(home, cache_root, profiles, back, chats, plans, now, dry=True).out()
        risk = {"days": back, "chats": at["keptChats"], "plans": at["keptPlans"]}
    try:
        ran = os.stat(str(Path(cache_root) / cs.CLEANUP_STAMP)).st_mtime
    except OSError:
        ran = None
    return {"ok": True, "mode": setting["mode"], "days": setting["days"], "defaultDays": DEFAULT_DAYS,
            "maxDays": MAX_DAYS, "pending": setting["pending"], "claudeDays": claude_days(home, profiles),
            "runs": load_runs(cache_root), "checkedAt": int(ran * 1000) if ran else None, "preview": preview,
            "previewDays": days, "claudeRisk": risk, "overrides": claude_overrides(home, profiles)}


def claude_days_back(cache_root):
    """The days Claude Code's own cleanup keeps once it's put back: the
    fewest of what the accounts said before (30 where they said nothing)."""
    days = [was.get("value") if was.get("had") and isinstance(was.get("value"), int) and was.get("value") >= 1
            else DEFAULT_DAYS for was in load_changed(cache_root).values()]
    return min(days) if days else DEFAULT_DAYS


def ids(text, check):
    return {i for i in text.split(",") if i and check(i)}


def main(argv=None):
    args = sys.argv[1:] if argv is None else list(argv)
    config_dirs, action, value, days, keep_chats, keep_plans = [], None, None, None, set(), set()
    dry, remote_run = False, False
    usage = USAGE
    while args:
        arg = args.pop(0)
        if arg == "--config-dir" and args:
            config_dirs.append(args.pop(0))
        elif arg.startswith("--config-dir="):
            config_dirs.append(arg.partition("=")[2])
        elif arg in ("--status", "--setting", "--run", "--uninstall"):
            action = arg
        elif arg == "--days" and args and args[0].isdigit() and 1 <= int(args[0]) <= MAX_DAYS:
            days = int(args.pop(0))
        elif arg in ("--set", "--place") and args:
            action, value = arg, args.pop(0)
            if arg == "--set" and value == "talpy" and args and args[0].isdigit():
                days = int(args.pop(0))
        elif arg == "--keep-chats" and args:
            keep_chats = ids(args.pop(0), cs.valid_id)
        elif arg == "--keep-plans" and args:
            keep_plans = ids(args.pop(0), lambda s: bool(cs.PLAN_SLUG.match(s)))
        elif arg == "--dry-run":
            dry = True
        elif arg == "--remote":
            remote_run = True
        else:
            sys.exit(usage)
    if action is None:
        sys.exit(usage)
    os.umask(0o077)
    home = Path.home()
    cache_root = cs.cache_dir(home)
    try:
        if action == "--status":
            result = status(home, cache_root, config_dirs, days=days)
        elif action == "--setting":  # (only the choice: no run, dry or not)
            s = load_setting(cache_root)
            result = {"ok": True, "mode": s["mode"], "days": s["days"], "pending": s["pending"], "maxDays": MAX_DAYS}
        elif action == "--set":
            result = set_mode(home, cache_root, config_dirs, value, days)
        elif action == "--run":
            result = run(home, cache_root, config_dirs)
        elif action == "--uninstall":
            before = load_setting(cache_root)
            if not os.path.exists(str(setting_path(cache_root))) or (before["mode"] == "claude" and not before["pending"]):
                result = {"ok": True, "message": ""}  # (Claude Code's own cleanup: nothing to put back)
            else:
                set_mode(home, cache_root, config_dirs, "claude", start=False)
                result = run(home, cache_root, config_dirs, wait=True)
                left = (["this computer"] if load_changed(cache_root) else []) + sorted(raised_hosts(cache_root))
                result["message"] = ("Claude Code cleans up old chats again" if not left else
                                     "Claude Code cleans up old chats again, but not yet on " + ", ".join(left)
                                     + ": choose its cleanup in Talpy Den's settings there, or set cleanupPeriodDays back yourself")
        else:
            if value != "claude" and not (value.isdigit() and 1 <= int(value) <= MAX_DAYS):
                sys.exit(usage)
            mode, n = ("claude", DEFAULT_DAYS) if value == "claude" else ("talpy", int(value))
            result = place(home, cache_root, cs.discover_profiles(home, config_dirs), mode, n, keep_chats, keep_plans,
                           time.time(), dry)
    except Exception as exc:  # (the front ends and the computer that asks must get an answer)
        result = {"ok": False, "message": f"{type(exc).__name__}: {exc}"}
    text = json.dumps(result)
    if remote_run:
        sys.stdout.write("\n" + cs.REMOTE_MARK + " ")
    sys.stdout.write(text + "\n")


if __name__ == "__main__":
    main()
