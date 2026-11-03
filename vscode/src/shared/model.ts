// The dashboard's derived values, shared by the extension (status bar,
// notifications) and the webview. Ported from the widget's main.qml.

import type { Agent, ChangeSummary, ChatRef, ChatStats, ClaudeCodeInfo, ContainerInfo, ContainerNote, Counts, Group, HostState, KeptChat, Limits, LimitWindow, LiveView, Memory, Overall, Overlap, PlanItem, ProjectRow, ProjectsData, QueuedTask, RecentChat, ReopenIn, Session, SharedPointer, SshUsage, StatsDay, Status, Stop, TaskProgress, Tokens, UsageStats, ViewState } from "./types";

// This computer's accounts and the hosts', for the counts, the badge and
// what needs you. A host whose last check failed still shows what it said
// before (dimmed), and at start what it said last time until its first check
// answers, but that doesn't count here: you can't reach its chats.
export function allGroups(status: Status | null, hosts: HostState[]): Group[] {
  const out: Group[] = status ? status.groups.slice() : [];
  for (const h of hosts) {
    if (h.result && !h.error && !h.cached) for (const g of h.result.groups) out.push({ ...g, host: h.name });
  }
  return out;
}

// ---------------------------------------------------------------- the chat a click means

// What the webview says when you click a chat (the extension does the work)
export function chatRefOf(s: Session, host?: string): ChatRef {
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
    state: s.state,
    tmux: !!s.tmux,
    jobId: s.jobId,
    openCommand: s.openCommand ?? null,
    stopCommand: s.stopCommand ?? null,
    vscodeTerminal: s.vscodeTerminal ?? null,
    // a fork of a shared chat is a chat of its own
    shared: !!s.shared && !s.shared.forkOf,
    plan: s.plan ? { slug: s.plan.slug, path: s.plan.path } : null,
  };
}

export function recentRef(c: RecentChat, host?: string): ChatRef {
  return {
    host,
    key: c.key,
    sessionId: c.sessionId,
    chatId: c.sessionId,
    profileDir: c.profileDir,
    name: c.name,
    cwd: c.cwd,
    kind: "chat",
    openCommand: c.openCommand ?? null,
    shared: c.shared,
  };
}

export function sharedRef(p: SharedPointer, host?: string): ChatRef {
  return {
    host,
    key: p.key,
    sessionId: p.sessionId,
    chatId: p.sessionId,
    profileDir: p.profileDir,
    name: p.name,
    openCommand: p.openCommand ?? null,
    shared: true,
  };
}

// The chat a click from the webview means, as the extension knows it now:
// found by host and row key, so the commands it runs are its own (from the
// status), never ones the page sent. null when it's gone (or never was). A
// shared chat's pointer (`<row key>/shared`) is the chat's own row, listed
// under the account it's used on: a click on it does what one on its name does.
export function findChatRef(status: Status | null, hosts: HostState[], host: unknown, key: unknown): ChatRef | null {
  if (typeof key !== "string" || !key || (host !== undefined && host !== null && typeof host !== "string")) return null;
  const where = host ? hosts.find((h) => h.name === host)?.result : status;
  for (const g of where?.groups ?? []) {
    const h = host ? (host as string) : undefined;
    for (const s of g.sessions ?? []) if (s.key === key) return chatRefOf(s, h);
    for (const c of [...(g.recent ?? []), ...(g.starred ?? [])]) if (c.key === key) return recentRef(c, h);
    for (const p of g.sharedHere ?? [])
      if (p.key === key)
        return (key.endsWith("/shared") ? findChatRef(status, hosts, host, key.slice(0, -"/shared".length)) : null) ?? sharedRef(p, h);
  }
  return null;
}

// A host's answer on this computer's clock: its times ("since", "last
// active", resets) are its own clock's, which may be off from ours
export function toLocalClock(result: Status, offset: number): Status {
  if (Math.abs(offset) < 5000) return result; // network delay, or close enough
  const at = (t: unknown) => (typeof t === "number" ? t + offset : t);
  const shift = (o: Record<string, unknown> | null | undefined, keys: string[]) => {
    if (o) for (const k of keys) o[k] = at(o[k]);
  };
  const out = JSON.parse(JSON.stringify(result)) as Status;
  out.generatedAt = at(out.generatedAt) as number;
  for (const g of out.groups ?? []) {
    for (const s of g.sessions ?? []) {
      shift(s as unknown as Record<string, unknown>, ["since", "startedAt"]);
      shift(s.peek as unknown as Record<string, unknown>, ["at"]);
      shift(s.peek?.recap as unknown as Record<string, unknown>, ["at"]);
      shift(s.stopped as unknown as Record<string, unknown>, ["at", "resetsAt"]);
      shift(s.movedFrom as unknown as Record<string, unknown>, ["at"]);
      shift(s.plan as unknown as Record<string, unknown>, ["updatedAt"]);
      shift(s.stats as unknown as Record<string, unknown>, ["startedAt", "lastAt"]);
      shift(s.review as unknown as Record<string, unknown>, ["editedAt"]);
      shift(s.review?.tests as unknown as Record<string, unknown>, ["at"]);
      for (const a of s.agents?.tree ?? []) shift(a as unknown as Record<string, unknown>, ["started", "updated"]);
    }
    for (const c of [...(g.recent ?? []), ...(g.starred ?? [])]) {
      shift(c as unknown as Record<string, unknown>, ["lastActive"]);
      shift(c.recap as unknown as Record<string, unknown>, ["at"]);
      shift(c.stopped as unknown as Record<string, unknown>, ["at", "resetsAt"]);
      shift(c.review as unknown as Record<string, unknown>, ["editedAt"]);
      shift(c.review?.tests as unknown as Record<string, unknown>, ["at"]);
    }
    for (const c of g.sharedHere ?? []) shift(c as unknown as Record<string, unknown>, ["lastActive", "since"]);
    for (const p of [...(g.plans ?? []), ...(g.starredPlans ?? [])]) shift(p as unknown as Record<string, unknown>, ["updatedAt"]);
    for (const m of g.memories ?? []) shift(m as unknown as Record<string, unknown>, ["updatedAt"]);
    if (g.limits) {
      shift(g.limits as unknown as Record<string, unknown>, ["updatedAt"]);
      for (const w of g.limits.windows ?? []) {
        shift(w as unknown as Record<string, unknown>, ["resetsAt"]);
        shift(w.forecast as unknown as Record<string, unknown>, ["fullAt"]);
      }
    }
  }
  return out;
}

// A chat with a process of its own can be stopped too (besides background
// sessions), whatever it's doing: in a terminal its claude quits (the chat is
// kept), in a Claude Code panel the tab shows it as interrupted and goes on with
// the next message (the widget's backend: stopping and interrupting chats).
export function canEndChat(s: { kind?: string; pid?: number | null; state?: string; entrypoint?: string }): boolean {
  return s.kind === "interactive" && s.pid != null;
}

// A chat that's working or waiting has something to interrupt (Ctrl+C), where
// it can be pressed: in a terminal of this window, or a tmux pane
export function hasTurn(s: { state?: string }): boolean {
  return s.state === "working" || s.state === "waiting";
}

// The claude command is on the machine a status came from (when unsure: no
// answer yet, or an older backend, it counts as there)
export function cliInstalled(status: Pick<Status, "cli"> | null | undefined): boolean {
  return status?.cli?.installed !== false;
}

// The status of the machine a chat is on: this computer's, or an SSH host's
// last good answer
export function machineStatus(state: Pick<ViewState, "status" | "hosts">, host?: string): Status | null | undefined {
  return host ? state.hosts.find((h) => h.name === host)?.result : state.status;
}

// The accounts a chat can move between: those of its own machine (this
// computer, or the SSH host it's on), when that machine can share
export function shareAccounts(status: Pick<Status, "canShare" | "groups"> | null | undefined): Group[] {
  return status?.canShare ? status.groups.filter((g) => !!g.shareProfile) : [];
}

// The Claude Code extension can reopen this account's chats: it's in this
// window, on the account its settings give it (an SSH host's: the host's
// ~/.claude, through Remote-SSH)
export function claudeCodeHere(g: Pick<Group, "host" | "vscodeHere" | "profileKeys">, info: ClaudeCodeInfo): boolean {
  if (!info.available) return false;
  return g.host ? !!g.vscodeHere : !!info.profileKey && (g.profileKeys ?? []).includes(info.profileKey);
}

// Where recent chats reopen: in a Claude Code panel when you picked that, or
// when there's no claude command for a terminal
export function reopensInClaudeCode(prefer: ReopenIn, cliHere: boolean, codeHere: boolean): boolean {
  return codeHere && (prefer === "claudeCode" || !cliHere);
}

