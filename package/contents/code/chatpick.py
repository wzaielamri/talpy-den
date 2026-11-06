"""A chat's own model and effort, picked in Talpy Chat (/model and /effort,
its picker), for pane.py --set-options: for that chat alone. Claude's own
/model and /effort save what you pick as your default for every new chat
(into your settings.json, whatever the chat was started with); this never
writes your settings:

- a background chat: what Claude wakes it with (its job's respawnFlags) gets
  the model and effort in place of its own. One open idle is stopped first
  and woken again at once, with no message (claude --bg --resume FULL-ID:
  live-checked on Claude Code 2.1.318, half a second, the same job, no
  "Switch model?"); one settled has them from its next message;
- a chat with no job of its own (it last ran in a terminal, closed now):
  kept for its next wake from here (talpy_den.keep_picked, go_on_with);
- not now: a chat at work or asking you something, or running commands in
  the background (claude stop would end them); and not here: one that runs
  in a terminal or VS Code's Claude (the front ends open /model there).

A module of its own (pane.py, run as a script, is compiled at every call).
Python 3.7+ and the standard library only (the SSH host backend too).
"""
import json
import os
import time

import talpy_den as cs

MODEL_ALIASES = ("opus", "sonnet", "fable", "haiku")
DEFAULT_WORDS = ("", "default")  # (/model default: Claude's own)


def pick_value(value, known=None):
    """A picked model or effort as claude takes it: None (not changed), ""
    (Claude's default) or the name; ValueError for one that isn't."""
    if value is None:
        return None
    value = value.strip()
    if value.lower() in DEFAULT_WORDS:
        return ""
    if known is not None:
        if value.lower() not in known:
            raise ValueError(f"Not an effort level: {value} (one of {', '.join(known)})")
        return value.lower()
    if not cs.MODEL_NAME.match(value):
        raise ValueError(f"Not a model: {value}")
    return value.lower() if value.lower() in MODEL_ALIASES else value


def label(model, effort):
    """"Sonnet · medium effort", as the answer says it."""
    words = []
    if model is not None:
        words.append(cs.model_label(model) or (model.capitalize() if model.isalpha() else model) if model
                     else "Claude's default model")
    if effort is not None:
        words.append(f"{effort} effort" if effort else "Claude's default effort")
    return " · ".join(words)


