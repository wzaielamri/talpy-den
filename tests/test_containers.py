"""Containers like SSH hosts: the list (Docker, Podman, nerdctl; this
computer's and an SSH host's), and status/run/start/attach through stand-in
engines that run the command here in a fake home of the container."""
import contextlib
import io
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_remote import CODE, FakeSSH, remote, cs  # noqa: E402

# A stand-in for docker, podman or nerdctl (which one: its file name), here
# or on the fake SSH host (whose commands run without this environment: its
# files are named in CONF). The containers are in CONF["containers"] (JSON:
# name -> {id, state, image, labels, mounts, started, finished, created,
# users}); a container's home is CONF["homes"]/<name>. Every call is logged
# to CONF["log"]; CONF["mode"] holds a failure to imitate.
FAKE_ENGINE = r'''
import json, os, subprocess, sys
engine = os.path.basename(sys.argv[0])
args = sys.argv[1:]
with open(CONF["log"], "a") as log:
    log.write(json.dumps([engine] + args) + "\n")
with open(CONF["mode"]) as f:
    mode = f.read().strip()
if mode == "down":
    sys.stderr.write("Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?\n")
    sys.exit(1)
if mode == "socket":
    sys.stderr.write("permission denied while trying to connect to the Docker daemon socket at unix:///var/run/docker.sock: "
                     "Get \"http://%2Fvar%2Frun%2Fdocker.sock/v1.24/containers/json\": dial unix /var/run/docker.sock: "
                     "connect: permission denied\n")
    sys.exit(1)
if mode == "hang":
    import time
    time.sleep(30)
with open(CONF["containers"]) as f:
    containers = json.load(f)
by_id = {c["id"]: name for name, c in containers.items()}

def find(key):
    name = by_id.get(key, key)
    if name not in containers:
        sys.stderr.write('Error: no container with name or ID "%s" found: no such container\n' % key if engine == "podman"
                         else "Error response from daemon: No such container: %s\n" % key)
        sys.exit(125 if engine == "podman" else 1)
    return name, containers[name]

def iso(seconds):
    import datetime
    if seconds is None:
        return "0001-01-01T00:00:00Z"
    return datetime.datetime.utcfromtimestamp(seconds).strftime("%Y-%m-%dT%H:%M:%S.123456789Z")

if args[:2] == ["ps", "-a"] and "json" in args:
    out = [{"Names": [name], "Id": c["id"], "State": c["state"], "Image": c["image"], "Labels": c.get("labels") or None,
            "Mounts": c.get("mounts") or [], "IsInfra": c.get("infra", False),
            "StartedAt": c.get("started") if c.get("started") is not None else -62135596800,
            "ExitedAt": c.get("finished") if c.get("finished") is not None else -62135596800,
            "Created": c.get("created")} for name, c in containers.items()]
    print(json.dumps(out))
elif args[:2] == ["ps", "-a"]:
    print("\n".join(c["id"] for c in containers.values()))
elif args[:2] == ["container", "inspect"]:
    template, keys = args[3], args[4:]
    if "{{json .Id}}" in template:   # (as Podman: its .Id only on its own)
        sys.stderr.write('Error: template: inspect:1:7: executing "inspect" at <.Id>: can\'t evaluate field Id in type interface {}\n')
        sys.exit(125)
    for key in keys:
        name, c = find(key)
        if '"mounts"' in template:
            print(json.dumps({"id": c["id"], "name": "/" + name, "state": c["state"], "started": iso(c.get("started")),
                              "finished": iso(c.get("finished")), "created": iso(c.get("created")),
                              "image": c["image"], "labels": c.get("labels"), "mounts": c.get("mounts") or []}))
        else:
            print(json.dumps({"id": c["id"], "state": c["state"], "labels": c.get("labels")}))
elif args[:1] == ["start"]:
    name, c = find(args[1])
    c["state"] = "running"
    with open(CONF["containers"], "w") as f:
        json.dump(containers, f)
    print(args[1])
elif args[:1] == ["exec"]:
    rest, user, env = args[1:], "", []
    while rest[0].startswith("-"):
        flag = rest.pop(0)
        if flag in ("-u", "--user"):
            user = rest.pop(0)
        elif flag in ("-e", "--env"):
            env.append(rest.pop(0))
    name, c = find(rest.pop(0))
    if c["state"] != "running":
        sys.stderr.write("Error: can only create exec sessions on running containers: container state improper\n"
                         if engine == "podman" else "Error response from daemon: container %s is not running\n" % c["id"])
        sys.exit(255 if engine == "podman" else 1)
    if user and user not in c.get("users", ["root"]):
        sys.stderr.write("Error: unable to find user %s: no matching entries in passwd file\n" % user)
        sys.exit(126)
    home = os.path.join(CONF["homes"], name)
    os.makedirs(home, exist_ok=True)
    path = CONF["path"] if not c.get("nopython") else "/nonexistent"
    sys.stdout.flush()
    os.chdir(home)
    os.execve("/bin/bash", ["bash", "-c", rest[2]] if rest[:2] == ["sh", "-c"] else ["bash", "-c", "exit 127"],
              {"HOME": home, "PATH": path, "XDG_CACHE_HOME": home + "/.cache", "FAKE_USER": user or "root"})
else:
    sys.stderr.write("fake engine: not imitated: %r\n" % args)
    sys.exit(2)
'''