// A chat running in a terminal (VS Code's or another, here or on an SSH
// host) can move to a Claude Code panel when Claude Code is on its account
// (codeHere): Claude quits in the terminal and the chat reopens in the tab
export function canMoveToClaudeCode(s: { kind?: string; pid?: number | null; state?: string; entrypoint?: string }, codeHere: boolean): boolean {
  return codeHere && canEndChat(s) && s.entrypoint !== "claude-vscode";
}

// The recent chats' switch: what each half does, or why it's greyed out
export function terminalReopenHint(host: string | undefined, cliHere: boolean): string {
  if (!cliHere)
    return `Claude Code's claude command isn't installed ${host ? hostWhere(host) : "here"}: it isn't on PATH, in ~/.local/bin, npm's or nvm's folders, nor on the login shell's PATH.`;
  if (containerOf(host)) return `Reopens the chat in ${hostLabel(host!)} in a terminal (claude --resume, in the container).`;
  return host ? `Reopens the chat on ${host} in a terminal (ssh, claude --resume).` : "Reopens the chat in a terminal (claude --resume).";
}

export function claudeCodeReopenHint(g: Pick<Group, "host" | "vscodeHere" | "profileKeys" | "title">, info: ClaudeCodeInfo, groups: Group[]): string {
  if (!info.available) return "The Claude Code extension isn't installed or enabled in this window.";
  if (g.host)
    return g.vscodeHere
      ? `Opens the chat in a Claude Code panel, in a VS Code window connected to ${hostLabel(g.host)} (${containerOf(g.host) ? "Dev Containers" : "Remote-SSH"}) on the chat's folder.`
      : `Claude Code ${hostWhere(g.host)} runs on another account: a new chat in its Claude Code chat tab on this one switches it, in a window connected to ${hostLabel(g.host)}.`;
  if (!claudeCodeHere(g, info)) {
    const on = groups.find((o) => !o.host && !!info.profileKey && (o.profileKeys ?? []).includes(info.profileKey));
    return `Claude Code runs on ${on ? on.title : info.profileKey || "another account"}, not ${g.title}: switch it with “Talpy Den: Default Claude Account…” (or the link in the hover of Talpy Den's status bar item) to reopen this account's chats there.`;
  }
  return "Opens the chat in a Claude Code panel, in the VS Code window that has the chat's folder (opened if it isn't).";
}

export function countStates(groups: Group[]): Counts {
  const c: Counts = { waiting: 0, working: 0, idle: 0, done: 0, limit: 0 };
  for (const g of groups) for (const s of g.sessions) if (atLimit(s)) c.limit += 1; else if (s.state in c) c[s.state] += 1;
  return c;
}

// A chat a usage limit stopped, until it resets (whether a process still has
// it open or not): it waits for the limit, not for you
export function atLimit(s: Pick<Session, "state" | "stopped">): boolean {
  return stopOf(s) === "limit";
}

// What stopped a chat's turn before it was through, while that holds: a usage
// limit (until it resets) or an expired login, else ""
export function stopOf(s: Pick<Session, "state" | "stopped">): Stop["kind"] | "" {
  return (s.state === "idle" || s.state === "done") && s.stopped && !s.stopped.over ? s.stopped.kind : "";
}

// The focus view (webview FocusView.tsx): the chats waiting for you (the one
// waiting longest first), the ones that finished a turn you haven't opened
// yet (finished: Dashboard's, as the widget's; newest first), the ones at
// work (longest first), the rest counted, and each account's 5-hour usage.
// A chat listed twice counts once, its first (most urgent) row.
export interface FocusItem {
  key: string;
  session: Session;
  group: Group;
}
export interface FocusLists {
  needs: FocusItem[];
  finished: FocusItem[];
  working: FocusItem[];
  rest: { idle: number; done: number; limit: number };
  usage: { name: string; pct: number }[];
}
export function focusLists(groups: Group[], finished: readonly string[] = []): FocusLists {
  const out: FocusLists = { needs: [], finished: [], working: [], rest: { idle: 0, done: 0, limit: 0 }, usage: [] };
  const seen = new Set<string>();
  const unopened = new Set(finished);
  for (const g of groups) {
    const five = g.limits?.windows.find((w) => w.key === "five_hour");
    if (five) out.usage.push({ name: (g.host ? g.host + ": " : "") + g.title, pct: five.pct });
    for (const s of g.sessions) {
      const key = petKeyOf(s, g.host);
      if (seen.has(key)) continue;
      seen.add(key);
      const item = { key, session: s, group: g };
      if (s.state === "waiting") out.needs.push(item);
      else if (s.state === "working") out.working.push(item);
      else if (unopened.has(key)) out.finished.push(item);
      else if (atLimit(s)) out.rest.limit += 1;
      else out.rest[s.state === "idle" ? "idle" : "done"] += 1;
    }
  }
  const since = (i: FocusItem) => i.session.since ?? 0;
  out.needs.sort((a, b) => since(a) - since(b));
  out.working.sort((a, b) => since(a) - since(b));
  out.finished.sort((a, b) => since(b) - since(a));
  return out;
}

export function overallState(groups: Group[], counts: Counts): Overall {
  if (counts.waiting) return "waiting";
  if (counts.working) return "working";
  // finished jobs kept for the record don't count as running
  return groups.some((g) => g.sessions.some((s) => (s.state === "idle" || s.state === "done") && s.pid !== null))
    ? "idle"
    : "none";
}

export function plural(n: number, one: string, many: string): string {
  return (n === 1 ? one : many).replace("%1", String(n));
}

// ---- containers: docker:NAME, podman:NAME, nerdctl:NAME (this computer's),
// ENGINE:NAME@HOST (on the SSH host HOST), picked and shown like SSH hosts
// (remote.py's ids)

export const CONTAINER_ID = /^(docker|podman|nerdctl):([A-Za-z0-9][A-Za-z0-9_.-]*)(?:@(.+))?$/;

// {engine, name, host} of a container's id ("" host: this computer's), or null for an SSH host
export function containerOf(id: string | undefined): { engine: string; name: string; host: string } | null {
  const m = CONTAINER_ID.exec(id ?? "");
  return m ? { engine: m[1], name: m[2], host: m[3] ?? "" } : null;
}

// How an SSH host or a container is named: lab, web, or web on lab
export function hostLabel(id: string): string {
  const c = containerOf(id);
  return !c ? id : c.host ? `${c.name} on ${c.host}` : c.name;
}

// on lab, in web, in web on lab
export function hostWhere(id: string): string {
  return containerOf(id) ? `in ${hostLabel(id)}` : `on ${id}`;
}

// "stopped 3 days ago", "stopped 5h 10m ago", "stopped"
export function containerStopped(c: Pick<ContainerInfo, "activeAt">, now: number): string {
  const age = c.activeAt ? Math.max(0, now - c.activeAt) : -1;
  return age < 0 ? "stopped" : age >= 2 * 86400000 ? plural(Math.floor(age / 86400000), "stopped %1 day ago", "stopped %1 days ago")
    : `stopped ${duration(age)} ago`;
}

// What the hosts picker says of a container: "podman · ubuntu:22.04 · stopped 3 days ago"
export function containerDescription(c: ContainerInfo, now: number): string {
  const parts = [c.folderShort ? c.folderShort : c.engine + (c.image ? ` · ${c.image}` : "")];
  if (!c.running) parts.push(containerStopped(c, now));
  if (c.sharesHome) parts.push("shares your home folder");
  return parts.join(" · ");
}

// A picked container's header line: "podman · ubuntu:22.04", or its dev container's folder (· on lab)
export function containerDetail(id: string, info: ContainerInfo | null | undefined): string {
  const c = containerOf(id);
  if (!c) return "";
  const parts = [info?.folderShort ? info.folderShort : c.engine + (info?.image ? ` · ${info.image}` : "")];
  if (c.host) parts.push(`on ${c.host}`);
  return parts.join(" · ");
}

