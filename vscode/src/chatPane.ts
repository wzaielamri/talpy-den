// A chat in an editor tab: its conversation as it goes (Claude's replies
// rendered, each tool call one line), a box to reply, what it asks while it
// waits for a permission (Allow once, Always allow, Deny), and its review:
// the files it changed against how they were before the chat, Undo, Commit
// only its files, Mark reviewed. The widget's pane.py does the work; the
// tab's page (webview/chat.tsx) only shows it and says what you clicked.
//
// What runs is decided here, from the extension's own state: the page names
// nothing but the tab's own chat, and what you typed.

import * as crypto from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import * as vscode from "vscode";
import type { Actions } from "./actions";
import { AGENT_ID } from "./agentRun";
import type { Backend } from "./backend";
import { openComparison } from "./changes";
import { cacheDir, chatOptionArgs, configDirArgs, setChatOptions, settings } from "./config";
import type { Dashboard } from "./dashboard";
import { noLinks } from "./notify";
import { chatRefOf, doingText, hostLabel, liveOf, petKeyOf, recentRef, stateText } from "./shared/model";
import { answersOf, askShownOf, chatWhere, copyCut, HOLD_MS, PICTURE_TYPES, queuedReply, reviewPending, reviewSeen, sameAsk, stampFresher, textScale, type PaneChat, type PaneHostMessage, type PaneMessage } from "./shared/pane";
import type { Answers, AskShown, ChatRef, Decision, Group, PlanItem, RecentChat, Session, ViewState } from "./shared/types";
import { isDecision } from "./shared/types";
import { chatFont } from "./doc";
import { asPaste, localAncestors, type Terminals } from "./terminals";

// Talpy Chat's keys (keys.mjs): each a command (package.json binds its key while a chat tab has
// the focus), and what it tells the tab in front to do
export const CHAT_KEYS: Record<string, string> = {
  "talpyDen.chat.sendNow": "sendNow",
  "talpyDen.chat.sendWhenTurnEnds": "sendLater",
  "talpyDen.chat.sendInBackground": "sendBackground",
  "talpyDen.chat.clear": "clear",
  "talpyDen.chat.stop": "stop",
  "talpyDen.chat.reply1": "chip1",
  "talpyDen.chat.reply2": "chip2",
  "talpyDen.chat.reply3": "chip3",
  "talpyDen.chat.reply4": "chip4",
  "talpyDen.chat.allow": "allow",
  "talpyDen.chat.alwaysAllow": "always",
  "talpyDen.chat.deny": "deny",
  "talpyDen.chat.previousPrompt": "promptUp",
  "talpyDen.chat.nextPrompt": "promptDown",
  "talpyDen.chat.showChat": "tabChat",
  "talpyDen.chat.showSteps": "tabSteps",
  "talpyDen.chat.showReview": "tabReview",
  "talpyDen.chat.toggleTasks": "tasks",
  "talpyDen.chat.copyLastReply": "copyLast",
  "talpyDen.chat.openWindow": "openWindow",
  "talpyDen.chat.keys": "help",
};

export const ASKS_SOMETHING_ELSE = "It asks something else now"; // (pane.py --keys --expect says the same)
const TEXT_MAX = 100_000; // (as a queued task's prompt may be)
const TEXT_IN_ARGS = 32_000; // bytes of a message that go to pane.py as an argument
type DictationState = Extract<PaneHostMessage, { type: "dictation" }>["state"];
const LIMIT = 120;
const LIMIT_MAX = 2000;

// The chat's row now: a listed session, else one of its account's recent chats.
// One Claude moved to the background under a new id (its terminal closed: the
// status's "moved") is that one's, movedTo, unless a chat still runs under the old
export function findPaneRow(state: Pick<ViewState, "status" | "hosts">, host: string, chatId: string, follow = true): { session?: Session; recent?: RecentChat; movedTo?: string } {
  const where = host ? state.hosts.find((h) => h.name === host)?.result : state.status;
  for (const g of where?.groups ?? []) {
    const s = (g.sessions ?? []).find((x) => (x.chatId || x.sessionId) === chatId || x.sessionId === chatId);
    if (s && (!follow || s.pid != null || !where?.moved?.[chatId])) return { session: s };
  }
  const to = follow ? where?.moved?.[chatId] : undefined;
  if (to && to !== chatId) return { ...findPaneRow(state, host, to, false), movedTo: to };
  for (const g of where?.groups ?? []) {
    const c = [...(g.recent ?? []), ...(g.starred ?? [])].find((x) => x.sessionId === chatId);
    if (c) return { recent: c };
  }
  return {};
}

// A new chat Talpy Chat starts (New Chat… in a Talpy Chat tab), till its first message starts it
interface Fresh {
  profile: string; // its account's profile (pane.py --start)
  account: string;
  cwd: string;
  short: string;
  plan: { slug: string; profileDir: string; title: string } | null;
  task: string; // sent as its first message once the tab is ready
}

export class ChatPanes implements vscode.Disposable {
  private panes = new Map<string, Pane>(); // "<host>|<chat id>" -> its tab
  private answers = 0; // (answers given: each one's id, for its tab)
  private newChats = 0;

  constructor(
    private extensionUri: vscode.Uri,
    private backend: Backend,
    private dash: Dashboard,
    private actions: Actions,
    private terminals: Terminals,
    private log: vscode.LogOutputChannel,
  ) {
    // a turn that ends while its tab shows it: you're looking
    dash.lookingAt = (id) => [...this.panes.values()].some((p) => p.shows(id));
  }

  open(chat: ChatRef, tab: "chat" | "review" = "chat"): void {
    this.dash.opened(chat); // (looked at: off the focus view's Finished lines)
    const chatId = chat.chatId || chat.sessionId;
    // (by the id it had: its tab, if one has it under the new id Claude moved it to)
    const key = `${chat.host ?? ""}|${findPaneRow(this.dash.state(), chat.host ?? "", chatId).movedTo ?? chatId}`;
    const pane = this.panes.get(key);
    if (pane) return pane.reveal(tab);
    const created = new Pane(this, chat, tab);
    this.panes.set(key, created);
    created.onClosed(() => this.panes.forEach((p, k) => p === created && this.panes.delete(k)));
  }

  // A new chat in a tab of its own, for that account and folder, with nothing started yet: your first
  // message there starts it in the background (pane.py --start, with the permission hook for it
  // alone), a task at once; plan: one it carries out (its first message, with what you wrote)
  openNew(group: Group, folder: { path: string; short: string }, task = "", plan?: PlanItem): void {
    const id = `new-${Date.now()}-${++this.newChats}`;
    const chat: ChatRef = { key: id, sessionId: "", chatId: id, profileDir: group.chatProfile, name: `New chat in ${folder.short}`,
                            cwd: folder.path, kind: "chat", pid: null };
    const fresh: Fresh = { profile: group.chatProfile, account: group.title, cwd: folder.path, short: folder.short,
                           plan: plan ? { slug: plan.slug, profileDir: plan.profileDir, title: plan.title } : null,
                           task: task || (plan ? "Implement this plan." : "") };
    const created = new Pane(this, chat, "chat", fresh);
    this.panes.set(`|${id}`, created);
    created.onClosed(() => this.panes.forEach((p, k) => p === created && this.panes.delete(k)));
  }