def podman_docker_shim(podman):
    """Fedora's podman-docker: a script that runs podman."""
    return f'#!/bin/sh\necho "Emulate Docker CLI using podman." >&2\nexec {podman} "$@"\n'


class FakeEngines(FakeSSH):
    """This computer with stand-in engines (and nothing else of the real
    machine's on PATH), and the fake SSH host lab with its own."""

    def setUp(self):
        super().setUp()
        root = Path(self.tmp.name)
        self.tools, self.engines, self.host_engines = root / "tools", root / "engines", root / "host-engines"
        for d in (self.tools, self.engines, self.host_engines):
            d.mkdir()
        for tool in ("bash", "sh", "env", "cat", "id", "dirname", "sleep"):
            found = subprocess.run(["bash", "-c", f"command -v {tool}"], capture_output=True, text=True).stdout.strip()
            if found:
                (self.tools / tool).symlink_to(found)
        (self.tools / "python3").symlink_to(sys.executable)
        self.containers_file, self.engine_log = root / "containers.json", root / "engine.log"
        self.homes, self.mode_file = root / "container-homes", root / "engine-mode"
        self.mode_file.write_text("")
        self.conf = {"containers": str(self.containers_file), "log": str(self.engine_log), "homes": str(self.homes),
                     "path": str(self.tools), "mode": str(self.mode_file)}
        os.environ.update({"PATH": f"{self.engines}:{self.bin}:{self.tools}", "FAKE_PATH": f"{self.host_engines}:{self.tools}"})
        self.now = time.time()
        self.put({})

    def engine(self, name, where=None, script=None):
        path = (where or self.engines) / name
        path.write_text(script or f"#!{sys.executable}\nCONF = {self.conf!r}\n{FAKE_ENGINE}")
        path.chmod(0o755)
        return path

    def engine_mode(self, mode):
        self.mode_file.write_text(mode)

    def put(self, containers):
        self.containers_file.write_text(json.dumps(containers))

    def container(self, name, state="running", days_ago=0, **kw):
        c = {"id": (name.encode().hex() * 64)[:64], "state": state, "image": "docker.io/library/ubuntu:22.04",
             "labels": None, "mounts": [], "started": self.now - days_ago * 86400 - 60,
             "finished": None if state == "running" else self.now - days_ago * 86400,
             "created": self.now - days_ago * 86400 - 3600, "users": ["root"]}
        c.update(kw)
        return c

    def engine_calls(self):
        return [json.loads(line) for line in self.engine_log.read_text().splitlines()] if self.engine_log.exists() else []

    def chat_in(self, name, title="work in the box"):
        """A finished background job in the container's home (its .claude)."""
        prof = self.homes / name / ".claude"
        (prof / "sessions").mkdir(parents=True, exist_ok=True)
        (prof / ".claude.json").write_text(json.dumps({"oauthAccount": {"accountUuid": "c", "organizationType": "claude_max",
                                                                       "displayName": "Box Me"}}))
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 60))
        (prof / "jobs/def67890").mkdir(parents=True)
        (prof / "jobs/def67890/state.json").write_text(json.dumps(
            {"state": "done", "tempo": "idle", "sessionId": "def67890", "name": title, "cwd": "/work",
             "updatedAt": stamp, "createdAt": stamp}))


DEV_LABELS = {"devcontainer.local_folder": "/home/someone/shop",
              "devcontainer.metadata": json.dumps([{"id": "ghcr.io/devcontainers/features/node:1"},
                                                   {"remoteUser": "node"}, {"remoteUser": "vscode"}])}


