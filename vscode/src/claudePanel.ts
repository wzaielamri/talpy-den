// The Claude Code extension's own chat, as a place for a new chat. It runs
// where the window's workspace is (this computer, or the Remote-SSH host), in
// the window's folder, on the account its own settings give it: it can only
// start a chat on that machine, and the menu says which account that is.

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import * as vscode from "vscode";
import { expandHome } from "../../core/src/settings";

const NEW_CHAT_TAB = "claude-vscode.editor.open"; // "Claude Code: Open in New Tab"

// The extension starts with VS Code and registers its commands wherever it
// runs, so they show whether it's there (in an untrusted folder it isn't).
export async function claudePanelAvailable(): Promise<boolean> {
  return (await vscode.commands.getCommands(true)).includes(NEW_CHAT_TAB);
}

// The config dir the Claude Code extension starts claude with on this
// computer: CLAUDE_CONFIG_DIR from claudeCode.environmentVariables, else
// VS Code's own, else ~/.claude.
export function panelConfigDir(vars: unknown, env: NodeJS.ProcessEnv = process.env): string {
  const list: unknown[] = Array.isArray(vars) ? vars : [];
  const entry = list.find((v) => !!v && typeof v === "object" && (v as { name?: unknown }).name === "CLAUDE_CONFIG_DIR") as
    | { value?: unknown }
    | undefined;
  const set = typeof entry?.value === "string" ? entry.value.trim() : "";
  return expandHome(set || env.CLAUDE_CONFIG_DIR || path.join(os.homedir(), ".claude"));
}

// How the backend names a profile: its real folder's name (a link like
// ~/.claude names the profile it points to)
export function profileKey(dir: string): string {
  try {
    return path.basename(fs.realpathSync(dir));
  } catch {
    return path.basename(dir);
  }
}

export function localPanelConfigDir(): string {
  return panelConfigDir(vscode.workspace.getConfiguration("claudeCode").get("environmentVariables"));
}

export function localPanelProfileKey(): string {
  return profileKey(localPanelConfigDir());
}

// Claude Code files a chat under the folder it started in (projects/<the
// folder, mangled> in the config dir), wherever Claude's `cd`s took it
export function filedUnder(configDir: string, folder: string, chatId: string): boolean {
  return fs.existsSync(path.join(configDir, "projects", folder.replace(/[^A-Za-z0-9]/g, "-"), `${chatId}.jsonl`));
}

// prompt: typed into the new chat's input, for you to send (the Claude
// Code extension's own command takes a session id, then a prompt)
export async function openPanelChat(prompt?: string): Promise<void> {
  if (prompt) await vscode.commands.executeCommand(NEW_CHAT_TAB, undefined, prompt);
  else await vscode.commands.executeCommand(NEW_CHAT_TAB);
}
