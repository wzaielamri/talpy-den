// The parts of remoteHost that ask VS Code which host this window is connected
// to (the rest is in core/src/agents/claudeCode/remoteHost.ts).

import { hostFromAuthority } from "../../core/src/agents/claudeCode/remoteHost";

// The authority of whatever this window has open: a folder, a workspace file,
// or an editor (hostFromAuthority: its host).
export function currentRemoteAuthority(vscode: typeof import("vscode")): string | undefined {
  const remote = vscode.env.remoteName;
  if (remote !== "ssh-remote" && remote !== "attached-container" && remote !== "dev-container") return undefined;
  const uris = [
    ...(vscode.workspace.workspaceFolders ?? []).map((f) => f.uri),
    ...(vscode.workspace.workspaceFile ? [vscode.workspace.workspaceFile] : []),
    ...vscode.window.visibleTextEditors.map((e) => e.document.uri),
  ];
  for (const uri of uris) {
    if (uri.scheme !== "vscode-remote") continue;
    if (remote === "ssh-remote" ? hostFromAuthority(uri.authority) : uri.authority.startsWith(remote + "+")) return uri.authority;
  }
  return undefined;
}

// A file of the host this window is connected to, as the window names it.
// (VS Code maps file: to and from vscode-local only for extensions running
// on the host: to this one, file: is a file of this computer.)
export function windowHostFile(vscode: typeof import("vscode"), file: string): import("vscode").Uri | undefined {
  const authority = currentRemoteAuthority(vscode);
  return authority ? vscode.Uri.from({ scheme: "vscode-remote", authority, path: file }) : undefined;
}