// The hosts picker's container sections: this computer's, then each
// connected SSH host's (and a host's whose container you picked); a picked
// container that isn't listed is still there, to unpick it
export function containerPlaces(
  here: ContainerInfo[],
  notes: ContainerNote[],
  hostContainers: Record<string, { containers?: ContainerInfo[]; notes?: ContainerNote[]; error?: string }>,
  connected: string[],
  picked: string[],
  days: number,
  now: number,
): { host: string; title: string; items: { id: string; label: string; description: string; picked: boolean }[]; notes: string[]; empty: string }[] {
  const none = days > 0 ? plural(days, "No containers active in the last day", "No containers active in the last %1 days") : "No running containers";
  const pickedOf = (host: string) => picked.filter((id) => containerOf(id)?.host === host);
  const hosts = connected.concat(
    picked.map((id) => containerOf(id)?.host ?? "").filter((h, i, all) => h && all.indexOf(h) === i && !connected.includes(h)),
  );
  const places = [{ host: "", title: "Containers on this computer", list: here, notes }];
  for (const host of hosts) {
    const kept = connected.includes(host) ? hostContainers[host] ?? {} : {};
    places.push({ host, title: `Containers on ${host}`, list: kept.containers ?? [], notes: [...(kept.notes ?? []), ...(kept.error ? [{ message: kept.error }] : [])] });
  }
  return places.map((place) => {
    const listed = place.list.filter((c) => c && c.id);
    const items = listed.map((c) => ({ id: c.id, label: c.name, description: containerDescription(c, now), picked: picked.includes(c.id) }));
    for (const id of pickedOf(place.host)) if (!listed.some((c) => c.id === id)) items.push({ id, label: containerOf(id)!.name, description: "", picked: true });
    const messages = place.notes.map((n) => n.message);
    return { host: place.host, title: place.title, items, notes: messages, empty: items.length || messages.length ? "" : none };
  });
}

// The hero's headline: the most important thing on the dashboard
// hostsAnswered: SSH hosts' chats count while this computer's status is missing
export function headlineText(state: Pick<ViewState, "status" | "errorText">, counts: Counts, hostsAnswered = false): string {
  if (!state.status && !hostsAnswered && state.errorText) return "Status unavailable";
  if (!state.status && !hostsAnswered) return "Looking for your chats…";
  if (counts.waiting) return plural(counts.waiting, "%1 chat needs you", "%1 chats need you");
  if (counts.working) return plural(counts.working, "%1 chat working", "%1 chats working");
  if (counts.idle) return plural(counts.idle, "Your turn in %1 chat", "Your turn in %1 chats");
  if (counts.limit) return plural(counts.limit, "%1 chat waits for its usage limit", "%1 chats wait for their usage limit");
  if (counts.done) return plural(counts.done, "%1 finished chat to look at", "%1 finished chats to look at");
  return "All quiet";
}

export function summaryText(counts: Counts): string {
  const parts: string[] = [];
  if (counts.waiting) parts.push(plural(counts.waiting, "%1 needs input", "%1 need input"));
  if (counts.working) parts.push(`${counts.working} working`);
  if (counts.idle) parts.push(`${counts.idle} idle`);
  if (counts.limit) parts.push(`${counts.limit} at the usage limit`);
  if (counts.done) parts.push(`${counts.done} done`);
  return parts.length ? parts.join(" · ") : "No chats running";
}

export function agentsRunning(groups: Group[]): number {
  let n = 0;
  for (const g of groups) for (const s of g.sessions) if (s.agents && s.state !== "done") n += s.agents.running;
  return n;
}

// Talpy's mood for the whole dashboard (talpy.mjs MOODS)
export function heroMood(state: Pick<ViewState, "status" | "errorText">, overall: Overall, groups: Group[]): string {
  const answered = !!state.status || groups.length > 0; // a host's chats count too
  if (!answered && state.errorText) return "error";
  if (!answered) return "loading";
  if (overall === "waiting") return "needs";
  if (overall === "working") return agentsRunning(groups) > 0 ? "agents" : "working";
  if (overall === "idle") return "idle";
  return "done";
}

// Plan usage is the account's, whichever machine it's used on. An account on
// several (this computer and SSH hosts: the same id) shows it once, where
// it's listed first, with the newest numbers of them all ("once"); "all"
// shows each machine's own, "none" no host's. As the widget (main.qml: withUsage).
export function shareUsage(
  status: Status | null,
  hosts: HostState[],
  mode: SshUsage,
): { status: Status | null; hosts: HostState[] } {
  if (mode === "all") return { status, hosts };
  const owners = new Map<string, { host: string; limits: Limits | null; from: string }>();
  const note = (g: Group, host: string) => {
    let o = owners.get(g.id);
    if (!o) owners.set(g.id, (o = { host, limits: null, from: "" }));
    if (g.limits && (!o.limits || g.limits.updatedAt > o.limits.updatedAt)) {
      o.limits = g.limits;
      o.from = host;
    }
  };
  for (const g of status?.groups ?? []) note(g, "");
  for (const h of hosts) for (const g of h.result?.groups ?? []) note(g, h.name);
  // limitsHidden where it shows elsewhere (or no host's does), limitsFrom
  // when the numbers come from another machine
  const shown = (g: Group, host: string): Group => {
    const o = owners.get(g.id);
    if (host && (mode === "none" || (o && o.host !== host))) return { ...g, limits: null, limitsHidden: true, accountLimits: o ? o.limits : g.limits };
    return !o || o.from === host ? g : { ...g, limits: o.limits, limitsFrom: o.from };
  };
  return {
    status: status && { ...status, groups: status.groups.map((g) => shown(g, "")) },
    hosts: hosts.map((h) => (h.result ? { ...h, result: { ...h.result, groups: h.result.groups.map((g) => shown(g, h.name)) } } : h)),
  };
}

// An account's plan usage, also where it isn't shown (shareUsage)
function usageOf(g: Pick<Group, "limits" | "accountLimits">): Limits | null {
  return g.limits ?? g.accountLimits ?? null;
}

// The account VS Code's Claude runs on in this window: this computer's, or
// in a Remote-SSH window the host's (what its VS Code server's settings say)
export function claudeCodeGroup(groups: Group[], hosts: HostState[], info: ClaudeCodeInfo): Group | undefined {
  const current = hosts.find((h) => h.current);
  return current
    ? groups.find((g) => g.host === current.name && g.vscodeHere)
    : groups.find((g) => !g.host && claudeCodeHere(g, info));
}

// The 5-hour window shown next to the status bar item: the account VS Code's
// Claude runs on (preferId, from claudeCodeGroup: its numbers may show on
// another machine's copy, shareUsage), else the account with an active
// session, else the one with the freshest numbers.
export function panelWindow(groups: Group[], preferId?: string): { window: LimitWindow; group: Group } | null {
  const preferred = preferId ? groups.find((g) => g.id === preferId && g.limits?.windows.length) : undefined;
  if (preferred) return { window: preferred.limits!.windows[0], group: preferred };
  let best: { window: LimitWindow; group: Group } | null = null;
  let bestScore = -1;
  for (const g of groups) {
    if (!g.limits || !g.limits.windows.length) continue;
    const active = g.sessions.some((s) => s.state === "working" || s.state === "waiting");
    const score = (active ? 1e15 : 0) + (Number.isFinite(g.limits.updatedAt) ? g.limits.updatedAt : 0);
    if (score > bestScore) {
      bestScore = score;
      best = { window: g.limits.windows[0], group: g };
    }
  }
  return best;
}

export function maxFiveHour(groups: Group[]): number {
  let m = 0;
  for (const g of groups) for (const w of g.limits ? g.limits.windows : []) if (w.key === "five_hour") m = Math.max(m, w.pct);
  return m;
}

// "work · Team", or "lab: work" for an SSH host's account
// Why NAME can't be a new account (~/.claude-NAME; accounts.py says the same
// and checks again), or "". folders: the accounts' folders now (~/.claude-work)
export function accountNameProblem(name: string, folders: string[]): string {
  if (!name) return "Give the account a name";
  if (name === "default" || name === "main") return `${name} is taken: main is what ~/.claude is called, default marks the default account`;
  if (!/^[A-Za-z][A-Za-z0-9_-]{0,31}$/.test(name)) return "Up to 32 letters, digits, - and _, starting with a letter";
  if (folders.includes(`~/.claude-${name}`)) return `There's an account called ${name} already`;
  return "";
}

export function groupLabel(g: Group): string {
  return g.host ? `${g.host}: ${g.name}` : g.name;
}

// Accounts close to their 5-hour limit, e.g. "work: 100% of the 5-hour limit!"
export function highUsageText(groups: Group[]): string {
  const parts: string[] = [];
  for (const g of groups)
    for (const w of g.limits ? g.limits.windows : [])
      if (w.key === "five_hour" && w.pct >= 90) parts.push(`${groupLabel(g)}: ${Math.round(w.pct)}% of the 5-hour limit!`);
  return parts.join(" ");
}

// A chat's key: its account and conversation, so its pet, its notifications
// and whether you've seen it stay the same while its row changes (e.g. a
// background session's row from running to finished, …/live to …/job). A
// chat shared with two accounts is two chats here.
export function petKeyOf(session: Pick<Session, "sessionId" | "key"> & { chatId?: string; profileDir?: string }, host?: string): string {
  return `${host ? `ssh:${host}|` : ""}${session.profileDir ?? ""}/${session.chatId || session.sessionId || session.key}`;
}

