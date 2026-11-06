// The chat tab (src/chatPane.ts, webview/chat.tsx): one chat's conversation
// as the widget's pane.py reads it, a box to reply, what it asks while it
// waits for a permission, and its review (what it changed, Undo, Commit,
// Mark reviewed). Shared by the extension and the tab's page.

import { clockText, formatTokens, hostLabel } from "./model";
import type { Answers, AskShown, Decision, PermissionAsk, Question, QueuedTask, RecentChat, Review, Session, SessionState, Status } from "./types";

// What came of a message (or a new chat's start) sent from Talpy Chat: went, to the chat itself;
// ask: its terminal takes no text, you choose; warn: it went, but message says what's wrong
export interface SendResult {
  ok: boolean;
  message: string;
  ask?: boolean;
  went?: boolean;
  warn?: boolean;
}

// A chat started or woken in the background without Talpy Den's permission hook (pane.py's
// "hooked": false, "hookWhy"): what it asks waits in its own prompt (Plasma's words too)
export function unhookedText(why: unknown): string {
  return `It went, but Talpy Chat can't answer what it asks (${typeof why === "string" && why ? why : "no permission hook"}): answer its prompts in a terminal.`;
}

// One item of a chat's conversation (pane.py: conversation_items)
export interface PaneItem {
  kind: "you" | "claude" | "tool" | "note" | "made";
  key: string; // the same in the next answer, while it's listed
  text?: string; // you, claude (markdown), note
  thinking?: boolean; // claude: a line Claude Code wrote while Claude thought, summing it up (thinking shown as updates), not its reply: dimmed, in italics, after ∴ (key "<its reply's>/thinking")
  name?: string; // tool: its name, e.g. "Bash"
  line?: string; // tool: one line, e.g. "Bash: npm test"
  status?: "ok" | "error" | "open"; // tool: how it went ("open": no result yet)
  input?: string; // tool: what it ran or changed
  output?: string; // tool: what came back
  summary?: string; // tool: what came of it, in a line ("3 lines", "1 failed", …)
  diff?: string[]; // tool: an edit's change (unified lines, @@ at the file's line numbers when known)
  error?: boolean; // note: an API error (a usage limit…)
  at: number | null;
  sending?: boolean; // you: the tab's own, your message on its way (PendingSent)
  until?: number; // you: the tab's own, held till then (ms): sent while Claude works, Edit / ✕ / Send now meanwhile
  queued?: boolean; // you: waiting in Claude's queue, till it takes it in at its next step (pane.py)
  pictures?: string[]; // you: the pictures in it, their files (pane.py prompt_pictures)
  thumbs?: { path: string; src: string }[]; // you: those the tab can show, with their address in it (the extension's)
  asked?: Asked; // tool: a question or a plan Claude asked; {state: "denied"}: a call you denied with a note
  answered?: "question" | "plan" | "permission"; // you: your answer to the call before it (key "<tool id>/answer")
  answers?: { header: string; question: string; answer: string; notes: string }[]; // you: a question's, each answered
  command?: { shell?: boolean; output?: string; error?: boolean }; // you: a command you ran (/compact, !ls: pane.py commands.py), what it printed (ANSI colours kept: ansi.mjs)
  of?: string; // made: the key of the step or the reply it's under
  made?: Made; // made: what it is (pane.py made.py); its text is its name, or "Plan: " and its title
}

// What Claude made, under the step that made it or the reply that names it (pane.py made.py): a
// picture, a plan (Markdown in a plans folder), a page (HTML) or another file (a PDF it read).
// Folded, only its name and size; unfolded, the file as it is now (a picture Claude read: what
// it saw, from the transcript, "step"), asked for then (madeAsk)
export interface Made {
  path: string; // where it is (on its SSH host, for a host's chat)
  type: "picture" | "plan" | "page" | "file";
  name: string;
  size: number | null; // bytes, when known
  gone?: boolean; // made by a step, not there now
  step?: string; // a Read's tool call: what Claude saw is in the transcript (pane.py --made --step)
}

