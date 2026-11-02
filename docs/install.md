# Installing, updating and removing

## Requirements

- **KDE Plasma 6** (6.0 or newer). Plasma 5 isn't supported: Kubuntu 24.04 LTS, for example, ships Plasma 5.27.
- **Claude Code** (the `claude` command), signed in. Talpy Den finds it on PATH, in `~/.local/bin` (Claude's installer) and npm's, bun's, Volta's, pnpm's or nvm's folders, or else on the PATH your login shell sets up.
- **python3**, 3.7 or newer. Every Plasma 6 distribution already has it.
- **jq**, for the status-line snippet that supplies plan usage and context.
- Optional:
  - **Konsole**, so that clicking a chat switches to its tab. With other terminals the window is raised. New terminals open in your default terminal (System Settings → Default Applications).
  - **PipeWire** (`pw-play`) or PulseAudio (`paplay`) for sounds.
  - **kdialog** (usually installed with KDE) for *Choose folder…*; `zenity` works too.
  - **Okular**, to read plans, memories and subagent runs rendered. Without it they open as a page in your web browser.
  - **gdbus** (`libglib2.0-bin` on Debian and Kubuntu, `glib2-tools` on openSUSE; Fedora and Arch have it) for switching Konsole tabs and raising windows, and **xdg-open** (`xdg-utils`) for opening chats in VS Code.
  - tmux; VS Code with the Claude Code extension.

| Distribution | Extra packages |
|---|---|
| Fedora KDE | `sudo dnf install jq` |
| Kubuntu, KDE neon, Debian | `sudo apt install jq` |
| Arch Linux | `sudo pacman -S jq` |
| openSUSE | `sudo zypper install jq` |

**Tested on:** Fedora 44 (Plasma 6.7, Qt 6.11), in daily use; Kubuntu 26.04 LTS (Plasma 6.6, Qt 6.10) and Kubuntu 25.10 (Plasma 6.4, Qt 6.9): install, uninstall, the popup and the test suite.

## Installation

```bash
git clone https://github.com/wzaielamri/talpy-den.git
cd talpy-den
./install.sh
```

Then right-click your panel → **Add Widgets…**, search for **Talpy Den** and drag it onto the panel (or onto the desktop).

You can add it more than once, e.g. on the panel and on each screen's desktop: the copies share one check and their settings, and only one of them notifies (one with a popup, when there is one). On the desktop, the pets rest while windows cover them (one window or several together), and all of it rests while they cover the whole widget.

Each [release](https://github.com/wzaielamri/talpy-den/releases) also has the Plasma widget as a `.plasmoid` file and the GNOME extension as a `.zip`, for installing without the repository (its notes say how), and the VS Code extension as a `.vsix`. `./install.sh` is still the easiest way: it also adds the status-line snippet.

For VS Code, [Talpy Den for VS Code](vscode.md) is an extension of its own, installed from the same [releases](https://github.com/wzaielamri/talpy-den/releases/latest) (a `.vsix`). It brings its own copy of the backend, so it doesn't need the Plasma widget, and it works alongside it.

`install.sh` does two things:

1. It installs the Plasma widget for your user (into `~/.local/share/plasma/plasmoids/`) with `kpackagetool6`. So that the chat pane shows Talpy in the taskbar rather than Plasma's icon (it's a window of Plasma's shell), it adds a KWin window rule for it (*Talpy Den: Talpy as the chat pane's icon*, in System Settings → Window Rules) and a desktop file hidden from menus (`~/.local/share/applications/org.wzaielamri.talpyden.chat.desktop`).
2. It adds a small snippet to the status-line script of each Claude profile (the script that `statusLine` in `~/.claude*/settings.json` runs). It shows the change and asks first (`--yes` skips the question), and keeps a backup next to the script. The snippet is plain POSIX sh, so it works in sh, bash and zsh scripts; running `./install.sh` again replaces an older copy. The snippet saves the status-line data (plan limits, context) for Talpy Den. What your status line shows stays the same.

<details>
<summary><b>No status line yet?</b></summary>

Plan usage and context come from Claude Code's status line. If you don't have one yet, this minimal one shows the model and the folder:

```bash
cat > ~/.claude/statusline.sh <<'EOF'
#!/bin/bash
input=$(cat)
jq -r '"\(.model.display_name) · \(.workspace.current_dir | split("/") | last)"' <<<"$input"
EOF
chmod +x ~/.claude/statusline.sh
```

Add this entry to `~/.claude/settings.json` (and likewise for other profiles such as `~/.claude-work`):

```json
"statusLine": { "type": "command", "command": "~/.claude/statusline.sh" }
```

Then run `./install.sh` again to add the snippet.

</details>

<details>
<summary><b>Manual installation</b></summary>

```bash
kpackagetool6 -t Plasma/Applet -i package
```

Then paste `statusline-snippet.sh` into your status-line script, right after the line that reads its input (`input=$(cat)`).

</details>

## Updating

```bash
cd talpy-den
git pull
./install.sh
```

If the panel keeps showing the old version, restart Plasma's shell: `systemctl --user restart plasma-plasmashell`.

The VS Code extension doesn't update by itself: install the `.vsix` of a newer [release](https://github.com/wzaielamri/talpy-den/releases/latest) the same way (`code --install-extension talpy-den-<version>.vsix`).

## Uninstalling

1. Right-click the widget → **Remove Talpy Den** (for each one you added).
2. In the repository folder, run:

   ```bash
   ./install.sh --uninstall
   ```

   This removes the Plasma widget and its window rule, and takes the snippet out of your status-line scripts (it shows the change and keeps a backup).
3. Optionally delete Talpy Den's cache, `rm -rf ~/.cache/talpy-den`, and its data, `rm -rf ~/.local/share/talpy-den`: the hooks' scripts and, if you set dictation up, its speech engine and models (about 600 MB, more with each bigger model). Keep both while the GNOME or VS Code extension still uses them.

Apart from what you change through it (the chats and plans you share, the accounts you add, permissions you allow or revoke, and the files a chat's review undoes or commits), Talpy Den never changes Claude Code's own files, so nothing else is left behind. Accounts you added stay (they're Claude's folders now), and so do their `~/.local/bin/claude-NAME` commands: remove those on the Accounts page first if you like. Shared chats stay shared: use **Keep only on …** first if you want them back as normal chats (see [Sharing chats](sharing.md)).