export function firstWaiting(groups: Group[]): { session: Session; group: Group } | null {
  for (const g of groups) for (const s of g.sessions) if (s.state === "waiting") return { session: s, group: g };
  return null;
}

export function reasonText(reason: string): string {
  switch (reason) {
    case "permission":
      return "Asks for permission";
    case "question":
      return "Has a question for you";
    case "network access":
      return "Asks for network access";
    case "goal approval":
      return "Proposes a goal";
    case "":
      return "Waiting for you";
    default:
      return reason;
  }
}

export function duration(ms: number): string {
  const m = Math.max(0, Math.round(ms / 60000));
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ${m % 60}m`;
  return `${Math.floor(h / 24)}d ${h % 24}h`;
}

export function resetText(w: LimitWindow, now: number): string {
  if (w.reset) return "reset";
  if (!w.resetsAt) return "";
  // The last minute reads "<1m": a rounded "0m" looked stuck
  return `resets in ${w.resetsAt - now < 60000 ? "<1m" : duration(w.resetsAt - now)}`;
}

export function stateText(s: Pick<Session, "state" | "reason" | "since"> & { stopped?: Stop | null }, now: number): string {
  const since = s.since ? ` · ${duration(now - s.since)}` : "";
  const reason = s.reason ? ` · ${s.reason}` : "";
  if (s.stopped && (s.state === "idle" || s.state === "done")) {
    if (s.stopped.kind === "login") return "Login expired";
    if (s.stopped.over) return "Limit reset · go on";
    return s.stopped.resetsAt
      ? `Limit · resets in ${s.stopped.resetsAt - now < 60000 ? "<1m" : duration(s.stopped.resetsAt - now)}`
      : "Hit a usage limit";
  }
  switch (s.state) {
    case "waiting":
      return "Needs input" + reason;
    case "working":
      return "Working" + reason + since;
    case "done":
      return (s.reason === "failed" ? "Failed" : s.reason === "stopped" ? "Stopped" : "Done") + since;
    default:
      return "Idle" + since;
  }
}

// (the unit by what it rounds to: 999,960 is "1.0M", not "1000.0k")
export function formatTokens(n: number): string {
  if (n >= 999.95e6) return (n / 1e9).toFixed(1) + "B";
  if (n >= 999.95e3) return (n / 1e6).toFixed(1) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1) + "k";
  return String(n);
}

// An account's token line: today's and the week's totals, each with its output
// (the widget's words; the models are in its tooltip)
export function tokensText(t: Tokens): string {
  return (
    `Tokens today ${formatTokens(t.today.total)} (${formatTokens(t.today.output)} out)` +
    ` · 7 days ${formatTokens(t.week.total)} (${formatTokens(t.week.output)} out)`
  );
}

// The dim line under an account's plan usage bars: how old the numbers are, and
// the host they're from when another machine's are newer (shareUsage); a
// fetch on its way (Refresh's, or while a chat works: fetchAt) says so
export function planUsageText(limits: Limits, from: string, now: number, fetchAt?: number | null): string {
  if (fetchingUsage(limits, now, fetchAt)) return "Fetching the plan usage…";
  if (!Number.isFinite(limits.updatedAt)) return "";
  const on = from ? `, on ${from}` : "";
  return now - limits.updatedAt < 60000 ? `Plan usage updated just now${on}` : `Plan usage as of ${duration(now - limits.updatedAt)} ago${on}`;
}

// A fetch of an account's plan usage started in the last 70 s, its numbers not in yet
export function fetchingUsage(limits: Limits | null | undefined, now: number, fetchAt?: number | null): boolean {
  return !!fetchAt && now - fetchAt < 70000 && (!limits || limits.updatedAt < fetchAt);
}

export function ago(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000));
  if (s < 60) return "just now";
  return `${duration(ms)} ago`;
}

// "high" ≥ 90 %, "medium" ≥ 70 %, else "low" (red / orange / accent)
export function usageLevel(pct: number): "high" | "medium" | "low" {
  return pct >= 90 ? "high" : pct >= 70 ? "medium" : "low";
}

// The same quoting as Python's shlex.quote, so commands built here match the
// backend's.
export function shellQuote(s: string): string {
  if (s === "") return "''";
  if (/^[\w@%+=:,./-]+$/.test(s)) return s;
  return "'" + s.replace(/'/g, "'\"'\"'") + "'";
}

// Tooltip lines: the summary, then each account's limits
export function tooltipLines(groups: Group[], counts: Counts, hosts: HostState[]): string[] {
  const lines = [summaryText(counts)];
  for (const g of groups) {
    if (!g.limits) continue;
    lines.push(
      (g.host ? g.host + ": " : "") + g.title + ": " + g.limits.windows.map((w) => `${w.label} ${Math.round(w.pct)}%`).join(" · "),
    );
  }
  for (const h of hosts) if (h.error) lines.push(`${h.name}: not reachable`);
  return lines;
}

// ---------------------------------------------------------------- live mode

// A running chat's live view (this computer's; views: by session id), or null
export function liveOf(s: Pick<Session, "pid" | "sessionId">, views: Record<string, LiveView> | undefined): LiveView | null {
  return liveMatch(s, views ? views[s.sessionId] : undefined);
}

// v, if it's the running chat's (its process's, not over)
export function liveMatch(s: Pick<Session, "pid">, v: LiveView | undefined): LiveView | null {
  return s.pid && v && (!v.pid || v.pid === s.pid) && v.state !== "ended" ? v : null;
}

// The newest of each running chat's views: the rows' (a check) and those
// the extension followed since (known); only the chats listed are kept
export function liveFromRows(groups: Group[], known: Record<string, LiveView>): Record<string, LiveView> {
  const out: Record<string, LiveView> = {};
  for (const g of groups) {
    for (const s of g.sessions) {
      if (!s.pid) continue;
      const mine = known[s.sessionId];
      const row = s.live ? { ...s.live, sessionId: s.sessionId, pid: s.pid } : null;
      const best = mine && (!row || (mine.at || 0) >= (row.at || 0)) ? mine : row;
      if (best) out[s.sessionId] = best;
    }
  }
  return out;
}

// views with the newer ones of these in (a view that ended goes); null: nothing new
export function withLive(views: Record<string, LiveView>, more: LiveView[]): Record<string, LiveView> | null {
  let next: Record<string, LiveView> | null = null;
  for (const v of more) {
    const id = v.sessionId;
    const old = id ? views[id] : undefined;
    if (!id || (old && (old.at || 0) >= (v.at || 0))) continue;
    next = next ?? { ...views };
    if (v.state === "ended") delete next[id];
    else next[id] = v;
  }
  return next;
}

// What a working chat does now: its live step when that's newer than what
// the last check read from its transcript (an edit with the lines it added
// and removed: "Edit: parser.py +12 −3"), else that
export function doingText(s: Pick<Session, "peek">, live: LiveView | null): string {
  const peek = s.peek;
  if (live && live.doing && (live.at || 0) >= (peek?.at || 0)) {
    const main = (live.steps || []).filter((st) => !st.agent);
    const last = main.length ? main[main.length - 1] : null;
    const counts = last && last.text === live.doing && (last.add || last.del) ? ` +${last.add || 0} −${last.del || 0}` : "";
    return live.doing + counts;
  }
  return peek?.activity || "";
}

// The ticker under the big Talpy: what each working chat does now
export interface TickerItem {
  key: string;
  name: string;
  text: string;
  host?: string;
  session: Session;
}

export function tickerItems(groups: Group[], views: Record<string, LiveView> | undefined): TickerItem[] {
  const out: TickerItem[] = [];
  for (const g of groups) {
    for (const s of g.sessions) {
      if (s.state !== "working") continue;
      const text = doingText(s, g.host ? null : liveOf(s, views));
      if (text) out.push({ key: petKeyOf(s, g.host), name: s.name, text, host: g.host, session: s });
    }
  }
  return out;
}

// One item at a time: a chat's new step shows at once when it's that chat's
// turn; another chat's waits dwellMs behind the one on show; with nothing
// new, the chats take turns every turnMs
export class TickerTurns {
  shown: TickerItem | null = null;
  shownAt = 0;
  private queue: string[] = [];
  private noted = new Map<string, string>();
  private items: TickerItem[] = [];

  constructor(readonly dwellMs = 1500, readonly turnMs = 4000) {}

  private show(item: TickerItem, now: number): void {
    if (!this.shown || this.shown.key !== item.key) this.shownAt = now;
    this.shown = item;
  }

  private advance(now: number): void {
    while (this.queue.length) {
      const next = this.items.find((it) => it.key === this.queue[0]);
      this.queue.shift();
      if (next) return this.show(next, now);
    }
    if (!this.items.length) {
      this.shown = null;
      return;
    }
    const at = this.shown ? this.items.findIndex((it) => it.key === this.shown?.key) : -1;
    this.show(this.items[(at + 1) % this.items.length], now);
  }

  // New items (a check, a step): what shows now
  update(items: TickerItem[], now: number): TickerItem | null {
    this.items = items;
    const keys = new Set(items.map((it) => it.key));
    this.queue = this.queue.filter((k) => keys.has(k));
    for (const it of items) {
      if (this.noted.get(it.key) === it.text) continue;
      this.noted.set(it.key, it.text);
      if (this.shown?.key !== it.key && !this.queue.includes(it.key)) this.queue.push(it.key);
    }
    for (const k of [...this.noted.keys()]) if (!keys.has(k)) this.noted.delete(k);
    const mine = this.shown ? items.find((it) => it.key === this.shown?.key) : undefined;
    if (mine) this.show(mine, now); // (its own new step: at once)
    else this.advance(now);
    return this.shown;
  }

  // The clock: another chat's turn when it's due
  tick(now: number): TickerItem | null {
    const on = now - this.shownAt;
    if (this.items.length > 1 && ((this.queue.length && on >= this.dwellMs) || on >= this.turnMs)) this.advance(now);
    return this.shown;
  }
}

// ---------------------------------------------------------------- a peek at a chat

// The line under a chat's folder: what it's doing (working), what it needs
// (waiting), its result (a finished background session) or what Claude said
// last (your turn, done); live: its live view (live mode)
export function peekLine(
  s: Pick<Session, "state" | "detail" | "reason" | "peek" | "tasks"> & { stopped?: Stop | null },
  live: LiveView | null = null,
): { kind: "activity" | "needs" | "result" | "reply" | "recap" | "stopped"; text: string } | null {
  const peek = s.peek;
  if (s.state === "working") {
    const what = doingText(s, live) || s.tasks?.current || "";
    return what ? { kind: "activity", text: `▸ ${what}` } : null;
  }
  if (s.state === "waiting") return { kind: "needs", text: s.detail || peek?.activity || reasonText(s.reason) };
  // what stopped it (a usage limit), then a background session's result,
  // Claude's recap of the chat, what Claude said last
  if (s.stopped) return { kind: "stopped", text: stopText(s.stopped) };
  if (s.state === "done" && s.detail) return { kind: "result", text: s.detail };
  if (peek?.recap?.text) return { kind: "recap", text: `Recap: ${peek.recap.text.split("\n")[0]}` };
  return peek?.replyLine ? { kind: "reply", text: `Claude: ${peek.replyLine}` } : null;
}

// Something to unfold under the row: the last exchange, tasks or changed files
export function hasPeek(s: Pick<Session, "peek" | "tasks" | "changes"> & { stats?: Session["stats"] }): boolean {
  return !!(s.peek && (s.peek.prompt || s.peek.reply || s.peek.recap)) || !!s.tasks?.items.length || !!s.changes || !!s.stats;
}

// ---------------------------------------------------------------- what stopped a chat

// The line under a chat that something stopped
export function stopText(stop: Stop): string {
  if (stop.kind === "login") return "Claude's login expired. Log in again (/login), then tell it to go on.";
  if (stop.over) return "The limit it hit has reset: open it and tell Claude to go on.";
  return stop.text;
}

// Another account of the chat's machine with room left in the limit that
// stopped it (the most, where known), to continue it there; null when there's
// none, or the chat can't move now. Not for a chat open in a Claude Code panel
// (the tab would start it again here with your next message), one that's at
// work again, or a session that continues another chat (the one with the
// chat's own id would be ended, not this one).
export function handoverTarget(
  s: Pick<Session, "stopped" | "chatId" | "sessionId" | "pid" | "entrypoint" | "state" | "profileDir">,
  accounts: Group[],
): { title: string; shareProfile: string; pct: number | null; label: string } | null {
  const stop = s.stopped;
  if (!stop || stop.kind !== "limit" || stop.over || !s.chatId) return null;
  if (s.pid !== null && (s.entrypoint === "claude-vscode" || s.state !== "idle" || s.sessionId !== s.chatId)) return null;
  let best: { title: string; shareProfile: string; pct: number | null; label: string } | null = null;
  for (const g of accounts) {
    if (!g.shareProfile || (g.profileKeys ?? []).includes(s.profileDir)) continue;
    const w = usageOf(g)?.windows.find((x) => x.key === (stop.window || "five_hour"));
    const pct = w ? w.pct : null;
    if (pct !== null && pct >= 95) continue;
    if (!best || (pct !== null && (best.pct === null || pct < best.pct)))
      best = { title: g.title, shareProfile: g.shareProfile, pct, label: w ? w.label : "" };
  }
  return best;
}

// When a chat a usage limit stopped can go on by itself (a minute after the
// limit resets: jump.py --queue-continue), in ms, or 0. Not one open in
// VS Code's Claude (its tab can't be ended), nor one at work again.
export function goOnAt(s: { stopped?: Stop | null; chatId?: string; sessionId: string; pid?: number | null; entrypoint?: string; state?: string }): number {
  const stop = s.stopped;
  if (!stop || stop.kind !== "limit" || stop.over || !stop.resetsAt || !(s.chatId || s.sessionId)) return 0;
  if (s.pid != null && (s.entrypoint === "claude-vscode" || s.state !== "idle" || s.sessionId !== s.chatId)) return 0;
  return stop.resetsAt + 60_000;
}

// The queued task that goes on with this chat (here, or on host), or null
// (not a reply waiting for its turn to end: that isn't a go-on)
export function queuedChat(status: Pick<Status, "queue"> | null, chatId: string, host?: string): QueuedTask | null {
  return (status?.queue ?? []).find((t) => !!t.chat && t.chat === chatId && !t.afterTurn && (t.host || "") === (host || "")) ?? null;
}

// Whether a queued task's line would only repeat a row: a chat's go-on whose
// chat is one of the account's rows, which says Goes on at … (SessionRow's
// goingOn); not one that failed (its line says why) nor a reply for when a
// turn ends. The queue lists only what no row shows.
export function onItsRow(t: QueuedTask, g: Pick<Group, "host" | "sessions">, status: Pick<Status, "queue"> | null): boolean {
  if (!t.chat || t.afterTurn || t.error) return false;
  return (g.sessions ?? []).some((s) => {
    const id = s.chatId || s.sessionId;
    return id === t.chat && (goOnAt(s) > 0 || !!s.stopped) && queuedChat(status, id, g.host)?.id === t.id;
  });
}

// What a queued task does, in a line; a chat's go-on names the chat as it's
// called now (its row's name in the status of its machine), else as queued
export function queuedWhat(t: QueuedTask, status?: Pick<Status, "groups"> | null): string {
  const name = (t.chat ? chatNameNow(status, t.chat) : "") || t.name;
  return t.chat ? `Go on with “${name || t.chat.slice(0, 8)}”` : t.planTitle ? `Carry out “${t.planTitle}”${t.prompt ? `: ${t.prompt}` : ""}` : t.prompt;
}

// A chat's name as its row (or its line in Recent chats) has it now, or ""
export function chatNameNow(status: Pick<Status, "groups"> | null | undefined, chatId: string): string {
  for (const g of status?.groups ?? []) {
    const s = g.sessions.find((x) => x.chatId === chatId || x.sessionId === chatId);
    if (s?.name) return s.name;
  }
  for (const g of status?.groups ?? []) {
    const r = (g.recent ?? []).find((x) => x.sessionId === chatId);
    if (r?.name) return r.name;
  }
  return "";
}

export function clockText(ms: number): string {
  return new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/** A chat Claude moved to the background under a new id (its row's movedFrom), in a line, or "". */
export function movedText(s: Pick<Session, "movedFrom">): string {
  const m = s.movedFrom;
  if (!m) return "";
  return (m.at ? `Moved to the background at ${clockText(m.at)}: Claude goes on with it under a new id.`
    : "Moved to the background: Claude goes on with it under a new id.") + "\n\n";
}

function dayText(d: Date): string {
  return d.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" });
}

// The days a task can start on later: today and the next six
export function laterDays(now: Date): string[] {
  const out: string[] = [];
  for (let i = 0; i < 7; i++) out.push(i === 0 ? "Today" : i === 1 ? "Tomorrow" : dayText(new Date(now.getFullYear(), now.getMonth(), now.getDate() + i)));
  return out;
}

// When a task picked for later starts (ms): `day` days after now's date, at
// `clock` ("9", "930", "9:30", "14:30"); 0 for no time, or one that has passed
export function laterAt(day: number, clock: string, now: Date): number {
  const m = /^(\d{1,2})(?::?(\d{2}))?$/.exec(clock.trim());
  if (!m || +m[1] > 23 || +(m[2] ?? 0) > 59) return 0;
  const at = new Date(now.getFullYear(), now.getMonth(), now.getDate() + day, +m[1], +(m[2] ?? 0)).getTime();
  return at > now.getTime() ? at : 0;
}

// Days from now's date to ms's (0 today, 1 tomorrow)
function daysAway(ms: number, now: number): number {
  const d = new Date(ms);
  const t = new Date(now);
  return Math.round((new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime() - new Date(t.getFullYear(), t.getMonth(), t.getDate()).getTime()) / 86_400_000);
}

// When a queued task starts, in words: "14:30" today, "tomorrow 09:00", "Fri 24 Oct 09:00"
export function startText(ms: number, now: number): string {
  const days = daysAway(ms, now);
  return days <= 0 ? clockText(ms) : days === 1 ? `tomorrow ${clockText(ms)}` : `${dayText(new Date(ms))} ${clockText(ms)}`;
}

// When a usage limit resets, for the title of its "resets in …"
export function resetAtText(ms: number, now: number): string {
  const days = daysAway(ms, now);
  return days <= 0 ? `Resets at ${clockText(ms)}` : days === 1 ? `Resets tomorrow at ${clockText(ms)}` : `Resets on ${dayText(new Date(ms))} at ${clockText(ms)}`;
}

// The chat (of host: an SSH host or a container) that keeps going, or null:
// this computer's status lists them all, a host's too (kept here, they go on from here)
export function keptChat(status: Pick<Status, "keep"> | null | undefined, chatId: string, host?: string): KeptChat | null {
  return status?.keep?.find((k) => k.chat === chatId && (k.host || "") === (host || "")) ?? null;
}

// Kept chats and queued tasks of SSH hosts and containers that aren't shown
// (not picked, or containers while Show containers is off): they go on all
// the same, from here over ssh, so the list says so where the hosts go
// (UnseenLines): a kept chat with its queued go-on, then the other tasks
export interface UnseenItem {
  host: string;
  name: string;
  kept: KeptChat | null;
  task: QueuedTask | null;
}
export function unseenHostItems(status: Pick<Status, "keep" | "queue"> | null | undefined, shown: string[]): UnseenItem[] {
  const out: UnseenItem[] = [];
  const queue = status?.queue ?? [];
  for (const k of status?.keep ?? []) {
    if (!k.host || shown.includes(k.host)) continue;
    const task = queue.find((t) => t.chat === k.chat && (t.host || "") === k.host && !t.afterTurn) ?? null;
    out.push({ host: k.host, name: k.name || k.chat.slice(0, 8), kept: k, task });
  }
  for (const t of queue)
    if (t.host && !shown.includes(t.host) && !out.some((x) => x.task === t))
      out.push({ host: t.host, name: t.chat ? t.name || t.chat.slice(0, 8) : "", kept: null, task: t });
  return out;
}

// What a chat that keeps going does, for its tag's title
export function keptTitle(kept: KeptChat): string {
  return [
    "Keeps going until it's done: when a usage limit stops it, it goes on by itself in the background a minute after the limit resets, in the permission mode it had, and again after each later one, until a turn of it ends by itself. When a go-on doesn't take or its turn breaks off (the connection lost), it tries again a few times.",
    kept.error || kept.note,
    "Click to stop it keeping going (a go-on that's queued already stays).",
  ]
    .filter(Boolean)
    .join("\n\n");
}

// When the usage limit an account is at resets (the latest of its full
// windows, or of one at the usage cap, else of the chats a limit stopped), or null
export function limitReset(g: Pick<Group, "limits" | "accountLimits" | "sessions" | "cap">, now: number): { at: number; label: string } | null {
  let best: { at: number; label: string } | null = null;
  for (const w of usageOf(g)?.windows ?? []) if (w.pct >= 95 && w.resetsAt && (!best || w.resetsAt > best.at)) best = { at: w.resetsAt, label: w.label };
  if (g.cap && (!best || g.cap.resetsAt > best.at)) best = { at: g.cap.resetsAt, label: g.cap.label };
  if (!best)
    for (const s of g.sessions)
      if (s.stopped?.kind === "limit" && !s.stopped.over && s.stopped.resetsAt && (!best || s.stopped.resetsAt > best.at))
        best = { at: s.stopped.resetsAt, label: "" };
  return best && best.at > now ? best : null;
}

// An account's queued tasks (on this computer, or on its SSH host)
export function queuedFor(status: Pick<Status, "queue"> | null | undefined, g: Pick<Group, "host" | "profileKeys">): QueuedTask[] {
  return (status?.queue ?? []).filter((t) => (t.host || "") === (g.host || "") && (g.profileKeys ?? []).includes(t.profile));
}

// "Also changed by “Renames”: src/parser.py", one line per other chat
export function overlapText(overlaps: Overlap[]): string {
  return overlaps
    .map((o) => `Also changed by “${o.name}”${o.count > 1 ? ` (${o.count} files)` : ""}: ${o.files.join(", ")}${o.count > o.files.length ? " …" : ""}`)
    .join("\n");
}

// ---------------------------------------------------------------- permission mode

// A chat's permission mode as its tag says it ("" when it isn't known; the
// default is Claude's manual mode)
export function modeText(mode: string | null | undefined): string {
  switch (mode) {
    case "default":
      return "Manual mode";
    case "plan":
      return "Plan mode";
    case "acceptEdits":
      return "Accept edits";
    case "auto":
      return "Auto mode";
    case "bypassPermissions":
      return "Bypass permissions";
    case "dontAsk":
      return "Don't ask";
    case "":
    case null:
    case undefined:
      return "";
    default:
      return mode;
  }
}

export function modeHint(mode: string | null | undefined): string {
  switch (mode) {
    case "plan":
      return "Plan mode: Claude looks around and writes a plan, and changes nothing until you approve it.";
    case "acceptEdits":
      return "Claude edits files without asking; other actions still ask you.";
    case "auto":
      return "Auto mode: Claude goes ahead with what it judges safe, and asks you about the rest.";
    case "bypassPermissions":
      return "Claude runs everything without asking.";
    case "dontAsk":
      return "What isn't allowed already is refused, without asking you.";
    case "default":
      return "Manual mode: Claude asks you before it edits a file or runs a command you haven't allowed. Shift+Tab in the chat changes it.";
    default:
      return "Shift+Tab in the chat changes it.";
  }
}

// ---------------------------------------------------------------- plans

// One of an account's plans, found by its key, as the extension knows it now
// (never what the page sent): {plan, group}, or null when it's gone
export function findPlan(status: Status | null, hosts: HostState[], host: unknown, groupId: unknown, key: unknown): { plan: PlanItem; group: Group } | null {
  if (typeof key !== "string" || !key || typeof groupId !== "string" || (host !== undefined && host !== null && typeof host !== "string")) return null;
  const where = host ? hosts.find((h) => h.name === host)?.result : status;
  const group = where?.groups.find((g) => g.id === groupId);
  const plan = [...(group?.plans ?? []), ...(group?.starredPlans ?? [])].find((p) => p.key === key);
  return plan && group ? { plan, group: host ? { ...group, host: host as string } : group } : null;
}

// What Hide leaves out, kind by kind: [one, several, in a title]
export type HiddenKind = "chats" | "plans" | "memories" | "projects";
export const HIDDEN_NOUNS: Record<HiddenKind, [string, string, string]> = {
  chats: ["chat", "chats", "Chats"],
  plans: ["plan", "plans", "Plans"],
  memories: ["memory", "memories", "Memories"],
  projects: ["project", "projects", "Projects"],
};

// How many of a kind a machine's status says are hidden
export function hiddenCount(status: Pick<Status, "dismissed" | "hiddenPlans" | "hiddenMemories" | "hiddenProjects"> | null | undefined, kind: HiddenKind): number {
  if (!status) return 0;
  return (kind === "chats" ? status.dismissed : kind === "plans" ? status.hiddenPlans : kind === "memories" ? status.hiddenMemories : status.hiddenProjects) ?? 0;
}

// One of an account's memories, by its key, as the extension knows it
export function findMemory(status: Status | null, hosts: HostState[], host: unknown, groupId: unknown, key: unknown): { memory: Memory; group: Group } | null {
  if (typeof key !== "string" || !key || typeof groupId !== "string" || (host !== undefined && host !== null && typeof host !== "string")) return null;
  const where = host ? hosts.find((h) => h.name === host)?.result : status;
  const group = where?.groups.find((g) => g.id === groupId);
  const memory = [...(group?.memories ?? []), ...(group?.instructions ?? [])].find((m) => m.key === key);
  return memory && group ? { memory, group: host ? { ...group, host: host as string } : group } : null;
}

// ---------------------------------------------------------------- the Projects tab's
// Its chats, plans and memories are this computer's, from week.py
// --projects: the extension finds the one a click names in what it last read

// The account (of this computer) a project's chat, plan or memory is on
export function groupOfProfile(status: Pick<Status, "groups"> | null | undefined, profileDir: string): Group | undefined {
  return status?.groups.find((g) => (g.profileKeys ?? []).includes(profileDir));
}

export function findProjectChat(data: ProjectsData | null | undefined, key: unknown): ChatRef | null {
  if (typeof key !== "string" || !key) return null;
  for (const p of data?.projects ?? []) for (const c of p.chats ?? []) if (c.key === key) return recentRef(c);
  return null;
}

export function findProjectPlan(data: ProjectsData | null | undefined, status: Status | null, key: unknown): { plan: PlanItem; group: Group } | null {
  if (typeof key !== "string" || !key) return null;
  const plan = (data?.projects ?? []).flatMap((p) => p.plans ?? []).find((x) => x.key === key);
  const group = plan ? groupOfProfile(status, plan.profileDir) : undefined;
  return plan && group ? { plan, group } : null;
}

export function findProjectMemory(data: ProjectsData | null | undefined, status: Status | null, key: unknown): { memory: Memory; group: Group } | null {
  if (typeof key !== "string" || !key) return null;
  const memory = (data?.projects ?? []).flatMap((p) => p.memories ?? []).find((m) => m.key === key);
  const group = memory ? groupOfProfile(status, memory.profileDir) : undefined;
  return memory && group ? { memory, group } : null;
}

// A line's folder inside a project: only its part below the project's
// folder ("server" for ~/repos/api/server in ~/repos/api), nothing for the
// project's folder itself; outside a project (or outside its folder), short
export function folderIn(folder: string, project: string, short: string): string {
  if (!project || !folder) return short;
  if (folder === project) return "";
  return folder.startsWith(project + "/") ? folder.slice(project.length + 1) : short;
}

// The ids of the chats listed as an account's chats now (open, or kept for
// the record): not again under a project's Chats
export function listedChats(groups: Pick<Group, "sessions">[]): Set<string> {
  const ids = new Set<string>();
  for (const g of groups) for (const s of g.sessions) for (const id of [s.chatId, s.sessionId, s.jobSessionId]) if (id) ids.add(id);
  return ids;
}

// ---------------------------------------------------------------- lists a page at a time
// Recent chats, ★ Starred chats and plans, and an opened project's chats,
// plans and memories show a page at a time (as many as the Recent chats
// setting, 5 when it's 0); "Show N more" adds the next page; folded again,
// a list shows its first page. The status lists a page more recent chats
// than show (so the next page is there at once) and counts them all
// (recentCount); past that a check that lists more is run once for the
// account (Dashboard.recentMore).

export function pageSizeOf(recentChats: number): number {
  return recentChats > 0 ? Math.round(recentChats) : 5;
}

// An account's recent chats as a check that listed more has them: asked, how many it was asked for
export interface RecentMore {
  recent: RecentChat[];
  asked: number;
}

// An account's Recent chats with pages of them shown: all there are of them
// here (the status', then more's past those, each once), how many there are
// in all (a check that listed fewer than it was asked for has them all),
// how many show, and how many a check should list for the next page (0: it's
// here, or there's none)
export function recentPage(group: Pick<Group, "recent" | "recentCount">, more: RecentMore | null | undefined, pages: number, size: number):
    { all: RecentChat[]; count: number; shown: number; fetch: number } {
  const recent = group.recent ?? [];
  let all = recent;
  if (more) {
    const listed = new Set(recent.map((c) => c.sessionId));
    all = recent.concat(more.recent.filter((c) => !listed.has(c.sessionId)));
  }
  const count = more && more.recent.length < more.asked ? all.length : Math.max(group.recentCount ?? 0, recent.length);
  const wanted = Math.min(count, size * (pages + 1));
  return { all, count, shown: Math.min(all.length, size * pages), fetch: all.length < wanted ? wanted : 0 };
}

// A paged list's title: "Recent chats (5 of 23)", all of them shown "Recent chats (23)"
export function pagedTitle(title: string, shown: number, count: number): string {
  return shown < count ? `${title} (${shown} of ${count})` : `${title} (${count})`;
}

// Its "Show N more" (N: the next page's) and that button's tooltip
export function moreText(shown: number, count: number, size: number): string {
  return `Show ${Math.min(size, count - shown)} more`;
}

export function moreTitle(shown: number, count: number): string {
  return `${shown} of ${count} show. Folded again, the list shows its first ones again.`;
}

// What goes on in each project now: each open chat in one project only, the
// closest one whose folder holds the chat's (a chat in ~/repos/app is app's,
// not also ~/repos's and ~'s when chats once ran there too); by project path
export function openChatsByProject(projects: { path: string }[], sessions: Session[]): Map<string, Session[]> {
  const out = new Map<string, Session[]>();
  for (const s of sessions) {
    let best = "";
    for (const p of projects)
      if (p.path && p.path.length > best.length && !!s.cwd && (s.cwd === p.path || s.cwd.startsWith(p.path + "/")))
        best = p.path;
    if (best) (out.get(best) ?? out.set(best, []).get(best)!).push(s);
  }
  return out;
}

// An opened project's lists, pages of each shown: its chats (not the ones
// listed as an account's chats now), plans and memories; tagged: each line
// says its account (the project is on several)
export function projectLists(p: ProjectRow, listed: Set<string>, pages: { chats?: number; plans?: number; memories?: number }, size: number) {
  const chats = (p.chats ?? []).filter((c) => !listed.has(c.sessionId));
  const plans = p.plans ?? [];
  const memories = p.memories ?? [];
  const shown = (n: number, pagesShown = 1) => Math.min(n, size * pagesShown);
  return {
    chats, chatsShown: shown(chats.length, pages.chats),
    plans, plansShown: shown(plans.length, pages.plans),
    memories, memoriesShown: shown(memories.length, pages.memories),
    tagged: (p.accounts ?? []).length > 1,
  };
}


export function taskMark(status: string): string {
  return status === "completed" ? "✓" : status === "in_progress" ? "▸" : "○";
}

export function tasksTitle(t: TaskProgress): string {
  const head = `Tasks: ${t.done} of ${t.total} done` + (t.current ? ` · now: ${t.current}` : "");
  return [head, ...t.items.map((i) => `${taskMark(i.status)} ${i.subject}`)].join("\n");
}

// The tag's text: "±3" (the widget's)
export function changesTag(c: ChangeSummary): string {
  return `±${c.count}`;
}

export function changesTitle(c: ChangeSummary, host?: string): string {
  const more = c.count > c.files.length ? `\n…and ${c.count - c.files.length} more` : "";
  const what = host
    ? `\nThey're on ${host}: compare them there.`
    : "\nClick to compare them with what they were before the chat, side by side (VS Code's changes view).";
  return `${plural(c.count, "%1 file changed", "%1 files changed")}:\n${c.files.join("\n")}${more}${what}`;
}

