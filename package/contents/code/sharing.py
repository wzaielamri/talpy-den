#!/usr/bin/env python3
"""Share a Claude Code chat between your Claude profiles, so another account
can continue it (jump.py's --share, --continue and --unshare).

A shared chat is one transcript file hard-linked into each profile's
projects/<project>/ folder: every profile lists it with its own chats, and
whichever account continues it writes to that same file. The chat's two
folders (projects/<project>/<id>/: subagents and tool results;
file-history/<id>/: undo checkpoints) move to a store, and each profile gets
a symlink to them, so Claude cleaning up one profile never takes them from
the others:

    ~/.local/share/claude-status/shared-chats/<project>/   ($XDG_DATA_HOME)
        <id>.jsonl           one more link to the transcript
        <id>/                the chat's folder
        <id>.file-history/   its undo checkpoints

A chat shared this way by another tool, into a store of its own, is found
through the profiles' links and handled where it is. talpy_den.py tells
shared chats apart by the transcript's inode, whoever shared them.

A chat can be open in only one Claude session at a time (two would write the
same file): a chat a session has open isn't shared or unshared.
Nothing here starts Claude or sends anything anywhere.

On an SSH host, remote.py runs this file's main() (python3 -I - with
talpy_den.py loaded first, remote.host_script), for the host's own
profiles:

    --share CHAT_ID [--profile PROFILE]   share it with every profile (from PROFILE's copy)
    --continue CHAT_ID --profile PROFILE  share it with PROFILE if needed; the command reopening it there
    --unshare CHAT_ID --profile PROFILE   keep it only on PROFILE
    --delete-chat CHAT_ID | --delete-plan SLUG [--profile PROFILE] | --delete-memory KEY [--describe]
                                          to the Trash (--describe: the question to ask first),
                                          with accounts.py loaded too (remote.delete)
    --move-plan SLUG [--profile PROFILE] [--into FOLDER | --back] [--no-setting] [--if-exists keep|replace]
                [--describe]              a plan into its project's plans folder, or back (move_plan)
    [--config-dir DIR]... [--remote]      extra Claude config dirs; the JSON after a marker line
"""

import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

import talpy_den as cs

# Claude's projects/<project> folder: the project's path with every other character as "-"
PROJECT_KEY = re.compile(r"^[A-Za-z0-9._-]+$")
TRANSCRIPT, FOLDER, CHECKPOINTS = "transcript", "folder", "checkpoints"
PARTS = (TRANSCRIPT, FOLDER, CHECKPOINTS)
FOLDERS = (FOLDER, CHECKPOINTS)


def store_root(home):
    data = os.environ.get("XDG_DATA_HOME", "")
    base = Path(data) if os.path.isabs(data) else home / ".local/share"
    # (the folder keeps its first name: each shared chat's profile links point into it)
    return base / "claude-status" / "shared-chats"


def in_profile(profile, key, chat_id, part):
    """Where a part of the chat is in a profile (its real folder)."""
    if part == TRANSCRIPT:
        return profile.real / "projects" / key / f"{chat_id}.jsonl"
    if part == FOLDER:
        return profile.real / "projects" / key / chat_id
    return profile.real / "file-history" / chat_id


def in_store(folder, chat_id, part):
    """Where a part of the chat is in a store folder (<store>/<project>)."""
    return folder / {TRANSCRIPT: f"{chat_id}.jsonl", FOLDER: chat_id, CHECKPOINTS: f"{chat_id}.file-history"}[part]


def same(a, b):
    try:
        return os.path.samefile(str(a), str(b))
    except OSError:
        return False


def present(path):
    return path.exists() or path.is_symlink()


def target(link):
    """What a symlink points to, resolved (also when it's gone)."""
    return Path(os.path.realpath(str(link)))


def inside(path, folder):
    try:
        return os.path.commonpath([str(path), str(folder)]) == str(folder)
    except ValueError:
        return False


def links(path):
    try:
        return os.stat(str(path)).st_nlink
    except OSError:
        return 0


def entry(path):
    """The directory entry a path names, through linked folders: two profiles
    whose projects/ is one folder (a symlink, or a bind mount, which no path
    shows: hence its folder's device and inode) reach the same entry, which is
    one copy of the chat, not two."""
    real = os.path.realpath(str(path))
    try:
        folder = os.stat(os.path.dirname(real))
    except OSError:
        return real
    return folder.st_dev, folder.st_ino, os.path.basename(real)


def merge_into(src, dst):
    """Move what's in the folder src into the folder dst (whatever dst
    doesn't have yet), then remove src if that emptied it."""
    for child in list(src.iterdir()):
        there = dst / child.name
        if not present(there):
            shutil.move(str(child), str(there))
        elif child.is_dir() and not child.is_symlink() and there.is_dir():
            merge_into(child, there)
    try:
        src.rmdir()
    except OSError:
        pass  # something both had: left where it was


def copies(profiles, chat_id):
    """The profiles that have this chat, grouped by file: [[(profile, transcript)]],
    the file most profiles link to first (then the newest)."""
    groups = []
    for p in profiles:
        path = cs.transcript_path(p, chat_id)
        if path is None or path.is_symlink() or not path.is_file():
            continue
        for g in groups:
            if same(g[0][1], path):
                g.append((p, path))
                break
        else:
            groups.append([(p, path)])
    groups.sort(key=lambda g: (-len(g), -(cs.mtime(g[0][1]) or 0)))
    return groups


def store_paths(sharers, key, chat_id, root):
    """{part: where it is in the store}. A chat shared before keeps its folders
    where the profiles' symlinks point (maybe another tool's store); the rest
    goes to <root>/<project>."""
    ours = root / key
    paths = {part: in_store(ours, chat_id, part) for part in PARTS}
    for part in FOLDERS:
        link = next((in_profile(p, key, chat_id, part) for p in sharers
                     if in_profile(p, key, chat_id, part).is_symlink()), None)
        if link is not None:
            paths[part] = target(link)
    # that store's own link to the transcript sits next to the chat's folder
    beside = paths[FOLDER].parent / f"{chat_id}.jsonl"
    if paths[FOLDER].parent != ours and beside.is_file() and same(beside, in_profile(sharers[0], key, chat_id, TRANSCRIPT)):
        paths[TRANSCRIPT] = beside
    return paths


