# Changelog

## Unreleased

### New

- **Your chats' states for other programs:** your chats, here and on
  your SSH hosts and containers, with their states and where each one
  runs, and your accounts' plan usage, go to
  `$XDG_RUNTIME_DIR/talpy-den/jobs.json` whenever one changes, for a
  status bar, a desk display or a script to follow (it can wait for the
  file with inotify instead of asking again and again).
- **Model and effort for one chat:** in a background chat or one that isn't
  open, `/model` and `/effort` list the models and effort levels as you type,
  and the one you pick (or `/model sonnet` typed) is for that chat alone:
  Claude's own commands save it as your default for every new chat. A
  background chat open idle takes it at once; one that isn't open, from your
  next message. A chat in a terminal still opens them there.
- **Right-click in Talpy Chat:** on the conversation, *Copy*, *Copy message*
  (as its Copy button) and *Select all* (every message; Ctrl+A there too);
  on the reply box, *Undo*, *Redo*, *Cut*, *Copy*, *Paste* (VS Code's own,
  as Ctrl+V: a picture too) and *Select all*, each with its key.
- **Old chats, your stars kept:** `talpyDen.oldChats` picks who deletes old
  chats and plans: Claude Code's own cleanup (the default: everything older
  than its `cleanupPeriodDays`, starred or not, for good) or Talpy Den, once
  a day, after `talpyDen.oldChatsDays` unused: it keeps what you starred and
  chats that are open, queued or keep going, and moves old plans to the Trash;
  here and on the SSH hosts and containers shown. Choosing it, or fewer days,
  asks first with what its first run deletes; **Talpy Den: Old Chats** shows
  each place's last run. One choice with Talpy Den on Plasma or GNOME.
- **Search and folds in Talpy Chat:** **Ctrl+F** (*Talpy Chat: Find in the
  Chat*) opens a find bar over the conversation's top right: what you type is
  found in what the tab shows (on Steps, what each step ran and got too), the
  matches near what you read marked in VS Code's own find colours, and the
  conversation stays where you read until you go to one: **Enter** or **F3**
  the next one from what you read, **Shift+Enter** or **Shift+F3** the one
  before (*3 of 12*); one in a folded part unfolds it first; **Esc** closes
  it. A message, reply or command output longer than about 40 lines shows its
  first 24 with *Show more · N more lines* (and *Show less*); a step's long
  output too. What the tab first read folds, but Claude's last reply then;
  what comes in while it's open doesn't. **Ctrl+O** (*Talpy Chat: Unfold or
  Fold Long Messages*) unfolds every long one and your answered questions and
  plans, and again folds them back as they were.
- **Keys in Talpy Chat:** each a command, *Talpy Chat: …*, whose key applies
  only while a Talpy Chat tab has the focus (never with it in the terminal or
  the side bar), and can be changed in Keyboard Shortcuts: **Ctrl+Enter**
  sends now (while Claude works, without the 5 s wait; in an empty box, the
  message waiting goes now), **Alt+Enter** when this turn ends,
  **Ctrl+Shift+Enter** on in the background where that button shows,
  **Ctrl+L** clears the box (Ctrl+Z brings it back), **Alt+1…4** take a
  suggested reply (with Shift: into the box first), **Alt+Y / Alt+A /
  Alt+N** answer what it asks as Allow once / Always allow / Deny… do,
  **Ctrl+↑ / Ctrl+↓** go to your previous / next message, **Ctrl+1 / 2 / 3**
  to Chat, Steps and Review, **Ctrl+T** shows or hides its tasks,
  **Ctrl+Shift+C** copies Claude's last reply, **Ctrl+Shift+O** opens its
  window; on a Mac, Cmd for Ctrl. In the tab, **Esc** closes what's open
  first (a menu, the big picture, the `/` and `@` list, the list of keys,
  the grey completion) and only then, in an empty box while Claude works,
  stops it; **PageUp / PageDown** scroll the conversation from the box too;
  **?** in an empty box lists every key, and buttons' tooltips name theirs.
  **Talpy Chat with the Chat That Needs You** (Ctrl+Alt+Shift+Q): Go to the
  Chat That Needs You, in its Talpy Chat tab.
- **Copy copies all of a reply:** one Talpy Chat shows cut (past 20,000
  characters) is read whole from the transcript on the click, and *Copied*
  shows once it's on the clipboard, else it says why.
- **Times, Copy and new messages in Talpy Chat:** a line comes before the
  first item of each new day (*Today*, *Yesterday*, *Mon 3 Nov*), and none
  before the first. With the pointer on a message, yours or Claude's reply,
  its time and **Copy** show over its top right corner: a reply goes on the
  clipboard as Markdown, as Claude wrote it, yours as you wrote it;
  *Copied* says it for a moment in the same place. Scrolled up while new
  messages come in, *2 new ↓* shows over the bottom of the conversation; a
  click goes to the end. Nothing moves what you're reading, and a long chat
  costs nothing more per message.
- **Context left and the turn so far in Talpy Chat:** its header has a tag,
  *Context 69% left*: what's left before Claude compacts the chat on its own,
  counted as Claude Code counts it (what Claude's last message read against
  its model's window), in the warning colour once Claude Code would say it's
  close, its tooltip suggesting `/compact` then; none when it can't be
  known. While Claude works, the working line ends with *8m 12s · 58 steps*
  before Stop: the time since your message, to the second, and its tool
  calls since, its clock ticking only while the tab is in front.
- **Commands in Talpy Chat:** a command you ran shows in its tab as yours,
  wherever you ran it (`/context`, `/model fable`, a skill, `$ ls` for
  Claude's `!` mode), with what it printed under it in Claude's colours. The
  `/` list runs each where it can (as checked on Claude Code 2.1.318): most
  from here; `/permissions` opens the view's Permissions tab; one that needs
  Claude's own panel or dialog (`/config`, `/btw`, `/clear`, and `/model`
  and `/effort`, which save your default for every new chat) opens in the
  chat's terminal with the command typed in for you to press Enter there
  (this window's terminal, tmux, its Claude Code panel's input), else on the
  clipboard; one that can't run on that chat is greyed, saying why.
- **Suggested replies in Talpy Chat:** once Claude's turn is over, small
  chips above the box answer the question it ended with (its options, the
  one it recommends in bold; an either/or's halves; Yes or No in its
  language) or offer what you usually reply after a turn that ended the
  same way (a usage limit, a chat that stopped…), from your own chats on
  that account and only when it's a good share of what you sent then. A
  click sends it; Shift+click (or *Edit before sending* on its right-click
  menu) puts it in the box; Alt+1…4 picks one; *Don't suggest this* hides
  one of yours (**Talpy Den: Suggest Hidden Replies Again** brings them
  back). Never while Claude works or asks, and none for half an hour after
  five messages in a row that weren't one. What you type is completed in
  grey from your usual replies (Tab or →). Worked out on this computer;
  `talpyDen.suggestReplies` (on) turns it off, and then nothing is read.
- **Stop in Talpy Chat:** while Claude works, **Stop** on the working line
  stops what it does now, as Esc in its terminal; the chat stays and takes
  your next message. For chats in this window's terminals, in tmux and in
  the background (Claude Code 2.1.318 and later 2.1 versions); elsewhere its
  tooltip says where to stop it.
- **Open in: Talpy Chat.** One more choice, listed first, in the switch
  above Recent chats: *Talpy Chat | Terminal | Claude Code panel*
  (`talpyDen.reopenIn`: `talpyChat`; the default stays `terminal`). A chat
  that isn't running opens in its Talpy Chat tab, where your next message
  goes on with it in the background, and a background chat no terminal
  shows opens there too. *New Chat…* lists *In a Talpy Chat tab* first: an
  empty tab for that account and folder with a ⚙ line (model, effort,
  permission mode), and your first message starts the chat in the
  background, shown at once with *Starting…*; a task goes as its first
  message. What it asks is answered in its tab: chats Talpy Chat starts or
  wakes get Talpy Den's permission hook for themselves alone, unless it's on
  for every chat. *Answer it in a terminal* for a prompt it can't answer; a
  folder Claude doesn't trust yet starts in a terminal. This computer's
  chats only, for now: on an SSH host or in a container, *New Chat…* says
  *Talpy Chat: this computer's chats for now* and why in its section's
  place, as the switch's tooltip does.
- **Your answers show in the chat:** an answered question stays in Talpy
  Chat as Claude's (its options folded, the ones you picked ✓), with your
  answer right under it as your message: the options, what you typed and
  your notes; *Approved the plan* or *Keep planning* and your note; a
  Deny's note under its call. The same wherever you answered, and at once
  when you answer from Talpy Den.
- **SSH hosts' projects in the Projects tab:** each SSH host and container
  shown follows this computer's projects, under its name, with its projects
  as read there (week.py --projects --on HOST, over your ssh connection; each
  host on its own, so a slow one holds up no other): its open chats, recap,
  chats, plans and memories on the accounts they're on there, whose buttons
  act on that host (reopen, star, move, hide, delete); *New chat here* starts
  on it, with the command its read sent; a plan drags only onto a project of
  its own machine; the eye button next to its name shows what you hid there.

### Better

- **Talpy Chat: ultracode for one chat, and what a chat uses now.**
  `/effort`'s list has *Turn ultracode on* (Extra high effort, with
  ultracode) or *Turn ultracode off*, for that chat alone, your settings
  untouched. `/model` and `/effort`'s lists mark what the chat uses with ✓
  (*now*, or *from your next message*), and the line under the box says it
  (*Now: Opus · Extra high effort*).
