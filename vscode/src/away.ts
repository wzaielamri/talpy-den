// "While you were away": when you come back to VS Code after a while, one
// notification sums up what happened meanwhile (chats that finished or
// failed, chats waiting for you, limits that reset) instead of one
// notification per chat. Away means no VS Code window was in use: each window
// notes when it was last in use in a small file in the cache folder, so
// coming back to another window than the one you left isn't an absence.

import * as fs from "node:fs";
import * as path from "node:path";
import * as vscode from "vscode";
import { cacheDir } from "./config";
import { duration } from "./shared/model";
import type { Group, Session } from "./shared/types";
import type { Changes, PetEvent } from "./transitions";

const MARK_EVERY_MS = 15000; // a window in use notes it this often
const LISTED = 4; // chats named per line, then "+N" (as Plasma's and GNOME's summary)

export interface Digest {
  away: number; // how long, ms
  title: string; // "While you were away (1h 12m)"
  lines: string[];
  message: string; // all of it on one line, for a notification
  first: { session: Session; host?: string } | null; // the chat waiting longest, to open
}

interface Happened {
  at: number;
  id: string;
  kind: "finished" | "failed" | "stopped" | "limit" | "login";
  name: string;
}

function names(list: string[]): string {
  const more = list.length - LISTED;
  return list.slice(0, LISTED).join(", ") + (more > 0 ? ` +${more}` : "");
}

// The digest of an absence, or null when nothing happened that you'd want to hear about
export function digestOf(away: number, happened: Happened[], resets: string[], groups: Group[], now: number): Digest | null {
  const waiting: { session: Session; host?: string }[] = [];
  for (const g of groups) for (const s of g.sessions) if (s.state === "waiting") waiting.push({ session: s, host: g.host });
  waiting.sort((a, b) => (a.session.since ?? now) - (b.session.since ?? now));
  // each chat once, as it last ended (a usage limit that showed a poll after
  // its turn ended comes after the "finished")
  const last = new Map<string, Happened>();
  for (const h of happened) last.set(h.id, h);
  const ended = (kind: Happened["kind"]) => [...last.values()].filter((h) => h.kind === kind).map((h) => h.name);
  const finished = ended("finished");
  const failed = ended("failed");
  const stopped = ended("stopped");
  const limited = ended("limit");
  const loggedOut = ended("login");
  if (!waiting.length && !finished.length && !failed.length && !stopped.length && !limited.length && !loggedOut.length)
    return null;
  const parts: string[] = [];
  if (waiting.length) {
    // (a line each for the first three, with its host, as Plasma's)
    for (const w of waiting.slice(0, 3))
      parts.push(`Needs you: ${w.session.name}${w.host ? ` · ${w.host}` : ""} (waiting ${duration(now - (w.session.since ?? now))})`);
    const rest = waiting.length - 3;
    if (rest > 0) parts.push(`+${rest} more ${rest === 1 ? "needs" : "need"} you`);
  }
  if (finished.length) parts.push(`Finished: ${names(finished)}`);
  if (failed.length) parts.push(`Failed: ${names(failed)}`);
  if (stopped.length) parts.push(`Stopped: ${names(stopped)}`);
  if (limited.length) parts.push(`Hit the usage limit: ${names(limited)}`);
  if (loggedOut.length) parts.push(`Login expired: ${names(loggedOut)}`);
  for (const r of [...new Set(resets)]) parts.push(r);
  const title = `While you were away (${duration(away)})`;
  return { away, title, lines: parts, message: `${title}: ${parts.join(" · ")}`, first: waiting[0] ?? null };
}

// What happened while this window wasn't in use
export class AwayTracker {
  private sinceMs: number | null = null;
  private happened: Happened[] = [];
  private resets: { at: number; text: string }[] = [];

  get since(): number | null {
    return this.sinceMs;
  }

  leave(now: number): void {
    if (this.sinceMs !== null) return;
    this.sinceMs = now;
    this.happened = [];
    this.resets = [];
  }

  note(changes: Pick<Changes, "finished">, resets: PetEvent[], now: number): void {
    if (this.sinceMs === null) return;
    for (const f of changes.finished) {
      const kind =
        f.stop || (f.session.reason === "failed" ? "failed" : f.session.reason === "stopped" ? "stopped" : "finished");
      this.happened.push({ at: f.at, id: f.id, kind, name: f.session.name });
    }
    for (const r of resets) if (r.kind === "reset") this.resets.push({ at: now, text: r.text.replace(/!+$/, "") });
  }

  // Back: the digest of the absence, counted from when any VS Code window was
  // last in use (lastUse), if it lasted at least minMs and something happened
  back(now: number, lastUse: number, groups: Group[], minMs: number): Digest | null {
    const since = Math.max(this.sinceMs ?? now, lastUse);
    const happened = this.happened.filter((h) => h.at >= since);
    const resets = this.resets.filter((r) => r.at >= since).map((r) => r.text);
    this.sinceMs = null;
    this.happened = [];
    this.resets = [];
    if (now - since < minMs) return null;
    return digestOf(now - since, happened, resets, groups, now);
  }
}

// In use: interacted with recently (VS Code's `active`), else focused
function inUse(state: vscode.WindowState): boolean {
  return (state as { active?: boolean }).active ?? state.focused;
}

// Follows this window's use and tells onBack when you come back to it
export class AwayWatch implements vscode.Disposable {
  readonly tracker = new AwayTracker();
  private markFile = path.join(cacheDir(), "vscode-active.json");
  private timer?: NodeJS.Timeout;
  private subscription: vscode.Disposable;

  constructor(private onBack: (now: number, lastUse: number) => void) {
    // Started in the background (unfocused) isn't being away from it: you
    // haven't used this window yet, so there's nothing to sum up later
    if (inUse(vscode.window.state)) this.inUse();
    this.subscription = vscode.window.onDidChangeWindowState((s) => {
      if (inUse(s)) {
        if (this.tracker.since === null) {
          if (!this.timer) this.inUse(); // the first use of this window
          return;
        }
        const lastUse = this.lastUse();
        this.inUse();
        this.onBack(Date.now(), lastUse);
      } else if (this.tracker.since === null) {
        this.mark();
        clearInterval(this.timer);
        this.tracker.leave(Date.now());
      }
    });
  }

  dispose(): void {
    clearInterval(this.timer);
    this.subscription.dispose();
  }

  // Away long enough that notifications of finished chats wait for the digest
  holding(now: number, minMs: number): boolean {
    const since = this.tracker.since;
    return since !== null && now - Math.max(since, this.lastUse()) >= minMs;
  }

  private inUse(): void {
    this.mark();
    clearInterval(this.timer);
    this.timer = setInterval(() => this.mark(), MARK_EVERY_MS);
  }

  private mark(): void {
    try {
      fs.mkdirSync(path.dirname(this.markFile), { recursive: true, mode: 0o700 });
      fs.writeFileSync(this.markFile, JSON.stringify({ pid: process.pid, at: Date.now() }), { mode: 0o600 });
    } catch {
      // without it, each window counts only its own use
    }
  }

  // When any VS Code window was last in use (0 when unknown)
  private lastUse(): number {
    try {
      const { at } = JSON.parse(fs.readFileSync(this.markFile, "utf8"));
      return typeof at === "number" ? at : 0;
    } catch {
      return 0;
    }
  }
}
