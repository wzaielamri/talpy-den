// The Claude Code extension's own chat, as a place for a new chat. It runs
// where the window's workspace is (this computer, or the Remote-SSH host), in
// the window's folder, on the account its own settings give it: it can only
// start a chat on that machine, and the menu says which account that is.

import * as vscode from "vscode";
import { panelConfigDir, profileKey } from "../../core/src/agents/claudeCode/claudePanel";

const NEW_CHAT_TAB = "claude-vscode.editor.open"; // "Claude Code: Open in New Tab"

// The extension starts with VS Code and registers its commands wherever it
// runs, so they show whether it's there (in an untrusted folder it isn't).
export async function claudePanelAvailable(): Promise<boolean> {
  return (await vscode.commands.getCommands(true)).includes(NEW_CHAT_TAB);
}

export function localPanelConfigDir(): string {
  return panelConfigDir(vscode.workspace.getConfiguration("claudeCode").get("environmentVariables"));
}

export function localPanelProfileKey(): string {
  return profileKey(localPanelConfigDir());
}

// prompt: typed into the new chat's input, for you to send (the Claude
// Code extension's own command takes a session id, then a prompt)
export async function openPanelChat(prompt?: string): Promise<void> {
  if (prompt) await vscode.commands.executeCommand(NEW_CHAT_TAB, undefined, prompt);
  else await vscode.commands.executeCommand(NEW_CHAT_TAB);
}
