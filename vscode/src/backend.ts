// Runs the widget's Python backend (vendor/code): talpy_den.py for this
// computer, remote.py for SSH hosts, jump.py for actions, notify_sound.py for
// sounds. Every call is a plain argument list (no shell).

import { spawn } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import { isComparison, type Comparison } from "./changes";
import { hostLabel, shellQuote } from "./shared/model";
import type { ContainerInfo, ContainerNote, FoundChat, FoundMemory, FoundPlan, FoundProject, LimitHistory, PermsData, ProjectsData, Status, WeekRecap } from "./shared/types";

export const REMOTE_MARK = "@@talpy-den@@";
const KILL_GRACE_MS = 3000;
const PIPE_GRACE_MS = 1000; // a helper's output, read after it exited

export interface RunResult {
  code: number | null;
  stdout: string;
  stderr: string;
  spawnError?: NodeJS.ErrnoException;
  timedOut?: boolean;
}

export interface SshHost {
  name: string;
  hostname: string;
  user: string;
  port: string;
  jump: string;
}

// An SSH host's containers as it listed them last, or why it couldn't
export interface HostContainers {
  containers?: ContainerInfo[];
  notes?: ContainerNote[];
  at?: number;
  error?: string;
}

export interface HostList {
  hosts: SshHost[];
  containers: ContainerInfo[];
  notes: ContainerNote[];
  hostContainers: Record<string, HostContainers>;
}

// What the search found: chats, and the project folders, plans and memories with the words
export interface FindAnswer {
  ok: boolean;
  results: FoundChat[];
  more: boolean;
  message: string;
  projects: FoundProject[];
  plans: FoundPlan[];
  memories: FoundMemory[];
}

export interface Answer {
  ok: boolean;
  message: string;
  command?: string; // jump.py --print-command: the shell command to run instead
  file?: string; // --agent-run --no-open: the file it saved
  how?: "resumed" | "typed" | "clipboard"; // --plan-feedback: how it reaches the chat
  text?: string; // --plan-feedback --print-command: the feedback, to paste or type in
  question?: string; // --delete-chat|plan|memory --describe: what to ask before it deletes
  ask?: "vscode"; // --remote-vscode: a container's, asked first (message: the question)
  // --start-queued: a chat's go-on waits for its background commands (what the
  // queue says), or ended them to go on; notify: say so (once, as it starts
  // waiting, and when it ends them)
  waits?: string;
  ended?: string[];
  notify?: boolean;
}

// The environment for helpers: VS Code's own variables would leak into the
// terminals and programs they start.
export function helperEnv(base: NodeJS.ProcessEnv = process.env): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = {};
  for (const [k, v] of Object.entries(base)) {
    if (k.startsWith("VSCODE_") || k.startsWith("ELECTRON_") || k === "APPLICATION_INSIGHTS_NO_DIAGNOSTIC_CHANNEL") continue;
    env[k] = v;
  }
  return env;
}

export function runProcess(
  command: string,
  args: string[],
  opts: { input?: string; timeoutMs?: number; cwd?: string } = {},
): Promise<RunResult> {
  return new Promise((resolve) => {
    let stdout = "";
    let stderr = "";
    let settled = false;
    let timedOut = false;
    const child = spawn(command, args, { cwd: opts.cwd, env: helperEnv(), stdio: ["pipe", "pipe", "pipe"] });
    // Too slow: SIGTERM first, so remote.py can end the ssh it runs (SIGKILL
    // would leave that behind), and SIGKILL if it's still there after a bit
    let killer: NodeJS.Timeout | undefined;
    let drained: NodeJS.Timeout | undefined;
    const timer = opts.timeoutMs
      ? setTimeout(() => {
          if (child.exitCode !== null || child.signalCode !== null) return; // (it exited: its output is coming)
          timedOut = true;
          child.kill("SIGTERM");
          killer = setTimeout(() => child.kill("SIGKILL"), KILL_GRACE_MS);
        }, opts.timeoutMs)
      : undefined;
    const done = (result: RunResult) => {
      if (settled) return;
      settled = true;
      if (timer) clearTimeout(timer);
      if (killer) clearTimeout(killer);
      if (drained) clearTimeout(drained);
      resolve(result);
    };
    child.stdout.setEncoding("utf8").on("data", (d: string) => (stdout += d));
    child.stderr.setEncoding("utf8").on("data", (d: string) => (stderr += d));
    child.on("error", (err: NodeJS.ErrnoException) => done({ code: null, stdout, stderr, spawnError: err }));
    child.on("close", (code) => done({ code, stdout, stderr, timedOut }));
    // Exited, but a process it left behind still holds its output open: what
    // came within a moment is its answer, however long that one runs
    child.on("exit", (code) => {
      drained = setTimeout(() => {
        child.stdout.destroy();
        child.stderr.destroy();
        done({ code, stdout, stderr, timedOut });
      }, PIPE_GRACE_MS);
    });
    child.stdin.on("error", () => undefined); // the child may exit before reading
    child.stdin.end(opts.input ?? "");
  });
}

