// What Find a Chat lists (actions.ts: findChat), from each source's answer:
// this computer first, then the SSH hosts shown. Under each source, the
// folders, plans, memories and chats it found, each kind under a heading you
// pick to fold or unfold it. Chats show at first; the rest too when no chat
// has the words. With SSH hosts shown, each source has a heading of its own.

import type { FindAnswer } from "./backend";
import { hostLabel } from "./shared/model";

export type FoundKind = "projects" | "plans" | "memories" | "chats";

export type FoundLine =
  | { fold: string; title: string; open: boolean; source: boolean } // a heading: picking it folds or unfolds what's under it
  | { kind: FoundKind; source: number; index: number } // one thing found: answers[source], its kind, index
  | { note: string; warning: boolean };

/** "<host>/<kind>" -> unfolded, as you picked it ("" is this computer, kind "source" the whole source) */
export type Folds = ReadonlyMap<string, boolean>;

const KINDS: [FoundKind, string][] = [
  ["projects", "Folders"],
  ["plans", "Plans"],
  ["memories", "Memories"],
  ["chats", "Chats"],
];

function found(answer: FindAnswer, kind: FoundKind): readonly unknown[] {
  return kind === "chats" ? answer.results : answer[kind];
}

function count(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

function shown(folds: Folds, host: string, kind: FoundKind | "source", answer: FindAnswer): boolean {
  return folds.get(`${host}/${kind}`) ?? (kind === "source" || kind === "chats" || answer.results.length === 0);
}

function summary(answer: FindAnswer): string {
  const parts = [count(answer.results.length, "chat", "chats") + (answer.more ? "+" : "")];
  if (answer.projects.length) parts.push(count(answer.projects.length, "folder", "folders"));
  if (answer.plans.length) parts.push(count(answer.plans.length, "plan", "plans"));
  if (answer.memories.length) parts.push(count(answer.memories.length, "memory", "memories"));
  return parts.join(", ");
}

export function foundLines(answers: readonly FindAnswer[], hosts: readonly string[], folds: Folds): FoundLine[] {
  const lines: FoundLine[] = [];
  if (!answers.length) return lines;
  answers.forEach((answer, source) => {
    const host = source ? hosts[source - 1] : "";
    if (hosts.length) {
      const open = shown(folds, host, "source", answer);
      const title = (host ? hostLabel(host) : "This computer") + (answer.ok ? ` · ${summary(answer)}` : "");
      lines.push({ fold: `${host}/source`, title, open, source: true });
      if (!open) return;
    }
    if (!answer.ok) lines.push({ note: answer.message, warning: true });
    for (const [kind, label] of KINDS) {
      const things = found(answer, kind);
      if (!things.length) continue;
      const open = shown(folds, host, kind, answer);
      const more = kind === "chats" && answer.more;
      lines.push({ fold: `${host}/${kind}`, title: `${label} (${things.length}${more ? "+" : ""})`, open, source: false });
      if (!open) continue;
      things.forEach((_, index) => lines.push({ kind, source, index }));
      if (more) lines.push({ note: "More chats have these words: add a word to narrow it down", warning: false });
    }
  });
  if (answers.every((answer) => KINDS.every(([kind]) => !found(answer, kind).length)))
    lines.push({ note: "Nothing with all of these words: no chat (its name, folder or your prompts), project folder, plan or memory", warning: false });
  return lines;
}

/** Is every source and every kind found unfolded? */
export function allShown(answers: readonly FindAnswer[], hosts: readonly string[], folds: Folds): boolean {
  return answers.every((answer, source) => {
    const host = source ? hosts[source - 1] : "";
    return shown(folds, host, "source", answer) && KINDS.every(([kind]) => !found(answer, kind).length || shown(folds, host, kind, answer));
  });
}

/** Unfold everything, or fold every kind found (the sources stay open) */
export function showAll(answers: readonly FindAnswer[], hosts: readonly string[], folds: Folds, open: boolean): Map<string, boolean> {
  const next = new Map(folds);
  answers.forEach((answer, source) => {
    const host = source ? hosts[source - 1] : "";
    if (open) next.set(`${host}/source`, true);
    for (const [kind] of KINDS) if (found(answer, kind).length) next.set(`${host}/${kind}`, open);
  });
  return next;
}