  // A tab's chat Claude moved to the background under a new id goes on under that one (Pane.follow)
  moved(pane: Pane, from: string, to: string): void {
    if (this.panes.get(from) === pane) this.panes.delete(from);
    if (!this.panes.has(to)) this.panes.set(to, pane);
    // (a message on its way to it under the id it had: the next ones still wait for it)
    const chain = this.sending.get(from);
    if (chain && !this.sending.has(to)) this.sending.set(to, chain);
  }

  // An answer to what a waiting chat asks (its row, the tab, a notification),
  // to the prompt that was shown there (shown) and no other: a chat that asks
  // something else now isn't answered. Through the hook's request shown, or
  // with keys in its tmux pane, which pane.py presses only while the chat
  // still asks about that tool use (--expect); Claude's questions: decision
  // "answer" with the answers. changed: it asks something else now.
  async answer(chat: ChatRef, decision: Decision, shown: AskShown | null, note = "", answers?: Answers): Promise<{ ok: boolean; message: string; changed?: boolean }> {
    const host = chat.host ?? "";
    const { session } = findPaneRow(this.dash.state(), host, chat.chatId || chat.sessionId);
    const p = session?.state === "waiting" ? session.permission : null;
    if (!session || !p || (p.answer !== "hook" && p.answer !== "keys")) return { ok: false, message: "It isn't asking anything you can answer from here" };
    if (!shown || !sameAsk(shown, p)) {
      this.dash.setActionError(`Couldn't answer ${session.name}: ${ASKS_SOMETHING_ELSE}`);
      this.refresh(host);
      return { ok: false, message: ASKS_SOMETHING_ELSE, changed: true };
    }
    const given = decision === "answer" ? answersOf(answers) : null;
    if (decision === "answer" && !given) return { ok: false, message: "Choose your answers first" };
    // (the request shown; one that came for that same prompt after it was shown, else)
    const request = p.answer === "hook" ? (shown.request ?? p.request) : null;
    const toolUse = shown.toolUse ?? p.toolUse ?? null;
    const args = request
      ? ["--answer", request]
      : ["--keys", session.sessionId, ...(session.profileDir ? ["--profile", session.profileDir] : []), ...(toolUse ? ["--expect", toolUse] : [])];
    // (shown at once as yours in its tab, if it's open, till the conversation has it)
    const tab = this.panes.get(`${host}|${chat.chatId || chat.sessionId}`) ?? this.panes.get(`${host}|${session.chatId || session.sessionId}`);
    const id = ++this.answers;
    tab?.answering({ type: "answering", id, ask: p, decision, note, ...(given ? { answers: given } : {}) });
    const r = await this.backend.pane([...args, "--decision", decision, ...(note.trim() ? ["--note", note.trim()] : []),
                                        ...(given ? ["--answers", JSON.stringify(given)] : []),
                                        ...(host ? ["--host", host] : configDirArgs())], 60000)
      .catch((e: unknown) => ({ ok: false, message: e instanceof Error ? e.message : String(e) }) as Record<string, unknown>);
    tab?.answering({ type: "answered", id, ok: !!r.ok });
    const answer = { ok: !!r.ok, message: String(r.message ?? ""), ...(r.changed === true ? { changed: true } : {}) };
    if (!answer.ok) this.dash.setActionError(`Couldn't answer ${session.name}: ${answer.message}`);
    this.refresh(host);
    return answer;
  }

  // A reply from a notification: sent the way the chat takes one; a chat in a
  // terminal that takes no text opens in its tab with it, to choose there
  async reply(chat: ChatRef, text: string): Promise<{ ok: boolean; message: string }> {
    const answer = await this.send(chat, text, "auto", false);
    if (answer.ask) this.draft(chat, text);
    else if (!answer.ok) this.dash.setActionError(answer.message);
    else if (answer.message) this.dash.setActionInfo(answer.message);
    return answer;
  }

  // A message held a moment in a tab that closed before it went (sent while
  // Claude works, to be taken back): it goes when its moment is up all the
  // same, as if the tab were open; one that doesn't go is said, with its text
  sendHeld(chat: ChatRef, text: string, how: "auto" | "background" | "copy" | "enter", until: number): void {
    setTimeout(() => void this.send(chat, text, how, false).then((r) => {
      if (r.ask) return this.draft(chat, text);
      if (r.ok) return;
      this.dash.setActionError(`Couldn't send your reply to ${chat.name || "the chat"}: ${r.message}`);
      void vscode.window.showErrorMessage(noLinks(`Couldn't send your reply to ${chat.name || "the chat"}: ${text} — ${r.message}`));
    }), Math.max(0, until - Date.now())).unref?.();
  }

  // The chat's tab, open with text as its unsent reply
  draft(chat: ChatRef, text: string): void {
    this.open(chat, "chat");
    this.panes.get(`${chat.host ?? ""}|${chat.chatId || chat.sessionId}`)?.draft(text);
  }

  // Your message to a chat: typed into this window's terminal it runs in, or
  // as pane.py --send does (tmux, its Claude Code panel's input, the background).
  // how "enter" (Enter in the tab): auto, but a terminal that takes no text
  // gets the copy, so Claude there never quits on an Enter. One message to a
  // chat at a time (its tab, a notification's Reply…), in the order sent: one
  // sent while another is still on its way goes once that one has (never
  // dropped). went: it went into the chat itself (typed in, or on in the
  // background), not into VS Code's input or the clipboard.
  async send(chat: ChatRef, text: string, how: "auto" | "background" | "copy" | "enter", afterTurn: boolean): Promise<{ ok: boolean; message: string; ask?: boolean; went?: boolean }> {
    text = text.trim();
    if (!text) return { ok: false, message: "Write your message first" };
    if (text.length > TEXT_MAX) return { ok: false, message: "That message is too long" };
    const key = `${chat.host ?? ""}|${chat.chatId || chat.sessionId}`;
    const before = this.sending.get(key) ?? Promise.resolve();
    const now = before.then(async () => {
      try {
        return await this.sendNow(chat, text, how, afterTurn);
      } catch (e) {
        return { ok: false, message: `Couldn't send it: ${e instanceof Error ? e.message : String(e)}` };
      }
    });
    this.sending.set(key, now);
    try {
      return await now;
    } finally {
      if (this.sending.get(key) === now) this.sending.delete(key);
    }
  }

  private sending = new Map<string, Promise<unknown>>(); // "<host>|<chat id>": the last message on its way to it

