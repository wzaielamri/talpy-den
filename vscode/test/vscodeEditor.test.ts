// VsCodeEditor, the EditorPort on VS Code: each part of VS Code's own UI the core asks for (the changes
// view, Talpy Den's doc tab, an editor tab, the plan review's comments, Claude Code's panel), shown as the
// extension shows it today.

import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";
import * as vscode from "vscode";
import * as stub from "./vscode-stub";
import "./useHost";
import { initDocs } from "../src/doc";
import type { PlanReview } from "../src/planReview";
import { VsCodeEditor } from "../src/vscodeEditor";
import type { Comparison } from "../../core/src/comparisons";

const last = () => stub.calls[stub.calls.length - 1];
const named = (u: vscode.Uri) => `${u.scheme}:${u.authority}:${u.path}`;

beforeEach(() => {
  stub.calls.length = 0;
  stub.answers.clear();
  stub.sectionValues.clear();
  stub.workspace.textDocuments = [];
  stub.env.remoteName = undefined;
  stub.setWorkspaceFolders(undefined);
  initDocs(vscode.Uri.file("/ext"));
});

test("openComparison opens VS Code's changes view", async () => {
  const c: Comparison = {
    title: "Fix the parser: all changes",
    folder: "/home/me/app",
    items: [{ label: "parse.ts", path: "/home/me/app/parse.ts", original: "/cache/changes/1/0/parse.ts", created: false, deleted: false }],
  };
  assert.equal(await new VsCodeEditor().openComparison(c), "");
  const { method, args } = last();
  assert.equal(method, "executeCommand");
  assert.equal(args[0], "vscode.changes");
  assert.equal(args[1], "Fix the parser: all changes");
  assert.deepEqual((args[2] as (vscode.Uri | undefined)[][]).map((r) => r.map((u) => u?.path)), [
    ["/home/me/app/parse.ts", "/cache/changes/1/0/parse.ts", "/home/me/app/parse.ts"],
  ]);
});

test("showDoc opens Talpy Den's doc tab", async () => {
  stub.stubFiles.set("/home/me/.claude/plans/calm-red-owl.md", "# Ship the parser");
  const before = stub.recorded.panels.length;
  const editor = new VsCodeEditor();
  assert.equal(await editor.showDoc("/home/me/.claude/plans/calm-red-owl.md"), "");
  assert.equal(stub.recorded.panels.length, before + 1);
  const panel = stub.recorded.panels.at(-1)! as unknown as { title: string } & (typeof stub.recorded.panels)[number];
  assert.equal(panel.title, "Ship the parser");
  // a file it can't read: the error, to report
  assert.match(await editor.showDoc("/home/me/.claude/plans/gone.md"), /no file/);
  panel.dispose();
});

// actions' openPlan and openMemory: a plan or memory of the host a Remote-SSH window is connected to opens as
// the window names it (vscode-remote), one of this computer as file: (windowHostFile)
test("a file of the window's host opens as the window names it, in the doc tab or an editor tab", async () => {
  const fsRead = stub.workspace.fs.readFile;
  const window = vscode.window as unknown as { showTextDocument: (...a: unknown[]) => Promise<unknown> };
  const realShow = window.showTextDocument;
  const read: vscode.Uri[] = [];
  const shown: unknown[][] = [];
  const file = "/home/me/.claude/plans/p.md";
  try {
    stub.stubFiles.set(file, "# P");
    (stub.workspace.fs as { readFile: unknown }).readFile = async (u: vscode.Uri) => (read.push(u), fsRead(u));
    window.showTextDocument = async (...a: unknown[]) => void shown.push(a);
    const editor = new VsCodeEditor();
    stub.env.remoteName = "ssh-remote";
    stub.setWorkspaceFolders([{ name: "app", uri: vscode.Uri.from({ scheme: "vscode-remote", authority: "ssh-remote+lab", path: "/home/me/app" }) }]);
    assert.equal(await editor.showDoc(file, { onWindowHost: true }), "");
    await editor.editFile(file, { onWindowHost: true });
    // (this computer's: file:, in a Remote-SSH window too)
    assert.equal(await editor.showDoc(file), "");
    await editor.editFile(file);
    // (a window with no remote: file:)
    stub.env.remoteName = undefined;
    stub.setWorkspaceFolders(undefined);
    await editor.editFile(file, { onWindowHost: true });
    const there = `vscode-remote:ssh-remote+lab:${file}`;
    const here = `file::${file}`;
    assert.deepEqual(read.map(named), [there, here]);
    assert.deepEqual(shown.map(([u, o]) => [named(u as vscode.Uri), o]), [[there, { preview: false }], [here, { preview: false }], [here, { preview: false }]]);
    // one that can't open: the error is thrown, for the caller to report
    window.showTextDocument = async () => {
      throw new Error("cannot open file:///nowhere");
    };
    await assert.rejects(editor.editFile("/nowhere"), /cannot open/);
  } finally {
    (stub.workspace.fs as { readFile: unknown }).readFile = fsRead;
    window.showTextDocument = realShow;
    stub.recorded.panels.at(-1)?.dispose();
  }
});

