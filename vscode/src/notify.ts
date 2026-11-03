// Notifications and sounds. Every VS Code window runs its own copy of the
// extension and sees the same changes, so only one of them speaks up: the
// window focused last (it notes itself in a small file in the cache folder).

import * as fs from "node:fs";
import * as path from "node:path";
import * as vscode from "vscode";
import type { Backend } from "./backend";
import type { ChatPanes } from "./chatPane";
import { cacheDir, settings } from "./config";
import { gnomeSoundTheme } from "./desktop";
import type { Digest } from "./away";
import { oneChoice, questionsOf, shownAsk } from "./shared/pane";
import type { Answers, AskShown, ChatRef, Question, Session } from "./shared/types";
import type { Changes } from "./transitions";

export function chatRef(s: Session, host?: string): ChatRef {
  return {
    host,
    key: s.key,
    sessionId: s.sessionId,
    chatId: s.chatId,
    profileDir: s.profileDir,
    name: s.name,
    entrypoint: s.entrypoint,
    pid: s.pid,
    cwd: s.cwd,
    kind: s.kind,
    jobId: s.jobId,
    openCommand: s.openCommand ?? null,
    stopCommand: s.stopCommand ?? null,
    terminalCommand: s.terminalCommand ?? null,
    vscodeTerminal: s.vscodeTerminal ?? null,
    shared: !!s.shared,
  };
}

function pidAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch (e) {
    return (e as NodeJS.ErrnoException).code === "EPERM";
  }
}

export class Notifier implements vscode.Disposable {
  private leaderFile = path.join(cacheDir(), "vscode-notify.json");
  private subscription: vscode.Disposable;
  panes?: ChatPanes; // the chats' tabs: replies and answers go through them (set once they're there)

  constructor(
    private backend: Backend,
    private open: (chat: ChatRef) => void,
  ) {
    if (vscode.window.state.focused) this.claim();
    this.subscription = vscode.window.onDidChangeWindowState((s) => {
      if (s.focused) this.claim();
    });
  }

  dispose(): void {
    this.subscription.dispose();
  }

  private claim(): void {
    try {
      fs.mkdirSync(path.dirname(this.leaderFile), { recursive: true, mode: 0o700 });
      fs.writeFileSync(this.leaderFile, JSON.stringify({ pid: process.pid, at: Date.now() }), { mode: 0o600 });
    } catch {
      // without the file every window notifies; still better than none
    }
  }

  // This window speaks for all: it was focused last, or the one that was is gone
  isLeader(): boolean {
    try {
      const { pid } = JSON.parse(fs.readFileSync(this.leaderFile, "utf8"));
      if (pid === process.pid) return true;
      if (typeof pid === "number" && pidAlive(pid)) return false;
    } catch {
      // no file yet
    }
    this.claim();
    return true;
  }

