#!/usr/bin/env python3
"""SSH hosts and containers for the Talpy Den widget.

    python3 -I remote.py --hosts [--container-days N] [--picked IDS] [--no-containers]
                                                    hosts named in ~/.ssh/config, this computer's containers
                                                    (running, or active in the last N days, default 30;
                                                    the picked ones always) and the hosts' last lists
    python3 -I remote.py --containers HOST [--container-days N] [--picked IDS]   an SSH host's containers
    python3 -I remote.py --start CONTAINER          start a stopped container
    python3 -I remote.py --last HOST...             each one's last answer (kept by --status), for the next start
    python3 -I remote.py --attach CONTAINER COMMAND (in a terminal) COMMAND in the container, in this terminal
    python3 -I remote.py --status HOST [--done-hours H] [--recent N] [--plans N] [--memories N] [--no-tokens]
                                     [--usage-refresh N]
    python3 -I remote.py --open HOST COMMAND        a terminal running COMMAND on HOST
    python3 -I remote.py --run HOST COMMAND         run COMMAND on HOST (e.g. claude stop)
    python3 -I remote.py --end HOST SESSION_ID [PROFILE] [--busy] [--keep-off CHAT_ID]   stop a chat in a terminal or VS Code there
                     (--keep-off: and once it's stopped, that chat doesn't keep going any more)
    python3 -I remote.py --interrupt HOST SESSION_ID [PROFILE]      interrupt a working chat in tmux there (or in the background)
    python3 -I remote.py --dismiss HOST SESSION_ID  hide a finished chat of HOST
    python3 -I remote.py --undismiss-all HOST
    python3 -I remote.py --hide HOST KIND ID        hide a chat, plan, memory or project of HOST (KIND
                                                    chats|plans|memories|projects; kept there)
    python3 -I remote.py --show-hidden HOST KIND    show HOST's hidden ones of KIND again
    python3 -I remote.py --delete-chat HOST CHAT_ID [PROFILE] [--describe]   a chat of HOST to the Trash there
    python3 -I remote.py --delete-plan HOST SLUG [PROFILE] [--describe]      (--describe: the question to ask
    python3 -I remote.py --delete-memory HOST KEY [--describe]               first, and what goes)
    python3 -I remote.py --agent-run HOST CHAT_ID AGENT_ID [PROFILE] [--no-open]   a subagent's run there, as a Markdown file here
    python3 -I remote.py --share HOST CHAT_ID [PROFILE]    share a chat with every account there (from PROFILE's copy)
    python3 -I remote.py --continue HOST CHAT_ID PROFILE [--print-command]   share it with PROFILE there if needed,
                                                    and reopen it there in a terminal (or print the command)
    python3 -I remote.py --unshare HOST CHAT_ID PROFILE    keep a shared chat only on PROFILE there
    python3 -I remote.py --find HOST QUERY          the chats there with every word of QUERY
    python3 -I remote.py --task HOST PROFILE FOLDER [--prompt TEXT] [--plan SLUG PLAN_PROFILE] [--model M] [--effort E]
                         [--permission-mode MODE] [--bg | --print-command]
                                                    a new chat there with a task: in the background there,
                                                    or in a terminal here (or print its command)
    python3 -I remote.py --put-image HOST PATH      a picture pasted here (jump.py --paste-image) to HOST, for a task there
    python3 -I remote.py --plan HOST SLUG [PROFILE] [--no-open]   a plan there, as a Markdown file here
    python3 -I remote.py --share-plan HOST SLUG PROFILE [TO]      share a plan with every account there (or TO)
    python3 -I remote.py --unshare-plan HOST SLUG PROFILE         keep a shared plan only on PROFILE there
    python3 -I remote.py --move-plan HOST SLUG PROFILE [--into FOLDER | --back] [--no-setting]
                         [--if-exists keep|replace] [--describe]  a plan there into its project's plans folder,
                                                    or back into the account's (--describe: what it would do)
    python3 -I remote.py --login HOST               a terminal where you log in to HOST for the widget
    python3 -I remote.py --disconnect HOST          close the connection you logged in with
    python3 -I remote.py --vscode-account HOST CONFIG_DIR|-   VS Code's Claude on HOST runs on that account
    python3 -I remote.py --accounts HOST ACCOUNTS_ARGS... [--print-command]   the host's Claude accounts
                                                    (accounts.py there: --list, --add, --login, --default, …)

--status runs talpy_den.py on HOST: the script goes to `python3 -I -` on
the host's stdin, so nothing is installed there (it keeps its caches in the
host's ~/.cache/talpy-den, like here). Sharing sends sharing.py the same
way, with talpy_den.py in front (host_script), and so do the accounts
(accounts.py: adding one, logging in or out, removing one, the default one).
A login there opens a terminal here, over ssh: Claude's own login, whose
code you paste into it. SSH runs in batch mode, so
it never asks for a password or a host key: log in once in a terminal for
that. One connection per host is kept open for a few minutes (ControlMaster),
so polls are quick even through a jump host. Prints one JSON line.

For a host that wants a password (or a passphrase, a code, a new host key),
--login opens a terminal where ssh itself asks for it: the widget never sees
it. That login's connection becomes the shared one the checks use, until
LOGIN_MINUTES after their last use, logging out (the sockets are in
$XDG_RUNTIME_DIR), or --disconnect.

Every HOST may also be a container: docker:NAME, podman:NAME or
nerdctl:NAME on this computer, ENGINE:NAME@HOST on the SSH host HOST.
Talpy Den works in it with the engine's exec (python3 -I - there, as on a
host), over ssh in HOST's shared connection for one on a host.
"""

import glob
import json
import os
import re
import select
import selectors
import shlex
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True  # no __pycache__ inside the installed widget...
if sys.version_info >= (3, 8):  # ...but talpy_den.py compiled in the data folder, as poll.py does (never the cache)
    _compiled = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "talpy-den" / "pycache"
    if _compiled.is_dir():
        sys.pycache_prefix = str(_compiled)
        sys.dont_write_bytecode = False
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # -I leaves the script dir off sys.path
import talpy_den as cs  # noqa: E402

HERE = Path(__file__).resolve().parent
HOST_NAME = re.compile(r"^[A-Za-z0-9_.@][A-Za-z0-9_.@:-]*$")
STATUS_TIMEOUT = 45
RUN_TIMEOUT = 60
LOGIN_MINUTES = 30  # a connection you logged in to stays this long after its last use
LOGIN_SHOWN = 3  # seconds the terminal shows "Logged in" before it closes


# ---------------------------------------------------------------- ~/.ssh/config


def config_words(value):
    """The words of a config value as ssh splits them: quotes kept together,
    and a word starting with # begins a comment."""
    try:
        words = shlex.split(value, comments=True)
    except ValueError:
        words = value.split()
    out = []
    for word in words:
        if word.startswith("#"):
            break
        out.append(word)
    return out


def config_lines(path, depth=0, seen=None):
    """(keyword, value) of an ssh config file, with Include files spliced in
    between ("include", "begin") and ("include", "end"): an Include inside a
    Host block doesn't end that block."""
    seen = set() if seen is None else seen
    try:
        real = path.resolve()
        if real in seen or depth > 8:
            return
        seen.add(real)
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"([A-Za-z]+)\s*(?:=\s*|\s+)(.*)", line)
        if not m:
            continue
        key, value = m.group(1).lower(), m.group(2).strip()
        if key == "include":
            for pattern in config_words(value):
                pattern = os.path.expanduser(pattern)
                if not os.path.isabs(pattern):
                    pattern = str(Path.home() / ".ssh" / pattern)
                for match in sorted(glob.glob(pattern)):
                    yield "include", "begin"
                    yield from config_lines(Path(match), depth + 1, seen)
                    yield "include", "end"
        else:
            yield key, value


def ssh_hosts(path=None):
    """Hosts with a name of their own in ~/.ssh/config (no wildcard patterns),
    in file order, with what's useful to show next to the name."""
    path = path or Path.home() / ".ssh" / "config"
    hosts, current, outer = {}, [], []
    for key, value in config_lines(path):
        if key == "include":
            if value == "begin":
                outer.append(current)
            elif outer:
                current = outer.pop()
        elif key == "host":
            current = []
            for name in config_words(value):
                if any(c in name for c in "*?!") or not HOST_NAME.match(name):
                    continue
                hosts.setdefault(name, {"name": name, "hostname": "", "user": "", "port": "", "jump": ""})
                current.append(name)
        elif key == "match":
            current = []
        elif current and key in ("hostname", "user", "port", "proxyjump"):
            field = "jump" if key == "proxyjump" else key
            words = config_words(value)
            for name in current:
                if not hosts[name][field] and words:  # ssh uses the first value it sees
                    hosts[name][field] = words[0]
    return list(hosts.values())


# ---------------------------------------------------------------- talking to a host


SOCKET_TMP = "/tmp"
SOCKET_DIR_MAX = 49  # a socket path may have 107 characters; ssh adds 58 (/%C and a temporary suffix)