// "2 KB", as a made file's folded line says it (Plasma's MadeLine.qml: the same rule)
export function madeSize(bytes: number | null | undefined): string {
  if (bytes == null || bytes < 0) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

// The folded line: "icon.svg · 2 KB", "Plan: Ship it · 3 KB", "shot.png · not there any more"
export function madeLine(it: Pick<PaneItem, "text" | "made">): string {
  const m = it.made;
  const size = madeSize(m?.size);
  return [it.text ?? m?.name ?? "", m?.gone ? "not there any more" : size].filter(Boolean).join(" · ");
}

// What unfolding it asks the extension for (null: nothing to read: another file, or one gone)
export function madeAsk(m: Made): { path: string; step?: string } | null {
  if (m.step) return { path: m.path, step: m.step };
  return m.gone || m.type === "file" ? null : { path: m.path };
}

// The files and Read steps a conversation shows as made: the only ones its tab may ask for (the
// extension's check, before pane.py's own)
export function madeOf(items: readonly PaneItem[] | undefined): { paths: Set<string>; steps: Set<string> } {
  const out = { paths: new Set<string>(), steps: new Set<string>() };
  for (const it of items ?? []) {
    if (it.kind !== "made" || !it.made || typeof it.made.path !== "string") continue;
    out.paths.add(it.made.path);
    if (it.made.step) out.steps.add(it.made.step);
  }
  return out;
}

// What Claude asked (pane.py asked_of): its questions, each with the options
// you picked, or its plan; and how you answered ("open": not yet; "failed":
// the call failed, nothing was asked)
export interface Asked {
  state: "open" | "answered" | "declined" | "chat" | "approved" | "keep" | "denied" | "failed";
  questions?: (Question & { picked: string[] })[];
  plan?: string; // Markdown
  title?: string;
}

// Is it a question or a plan to show as Claude's, in Chat and Steps: once
// you answered it (or as your answer to it goes: answering)
export function askedShows(it: PaneItem, answering = false): boolean {
  const a = it.asked;
  if (!a || (!a.questions && a.plan === undefined)) return false;
  return a.state === "open" ? answering : a.state !== "failed" && a.state !== "denied";
}

export interface Conversation {
  ok: boolean;
  message?: string;
  unchanged?: boolean; // as in the last answer (--if-changed)
  missing?: boolean; // no transcript: the chat hasn't started yet, or it's gone
  chatId?: string;
  profileDir?: string;
  name?: string;
  cwd?: string;
  items?: PaneItem[];
  more?: boolean; // there are older items
  capped?: boolean; // there are, but the tab shows no more (LIMIT_MAX)
  stamp?: string;
  mode?: string | null;
  // (talpyDen.suggestReplies: pane.py --suggest) how its last turn ended (null: mid-turn, or a
  // message waiting in Claude's queue), whether the transcript says it's over, and its question as chips
  ended?: TurnEnded | null;
  over?: boolean;
  asks?: Asks | null;
  predicted?: string | null; // Claude's own guess at your reply to its question (a background chat's: its first chip)
  context?: ContextLeft | null; // how full its context is (null: not known)
  turn?: TurnSoFar | null; // Claude's turn so far, while it's going on
  options?: ChatOptions; // the model and effort it uses now (/model and /effort's lists mark them)
}

// One file a chat changed (pane.py: chat_review)
export interface ReviewFile {
  label: string;
  path: string;
  added: number | null;
  removed: number | null;
  diff: string[];
  created: boolean;
  deleted: boolean;
  binary: boolean;
  unknown: boolean; // no earlier version is kept: it can't be undone
  now?: string[]; // unknown: its first lines as they are now
}

export interface ReviewAnswer {
  ok: boolean;
  message: string; // the commit message it suggests (or why it failed)
  files: ReviewFile[];
  tests: Review["tests"];
  editedAt: number | null;
  repos: string[];
  reviewedAt?: number | null;
}

// The chat as the tab shows it: its row now (or what the tab was opened with)
export interface PaneChat {
  host: string;
  chatId: string;
  sessionId: string;
  profileDir: string;
  name: string;
  cwd: string;
  state: SessionState;
  stateText: string;
  stateShort?: string; // the same without how long ("Working"): the header's while the working line says the turn's own time
  route: Session["reply"] | "vscodeTerminal"; // vscodeTerminal: one of this window's terminals (it types it in)
  busy: boolean; // working or waiting
  atWork: boolean; // working, its turn not over (only a background command after it isn't): a message waits a moment
  bgStop: boolean; // a background chat Stop can interrupt (its row's: the Claude Code versions that was checked on)
  activity: string; // what it does now
  permission: PermissionAsk | null;
  changes: number; // files it changed
  reviewPending: boolean;
  reviewed: boolean; // its changes since its last edit marked reviewed, whether it works now or not (the Reviewed ✓ button)
  review: Review | null;
  queued: { id: string; prompt: string; error: string } | null; // a reply waiting for its turn to end
  canMove: boolean; // runs in a terminal, on the account Claude Code is on: it can move to a Claude Code panel
  where: ChatWhere;
  terminalApp: string; // the terminal it runs in, by name (Konsole, kitty…), or ""
  attached: Session["attached"]; // a background session shown in a terminal too
  // what its row in the list says of it too: shared, its permission mode, its plan, its subagents
  profile: string;
  shared: Session["shared"];
  mode: string;
  plan: { title: string } | null;
  agents: Session["agents"];
  tasks: Session["tasks"]; // its task list (the strip under the header), or null
  // A new chat (New Chat… in a Talpy Chat tab), till your first message starts it in the background:
  // its account, folder, the plan it carries out, and the model, effort and mode it starts with (its ⚙ line)
  fresh?: NewChat | null;
  starting?: boolean; // your first message started it, and it isn't listed yet: "Starting…"
}

export interface NewChat {
  account: string;
  folder: string; // as shown (~/repos/x)
  plan: string; // the title of the plan it carries out, or ""
  model: string;
  effort: string;
  mode: string;
}

// A new chat's ⚙ line: the model, effort and permission mode it starts with (the same words as
// Plasma's; "": Claude's own default)
export const CHAT_MODELS: [string, string][] = [["opus", "Opus"], ["sonnet", "Sonnet"], ["fable", "Fable"], ["haiku", "Haiku"], ["", "Claude's default model"]];
export const CHAT_EFFORTS: [string, string][] = [["low", "Low"], ["medium", "Medium"], ["high", "High"], ["xhigh", "Extra high"], ["max", "Max"], ["", "Claude's default effort"]];
export const CHAT_MODES: [string, string][] = [["default", "Manual (asks first)"], ["acceptEdits", "Accept edits"], ["plan", "Plan"], ["auto", "Auto"],
  ["dontAsk", "Don't ask"], ["bypassPermissions", "Bypass permissions"], ["", "Claude's default mode"]];

// Where a chat runs (the tag under its name, the same words as the rows'):
// a background session, closed (no process: a reply goes on in the
// background), a Claude Code panel, tmux, a terminal of VS Code (this
// window's or another's) or another terminal
export type ChatWhere = "new" | "background" | "closed" | "claude" | "tmux" | "vscode" | "terminal";

export function chatWhere(s: Pick<Session, "pid" | "kind" | "entrypoint" | "tmux" | "vscodeTerminal" | "terminalApp"> | undefined, terminalHere: boolean): ChatWhere {
  if (!s || !s.pid) return "closed";
  if (s.kind === "bg") return "background";
  if (s.entrypoint === "claude-vscode") return "claude";
  if (s.tmux) return "tmux";
  return terminalHere || s.vscodeTerminal || s.terminalApp === "VS Code" ? "vscode" : "terminal";
}

// A background session shown in a terminal too (claude attach): its second tag
export function attachedTag(attached: Session["attached"]): { tag: string; title: string } | null {
  if (!attached) return null;
  const tag = attached.in === "tmux" ? "Tmux" : attached.in === "vscode" ? "VS Code terminal" : "Terminal";
  return { tag, title: attached.app ? `Shown in a terminal too (${attached.app}): claude attach.` : "Shown in a terminal too: claude attach." };
}

// Its tag, and what the tag says on hover (terminalApp: the terminal's name; account: a new chat's)
export function whereTag(where: ChatWhere, terminalApp = "", account = ""): { tag: string; title: string } {
  switch (where) {
    case "new":
      return { tag: "New", title: `Not started yet: your first message starts it in the background, on ${account}.` };
    case "background":
      return { tag: "Background", title: "A background chat: Claude's background service runs it, with no terminal of its own. Open in a terminal shows it in one too (claude attach)." };
    case "closed":
      return { tag: "Not open", title: "No terminal or panel has it open: a reply goes on with it in the background." };
    case "claude":
      return { tag: "Claude Code panel", title: "It runs in a Claude Code panel in VS Code (the Claude Code extension)." };
    case "tmux":
      return { tag: "Tmux", title: "It runs in a tmux pane." };
    case "vscode":
      return { tag: "VS Code terminal", title: "It runs in a terminal of VS Code." };
    default:
      return { tag: "Terminal", title: terminalApp ? `It runs in a terminal (${terminalApp}).` : "It runs in a terminal." };
  }
}

// extension -> tab
export type PaneHostMessage =
  | { type: "chat"; chat: PaneChat }
  | { type: "conversation"; answer: Conversation }
  | { type: "review"; answer: ReviewAnswer | null; error: string }
  // ask: its terminal takes no text: choose; id: the message it's for (send); went: it went into the chat
  // itself (typed in, or on in the background: not VS Code's input or the clipboard)
  | { type: "result"; kind: string; ok: boolean; message: string; ask?: boolean; id?: number; went?: boolean; how?: string; warn?: boolean } // how: an "options" result's (now, next)
  | { type: "textSize"; scale: number } // talpyDen.chatTextScale
  | { type: "font"; family: string } // talpyDen.chatFont, as a CSS font-family ("": VS Code's own)
  | { type: "diffLayout"; split: boolean } // talpyDen.diffSideBySide
  | { type: "picked"; paths: string[] } // files picked to attach (+), attached as dropped ones
  | { type: "picture"; id: string; path: string; error: string } // a pasted picture, saved (path: where the chat opens it)
  | { type: "file"; id: string; path: string } // a file dropped on the tab: named in the reply (@path)
  | { type: "offers"; offers: Offers | null } // what the reply box offers as you type (pane.py --complete; null: it couldn't be read)
  | { type: "startWith"; text: string } // a new chat's task: sent as its first message, as if you typed it
  | { type: "suggest"; on: boolean } // talpyDen.suggestReplies
  | { type: "replies"; replies: UsualReplies | null } // your usual replies (pane.py --replies)
  // dictating: "starting" (the microphone, not recording yet), "recording", "writing", "model" (downloading one), "setup" (setting it up), "" (done:
  // text written down, or why not); offerModel: whisper is there but no speech model (engine: which
  // one), offerSetup: nothing writes it down yet (setupMb: what setting up downloads); the tab asks
  // before either
  | { type: "dictation"; state: "" | "starting" | "recording" | "writing" | "model" | "setup"; text?: string; message?: string; offerModel?: boolean;
      engine?: string; offerSetup?: boolean; setupMb?: number; ok?: boolean } // ok: message says it worked (set up, downloaded)
  | { type: "visible"; visible: boolean } // the tab shown or hidden (its working Talpy moves only while shown)
  // an answer to what the chat asks (from the tab, its row or a notification): on its way (shown at once
  // as yours: PendingAnswer), then whether it went
  | { type: "answering"; id: number; ask: PermissionAsk; decision: Decision; note: string; answers?: Answers }
  | { type: "answered"; id: number; ok: boolean }
  | { type: "copied"; id: number; ok: boolean; message: string } // a copyItem on the clipboard (ok), or why not
  // a made file unfolded (madeAsk; pane.py --made): a picture as a data: URL (src), a plan's or a page's
  // first lines (text; cut: there's more), or why not (gone: not there any more; big: too big to show)
  | { type: "made"; id: number; ok: boolean; src?: string; text?: string; cut?: boolean; message?: string; gone?: boolean; big?: boolean }
  | { type: "key"; key: string }; // a key's command (talpyDen.chat.*, package.json): an id of keys.mjs's table

// tab -> extension
export type PaneMessage =
  | { type: "ready" }
  | { type: "more" } // older items too
  | { type: "send"; text: string; how: "auto" | "background" | "copy" | "enter"; afterTurn: boolean; id?: number } // id: shown at once (PendingSent)
  | { type: "hold"; id: number; text: string; how: "auto" | "background" | "copy" | "enter" } // held a moment (PendingSent "held"): goes even if the tab closes meanwhile
  | { type: "unhold"; id: number } // a held one taken back (Edit, Cancel)
  | { type: "unqueue" } // the reply waiting for the turn to end
  | { type: "answer"; decision: Decision; note: string; answers?: Answers; shown: AskShown | null } // shown: the prompt you answer
  | { type: "review" }
  | { type: "diff"; path: string } // a file's change in VS Code's diff editor
  | { type: "undo"; path: string } // "*": all of them
  | { type: "commit"; message: string }
  | { type: "reviewed"; on: boolean }
  | { type: "openWindow" }
  | { type: "stop" } // Stop on its working line: what Claude does now (stopOf)
  | { type: "chatOptions"; model: string; effort: string; mode: string } // a new chat's ⚙ line (kept for the next new chat)
  | { type: "openPlan" } // the plan it made
  | { type: "openAgentRun"; agentId: string } // a subagent's whole run, in the Markdown preview (its strip)
  | { type: "moveToClaudeCode" } // Claude quits in its terminal, the chat reopens in a Claude Code panel (asks first)
  | { type: "copy"; text: string } // a code block of a reply, to the clipboard
  | { type: "paste" } // the right-click menu's Paste in the reply box: VS Code's paste, as Ctrl+V (a picture too)
  // Copy on a message, or Ctrl+Shift+C: its text (copyText), all of it: one shown cut (copyCut) is
  // read whole from the transcript first; answered with copied once it's on the clipboard
  | { type: "copyItem"; id: number; key: string; text: string }
  | { type: "openPicture"; path: string } // a picture of yours, in VS Code's image viewer
  | { type: "made"; id: number; path: string; step?: string } // a made file unfolded (madeAsk): answered with "made"
  // a made file opened (this computer's): a picture in VS Code's image viewer, a plan in its editor, a page or
  // another file in your browser or the app for it
  | { type: "openMade"; path: string }
  | { type: "textSize"; scale: number } // A− / A+: talpyDen.chatTextScale
  | { type: "diffLayout"; split: boolean } // side by side or one after the other: talpyDen.diffSideBySide
  | { type: "pickFiles" } // + : files to attach, from VS Code's file dialog (answered with "picked")
  | { type: "picture"; id: string; mime: string; data: string } // pasted in the reply (base64): saved, an SSH host's copied there
  | { type: "attach"; id: string; path: string } // a file dropped from VS Code's Explorer: a picture saved as one, a file named
  | { type: "screenshot"; id: string } // a region of the screen you pick, as a picture
  | { type: "complete" } // what the reply box offers (answered with "offers")
  | { type: "typeIn"; text: string } // a command for Claude's own panel: in its terminal, typed in or on the clipboard (commandRun "terminal")
  | { type: "openPermissions" } // /permissions: Talpy Den's Permissions tab (commandRun "page")
  | { type: "setOptions"; model?: string; effort?: string } // /model, /effort: for this chat alone (commandRun "picker"; result "options")
  | { type: "replies" } // your usual replies (answered with "replies")
  | { type: "hideReply"; text: string } // a chip's Don't suggest this
  | { type: "dictate"; action: "toggle" | "cancel" | "getModel" | "setup" }; // the microphone (answered with "dictation")

// What the reply box offers as you type (pane.py --complete): / at the start
// Claude's commands, yours and the project's, and skills; @ the project's
// files; ↑ / ↓ your past prompts in its folder (newest first)
export interface Offers {
  commands: CommandOffer[];
  files: string[];
  history: string[];
  typed?: Record<string, { run: CommandKind; runArgs?: CommandKind; why?: string; of?: string }>; // names not listed (aliases, Claude's other panels)
}

// How Talpy Chat runs a command (pane.py commands.py, as checked live on Claude Code 2.1.318):
// "here" (sent as it is: it runs, what it prints shows under it), "page" (Talpy Den's own page for
// it: /permissions, the Permissions tab), "picker" (Talpy Chat's own list: /model and /effort for
// the chat alone, pane.py --set-options; a chat in a terminal opens Claude's own there), "terminal"
// (it needs Claude's own panel or dialog, where a background chat would sit unseen: opened in the
// chat's terminal, typed in for you there or on the clipboard, to press Enter there)
export type CommandKind = "here" | "page" | "picker" | "terminal";
export interface CommandOffer {
  name: string;
  about: string;
  kind: string; // "Claude", "yours", "project", "your skill"…
  run?: CommandKind;
  runArgs?: CommandKind; // with an argument, when other (/export FILE)
  why?: string; // why it opens in the terminal
}
export interface CommandRun {
  run: CommandKind | "off"; // off: it can't run on this chat (why)
  name: string; // "/config", or "!" for a shell command
  why: string;
  arg?: string; // the picker's: what follows the name ("" for none: the list)
}

// A command in the box (Plasma ChatPane commandRun: the same rule and words): how it runs on
// this chat, or null for a message (or one Talpy Chat doesn't know: sent as it is). A shell
// command (! in Claude's prompt) runs only where Claude's prompt takes it: not in a new chat nor
// one that isn't running (claude --resume reads it as a message), and in a terminal that takes no
// text it's pasted there. One for Claude's own panel goes into its Claude Code panel's input as
// any message (you press Enter there, in Claude's own)
export function commandRun(text: string, offers: Offers | null, chat: Pick<PaneChat, "where" | "route"> | null | undefined): CommandRun | null {
  const t = text.trim();
  const where = chat?.where, route = chat?.route;
  if (/^![^!]/.test(t)) {
    if (where === "new")
      return { run: "off", name: "!", why: "A new chat starts in the background, where Claude reads ! as a message: start it first, then run the command in its terminal." };
    if (where === "closed")
      return { run: "off", name: "!", why: "A chat that isn't running reads ! as a message, not as a shell command: open it in its terminal to run it there." };
    return { run: route === "terminal" ? "terminal" : "here", name: "!", why: "" };
  }
  const m = /^\/([^\s/]+)(?:\s+([\s\S]*))?$/.exec(t);
  if (!m) return null;
  // (the list's kinds unread, they couldn't be: these three never go as a message all the same)
  const c: { run?: CommandKind; runArgs?: CommandKind; why?: string; of?: string } | null = offers
    ? offers.commands.find((x) => x.name === "/" + m[1]) ?? offers.typed?.[m[1]] ?? null
    : ["model", "effort"].includes(m[1]) ? { run: "picker", why: `saves it as your default ${m[1]} for every new chat` }
    : m[1] === "config" ? { run: "terminal", why: "needs Claude's own screen" } : null;
  if (!c?.run) return null;
  let run: CommandKind = m[2]?.trim() && c.runArgs ? c.runArgs : c.run;
  const name = c.of || "/" + m[1];
  // Talpy Chat's own list (/model, /effort): for a background or closed chat alone (pane.py
  // --set-options); a new one has its ⚙ line; one in a terminal opens Claude's own there
  if (run === "picker") {
    if (where === "new")
      return { run: "off", name, why: `Pick its ${m[1] === "effort" ? "effort" : "model"} on the ⚙ line above: it starts with it.` };
    if (where !== "background" && where !== "closed") run = "terminal";
  }
  if (run === "terminal" && route === "vscode") run = "here"; // (its Claude Code panel's input: you press Enter there)
  if (run === "terminal" && where === "new")
    return { run: "off", name, why: `${name} ${c.why ?? ""}: start the chat first, then it opens in its terminal.` };
  return { run, name, why: c.why ?? "", ...(run === "picker" ? { arg: (m[2] ?? "").trim() } : {}) };
}

// Talpy Chat's model and effort list (commandRun "picker"): /model or /effort and what follows
export function pickerOf(text: string): { kind: "model" | "effort"; value: string } | null {
  const m = /^\/(model|effort)(?:\s+(\S*))?\s*$/.exec(text.trim());
  return m ? { kind: m[1] as "model" | "effort", value: m[2] ?? "" } : null;
}

// What a pick is called ("Sonnet", "Medium effort", "Claude's default model")
export function pickLabel(kind: "model" | "effort", value: string): string {
  const v = value.toLowerCase();
  if (v === "" || v === "default") return kind === "model" ? "Claude's default model" : "Claude's default effort";
  if (kind === "effort" && v === ULTRACODE) return "Ultracode, with Extra high effort";
  const known = (kind === "model" ? CHAT_MODELS : CHAT_EFFORTS).find(([k]) => k === v);
  if (kind === "effort") return `${known ? known[1] : value} effort`;
  return known ? known[1] : value;
}

// Claude's ultracode (an effort of its own: Extra high, with ultracode on; /effort's toggle here)
export const ULTRACODE = "ultracode";

// What a chat uses now (pane.py --conversation's "options", chatpick.options_now): what Claude
// wakes it with, else what you picked for its next message (next), else what it last ran on (its
// last reply's model, e.g. "claude-opus-5-5"); "" is Claude's default, null not known
export interface ChatOptions {
  model: string | null;
  effort: string | null; // xhigh when ultracode is on
  ultracode: boolean;
  next: boolean;
}

// A model as the list names it: its alias for a full name ("claude-opus-5-5[1m]": "opus")
export function modelKey(model: string): string {
  const m = model.toLowerCase();
  return CHAT_MODELS.find(([k]) => k && m.includes(k))?.[0] ?? m;
}

// What the chat uses once a pick is set (how: "now", or "next": from its next message)
export function withPick(now: ChatOptions | null, kind: "model" | "effort", value: string, how: string): ChatOptions {
  const was = now ?? { model: null, effort: null, ultracode: false, next: false };
  const v = value.toLowerCase() === "default" ? "" : value.toLowerCase();
  const next = how === "next";
  return kind === "model" ? { ...was, model: v, next } : { ...was, effort: v === ULTRACODE ? "xhigh" : v, ultracode: v === ULTRACODE, next };
}

// "Opus · Extra high effort, with ultracode" (null: nothing known)
export function nowText(now: ChatOptions | null | undefined): string | null {
  if (!now || (now.model === null && now.effort === null)) return null;
  const words = [now.model === null ? "" : pickLabel("model", modelKey(now.model)),
    now.effort === null ? "" : pickLabel("effort", now.effort) + (now.ultracode ? ", with ultracode" : "")];
  return words.filter(Boolean).join(" · ");
}

// The list for /model or /effort as you type its name (suggestFor): each with what it sets, the one
// the chat uses now marked (✓, "now" or "from your next message"); /effort's also turns ultracode
// on or off
export function pickerItems(kind: "model" | "effort", q: string, now?: ChatOptions | null): Suggestion[] {
  const query = q.toLowerCase();
  const on = !!now?.ultracode;
  const rows: { v: string; label: string; insert: string; toggle?: boolean }[] =
    (kind === "model" ? CHAT_MODELS : CHAT_EFFORTS).map(([v, label]) => ({ v, label, insert: `/${kind} ${v || "default"}` }));
  if (kind === "effort")
    rows.splice(rows.length - 1, 0, { v: ULTRACODE, label: on ? "Turn ultracode off" : "Turn ultracode on", insert: `/effort ${on ? "xhigh" : ULTRACODE}`, toggle: true });
  const used = (v: string) => !!now && (kind === "model" ? now.model !== null && modelKey(now.model) === v : now.effort !== null && now.effort === v);
  return rows
    .filter((r) => !query || (r.v || "default").startsWith(query) || r.label.toLowerCase().split(/[\s']+/).some((w) => w.startsWith(query)))
    .map((r) => {
      const mark = !r.toggle && used(r.v);
      const about = [mark ? (now!.next ? "from your next message" : "now") + (kind === "effort" && on ? ", with ultracode" : "") : "",
        r.toggle ? (on ? "Extra high effort stays" : "with Extra high effort") : "", "for this chat alone"];
      return { text: r.label, about: about.filter(Boolean).join(" · "), insert: r.insert, run: true, ...(mark ? { now: true } : {}) };
    });
}

// What the line under the box says of a command (null: what it says of any message, routeHint)
export function commandHint(ran: CommandRun | null, route: PaneChat["route"] | undefined, host = "", now?: ChatOptions | null): string | null {
  if (!ran) return null;
  const where = host ? ` (on ${hostLabel(host)})` : "";
  if (ran.run === "off") return ran.why;
  if (ran.run === "page") return "Enter opens Talpy Den's Permissions tab: what Claude may do without asking, in every chat.";
  if (ran.run === "picker") {
    const p = pickerOf(ran.name);
    const words = p?.kind === "effort" ? "effort level" : "model";
    const kind = p?.kind ?? "model";
    const exact = !!ran.arg && pickerItems(kind, "", now).some((s) => s.insert === `/${kind} ${ran.arg!.toLowerCase()}`);
    const named = !ran.arg ? "" : exact || !pickerItems(kind, ran.arg, now).length ? pickLabel(kind, ran.arg) : "";
    const used = nowText(now);
    return (used ? `${now!.next ? "From your next message" : "Now"}: ${used}. ` : "")
      + (named ? `Enter: ${named} for this chat alone` : ran.arg ? `Enter: the ${words} picked in the list, for this chat alone`
      : `Enter lists the ${words}s: for this chat alone`)
      + ` (in its terminal, Claude's ${ran.name} would also make it your default for every new chat).${where}`;
  }
  if (ran.run === "terminal" && ran.name === "!")
    return `Its terminal takes no text from outside: Enter copies the command and opens its terminal, to paste it there.${where}`;
  if (ran.run === "terminal")
    return (route === "tmux" ? `${ran.name} ${ran.why}: Enter types it into its tmux pane, for you to press Enter there.`
      : route === "vscodeTerminal" ? `${ran.name} ${ran.why}: Enter types it into its terminal in this window, for you to press Enter there.`
      : `${ran.name} ${ran.why}: Enter opens the chat's terminal, with the command on the clipboard to paste there.`) + where;
  if (ran.name === "!") return `A shell command, as Claude's ! mode: it runs in the chat's folder, then Claude answers what it printed.${where}`;
  return null;
}

// A command's look in the / list, on this chat: where it opens (tag), greyed with why (off)
export function commandOffer(c: CommandOffer, offers: Offers, chat: Pick<PaneChat, "where" | "route"> | null | undefined): { tag: string; off: boolean; tip: string; about: string } {
  const ran = commandRun(c.name, offers, chat) ?? { run: "here" as const, name: c.name, why: "" };
  const about = c.about + (c.kind === "Claude" ? "" : ` · ${c.kind}`);
  if (ran.run === "off") return { tag: "", off: true, tip: ran.why, about: ran.why };
  if (ran.run === "terminal") return { tag: "Terminal", off: false, tip: `${c.name} ${ran.why}: it opens in the chat's terminal, typed in for you there.`, about };
  if (ran.run === "page") return { tag: "Talpy Den", off: false, tip: "Opens Talpy Den's Permissions tab: what Claude may do without asking, in every chat.", about };
  if (ran.run === "picker") return { tag: "", off: false, tip: `For this chat alone: in its terminal, Claude's ${c.name} would also make it your default for every new chat.`, about: about + " · this chat" };
  return { tag: "", off: false, tip: "", about };
}

export interface Suggestion {
  text: string;
  about: string;
  insert: string;
  tag?: string; // a command that runs elsewhere: "Terminal", "Talpy Den" (commandOffer)
  off?: boolean; // one that can't run on this chat: greyed, about says why
  tip?: string;
  run?: boolean; // taken, it runs at once (a model or effort of the picker's list)
  now?: boolean; // the picker's: what the chat uses now (✓)
}

// For the text before the cursor: where the word being completed starts and
// what fits it (at most 8: commands that start with it first, files whose
// name starts with it first, then shorter paths); none for a word you closed
// the list for (dismissed)
export function suggestFor(before: string, offers: Offers | null, dismissed = "", chat?: Pick<PaneChat, "where" | "route"> | null,
                           now?: ChatOptions | null): { start: number; items: Suggestion[]; token: string } {
  // (/model or /effort and a space, on a chat Talpy Chat sets them for: its own list of them)
  const pick = /^\/(model|effort)\s+(\S*)$/.exec(before);
  if (pick && before !== dismissed && commandRun("/" + pick[1], offers, chat)?.run === "picker")
    return { start: 0, items: pickerItems(pick[1] as "model" | "effort", pick[2], now), token: before };
  const command = /^\/([^\s]*)$/.exec(before);
  const file = /(^|\s)@("?)([^\s"]*)$/.exec(before);
  const token = command ? before : file ? before.slice(before.length - file[0].length + file[1].length) : "";
  if (!token || token === dismissed || !offers) return { start: -1, items: [], token };
  const q = (command ? command[1] : file![3]).toLowerCase();
  let items: Suggestion[];
  if (command) {
    const starts = (n: string) => (n.toLowerCase().startsWith("/" + q) ? 0 : 1);
    items = offers.commands.filter((c) => c.name.toLowerCase().includes(q)).sort((a, b) => starts(a.name) - starts(b.name)).slice(0, 8)
      .map((c) => ({ text: c.name, insert: c.name + " ", ...commandOffer(c, offers, chat) }));
  } else {
    const rank = (f: string) => {
      const base = f.slice(f.lastIndexOf("/") + 1).toLowerCase();
      return base.startsWith(q) ? 0 : base.includes(q) ? 1 : 2;
    };
    items = offers.files.filter((f) => f.toLowerCase().includes(q)).slice(0, 400)
      .sort((a, b) => rank(a) - rank(b) || a.length - b.length)
      .map((f) => ({ text: "@" + f, about: "", insert: fileMention(f) + " " }));
  }
  return { start: before.length - token.length, items: items.slice(0, 8), token };
}

// A file named in a reply as Claude's prompt names one (@path; quoted with spaces)
export function fileMention(path: string): string {
  return /\s/.test(path) ? `@"${path}"` : `@${path}`;
}

// The paths of file:// links (a drop's text/uri-list)
export function droppedPaths(uriList: string): string[] {
  return uriList.split(/\r?\n/).map((l) => l.trim()).filter((l) => l.startsWith("file://"))
    .map((l) => { try { return decodeURIComponent(new URL(l).pathname); } catch { return ""; } }).filter(Boolean);
}

// The pictures Claude takes, pasted into a reply
export const PICTURE_TYPES = ["image/png", "image/jpeg", "image/webp", "image/gif"];

// The pictures a text names ([Image: /path], pasted in), each once
export function picturesIn(text: string): string[] {
  const out: string[] = [];
  for (const m of text.matchAll(/\[Image: (\/[^\]\n]+)\]/g)) if (!out.includes(m[1])) out.push(m[1]);
  return out;
}

// text without the picture at path
export function withoutPicture(text: string, path: string): string {
  const token = `[Image: ${path}]`;
  return text.split(token + " ").join("").split(token).join("");
}

// The tab's text size, times VS Code's font size (talpyDen.chatTextScale)
export const TEXT_SCALES = [0.9, 1, 1.15, 1.3, 1.5, 1.75, 2];
export function textScale(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? Math.min(2, Math.max(0.8, value)) : 1.15;
}

// Claude's questions a waiting chat asks ([] for a permission prompt)
export function questionsOf(ask: PermissionAsk | null | undefined): Question[] {
  return ask?.questions ?? [];
}

// One question with one answer: its options, to be buttons (at most 4, as Claude asks); else []
export function oneChoice(ask: PermissionAsk | null | undefined): Question["options"] {
  const qs = questionsOf(ask);
  return qs.length === 1 && !qs[0].multiSelect ? qs[0].options.slice(0, 4) : [];
}

const ANSWERS_MAX = 16;
const ANSWER_CHARS = 10_000;

// Answers a page sent, if they are answers ({question: [strings]}, not too many), else null
export function answersOf(x: unknown): Answers | null {
  if (typeof x !== "object" || x === null || Array.isArray(x)) return null;
  const out: Answers = {};
  const entries = Object.entries(x as Record<string, unknown>);
  if (!entries.length || entries.length > ANSWERS_MAX) return null;
  for (const [q, v] of entries) {
    if (!Array.isArray(v) || v.length > ANSWERS_MAX || !v.every((a) => typeof a === "string" && a.length <= ANSWER_CHARS)) return null;
    out[q] = v as string[];
  }
  return out;
}

const ASK_ID_CHARS = 200;
const ASK_LINE_CHARS = 2000;

// The prompt a notification, row or tab shows, as its answer names it (null: none)
export function shownAsk(p: PermissionAsk | null | undefined): AskShown | null {
  if (!p) return null;
  return { request: p.request ?? null, toolUse: p.toolUse ?? null, line: p.line ?? "" };
}

// What a page says it showed: an AskShown, else null
export function askShownOf(x: unknown): AskShown | null {
  if (typeof x !== "object" || x === null || Array.isArray(x)) return null;
  const { request, toolUse, line } = x as Record<string, unknown>;
  const id = (v: unknown) => v === null || (typeof v === "string" && v.length > 0 && v.length <= ASK_ID_CHARS);
  if (!id(request) || !id(toolUse) || typeof line !== "string" || line.length > ASK_LINE_CHARS) return null;
  return { request: request as string | null, toolUse: toolUse as string | null, line };
}

// Is what the chat asks now the prompt that was shown? By its tool use when
// both know it, else by the hook's request when both have one, else by its
// line (an older backend's, with neither)
export function sameAsk(shown: AskShown, now: PermissionAsk): boolean {
  const toolUse = now.toolUse ?? null;
  if (shown.toolUse && toolUse) return shown.toolUse === toolUse;
  if (shown.request && now.request) return shown.request === now.request;
  return shown.line === (now.line ?? "");
}

// The key of a chat's mark in status.reviewed
export function reviewKey(chatId: string, host?: string): string {
  return host ? `${host}|${chatId}` : chatId;
}

// Finished, changed files, not marked reviewed since (0: marked not
// reviewed); what chats changed before the widget first looked isn't to review
export function reviewPending(
  item: { review?: Review | null; state?: SessionState; chatId?: string; sessionId: string },
  status: Status | null | undefined,
  host?: string,
): boolean {
  if (!item.review?.editedAt || item.state === "working" || item.state === "waiting") return false;
  return !reviewSeen(item, status, host);
}

// Its changes since its last edit marked reviewed (or older than what's to
// review at all), whether it works now or not
export function reviewSeen(
  item: { review?: Review | null; chatId?: string; sessionId: string },
  status: Status | null | undefined,
  host?: string,
): boolean {
  const edited = item.review?.editedAt;
  if (!edited) return true;
  const mark = status?.reviewed?.[reviewKey(item.chatId || item.sessionId, host)];
  const seen = mark === 0 ? 0 : Math.max(mark ?? 0, status?.reviewedSince ?? 0);
  return seen >= edited;
}

// The reply waiting for a chat's turn to end (pane.py --send --after-turn)
export function queuedReply(status: Status | null | undefined, chatId: string, host?: string): QueuedTask | null {
  return status?.queue?.find((t) => t.afterTurn && t.chat === chatId && (t.host || "") === (host || "")) ?? null;
}

// The tests badge: "Tests ✓", "Tests ✗" or "Not tested" (since the last edit)
export function testsText(review: Review | null | undefined): { text: string; title: string; ok: boolean | null } | null {
  if (!review) return null;
  const run = review.tests;
  if (!run) return { text: "Not tested", title: "Claude ran no test command (pytest, npm test, cargo test, …) after it last changed a file.", ok: null };
  return run.ok
    ? { text: "Tests", title: `Tests passed after its last edit: ${run.command}`, ok: true }
    : { text: "Tests", title: `Tests failed after its last edit: ${run.command}`, ok: false };
}

// Your message, at once: the chat tab shows it as you send it (as being sent,
// then as yours) till the conversation has it, as the Plasma pane does
export interface PendingSent {
  id: number;
  text: string;
  at: number; // ms, when you sent it
  state: "held" | "sending" | "sent"; // held: sent while Claude works, a moment to take it back (HOLD_MS)
  sentAt: number; // ms, when pane.py said it went
  known: string[]; // the keys of your prompts shown then: the one this becomes is another
  until?: number; // held: when it goes to Claude (ms)
  how?: "auto" | "background" | "copy" | "enter"; // held: how it's sent then
}

// Your answer, at once: as you answer what a chat asks (in the tab, its row or
// a notification), the tab shows it as yours till the conversation has it
export interface PendingAnswer {
  id: number;
  text: string; // as the conversation will have it (answerText)
  answered: NonNullable<PaneItem["answered"]>;
  at: number; // ms, when you answered
  for: string; // the key of the call it answers ("": not known)
  known: string[]; // the keys of your answers listed then: the one this becomes is another
  state: "sending" | "sent";
  sentAt: number; // ms, when pane.py said it went
}

// One question's answer as Claude's dialog sends it (pane.py answer_text):
// the option chosen or what you typed; several, ", " between them (one with
// ", " or a quote in it quoted)
export function joinAnswer(values: string[], multi: boolean): string {
  const given = values.map((v) => v.trim()).filter(Boolean);
  if (!multi) return given[0] ?? "";
  return given.map((v) => (v.includes(", ") || v.includes('"') ? JSON.stringify(v) : v)).join(", ");
}

// What your answer to a prompt says, as the conversation will have it
// (pane.py your_answer): the options you picked or what you typed, one line a
// question when there are several ("Header: answer"); Approved the plan, or
// Keep planning and your note; a Deny's or a Decline's note. "": nothing of
// yours to show (an Allow, a Deny or a Decline without a note)
export function answerText(ask: Pick<PermissionAsk, "questions" | "plan">, decision: Decision, note: string, answers?: Answers): string {
  const said = note.trim();
  if (ask.plan) {
    if (decision === "approve" || decision === "approve-edits") return "Approved the plan";
    return decision === "keep" || decision === "deny" ? "Keep planning" + (said ? "\n" + said : "") : "";
  }
  if (decision === "answer" && answers) {
    const given = (ask.questions ?? []).map((q) => ({ q, text: joinAnswer(answers[q.question] ?? [], q.multiSelect) })).filter((a) => a.text);
    return given.map((a) => (given.length > 1 ? `${a.q.header || a.q.question}: ` : "") + a.text).join("\n");
  }
  return decision === "deny" ? said : "";
}

// What kind of answer it is (PaneItem answered)
export function answerKind(ask: Pick<PermissionAsk, "questions" | "plan">): NonNullable<PaneItem["answered"]> {
  return ask.plan ? "plan" : ask.questions?.length ? "question" : "permission";
}

// The call an answer is to: the one it asks about (its tool use), else its
// tool's newest call that has no result yet ("": none listed)
export function answerFor(items: PaneItem[], ask: Pick<PermissionAsk, "tool" | "toolUse">): string {
  if (ask.toolUse && items.some((it) => it.key === ask.toolUse)) return ask.toolUse;
  for (let i = items.length - 1; i >= 0; i--) {
    const it = items[i];
    if (it.kind === "tool" && it.status === "open" && it.name === ask.tool) return it.key;
  }
  return "";
}

// The ids of the answers the conversation has now: its call's answer (or
// its call has a result, with nothing of yours to show), or, for one whose
// call isn't known, an answer of yours that wasn't there; or one that went
// 30 s ago (it went: the conversation just doesn't show it)
export function answersTaken(items: PaneItem[], pending: PendingAnswer[], now: number): Set<number> {
  const done = new Set<number>();
  for (const p of pending) {
    const found = p.for
      ? items.some((it) => it.key === `${p.for}/answer` || (it.key === p.for && it.status !== "open"))
      : items.some((it) => !!it.answered && !p.known.includes(String(it.key)));
    if (found || (p.state === "sent" && now - p.sentAt > 30000)) done.add(p.id);
  }
  return done;
}

// How long a message sent while Claude works waits, queued, to be taken back
// (Edit, Cancel, ↑ in an empty box), as ↑ does in Claude's terminal
export const HOLD_MS = 5000;

const squash = (s: string) => s.replace(/\s+/g, " ").trim();

// The ids of the ones the conversation has now: a prompt of yours that wasn't
// there when you sent it, with its words (or the start of them, cut with …);
// or, after a moment, any new one of this computer's chat (local: Claude can
// have changed its words, a picture's say); or one that went 30 s ago (it
// went: the conversation just doesn't show it)
export function pendingTaken(items: PaneItem[], pending: PendingSent[], now: number, local: boolean): Set<number> {
  const claimed = new Set<string>();
  const done = new Set<number>();
  for (const p of pending) {
    if (p.state === "held") continue; // (not sent yet: nothing in the conversation is it)
    const want = squash(p.text);
    const bare = want.startsWith("!") ? squash(want.slice(1)) : ""; // (a shell command waits in Claude's queue without its !)
    const found = items.find((it) => {
      const key = String(it.key);
      if (it.kind !== "you" || it.answered || p.known.includes(key) || claimed.has(key)) return false;
      const said = squash(it.text ?? "");
      const cut = said.endsWith("…") ? said.slice(0, -1).trim() : "";
      return said === want || (bare !== "" && said === bare) || (cut !== "" && want.startsWith(cut))
        || (local && p.state === "sent" && now - p.sentAt > 3000 && (it.at ?? 0) >= p.at - 2000);
    });
    if (found) claimed.add(String(found.key));
    if (found || (p.state === "sent" && now - p.sentAt > 30000)) done.add(p.id);
  }
  return done;
}

// What ↑ / ↓ go through in the reply box: your prompts, newest first, each
// once. This chat's own first: the ones you just sent (not those held, still
// in their band to take back), then the conversation's; then your past prompts
// in its folder (Claude's prompt history, history.jsonl, which has only some
// of the messages sent from outside its terminal, and is read once a minute)
export function promptHistory(items: PaneItem[], pending: PendingSent[], past: string[]): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  const add = (t: string | undefined) => {
    const text = (t ?? "").trim();
    const key = squash(text);
    if (text && !seen.has(key)) {
      seen.add(key);
      out.push(text);
    }
  };
  for (let i = pending.length - 1; i >= 0; i--) if (pending[i].state !== "held") add(pending[i].text);
  for (let i = items.length - 1; i >= 0; i--) if (items[i].kind === "you" && !items[i].answered) add(items[i].text);
  for (const t of past) add(t);
  return out;
}

// Is a conversation's stamp ("<size>:<time>/<length>") one to show, after the
// one shown (current)? Not one read for another length (Show earlier
// meanwhile), nor one read before it (a transcript only grows): the watcher's
// answer and a read's can cross
export function stampFresher(next: unknown, current: string, limit: number): boolean {
  const a = String(next ?? "").split("/");
  if (a.length > 1 && a[1] !== String(limit)) return false;
  if (!current) return true;
  const b = current.split("/");
  return a[1] !== b[1] || Number(a[0].split(":")[0]) >= Number(b[0].split(":")[0]);
}

// Your text with each picture it names ([Image: /path]) as [Image #1],
// [Image #2]…, as Claude's terminal writes them (its picture under it)
export function numberedPictures(text: string): string {
  const seen = new Map<string, number>();
  return text.replace(/\[Image: (\/[^\]\n]+)\]/g, (_all, p: string) => {
    if (!seen.has(p)) seen.set(p, seen.size + 1);
    return `[Image #${seen.get(p)}]`;
  });
}