  // holdDone: you're away; finished (and stopped) chats wait for the digest (away.ts)
  handle(changes: Changes, opts: { holdDone?: boolean } = {}): void {
    const notices = opts.holdDone ? changes.notices.filter((n) => n.kind === "waiting" || n.kind === "overlap") : changes.notices;
    if (!notices.length || !this.isLeader()) return;
    for (const n of notices) {
      const text = `${n.title} — ${n.body}`;
      const show = n.kind === "done" || n.kind === "reset" ? vscode.window.showInformationMessage : vscode.window.showWarningMessage;
      const chat = chatRef(n.session, n.host);
      const p = n.kind === "waiting" ? n.session.permission : null;
      const asks = !!p && (p.answer === "hook" || p.answer === "keys") && !!this.panes;
      // its buttons answer the prompt this notification shows, never one the chat asks after it
      const shown = shownAsk(p);
      if (asks && questionsOf(p).length) {
        this.askQuestions(text, show, chat, n.session, shown);
        continue;
      }
      // a plan: approve it (accepting edits or not), or plan on with a note
      if (asks && p!.plan) {
        const planText = `${n.session.name} has a plan ready${p!.plan.title ? `: ${p!.plan.title}` : ""}`;
        void show(planText, "Approve, accept edits", "Approve", "Keep planning…", "Open").then(async (choice) => {
          const panes = this.panes;
          if (!panes) return;
          if (choice === "Approve, accept edits") this.told(chat, await panes.answer(chat, "approve-edits", shown));
          else if (choice === "Approve") this.told(chat, await panes.answer(chat, "approve", shown));
          else if (choice === "Keep planning…") {
            const note = await vscode.window.showInputBox({ title: `Keep planning: ${n.session.name}`, prompt: "What should change in the plan? (optional)", ignoreFocusOut: true });
            if (note !== undefined) this.told(chat, await panes.answer(chat, "keep", shown, note.trim()));
          } else if (choice === "Open") this.openChat(chat);
        });
        continue;
      }
      // a permission prompt: answer it here, in Claude's own order (Yes, Yes
      // and don't ask again, No); a chat that waits or finished: reply here
      // (two chats on the same files, a limit that reset: Open only)
      const buttons = asks
        ? ["Allow once", ...(p!.answer === "keys" || p!.always ? ["Always allow"] : []), "Deny", "Deny with a note…", "Open"]
        : this.panes && (n.kind === "done" || (n.kind === "waiting" && !p)) ? ["Reply…", "Open"] : ["Open"];
      // (what Always allow lets through from now on, next to the button)
      const always = asks && p!.answer === "hook" && p!.always ? ` · Always allow: ${p!.always}` : "";
      void show(text + always, ...buttons).then(async (choice) => {
        const panes = this.panes;
        if (choice === "Open") {
          if (panes && settings.clickOpensPane()) panes.open(chat, "chat");
          else this.open(chat);
        } else if (panes && (choice === "Allow once" || choice === "Always allow" || choice === "Deny")) {
          this.told(chat, await panes.answer(chat, choice === "Allow once" ? "allow" : choice === "Always allow" ? "always" : "deny", shown));
        } else if (panes && choice === "Deny with a note…") {
          const note = await vscode.window.showInputBox({ title: `Deny ${n.session.name}`, prompt: "What should Claude do instead? (optional)", ignoreFocusOut: true });
          if (note !== undefined) this.told(chat, await panes.answer(chat, "deny", shown, note.trim()));
        } else if (panes && choice === "Reply…") {
          const reply = await vscode.window.showInputBox({ title: `Reply to ${n.session.name}`, prompt: "Sent the way the chat takes it", ignoreFocusOut: true });
          if (reply?.trim()) this.notSent(chat, reply, await panes.reply(chat, reply));
        }
      });
    }
    const sound = opts.holdDone && changes.sound !== "waiting" ? "" : changes.sound;
    if (sound && settings.notifySound()) {
      const file =
        sound === "waiting" ? settings.soundWaiting() : sound === "failed" ? settings.soundFailed() : settings.soundDone();
      if (file) void gnomeSoundTheme().then((theme) => this.backend.sound(file, settings.soundVolume(), theme));
    }
  }

  // Claude's questions: one with one answer has a button per option, then
  // Other… (your own words); else Answer… goes through them one by one
  // (VS Code's pickers); Open shows the chat
  private askQuestions(text: string, show: typeof vscode.window.showWarningMessage, chat: ChatRef, s: Session, shown: AskShown | null): void {
    const choices = oneChoice(s.permission);
    const items: (vscode.MessageItem & { run: () => Promise<Answers | null | "open"> })[] = [
      ...choices.map((o) => ({ title: o.label, run: async () => ({ [questionsOf(s.permission)[0].question]: [o.label] }) })),
      choices.length
        ? { title: "Other…", run: () => this.ownWords(s, questionsOf(s.permission)[0]) }
        : { title: "Answer…", run: () => this.pickAnswers(s, questionsOf(s.permission)) },
      { title: "Open", run: async () => "open" as const },
    ];
    void show(text, ...items).then(async (item) => {
      const panes = this.panes;
      const answer = item ? await item.run() : null;
      if (!panes || !answer) return;
      if (answer === "open") {
        if (settings.clickOpensPane()) panes.open(chat, "chat");
        else this.open(chat);
      } else this.told(chat, await panes.answer(chat, "answer", shown, "", answer));
    });
  }

