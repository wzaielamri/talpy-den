// EditorPort on VS Code: its changes view (changes.ts), Talpy Den's doc tab (doc.ts), an editor tab, the
// plan review's comments (planReview.ts) and Claude Code's panel (claudePanel.ts), each as the extension
// shows it. The core's paths become vscode.Uri here.

import * as vscode from "vscode";
import type { Comparison } from "../../core/src/comparisons";
import type { Event } from "../../core/src/events";
import type { EditorPort, PlanComment } from "../../core/src/ports";
import { openComparison } from "./changes";
import { claudePanelAvailable, localPanelConfigDir, localPanelProfileKey, openPanelChat } from "./claudePanel";
import { showDoc } from "./doc";
import type { PlanReview } from "./planReview";
import { windowHostFile } from "./remoteHost";

export class VsCodeEditor implements EditorPort {
  planReview?: PlanReview; // your comments on plans (set once it's there)

  openComparison(c: Comparison): Promise<string> {
    return openComparison(c);
  }

  showDoc(path: string, options?: { onWindowHost?: boolean }): Promise<string> {
    return showDoc(fileUri(path, options));
  }

  async editFile(path: string, options?: { onWindowHost?: boolean }): Promise<void> {
    await vscode.window.showTextDocument(fileUri(path, options), { preview: false });
  }

  async saveEdits(path: string): Promise<void> {
    const uri = vscode.Uri.file(path);
    const doc = vscode.workspace.textDocuments.find((d) => d.uri.toString() === uri.toString());
    if (doc?.isDirty) await doc.save();
  }

  async planComments(path: string): Promise<PlanComment[]> {
    return (await this.planReview?.comments(path)) ?? [];
  }

  clearPlanComments(path: string): void {
    this.planReview?.clear(path);
  }

  claudePanelAvailable(): Promise<boolean> {
    return claudePanelAvailable();
  }

  // (the Claude Code extension installed, removed or, in a new folder, enabled)
  readonly onDidChangeClaudePanel: Event<void> = (listener) => vscode.extensions.onDidChange(() => listener());

  claudeCodeInstalled(): boolean {
    return !!vscode.extensions.getExtension("anthropic.claude-code");
  }

  localPanelConfigDir(): string {
    return localPanelConfigDir();
  }

  localPanelProfileKey(): string {
    return localPanelProfileKey();
  }

  openPanelChat(prompt?: string): Promise<void> {
    return openPanelChat(prompt);
  }
}

// A file of the window's host as the window names it (vscode-remote), when it's connected to one; else, and
// for this computer's, file: (in a Remote-SSH window too: this extension runs on this computer)
function fileUri(path: string, options?: { onWindowHost?: boolean }): vscode.Uri {
  return (options?.onWindowHost && windowHostFile(vscode, path)) || vscode.Uri.file(path);
}