def device(path):
    """The filesystem (st_dev) a path is on, or would be on: that of its
    nearest folder that exists."""
    for p in (path, *path.parents):
        try:
            return os.stat(str(p)).st_dev
        except OSError:
            continue
    return None


def elsewhere(path, places):
    """Labels of the places (label, path) on another filesystem than path:
    hard links can't cross filesystems (another disk, partition or btrfs
    subvolume)."""
    here = device(path)
    return [label for label, p in places if device(p) != here]


def link_into(link, stored):
    """A profile's hard link to the transcript, or symlink to a folder."""
    link.parent.mkdir(parents=True, exist_ok=True)
    if stored.is_dir():
        os.symlink(str(stored), str(link))
    else:
        os.link(str(stored), str(link))


def share(profiles, chat_id, into, root, source=None):
    """Share a chat into the profiles `into`: from `source`'s copy, else the one
    most profiles have. (ok, message)."""
    groups = copies(profiles, chat_id)
    if not groups:
        return False, "That chat has no transcript on this computer"
    chat = next((g for g in groups if source is not None and any(p.real == source.real for p, _ in g)), None)
    if chat is None:
        if len(groups) > 1 and len(groups[1]) == len(groups[0]):
            names = ", ".join(p.label for g in groups for p, _ in g)
            return False, f"Different chats have this id on {names}; left everything as it is"
        chat = groups[0]
    path = chat[0][1]
    key = path.parent.name
    if not PROJECT_KEY.match(key) or key in (".", ".."):
        return False, f"Unexpected project folder {key}; left the chat as it is"
    sharers = [p for p, _ in chat]
    have = {p.real for p in sharers}
    store = store_paths(sharers, key, chat_id, root)
    # Checked first, so nothing is left half-done
    apart = elsewhere(path, [("the shared-chat folder", store[TRANSCRIPT])] +
                      [(q.label, in_profile(q, key, chat_id, TRANSCRIPT)) for q in into if q.real not in have])
    if apart:
        return False, (f"Can't share it: {', '.join(apart)} {'is' if len(apart) == 1 else 'are'} on another disk or "
                       f"partition than this chat, and a shared chat is one file linked into each account. "
                       f"Keep the Claude folders and {store[TRANSCRIPT].parent.parent} on one filesystem")
    if present(store[TRANSCRIPT]) and not same(store[TRANSCRIPT], path):
        return False, f"{store[TRANSCRIPT]} is a different chat with the same id; left everything as it is"
    for part in FOLDERS:  # also checked before anything changes
        there = store[part]
        heres = [in_profile(p, key, chat_id, part) for p in sharers]
        linked = any(here.is_symlink() and target(here) == there for here in heres)
        stray = there.is_dir() and any(there.iterdir()) or present(there) and not there.is_dir()
        if not linked and stray and any(here.is_dir() and not here.is_symlink() for here in heres):
            return False, f"{there} is already there; left the chat as it is"
    old_umask = os.umask(0o077)  # the store holds chats: only you can read it
    try:
        if not present(store[TRANSCRIPT]):
            store[TRANSCRIPT].parent.mkdir(parents=True, exist_ok=True)
            os.link(str(path), str(store[TRANSCRIPT]))
        # The chat's folders move to the store (the ones Claude makes later are
        # made there now), and the profiles that have it link to them.
        for part in FOLDERS:
            there = store[part]
            linked = any(here.is_symlink() and target(here) == there
                         for here in (in_profile(p, key, chat_id, part) for p in sharers))
            for p in sharers:
                here = in_profile(p, key, chat_id, part)
                if here.is_symlink():
                    if target(here) == there and not there.exists():
                        there.mkdir(parents=True)  # its store folder went missing
                elif here.is_dir():
                    if not linked and there.is_dir() and not any(there.iterdir()):
                        there.rmdir()  # left over, empty
                    if not present(there):
                        there.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(here), str(there))
                        os.symlink(str(there), str(here))
                        linked = True
                    # else: this profile keeps a folder of its own
                elif not present(here):
                    there.mkdir(parents=True, exist_ok=True)
                    link_into(here, there)
                    linked = True
        added, skipped = [], []
        for q in into:
            if q.real in have:
                continue
            plan = [(in_profile(q, key, chat_id, part), path if part == TRANSCRIPT else store[part]) for part in PARTS]
            if any(present(link) and not same(link, stored) for link, stored in plan):
                skipped.append(q.label)  # a chat of its own with this id
                continue
            for link, stored in plan:
                if not present(link):
                    link_into(link, stored)
            have.add(q.real)
            added.append(q.label)
    except OSError as exc:
        return False, f"Couldn't share the chat: {exc}"
    finally:
        os.umask(old_umask)
    on = [p.label for p in profiles if p.real in have]
    if added:
        message = f"Chat shared: it's now on {', '.join(on)}."
    elif skipped:
        return False, f"Not shared: {', '.join(skipped)} already has a different chat with the same id"
    else:
        message = f"This chat is already shared with {', '.join(on)}."
    if skipped:
        message += f" Not added to {', '.join(skipped)}: it has a different chat with the same id."
    return True, message


