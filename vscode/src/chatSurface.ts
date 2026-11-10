// Where a Talpy Chat shows: an editor tab of its own (a webview panel), or
// Talpy Chat's view in the secondary side bar, beside Claude Code's and
// Copilot's chats, where no file opens over it (talpyDen.chatPlace:
// "sideBar"; VS Code 1.106 and later lets an extension put a view there).
// The view holds one chat at a time: the next one opened takes its place.

import * as vscode from "vscode";

export const CHAT_VIEW = "talpyDen.chatView";
// (the view shows only while this is set: an older VS Code, which has no such bar, would list it under Explorer)
export const CHAT_VIEW_CONTEXT = "talpyDen.chatSideBar";

// VS Code has a secondary side bar for extensions' views (as the Claude Code extension checks it)
export function sideBarSupported(version: string = vscode.version): boolean {
  const [major = 0, minor = 0] = version.split(".").map(Number);
  return major > 1 || (major === 1 && minor >= 106);
}

// What a chat's page needs of where it shows (a vscode.WebviewPanel is one as it is)
export interface ChatSurface {
  readonly webview: vscode.Webview;
  readonly visible: boolean;
  readonly active: boolean; // in front, with the focus (its keys go to it)
  title: string;
  iconPath?: vscode.WebviewPanel["iconPath"];
  reveal(): void;
  readonly onDidChangeViewState: vscode.Event<unknown>;
  readonly onDidDispose: vscode.Event<void>;
  dispose(): void;
}

// Talpy Chat's view, while one chat shows in it. Closing the chat (dispose)
// gives the view back, it doesn't close it: released() says so, for whoever
// shows the next one (or the empty view's words).
export class ViewSurface implements ChatSurface {
  private gone = new vscode.EventEmitter<void>();
  readonly onDidDispose = this.gone.event;
  readonly onDidChangeViewState: vscode.Event<unknown>;
  iconPath: vscode.WebviewPanel["iconPath"] = undefined; // (a view's icon is its container's)
  private released = false;
  private focused = false; // (the page says: VS Code doesn't tell which view has the focus)

  constructor(private view: vscode.WebviewView, options: vscode.WebviewOptions) {
    view.webview.options = options;
    this.onDidChangeViewState = view.onDidChangeVisibility;
  }

  get webview(): vscode.Webview {
    return this.view.webview;
  }
  get visible(): boolean {
    return !this.released && this.view.visible;
  }
  get active(): boolean {
    return this.visible && this.focused;
  }
  // (the chat's name, after the view's own: "Talpy Chat  fix the tests")
  get title(): string {
    return this.view.description ?? "";
  }
  set title(text: string) {
    if (!this.released) this.view.description = text;
  }
  focus(on: boolean): void {
    this.focused = on;
  }
  reveal(): void {
    if (!this.released) this.view.show(false);
  }
  dispose(): void {
    if (this.released) return;
    this.released = true;
    this.gone.fire();
    this.gone.dispose();
  }
}

// The view with no chat in it: what to do, in the theme's colours (no script)
export function emptyView(view: vscode.WebviewView): void {
  view.description = undefined;
  view.webview.options = { enableScripts: false };
  view.webview.html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<style>
  body { margin: 0; padding: 16px; color: var(--vscode-descriptionForeground); font-family: var(--vscode-font-family); font-size: var(--vscode-font-size); line-height: 1.5; }
  strong { color: var(--vscode-foreground); }
</style>
<title>Talpy Chat</title>
</head>
<body>
<p><strong>No chat here yet.</strong></p>
<p>Click a chat in Talpy Den's list, or start one with New Chat…: it opens here, one at a time.</p>
<p>To open chats in editor tabs again, set <em>Talpy Den: Chat Place</em> to <em>tab</em> in the settings.</p>
</body>
</html>`;
}
