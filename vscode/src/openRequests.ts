// Another program's request that a chat be brought up as a click on its row does (Talpy Den's jump.py --job:
// Talpy Den Display's tap): a file of its own each (req-<16 hex>.json: the chat's jobs file id and the time,
// nothing else) in $XDG_RUNTIME_DIR/talpy-den/opens (in memory, yours alone, gone when you log out). The Plasma
// widget takes one at once (live.py --opens offers it, --take-open takes it); VS Code's window that speaks for
// all only when no widget did within FALLBACK_MS, and, as the widget, only a request for a chat it lists: else
// it's left, and jump.py, whose file it is, takes it back and brings the chat up itself. Taken by renaming it
// away (of two takers one gets it); only a fresh request naming a jobs file id is ever taken, and the id is only
// compared with the rows' own keys: nothing in it is ever run or used as a path. Its file's name goes into a path
// only if it's OPEN_NAME exactly (16 hex digits, made by jump.py): keep it that strict.

import * as crypto from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";
import { chatRefOf } from "./shared/model";
import type { ChatRef, HostState, Status } from "./shared/types";

export const OPEN_NAME = /^req-[0-9a-f]{16}\.json$/;
export const OPEN_MAX_AGE_MS = 10_000; // (a tap long ago mustn't open a tab now)
export const OPEN_AHEAD_MS = 2_000; // (nor one from the future, more than a clock's slip)
export const OPEN_MAX_BYTES = 1024;
export const OPEN_STALE_MS = 60_000; // a writer's or a taker's file left behind (killed in between): swept
export const FALLBACK_MS = 800; // the widget's turn first: it takes a request at once
const RESCAN_MS = 60_000; // the folder watched again if it went (as live.ts's sessions folders)
export const JOB_ID_MAX = 300;
// A jobs file id (the backend's place_jobs: a row's key, "<host>:" before a host's or container's), in letters,
// digits and _ . @ : + - only: live.py's and jump.py's JOB_ID, the same rule
export const JOB_ID = /^(?:[A-Za-z0-9_.@][A-Za-z0-9_.@:-]*:)?[A-Za-z0-9_.+-]+\/[A-Za-z0-9_.-]+\/(?:live|job|chat)(?:\/shared)?$/;

export function jobIdOk(id: unknown): id is string {
  return typeof id === "string" && id.length <= JOB_ID_MAX && JOB_ID.test(id) && !id.includes("..") && !id.startsWith("-");
}

function privateDir(p: string): boolean {
  const st = fs.lstatSync(p);
  return st.isDirectory() && st.uid === process.getuid?.() && (st.mode & 0o077) === 0;
}

// $XDG_RUNTIME_DIR/talpy-den/opens (made, 0700), or null: no runtime folder, or it or the folders in it aren't
// folders of yours only you can use (then there are no requests). Leftovers are swept.
export function openDir(env: NodeJS.ProcessEnv = process.env): string | null {
  const runtime = env.XDG_RUNTIME_DIR;
  if (!runtime || !path.isAbsolute(runtime)) return null;
  const folder = path.join(runtime, "talpy-den", "opens");
  let names: string[];
  try {
    fs.mkdirSync(folder, { recursive: true, mode: 0o700 });
    if (!privateDir(runtime) || !privateDir(path.dirname(folder)) || !privateDir(folder)) return null;
    names = fs.readdirSync(folder);
  } catch {
    return null;
  }
  const now = Date.now();
  for (const name of names) {
    if (!name.startsWith("tmp-") && !name.startsWith("taken-")) continue;
    try { // (each on its own: a take's or a write's file comes and goes meanwhile)
      const st = fs.lstatSync(path.join(folder, name));
      if (now - st.mtimeMs > OPEN_STALE_MS && !st.isDirectory()) fs.unlinkSync(path.join(folder, name));
    } catch {
      // (gone already)
    }
  }
  return folder;
}