class IdTests(unittest.TestCase):
    def test_ids_parse_one_way(self):
        p = remote.place("podman:web-1")
        self.assertEqual((p.container, p.engine, p.name, p.host, p.label), (True, "podman", "web-1", None, "web-1"))
        p = remote.place("docker:api@user@lab.example")
        self.assertEqual((p.engine, p.name, p.host, p.label), ("docker", "api", "user@lab.example", "api on user@lab.example"))
        p = remote.place("lab")
        self.assertEqual((p.container, p.host, p.label), (False, "lab", "lab"))
        self.assertEqual(remote.place("nerdctl:x.y_z").engine, "nerdctl")
        for bad in ("podman:-x", "docker:a@podman:b", "podman:a b", "docker:a@-oProxyCommand=x", "podman:$(id)"):
            with self.assertRaises(ValueError, msg=bad):
                remote.place(bad)

    def test_times(self):
        self.assertEqual(cs.container_time(1700000000), 1700000000000)
        self.assertEqual(cs.container_time("2023-11-14T22:13:20.123456789Z"), 1700000000123)
        self.assertEqual(cs.container_time("2023-11-14T23:13:20+01:00"), 1700000000000)
        for broken in (-62135596800, "0001-01-01T00:00:00Z", 0, None, "", "soon", time.time() + 7 * 86400, True):
            self.assertIsNone(cs.container_time(broken), broken)

    def test_short_image_and_users(self):
        self.assertEqual(cs.short_image("docker.io/library/node:20"), "node:20")
        self.assertEqual(cs.short_image("docker.io/osrf/ros:humble"), "osrf/ros:humble")
        self.assertEqual(cs.short_image("localhost/mine:latest"), "mine:latest")
        self.assertEqual(cs.short_image("sha256:" + "ab" * 32), "ab" * 6)
        self.assertEqual(cs.devcontainer_user(DEV_LABELS), "vscode")  # (the last one wins)
        self.assertEqual(cs.devcontainer_user({"devcontainer.metadata": "not json"}), "")
        self.assertEqual(cs.container_user(None), "")
        import pwd
        self.assertEqual(cs.container_user({"manager": "distrobox"}), pwd.getpwuid(os.getuid()).pw_name)


