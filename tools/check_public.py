#!/usr/bin/env python3
"""Check that what goes into this repository can be published.

    python3 tools/check_public.py --staged     files staged for commit + the author (pre-commit hook)
    python3 tools/check_public.py --message F  a commit message (commit-msg hook)
    python3 tools/check_public.py --all        every tracked file
    python3 tools/check_public.py --history    every commit: authors, messages and every added line
    python3 tools/check_public.py PATH...      these files or folders (e.g. an unpacked .vsix)

Two kinds of rules:
- generic ones, the same everywhere (CI too): API keys and tokens, private
  keys, IP addresses, email addresses, absolute home folders;
- personal ones, taken from the machine running the check: the user name,
  home folder and host name, the hosts, host names and users in ~/.ssh/config,
  and every line of .git/info/private-patterns (git never commits that file).
  So this script names nothing personal itself.

Allowed: documentation examples (example.com, 192.0.2.x, /home/alice), the
identities in tools/public-identities.txt, and any line containing
"check-public: ok". Exit status 1, with one line per finding, when something
is found; matches are masked so the output can go into CI logs.
"""

import getpass
import glob
import os
import re
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_LINE = "check-public: ok"
BINARY_SUFFIXES = {".png", ".gif", ".jpg", ".jpeg", ".webp", ".ico", ".vsix", ".zip", ".woff", ".woff2"}

