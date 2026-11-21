// Talpy Chat's chats in VS Code: each chat's page in an editor tab, or in
// Talpy Chat's view in the secondary side bar (talpyDen.chatPlace), where
// core/src/chatPanes.ts opens them (PaneSurfaces). Here: the panels and the
// view, their page (its HTML, the files it may load), and what only VS Code
// does of what a page says (its paste; which chat the side bar's view has
// the focus for). What a chat shows, and what runs, is the core's.

import * as crypto from "node:crypto";
import * as vscode from "vscode";
import { windowFolders } from "../../core/src/actions";
import { picturesDir } from "../../core/src/chatPanes";
import type { Dashboard } from "../../core/src/dashboard";
import { Emitter, type Event } from "../../core/src/events";
import type { HostServices } from "../../core/src/host";
import type { ChatPage, PaneSurface, PaneSurfaces } from "../../core/src/ports";
import { settings } from "../../core/src/settings";
import { defaultGroup, machineStatus } from "../../core/src/shared/model";
import type { PaneHostMessage, PaneMessage } from "../../core/src/shared/pane";
import { CHAT_VIEW, CHAT_VIEW_CONTEXT, emptyView, sideBarSupported, ViewSurface } from "./chatSurface";

// Talpy Chat's keys (keys.mjs): each a command (package.json binds its key while a chat tab has
// the focus), and what it tells the tab in front to do
export const CHAT_KEYS: Record<string, string> = {
  "talpyDen.chat.sendNow": "sendNow",
  "talpyDen.chat.sendWhenTurnEnds": "sendLater",
  "talpyDen.chat.sendInBackground": "sendBackground",
  "talpyDen.chat.clear": "clear",
  "talpyDen.chat.stop": "stop",
  "talpyDen.chat.reply1": "chip1",
  "talpyDen.chat.reply2": "chip2",
  "talpyDen.chat.reply3": "chip3",
  "talpyDen.chat.reply4": "chip4",
  "talpyDen.chat.allow": "allow",
  "talpyDen.chat.alwaysAllow": "always",
  "talpyDen.chat.deny": "deny",
  "talpyDen.chat.previousPrompt": "promptUp",
  "talpyDen.chat.nextPrompt": "promptDown",
  "talpyDen.chat.showChat": "tabChat",
  "talpyDen.chat.showSteps": "tabSteps",
  "talpyDen.chat.showReview": "tabReview",
  "talpyDen.chat.toggleTasks": "tasks",
  "talpyDen.chat.copyLastReply": "copyLast",
  "talpyDen.chat.find": "find",
  "talpyDen.chat.foldAll": "fold",
  "talpyDen.chat.toggleBookmark": "bookmark",
  "talpyDen.chat.bookmarks": "bookmarks",
  "talpyDen.chat.previousBookmark": "bookmarkUp",
  "talpyDen.chat.nextBookmark": "bookmarkDown",
  "talpyDen.chat.openWindow": "openWindow",
  "talpyDen.chat.keys": "help",
};

// Where the core's chats show: an editor tab each, or the side bar's view
export class ChatSurfaces implements PaneSurfaces {
  // ---------------------------------------------------------------- Talpy Chat in the side bar
  //
  // talpyDen.chatPlace "sideBar" (the default): a chat opens in Talpy Chat's view in the secondary side
  // bar, beside Claude Code's and Copilot's chats, where no file opens over it, instead of an editor tab
  // ("tab"): one chat at a time, the next one opened takes its place (chatSurface.ts: the view as the
  // panel a chat's surface has).

  private sideView: vscode.WebviewView | undefined; // the view, once VS Code made it
  private side: ChatSurface | undefined; // the chat it shows
  private sideNext: (() => void) | undefined; // (what opens once the view is made)

  constructor(private extensionUri: vscode.Uri, private host: HostServices, private dash: Dashboard) {}

  private inSideBar(): boolean {
    return settings.chatPlace() === "sideBar" && sideBarSupported();
  }