// actions' sendPlanFeedback: what you changed and didn't save yet counts, then your comments on the plan's lines
test("plan feedback: an editor's unsaved changes are saved, the plan review's comments read and cleared", async () => {
  const editor = new VsCodeEditor();
  const saved: string[] = [];
  const doc = (path: string, isDirty: boolean) => ({ uri: vscode.Uri.file(path), isDirty, save: async () => (saved.push(path), true) });
  stub.workspace.textDocuments = [doc("/p/a.md", true), doc("/p/b.md", false)];
  await editor.saveEdits("/p/a.md");
  await editor.saveEdits("/p/b.md"); // (nothing unsaved)
  await editor.saveEdits("/p/c.md"); // (not open)
  assert.deepEqual(saved, ["/p/a.md"]);
  // no plan review yet: no comments, nothing to clear
  assert.deepEqual(await editor.planComments("/p/a.md"), []);
  editor.clearPlanComments("/p/a.md");
  const comment = { from: 3, to: 4, quote: "- step two", text: "Do this first" };
  const cleared: string[] = [];
  editor.planReview = { comments: async (f: string) => (f === "/p/a.md" ? [comment] : []), clear: (f: string) => void cleared.push(f) } as unknown as PlanReview;
  assert.deepEqual(await editor.planComments("/p/a.md"), [comment]);
  editor.clearPlanComments("/p/a.md");
  assert.deepEqual(cleared, ["/p/a.md"]);
});

test("Claude Code's panel: whether it's here, the account it runs on, a new chat in it, a change of extensions", async () => {
  const editor = new VsCodeEditor();
  const commands = vscode.commands as unknown as { getCommands: () => Promise<string[]> };
  const realCommands = commands.getCommands;
  try {
    assert.equal(await editor.claudePanelAvailable(), false);
    commands.getCommands = async () => ["workbench.action.reloadWindow", "claude-vscode.editor.open"];
    assert.equal(await editor.claudePanelAvailable(), true);
  } finally {
    commands.getCommands = realCommands;
  }
  stub.sectionValues.set("claudeCode.environmentVariables", [{ name: "CLAUDE_CONFIG_DIR", value: "/nowhere/.claude-work" }]);
  assert.equal(editor.localPanelConfigDir(), "/nowhere/.claude-work");
  assert.equal(editor.localPanelProfileKey(), ".claude-work");
  await editor.openPanelChat("Fix the parser");
  assert.deepEqual(last(), { method: "executeCommand", args: ["claude-vscode.editor.open", undefined, "Fix the parser"] });
  await editor.openPanelChat();
  assert.deepEqual(last(), { method: "executeCommand", args: ["claude-vscode.editor.open"] });
  let changes = 0;
  const subscription = editor.onDidChangeClaudePanel(() => changes++);
  stub.changeExtensions();
  subscription.dispose();
  stub.changeExtensions();
  assert.equal(changes, 1);
});

// accountSwitch's switch: no Claude Code extension, no VS Code Claude to switch. Installed is not the same as
// its panel being available: in an untrusted folder it's there, its commands not registered
test("claudeCodeInstalled: whether the Claude Code extension is installed, even where its panel can't open chats", async () => {
  const editor = new VsCodeEditor();
  assert.equal(editor.claudeCodeInstalled(), false);
  try {
    stub.installedExtensions.add("anthropic.claude-code");
    assert.equal(editor.claudeCodeInstalled(), true);
    assert.equal(await editor.claudePanelAvailable(), false);
  } finally {
    stub.installedExtensions.clear();
  }
  stub.installedExtensions.add("someone.else");
  assert.equal(editor.claudeCodeInstalled(), false);
  stub.installedExtensions.clear();
});