TOKENS = [
    ("Anthropic API key", r"sk-ant-[A-Za-z0-9_-]{16,}"),
    ("API key (sk-)", r"\bsk-(?!ant-)[A-Za-z0-9_-]{32,}"),  # (also OpenAI's sk-proj-…)
    ("GitLab token", r"\bglpat-[A-Za-z0-9_-]{20,}"),
    ("Hugging Face token", r"\bhf_[A-Za-z0-9]{30,}"),
    ("GitHub token", r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})"),
    ("AWS access key", r"\bAKIA[0-9A-Z]{16}\b"),
    ("Google API key", r"\bAIza[0-9A-Za-z_-]{35}\b"),
    ("Slack token", r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    ("npm token", r"\bnpm_[A-Za-z0-9]{36}\b"),
    ("private key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("JSON web token", r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    ("password in URL", r"[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@"),
]
TOKEN_RES = [(name, re.compile(rx)) for name, rx in TOKENS]
IPV4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?!\w|\.\d)")  # also at a sentence's end
# (with :: and at least 3 groups, or all 8: not a time like 10:40:00, nor std::string)
IPV6 = re.compile(r"(?<![\w:.])(?:(?:[0-9A-Fa-f]{1,4}:){1,6}:(?:[0-9A-Fa-f]{1,4}:){0,5}[0-9A-Fa-f]{1,4}"
                  r"|::(?:[0-9A-Fa-f]{1,4}:){1,6}[0-9A-Fa-f]{1,4}|(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4})(?![\w:])")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
HOME_PATH = re.compile(r"(?:/home|/Users|[A-Za-z]:\\+Users)[/\\]+([A-Za-z0-9._-]+)")
EXAMPLE_USERS = {"alice", "bob", "carol", "user", "you", "me", "example", "someone", "tester", "u", "x"}
EXAMPLE_DOMAINS = ("example.com", "example.org", "example.net")  # the domain itself or a subdomain
EXAMPLE_TLDS = (".example", ".invalid", ".test", ".localhost")
# Commits a contributor made and that are published as they are: --history
# doesn't check their author and committer (all they added still is)
PUBLISHED_IDENTITIES = {"a993a0a8e24450b2ea6490d06f74ef04bc0bfe92", "af361e91e3e685c8e3f101fab0b7c02eab50871d"}
# Values from ~/.ssh/config (and host names) that are far too common to be personal: account names, forges,
# the distributions' default host names, and plain words people name a host by, which the code uses as words
# ("lab" is this repository's own example host)
COMMON = {"root", "git", "ubuntu", "admin", "user", "debian", "pi", "localhost", "github.com", "gitlab.com",
          "bitbucket.org", "ssh.github.com", "ssh.dev.azure.com", "vs-ssh.visualstudio.com",
          "fedora", "archlinux", "localhost.localdomain", "raspberrypi",
          "lab", "work", "dev", "prod", "test", "home", "server", "remote", "local", "build", "staging", "backup",
          "desktop", "laptop", "office", "cloud", "box", "gpu", "nas", "web"}
SCISSORS = "# ------------------------ >8 ------------------------"  # git commit -v: the diff follows it


def mask(text):
    return text[:1] + "…"  # CI logs are public: the rule and place say enough


def public_identities():
    path = ROOT / "tools" / "public-identities.txt"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return set()
    return {l.strip().lower() for l in lines if l.strip() and not l.lstrip().startswith("#")}


def ssh_config_values(path, seen):
    """Host aliases, HostName, User and ProxyJump values of an ssh config (and its Includes)."""
    out = set()
    try:
        real = path.resolve()
        if real in seen:
            return out
        seen.add(real)
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return out
    for line in lines:
        words = line.split("#", 1)[0].replace("=", " ").split()
        if len(words) < 2:
            continue
        key, values = words[0].lower(), words[1:]
        if key == "include":
            for pattern in values:
                pattern = os.path.expanduser(pattern)
                if not os.path.isabs(pattern):
                    pattern = str(Path.home() / ".ssh" / pattern)
                for inc in sorted(glob.glob(pattern)):
                    out |= ssh_config_values(Path(inc), seen)
        elif key in ("host", "hostname", "user", "proxyjump"):
            for v in values:
                for part in v.split(","):
                    part = part.split("@")[-1].split(":")[0] if key == "proxyjump" else part
                    if part and not any(c in part for c in "*?!%"):
                        out.add(part)
    return out


def default_hostname():
    """The host name the distribution gives a machine whose name was never set (os-release's DEFAULT_HOSTNAME)."""
    for path in ("/etc/os-release", "/usr/lib/os-release"):
        try:
            for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("DEFAULT_HOSTNAME="):
                    return line.split("=", 1)[1].strip().strip("\"'").lower()
            return ""
        except OSError:
            pass
    return ""


def personal_strings():
    """Things that identify this machine or its owner; never in a public file."""
    found = set()
    # (on GitHub Actions the machine is a runner: its user is "runner", a word
    # the code uses, and nothing about it is anyone's)
    if os.environ.get("GITHUB_ACTIONS") != "true":
        try:
            found.add(getpass.getuser())
        except Exception:
            pass
        home = str(Path.home())
        if home not in ("/", "/root"):
            found.add(home)
        try:
            name = socket.gethostname()
            if name.lower() != default_hostname():  # (a host name never set: the distribution's, not yours)
                found.add(name)
                found.add(name.split(".")[0])
        except OSError:
            pass
    found |= ssh_config_values(Path.home() / ".ssh" / "config", set())
    try:  # (the repository's own .git, also from a worktree, whose .git is a file)
        private = Path(git("rev-parse", "--path-format=absolute", "--git-common-dir").strip()) / "info" / "private-patterns"
    except (OSError, subprocess.CalledProcessError):
        private = ROOT / ".git" / "info" / "private-patterns"
    try:
        for line in private.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                found.add(line.strip())
    except OSError:
        pass
    return sorted(s for s in found if len(s) >= 3 and s.lower() not in COMMON)


class Checker:
    def __init__(self):
        self.identities = public_identities()
        self.personal = [(s, re.compile(r"(?<![A-Za-z0-9])" + re.escape(s) + r"(?![A-Za-z0-9])", re.I))
                         for s in personal_strings()]
        self.findings = []

    def email_ok(self, email):
        e = email.lower()
        local, _, domain = e.partition("@")
        example = any(domain == d or domain.endswith("." + d) for d in EXAMPLE_DOMAINS) or domain.endswith(EXAMPLE_TLDS)
        return (e in self.identities or example or domain == "users.noreply.github.com"
                or local in ("noreply", "no-reply") or e in ("git@github.com", "support@github.com"))  # (GitHub's own: Dependabot signs off as support@) check-public: ok

    def check_line(self, where, line):
        for name, rx in TOKEN_RES:  # never allowed, "check-public: ok" or not
            for m in rx.finditer(line):
                self.report(where, name, m.group(0))
        if SKIP_LINE in line:
            return
        for m in IPV4.finditer(line):
            ip = m.group(0)
            octets = [int(o) for o in ip.split(".")]
            if max(octets) > 255:
                continue
            if octets[0] == 127 or ip in ("0.0.0.0", "255.255.255.255") or ip.startswith(("192.0.2.", "198.51.100.", "203.0.113.")):
                continue
            self.report(where, "IP address", ip)
        for m in IPV6.finditer(line):
            ip = m.group(0)
            if len([g for g in ip.split(":") if g]) >= 3 and not ip.lower().startswith("2001:db8:"):  # (documentation's)
                self.report(where, "IP address", ip)
        for m in EMAIL.finditer(line):
            if not self.email_ok(m.group(0)):
                self.report(where, "email address", m.group(0))
        for m in HOME_PATH.finditer(line):
            if m.group(1).lower() not in EXAMPLE_USERS:
                self.report(where, "absolute home folder", m.group(0))
        for value, rx in self.personal:
            for m in rx.finditer(line):
                self.report(where, "personal (from this machine)", m.group(0))

    def check_text(self, label, text):
        self.check_line(label + " (path)", label)
        for n, line in enumerate(text.splitlines(), 1):
            self.check_line(f"{label}:{n}", line)

    def check_bytes(self, label, data):
        if data.startswith((b"\xff\xfe", b"\xfe\xff")) and Path(label).suffix.lower() not in BINARY_SUFFIXES:
            self.check_text(label, data.decode("utf-16", errors="replace"))  # text, with NULs between its letters
            return
        if Path(label).suffix.lower() in BINARY_SUFFIXES or b"\0" in data[:8192]:
            self.check_line(label + " (path)", label)
            if Path(label).suffix.lower() in {".png", ".gif", ".jpg", ".jpeg", ".webp"}:
                print(f"note: {label}: image — make sure it only shows demo data", file=sys.stderr)
            return
        self.check_text(label, data.decode("utf-8", errors="replace"))

    def check_identity(self, label, email):
        if not self.email_ok(email):
            self.report(label, "commit identity not in tools/public-identities.txt", email)

    def report(self, where, rule, match):
        self.findings.append(f"{where}: {rule}: {mask(match)}")


def git(*args, binary=False):
    r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, check=True)
    return r.stdout if binary else r.stdout.decode("utf-8", errors="replace")