- **Talpy Chat: Claude's thinking isn't shown as its reply.** The lines
  Claude Code writes to sum up Claude's thinking while it works are dimmed,
  in italics, after *∴*, as in Claude's terminal: such a line can tell what
  Claude means to do as if it were done. *Copy* on one copies that line
  alone, and Ctrl+Shift+C still copies Claude's last reply.
- **Talpy Chat:** a wake-up Claude scheduled for itself is a small note in
  its place, no longer a message of yours at the end of the chat; an
  answered question's options are a bulleted list, each with what it means
  under it.
- **Background chats open in Talpy Chat** whatever `talpyDen.reopenIn` says
  (one on this computer that no terminal shows); **Interrupt or stop** on a
  background chat's row at work; rows say *51% left* before Claude compacts
  the chat, counting your `autoCompactWindow`; Talpy Chat's header says
  *Working* without a second time; **Alt+Y** sends the answers to Claude's
  questions; turning the permission hook off asks whether the chats Talpy
  Chat started keep theirs.
- **Talpy Chat's icon:** Talpa with a speech bubble, on its tabs and the
  *Open in* switch (in colour) and on the buttons that open a chat in it.
- **A Remote-SSH window's host comes first** in the view, tagged *this
  window*, then this computer's accounts under a *This computer* head, then
  the other hosts.
- **One name: Talpy Chat.** A chat's tab is called Talpy Chat everywhere:
  *Open in Talpy Chat* on a row, in tooltips, settings and the docs.

- **Plan usage stays at its newest numbers.** An idle chat's status line,
  drawn again an hour after its last reply, no longer pulls an account's
  plan usage back to that hour's numbers (100% showed as 32%): each counts
  as of its chat's last reply.
- **Your plan's limits now, on today's Day.** The Recap shows it on the
  Day view of today only, with the newest numbers, as the Chats tab's.
- **Refresh brings the Recap the plan usage it fetched.** The Recap reads
  once more when the numbers Refresh asked for have come in, rather than
  keeping the old ones until you open it again.
- **Today against the days before by this time.** While today isn't over,
  the Recap compares it with the day (7 or 30 days) before up to this time
  of day, so its numbers don't look down until midnight.
- **One timeline on the Day.** *Chat by chat* has the day's own row, *All
  chats*, on top, on the same hours, and each chat's time and cost at its
  lane's end; *Through the day* and *Chats it worked on most* are gone from
  the Day, which said it again.
- **Rows of 7 days say their days** (*23–29 Oct*, *7–8 Oct*), and
  everything's oldest starts with your first chat's day.
- **What Claude did** lists only its *Other tools*, not the commands, edits
  and subagents counted above them.
- **Tips' shares** say what they are (*96% of usage*); their icons say where
  each tip comes from.
- **Your plan's limits over time** (was *Advanced analyses*) sits right after
  the limits now; the first tile says *You were at it*; project names get the
  room they need.
- **A copy keeps Talpy Chat's hook:** a chat Talpy Chat started that goes on
  as a copy (Keep going, a queued go-on) still has its prompts answered there.
- **One wake for two windows:** sending from Plasma's Talpy Chat and this
  tab to one stopped chat at once wakes it once (no copy of the chat).

## 1.18.0

### New

- **A month in the Recap:** **Day | Week | Month | Overall**: your last 30
  days, a row per week, against the 30 days before, stepping back 30 days at
  a time; its share card says *My month with Claude*.
- **How your plan's limits changed:** a folded section at the end of the
  Recap works out, from your own chats and the limit readings Talpy Den
  keeps for 90 days, how much a 5-hour window and a week of each account's
  plan held, week by week, and says when a plan change, or one of
  Anthropic's, changed that and by how much.
- **One status bar item:** Talpy with the count of chats that need you, and
  the default account's 5-hour usage beside its name (**1 · work 42%**); its
  hover changes the default account.
- **The chat tab looks like Claude's terminal:** in your terminal's font
  (`talpyDen.chatFont`), bold and headings in the terminal's blue, bullets
  in Claude's orange and code blocks in their language's colors. A code
  block's **Copy** says *Copied*.
- **A message sent while Claude works is queued:** for 5 s it waits with
  **Edit**, **Send now** and **Cancel**, then Claude takes it in at its next
  step, as its terminal's queue does.