// What a code block's Copy puts on the clipboard: its text, without the "! "
// of a command Claude means for its prompt in a terminal (where a line that
// starts with ! runs in the chat's shell) when each of its lines has one. The
// pane shows it as written; pasted in a shell, ! is "not" (the command runs,
// its exit status turned round, and a && after it goes the other way).
export function clipboardCode(code: string): string {
  const lines = code.split("\n");
  const filled = lines.filter((line) => line.trim() !== "");
  if (filled.length === 0 || !filled.every((line) => /^!\s+\S/.test(line))) return code;
  return lines.map((line) => line.replace(/^!\s+/, "")).join("\n");
}

// How a reply reaches the chat, in a sentence
export function routeHint(route: PaneChat["route"], hasProcess: boolean, kind: string, host: string, asks: ReplyAnswer = ""): string {
  const where = host ? ` (on ${hostLabel(host)})` : "";
  if (asks) return REPLY_ANSWERS[asks].hint + where;
  switch (route) {
    case "tmux":
      return `Typed into its tmux pane.${where}`;
    case "vscodeTerminal":
      return "Typed into its terminal in this window.";
    case "vscode":
      return `Goes into the chat's input in its Claude Code panel: press Enter there.${where}`;
    case "terminal":
      return `Its terminal takes no text from outside: send it, and Claude there quits and the chat goes on in the background, or copy it and open its terminal.${where}`;
    default:
      return hasProcess && kind === "bg"
        ? `Goes into the background chat as it runs, as if you typed it there.${where}`
        : `The chat goes on in the background with your message.${where}`;
  }
}