// ---------------------------------------------------------------- usage forecast

// "At this pace: full in 1h 20m, 45m before it resets", when a plan window
// would run out before it resets (the widget's words)
export function forecastWarning(w: LimitWindow, now: number): string {
  const f = w.forecast;
  if (!f || f.fullAt === null || !w.resetsAt || w.reset) return "";
  return `At this pace: full in ${duration(f.fullAt - now)}, ${duration(w.resetsAt - f.fullAt)} before it resets`;
}

export function forecastTitle(w: LimitWindow, now: number): string {
  const f = w.forecast;
  if (!f || w.reset) return "";
  const when = (ms: number) => (ms - now > 20 * 3600000 ? `${new Date(ms).toLocaleDateString([], { weekday: "short" })} ${clockText(ms)}` : clockText(ms));
  const lines = [f.basis === "hour" ? `Your pace over the last hour: ${f.rate.toFixed(1)}% an hour.` : `Your pace in this window so far: ${f.rate.toFixed(1)}% an hour.`];
  if (f.fullAt !== null && w.resetsAt) lines.push(`At this pace it runs out at ${when(f.fullAt)}, ${duration(w.resetsAt - f.fullAt)} before it resets.`);
  else if (w.pct < 100) lines.push(`At this pace: about ${Math.round(f.atReset)}% when it resets (the faded part of the bar).`);
  lines.push(`An even pace through the window would be at ${Math.round(f.evenPct)}% by now (the mark).`);
  return lines.join("\n");
}