function lastLine(text: string): string {
  const lines = text.trim().split("\n");
  return lines[lines.length - 1] || "";
}

export class Backend {
  readonly codeDir: string;
  private pythonChecked = "";

  constructor(
    extensionPath: string,
    private python: () => string,
  ) {
    this.codeDir = path.join(extensionPath, "vendor", "code");
  }

  private script(name: string): string {
    return path.join(this.codeDir, name);
  }

  // poll.py runs talpy_den.py with its compiled code cached (in the
  // widget's cache folder); a widget vendored before it came has none
  private statusScript?: string;
  private pollScript(): string {
    if (this.statusScript === undefined) {
      const poll = this.script("poll.py");
      this.statusScript = fs.existsSync(poll) ? poll : this.script("talpy_den.py");
    }
    return this.statusScript;
  }

  // Why Python can't be used, or "" when it can (checked once per path)
  async checkPython(): Promise<string> {
    const python = this.python();
    if (this.pythonChecked === python) return "";
    const r = await runProcess(python, ["-I", "-c", "import sys; sys.exit(0 if sys.version_info >= (3, 7) else 3)"], {
      timeoutMs: 15000,
    });
    if (r.spawnError)
      return `Can't run "${python}" (${r.spawnError.code ?? r.spawnError.message}). Install Python 3.7 or newer, or set talpyDen.pythonPath.`;
    if (r.code === 3) return `"${python}" is older than Python 3.7; set talpyDen.pythonPath to a newer one.`;
    if (r.code !== 0) return `"${python}" doesn't work: ${lastLine(r.stderr) || `exit ${r.code}`}`;
    this.pythonChecked = python;
    return "";
  }

  // This computer's status. Run in --remote mode too: then every row carries
  // the shell command that opens it, which the extension runs in a terminal.
  async status(args: string[]): Promise<{ status?: Status; error?: string }> {
    // (--local: VS Code's account is this computer's VS Code's, not a VS Code server's)
    const r = await runProcess(this.python(), ["-I", this.pollScript(), "--remote", "--local", ...args], { timeoutMs: 60000 });
    if (r.spawnError) return { error: `Can't run Python: ${r.spawnError.message}` };
    if (r.timedOut) return { error: "The status check took longer than a minute." };
    // The JSON is the one line after the marker; a chat's prompt or reply
    // inside it may mention the marker too, so only one at a line start counts
    const mark = r.stdout.lastIndexOf("\n" + REMOTE_MARK);
    if (mark < 0) return { error: `Status script failed: ${lastLine(r.stderr) || "no output"}` };
    try {
      const parsed = JSON.parse(r.stdout.slice(mark + 1 + REMOTE_MARK.length));
      if (!parsed.ok) return { error: `Status unavailable: ${parsed.error}` };
      return { status: parsed as Status };
    } catch {
      return { error: "The status script's answer couldn't be read." };
    }
  }

  // Refresh: Claude Code fetches the plan usage of every account whose numbers
  // are over a minute old, chat at work or not (talpy_den.py --fetch-usage)
  async fetchUsage(args: string[]): Promise<void> {
    await this.json(["talpy_den.py", "--fetch-usage", ...args], 30000);
  }