// Stop on its working line (Plasma ChatPane canStop, the same rule and words): while Claude
// works on its turn, what it does now stops, as Esc in its terminal, and the chat stays and takes
// your next message. Where Talpy Chat reaches it: a terminal of this window (Ctrl+C typed in, as
// Interrupt does), tmux (Ctrl+C in its pane), or a background chat on a Claude Code version that
// was checked on (its row's bgStop: Esc through Claude's background service). Else no Stop, and
// elsewhere says where to stop it (the working line's tooltip); title: Stop's own
export function stopOf(chat: Pick<PaneChat, "state" | "atWork" | "where" | "route" | "bgStop"> | null | undefined): { can: boolean; title: string; elsewhere: string } {
  const no = { can: false, title: "", elsewhere: "" };
  if (!chat || chat.state !== "working" || !chat.atWork) return no;
  if (chat.route === "vscodeTerminal")
    return { ...no, can: true, title: "Stop what Claude is doing now, as Ctrl+C in its terminal: the chat stays open there and takes your next message." };
  if (chat.where === "tmux")
    return { ...no, can: true, title: "Stop what Claude is doing now, as Ctrl+C in its tmux pane: the chat stays open there and takes your next message." };
  if (chat.where === "background" && chat.bgStop)
    return { ...no, can: true, title: "Stop what Claude is doing now, as Esc in its terminal: the background chat stays and takes your next message." };
  return { ...no, elsewhere: chat.where === "claude" ? "To stop it: the stop button in its Claude Code panel."
    : chat.where === "background" ? "To stop it: open it in a terminal and press Esc there. Talpy Chat's Stop doesn't know the background chats of this Claude Code version yet."
    : "To stop it: press Esc in its terminal. Talpy Chat can't type into that terminal." };
}

