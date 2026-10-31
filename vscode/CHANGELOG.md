# Changelog

## Unreleased

- **Colored where the color says something, as in Plasma:** an icon
  itself (never its button's or tag's box): Cancel's ×, Deny and Delete…
  red; Allow, Always allow, Reviewed and passed tests green; a warning
  orange; the star yellow; every other icon plain. *⇄*, *Plan ↗*, *✎*,
  *↩ Send to Claude*, *★*, *Tests ✓/✗* and the review's folds are icons
  now. The chat tab's *A− A+* and *Open its window* are icon buttons, its
  permission buttons have icons and none is filled blue, a plan's and a
  memory's kind icon is 16 px, the Permissions tab has an icon for each
  kind of permission, and the **⋯** menu has *Go to the Chat That Needs
  You* while one does.
- **Games with the big Talpy:** four quick clicks on him and he laughs,
  says *Let's play!*, and a game starts (*Play with Talpy* in the view's
  **⋯** menu too). Peekaboo holes: three holes open and he pops out of one
  at random; click him before he ducks; he's quicker each round, then
  dances and the holes close. 10 to 30 seconds; Esc, a click outside his
  stage or a chat that needs you ends it at once. No scores; it ticks and
  draws only while it runs.
- **Push Talpy into his burrow:** a drag that starts downward while he's in
  his burrow pushes him in: he squashes and sinks as far as your hand goes;
  let go and he stays down a moment, then peeks out (*hey!*, or a giggle).
  If a chat needs you, he pops straight back up with his sign. Up or
  sideways is the tug of before; the chats' pets too.
- **Playful Talpy (`talpyDen.playfulTalpy`, on by default):** off, Talpy only
  shows what your chats do: his moods, his lamp and quiet moves (looking
  around, typing, thinking, sleeping); no prop tricks, no joke bubbles, no
  cookie, no games. *Turn Off Playful Talpy* / *Turn On Playful Talpy* in
  the view's **⋯** menu switch it at once.
- **The Talpy Den icon has its badge from startup,** like Source
  Control's: the chats that need you, else the chats that finished since you
  last looked (as the Plasma panel counts them), its tooltip saying which
  (*2 chats need you*, *3 chats finished*). It showed only the chats that
  need you, and only once you had opened the view in that window: a tree
  view nobody sees carries it until the view is there. Dragged to another
  container, the view takes its badge along.
