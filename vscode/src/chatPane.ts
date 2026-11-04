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
import { cacheDir, configDirArgs } from "./config";
import type { Dashboard } from "./dashboard";
import { chatRefOf, doingText, liveOf, petKeyOf, recentRef, stateText } from "./shared/model";
import { answersOf, askShownOf, chatWhere, PICTURE_TYPES, queuedReply, reviewPending, reviewSeen, sameAsk, stampFresher, textScale, type PaneChat, type PaneHostMessage, type PaneMessage } from "./shared/pane";
import type { Answers, AskShown, ChatRef, Decision, RecentChat, Session, ViewState } from "./shared/types";
import { isDecision } from "./shared/types";
import { asPaste, localAncestors, type Terminals } from "./terminals";

export const ASKS_SOMETHING_ELSE = "It asks something else now"; // (pane.py --keys --expect says the same)
const TEXT_MAX = 100_000; // (as a queued task's prompt may be)
const TEXT_IN_ARGS = 32_000; // bytes of a message that go to pane.py as an argument
type DictationState = Extract<PaneHostMessage, { type: "dictation" }>["state"];
const LIMIT = 120;
const LIMIT_MAX = 2000;

// The chat's row now: a listed session, else one of its account's recent chats
export function findPaneRow(state: Pick<ViewState, "status" | "hosts">, host: string, chatId: string): { session?: Session; recent?: RecentChat } {
  const where = host ? state.hosts.find((h) => h.name === host)?.result : state.status;
  for (const g of where?.groups ?? []) {
    const s = (g.sessions ?? []).find((x) => (x.chatId || x.sessionId) === chatId || x.sessionId === chatId);
    if (s) return { session: s };
  }
  for (const g of where?.groups ?? []) {
    const c = [...(g.recent ?? []), ...(g.starred ?? [])].find((x) => x.sessionId === chatId);
    if (c) return { recent: c };
  }
  return {};
}

export class ChatPanes implements vscode.Disposable {
  private panes = new Map<string, Pane>(); // "<host>|<chat id>" -> its tab

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
    const key = `${chat.host ?? ""}|${chatId}`;
    const pane = this.panes.get(key);
    if (pane) return pane.reveal(tab);
    const created = new Pane(this, chat, tab);
    this.panes.set(key, created);
    created.onClosed(() => this.panes.delete(key));
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
    const r = await this.backend.pane([...args, "--decision", decision, ...(note.trim() ? ["--note", note.trim()] : []),
                                        ...(given ? ["--answers", JSON.stringify(given)] : []),
                                        ...(host ? ["--host", host] : configDirArgs())], 60000);
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
    const chatId = chat.chatId || chat.sessionId;
    const { session } = findPaneRow(this.dash.state(), host, chatId);
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
    const sid = session?.sessionId ?? chat.sessionId;
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
  private terminalHere = false;