// How full the chat's context is (pane.py: talpy_den.context_left), a tag in its header: what's
// left till Claude compacts the chat on its own (auto-compact), as Claude Code counts it; near: as
// Claude Code says it's close, in the warning colour. None when it can't be known (Plasma ChatPane:
// the same words)
export interface ContextLeft {
  used: number; // tokens Claude's last message read, cached or not
  window: number; // its model's context window
  compactAt: number; // where Claude compacts it
  left: number; // % till then
  near: boolean;
}
export function contextText(c: ContextLeft): string {
  return `Context ${c.left}% left`;
}
export function contextHint(c: ContextLeft): string {
  return `${formatTokens(c.used)} of its ${formatTokens(c.window)} tokens of context are used. Claude compacts the chat on its own at about ${formatTokens(c.compactAt)}: it sums up the conversation so far and goes on from that.` +
    (c.near ? " That's soon: run /compact now to say what it keeps, if you'd rather choose." : "");
}

// Claude's turn so far (pane.py: talpy_den.TurnSoFar), at the working line's end while it works:
// the time since your message that started it, and its steps (tool calls) since. The time is
// shown to the second ("8m 12s", "1h 5m 7s"): tickIn says when it changes next
export interface TurnSoFar {
  startedAt: number; // ms
  steps: number;
}
export function turnTime(ms: number): string {
  const s = Math.floor(Math.max(0, ms) / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  return m < 60 ? `${m}m ${s % 60}s` : `${Math.floor(m / 60)}h ${m % 60}m ${s % 60}s`;
}
export function turnText(t: TurnSoFar, now: number): string {
  const time = turnTime(now - t.startedAt);
  return t.steps > 0 ? `${time} · ${t.steps === 1 ? "1 step" : `${t.steps} steps`}` : time;
}
export function turnHint(t: TurnSoFar, now: number): string {
  return `Claude's turn so far: ${turnTime(now - t.startedAt)} since your message, ${t.steps === 1 ? "1 step" : `${t.steps} steps`} (its tool calls, in the Steps tab).`;
}
export function turnTickIn(t: TurnSoFar, now: number): number {
  return 1000 - (Math.max(0, now - t.startedAt) % 1000);
}

// Times in the conversation (Plasma ChatPane, the same words and rules): a line before the first
// item of each new day, none before the first item shown ("Today", "Yesterday", "Mon 3 Nov"; the
// year when it isn't this one), and a message's time on hover ("14:32"; "Yesterday 14:32",
// "Mon 3 Nov 14:32" for an earlier day). A day starts only with a later day than any before it (a
// message still in Claude's queue is listed last, with the time you sent it); items with no time
// start none
function dayStart(ms: number): number {
  const d = new Date(ms);
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}
export function dayLabel(at: number, now: number): string {
  const d = new Date(at);
  const days = Math.round((dayStart(now) - dayStart(at)) / 86_400_000);
  if (days <= 0) return "Today";   // (a host's clock a little ahead: today too)
  if (days === 1) return "Yesterday";
  return d.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short",
                                    ...(d.getFullYear() !== new Date(now).getFullYear() ? { year: "numeric" } : {}) });
}
export function timeText(at: number, now: number): string {
  return dayStart(at) >= dayStart(now) ? clockText(at) : `${dayLabel(at, now)} ${clockText(at)}`;
}
// The keys of the items a day's line comes before, of those the tab shows (showsOn: on the Chat
// tab, a day with only tool calls has no line); Date is made once a day, not once an item
export function dayBreaks(items: readonly PaneItem[], steps: boolean): Set<string> {
  const out = new Set<string>();
  let end = 0;   // (when the latest day so far ends, ms)
  for (const it of items) {
    if (!it.at || it.at < end || !showsOn(it, steps)) continue;
    if (end) out.add(it.key);
    const d = new Date(it.at);
    end = new Date(d.getFullYear(), d.getMonth(), d.getDate() + 1).getTime();
  }
  return out;
}

