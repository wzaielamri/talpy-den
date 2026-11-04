// A plan, a subagent's run or a memory, shown in Talpy Den's own tab (one,
// reused), rendered as the chat tab renders replies (webview/doc.tsx), not
// in VS Code's Markdown preview: that loads the web pictures a file names
// (![](https://…?d=…) is fetched the moment you open it, a way out for what
// a chat read), where this page's CSP lets in no picture from anywhere but
// Talpy Den itself. Open as text shows the file in the editor (a plan's
// comments and Send Feedback to Claude are there). The page follows the
// file while it's open. Made only on a click.

import * as crypto from "node:crypto";
import * as os from "node:os";
import * as path from "node:path";
import * as vscode from "vscode";
import { textScale } from "./shared/pane";

let extensionUri: vscode.Uri | undefined;

// Set once at activation: where the page's script and style are
export function initDocs(uri: vscode.Uri): void {
  extensionUri = uri;
}

// Its title: its first heading, else the file's name
export function docTitle(text: string, file: string): string {
  const heading = /^#{1,6}\s+(.+?)\s*#*\s*$/m.exec(text.slice(0, 20000));
  const title = heading ? heading[1].replace(/[*_`]/g, "") : path.basename(file, ".md");
  return title.length > 60 ? `${title.slice(0, 59)}…` : title;
}

// The page: its text (and its file's name) in it, nothing loaded but Talpy Den's own script and style
export function docHtml(webview: Pick<vscode.Webview, "cspSource" | "asWebviewUri">, root: vscode.Uri, doc: { text: string; file: string },
  look: { scale: number; font: string }): string {
  const nonce = crypto.randomBytes(16).toString("base64");
  const asset = (...p: string[]) => webview.asWebviewUri(vscode.Uri.joinPath(root, ...p)).toString();
  const csp = [
    "default-src 'none'",
    "base-uri 'none'",
    "form-action 'none'",
    `img-src ${webview.cspSource} data:`,
    `style-src ${webview.cspSource} 'unsafe-inline'`,
    `font-src ${webview.cspSource}`,
    `script-src 'nonce-${nonce}'`,
  ].join("; ");
  const config = JSON.stringify({ ...doc, ...look }).replace(/</g, "\\u003c");
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="${csp}">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="stylesheet" href="${asset("dist", "webview-style.css")}">
<title>Talpy Den</title>
</head>
<body class="chat-page">
<script nonce="${nonce}">window.TALPY_DOC = ${config};</script>
<script nonce="${nonce}" src="${asset("dist", "doc.js")}"></script>
</body>
</html>`;
}

class DocView {
  private panel: vscode.WebviewPanel | undefined;
  private uri: vscode.Uri | undefined;
  private watcher: vscode.Disposable | undefined;
  private reading = 0;

  constructor(private root: vscode.Uri) {}

  // the error to report, or ""
  async show(uri: vscode.Uri): Promise<string> {
    let text: string;
    try {
      text = new TextDecoder().decode(await vscode.workspace.fs.readFile(uri));
    } catch (e) {
      return e instanceof Error ? e.message : String(e);
    }
    const title = docTitle(text, uri.path);
    this.uri = uri;
    if (!this.panel) {
      this.panel = vscode.window.createWebviewPanel("talpyDen.doc", title, vscode.ViewColumn.Active, {
        enableScripts: true,
        retainContextWhenHidden: true, // (where you scrolled to stays)
        localResourceRoots: [vscode.Uri.joinPath(this.root, "dist")],
      });
      this.panel.iconPath = vscode.Uri.joinPath(this.root, "media", "talpy.svg");
      this.panel.webview.onDidReceiveMessage((m: unknown) => void this.receive(m));
      this.panel.onDidDispose(() => {
        this.watcher?.dispose();
        this.panel = this.watcher = this.uri = undefined;
      });
    } else {
      this.panel.title = title;
      this.panel.reveal();
    }
    // (its file named from ~ on, its own heading as its title)
    const home = os.homedir();
    const file = uri.path === home || uri.path.startsWith(home + "/") ? "~" + uri.path.slice(home.length) : uri.path;
    this.panel.webview.html = docHtml(this.panel.webview, this.root, { text, file }, look());
    this.follow(uri);
    return "";
  }

  // The file changed (Claude revised its plan): the page shows it as it is now
  private follow(uri: vscode.Uri): void {
    this.watcher?.dispose();
    const watcher = vscode.workspace.createFileSystemWatcher(new vscode.RelativePattern(vscode.Uri.joinPath(uri, ".."), path.posix.basename(uri.path)));
    const again = () => void this.reread(uri);
    watcher.onDidChange(again);
    watcher.onDidCreate(again);
    this.watcher = watcher;
  }

  private async reread(uri: vscode.Uri): Promise<void> {
    const n = ++this.reading;
    try {
      const text = new TextDecoder().decode(await vscode.workspace.fs.readFile(uri));
      if (n !== this.reading || !this.panel || this.uri?.toString() !== uri.toString()) return;
      this.panel.title = docTitle(text, uri.path);
      void this.panel.webview.postMessage({ type: "doc", text });
    } catch {
      // (gone or being written: the next change shows it)
    }
  }

  private async receive(m: unknown): Promise<void> {
    const msg = m as { type?: unknown; text?: unknown };
    if (msg?.type === "openText" && this.uri) {
      try {
        await vscode.window.showTextDocument(this.uri, { preview: false, viewColumn: this.panel?.viewColumn });
      } catch (e) {
        void vscode.window.showErrorMessage(`Talpy Den: couldn't open ${this.uri.path}: ${e instanceof Error ? e.message : String(e)}`);
      }
    } else if (msg?.type === "copy" && typeof msg.text === "string") {
      await vscode.env.clipboard.writeText(msg.text);
    }
  }
}

// The conversation's font (talpyDen.chatFont): the terminal's, as Claude's
// terminal shows a chat (terminal.integrated.fontFamily, which falls back to
// the editor's), the editor's, or "" (VS Code's own); the chat tab's and this page's
export function chatFont(): string {
  const which = vscode.workspace.getConfiguration("talpyDen").get("chatFont");
  if (which === "ui") return "";
  const editor = vscode.workspace.getConfiguration("editor").get<string>("fontFamily") || "var(--vscode-editor-font-family, monospace)";
  const terminal = which === "editor" ? "" : vscode.workspace.getConfiguration("terminal.integrated").get<string>("fontFamily") || "";
  return terminal || editor;
}

// The chat tab's text size and font
function look(): { scale: number; font: string } {
  return { scale: textScale(vscode.workspace.getConfiguration("talpyDen").get("chatTextScale")), font: chatFont() };
}

let view: DocView | undefined;

// A Markdown file in Talpy Den's tab; the error to report, or ""
export async function showDoc(uri: vscode.Uri): Promise<string> {
  if (!extensionUri) return "Talpy Den isn't ready yet";
  view ??= new DocView(extensionUri);
  return view.show(uri);
}