  private async sendNow(chat: ChatRef, text: string, how: "auto" | "background" | "copy" | "enter", afterTurn: boolean): Promise<{ ok: boolean; message: string; ask?: boolean; went?: boolean }> {
    const host = chat.host ?? "";
    // (to where the chat is now: one Claude moved to the background meanwhile
    // goes on under its new id, also for a message that waited its turn)
    const { session, movedTo } = findPaneRow(this.dash.state(), host, chat.chatId || chat.sessionId);
    const chatId = movedTo ?? (chat.chatId || chat.sessionId);
    const copy = async (said: string) => {
      await vscode.env.clipboard.writeText(text);
      if (session) await this.actions.open(chatRefOf(session, host || undefined));
      return { ok: true, message: said };
    };
    if (!afterTurn && how === "copy") return copy("Your message is in the clipboard: paste it into the chat");
    // in one of this window's terminals: typed in, as a paste, then Enter
    const terminal = !afterTurn ? await this.windowTerminal(session, host) : undefined;
    if (terminal && session) {
      if (session.state === "waiting") return { ok: false, message: "It's asking you something: answer that first" };
      terminal.sendText(asPaste(text), false);
      await new Promise((r) => setTimeout(r, 300));
      terminal.sendText("\r", false);
      this.refresh(host);
      return { ok: true, message: "Sent (typed into its terminal)", went: true };
    }
    const sid = session?.sessionId ?? (movedTo ? "" : chat.sessionId);
    // (a long message goes in a file of its own, private to you, that pane.py
    // removes once read: one command-line argument holds 128 KiB at most; a
    // host's too, so it isn't in the process list while the host answers)
    const file = host || Buffer.byteLength(text) > TEXT_IN_ARGS ? path.join(cacheDir(), `text-${crypto.randomUUID()}.txt`) : "";
    // (enter goes as auto: the copy is VS Code's clipboard, also in a remote window)
    const args = ["--send", chatId, ...(file ? ["--text-file", file] : ["--text", text]), "--how", how === "enter" ? "auto" : how, ...(sid ? ["--session", sid] : []),
                  ...(chat.profileDir ? ["--profile", chat.profileDir] : []), ...(afterTurn ? ["--after-turn", "--name", chat.name || ""] : []),
                  ...(host ? ["--host", host] : configDirArgs())];
    let r: Record<string, any>;
    try {
      if (file) {
        fs.mkdirSync(cacheDir(), { recursive: true, mode: 0o700 });
        fs.writeFileSync(file, text, { mode: 0o600, flag: "wx" });
      }
      r = await this.backend.pane(args, 180000);
    } finally {
      if (file) fs.rmSync(file, { force: true });
    }
    if (r.ok && r.how === "ask" && how === "enter")
      return copy("Its terminal takes no text from outside, so your message is in the clipboard: paste it there");
    if (r.ok && r.how === "ask") return { ok: true, message: String(r.message ?? ""), ask: true };
    if (r.ok && r.how === "vscode" && typeof r.link === "string" && r.link.startsWith("vscode://anthropic.claude-code/open?")) {
      // (this computer's chat: in the VS Code window that runs it, raised first, not the one used last)
      if (host) await vscode.env.openExternal(vscode.Uri.parse(r.link));
      else {
        const opened = await this.backend.action("jump.py", ["--vscode-link", sid || chatId, r.link, ...configDirArgs()]);
        if (!opened.ok) return { ok: false, message: `Couldn't open the chat: ${opened.message}` };
      }
    }
    this.refresh(host);
    return { ok: !!r.ok, message: String(r.message ?? ""), went: !!r.ok && (r.how === "typed" || r.how === "background") };
  }

  // A command that needs Claude's own panel or dialog (shared/pane.ts commandRun "terminal"),
  // put where Claude's prompt is, for you to press Enter there (never sent): typed into one of
  // this window's terminals (and shown), or by pane.py --type-in into its tmux pane, its Claude
  // Code panel's input; else on the clipboard. Then its terminal comes up (as Open its window)
  async typeIn(chat: ChatRef, text: string): Promise<{ ok: boolean; message: string }> {
    const host = chat.host ?? "";
    const { session, movedTo } = findPaneRow(this.dash.state(), host, chat.chatId || chat.sessionId);
    const chatId = movedTo ?? (chat.chatId || chat.sessionId);
    const ref = session ? chatRefOf(session, host || undefined) : chat;
    const terminal = await this.windowTerminal(session, host);
    if (terminal && session && session.state !== "waiting") {
      terminal.sendText(asPaste(text), false);
      terminal.show();
      return { ok: true, message: "It's typed into its terminal: press Enter there" };
    }
    const sid = session?.sessionId ?? (movedTo ? "" : chat.sessionId);
    const r = await this.backend.pane(["--type-in", chatId, "--text", text, "--no-copy", ...(sid ? ["--session", sid] : []),
      ...(chat.profileDir ? ["--profile", chat.profileDir] : []), ...(host ? ["--host", host] : configDirArgs())], host ? 60000 : 20000);
    if (!r.ok) return { ok: false, message: String(r.message ?? "That didn't work") };
    if (r.how === "vscode" && typeof r.link === "string" && r.link.startsWith("vscode://anthropic.claude-code/open?")) {
      if (host) await vscode.env.openExternal(vscode.Uri.parse(r.link));
      else {
        const opened = await this.backend.action("jump.py", ["--vscode-link", sid || chatId, r.link, ...configDirArgs()]);
        if (!opened.ok) return { ok: false, message: `Couldn't open the chat: ${opened.message}` };
      }
      return { ok: true, message: String(r.message ?? "") };
    }
    if (r.how === "copy") await vscode.env.clipboard.writeText(text);   // (VS Code's clipboard: also in a remote window)
    await this.actions.open(ref, true);
    return { ok: true, message: r.how === "copy" ? `It's in the clipboard. ${String(r.message ?? "")}` : String(r.message ?? "") };
  }

  // /permissions (commandRun "page"): Talpy Den's Permissions tab (extension.ts sets it)
  openPermissions: () => Promise<void> = async () => undefined;

  // Stop on a chat's working line (shared/pane.ts stopOf): what Claude does
  // now stops and the chat stays. In one of this window's terminals Ctrl+C is
  // typed in, as Interrupt does; else pane.py --interrupt (Ctrl+C in its tmux
  // pane, Esc into a background chat through Claude's background service; an
  // SSH host's there)
  async interrupt(chat: ChatRef): Promise<{ ok: boolean; message: string }> {
    const host = chat.host ?? "";
    const { session } = findPaneRow(this.dash.state(), host, chat.chatId || chat.sessionId);
    if (!session || session.state !== "working") return { ok: false, message: "It isn't working any more, so there's nothing to stop" };
    const terminal = await this.windowTerminal(session, host);
    if (terminal) {
      terminal.sendText("\x03", false); // (Ctrl+C, as if pressed in it: Claude's terminal is raw, a key, not a signal)
      this.refresh(host);
      return { ok: true, message: "Interrupted (Ctrl+C in its terminal)" };
    }
    const chatId = session.chatId || session.sessionId;
    const r = await this.backend.pane(["--interrupt", chatId, ...(session.sessionId !== chatId ? ["--session", session.sessionId] : []),
      ...(session.profileDir ? ["--profile", session.profileDir] : []), ...(host ? ["--host", host] : configDirArgs())], host ? 60000 : 20000);
    this.refresh(host);
    return { ok: !!r.ok, message: String(r.message ?? "") };
  }

  // The terminal of this window a chat of this computer (or of the host this
  // window is on) runs in, if one does
  private async windowTerminal(session: Session | undefined, host: string): Promise<vscode.Terminal | undefined> {
    if (!session?.pid || session.entrypoint === "claude-vscode" || session.kind === "bg" || session.tmux) return undefined;
    if (host) return undefined; // (an SSH host's: only its pid is known, not its ancestors here)
    return this.terminals.find(localAncestors(session.pid), false);
  }

  refresh(host: string): void {
    void this.dash.refresh();
    if (host) void this.dash.pollHost(host);
  }

  // (for the panes)
  get ext() {
    return { uri: this.extensionUri, backend: this.backend, dash: this.dash, actions: this.actions, log: this.log, panes: this };
  }

  // A key's command (talpyDen.chat.*, bound only while a chat tab has the focus): to the tab in
  // front, whose page does what it says (keys.mjs's id); false: no chat tab is in front
  key(key: string): boolean {
    const pane = [...new Set(this.panes.values())].find((p) => p.active);
    if (!pane) return false;
    pane.key(key);
    return true;
  }

