import { test, beforeEach } from "node:test";
import * as assert from "node:assert/strict";
import * as vscode from "vscode";
import * as stub from "./vscode-stub";
import * as fs from "node:fs";
import { settingNames } from "../src/legacySettings";
import { VsCodeHost } from "../src/vscodeHost";

const logLines: string[] = [];
const channel = { info: (m: string) => logLines.push(`info ${m}`), warn: (m: string) => logLines.push(`warn ${m}`), error: (m: string) => logLines.push(`error ${m}`) };
const keys = settingNames(JSON.parse(fs.readFileSync("package.json", "utf8")));
const make = () => new VsCodeHost(channel as unknown as vscode.LogOutputChannel, keys);
const last = () => stub.calls[stub.calls.length - 1];

beforeEach(() => {
  stub.calls.length = 0;
  stub.answers.clear();
  stub.sectionValues.clear();
  stub.overrides.clear();
  stub.setWorkspaceFolders(undefined);
  stub.env.remoteName = undefined;
  stub.env.uiKind = stub.UIKind.Desktop;
  logLines.length = 0;
});

test("message passes level, text, modal and detail, and returns the chosen action", async () => {
  const host = make();
  stub.answers.set("showWarningMessage", "Delete");
  const got = await host.message("warning", "Sure?", { modal: true, detail: "It can't be undone" }, "Delete", "Keep");
  assert.equal(got, "Delete");
  assert.deepEqual(last(), { method: "showWarningMessage", args: ["Sure?", { modal: true, detail: "It can't be undone" }, "Delete", "Keep"] });
  await host.message("info", "Hi");
  assert.equal(last().method, "showInformationMessage");
  assert.deepEqual(last().args, ["Hi", {}]);
  await host.message("error", "Oops");
  assert.equal(last().method, "showErrorMessage");
});

test("a cancelled message returns undefined", async () => {
  assert.equal(await make().message("info", "Hi", undefined, "Ok"), undefined);
});

test("pick maps separators and icons and returns the caller's item", async () => {
  const mine = { label: "Home", icon: "folder", id: 7 };
  let shown: Record<string, unknown>[] = [];
  stub.answers.set("showQuickPick", (items: Record<string, unknown>[]) => ((shown = items), items[1]));
  const got = await make().pick([{ label: "Recent", separator: true }, mine], { title: "Where", placeHolder: "a folder", matchOnDescription: true });
  assert.equal(got, mine);
  assert.equal(shown[0].kind, vscode.QuickPickItemKind.Separator);
  assert.deepEqual(shown[1].iconPath, new vscode.ThemeIcon("folder"));
  assert.deepEqual(last().args[1], { title: "Where", placeHolder: "a folder", matchOnDescription: true });
  stub.answers.set("showQuickPick", undefined);
  assert.equal(await make().pick([mine]), undefined);
});

test("pickMany passes canPickMany and returns the caller's items", async () => {
  const a = { label: "a" };
  const b = { label: "b", picked: true };
  stub.answers.set("showQuickPick", (items: unknown[]) => items);
  const got = await make().pickMany([a, b], { title: "Which" });
  assert.equal((last().args[1] as { canPickMany: boolean }).canPickMany, true);
  assert.equal(got?.length, 2);
  assert.equal(got?.[0], a);
  assert.equal(got?.[1], b);
  stub.answers.set("showQuickPick", undefined);
  assert.equal(await make().pickMany([a]), undefined);
});

test("input passes its options, validateInput included", async () => {
  const validateInput = (v: string) => (v ? undefined : "empty");
  stub.answers.set("showInputBox", "typed");
  const got = await make().input({ title: "T", prompt: "P", placeHolder: "H", value: "V", password: true, ignoreFocusOut: true, validateInput });
  assert.equal(got, "typed");
  assert.deepEqual(last().args[0], { title: "T", prompt: "P", placeHolder: "H", value: "V", password: true, ignoreFocusOut: true, validateInput });
});