  // The view's provider, and the context key it shows by (package.json: its "when")
  sideBar(): vscode.Disposable {
    const context = () => void vscode.commands.executeCommand("setContext", CHAT_VIEW_CONTEXT, this.inSideBar());
    context();
    const made = [
      vscode.window.registerWebviewViewProvider(CHAT_VIEW, {
        resolveWebviewView: (view) => {
          this.sideView = view;
          view.onDidDispose(() => {
            if (this.sideView === view) this.sideView = undefined;
            this.side?.dispose();
          });
          const next = this.sideNext;
          this.sideNext = undefined;
          next?.();
          if (!this.side) this.showEmpty(view); // (nothing to show in it yet, or what opened has a tab already)
        },
      }, { webviewOptions: { retainContextWhenHidden: true } }),
      vscode.workspace.onDidChangeConfiguration((e) => {
        if (!e.affectsConfiguration("talpyDen.chatPlace")) return;
        context();
        if (!this.inSideBar()) this.side?.dispose(); // (its view goes: the chat opens in a tab the next time)
      }),
      // (the empty view's buttons: the folders this window has open, the account they start on)
      this.host.onDidChangeWorkspaceFolders(() => this.emptyAgain()),
      this.dash.onState(() => this.emptyAgain()),
    ];
    return { dispose: () => made.forEach((d) => d.dispose()) };
  }

  // The view with no chat in it: a new chat in each folder this window has open, on the default account of
  // their machine (named when it has more), or any other (chatSurface.ts emptyView)
  private showEmpty(view: vscode.WebviewView): void {
    const machine = this.dash.currentHost;
    const groups = machineStatus(this.dash.state(), machine)?.groups ?? [];
    emptyView(view, {
      folders: windowFolders(this.host.workspaceFolders(), machine, machine)
        .map((f) => ({ uri: f.uri, name: f.name, path: (machine ? `${machine}:` : "") + f.path })),
      account: groups.length > 1 ? defaultGroup(groups)?.title : undefined,
    });
  }
  private emptyAgain(): void {
    if (this.sideView && !this.side) this.showEmpty(this.sideView);
  }

  // With the side bar its place and the view not made yet, VS Code makes the view first (its focus
  // command) and run goes once it has: true, not now. Else false
  openLater(run: () => void): boolean {
    if (!this.inSideBar() || this.sideView) return false;
    this.sideNext = run;
    void vscode.commands.executeCommand(`${CHAT_VIEW}.focus`);
    return true;
  }

  // A chat's page: the side bar's view as its panel, with the side bar its place (the chat that was there
  // closes: a message it held still goes); else a tab of its own
  open(_key: string, title: string, page: ChatPage): PaneSurface {
    const view = this.inSideBar() ? this.sideView : undefined;
    let panel: vscode.WebviewPanel;
    if (view) {
      this.side?.dispose();
      view.show(false);
      panel = new ViewSurface(view, chatWebviewOptions(this.extensionUri));
    } else {
      panel = vscode.window.createWebviewPanel("talpyDen.chat", title, vscode.ViewColumn.Active, {
        enableScripts: true,
        retainContextWhenHidden: true,
        // (and the pictures in your messages, shown small: Talpy Den's folder of them)
        localResourceRoots: [vscode.Uri.joinPath(this.extensionUri, "dist"), vscode.Uri.file(picturesDir())],
      });
    }
    panel.title = title; // (the view's too: the chat's name after its own)
    panel.iconPath = vscode.Uri.joinPath(this.extensionUri, "media", "talpy-chat.svg");   // (Talpa with a speech bubble, in colour: both themes)
    const surface = new ChatSurface(panel, this.host, () => !!this.side?.active);
    if (view) {
      this.side = surface;
      panel.onDidDispose(() => {
        if (this.side !== surface) return;
        this.side = undefined;
        if (this.sideView === view) this.showEmpty(view); // (closed with nothing after it)
      });
    }
    panel.webview.html = chatHtml(panel.webview, this.extensionUri, page);
    return surface;
  }
}

