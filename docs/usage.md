# Using Talpy Den

## What a click does

| Where | What it does |
|---|---|
| Panel icon | Left-click opens the popup, middle-click refreshes. Right-click: *Refresh*, *Show Hidden Chats Again (N)* (and *… Plans …*, *… Memories …*, *… Projects Again (N)*, each while something of that kind is hidden), *Go to the Chat That Needs You* (when one does), *Play with Talpy* and *Playful Talpy* (with the pet on), *Open Usage Page on claude.ai*, the *Default Account* (with two accounts or more), and the settings. |
| The popup's top row | The tabs, then Focus and Find a chat (on the first tab), SSH hosts, Refresh (on the Recap, Permissions or Projects tab it reads that tab again too: they have no button of their own for it), and the gear: the settings (in the system tray, the tray's own heading has that button). |
| The big Talpy | Click its headline (*… needs you*) to go to that chat. Click it to pet it (four quick clicks: he laughs, *Let's play!*, and a game starts, asleep too: he grumbles at the first three, then wakes up for it; *Play with Talpy* in the right-click menu, or VS Code's **⋯** menu, too), double-click to make it dance, drag it out of its burrow (it hangs on for a second), or push it down into it (a drag that starts downward: it hangs on and pushes back, sinking a little, until you hold it down for a second or push on and it gives in; let go before that and it springs back up; back up or sideways, you pull it out instead, and back down before it's out, you push it in again). Double-click its stage a little away from it for a cookie: it runs after it as you drag the cookie around (let go and it floats down; pick it up again any time), and eats it. With *Playful Talpy* off (settings, or the right-click menu; in VS Code the view's **⋯** menu), Talpy only shows what your chats do: no tricks or props, no jokes, no cookie (one that's out vanishes in a puff, and he digs in where he is). |
| A chat's name | Jumps to the chat: its terminal tab, its VS Code window, or a terminal attached to the background chat. |
| The line under a chat | Unfolds your last prompt, Claude's reply, the chat's tasks, and buttons that compare what it changed (all of it, or its last turn). |
| **±3** next to a chat | Compares the files the chat changed in VS Code. |
| An account's token line | Unfolds its last 14 days: tokens per day, chats, prompts, busiest folders and models. |
| Talpy Den's keyboard shortcut | Goes to the chat that needs you, else opens the popup (set the key in the settings, on the Keyboard Shortcuts page). |
| Hovering a chat | Its row is shaded (a recent chat's, a plan's or a memory's line too, as in VS Code and GNOME). ■ stops or interrupts a chat (it asks first; for a chat that keeps going, also whether to turn that off), the hide button (a struck-out eye) hides a finished one, the trash button deletes it to the Trash (it asks first), and the share button shares a chat with your other accounts. The buttons also show while the chat's name or one of them has the keyboard's focus (Tab gets there), and on a touch screen when you press and hold the row. |
| A chat's pet | Opens its chat. |
| The speech bubble with a plus next to an account (**New chat**) | A field for what Claude should do (optional), then the account's recent folders and **Choose folder…** (an SSH host's: its home folder instead). Click one for a new chat there: in a terminal, in VS Code (the switch at the top of the list) or, with a task and **In the background**, as a background chat. |
| *Recent chats* | Unfolds the account's older conversations, newest first, a page at a time (as many as the *Recent chats* setting; **Show N more** under them for more, and the title says how many of all show: *Recent chats (5 of 23)*; folded again, it starts over). Click one to reopen it, in a terminal or in VS Code (the switch at the top of the list). Hovering one, the trash button deletes it (it asks first). |
| *★ Starred chats*, *★ Starred plans* | The chats and plans of the account you starred, however old, newest first, a page at a time as *Recent chats*. |
| A plan (under *★ Starred plans*, or in its project in the **Projects** tab) | Click it to open it. Hovering one: ▶ carries it out in a new chat, ◀ goes back to the chat that made it, **Move to project…** (a page with an arrow out of it) puts its file into a project's own plans folder, the share button shares it with your other accounts, the hide button hides it and the trash button deletes it (both ask first). One in a project's folder has **Move back** (an arrow into the page) instead of sharing. *chat gone* where its folder would be: the chat that made it went before Talpy Den saw it, so its project isn't known. |
| Dragging a plan by its name in the **Projects** tab | Onto another project's card (it lights up; near the top or bottom the list scrolls): asks to move the plan there, at the top of that card. Dropping it on its own project or outside a card does nothing. |
| The question before a plan moves | Where it goes; *Keep this project's new plans there too* (checked: the project's `.claude/settings.local.json` names `.claude/plans`, so Claude's chats there find the plan; unchecked, they won't find it by its name); whether git would show it; **Keep both** or **Replace** when a plan of that name is there. **Move** moves it; Esc, **Cancel** or a click anywhere else leaves it (Enter doesn't move it). |
| **Plan ↗** next to a chat | Opens the plan that chat wrote, to read. |
| **✎** next to it, or in a plan's row | Opens the plan's Markdown file to change it (your text editor; VS Code if the settings open plans there). |
| **↩ Send to Claude** next to a chat | You changed its plan: sends your changes to the chat, which revises the plan. |
| The account's `CLAUDE.md` (its last line: *Your instructions for every chat on this account*) | Click it to read it, ✎ to change it. |
| A memory (in its project in the **Projects** tab) | What Claude remembers: click one to read it, ✎ to change it, the hide button to hide it, the trash button to delete it (it asks first). |
| **Continue on …** under a chat | A usage limit stopped it: continues it on that account, which has room left. |
| **Go on at …** under a chat | A usage limit stopped it: it goes on by itself in the background once the limit resets (click again to cancel). In *Recent chats*, its **Limit** tag does the same. |
| **☆** next to a chat, a recent chat or a plan | Stars it: the account lists it under *★ Starred chats* or *★ Starred plans*, however old it is. **★** unstars it. |
| **Keep going** under a chat | The same, and again after every later limit, until it's done (in *Recent chats*: **↻**). Click **↻ Keeps going** to stop that; red, it says why: *(gave up)* or *(can't go on now)*, with more in its tooltip. |
| A queued task under an account | Starts it now, or cancels it (it asks first when it has text you wrote). A chat's go-on isn't listed there while the chat has a row: its **Goes on at …** tag says it. |
| **⚠ Same files** next to a chat | Goes to the other chat that changes the same files. |
| Filter button at the top (**Focus**) | Shows only what needs you, the chats that finished a turn you haven't looked at yet and one line for each chat at work; **Show everything** goes back. |
| Microphone in the chat pane (**Dictate**) | Records your reply and writes it into the box (click again to stop); the first time, it offers to set dictation up. |
| Magnifier at the top | Finds a chat by the words in its name, folder or your prompts, and project folders, plans and memories with those words. |
| Hosts button at the top | Picks the SSH hosts and containers to show; **Reload** reads `~/.ssh/config` and the container lists again, the picker staying open (*Reloading…* until they've answered). |
| The eye button next to an SSH host's name | Shows that host's hidden chats, plans, memories or projects again. |
| **Start** at a stopped container | Starts it (`docker start`), then shows its chats. |
| A project in the **Projects** tab | Click it to open it: its open chats, Claude's last recap of it, its chats, plans and memories, a page at a time. The speech bubble starts a new chat there; the hide button (a struck-out eye) hides it from the tab (nothing is deleted); right-click → *Show Hidden Projects Again (N)* brings it back. |
| A project in the Recap's *Where Claude worked* | Opens it in the **Projects** tab. |
| **Log in…** at an account | An account that isn't logged in (a new one, or one you logged out of): a terminal opens with Claude's own login. |

## Settings

Right-click Talpy Den's icon → **Configure Talpy Den…**, or the gear at the end of the popup's top row. The settings come in pages, the same categories in the same order as VS Code's and GNOME's settings: *General*, *Chats*, *Notifications*, *Usage & limits*, *Talpy*, *Recap*, *Hosts* and *Advanced*, then *Accounts* (below) and Plasma's own *Keyboard Shortcuts*.

### General

The chat list, then the panel icon.

| Setting | Default | |
|---|---|---|
| Recent chats per account | 5 | How many show at a time in *Recent chats*, *★ Starred chats* and *★ Starred plans* and a project's lists (**Show N more** for more); 0 hides *Recent chats* |
| Keep finished background chats | 24 h | 0 hides them right away |
| Tokens | on | Token totals |
| Usage | on | The default account's 5-hour usage next to the icon |
| Icon | on | Blink while a chat needs you (until you open the popup), pulse when one finishes |

### Chats

Where chats open, new chats, permission prompts, the chat window.

| Setting | Default | |
|---|---|---|
| A click on a chat opens it beside the popup | on | Off: in its terminal or VS Code tab. Where new and recent chats open, a terminal or VS Code, is the *Terminal \| VS Code* switch at the top of their lists; the model, effort and permission mode a new chat starts with are picked in its new-chat box |
| Answer permission prompts from Talpy Den | off | The hook that lets rows, the pane and notifications answer permission prompts and Claude's questions (see [Features](features.md)); changes Claude's settings at once |
| Keyboard answers | off | Two global shortcuts that answer the chat that has waited longest for a permission, from anywhere: **Meta+Alt+Y** allows it once (a plan: approves it), **Meta+Alt+N** denies it (a plan: keeps planning). They take *Answer permission prompts from Talpy Den*; pick other keys in System Settings → Shortcuts → Talpy Den |
| Dictation language | auto | The language you dictate in (`en`, `de`, `fr`…), or auto to let whisper tell; below it, set up dictation, download, delete or pick a speech model, or remove faster-whisper |

### Notifications

When to notify, sounds, while you're away, the keyboard shortcut.

| Setting | Default | |
|---|---|---|
| Notify | both on | When a chat needs input, and when it finishes a turn… |
| …if the turn took at least | 30 s | …that ran at least this long |
| Sound | on, 70% | Sounds for needs input / finished / failed or stopped (a usage limit or an expired login stopped a chat): from your sound theme, a file, or none |
| While you're away | on, 5 min | Once the screen has been locked this long, one notification sums it all up when you're back |
| Phone | off | Meanwhile, send chats that need you (and, if you like, ones that finish) to your phone with KDE Connect: every paired phone that's reachable, or the one you pick; *Send a test* tries it |
| Keyboard shortcut | goes to the chat | Goes to the chat that needs you (else opens the popup); the key itself is set on the Keyboard Shortcuts page |

### Usage & limits

| Setting | Default | |
|---|---|---|
| Usage cap | off (90% when on) | Once an account's 5-hour or weekly window reaches it, the account's chats at work on this computer are stopped, once in that window (in tmux and VS Code's Claude the turn is interrupted and the chat stays open); queued tasks wait for the reset, and chats that keep going go on then. Chats you start or answer yourself afterwards aren't stopped again |
| Fetch plan usage older than | 5 min | VS Code's Claude Code panel runs no status line, so its chats don't bring plan usage up to date: while one of an account's chats works and its numbers are this old, Claude Code fetches them (`claude -p /usage`, as `/usage` does: no tokens, no chat saved), at most this often; on SSH hosts too. 0: never |

### Talpy

| Setting | Default | |
|---|---|---|
| Pet | on | Talpy in the popup and in notifications |
| Playful Talpy | on | His tricks and props, jokes, cookies and games; off, he only shows what your chats do (his moods, his lamp and quiet moves), and a game or a cookie that's out ends at once. Also in the right-click menu |
| Chat pets per account | 5 | 0 keeps only the big Talpy |

### Recap

| Setting | Default | |
|---|---|---|
| Monday recap | on | On Mondays, sum up the last 7 days in a notification (it opens the Recap) |
| Amounts in | US dollars | The Recap tab's amounts: US dollars (Claude's API prices), or another currency at the European Central Bank's rate of the day |
| Keep a history beyond Claude's 30 days | on | The Recap's **Overall** keeps the numbers of chats Claude Code has deleted, and your plan's windows that ended for 90 days. Unticking it asks first when the history holds such chats or windows, since they go for good; **Delete Saved History…** starts it again (the windows go too) |
| Suggest rules for the permission prompts you answered | on | The Permissions tab offers rules that would have let those prompts through, each with **Allow**; off, it only counts the prompts |

### Hosts

SSH hosts and containers are picked with the hosts button at the top of the popup.

| Setting | Default | |
|---|---|---|
| Check SSH hosts every | 30 s | Containers too |
| Plan usage on SSH hosts | once per account | An account on this computer and a host (or on two hosts) shows its plan usage where it's listed first, with the newest numbers of them all; or on every host, or on none |
| Show containers | on | Docker, Podman and nerdctl containers in the hosts picker; off, no container engine is asked anything (the picked ones stay picked) |
| List containers active in the last | 30 days | Stopped containers started or stopped in these days are listed with the running ones; 0: only running ones |

### Advanced

How often Talpy Den checks, extra Claude folders, where plans open.

| Setting | Default | |
|---|---|---|
| While a chat works, check every | 2000 ms | How often a working chat's line (what it's doing) is brought up to date; greyed out with live mode on, whose steps show as they happen (a working chat is checked every 6 s then) |
| While no chat works, check every | 20000 ms | For what changes while no chat does anything: plan usage and its forecast, a usage limit resetting, a queued task coming due, a Claude that crashed. A chat that starts, ends, starts working, asks for something or finishes its turn shows at once either way |
| Live mode | off | A hook that notes each step of each chat as it happens (Claude doesn't wait for it), so rows, the pane and the line under the big Talpy follow every tool call; changes Claude's settings at once |
| Extra config dirs | – | Claude config folders besides `~/.claude` and `~/.claude-*` |
| Open plans and runs in | Okular if installed, else your browser | Plans and subagent runs (Markdown): in Okular, your browser (a page Talpy Den makes), VS Code (in a tab of the Talpy Den extension for VS Code, 1.13 or newer), or your app for Markdown files |

## Accounts

The **Accounts** page of the settings (on GNOME, the *Accounts* tab of its settings) lists the Claude accounts on this computer, or with **On:** those of an SSH host you picked in the popup: each one's folder, whom it's logged in as (Claude's own `claude auth status` says), whether it's the default, whether plain `claude` or VS Code's Claude runs on it, and its running chats. It works with one account or many, with `~/.claude` as a folder or as a link to one of them, with or without VS Code:

- **Add an account:** a name, e.g. `work`, makes `~/.claude-work` (with a `.profile-name` file holding its name), then opens a terminal with Claude's own login (`claude auth login`): Claude opens your browser, you sign in with the other account, and Claude keeps the login in that folder. The account is in the popup right away, with **Log in…** until you're logged in.
  - **Settings shared with** an account you pick: its `settings.json` (your status line too, so the plan usage bars work at once), `CLAUDE.md`, `keybindings.json`, and your own skills, agents, commands and output styles one by one, are linked into the new folder. A change on one account is a change on both. The links point at the real files, never through `~/.claude` (which may be switched to another account). The login, history, MCP servers, plugins and the skills claude.ai syncs for an account (`skills/synced`) stay per account. Or *Claude's defaults*: a fresh folder.
  - **A `claude-work` command** (on unless you untick it): `~/.local/bin/claude-work` runs Claude on the account in any terminal, in bash, zsh or fish. An existing program of that name is never replaced. Where `~/.claude` links to the account, it runs Claude under that name, as terminals do, since Claude keys its background service by the folder's name.
- **Log in…** for an account that isn't logged in; **Log out…** (asks first) is `claude auth logout`: Claude revokes the login and deletes it, and the account's chats and history stay. Not while chats run on it: they'd lose the login.
- **Remove…** (asks first) logs out, then moves the folder to the Trash, with its chats, history and settings: restore it from there if you change your mind. Its `claude-NAME` command goes too. Only for `~/.claude-NAME` folders that no chat, `~/.claude` (a link to it) or VS Code's Claude uses. Chats shared with your other accounts stay on them, and so does what they share from it: settings an account was added with (**Settings: Shared with…**), or a `projects` folder linked into it, moves to the first account that links to it (the default account first) before the folder goes, the others keep sharing it there, and the question says where each goes.
- **Make Default:** the default account is listed first in the popup (and in the VS Code extension), marked **default** where a machine has two or more accounts, its 5-hour usage goes next to the panel icon, and both VS Code's Claude and plain `claude` run on it. **Make Default** points them there: VS Code's Claude through its `claudeCode.environmentVariables` setting (only that entry of VS Code's settings file changes; its comments and the rest stay), plain `claude` by pointing the `~/.claude` link at the account. Where `~/.claude` is a folder, it's never turned into a link: plain `claude` stays on it, and `claude-NAME` runs the others. A link is only re-pointed, never made (also where there's no `~/.claude`): without `CLAUDE_CONFIG_DIR` set, plain `claude` reads its account settings from `~/.claude.json`, whatever the link says, so a `~/.claude` link of your own needs `export CLAUDE_CONFIG_DIR="$HOME/.claude"` in your shell (profile tools that make the link set it). Without VS Code and a `~/.claude` link there's nothing to switch, and **Make Default** doesn't show. The panel icon's right-click menu has the accounts too, under **Default Account**, to switch without opening the settings. Which account is the default: VS Code's Claude's where VS Code is installed (what the VS Code extension's status bar shows), else plain `claude`'s. When the two differ (say you switched VS Code's Claude by hand), the page says so, and **Make Default** on the default lines plain `claude` up with it.
  - **Not while it would cut a chat off:** a chat working in VS Code's Claude (VS Code's account changes, and its window reloads), or any Claude running through the name `~/.claude` (a chat in a terminal, VS Code or the background, or Claude's background service: pointed elsewhere, it would go on on the other account). Close those, or let them finish, then try again. Chats started on an account's own folder (`claude-work`, the new-chat bubble in the popup) aren't affected.
- **On an SSH host** (**On:** at the top), all of this works the same, on the host's own accounts: over ssh, with nothing installed there (`accounts.py` goes over the connection like the status script). Logging in opens a terminal here, where Claude's login runs on the host: open the address it shows in your browser and paste the code you get back. Its default account is the one its VS Code server's Claude uses (that server's settings), else plain `claude`'s there, and it's marked **default** in the host's part of the popup. **Make Default** there changes that server's setting (only that entry; the file's comments stay) and the host's `~/.claude` link, with the same checks, made on the host; removing an account puts it into the host's own Trash.

Talpy Den never sees a login: you sign in on Claude's own pages, and Claude itself writes and deletes it (`.credentials.json` in the account's folder, which Talpy Den never opens). On an SSH host the code you paste goes into that terminal, straight to Claude on the host. A login terminal in VS Code isn't kept or restored by VS Code.

Chats aren't copied between accounts: to move a chat to another account, share it (see [Sharing chats](sharing.md)).

**The icon** shows one number, the most urgent: red for chats that need you, else green for chats that finished since you last opened the popup (turns as long as the "finished" notifications ask for). While a chat works, Talpy glances around; hovering the icon lists every count.

**In the system tray (Plasma):** Talpy Den can sit in the system tray as well as (or instead of) on a panel: right-click the tray's arrow → **Configure System Tray…** → **Entries** → **Talpy Den**. It's off until you switch it on. *Shown when relevant* shows it while a chat runs; clicking it opens the same popup. With two Talpy Den widgets or more (say one in the panel and one on the desktop), only one of them sends notifications and sounds: a copy with a popup (in a panel or the tray), the one running longest, so what a notification opens shows where you can see it; a copy shown in place on the desktop notifies only when no copy with a popup runs, and a lone copy always does. They share their settings: a change in one shows in the other within a few seconds, and a new one starts with what the others use.
