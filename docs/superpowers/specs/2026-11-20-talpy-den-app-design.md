# Talpy Den as an app (design)

Date: 2026-11-20. Size: a project (full design).

## Intent

Talpy Den today is three front ends over one Python backend: the Plasma widget
(about 36,000 lines of QML), the GNOME Shell extension (about 9,000 lines of
JavaScript, behind on features) and the VS Code extension (about 27,000 lines
of TypeScript and React, at parity with Plasma). Every feature is written two
or three times, and GNOME keeps falling behind.

The owner wants **one Talpy Den app that is the same for everyone**: the same
screens and behaviour on every system, so that **a change made once reaches
every platform**, and shipping it is "wrap the same app as a deb, an rpm, and
later an exe or a dmg". In the owner's words: "the same feeling for all users,
and when I change something it changes for all, so it's easy to maintain later
on all platforms."

It is also the base for what comes later (not built now): other agents next to
Claude Code, then Talpy Den's own agent harness (agentic coding, a companion
agent for the whole system), and maybe a phone app. For that, Talpy Den has to
be an app with its own background process, not a widget inside plasmashell.

Two measurements from 2026-11-20 on the owner's laptop back this up:
plasmashell used 66–92% of a core while Talpy Chat windows were open (each one
a plasmashell window), every reinstall of the widget restarts plasmashell and
closes every Talpy Chat window, and the status check starts Python every 2 s
(0.14 s each, about 5% of a core, in both Plasma and VS Code when both run).

## Who it's for

Mainly the owner today ("not many people use it, I think only me for now");
public users later, through packages. The owner uses the Plasma widget daily on
KDE (panel icon plus the full dashboard on the laptop's desktop) and Talpy Chat
windows spread over several screens.

## Goals

1. **One app** (the "Talpy Den app") with everything Talpy Den does today on
   Plasma and in VS Code: the dashboard (chats, accounts, plan usage, SSH hosts
   and containers, pets, games), Talpy Chat, Projects, Permissions, Recap,
   queued tasks, finding chats, notifications. The owner: "everything should be
   identical in both"; the first release is the **union** of the two (see
   "Parity on release day").
2. **One UI**: the app's screens are the VS Code extension's React UI
   (`vscode/webview`), so VS Code and the app show the same thing and a feature
   is written once.