  // The hosts with a name of their own in ~/.ssh/config, this computer's
  // containers (containerArgs: --container-days, --picked, or
  // --no-containers) and the SSH hosts' container lists as last fetched
  async hostList(containerArgs: string[]): Promise<HostList | null> {
    const r = await this.json(["remote.py", "--hosts", ...containerArgs], 15000);
    if (!r || !r.ok) return null;
    return {
      hosts: Array.isArray(r.hosts) ? (r.hosts as SshHost[]) : [],
      containers: Array.isArray(r.containers) ? (r.containers as ContainerInfo[]) : [],
      notes: Array.isArray(r.notes) ? (r.notes as ContainerNote[]) : [],
      hostContainers: r.hostContainers && typeof r.hostContainers === "object" ? (r.hostContainers as Record<string, HostContainers>) : {},
    };
  }

  async sshHosts(): Promise<SshHost[]> {
    return (await this.hostList(["--no-containers"]))?.hosts ?? [];
  }

  // An SSH host's containers, listed there (remote.py --containers)
  async hostContainers(host: string, containerArgs: string[]): Promise<HostContainers> {
    const r = await this.json(["remote.py", "--containers", host, ...containerArgs], 70000);
    if (!r || !r.ok) return { error: String(r?.error || r?.message || "no answer") };
    return {
      containers: Array.isArray(r.containers) ? (r.containers as ContainerInfo[]) : [],
      notes: Array.isArray(r.notes) ? (r.notes as ContainerNote[]) : [],
      at: typeof r.at === "number" ? r.at : Date.now(),
    };
  }

  // Each host's and container's last answer, kept from its last check (remote.py --last)
  async lastAnswers(hosts: string[]): Promise<Record<string, { at: number; offset: number; answer: { ok: boolean; result?: Status } }>> {
    if (!hosts.length) return {};
    const r = await this.json(["remote.py", "--last", ...hosts], 15000);
    return r && r.ok && r.last && typeof r.last === "object" ? r.last : {};
  }

  // A terminal's command line for a command in a container (remote.py --attach)
  attachLine(host: string, command: string): string {
    return [this.python(), "-I", this.script("remote.py"), "--attach", host, command].map(shellQuote).join(" ");
  }

  // login: the host wants a password (or a passphrase, a code, its host key
  // confirmed); loggedIn: the check went through a connection you logged in with;
  // a container's: stopped (Start), gone
  async hostStatus(host: string, args: string[]): Promise<{ ok: boolean; result?: Status; error?: string; login?: boolean; loggedIn?: boolean; stopped?: boolean; gone?: boolean }> {
    const r = await this.json(["remote.py", "--status", host, ...args], 70000);
    if (!r) return { ok: false, error: `${hostLabel(host)}: no answer from the SSH helper` };
    if (r.ok && r.result) return { ok: true, result: r.result as Status, loggedIn: !!r.loggedIn };
    return { ok: false, error: String(r.error || r.message || "no answer"), login: !!r.login, stopped: !!r.stopped, gone: !!r.gone };
  }

  // The chats with every word of query (talpy_den.py --find; an SSH
  // host's through remote.py, each with the command that reopens it there)
  async find(query: string, host?: string, extra: string[] = []): Promise<FindAnswer> {
    let r: Record<string, any> | null;
    if (host) r = await this.json(["remote.py", "--find", host, query], 60000);
    else {
      // --remote: each with the command that reopens it, as for the status
      const run = await runProcess(this.python(), ["-I", this.pollScript(), "--find", query, "--remote", ...extra], { timeoutMs: 60000 });
      const mark = run.stdout.lastIndexOf("\n" + REMOTE_MARK);
      try {
        r = mark < 0 ? null : JSON.parse(run.stdout.slice(mark + 1 + REMOTE_MARK.length));
      } catch {
        r = null;
      }
      if (!r) r = { ok: false, message: run.spawnError?.message ?? (lastLine(run.stderr) || "no answer") };
    }
    if (!r || !r.ok) return { ok: false, results: [], more: false, message: String(r?.message ?? r?.error ?? "no answer"), projects: [], plans: [], memories: [] };
    // an SSH host's times on this computer's clock (as toLocalClock puts its status)
    const offset = host && typeof r.generatedAt === "number" ? Date.now() - r.generatedAt : 0;
    const list = <T>(v: unknown, key: string): T[] =>
      Array.isArray(v) ? v.map((x) => (Math.abs(offset) < 5000 || typeof x?.[key] !== "number" ? x : { ...x, [key]: x[key] + offset })) : [];
    return {
      ok: true, results: list<FoundChat>(r.results, "lastActive"), more: !!r.more, message: "",
      projects: list<FoundProject>(r.projects, "lastActive"), plans: list<FoundPlan>(r.plans, "updatedAt"), memories: list<FoundMemory>(r.memories, "updatedAt"),
    };
  }