class ListTests(FakeEngines):
    def test_running_and_recent_ones_running_first(self):
        self.engine("podman")
        self.put({"old": self.container("old", "exited", days_ago=40),
                  "recent": self.container("recent", "exited", days_ago=3),
                  "web": self.container("web", days_ago=100, image="docker.io/library/nginx:1"),
                  "made": self.container("made", "created", days_ago=1, started=None),
                  "never": self.container("never", "created", days_ago=400, started=None),
                  "infra": self.container("infra", infra=True),
                  "dev": self.container("dev", "exited", days_ago=10, labels=DEV_LABELS),
                  "box": self.container("box", "exited", days_ago=2, labels={"manager": "distrobox"},
                                        mounts=[str(Path.home()), "/tmp"])})
        out = remote.containers_here(30)
        self.assertEqual([c["id"] for c in out["containers"]],
                         ["podman:web", "podman:made", "podman:box", "podman:recent", "podman:dev"])
        by = {c["name"]: c for c in out["containers"]}
        self.assertEqual((by["web"]["running"], by["web"]["image"], by["web"]["state"]), (True, "nginx:1", "running"))
        self.assertEqual((by["dev"]["devcontainer"], by["dev"]["folder"], by["dev"]["user"]),
                         (True, "/home/someone/shop", "vscode"))
        self.assertTrue(by["box"]["sharesHome"])
        self.assertFalse(by["dev"]["sharesHome"])
        self.assertAlmostEqual(by["recent"]["activeAt"] / 1000, self.now - 3 * 86400, delta=2)
        self.assertEqual(out["notes"], [])
        # 0 days: only the running ones; a picked one always
        self.assertEqual([c["id"] for c in remote.containers_here(0)["containers"]], ["podman:web"])
        self.assertEqual([c["id"] for c in remote.containers_here(0, ["podman:old", "docker:web", "podman:x@lab"])["containers"]],
                         ["podman:web", "podman:old"])
        # (one call for all of Podman's)
        self.assertEqual({tuple(c[:3]) for c in self.engine_calls()}, {("podman", "ps", "-a")})
        # the users to work as are kept for the checks
        users = json.loads((cs.cache_dir(Path.home()) / "containers.json").read_text())["users"]
        self.assertEqual(users["podman:dev"]["user"], "vscode")
        self.assertEqual(oct((cs.cache_dir(Path.home()) / "containers.json").stat().st_mode & 0o777), "0o600")

    def test_docker_names_them_then_one_inspect(self):
        self.engine("docker")
        self.put({"api": self.container("api", "exited", days_ago=5, labels=DEV_LABELS),
                  "db": self.container("db"), "gone-long": self.container("gone-long", "exited", days_ago=90)})
        out = remote.containers_here(30)
        self.assertEqual([c["id"] for c in out["containers"]], ["docker:db", "docker:api"])
        self.assertEqual(out["containers"][1]["folderShort"], "/home/someone/shop")
        calls = self.engine_calls()
        self.assertEqual([c[:4] for c in calls], [["docker", "ps", "-a", "-q"], ["docker", "container", "inspect", "--format"]])
        self.assertEqual(len(calls[1]) - 5, 3)  # (all of them in one inspect)
        self.assertAlmostEqual(out["containers"][1]["activeAt"] / 1000, self.now - 5 * 86400, delta=2)

    def test_a_docker_that_is_podman_is_listed_once(self):
        podman = self.engine("podman")
        self.engine("docker", script=podman_docker_shim(podman))
        self.engine("nerdctl")
        self.put({"web": self.container("web")})
        out = remote.containers_here(30)
        self.assertEqual(sorted(c["id"] for c in out["containers"]), ["nerdctl:web", "podman:web"])
        self.assertNotIn("docker", {c[0] for c in self.engine_calls()})
        engines = json.loads((cs.cache_dir(Path.home()) / "containers.json").read_text())["engines"]
        self.assertEqual(list(engines.values())[0]["engine"], "podman")
        # a link named docker to podman too
        (self.engines / "docker").unlink()
        (self.engines / "docker").symlink_to(podman)
        self.assertEqual(sorted(cs.container_engines(cs.cache_dir(Path.home()))), ["nerdctl", "podman"])

    def test_engine_trouble_is_a_note(self):
        self.engine("docker")
        self.engine("podman")
        self.put({"web": self.container("web")})
        for mode, words in (("down", "Docker isn't running."), ("socket", "You can't use Docker's socket")):
            self.engine_mode(mode)
            out = remote.containers_here(30)
            self.assertEqual(out["containers"], [])
            notes = {n["engine"]: n["message"] for n in out["notes"]}
            self.assertTrue(notes["docker"].startswith(words), notes)
        self.engine_mode("")

    def test_a_hung_engine_holds_up_only_itself(self):
        self.engine("podman")
        hung = self.engines / "docker"
        hung.write_text("#!/bin/bash\nexec sleep 30\n")
        hung.chmod(0o755)
        self.put({"web": self.container("web")})
        old = cs.CONTAINER_LIST_TIMEOUT
        cs.CONTAINER_LIST_TIMEOUT = 1
        try:
            started = time.time()
            out = remote.containers_here(30)
        finally:
            cs.CONTAINER_LIST_TIMEOUT = old
        self.assertLess(time.time() - started, 3)
        self.assertEqual([c["id"] for c in out["containers"]], ["podman:web"])
        self.assertEqual(out["notes"], [{"engine": "docker", "message": "Docker didn't answer within 1 s."}])

    def test_no_engine_and_show_containers_off(self):
        self.assertEqual(remote.containers_here(30), {"containers": [], "notes": []})
        self.engine("podman")
        self.put({"web": self.container("web")})
        out = remote.hosts_and_containers(containers=False)
        self.assertEqual((out["containers"], out["hostContainers"]), ([], {}))
        self.assertEqual(self.engine_calls(), [])  # (off: the engines aren't asked anything)

    def test_hosts_command_line(self):
        self.engine("podman")
        self.put({"web": self.container("web"), "old": self.container("old", "exited", days_ago=8)})
        r = subprocess.run([sys.executable, "-I", str(CODE / "remote.py"), "--hosts", "--container-days", "7",
                            "--picked", "lab,podman:old"], capture_output=True, text=True, env=os.environ)
        out = json.loads(r.stdout)
        self.assertEqual([c["id"] for c in out["containers"]], ["podman:web", "podman:old"])
        r = subprocess.run([sys.executable, "-I", str(CODE / "remote.py"), "--hosts", "--no-containers"],
                           capture_output=True, text=True, env=os.environ)
        self.assertEqual(json.loads(r.stdout)["containers"], [])