- **A chat's tasks in its tab:** under the header, a slim strip with a
  progress bar and *3/7 · what it's on*, folded; a click unfolds the tasks
  (✓ done, ▸ the one it's on, ○ to do) and its subagents with what each
  does now, the running ones first. Only a chat with a task list has it,
  and the list is made only when unfolded.
- **The tabs in the order you go to them: Talpy Den, Projects,
  Permissions, Recap.** A project's dots stand at the top right of its
  line, which is a little taller: **New chat here** and **Hide** show on
  hover or Tab over the end of its folder's line, instead of keeping their
  room after the dots.
- **A queued task is a line as a recent chat's:** its clock (or ⚠ when it
  didn't start), what it is, and at the line's end its folder and when it
  starts; **Start now** and **Cancel** show on hover or Tab, over that end,
  instead of all the time, and *starts in…* is no longer a line of its own.
- **One icon for one thing, the same as in Plasma and GNOME, and plain:**
  the widget's icon table (`icons.mjs`) gives each meaning its icon, and
  every button and mark asks it. **Cancel** is an × (a queued task's was a
  trash can), the **trash can** is only *Delete…* to the Trash, and
  **Hide** is a struck-out eye, beside *Show hidden*'s eye. The clock, ✓
  and ↻ written as text (*⏱ Go on at*, *✓ Goes on at*, *↻ Keep going*,
  *↻ Keeps going*, a recent chat's *⏱ 21:21* and ↻, a queued task's ⏱ and
  ⚠, *⚠ Same files*) are icons as big as the buttons' now; *Goes on at* is
  pressed, as a toggle that's on, and only a warning or an error is
  colored.
- **The view is what goes on now and your shortlists; the Projects tab has
  everything else, by project:** under each account, **Recent chats**,
  **★ Starred chats** and **★ Starred plans** are flat lists, newest first,
  a page at a time (as many as `talpyDen.recentChats`): **Show N more**
  under one shows the next page at once, its title says how many of all
  show (*Recent chats (10 of 23)*), and folded again it starts over; the
  account's `CLAUDE.md` is one line to read or edit. Its **Plans** and
  **Memories** folds are gone from there: the **Projects** tab lists each
  project folded (it stays so), newest first, with when Claude last worked
  there and a dot for each of its open chats, and opened, its open chats,
  Claude's last recap of it, and all its chats, plans and memories as the
  same lines as under an account, with their buttons (open, reopen, edit,
  star, send, carry out, continue, share, hide, delete), a page at a time,
  each with its account when the project is on several, *(not there any
  more)* for a folder that's gone, and a line's folder said only below the
  project's (*server* for *~/repos/api/server*). No time or money in the
  Projects tab any more (the Recap has them, by project), and a project in
  the Recap's *Where Claude worked* opens it there. Lists and projects open
  as quickly as before or quicker: a line's buttons are made the first time
  they're wanted, and a project's plans and memories a frame after its
  chats; the status check counts every recent chat without getting slower.
- **The Recap reads as a story:** the big picture first (the tiles in the
  order *You*, *Claude worked*, *Prompts*, *Tokens*, *At API prices*), then
  what Claude did, when (the day-by-day graph, your plan's limits over the
  same days, the day chat by chat), where (by project, the chats it worked
  on most), and the money last (API prices, and what could use less of your
  plan, which now also says what coming back to chats after their cache
  expired cost). *Turns that cost the most* and the *Costliest chats* line
  are gone: they repeated *Chats it worked on most*.
- **Delete a chat, a plan or a memory, to the Trash:** the trash button
  beside a line's × (a finished chat, a recent chat, a plan, a memory) asks
  first, saying what goes and on which accounts (*Delete “Fix the build” on
  work and personal? It goes to the Trash with its subagents and
  checkpoints; the Recap keeps its numbers.*), then says *Moved to the
  Trash*. A chat goes from every account it's shared with, with its
  subagents and checkpoints, and not while Claude has it open (*It's open on
  work. Exit it there first.*); the Recap keeps its numbers, and its star,
  Hide, Keep going and queued go-ons forget it. A plan goes from every
  account it's on; a memory goes with its own line in its folder's
  `MEMORY.md`, the rest of the file kept as it was. An account's `CLAUDE.md`
  and projects aren't deleted this way, and an SSH host's goes to that
  host's Trash.
- **Hide plans, memories and projects as you hide chats:** an × on their
  line (*Hide this plan*, *Hide this memory*, *Hide this project*; a chat's
  says *Hide this chat* instead of *Remove from the list*), and the view's
  **⋯** menu and the Command Palette show each kind again: **Show Hidden
  Chats Again**, **Show Hidden Plans Again**, **Show Hidden Memories
  Again**, **Show Hidden Projects Again**, each only while something of that
  kind is hidden; an SSH host's eye button offers its own. Plans carry a
  task icon and memories their kind's, in the Projects tab too.
- **Stop asks about Keep going:** stopping a chat that keeps going says so
  in its question (*It keeps going after usage limits.*) and offers
  **Stop**, which leaves Keep going on for the next limit, and **Stop and
  turn Keep going off**; the answer says what's left (*Stopped. It won't go
  on by itself any more*).
- **A chat goes on with its own model and effort, every time:** a chat that
  goes on after a usage limit (Keep going, **Go on at …**, a queued go-on)
  runs on the model of its last reply and the effort its tag shows, also
  after the first go-on, and the answer says which (*Went on in the
  background on work (Opus 5.5 · xhigh)*). A Claude Code panel chat goes on
  in the permission mode its first prompt named, and one you interrupted
  (Esc) is let go instead of started again.
- **Chat, never session; Talpy Den, never "the widget":** every text says
  chat (*Stop this background chat*, *Open this background chat on lab in a
  terminal*, *Only one Claude can have it open at a time*), and Talpy Den
  where it said the widget (an account Talpy Den can't tell, the settings'
  notes about Plasma and GNOME); the Failed sound's setting says it also
  plays when a usage limit or an expired login stops a chat, and the hint
  for adding SSH hosts names the SSH hosts button.
- **The Recap on a day the clocks change:** on a 23- or 25-hour day the Week
  view draws that day's times by its own clock, under the same 0, 6, 12, 18
  and 24 and quarter lines as the other days, instead of an hour off by
  evening; pointing at it reads that clock too.
- **Questions before what can't be undone:** cancelling a queued task you
  wrote, or a reply waiting for a chat's turn to end, asks first (*Cancel
  this task? It doesn't start, and what you wrote for it is gone.* **Cancel
  it** / **Keep it**), its button a trash can instead of the × that hides a
  chat; unticking `talpyDen.recapHistory` asks when the history holds chats
  Claude has deleted (*Stop keeping the history? …*), only in the window
  where you unticked it, and the setting shows the choice Talpy Den on
  Plasma or GNOME made too; Review's **Undo** says a file the chat made is
  deleted for good, with what you changed in it since.