def control_dir():
    """Folder for ssh's shared connections (one per host), or None to go
    without. Short on purpose: under ~/.cache a long home folder name made
    the socket path too long. $XDG_RUNTIME_DIR (/run/user/<uid>) is short and
    private; else a folder in /tmp that only you own. The VS Code extension
    uses the same folder (sshControl.ts), so both share the connections."""
    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    if os.path.isabs(runtime) and os.path.isdir(runtime):
        d = Path(runtime) / "talpy-den-ssh"
    else:
        d = Path(SOCKET_TMP) / f"talpy-den-ssh-{os.getuid()}"
    if len(str(d)) > SOCKET_DIR_MAX:
        return None
    try:
        d.mkdir(mode=0o700, exist_ok=True)
        st = os.lstat(str(d))
        if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid():
            return None  # a link, or someone else's: no sockets there
        if st.st_mode & 0o077:
            os.chmod(str(d), 0o700)
    except OSError:
        return None
    return d


def ssh_options(batch=True):
    """Options for every connection: batch mode (never ask, never hang), keep
    one connection per host open for reuse, no X11/agent forwarding. A host's
    RemoteCommand (e.g. starting tmux) and port forwards from ~/.ssh/config
    are left out: they'd replace the widget's command, or hold your tunnels'
    ports in the shared connection."""
    d = control_dir()
    opts = ["-o", "ControlMaster=auto", "-o", f"ControlPath={d}/%C", "-o", "ControlPersist=300"] if d else []
    opts += ["-o", "ServerAliveInterval=10", "-o", "ServerAliveCountMax=3",
             "-o", "RemoteCommand=none", "-o", "ClearAllForwardings=yes"]
    if batch:
        opts += ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o", "ForwardX11=no", "-o", "ForwardAgent=no"]
    return opts


posix = cs.posix  # command for the host's login shell (fish and csh too), run by sh


def answer_after_mark(stdout):
    """The JSON answer a script printed after the marker line, or None. The
    answer is one line, and the text inside it (a chat's prompt or reply) may
    mention the marker too: only a marker at the start of a line counts."""
    mark = stdout.rfind("\n" + cs.REMOTE_MARK)
    if mark < 0:
        return None
    try:
        answer = json.loads(stdout[mark + 1 + len(cs.REMOTE_MARK):])
    except ValueError:
        return None
    return answer if isinstance(answer, dict) else None


def ssh(host, command, stdin=None, timeout=RUN_TIMEOUT):
    """Run command on host, an SSH host or a container (run_on): the CompletedProcess."""
    return run_on(host, command, stdin, timeout)


# First on a host: a python3 older than 3.7 there (RHEL 8's is 3.6) says so,
# not the error of a call it lacks later on
PYTHON_CHECK = ("import sys\n"
                "if sys.version_info < (3, 7):\n"
                "    import json\n"
                "    why = 'python3 there is %d.%d; Talpy Den needs 3.7 or newer' % sys.version_info[:2]\n"
                "    sys.stdout.write('\\n" + cs.REMOTE_MARK + " ' + json.dumps({'ok': False, 'error': why, 'message': why}) + '\\n')\n"
                "    sys.exit(0)\n")


def host_script(name="talpy_den.py", also=()):
    """What runs on a host, on python3's stdin: talpy_den.py, or another
    script of this folder that imports it (sharing.py), after talpy_den.py
    (and the scripts also, e.g. accounts.py) loaded as those modules; each
    after PYTHON_CHECK."""
    status = (HERE / "talpy_den.py").read_text(encoding="utf-8")
    if name == "talpy_den.py":
        return PYTHON_CHECK + status
    script = PYTHON_CHECK + "import sys, types\n"
    for module in ("talpy_den.py", *also):
        text = status if module == "talpy_den.py" else (HERE / module).read_text(encoding="utf-8")
        script += (f"module = sys.modules[{module[:-3]!r}] = types.ModuleType({module[:-3]!r})\n"
                   f"exec(compile({text!r}, {module!r}, 'exec'), module.__dict__)\n")
    return script + (HERE / name).read_text(encoding="utf-8")


def check_host(host):
    if not isinstance(host, str) or not HOST_NAME.match(host):
        raise ValueError(f"not a host name: {host!r}")
    return host


# ---------------------------------------------------------------- containers
#
# A Docker, Podman or nerdctl container is a place like an SSH host, its id
# ENGINE:NAME (this computer's) or ENGINE:NAME@HOST (one on the SSH host
# HOST). A container's name holds neither : nor @, so the id parses one way,
# and it fits HOST_NAME: every list keyed by host (the picked ones, stars,
# hidden ones, the queue) takes it as it is. Talpy Den works in one through
# the engine's exec (over ssh for a host's, in that host's shared
# connection), as the container's own user, or (one that runs as root) the
# user VS Code's Dev Containers works as there, or you in a Toolbox or
# Distrobox, never as root from a label (talpy_den.container_user); nothing
# is installed in it.

CONTAINER = re.compile(r"^(docker|podman|nerdctl):([A-Za-z0-9][A-Za-z0-9_.-]*)(?:@(.+))?$")
CONTAINER_STATE_TIMEOUT = 15
# What a container is from one inspect: its id (a container made again has a
# new one), its state, its own user and labels (VS Code's user there). (The
# id in quotes as it is: Podman takes .Id for its .ID only on its own, not in
# {{json .Id}}.)
INSPECT_TEMPLATE = ('{"id":"{{.Id}}","state":{{json .State.Status}},"user":{{json .Config.User}},'
                    '"labels":{{json .Config.Labels}}}')


class Place:
    """Where an id points: an SSH host (host), or a container (engine, name)
    on this computer (host None) or on the SSH host host."""

    def __init__(self, ident, host, engine=None, name=None):
        self.id, self.host, self.engine, self.name = ident, host, engine, name

    @property
    def container(self):
        return self.engine is not None

    @property
    def label(self):
        """The name a message says: the host's, or foo / foo on HOST."""
        if not self.container:
            return self.host
        return f"{self.name} on {self.host}" if self.host else self.name

    @property
    def engine_title(self):
        return cs.ENGINE_TITLES.get(self.engine, self.engine)


def place(ident):
    """The Place of an id (check_host: one that could only be a name)."""
    ident = check_host(ident)
    m = CONTAINER.match(ident)
    if not m:
        if re.match(r"(docker|podman|nerdctl):", ident):
            raise ValueError(f"not a container: {ident!r}")
        return Place(ident, ident)
    engine, name, host = m.groups()
    if host is not None and (not HOST_NAME.match(host) or CONTAINER.match(host)):
        raise ValueError(f"not a container: {ident!r}")
    return Place(ident, host, engine, name)


def label(ident):
    """How a message names an SSH host or a container."""
    try:
        return place(ident).label
    except ValueError:
        return str(ident)


def containers_file():
    return cs.state_dir(cs.cache_dir(Path.home())) / "containers.json"


def change_containers_file(change):
    """change(saved) on containers.json (the users in containers, the hosts'
    container lists, which engine `docker` is), under a lock: two checks
    at once don't lose each other's (talpy_den.change_containers_file)."""
    cs.change_containers_file(cs.cache_dir(Path.home()), change)


def remember_users(found, inspected=False):
    """The user to work as in each container inspected (found: [{"id", "cid",
    "user", "own"}]), or each one listed's id (found: [{"id", "cid"}]): one
    listed with another id than the one kept was made again, and its user is
    asked anew."""
    def change(saved):
        users = saved.get("users") if isinstance(saved.get("users"), dict) else {}
        for c in found:
            cid, known = c.get("cid") or "", users.get(c["id"])
            if inspected:
                users[c["id"]] = {"cid": cid, "user": c.get("user") or "", "own": c["own"]}
            elif not (isinstance(known, dict) and known.get("cid") == cid):
                users[c["id"]] = {"cid": cid}
        saved["users"] = users
    try:
        change_containers_file(change)
    except OSError:
        pass


def vscode_allowed(ident, allow=False):
    """Whether a click on a chat may attach VS Code to the container ident
    (Dev Containers shares your SSH agent and Git credentials with it), or
    connect it to the SSH host ident (its VS Code server can read your
    clipboard and open links here): you said so for this very container (its
    id now: one made again with that name asks anew), or for that host;
    allow: you say so now, and it's kept."""
    p = place(ident)
    if p.container:
        try:
            found, _r = inspect(p)
        except (OSError, subprocess.TimeoutExpired, ValueError):
            found = None
        cid = found["cid"] if found else ""
    else:
        cid = "ssh"  # (a host's: kept by its name)

    def keep(saved):
        said = saved.get("vscode") if isinstance(saved.get("vscode"), dict) else {}
        said[ident] = cid
        saved["vscode"] = said
    if allow:
        if cid:
            try:
                change_containers_file(keep)
            except OSError:
                pass
        return True
    saved = cs.read_json(containers_file())
    said = saved.get("vscode") if isinstance(saved, dict) and isinstance(saved.get("vscode"), dict) else {}
    return bool(cid) and said.get(ident) == cid


def engine_line(p, args):
    """The command line running the engine with args where p's container is."""
    argv = [p.engine, *args]
    if p.host is None:
        return argv
    return ["ssh", *ssh_options(), "-T", p.host, posix(" ".join(shlex.quote(a) for a in argv))]