// ---------------------------------------------------------------- the chat that needs you

// A chat's key as the transition tracker keeps it ("ssh:<host>|…" for a host's)
export function trackKey(s: Pick<Session, "sessionId" | "key"> & { chatId?: string; profileDir?: string }, host?: string): string {
  return petKeyOf(s, host);
}

export interface ChatSpot {
  id: string; // trackKey
  session: Session;
  host?: string;
}

// The chats that need you, most urgent first: the waiting ones (the one
// waiting longest first), then the ones that finished a turn you haven't
// looked at yet (unseen: trackKey -> when; newest first)
// The Activity Bar badge, as the Plasma panel's: the chats that need you,
// else the ones that finished since you last looked; its tooltip says which
export function badgeOf(waiting: number, finished: number): { value: number; tooltip: string } | undefined {
  if (waiting > 0) return { value: waiting, tooltip: `${waiting} chat${waiting === 1 ? " needs" : "s need"} you` };
  if (finished > 0) return { value: finished, tooltip: `${finished} chat${finished === 1 ? "" : "s"} finished` };
  return undefined;
}

export function chatsNeedingYou(groups: Group[], unseen: ReadonlyMap<string, number>): ChatSpot[] {
  const waiting: ChatSpot[] = [];
  const finished: { spot: ChatSpot; at: number }[] = [];
  const seen = new Set<string>();
  for (const g of groups)
    for (const s of g.sessions) {
      const spot = { id: trackKey(s, g.host), session: s, host: g.host };
      if (seen.has(spot.id)) continue; // the chat's most urgent row came first
      seen.add(spot.id);
      if (s.state === "waiting") waiting.push(spot);
      else if (unseen.has(spot.id) && (s.state === "idle" || s.state === "done")) finished.push({ spot, at: unseen.get(spot.id)! });
    }
  waiting.sort((a, b) => (a.session.since ?? 0) - (b.session.since ?? 0));
  finished.sort((a, b) => b.at - a.at);
  return [...waiting, ...finished.map((f) => f.spot)];
}