// What the request file at p is: "ok" and its id (a fresh request naming a jobs file id); "drop", one that never
// will be (stale; not a regular file of yours of at most OPEN_MAX_BYTES, or a link; not a request of the right
// shape); "skip", one that can't be told now (unreadable for a moment, or ahead of the clock: its writer takes it
// back)
function readRequest(p: string, nowMs: number): { verdict: "ok" | "drop" | "skip"; id: string | null } {
  let fd: number;
  try {
    fd = fs.openSync(p, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW | fs.constants.O_NONBLOCK);
  } catch (e) {
    return { verdict: (e as NodeJS.ErrnoException).code === "ELOOP" ? "drop" : "skip", id: null }; // (ELOOP: a link)
  }
  let data = "";
  try {
    const st = fs.fstatSync(fd);
    if (!st.isFile() || st.uid !== process.getuid?.() || st.size > OPEN_MAX_BYTES) return { verdict: "drop", id: null };
    const buf = Buffer.alloc(OPEN_MAX_BYTES + 1);
    data = buf.subarray(0, fs.readSync(fd, buf, 0, buf.length, 0)).toString("utf8");
  } catch {
    return { verdict: "skip", id: null };
  } finally {
    fs.closeSync(fd);
  }
  let asked: unknown;
  try {
    asked = JSON.parse(data);
  } catch {
    return { verdict: "drop", id: null };
  }
  if (!asked || typeof asked !== "object" || Array.isArray(asked)) return { verdict: "drop", id: null };
  const { id, at } = asked as { id?: unknown; at?: unknown };
  if (!jobIdOk(id) || typeof at !== "number" || !Number.isInteger(at) || at < nowMs - OPEN_MAX_AGE_MS)
    return { verdict: "drop", id: null };
  if (at > nowMs + OPEN_AHEAD_MS) return { verdict: "skip", id: null };
  return { verdict: "ok", id };
}

// Take the request file name (renamed away, then gone: once). taken false: none of that name (another took it);
// id null: it was taken but isn't a fresh request naming a jobs file id
export function takeOpen(folder: string, name: string, nowMs: number): { taken: boolean; id: string | null } {
  if (!OPEN_NAME.test(name)) return { taken: false, id: null };
  const taken = path.join(folder, `taken-${process.pid}-${crypto.randomBytes(4).toString("hex")}.json`);
  try {
    fs.renameSync(path.join(folder, name), taken); // (atomic: of two takers one gets it; a link moves as a link)
  } catch {
    return { taken: false, id: null };
  }
  try {
    const read = readRequest(taken, nowMs);
    return { taken: true, id: read.verdict === "ok" ? read.id : null };
  } finally {
    try {
      fs.unlinkSync(taken);
    } catch {
      // (gone already)
    }
  }
}

// The fresh requests in folder, the oldest first; one that never will be (stale, of a wrong shape, not a file) is
// taken and dropped, one that can't be told now is left (its writer takes it back)
export function pendingOpens(folder: string, nowMs: number): { name: string; id: string; mtimeMs: number }[] {
  let names: string[] = [];
  try {
    names = fs.readdirSync(folder).filter((n) => OPEN_NAME.test(n));
  } catch {
    return [];
  }
  const dated: { name: string; mtimeMs: number }[] = [];
  for (const name of names) {
    try {
      dated.push({ name, mtimeMs: fs.lstatSync(path.join(folder, name)).mtimeMs });
    } catch {
      // (taken meanwhile)
    }
  }
  dated.sort((a, b) => a.mtimeMs - b.mtimeMs || (a.name < b.name ? -1 : 1));
  const out: { name: string; id: string; mtimeMs: number }[] = [];
  for (const d of dated) {
    const read = readRequest(path.join(folder, d.name), nowMs);
    if (read.verdict === "ok" && read.id) out.push({ ...d, id: read.id });
    else if (read.verdict === "drop") takeOpen(folder, d.name, nowMs);
  }
  return out;
}