def inspect(p, timeout=CONTAINER_STATE_TIMEOUT):
    """(what one inspect of p's container says: {"state", "user", "cid"} or
    None, the CompletedProcess). The user it gives is kept (remember_users)."""
    args = ["container", "inspect", "--format", INSPECT_TEMPLATE, p.name]
    line = engine_line(p, args)
    if p.host is not None:  # (a Toolbox's user is you there: your name there comes along)
        line[-1] = posix(" ".join(shlex.quote(a) for a in [p.engine, *args]) + " && id -un")
    r = subprocess.run(line, stdin=subprocess.DEVNULL, capture_output=True, text=True, errors="replace",
                       timeout=timeout)
    lines = r.stdout.strip().splitlines()
    try:
        info = json.loads(lines[0]) if r.returncode == 0 and lines else None
    except ValueError:
        info = None
    if not isinstance(info, dict):
        return None, r
    labels = info.get("labels") if isinstance(info.get("labels"), dict) else {}
    own = info.get("user") if isinstance(info.get("user"), str) else ""
    you = (lines[-1].strip() if len(lines) > 1 else "") if p.host is not None else None
    found = {"id": p.id, "cid": info.get("id") or "", "user": cs.container_user(labels, own, you), "own": own,
             "state": (info.get("state") or "").lower()}
    remember_users([found], inspected=True)
    return found, r


def exec_user(p, fresh=False):
    """(the user to work as in p's container, "" for its own; whether it was
    known already). Known: from its last inspect (one kept by an older Talpy
    Den, without its own user, isn't); else (or fresh) one inspect says."""
    if not fresh:
        saved = cs.read_json(containers_file())
        users = saved.get("users") if isinstance(saved, dict) and isinstance(saved.get("users"), dict) else {}
        known = users.get(p.id)
        if isinstance(known, dict) and isinstance(known.get("user"), str) and isinstance(known.get("own"), str):
            return known["user"], True
    try:
        found, _r = inspect(p)
    except (OSError, subprocess.TimeoutExpired):
        found = None
    return (found["user"] if found else ""), False


def exec_line(p, command, user="", tty=False):
    """The engine's exec running command (POSIX shell) in p's container, as
    user; tty: in a terminal here (with its TERM), and an ssh that may ask."""
    argv = [p.engine, "exec", "-it" if tty else "-i"]
    if tty:
        argv += ["-e", "TERM", "-e", "COLORTERM"]
    if user:
        argv += ["-u", user]
    argv += [p.name, "sh", "-c", command]
    if p.host is None:
        return argv
    return ["ssh", *ssh_options(batch=not tty), "-t" if tty else "-T", p.host,
            posix(" ".join(shlex.quote(a) for a in argv))]


def run_on(ident, command, stdin=None, timeout=RUN_TIMEOUT, binary=False):
    """Run command (POSIX shell) on an SSH host or in a container (batch
    mode): the CompletedProcess. Output that isn't UTF-8 (a login script's
    greeting) can't break the answer; binary: stdin and the output are bytes.
    Past ANSWER_MAX of output, TooMuch (run_capped)."""
    p = place(ident)
    if not p.container:
        return run_capped(["ssh", *ssh_options(), "-T", p.host, posix(command)], stdin, timeout, binary)
    user, known = exec_user(p)
    r = run_capped(exec_line(p, command, user), stdin, timeout, binary)
    err = r.stderr if not binary else r.stderr.decode("utf-8", "replace")
    if known and r.returncode != 0 and "unable to find user" in err.lower():  # (made again since: ask anew)
        user, _known = exec_user(p, fresh=True)
        r = run_capped(exec_line(p, command, user), stdin, timeout, binary)
    return r


# What's read of a host's (or a container's) output, its stdout and its
# stderr each: a real answer has well under 1 MB (a busy host's status,
# 50 KB), and a host that sends more can't fill this computer's memory, or
# Talpy Den's cache with it (hosts/<host>.json, read at every start)
ANSWER_MAX = 16 << 20


class TooMuch(OSError):
    """A host's output went past ANSWER_MAX: the command there was ended (cant_run says so)."""