3. **One core**: a background process per user that watches Claude Code once
   and pushes changes to everything connected (app windows, VS Code, the Plasma
   and GNOME parts, Talpy Den Display's `jobs.json`).
4. **VS Code keeps working on its own.** Without the app installed it runs its
   own copy of the core, as today; with the app installed it connects to the
   app's core. ("It is easier for VS Code users, or they would feel pushed.")
5. **KDE**: the panel icon shows Talpy's glyph, the badge and the usage %; a
   click opens the app (no popup). An optional desktop widget shows the full
   dashboard on the desktop, as today (the owner's screenshot of 2026-11-20);
   a chat clicked there opens its Talpy Chat window.
6. **GNOME**: the top-bar icon with the badge and a short list; a click opens
   the app.
7. **Talpy Chat**: each chat in a window of its own, from the app.
8. **Packages**: rpm (Fedora) and deb (Ubuntu) from repositories, so updates
   come with the system's updates; later exe (Windows) and dmg (macOS).
9. **Interfaces defined now, used later**: an agent adapter (Claude Code is the
   only one now), one client connection, and a platform layer (Linux now).

## Non-goals (for now)

- Talpy Den's own harness, agents other than Claude Code, the phone.
- macOS and Windows builds (designed for, not built; see "Later").
- Rust (see "Rust: what and when").
- New features: the first release is the switch, at parity.

## Anti-goals

It would be a failure, even if it works, if:

- VS Code users have to install the app to keep using Talpy Den.
- Any promise in `docs/privacy.md` breaks: a network port, telemetry, data
  leaving the computer that doesn't leave today.
- The owner loses something they use on release day (they switch at once).
- It is heavier than today: CPU while idle or locked, a desktop widget that
  redraws the desktop for nothing, an app that draws while hidden.
- There are still two UIs to keep in step.

## Constraints

- **Targets**: Linux first. Full desktop integration on current Fedora (KDE
  Plasma 6, GNOME 51) and Ubuntu 26.04 LTS (GNOME 50); the GNOME extension
  supports 49, 50 and 51 (its 43/44 version kept as today if cheap). On Ubuntu
  24.04 LTS (GNOME 46) and Kubuntu 24.04 (Plasma 5): **the app and its tray
  icon only** (owner, 2026-11-20): no top-bar list, and on GNOME a chat's
  terminal can't be brought to the front there. Later macOS, Windows, the
  phone.
- **Privacy** (`docs/privacy.md`): nothing is sent anywhere; Talpy Den calls
  no Anthropic API itself; it reads Claude Code's files and runs `claude`,
  `ssh` and container tools as the user does; its files stay where they are and
  readable only by the user.
- **SSH hosts and containers** keep running the Python scripts (`remote.py`
  sends them compressed, as since 2026-11-20); Python 3.7 there.
- **Users keep their own Claude Code sign-in.** Talpy Den doesn't sign in to
  anything.
- `tools/check_public.py` (nothing private in commits), one shared version for
  every artifact (`docs/development.md`, Releases), the reliance list in
  `docs/claude-code-updates.md`.
- The owner is a single developer: the plan has to keep every step a working
  release.

## Approaches

Considered (2026-11-20, with the owner):

| | A. Electron + shared TypeScript core | B. Python core + Electron UI | C. Tauri (Rust) + Node sidecar | Native Qt app |
|---|---|---|---|---|
| UI | VS Code's React UI, as is | as is | as is | rewrite or Plasma QML |
| Core | VS Code's host code, moved into a shared package | host logic rewritten in Python | the TypeScript core run by a bundled Node | QML logic |
| VS Code without the app | runs the same core package | needs the Python service or its own copy | same as A | separate UI |
| Same look everywhere | yes: Chromium everywhere | yes | no: WebKitGTK on Linux, WebKit on macOS, Chromium on Windows | yes |
| Size | ~100 MB download, ~200–300 MB memory | same | ~10 MB, ~80–150 MB | lighter |
| Long term (harness, coding, companion) | Anthropic's official SDKs (Client SDK, Claude Agent SDK) and the MCP SDK are TypeScript and Python; VS Code's editor (Monaco) and terminals (xterm.js, node-pty) run on Node and Chromium | Python SDKs fine, UI as A | Rust has no official Anthropic SDK; the agent code would still run in the bundled Node | two UIs (app and VS Code) |

**Picked: A (owner, 2026-11-20).** It reuses the code VS Code users run today
for both the UI and the core, keeps one UI, looks the same on every system, and
is where the agent SDKs and coding components live. B rewrites working code;
C costs a second runtime and a weaker engine on Linux, the main platform, for a
smaller download; Qt keeps two UIs. Flutter was ruled out (a rewrite of
everything).

**Measured (2026-11-20, a throwaway test on the owner's laptop, Fedora KDE on
Wayland).** The UI's demo pages (`vscode/dev/harness.html` for the dashboard,
`vscode/dev/chat.html` for Talpy Chat), the same timeline in Electron 45.4.1
(Chromium 156) and in WebKitGTK 2.54.2, the engine Tauri uses on Linux (in a
small GTK window; Tauri's own shell would add little). Memory is PSS summed
over each app's processes:

| | Electron 45 | WebKitGTK (Tauri on Linux) |
|---|---|---|
| Dashboard, click to visible (first window) | 400 ms | 939 ms |
| A Talpy Chat window, click to visible | **~90–150 ms** | ~520–565 ms |
| Memory: the dashboard alone | 337 MB | **~190 MB** |
| Memory: each further chat window | **~20 MB** | ~55 MB |
| Memory: dashboard + 10 chat windows | **588 MB** | ~750 MB |
| CPU: dashboard (demo data, pets moving) | 50% of a core | 37% |
| CPU: dashboard + 10 chat windows | 110% | 95% |

What it means: WebKitGTK is lighter only for a single window; with many
chats open, which is how the owner works ("many agents in parallel, many chats
loaded at the same time… I click and I get directly the answer"), Electron
opens a chat about five times faster and needs less memory. Both engines draw
the UI the same way. And in both, **the UI's own animations cost the CPU**
(half a core for the dashboard's demo, ~5–6% for each idle chat window), so
the shared UI needs the treatment the Plasma widget got on 2026-11-20 (see
"Performance budgets"); VS Code's users gain from it too.

The owner's condition: **the shell stays replaceable.** The UI and the core
talk only through Talpy Den's own connection, never through Electron APIs, so
the shell could become Tauri later without touching either.

And **the UI stays replaceable too**: it holds no logic of its own. It draws
what the core sends and sends back what the user did; what a chat's state
means, what to notify, what an action does, all of it is decided in the core.
If Talpy Den later becomes an editor in Zed's league and the web UI isn't
enough (the owner asked, 2026-11-20), a native front end (GPUI, say) is one
more client of the same core: only the UI is written again, never the agents,
the harness, the adapters or the connection. GPUI was weighed now and left for
then: it would cost the whole UI before anything ships, give up the UI shared
with VS Code (which shows only web UIs) and the Plasma desktop widget, and it's
young outside Zed; an agentic coding app (editor, terminals, diffs, many
agents) is what VS Code and its forks already build on Electron (Monaco,
xterm.js). A shortcut to "Talpy Den in Zed": Talpy Den's harness can itself
speak ACP as an agent, and then runs inside Zed and the other ACP editors.

## The design

### Overview

```
   Claude Code (sessions, transcripts, hooks, service socket, CLI)
                 │                      ┌── SSH hosts / containers
                 ▼                      │   (Python scripts, as today)
   ┌──────────────────────────────────────────────┐
   │ core (TypeScript, a user background process) │
   │  agent adapter: Claude Code                  │
   │  platform layer: Linux                       │
   │  Python worker (talpy_den.py, week.py, …)    │
   └──────────────┬───────────────────────────────┘
                  │ one set of messages: a Unix socket only the user can open
                  │ (app, VS Code), and the session D-Bus (Linux desktop parts)
   ┌──────────┬───┴──────────┬──────────────┬───────────────┬──────────────┐
   app        VS Code         Plasma panel   Plasma desktop  GNOME          jobs.json
   (windows,  (same UI;       icon (glyph,   widget (the     extension      (Talpy Den
   tray)      own core if     badge, %)      dashboard)      (icon, list)   Display)
              no app)
```

### The core

**What it is.** The VS Code extension's host code (`vscode/src`: actions,
dashboard, chat pane, transitions, notifications, accounts, live watcher,
remote hosts…, with `vscode/src/shared`) moved into a package of its own
(`core/`), plus the Python backend as today. It runs in one of two places: as
the app's background process, or inside VS Code when the app isn't installed.

**Host services.** 21 of the 38 host files call VS Code's API today (mostly
`vscode.window` 156×, `vscode.commands` 67×, `vscode.workspace` 45×,
`vscode.Uri` 44×, `vscode.env` 24×). Those calls go behind one interface the
core asks for: notify, ask (quick pick, input, confirm), open a terminal or a
URL, read and write settings, the clipboard, the status bar text. VS Code
implements it with its API (behaviour unchanged); the app implements it with
its own windows and the platform layer.

**Agent adapters.** The owner wants other agents to be easy to add later:
Gemini CLI and the like, and the owner's own agent on a custom endpoint.
Everything that knows one agent sits behind one interface, and the rest of the
core, the connection and the UI speak only agent-neutral terms:

- **An agent-neutral model.** A chat (its agent, state, folder, host), its
  turns and messages, tool calls (kind, title, status, the diff they make),
  permission requests (with their options), questions, a plan (to-do list),
  subagents. Usage windows, accounts, background jobs, Remote Control and the
  like are **capabilities**: an adapter says which it has, and the UI shows
  only those (a Gemini chat shows no Claude plan bars). Each chat carries its
  agent's id, and the UI names the agent ("Claude", "Gemini") where today it
  says Claude.
- **Two kinds of adapter.**
  - *Watching*: the agent runs elsewhere (a terminal, an SSH host) and Talpy
    Den reads its files and drives it from outside: **Claude Code** today,
    shaped by the sections of `docs/claude-code-updates.md` (sessions,
    background jobs, the service socket, the CLI, transcripts, hooks, settings,
    the status line, wording, SSH hosts and containers).
  - *Running*: Talpy Den starts the agent and talks to it. The general route
    is the **Agent Client Protocol** (ACP: an open standard, JSON-RPC over the
    agent's stdio, the editor-to-agent counterpart of what LSP is for language
    servers). Its agent list (agentclientprotocol.com, 2026-11-20) names 51,
    among them Gemini CLI, Goose, OpenCode, Qwen Code, GitHub Copilot and
    Cline natively, and Codex CLI and Claude Agent through adapters. **One ACP
    adapter covers all of them**, and the owner's own agent plugs in by
    speaking ACP. Talpy Den's own harness is a running adapter too, on the
    Claude Agent SDK (TypeScript).
- **The model follows ACP's terms** where they fit (sessions, prompt turns,
  session updates, tool calls and their updates, permission requests, plans,
  the file system and terminal requests an agent makes of its client), so the
  ACP adapter maps one to one, and Claude Code's adapter translates its files
  into the same terms.

Now: only the Claude Code adapter, with the agent-neutral model and the
capabilities in place (release 1 makes the shared types agent-neutral where
it costs little, with no change users see). Later: the ACP adapter, with Gemini
CLI as its first test.

**Platform layer.** What differs per system, Linux only now: finding running
chats (`/proc`), bringing a chat's terminal to the front (Konsole, tmux, GNOME
Terminal, Ptyxis; KWin and the GNOME extension's raiser), notifications and
their sounds, phone notifications (KDE Connect), file locations (XDG folders,
`~/.claude*`), dictation's recorder.

**Python.** The scripts stay. The status check stops starting Python every
2 s: a **long-running Python worker** (one process, `poll.py`'s cached code)
answers the core's requests over its stdin and stdout. That removes the start
cost (about 5% of a core today) without a rewrite. Moving local logic from
Python into the TypeScript core is allowed step by step later (macOS and
Windows have no Python by default); the SSH-host scripts stay Python.

**One per user, started on demand.** With the app installed, a systemd user
socket unit owns the socket (`$XDG_RUNTIME_DIR/talpy-den/core.sock`, folder
mode 0700) and starts the core at the first connection (the panel icon at
login, the app, VS Code); the core keeps running (it notifies and starts queued
tasks even with no window). Without the app (VS Code alone), VS Code runs the
core inside itself, as today, and listens on no socket.

**Locked screen.** The core watches `org.freedesktop.ScreenSaver`
(`ActiveChanged`, as the Plasma widget does since 2026-11-20) and tells every
client; what moves holds still while locked, and a client covered by windows
says so to the core the same way. Checks and notifications go on.

### The connection

One set of messages, reached two ways, both only by the user's own processes:

- **The socket** (the app, VS Code; every platform later): a Unix socket,
  newline-delimited JSON. The messages start from the ones the VS Code UI and
  host exchange today (`WebviewMessage`, 62 kinds, and `HostMessage` in
  `vscode/src/shared/types.ts`), plus what thin clients need: a small
  "summary" (the badge count and colour, usage %, the glyph's mode, the short
  list) and "open this" requests (open the app, a chat, settings).
- **The session D-Bus** (Linux's desktop parts: the Plasma widgets and the
  GNOME extension): a small interface of the core with the summary (a property
  and a change signal), the "open this" methods, and a relay that carries the
  same messages for the desktop widget's page. Plasma's QML reaches it with
  `org.kde.plasma.workspace.dbus` (its `SignalWatcher` and `asyncCall`, used by
  the widget's lock watch since 2026-11-20) and passes messages to and from the
  page with QtWebChannel's `WebChannel`; GNOME uses Gio. So the Plasma parts
  stay plain QML: **no compiled code**, nothing to rebuild for each distro or Qt
  version, and the packages still come from one `electron-builder` setup.
- A hello first: protocol version, client kind, what it subscribes to. A client
  gets the full state, then changes.
- There is no TCP port, not even on localhost. The socket's folder is mode
  0700; the session bus is the user's own.
- Talpy Den Display's `$XDG_RUNTIME_DIR/talpy-den/jobs.json` is written by the
  core, as today.

### Parity on release day

The owner switches at once, so the app carries what each front end has today
(the reviewer counted 54 Plasma settings, `package/contents/config/main.xml`,
and 43 VS Code ones):

- **From Plasma, into the core and the app**: phone notifications through KDE
  Connect (`phoneWhileAway`, `phoneFinished`, `phoneDevice`), the shortcuts
  (the chat that needs you, Talpy Chat: global shortcuts through the platform
  layer, KDE's KGlobalAccel and GNOME's as the extension does today), the app
  that shows Markdown (`markdownApp`: Okular or the browser), the side
  questions' model, Talpy Chat's terminal font, the Accounts and Hosts settings
  pages. The icon's blink stays with the panel icon.
- **The app's own, where VS Code gives its own today**: a **settings page** in
  the shared UI (`vscode/webview` has none: its gear opens VS Code's Settings)
  with the union of the settings; **pickers, inputs and confirmations** in the
  UI where VS Code uses quick picks and input boxes (35 calls); a **command
  menu** for the commands VS Code puts in its palette (about 35: Live Mode,
  Dictation Models, Old Chats, Show Hidden…).
- **Handed off, as Plasma does today**: a chat's changes open in VS Code's
  changes view through Talpy Den's `vscode://` links when VS Code is installed,
  else a diff per file (`code --diff`, `jump.py`); plans in Okular or the
  browser; plan line comments stay VS Code's. The app's own diff and review
  views come later (Monaco), with agentic coding.

### Notifications and questions

One place decides: the core. When a client window has focus (an app window or
a VS Code window connected to the core), the notification and its question
(Allow, Deny, Reply, an answer) show there, in the window, as VS Code shows them
today; otherwise as a desktop notification (KDE, GNOME), with actions where the
desktop has them. Clients tell the core when they gain and lose focus. A
notification shows once, where you're looking. The Monday Recap and the "while
you were away" summary follow the same rule.

### The app (Electron)

- **Main process**: windows, the tray icon (KDE; Ubuntu's GNOME has tray
  support, Fedora's GNOME gets the extension instead), single instance (a
  second start brings the open window to the front), the connection to the
  core. The app's windows talk to the main process through a preload bridge
  that offers exactly what `webview/env.ts` offers today (`post`, messages in,
  saved state), and the main process relays to the core.
- **Windows**: the dashboard (the VS Code view's UI) and one Talpy Chat window
  per chat (`chat.tsx`), as Plasma does today.
- **Security**: context isolation and the renderer sandbox on, no Node in the
  pages, a content security policy of local files only, no navigation away, no
  remote content; links open in the browser (http and https only).
- **The core** runs as a separate process with Electron's own Node
  (`ELECTRON_RUN_AS_NODE`), so no system Node is needed.

### VS Code

On start it looks for the socket. If it's there, VS Code is a client, and its
view and Talpy Chat tabs **load the app's installed UI files** instead of its
own, so the UI always matches the core it talks to, whichever was updated last
(the Marketplace updates the extension on its own; the app comes with the
system's updates). The extension then keeps only what only VS Code can do (its
terminals and editor tabs, the changes view, plan comments, its settings
editor, mirrored to the core's settings), which the core asks for through the
connection. If the app is older than the extension needs (a minimum app
version in the extension), VS Code runs its own core, as when the app isn't
installed. The backend's `--instance` election stays for good, as a guard
against two cores notifying.

Without the app, nothing changes: VS Code runs the core inside itself and uses
its own UI files. Its settings editor stays its settings page.

### Plasma

- **Panel icon** (the widget in the panel): Talpy's glyph, the badge, the usage
  % (as in the owner's screenshot), from the core's summary; a click opens the
  app (or brings it to the front). No popup. The glyph keeps today's rules (it
  moves on the beat, one frame a picture, holds still under the locked screen).
- **Desktop widget** (optional, Add Widgets): the dashboard in a Qt web view
  (QtWebEngine, `qt6-qtwebengine` on Fedora), showing the app's UI files from
  the installed app. It keeps the cover watch (`CoverWatch.qml`) and tells the
  page when it's covered or the screen is locked (the `visible` message exists
  already), so the pets hold still for nobody.
- Both reach the core through its D-Bus interface, in plain QML (see "The
  connection"): the panel icon reads the summary; the desktop widget's page
  gets a bridge object through `WebChannel` in place of `acquireVsCodeApi`.
- The old popup and desktop dashboard (`package/contents/ui`) are removed on
  release day (owner's choice: switch at once).

### GNOME

The extension keeps the top-bar icon, the badge and a short list (the chats
that need you, a line per working chat), opens the app on a click, and keeps
the window raiser that only the shell may do (bringing a chat's terminal to
the front). It reaches the core through its D-Bus interface (Gio). Its popup's
other parts are removed.

### Settings

One settings file owned by the core (`$XDG_CONFIG_HOME/talpy-den/settings.json`),
with today's settings (the same in Plasma, GNOME and VS Code, in the same
order). The app has a settings page (the UI's); VS Code keeps its settings
editor and mirrors it to the core's file while connected; the Plasma and GNOME
settings buttons open the app's page. On first start the app imports the
Plasma widget's settings (and VS Code's, where set) once.

Things `install.sh` does in the user's files today (the status-line snippet,
the permission and live hooks in Claude Code's settings) a package can't do:
the app does them on first start, after asking, as `install.sh` asks.

### Privacy and security rules

- No network port; the socket only the user can open, and the user's own
  session bus.
- No telemetry, no crash reports, no analytics. Electron's crash reporter off.
- No remote content in the UI; a content security policy of local files.
- Updates: rpm and deb come from the repositories, through the system's
  updates; the app checks nothing by itself. The AppImage (and later exe and
  dmg) asks once, on first start, whether to look for new versions: that check
  reads the GitHub releases list and sends nothing about the user, and
  `docs/privacy.md` says so. Off means never.
- Everything `docs/privacy.md` lists stays true; it gets a section for the app.

### Performance budgets

Checked the way they were measured on 2026-11-20 (per-thread CPU from `/proc`,
a KWin script counting each window's repaints):

- The core: under 1% of a core on average while chats work, near 0 when none
  does and while the screen is locked.
- The app: nothing drawn while its windows are hidden or minimized; a Talpy
  Chat window while a tool runs no worse than today's 32 repaints a second
  (Chromium repaints only the changed area).
- **The shared UI's animations** (measured above: half a core for the
  dashboard's demo, ~5–6% for each idle chat window, in both engines) follow
  the rules the Plasma widget got on 2026-11-20: one clock for what moves in a
  page, CSS animations the compositor runs instead of drawing each frame in
  JavaScript where the look allows, and nothing moving in a page nobody sees
  (hidden, minimized, covered, the screen locked). Targets: an idle chat window
  under 1% of a core, the dashboard with the pets moving under 10%. This is
  part of release 3 and lands in VS Code at the same time.
- **Opening a chat**: visible within ~150 ms of the click (Electron measured
  ~90–150 ms), with ten or more chat windows open.
- The panel icon: at most today's ~14 repaints a second while chats work.
- The desktop widget: holds still covered, under windows or locked.
- Memory: the core under ~150 MB; the app with the dashboard and one Talpy Chat
  window under ~400 MB.

### Packaging, updates, releases

- `electron-builder` from one configuration: rpm, deb and AppImage now; later
  exe and dmg. One version for the app, VS Code and the thin widgets.
- **Electron stays supported.** A new Electron major comes every 8 weeks and
  only the newest three get fixes (about 6 months each; 45 is the newest on
  2026-11-20, Chromium 156, supported until 2027-04-27). Each Talpy Den
  release moves to the newest stable Electron, and a security fix in a
  supported one is a release of its own. The app never ships an Electron past
  its end of life.
- Fedora: an rpm in a COPR repository. Ubuntu: a deb in Talpy Den's own apt
  repository (or a PPA), with an AppArmor profile so Electron's sandbox works
  on 24.04 and later (as Chrome and VS Code ship one). The AppImage is a
  fallback (on Ubuntu it would have to run without that sandbox).
- The packages carry the app, the core's systemd user units and its D-Bus
  service file, the Plasma widgets (plain QML), the GNOME extension, the
  desktop file and the icons. The release workflow builds them with the VS
  Code extension; nothing in them is compiled per distro.

### Rust: what and when

Measured 2026-11-20 on the owner's laptop (1,177 transcripts, about 2 GB):
finding a chat across everything 0.35 s, the Recap over all of history
0.48 s, a status check 0.14 s (its cost is Python starting every 2 s, which the
worker removes). **Nothing is worth porting to Rust now.** Rust comes in piece
by piece where a measurement in the new core shows a hot spot that TypeScript
can't fix, as a native module of the core (for example: watching many files,
full-text search over a very large history, a sandbox for agent commands, a
small always-on companion process). The shell can become Tauri later because
of the connection rule above.

### Later (designed for, not built)

- **macOS, Windows**: the same app and UI; the platform layer gets their
  versions (process list, terminals: Terminal.app/iTerm2, Windows Terminal);
  the core starts with the app or as a login item instead of systemd; Python on
  this computer replaced by core code or bundled; signing (an Apple developer
  account, a Windows code-signing certificate).
- **Other agents**: the ACP adapter (Gemini CLI first; then any agent on
  ACP's list, and the owner's custom-endpoint agent once it speaks ACP).
  Agents that don't speak ACP but keep session files can get a watching
  adapter of their own, as Claude Code has.
- **Harness**: an adapter that runs agents itself, on the Claude Agent SDK
  (TypeScript), with an API key (Anthropic doesn't allow third-party products
  to offer claude.ai login unless approved); coding views from VS Code's
  components (Monaco, xterm.js).
- **Phone**: the same UI in a mobile shell, connected to the core over a
  private network (authentication required; not a public port).

## Releases, in order

Each one is a working Talpy Den.

1. **Core package**: the host code moves from `vscode/src` into `core/` behind
   the host services interface; VS Code runs it in-process. Nothing changes for
   users. VS Code's tests pass unchanged.
2. **Core process and connection**: the socket, the protocol, the systemd user
   units, the Python worker; VS Code connects when the socket is there.
3. **The app**: Electron with the dashboard and Talpy Chat windows, the tray,
   notifications, the settings page, pickers and command menu, the Plasma-only
   features (phone, shortcuts, Markdown app…), the one-time import, the
   first-start setup (status line, hooks); rpm for the owner's daily use, next
   to the old widget while it's being built.
4. **The switch (2.0)**: the core's D-Bus interface, the thin Plasma panel
   icon and desktop widget, the thin GNOME extension, VS Code loading the app's
   UI files when connected, the deb with its AppArmor
   profile, the COPR and apt repositories, the AppImage; the old QML popup,
   desktop dashboard and GNOME popup removed; docs and `docs/privacy.md` for the
   app.
5. **Clean-up**: the retired QML and GNOME UI code deleted, tests for them
   moved or dropped.

## Testing

- The Python suite (`python3 -m unittest discover -s tests`) and VS Code's
  (`npm test`) keep passing through every release.
- The core: unit tests under Node, and contract tests for every message of the
  connection (both ends agree on the shapes).
- The app: an end-to-end smoke test (Electron under Playwright) with the demo
  data VS Code's harness already has (`vscode/dev/harness.html`).
- The thin parts: an offscreen render of the Plasma widgets
  (`tools/render_popup.sh`'s way) and the headless GNOME Shell run
  (`tools/gnome/shell.sh`, GNOME 50 and 51).
- The app on each target: current Fedora (KDE, GNOME), Ubuntu 26.04, and
  Ubuntu 24.04 (the app and its tray icon, the deb's AppArmor profile).
- The performance budgets, measured on the owner's laptop before the switch.

## Decided by the owner (2026-11-20)

- One app, the same for all users; a change made once reaches every platform.
- VS Code keeps working without the app, and uses the app's core when it's
  there.
- Switch at once: the old popup goes on release day.
- KDE panel icon: glyph, badge, usage %; a click opens the app; no popup.
- The desktop dashboard stays as an optional widget.
- Parity: everything identical to today's VS Code version.
- Secure and private, as promised; updates when a new version is released.
- Linux first (Fedora and Ubuntu, KDE and GNOME); macOS, Windows, phone later.
- Ubuntu 24.04 and Kubuntu 24.04: the app and its tray icon only, no port of
  the GNOME extension to 46–48.
- Electron, the React UI and a TypeScript core; the shell kept replaceable;
  Rust later, piece by piece; nothing to Rust now.
- Harness and other agents later; the agent adapter now, made so that Gemini
  CLI and the owner's own custom-endpoint agent are easy to add.

## My calls (for the owner to check)

- Each chat in a window of its own (as on Plasma today).
- The core started by a systemd user socket unit; VS Code alone runs its own.
- The connection: a Unix socket, newline-delimited JSON, a version in the
  hello; no TCP port at all.
- The Plasma widgets and the GNOME extension reach the core through a small
  D-Bus interface, in plain QML and Gio: no compiled code to rebuild per
  distro (the reviewer's point: a compiled QML module is tied to the Qt it was
  built with).
- VS Code, connected, loads the app's installed UI files, so UI and core
  always match; an app older than the extension's minimum means VS Code runs
  its own core; the `--instance` election stays as a guard.
- Release-day parity is the union of Plasma's and VS Code's features and
  settings; what VS Code itself provides (changes view, plan comments) is
  handed off to VS Code as Plasma does today.
- Notifications show once: in the focused window (app or VS Code), else on the
  desktop.
- Other agents through the Agent Client Protocol (one adapter for many
  agents); the core's agent-neutral model follows ACP's terms; agent features
  such as usage windows are capabilities the UI shows only where an agent has
  them.
- A long-running Python worker instead of rewriting the backend.
- One settings file owned by the core; a one-time import.
- rpm first (the owner's Fedora), then the deb with an AppArmor profile; the
  AppImage as a fallback; the AppImage's update check asked on first start.
- `electron-builder`; Electron's crash reporter off.
- The performance budgets' numbers.
- The order of the releases.

## Left to the builder

Names (packages, the D-Bus interface, the app's id and desktop file), the
protocol's exact message shapes beyond today's, the repository layout for
`core/` and `app/`, how the UI's saved state is kept per window, icons, the
app's colours (the UI uses VS Code's `--vscode-*` colour variables: the app
supplies its own, light and dark), whether KDE also gets the app's tray icon
next to the panel icon, how release 2 is shipped before the app exists, the
COPR and apt repository setup, and how VS Code's settings mirror to the core's
file.

## Risks

- **Two cores at once** while VS Code runs its own and the app is installed
  later, or the app is older than VS Code needs: VS Code must notice the
  socket and switch, or both notify (the backend's `--instance` election stays
  as a guard).
- **A web view inside plasmashell** (the desktop widget): its memory, and
  repaints of the desktop window while the pets move; the budgets must hold.
- **Ubuntu's sandbox rule** for Electron: the deb's AppArmor profile must be
  right, or the app runs unsandboxed or not at all.
- **The first-start setup** edits Claude Code's settings (hooks, status line):
  it must ask, be undoable, and match what `install.sh` does today.
- **GNOME's extension review** (extensions.gnome.org) for an extension that
  needs the app: it may have to ship only in the packages.
