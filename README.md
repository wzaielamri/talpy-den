<div align="center">

# Talpy Den

**Every Claude Code chat you have running, at a glance: in your KDE Plasma or GNOME panel, and in VS Code.**

Which chats are working, which need you and how much of your plan is left,
across all your accounts, SSH hosts and containers, one click away.
And Talpy, a pet that acts out what each chat is doing.

[![Tests](https://github.com/wzaielamri/talpy-den/actions/workflows/tests.yml/badge.svg)](https://github.com/wzaielamri/talpy-den/actions/workflows/tests.yml)
[![KDE Plasma 6](https://img.shields.io/badge/KDE_Plasma-6-1d99f3?logo=kde&logoColor=white)](https://www.opendesktop.org/p/2380946/)
[![GNOME Shell 43, 44, 49+](https://img.shields.io/badge/GNOME_Shell-43%20%7C%2044%20%7C%2049%2B-4a86cf?logo=gnome&logoColor=white)](docs/gnome.md)
[![VS Code](https://img.shields.io/badge/VS_Code-1.90%2B-007acc)](https://marketplace.visualstudio.com/items?itemName=wzaielamri.talpy-den)
[![Python 3.7+](https://img.shields.io/badge/python-3.7%2B-3776ab?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

<img src="docs/screenshots/popup-light.png" alt="The Talpy Den popup: the big Talpy says one chat needs you; below, each account shows its chats as pets, plan usage bars, token totals and its chats" width="48%">&nbsp;<img src="docs/screenshots/popup-dark.png" alt="The same popup in a dark theme" width="48%">

</div>

> [!NOTE]
> An independent project: not affiliated with or endorsed by Anthropic, and written with AI assistance. See [About this project](#about-this-project).

## What it does

- **Every chat in one place:** terminal chats, background chats and VS Code's Claude tabs, on this computer, your SSH hosts and your Docker or Podman containers, per Claude account: which need you (and for what), which work (and on what), which are done, and each account's plan usage with where your pace leads.
- **Act without switching:** jump to a chat's terminal or VS Code tab, or chat with it right from the panel: reply, answer its permission prompts and questions, see what it changed and undo it.
- **Start chats** in a terminal, in VS Code or in the background, with a task, later, or once a usage limit resets; a chat a limit stopped can keep going by itself.
- **Find and reuse:** any chat by its words, recent chats, plans and memories; continue a chat on another account when one hits its limit; hide what you don't need, or delete it to the Trash.
- **Recap and Permissions:** your day, week or everything with Claude (time, tokens, what it would cost at API prices, what would use less of your plan), and every permission you gave, to revoke.
- **Notifications** when a chat needs you or finishes, one summary when you come back, and to your phone if you like.

<p align="center"><img src="docs/screenshots/pets.gif" alt="Pets reacting: a chat finishes and its pet celebrates, a new chat's pet digs up out of the ground, and the big Talpy cheers when a usage limit resets" width="500"></p>

Everything it does: [Features](docs/features.md).

## Get it

**KDE Plasma 6:**

```bash
git clone https://github.com/wzaielamri/talpy-den.git && cd talpy-den && ./install.sh
```

The widget is also on [opendesktop.org](https://www.opendesktop.org/p/2380946/). Then right-click your panel → **Add Widgets…** and add **Talpy Den**. It needs Claude Code, python3 and jq; `install.sh` also adds the small status-line snippet that plan usage comes from ([details](docs/install.md)).

**GNOME Shell 49 or newer, or 43 and 44 (Debian 12):** the same `./install.sh` (in a GNOME session it installs the GNOME extension), then log out and back in. [What's different on GNOME](docs/gnome.md).

**VS Code:** install it from the [Visual Studio Marketplace](https://marketplace.visualstudio.com/items?itemName=wzaielamri.talpy-den) (or search for **Talpy Den** in the Extensions view). Or download `talpy-den-<version>.vsix` from the [latest release](https://github.com/wzaielamri/talpy-den/releases/latest), then `code --install-extension talpy-den-<version>.vsix`. It needs Python 3.7+ and works on its own or next to Talpy Den on Plasma or GNOME, also in Remote-SSH windows: see [In VS Code](docs/vscode.md).

Each release also has the Plasma widget as a `.plasmoid` and the GNOME extension as a `.zip`. To update: `git pull && ./install.sh` (VS Code from the Marketplace updates by itself; a downloaded `.vsix` needs the newer release's).

## Documentation

- [Installing, updating and removing](docs/install.md): requirements, the status-line snippet, installing by hand
- [Features](docs/features.md): everything it shows and does, in detail
- [Using it](docs/usage.md): what each click does, the settings, accounts
- [Sharing chats between accounts](docs/sharing.md)
- [On GNOME](docs/gnome.md)
- [In VS Code](docs/vscode.md): the extension's view, its settings and commands
- [Privacy](docs/privacy.md): it reads Claude Code's files, calls no Anthropic API itself and sends nothing anywhere
- [How it works](docs/how-it-works.md)
- [Troubleshooting and limitations](docs/troubleshooting.md)
- [Development](docs/development.md): tests, the layout of the code, releases

## About this project

I built Talpy Den to make my own day-to-day work with Claude Code easier. With several chats running across different profiles and machines, I wanted one glance at the panel to tell me which chats need me and how much of my plan I've used. I'm sharing it in case it's useful to others.

### Not affiliated with Anthropic

This is an independent, personal project. It is not affiliated with, endorsed by, sponsored by or otherwise connected to Anthropic, PBC, and building it does not make me a representative of Anthropic in any way. "Claude" and "Claude Code" are trademarks of Anthropic, PBC; they appear here only to describe what Talpy Den works with.

Talpy Den only reads files that Claude Code writes on your own computer, and changes them only when you ask it to: when you share a chat between your accounts, delete a chat, a plan or a memory (to the Trash), add, remove or pick the default account, allow or revoke a permission, undo or commit a chat's changes from its review, or turn on live mode or answering permission prompts from Talpy Den (a hook in Claude's settings). It does not call any Anthropic API itself, and it sends no data anywhere: plan usage that's old while a chat works (in VS Code's Claude Code panel, which runs no status line) is fetched by Claude Code's own `/usage` (`claude -p /usage`), logging in and out is Claude Code's own command, and dictation runs on your computer ([Privacy](docs/privacy.md) has the details). The *Open Usage Page on claude.ai* menu entry just opens that page in your browser.

### AI-assisted development

The code, tests and documentation in this repository were largely generated with an AI coding assistant (Claude Code, using Anthropic's Claude models) under my direction. I defined what Talpy Den should do, made the design decisions, and reviewed and tested the result on my own machine (Fedora, KDE Plasma 6).

As with any open-source code, please read it before you run it. It is provided under the MIT License, "as is", without warranty of any kind.

## Credits

[Claude Usage Widget](https://github.com/projectvelox/claude-usage-widget) inspired how the pet reacts to usage and clicks.

## Author

Made by Wadhah Zai El Amri: more of my projects and work are on [my website](https://wzaielamri.github.io).

## License

[MIT](LICENSE) © 2026 Wadhah Zai El Amri