  async routeHere(session: Session | undefined, host: string): Promise<boolean> {
    return !!(await this.windowTerminal(session, host));
  }

  dispose(): void {
    for (const p of [...this.panes.values()]) p.dispose();
    this.panes.clear();
  }
}

// Talpy Den's folder of pictures (pasted ones, and those pasted into a chat
// in Claude's terminal: pane.py prompt_pictures); only its pictures show in a tab
function picturesDir(): string {
  return path.join(cacheDir(), "images");
}
function inPictures(file: string): boolean {
  return path.resolve(file).startsWith(picturesDir() + path.sep);
}

class Pane implements vscode.Disposable {
  private panel: vscode.WebviewPanel;
  private host: string;
  private chatId: string;
  private chat: ChatRef;
  private stamp = "";
  private limit = LIMIT;
  private loading = false;
  private loadAgain = false;
  private lastState: string | undefined; // (its state when the tab last heard)
  private timer: NodeJS.Timeout | undefined;
  private disposables: vscode.Disposable[] = [];
  private closed = new vscode.EventEmitter<void>();
  readonly onClosed = this.closed.event;
  private ready = false;
  private shown = false; // (the tab showed at its last view-state change)
  private pendingDraft = "";
  private held = new Map<number, { text: string; how: "auto" | "background" | "copy" | "enter"; until: number }>(); // (the page's, till they go: ChatPanes.sendHeld)
  private terminalHere = false;
  private starting: Promise<{ ok: boolean; message: string; went?: boolean }> | null = null; // (a new chat's first message, on its way)
  private startedAt = 0; // (it started: its transcript may not be there for a moment)

  constructor(
    private owner: ChatPanes,
    chat: ChatRef,
    tab: "chat" | "review",
    private fresh: Fresh | null = null,
  ) {
    this.chat = chat;
    this.host = chat.host ?? "";
    this.chatId = chat.chatId || chat.sessionId;
    const { uri } = owner.ext;
    this.panel = vscode.window.createWebviewPanel("talpyDen.chat", chat.name || this.chatId.slice(0, 8), vscode.ViewColumn.Active, {
      enableScripts: true,
      retainContextWhenHidden: true,
      // (and the pictures in your messages, shown small: Talpy Den's folder of them)
      localResourceRoots: [vscode.Uri.joinPath(uri, "dist"), vscode.Uri.file(picturesDir())],
    });
    this.panel.iconPath = vscode.Uri.joinPath(uri, "media", "talpy.svg");
    this.shown = this.panel.visible;
    this.panel.webview.html = this.html(tab);
    this.disposables.push(
      this.panel.webview.onDidReceiveMessage((m: unknown) =>
        void this.receive(m).catch((e) => this.owner.ext.log?.warn?.(`Talpy Chat's request failed: ${e instanceof Error ? e.message : String(e)}`))),
      // shown again: the conversation at once (nothing read it while hidden);
      // focus moving between editors changes nothing
      this.panel.onDidChangeViewState(() => {
        if (this.disposed || this.panel.visible === this.shown) return;
        this.shown = this.panel.visible;
        this.post({ type: "visible", visible: this.shown });
        // (the look's pace once the read has started the watcher again: 15 s, not 1.5)
        if (this.shown && this.ready) void this.load().finally(() => this.schedule());
        else this.schedule();
      }),
      this.panel.onDidDispose(() => this.dispose()),
      owner.ext.dash.onState(() => void this.pushChat()),
      // live mode: the chat did a step: what it does now, and the conversation at once
      owner.ext.dash.onLive((e) => {
        if (this.host || !this.chat.sessionId || !e.changed.includes(this.chat.sessionId)) return;
        void this.pushChat();
        if (!this.disposed && this.panel.visible) void this.load();
      }),
      vscode.workspace.onDidChangeConfiguration((e) => {
        if (e.affectsConfiguration("talpyDen.chatTextScale")) this.post({ type: "textSize", scale: Pane.textScale() });
        if (e.affectsConfiguration("talpyDen.chatFont") || e.affectsConfiguration("terminal.integrated.fontFamily")
            || e.affectsConfiguration("editor.fontFamily")) this.post({ type: "font", family: Pane.chatFont() });
        if (e.affectsConfiguration("talpyDen.diffSideBySide")) this.post({ type: "diffLayout", split: Pane.sideBySide() });
        if (e.affectsConfiguration("talpyDen.suggestReplies")) {
          this.post({ type: "suggest", on: Pane.suggests() });
          this.stamp = "";   // (read again, with or without how its turn ended)
          void this.load();
        }
        if (this.fresh && (e.affectsConfiguration("talpyDen.newChatModel") || e.affectsConfiguration("talpyDen.newChatEffort")
            || e.affectsConfiguration("talpyDen.newChatMode"))) void this.pushChat();   // (its ⚙ line)
      }),
    );
  }

  private static sideBySide(): boolean {
    return vscode.workspace.getConfiguration("talpyDen").get("diffSideBySide") !== false;
  }

  // Suggest replies (talpyDen.suggestReplies): off, nothing is read or worked out for them
  static suggests(): boolean {
    return vscode.workspace.getConfiguration("talpyDen").get("suggestReplies") !== false;
  }

  // The conversation's font (talpyDen.chatFont, doc.ts chatFont)
  static chatFont(): string {
    return chatFont();
  }

  private static textScale(): number {
    return textScale(vscode.workspace.getConfiguration("talpyDen").get("chatTextScale"));
  }

  reveal(tab: "chat" | "review"): void {
    if (this.disposed) return;
    this.panel.reveal();
    // (on tab:review the page shows its Review tab and asks for the review, once)
    this.post({ type: "result", kind: "tab:" + tab, ok: true, message: "" });
  }

  // In front, with the focus (its keys go to it)
  get active(): boolean {
    return !this.disposed && this.panel.active;
  }
  key(key: string): void {
    if (this.ready) this.post({ type: "key", key });
  }

  // It's on screen with the chat id (petKeyOf) names
  shows(id: string): boolean {
    return !this.disposed && this.panel.visible && petKeyOf(this.chat, this.host || undefined) === id;
  }

  draft(text: string): void {
    if (this.ready) this.post({ type: "result", kind: "draft", ok: true, message: text, ask: true });
    else this.pendingDraft = text;
  }

  // An answer to what the chat asks, on its way or gone (ChatPanes.answer): shown at once
  answering(m: Extract<PaneHostMessage, { type: "answering" | "answered" }>): void {
    if (this.ready) this.post(m);
  }

  // (nothing once the tab is closed: its panel's webview, title and visible throw then)
  private post(m: PaneHostMessage): void {
    if (this.disposed) return;
    void this.panel.webview.postMessage(m);
  }