def write_flags(state_path, chat_id, model, effort):
    """Its job's saved options with the model and effort in place of its
    own (in one go, its file's mode kept): whether they're there now."""
    import shutil
    job = cs.read_json(state_path)
    flags = job.get("respawnFlags") if isinstance(job, dict) and job.get("sessionId") == chat_id else None
    if not isinstance(flags, list) or not all(isinstance(f, str) for f in flags):
        return False
    tmp = state_path.with_name(f".{state_path.name}.{os.getpid()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dict(job, respawnFlags=cs.replace_options(flags, model, effort)), f)
        shutil.copymode(state_path, tmp)
        os.replace(tmp, state_path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return False
    return True


def let_go(profiles, runs_on, chat_id, job_id, wait):
    """Wait till no process has the chat open and Claude's background
    service no longer holds its job (claude --bg --resume would start a copy
    meanwhile): whether it let go."""
    held = lambda: any(e.get("sessionId") == chat_id for e, _, _ in cs.live_entries_all(profiles)) \
        or cs.daemon_holds([runs_on], sorted({job_id, chat_id[:8]}))
    deadline = time.time() + wait
    while held():
        if time.time() >= deadline:
            return False
        time.sleep(0.1)
    return True


def set_options(home, extra_dirs, profile_key, chat_id, model=None, effort=None, claude=None, prefix=(),
                wait=cs.END_WAIT):
    """Set a chat's own model and effort (None: as it is; "" or "default":
    Claude's default): {"ok", "message", "how": "now" (it goes on with them
    at once) | "next" (from your next message) | "terminal" (not from here),
    "model", "effort"}. One wake of a chat at a time (talpy_den.wake_lock)."""
    try:
        model = pick_value(model)
        effort = pick_value(effort, cs.EFFORT_LEVELS)
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}
    if model is None and effort is None:
        return {"ok": False, "message": "Pick a model or an effort level"}
    if not cs.valid_id(chat_id):
        return {"ok": False, "message": f"Not a chat: {chat_id}"}
    profiles = cs.discover_profiles(home, extra_dirs)
    profile = next((p for p in profiles if cs.matches_profile(p, profile_key)), None)
    if profile is None or cs.transcript_path(profile, chat_id) is None:
        return {"ok": False, "message": "That chat isn't on this account any more"}
    with cs.wake_lock(home, chat_id) as waited:
        if waited:
            cs.wake_settle(home, extra_dirs, chat_id)
        answer = set_now(home, profiles, profile, chat_id, model, effort, claude, prefix, wait)
    return dict(answer, model=model, effort=effort)


def set_now(home, profiles, profile, chat_id, model, effort, claude, prefix, wait):
    """set_options' change, under its lock."""
    said = label(model, effort)
    for entry, runs_on, _holder in cs.live_entries_all(profiles):
        if entry.get("sessionId") != chat_id or entry.get("kind") not in cs.SESSION_KINDS or entry.get("spare"):
            continue
        if entry.get("kind") != "bg" or not cs.valid_id(entry.get("jobId") or "") or entry.get("parkedJobId"):
            return {"ok": False, "how": "terminal",
                    "message": "It runs in a terminal: change its model there (Claude saves it as your default for "
                               "new chats too)"}
        state = cs.session_state(entry)
        if state == "waiting":
            return {"ok": False, "message": "It's asking you something: answer that first"}
        if state != "idle":
            return {"ok": False, "message": "Claude is at work: pick it again once this turn ends"}
        commands = cs.background_commands(entry, runs_on)
        if commands:
            return {"ok": False, "message": "It runs " + (f"{len(commands)} commands" if len(commands) > 1 else "a command")
                    + " in the background (" + ", ".join(commands[:3]) + "): changing its model stops it, and them. "
                    "Pick it again once they're done"}
        job_id = entry["jobId"]
        state_path = runs_on.path / "jobs" / job_id / "state.json"
        record = cs.read_json(state_path)
        if not (isinstance(record, dict) and record.get("sessionId") == chat_id):
            return {"ok": False, "message": "Its background job isn't one Talpy Den can change"}
        claude = claude or cs.find_claude(home, ask_shell=True)
        if claude is None:
            return {"ok": False, "message": "No claude command found"}
        ok, message = cs.stop_background(runs_on, job_id, record, home, claude)
        if not ok:
            return {"ok": False, "message": message}
        if not let_go(profiles, runs_on, chat_id, job_id, wait):
            return {"ok": False, "message": "Its background job didn't let go of it in time: your next message wakes "
                                            "it, then pick it again"}
        if not write_flags(state_path, chat_id, model, effort):
            return {"ok": False, "message": "Couldn't change its saved options: your next message wakes it as it was"}
        folder = entry.get("cwd") if isinstance(entry.get("cwd"), str) and os.path.isdir(entry["cwd"]) else \
            (cs.chat_folder(cs.transcript_path(profile, chat_id)) or str(home))
        ok, message, _job = cs.start_background(runs_on, folder, None, home, claude, prefix=prefix, resume=chat_id)
        if not ok:
            return {"ok": True, "how": "next",
                    "message": f"{said} for this chat: it stopped and didn't wake again ({message}); your next "
                               "message wakes it with them"}
        return {"ok": True, "how": "now", "message": f"{said} for this chat from now on"}
    # not open: its own job's saved options, else kept for its next wake from here
    state_path = profile.path / "jobs" / chat_id[:8] / "state.json"
    record = cs.read_json(state_path)
    if isinstance(record, dict) and record.get("sessionId") == chat_id:
        if not let_go(profiles, profile, chat_id, chat_id[:8], wait) or not write_flags(state_path, chat_id, model, effort):
            return {"ok": False, "message": "Couldn't change its saved options: try again in a moment"}
    else:
        cs.keep_picked(home, chat_id, model, effort)
    return {"ok": True, "how": "next", "message": f"{said} for this chat, from your next message"}
