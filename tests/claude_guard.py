"""No test runs the real claude.

The real claude is usually on PATH (~/.local/bin), and find_claude(ask_shell=True)
asks your login shell for it besides. So a test that reaches a command line
without a fake claude of its own would start the real one: once, a background
service for a test's temporary config folder. Every test module imports this
first: from then on PATH starts with a claude that only notes it ran and
fails, and SHELL is a login shell whose PATH has only that one. A test that
sets PATH or SHELL itself (a fake bin, the find_claude tests) still gets its
own, and child processes inherit the guard.

Each test that runs the guard's claude fails, naming what it was asked."""
import atexit
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


def _install():
    folder = Path(tempfile.mkdtemp(prefix="talpy-den-test-guard-"))
    atexit.register(shutil.rmtree, str(folder), True)
    log, bin_dir = folder / "ran.log", folder / "bin"
    bin_dir.mkdir()
    log.touch()
    claude = bin_dir / "claude"
    claude.write_text('#!/bin/sh\nprintf "%%s\\n" "$*" >> "%s"\n'
                      'echo "a test ran claude outside its own fake bin (tests/claude_guard.py)" >&2\n'
                      'exit 97\n' % log)
    shell = folder / "login-shell"
    # asked for its PATH as find_claude asks (talpy_den.login_shell_path), it knows only the guard's
    # claude; anything else (tmux's panes, a terminal's script) gets a plain sh
    shell.write_text('#!/bin/sh\n[ "$*" = "-l -i -c env" ] && exec echo "PATH=%s:/usr/bin:/bin"\n'
                     'exec /bin/sh "$@"\n' % bin_dir)
    for exe in (claude, shell):
        exe.chmod(0o755)
    os.environ["PATH"] = os.pathsep.join([str(bin_dir), os.environ.get("PATH", "")])
    os.environ["SHELL"] = str(shell)

    run = unittest.TestCase.run

    def guarded(self, result=None):
        before = len(ran())
        outcome = run(self, result)
        new = ran()[before:]
        if new and result is not None:
            try:
                raise AssertionError("ran claude outside the test's own fake bin: " + "; ".join(new))
            except AssertionError:
                result.addFailure(self, sys.exc_info())
        return outcome

    unittest.TestCase.run = guarded
    return log, claude


def ran():
    """What the guard's claude was asked so far, a line per run."""
    try:
        return LOG.read_text().splitlines()
    except OSError:
        return []


def forget():
    """For a test that runs the guard on purpose."""
    LOG.write_text("")


LOG, CLAUDE = _install()