def keep_only(profiles, chat_id, keep, root):
    """Make a shared chat a normal chat of `keep` again: it keeps the
    transcript and gets the chat's folders back; the other profiles lose it.
    (ok, message)."""
    groups = copies(profiles, chat_id)
    mine = next((g for g in groups if any(p.real == keep.real for p, _ in g)), None)
    if mine is None and len(groups) > 1:
        return False, f"Several profiles have different chats with this id; {keep.label} has none of them"
    chat = mine or (groups[0] if groups else None)
    if chat is None:
        return False, "That chat has no transcript on this computer"
    path = chat[0][1]
    key = path.parent.name
    if not PROJECT_KEY.match(key) or key in (".", ".."):
        return False, f"Unexpected project folder {key}; left the chat as it is"
    sharers = sorted((p for p, _ in chat), key=lambda p: p.real != keep.real)  # keep's own links first
    entries = {entry(t) for _, t in chat}
    shared = len(entries) > 1 or links(path) > 1 or any(
        in_profile(p, key, chat_id, part).is_symlink() for p in sharers for part in FOLDERS)
    if not shared:
        if any(len({entry(t) for _, t in g}) > 1 for g in groups):
            return False, f"{keep.label} has its own, different copy of this chat; left everything as it is"
        return False, "This chat isn't shared"
    kept = in_profile(keep, key, chat_id, TRANSCRIPT)
    if not present(kept) and elsewhere(path, [(keep.label, kept)]):
        return False, (f"Can't keep it only on {keep.label}: its folder is on another disk or partition than this "
                       f"chat, and the chat would have to be copied there. Left everything as it is")
    store = store_paths(sharers, key, chat_id, root)
    own_dirs = [p.real for p in profiles]
    moved = {}  # part: where its folder was
    removed = []
    old_umask = os.umask(0o077)
    try:
        # keep gets the chat's folders back
        for part in FOLDERS:
            here = in_profile(keep, key, chat_id, part)
            if here.is_symlink():
                was = target(here)
                os.unlink(str(here))
                if was.is_dir():
                    shutil.move(str(was), str(here))
                moved[part] = was
            elif not present(here) and store[part].is_dir():
                here.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(store[part]), str(here))
                moved[part] = store[part]
            elif here.is_dir() and store[part].is_dir() and entry(store[part]) != entry(here):
                # A folder of its own stays; what the others kept in the store
                # (their subagents, checkpoints of this chat) joins it
                merge_into(store[part], here)
                moved[part] = store[part]
        if not present(kept):
            link_into(kept, path)
        # the others lose it (not keep's own entry, seen through a linked folder)
        for q in profiles:
            if q.real == keep.real:
                continue
            gone = False
            t = in_profile(q, key, chat_id, TRANSCRIPT)
            if not t.is_symlink() and t.is_file() and same(t, kept) and entry(t) != entry(kept):
                os.unlink(str(t))
                gone = True
            for part in FOLDERS:
                link = in_profile(q, key, chat_id, part)
                if link.is_symlink() and target(link) in (moved.get(part), store[part]):
                    os.unlink(str(link))
                    gone = True
            if gone:
                removed.append(q.label)
        # and so does the store
        stored = store[TRANSCRIPT]
        if (entry(stored) != entry(kept) and not any(inside(stored, d) for d in own_dirs) and stored.is_file()
                and same(stored, kept)):
            os.unlink(str(stored))
        for folder in {stored.parent, *(m.parent for m in moved.values())}:
            if not any(inside(folder, d) for d in own_dirs):
                try:
                    folder.rmdir()  # only if it's empty now
                except OSError:
                    pass
    except OSError as exc:
        return False, f"Couldn't finish unsharing the chat: {exc}"
    finally:
        os.umask(old_umask)
    message = f"This chat is now a normal chat of {keep.label} again."
    if removed:
        message += f" Removed from {', '.join(removed)}."
    return True, message


# ---------------------------------------------------------------- plans
#
# A plan (<cfg>/plans/<slug>.md, what a chat in plan mode writes) is shared
# the same way: one file hard-linked into each profile's plans/ folder, so a
# chat continued on another account finds its plan there, and a change shows
# on every account (Claude writes plans in place). Sharing a chat shares its
# plan too.


def plan_copies(profiles, slug):
    """[(profile, path)] of the profiles that have the plan called slug."""
    out = []
    for p in profiles:
        path = cs.plan_path(p, slug)
        if path is not None and path.is_file() and not path.is_symlink():
            out.append((p, path))
    return out


def share_plan(profiles, slug, into, source=None):
    """Link the plan called slug into the profiles `into`, from source's copy
    (else the newest one): (ok, message)."""
    have = plan_copies(profiles, slug)
    if not have:
        return False, "That plan isn't there any more"
    src = next((path for p, path in have if source is not None and p.real == source.real), None)
    if src is None:
        src = max(have, key=lambda c: cs.mtime(c[1]) or 0)[1]
    added, skipped, apart = [], [], []
    old_umask = os.umask(0o077)
    try:
        for q in into:
            dest = cs.plan_path(q, slug)
            if present(dest):
                if not same(dest, src):
                    skipped.append(q.label)  # a plan of its own with that name
                continue
            if device(dest) != device(src):
                apart.append(q.label)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.link(str(src), str(dest))
            added.append(q.label)
    except OSError as exc:
        return False, f"Couldn't share the plan: {exc}"
    finally:
        os.umask(old_umask)
    on = [p.label for p in profiles if same(cs.plan_path(p, slug), src)]
    if not added and (skipped or apart):
        why = (f"{', '.join(skipped)} already {'has' if len(skipped) == 1 else 'have'} another plan of that name"
               if skipped else f"{', '.join(apart)} {'is' if len(apart) == 1 else 'are'} on another disk or partition")
        return False, f"Not shared: {why}"
    message = f"Plan shared: it's on {', '.join(on)} now." if added else f"This plan is on {', '.join(on)} already."
    if skipped:
        message += f" Not on {', '.join(skipped)}: there's another plan of that name there."
    if apart:
        message += f" Not on {', '.join(apart)}: another disk or partition."
    return True, message


def keep_plan_only(profiles, slug, keep):
    """The plan called slug stays on keep only; the other profiles' links to
    it go (a plan of their own with that name stays): (ok, message)."""
    have = plan_copies(profiles, slug)
    kept = next((path for p, path in have if p.real == keep.real), None)
    if kept is None:
        return False, f"{keep.label} doesn't have this plan"
    removed = []
    try:
        for q, path in have:
            if q.real != keep.real and same(path, kept) and entry(path) != entry(kept):
                os.unlink(str(path))
                removed.append(q.label)
    except OSError as exc:
        return False, f"Couldn't finish: {exc}"
    if not removed:
        return False, "This plan isn't shared"
    return True, f"The plan is only on {keep.label} now. Removed from {', '.join(removed)}."


def share_chat_plan(profiles, chat_id, into):
    """With a chat, its plan (best effort: a chat without one, or a plan
    that can't be linked, just stays as it is)."""
    for p in profiles:
        path = cs.transcript_path(p, chat_id)
        slug = cs.transcript_slug(path, path.stat().st_size) if path is not None and path.is_file() else None
        if slug and cs.plan_path(p, slug).is_file():
            try:
                share_plan(profiles, slug, into, p)
            except OSError:
                pass
            return