  constructor(
    private owner: ChatPanes,
    chat: ChatRef,
    tab: "chat" | "review",
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
        void this.receive(m).catch((e) => this.owner.ext.log?.warn?.(`The chat tab's request failed: ${e instanceof Error ? e.message : String(e)}`))),
      // shown again: the conversation at once (nothing read it while hidden);
      // focus moving between editors changes nothing
      this.panel.onDidChangeViewState(() => {
        if (this.disposed || this.panel.visible === this.shown) return;
        this.shown = this.panel.visible;
        this.post({ type: "visible", visible: this.shown });
        if (this.shown && this.ready) void this.load();
        this.schedule();
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
      }),
    );
  }

  private static sideBySide(): boolean {
    return vscode.workspace.getConfiguration("talpyDen").get("diffSideBySide") !== false;
  }

  // The conversation's font (talpyDen.chatFont): the terminal's, as Claude's
  // terminal shows a chat (terminal.integrated.fontFamily, which falls back to
  // the editor's), the editor's, or "" (VS Code's own)
  static chatFont(): string {
    const which = vscode.workspace.getConfiguration("talpyDen").get("chatFont");
    if (which === "ui") return "";
    const editor = vscode.workspace.getConfiguration("editor").get<string>("fontFamily") || "var(--vscode-editor-font-family, monospace)";
    const terminal = which === "editor" ? "" : vscode.workspace.getConfiguration("terminal.integrated").get<string>("fontFamily") || "";
    return terminal || editor;
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

  // It's on screen with the chat id (petKeyOf) names
  shows(id: string): boolean {
    return !this.disposed && this.panel.visible && petKeyOf(this.chat, this.host || undefined) === id;
  }

  draft(text: string): void {
    if (this.ready) this.post({ type: "result", kind: "draft", ok: true, message: text, ask: true });
    else this.pendingDraft = text;
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
    const { session, recent } = findPaneRow(state, this.host, this.chatId);
    if (session) this.chat = chatRefOf(session, this.host || undefined);
    else if (recent) this.chat = recentRef(recent, this.host || undefined);
    this.terminalHere = session ? await this.owner.routeHere(session, this.host) : false;
    if (this.disposed) return; // (closed meanwhile)
    const item = session ?? (recent ? { ...recent, chatId: recent.sessionId, state: "done" as const } : undefined);
    const queued = queuedReply(state.status, this.chatId, this.host || undefined);
    const chat: PaneChat = {
      host: this.host,
      chatId: this.chatId,
      sessionId: session?.sessionId ?? this.chat.sessionId,
      profileDir: session?.profileDir ?? recent?.profileDir ?? this.chat.profileDir,
      name: session?.name ?? recent?.name ?? this.chat.name,
      cwd: session?.cwd ?? recent?.cwd ?? this.chat.cwd ?? "",
      state: session?.state ?? "done",
      stateText: session ? stateText(session, state.now) : "not running",
      route: this.terminalHere ? "vscodeTerminal" : (session?.reply ?? "background"),
      busy: session?.state === "working" || session?.state === "waiting",
      atWork: session?.state === "working" && session.reason !== "background shell",
      activity: session ? doingText(session, this.host ? null : liveOf(session, state.live)) : "",
      permission: session?.state === "waiting" ? (session.permission ?? null) : null,
      changes: (session?.changes ?? recent?.changes)?.count ?? 0,
      reviewPending: item ? reviewPending(item, state.status, this.host || undefined) : false,
      reviewed: item ? reviewSeen(item, state.status, this.host || undefined) : true,
      review: session?.review ?? recent?.review ?? null,
      queued: queued ? { id: queued.id, prompt: queued.prompt, error: queued.error } : null,
      canMove: !!session && this.owner.ext.actions.canMoveToClaudeCode(this.chat),
      where: chatWhere(session, this.terminalHere),
      terminalApp: session?.terminalApp ?? "",
      attached: session?.kind === "bg" ? (session.attached ?? null) : null,
      profile: session?.profile ?? "",
      shared: session?.shared ?? null,
      mode: session?.peek?.mode ?? "",
      plan: session?.plan ? { title: session.plan.title } : null,
      agents: session?.agents ?? null,
      tasks: session?.tasks && session.tasks.total > 0 ? session.tasks : null,
    };
    this.panel.title = chat.name || this.chatId.slice(0, 8);
    if (this.ready) this.post({ type: "chat", chat });
    // its turn began or ended, it asks something: the conversation now
    if (this.lastState !== undefined && chat.state !== this.lastState && this.panel.visible) void this.load();
    this.lastState = chat.state;
  }

  // The conversation, again while the tab shows (often for this computer's
  // chats; with live mode it's read at each step, so this is a fallback)
  private schedule(): void {
    if (this.timer) clearTimeout(this.timer);
    this.timer = undefined;
    if (this.disposed || !this.panel.visible) return; // (closed: the reading stops)
    // (with the watcher, only for what it can't see: a moment it wasn't running)
    const every = this.host ? 5000 : this.watchFailures === 0 && this.watching ? 15000 : this.owner.ext.dash.liveHook ? 5000 : 1500;
    this.timer = setTimeout(() => void this.load().finally(() => this.schedule()), every);
  }

  private async load(): Promise<void> {
    if (this.disposed) return;
    if (this.loading) {
      this.loadAgain = true; // (something changed while it was read: read it again then)
      return;
    }
    this.loading = true;
    try {
      const r = await this.owner.ext.backend.pane([
        "--conversation", this.chatId, "--limit", String(this.limit), ...(this.stamp ? ["--if-changed", this.stamp] : []),
        ...(this.chat.profileDir ? ["--profile", this.chat.profileDir] : []), ...(this.host ? ["--host", this.host] : configDirArgs()),
      ], this.host ? 60000 : 30000);
      if (this.disposed || (r.ok && r.unchanged)) return;
      this.take(r);
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
        const asked = Date.now();
        const r = await this.owner.ext.backend.pane([
          "--conversation", this.chatId, "--limit", String(limit), "--if-changed", stamp, "--wait", "50",
          ...(this.chat.profileDir ? ["--profile", this.chat.profileDir] : []), ...configDirArgs(),
        ], 70000);
        if (this.disposed) return;
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
        break;
      case "more":
        this.limit = Math.min(LIMIT_MAX, this.limit * 2);
        this.stamp = "";
        await this.load();
        break;
      case "send": {
        if (typeof m.text !== "string" || !["auto", "background", "copy", "enter"].includes(m.how)) break;
        const r = await this.owner.send(this.chat, m.text, m.how, m.afterTurn === true);
        this.result(m.afterTurn ? "later" : "send", r, typeof m.id === "number" ? m.id : undefined);
        await this.load();   // (the watcher has it already, as it's written; an SSH host's chat now)
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
        await actions.open(this.chat);
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
                    error: there.path ? "" : this.host && saved.path ? `Couldn't copy the picture to ${this.host}: ${there.message}` : there.message });
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
          if (this.host) this.post({ type: "picture", id: m.id, path: "", error: `Only pictures go to ${this.host}'s chat (copied there): that file is on this computer` });
          else this.post({ type: "file", id: m.id, path: got.path });
          break;
        }
        const there = this.host ? await backend.putImage(this.host, got.path) : got;
        this.post({ type: "picture", id: m.id, path: there.path ?? "",
                    error: there.path ? "" : `Couldn't copy the picture to ${this.host}: ${there.message}` });
        break;
      }
      case "dictate":
        await this.dictate(m.action);
        break;
      case "complete": {
        const r = await backend.pane(["--complete", this.chatId, ...(this.chat.profileDir ? ["--profile", this.chat.profileDir] : []),
          ...(this.host ? ["--host", this.host] : configDirArgs())], this.host ? 60000 : 20000);
        if (r.ok) this.post({ type: "offers", offers: { commands: Array.isArray(r.commands) ? r.commands : [],
          files: Array.isArray(r.files) ? r.files : [], history: Array.isArray(r.history) ? r.history : [] } });
        break;
      }
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
    const config = JSON.stringify({ tab, local: !this.host, scale: Pane.textScale(), split: Pane.sideBySide(), font: Pane.chatFont() });
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
    if (this.timer) clearTimeout(this.timer);
    this.timer = undefined;
    for (const d of this.disposables) d.dispose();
    this.disposables = [];
    this.closed.fire();
    this.closed.dispose();
    this.panel.dispose();
  }
}
