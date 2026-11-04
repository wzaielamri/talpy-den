# Talpy Den for VS Code

Every Claude Code chat you have running, on this computer, in your containers and on your SSH
hosts, in one VS Code view: which ones need you, which are working, how much
of your plan is left, and Talpy, a pet who acts it all out.

- **Every chat at a glance**, per Claude account: terminal chats, background
  chats and Claude Code panels, here, on your SSH hosts and in your Docker,
  Podman or nerdctl containers (also from a Remote-SSH or Dev Containers
  window), with each account's plan usage and where your pace leads.
- **Act without switching**: click a chat for its tab to follow the
  conversation, reply, answer its permission prompts and questions, and
  review or undo what it changed.
- **Notifications** when a chat needs you or finishes, and one key
  (Ctrl+Alt+Shift+C) for the chat that needs you.
- **Start chats** in a terminal, a Claude Code panel or the background, with
  a task, later, or once a usage limit resets; a chat can keep going by
  itself after each usage limit, also on your SSH hosts and in containers.
- **Recap and Permissions**: your day, week or everything with Claude, and
  every permission you gave, to revoke.
- **Recent chats, ★ starred chats and plans** under each account, a page at a
  time; **every chat, plan and memory by project** on the Projects tab; and
  Find a Chat. Star, hide or delete them.

<!-- Screenshots show demo data only (Talpy Den: Toggle Demo Data, or dev/harness.html), never real chats. -->
<p>
  <img src="docs/screenshots/view-dark.png" alt="The Talpy Den view in a dark theme: Talpy under &quot;1 chat needs you&quot;, an account with its chats, their pets, plan usage bars, plans and memories, and an SSH host with a chat a usage limit stopped" width="300">
  <img src="docs/screenshots/view-light.png" alt="The same view in a light theme" width="300">
</p>

As an editor tab (**Talpy Den: Open in Editor Tab**):

<img src="docs/screenshots/editor-tab.png" alt="The view opened as a wide editor tab" width="640">

## Install

Click **Install** on this page, or search for **Talpy Den** in VS Code's
Extensions view. Or download `talpy-den-<version>.vsix` from the
[latest release](https://github.com/wzaielamri/talpy-den/releases/latest)
and run `code --install-extension talpy-den-<version>.vsix` (or Extensions
view → **⋯** → **Install from VSIX…**); a downloaded extension doesn't update
by itself, so install a newer release the same way.

**Needs** Linux, VS Code 1.90 or newer, Python 3.7+ and Claude Code; for the
plan usage bars, `jq` and a small status-line snippet (**Talpy Den: Set Up
Plan Usage Bars…** adds it). An SSH host needs key-based login (or **Log in…**
where it wants a password) and `python3`; nothing is installed there.

## Everything else

What each part of the view does, the settings and commands, privacy and
troubleshooting are in the
[Talpy Den repository](https://github.com/wzaielamri/talpy-den#readme),
for VS Code in [In VS Code](https://github.com/wzaielamri/talpy-den/blob/main/docs/vscode.md).
Talpy Den runs in the KDE Plasma and GNOME panels too.

Not affiliated with Anthropic. Claude and Claude Code are Anthropic's.
Made by [Wadhah Zai El Amri](https://wzaielamri.github.io/).
[MIT](LICENSE) © 2026 Wadhah Zai El Amri