class HostListTests(FakeEngines):
    def test_an_ssh_hosts_containers(self):
        self.engine("docker", self.host_engines)
        self.put({"api": self.container("api"), "old": self.container("old", "exited", days_ago=50)})
        out = remote.host_containers("lab", 30, ["docker:old@lab", "docker:old"])
        self.assertTrue(out["ok"], out)
        self.assertEqual([c["id"] for c in out["containers"]], ["docker:api@lab", "docker:old@lab"])
        self.assertEqual(out["containers"][0]["host"], "lab")
        self.assertEqual(self.calls()[-1], ["lab", "python3 -I - --remote --list-containers 30 --picked docker:old"])
        # kept for the next start
        cached = remote.hosts_and_containers()["hostContainers"]
        self.assertEqual([c["id"] for c in cached["lab"]["containers"]], ["docker:api@lab", "docker:old@lab"])
        self.mode("unreachable")
        out = remote.host_containers("lab")
        self.assertEqual((out["ok"], out["host"]), (False, "lab"))
        self.assertIn("Can't reach lab", out["error"])
        with self.assertRaises(ValueError):
            remote.host_containers("docker:api")


class ContainerStatusTests(FakeEngines):
    def test_status_inside_as_vscodes_user(self):
        self.engine("podman")
        self.put({"shop": self.container("shop", labels=DEV_LABELS, users=["root", "vscode"])})
        self.chat_in("shop")
        out = remote.status("podman:shop", recent=3, tokens=False)
        self.assertTrue(out["ok"], out)
        (group,) = out["result"]["groups"]
        self.assertEqual(group["title"], "Box Me · Max")
        self.assertEqual(group["sessions"][0]["name"], "work in the box")
        self.assertIn("claude attach def67890", group["sessions"][0]["openCommand"])
        calls = self.engine_calls()
        self.assertEqual(calls[0][:3], ["podman", "container", "inspect"])  # (once: which user)
        self.assertEqual(calls[1][:7], ["podman", "exec", "-i", "-u", "vscode", "shop", "sh"])
        self.assertEqual(calls[1][8], "python3 -I - --remote --recent 3 --no-tokens")
        self.assertFalse(out["loggedIn"])
        # the next check knows the user: one call
        self.assertTrue(remote.status("podman:shop", tokens=False)["ok"])
        self.assertEqual([c[1] for c in self.engine_calls()[2:]], ["exec"])
        # nothing was written in it but Talpy Den's cache
        self.assertEqual(sorted(p.name for p in (self.homes / "shop/.cache").iterdir()), ["talpy-den"])

    def test_a_container_made_again_without_that_user(self):
        self.engine("docker")
        self.put({"shop": self.container("shop", labels=DEV_LABELS, users=["root", "vscode"])})
        self.assertTrue(remote.status("docker:shop", tokens=False)["ok"])
        self.put({"shop": self.container("shop", id="f" * 64, users=["root"])})  # (no dev container now)
        out = remote.status("docker:shop", tokens=False)
        self.assertTrue(out["ok"], out)
        self.assertEqual([c[1] for c in self.engine_calls()[2:]], ["exec", "container", "exec"])
        self.assertNotIn("-u", self.engine_calls()[-1])

    def test_failures_in_plain_words(self):
        self.engine("podman")
        self.engine("docker")
        self.put({"off": self.container("off", "exited", days_ago=3), "bare": self.container("bare", nopython=True)})
        out = remote.status("podman:off")
        self.assertEqual((out["ok"], out["error"], out.get("stopped")), (False, "off is stopped.", True))
        self.assertEqual(remote.status("docker:off")["error"], "off is stopped.")
        out = remote.status("podman:nope")
        self.assertEqual((out["error"], out.get("gone")), ("There's no container nope any more.", True))
        self.assertEqual(remote.status("podman:bare")["error"], "python3 isn't installed in bare; Talpy Den needs it there.")
        self.engine_mode("socket")
        self.assertIn("You can't use Docker's socket", remote.status("docker:x")["error"])
        self.engine_mode("down")
        self.assertEqual(remote.status("docker:x")["error"], "Docker isn't running.")
        self.engine_mode("")
        self.assertEqual(remote.status("nerdctl:x")["error"], "nerdctl isn't installed here.")

    def test_run_text_and_start(self):
        self.engine("podman")
        self.put({"box": self.container("box"), "off": self.container("off", "exited")})
        self.assertEqual(remote.run("podman:box", "echo hi from $FAKE_USER"), (True, "hi from root"))
        self.assertEqual(remote.run("podman:box", "echo oops >&2; exit 3"), (False, "oops"))
        self.assertEqual(remote.run("podman:off", "true"), (False, "off is stopped."))
        put = remote.put_text("podman:box", "語 it's")
        self.assertTrue(put["ok"], put)
        self.assertEqual(Path(put["path"]).read_text(encoding="utf-8"), "語 it's")
        self.assertEqual(remote.start("podman:off"), (True, "Started off"))
        self.assertEqual(remote.run("podman:off", "echo up"), (True, "up"))
        self.assertEqual(remote.start("podman:nope"), (False, "There's no container nope any more."))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            remote.main(["--start", "podman:box"])
        self.assertEqual(json.loads(out.getvalue()), {"ok": True, "message": "Started box"})
        with self.assertRaises(ValueError):
            remote.start("lab")

    def test_login_is_its_hosts(self):
        with self.assertRaises(ValueError):
            remote.ssh_host_of("podman:box")
        self.assertEqual(remote.ssh_host_of("podman:box@lab"), "lab")
        self.assertEqual(remote.ssh_host_of("lab"), "lab")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            remote.main(["--login", "podman:box"])
        self.assertFalse(json.loads(out.getvalue())["ok"])


