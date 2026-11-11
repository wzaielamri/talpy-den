# Development

```bash
python3 -m unittest discover -s tests           # the test suite
tools/render_popup.sh /tmp/popup.png            # screenshot of the repo's popup (offscreen), QML messages in /tmp/popup.log
tools/bench/bench.py all                        # Talpy Chat's timings and idle CPU (offscreen, made-up chats); tools/bench/vscode_bench.py: VS Code's
kpackagetool6 -t Plasma/Applet -u package       # reinstall after changes
plasmawindowed org.wzaielamri.talpyden      # run the installed widget in a window
```

GNOME extension:

```bash
gjs -m gnome/tests/test_logic.js                # its logic (no GNOME Shell needed)
gnome/build.sh                                  # build it into gnome/build/ (zip for gnome-extensions install)
tools/gnome/shell.sh /tmp/gnome                 # run it in a headless GNOME Shell (Ubuntu 26.04, podman) with made-up data, screenshots in /tmp/gnome
tools/gnome/shell.sh /tmp/gnome tools/gnome/steps-actions.sh   # jumping, notifications, settings, turning it off and on
```

VS Code extension (in `vscode/`; [In VS Code](vscode.md#development) says more):

```bash
cd vscode && npm ci                             # once
npm run check && npm test                       # type check, its tests
npm run package                                 # build talpy-den-<version>.vsix
```

```
package/                  the Plasma widget (what install.sh installs)
├── metadata.json
└── contents/
    ├── ui/               QML: main.qml (data, actions), FullRepresentation.qml (popup), GroupSection.qml (account),
    │                     SessionRow.qml, PetStrip.qml + Pet.qml (pets), hub/Hub.qml (checks shared by all copies), …
    ├── code/             Python: talpy_den.py (status; poll.py runs it for each check, compiled code kept in ~/.local/share/talpy-den),
    │                     jump.py (actions), sharing.py (shared chats), accounts.py (accounts), remote.py (SSH),
    │                     markdown_page.py (plans and runs as a web page), notify_sound.py
    ├── config/           settings schema and pages
    ├── ui/talpy/         Talpy, the pet: its parts, moods and actions (shared with GNOME and VS Code)
    ├── ui/icons.mjs      the icon table: one icon per meaning for Plasma, VS Code and GNOME (tests/test_icons.py)
    └── pets/             Talpy's notification icons (made by tools/talpy_icons.mjs)
gnome/                    the GNOME Shell extension: extension/ (GJS: indicator.js, logic.js, ui/, prefs.js), build.sh, tests/
vscode/                   the VS Code extension (TypeScript: src/ the extension, webview/ its view); each build copies the
                          backend, Talpy and the snippet into vscode/vendor/
statusline-snippet.sh     the snippet install.sh adds to your status line
tests/                    unit tests: they build Claude Code's files in temporary folders
tools/                    render_popup.sh (offscreen screenshots), talpy_icons.mjs (Talpy's still pictures), talpy_font.py (VS Code's
                          status bar icon font of them: needs potrace and python3-fontforge), gnome/ (headless GNOME Shell test),
                          check_public.py (nothing private gets committed), bench/ (Talpy Chat's timings, before and after a change)
```

The tests build Claude Code's files (sessions, background jobs, transcripts, shared-chat links, a switched `~/.claude` link) in temporary folders. `tests/test_remote.py` drives the SSH code through a stand-in `ssh` that runs the command locally.

**Releases:** the Plasma widget, the GNOME extension and the VS Code extension share one version. Raise it in `package/metadata.json`, `gnome/extension/metadata.json` and `vscode/package.json`, add a `## <version>` entry to `CHANGELOG.md` and `vscode/CHANGELOG.md` (the first starting with a short `### Highlights` list, then `### Every change`: the release page shows only the highlights, with links to both changelogs), commit, then push a tag (`git tag v<version> && git push origin main v<version>`). The release workflow checks, tests and builds all three and publishes them with those entries as the notes.

**When Claude Code updates:** Talpy Den reads Claude Code's files, talks to its background service and matches its wording, most of it not a documented interface. [claude-code-updates.md](claude-code-updates.md) lists each of these reliances, where the code uses it, how to check it on a new version and which test covers it; go through it after a Claude Code update, and add an item when new code relies on something new.

**Nothing private:** `tools/check_public.py` refuses commits with tokens, keys, IP addresses, emails, home folders or anything naming the machine it runs on or its SSH hosts (CI runs it on every file and the whole history). Turn it on once per clone with `git config core.hooksPath .githooks`. The hooks run it as `main` has it committed, so a branch you commit or merge on (a pull request's) can't run its own copy; a change to it checks commits once it is on `main`.

**Contributing:** issues and pull requests are welcome. Please run the tests, and check QML changes with `tools/render_popup.sh`. Keep `talpy_den.py` and `sharing.py` compatible with Python 3.7, because they also run on SSH hosts (a test checks this).