# ---------------------------------------------------------------- moving a plan into its project
#
# Move to project (jump.py --move-plan; on an SSH host remote.py runs this
# file there) puts an account's plan into a project's own plans folder: the
# folder the project's plansDirectory names for the plan's account (as
# Claude reads it), else <project>/.claude/plans, under the same name, so
# the chat that made it finds it there by its slug once the project names
# that folder. When it names none, the move can add "plansDirectory":
# ".claude/plans" to the project's .claude/settings.local.json (the one
# Claude reads for it; its other keys stay; .claude/settings.json is never
# touched). Move back puts a plan of a project's folder into an account's
# plans/. Never over another file of that name: keep both (the one that
# moves gets a free name) or replace (the other goes to the Trash). Every
# account's link to it goes with it (a plan in a project's folder is every
# account's); its noted project, the chat that made it and whether it's
# hidden follow it; stars are the asking computer's (jump.py, remote.py).

IF_EXISTS = ("keep", "replace")
MOVE_CHOICES = 40  # the projects offered, newest first


def free_slug(folder, slug):
    """A name for a plan in folder that no file there has: slug-2, slug-3, …"""
    n = 2
    while True:
        name = f"{slug[:120]}-{n}"
        if not os.path.lexists(os.path.join(folder, name + ".md")):
            return name
        n += 1