test("choose a folder: canSelectFolders, the default path and the open label", async () => {
  stub.answers.set("showOpenDialog", [vscode.Uri.file("/home/me/proj")]);
  const got = await make().choose({ kind: "folder", title: "Where", openLabel: "Start Chat Here", defaultPath: "/home/me" });
  assert.deepEqual(got, ["/home/me/proj"]);
  const o = last().args[0] as { canSelectFolders: boolean; canSelectFiles: boolean; canSelectMany: boolean; defaultUri: vscode.Uri; openLabel: string; title: string };
  assert.equal(o.canSelectFolders, true);
  assert.equal(o.canSelectFiles, false);
  assert.equal(o.canSelectMany, false);
  assert.equal(o.defaultUri.fsPath, "/home/me");
  assert.equal(o.openLabel, "Start Chat Here");
  assert.equal(o.title, "Where");
  stub.answers.set("showOpenDialog", undefined);
  assert.equal(await make().choose({ kind: "folder" }), undefined);
  stub.answers.set("showOpenDialog", []);
  assert.equal(await make().choose({ kind: "folder" }), undefined);
});

test("choose on the remote uses the remote scheme", async () => {
  stub.env.remoteName = "ssh-remote";
  stub.setWorkspaceFolders([{ name: "proj", uri: vscode.Uri.from({ scheme: "vscode-remote", authority: "ssh-remote+box", path: "/srv/proj" }) }]);
  stub.answers.set("showOpenDialog", [vscode.Uri.from({ scheme: "vscode-remote", authority: "ssh-remote+box", path: "/srv/other" })]);
  const got = await make().choose({ kind: "folder", onRemote: true, defaultPath: "/home/you" });
  assert.deepEqual(got, ["/srv/other"]);
  const uri = (last().args[0] as { defaultUri: vscode.Uri }).defaultUri;
  assert.equal(uri.scheme, "vscode-remote");
  assert.equal(uri.authority, "ssh-remote+box");
  assert.equal(uri.path, "/home/you");
  // no folder open to borrow a scheme from: VS Code picks the start
  stub.setWorkspaceFolders(undefined);
  await make().choose({ kind: "folder", onRemote: true, defaultPath: "/home/you" });
  assert.equal((last().args[0] as { defaultUri?: unknown }).defaultUri, undefined);
});

test("choose files with filters and many", async () => {
  stub.answers.set("showOpenDialog", [vscode.Uri.file("/a.png"), vscode.Uri.file("/b.jpg")]);
  const filters = { Pictures: ["png", "jpg"] };
  const got = await make().choose({ kind: "file", many: true, filters });
  assert.deepEqual(got, ["/a.png", "/b.jpg"]);
  const o = last().args[0] as { canSelectFiles: boolean; canSelectFolders: boolean; canSelectMany: boolean; filters: unknown };
  assert.equal(o.canSelectFiles, true);
  assert.equal(o.canSelectFolders, false);
  assert.equal(o.canSelectMany, true);
  assert.deepEqual(o.filters, filters);
});

test("progress uses the window or a notification", async () => {
  const host = make();
  assert.equal(await host.progress({ where: "window", title: "Working" }, async () => 5), 5);
  assert.deepEqual(last().args[0], { location: vscode.ProgressLocation.Window, title: "Working" });
  assert.equal(await host.progress({ where: "notification", title: "Installing" }, async () => "done"), "done");
  assert.deepEqual(last().args[0], { location: vscode.ProgressLocation.Notification, title: "Installing" });
});

test("settings get reads talpyDen.<key>, update writes the global scope", async () => {
  const host = make();
  stub.overrides.set("chatTextScale", 1.5);
  assert.equal(host.settings.get("chatTextScale", 1), 1.5);
  assert.equal(host.settings.get("nothingSet", "dflt"), "dflt");
  await host.settings.update("chatTextScale", 2);
  assert.deepEqual(last(), { method: "config.update", args: ["talpyDen", "chatTextScale", 2, vscode.ConfigurationTarget.Global] });
  stub.answers.set("config.inspect", { globalValue: 1, workspaceValue: 2, workspaceFolderValue: 3, defaultValue: 0 });
  assert.deepEqual(host.settings.inspect("chatTextScale"), { global: 1, workspace: 2, workspaceFolder: 3 });
  stub.answers.set("config.inspect", undefined);
  assert.equal(host.settings.inspect("chatTextScale"), undefined);
});