  // The chat as the tab shows it, from the extension's state now
  private async pushChat(): Promise<void> {
    if (this.disposed) return;
    const state = this.owner.ext.dash.state();
    const { session, recent, movedTo } = findPaneRow(state, this.host, this.chatId);
    if (session) this.chat = chatRefOf(session, this.host || undefined);
    else if (recent) this.chat = recentRef(recent, this.host || undefined);
    if (movedTo) this.follow(movedTo);
    this.terminalHere = session ? await this.owner.routeHere(session, this.host) : false;
    if (this.disposed) return; // (closed meanwhile)
    const item = session ?? (recent ? { ...recent, chatId: recent.sessionId, state: "done" as const } : undefined);
    const queued = queuedReply(state.status, this.chatId, this.host || undefined);
    // (a new chat: till it's listed, "Starting…" once your first message went)
    const starting = !!this.starting || (!!this.startedAt && !session && !recent);
    const chat: PaneChat = {
      host: this.host,
      chatId: this.chatId,
      sessionId: session?.sessionId ?? this.chat.sessionId,
      profileDir: session?.profileDir ?? recent?.profileDir ?? this.chat.profileDir,
      name: session?.name ?? recent?.name ?? this.chat.name,
      cwd: session?.cwd ?? recent?.cwd ?? this.chat.cwd ?? "",
      state: session?.state ?? "done",
      stateText: session ? stateText(session, state.now) : starting ? "starting" : this.fresh ? "new" : "not running",
      route: this.terminalHere ? "vscodeTerminal" : (session?.reply ?? "background"),
      busy: session?.state === "working" || session?.state === "waiting",
      atWork: session?.state === "working" && session.reason !== "background shell",
      bgStop: !!session?.bgStop,
      activity: session ? doingText(session, this.host ? null : liveOf(session, state.live)) : "",
      permission: session?.state === "waiting" ? (session.permission ?? null) : null,
      changes: (session?.changes ?? recent?.changes)?.count ?? 0,
      reviewPending: item ? reviewPending(item, state.status, this.host || undefined) : false,
      reviewed: item ? reviewSeen(item, state.status, this.host || undefined) : true,
      review: session?.review ?? recent?.review ?? null,
      queued: queued ? { id: queued.id, prompt: queued.prompt, error: queued.error } : null,
      canMove: !!session && this.owner.ext.actions.canMoveToClaudeCode(this.chat),
      where: starting ? "background" : this.fresh ? "new" : chatWhere(session, this.terminalHere),
      terminalApp: session?.terminalApp ?? "",
      attached: session?.kind === "bg" ? (session.attached ?? null) : null,
      profile: session?.profile ?? "",
      shared: session?.shared ?? null,
      mode: session?.peek?.mode ?? "",
      plan: session?.plan ? { title: session.plan.title } : null,
      agents: session?.agents ?? null,
      tasks: session?.tasks && session.tasks.total > 0 ? session.tasks : null,
      fresh: this.fresh ? { account: this.fresh.account, folder: this.fresh.short, plan: this.fresh.plan?.title ?? "",
                            model: settings.newChatModel(), effort: settings.newChatEffort(), mode: settings.newChatMode() } : null,
      starting,
    };
    this.panel.title = chat.name || this.chatId.slice(0, 8);
    if (this.ready) this.post({ type: "chat", chat });
    // its turn began or ended, it asks something: the conversation now
    if (this.lastState !== undefined && chat.state !== this.lastState && this.panel.visible) void this.load();
    this.lastState = chat.state;
  }

  // Claude moved the chat to the background under a new id (its terminal
  // closed): the same conversation goes on there, so the tab goes on with it,
  // its new transcript read now (a read for the id it had is left out)
  private follow(to: string): void {
    this.owner.moved(this, `${this.host}|${this.chatId}`, `${this.host}|${to}`);
    this.chatId = to;
    if ((this.chat.chatId || this.chat.sessionId) !== to) this.chat = { ...this.chat, chatId: to, sessionId: to }; // (its row may come a check later)
    this.stamp = "";
    void this.load();
  }

  // The conversation, again while the tab shows (often for this computer's
  // chats; with live mode it's read at each step, so this is a fallback)
  private schedule(): void {
    if (this.timer) clearTimeout(this.timer);
    this.timer = undefined;
    if (this.disposed || !this.panel.visible) return; // (closed: the reading stops)
    // (with the watcher, only for what it can't see: a moment it wasn't running; an SSH host's chat
    // every second just after you sent it something, till that shows: chaseUntil)
    const every = this.host ? (Date.now() < this.chaseUntil ? 1000 : 5000) : this.watchFailures === 0 && this.watching ? 15000 : this.owner.ext.dash.liveHook ? 5000 : 1500;
    this.timer = setTimeout(() => void this.load().finally(() => this.schedule()), every);
  }

  private chaseUntil = 0;
  private async load(): Promise<void> {
    if (this.disposed) return;
    if (this.fresh) {   // (nothing to read yet: it shows empty, ready for your first message)
      this.post({ type: "conversation", answer: { ok: true, items: [], stamp: "", more: false } as never });
      return;
    }
    if (this.loading) {
      this.loadAgain = true; // (something changed while it was read: read it again then)
      return;
    }
    this.loading = true;
    const chatId = this.chatId;
    try {
      const r = await this.owner.ext.backend.pane([
        "--conversation", chatId, "--limit", String(this.limit), ...(this.stamp ? ["--if-changed", this.stamp] : []),
        ...(Pane.suggests() ? ["--suggest"] : []),
        ...(this.chat.profileDir ? ["--profile", this.chat.profileDir] : []), ...(this.host ? ["--host", this.host] : configDirArgs()),
      ], this.host ? 60000 : 30000);
      if (this.disposed) return;
      if (r.ok && r.unchanged) return void this.watch(); // (shown again, nothing new: it waits on it again)
      // (a chat just started has no transcript for a moment: your message shows meanwhile)
      if (!r.ok && r.missing && this.startedAt && Date.now() - this.startedAt < 60000) return;
      if (chatId !== this.chatId) {
        this.loadAgain = true; // (Claude moved it meanwhile: its new id's, follow)
        return;
      }
      if (this.take(r) && r.ok) this.chaseUntil = 0; // (something new: your message, or what Claude writes)
    } finally {
      this.loading = false;
      if (this.loadAgain) {
        this.loadAgain = false;
        if (!this.disposed) void this.load();
      }
    }
    void this.watch();
  }

  // A read's answer, or the watcher's (not one read before what's shown: stampFresher)
  private take(r: Record<string, any>): boolean {
    if (r.ok && !stampFresher(r.stamp, this.stamp, this.limit)) return false;
    // (your pictures, small: those in Talpy Den's folder of them, by the address the tab can load; not an SSH host's)
    if (r.ok && Array.isArray(r.items) && !this.host)
      for (const it of r.items as Record<string, any>[])
        if (Array.isArray(it.pictures))
          it.thumbs = it.pictures.filter((f: unknown): f is string => typeof f === "string" && inPictures(f))
            .map((f: string) => ({ path: f, src: this.panel.webview.asWebviewUri(vscode.Uri.file(f)).toString() }));
    if (r.ok && typeof r.stamp === "string") this.stamp = r.stamp;
    // (at the most a tab shows: no Show earlier, it says so instead)
    const capped = r.ok && !!r.more && this.limit >= LIMIT_MAX;
    this.post({ type: "conversation", answer: (r.ok ? { ...r, more: !!r.more && !capped, capped } : r) as never });
    return true;
  }