// Copy, on a message's hover: Claude's reply as Markdown, as the transcript has it (not as it's
// shown), yours as you typed it (a command too: "/compact", "!ls"); nothing for other items
export function copyText(it: PaneItem): string {
  return it.kind === "claude" || it.kind === "you" ? it.text ?? "" : "";
}
// A text Talpy Chat keeps cut (pane.py's TEXT_CHARS: "…" on a line of its own at its end): Copy
// reads it whole from the transcript first (pane.py --reply-text), else it's copied as it is
export function copyCut(text: string): boolean {
  return text.endsWith("\n…");
}
// A thinking line's mark (∴, as in Claude Code's terminal), on hover (Plasma ChatPane: the same words)
export const THINKING_TIP = "Claude's thinking, as Claude Code sums it up while Claude works: not its reply. It can tell what Claude means to do as if it were done.";

// Claude's last reply (Ctrl+Shift+C copies it; not a thinking line)
export function lastReply(items: readonly PaneItem[]): PaneItem | null {
  for (let i = items.length - 1; i >= 0; i--) if (items[i].kind === "claude" && !items[i].thinking) return items[i];
  return null;
}

// Search (Ctrl+F) and folding (Show more / Show less, Ctrl+O): the widget's find.mjs, so Plasma's
// Talpy Chat counts the same matches and folds the same texts (see there)
export { allIn, findCount, findIn, findParts, findStep, FOLD_LINES, FOLD_SHOWN, foldOf, nthIn, plainOf, type FindHit, type Fold } from "../../vendor/find.mjs";