test("settings onDidChange fires with the changed talpyDen keys", () => {
  const host = make();
  const got: string[][] = [];
  const sub = host.settings.onDidChange((keys) => got.push(keys));
  stub.changeSettings("talpyDen.chatTextScale");
  assert.deepEqual(got, [["chatTextScale"]]);
  stub.changeSettings("editor.fontSize");
  assert.equal(got.length, 1);
  stub.changeSettings("talpyDen.chatTextScale", "talpyDen.diffSideBySide", "files.exclude");
  assert.deepEqual(got[1].sort(), ["chatTextScale", "diffSideBySide"]);
  sub.dispose();
  stub.changeSettings("talpyDen.chatTextScale");
  assert.equal(got.length, 2);
});

test("settings other reads another section", () => {
  const host = make();
  stub.sectionValues.set("terminal.integrated.fontFamily", "Fira");
  assert.equal(host.settings.other("terminal.integrated", "fontFamily", ""), "Fira");
  assert.equal(host.settings.other("editor", "fontFamily", "mono"), "mono");
});

test("focus mirrors window state and fires on change", () => {
  const host = make();
  stub.setWindowFocused(false);
  assert.equal(host.focus.focused, false);
  const got: boolean[] = [];
  host.focus.onDidChange((f) => got.push(f));
  stub.setWindowFocused(true);
  assert.equal(host.focus.focused, true);
  stub.setWindowFocused(false);
  assert.deepEqual(got, [true, false]);
});

test("workspaceFolders lists names and paths and tells of changes", () => {
  const host = make();
  assert.deepEqual(host.workspaceFolders(), []);
  let changes = 0;
  host.onDidChangeWorkspaceFolders(() => changes++);
  stub.setWorkspaceFolders([{ name: "proj", uri: vscode.Uri.file("/home/me/proj") }]);
  assert.deepEqual(host.workspaceFolders(), [{ name: "proj", path: "/home/me/proj" }]);
  assert.equal(changes, 1);
});

test("environment mirrors remoteName and web", () => {
  const host = make();
  assert.equal(host.environment.remoteName, undefined);
  assert.equal(host.environment.web, false);
  stub.env.remoteName = "ssh-remote";
  stub.env.uiKind = stub.UIKind.Web;
  assert.equal(host.environment.remoteName, "ssh-remote");
  assert.equal(host.environment.web, true);
});

test("environment's remoteAuthority is the remote the window has open, read anew each time", () => {
  const host = make();
  const remoteFolder = (authority: string) => [{ name: "app", uri: vscode.Uri.from({ scheme: "vscode-remote", authority, path: "/home/me/app" }) }];
  assert.equal(host.environment.remoteAuthority, undefined);
  stub.env.remoteName = "ssh-remote";
  stub.setWorkspaceFolders(remoteFolder("ssh-remote+lab"));
  assert.equal(host.environment.remoteAuthority, "ssh-remote+lab");
  stub.setWorkspaceFolders(remoteFolder("ssh-remote+other"));
  assert.equal(host.environment.remoteAuthority, "ssh-remote+other");
  // (a Dev Containers window: its container's)
  stub.env.remoteName = "dev-container";
  stub.setWorkspaceFolders(remoteFolder("dev-container+6170"));
  assert.equal(host.environment.remoteAuthority, "dev-container+6170");
  // a remote window with nothing of the remote open, and a remote it doesn't know (WSL)
  stub.setWorkspaceFolders([{ name: "here", uri: vscode.Uri.file("/home/me/here") }]);
  assert.equal(host.environment.remoteAuthority, undefined);
  stub.env.remoteName = "wsl";
  stub.setWorkspaceFolders(remoteFolder("wsl+Ubuntu"));
  assert.equal(host.environment.remoteAuthority, undefined);
});

