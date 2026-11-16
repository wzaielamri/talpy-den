// Talpy Chat in the secondary side bar, beside Claude Code's and Copilot's
// chats, where no file opens over it (talpyDen.chatPlace: "sideBar", the
// default; "tab": an editor tab for each chat, as it was. VS Code 1.106 and
// later lets an extension put a view there: an older one opens tabs). The view holds one
// chat at a time: the next one opened takes its place. A chat's page is
// written for an editor tab (a webview panel), so the view is handed to it as
// one (ViewSurface).

import * as vscode from "vscode";

export const CHAT_VIEW = "talpyDen.chatView";
// (the view shows only while this is set: an older VS Code, which has no such bar, would list it under Explorer)
export const CHAT_VIEW_CONTEXT = "talpyDen.chatSideBar";

// VS Code has a secondary side bar for extensions' views (as the Claude Code extension checks it)
export function sideBarSupported(version: string = vscode.version): boolean {
  const [major = 0, minor = 0] = version.split(".").map(Number);
  return major > 1 || (major === 1 && minor >= 106);
}

// Talpy Chat's view as the panel of the chat it shows. Closing the chat
// (dispose) gives the view back, it doesn't close it: whoever shows the next
// one (or the empty view's words) goes on with it.
export class ViewSurface implements vscode.WebviewPanel {
  readonly viewType = "talpyDen.chat";
  readonly options: vscode.WebviewPanelOptions = {};
  readonly viewColumn = undefined;
  iconPath: vscode.WebviewPanel["iconPath"] = undefined; // (a view's icon is its container's)
  private gone = new vscode.EventEmitter<void>();
  readonly onDidDispose = this.gone.event;
  private changed = new vscode.EventEmitter<vscode.WebviewPanelOnDidChangeViewStateEvent>();
  readonly onDidChangeViewState = this.changed.event;
  private watching: vscode.Disposable;
  private released = false;
  private focused = false; // (the page says: VS Code doesn't tell which view has the focus)

  constructor(private view: vscode.WebviewView, options: vscode.WebviewOptions) {
    view.webview.options = options;
    this.watching = view.onDidChangeVisibility(() => this.changed.fire({ webviewPanel: this }));
  }

  get webview(): vscode.Webview {
    return this.view.webview;
  }
  get visible(): boolean {
    return !this.released && this.view.visible;
  }
  // In front, with the focus (its keys go to it)
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
    this.watching.dispose();
    this.changed.dispose();
    this.gone.fire();
    this.gone.dispose();
  }
}

// The folders this window has open on that machine, with each one's path there: this computer's (no host) in a
// window of its own, a host's or a container's in a Remote-SSH or Dev Containers window on it (currentHost)
export function windowFolders(host: string | undefined, currentHost: string | undefined): { folder: vscode.WorkspaceFolder; path: string }[] {
  const open = vscode.workspace.workspaceFolders ?? [];
  if (!host) return open.filter((f) => f.uri.scheme === "file").map((folder) => ({ folder, path: folder.uri.fsPath }));
  return host === currentHost ? open.filter((f) => f.uri.scheme !== "file").map((folder) => ({ folder, path: folder.uri.path })) : [];
}

// The command the empty view's "New chat in <folder>" runs (a folder this window has open, by its URI)
export const NEW_CHAT_HERE = "talpyDen.newChatHere";

// What the empty view offers: a new chat in each folder this window has open (on the default account,
// named when the machine has more), and New Chat… for any other folder or account
export interface EmptyStarts {
  folders: { uri: string; name: string; path: string }[];
  account?: string;
}

function escaped(text: string): string {
  return text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

// The view with no chat in it, in the theme's colours (no script: its buttons are command links)
export function emptyHtml(starts: EmptyStarts): string {
  const here = starts.folders.map((f) =>
    `<a class="button" href="command:${NEW_CHAT_HERE}?${escaped(encodeURIComponent(JSON.stringify([f.uri])))}" title="${escaped(f.path)}">New chat in ${escaped(f.name)}</a>`);
  const other = `<a class="button${here.length ? " secondary" : ""}" href="command:talpyDen.newChat">${here.length ? "Other folder or account…" : "New chat…"}</a>`;
  const account = here.length && starts.account ? `<p class="small">On ${escaped(starts.account)}, the default account.</p>` : "";
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<style>
  body { margin: 0; padding: 16px; color: var(--vscode-descriptionForeground); font-family: var(--vscode-font-family); font-size: var(--vscode-font-size); line-height: 1.5; }
  strong { color: var(--vscode-foreground); }
  .starts { display: flex; flex-direction: column; gap: 8px; max-width: 300px; margin: 12px 0; }
  .button { display: block; box-sizing: border-box; padding: 4px 8px; border: 1px solid var(--vscode-button-border, transparent); border-radius: 2px; text-align: center;
            text-decoration: none; overflow-wrap: anywhere; /* (a narrow side bar: the folder's whole name, on two lines) */
            color: var(--vscode-button-foreground); background: var(--vscode-button-background); }
  .button:hover { background: var(--vscode-button-hoverBackground); }
  .button:focus { outline: 1px solid var(--vscode-focusBorder); outline-offset: 2px; }
  .button.secondary { color: var(--vscode-button-secondaryForeground); background: var(--vscode-button-secondaryBackground); }
  .button.secondary:hover { background: var(--vscode-button-secondaryHoverBackground); }
  .small { margin: 0; font-size: 0.9em; }
</style>
<title>Talpy Chat</title>
</head>
<body>
<p><strong>No chat here yet.</strong></p>
<div class="starts">
${[...here, other].join("\n")}
${account}
</div>
<p>Or click a chat in Talpy Den's list: it opens here, one at a time.</p>
<p>For an editor tab for each chat instead, set <em>Talpy Den: Chat Place</em> to <em>tab</em> in the settings.</p>
</body>
</html>`;
}

// The view with no chat in it: what to start (only set when it changes: a new page reloads the view)
export function emptyView(view: vscode.WebviewView, starts: EmptyStarts = { folders: [] }): void {
  view.description = undefined;
  const html = emptyHtml(starts);
  if (view.webview.options.enableScripts === false && view.webview.html === html) return;
  view.webview.options = { enableScripts: false, enableCommandUris: [NEW_CHAT_HERE, "talpyDen.newChat"] };
  view.webview.html = html;
}