def git_shows(folder, path):
    """Would path show up in git in folder's repository (not ignored)? None
    when folder isn't in one (or there's no git)."""
    import subprocess
    try:
        r = subprocess.run(["git", "-C", folder, "check-ignore", "-q", "--", path], stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    return {0: False, 1: True}.get(r.returncode)


def add_plans_setting(path):
    """Put "plansDirectory": ".claude/plans" into a project's
    settings.local.json (made if it isn't there), its other keys as they
    were; ValueError when it isn't a JSON object (then it's left as it is)."""
    real = os.path.realpath(path)
    data, there = {}, os.path.isfile(real)
    if there:
        with open(real, encoding="utf-8") as f:
            text = f.read()
        try:
            data = json.loads(text) if text.strip() else {}
        except ValueError:
            data = None
        if not isinstance(data, dict):
            raise ValueError(f"{os.path.basename(path)} isn't a JSON object: left it as it is")
    data[cs.PLANS_SETTING] = cs.PROJECT_PLANS_DIR
    os.makedirs(os.path.dirname(real), exist_ok=True)
    tmp = os.path.join(os.path.dirname(real), f".{os.path.basename(real)}.{os.getpid()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        if there:
            shutil.copymode(real, tmp)
        os.replace(tmp, real)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def place(src, dest):
    """src's file at dest too (dest mustn't be there: FileExistsError), as a
    link, or a copy on another disk."""
    try:
        os.link(str(src), str(dest))
        return
    except FileExistsError:
        raise
    except OSError:
        pass
    tmp = os.path.join(os.path.dirname(str(dest)), f".{os.path.basename(str(dest))}.{os.getpid()}.tmp")
    try:
        shutil.copy2(str(src), tmp)
        os.link(tmp, str(dest))
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def move_ctx(profiles, home):
    root = cs.cache_dir(home)
    return cs.Context(home=home, profiles=profiles, plan_dirs=cs.PlanDirs(root / "plan-dirs.json", save=False),
                      plan_projects=cs.PlanProjects(root, save=False))


def plan_origin(profiles, ctx, slug):
    """{"project": the folder the chat that made a plan started in, "cwd",
    "chat", "profile"} as noted (cs.PlanProjects), else from that chat
    (the newest with its slug); {} when there's none."""
    noted = ctx.plan_projects.get(slug)
    if noted:
        return dict(noted, project=noted.get("project") or noted.get("cwd") or "")
    p, transcript = cs.plan_chat(profiles, slug)
    if transcript is None:
        return {}
    start = cs.first_cwd(transcript)
    return {"project": start, "cwd": start, "chat": transcript.stem, "profile": p.key}


def move_plan(profiles, home, slug, name, folder=None, back=False, setting=True, if_exists=None, describe=False):
    """Move a plan of the profile name (else the only one) into the project
    folder's plans folder (folder None: the chat's own), or (back) a plan of
    a project's folder into the account name's plans/; or (describe) say
    what that would do. {"ok", "message", "question", "title", "slug" (its
    name once moved), "back", "project", "projectShort", "target",
    "targetShort", "setting" (where the project's plansDirectory comes
    from: "local", "project", "user"; "": none, so the move can add one,
    setting: it does), "settingsFile", "git" (it would show up in git
    there; None: no repository), "exists" (another plan of that name is
    there: if_exists says keep both or replace), "free" (keep both's name),
    "account", "lost" (back: the project's chats look for it in the
    project's folder), "choices" [{"path", "short"}] and "default" (the
    projects to pick from)}."""
    out = {"ok": False, "message": "", "question": "", "title": "", "slug": slug, "back": back, "project": "",
           "projectShort": "", "target": "", "targetShort": "", "setting": "", "settingsFile": "", "git": None,
           "exists": False, "free": "", "account": "", "lost": False, "choices": [], "default": ""}
    if not cs.PLAN_SLUG.match(slug or ""):
        return dict(out, message=f"Not a plan name: {slug}")
    owner = named(profiles, name) if name else None
    if name and owner is None:
        return dict(out, message=f"No Claude profile called {name}")
    if if_exists is not None and if_exists not in IF_EXISTS:
        return dict(out, message=f"Keep both or replace, not {if_exists}")
    ctx = move_ctx(profiles, home)
    short = lambda p: cs.short_folder(str(p), home)  # noqa: E731
    accounts = set()
    for p in profiles:
        try:
            st = os.stat(str(p.real / "plans"))
            accounts.add((st.st_dev, st.st_ino))
        except OSError:
            pass
    in_project = None   # (moving one of a project's folder to another project: that project)
    if back:
        src, project = cs.project_plan_of(ctx, slug)
        if src is None:
            return dict(out, message="That plan isn't in a project's folder any more")
        if owner is None:
            key = cs.project_plan_owner(ctx, slug, project)
            owner = next((p for p in profiles if p.key == key), profiles[0])
        dest_dir = str(owner.path / "plans")
        where, value = cs.project_settings(ctx, project, owner)
        out["lost"] = bool(value is not None and cs.plans_dir_in(project, value))
        folder = project
    else:
        have = plan_copies(profiles, slug)
        src = next((path for p, path in have if owner is not None and p.real == owner.real), None) \
            if owner is not None else (have[0][1] if have and all(same(path, have[0][1]) for _, path in have) else None)
        if src is None and not any(owner is None or p.real == owner.real for p, _ in have):
            src, in_project = cs.project_plan_of(ctx, slug)   # (one in a project's folder, to another project)
        if src is None:
            if not have:
                return dict(out, message="That plan isn't there any more")
            return dict(out, message=(f"{owner.label} doesn't have this plan" if owner is not None else
                                      "Several accounts have a different plan of that name: say which account's goes"))
        if owner is None:
            key = cs.project_plan_owner(ctx, slug, in_project) if in_project else None
            owner = next((p for p in profiles if p.key == key), None) if key else \
                next(p for p, path in have if same(path, src))
            owner = owner or profiles[0]
        starts = cs.start_folders(ctx)
        choices = sorted((f for f in starts if os.path.isdir(f) and os.path.normpath(f) != os.path.normpath(str(home))),
                         key=lambda f: -starts[f][0])[:MOVE_CHOICES]
        default = plan_origin(profiles, ctx, slug).get("project") or ""
        default = default if default and os.path.isdir(default) and default != in_project else ""
        if default:  # (the chat's own first)
            choices = [default] + [f for f in choices if f != default]
        out["choices"] = [{"path": f, "short": short(f)} for f in choices]
        out["default"] = default
        folder = folder or default
        out["title"], out["account"] = cs.plan_title(src) or slug, owner.label
        if not folder:
            return dict(out, ok=bool(describe), message="" if describe else "Pick the project it goes to",
                        question=f"Move “{out['title']}” to which project?")
        folder = os.path.normpath(folder)
        if not os.path.isabs(folder) or not os.path.isdir(folder):
            return dict(out, message=f"{short(folder)} isn't a folder here")
        where, value = cs.project_settings(ctx, folder, owner)
        named_dir = cs.plans_dir_in(folder, value) if value is not None else None
        dest_dir = named_dir or os.path.join(folder, cs.PROJECT_PLANS_DIR)
        out["setting"] = where if named_dir else ""
        out["settingsFile"] = short(cs.local_settings_file(ctx, folder))
    dest = os.path.join(dest_dir, slug + ".md")
    try:
        st = os.stat(dest_dir)
        if not back and (st.st_dev, st.st_ino) in accounts:
            return dict(out, message=f"{short(dest_dir)} is an account's own plans folder")
    except OSError:
        pass
    out.update(title=cs.plan_title(src) or slug, account=owner.label, project=folder, projectShort=short(folder),
               target=dest, targetShort=short(dest))
    if same(dest, src):
        return dict(out, message="It's there already")
    out["exists"] = os.path.lexists(dest)
    out["free"] = free_slug(dest_dir, slug) if out["exists"] else ""
    if not back:
        out["git"] = git_shows(folder, dest)
    if back:
        question = f"Move “{out['title']}” back to {owner.label}?"
        if out["lost"]:
            question += f" Claude's chats in {out['projectShort']} look for plans in its folder: they won't find it there."
    else:
        question = f"Move “{out['title']}” to {out['projectShort']}? It goes to {out['targetShort']}."
        if out["git"]:
            question += " It would show up in git there."
        if not out["setting"]:
            question += (f" With “Keep this project's new plans there too”, {out['settingsFile']} names that folder;"
                         " without it, Claude's chats there won't find the plan by its name.")
    if out["exists"]:
        question += f" There's another plan called {slug} there: keep both ({out['free']}), or replace it?"
    out["question"] = question
    if describe:
        return dict(out, ok=True, message=question)
    if out["exists"] and if_exists is None:
        return dict(out, message=f"There's another plan called {slug} there: keep both, or replace it?")
    new_slug = out["free"] if out["exists"] and if_exists == "keep" else slug
    dest = os.path.join(dest_dir, new_slug + ".md")
    # (every account's link to it goes once it's there: it's in one place then)
    links = [src] if back or in_project else [path for _p, path in plan_copies(profiles, slug) if same(path, src)]
    added = False
    try:
        if not back and not out["setting"] and setting:
            add_plans_setting(cs.local_settings_file(ctx, folder))
            added = True
        os.makedirs(dest_dir, exist_ok=True)
        if out["exists"] and if_exists == "replace":
            ok, why = to_trash([Path(dest)], home)
            if not ok:
                return dict(out, message=why)
        place(src, dest)
    except FileExistsError:
        return dict(out, message=f"Another plan called {new_slug} came there meanwhile: nothing moved")
    except (OSError, ValueError) as exc:
        return dict(out, message=f"Couldn't move it: {getattr(exc, 'strerror', None) or exc}")
    try:
        for path in links:
            os.unlink(str(path))
    except OSError as exc:
        return dict(out, ok=True, slug=new_slug, message=f"Moved it, but a copy stayed: {exc.strerror or exc}")
    note_move(ctx, home, slug, new_slug, folder, owner)
    message = (f"Moved the plan back to {owner.label}" if back else
               f"Moved the plan to {short(dest_dir)}" + (f"; {out['settingsFile']} keeps the project's new plans there"
                                                         if added else ""))
    return dict(out, ok=True, slug=new_slug, target=dest, targetShort=short(dest), message=message)


def note_move(ctx, home, slug, new_slug, folder, owner):
    """The moved plan keeps its project and its chat; a hidden one stays
    hidden under its new name."""
    root = cs.cache_dir(home)
    noted = plan_origin(ctx.profiles, ctx, slug)
    entry = {"cwd": noted.get("cwd") or folder, "project": folder, "chat": noted.get("chat") or "",
             "profile": noted.get("profile") or owner.key, "at": int(time.time() * 1000)}
    try:
        cs.change_plan_projects(root, put={new_slug: entry})
        if new_slug != slug and slug in cs.load_hidden(root)["plans"]:
            cs.change_hidden(root, "plans", add=new_slug)
    except OSError:
        pass


# ---------------------------------------------------------------- what the buttons do


def open_in(profiles, chat_id):
    """Label of the profile where a running session has this chat open, or None."""
    for entry, runs_on, _holder in cs.live_entries_all(profiles):
        if entry.get("sessionId") == chat_id and entry.get("kind") in cs.SESSION_KINDS and not entry.get("spare"):
            return runs_on.label
    return cs.shared_holder(chat_id, profiles)


def named(profiles, name):
    """The profile called name (a folder name like .claude-work, or a path), or None."""
    return next((p for p in profiles if name and cs.matches_profile(p, name)), None)


def give_to(profiles, chat_id, name, root, end_first=False, home=None):
    """Give the profile `name` a chat, shared if it doesn't have it yet:
    (its profile, its transcript of the chat), or (None, why not). With
    end_first, a session that has it open idle (e.g. stopped by a usage
    limit) is ended first (talpy_den.end_for_handover)."""
    target = named(profiles, name)
    if target is None:
        return None, f"No Claude profile called {name}"
    if end_first:
        ok, message = cs.end_for_handover(home or Path.home(), profiles, chat_id)
        if not ok:
            return None, message
    busy = open_in(profiles, chat_id)
    if busy:
        return None, f"It's open on {busy}. A chat can be open in one place at a time: exit it there first."
    paths = [path for p in profiles for path in [cs.transcript_path(p, chat_id)] if path]
    if not paths:
        return None, "That chat has no transcript on this computer"
    there = cs.transcript_path(target, chat_id)
    if there is None:
        ok, message = share(profiles, chat_id, [target], root)
        if not ok:
            return None, message
        there = cs.transcript_path(target, chat_id)
        if there is None:
            return None, f"It wasn't added to {target.label}: {message}"
    elif any(not os.path.samefile(there, other) for other in paths):
        return None, f"{target.label} has a different chat with the same id; left everything as it is"
    share_chat_plan(profiles, chat_id, [target])
    return target, there


def continue_command(profiles, chat_id, name, root, home, claude, end_first=False):
    """Continue a chat on the profile `name`: share it with that profile if
    needed, and hand back the shell command that reopens it there (claude:
    how to run claude): (ok, message, command or None)."""
    target, there = give_to(profiles, chat_id, name, root, end_first, home)
    if target is None:
        return False, there, None
    folder = cs.chat_folder(there)
    command = cs.in_folder(folder, cs.resume_command(target, chat_id, home, folder, claude))
    return True, f"Continuing it on {target.label}", command


def share_with_all(profiles, chat_id, root, name=None):
    """Share a chat with every profile (from the copy of the profile `name`, if given)."""
    busy = open_in(profiles, chat_id)
    if busy:
        return False, f"It's open on {busy}. Exit it there first."
    ok, message = share(profiles, chat_id, profiles, root, named(profiles, name))
    if ok:
        share_chat_plan(profiles, chat_id, profiles)
    return ok, message


def keep_only_on(profiles, chat_id, name, root):
    """Make a shared chat a normal chat of the profile `name` again; the others lose it."""
    keep = named(profiles, name)
    if keep is None:
        return False, f"No Claude profile called {name}"
    busy = open_in(profiles, chat_id)
    if busy:
        return False, f"It's open on {busy}. Exit it there first."
    return keep_only(profiles, chat_id, keep, root)


def plan_sharing(profiles, slug, name, share_it, to=None, home=None):
    """--share-plan (from the profile name's copy, with every profile or only
    to) and --unshare-plan (keep it on name only): (ok, message). A plan in
    a project's folder (with home: looked for) isn't shared: every account
    reads it there."""
    if not cs.PLAN_SLUG.match(slug or ""):
        return False, f"Not a plan name: {slug}"
    if home is not None and not plan_copies(profiles, slug) and cs.find_project_plan(profiles, slug, home)[0]:
        return False, "This plan is in its project's folder: every account has it there"
    source = named(profiles, name) if name else None
    if name and source is None:
        return False, f"No Claude profile called {name}"
    if not share_it:
        return keep_plan_only(profiles, slug, source)
    into = profiles
    if to:
        target = named(profiles, to)
        if target is None:
            return False, f"No Claude profile called {to}"
        into = [target]
    return share_plan(profiles, slug, into, source)


# ---------------------------------------------------------------- deleting
#
# A chat, a plan or a memory can be deleted (jump.py --delete-chat,
# --delete-plan, --delete-memory; on an SSH host remote.py runs this file's
# main() there): it goes to the Trash (accounts.move_to_trash; the host's
# Trash on a host), from every account that has it, after a question the
# front ends ask with describe's words. Nothing is unlinked: another
# account's link (a shared chat's transcript and folders, a plan) goes to the
# Trash too. A chat a session has open isn't deleted.

DELETE_KINDS = ("chat", "plan", "memory")
MEMORY_KEY = re.compile(r"^(.+)/([A-Za-z0-9._-]+)/([^/]+)/memory$")  # <profile>/<project>/<name>/memory


def spot(path):
    """The directory entry path names, not followed if it's a link (entry()
    follows it): (its folder's device and inode, its name)."""
    folder = os.path.realpath(os.path.dirname(str(path)))
    try:
        st = os.stat(folder)
    except OSError:
        return folder, os.path.basename(str(path))
    return st.st_dev, st.st_ino, os.path.basename(str(path))


def and_list(names):
    names = list(names)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def gather(pairs):
    """[(profile, path)] → (the profiles' labels, the paths once each, as entries)."""
    labels, paths, seen = [], [], set()
    for p, path in pairs:
        if p is not None and p.label not in labels:
            labels.append(p.label)
        if present(path) and spot(path) not in seen:
            seen.add(spot(path))
            paths.append(path)
    return labels, paths


def chat_jobs(profiles, chat_id):
    """The background-job folders of a chat: [(profile, jobs/<id>, its
    state.json)] of each job that ran it (its sessionId) or took it over
    (its resumeSessionId)."""
    found = []
    for p in profiles:
        for d in cs.job_dirs(p):
            job = cs.read_json(d / "state.json")
            if not isinstance(job, dict):
                continue
            if chat_id in (job.get("sessionId"), job.get("resumeSessionId")) \
                    or (d.name == chat_id[:8] and not cs.valid_id(job.get("sessionId"))):
                found.append((p, d, job))
    return found


def job_at_work(profiles, jobs):
    """The label of the profile where one of these jobs (chat_jobs) isn't
    finished, or has a process, or None."""
    live = {e.get("jobId") for e, _, _ in cs.live_entries_all(profiles)}
    return next((p.label for p, d, job in jobs if d.name in live or not cs.job_finished(job)), None)


def chat_to_delete(profiles, chat_id, name, root):
    """The copy of a chat that goes (the one the profile name has, else the
    only one), from every profile that shares it: (its accounts, the paths
    to move to the Trash, its transcript), or (None, why not, None)."""
    if not cs.valid_id(chat_id):
        return None, f"Not a chat: {chat_id}", None
    groups = copies(profiles, chat_id)
    if not groups:
        return None, "That chat isn't there any more", None
    if name:
        owner = named(profiles, name)
        if owner is None:
            return None, f"No Claude profile called {name}", None
        chat = next((g for g in groups if any(p.real == owner.real for p, _ in g)), None)
        if chat is None:
            return None, f"{owner.label} doesn't have this chat", None
    elif len(groups) > 1:
        return None, "Several accounts have different chats with this id: say which account's goes", None
    else:
        chat = groups[0]
    path = chat[0][1]
    key = path.parent.name
    if not PROJECT_KEY.match(key) or key in (".", ".."):
        return None, f"Unexpected project folder {key}; left the chat as it is", None
    sharers = [p for p, _ in chat]
    pairs = list(chat) + [(p, in_profile(p, key, chat_id, part)) for p in sharers for part in FOLDERS]
    # (its finished background chat's folder too: else its record stays listed, with nothing to show)
    pairs += [(None, d) for _, d, _ in chat_jobs(sharers, chat_id)]
    store = store_paths(sharers, key, chat_id, root)
    if store[TRANSCRIPT].is_file() and same(store[TRANSCRIPT], path):
        pairs.append((None, store[TRANSCRIPT]))  # (the store's own link to it)
    for part in FOLDERS:  # (what the profiles' links point to)
        if any(in_profile(p, key, chat_id, part).is_symlink() for p in sharers) and store[part].is_dir():
            pairs.append((None, store[part]))
    labels, paths = gather(pairs)
    return labels, paths, path


def plan_to_delete(profiles, slug, name, home=None):
    """A plan that goes (the profile name's, else the only one), from every
    profile it's linked into: (its accounts, its paths, the file), or (None,
    why not, None). With home, one in a project's plans folder too, when
    the profile name (else any) has none of that name: ([], [its path], it)."""
    if not cs.PLAN_SLUG.match(slug or ""):
        return None, f"Not a plan name: {slug}", None
    have = plan_copies(profiles, slug)
    owner = named(profiles, name) if name else None
    if home is not None and not any(owner is None or p.real == owner.real for p, _ in have):
        path, _folder = cs.find_project_plan(profiles, slug, home)
        if path is not None:
            return [], [path], path
    if not have:
        return None, "That plan isn't there any more", None
    if name:
        owner = named(profiles, name)
        if owner is None:
            return None, f"No Claude profile called {name}", None
        src = next((path for p, path in have if p.real == owner.real), None)
        if src is None:
            return None, f"{owner.label} doesn't have this plan", None
    else:
        src = have[0][1]
        if not all(same(path, src) for _, path in have):
            return None, "Several accounts have a different plan of that name: say which account's goes", None
    labels, paths = gather((p, path) for p, path in have if same(path, src))
    return labels, paths, src


def memory_to_delete(profiles, key):
    """A memory file, by the key the status lists it with: (its profile, its
    path), or (None, why not). An account's CLAUDE.md isn't one."""
    if (key or "").endswith("/CLAUDE.md/memory"):
        return None, "CLAUDE.md, your instructions for every chat on the account, isn't deleted from here"
    m = MEMORY_KEY.match(key or "")
    if not m or m.group(2) in (".", "..") or m.group(3) in (".", "..", "MEMORY"):
        return None, f"Not a memory: {key}"
    p = next((q for q in profiles if q.key == m.group(1)), None)
    if p is None:
        return None, f"No Claude profile called {m.group(1)}"
    path = p.path / "projects" / m.group(2) / "memory" / (m.group(3) + ".md")
    if not path.is_file():
        return None, "That memory isn't there any more"
    return p, path


def unindex_memory(path):
    """Take the lines of the memory folder's MEMORY.md that link path's file
    out (Claude reads that index in each new chat); every other byte stays.
    Whether it changed."""
    index = os.path.realpath(str(path.parent / "MEMORY.md"))
    try:
        with open(index, "rb") as f:
            data = f.read()
    except FileNotFoundError:
        return False
    link = re.compile(rb"\]\(\s*<?(?:\./)?" + re.escape(path.name.encode("utf-8")) + rb">?(?:\s+\"[^\"]*\")?\s*\)")
    lines = data.splitlines(keepends=True)
    kept = [line for line in lines if not link.search(line)]
    if len(kept) == len(lines):
        return False
    tmp = os.path.join(os.path.dirname(index), f".MEMORY.md.{os.getpid()}.tmp")
    try:
        with open(tmp, "wb") as f:
            f.write(b"".join(kept))
        shutil.copymode(index, tmp)
        os.replace(tmp, index)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return True


def recap_reads(home, profiles):
    """The Recap reads what the transcripts added before one goes (week.py's
    cache keeps what it read: the Recap keeps the chat's numbers)."""
    try:
        import week  # (not on an SSH host: there it reads them when the Recap asks)
    except ImportError:
        return
    try:
        cache_root = cs.cache_dir(home)
        if week.cache_path(cache_root).is_file():
            import time
            week.updated_cache(cache_root, profiles, int(time.time() * 1000))
    except Exception:  # (the Recap is no reason not to delete)
        pass


def to_trash(paths, home):
    """Move the paths to the Trash, links first (a link to a folder that went
    already would be one to nothing): (ok, message)."""
    import accounts
    for path in paths:
        why = accounts.trash_problem(path, home)
        if why:
            return False, f"Nothing was deleted: {why}"
    done = 0
    try:
        for path in sorted(paths, key=lambda path: not path.is_symlink()):
            accounts.move_to_trash(path, home)
            done += 1
    except (OSError, ValueError, accounts.subprocess.SubprocessError) as exc:
        return False, f"Couldn't finish: {exc}" + (f" ({done} of {len(paths)} moved to the Trash)" if done else "")
    return True, "Moved to the Trash"


def delete(profiles, kind, item, name, root, home, describe=False):
    """Delete a chat, a plan or a memory (kind chat, plan, memory; name: the
    profile whose copy), or (describe) say what would go: {"ok", "message",
    and with describe "question", "name", "accounts", "open"}. The question
    is the one to ask; "open" names the account a session has the chat open
    on (it isn't deleted then: ok is false, the message says why), as does
    a background job of the chat that isn't finished."""
    at_work = None
    if kind == "memory":
        p, path = memory_to_delete(profiles, item)
        if p is None:
            return {"ok": False, "message": path}
        title = cs.memory_head(path).get("name") or path.stem
        folder = cs.memory_folder(path.parent.parent)[0]
        question = (f"Delete the memory “{title}”? It goes to the Trash, and Claude stops reading it in new "
                    f"chats in {cs.short_path(folder, home)}.")
        labels, paths, busy = [p.label], [path], None
    elif kind == "plan":
        labels, paths, src = plan_to_delete(profiles, item, name, home)
        if labels is None:
            return {"ok": False, "message": paths}
        title, busy = cs.plan_title(src) or item, None
        question = (f"Delete the plan “{title}” on {and_list(labels)}? It goes to the Trash." if labels else
                    f"Delete the plan “{title}” from {cs.short_folder(str(src.parent), home)}? It goes to the Trash.")
    else:
        labels, paths, src = chat_to_delete(profiles, item, name, root)
        if labels is None:
            return {"ok": False, "message": paths}
        try:
            title = cs.read_chat_info(src, src.stat().st_size)[0] or item[:8]
        except OSError:
            title = item[:8]
        busy = open_in(profiles, item)
        at_work = None if busy else job_at_work(profiles, chat_jobs(profiles, item))
        question = (f"Delete “{title}” on {and_list(labels)}? It goes to the Trash with its subagents and "
                    "checkpoints; the Recap keeps its numbers.")
    why = f"It's open on {busy}. Exit it there first." if busy else ""
    if at_work:
        why = f"It runs in the background on {at_work}. Stop it first."
    if describe:
        # ("folder": a project's plans folder the plan is in, as the question names it)
        return {"ok": not why, "message": why or question, "question": question, "name": title, "accounts": labels,
                "open": busy or "", "folder": cs.short_folder(str(src.parent), home) if kind == "plan" and not labels else ""}
    if why:
        return {"ok": False, "message": why}
    if kind == "chat":
        recap_reads(home, profiles)
    ok, message = to_trash(paths, home)
    if ok and kind == "memory":
        try:
            unindex_memory(path)
        except OSError as exc:
            message += f", but MEMORY.md still names it ({exc.strerror or exc})"
    if ok:
        try:
            cs.forget_deleted(cs.cache_dir(home), kind + "s" if kind != "memory" else "memories", item)
        except OSError:
            pass
    return {"ok": ok, "message": message}


USAGE = ("usage: sharing.py (--share CHAT_ID | --continue CHAT_ID [--end-first] | --unshare CHAT_ID) [--profile PROFILE]\n"
         "       sharing.py (--share-plan SLUG [--to PROFILE] | --unshare-plan SLUG) [--profile PROFILE]\n"
         "       sharing.py (--delete-chat CHAT_ID | --delete-plan SLUG) [--profile PROFILE] [--describe]\n"
         "       sharing.py --delete-memory KEY [--describe]\n"
         "       sharing.py --move-plan SLUG [--profile PROFILE] [--into FOLDER | --back] [--no-setting]\n"
         "                  [--if-exists keep|replace] [--describe]\n"
         "                  [--config-dir DIR]... [--remote]   (--continue, --unshare and --unshare-plan need --profile)")


def main(argv=None):
    """On an SSH host (remote.py): prints {"ok", "message"} and, for
    --continue, "command"."""
    args = sys.argv[1:] if argv is None else list(argv)
    action, chat_id, name, extra, remote, end_first, to = None, None, None, [], False, False, None
    describe, into, back, setting, if_exists = False, None, False, True, None
    while args:
        arg = args.pop(0)
        if arg in ("--share", "--continue", "--unshare", "--share-plan", "--unshare-plan", "--delete-chat",
                   "--delete-plan", "--delete-memory", "--move-plan") and args and action is None:
            action, chat_id = arg, args.pop(0)
        elif arg == "--describe":
            describe = True
        elif arg == "--into" and args:
            into = args.pop(0)
        elif arg == "--back":
            back = True
        elif arg == "--no-setting":
            setting = False
        elif arg == "--if-exists" and args:
            if_exists = args.pop(0)
        elif arg == "--profile" and args:
            name = args.pop(0)
        elif arg == "--to" and args:
            to = args.pop(0)
        elif arg == "--end-first":
            end_first = True
        elif arg == "--config-dir" and args:
            extra.append(args.pop(0))
        elif arg == "--remote":
            remote = True
        else:
            sys.exit(USAGE)
    deleting = action is not None and action.startswith("--delete-")
    moving = action == "--move-plan"
    if action is None or (action not in ("--share", "--share-plan") and not deleting and not moving and not name) \
            or (describe and not deleting and not moving) \
            or ((into is not None or back or not setting or if_exists is not None) and not moving) or (into and back):
        sys.exit(USAGE)
    home, command, more = Path.home(), None, {}
    try:
        profiles, root = cs.discover_profiles(home, extra), store_root(home)
        if action == "--share":
            ok, message = share_with_all(profiles, chat_id, root, name)
        elif action == "--unshare":
            ok, message = keep_only_on(profiles, chat_id, name, root)
        elif action in ("--share-plan", "--unshare-plan"):
            ok, message = plan_sharing(profiles, chat_id, name, action == "--share-plan", to, home)
        elif deleting:
            more = delete(profiles, action[len("--delete-"):], chat_id, name, root, home, describe)
            ok, message = more.pop("ok"), more.pop("message")
        elif moving:
            more = move_plan(profiles, home, chat_id, name, into, back, setting, if_exists, describe)
            ok, message = more.pop("ok"), more.pop("message")
        else:
            # A click: the login shell may be asked where claude is
            ok, message, command = continue_command(profiles, chat_id, name, root, home,
                                                    cs.find_claude(home, ask_shell=True), end_first)
    except Exception as exc:  # report, don't crash: the widget shows the message
        ok, message = False, f"{type(exc).__name__}: {exc}"
    if remote:
        # Login scripts on the host may print things first: the JSON follows a marker
        sys.stdout.write("\n" + cs.REMOTE_MARK + " ")
    # ASCII: a lone surrogate in a name can't break the answer
    json.dump({"ok": ok, "message": message, **more, **({"command": command} if command else {})}, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