class HostContainerTests(FakeEngines):
    def test_a_container_on_an_ssh_host(self):
        self.engine("podman", self.host_engines)
        self.put({"gpu": self.container("gpu", labels=DEV_LABELS, users=["root", "vscode"]),
                  "off": self.container("off", "exited")})
        self.chat_in("gpu")
        out = remote.status("podman:gpu@lab", tokens=False)
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["result"]["groups"][0]["sessions"][0]["name"], "work in the box")
        host, command = self.calls()[-1]
        self.assertEqual(host, "lab")
        self.assertEqual(shlex.split(command)[:7], ["podman", "exec", "-i", "-u", "vscode", "gpu", "sh"])
        self.assertEqual(self.engine_calls()[-1][:2], ["podman", "exec"])
        out = remote.status("podman:off@lab")
        self.assertEqual((out["error"], out.get("stopped"), out["login"]), ("off on lab is stopped.", True, False))
        # the host's trouble is the host's
        self.mode("denied")
        out = remote.status("podman:gpu@lab")
        self.assertIn("lab refused the login", out["error"])
        self.assertTrue(out["login"])
        self.mode("")
        os.environ["FAKE_PATH"] = str(self.tools)  # (no podman there)
        self.assertEqual(remote.status("podman:gpu@lab")["error"], "Podman isn't installed on lab.")

    def test_start_there(self):
        self.engine("docker", self.host_engines)
        self.put({"off": self.container("off", "exited")})
        self.assertEqual(remote.start("docker:off@lab"), (True, "Started off on lab"))
        self.assertEqual(self.calls()[-1], ["lab", "docker start off"])


class LastAnswerTests(FakeEngines):
    def test_the_last_answer_is_kept_for_the_next_start(self):
        self.engine("podman")
        self.put({"box": self.container("box"), "off": self.container("off", "exited")})
        self.chat_in("box")
        self.assertEqual(remote.last_answers(["podman:box", "lab"]), {})
        self.assertTrue(remote.status("podman:box", tokens=False)["ok"])
        self.assertTrue(remote.status("lab", tokens=False)["ok"])
        self.assertFalse(remote.status("podman:off")["ok"])  # (only answers that worked)
        last = remote.last_answers(["podman:box", "lab", "podman:off", "nowhere"])
        self.assertEqual(sorted(last), ["lab", "podman:box"])
        self.assertEqual(last["podman:box"]["answer"]["result"]["groups"][0]["sessions"][0]["name"], "work in the box")
        self.assertLess(abs(last["lab"]["offset"]), 5000)
        path = cs.cache_dir(Path.home()) / "hosts/podman:box.json"
        self.assertEqual(oct(path.stat().st_mode & 0o777), "0o600")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            remote.main(["--last", "lab"])
        self.assertEqual(list(json.loads(out.getvalue())["last"]), ["lab"])