  // The watcher: a chat of this computer is read the moment its transcript
  // changes (pane.py --conversation --wait: it waits for that, up to 50 s,
  // then again), so your message and what Claude writes show at once, not at
  // the next look. Not for an SSH host's (a look every 5 s); three failures
  // in a row: looks only.
  private watching = false;
  private watchFailures = 0;
  private async watch(): Promise<void> {
    if (this.watching || this.host || this.disposed || !this.stamp || this.watchFailures >= 3) return;
    this.watching = true;
    try {
      // (a pause that doesn't keep VS Code's extension host, or a test, from ending)
      const pause = (ms: number) => new Promise<void>((done) => setTimeout(done, ms).unref?.());
      while (!this.disposed && this.panel.visible && this.stamp && this.watchFailures < 3) {
        const limit = this.limit;
        const stamp = this.stamp;
        const chatId = this.chatId;
        const asked = Date.now();
        const r = await this.owner.ext.backend.pane([
          "--conversation", chatId, "--limit", String(limit), "--if-changed", stamp, "--wait", "50", ...(Pane.suggests() ? ["--suggest"] : []),
          ...(this.chat.profileDir ? ["--profile", this.chat.profileDir] : []), ...configDirArgs(),
        ], 70000);
        if (this.disposed) return;
        if (chatId !== this.chatId) continue; // (Claude moved it meanwhile: its new id's is waited on now)
        if (!r.ok) {
          this.watchFailures += 1;
          await pause(5000);
          continue;
        }
        this.watchFailures = 0;
        const changed = !r.unchanged && typeof r.stamp === "string" && r.stamp !== stamp;
        // (one read for another length, Show earlier meanwhile: read again)
        if (changed && !this.take(r)) void this.load();
        // (an answer at once is paced: a change that came meanwhile, the next ask a moment later; nothing
        // new, a pane.py that doesn't wait, an old one on the way: in 5 s. Never again and again)
        const spent = Date.now() - asked;
        if (spent < 250) await pause(changed ? 250 - spent : 5000);
      }
    } finally {
      this.watching = false;
    }
  }

  // A new chat's first message: it starts in the background (pane.py --start: on its account, in
  // its folder, with the new-chat model, effort and mode, and the permission hook for it alone),
  // and the tab goes on with it under its id. One sent while that's on its way goes to it after.
  private async start(text: string): Promise<{ ok: boolean; message: string; went?: boolean }> {
    if (this.starting) {
      const first = await this.starting;
      if (!first.ok || this.fresh) return { ok: false, message: "The chat didn't start: send it again once it has" };
      return this.owner.send(this.chat, text, "auto", false);
    }
    const f = this.fresh;
    if (!f) return this.owner.send(this.chat, text, "auto", false);
    this.starting = (async () => {
      const file = Buffer.byteLength(text) > TEXT_IN_ARGS ? path.join(cacheDir(), `text-${crypto.randomUUID()}.txt`) : "";
      let r: Record<string, any>;
      try {
        if (file) {
          fs.mkdirSync(cacheDir(), { recursive: true, mode: 0o700 });
          fs.writeFileSync(file, text, { mode: 0o600, flag: "wx" });
        }
        r = await this.owner.ext.backend.pane([
          "--start", f.profile, "--cwd", f.cwd, ...(file ? ["--text-file", file] : ["--text", text]), ...chatOptionArgs(),
          ...(f.plan ? ["--plan", f.plan.slug, "--plan-profile", f.plan.profileDir] : []), ...configDirArgs(),
        ], 180000);
      } catch (e) {
        r = { ok: false, message: e instanceof Error ? e.message : String(e) };
      } finally {
        if (file) fs.rmSync(file, { force: true });
      }
      if (this.disposed || !r.ok || typeof r.chat !== "string") return { ok: false, message: String(r.message ?? "It didn't start") };
      const from = this.chatId;
      this.fresh = null;
      this.startedAt = Date.now();
      this.owner.moved(this, `|${from}`, `|${r.chat}`);
      this.chatId = r.chat;
      this.chat = { ...this.chat, key: r.chat, chatId: r.chat, sessionId: r.chat, profileDir: typeof r.profileDir === "string" ? r.profileDir : this.chat.profileDir };
      this.stamp = "";
      this.owner.refresh("");
      return { ok: true, message: "", went: true };
    })();
    void this.pushChat();   // (Starting…)
    try {
      return await this.starting;
    } finally {
      this.starting = null;
      void this.pushChat();
      void this.load();
    }
  }

  private async loadReview(): Promise<void> {
    const r = await this.owner.ext.backend.pane([
      "--review", this.chatId, ...(this.chat.profileDir ? ["--profile", this.chat.profileDir] : []),
      ...(this.host ? ["--host", this.host] : configDirArgs()),
    ], this.host ? 90000 : 60000);
    this.post({ type: "review", answer: r.ok ? (r as never) : null, error: r.ok ? "" : String(r.message ?? "") });
  }

  private result(kind: string, r: { ok: boolean; message: string; ask?: boolean; went?: boolean }, id?: number): void {
    this.post({ type: "result", kind, ok: r.ok, message: r.message, ...(r.ask ? { ask: true } : {}), ...(r.went ? { went: true } : {}),
                ...(typeof id === "number" ? { id } : {}) });
  }

