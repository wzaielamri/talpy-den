#!/usr/bin/env python3
"""What the widgets run for each status check: talpy_den.py's main().

Python compiles the script it's given on every run (talpy_den.py is about
180 KB: half of what a check costs) but keeps the modules it imports compiled.
So this small script imports it, with the compiled copy in Talpy Den's data
folder (~/.local/share/talpy-den/pycache, beside the hooks Claude runs),
never inside the installed widget, nor in the cache: a container given your
~/.cache (to share pip's) could put code there that ran here. The options are
talpy_den.py's own.
"""
import os
import sys
from pathlib import Path

os.umask(0o077)  # cache files are private to the user
sys.dont_write_bytecode = True  # no __pycache__ inside the installed widget...
if sys.version_info >= (3, 8):  # ...but a copy in the data folder (3.7 compiles every time)
    compiled = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "talpy-den" / "pycache"
    try:
        compiled.mkdir(parents=True, exist_ok=True)  # (0700: this run's umask)
        sys.pycache_prefix = str(compiled)
        sys.dont_write_bytecode = False
    except OSError:
        pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # -I leaves the script dir off sys.path
import talpy_den  # noqa: E402

if __name__ == "__main__":
    talpy_den.main()