// Which one a press of the shortcut goes to: the first, or (pressed again
// soon) the one after the last it went to
export function nextChatIndex(list: ChatSpot[], last: { id: string; at: number } | null, now: number, againMs = 30000): number {
  if (!list.length) return -1;
  if (!last || now - last.at > againMs) return 0;
  const i = list.findIndex((c) => c.id === last.id);
  return i < 0 ? 0 : (i + 1) % list.length;
}

// ---------------------------------------------------------------- stats

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// A local YYYY-MM-DD as a Date at local midnight
function localDate(day: string): Date {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(y, (m || 1) - 1, d || 1);
}

export function weekdayShort(day: string): string {
  return WEEKDAYS[localDate(day).getDay()];
}

// Under a day's bar: its weekday's letter ("T"), on every bar, as Plasma's and GNOME's
export function weekdayLetter(day: string): string {
  return weekdayShort(day)[0];
}

// "Tue 15 Oct"
export function dayLabel(day: string): string {
  const d = localDate(day);
  return `${WEEKDAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}`;
}

// A part of a whole as a percentage: "99%", "<1%", ">99%" (not a rounded
// "100%" beside another part's "<1%"), as Plasma's
export function sharePercent(part: number, whole: number): string {
  if (whole <= 0 || part <= 0) return "0%";
  const pct = (100 * part) / whole;
  return pct < 1 ? "<1%" : pct > 99 && pct < 100 ? ">99%" : `${Math.round(pct)}%`;
}

