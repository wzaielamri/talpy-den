// Which SSH host this VS Code window is connected to (Remote-SSH), or which
// container (Dev Containers: attached-container, dev-container), if any.
// The extension itself always runs on this computer ("extensionKind": ["ui"]),
// so it reaches that host with its own ssh, like any other picked host.

import { spawnSync } from "node:child_process";
import { containerOf } from "./shared/model";

// The host names remote.py accepts (its HOST_NAME)
export const HOST_NAME = /^[A-Za-z0-9_.@][A-Za-z0-9_.@:-]*$/;

// "ssh-remote+myhost" -> "myhost". Remote-SSH writes names that don't fit in
// a URI authority (upper case, user@host, …) as hex-encoded JSON:
// "ssh-remote+7b22686f73744e616d65223a…" -> {"hostName":"…","user":"…"}.
export function hostFromAuthority(authority: string | undefined): string | undefined {
  let host = withPort(authority);
  if (!host) return undefined;
  // "user@host:2222": ssh takes no port in the destination; keep host aliases simple
  if (host.includes(":")) host = host.slice(0, host.indexOf(":"));
  return HOST_NAME.test(host) ? host : undefined;
}

// The port the window reached its host on, when one was given ("user@host:2222"
// typed into Remote-SSH's connect box): ssh <host> may go to another one
export function portFromAuthority(authority: string | undefined): number | undefined {
  const host = hostFromAuthority(authority) ? withPort(authority) : undefined;
  const port = host?.includes(":") ? Number(host.slice(host.lastIndexOf(":") + 1)) : NaN;
  return Number.isInteger(port) && port > 0 && port < 65536 ? port : undefined;
}

// The port ssh <host> connects to (ssh -G: ~/.ssh/config applied, nothing
// connected), or undefined when ssh can't say
export function sshPort(host: string): number | undefined {
  const r = spawnSync("ssh", ["-G", host], { encoding: "utf8", timeout: 5000 });
  const m = /^port (\d+)$/m.exec(r.stdout ?? "");
  return m ? Number(m[1]) : undefined;
}

// The authority's user@host[:port]
function withPort(authority: string | undefined): string | undefined {
  if (!authority) return undefined;
  const plus = authority.indexOf("+");
  if (plus < 0 || authority.slice(0, plus) !== "ssh-remote") return undefined;
  let rest = authority.slice(plus + 1);
  try {
    rest = decodeURIComponent(rest);
  } catch {
    return undefined;
  }
  let host = rest;
  if (/^(?:[0-9a-f]{2})+$/i.test(rest) && rest.startsWith("7b")) {
    try {
      const decoded = JSON.parse(Buffer.from(rest, "hex").toString("utf8"));
      if (decoded && typeof decoded.hostName === "string") {
        host = (typeof decoded.user === "string" && decoded.user ? decoded.user + "@" : "") + decoded.hostName;
        if (typeof decoded.port === "number" || (typeof decoded.port === "string" && decoded.port)) host += ":" + decoded.port;
      }
    } catch {
      // not JSON after all: a host name made of hex digits
    }
  }
  return host;
}

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

// The container a Dev Containers window is in, as remote.py names it
// (engine:NAME, engine:NAME@HOST through Remote-SSH): its authority names it
// (attached-container: {"containerName": "/NAME"} in hex JSON, or its id),
// or its project folder and config file do (dev-container: {"hostPath": …,
// "configFile": …}), looked up in the containers listed (known) of the engine
// Dev Containers runs (dockerPath, its setting; a docker that is Podman's
// reaches Podman's: viaDocker). "" for a container window it can't name (not
// listed yet, or more than one fits); undefined for a window that isn't in
// a container.
export function containerFromAuthority(
  authority: string | undefined,
  known: { id: string; engine: string; name: string; folder?: string; configFile?: string; cid?: string; host?: string; viaDocker?: boolean }[],
  dockerPath = "docker",
): string | undefined {
  const m = /^(attached-container|dev-container)\+([0-9a-fA-F]+)(?:@(.+))?$/.exec(authority ?? "");
  if (!m) return undefined;
  const host = m[3] ? hostFromAuthority(m[3]) : "";
  if (m[3] && !host) return ""; // (through something else than Remote-SSH: WSL, a tunnel)
  let config: Record<string, unknown> | string;
  try {
    const text = Buffer.from(m[2], "hex").toString("utf8");
    config = text.startsWith("{") ? JSON.parse(text) : text;
  } catch {
    return "";
  }
  const base = dockerPath.split("/").pop() ?? "docker";
  const engine = base === "podman" || base === "nerdctl" ? base : "docker";
  // (a listed one whose id is that container on this host, a host's list can't name another
  // place; of the engine the window's Dev Containers runs)
  const here = known.filter((c) => {
    const id = containerOf(c.id);
    return (c.host ?? "") === host && !!id && id.host === host && id.engine === c.engine && id.name === c.name
      && (c.engine === engine || (engine === "docker" && !!c.viaDocker));
  });
  let found: typeof known = [];
  let name = "";
  if (typeof config === "string") {
    found = here.filter((c) => c.cid === config || (c.cid ?? "").startsWith(config as string)); // (an id)
  } else if (m[1] === "attached-container" && typeof config.containerName === "string") {
    name = config.containerName.replace(/^\//, "");
    found = here.filter((c) => c.name === name);
  } else if (typeof config.hostPath === "string") {
    // its project folder (the dev container made for it) and, when both say, its config file
    const cf = config.configFile as { fsPath?: unknown; path?: unknown } | string | undefined;
    const file = typeof cf === "string" ? cf : typeof cf?.fsPath === "string" ? cf.fsPath : typeof cf?.path === "string" ? cf.path : "";
    found = here.filter((c) => c.folder === config.hostPath && (!file || !c.configFile || c.configFile === file));
  }
  if (found.length) return found.length === 1 ? found[0].id : "";
  if (!name || !/^[A-Za-z0-9][A-Za-z0-9_.-]*$/.test(name)) return "";
  return `${engine}:${name}` + (host ? `@${host}` : "");
}

// A file of the host this window is connected to, as the window names it.
// (VS Code maps file: to and from vscode-local only for extensions running
// on the host: to this one, file: is a file of this computer.)
export function windowHostFile(vscode: typeof import("vscode"), file: string): import("vscode").Uri | undefined {
  const authority = currentRemoteAuthority(vscode);
  return authority ? vscode.Uri.from({ scheme: "vscode-remote", authority, path: file }) : undefined;
}
