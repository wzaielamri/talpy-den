// The chat tab (src/chatPane.ts, webview/chat.tsx): one chat's conversation
// as the widget's pane.py reads it, a box to reply, what it asks while it
// waits for a permission, and its review (what it changed, Undo, Commit,
// Mark reviewed). Shared by the extension and the tab's page.

import type { Answers, AskShown, Decision, PermissionAsk, Question, QueuedTask, RecentChat, Review, Session, SessionState, Status } from "./types";

// One item of a chat's conversation (pane.py: conversation_items)
export interface PaneItem {
  kind: "you" | "claude" | "tool" | "note";
  key: string; // the same in the next answer, while it's listed
  text?: string; // you, claude (markdown), note
  name?: string; // tool: its name, e.g. "Bash"
  line?: string; // tool: one line, e.g. "Bash: npm test"
  status?: "ok" | "error" | "open"; // tool: how it went ("open": no result yet)
  input?: string; // tool: what it ran or changed
  output?: string; // tool: what came back
  summary?: string; // tool: what came of it, in a line ("3 lines", "1 failed", …)
  diff?: string[]; // tool: an edit's change (unified lines, @@ at the file's line numbers when known)
  error?: boolean; // note: an API error (a usage limit…)
  at: number | null;
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
  route: Session["reply"] | "vscodeTerminal"; // vscodeTerminal: one of this window's terminals (it types it in)
  busy: boolean; // working or waiting
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
}

// Where a chat runs (the tag under its name, the same words as the rows'):
// a background session, closed (no process: a reply goes on in the
// background), a Claude Code panel, tmux, a terminal of VS Code (this
// window's or another's) or another terminal
export type ChatWhere = "background" | "closed" | "claude" | "tmux" | "vscode" | "terminal";

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

// Its tag, and what the tag says on hover (terminalApp: the terminal's name)
export function whereTag(where: ChatWhere, terminalApp = ""): { tag: string; title: string } {
  switch (where) {
    case "background":
      return { tag: "Background", title: "A background chat: Claude's background service runs it, with no terminal of its own. Open its window to see it in a terminal (claude attach)." };
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
  | { type: "result"; kind: string; ok: boolean; message: string; ask?: boolean } // ask: its terminal takes no text: choose
  | { type: "textSize"; scale: number } // talpyDen.chatTextScale
  | { type: "diffLayout"; split: boolean } // talpyDen.diffSideBySide
  | { type: "picked"; paths: string[] } // files picked to attach (+), attached as dropped ones
  | { type: "picture"; id: string; path: string; error: string } // a pasted picture, saved (path: where the chat opens it)
  | { type: "file"; id: string; path: string } // a file dropped on the tab: named in the reply (@path)
  | { type: "offers"; offers: Offers } // what the reply box offers as you type (pane.py --complete)
  // dictating: "starting" (the microphone, not recording yet), "recording", "writing", "model" (downloading one), "setup" (setting it up), "" (done:
  // text written down, or why not); offerModel: whisper is there but no speech model (engine: which
  // one), offerSetup: nothing writes it down yet (setupMb: what setting up downloads); the tab asks
  // before either
  | { type: "dictation"; state: "" | "starting" | "recording" | "writing" | "model" | "setup"; text?: string; message?: string; offerModel?: boolean;
      engine?: string; offerSetup?: boolean; setupMb?: number; ok?: boolean } // ok: message says it worked (set up, downloaded)
  | { type: "visible"; visible: boolean }; // the tab shown or hidden (its working Talpy moves only while shown)

// tab -> extension
export type PaneMessage =
  | { type: "ready" }
  | { type: "more" } // older items too
  | { type: "send"; text: string; how: "auto" | "background" | "copy" | "enter"; afterTurn: boolean }
  | { type: "unqueue" } // the reply waiting for the turn to end
  | { type: "answer"; decision: Decision; note: string; answers?: Answers; shown: AskShown | null } // shown: the prompt you answer
  | { type: "review" }
  | { type: "diff"; path: string } // a file's change in VS Code's diff editor
  | { type: "undo"; path: string } // "*": all of them
  | { type: "commit"; message: string }
  | { type: "reviewed"; on: boolean }
  | { type: "openWindow" }
  | { type: "openPlan" } // the plan it made
  | { type: "moveToClaudeCode" } // Claude quits in its terminal, the chat reopens in a Claude Code panel (asks first)
  | { type: "copy"; text: string } // a code block of a reply, to the clipboard
  | { type: "textSize"; scale: number } // A− / A+: talpyDen.chatTextScale
  | { type: "diffLayout"; split: boolean } // side by side or one after the other: talpyDen.diffSideBySide
  | { type: "pickFiles" } // + : files to attach, from VS Code's file dialog (answered with "picked")
  | { type: "picture"; id: string; mime: string; data: string } // pasted in the reply (base64): saved, an SSH host's copied there
  | { type: "attach"; id: string; path: string } // a file dropped from VS Code's Explorer: a picture saved as one, a file named
  | { type: "screenshot"; id: string } // a region of the screen you pick, as a picture
  | { type: "complete" } // what the reply box offers (answered with "offers")
  | { type: "dictate"; action: "toggle" | "cancel" | "getModel" | "setup" }; // the microphone (answered with "dictation")

// What the reply box offers as you type (pane.py --complete): / at the start
// Claude's commands, yours and the project's, and skills; @ the project's
// files; ↑ / ↓ your past prompts in its folder (newest first)
export interface Offers {
  commands: { name: string; about: string; kind: string }[];
  files: string[];
  history: string[];
}

export interface Suggestion {
  text: string;
  about: string;
  insert: string;
}

// For the text before the cursor: where the word being completed starts and
// what fits it (at most 8: commands that start with it first, files whose
// name starts with it first, then shorter paths); none for a word you closed
// the list for (dismissed)
export function suggestFor(before: string, offers: Offers | null, dismissed = ""): { start: number; items: Suggestion[]; token: string } {
  const command = /^\/([^\s]*)$/.exec(before);
  const file = /(^|\s)@("?)([^\s"]*)$/.exec(before);
  const token = command ? before : file ? before.slice(before.length - file[0].length + file[1].length) : "";
  if (!token || token === dismissed || !offers) return { start: -1, items: [], token };
  const q = (command ? command[1] : file![3]).toLowerCase();
  let items: Suggestion[];
  if (command) {
    const starts = (n: string) => (n.toLowerCase().startsWith("/" + q) ? 0 : 1);
    items = offers.commands.filter((c) => c.name.toLowerCase().includes(q)).sort((a, b) => starts(a.name) - starts(b.name))
      .map((c) => ({ text: c.name, about: c.about + (c.kind === "Claude" ? "" : ` · ${c.kind}`), insert: c.name + " " }));
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

// How a reply reaches the chat, in a sentence
export function routeHint(route: PaneChat["route"], hasProcess: boolean, kind: string, host: string): string {
  const where = host ? ` (on ${host})` : "";
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
        ? `Its background chat stops, then goes on with your message.${where}`
        : `The chat goes on in the background with your message.${where}`;
  }
}

// A recent chat as a row the tab can show (it has no process: finished)
export function recentAsRow(c: RecentChat): Pick<Session, "sessionId" | "chatId" | "profileDir" | "name" | "cwd" | "state" | "pid" | "kind"> & {
  review?: Review | null;
  changes?: RecentChat["changes"];
} {
  return { sessionId: c.sessionId, chatId: c.sessionId, profileDir: c.profileDir, name: c.name, cwd: c.cwd, state: "done", pid: null,
           kind: "chat", review: c.review ?? null, changes: c.changes ?? null };
}