  // The Recap tab's recap (week.py): read from the chats' transcripts (only
  // what they added since it last ran), and only when the tab asks
  async week(args: string[]): Promise<{ recap?: WeekRecap; error?: string }> {
    const r = await this.json(["week.py", ...args], 180000);
    if (!r || !r.ok) return { error: String(r?.error ?? r?.message ?? "no answer") };
    return { recap: r as WeekRecap };
  }

  // The Recap's How your limits changed (week.py --limits): read only while it's unfolded
  async limits(args: string[]): Promise<{ data?: LimitHistory; error?: string }> {
    const r = await this.json(["week.py", "--limits", ...args], 180000);
    if (!r || !r.ok) return { error: String(r?.error ?? r?.message ?? "no answer") };
    return { data: r as LimitHistory };
  }

  // The Monday recap (week.py --monday-recap): due once a week for whichever copy asks first
  // Whether the Recap keeps its history, and how many chats Claude deleted are in it (week.py --history-status)
  async historyStatus(): Promise<{ keep: boolean; deletedChats: number } | null> {
    const r = await this.json(["week.py", "--history-status"], 60000);
    return r?.ok && typeof r.keep === "boolean" ? { keep: r.keep, deletedChats: Number(r.deletedChats) || 0 } : null;
  }

  async mondayRecap(args: string[]): Promise<Record<string, any> | null> {
    return this.json(["week.py", "--monday-recap", ...args], 180000);
  }

  // The Projects tab's data (week.py --projects)
  async projects(args: string[]): Promise<{ data?: ProjectsData; error?: string }> {
    const r = await this.json(["week.py", "--projects", ...args], 180000);
    if (r?.ok && Array.isArray(r.projects)) return { data: r as ProjectsData };
    return { error: String(r?.error ?? r?.message ?? "the helper gave no answer") };
  }

  // The Permissions tab's data (week.py --permissions)
  async perms(args: string[]): Promise<{ data?: PermsData; error?: string }> {
    const r = await this.json(["week.py", "--permissions", ...args], 180000);
    if (!r || !r.ok) return { error: String(r?.error ?? r?.message ?? "no answer") };
    return { data: r as PermsData };
  }

  // jump.py / remote.py actions; they print {"ok": bool, "message": str}
  async action(scriptName: "jump.py" | "remote.py" | "talpy_den.py" | "week.py", args: string[], timeoutMs = 90000): Promise<Answer> {
    const r = await this.json([scriptName, ...args], timeoutMs);
    if (!r) return { ok: false, message: "the helper gave no answer" };
    return {
      ok: !!r.ok,
      message: String(r.message ?? r.error ?? ""),
      ...(typeof r.command === "string" ? { command: r.command } : {}),
      ...(typeof r.file === "string" ? { file: r.file } : {}),
      ...(r.how === "resumed" || r.how === "typed" || r.how === "clipboard" ? { how: r.how } : {}),
      ...(typeof r.text === "string" ? { text: r.text } : {}),
      ...(typeof r.question === "string" ? { question: r.question } : {}),
    };
  }

  // accounts.py (the accounts on this computer, or host's through remote.py
  // --accounts): its whole answer
  async accounts(args: string[], host?: string, timeoutMs = 90000): Promise<Record<string, any>> {
    const argv = host ? ["remote.py", "--accounts", host, ...args] : ["accounts.py", ...args];
    return (await this.json(argv, timeoutMs)) ?? { ok: false, message: "the helper gave no answer" };
  }