  // An answer from a notification that didn't go through (the chat asks
  // something else now, or the helper failed): said, with the chat to open
  private told(chat: ChatRef, answer: { ok: boolean; message: string }): void {
    if (answer.ok) return;
    void vscode.window.showWarningMessage(`Talpy Den: couldn't answer ${chat.name}: ${answer.message}`, "Open").then((choice) => {
      if (choice !== "Open") return;
      if (this.panes && settings.clickOpensPane()) this.panes.open(chat, "chat");
      else this.open(chat);
    });
  }

  // A reply from a notification that wasn't sent: said, and Open shows the
  // chat's tab with it as the unsent reply (the box it was typed in is gone)
  private notSent(chat: ChatRef, text: string, answer: { ok: boolean; message: string }): void {
    if (answer.ok) return;
    void vscode.window.showWarningMessage(`Talpy Den: couldn't send your message to ${chat.name}: ${answer.message}`, "Open").then((choice) => {
      if (choice === "Open") this.panes?.draft(chat, text);
    });
  }

  // A question answered in your own words (null: you closed the box)
  private async ownWords(s: Session, q: Question): Promise<Answers | null> {
    const text = await vscode.window.showInputBox({ title: `${s.name}: ${q.header || "your answer"}`, prompt: q.question, ignoreFocusOut: true });
    return text?.trim() ? { [q.question]: [text.trim()] } : null;
  }

  // Each question in a picker of its options (several to tick for a
  // multiSelect one), with "Other…" for your own words; null if you stop
  private async pickAnswers(s: Session, questions: Question[]): Promise<Answers | null> {
    const answers: Answers = {};
    for (const [i, q] of questions.entries()) {
      const items: (vscode.QuickPickItem & { own?: boolean })[] = [
        ...q.options.map((o) => ({ label: o.label, detail: o.description || undefined })),
        { label: "Other…", description: "answer in your own words", own: true },
      ];
      const title = `${s.name}: ${q.header || "question"}${questions.length > 1 ? ` (${i + 1}/${questions.length})` : ""}`;
      const opts = { title, placeHolder: q.question, ignoreFocusOut: true, matchOnDetail: true };
      const picked = q.multiSelect
        ? await vscode.window.showQuickPick(items, { ...opts, canPickMany: true })
        : await vscode.window.showQuickPick(items, opts).then((one) => (one ? [one] : undefined));
      if (!picked?.length) return null;
      const values = picked.filter((it) => !it.own).map((it) => it.label);
      if (picked.some((it) => it.own)) {
        const own = await this.ownWords(s, q);
        if (!own) return null;
        values.push(...own[q.question]);
      }
      answers[q.question] = values;
    }
    return answers;
  }

  // A notification's Open: the chat's tab when clicks open it (as a row's
  // click does), else the chat itself
  private openChat(chat: ChatRef): void {
    if (this.panes && settings.clickOpensPane()) this.panes.open(chat, "chat");
    else this.open(chat);
  }

  // What happened while you were away, in one notification
  digest(d: Digest, showView: () => void): void {
    if (!this.isLeader()) return;
    const action = d.first ? `Open ${d.first.session.name}` : "Show Chats";
    void vscode.window.showInformationMessage(d.message, action).then((choice) => {
      if (choice !== action) return;
      if (d.first) this.openChat(chatRef(d.first.session, d.first.host));
      else showView();
    });
  }
}