// Bookmarks (Ctrl+D, the list, Alt+↑ / Alt+↓): the widget's bookmarks.mjs, so Plasma's Talpy Chat
// bookmarks the same messages and goes to the same one (see there)
export { adoptable, BOOKMARKS_MAX, canBookmark, entryOf, keysOf, oneLine, SNIPPET_CHARS, snippetOf, stateOf, staysOpen, step as bookmarkStep, withBookmark, withoutBookmark, type Bookmark, type BookmarkState, type BookmarkStep } from "../../vendor/bookmarks.mjs";

// Does it show on that tab: Chat leaves out Claude's tool calls, but not a question or a plan you
// answered, nor a call you denied with a note (what a call made shows on both, under it)
export function showsOn(it: PaneItem, steps: boolean): boolean {
  return steps || it.kind !== "tool" || askedShows(it) || it.asked?.state === "denied";
}
// The "3 new" badge at the list's bottom while you're scrolled up: what came in below since you
// left its end (seen: the keys there then), after the last of those, that its tab shows (earlier
// ones, Show earlier's, are above; none of them left: nothing to tell). A click goes to the end;
// it's gone once you're there
export function newBelow(seen: ReadonlySet<string>, items: readonly PaneItem[], steps: boolean): number {
  let n = 0;
  for (let i = items.length - 1; i >= 0; i--) {
    if (seen.has(items[i].key)) return n;
    if (showsOn(items[i], steps)) n++;
  }
  return 0;
}
export function newText(n: number): string {
  return `${n} new`;
}
export function newHint(n: number): string {
  return `${n === 1 ? "One new item" : `${n} new items`} below, since you scrolled up. Click to go to the end.`;
}

