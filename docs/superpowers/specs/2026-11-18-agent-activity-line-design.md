# Agent rows say what they do, in words (design)

Date: 2026-11-18. Size: a small change (short design).

## Why

Claude Code's own agent list reads like this:

    ○ general-purpose  Reading both CHANGELOG.md headers   17m 31s · ↓ 230.2k tokens

At a glance it says what the agent is working on and how big its context is.
Talpy Den's agent rows show the raw tool call instead
(`Bash: sed -n 1,25p CHANGELOG.md | cut -c1-400; echo ----; …`), and the
token count appears only when the agent is unfolded. That count is also a
different number: the total over every request. The owner wants:

- a readable line saying what each agent is doing right now, which changes
  as the agent moves on;
- a token count on the row, as in Claude's list;
- **when the agent is clicked**, the exact tools it is running right now,
  for example the whole command and how long it has been running, under
  the readable line;
- Talpy Den kept as fast as it is.

## Approaches

1. **Picked: use only what is already on disk.** Talpy Den already reads
   the end of each agent's transcript, and everything this needs is in
   there. No extra reads and no model calls.
2. Option 1, plus one-line summaries that Talpy Den writes itself with
   Haiku, at most once a minute per running agent and only while a view
   is open. This is closest to Claude's wording, but it uses plan usage,
   lags a few seconds and adds a worker. Not now. It could become an
   opt-in later if the lines read too mechanical.
3. Dropped: reading Claude's own summaries. Claude Code makes them by
   forking the agent's context (`[AgentSummary]`, `skipTranscript`) and
   keeps them only in the running process. They reach programs that drive
   Claude through the SDK's stream (`task_progress.summary`), which Talpy
   Den's chats don't use. Nothing is written to a file.

## What gets built

**The readable line** (the agent's `activity` while it runs) comes from
the tool call it is on, in Claude's own words for its tools:

- if the call has a `description` (Bash, Agent, Monitor), use that,
  with its first word in the -ing form when it's a plain verb
  ("Read the top of both CHANGELOG.md files" → "Reading the top of
  both CHANGELOG.md files"); otherwise use the description as written;
- otherwise: Reading `<file>`, Editing `<file>`, Writing `<file>`,
  Finding `<pattern>`, Searching for `<pattern>`, Fetching `<url>`,
  Searching the web for `<query>`, Running `<command, short>`, and for
  MCP tools `<server>: <tool>`;
- the states it has today ("thinking…", "writing…", "starting…", done =
  the first line of its report) stay as they are; "(thinking about the
  result)" stays too.

**Running now** (shown when the agent is unfolded, above its last steps):
each tool call of its newest reply that has no result yet. For each one,
the exact call as Talpy Den writes it today (`describe_tool`, allowed
longer, e.g. the whole first line of the command) and how long ago it
started ("for 2m 10s", counted from that entry's timestamp and ticking
like the row's "running · 17m"). Parallel calls each get a line. When the
agent is between tools, the section is left out.

**Tokens on the row**: the agent's context now, which is the newest
reply's usage (input + cache read + cache write + output). Claude shows
this same number: 222.7k measured from the reply 40 s before its 230.2k.
It appears after the status, e.g. `running · 17m · 223k tokens`, done
agents included. The unfolded summary keeps the all-requests total,
reworded so the two numbers aren't confused: "116 tool calls · 18.3M
tokens processed" (my call on the wording).

**The main chat** (my call): the chat row's own "what it's doing now"
line uses the same readable wording. For a background chat that is
working, the line is Claude's own one-line "what it's doing" from its
job's state.json (`detail`), which Claude updates during the turn and
Talpy Den shows today only once the chat is done. The exact calls stay
where they are: its steps and the live ticker.

**Where**: the agent tree in the Plasma widget and Talpy Chat
(`AgentTree.qml`, used by `SessionRow.qml` and `ChatPane.qml`), and in
VS Code's main view and chat tab (`AgentTree.tsx`, used by
`SessionRow.tsx` and `chat.tsx`). SSH hosts and containers get the same
lines, because their rows come from the same script. GNOME isn't changed;
the new fields are added alongside the old ones, so it keeps working.

## Constraints

- No new file reads, processes or model calls. Everything comes from the
  transcript tail that `agent_end` already reads and the job state that
  `session_row` already reads. Bump `AGENT_CACHE_VERSION` so cached
  progress is read again in the new shape.
- The exact calls in Talpy Chat's transcript view and the agents' "last
  steps" stay exact (`describe_tool`). Only the headline line changes.
- No flicker. The "for 2m 10s" ticks from the render clock the rows
  already use, not from extra checks.

## Not in this change

- Talpy-made model summaries (option 2).
- An agent's own background shells and its task list. The chat's task
  list stays where it is.
- GNOME.

## Left to the builder

- The verb table for the -ing form. Keep it small; when unsure, leave the
  description as written.
- Field names (e.g. `running: [{"line", "since"}]` and `context` on an
  agent, and where the main chat's working line goes on the row).
- Matching the parallel tool calls to their results, given that each
  block of a reply is a transcript entry of its own.