  private async receive(raw: unknown): Promise<void> {
    if (!raw || typeof raw !== "object") return;
    const m = raw as PaneMessage;
    const { backend, actions } = this.owner.ext;
    const where = this.host ? ["--host", this.host] : configDirArgs();
    const profile = this.chat.profileDir ? ["--profile", this.chat.profileDir] : [];
    switch (m.type) {
      case "ready":
        this.ready = true;
        await this.pushChat();
        await this.load();
        this.schedule();
        if (this.pendingDraft) {
          this.draft(this.pendingDraft);
          this.pendingDraft = "";
        }
        // (a new chat's task: its first message, shown as sent at once, as one you typed)
        if (this.fresh?.task) {
          this.post({ type: "startWith", text: this.fresh.task });
          this.fresh.task = "";
        }
        break;
      case "chatOptions":
        if ([m.model, m.effort, m.mode].every((v) => typeof v === "string")) await setChatOptions(m.model, m.effort, m.mode);
        break;
      case "more":
        this.limit = Math.min(LIMIT_MAX, this.limit * 2);
        this.stamp = "";
        await this.load();
        break;
      case "hold":
        if (typeof m.id === "number" && typeof m.text === "string" && ["auto", "background", "enter"].includes(m.how))
          this.held.set(m.id, { text: m.text, how: m.how, until: Date.now() + HOLD_MS });
        break;
      case "unhold":
        this.held.delete(m.id);
        break;
      case "send": {
        if (typeof m.id === "number") this.held.delete(m.id); // (it goes now: from the tab)
        if (typeof m.text !== "string" || !["auto", "background", "copy", "enter"].includes(m.how)) break;
        // (a new chat's first message starts it; one sent meanwhile waits for that, then goes to it)
        const r = this.fresh || this.starting ? await this.start(m.text) : await this.owner.send(this.chat, m.text, m.how, m.afterTurn === true);
        this.result(m.afterTurn ? "later" : "send", r, typeof m.id === "number" ? m.id : undefined);
        if (this.host && r.went) this.chaseUntil = Date.now() + 10000; // (as Plasma: read every second for 10 s, till it shows)
        await this.load();   // (the watcher has it already, as it's written; an SSH host's chat now)
        if (this.chaseUntil) this.schedule();
        break;
      }
      case "unqueue": {
        const q = queuedReply(this.owner.ext.dash.state().status, this.chatId, this.host || undefined);
        if (q) await actions.unqueue(q.id);
        break;
      }
      case "answer":
        if (isDecision(m.decision))
          this.result("answer", await this.owner.answer(this.chat, m.decision, askShownOf(m.shown), typeof m.note === "string" ? m.note : "",
                                                        answersOf(m.answers) ?? undefined));
        break;
      case "review":
        await this.loadReview();
        break;
      case "diff":
        if (typeof m.path === "string" && !this.host) await this.diff(m.path);
        break;
      case "undo": {
        if (typeof m.path !== "string") break;
        const r = await backend.pane(["--undo", this.chatId, ...(m.path !== "*" ? ["--file", m.path] : []), ...profile, ...where]);
        this.result("undo", { ok: !!r.ok, message: String(r.message ?? "") });
        await this.loadReview();
        this.owner.refresh(this.host);
        break;
      }
      case "commit": {
        if (typeof m.message !== "string" || !m.message.trim()) break;
        const r = await backend.pane(["--commit", this.chatId, "--message", m.message, ...profile, ...where], 180000);
        this.result("commit", { ok: !!r.ok, message: String(r.message ?? "") });
        await this.loadReview();
        break;
      }
      case "reviewed": {
        // (kept on this computer, for a host's chat too)
        const r = await backend.pane(["--reviewed", this.chatId, ...(m.on ? [] : ["--off"]), ...(this.host ? ["--host", this.host] : [])]);
        this.result("reviewed", { ok: !!r.ok, message: String(r.message ?? "") });
        this.owner.refresh(this.host);
        break;
      }
      case "openPlan": {
        const { session } = findPaneRow(this.owner.ext.dash.state(), this.host, this.chatId);
        if (session?.plan) void this.owner.ext.actions.openPlan({ ...session.plan, profileDir: this.chat.profileDir }, this.host || undefined, false);
        break;
      }
      case "openAgentRun":
        if (typeof m.agentId === "string" && AGENT_ID.test(m.agentId)) await actions.openAgentRun(this.chat, m.agentId);
        break;
      case "openWindow":
        // (a background chat's: a terminal on it, claude attach, also where its window is this tab)
        if (!this.fresh) await actions.open(this.chat, true);
        break;
      case "stop":
        if (!this.fresh) this.result("stop", await this.owner.interrupt(this.chat));
        break;
      case "moveToClaudeCode":
        await actions.moveToClaudeCode(this.chat);
        break;
      case "openPicture":
        if (typeof m.path === "string" && !this.host && inPictures(m.path))
          await vscode.commands.executeCommand("vscode.open", vscode.Uri.file(m.path));
        break;
      case "copy":
        // (a code block's Copy: its button says Copied, so nothing under the conversation)
        if (typeof m.text !== "string") break;
        try {
          await vscode.env.clipboard.writeText(m.text);
        } catch (e) {
          this.result("copy", { ok: false, message: `Couldn't copy it: ${(e as Error).message}` });
        }
        break;
      case "copyItem": {
        // all of it: a text shown cut is read whole from the transcript first (pane.py --reply-text);
        // Copied is said once it's on the clipboard
        if (typeof m.text !== "string" || typeof m.key !== "string" || typeof m.id !== "number") break;
        let text = m.text;
        if (copyCut(text) && !this.fresh) {
          const r = await backend.pane(["--reply-text", this.chatId, "--key", m.key, ...profile, ...where], this.host ? 30000 : 15000);
          if (!r.ok || typeof r.text !== "string") {
            this.post({ type: "copied", id: m.id, ok: false, message: `Couldn't copy all of it: ${String(r.message ?? "it couldn't be read")}` });
            break;
          }
          text = r.text;
        }
        try {
          await vscode.env.clipboard.writeText(text);
          this.post({ type: "copied", id: m.id, ok: true, message: "" });
        } catch (e) {
          this.post({ type: "copied", id: m.id, ok: false, message: `Couldn't copy it: ${(e as Error).message}` });
        }
        break;
      }
      case "picture": {
        // saved where the widget keeps pasted pictures; an SSH host's chat gets a copy there
        // (the tab asked you first)
        if (typeof m.id !== "string" || typeof m.data !== "string" || !PICTURE_TYPES.includes(m.mime)) {
          this.post({ type: "picture", id: String(m.id ?? ""), path: "", error: "Claude takes PNG, JPEG, WebP and GIF pictures" });
          break;
        }
        const saved = await backend.saveImage(m.mime, m.data);
        const there = saved.path && this.host ? await backend.putImage(this.host, saved.path) : saved;
        this.post({ type: "picture", id: m.id, path: there.path ?? "",
                    error: there.path ? "" : this.host && saved.path ? `Couldn't copy the picture to ${hostLabel(this.host)}: ${there.message}` : there.message });
        break;
      }
      case "screenshot":
      case "attach": {
        // a picture goes in as a pasted one (an SSH host's chat gets a copy there,
        // as you asked for it on its tab); another file is named, this computer's chats only
        if (typeof m.id !== "string" || (m.type === "attach" && typeof m.path !== "string")) break;
        const got = m.type === "screenshot" ? await backend.screenshot() : await backend.attach(m.path);
        if (!got.path) {
          if (got.message !== "No screenshot taken") this.post({ type: "picture", id: m.id, path: "", error: got.message });
          else this.post({ type: "picture", id: m.id, path: "", error: "" });
          break;
        }
        if (m.type === "attach" && "picture" in got && got.picture === false) {
          if (this.host) this.post({ type: "picture", id: m.id, path: "", error: `Only pictures go to ${hostLabel(this.host)}'s chat (copied there): that file is on this computer` });
          else this.post({ type: "file", id: m.id, path: got.path });
          break;
        }
        const there = this.host ? await backend.putImage(this.host, got.path) : got;
        this.post({ type: "picture", id: m.id, path: there.path ?? "",
                    error: there.path ? "" : `Couldn't copy the picture to ${hostLabel(this.host)}: ${there.message}` });
        break;
      }
      case "dictate":
        await this.dictate(m.action);
        break;
      case "complete": {
        // (a new chat's: its folder's, and your prompts there)
        const r = await backend.pane([...(this.fresh ? ["--complete", "-", "--cwd", this.fresh.cwd] : ["--complete", this.chatId]),
          ...(this.chat.profileDir ? ["--profile", this.chat.profileDir] : []),
          ...(this.host ? ["--host", this.host] : configDirArgs())], this.host ? 60000 : 20000);
        // (null: they couldn't be read: a command waiting for them goes as a message)
        this.post({ type: "offers", offers: r.ok ? { commands: Array.isArray(r.commands) ? r.commands : [],
          files: Array.isArray(r.files) ? r.files : [], history: Array.isArray(r.history) ? r.history : [],
          typed: r.typed && typeof r.typed === "object" ? r.typed : {} } : null });
        break;
      }
      case "typeIn":
        if (typeof m.text === "string" && m.text.trim() && !this.fresh) this.result("typein", await this.owner.typeIn(this.chat, m.text.trim()));
        break;
      case "openPermissions":
        await this.owner.openPermissions();
        break;
      case "replies": {
        // your usual replies, from the chats on its account (a first read can take some seconds: the tab doesn't wait)
        if (!Pane.suggests()) break;
        const r = await backend.pane([...(this.fresh ? ["--replies", "-", "--cwd", this.fresh.cwd] : ["--replies", this.chatId]),
          ...(this.chat.profileDir ? ["--profile", this.chat.profileDir] : []), ...where], this.host ? 90000 : 60000);
        if (r.ok) this.post({ type: "replies", replies: { chips: r.chips && typeof r.chips === "object" ? r.chips : {},
                                                          ranked: Array.isArray(r.ranked) ? r.ranked : [] } });
        break;
      }
      case "hideReply":
        if (typeof m.text === "string" && m.text.trim()) await backend.pane(["--hide-reply", m.text, ...where]);
        break;
      case "textSize":
        if (typeof m.scale === "number" && Number.isFinite(m.scale))
          await vscode.workspace.getConfiguration("talpyDen").update("chatTextScale", textScale(m.scale), vscode.ConfigurationTarget.Global);
        break;
      case "diffLayout":
        await vscode.workspace.getConfiguration("talpyDen").update("diffSideBySide", m.split === true, vscode.ConfigurationTarget.Global);
        break;
      case "pickFiles": {
        // + : VS Code's own file dialog, in the chat's folder; an SSH host's chat takes pictures
        // (an SSH host's chat: this computer's files, which go there, also in a window connected to it)
        const folder = !this.host && this.chat.cwd ? vscode.Uri.file(this.chat.cwd) : this.host ? vscode.Uri.file(os.homedir()) : undefined;
        const picked = await vscode.window.showOpenDialog({
          canSelectMany: true, openLabel: "Attach", defaultUri: folder, title: "Attach to your reply",
          ...(this.host ? { filters: { Pictures: ["png", "jpg", "jpeg", "webp", "gif"] } } : {}),
        });
        this.post({ type: "picked", paths: (picked ?? []).filter((u) => u.scheme === "file").map((u) => u.fsPath) });
        break;
      }
    }
  }