def run_capped(line, stdin=None, timeout=RUN_TIMEOUT, binary=False):
    """subprocess.run(line, input=stdin, capture_output=True, timeout=timeout,
    text=not binary, errors="replace"), reading at most ANSWER_MAX bytes of
    stdout and of stderr as they come: past that the command is ended, and
    TooMuch raised. (As subprocess's own: writes of PIPE_BUF a pipe takes
    in one go, so neither side waits on the other.)"""
    data = None if stdin is None else stdin if binary else stdin.encode("utf-8")
    proc = subprocess.Popen(line, stdin=subprocess.PIPE if data is not None else None,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    got, size = {proc.stdout: [], proc.stderr: []}, {proc.stdout: 0, proc.stderr: 0}
    sent, deadline = 0, time.monotonic() + timeout
    try:
        with selectors.DefaultSelector() as sel:
            sel.register(proc.stdout, selectors.EVENT_READ)
            sel.register(proc.stderr, selectors.EVENT_READ)
            if data:
                sel.register(proc.stdin, selectors.EVENT_WRITE)
            elif data is not None:
                proc.stdin.close()
            while sel.get_map():
                left = deadline - time.monotonic()
                if left <= 0:
                    raise subprocess.TimeoutExpired(line, timeout)
                for key, _ in sel.select(left):
                    f = key.fileobj
                    if f is proc.stdin:
                        try:
                            sent += os.write(f.fileno(), data[sent:sent + select.PIPE_BUF])
                        except BrokenPipeError:  # (it ended before it read it all)
                            sent = len(data)
                        if sent >= len(data):
                            sel.unregister(f)
                            f.close()
                        continue
                    chunk = os.read(f.fileno(), 1 << 16)
                    if not chunk:
                        sel.unregister(f)
                        continue
                    got[f].append(chunk)
                    size[f] += len(chunk)
                    if size[f] > ANSWER_MAX:
                        raise TooMuch(f"over {ANSWER_MAX >> 20} MB")
        proc.wait(max(0, deadline - time.monotonic()))
    except BaseException:  # (a timeout, too much, or SIGTERM: the widget gave up on it)
        proc.kill()
        proc.wait()
        raise
    finally:
        for f in (proc.stdin, proc.stdout, proc.stderr):
            try:
                if f is not None:
                    f.close()
            except OSError:
                pass
    stdout, stderr = b"".join(got[proc.stdout]), b"".join(got[proc.stderr])
    if not binary:  # (as text=True reads it: \r\n and \r are \n)
        stdout, stderr = (b.decode("utf-8", "replace").replace("\r\n", "\n").replace("\r", "\n") for b in (stdout, stderr))
    return subprocess.CompletedProcess(line, proc.returncode, stdout, stderr)


def container_problem(p, code, stderr):
    """(a sentence for why working in p's container failed, what it was:
    "stopped", "paused", "gone", "engine" or ""), or (None, "") when it
    isn't the container's (the ssh to its host, say)."""
    low = stderr.lower()
    title, where = p.engine_title, f" on {p.host}" if p.host else ""
    if p.host is not None and code == 255 and not any(s in low for s in ("container", "exec session")):
        return None, ""  # (ssh's own failure: its host's)
    if "is not running" in low or "state improper" in low or "exec sessions on running containers" in low:
        return f"{p.label} is stopped.", "stopped"
    if "is paused" in low:
        return f"{p.label} is paused ({p.engine} unpause {p.name}).", "paused"
    if "no such container" in low or "no container with name or id" in low:
        return f"There's no container {p.label} any more.", "gone"
    if "permission denied" in low and ("socket" in low or "daemon" in low):
        return f"You can't use {title}'s socket{where}: add yourself to its group (docker), then log in again.", "engine"
    if "cannot connect to the docker daemon" in low or "is the docker daemon running" in low \
            or "cannot connect to podman" in low:
        return f"{title} isn't running{where}.", "engine"
    if code == 127 and re.search(r"\b%s: (command )?not found" % re.escape(p.engine), low):
        return f"{title} isn't installed on {p.host}.", "engine"
    if re.search(r"""[`"']sh[`"']:? (executable file )?not found|executable file .sh. not found""", low):
        return f"{p.label} has no shell (sh); Talpy Den needs sh and python3 there.", ""
    if code == 127 or "python3: not found" in low or "python3: command not found" in low:
        return f"python3 isn't installed in {p.label}; Talpy Den needs it there.", ""
    if "unable to find user" in low:
        return f"{p.label}: {last_line(stderr)}", ""
    return None, ""


def paused_told(p, why, kind, stderr):
    """container_problem's (why, kind), a paused container told from a
    stopped one: Podman refuses an exec, or a start, of a paused one in a
    stopped one's words ("container state improper"), so then (only) an
    inspect tells."""
    if kind != "stopped" or "state improper" not in stderr.lower():
        return why, kind
    try:
        found, _ = inspect(p)
    except (OSError, subprocess.TimeoutExpired):
        found = None
    if found is not None and found["state"] == "paused":
        return f"{p.label} is paused ({p.engine} unpause {p.name}).", "paused"
    return why, kind


def container_state(ident):
    """(whether ident is a container that isn't running, a sentence why):
    (False, "") for a running one and for an SSH host."""
    p = place(ident)
    if not p.container:
        return False, ""
    try:
        found, r = inspect(p)
    except subprocess.TimeoutExpired:
        return True, f"{p.label} didn't answer within {CONTAINER_STATE_TIMEOUT} s."
    except OSError:
        return True, f"{p.engine_title} isn't installed here."
    if found is None:
        return True, explain(ident, r.returncode, r.stderr)
    if found["state"] in cs.CONTAINER_RUNNING:
        return (True, f"{p.label} is paused ({p.engine} unpause {p.name}).") if found["state"] == "paused" else (False, "")
    return True, f"{p.label} is stopped."


def start(ident):
    """Start a stopped container: (ok, message)."""
    p = place(ident)
    if not p.container:
        raise ValueError(f"not a container: {ident}")
    try:
        r = subprocess.run(engine_line(p, ["start", p.name]), stdin=subprocess.DEVNULL, capture_output=True,
                           text=True, errors="replace", timeout=RUN_TIMEOUT)
    except subprocess.TimeoutExpired:
        return False, f"{p.label} didn't start within {RUN_TIMEOUT} s"
    except OSError:
        return False, f"{p.engine_title} isn't installed here"
    if r.returncode != 0:
        return False, paused_told(p, *container_problem(p, r.returncode, r.stderr), r.stderr)[0] \
            or explain(ident, r.returncode, r.stderr)
    return True, f"Started {p.label}"


def attach(ident, command):
    """In this terminal: command (POSIX shell, e.g. claude --resume) in a
    terminal of its own in the container ident (exec -it, over ssh -t for
    one on an SSH host). A container that isn't running says so (exit 1)."""
    p = place(ident)
    if not p.container:
        raise ValueError(f"not a container: {ident}")
    try:
        found, r = inspect(p)
    except subprocess.TimeoutExpired:
        print(f"{p.label} didn't answer within {CONTAINER_STATE_TIMEOUT} s.")
        return 1
    except OSError:
        print(f"{p.engine_title} isn't installed here.")
        return 1
    if found is None:
        print(explain(ident, r.returncode, r.stderr))
        return 1
    if found["state"] not in cs.CONTAINER_RUNNING:
        print(f"{p.label} is stopped. Start it with Start in Talpy Den, or: {p.engine} start {p.name}")
        return 1
    line = exec_line(p, command, found["user"], tty=True)
    sys.stdout.flush()
    os.execvp(line[0], line)


def attach_line(ident, command):
    """The terminal's command line for a command in a container (attach)."""
    return " ".join(shlex.quote(a) for a in [sys.executable or "python3", "-I", str(HERE / "remote.py"),
                                             "--attach", ident, command])


# ---------------------------------------------------------------- container lists


def picked_names(picked, host=None):
    """The picked containers of one place (host None: this computer), as
    talpy_den.list_containers takes them (engine:name)."""
    out = []
    for ident in picked:
        m = CONTAINER.match(ident)
        if m and m.group(3) == host:
            out.append(m.group(1) + ":" + m.group(2))
    return out


def containers_here(days=cs.CONTAINER_DAYS, picked=()):
    """This computer's containers (talpy_den.list_containers): {"containers", "notes"}."""
    found = cs.list_containers(cs.cache_dir(Path.home()), Path.home(), days, picked_names(picked))
    remember_users(found["containers"])
    return found


def host_containers(host, days=cs.CONTAINER_DAYS, picked=()):
    """An SSH host's containers, listed there (talpy_den.py --list-containers):
    {"ok", "host", "containers", "notes", "at"} (their ids end in @host), kept
    for the next start (cached_host_containers), or {"ok": False, "error"}."""
    host = check_host(host)
    if CONTAINER.match(host):
        raise ValueError(f"not an SSH host: {host}")
    names = picked_names(picked, host)
    answer = host_answer(host, ["--list-containers", str(days)] + (["--picked", ",".join(names)] if names else []))
    if not answer["ok"]:
        return {"ok": False, "host": host, "error": answer["message"] or f"{host} couldn't list its containers"}
    listed = answer.get("containers") if isinstance(answer.get("containers"), list) else []
    found = [host_container(dict(c, id=c["id"] + "@" + host), host) for c in listed
             if isinstance(c, dict) and isinstance(c.get("id"), str)]
    out = {"containers": [c for c in found if c],
           "notes": [n for n in answer.get("notes") or [] if isinstance(n, dict)],
           "at": int(time.time() * 1000)}
    remember_users(out["containers"])

    def keep(saved):
        hosts = saved.get("hosts") if isinstance(saved.get("hosts"), dict) else {}
        hosts[host] = out
        saved["hosts"] = hosts
    try:
        change_containers_file(keep)
    except OSError:
        pass
    return {"ok": True, "host": host, **out}


def host_container(c, host):
    """One of an SSH host's containers as its list says (its id
    ENGINE:NAME@host), with its engine and name from that id; None for one
    whose id isn't a container of host's (an SSH destination such as root@lab,
    a container on another host): a host's list names its own containers only."""
    m = CONTAINER.fullmatch(c.get("id")) if isinstance(c, dict) and isinstance(c.get("id"), str) else None
    if not m or m.group(3) != host:
        return None
    return dict(c, engine=m.group(1), name=m.group(2), host=host)


def cached_host_containers():
    """The SSH hosts' container lists as they were last fetched: {host: {"containers", "notes", "at"}}."""
    saved = cs.read_json(containers_file())
    hosts = saved.get("hosts") if isinstance(saved, dict) else None
    out = {}
    for h, v in hosts.items() if isinstance(hosts, dict) else ():
        if isinstance(v, dict) and HOST_NAME.match(h) and not CONTAINER.match(h):
            found = [host_container(c, h) for c in v["containers"]] if isinstance(v.get("containers"), list) else []
            out[h] = dict(v, containers=[c for c in found if c])
    return out


def hosts_and_containers(days=cs.CONTAINER_DAYS, picked=(), containers=True):
    """--hosts: ~/.ssh/config's hosts, this computer's containers (unless
    not containers: then no engine is asked anything) and the hosts' last
    container lists."""
    out = {"ok": True, "hosts": ssh_hosts(), "containers": [], "notes": [], "hostContainers": {}}
    if containers:
        out.update(containers_here(days, picked))
        out["hostContainers"] = cached_host_containers()
    return out


def explain(host, code, stderr):
    """A sentence for why talking to host (or working in a container) failed."""
    text = stderr.strip()
    last = text.splitlines()[-1] if text else ""
    low = text.lower()
    p = place(host)
    if p.container:
        why, _kind = container_problem(p, code, stderr)
        if why:
            return why
        if p.host is None:
            return f"{p.label}: {last}" if last else f"{p.label}: {p.engine} exec failed (exit {code})"
        host = p.host  # (else it's the ssh to its host that failed)
    if "host key verification failed" in low or "no matching host key" in low:
        return f"{host}'s host key isn't known yet. Run ssh {host} once in a terminal to accept it."
    if "permission denied" in low or "too many authentication failures" in low:
        return f"{host} refused the login. Talpy Den can't type a password: load your key into the agent (ssh-add) or run ssh {host} once in a terminal."
    if "could not resolve hostname" in low or "name or service not known" in low:
        return f"Can't find {host} (DNS). Are you on the right network or VPN?"
    if any(s in low for s in ("connection timed out", "operation timed out", "no route to host",
                              "network is unreachable", "connection refused", "connection closed by")):
        return f"Can't reach {host}: {last}"
    if code == 127 or "python3: command not found" in low or "python3: not found" in low:
        return f"python3 isn't installed on {host}; Talpy Den needs it there."
    return f"{host}: {last}" if last else f"{host}: ssh failed (exit {code})"


def status(host, *args, **kw):
    """The widget's status of host (host_status's), its chats put in the jobs file too."""
    out = host_status(host, *args, **kw)
    publish_host_jobs(out)
    return out


def publish_host_jobs(out):
    """A host's or container's chats in the jobs file (talpy_den.py's, for other programs), on this
    computer's clock; none while it can't be reached (a check that failed)."""
    try:
        p, now = place(out["host"]), int(time.time() * 1000)
        result = out.get("result") if out.get("ok") else None
        jobs = None
        if isinstance(result, dict):
            offset = now - (cs.number(result.get("generatedAt")) or now)   # (as remember_answer has it)
            jobs = cs.place_jobs(result.get("groups"), p.id, p.engine if p.container else "ssh", offset)
        cache = cs.cache_dir(Path.home())
        cs.publish_jobs(cs.jobs_file_path(Path.home(), cache), cache, p.id, jobs, now)
    except (OSError, ValueError, TypeError, KeyError):
        pass


def host_status(host, done_hours=None, recent=None, tokens=True, usage_refresh=None, plans=None, memories=None):
    """The widget's status of host, as talpy_den.py --remote prints it there."""
    host = check_host(host)
    args = ["--remote"]
    if done_hours is not None:
        args += ["--done-hours", str(done_hours)]
    if recent is not None:
        args += ["--recent", str(recent)]
    if plans is not None:
        args += ["--plans", str(plans)]
    if memories is not None:
        args += ["--memories", str(memories)]
    if not tokens:
        args.append("--no-tokens")
    if usage_refresh is not None:  # (the host's accounts' plan usage, fetched there)
        args += ["--usage-refresh", str(usage_refresh)]
    stars = cs.starred_of(cs.load_stars(cs.cache_dir(Path.home())), host)  # (the stars are kept here)
    for kind in cs.STAR_KINDS:
        if stars[kind]:
            args += [f"--starred-{kind}", ",".join(sorted(stars[kind]))]
    # (its chats that keep going are kept here too: listed there while they do, and how each stands)
    kept = [k for k in cs.load_keep(cs.cache_dir(Path.home()))["chats"] if k["host"] == host and "/" not in k["profile"]]
    if kept:
        args += ["--kept-chats", ",".join(f"{k['chat']}/{k['profile']}" for k in kept)]
    # (and the Recap's history setting: the plan windows that ended kept there follow it, as here)
    keep, since = cs.history_setting(cs.cache_dir(Path.home()))
    if not keep:
        args.append("--no-history")
    elif since:
        args += ["--history-since", str(since)]
    started, p = time.time(), place(host)
    try:
        r = ssh(host, "python3 -I - " + " ".join(shlex.quote(a) for a in args), host_script(), STATUS_TIMEOUT)
    except subprocess.TimeoutExpired:
        return {"ok": False, "host": host, "error": f"{p.label} didn't answer within {STATUS_TIMEOUT} s."}
    except OSError as exc:
        return {"ok": False, "host": host, "error": cant_run(p, exc)}
    elapsed = int((time.time() - started) * 1000)
    if "\n" + cs.REMOTE_MARK not in r.stdout:
        why, kind = paused_told(p, *container_problem(p, r.returncode, r.stderr), r.stderr) if p.container else (None, "")
        # (only ssh's own failure asks for a login: not the engine's "permission denied" on its socket there)
        login = p.host is not None and r.returncode == 255 and needs_login(r.stderr) and not why
        out = {"ok": False, "host": host, "error": why or explain(host, r.returncode, r.stderr), "elapsedMs": elapsed,
               "login": login}
        if kind in ("stopped", "paused", "gone"):  # (stopped: Start, and no checks until then; gone; paused)
            out[kind] = True
        return out
    result = answer_after_mark(r.stdout)
    if result is None:
        return {"ok": False, "host": host, "error": f"{p.label} sent an answer Talpy Den can't read.", "elapsedMs": elapsed}
    if not result.get("ok"):
        return {"ok": False, "host": host, "error": f"{p.label}: {result.get('error') or 'status failed'}", "elapsedMs": elapsed}
    out = {"ok": True, "host": host, "result": chats_with_ids(result), "elapsedMs": elapsed,
           "loggedIn": p.host is not None and logged_in(p.host)}
    remember_answer(host, out)
    try:  # (its chats Claude moved to the background there under a new id: their stars, keeping going and go-ons follow)
        cs.follow_host_moves(cs.cache_dir(Path.home()), host, result.get("moved"), stars, kept)
    except (OSError, ValueError):
        pass
    return out


def chats_with_ids(result):
    """A host's answer without its chats whose id isn't a chat's (cs.valid_id;
    none yet, a chat just starting, stays): the front ends pass a chat's
    sessionId and chatId on as words of command lines here, and a host's
    "--screenshot" was taken for that flag."""
    def plain(s):
        return isinstance(s, dict) and all(s.get(k) in (None, "") or cs.valid_id(s[k]) for k in ("sessionId", "chatId"))
    for g in result.get("groups") if isinstance(result.get("groups"), list) else []:
        for key in ("sessions", "recent", "starred"):
            if isinstance(g, dict) and isinstance(g.get(key), list):
                g[key] = [s for s in g[key] if plain(s)]
    return result


# Each host's and container's last answer, kept for the next start: the
# widget shows it at once (dimmed, "updated 3 min ago") while its first check
# runs. In Talpy Den's cache folder, private to you (its chats are in it).
ANSWERS_DIR = "hosts"


def answer_file(host):
    return cs.cache_dir(Path.home()) / ANSWERS_DIR / (check_host(host) + ".json")


def remember_answer(host, out):
    """Keep host's answer (and how far its clock is from this one's) for --last."""
    try:
        path = answer_file(host)
        cs.private_dir(path.parent)
        result = out.get("result") or {}
        offset = int(time.time() * 1000) - (result.get("generatedAt") or int(time.time() * 1000))
        cs.write_json_atomic(path, {"at": int(time.time() * 1000), "offset": offset, "answer": out})
        os.chmod(str(path), 0o600)
    except (OSError, ValueError, TypeError):
        pass


def last_answers(hosts):
    """The last answer kept for each of hosts that has one:
    {host: {"at": when, "offset": its clock's distance from this one's (ms), "answer": as --status gave it}}."""
    out = {}
    for host in hosts:
        try:
            # (kept as JSON, an answer may take 3 times its size, \uXXXX; one bigger was kept before ANSWER_MAX)
            if answer_file(host).stat().st_size > 3 * ANSWER_MAX:
                continue
            saved = cs.read_json(answer_file(host))
        except (OSError, ValueError):
            continue
        if isinstance(saved, dict) and isinstance(saved.get("answer"), dict) and saved["answer"].get("ok"):
            if isinstance(saved["answer"].get("result"), dict):  # (one kept before ids were checked, too)
                chats_with_ids(saved["answer"]["result"])
            out[host] = {"at": saved.get("at") or 0, "offset": saved.get("offset") or 0, "answer": saved["answer"]}
    return out


def cant_run(p, exc):
    """Why the engine (or ssh) couldn't run at all."""
    if isinstance(exc, TooMuch):
        return f"{p.label} sent too much ({exc}): Talpy Den stopped reading it."
    if p.container and p.host is None:
        return f"{p.engine_title} isn't installed here." if isinstance(exc, FileNotFoundError) else f"Can't run {p.engine}: {exc}"
    return f"Can't run ssh: {exc}"


def last_line(text):
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    return lines[-1] if lines else ""


def outcome(host, r):
    """(ok, message) of a command run on host: its last line of output, or
    why it failed. Only stdout says how it went: the host's shell may print
    warnings on stderr (e.g. about a missing locale) after it."""
    if r.returncode != 0:
        p = place(host)
        if r.returncode == 255 or (p.container and container_problem(p, r.returncode, r.stderr)[0]):
            return False, explain(host, r.returncode, r.stderr)
        return False, last_line(r.stderr) or last_line(r.stdout) or f"exit {r.returncode}"
    return True, last_line(r.stdout) or "Done"


def run(host, command, stdin=None):
    """Run a shell command on host; (ok, last line of its output)."""
    p = place(host)
    try:
        r = ssh(host, command, stdin)
    except subprocess.TimeoutExpired:
        return False, f"{p.label} didn't answer within {RUN_TIMEOUT} s"
    except OSError as exc:
        return False, cant_run(p, exc)
    return outcome(host, r)


def host_answer(host, args, name="talpy_den.py", also=(), timeout=RUN_TIMEOUT):
    """Run a script of this folder on host with args (it goes to python3's
    stdin, as for --status): its answer, {"ok", "message", ...}; "reached":
    False when the host (or the container) couldn't be reached, not when
    the script there said no or took too long (it got there: ssh gives up on
    a host it can't reach well before, ConnectTimeout and ServerAlive*), so
    it may have done it (a queued go-on starts again once it answers:
    jump.start_queued, talpy_den.requeue_reached). Your own text in args
    (TEXT_ARGS) goes on the stdin too, before the script, not in ssh's
    command (with_texts)."""
    host = check_host(host)
    args = list(args)
    script, args = with_texts(host_script(name, also), args)
    command = "python3 -I - --remote " + " ".join(shlex.quote(a) for a in args)
    p = place(host)
    try:
        r = ssh(host, command, script, timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "message": f"{p.label} didn't answer within {timeout} s"}
    except OSError as exc:
        return {"ok": False, "reached": False, "message": cant_run(p, exc)}
    answer = answer_after_mark(r.stdout)
    if answer is not None:
        return {**answer, "ok": bool(answer.get("ok")), "message": answer.get("message") or ""}
    ok, message = outcome(host, r)
    if ok:  # it ran, but didn't answer as the script does
        return {"ok": False, "message": f"{p.label} sent an answer Talpy Den can't read."}
    # (ssh couldn't connect, or the container isn't running: not what the script said)
    unreached = r.returncode == 255 or (p.container and container_problem(p, r.returncode, r.stderr)[0])
    return {"ok": False, "message": message, **({"reached": False} if unreached else {})}


# Your own text for a host's script, a reply, a task's prompt, a note or
# answers: a command is seen in the process list by every user of the host
# (sh -c there) and of this computer (ssh's), the stdin isn't; it holds any
# length too (one argument of a command holds 128 KiB at most), and a login
# shell there never reads it.
TEXT_ARGS = ("--text", "--prompt", "--note", "--answers", "--message")


def with_texts(script, args):
    """(script, args) for python3 -I - --remote on a host: with a TEXT_ARGS
    value in args, the args without those texts, and the script after a line
    that gives it all its args there (Python 3.7's too), in ASCII: before
    3.10, Python reading its script from stdin misreads a long line of other
    characters (a reply in Japanese: "SyntaxError: Non-UTF-8 code")."""
    texts = {i for i in range(1, len(args)) if args[i - 1] in TEXT_ARGS}
    if not texts:
        return script, args
    shown = [a for i, a in enumerate(args) if i not in texts and i + 1 not in texts]
    return "import sys; sys.argv[1:] = %s\n" % ascii(["--remote", *args]) + script, shown


def run_status_script(host, args):
    """Run talpy_den.py on host with args: (ok, its message)."""
    answer = host_answer(host, args)
    return answer["ok"], answer["message"]


def vscode_account(host, config_dir):
    """Have VS Code's Claude on host run on the account whose folder is
    config_dir there (None: a plain ~/.claude), in the settings of its VS Code
    server, which windows connected to the host read: (ok, message)."""
    server = cs.VSCODE_SERVERS.get(cs.vscode_app()[1] or "", cs.VSCODE_SERVERS["Code"])
    return run_status_script(host, ["--vscode-account", config_dir or "-", "--vscode-server", server])


def dismiss(host, session_id=None):
    """Hide a finished chat in the host's list (or show all again)."""
    return run_status_script(host, ["--dismiss", session_id] if session_id else ["--undismiss-all"])


def hide(host, kind, item_id=None):
    """Hide a chat, plan, memory or project in the host's lists (kept on the
    host, as its status leaves them out there), or show that kind again."""
    return run_status_script(host, ["--hide", kind, item_id] if item_id is not None else ["--show-hidden", kind])


def delete(host, kind, item, profile=None, describe=False):
    """Delete a chat, a plan or a memory of host (kind chat, plan, memory)
    to the host's Trash, or (describe) say what would go (sharing.delete
    there): its answer. Its stars and queued tasks, kept here, forget it
    (a plan's question says its queued tasks go too)."""
    args = ["--delete-" + kind, item] + (["--profile", profile] if profile else []) + (["--describe"] if describe else [])
    answer = host_answer(host, args, "sharing.py", also=("accounts.py",))
    if describe and kind == "plan" and isinstance(answer.get("question"), str):
        more = cs.plan_tasks_go(cs.queued_for_plan(cs.cache_dir(Path.home()), item, host))
        if more and answer.get("message") == answer["question"]:
            answer["message"] += more
        answer["question"] += more
    if answer["ok"] and not describe:
        cs.forget_deleted(cs.cache_dir(Path.home()), {"chat": "chats", "plan": "plans"}.get(kind, "memories"), item, host)
    return answer


def end(host, session_id, profile=None, busy=False):
    """Stop a chat that runs on host (talpy_den.stop_chat); only an idle one unless busy."""
    return run_status_script(host, ["--end", session_id] + (["--profile", profile] if profile else [])
                             + (["--busy"] if busy else []))


def end_args(args):
    """--end's words (HOST SESSION_ID [PROFILE]) and the chat --keep-off names ("" if none)."""
    words, keep_off, rest = [], "", list(args)
    while rest:
        a = rest.pop(0)
        if a == "--keep-off" and rest and cs.valid_id(rest[0]):
            keep_off = rest.pop(0)
        elif a != "--busy":
            words.append(a)
    return words, keep_off


def interrupt(host, session_id, profile=None):
    """Interrupt a working chat in tmux on host, or a background one there (talpy_den.interrupt_chat_by_id)."""
    return run_status_script(host, ["--interrupt", session_id] + (["--profile", profile] if profile else []))


def agent_run(host, chat_id, agent_id, profile=None, open_it=True):
    """A chat's subagent on host: its run (talpy_den.agent_run there),
    saved here as Markdown and opened, as jump.show_agent_run does for one
    here: (ok, message, file)."""
    p = place(host)
    import jump
    args = ["--remote", "--agent-run", agent_id, "--chat", chat_id] + (["--profile", profile] if profile else [])
    try:
        r = ssh(host, "python3 -I - " + " ".join(shlex.quote(a) for a in args), host_script())
    except subprocess.TimeoutExpired:
        return False, f"{p.label} didn't answer within {RUN_TIMEOUT} s", None
    except OSError as exc:
        return False, cant_run(p, exc), None
    if "\n" + cs.REMOTE_MARK not in r.stdout:
        return False, explain(host, r.returncode, r.stderr), None
    answer = answer_after_mark(r.stdout)
    if answer is None:
        return False, f"{p.label} sent an answer Talpy Den can't read.", None
    if not answer.get("ok") or not isinstance(answer.get("markdown"), str):
        return False, f"{p.label}: {answer.get('message') or 'no such subagent'}", None
    path = jump.save_run(Path.home(), answer.get("title"), agent_id, answer["markdown"])
    if open_it:
        ok, why = jump.open_markdown(path)
        if not ok:
            return False, why, str(path)
    return True, f"{answer.get('message')} {where(host)}", str(path)


def share(host, chat_id, profile=None):
    """Share a chat with every account on host (sharing.py there), from
    profile's copy if given."""
    answer = host_answer(host, ["--share", chat_id] + (["--profile", profile] if profile else []), "sharing.py")
    return answer["ok"], answer["message"]


def unshare(host, chat_id, profile):
    """Keep a shared chat of host only on profile; the host's other accounts lose it."""
    answer = host_answer(host, ["--unshare", chat_id, "--profile", profile], "sharing.py")
    return answer["ok"], answer["message"]


def continue_on(host, chat_id, profile, open_it=True, end_first=False):
    """Continue a chat of host on another account there: shared with it if
    needed, then reopened in a local terminal (ssh -t), or, without open_it,
    the command that reopens it there: (ok, message, command). end_first: an
    idle session that has it open there quits first (talpy_den.end_for_handover)."""
    answer = host_answer(host, ["--continue", chat_id, "--profile", profile] + (["--end-first"] if end_first else []),
                         "sharing.py")
    if not answer["ok"]:
        return False, answer["message"], None
    command = answer.get("command")
    if not isinstance(command, str) or not command:
        return False, f"{label(host)} didn't say how to reopen it", None
    if not open_it:
        return True, answer["message"], command
    ok, message = open_remote(host, command)
    return ok, message, command


def find(host, query):
    """The chats on host with every word of query (talpy_den.find_chats
    there), each with the command that reopens it there."""
    answer = host_answer(host, ["--find", query])
    return {**answer, "results": answer.get("results") or [], "more": bool(answer.get("more"))}


def plan_text(host, slug, profile=None):
    """A plan of host: {"ok", "title", "markdown", "where"} (talpy_den.plan_markdown there)."""
    return host_answer(host, ["--plan-text", slug] + (["--profile", profile] if profile else []))


def open_plan(host, slug, profile=None, open_it=True):
    """A plan of host, saved here as Markdown (a copy) and opened: (ok, message, file)."""
    import jump
    answer = plan_text(host, slug, profile)
    if not answer.get("ok") or not isinstance(answer.get("markdown"), str):
        return False, answer.get("message") or f"{label(host)} doesn't have that plan", None
    folder = jump.runs_folder(Path.home())
    # (the slug comes from the host's or container's answer: only safe characters go in a file name here)
    safe = lambda text: re.sub(r"[^A-Za-z0-9_.-]", "_", text).lstrip(".")
    path = folder / f"plan-{safe(host)}-{safe(slug)}.md"
    with open(path, "w", encoding="utf-8") as f:
        f.write(answer["markdown"])
    if open_it:
        ok, why = jump.open_markdown(path)
        if not ok:
            return False, why, str(path)
    return True, f"Opened the plan {answer.get('title') or slug} from {label(host)} (a copy)", str(path)


def plan_sharing(host, slug, profile, share_it, to=None):
    """Share a plan of host with its other accounts (or keep it on profile only), there."""
    args = (["--share-plan", slug] if share_it else ["--unshare-plan", slug]) + ["--profile", profile] \
        + (["--to", to] if to else [])
    answer = host_answer(host, args, "sharing.py")
    return answer["ok"], answer["message"]


def move_plan(host, slug, profile, into=None, back=False, setting=True, if_exists=None, describe=False):
    """Move a plan of host into a project's plans folder there, or back into
    the account's (sharing.move_plan there), or (describe) say what that
    would do: its answer. A starred one (the stars are kept here) stays
    starred under the name it gets, and a queued task (kept here too) takes
    it by that name."""
    args = ["--move-plan", slug, "--profile", profile] + (["--into", into] if into else []) \
        + (["--back"] if back else []) + ([] if setting else ["--no-setting"]) \
        + (["--if-exists", if_exists] if if_exists else []) + (["--describe"] if describe else [])
    answer = host_answer(host, args, "sharing.py", also=("accounts.py",))
    if answer["ok"] and not describe and isinstance(answer.get("slug"), str) and cs.PLAN_SLUG.match(answer["slug"]):
        import jump
        jump.follow_plan(cs.cache_dir(Path.home()), slug, answer["slug"], host)
    return answer


def task(host, profile, folder, text="", plan=None, plan_profile=None, background=False, open_it=True,
         model=None, effort=None, mode=None):
    """A new chat on host's profile in folder there, with a task (and that
    model, effort and permission mode): in the background there, or in a terminal here (ssh
    -t), or (without open_it) the command that starts it there. {"ok",
    "message", "id" | "command"}."""
    args = ["--start-task" if background else "--task-command", folder or "~", "--profile", profile]
    if text:
        args += ["--prompt", text]
    if plan:
        args += ["--plan", plan] + (["--plan-profile", plan_profile] if plan_profile else [])
    if model:
        args += ["--model", model]
    if effort:
        args += ["--effort", effort]
    if mode:
        args += ["--permission-mode", mode]
    answer = host_answer(host, args)
    if background or not answer["ok"]:
        return answer
    command = answer.get("command")
    if not isinstance(command, str) or not command:
        return {"ok": False, "message": f"{label(host)} didn't say how to start it"}
    if not open_it:
        return {"ok": True, "message": "", "command": command}
    ok, message = open_remote(host, command)
    return {"ok": ok, "message": message}


# A picture pasted here for a task there goes to the host's pictures folder
# (talpy_den.images_dir there: its XDG_CACHE_HOME or ~/.cache), on python3's
# stdin. Pictures older than IMAGES_KEEP_DAYS go, as here.
PUT_IMAGE = """
import json, os, sys, time
from pathlib import Path
name, stem = sys.argv[1], sys.argv[1].rsplit(".", 1)
folder = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "talpy-den" / "images"
folder.mkdir(parents=True, exist_ok=True)
folder.chmod(0o700)
for old in folder.iterdir():
    try:
        if old.stat().st_mtime < time.time() - %d * 86400:
            old.unlink()
    except OSError:
        pass
n = 1
while True:
    path = folder / (name if n == 1 else "%%s-h%%d.%%s" %% (stem[0], n, stem[1]))
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        break
    except FileExistsError:
        n += 1
with os.fdopen(fd, "wb") as f:
    f.write(sys.stdin.buffer.read())
sys.stdout.write("\\n%s " + json.dumps({"ok": True, "message": "", "path": str(path)}) + "\\n")
""" % (cs.IMAGES_KEEP_DAYS, cs.REMOTE_MARK)
PICTURE_NAME = re.compile(r"^[0-9]{8}-[0-9]{6}(-[0-9]+)?\.(png|jpg|webp|gif)$")


def put_image(host, path):
    """Copy a picture pasted here (jump.py --paste-image) to host, for a task
    there: {"ok", "message", "path": the copy there, "local": path}."""
    p, picture = place(host), Path(path)
    if picture.parent != cs.images_dir(Path.home()) or not PICTURE_NAME.match(picture.name) or not picture.is_file():
        return {"ok": False, "message": "That isn't a picture pasted into a task"}
    command = "python3 -I -c " + shlex.quote(PUT_IMAGE) + " " + shlex.quote(picture.name)
    try:
        r = run_on(host, command, picture.read_bytes(), binary=True)
    except subprocess.TimeoutExpired:
        return {"ok": False, "message": f"{p.label} didn't answer within {RUN_TIMEOUT} s"}
    except OSError as exc:
        return {"ok": False, "message": cant_run(p, exc)}
    r = subprocess.CompletedProcess(r.args, r.returncode, r.stdout.decode("utf-8", "replace"),
                                    r.stderr.decode("utf-8", "replace"))
    answer = answer_after_mark(r.stdout)
    if answer is not None and answer.get("path"):
        return {"ok": True, "message": "", "path": answer["path"], "local": str(picture)}
    ok, message = outcome(host, r)
    return {"ok": False, "message": f"{label(host)} sent an answer Talpy Den can't read." if ok else message}


def continue_chat(host, profile, chat_id, folder="", text="", ends_at=None, force=False):
    """Go on with host's chat a usage limit stopped, in the background there
    (talpy_den.continue_chat; ends_at: how long it waits for the chat's
    background commands; force: whatever its newest turn, a chat that keeps
    going whose turn broke off): {"ok", "message", "id"} (or "waits", "ended")."""
    args = ["--continue-chat", chat_id, "--profile", profile]
    if force:
        args.append("--force")
    if folder:
        args += ["--folder", folder]
    if text:
        args += ["--prompt", text]
    if ends_at is not None:
        args += ["--ends-at", str(int(ends_at))]
    return host_answer(host, args)


ACCOUNT_ACTIONS = ("--list", "--add", "--login", "--logout", "--remove", "--command", "--no-command", "--default")


def accounts(host, args):
    """accounts.py on host with args: its answer. A login (--add, --login)
    opens a terminal here running it there over ssh, unless --print-command
    asks for the command itself (the VS Code extension runs it in its own)."""
    if not args or args[0] not in ACCOUNT_ACTIONS:
        raise ValueError("not an accounts.py action: " + (args[0] if args else "none"))
    printing = "--print-command" in args
    args = [a for a in args if a != "--print-command"]
    answer = host_answer(host, args, "accounts.py")
    command = answer.pop("command", None)
    if not answer["ok"] or not isinstance(command, str) or not command:
        return answer
    if printing:
        return {**answer, "command": command}
    ok, message = open_remote(host, command)
    return {**answer, "ok": ok, "message": answer["message"] if ok else message}


def open_remote(host, command):
    """A local terminal running command on host (ssh -t: Claude needs a terminal).
    Not in batch mode: ssh may ask for a password or host key there."""
    p = place(host)
    import jump
    if p.container:  # (attach says so in the terminal when it isn't running)
        line = attach_line(host, command)
    else:
        line = " ".join(shlex.quote(a) for a in ["ssh", *ssh_options(batch=False), "-t", host, posix(command)])
    if not jump.open_terminal(str(Path.home()), line):
        return False, "No terminal found to open the chat in"
    return True, f"Opened a terminal {where(host)}"


def where(ident):
    """on HOST, in foo, in foo on HOST."""
    p = place(ident)
    return f"in {p.label}" if p.container else f"on {p.host}"


def needs_login(stderr):
    """Whether logging in once in a terminal (--login) would let the checks
    through: the host wants a password, a passphrase or a key the agent
    doesn't hold, or its host key isn't known yet."""
    low = stderr.lower()
    return any(s in low for s in ("permission denied", "too many authentication failures",
                                  "host key verification failed"))


def login_marker(host):
    """A file next to the shared connections saying you logged in to host
    through the widget (so it offers to disconnect), or None."""
    d = control_dir()
    return d / f"{check_host(host)}.login" if d else None


def logged_in(host):
    """Whether you logged in to host with --login and that connection is still open."""
    marker = login_marker(host)
    if marker is None or not marker.exists():
        return False
    try:
        r = subprocess.run(["ssh", *ssh_options(), "-O", "check", host], capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


def ssh_host_of(ident):
    """The SSH host an id reaches through: the host, or a container's host
    (a login there is that host's). This computer's containers have none."""
    p = place(ident)
    if p.host is None:
        raise ValueError(f"{p.label} is a container on this computer: there's nothing to log in to")
    return p.host


def login(host):
    """A terminal where you log in to host for the widget (login_here); for
    a container on an SSH host, to that host."""
    host = ssh_host_of(host)
    import jump
    line = " ".join(shlex.quote(a) for a in [sys.executable or "python3", "-I", str(HERE / "remote.py"),
                                             "--login-here", host])
    # (the window closes by itself once you're in; it stays when it failed)
    if not jump.open_terminal(str(Path.home()), line + " && exit"):
        return False, "No terminal found to log in"
    return True, f"Log in to {host} in the terminal"


def login_here(host):
    """Log in to host in this terminal: ssh asks for the password (passphrase,
    code, host key) itself, so it goes to ssh only. The connection stays as
    the one the checks share. Host keys are checked as always. Exit status:
    ssh's, or 1 when there's no private folder for the connection."""
    host = ssh_host_of(host)
    d = control_dir()
    if d is None:
        print("There's no private folder for the shared connection ($XDG_RUNTIME_DIR), so Talpy Den can't keep a login.")
        return 1
    print(f"Logging in to {host} for Talpy Den. Type what ssh asks for (password, passphrase, code):")
    print("it goes to ssh only, Talpy Den never sees it.\n")
    # The window closes once you're in, and what's left of its session gets
    # SIGHUP: the shared connection detaches from it, but the connection to a
    # jump host it goes through (ProxyJump) doesn't, and ended there (the
    # next check needed a new login). Ignored here, it's ignored there too.
    hup = signal.signal(signal.SIGHUP, signal.SIG_IGN)
    # ssh takes an option's first value: these go before the shared ones
    try:
        r = subprocess.run(["ssh", "-o", "ControlMaster=auto", "-o", f"ControlPersist={LOGIN_MINUTES}m",
                            "-o", "ForwardAgent=no", "-o", "ForwardX11=no",  # (whatever ~/.ssh/config says)
                            *ssh_options(batch=False), "-T", host, posix("true")])
    except OSError as exc:
        print(f"Can't run ssh: {exc}")
        return 1
    finally:
        signal.signal(signal.SIGHUP, hup)
    if r.returncode != 0:
        print(f"\nThe login to {host} didn't work (ssh exit {r.returncode}).")
        return r.returncode
    marker = login_marker(host)
    marker.touch(mode=0o600)
    os.chmod(str(marker), 0o600)
    print(f"\nLogged in. Talpy Den checks {host} through this connection now. It closes {LOGIN_MINUTES} minutes "
          "after Talpy Den stops using it, when you log out, or when you disconnect.")
    time.sleep(LOGIN_SHOWN)
    return 0


def disconnect(host):
    """Close the shared connection to host (the one you logged in with):
    nothing new can use it (ssh -O stop), and it ends with the last terminal
    open over it (-O exit would end those too). A container's: its host's."""
    host = ssh_host_of(host)
    marker = login_marker(host)
    if marker is not None:
        try:
            marker.unlink()
        except FileNotFoundError:
            pass
    try:
        r = subprocess.run(["ssh", *ssh_options(), "-O", "stop", host], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"Can't close the connection to {host}: {exc}"
    return True, f"Disconnected from {host}" if r.returncode == 0 else f"No open connection to {host}"


USAGE = __doc__.split("\n\n")[1]


def list_options(args):
    """--hosts' and --containers' options: --container-days N, --picked IDS, --no-containers."""
    kw, rest = {"days": cs.CONTAINER_DAYS, "picked": [], "containers": True}, list(args)
    while rest:
        arg = rest.pop(0)
        if arg == "--container-days" and rest and rest[0].isdigit():
            kw["days"] = int(rest.pop(0))
        elif arg == "--picked" and rest:
            kw["picked"] = [i for i in rest.pop(0).split(",") if i]
        elif arg == "--no-containers":
            kw["containers"] = False
        else:
            sys.exit(USAGE)
    return kw


def stop_on_term(signum, frame):
    """A widget that gives up on a check (or is turned off) ends it with
    SIGTERM: exiting through Python lets subprocess.run end its ssh too."""
    sys.exit(128 + signum)


def main(argv=None):
    args = sys.argv[1:] if argv is None else list(argv)
    if not args:
        sys.exit(USAGE)
    signal.signal(signal.SIGTERM, stop_on_term)
    action, args = args[0], args[1:]
    try:
        if action == "--hosts":
            kw = list_options(args)
            out = hosts_and_containers(**kw)
        elif action == "--containers" and args:
            kw = list_options(args[1:])
            if not kw.pop("containers"):
                sys.exit(USAGE)
            out = host_containers(args[0], **kw)
        elif action == "--last":
            out = {"ok": True, "last": last_answers(args)}
        elif action == "--attach" and len(args) == 2:  # (in the terminal open_remote opens)
            sys.exit(attach(*args))
        elif action == "--start" and len(args) == 1:
            ok, message = start(args[0])
            out = {"ok": ok, "message": message}
        elif action == "--status" and args:
            host, rest, kw = args[0], args[1:], {}
            while rest:
                arg = rest.pop(0)
                if arg == "--done-hours" and rest:
                    kw["done_hours"] = float(rest.pop(0))
                elif arg in ("--recent", "--plans", "--memories") and rest:
                    kw[arg[2:]] = int(rest.pop(0))
                elif arg == "--no-tokens":
                    kw["tokens"] = False
                elif arg == "--usage-refresh" and rest and rest[0].isdigit():
                    kw["usage_refresh"] = int(rest.pop(0))
                else:
                    sys.exit(USAGE)
            out = status(host, **kw)
        elif action in ("--open", "--run") and len(args) == 2:
            ok, message = (open_remote if action == "--open" else run)(args[0], args[1])
            out = {"ok": ok, "message": message}
        elif action == "--dismiss" and len(args) == 2:
            ok, message = dismiss(args[0], args[1])
            out = {"ok": ok, "message": message}
        elif action in ("--delete-chat", "--delete-plan", "--delete-memory") and \
                1 < len([a for a in args if a != "--describe"]) <= (2 if action == "--delete-memory" else 3):
            out = delete(args[0], action[len("--delete-"):], *[a for a in args[1:] if a != "--describe"],
                         describe="--describe" in args)
        elif action in ("--hide", "--show-hidden") and len(args) == (3 if action == "--hide" else 2):
            ok, message = hide(*args)
            out = {"ok": ok, "message": message}
        elif action == "--end" and len(end_args(args)[0]) in (2, 3):
            words, keep_off = end_args(args)
            ok, message = end(*words, busy="--busy" in args)
            if ok and keep_off:  # (stopped: Keep going off too; not stopped, it stays on, as for a chat here)
                import jump  # (its words name a go-on that's still queued for it, as for a chat here)
                message = f"{message.rstrip('.')}. {jump.keep_off(Path.home(), [], keep_off, words[0])[1]}"
            out = {"ok": ok, "message": message}
        elif action == "--interrupt" and len(args) in (2, 3):
            ok, message = interrupt(*args)
            out = {"ok": ok, "message": message}
        elif action == "--agent-run" and len([a for a in args if a != "--no-open"]) in (3, 4):
            ok, message, path = agent_run(*[a for a in args if a != "--no-open"], open_it="--no-open" not in args)
            out = {"ok": ok, "message": message, **({"file": path} if path else {})}
        elif action == "--share" and len(args) in (2, 3):
            ok, message = share(*args)
            out = {"ok": ok, "message": message}
        elif action == "--unshare" and len(args) == 3:
            ok, message = unshare(*args)
            out = {"ok": ok, "message": message}
        elif action == "--continue" and len([a for a in args if a not in ("--print-command", "--end-first")]) == 3:
            printing = "--print-command" in args
            ok, message, command = continue_on(*[a for a in args if a not in ("--print-command", "--end-first")],
                                               open_it=not printing, end_first="--end-first" in args)
            out = {"ok": ok, "message": message, **({"command": command} if command and printing else {})}
        elif action == "--find" and len(args) == 2:
            out = find(*args)
        elif action == "--plan" and len([a for a in args if a != "--no-open"]) in (2, 3):
            ok, message, path = open_plan(*[a for a in args if a != "--no-open"], open_it="--no-open" not in args)
            out = {"ok": ok, "message": message, **({"file": path} if path else {})}
        elif action == "--move-plan" and len(args) >= 3:
            host, slug, profile, rest, kw = args[0], args[1], args[2], args[3:], {}
            while rest:
                arg = rest.pop(0)
                if arg == "--into" and rest and "back" not in kw:
                    kw["into"] = rest.pop(0)
                elif arg == "--back" and "into" not in kw:
                    kw["back"] = True
                elif arg == "--no-setting":
                    kw["setting"] = False
                elif arg == "--if-exists" and rest:
                    kw["if_exists"] = rest.pop(0)
                elif arg == "--describe":
                    kw["describe"] = True
                else:
                    sys.exit(USAGE)
            out = move_plan(host, slug, profile, **kw)
        elif action in ("--share-plan", "--unshare-plan") and len(args) in (3, 4):
            ok, message = plan_sharing(args[0], args[1], args[2], action == "--share-plan",
                                       args[3] if len(args) == 4 else None)
            out = {"ok": ok, "message": message}
        elif action == "--task" and len(args) >= 3:
            host, profile, folder, rest, kw = args[0], args[1], args[2], args[3:], {}
            while rest:
                arg = rest.pop(0)
                if arg == "--prompt" and rest:
                    kw["text"] = rest.pop(0)
                elif arg == "--plan" and len(rest) >= 2:
                    kw["plan"], kw["plan_profile"] = rest.pop(0), rest.pop(0)
                elif arg in ("--model", "--effort") and rest:
                    kw[arg[2:]] = rest.pop(0) or None
                elif arg == "--permission-mode" and rest:
                    kw["mode"] = rest.pop(0) or None
                elif arg == "--bg":
                    kw["background"] = True
                elif arg == "--print-command":
                    kw["open_it"] = False
                else:
                    sys.exit(USAGE)
            out = task(host, profile, folder, **kw)
        elif action == "--put-image" and len(args) == 2:
            out = put_image(*args)
        elif action == "--login" and len(args) == 1:
            ok, message = login(args[0])
            out = {"ok": ok, "message": message}
        elif action == "--login-here" and len(args) == 1:  # (in the terminal --login opens)
            sys.exit(login_here(args[0]))
        elif action == "--vscode-account" and len(args) == 2:
            ok, message = vscode_account(args[0], None if args[1] == "-" else args[1])
            out = {"ok": ok, "message": message}
        elif action == "--accounts" and len(args) >= 2:
            out = accounts(args[0], args[1:])
        elif action == "--disconnect" and len(args) == 1:
            ok, message = disconnect(args[0])
            out = {"ok": ok, "message": message}
        elif action == "--undismiss-all" and len(args) == 1:
            ok, message = dismiss(args[0])
            out = {"ok": ok, "message": message}
        else:
            sys.exit(USAGE)
    except (ValueError, OSError) as exc:
        out = {"ok": False, "error": str(exc), "message": str(exc)}
    print(json.dumps(out))  # ASCII: a lone surrogate in a host's text can't break it


if __name__ == "__main__":
    main()