// Suggested replies (Plasma ChatPane, the same rules and words): small chips above the box once
// Claude's turn is over, each sent only with a click. First the answers to the question Claude
// ended with (pane.py asks_of: its options, an either/or's halves, or Yes and No), then your
// usual replies after a turn that ended the same way (pane.py --replies: usual_replies)
export type TurnEnded = "asked" | "finished" | "limit" | "interrupted" | "failed" | "stopped";
export interface Asks {
  kind: "options" | "either" | "yesno";
  choices: { label: string; send: string; recommended: boolean }[];
}
export interface UsualReplies {
  chips: Partial<Record<TurnEnded, string[]>>; // how a turn ended -> what you usually reply then
  ranked: string[]; // every reply of yours, the most used first: what you type is completed from them
}
export interface ReplyChip {
  label: string;
  send: string;
  recommended: boolean; // (Claude says it would take this option)
  usual: boolean; // (one of your usual replies: "Don't suggest this" hides it)
  title: string;
  predicted?: boolean; // (Claude's own guess at your reply: Conversation.predicted)
}
export const CHIPS_MAX = 4;
export const CHIPS_IGNORED = 5; // turns in a row with chips and none used: none for CHIPS_REST_MS then
export const CHIPS_REST_MS = 30 * 60_000;
export const CHIPS_AFTER_SEND_MS = 15_000; // (just after you sent something, only the transcript says the turn is over)
const ENDED_AFTER: Record<TurnEnded, string> = {
  asked: "Claude's questions", finished: "a finished turn", limit: "a usage limit", interrupted: "an interruption",
  failed: "an error", stopped: "a chat that stopped",
};

// A reply as replies are compared (pane.py reply_key): case, outer quotes, final punctuation and
// extra spaces left out
export function replyKey(text: string): string {
  return text.normalize("NFKC").toLowerCase().trim().replace(/^["'`“”‘’]+|["'`“”‘’]+$/g, "")
    .replace(/[\s.!?,;:…。！？]+$/u, "").split(/\s+/).filter(Boolean).join(" ");
}

// The chips for a turn that's over: Claude's own guess at your reply (predicted: a background
// chat's), then Claude's question's (more options than fit: the ones it recommends, then the first
// ones, in their order), then your usual replies after a turn that ended so, each once and none you
// hid; at most CHIPS_MAX
export function chipsOf(asks: Asks | null | undefined, ended: TurnEnded | null | undefined, usual: UsualReplies | null | undefined,
                        hidden: ReadonlySet<string> = new Set(), predicted?: string | null): ReplyChip[] {
  const guess = (predicted ?? "").trim();
  const room = CHIPS_MAX - (guess ? 1 : 0);
  let choices = asks?.choices ?? [];
  if (choices.length > room) {
    const marked = choices.filter((c) => c.recommended).slice(0, room);
    const rest = choices.filter((c) => !c.recommended).slice(0, room - marked.length);
    choices = choices.filter((c) => marked.includes(c) || rest.includes(c));
  }
  const out: ReplyChip[] = [];
  const seen = new Set<string>();
  const add = (label: string, send: string, recommended: boolean, usual: boolean, guessed = false) => {
    const n = out.length + 1;
    out.push({ label, send, recommended, usual, ...(guessed ? { predicted: true } : {}), title: guessed
      ? `Claude's own guess at your reply: sends “${send}” (Alt+${n}). Shift+click: put it in the box first, to add to it.`
      : usual
      ? `Your usual reply after ${ENDED_AFTER[ended!]}: sends “${send}” (Alt+${n}). Shift+click: put it in the box first, to add to it. Right-click: don't suggest it again.`
      : `Answers Claude's question with “${send}” (Alt+${n}).${recommended ? " Claude recommends this one." : ""} Shift+click: put it in the box first, to add to it.` });
    seen.add(replyKey(send));
  };
  if (guess) add(guess, guess, false, false, true);
  for (const c of choices) if (!seen.has(replyKey(c.send))) add(c.label, c.send, !!c.recommended, false);
  for (const t of (ended && usual?.chips?.[ended]) || []) {
    if (out.length >= CHIPS_MAX) break;
    const key = replyKey(t);
    if (!seen.has(key) && !hidden.has(key)) add(t, t, false, true);
  }
  return out;
}

// Whether the chips show: Suggest replies on, a chat that's going (not a new one), its turn over
// (the transcript says so, else the chat isn't at work and nothing went to it a moment ago), not
// asking for a permission, the box empty, nothing of yours on its way or queued, not backed off
export function chipsWanted(c: { on: boolean; fresh: boolean; ended: TurnEnded | null | undefined; over: boolean; state: string; text: string;
                                 pending: boolean; resting: boolean; sentAt: number }, now: number): boolean {
  if (!c.on || c.fresh || !c.ended || c.text.trim() !== "" || c.pending || c.resting || c.state === "waiting") return false;
  return c.over || (c.state !== "working" && now - c.sentAt > CHIPS_AFTER_SEND_MS);
}

// Backing off, as Claude Code does with its own suggestions: a message you sent after chips showed
// that turn (shown: those; typing hides them), none of them (typed or clicked), counts;
// CHIPS_IGNORED in a row, and there are none for CHIPS_REST_MS (restUntil: when they're back; 0: none now)
export function chipsAfterSend(ignored: number, shown: ReplyChip[], text: string, now: number): { ignored: number; restUntil: number } {
  if (!shown.length) return { ignored, restUntil: 0 };
  if (shown.some((c) => replyKey(c.send) === replyKey(text))) return { ignored: 0, restUntil: 0 };
  return ignored + 1 >= CHIPS_IGNORED ? { ignored: 0, restUntil: now + CHIPS_REST_MS } : { ignored: ignored + 1, restUntil: 0 };
}

// Completion as you type: the rest of the first of your usual replies (those after a turn that
// ended as this one did first) that starts with what you typed, in grey; "" for none. Not for a
// command, nor a text of several lines
export function completionOf(text: string, usual: UsualReplies | null | undefined, ended?: TurnEnded | null,
                             hidden: ReadonlySet<string> = new Set()): string {
  if (!usual || !text.trim() || text.includes("\n") || /^[/!]/.test(text)) return "";
  const low = text.toLowerCase();
  for (const r of [...((ended && usual.chips?.[ended]) || []), ...(usual.ranked ?? [])])
    if (r.length > text.length && r.toLowerCase().startsWith(low) && !hidden.has(replyKey(r))) return r.slice(text.length);
  return "";
}

// A new chat's line under the box (Plasma's routeHint for one, the same words)
export function newChatHint(fresh: NewChat, starting: boolean): string {
  return starting ? "The chat starts in the background with your message."
    : `Your first message starts the chat in the background, on ${fresh.account} in ${fresh.folder}: you answer what it asks here.`;
}

// A background chat that asks you something you can answer here: your reply
// answers it, as typing in its own prompt does, and never stops the chat
// (Plasma ChatPane replyAnswers): "deny" a permission, your words going to
// Claude with the No; "plan" keeps it planning, with them as what to change;
// "question" (one): they're your answer, in your own words; "decline"
// (several): declined, with them. "": your reply goes as routeHint says
export type ReplyAnswer = "" | "deny" | "plan" | "question" | "decline";
export function replyAnswers(chat: Pick<PaneChat, "where" | "permission"> | null | undefined): ReplyAnswer {
  const p = chat?.permission;
  if (!p || chat.where !== "background" || (p.answer !== "hook" && p.answer !== "keys")) return "";
  const questions = p.questions ?? [];
  return questions.length > 1 ? "decline" : questions.length ? "question" : p.plan ? "plan" : "deny";
}
// Its Send button, and the line under the box
export const REPLY_ANSWERS: Record<Exclude<ReplyAnswer, "">, { send: string; hint: string }> = {
  deny: { send: "Deny with this note", hint: "It's asking for a permission: your message denies it and goes to Claude with the No, as if you typed it in its prompt." },
  plan: { send: "Keep planning with this note", hint: "It's asking about its plan: your message keeps it planning and goes to Claude as what to change." },
  question: { send: "Send as your answer", hint: "It's asking you a question: your message is your answer, in your own words." },
  decline: { send: "Decline with this note", hint: "It's asking you questions: your message declines them and goes to Claude with the No." },
};

// A recent chat as a row the tab can show (it has no process: finished)
export function recentAsRow(c: RecentChat): Pick<Session, "sessionId" | "chatId" | "profileDir" | "name" | "cwd" | "state" | "pid" | "kind"> & {
  review?: Review | null;
  changes?: RecentChat["changes"];
} {
  return { sessionId: c.sessionId, chatId: c.sessionId, profileDir: c.profileDir, name: c.name, cwd: c.cwd, state: "done", pid: null,
           kind: "chat", review: c.review ?? null, changes: c.changes ?? null };
}
