// The extension's settings (talpyDen.*), read fresh on every use so a
// change applies at the next poll.

import * as os from "node:os";
import * as path from "node:path";
import * as vscode from "vscode";
import type { ReopenIn, SshUsage, ViewSettings } from "./shared/types";

function cfg() {
  return vscode.workspace.getConfiguration("talpyDen");
}

// A whole number in [min, max]: the scripts take counts like --recent 2.5 as an error
function num(key: string, fallback: number, min: number, max: number): number {
  const v = cfg().get<number>(key, fallback);
  return Math.round(Math.min(max, Math.max(min, typeof v === "number" && isFinite(v) ? v : fallback)));
}

export function expandHome(p: string): string {
  return p === "~" ? os.homedir() : p.startsWith("~/") ? path.join(os.homedir(), p.slice(2)) : p;
}

export const settings = {
  pollInterval: () => num("pollInterval", 2000, 1000, 60000),
  idlePollInterval: () => num("idlePollInterval", 20000, 1000, 300000),
  remotePollSeconds: () => num("remotePollSeconds", 30, 10, 600),
  showContainers: () => cfg().get<boolean>("showContainers", true) !== false,
  containerDays: () => num("containerDays", 30, 0, 365),
  sshHosts: () => [...new Set((cfg().get<string[]>("sshHosts", []) ?? []).map((h) => String(h).trim()).filter(Boolean))], // (a host twice would be two rows)
  includeCurrentRemote: () => cfg().get<boolean>("includeCurrentRemote", true),
  clickOpensPane: () => cfg().get<boolean>("clickOpensPane", true) !== false,
  openIn: () => (cfg().get<string>("openIn", "vscode") === "system" ? "system" : "vscode"),
  reopenIn: (): ReopenIn => (cfg().get<string>("reopenIn", "terminal") === "claudeCode" ? "claudeCode" : "terminal"),
  sshUsage: (): SshUsage => {
    const v = cfg().get<string>("sshUsage", "once");
    return v === "all" || v === "none" ? v : "once";
  },
  recapCurrency: () => {
    const v = cfg().get<string>("recapCurrency", "USD");
    return typeof v === "string" && /^[A-Z]{3}$/.test(v) ? v : "USD";
  },
  recapRules: () => cfg().get<boolean>("recapRules", true) !== false,
  recapHistory: () => cfg().get<boolean>("recapHistory", true) !== false,
  notifyWaiting: () => cfg().get<boolean>("notifyWaiting", true),
  notifyDone: () => cfg().get<boolean>("notifyDone", true),
  notifyDoneMinSeconds: () => num("notifyDoneMinSeconds", 30, 0, 3600),
  notifySound: () => cfg().get<boolean>("notifySound", true),
  soundVolume: () => num("soundVolume", 70, 0, 100),
  soundWaiting: () => cfg().get<string>("soundWaiting", "message-new-instant"),
  soundDone: () => cfg().get<string>("soundDone", "outcome-success,complete"),
  soundFailed: () => cfg().get<string>("soundFailed", "dialog-error"),
  showUsageInStatusBar: () => cfg().get<boolean>("showUsageInStatusBar", true),
  recentChats: () => num("recentChats", 5, 0, 20),
  keepDoneHours: () => num("keepDoneHours", 24, 0, 168),
  showTokens: () => cfg().get<boolean>("showTokens", true),
  awayDigest: () => cfg().get<boolean>("awayDigest", true),
  awayMinutes: () => num("awayMinutes", 5, 1, 240),
  python: () => expandHome(cfg().get<string>("pythonPath", "python3")?.trim() || "python3"),
  usageCap: () => num("usageCap", 0, 0, 100),
  usageRefreshMinutes: () => num("usageRefreshMinutes", 5, 0, 60),
  newChatModel: () => (cfg().get<string>("newChatModel", "opus") ?? "").trim(),
  newChatEffort: () => (cfg().get<string>("newChatEffort", "xhigh") ?? "").trim(),
  newChatMode: () => (cfg().get<string>("newChatMode", "") ?? "").trim(),
};

