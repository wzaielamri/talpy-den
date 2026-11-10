// Keys, chat references and per-row rules shared by the components. The
// extension does the work (open, stop, share, menus); the webview only says
// which chat, as a ChatRef.

import { canEndChat, HIDDEN_NOUNS, type HiddenKind, petKeyOf, shareAccounts, containerOf, hostLabel } from "../../src/shared/model";
import type { ChatRef, Group, RecentChat, Session, SharedPointer, Status } from "../../src/shared/types";
import type { StageChat } from "../pets/api";

// An account's key: ids are only unique per machine
export function groupKeyOf(g: Group): string {
  return (g.host ? g.host + "/" : "") + g.id;
}

// A row's key, for UI state kept across polls (open subagent trees): by its
// chat, not its key, which goes from live to job when a background session ends
export function rowKeyOf(s: Pick<Session, "key" | "profileDir" | "sessionId" | "chatId">, host?: string): string {
  return (host ? host + "|" : "") + s.profileDir + "/" + (s.chatId || s.sessionId);
}

// (built where the extension can rebuild them from its own state: model.ts)
export { chatRefOf, recentRef, sharedRef } from "../../src/shared/model";

// The account's chats for its pet stage: the ones that need you or work
// first, one per conversation (a chat can have a running and a finished row)
export function stageChats(g: Group): StageChat[] {
  const rank: Record<string, number> = { waiting: 0, working: 1, idle: 2, done: 3 };
  const seen = new Set<string>();
  const out: StageChat[] = [];
  for (const s of g.sessions) {
    const key = petKeyOf(s, g.host);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(g.host ? { key, session: s, host: g.host, order: out.length } : { key, session: s, order: out.length });
  }
  return out.sort((a, b) => (rank[a.session.state] ?? 4) - (rank[b.session.state] ?? 4) || a.order - b.order);
}

export function fiveHourOf(g: Group): number {
  const w = g.limits?.windows.find((w) => w.key === "five_hour");
  return w ? w.pct : 0;
}

// A working chat whose context is nearly full and that has no pet of its own
// to show it; the hero says it now and then
export function contextFullText(groups: Group[], petColor: (key: string) => string): string {
  for (const g of groups)
    for (const s of g.sessions)
      if (s.state === "working" && s.context != null && s.context >= 85 && petColor(petKeyOf(s, g.host)) === "")
        return `${s.name}: context ${Math.round(s.context)}% full`;
  return "";
}

// A finished chat can be shared, continued on another account or kept on
// one, between the accounts of its own machine (this computer, or its SSH
// host: status is that machine's); not while a session has it open.
export function canShare(s: Session, status: Status | null | undefined): boolean {
  return s.pid === null && s.state === "done" && !!s.chatId && shareAccounts(status).length >= 2;
}

export function canShareRecent(status: Status | null | undefined): boolean {
  return shareAccounts(status).length >= 2;
}

export function shareTitle(host?: string): string {
  return `Continue on another account…\nShare this chat with your other accounts${containerOf(host) ? ` in ${hostLabel(host!)}` : host ? ` on ${host}` : ""} and pick it up there, or keep it on one account only.`;
}

// Removing only hides a finished row, also one whose process is still there,
// as in the Plasma widget (it comes back once it runs again)
export function canRemove(s: Session): boolean {
  return s.state === "done";
}

// Hide: a finished row, and one no process runs that a usage limit or an
// expired login stopped (talpy_den.row_over: it had no button that took it
// off the list; it comes back once it runs again)
export function canHide(s: Session): boolean {
  return canRemove(s) || (s.state === "idle" && s.pid === null && !!s.stopped);
}

// Background jobs with a running process (`claude stop`; a host's come with
// the command that stops them there), and idle chats in a terminal (canEndChat)
export function canStop(s: Session, host?: string): boolean {
  return canEndChat(s) || !!s.stopCommand || (!host && !!s.jobId && s.pid !== null);
}

