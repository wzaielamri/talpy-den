// What only one host can do, asked for through a port of its own (the rest goes through HostServices):
// terminals, VS Code's own UI (its changes view, Talpy Den's doc tab, an editor tab, the plan review,
// Claude Code's panel) and Talpy Chat's panes. Each has exactly the members the core calls; paths cross
// as plain strings, never as a host's own types.

import type { Comparison } from "./comparisons";
import type { Event } from "./events";
import type { Answers, AskShown, ChatRef, Decision, Group, PlanItem } from "./shared/types";
import type { Place } from "./terminal";

export type { Place } from "./terminal";

// A chat's terminal, once found or started
export interface TerminalHandle {
  show(): void; // actions' open and sendPlanFeedback; chatPanes' typeIn
  // addNewLine false: the text only, Enter sent on its own (actions' stop and sendPlanFeedback; chatPanes' send,
  // typeIn and interrupt)
  sendText(text: string, addNewLine: boolean): void;
}

// The host's terminals (VS Code: terminals.ts)
export interface TerminalPort {
  // The terminal of this window a process runs in (one of ancestors is its shell); ancestors are this
  // computer's, or the window's host's (actions' open, stop and sendPlanFeedback; chatPanes' windowTerminal)
  find(ancestors: Set<number>, onWindowHost: boolean): Promise<TerminalHandle | undefined>;
  // command in a new terminal, or the one still running it for key, shown; private: not kept over a reload
  // (a login); chatOn: the window's host a chat runs on (actions' open, openSystem, share, handOver,
  // sendPlanFeedback, newChat, login and loginHost; accounts' add and login)
  run(key: string, name: string, command: string, place: Place, opts?: { private?: boolean; chatOn?: string }): Promise<TerminalHandle>;
}

// A comment of yours on a plan's lines, sent with your feedback (jump.py --plan-feedback --comments)
export interface PlanComment {
  from: number; // its lines, from 1
  to: number;
  quote: string;
  text: string;
}

// What VS Code shows in its own UI and an app does its own way (or not at all) (VS Code: vscodeEditor.ts)
export interface EditorPort {
  // A chat's changed files side by side (VS Code's changes view); the error to report, or "" when it opened
  // (actions' compareChanges, chatPanes' diff)
  openComparison(c: Comparison): Promise<string>;
  // A Markdown file (a plan, a subagent's run, a memory) in Talpy Den's doc tab; the error to report, or "".
  // onWindowHost: a file of the host the window is connected to (Remote-SSH), else this computer's
  // (actions' openPlan, openMemory and openAgentRun; the extension's /markdown links)
  showDoc(path: string, options?: { onWindowHost?: boolean }): Promise<string>;
  // The file in an editor tab, to change it; throws when it can't open (actions' openPlan and openMemory, edit)
  editFile(path: string, options?: { onWindowHost?: boolean }): Promise<void>;
  // What an editor holds of this computer's file and didn't save yet, saved (actions' sendPlanFeedback)
  saveEdits(path: string): Promise<void>;
  // Your comments on a plan file's lines, top to bottom; none before the plan review is there
  // (actions' sendPlanFeedback)
  planComments(path: string): Promise<PlanComment[]>;
  // ... sent: gone (actions' sendPlanFeedback)
  clearPlanComments(path: string): void;
  // Whether Claude Code's panel can open chats in this window (dashboard's checkClaudeCode, actions' panelChoice)
  claudePanelAvailable(): Promise<boolean>;
  // It may have come or gone: the host's extensions changed (dashboard checks claudePanelAvailable again)
  readonly onDidChangeClaudePanel: Event<void>;
  // Whether the Claude Code extension is installed, its panel able to open chats here or not (an untrusted
  // folder: not) (accountSwitch.ts:115 switch: none, no VS Code Claude to switch)
  claudeCodeInstalled(): boolean;
  // The Claude config folder the panel runs this computer's chats on (actions' windowHasChat)
  localPanelConfigDir(): string;
  // ... as a profile key (dashboard's claudeCodeInfo; actions' openInClaudeCode and panelChoice;
  // accountSwitch's update, switch and switchTo)
  localPanelProfileKey(): string;
  // A new chat in the panel; prompt: typed into its input, for you to send (actions' panelChat)
  openPanelChat(prompt?: string): Promise<void>;
}

// What actions calls of the account switch (VS Code: accountSwitch.ts), until that moves to the core (Task 10,
// which removes this). switchHost: Claude Code on this window's SSH host runs on the group's account from now on
// (actions' panelChat, for a chat tab on another account than Claude Code's there); false: it couldn't (said)
export interface AccountSwitch {
  switchHost(group: Group): Promise<boolean>;
}

// Talpy Chat's panes, as notify.ts and actions.ts use them (VS Code: chatPane.ts ChatPanes)
export interface ChatPanesPort {
  // The chat's pane, opened or brought up (notify's handle, askQuestions, told and openChat; actions' open and nextChat)
  open(chat: ChatRef, tab?: "chat" | "review"): void;
  // A new chat in a pane of its own, nothing started yet; plan: one it carries out (actions' newChat)
  openNew(group: Group, folder: { path: string; short: string }, task?: string, plan?: PlanItem): void;
  // An answer to what a waiting chat asks, to the prompt shown and no other; changed: it asks something
  // else now (notify's handle and askQuestions: Allow, Deny, Approve, Keep planning, Claude's questions)
  answer(chat: ChatRef, decision: Decision, shown: AskShown | null, note?: string, answers?: Answers): Promise<{ ok: boolean; message: string; changed?: boolean }>;
  // A reply, sent the way the chat takes one (notify's handle: Reply…)
  reply(chat: ChatRef, text: string): Promise<{ ok: boolean; message: string }>;
  // The chat's pane, open with text as its unsent reply (notify's notSent: a reply that didn't go)
  draft(chat: ChatRef, text: string): void;
}