// The listed chat of a jobs file id: a session row whose key (with "<host>:" before a shown host's) is the id,
// this computer's first, as the widget looks it up; null for any other id
export function findJobRef(status: Status | null, hosts: HostState[], jobId: unknown): ChatRef | null {
  if (!jobIdOk(jobId)) return null;
  const rowIn = (where: Status | null | undefined, host?: string): ChatRef | null => {
    for (const g of where?.groups ?? [])
      for (const s of g.sessions ?? []) if ((host ? `${host}:` : "") + s.key === jobId) return chatRefOf(s, host);
    return null;
  };
  const here = rowIn(status);
  if (here) return here;
  for (const h of hosts)
    if (jobId.startsWith(`${h.name}:`)) {
      const there = rowIn(h.result, h.name);
      if (there) return there;
    }
  return null;
}

// Watches the requests' folder (fs.watch, as live.ts watches the sessions); a request still there FALLBACK_MS
// after it was left (no widget took it) is taken by the window that speaks for all (leader), if canOpen says this
// window lists its chat, and handed to open
export class OpenWatch {
  private watcher: fs.FSWatcher | undefined;
  private timer: NodeJS.Timeout | undefined;
  private rescan: NodeJS.Timeout | undefined;
  private folder: string | null = null;
  private ino = -1; // the watched folder's (another one at its name: it was removed and made again)
  private stopped = false;

  constructor(private readonly canOpen: (jobId: string) => boolean, private readonly open: (jobId: string) => void,
              private readonly leader: () => boolean, private readonly env: NodeJS.ProcessEnv = process.env,
              private readonly waitMs = FALLBACK_MS, private readonly rescanMs = RESCAN_MS) {}

  start(): void {
    this.arm();
    this.rescan = setInterval(() => this.arm(), this.rescanMs);
    this.rescan.unref?.();
  }

  // The folder watched (again: it went, was made again, or wasn't there yet), and a look for what's left in it
  private arm(): void {
    if (this.stopped) return;
    if (this.watcher && this.folder) {
      let ino = -2;
      try {
        ino = fs.statSync(this.folder).ino;
      } catch {
        // (gone)
      }
      if (ino === this.ino) return; // (the same folder, still watched)
      this.watcher.close(); // (fs.watch says nothing when its folder goes: another one now, or none)
      this.watcher = undefined;
    }
    this.folder = openDir(this.env);
    if (!this.folder) return;
    try {
      this.ino = fs.statSync(this.folder).ino;
      this.watcher = fs.watch(this.folder, { persistent: false }, () => this.soon(this.waitMs));
      this.watcher.on("error", () => {
        this.watcher?.close();
        this.watcher = undefined;
      });
    } catch {
      this.watcher = undefined;
    }
    this.soon(this.waitMs);
  }

  private soon(delay: number): void {
    if (this.stopped || this.timer) return;
    this.timer = setTimeout(() => {
      this.timer = undefined;
      this.look();
    }, Math.max(0, delay));
  }

  private look(): void {
    if (this.stopped || !this.folder) return;
    const now = Date.now();
    for (const r of pendingOpens(this.folder, now)) {
      const age = now - r.mtimeMs;
      if (age < this.waitMs) {
        this.soon(this.waitMs - age); // (the widget's turn first)
        return;
      }
      if (!this.leader()) return; // (another window speaks for all)
      if (!this.canOpen(r.id)) continue; // (not a chat this window lists: left, jump.py takes it back)
      const got = takeOpen(this.folder, r.name, Date.now());
      if (got.taken && got.id === r.id) this.open(r.id);
    }
  }

  dispose(): void {
    this.stopped = true;
    if (this.timer) clearTimeout(this.timer);
    if (this.rescan) clearInterval(this.rescan);
    this.timer = this.rescan = undefined;
    this.watcher?.close();
    this.watcher = undefined;
  }
}