- **A short README:** the extension's page says what Talpy Den is, what it
  does, how to install it and what it needs; the whole guide, with every
  setting and command (`talpyDen.usageCap`, `newChatModel`, `newChatEffort`,
  `newChatMode`, `diffSideBySide`, **Allow the Oldest Prompt** / **Deny the
  Oldest Prompt** on Ctrl+Alt+Shift+Y / N, Hide, Delete… and Show Hidden …
  Again), is the repository's [In VS
  Code](https://github.com/wzaielamri/talpy-den/blob/main/docs/vscode.md)
  page.
- **A cookie for Talpy, and a tug of war for its burrow:** double-click the
  big Talpy's stage a little away from it and a cookie pops up there, mostly
  chocolate chip, now and then double chocolate, sprinkles, ginger, mint,
  jam, oatmeal raisin or white chocolate. It spots it (and names it), jumps
  out of its burrow (which stays where it was) and runs to it. A cookie is
  light: it hops a little as it pops up and floats down to the floor, lands
  with a soft squash and a bounce or two, flies on the way you threw it if
  you let go on the move, and you can pick it up again whenever you like; hold it up out of reach and it begs and keeps jumping for it,
  lower it a little and it snatches it out of your hand. The cookie is
  drawn in front of it, so it steps right behind it and takes it where it
  is. Each flavour tastes its own way, and now and then it says thanks its
  way too (a bow, a fanfare on a little horn, confetti, a twirl, a blown
  kiss or a few hops), never as a prize: nothing is counted or kept. Then
  it digs a new burrow right there. Drag a Talpy out of its burrow and it
  hangs on to the rim for a second, stretching, trembling and leaning
  towards your hand, before it pops out into it; let go before that and it drops back in. Put
  down while a cookie is out, it goes straight after it. Clicking it still
  pets it, and the headline and the line under it still open your chats.
- **Manual mode has its tag, and ultracode shows beside the effort:** a
  chat in Claude's default permission mode says *Manual mode* beside its
  name, as Claude calls it, like *Plan mode*, *Auto mode* and *Accept edits*
  (it had no tag). A chat with ultracode on (Claude's `/effort` ultracode,
  or `/ultracode on`) says so after its model and effort, e.g. *Opus 5.5 ·
  xhigh · ultracode*, from the next prompt on, as Claude notes it in the
  chat.
- **A gear for the settings, and the same buttons in the same order as on
  Plasma:** the gear at the end of the view's title bar (and of the editor
  tab's header; **Talpy Den: Open Settings** in the Command Palette) opens
  VS Code's Settings editor at Talpy Den's settings. The buttons go as on
  Plasma and GNOME: Focus, Find a chat, SSH hosts, Refresh, Settings. **Add
  Claude Account…** moved to the **⋯** menu, next to **Claude Accounts…**
  and **Default Claude Account…**; the menu is in three parts now: the view,
  plan usage, accounts.
- **A new chat is a speech bubble with a plus:** the **+** beside an
  account's name read as *add an account*; a bubble with a plus starts a
  new chat now, beside an account and on a project in the Projects tab.
  The **+** at the top of the view was **Add Account…**, which is in the
  **⋯** menu now; **Talpy Den: New Chat…** stays in the Command Palette.
- **The chat tab's reply row as on Plasma:** the microphone, attaching files
  and the screenshot are icons now, a paperclip and a camera for the two
  that were the text buttons *+* and *Screenshot…*; while dictation records
  or writes it down, what it's doing shows beside the microphone.
- **Refresh fetches the plan usage too:** an account's numbers came only
  with its chats' replies (and every 5 minutes while one of its chats
  worked in the Claude Code panel), so an account with no chat at work here
  kept numbers hours old. **Refresh** (its button, its command) now has
  Claude Code fetch every account's plan usage that's over a minute old
  (`claude -p /usage`: no tokens, no chat saved; at most once a minute),
  and the line under its bars says *Fetching the plan usage…* until the
  numbers are in.
- **A background chat shown in a terminal says so:** beside its *Background*
  tag, in the list and in the chat tab: *Terminal* (its tooltip names the
  terminal), *Tmux* or *VS Code terminal*, for `claude attach` and for
  Claude Code's agent view, in every terminal: the terminal counts for the
  chat it was opened for, by its id. Where the terminal says its tab's title
  (Konsole, Yakuake, tmux) and the title names another listed chat, the
  agent view switched to that one, and the tag follows it (of several chats
  with that name, only the one it was opened for counts).