- **Pictures in your messages** read *[Image #1]*, with a thumbnail under
  the message, big on a click.

### Better

- **Your message shows the moment you press Enter,** and Claude's reply as
  soon as it's written: the chat tab waits on the chat's transcript rather
  than reading it every few seconds. Messages to a chat go one after the
  other, in order, none dropped, and ↑ brings back the one you just sent.
- **A reply to a background chat that asks you something answers it** (your
  words go with a Deny, or as the answer to its question), and a message to
  a running background chat goes in as if typed there: the chat is never
  stopped for it.
- **A chat Claude moves to the background stays the same chat:** its tab,
  your messages on their way, its pet, star, Keep going and queued go-on
  follow it to its new id, also on SSH hosts, and Delete takes its older
  copy along.
- **The Projects tab:** projects stand out (a bigger, bold name, shaded
  under the pointer, their *Active chats* apart), a worktree's chats are in
  its repository's project, and plans and memories are where they belong:
  plan files a chat wrote itself, a project's plans folder after Claude
  deleted its chats, a renamed project's memories. A project under *Where
  Claude worked* in the Recap opens there.
- **A container is named as its section names it** (*web on lab*, not
  `podman:web@lab`) in every notification, question and menu.
- **The Talpy Den tab keeps its pets** while you look at another tab; the
  Permissions tab's lines are shaded under the pointer, and a prompt's and a
  question's buttons are framed.
- **Status checks stay quick** with many chats open in a big project.

### Fixed

- **Keep going:** one go-on at the reset, not two; a chat that keeps going
  on a hidden SSH host or container still goes on after a limit; its notes
  and notifications say what's so.
- **Limits and queued tasks as in Plasma:** a turn a limit broke off is no
  longer told as finished, a task due on an account at its limit waits for
  the reset, a reply that can't be sent is told, and a message held 5 s
  still goes when you close the chat's tab.
- **Rows show what's so:** a chat in Claude's VS Code panel or in the
  background no longer shows an old run's model and cost, the **Tests**
  badge counts only a test run, and a starred chat you fork stays under
  *Starred*.
- **Deleting a plan** takes its older copies and the tasks queued to carry
  it out along.
- **The Recap** lists every window of your plan (one at 0% too), counts an
  SSH host's work on the right day when its clock is off, and its history
  setting covers your plan's windows, here and on every host.
- **SSH hosts and containers:** a click finds the chats of a host named
  `user@host` and a chat in a VS Code terminal of a container on a host; a
  new chat in VS Code on a host waits for its window to connect; a Docker
  socket you can't use, an old python3 and a paused Podman container each
  say so; and containers follow **Show containers**, with the Permissions
  tab working on them.
- **Smaller fixes:** **Move to project…** on a plan from your home folder
  asks which project, removing an account keeps your other accounts' shared
  skills working, *Shared through git* only in a git repository, bold ends
  at its own marks, and Find a Chat and a plan's comments work in more
  places.

### Safer

- **A container or an SSH host can no longer pick a program Talpy Den runs
  on this computer:** its Python, SSH hosts, Claude folders and Recap
  history are read only from your own user settings, never from a remote
  window's machine settings or a workspace.
- **A repository or a remote can no longer start your chats with permission
  prompts off, nor stop them:** the new chats' permission mode, model and
  effort and the usage cap come only from your user settings.
- **A chat can no longer put a link that runs a VS Code command into a
  notification:** what a chat or a host wrote shows there as written.
- **Plans, subagents' runs and memories open in a Talpy Den tab**, rendered
  as the chat tab renders replies, which loads no pictures from the web (VS
  Code's Markdown preview did, the moment you opened one). **Open as text**
  shows the file in the editor, with a plan's comments.
- **Opening VS Code on a container or an SSH host asks once:** a click no
  longer attaches VS Code to it by itself (sharing your SSH agent and Git
  credentials, or your clipboard); **Open in a terminal instead** is there
  too.
- **Nothing in your `~/.cache` runs or acts any more:** Talpy Den's compiled
  Python and what it acts on by itself (queued tasks, chats that keep going,
  shared settings, permission answers) are in `~/.local/share/talpy-den` and
  `~/.local/state/talpy-den`, so a container given your cache can't run code
  as you, start a chat or answer a prompt. Older files move over by
  themselves.
- **A repository's links can no longer reach your files:** a plan or a plans
  folder linked out of it isn't listed, and Undo, Allow and Move to project
  never write through a link.
- **A plan can no longer press keys in its chat** when you send your
  feedback on it.
- **Permission prompts show what you allow:** an MCP tool's arguments,
  everything *Always allow* saves (in notifications too), *New prompt* when
  one takes another's place under the pointer; a notification for a long
  command offers **Open** instead of *Always allow*.
- **Containers and SSH hosts stay in their place:** Talpy Den works in a
  container as its own user, never root because of a label; a host can't
  pick what opens here, list another host as its container or send more
  than 16 MB; your replies to its chats aren't in its process list.
- **Odd files no longer hang Talpy Den:** a link to `/dev/zero` or a pipe,
  a big file or deeply nested JSON in a repository or a chat is skipped or
  compared in part.
- **Dictation's Set up** installs the versions it was checked with and
  checks each speech model's SHA-256.

Every change in detail is in the repository's
[CHANGELOG](https://github.com/wzaielamri/talpy-den/blob/v1.18.0/CHANGELOG.md).

## 1.17.0

### New

- **Keep going on SSH hosts and in containers:** a chat there goes on by
  itself after each usage limit, as one on this computer. A go-on that
  couldn't reach its host starts once the host answers again, and what keeps
  going on a host you don't show is still listed, with **Show** and **Stop**.
- **Docker, Podman and nerdctl containers**, here and on your SSH hosts,
  shown like SSH hosts: their accounts, chats, plans and Recap.
- **The Projects tab:** every chat, plan and memory by project. The view
  itself is what goes on now and your shortlists: recent chats, ★ starred
  chats and plans, a page at a time.
- **Delete** a chat, a plan or a memory (to the Trash), and **hide** plans,
  memories and projects as you hide chats.
- **Plans in a project's own folder** (`plansDirectory`, `.claude/plans`) are
  listed, and **Move to project…** puts a plan there.
- **Play with Talpy:** a cookie to chase, a tug of war for his burrow, push
  him into it, or four quick clicks for a game (Playful Talpy turns it off).
- **The chat tab** shows what each subagent does (its *Agents* tag), the
  chat's tasks, what Claude tells you as it works, and the chat's tags.

### Better

- **A background chat goes on where it is** after a usage limit (a terminal
  showing it stays on it), in its own permission mode, model and effort, and
  a go-on waits for the commands it runs in the background.
- **A chat Claude moved to the background** when you closed its terminal
  keeps its star, Keep going, queued go-on and name under its new id.
- **Stop asks about Keep going**, and every question comes before what
  can't be undone.
- **The Recap reads as a story**, and the settings come in categories.
- **One look everywhere:** the same icons, words and button order as Talpy
  Den on Plasma and GNOME, colour only where it means something, buttons
  that look like buttons, rows that keep their buttons in a narrow view, and
  High Contrast themes.
- **The status bar shows Talpy** without redrawing VS Code all the time, and
  VS Code and Talpy Den on Plasma don't slow each other down.

### Fixed

- Plan usage keeps up with chats in Claude's VS Code panel, and Refresh
  fetches it too.
- Replies arrive whole, reach the window that runs the chat, and wait for a
  turn to end, also on SSH hosts and in tmux.
- Allow and Deny answer what the chat asks now; *Always allow* works for an
  edit in a tmux chat.
- The review's Undo, Commit and Compare show what the chat changed.
- Remote-SSH windows, hosts whose login shell is fish or tcsh, and
  Disconnect, which leaves your terminals open.
- Many smaller fixes to the pets, the Recap and the Permissions and Projects
  tabs.

Every change in detail is in the repository's
[CHANGELOG](https://github.com/wzaielamri/talpy-den/blob/v1.17.0/CHANGELOG.md).

## 1.16.1

- **Enter on a chat in a terminal copies your reply:** for a chat whose
  terminal takes no text from outside, the first Enter in the chat tab
  changed nothing you could see (it only got ready to ask), and the next
  one, or an Enter on a reply from a notification, made Claude in that
  terminal quit and the chat go on in the background. Enter now puts your
  reply on the clipboard and opens the chat's terminal, to paste it there;
  Claude there never quits on an Enter. **Send, go on in the background**
  still moves it to the background.
- **Allow answers only what it showed:** Allow, Deny and the other answers
  in a notification, a chat's row or its tab answered whatever the chat
  asked by then: a chat answered in its terminal that asked something else
  right after got no new notification, and the old one's Allow approved the
  new prompt, one you never saw. An answer now goes only to the prompt it
  showed (in tmux, `pane.py --keys … --expect`): when the chat asks
  something else, nothing is answered, you're told, and the new prompt gets
  a notification of its own.
- **A message goes once:** Enter pressed twice, or Enter and then Send, in a
  chat tab sent your message twice (in tmux typed in twice, in the
  background two runs). The box says *Sending…* until it has gone, and a
  chat takes one message at a time.
- **Chats in the Recap and Projects tabs reopen:** clicking one that wasn't
  running and wasn't among the account's recent chats said it *runs in a
  terminal outside this VS Code window* and opened nothing (where windows
  can't be brought up: GNOME without the Talpy Den extension, XFCE, macOS).
  It reopens in VS Code's terminal now (in a Claude Code tab where the
  switch says so), with the account's recent or starred chats' command, else
  the one `jump.py --resume --print-command` gives.
- **The microphone stops with the tab:** a second click on Dictate while the
  microphone was starting started a second recording, and closing the tab
  (or ×) then left that one recording for up to 5 minutes. A click while it
  starts does nothing now, and a closed tab stops a recording that's
  starting.
- **No errors after closing a chat tab:** a tab closed while it was reading
  its chat (seconds, for an SSH host's) logged *Webview is disposed* errors
  and went on reading. Nothing more is read or sent once it's closed.
- **Copying the Recap's card** used a file of a fixed name in the temp
  folder: on a computer you share, another user's card of the same day made
  it fail without a word. It's copied from a private folder of its own now,
  and a failure is said.
- **A setting checks again only what it changes:** every change to a Talpy
  Den setting (the chat tab's text size, a sound) checked every SSH host
  again. Now only one that changes what the checks run with does.
- **From the Plasma widget's fixes** (the same Python helpers): answering
  permission prompts and live mode work on Debian and Ubuntu, whose `sh` is
  dash, and with a space in your home folder's name; two Claude folders of
  one name (`~/.claude`, `/data/.claude`) no longer show each other's plan
  usage; in half-hour time zones (India, Nepal) the Recap counts tokens and
  cost on the right day; and Undo no longer deletes a file that was there
  before the chat when no earlier copy of it was kept.
- **Development:** fast-uri, markdown-it and undici (packages of the build
  tools) updated for their security fixes.

## 1.16.0

- **Now Talpy Den:** the extension is called **Talpy Den** and the pet
  **Talpy**. It is a new extension (`wzaielamri.talpy-den`, settings
  `talpyDen.*`): install it and remove *Claude Status* from VS Code's
  extensions. Your `claudeStatus.*` settings are copied to `talpyDen.*` the
  first time it starts (what you had already set under the new names stays).
  Its data folders moved to `talpy-den` by themselves (a link stays under the
  old name for an older status-line snippet), and the plan-usage setup
  recognizes what the old extension added (its snippet, its status-line
  wrapper) and brings it up to date. In the view the app's name is the first
  tab (your chats), where the title *Claude Code* and a *Chats* tab were.
- **Replies you send while Claude works show in a chat's tab:** a message
  sent in the middle of a turn never showed there (only prompts that started
  a turn did). It now shows the moment you send it, where you sent it, and
  only once; one you take back into your input box goes away again.
- **The weekly bar after a reset:** right after a week's limit reset, the
  weekly bar vanished until your first reply of the new week (Claude Code
  leaves that window out until it has usage). It now shows as *reset* at 0%.
- **A chat you continued on another account is listed once:** a background
  chat that waited at one account's usage limit and that you went on with on
  another account was listed on both. It's now listed where it runs, and the
  other account says where that is.
- **The Output tab looks like the terminal:** a background session's screen
  shows in Claude's own colors on a terminal's dark ground (tool calls,
  diffs, the spinner, the prompt box, your status line), stays at the end as
  it changes unless you scrolled up (⤓ takes you back), and is drawn again
  only when the screen changed.
- **Pets move in even steps:** each picture of a pet's move shows for the same
  number of frames (counted, not timed), so a frame that comes a little early
  or late no longer makes one picture show for a frame and the next for three.
- **Changes you can read at a glance in a chat's tab:** each edit shows its
  change right under it: line numbers, removed lines in red and added ones in
  green, the words that changed marked brighter, and the file's syntax
  colors. Folded, an edit shows the lines around its first change; click it
  for all of it. Where the tab is wide enough a change shows **side by side**
  (before | after); the switch in its corner, the Review tab's *Side by side*
  button and `talpyDen.diffSideBySide` set it. A change you're asked to
  allow shows the same way.
- **Tool calls that read well:** a call says what it did in code's font
  (**Bash** `git status`), and unfolded it shows the command and what it
  printed apart, a file it read as numbered lines in the file's colors, and
  a search's settings by name.
- **New files in the Review tab:** a file a chat made outside its folder
  showed *no earlier version kept* and nothing else; now the chat's own Edit
  and Write calls tell how it was (a new file shows all its lines as added),
  and one still unknown shows its lines as they are now.
- **Attach with +:** a **+** button by *Dictate* and *Screenshot…* opens VS
  Code's file dialog in the chat's folder: a picture goes into your reply as
  one, another file is named for Claude to read.
- **Smooth pets:** the chats' pets went through four pictures a move and
  faded from pose to pose; now each pet plays its moves as they are, a
  picture each frame of the move, each drawn once and shown again round
  after round, and moves from pose to pose through pictures in between.
  What flies about (dirt, hearts, z's, confetti) shows for every pet. The
  open burrow is drawn once and copied into each picture, which halves what
  a picture costs. A pet you pick up trails your mouse on a spring, swings
  as you move it and wobbles when you let go.
- **Projects:** a new **Projects** tab with each project you chatted in
  (its git repository, else its folder), the newest first: its chats at
  work now, Claude's last recap of it, how long Claude worked on it and what
  that cost (the last 7 days and everything kept), its latest chats (click
  one to bring it up), its plans and memories, and **+** for a new chat
  there (on the account of its newest chat, with that folder first).
- **Share your week as a picture:** the share button in the Recap makes a
  card of the period shown (a day, the 7 days or everything): Talpy, how
  long Claude worked and how long you did, your prompts and chats, Claude's
  work day by day and the tokens, with your projects' names if you tick
  *Name the projects on it*. **Save** puts it in your Pictures folder,
  **Copy** puts it on the clipboard.
- **The day, chat by chat:** the Recap's **Day** view has a lane for each
  chat that did something that day: when Claude worked, when it waited for
  you to allow something or answer a question, and when it was paused
  (asleep, a usage limit); between those it was your turn. Point at a lane
  for its numbers; a name brings the chat up.
- **The Monday recap:** once a week (Monday from 9 o'clock, or the first
  time VS Code runs after that), a notification sums up the last 7 days:
  how long Claude worked over how many chats, your time and prompts, the
  project most of it went to, and against the week before; **Open the
  Recap** shows them. It comes once, here or in the Plasma widget
  (`talpyDen.mondayRecap` turns it off).
- **A background session's screen:** the tab of a background session
  (`claude --bg`) has an **Output** tab: its terminal as Claude draws it
  right now (what `claude attach` would show), read again every 2 seconds
  while you look at it, from its background service (never started for it).
- **Dictate a reply:** **Dictate** in a chat's tab records what you say;
  click it again and whisper writes it down where you're typing (× drops
  it). It runs on this computer only (not in a Remote window): what you say
  never leaves it, and the recording is deleted once written down. The first
  click offers to set dictation up: faster-whisper (from pypi.org, in a
  Python environment of its own) and its base speech model (from
  huggingface.co), about 610 MB in `~/.local/share/talpy-den/whisper`,
  no sudo and no compiler needed. If whisper.cpp's `whisper-cli` is on your
  PATH it's used instead. **Talpy Den: Dictation Models…** lists the
  speech models (tiny to large-v3-turbo, with their sizes and what each is
  like) to download, delete or use (by default the best one downloaded), and
  removes faster-whisper again; one choice for the extension and the Plasma
  widget. `talpyDen.dictateLanguage` (auto by default).
- **A reply box that helps:** in a chat's tab, `/` at the start offers
  Claude's commands, your own and the project's commands and skills (with
  what each does); `@` offers the project's files; ↑ and ↓ go through what
  you asked in that folder before. ↑ / ↓ pick, Tab or Enter takes one, Esc
  closes the list.
- **Drop files and screenshots on a chat:** in a chat's tab, drop files
  from VS Code's Explorer on the reply (hold Shift while dragging, as for
  any web page in VS Code): a picture goes in as a pasted one, any other
  file is named in it (`@path`, as in Claude's prompt); pictures can be
  dropped from anywhere. **Screenshot…** lets you pick a region of the
  screen and puts its picture in your reply (Spectacle; GNOME Screenshot,
  grim and slurp, or maim elsewhere). An SSH host's chat takes pictures
  only (copied there).
- **Keyboard answers:** *Allow the Oldest Prompt* (Ctrl+Alt+Shift+Y) and
  *Deny the Oldest Prompt* (Ctrl+Alt+Shift+N) answer the chat that has
  waited longest for a permission (a plan: approve it, or keep planning);
  the status bar says what was answered. They take *Answer Permission
  Prompts from Talpy Den*.
- **Approve a plan from VS Code:** a chat that leaves plan mode shows its
  plan in its row (*Read the whole plan* opens its tab) and in its chat
  tab, with **Approve, accept edits**, **Approve** and **Keep planning…**
  (what to change: Claude works on the plan and shows it again). Its
  notification has the same buttons. That takes *Answer Permission Prompts
  from Talpy Den*; the chat's own dialog works too.
- **Focus view:** the filter button beside the tabs shows only what needs
  you: the chats waiting for you as full rows (their questions, Allow /
  Deny), the chats that finished a turn in the last 15 minutes, one line
  for each chat at work with what it does now (click to open it), how many
  others are idle or done, and each account's 5-hour usage. **Show
  everything** (or the button again) brings back the whole view.
- **Motion in the list:** a chat that moves up or down the list slides to
  its new place instead of jumping, a new chat fades in, the usage and
  context bars and the usage numbers glide to a new value, a tab slides in
  from the side it's on, and the chat tab grows open. Nothing moves when
  your system asks for less motion.
- **More for Talpy to do:** it blows soap bubbles, grows a flower and
  smells it, eats a cookie, takes a selfie, hops like a bunny, boogies, and
  cheers *yay!* when a chat finishes; petting it may get heart eyes, a wink
  or a blown kiss; asleep it dreams with a bubble at its nose, watches a
  shooting star or a firefly.
- **Chats change the moment they do:** this computer's chats were checked
  every 2 seconds (every 10 while the view was hidden), so a chat that
  started, waited for you or finished showed up late, and each check cost a
  little, also while nothing happened. Now the extension watches Claude's
  session files: a chat that starts, ends, starts working, asks for
  something or finishes its turn is checked at once (also when you answer
  or interrupt it in its terminal), with its pet, notification and sound. In
  between it checks far less often: every 20 seconds while no chat works,
  every 6 while the window isn't focused. Chat tabs read the conversation
  again when their chat changes, too.
- **Live mode:** each step of each chat as it happens: its row says what it
  does right now (*▸ Edit: parser.py +12 −3*, *▸ Bash: pytest*), and its tab
  reads the conversation again at each step (else every 5 seconds, not 1.5).
  **Talpy Den: Live Mode…** turns it on: it adds a hook to each Claude
  profile's `settings.json` that notes each event of a chat in
  `~/.cache/talpy-den/live` (Claude doesn't wait for it). Then the rest
  is checked every 6 seconds while chats work.
- **A setting for the checks while no chat works:** `talpyDen.idlePollInterval` (20 s by default) sets how often this computer is checked while no chat works, for what changes without a chat doing anything (plan usage, times); `talpyDen.pollInterval` says it's for while a chat works, and has no effect with Live Mode on.
- **What the chats do now, under the big Talpy:** one line with the step a
  working chat does right now, taking turns between the chats at work (a
  chat that did something new goes first). Click it for that chat's tab.
- **Now in the Talpy Den repository:** the extension moved to
  [github.com/wzaielamri/talpy-den](https://github.com/wzaielamri/talpy-den)
  (`vscode/`), next to the widget, and its releases come from there, with the
  widget's: download the `.vsix` from the
  [latest release](https://github.com/wzaielamri/talpy-den/releases/latest).
  The backend is the widget's own at each build, no longer a copy that
  could lag behind.

## 1.15.2

- **Move a chat to Claude Code:** a chat running in a terminal can go on in
  a Claude Code tab: **Move to Claude Code** in its tab, or the → button of
  its row (when Claude Code is on the chat's account). It asks first: Claude
  quits in its terminal, which stays open, and the chat reopens in a Claude
  Code tab. A chat that's working or waiting for you is stopped only once you
  say so (**Stop and Move**), and an idle one that got back to work
  meanwhile isn't touched.
- **Reopened where the switch says, from anywhere:** the **Terminal | Claude
  Code tab** switch above Recent chats said where they reopen, but **Open its
  window** in a chat's tab, its row and Find a Chat still reopened a chat
  that isn't running in a terminal. Now they all reopen it where the switch
  says.
- **The hole stays where it was:** pulling Talpa out of its burrow carried its
  hole along under it, shrinking within a third of a second, as if the hole
  were dragged by. Now the hole stays where Talpa was while you hold it, and
  fills in once Talpa has landed; it digs a new one where it lands, as before.
- **Tokens in the Recap:** a **Tokens** number beside *At API prices*, for the
  day, the 7 days or everything (**Day | Week | Overall**): all the tokens
  your chats read and wrote, against the period before, with its trend line;
  point at it for how many were new input, read from the cache, written to the
  cache and written by Claude. A row of the timeline says its tokens too when
  you point at its numbers. Vendored backend at the widget's 31760a8.
- **A bigger icon:** the extension's icon (in the Extensions list and on the
  Marketplace) is Talpa itself, as large as the widget's, without the navy
  square behind it.

## 1.15.1

- **Pictures in a reply:** Ctrl+V in a chat's tab pastes a picture (a
  screenshot, say): it's saved where the widget keeps pasted pictures, named
  in your reply with a thumbnail under the box (× takes it out). When the
  chat goes on in the background with it, it may open the picture; a chat
  that's running asks you first, as for any file outside its folder. For an
  SSH host's chat the tab asks to copy the picture there first.
- **Plan limits that line up:** in the Recap tab, each window's chart (and
  every other list's bars) got what room its row's text left, so the weekly
  one came out shorter than the 5-hour one. Now a list's bars all start and
  end at the same place.
- **Enter sends a reply:** in a chat's tab, Enter sends what you wrote and
  Shift+Enter starts a new line, as in Claude's own prompt (it took
  Ctrl+Enter). For a chat whose terminal takes no text from outside, the
  first Enter asks how to send it.
- **The big Talpa goes anywhere:** it was kept to the right half of its
  banner, clear of the headline. Now you can drag it all the way across, and
  it digs over the headline on its own too, in front of the words, as in the
  widget.
- **A chat's tab reads like Claude's terminal:** a dot before each of
  Claude's replies and tool calls (green when a call worked, red when it
  failed, blinking while it runs), what came of a call under it (*⎿ 3
  lines*, *⎿ 2 lines added, 1 removed*, the first line of what a command
  printed, or its error), your prompts set off in your accent color, and a
  gap before each of them, so a turn starts where you see it. Claude's
  replies are in larger text: headings in Claude's orange and in their size,
  lists, inline code in color, code blocks framed with their language and a
  **Copy** button, quotes and tables. While it works, the last line says so
  with Claude's spinner. **A−** / **A+** beside its name (or Ctrl+wheel) set
  the text size, kept in the new setting `claudeStatus.chatTextScale`.
- **Answer Claude's questions from the view:** when Claude asks you a
  multiple-choice question (its questions with options to pick from), the
  chat's row and its tab show each question with its options (choose one, or
  any for a question that takes several) and a field to answer in your own
  words, then **Send answers**, or **Decline…** (a note for Claude optional).
  Its notification has a button for each option when it's one question with
  one answer, then **Other…** (your own words); with more, **Answer…** goes
  through them one by one in VS Code's pickers. In the tab, what a chat asks
  takes at most half its height, so the conversation stays in sight. That
  takes **Claude Status: Answer Permission Prompts from Claude Status…**;
  Claude still asks in the chat too, and the first answer counts.

## 1.15.0

- **Chat with any chat from the view:** a click on a chat opens it in an
  editor tab: its conversation as it goes, Claude's replies rendered and each
  tool call folded into one line (*▸ Bash: pytest ✓*, click it for what it ran
  and got), with a box to reply: **Send**, or **Send when this turn ends**.
  The message goes the way the chat takes one: typed into its terminal in
  this window or its tmux pane, into its Claude Code tab's input, or the chat
  goes on with it in the background (`claude --bg --resume`, the same chat; a
  running background session stops first). A chat in a terminal outside VS
  Code takes no text from outside, so you choose there: it goes on in the
  background, or the message goes to the clipboard and its terminal comes
  up. Also for SSH hosts' chats; a notification takes a reply (**Reply…**).
  The window button beside a chat and a click on its pet still open the
  chat itself, and `claudeStatus.clickOpensPane` makes a click on its name
  do that again. A shared chat's line under another account does what a
  click on the chat's name does.
- **Answer permission prompts from the view:** a chat waiting for a
  permission shows the command, or the file and its change, with **Allow
  once**, **Always allow** and **Deny** (a note for Claude optional), in
  Claude's own order, in its row, its tab and its notification. That takes
  **Claude Status: Answer Permission Prompts from Claude Status…**, which adds
  a hook to Claude's settings (here and on the SSH hosts shown); Claude still
  asks in the chat too, and the first answer counts. Chats in tmux can be
  answered without it.
- **Review what a chat did:** the tab's **Review** lists the files a chat
  changed with their added and removed lines and diffs, against the files
  before the chat, with **Diff**, **Undo** (a file, or all), **Commit these
  files…** (only the chat's, with a message from its name and recap that you
  edit) and **Mark reviewed**. Finished chats that changed files say **to
  review** until then, with whether tests passed after their last edit.

- **A Recap tab:** the view's new **Recap** tab shows your last 7 days with
  Claude: how long you were at it and how long Claude worked (its own count
  of each turn, without the time it waited for your answers), against the
  week before; a timeline with a row per day (when you were at it, when
  Claude worked, darker where several chats worked at once, and when it
  waited for you; point at it to see what went on then); the projects and
  chats it worked on most; what the same work would cost at Claude's API
  prices, by model, with what the cache saved; and what would use less of
  your plan, with the rules of Claude Code's own `/usage` (*Start fresh when
  you switch tasks*, *Save max effort for hard tasks*, …): each tip with the
  share of the week's usage it touches and a command to copy. Step back a
  week at a time (up to four), and look at all accounts or one. SSH hosts
  shown count too. It reads the chats' transcripts, so it uses no tokens, and
  only while the tab is open; the status checks don't change.
- **Chat pets without the flicker, and smoother:** a chat's pet went a
  little darker and lighter again whenever it changed pose: while one
  picture faded into the next, both were half see-through, and the view's
  background showed through Talpa. The next pose now fades in mixed with
  the one shown, so its colors hold. Quick moves (typing, waving, bouncing,
  juggling) go round four pictures instead of two, slow ones (nodding off,
  swaying, floating) at their own pace, and the big moves are drawn as they
  happen again instead of fading: jumping out of its burrow when its chat
  is done, popping up when a chat starts, ducking down and peeking out, with
  what flies off landing first. While it types or bounces it looks straight
  at you.
- **A day, a week or everything:** the Recap tab switches between **Day**
  (one day across its 24 hours, against the day before; step back a day at
  a time), **Week** (the last 7 days, as before) and **Overall** (everything
  since your first chat, a row per 7 days), and steps back as far as your
  history goes. Claude Code deletes chats after 30 days; the Recap keeps
  their numbers past that (`claudeStatus.recapHistory`, on by default; one
  choice with the widget), and **Claude Status: Delete the Recap's Saved
  History…** starts it again from the chats Claude still has.
- **A Permissions tab:** the view's new **Permissions** tab, next to
  **Recap**, lists the permissions you gave, here and on the SSH hosts
  shown: the rules and modes in your settings, your administrator's and
  every folder's `.claude` settings (the rules Claude saved when you
  answered *don't ask again* included), approved `.mcp.json` servers, the
  settings that loosen a check, and the folders you trusted; **Revoke…**
  says what it changes in which file, then does, on the host for a host's
  (a folder's `.claude/settings.json`, shared through git, and your
  administrator's are listed, not changed). Under it, the permission prompts
  you answered in the last 7 days, with the rules that would have let the
  most of them through (another project's folder to read, edits in the
  chat's own folder, a read-only command, a site's pages): **Allow…** says
  what changes where, then writes the rule into the
  `.claude/settings.local.json` of the folder the chats started in, and
  **Undo** takes it back (`claudeStatus.recapRules` leaves the rules out, so
  there's no **Allow…** to click by mistake).
- **More in the Recap tab:** red marks on the timeline where a usage limit
  stopped a chat, and how full your plan's windows are now, with how they
  filled up. The turns that cost most, the costliest chats, and what coming
  back to chats after their cache had expired cost. A trend line of the last
  five weeks under each number. What Claude did: tool calls, commands, edits
  (files and lines), subagents, web searches, compactions. Click a day or a
  project for its chats. And `claudeStatus.recapCurrency` shows the amounts
  in euros or another currency, at the European Central Bank's rate of the
  day (downloaded at most every 6 hours, only while the tab is open).
- **The Recap tab's name** no longer breaks over two lines in a narrow view.
- **Keep going until it's done:** a chat at work on this computer can keep
  going while you're away (the ↻ button on its row): when a usage limit
  stops it, it goes on by itself in the background a minute after the limit
  resets, and again after each later limit, however many that takes, until
  a turn of it ends by itself. Its row says **↻ Keeps going**; click that to
  stop it. A chat a limit has stopped already offers both: **Go on at …**
  goes on once when the limit resets, **↻ Keep going** goes on then and after
  every later limit too (in Recent chats: **limit** and **↻** beside it). A
  queued go-on and *↻ Keeps going* show side by side, so you see what will
  happen.
- **A chat goes on in its permission mode:** a chat in auto mode (or plan
  mode, accept edits, …) that went on by itself after a limit went on in
  auto mode the first time, but in the default mode, asking before
  everything, from the second time on. It keeps its mode every time now.
  (Not bypass permissions: a chat in that mode goes on asking first.)
- **Going on is checked:** when a go-on didn't take (nothing new in the chat
  five minutes after it went on) or its turn broke off on an API error that
  isn't a limit (the connection lost, say), it goes on again after a pause,
  five times with longer and longer pauses, then says it gave up. A chat
  waiting for your answer, one whose login expired and one open in a Claude
  Code tab are left alone, and say why. (While the computer sleeps nothing
  can run: a chat goes on when it wakes up.)
- **A usage cap** (`claudeStatus.usageCap`): an account's chats at work on
  this computer are stopped once one of its plan windows reaches the
  percentage you set, once in that window. Queued tasks wait until it
  resets, and chats that keep going go on then.
- **Starred chats and plans:** the star button next to a chat (a running
  one or a recent one) or a plan stars it. Each account then lists its
  starred ones under **Recent chats → ★ Starred** and **Plans → ★ Starred**,
  newest first, however old they are; those folds stay closed until you
  open them. Click ★ to unstar. An SSH host's chats and plans can be starred
  too. The stars are kept on this computer and shared with the Plasma
  widget.
- **Model, effort and permissions for new chats:** **New Chat…** has the
  model (Opus, Sonnet, Fable, Haiku or Claude's default), the reasoning
  effort (low to max) and the permission mode (manual, accept edits, plan,
  auto, don't ask, bypass permissions or Claude's default) a chat in a
  terminal or in the background starts with, Opus, extra high and Claude's
  default mode to begin with (`claudeStatus.newChatModel`,
  `claudeStatus.newChatEffort`, `claudeStatus.newChatMode`). Also for queued
  tasks and SSH hosts; a Claude Code tab has its own settings for them.
- **When a limit resets:** hovering over *resets in 2h 5m* (a plan window's,
  or a chat's *Limit · resets in …*) shows the time it resets, with the day
  when that isn't today.
- **A chat a usage limit stops isn't "finished":** its notification said
  *… finished*, the pet cheered and the summary for when you're back listed
  it under *Finished*. Now it says *… hit the usage limit* with Claude's
  message (which limit, when it resets), and *It goes on by itself after the
  reset* for a chat that keeps going; the pet is out of steam, the sound is
  the one for a failed turn, and the summary has a line *Hit the usage
  limit: …*. A chat whose login expired says that. Claude writes a chat's
  last message a moment after its turn ends, so now and then the limit
  showed only on the next check: a second notification says so then.
- The backend is the widget's at 633e0f2.
- **A recent chat reopened in a Claude Code tab** opens in this window when
  it has the chat's project open. Where Claude had gone into a subfolder
  (`cd source`), or out of the folder the chat started in, a new VS Code
  window opened just for that folder. When another window has the project,
  that one comes up instead of a new one for the subfolder.

## 1.14.1

- **Claude Code tab** in Recent chats stayed greyed out (*The Claude Code
  extension isn't installed or enabled in this window*) for good when the
  Claude Code extension started a moment after this one, which both do as
  VS Code starts up. It's looked for again until it's there.

## 1.14.0

- **Talpa, a new pet of its own:** Clawd is gone. Talpa lives in a burrow:
  it stays half underground while it works and plays, digs over to another
  spot (towards your mouse) instead of walking, and only comes all the way
  out when you drag it out; dropped, it digs back in where it landed. A new
  chat's pet digs up out of the ground, and one whose chat leaves the list
  waves and digs away. Its lamp glows in the chat's state color, and it
  picks what to do at random from what fits the moment, so it's never the
  same twice. A chat's pet wears a calm version of the chat's color. It's
  the same creature as in the Plasma widget and the GNOME extension, drawn
  by the same code.
- **A new icon:** Talpa peeking up out of the ground, in the view's header
  (in the state color: it pops up when a chat needs you, glances around
  while Claude works, smiles when it's your turn and sleeps when nothing
  runs), in the sidebar and on the extension's page.
- **Chats in a steady order, pets too:** an account's chats that need you
  come first (the one asking longest first), the others in the order they
  started, the newest last; a row no longer jumps around while its chat
  works, idles or finishes. Its pets stand left to right in the same order,
  and when a new chat comes the others hurry over to make room. The bar in
  the pet's color next to each chat is twice as wide, so you find a pet's
  chat at a glance.
- **Lighter:** only the big Talpa is drawn all the time, and only as often
  as that shows something new. A chat's pet shows pictures, drawn when what
  it shows changes: each pose fades over to the next, quick moves go back
  and forth between two pictures, and it still blinks and looks around;
  while you hold it, it's drawn live. The stage's glow fades without
  redrawing the stage.
- Usage at the limit, failed chats and errors are in a proper red (the
  theme's chart red, not its paler error text color).

- A plan or memory in a long folder lost the end of its time ("5d 22h a")
  at the row's end, whatever the panel's width: the folder is now cut in
  the middle, as in **Recent chats**, and the time always shows.
- The chart of an account's last days drew a grey bar on days without any
  tokens, and the bars of days with no weekday under them reached down into
  the weekdays, taller than they should be: a day without tokens now has no
  bar, and all bars stand on the same line.
- Feedback on a plan was never sent: the chat didn't reopen and nothing
  was copied to paste, although your comments were cleared. It reaches the
  chat again.
- **Set Up Plan Usage Bars** replaced a `settings.json` that is a link
  (accounts sharing one settings file) with a plain file per account: it
  writes through the link now, once per file.
- **Remove from the list** is offered on every finished chat, also one whose
  process is still there, as in the Plasma widget.
- Continuing the chat that made a shared plan opened Claude Code on the
  plan's account instead of the chat's, and failed.
- A folder typed for an SSH host as `~/project` was ignored, so the chat
  started in the home folder: it's taken in the host's home folder now, and
  other relative paths are refused.
- While the view is hidden, a slow `claudeStatus.pollInterval` (over 10 s)
  is kept instead of checking every 10 s; a host listed twice in
  `claudeStatus.sshHosts` shows once.
- Where an SSH host's plan usage shows under another account
  (`claudeStatus.sshUsage`), **Continue on …** and waiting for the limit
  ignored that usage; the host's memories showed its own clock's time.
- Token counts said *1000.0k* just below a million.
- On GNOME without the widget's Claude Status GNOME Shell extension (not
  installed, turned off, or GNOME 45 to 48, which it doesn't run on),
  clicking a chat in another window, such as a VS Code window connected to
  an SSH host or a terminal app, failed with *Couldn't raise the VS Code
  window (is the Claude Status GNOME Shell extension enabled?)*. The view
  now checks that the GNOME Shell extension is running before it tries,
  and says where the chat runs when it isn't.
- Clicking a background job that a terminal outside VS Code already shows
  (such as the Konsole tab the Plasma widget opened) attached it a second
  time in VS Code's terminal: that terminal comes up now (on Plasma, and on
  GNOME with the Claude Status GNOME Shell extension; elsewhere the view
  says where it is), and one of this window's terminals that shows it is
  brought up.
- Pets: a chat's pet never heard that its usage limit had reset (it kept
  its low-battery pose); a hidden view piled up the sparks of pet
  reactions until it was shown; a pet you held could walk off or vanish
  from under the pointer; a pet still walking in went on to its old spot.
- The backend it shares with the Claude Status widget got the widget's
  fixes: tasks and plans reach Claude's tab whole (an `&` cut them), a
  one-word task no longer runs a Claude command, switching VS Code's account
  keeps the settings file as it was (a link, its line ends, commas inside
  values), **Remove** refuses to take files other accounts use to the
  Trash, and more (see the widget's changelog).

## 1.13.0

- **Wait for the usage limit:** when an account is at its usage limit,
  **New Chat… → Start with a task…** offers **After the limit resets (in
  2h 15m, at 16:10)**, in a recent folder or **Choose folder…**: the task
  is queued under the account and starts in the background a minute after
  the limit resets (as soon as VS Code or the widget runs, if neither did
  then). The account lists its queued
  tasks with when they start: start one now (▶) or cancel it (✕). One that
  can't start (e.g. its folder isn't trusted any more) stays, saying why.
  The queue is shared with the Plasma widget, and only one of them starts
  a task. Also for SSH hosts' accounts (they start from here, over ssh).
- **Queued tasks wait for the limit:** a task (or a chat going on by
  itself) whose account is at its usage limit when its time comes waits
  on, and starts a minute after that resets, instead of stopping at once;
  ▶ still starts it right away. A chat that went on by itself keeps its
  name.
- **Start a background task later:** **New Chat… → Start with a task…**
  offers **Later, at a time you pick…**: a day (today or one of the next
  six), a time, then the folder. The task waits under the account and
  starts in the background then (as soon as VS Code or the widget runs, if
  neither did then); it's listed with when it starts, to start now or
  cancel. Also for SSH hosts' accounts.
- **Chats go on by themselves after the limit:** a chat a usage limit
  stopped gets **⏱ Go on at 10:41** (next to **Continue on …**): a minute
  after the limit resets, it goes on in the background with *The usage
  limit has reset: go on where you stopped.* (`claude --bg --resume`: the
  same chat). An idle Claude that still has it open quits first (a
  background session is stopped); if the chat went on before then,
  nothing happens. It's listed with the queued tasks (click it again, or
  ✕, to cancel). In **Recent chats**, click a chat's red **limit** tag.
  Only in folders Claude trusts (as for background tasks). Also on SSH
  hosts.
- **A background session the limit stopped** said *Needs input* (Claude
  marks it as blocked, *rate limited — wait and retry*): it now says
  **Limit · resets in …** like the others, and doesn't count as needing
  you.
- **The summary counts chats at the usage limit apart:** *1 working · 2 at
  the usage limit* (red), instead of counting them as idle or done.
- **A recent chat's or a plan's tooltip** shows its whole folder (the
  line may cut it short).
- **Finding more than chats:** **Find a Chat…** also finds project folders
  (by their path: pick one for a new chat there), plans (by their title or
  text) and memories (by what they say), listed before the chats. Each
  kind folds under its heading (**Memories (9)**, **Chats (26)**: pick one
  to fold or unfold it), and so does each computer when SSH hosts are
  shown: the chats show at first, the rest too when no chat has the words.
  The button in the title bar unfolds (or folds) them all.
- **Find a Chat…** keeps its headings and lists the chats newest first
  while you type (VS Code sorted them by how well their names matched).
- **Each account's memories:** what Claude keeps about you and your
  projects (`<config>/projects/<folder>/memory`) is listed under each
  account (**Memories**, folded), after the account's own `CLAUDE.md` (your
  instructions for every chat on it), newest first, with the folder each is
  for: one opens in the Markdown preview, and the edit button opens its
  file, to change what Claude remembers.
- **Feedback on a plan, as in a review:** in a plan's file (✎), the **+**
  next to a line adds a comment for Claude; change the file itself too if
  you like. **Send Feedback to Claude** (the send button in the editor's
  title bar, **↩ send to Claude** next to the chat's plan, or the plan's
  row) sends your comments, with the lines they're on, and exactly what
  you changed (told apart from Claude's own version of the plan, rebuilt
  from the chat) to the chat that made it, which revises the plan in plan
  mode. A chat idle in one of this window's terminals, or in tmux, gets it
  typed in; one in a Claude Code tab or another terminal gets it on the
  clipboard and comes up, to paste it there; one that isn't open reopens
  in plan mode with it.
- **Plans open in the Markdown preview,** rendered, instead of as a text
  file. To change one, the **✎** next to a chat's **plan ↗** tag, or in
  the plan's row, opens its file in an editor tab (so does the preview's
  **Open Source** button): what you change is the plan.
- **Two chats changing the same files:** chats that are open and changed
  some of the same files get a red **⚠ same files** tag naming the other
  chat and the files (click it to go there), and a notification when it
  starts (with the "waiting" ones): two chats editing one file can
  overwrite each other's work. Also on SSH hosts.
- **The widget's plans and subagent runs in VS Code:** the Plasma
  widget's **Open plans and runs in: VS Code** shows them in VS Code's
  Markdown preview, through a `vscode://` link this extension handles (it
  opens only plans of a Claude config folder and the widget's runs).
- **Open the whole run** in a Remote-SSH window opens the run file of
  this computer (it looked for it on the SSH host).
- A background chat shared with another account, then kept only there
  (**Keep only on …**), came back under the account it ran on, as a
  stopped background session, for a day (Claude keeps that account's
  record of the session): it's now only on the account that kept it.

## 1.12.0

- **Chats a usage limit stopped:** a chat that hit a usage limit
  (*You've hit your session limit*) says so in red, with when that limit
  resets (from the account's plan usage, else from Claude's message), and
  its pet's battery runs low. Once the limit has reset, a notification
  per account says which chats can go on (with the "finished"
  notifications). Meanwhile **Continue on personal** under the chat moves
  it to another account with room left in that limit: shared with it,
  then reopened there in VS Code's terminal. An idle Claude that still has
  it open quits first; one in a Claude Code tab, close the tab first. A
  chat whose login expired says so too.
- **Claude's recap:** when you come back to a chat after a while, Claude
  Code writes a short recap of it (*You asked …; Next step: …*). While
  nothing was said after it, it's the line under the chat (instead of
  Claude's last words) and the first thing in its peek; recent chats show
  theirs in their tooltip.
- **Start a chat with a task, also in the background:** **New Chat…**
  offers **Start with a task…**: say what Claude should do, then pick
  where. In a terminal it's sent right away, in a Claude Code chat tab it's
  typed in for you to send, and **In the background** runs it as a
  background session (`claude --bg`): no window opens, and it's listed
  right away. The background only works in folders Claude trusts already
  (it can't ask there), so never in your home folder. Also on SSH hosts.
- **Find a Chat…** (the search button in the view's title bar): every
  chat with all the words you type in its name, its folder or one of your
  prompts, on this computer and on the SSH hosts shown, newest first. Pick
  one to go to it, or to reopen it.
- **Plans:** a chat that wrote a plan in plan mode gets a **plan ↗** tag
  that opens it in an editor tab (yours to change; an SSH host's that this
  window isn't connected to opens as a copy). Each account lists its plans
  (**Plans**, folded): open one, **carry it out** in a new chat (the plan
  is the chat's first message, with what you add, in a terminal, the
  background or a Claude Code tab), go back to the chat that made it, or
  share it with your other accounts (one file on all of them; **Keep only
  on …** undoes it). Sharing a chat shares its plan too.
- **Permission mode:** a chat in plan mode, auto mode, accept edits or
  don't ask says so next to its name; one that bypasses permissions says
  so in red.
- **SSH hosts that want a password:** such a host shows **Log in…**, which
  opens a terminal where `ssh` itself asks for the password (or
  passphrase, one-time code, new host key): the extension never sees it.
  The checks then go through the connection that login opened, until 30
  minutes after their last check, until you log out, or until you click
  the host's **Disconnect** button.
- The backend is the widget's 1.12.0: background sessions open, stop and
  start even with `CLAUDE_CODE_DISABLE_AGENT_VIEW` set for your whole
  desktop.

## 1.11.0

- **Accounts:** **Claude Status: Claude Accounts…**
  (in the view's ⋯ menu) lists this computer's Claude accounts: whom each
  is logged in as, whether plain `claude` or VS Code's Claude runs on it,
  its running chats. **Add Claude Account…** (also in the account item's
  switcher) makes `~/.claude-NAME` and opens a terminal with Claude's own
  login, optionally with your settings, `CLAUDE.md`, keybindings and own
  skills, agents and commands linked from another account, and a
  `claude-NAME` command. An account can log in or out
  (`claude auth logout`), get or lose its command, be used for VS Code's
  Claude, or be removed (logged out, its folder to the Trash). Login
  terminals are transient: VS Code doesn't keep or restore them. The
  extension never sees a login.
- **Log in…** in the view for an account that isn't logged in (a new one,
  or logged out), also on an SSH host.
- **One default account:** the default account is listed first and marked
  **default** (on each SSH host too, with two or more accounts) (as in the
  Plasma and GNOME widgets: this view listed the account `~/.claude` links
  to first, while the status bar showed VS Code's), its usage is in the
  status bar, and VS Code's Claude and plain `claude` run on it. The
  status bar's account item (**Default Claude Account…**) and **Make
  Default** in Claude Accounts point VS Code's Claude there and, where
  `~/.claude` is a link, plain `claude` too; refused while a chat works in
  VS Code's Claude or any Claude runs through the name `~/.claude`. In a
  Remote-SSH window: the host's default, its `~/.claude` included.
- **Accounts on SSH hosts:** Claude Accounts… first asks whose: this
  computer's or a host's in the view; on a host everything goes over ssh,
  with nothing installed there.
- **Switch Claude Code's account in a Remote-SSH window:** the account item in
  the status bar shows which of the host's accounts Claude Code there runs on,
  and switches it. VS Code keeps that setting per host (it's a machine
  setting, written to the host's Remote Settings from a window connected to
  it), so this computer's account stays as it is; the Claude extension
  follows the change for new chats.
- A new chat in the Claude Code chat tab on the host's other account switches
  Claude Code there to that account first (the menu says so), and it stays on
  it. Before, the chat started on the host's other account.
- **An account's plan usage shows once:** an account logged in on this
  computer and on an SSH host (or on two hosts) has one plan usage, which
  showed under each copy. It now shows where the account is listed first,
  with the newest numbers of them all (the machine they come from is named
  when it's another one). `claudeStatus.sshUsage` shows each host's own
  again (`all`) or none on hosts (`none`).
- The status bar's 5-hour usage is that of the account VS Code's Claude runs
  on (in a Remote-SSH window: the host's), when it has numbers. It was the
  account with a running chat, so a terminal chat on another account showed
  that account's.
- **Plan usage of accounts used in VS Code** (also on SSH hosts), the
  **Claude Code changed something** note, checks that cost less (`poll.py`)
  and VS Code's account listed first come with the widget's backend.
- **A chat in another window's terminal comes into view:** opening a chat
  that runs in the terminal of another VS Code window raised that window
  only; its terminal now comes up there, also with the panel closed. The
  same for a chat in the terminal of a Remote-SSH window connected to an
  SSH host, and when the Plasma and GNOME widgets open such a chat (they
  hand it over with a `vscode://wzaielamri.claude-status/terminal` link).
- **Orange like the widgets:** *needs you* and plan usage from 70% use VS
  Code's orange (`charts.orange`); they were the theme's warning color,
  which is yellow in VS Code's own themes, while the Plasma and GNOME
  widgets show orange.

## 1.10.1

- **Share chats on SSH hosts:** a host with two or more Claude accounts
  (the one this window is connected to with Remote-SSH, or any host you
  picked) gets the share button too: **Continue on …** shares the chat with
  that account there and opens it in VS Code's terminal (through ssh, or the
  window's own terminal on its Remote-SSH host), **Share with all accounts**
  and **Keep only on …** work as they do here, between the host's accounts.
  Nothing is installed on the host.

Fixes (from a review of the whole code):

- A chat whose prompt or reply mentioned the status script's answer marker
  made the whole view say "The status script's answer couldn't be read".
- The extension runs a chat's open and stop commands from its own status,
  never ones the view sends it, and checks every message from the view.
- When Python didn't work at first and the view was opened meanwhile, SSH
  hosts never showed once it did. A fractional number in a count setting
  (e.g. 2.5 recent chats) broke every check; they're whole numbers now.
- A chat's notifications follow the chat, not its row: a background session
  whose row changes as it finishes still notifies, and one listed twice no
  longer alerts every minute. A host that stopped answering no longer counts
  in the badge, status bar or "go to the chat that needs you", and a host's
  clock being off no longer skews its times.
- Plan usage bars setup: a missing or outdated wrapper script is repaired,
  it's written before the settings point at it, files are replaced in one
  step, and what changed in them while the dialog was open is kept.
  `bash $HOME/…` status lines and more ways of reading the input are found.
- Switching VS Code's Claude to a plain `~/.claude` while VS Code itself was
  started with `CLAUDE_CONFIG_DIR` says so instead of doing nothing.
  `pythonPath`, `sshHosts` and `extraConfigDirs` can't be set by a workspace;
  the Terminal | Claude Code switch writes where its value comes from.
- A second quick click on a recent chat no longer starts it twice; a check
  that's given up on ends its ssh too; a window started in the background
  no longer greets you with "While you were away".
- The view: one account that fails to draw no longer blanks the rest,
  subagents that ended on an API error show as failed, pets fetch a pose
  again after a failed load, and polls do less work.
- With the widget's backend fixes (vendored): SSH answers, shared chats,
  caches shared by several copies, and more (see the widget's changelog).

## 1.10.0

- **Open a subagent:** click a subagent in a chat's agent tree to unfold it:
  the task it was given, its tool calls and tokens so far, its last steps
  and, once it's done, its report. **Open the whole run** shows everything
  it did in VS Code's Markdown preview: the task, every step with the start
  of each result, messages the chat sent it, and its report (an SSH host's
  is fetched over ssh). Claude Code itself can't open a subagent from
  outside, so this is the way to read one.

## 1.9.0

- **Your last days:** an account's token line unfolds its last 14 days:
  tokens per day as bars (today's in the accent color; hover one for its
  chats and prompts), the totals, the busiest folders and the models used.
- **A chat's recap:** the unfolded peek ends with the chat's numbers: your
  prompts, how long Claude worked, its tool calls by tool, its tokens
  (subagents included) and, when the status line says so, its cost at API
  prices.

## 1.8.0

- **See what a chat is doing without switching to it:** a line under each
  chat says what it's on right now (*▸ Bash: npm test*), what it needs, or
  the first line of Claude's last reply. Click it for your last prompt,
  Claude's whole reply, the chat's tasks and its changed files.
- **Task progress:** a chat with a task list gets a **2/4** tag that fills up
  as tasks get done; its tooltip lists them with the one it's on now.
- **Compare what a chat changed:** the **± 3 files** tag opens VS Code's
  changes view with every file the chat changed, as it was before the chat
  and now (or only its last turn, from the unfolded peek). The Plasma and
  GNOME widgets open the same view through this extension
  (`vscode://wzaielamri.claude-status/changes`).
- **Usage forecast:** each plan bar shows where your pace leads by the reset
  (lighter) and where an even pace would be by now (a tick). When the
  5-hour limit would run out first, a line under it says when.
- **Go to the chat that needs you:** Ctrl+Alt+Shift+C (**Claude Status: Go
  to the Chat That Needs You**) opens the chat waiting longest; press it again
  for the next one, then the chats that finished while you weren't looking.
  With none, it shows the view.
- **While you were away:** back at VS Code after 5 minutes or more
  (`claudeStatus.awayMinutes`), one notification and a card in the view sum
  up what happened: chats that need you, finished or failed, limits that
  reset. Meanwhile, notifications of finished chats wait for it
  (`claudeStatus.awayDigest`). With notifications off, only the card shows.

## 1.7.0

- The same version as the widget and the GNOME extension: all three are 1.7.0.
- **Stop or interrupt any running chat:** the ■ button works on every chat
  with a process, whatever it's doing, and asks first, saying what will
  happen. In a terminal, Claude quits as when its terminal closes (the chat
  is kept and moves to Recent chats); in a Claude Code tab it's like the tab's
  own stop button (the tab says *Interrupted* and goes on with your next
  message). A working chat in one of this window's terminals, or in tmux, can
  be interrupted instead: Ctrl+C, which stops the turn and its subagents, and
  keeps the chat open. Also on SSH hosts.
- **Model and effort:** chats show their reasoning effort next to the model,
  subagents the model they run on.
- From the widget's backend 1.7.0: stopping by signal as each host expects
  (SIGINT for Claude Code tabs, SIGTERM in terminals) and ending what a
  stopped chat leaves behind; `jump.py --interrupt`; models and effort.

## 1.6.0

- The same version as the widget and the GNOME extension: all three are 1.6.0.
- **Stop idle chats:** a chat in a terminal whose turn is over gets the ■
  stop button too (it asks first). Claude quits as when its terminal closes:
  the terminal stays open, and the chat is kept and moves to Recent chats. One
  that got back to work meanwhile isn't touched. Also on SSH hosts. Not for
  chats in a Claude Code tab, where it would show as an error.
- **Recent chats in a Claude Code tab:** a **Terminal | Claude Code tab**
  switch above an account's recent chats (`claudeStatus.reopenIn`). In Claude
  Code, a chat reopens in the window that has its folder (opened if needed;
  an SSH host's through Remote-SSH).
- **Terminal or Claude Code, whichever is there:** without the `claude`
  command on a chat's machine, Terminal is greyed out and recent chats reopen
  in Claude Code; **New chat** says so and offers the chat tab. Claude Code
  tab is greyed out when the extension isn't there or runs on another
  account. The tooltips say why.
- From the widget's backend: `claude_status.py` reports whether the `claude`
  command is there; `jump.py --stop` stops idle chats, and `jump.py --resume
  … --vscode` reopens a chat in VS Code.

## 1.5.0

- From now on this extension has the same version as the Plasma widget and the GNOME
  extension: all three are 1.5.0.
- **Switch VS Code's Claude between your accounts:** the status bar shows
  which account the Claude Code panel runs on (**Claude: work**); click it,
  or run **Use Account for VS Code's Claude…**, and the window reloads on
  the one you pick. It changes only VS Code's `claudeCode.environmentVariables`:
  plain `claude` in a terminal and running chats keep their accounts.
- **Continue on …** opens the chat on the other account in VS Code's
  terminal, like every other chat, instead of always in your desktop's
  terminal (`claudeStatus.openIn` = `system` keeps that).
- From the widget's backend:
  - `claude` is found beyond PATH: in `~/.local/bin`, npm's, bun's, Volta's,
    pnpm's and nvm's folders, or on your login shell's PATH.
  - SSH hosts work with any home folder: the shared-connection sockets moved
    to `$XDG_RUNTIME_DIR` (a long home folder name made their path too long).
  - The status-line snippet is plain POSIX sh (it broke status lines run by
    `sh`); **Set Up Plan Usage Bars…** replaces an older copy.
  - Sharing checks for one filesystem first, instead of failing half-way.
  - Lighter status checks: token totals are summed per day when transcripts
    are read, not on every check.

## 0.1.3

- Sharing chats between your accounts is built in (the widget 1.4's
  backend): with two or more Claude accounts on this computer, a finished
  chat's share button offers **Continue on …**, **Share with all accounts**
  and **Keep only on …**, with any profiles and no extra tool. It used to
  appear only where the author's own sharing script was installed.
  **Continue on …** shares the chat with that account only.

## 0.1.2

- New chat asks where: in a terminal as before, or as a Claude Code chat tab
  in this window (the Claude Code extension's own chat). The tab is offered
  for accounts on the window's machine and opens in the window's folder; the
  menu says when the extension is set to another account than the one picked.

## 0.1.1

From the widget's latest fixes (backend synced to its GNOME release):

- A shared chat that moved on to a copy of itself, after that copy was shared
  too, is listed once instead of twice.
- The last minute before a plan limit resets reads "resets in <1m", not "0m".
- New status is stored before the pets and notifications react to it, so one
  reaction that fails can't stop the view from updating (the widget froze at
  every plan-limit reset that way).
- GNOME: chats running outside VS Code are brought to the front through the
  widget's GNOME Shell extension, chats open in GNOME's terminal with
  `claudeStatus.openIn` = `system`, and sounds use GNOME's sound theme.

## 0.1.0

First version: the Claude Status Plasma widget's dashboard in VS Code.

- Every Claude Code chat on this computer and on picked SSH hosts, in an
  Activity Bar view (also as an editor tab), with plan usage, tokens,
  subagents, recent chats and the animated Clawd pets.
- Runs on your side, also in Remote-SSH windows; the window's host is shown
  without setup.
- Chats open in VS Code's terminal on the machine they're on.
- Notifications and sounds from one window at a time; status bar item and
  Activity Bar badge.
- Plan usage bars setup for any status line, with undo.
- Demo mode for screenshots.