  // The microphone: record, then whisper (whisper.cpp, or the faster-whisper dictate.py sets up)
  // writes it down on this computer (Talpy Den runs on your side, also in a Remote window); not in a
  // browser, which runs no Python
  private recording = ""; // the recording's id while it records
  // Where dictating is: "starting" (--status, --start on their way: no second
  // recorder meanwhile), "recording", "writing" (--stop), "model", "setup"
  private dictation: DictationState = "";
  private cancelStart = false; // cancelled (or the tab closed) while it started: stopped once it has
  private async dictate(action: "toggle" | "cancel" | "getModel" | "setup"): Promise<void> {
    const { backend } = this.owner.ext;
    const tell = (m: Omit<Extract<PaneHostMessage, { type: "dictation" }>, "type">) => this.post({ type: "dictation", ...m });
    if (vscode.env.uiKind === vscode.UIKind.Web) {
      tell({ state: "", message: "Dictating works in VS Code on your computer, not in a browser", ok: false });
      return;
    }
    if (action === "cancel") {
      if (this.dictation === "starting") {
        this.cancelStart = true; // (the start sees it)
        return;
      }
      const id = this.recording;
      this.recording = "";
      if (this.dictation === "recording") this.dictation = "";
      if (id) await backend.dictate(["--cancel", id]);
      tell({ state: this.dictation });
      return;
    }
    // a step still on its way (a click the page sent twice, say): the page hears where it is
    if (this.dictation !== "" && !(action === "toggle" && this.dictation === "recording")) {
      tell({ state: this.dictation });
      return;
    }
    if (action === "getModel" || action === "setup") {
      this.dictation = action === "getModel" ? "model" : "setup";
      tell({ state: this.dictation });
      const r = action === "getModel" ? await backend.dictate(["--get-model", "base"], 900000) : await backend.dictate(["--setup"], 3600000);
      this.dictation = "";
      tell({ state: "", message: String(r.message ?? ""), ok: !!r.ok });
    } else if (this.dictation === "recording") {
      const id = this.recording;
      this.recording = "";
      this.dictation = "writing";
      tell({ state: "writing" });
      const language = vscode.workspace.getConfiguration("talpyDen").get<string>("dictateLanguage") || "auto";
      const r = await backend.dictate(["--stop", id, "--language", language], 600000);
      this.dictation = "";
      tell({ state: "", text: r.ok ? String(r.text ?? "") : "", message: r.ok ? "" : String(r.message ?? "") });
    } else {
      this.dictation = "starting";
      this.cancelStart = false;
      tell({ state: "starting" });
      const id = `r${Date.now()}`;
      let started = false;
      try {
        const st = await backend.dictate(["--status"]);
        if (this.disposed || this.cancelStart) return tell({ state: "" });
        if (!st.ok) {
          if (st.recorder && st.canSetup) tell({ state: "", offerSetup: true, setupMb: Number(st.setupMb) || 612 });
          else if (st.recorder && st.tool && !st.model) tell({ state: "", offerModel: true, engine: String(st.engine ?? "whisper") });
          else tell({ state: "", message: `To dictate, install ${(Array.isArray(st.missing) ? st.missing : []).join(" and ")}.` });
          return;
        }
        const r = await backend.dictate(["--start", id]);
        if (r.ok && (this.disposed || this.cancelStart)) {
          // closed (or cancelled) while it started: it stops now, and its recording is deleted
          await backend.dictate(["--cancel", id]);
          return tell({ state: "" });
        }
        if (!r.ok) return tell({ state: "", message: String(r.message ?? "") });
        started = true;
        this.recording = id;
        tell({ state: "recording" });
      } finally {
        this.dictation = started ? "recording" : "";
        this.cancelStart = false;
      }
    }
  }

  // One file's change, in VS Code's diff editor (this computer's chats)
  private async diff(file: string): Promise<void> {
    const { backend } = this.owner.ext;
    const answer = await backend.changes(this.chatId, this.chat.profileDir, false, configDirArgs());
    const item = answer.comparison?.items.find((i) => i.path === file);
    if (!answer.comparison || !item) {
      this.result("diff", { ok: false, message: answer.message || "No earlier version of that file to compare with" });
      return;
    }
    const error = await openComparison({ ...answer.comparison, title: `${answer.comparison.title}: ${item.label}`, items: [item] });
    if (error) this.result("diff", { ok: false, message: error });
  }

  private html(tab: "chat" | "review"): string {
    const webview = this.panel.webview;
    const { uri } = this.owner.ext;
    const nonce = crypto.randomBytes(16).toString("base64");
    const asset = (...p: string[]) => webview.asWebviewUri(vscode.Uri.joinPath(uri, ...p)).toString();
    const config = JSON.stringify({ tab, local: !this.host, scale: Pane.textScale(), split: Pane.sideBySide(), font: Pane.chatFont(),
                                    suggest: Pane.suggests() });
    const csp = [
      "default-src 'none'",
      "base-uri 'none'",
      "form-action 'none'",
      `img-src ${webview.cspSource} data:`,
      `style-src ${webview.cspSource} 'unsafe-inline'`,
      `font-src ${webview.cspSource}`,
      `script-src 'nonce-${nonce}'`,
    ].join("; ");
    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="${csp}">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="stylesheet" href="${asset("dist", "webview-style.css")}">
<title>Talpy Chat</title>
</head>
<body class="chat-page">
<script nonce="${nonce}">window.CLAUDE_CHAT = ${config.replace(/</g, "\\u003c")};</script>
<script nonce="${nonce}" src="${asset("dist", "chat.js")}"></script>
</body>
</html>`;
  }

  private disposed = false;

  dispose(): void {
    if (this.disposed) return; // (closing the panel calls this again)
    this.disposed = true;
    // (the tab closed while it listened; one still starting is stopped once it has: dictate sees disposed)
    if (this.recording) void this.owner.ext.backend.dictate(["--cancel", this.recording]);
    this.recording = "";
    // (a message it held a moment still goes, when its moment is up)
    for (const h of this.held.values()) this.owner.sendHeld(this.chat, h.text, h.how, h.until);
    this.held.clear();
    if (this.timer) clearTimeout(this.timer);
    this.timer = undefined;
    for (const d of this.disposables) d.dispose();
    this.disposables = [];
    this.closed.fire();
    this.closed.dispose();
    this.panel.dispose();
  }
}