// What the side bar's view lets a chat's page do, as a tab does (ChatSurfaces.open): run its script,
// load the extension's files and the pictures in your messages (Talpy Den's folder of them)
function chatWebviewOptions(uri: vscode.Uri): vscode.WebviewOptions {
  return { enableScripts: true, localResourceRoots: [vscode.Uri.joinPath(uri, "dist"), vscode.Uri.file(picturesDir())] };
}

// A chat's page in its panel (an editor tab, or the side bar's view as one), as the core's ChatPanes uses it.
// Two things the page says are VS Code's alone, done here once (whoever listens) and not passed on: "focus"
// (the side bar's view: whether its keys are this chat's, as VS Code doesn't say which view has the focus) and
// "paste"; onDidReceive passes on the rest, until the panel closes
class ChatSurface implements PaneSurface {
  private received = new Emitter<PaneMessage>();
  readonly onDidReceive: Event<PaneMessage> = this.received.event;

  // sideFocused: the side bar's chat has the focus, so a tab's keys aren't its own though it's the editor in front
  constructor(private panel: vscode.WebviewPanel, private host: HostServices, private sideFocused: () => boolean) {
    // (the side bar's view outlives its chat: the next one listens to its page, this one no more)
    const listening = panel.webview.onDidReceiveMessage((m: unknown) => this.receive(m));
    panel.onDidDispose(() => {
      listening.dispose();
      this.received.dispose();
    });
  }

  post(message: PaneHostMessage): void {
    void this.panel.webview.postMessage(message);
  }
  reveal(): void {
    this.panel.reveal();
  }
  get visible(): boolean {
    return this.panel.visible;
  }
  get active(): boolean {
    return this.panel instanceof ViewSurface ? this.panel.active : this.panel.active && !this.sideFocused();
  }
  get title(): string {
    return this.panel.title;
  }
  set title(text: string) {
    this.panel.title = text;
  }
  resourceUri(path: string): string {
    return this.panel.webview.asWebviewUri(vscode.Uri.file(path)).toString();
  }

  private receive(m: unknown): void {
    const type = m && typeof m === "object" ? (m as { type?: unknown }).type : undefined;
    if (type === "focus") {
      if (this.panel instanceof ViewSurface) this.panel.focus((m as { on?: unknown }).on === true);
    } else if (type === "paste") {
      // (the right-click menu's Paste in the reply box: what Ctrl+V runs there, so a picture on the
      // clipboard comes in as a pasted one)
      Promise.resolve(vscode.commands.executeCommand("editor.action.clipboardPasteAction"))
        .catch((e) => this.host.log.warn(`Talpy Chat's request failed: ${e instanceof Error ? e.message : String(e)}`));
    } else this.received.fire(m as PaneMessage);
  }
  // (focus moving between editors too: the core goes by visible)
  readonly onDidChangeView: Event<void> = (listener) => this.panel.onDidChangeViewState(() => listener(undefined));
  readonly onDidDispose: Event<void> = (listener) => this.panel.onDidDispose(() => listener(undefined));

  dispose(): void {
    this.panel.dispose();
  }
}

// A chat's page: its script and style from the extension's dist/, what it starts with (page, as
// window.CLAUDE_CHAT), nothing loaded from anywhere else
function chatHtml(webview: vscode.Webview, root: vscode.Uri, page: ChatPage): string {
  const nonce = crypto.randomBytes(16).toString("base64");
  const asset = (...p: string[]) => webview.asWebviewUri(vscode.Uri.joinPath(root, ...p)).toString();
  const config = JSON.stringify(page);
  const csp = [
    "default-src 'none'",
    "base-uri 'none'",
    "form-action 'none'",
    `img-src ${webview.cspSource} data:`,
    `style-src ${webview.cspSource} 'unsafe-inline'`,
    `font-src ${webview.cspSource}`,
    `script-src 'nonce-${nonce}'`,
  ].join("; ");
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="${csp}">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="stylesheet" href="${asset("dist", "webview-style.css")}">
<title>Talpy Chat</title>
</head>
<body class="chat-page">
<script nonce="${nonce}">window.CLAUDE_CHAT = ${config.replace(/</g, "\\u003c")};</script>
<script nonce="${nonce}" src="${asset("dist", "chat.js")}"></script>
</body>
</html>`;
}