- **The chat tab's Chat tab is your messages and Claude's replies, and a
  Steps tab has the rest:** **Chat** shows only what you and Claude say (and
  what needs you: a permission, a question, a plan), with what it's doing on
  the working line; **Steps** is what the Chat tab was, every tool call too.
  The **Output** tab of a background chat is gone: **Open its window** shows
  any chat where it runs.
- **A tag says where a chat runs, in the list and in the chat tab:**
  *Terminal* (its tooltip names the terminal), *VS Code terminal*, *Tmux*,
  *Claude Code panel*, *Background* or *Not open*, as on Plasma.
- **A row's buttons are packed close:** narrow buttons side by side, and
  what's under them is cut right where they begin.
- **The same words everywhere:** a chat in the Claude Code extension is in
  its *Claude Code panel*, as on Plasma (it was *Claude Code tab* here, *VS
  Code* on its row), the switch for reopened chats too, and every tag starts
  with a capital: *Auto mode*, *To review*, *Not tested*, *Background*,
  *Default*…
- **What Claude tells you as it works shows in the chat tab:** with Claude
  Code showing thinking as updates, those words are kept as thinking in
  the transcript, and the tab left them out, in Chat and in Steps.
- **A chat that hasn't started yet says so:** its tab said *That chat's
  transcript isn't there any more*, in red; it says *This chat hasn't
  started yet, or it isn't there any more* now, as a note.
- **A chat in the Claude Code panel shows its permission mode:** its tag
  (*Auto mode*, *Plan mode*…) was missing: the panel names the mode at a
  chat's first prompt only, and the row looked for it in the chat's newest
  lines.
- **Lists line up in columns:** recent chats, plans and memories end in a
  folder column and a time column, so their tags, folders and times line up,
  as on Plasma.
- **Every account's usage bars are alike:** they start and end at the same
  place in every account, *resets in …* at the line's end in a column kept
  for it; an account with no reset time had longer bars.
- **Hiding a chat is a plain button,** as on Plasma (it was a −).
- **The chat tab shows its chat's tags:** beside where it runs, what its
  row in the list says: *⇄ Shared* or *⇄ Shared copy*, its permission mode,
  *Plan ↗* (click: the plan) and its subagents.
- **Inline code's ground ends with its last character:** in the chat tab
  it had room on each side that read as a space before a comma.
- **The ticker is in the big Talpy's box:** what the working chats do right
  now is the box's last line, under the counts, as on Plasma; it was a line
  under the box.
- **Pets wait for one that leaves:** when a chat left the list, the pets
  beside it tunnelled over to their new spots at once, onto the one still
  waving and digging away, and a chat that got a pet's place dug up where
  another stood. They wait until it's gone now, then move up and the new
  one comes.
- **Talpy thinks while a chat works:** the chat tab's working line had
  Claude's orange ✻ turning. It's Talpy now, looking up at thought dots that
  rise one after another, and the line is in the working color, as on
  Plasma.
- **The Projects tab starts folded, and a project's folder line fits:** the
  first three projects were open, and next to each project's numbers its
  folder and *last at work* line ran out of room in a narrow sidebar, cut
  right after the folder. Every project starts folded now, its folder and
  *last at work* line has the width under its name, and the arrow sits on
  the name.
- **A pet you hold swings as on Plasma:** one you held and swung kept
  swinging like a pendulum for seconds, its burrow swinging with it as it
  dug in; its springs were only roughly Plasma's. They're stepped as Qt
  steps Plasma's now (16 ms at a time, in the same order), so put down, it
  wobbles back upright as in Plasma, a little, and stands upright once its
  burrow opens: the burrow never swings.
- **Replies reach the VS Code window that runs the chat:** a reply from a
  chat's tab to a chat in a Claude Code panel (and one sent when the turn
  ends) goes to the window that runs it, raised first, not whichever window
  was used last; a plan's notification and the away summary open the chat's
  tab when clicks open it, as every other notification does.
- **Waiting replies go when they can:** a reply waiting for a chat's turn to
  end, on an account at its usage limit, waits for the reset (*It waits for
  the usage limit: it starts at 14:31*) as a queued task does, instead of
  starting only to stop at once; cancelling it, or turning Keep going off
  meanwhile, leaves the other alone and says so; Enter on an SSH host's chat
  in a plain terminal copies the message here and opens its terminal instead
  of saying the clipboard can't be used.
