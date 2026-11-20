// What a chat's terminal needs that asks nothing of VS Code: where it runs, the
// text pasted into it, and the processes here that are its ancestors or show a
// background job.

import * as fs from "node:fs";

export type Place = { kind: "local" } | { kind: "windowHost" } | { kind: "ssh"; host: string };

// Text typed into a chat's terminal as one paste (Claude takes it in as
// one): nothing in it can end the paste early and press keys (an ESC[201~
// in a plan's line, then Ctrl+C and a !command), so its control characters
// are left out, but tabs and new lines (a CR is one); as pane.py's as_typed
export function asPaste(text: string): string {
  return `\x1b[200~${text.replace(/\r\n?/g, "\n").replace(/[\x00-\x08\x0b-\x1f\x7f-\x9f]/g, "")}\x1b[201~`;
}

// Parent of a process here, from /proc (Linux); null when unknown
export function parentPid(pid: number): number | null {
  try {
    const stat = fs.readFileSync(`/proc/${pid}/stat`, "utf8");
    // pid (comm) state ppid …; comm may hold spaces and parentheses
    const fields = stat.slice(stat.lastIndexOf(")") + 2).split(" ");
    const ppid = Number(fields[1]);
    return Number.isInteger(ppid) && ppid > 0 ? ppid : null;
  } catch {
    return null;
  }
}

export function localAncestors(pid: number): Set<number> {
  const out = new Set<number>();
  for (let p: number | null = pid; p && p > 1 && !out.has(p) && out.size < 64; p = parentPid(p)) out.add(p);
  return out;
}

// The `claude attach <jobId>` processes here: terminals showing that
// background job (jump.py's attach_clients)
export function attachClients(jobId: string, procDir = "/proc"): number[] {
  const out: number[] = [];
  let entries: string[];
  try {
    entries = fs.readdirSync(procDir);
  } catch {
    return out; // not Linux
  }
  for (const p of entries) {
    if (!/^\d+$/.test(p)) continue;
    try {
      if (fs.readFileSync(`${procDir}/${p}/comm`, "utf8").trim() !== "claude") continue;
      const argv = fs.readFileSync(`${procDir}/${p}/cmdline`, "utf8").split("\0");
      if (argv[1] === "attach" && argv[2] === jobId) out.push(Number(p));
    } catch {
      // gone, or not ours to read
    }
  }
  return out;
}