// A bar's tooltip: "Tue 15 Oct: 446.8M tokens (1.7M out) · 6 chats · 73 prompts"
export function dayTitle(d: StatsDay): string {
  if (!d.total && !d.prompts) return `${dayLabel(d.day)}: nothing`;
  return (
    `${dayLabel(d.day)}: ${formatTokens(d.total)} tokens (${formatTokens(d.output)} out)` +
    ` · ${plural(d.chats, "%1 chat", "%1 chats")} · ${plural(d.prompts, "%1 prompt", "%1 prompts")}`
  );
}

// "14 days: 997.4M tokens (3.2M out) · 15 chats · 253 prompts · 5 active days"
export function statsSummary(s: UsageStats): string {
  const sum = s.sum;
  return (
    `${s.days.length} days: ${formatTokens(sum.total)} tokens (${formatTokens(sum.output)} out)` +
    ` · ${plural(sum.chats, "%1 chat", "%1 chats")} · ${plural(sum.prompts, "%1 prompt", "%1 prompts")}` +
    ` · ${plural(sum.activeDays, "%1 active day", "%1 active days")}`
  );
}

// "Opus 5.5 99% · Sonnet 5.5 <1%"
export function modelShares(models: UsageStats["models"]): string {
  const whole = models.reduce((n, m) => n + m.total, 0);
  return models.map((m) => `${m.model} ${sharePercent(m.total, whole)}`).join(" · ");
}



// The recap under a chat's peek: "3 prompts · worked 51m · 278 tool calls
// (Bash 236, Read 23, Write 5) · 85.3M tokens (249.0k out) · $12.40 at API prices"
export function recapText(st: ChatStats, costUsd?: number | null): string {
  const parts = [plural(st.prompts, "%1 prompt", "%1 prompts")];
  if (st.workedMs > 0) parts.push(`worked ${duration(st.workedMs)}`);
  if (st.toolCalls) {
    const top = (st.tools ?? []).slice(0, 3).map(([name, n]) => `${name} ${n}`).join(", ");
    parts.push(plural(st.toolCalls, "%1 tool call", "%1 tool calls") + (top ? ` (${top})` : ""));
  }
  if (st.tokens.total) parts.push(`${formatTokens(st.tokens.total)} tokens (${formatTokens(st.tokens.output)} out)`);
  if (costUsd) parts.push(`$${costUsd.toFixed(2)} at API prices`);
  return parts.join(" · ");
}

// ---------------------------------------------------------------- a subagent unfolded

// Its open state, kept by row and agent ("[host|]row key|agent id")
export function agentDetailKey(rowKey: string, agentId: string): string {
  return `${rowKey}|${agentId}`;
}

// "12 tool calls · 45.2k tokens", leaving out what isn't known
export function agentSummary(a: Pick<Agent, "toolCalls" | "tokens">): string {
  const parts = [];
  if (typeof a.toolCalls === "number") parts.push(plural(a.toolCalls, "%1 tool call", "%1 tool calls"));
  if (typeof a.tokens === "number" && a.tokens > 0) parts.push(`${formatTokens(a.tokens)} tokens`);
  return parts.join(" · ");
}

// A chat's subagents in its chat tab's strip: the running ones first, each of
// the chat's own with the ones it started (the status's tree stays a tree)
export function agentsRunningFirst(tree: Agent[]): Agent[] {
  const started: Agent[][] = [];
  for (const a of tree) {
    if (a.depth === 0 || !started.length) started.push([a]);
    else started[started.length - 1].push(a);
  }
  const busy = (list: Agent[]) => list.some((a) => a.status === "running");
  return [...started.filter(busy), ...started.filter((list) => !busy(list))].flat();
}

// What a chat's subagents do, for its strip's line when it has no task list:
// the running one's description and what it does, else how many run, else how they ended
export function agentsNow(agents: { done: number; total: number; tree: Agent[] }): string {
  const running = agents.tree.filter((a) => a.status === "running");
  if (running.length === 1) return (running[0].description || running[0].type) + (running[0].activity ? `: ${running[0].activity}` : "");
  return running.length > 1 ? `${running.length} running` : agents.done >= agents.total ? "all done" : "none running";
}

// The tooltip of "Open the whole run"
export function agentRunTitle(host?: string): string {
  return (
    "Its task, every step with the start of each result, and its report, as Markdown. Claude Code itself can't open a subagent from outside." +
    (host ? (containerOf(host) ? ` Fetched from ${hostLabel(host)}.` : ` Fetched from ${host} over ssh.`) : "")
  );
}

function clock(ms: number, now: number): string {
  const d = new Date(ms);
  const time = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  return now - ms < 20 * 3600000 ? time : `${WEEKDAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]} ${time}`;
}

export function recapTitle(st: ChatStats, now: number): string {
  const t = st.tokens;
  const lines = [];
  if (st.startedAt) lines.push(`Started ${clock(st.startedAt, now)}`);
  if (st.lastAt) lines.push(`Last activity ${clock(st.lastAt, now)} (${ago(now - st.lastAt)})`);
  if (st.workedMs) lines.push(`Claude worked ${duration(st.workedMs)}: each turn from your prompt to its last step`);
  if (st.tools.length) lines.push(`Tools: ${st.tools.map(([name, n]) => `${name} ${n}`).join(", ")}`);
  lines.push(
    `Tokens (subagents included): input ${formatTokens(t.input)} · output ${formatTokens(t.output)} · ` +
      `cache read ${formatTokens(t.cacheRead)} · cache write ${formatTokens(t.cacheWrite)}`,
  );
  return lines.join("\n");
}