class AttachTests(FakeEngines):
    def attach(self, ident, command="claude --resume x"):
        ran, out = [], io.StringIO()
        old = os.execvp
        os.execvp = lambda path, argv: ran.append(argv)
        try:
            with contextlib.redirect_stdout(out):
                code = remote.attach(ident, command)
        finally:
            os.execvp = old
        return code, ran, out.getvalue()

    def test_a_terminal_in_the_container(self):
        self.engine("podman")
        self.put({"shop": self.container("shop", labels=DEV_LABELS), "off": self.container("off", "exited")})
        code, ran, _ = self.attach("podman:shop", "cd /w 2>/dev/null; claude --resume x")
        self.assertEqual(ran, [["podman", "exec", "-it", "-e", "TERM", "-e", "COLORTERM", "-u", "vscode", "shop",
                                "sh", "-c", "cd /w 2>/dev/null; claude --resume x"]])
        code, ran, said = self.attach("podman:off")
        self.assertEqual((code, ran), (1, []))
        self.assertIn("off is stopped. Start it with Start in Talpy Den, or: podman start off", said)
        code, ran, said = self.attach("podman:nope")
        self.assertEqual((code, said.strip()), (1, "There's no container nope any more."))

    def test_one_on_an_ssh_host(self):
        self.engine("docker", self.host_engines)
        self.put({"api": self.container("api")})
        code, ran, _ = self.attach("docker:api@lab", "claude")
        (line,) = ran
        self.assertEqual(line[0], "ssh")
        self.assertEqual(line[-3:-1], ["-t", "lab"])
        self.assertNotIn("BatchMode=yes", line)  # (a terminal may ask for a password)
        self.assertEqual(remote.cs.shlex.split(test_unwrap(line[-1])),
                         ["docker", "exec", "-it", "-e", "TERM", "-e", "COLORTERM", "api", "sh", "-c", "claude"])

    def test_open_remote_opens_attach_in_a_terminal(self):
        import jump
        opened, old = [], jump.open_terminal
        jump.open_terminal = lambda cwd, cmd: opened.append(cmd) or True
        try:
            self.assertEqual(remote.open_remote("podman:shop", "claude --resume x"), (True, "Opened a terminal in shop"))
            self.assertEqual(remote.open_remote("podman:shop@lab", "claude"), (True, "Opened a terminal in shop on lab"))
        finally:
            jump.open_terminal = old
        words = shlex.split(opened[0])
        self.assertEqual(words[1:], ["-I", str(CODE / "remote.py"), "--attach", "podman:shop", "claude --resume x"])


class JumpTests(unittest.TestCase):
    def setUp(self):
        import jump
        self.jump = jump

    def test_exec_lines(self):
        t = self.jump.container_target
        self.assertEqual(t(["podman", "exec", "-it", "-e", "TERM", "-e", "COLORTERM", "-u", "vscode", "web", "sh", "-c", "x"]), "web")
        self.assertEqual(t(["/usr/bin/docker", "exec", "-i", "--user=node", "-w", "/w", "--env-file", "f", "--", "abc123", "sh"]),
                         "abc123")
        self.assertEqual(t(["docker", "--context", "lab", "container", "exec", "-d", "web", "true"]), "web")
        self.assertEqual(t(["nerdctl", "-n", "k8s.io", "exec", "-it", "box", "bash"]), "box")
        for other in (["docker", "ps"], ["docker", "run", "-it", "web"], ["ssh", "exec", "web"], ["podman", "exec"], []):
            self.assertIsNone(t(other), other)

    def test_an_ssh_line_that_execs_there(self):
        line = remote.exec_line(remote.place("podman:gpu@lab"), "cd '/w x' 2>/dev/null; claude --resume a", "vscode", tty=True)
        self.assertEqual(self.jump.ssh_target(line), "lab")
        inner = shlex.split(self.jump.ssh_remote_command(line))
        self.assertEqual(self.jump.container_target(inner), "gpu")
        self.assertEqual(inner[-1], "cd '/w x' 2>/dev/null; claude --resume a")

    def test_vscode_addresses(self):
        authority = self.jump.container_authority("docker:shop")
        self.assertTrue(authority.startswith("attached-container+"))
        self.assertEqual(json.loads(bytes.fromhex(authority.split("+", 1)[1]).decode()), {"containerName": "/shop"})
        self.assertTrue(self.jump.container_authority("podman:shop@lab").endswith("@ssh-remote+lab"))
        self.assertEqual(self.jump.remote_folder_uri("lab", "/srv/a b"), "vscode-remote://ssh-remote+lab/srv/a%20b")
        self.assertEqual(self.jump.remote_folder_uri("docker:shop", "/w"), f"vscode-remote://{authority}/w")
        self.assertEqual((self.jump.remote_caption("lab"), self.jump.remote_caption("docker:shop@lab")), ("[SSH: lab]", "(shop)"))
        self.assertEqual(self.jump.remote_authority("lab"), "ssh-remote+lab")