// claude's options for the model, effort and permission mode new chats start with (New Chat… picks them)
export function chatOptionArgs(): string[] {
  const model = settings.newChatModel();
  const effort = settings.newChatEffort();
  const mode = settings.newChatMode();
  return [...(model ? ["--model", model] : []), ...(effort ? ["--effort", effort] : []), ...(mode ? ["--permission-mode", mode] : [])];
}

// (each where it's set: a workspace's own value would win over a global one)
export async function setChatOptions(model: string, effort: string, mode: string): Promise<void> {
  await cfg().update("newChatModel", model, whereSet("newChatModel"));
  await cfg().update("newChatEffort", effort, whereSet("newChatEffort"));
  await cfg().update("newChatMode", mode, whereSet("newChatMode"));
}

// Where a setting's value comes from: its folder's, its workspace's, else the user's
function whereSet(key: string): vscode.ConfigurationTarget {
  const set = cfg().inspect<unknown>(key);
  return set?.workspaceFolderValue !== undefined
    ? vscode.ConfigurationTarget.WorkspaceFolder
    : set?.workspaceValue !== undefined
      ? vscode.ConfigurationTarget.Workspace
      : vscode.ConfigurationTarget.Global;
}

export function viewSettings(): ViewSettings {
  return {
    showPet: cfg().get<boolean>("showPet", true),
    playful: cfg().get<boolean>("playfulTalpy", true) !== false,
    chatPets: num("chatPets", 5, 0, 8),
    showTokens: settings.showTokens(),
    recentChats: settings.recentChats(),
    reopenIn: settings.reopenIn(),
    recapCurrency: settings.recapCurrency(),
    recapRules: settings.recapRules(),
    clickOpensPane: settings.clickOpensPane(),
    showContainers: settings.showContainers(),
  };
}

// Config dirs beyond ~/.claude and ~/.claude-* (which the backend finds by
// itself): the one Claude Code itself would use here ($CLAUDE_CONFIG_DIR), and
// any the user added.
export function extraConfigDirs(env: NodeJS.ProcessEnv = process.env): string[] {
  const dirs = (cfg().get<string[]>("extraConfigDirs", []) ?? []).map((d) => expandHome(String(d).trim())).filter(Boolean);
  if (env.CLAUDE_CONFIG_DIR) dirs.unshift(expandHome(env.CLAUDE_CONFIG_DIR));
  return [...new Set(dirs)];
}

export function configDirArgs(): string[] {
  return extraConfigDirs().flatMap((d) => ["--config-dir", d]);
}

// Arguments of every status run, here and on hosts: a page more recent chats
// than show (so the next page is there at once), and of the plans only the
// starred ones, of the memories only the accounts' CLAUDE.md (the rest is in
// the Projects tab)
export function statusArgs(): string[] {
  const recent = settings.recentChats();
  const args = ["--done-hours", String(settings.keepDoneHours()), "--recent", String(recent > 0 ? 2 * recent : 0), "--plans", "0", "--memories", "0"];
  if (!settings.showTokens()) args.push("--no-tokens");
  // (an account's plan usage this old is fetched while one of its chats works)
  args.push("--usage-refresh", String(settings.usageRefreshMinutes()));
  return args;
}

// (a "machine" setting: only the user's settings hold it)
export async function setSshHosts(hosts: string[]): Promise<void> {
  await cfg().update("sshHosts", hosts, vscode.ConfigurationTarget.Global);
}

// Written where it's set: a workspace's own value would win over the user's
export async function setReopenIn(where: ReopenIn): Promise<void> {
  await cfg().update("reopenIn", where, whereSet("reopenIn"));
}

export function cacheDir(): string {
  return path.join(process.env.XDG_CACHE_HOME || path.join(os.homedir(), ".cache"), "talpy-den");
}