  // The chat tab's helper (pane.py): a chat's conversation, a reply to it,
  // an answer to its permission prompt, its review; its whole answer
  async pane(args: string[], timeoutMs = 90000): Promise<Record<string, any>> {
    return (await this.json(["pane.py", ...args], timeoutMs)) ?? { ok: false, message: "the helper gave no answer" };
  }

  // A picture pasted in a chat's tab (base64 of type mime), saved where the
  // widget keeps pasted pictures (jump.py --save-image): its file, or why not
  async saveImage(mime: string, data: string): Promise<{ path?: string; message: string }> {
    const r = await this.json(["jump.py", "--save-image", mime], 30000, data);
    return r?.ok && typeof r.path === "string" ? { path: r.path, message: "" } : { message: String(r?.message ?? "the helper gave no answer") };
  }

  // A region of the screen you pick (jump.py --screenshot), saved as a picture; a
  // file dropped on a reply (jump.py --attach): a picture saved as one, a file named where it is
  async screenshot(): Promise<{ path?: string; message: string }> {
    const r = await this.json(["jump.py", "--screenshot"], 300000);
    return r?.ok && typeof r.path === "string" ? { path: r.path, message: "" } : { message: String(r?.message ?? "the helper gave no answer") };
  }

  // Dictation (dictate.py): --status, --start ID, --stop ID [--language L], --cancel ID, --get-model NAME
  async dictate(args: string[], timeoutMs = 30000): Promise<Record<string, any>> {
    return (await this.json(["dictate.py", ...args], timeoutMs)) ?? { ok: false, message: "the helper gave no answer" };
  }

  async attach(path: string): Promise<{ path?: string; picture?: boolean; message: string }> {
    const r = await this.json(["jump.py", "--attach", path], 30000);
    return r?.ok && typeof r.path === "string" ? { path: r.path, picture: r.picture === true, message: "" }
      : { message: String(r?.message ?? "the helper gave no answer") };
  }

  // A PNG to the clipboard (jump.py --copy-image)
  async copyImage(path: string): Promise<{ ok: boolean; message: string }> {
    const r = await this.json(["jump.py", "--copy-image", path], 15000);
    return { ok: !!r?.ok, message: String(r?.message ?? "the helper gave no answer") };
  }

  // That picture copied to an SSH host (remote.py --put-image): the copy's path there
  async putImage(host: string, path: string): Promise<{ path?: string; message: string }> {
    const r = await this.json(["remote.py", "--put-image", host, path], 120000);
    return r?.ok && typeof r.path === "string" ? { path: r.path, message: "" } : { message: String(r?.message ?? "the helper gave no answer") };
  }

  // What a chat changed (jump.py --changes --list): the files, with copies of
  // what they were before it (or before its last turn)
  async changes(chatId: string, profileDir: string, turn: boolean, extra: string[] = []): Promise<{ message: string; comparison?: Comparison }> {
    const args = ["jump.py", "--changes", chatId, ...(profileDir ? ["--profile", profileDir] : []), ...(turn ? ["--turn"] : []), "--list", ...extra];
    const r = await this.json(args, 60000);
    if (!r) return { message: "the helper gave no answer" };
    const message = String(r.message ?? r.error ?? "");
    return r.ok && isComparison(r.comparison) ? { message, comparison: r.comparison } : { message: message || "no answer" };
  }

  // theme: the sound theme when the desktop keeps it elsewhere (GNOME)
  sound(sound: string, volume: number, theme?: string): void {
    const args = ["-I", this.script("notify_sound.py"), sound, "--volume", String(volume)];
    if (theme) args.push("--theme", theme);
    void runProcess(this.python(), args, { timeoutMs: 30000 });
  }

  private async json(argv: string[], timeoutMs: number, input?: string): Promise<Record<string, any> | null> {
    const [name, ...args] = argv;
    const r = await runProcess(this.python(), ["-I", this.script(name), ...args], { timeoutMs, input });
    if (r.spawnError || r.timedOut) return { ok: false, message: r.timedOut ? "timed out" : r.spawnError!.message };
    try {
      return JSON.parse(r.stdout.trim().split("\n").pop() || "");
    } catch {
      return { ok: false, message: lastLine(r.stderr) || "the helper gave no answer" };
    }
  }
}