class JumpByIdTests(FakeEngines):
    def test_dev_containers_exec_by_id(self):
        import jump
        self.engine("docker")
        cid = "ab" * 32
        self.put({"shop": self.container("shop", id=cid)})
        remote.containers_here(30)  # (the listing keeps each one's id)
        p, names = jump.container_names("docker:shop")
        self.assertEqual(names, {"shop", cid, cid[:12]})
        me = os.getpid()
        old = jump.proc_cmdline
        jump.proc_cmdline = lambda pid: ["docker", "exec", "-i", cid, "/bin/sh"] if pid == me else []
        try:
            self.assertTrue(jump.runs_in_container(me, p, names))
            self.assertFalse(jump.runs_in_container(me, *jump.container_names("docker:other")))
        finally:
            jump.proc_cmdline = old


REPO = CODE.parent.parent.parent
JS_CONTAINER = "/^(docker|podman|nerdctl):([A-Za-z0-9][A-Za-z0-9_.-]*)(?:@(.+))?$/"


class FrontEndTests(unittest.TestCase):
    """The front ends name containers as remote.py does, and share the two settings."""

    def test_the_same_ids_everywhere(self):
        self.assertEqual(JS_CONTAINER, "/" + remote.CONTAINER.pattern + "/")
        for path in ("package/contents/ui/main.qml", "package/contents/ui/configAccounts.qml", "gnome/extension/logic.js",
                     "vscode/src/shared/model.ts"):
            self.assertIn(JS_CONTAINER, (REPO / path).read_text(), path)

    def test_the_settings_are_shared(self):
        main = (REPO / "package/contents/ui/main.qml").read_text()
        xml = (REPO / "package/contents/config/main.xml").read_text()
        page = (REPO / "package/contents/ui/configHosts.qml").read_text()
        for key in ("showContainers", "containerDays"):
            self.assertIn(f'<entry name="{key}"', xml)
            self.assertIn(f'"{key}"', main.split("readonly property var sharedKeys", 1)[1].split("]", 1)[0])
            self.assertIn(f"cfg_{key}", page)
        self.assertEqual((cs.config_defaults()["showContainers"], cs.config_defaults()["containerDays"]), (True, 30))
        schema = (REPO / "gnome/extension/schemas/org.gnome.shell.extensions.talpy-den.gschema.xml").read_text()
        prefs = (REPO / "gnome/extension/prefs.js").read_text()
        for key in ("show-containers", "container-days"):
            self.assertIn(f'<key name="{key}"', schema)
            self.assertIn(f"'{key}'", prefs)
        package = json.loads((REPO / "vscode/package.json").read_text())
        hosts = next(c for c in package["contributes"]["configuration"] if c["title"] == "Hosts")["properties"]
        self.assertEqual((hosts["talpyDen.showContainers"]["default"], hosts["talpyDen.containerDays"]["default"]), (True, 30))


class PickerRefillTests(unittest.TestCase):
    def test_the_picker_refills_without_destroying_what_plasma_deleted(self):
        # (clearMenuItems deletes the old items itself: destroying them again threw on
        # the second fill, after Reload, and the picker stayed empty for good)
        main = (REPO / "package/contents/ui/main.qml").read_text()
        fill = main.split("function fillHostsMenu()", 1)[1].split("\n    }\n", 1)[0]
        self.assertIn("hostsMenu.clearMenuItems()", fill)
        self.assertNotIn(".destroy()", fill)


class UntrustedAnswerTests(FakeEngines):
    def test_a_plans_name_from_a_container_stays_in_its_folder(self):
        import jump
        old = remote.plan_text
        remote.plan_text = lambda host, slug, profile=None: {"ok": True, "markdown": "# x", "title": "x"}
        try:
            ok, _message, path = remote.open_plan("podman:box", "../../../.claude/CLAUDE", open_it=False)
        finally:
            remote.plan_text = old
        self.assertTrue(ok)
        self.assertEqual(Path(path).parent, jump.runs_folder(Path.home()))
        self.assertNotIn("/", Path(path).name)


def test_unwrap(command):
    from test_remote import unwrapped
    return unwrapped(command)


if __name__ == "__main__":
    unittest.main()