- **Permission prompts without the hook:** a chat that made several calls at
  once shows the request of the oldest one still open, the one Claude asks
  about first, and a tmux chat whose prompt may be about another call than
  the one shown (a subagent's, or one of several at once) gets no Allow /
  Deny keys: you answer it in the chat. With the hook's folder cleaned up by
  hand, Claude asks as it would without the hook instead of taking the
  missing file as a refusal.
- **A memory whose folder is gone still shows it:** a memory of a folder
  that was renamed, moved or deleted shows that folder (the one its chats
  ran in), marked *(not there any more)*.
- **Forked chats count once:** a forked chat, or one continued in another
  folder, counts the turns, permission prompts, large tool results and
  compactions it copied once, in the Recap, the Permissions tab and the
  Projects tab; a suggested rule shows *Allowed now* only when the folder's
  settings or those of the accounts whose chats asked have it.
- **The Monday recap counts what the Recap counts:** the SSH hosts whose
  last check answered too, and it says its times as the Recap does (*Claude
  worked 20m over 1 chat; you, 5m and 3 prompts.*) instead of *0 h over 1
  chats*.
- **Review keeps links and ignored files right:** **Undo** puts back the
  file a link points to and leaves the link alone, **Commit** leaves out
  files git ignores and says how many, *Reviewed ✓* goes by your mark, also
  while the chat works, and the **Undo all** question and the commit box
  open right above the buttons that open them.
- **Small things that were off:** a plan's step with its commands in a
  fenced code block shows them as a code block; a chat with ultracode on
  keeps its *· ultracode* tag after a turn with big tool results; a chat
  that went on after a turn broke off keeps its own name; a starred chat or
  plan of an SSH host opens in a terminal like a recent one; an SSH host's
  accounts tag *VS Code's Claude* only where VS Code ever connected to that
  host; **Keep only on …** says the chat leaves the other accounts' lists
  while the conversation stays, with **Keep Only on work** as its button; a
  heading ending in `#` (*Notes on C#*) keeps it and a bare address with
  parentheses links to the whole page; Chat ↔ Steps stays on the message you
  were reading; a running background chat's reply hint says *Its background
  chat stops, then goes on with your message*.
- **The pets, steadier:** hiding the view while Talpy goes after a cookie no
  longer hangs it; one grabbed again while it gets its bearings after a drop
  stays in your hand; one interrupted while tunnelling pops up where it is;
  petting the big Talpy while subagents work says how many (*Juggling 3
  agents!*); the pets are painted again after the graphics lose their
  pictures (a GPU reset, as after a suspend) or a zoom change; and the
  little working Talpy in a chat's tab holds still while the tab is in the
  background.
- **Find a Chat, New Chat… and the rest:** **Find a Chat** searches the SSH
  hosts whose last check answered, so one out of reach no longer leaves the
  list empty for seconds at each word; **New Chat…** keeps the model, effort
  and mode you pick where they count, and its task box stays open when you
  click elsewhere and offers what you typed again after a later question was
  cancelled; after Stop, Hide, Show again, Share and the like the list
  checks again once a running check is done; the **+** (Attach) of an SSH
  host's chat opens on this computer's files; Send Feedback to Claude shows
  only on a plan's file on this computer; the microphone works in a Remote
  window too; *Dictation is set up* no longer shows as an error; and in demo
  mode a click on a made-up chat, its Allow / Deny or a queued task's Start
  it now says the chats are made up.
- **Plan usage keeps up with chats in Claude's VS Code panel:** the panel
  runs no status line, and Claude Code updates its own copy of the usage
  only when `/usage` runs, so an account used only there showed the same
  numbers for a day or more. Now, while one of its chats works (or has just
  ended a turn) and its numbers are more than 5 minutes old, Talpy Den has
  Claude Code fetch them, at most every 5 minutes per account and on SSH
  hosts too: `claude -p /usage`, which uses no tokens, runs no hooks and
  saves no chat, so it never shows as a chat. `talpyDen.usageRefreshMinutes`
  sets the minutes (`0`: never). With a terminal chat's status line keeping
  them fresh, nothing changes.
- **Chats stopped at the 5-hour limit with Claude Code 2.1.312:** Claude
  now calls it the *5-hour limit* (before, the *session limit*), and such
  a stop wasn't tied to the account's 5-hour window: its bar didn't show
  it full, and *Go on at …* and **Keep going** guessed the reset from the
  message. Both names work now, and the reset Claude notes with the stop
  comes first, so a shared chat that another account's limit stopped no
  longer fills this account's bar and goes on when that account's limit
  resets.
- **Keep going waits when nobody knows when the limit resets:** out of
  usage credits, or a limit Claude dates more than a day out (*resets Oct
  30, 7pm*), a chat that keeps going went on again every few seconds, each
  time adding a go-on and a limit error to the chat, and a notification.
  Dates in Claude's message are read now; with no reset to go by, it tries
  again after 2, 5, 15, 30 and 60 minutes, then gives up and says so.
- **The Permissions tab no longer suggests rules that let more through
  than they say:** *Allow “rg”*, *“tree”*, *“git branch”*, *“git diff”*,
  *“git log”* and *“git show”* let a chat run those with any options, and
  some options run another program (`rg --pre`), write any file (`git diff
  --output=…`, `tree -o`) or delete a branch (`git branch -D`), all
  without asking. They aren't offered any more; rules you added with them
  stay until you revoke them.
- **Allow and Deny answer what the chat asks now:** after you answered a
  permission prompt in the chat and it asked again right away, the chat's
  row, its tab, the notification and *Allow the oldest prompt* could still
  offer the first prompt, and Allow or Deny there went nowhere, though it
  said *Allowed* or *Denied*. They show the newest prompt now, and an
  answer to one the chat asked again after isn't taken: you're told it
  asks something else now.
- **The next permission prompt is told at once:** when a chat asked again
  within a minute of its last prompt (you allowed a command, and it asked
  for the next), its notification came a check later and without a sound,
  and the same prompt asked again could be told twice. A new prompt is
  told right away now, and only the same one asked again is held back.
- **Your replies arrive whole:** a message from the chat tab (or one
  queued for after the turn) to a chat in VS Code's Claude was cut off at
  an `&`, and a `+` in it became a space. A message of more than about
  43,000 characters in Japanese or Chinese (65,000 with accents or
  Cyrillic), or a few thousand to an SSH host's chat, passed the tab's
  length check and then failed with only *spawn E2BIG*. A reply reaches
  the chat as you wrote it now; a long one goes over in a file private to
  you, removed once read, and over 100,000 characters still says *That
  message is too long*.
- **A reply queued for after an SSH host's turn waits for it:** one check
  of the host that failed (a VPN or Wi-Fi blip, the laptop waking up) made
  its chat look gone, so the reply was sent while the chat was still
  working, or failed and stayed in the queue with an error. It waits until
  the host answers and lists the chat as done; a task due on a host at its
  usage limit waits for the reset there too.
- **Two replies typed into tmux chats at once go each to its own chat:**
  both went through one shared paste buffer, so one chat could get (and
  run) the other's message while the other got *no buffer*.
- **Disconnect leaves your terminals open:** disconnecting from an SSH
  host also ended the chats you had open in terminals over that
  connection. Now nothing new uses the connection, and it closes once the
  last of those terminals does.
- **SSH hosts whose login shell is fish or tcsh:** what the extension runs
  there (in a host's terminal too) went through that shell's own quoting
  first, so a prompt, a folder or a picture with a backslash, a newline or
  a `!` (and with tcsh every pasted picture) failed or arrived changed.
  Commands now reach `sh` there in a form every shell passes on as it is.
- **Make default keeps every account listed:** when `~/.claude` linked to
  an account's folder with another name (say `~/accounts/work`), making
  another account the default dropped that one from every list, with no
  word. It now says so instead, until that folder is in
  `talpyDen.extraConfigDirs`.
- **An account reads as on Plasma:** its token line gives today's and the
  week's totals with their output (*Tokens today 378.3k (12.0k out) · 7 days
  502.9k (15.0k out)*); the week's two biggest models, cut off mid-name in a
  narrow sidebar, are in its tooltip. How old the plan usage is shows in a
  dim line under the bars (*Plan usage as of 5m ago*, *…, on lab*), not as
  *usage updated …* at the right of the heading. A chat's state words are
  colored only when it needs you or a usage limit holds it (*Working* blue
  and *Done* green drowned out *Needs input*); the dot carries every state's
  color. Removing a finished chat from the list is a − (it was the × that
  also cancels a queued task and hides a host). An account with nothing
  running reads *No chats running* in the hero, and the files-changed tag
  reads *±3*, with *3 files changed* over its list.
- **The focus view's Finished lines are the chats you haven't looked at
  yet:** they listed every chat whose turn ended in the last 15 minutes,
  also ones you had opened and short turns, and left out failed ones. As on
  Plasma, they now list each chat whose turn (as long as the finished
  notification asks) ended while its tab wasn't showing it, failed ones too
  (*Failed: look at what happened*), until you open that chat.
- **The sidebar at its narrowest:** below about 330 px the Focus button
  was pushed off the right edge with no way to reach it, and around 220 px
  the Projects tab too. There the tabs you aren't on are icons now (named
  in their tooltips), so every tab and the Focus button stay in sight down
  to 200 px.
- **High Contrast themes:** a chat that needs you and one at work had the
  same color (two oranges in High Contrast Dark, two blues in High
  Contrast Light), on rows, dots, counts and usage bars. Needs you is
  orange and working blue in both now. In High Contrast Light the chat
  tab's inline code, code blocks and syntax colors were pale on white (the
  dark theme's); they're the light theme's now.
- **The chat tab stays quick in a long chat:** each key typed in the reply
  drew the whole conversation again, some 200 ms a key after a few *Show
  earlier*; typing, a dictation's running seconds and the chat's checks
  leave it be now. A tab opened on its Review compared the chat's files
  three times at once (over ssh for an SSH host's chat), once now. The
  Review's commit message box was unframed, read as plain text and had no
  focus ring; it's an input in the editor's font now. A JSON or YAML key,
  and an HTML tag, in a diff is green as on Plasma, not grey like a comment.
- **A chat's tab shows the newest reply as soon as you switch back:**
  nothing reads a hidden tab's conversation, and on showing it again the
  first read came only after up to 5 seconds (and moving focus between
  editors put it off again), so Claude's last reply was missing while the
  header already said the turn was done.
- **Claude's replies show as Claude wrote them:** globs and arguments such
  as `*.py and *.js`, `*args` or `**kwargs` lost their asterisks and turned
  part of the reply italic or bold; a `\|` in a table split its cell in two
  with the backslash showing; a code block under a numbered step was shown
  and copied with the step's indentation on every line; a numbered list with
  bullets under a step numbered the bullets too, and the next step got a
  later number (*1. Step one, 2. detail, 3. detail, 4. Step two*); and a
  link to a page with parentheses in its address (Wikipedia's
  *C_(programming_language)*) opened a cut-off address and left a stray `)`
  after its text. They show and copy as written now (the bullets a list of
  their own under their step, as in Plasma's chat pane, the whole address
  the link), and a bare `https://` address is a link.
- **Back from Review or Output:** a chat tab showed the chat's beginning
  and stopped following new steps. It's at its end and follows it again if
  it was when you left, else where you were. *Show earlier* past the
  2000th step stayed and did nothing; a note says only the last 2000 steps
  are shown there now.
- **Permission prompts:** a Deny note begun for one prompt stayed open,
  with its text, when the chat went on to ask the next, and Enter then
  denied that one with your note; and the Enter that picks a word in an
  input method (Chinese, Japanese, Korean…) sent the Deny with a
  half-written note. A new prompt starts afresh now, and Enter waits for
  the word.
- **Undo and Commit in the review:** Undo brought a file the chat deleted
  (and its folder) back private to you, so a script came back not
  executable; it comes back as git has it, with your usual permissions.
  *Commit* also committed your own changes to files that a chat's file
  name matched as a pattern (`app/[id]/page.tsx`, `a[1].txt`); names are
  taken as they are now.
- **Compare in VS Code shows what the review shows:** a file Claude keeps
  no copy of (one outside the chat's folder, say) has its earlier version
  in what the chat's first edit of it gave back; the review used that, but
  *Compare in VS Code* asked git only, so it left such a file out or said
  it had *no earlier version to compare with*.
- **The chat tab counts an edit's lines right:** a changed line starting
  with `--` or `++` (a Markdown rule `---`, YAML front matter, `++i`)
  wasn't counted, so an edit could say *1 line removed* for one line added
  and two removed.
- **Always allow for an edit in a tmux chat:** Claude's dialog for an edit
  offers *Yes, allow all edits during this session* rather than *Yes, and
  don't ask again*, so *Always allow* said *That answer isn't one of the
  choices it shows*. It picks that option now.
- **Notifications about several chats offer only Open:** *Two chats change
  the same files* showed the first chat's Allow once and Deny (or its plan,
  or its question's options) when that chat was asking something, so Allow
  approved a command the notification never named; and *the usage limit
  reset* had a *Reply…* that went to the first chat it named only. Both have
  just *Open* now, as on Plasma. A chat open on two accounts made two *same
  files* notifications; it makes one.
- **A reply from a notification that isn't sent says so:** when the
  message typed into a notification's *Reply…* couldn't be sent, only the
  Talpy Den view said why, which usually isn't on screen then, and the
  text was gone. A notification says so now, and its *Open* shows the
  chat's tab with your message ready to send again.
- **Live mode keeps every step of a chat that runs for days:** a new chat
  elsewhere removed the lock of a chat older than three days, so two of its
  events could arrive at once and one was lost (a finished turn could show
  as working). The hook you have updates itself at the next check.
- **Dictation leaves nothing behind:** a recording that the chat tab
  cancelled while it was still starting is stopped as soon as it starts,
  and recordings left behind are removed after an hour.
- **What you opened on a chat stays open when its Claude ends:** when a
  background chat finished, its row folded the details or the subagents you
  had open, and faded in as if it were a new chat. They're kept by the chat
  now.
- **Go on at … says the day:** a weekly limit that resets on another day
  read *Go on at 09:01*, as if it were today. The button, its tooltips, a
  recent chat's ⏱ tag and a queued chat's line say *tomorrow 09:01* or
  *Fri 30 Oct 09:01* now.
- **A usage bar's forecast in Plasma's words:** the red line under a bar
  said when the window resets (*full in 1h 20m (resets in 2h 5m)*); it says
  how long before the reset it runs out now (*full in 1h 20m, 45m before it
  resets*), and its tooltip gives your pace with one decimal, the time it
  runs out, and no *about N% when it resets* for a full window.
- **Remote-SSH windows:** plans, memories and subagent runs opened through
  an address the window doesn't serve, so *Couldn't open the plan* (or the
  memory, or the subagent's run) came instead, a plan of this computer
  took no comments there, and the window host's own plans and memories
  opened this computer's file of the same path; each opens from where it
  is now. A window connected to `user@host:2222` had its host checked on
  ssh's own port (22 unless `~/.ssh/config` says otherwise), so the host
  showed *no answer*, or another machine's chats; such a host isn't added
  by itself any more, and you're told once that a `Host` entry with that
  `Port` lets it.
- **New chats on an SSH host follow `talpyDen.openIn`:** set to your
  desktop's terminal, a new chat on a host (with a task or without) still
  opened in a VS Code terminal; it opens in your desktop's terminal now,
  as the host's other chats do.
- **Find a Chat shows an SSH host's chats with the right ages:** the
  chats, folders and plans found on a host whose clock is off said how
  long ago by the host's clock. They go by this computer's clock now, as
  the host's own rows do.
- **Send Feedback for plans in your other Claude folders:** a plan in a
  folder of `talpyDen.extraConfigDirs` (or `$CLAUDE_CONFIG_DIR`) took
  comments, but the editor showed no button to send them.
- **An SSH host's chats in the Recap of an earlier day or week:** with a
  host whose clock is set to a time zone west of yours (a UTC server seen
  from Singapore, a New York one from Berlin), the Recap of yesterday or
  last week left out the last 16 to 19 hours of the host's chats: the host
  counted the days by its own calendar. It now sends the chats of the days
  you see.
- **The Recap's plan limits after a reset:** *Your plan's limits now*
  showed a window that had reset since the last reply (the usual case
  after a limit stopped your chats) at its old percentage, in red, with a
  reset time already past (*97% · resets 14:00*) and the old window's
  fill. It shows *0% · reset* now, as the usage bars do.
- **The Recap's share card and dates:** the Overall share card's bars ran
  from the newest week to the oldest, backwards against the Week card's, and
  with more than about 30 weeks of history they ran off the card's right
  edge; they show the last 20 weeks now, oldest first. *Everything since …*,
  the price list's date and the exchange rate's read *24 Oct 2026*, not *24
  October 2026*, as on Plasma. *Open the Recap* from the Monday notification
  no longer makes the next Talpy Den page that loads (*Open in Editor* hours
  later, say) start on the Recap too.
- **The Recap, Permissions and Projects tabs:** a day's chats and a
  folder's chats open from the keyboard too (Tab to it, then Enter or
  Space). In *Chats it worked on most* the folder gives way before the
  chat's name in a narrow sidebar (names read *Nigh…* before). One Revoke
  or Allow reads your permissions again once, not once per section (with
  SSH hosts several reads of everything at once), and showing the tab
  again doesn't read them once more per section. The Projects tab's
  running chats say how they stand (*Needs input · permission*, *Done · 3h
  0m*) beside a dot in that state's color, not a blue dot for all and the
  word *done*; and the tab no longer reads every chat every 10 minutes
  while the view is hidden.
- **Pets:** when an account's last chat left, its stage folded away at once
  with the pet frozen, and the pet waved and dug away later, beside the next
  chat's pet; the stage stays open until the pet is gone now, as on Plasma.
  A chat that finished (or failed, or hit a limit) while the view was hidden
  was acted out with its words when you next looked, however long ago that
  was; now a pet acts out only what happened in the last minute, and leaves
  older news be. After switching to another dark theme (or another light
  one), the pets' words, z's and sparks kept the old theme's color until the
  view reloaded; they follow it now.
- **A check that ended isn't waited for:** when a helper had answered but
  something it started still held its output, the view waited until that
  ended, then said the check took too long (and no other check of this
  computer started meanwhile).
- **VS Code and Talpy Den on Plasma don't slow each other down:** each made
  the other read its chats' transcripts again from the start, on every
  check, when they list different chats.

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