export function isBackground(s: Session): boolean {
  return s.kind === "bg" || s.kind === "job";
}

// inCode: a chat no Claude has open reopens in a Claude Code panel (the switch
// of Recent chats)
export function openHint(s: Session, host?: string, inCode = false, inTalpy = false): string {
  if (inTalpy) return s.kind === "chat" ? "Reopen this chat in Talpy Chat" : "Open this background chat in Talpy Chat (no terminal shows it)";
  if (s.kind === "chat" && inCode) return host ? `Reopen this chat in a Claude Code panel (VS Code connected to ${hostLabel(host)})` : "Reopen this chat in a Claude Code panel";
  if (containerOf(host)) {
    const name = hostLabel(host!);
    if (s.entrypoint === "claude-vscode" && !s.openCommand) return `Show this conversation in VS Code (connected to ${name})`;
    if (!s.openCommand) return `Switch to the terminal open in ${name}`;
    if (s.kind === "chat") return `Reopen this chat in ${name} in a terminal`;
    return `Open this background chat in ${name} in a terminal`;
  }
  if (host) {
    if (s.entrypoint === "claude-vscode" && !s.openCommand) return `Show this conversation in VS Code (connected to ${host})`;
    if (!s.openCommand) return `Switch to the terminal with the ssh connection to ${host}`;
    if (s.kind === "chat") return `Reopen this chat on ${host} in a terminal (ssh)`;
    return `Open this background chat on ${host} in a terminal (ssh)`;
  }
  if (s.entrypoint === "claude-vscode") return "Open this conversation in VS Code";
  if (s.kind === "chat") return "Reopen this chat in a terminal (claude --resume)";
  if (isBackground(s) && s.pid === null) return "Reopen this background chat in a terminal";
  if (isBackground(s)) return "Show this background chat in a terminal";
  return "Switch to the terminal running this chat";
}

export function sharedTagTitle(s: Session): string {
  const info = s.shared;
  if (!info) return "";
  const profiles = (info.profiles ?? []).join(" + ");
  const stopped = info.stoppedCopies?.length
    ? `\nIts background chat on ${info.stoppedCopies.join(", ")} was stopped; ${info.stoppedCopies.join(", ")} shows a link to this ${info.forkOf ? "copy" : "chat"}.`
    : "";
  if (info.forkOf)
    return (
      `Copy of a shared chat\nA copy of a chat shared between the ${profiles} profiles: Claude forked it into a chat of its own on ${s.profile}, so new messages here are only on ${s.profile}.` +
      (info.movedHere ? "\nThe shared chat continued here, so it isn't listed itself." : "") +
      stopped
    );
  return (
    `Shared chat\nThis chat is shared between the ${profiles} profiles: it continues on whichever account you open it with. Only one Claude can have it open at a time.` +
    (s.kind === "chat" ? `\nListed here because it was used on ${s.profile} last.` : "") +
    (info.openIn ? `\nOpen in ${info.openIn} right now.` : "") +
    stopped
  );
}

// Hide's tooltip, after its name: nothing is deleted, and what brings it back
export function hideHint(kind: HiddenKind, host?: string): string {
  const back = host ? `The eye button next to ${hostLabel(host)}'s name brings it back.`
    : `Show Hidden ${HIDDEN_NOUNS[kind][2]} Again (the view's ⋯ menu) brings it back.`;
  return "Only hides it here; nothing is deleted. " + (kind === "chats" ? "It comes back if the chat runs again. " : "") + back;
}

// Delete…'s tooltip, after its name (as Plasma's)
export function deleteHint(kind: "chat" | "plan" | "memory"): string {
  return kind === "chat" ? "Moves it to the Trash, on every account it's shared with, with its subagents and checkpoints; the Recap keeps its numbers. It asks first."
    : kind === "plan" ? "Moves its file to the Trash, on every account it's on. It asks first."
    : "Moves its file to the Trash and takes its line out of MEMORY.md: Claude stops reading it in new chats in its folder. It asks first.";
}