def main(argv):
    checker = Checker()
    if not argv:
        sys.exit(__doc__.split("\n\n")[1])
    mode = argv[0]
    if mode == "--staged":
        names = [n for n in git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z").split("\0") if n]
        for name in names:
            checker.check_bytes(name, git("show", ":" + name, binary=True))
        for var in ("GIT_AUTHOR_IDENT", "GIT_COMMITTER_IDENT"):
            ident = git("var", var).strip()
            m = re.search(r"<([^>]*)>", ident)
            if m:
                checker.check_identity(var, m.group(1))
    elif mode == "--message" and len(argv) == 2:
        text = Path(argv[1]).read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        lines = lines[:lines.index(SCISSORS)] if SCISSORS in lines else lines  # (git drops what follows)
        text = "\n".join(l for l in lines if not l.startswith("#"))
        checker.check_text("commit message", text)
    elif mode in ("--all", "--history"):
        for m in argv:
            if m == "--all":
                for name in [n for n in git("ls-files", "-z").split("\0") if n]:
                    path = ROOT / name
                    if path.is_file():
                        checker.check_bytes(name, path.read_bytes())
            elif m == "--history":
                for line in git("log", "--all", "--format=%H %ae %ce").splitlines():
                    sha, author, committer = line.split(" ", 2)
                    if sha in PUBLISHED_IDENTITIES:
                        continue
                    checker.check_identity(f"commit {sha[:10]} author", author)
                    checker.check_identity(f"commit {sha[:10]} committer", committer)
                log = git("log", "--all", "-p", "--no-color", "--no-ext-diff", "--text", "--format=@@commit %H%n%B")
                sha, path = "", ""
                for line in log.splitlines():
                    if line.startswith("@@commit "):
                        sha, path = line[9:19], "message"
                        continue
                    if line.startswith("+++ b/"):
                        path = line[6:]
                        checker.check_line(f"commit {sha} {path} (path)", path)
                    elif line.startswith("+") and line != "+++ /dev/null":  # (a line of its own may start with ++)
                        checker.check_line(f"commit {sha} {path}", line[1:])
                    elif path == "message":
                        checker.check_line(f"commit {sha} message", line)
            else:
                sys.exit(__doc__.split("\n\n")[1])
    else:
        for arg in argv:
            p = Path(arg)
            files = [f for f in p.rglob("*") if f.is_file()] if p.is_dir() else [p]
            for f in files:
                checker.check_bytes(str(f.relative_to(p) if p.is_dir() else f), f.read_bytes())
    for finding in checker.findings:
        print(finding)
    if checker.findings:
        print(f"\n{len(checker.findings)} finding(s): this can't be published as it is. "
              f"Remove them, or add '{SKIP_LINE}' to a line that is really fine.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