test("openFile, revealFile, openSettings, showView and setContext run their VS Code commands", async () => {
  const host = make();
  await host.openFile("/home/me/a.md");
  assert.equal(last().args[0], "vscode.open");
  assert.equal((last().args[1] as vscode.Uri).fsPath, "/home/me/a.md");
  await host.revealFile("/home/me/a.md");
  assert.equal(last().args[0], "revealFileInOS");
  assert.equal((last().args[1] as vscode.Uri).fsPath, "/home/me/a.md");
  await host.openSettings("talpyDen.chatTextScale");
  assert.deepEqual(last().args, ["workbench.action.openSettings", "talpyDen.chatTextScale"]);
  await host.showView();
  assert.deepEqual(last().args, ["talpyDen.view.focus"]);
  host.setContext("talpyDen.chatSideBar", true);
  assert.deepEqual(last().args, ["setContext", "talpyDen.chatSideBar", true]);
});

test("clipboard reads and writes", async () => {
  const host = make();
  await host.clipboard.write("copied");
  assert.equal(await host.clipboard.read(), "copied");
});

test("openExternal parses the URL", async () => {
  const host = make();
  assert.equal(await host.openExternal("https://example.com/x"), true);
  const uri = last().args[0] as vscode.Uri;
  assert.equal(uri.scheme, "https");
  assert.match(uri.toString(), /example\.com\/x/);
});

test("statusMessage sets the status bar message", () => {
  make().statusMessage("Copied", 2500);
  assert.deepEqual(last(), { method: "setStatusBarMessage", args: ["Copied", 2500] });
});

test("settings update writes the scope it's given, global by default", async () => {
  const host = make();
  await host.settings.update("reopenIn", "talpy");
  assert.equal(last().args[3], vscode.ConfigurationTarget.Global);
  await host.settings.update("reopenIn", "talpy", "global");
  assert.equal(last().args[3], vscode.ConfigurationTarget.Global);
  await host.settings.update("reopenIn", "talpy", "workspace");
  assert.deepEqual(last().args, ["talpyDen", "reopenIn", "talpy", vscode.ConfigurationTarget.Workspace]);
  await host.settings.update("reopenIn", "talpy", "workspaceFolder");
  assert.equal(last().args[3], vscode.ConfigurationTarget.WorkspaceFolder);
});

test("settings updateOther writes another section's key globally", async () => {
  await make().settings.updateOther("claudeCode", "environmentVariables", [{ name: "A", value: "b" }]);
  assert.deepEqual(last(), { method: "config.update", args: ["claudeCode", "environmentVariables", [{ name: "A", value: "b" }], vscode.ConfigurationTarget.Global] });
});

test("settings watchOther fires with the touched keys only", () => {
  const host = make();
  const got: string[][] = [];
  const sub = host.settings.watchOther(["editor.fontFamily", "terminal.integrated.fontFamily"])((keys) => got.push(keys));
  stub.changeSettings("files.exclude");
  assert.equal(got.length, 0);
  stub.changeSettings("terminal.integrated.fontFamily");
  assert.deepEqual(got, [["terminal.integrated.fontFamily"]]);
  stub.changeSettings("editor.fontFamily", "terminal.integrated.fontFamily");
  assert.deepEqual(got[1], ["editor.fontFamily", "terminal.integrated.fontFamily"]);
  sub.dispose();
  stub.changeSettings("editor.fontFamily");
  assert.equal(got.length, 2);
});

test("choose with localOnly keeps only this computer's files", async () => {
  const remote = vscode.Uri.from({ scheme: "vscode-remote", authority: "ssh-remote+box", path: "/srv/a.png" });
  stub.answers.set("showOpenDialog", [vscode.Uri.file("/home/me/b.png"), remote]);
  assert.deepEqual(await make().choose({ kind: "file", many: true, localOnly: true }), ["/home/me/b.png"]);
  assert.deepEqual(await make().choose({ kind: "file", many: true }), ["/home/me/b.png", "/srv/a.png"]);
  stub.answers.set("showOpenDialog", [remote]);
  assert.equal(await make().choose({ kind: "file", localOnly: true }), undefined);
});

test("log writes to the output channel", () => {
  const host = make();
  host.log.info("a");
  host.log.warn("b");
  host.log.error("c");
  assert.deepEqual(logLines, ["info a", "warn b", "error c"]);
});
