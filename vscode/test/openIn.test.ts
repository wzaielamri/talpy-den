// Stopping idle chats, where chats reopen: a terminal or a Claude Code panel,
// whichever is there (no claude command, Claude Code missing or on another
// account), and moving a running chat from its terminal to a Claude Code panel.

import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { test } from "node:test";
import {
  canEndChat,
  canMoveToClaudeCode,
  claudeCodeHere,
  hasTurn,
  claudeCodeReopenHint,
  cliInstalled,
  openChatsIn,
  opensInTalpyChat,
  reopensInClaudeCode,
  talpyChatHere,
  talpyChatHint,
  talpyChatOff,
  talpyChatTitle,
  terminalReopenHint,
  thisWindowFirst,
} from "../src/shared/model";
import type { Group, PlanItem } from "../src/shared/types";
import * as vscode from "vscode";
import type { AccountSwitch } from "../src/accountSwitch";
import { Actions, typedFolder } from "../src/actions";
import type { Backend } from "../src/backend";
import type { Dashboard } from "../src/dashboard";
import type { Terminals } from "../src/terminals";

const chat = { kind: "interactive", entrypoint: "cli", state: "idle", pid: 42 };

test("a chat with a process can be stopped, whatever it's doing; a working one interrupted", () => {
  assert.equal(canEndChat(chat), true);
  assert.equal(canEndChat({ ...chat, state: "working" }), true, "it asks first");
  assert.equal(canEndChat({ ...chat, entrypoint: "claude-vscode" }), true, "its Claude Code panel goes on");
  assert.equal(canEndChat({ ...chat, kind: "bg" }), false, "background sessions: claude stop");
  assert.equal(canEndChat({ ...chat, pid: null }), false, "no process");
  assert.equal(canEndChat({ kind: "chat", pid: null }), false, "a recent chat's reference");
  assert.deepEqual(["working", "waiting", "idle", "done"].map((state) => hasTurn({ state })), [true, true, false, false]);
});

test("the claude command counts as there unless the backend says it isn't", () => {
  assert.equal(cliInstalled(null), true);
  assert.equal(cliInstalled({}), true, "an older backend");
  assert.equal(cliInstalled({ cli: { installed: true } }), true);
  assert.equal(cliInstalled({ cli: { installed: false } }), false);
});

const work = { title: "work · Team", profileKeys: [".claude-work"] } as Pick<Group, "title" | "profileKeys"> as Group;
const personal = { title: "personal · Pro", profileKeys: [".claude-personal"] } as Group;
const onWork = { available: true, profileKey: ".claude-work" };

test("Claude Code reopens the chats of the account it runs on (a host's: the host's ~/.claude)", () => {
  assert.equal(claudeCodeHere(work, onWork), true);
  assert.equal(claudeCodeHere(personal, onWork), false);
  assert.equal(claudeCodeHere(work, { available: false, profileKey: null }), false, "not installed");
  assert.equal(claudeCodeHere({ ...personal, host: "lab", vscodeHere: true }, onWork), true);
  assert.equal(claudeCodeHere({ ...work, host: "lab", vscodeHere: false }, onWork), false);
});

test("recent chats reopen where you picked, or in Claude Code without a claude command", () => {
  assert.equal(reopensInClaudeCode("terminal", true, true), false);
  assert.equal(reopensInClaudeCode("claudeCode", true, true), true);
  assert.equal(reopensInClaudeCode("terminal", false, true), true, "no claude command");
  assert.equal(reopensInClaudeCode("claudeCode", true, false), false, "Claude Code isn't on this account");
});

test("Talpy Chat is one more choice: this computer's chats, a new one where a hook given to one chat runs", () => {
  const here = { cli: { installed: true } };
  const managed = { cli: { installed: true, hooks: false } };
  assert.equal(talpyChatHere(here, undefined, false), true);
  assert.equal(talpyChatHere(null, undefined, false), true, "not known yet: there");
  assert.equal(talpyChatHere(here, "lab", true), false, "an SSH host's prompts can't reach it yet");
  assert.equal(talpyChatHere({ cli: { installed: false } }, undefined, true), false);
  assert.equal(talpyChatHere(managed, undefined, false), false, "managed settings: only their own hooks");
  assert.equal(talpyChatHere(managed, undefined, true), true, "a chat that isn't running still opens there");
  // where chats open: Claude Code as before, Talpy Chat only where you picked it and it works
  assert.equal(openChatsIn("terminal", here, undefined, true, true), "terminal", "nobody's choice changes");
  assert.equal(openChatsIn("claudeCode", here, undefined, true, true), "claudeCode");
  assert.equal(openChatsIn("talpyChat", here, undefined, true, true), "talpyChat");
  assert.equal(openChatsIn("talpyChat", here, "lab", true, true), "terminal");
  assert.equal(openChatsIn("talpyChat", { cli: { installed: false } }, undefined, true, true), "claudeCode", "no claude command");
  assert.equal(openChatsIn("talpyChat", managed, undefined, false, false), "terminal");
  // its window: a chat that isn't running, or a background one no terminal shows
  assert.equal(opensInTalpyChat({ kind: "chat", pid: null }, "talpyChat", here, undefined, false), true);
  // a background chat no terminal shows: Talpy Chat whatever Open in says (this computer's; a host's in its terminal)
  assert.equal(opensInTalpyChat({ kind: "bg", pid: 7, attached: null }, "terminal", here, undefined, false), true);
  assert.equal(opensInTalpyChat({ kind: "bg", pid: 7, attached: null }, "claudeCode", here, undefined, true), true);
  assert.equal(opensInTalpyChat({ kind: "bg", pid: 7, attached: null }, "talpyChat", here, "gpu", false), false);
  assert.equal(opensInTalpyChat({ kind: "bg", pid: 7, attached: null }, "talpyChat", here, undefined, false), true);
  assert.equal(opensInTalpyChat({ kind: "bg", pid: 7, attached: { in: "terminal", app: "Konsole" } }, "talpyChat", here, undefined, false), false,
               "the terminal it's shown in");
  assert.equal(opensInTalpyChat({ kind: "interactive", pid: 7 }, "talpyChat", here, undefined, false), false, "running chats stay where they run");
  assert.equal(opensInTalpyChat({ kind: "chat", pid: null }, "terminal", here, undefined, false), false);
  // the same words as Plasma's
  assert.equal(talpyChatTitle(here, undefined, false), "New chats in Talpy Chat");
  assert.equal(talpyChatHint(here, undefined, false),
               "New chats run in the background and open here: reply, answer Claude's prompts, see what changed. Open one in a terminal any time.");
  assert.equal(talpyChatTitle(here, "lab", true), "This computer's chats for now");
  assert.equal(talpyChatTitle(here, "podman:web", false), "This computer's chats for now");
  assert.match(talpyChatHint(managed, undefined, false), /allowManagedHooksOnly/);
  // New Chat…'s line where its Talpy Chat section isn't offered: the switch's title and why
  assert.deepEqual(talpyChatOff(here, "lab"), { title: "This computer's chats for now", why: "it can't answer the prompts of a chat on lab yet" });
  assert.deepEqual(talpyChatOff(here, "podman:web"), { title: "This computer's chats for now", why: "it can't answer the prompts of a chat in web yet" });
  assert.deepEqual(talpyChatOff(managed, undefined), { title: "Hooks are off here", why: "managed settings here let only their own hooks run" });
  assert.equal(talpyChatOff(here, undefined), null, "offered");
  assert.equal(talpyChatOff({ cli: { installed: false } }, "lab"), null, "no claude command: the terminal's section says so");
});

test("in a Remote-SSH window, the section of its host comes first, then this computer's, then the other hosts", () => {
  const h = (name: string, current = false) => ({ name, current });
  assert.deepEqual(thisWindowFirst([h("lab"), h("build-server", true), h("podman:web")]), { first: [h("build-server", true)], rest: [h("lab"), h("podman:web")] });
  assert.deepEqual(thisWindowFirst([h("lab"), h("podman:web")]), { first: [], rest: [h("lab"), h("podman:web")] }, "a local window: as before");
});

test("New Chat… on an SSH host says where Talpy Chat isn't offered, in its section's place", async () => {
  const stub = vscode as unknown as typeof import("./vscode-stub");
  const window = stub.window as unknown as Record<string, unknown>;
  const pick = window.showQuickPick;
  const shown: { label: string; description?: string; kind?: number }[][] = [];
  window.showQuickPick = async (items: { label: string; description?: string; kind?: number }[]) => (shown.push(items), undefined);
  try {
    const group = (host: string) => ({
      id: host || "w", title: "work", chatProfile: ".claude", profileKeys: [".claude"], sessions: [], homeChatCommand: "cd ~ 2>/dev/null; claude", host: host || undefined,
      projects: [{ path: "/srv/app", short: "~/app", newChatCommand: "cd /srv/app 2>/dev/null; claude", trusted: true }],
    } as unknown as Group);
    const dash = { opened() {}, demo: false, currentHost: "build-server",
      state: () => ({ status: { groups: [group("")], cli: { installed: true } }, hosts: [{ name: "build-server", current: true, result: { groups: [group("build-server")], cli: { installed: true } } }] }),
      setActionError: () => undefined, isVisible: () => true };
    const actions = new Actions({ action: async () => ({ ok: true, message: "" }) } as unknown as Backend, dash as unknown as Dashboard,
      {} as unknown as Terminals, { warn: () => undefined } as unknown as vscode.LogOutputChannel, {} as AccountSwitch);
    await actions.newChat("build-server", "build-server");
    const labels = shown[0].map((i) => i.label);
    const at = labels.indexOf("In a Talpy Chat tab");
    assert.ok(at >= 0, labels.join(" | "));
    assert.equal(labels[at + 1], "$(info) Talpy Chat: this computer's chats for now");
    assert.equal(shown[0][at + 2].label, "In a terminal", "only the line");
    assert.equal(shown[0][at + 1].description, "it can't answer the prompts of a chat on build-server yet");
    await actions.newChat("w");
    const here = shown[1].map((i) => i.label);
    assert.ok(!here.some((l) => l.startsWith("$(info) Talpy Chat")), "offered on this computer");
    assert.equal(here[here.indexOf("In a Talpy Chat tab") + 1], "$(folder) ~/app");
  } finally {
    window.showQuickPick = pick;
  }
});

test("each half says what it does, or why it's greyed out", () => {
  assert.equal(terminalReopenHint(undefined, true), "Reopens the chat in a terminal (claude --resume).");
  assert.match(terminalReopenHint("lab", false), /^Claude Code's claude command isn't installed on lab/);
  assert.match(claudeCodeReopenHint(personal, onWork, [work, personal]), /^Claude Code runs on work · Team, not personal · Pro/);
  assert.match(claudeCodeReopenHint(work, { available: false, profileKey: null }, []), /isn't installed or enabled/);
  assert.match(claudeCodeReopenHint(work, onWork, [work]), /^Opens the chat in a Claude Code panel/);
});

test("a plan's chat reopens in a Claude Code panel only when Claude Code is on the chat's account", async () => {
  // (the plan is shared with work, Claude Code's account; the chat that made it is personal's)
  const stub = vscode as unknown as typeof import("./vscode-stub");
  const getConfiguration = stub.workspace.getConfiguration;
  stub.workspace.getConfiguration = () => ({
    get: <T>(key: string, fallback: T) => (key === "reopenIn" ? "claudeCode" : fallback) as T,
    update: async () => undefined,
  });
  try {
    const work = { id: "w", title: "work", profileKeys: ["work"], sessions: [], vscodeHere: true } as unknown as Group;
    const personal = { id: "p", title: "personal", profileKeys: ["personal"], sessions: [] } as unknown as Group;
    const plan = {
      slug: "s", title: "Plan", path: "/p.md", updatedAt: 0, key: "work/s", profileDir: "work", profile: "work", shared: true,
      chatId: "c1", chatProfileDir: "personal", cwd: "/proj", cwdShort: "~/proj", openCommand: "cd /proj 2>/dev/null; claude --resume c1",
    } as PlanItem;
    const helpers: string[][] = [];
    const runs: string[] = [];
    const dash = { opened() {},
      demo: false,
      state: () => ({ status: { groups: [work, personal], cli: { installed: true } }, hosts: [] }),
      claudeCodeInfo: () => ({ available: true, profileKey: "work" }),
      setActionError: () => undefined,
      isVisible: () => true,
    };
    const actions = new Actions(
      { action: async (_script: string, args: string[]) => (helpers.push(args), { ok: false, message: "Claude Code isn't on personal" }) } as unknown as Backend,
      dash as unknown as Dashboard,
      { run: async (_key: string, _name: string, command: string) => void runs.push(command) } as unknown as Terminals,
      { warn: () => undefined } as unknown as vscode.LogOutputChannel,
      {} as AccountSwitch,
    );
    await actions.continuePlanChat(plan, work);
    assert.deepEqual(helpers, [], "not jump.py --resume --vscode on an account Claude Code isn't on");
    assert.deepEqual(runs, [plan.openCommand], "in a terminal, on personal");
  } finally {
    stub.workspace.getConfiguration = getConfiguration;
  }
});

test("a folder typed for an SSH host: its full path, or one in its home folder", () => {
  assert.equal(typedFolder(" /srv/app ", "/home/me"), "/srv/app");
  assert.equal(typedFolder("~/project", "/home/me"), "/home/me/project", "not the home folder itself");
  assert.equal(typedFolder("~", "/home/me/"), "/home/me");
  assert.equal(typedFolder("project", "/home/me"), null, "it would start in the home folder");
  assert.equal(typedFolder("~other/x", "/home/me"), null);
  assert.equal(typedFolder("~/project", null), null, "the host's home isn't known");
});

test("a recent chat reopens in this window when it has the chat's project open", async () => {
  // (Claude's `cd`s move a chat's folder into subfolders, or out of the
  // folder it started in, which Claude Code files it under)
  const stub = vscode as unknown as typeof import("./vscode-stub");
  const config = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "talpy-den-test-")), ".claude-work");
  fs.mkdirSync(path.join(config, "projects", "-proj"), { recursive: true });
  fs.writeFileSync(path.join(config, "projects", "-proj", "c2.jsonl"), "");
  const saved = { env: process.env.CLAUDE_CONFIG_DIR, openExternal: stub.env.openExternal, folders: stub.workspace.workspaceFolders };
  process.env.CLAUDE_CONFIG_DIR = config; // Claude Code's account here
  const links: string[] = [];
  (stub.env as { openExternal: unknown }).openExternal = async (uri: { path: string }) => (links.push(uri.path), true);
  const setFolders = (...paths: string[]) =>
    void ((stub.workspace as { workspaceFolders: unknown }).workspaceFolders = paths.map((p) => ({ uri: stub.Uri.file(p) })));
  try {
    const helpers: string[][] = [];
    const actions = new Actions(
      { action: async (_script: string, args: string[]) => (helpers.push(args), { ok: true, message: "" }) } as unknown as Backend,
      { demo: false, currentHost: undefined } as unknown as Dashboard,
      {} as Terminals,
      { warn: () => undefined } as unknown as vscode.LogOutputChannel,
      {} as AccountSwitch,
    );
    const reopen = (id: string, cwd: string) => actions.openInClaudeCode({ key: id, sessionId: id, profileDir: ".claude-work", name: id, cwd });
    setFolders("/proj/");
    await reopen("c1", "/proj/source"); // went into a subfolder
    await reopen("c2", "/home/me"); // started in /proj, then went out of it
    await reopen("c3", "/projector"); // another folder, that only starts the same
    setFolders("/proj/source");
    await reopen("c4", "/proj"); // this window has only a part of it
    assert.deepEqual(links, ["vscode://anthropic.claude-code/open?session=c1", "vscode://anthropic.claude-code/open?session=c2"]);
    assert.deepEqual(helpers.map((args) => args[1]), ["c3", "c4"], "VS Code opens the others' folders (jump.py)");
  } finally {
    if (saved.env === undefined) delete process.env.CLAUDE_CONFIG_DIR;
    else process.env.CLAUDE_CONFIG_DIR = saved.env;
    stub.env.openExternal = saved.openExternal;
    (stub.workspace as { workspaceFolders: unknown }).workspaceFolders = saved.folders;
  }
});

test("a chat running in a terminal can move to a Claude Code panel, when Claude Code is on its account", () => {
  assert.equal(canMoveToClaudeCode(chat, true), true);
  assert.equal(canMoveToClaudeCode({ ...chat, state: "working" }, true), true, "it asks to stop it first");
  assert.equal(canMoveToClaudeCode(chat, false), false, "Claude Code isn't on its account");
  assert.equal(canMoveToClaudeCode({ ...chat, entrypoint: "claude-vscode" }, true), false, "it's in one already");
  assert.equal(canMoveToClaudeCode({ ...chat, kind: "bg" }, true), false, "a background session attaches");
  assert.equal(canMoveToClaudeCode({ kind: "chat", pid: null }, true), false, "not running: it reopens");
});

// Actions for this computer's chats on the work account (Claude Code's), with
// what they ran: helpers (jump.py, without the --config-dir of the machine
// the tests run on), terminals, and what failed
// (claudeCode: false, Claude Code isn't here; recent, starred: what the account lists)
function actionsHere(answers: { ok: boolean; message: string; command?: string }[] = [], opts: { claudeCode?: boolean; recent?: unknown[]; starred?: unknown[]; keep?: unknown[] } = {}) {
  const work = { id: "w", title: "work", profileKeys: ["work"], sessions: [], recent: opts.recent ?? [], starred: opts.starred ?? [] } as unknown as Group;
  const helpers: string[][] = [];
  const runs: string[] = [];
  const failures: string[] = [];
  const dash = { opened() {},
    demo: false,
    currentHost: undefined,
    state: () => ({ status: { groups: [work], cli: { installed: true }, keep: opts.keep ?? [] }, hosts: [] }),
    claudeCodeInfo: () => (opts.claudeCode === false ? { available: false, profileKey: null } : { available: true, profileKey: "work" }),
    setActionError: (m: string) => void failures.push(m),
    setActionInfo: () => undefined,
    isVisible: () => true,
    refresh: async () => undefined,
  };
  const actions = new Actions(
    {
      action: async (_script: string, args: string[]) => (
        helpers.push(args.filter((a, i) => a !== "--config-dir" && args[i - 1] !== "--config-dir")), answers.shift() ?? { ok: true, message: "" }
      ),
    } as unknown as Backend,
    dash as unknown as Dashboard,
    { run: async (_key: string, _name: string, command: string) => void runs.push(command), find: async () => undefined } as unknown as Terminals,
    { warn: () => undefined } as unknown as vscode.LogOutputChannel,
    {} as AccountSwitch,
  );
  return { actions, helpers, runs, failures };
}

test("stopping a chat that keeps going asks whether Keep going goes off too", async () => {
  const fix = { key: "k", sessionId: "s1", chatId: "c1", profileDir: "work", name: "Fix", state: "idle", kind: "interactive", entrypoint: "cli", pid: 42 };
  const window = vscode.window as unknown as { showWarningMessage: (...a: unknown[]) => Promise<unknown> };
  const was = window.showWarningMessage;
  const asked: unknown[][] = [];
  try {
    for (const [keep, choice, flags] of [
      [[{ chat: "c1" }], "Stop and turn Keep going off", ["--and-keep-off", "c1"]],
      [[{ chat: "c1" }], "Stop", []],
      [[], "Stop", []],
    ] as [unknown[], string, string[]][]) {
      const { actions, helpers } = actionsHere([], { keep });
      asked.length = 0;
      window.showWarningMessage = async (...a: unknown[]) => (asked.push(a), choice);
      await actions.stop(fix as never);
      const detail = (asked[0][1] as { detail: string }).detail;
      assert.equal(/It keeps going after usage limits\./.test(detail), keep.length > 0);
      assert.equal(asked[0].includes("Stop and turn Keep going off"), keep.length > 0);
      assert.deepEqual(helpers.at(-1), ["--stop", "s1", "--profile", "work", ...flags]);
    }
  } finally {
    window.showWarningMessage = was;
  }
});

test("a chat that isn't running reopens where the switch says, from its tab or its row too", async () => {
  const { overrides } = await import("./vscode-stub");
  const finished = { key: "k", sessionId: "c1", chatId: "c1", profileDir: "work", name: "c1", cwd: "/proj", kind: "chat", pid: null, openCommand: "cd /proj 2>/dev/null; claude --resume c1" };
  try {
    let t = actionsHere();
    await t.actions.open(finished);
    assert.deepEqual(t.runs, [finished.openCommand], "in a terminal by default");
    assert.deepEqual(t.helpers, []);

    overrides.set("reopenIn", "claudeCode");
    t = actionsHere();
    await t.actions.open(finished);
    assert.deepEqual(t.runs, [], "not in a terminal");
    assert.deepEqual(t.helpers, [["--resume", "c1", "--profile", "work", "--vscode"]], "in a Claude Code panel");

    t = actionsHere();
    await t.actions.open({ ...finished, profileDir: "personal" });
    assert.deepEqual(t.runs, [finished.openCommand], "Claude Code isn't on that account: a terminal");

    t = actionsHere();
    await t.actions.open({ ...finished, kind: "interactive", pid: 42, openCommand: null, state: "idle" });
    assert.deepEqual(t.helpers.filter((a) => a.includes("--vscode")), [], "a running chat opens where it runs");
  } finally {
    overrides.clear();
  }
});

test("moving a chat to a Claude Code panel stops it first, a working one only once you say so", async () => {
  const stub = vscode as unknown as typeof import("./vscode-stub");
  const ask = stub.window.showWarningMessage;
  const asked: { title: string; buttons: string[] }[] = [];
  let pick: (buttons: string[]) => string | undefined = (buttons) => buttons[0];
  (stub.window as { showWarningMessage: unknown }).showWarningMessage = async (title: string, _opts: unknown, ...buttons: string[]) =>
    (asked.push({ title, buttons }), pick(buttons));
  const running = { key: "k", sessionId: "s1", chatId: "c1", profileDir: "work", name: "Fix it", cwd: "/proj", kind: "interactive", entrypoint: "cli", pid: 42, state: "idle" as const };
  try {
    let t = actionsHere();
    await t.actions.moveToClaudeCode(running);
    assert.deepEqual(asked.pop()?.buttons, ["Move"]);
    assert.deepEqual(t.helpers, [["--stop", "s1", "--profile", "work"], ["--resume", "c1", "--profile", "work", "--vscode"]], "an idle one: only while it's idle");

    t = actionsHere();
    await t.actions.moveToClaudeCode({ ...running, state: "working" });
    assert.deepEqual(asked.pop()?.buttons, ["Stop and Move"]);
    assert.deepEqual(t.helpers[0], ["--stop", "s1", "--profile", "work", "--busy"]);
    assert.equal(t.helpers.length, 2);

    pick = () => undefined; // Cancel
    t = actionsHere();
    await t.actions.moveToClaudeCode({ ...running, state: "waiting" });
    assert.deepEqual(t.helpers, [], "nothing stopped");

    pick = (buttons) => buttons[0];
    t = actionsHere([{ ok: false, message: "It's working again, so it wasn't stopped" }]);
    await t.actions.moveToClaudeCode(running);
    assert.equal(t.helpers.length, 1, "not reopened while it still runs");
    assert.match(t.failures[0], /working again/);

    asked.length = 0;
    t = actionsHere();
    await t.actions.moveToClaudeCode({ ...running, entrypoint: "claude-vscode" });
    await t.actions.moveToClaudeCode({ ...running, profileDir: "personal" });
    assert.deepEqual(asked, [], "in a Claude Code panel already, or Claude Code isn't on its account: not asked");
    assert.deepEqual(t.helpers, []);
  } finally {
    (stub.window as { showWarningMessage: unknown }).showWarningMessage = ask;
  }
});

test("a chat the Recap names that isn't running reopens: with the command its account lists, else the one jump.py has for it", async () => {
  const { overrides } = await import("./vscode-stub");
  const desktop = process.env.XDG_CURRENT_DESKTOP;
  process.env.XDG_CURRENT_DESKTOP = "XFCE"; // (nothing here brings other windows up)
  const id = "c76cd817-da30";
  const listed = { key: `work/${id}/recent`, sessionId: id, name: "Ports", cwd: "/w/app", profileDir: "work", lastActive: 0,
                   openCommand: `cd /w/app 2>/dev/null; claude --resume ${id}` };
  try {
    // not listed anywhere (older than the recent chats): the command jump.py has for it, in VS Code's
    // terminal too; it isn't "in a terminal outside this window"
    const resumed = `cd /w/app 2>/dev/null; claude --resume ${id}`;
    let t = actionsHere([{ ok: true, message: "", command: resumed }], { claudeCode: false });
    await t.actions.openWeekChat(id, "work", "Ports", "/w/app");
    assert.deepEqual(t.helpers, [["--resume", id, "--profile", "work", "--print-command"]]);
    assert.deepEqual(t.runs, [resumed]);
    assert.deepEqual(t.failures, []);
    // one jump.py can't reopen (gone from that account): said
    t = actionsHere([{ ok: false, message: "That chat isn't on this account" }], { claudeCode: false });
    await t.actions.openWeekChat(id, "work", "Ports", "/w/app");
    assert.deepEqual(t.runs, []);
    assert.deepEqual(t.failures, ["Couldn't reopen Ports: That chat isn't on this account"]);
    // one of its account's recent or starred chats: their command, in VS Code's terminal
    for (const where of [{ recent: [listed] }, { starred: [listed] }]) {
      t = actionsHere([], { claudeCode: false, ...where });
      await t.actions.openWeekChat(id, "work", "Ports", "/w/app");
      assert.deepEqual(t.runs, [listed.openCommand]);
      assert.deepEqual(t.helpers, []);
    }
    // where the switch says: a Claude Code panel
    overrides.set("reopenIn", "claudeCode");
    t = actionsHere();
    await t.actions.openWeekChat(id, "work", "Ports", "/w/app");
    assert.deepEqual(t.helpers, [["--resume", id, "--profile", "work", "--vscode"]]);
    assert.deepEqual(t.runs, []);
    overrides.delete("reopenIn");
    // talpyDen.openIn "system": the widget's way, also for one that's listed
    overrides.set("openIn", "system");
    t = actionsHere([], { claudeCode: false, recent: [listed] });
    await t.actions.openWeekChat(id, "work", "Ports", "/w/app");
    assert.deepEqual(t.helpers, [[id, "--profile", "work"]]);
    assert.deepEqual(t.runs, []);
    overrides.delete("openIn");
    // an SSH host's chat with no command to reopen it: said as it is
    t = actionsHere([], { claudeCode: false });
    await t.actions.open({ host: "lab", key: "k", sessionId: "c1", chatId: "c1", profileDir: ".claude", name: "Ports", cwd: "", kind: "chat", pid: null, openCommand: null });
    assert.deepEqual(t.helpers, []);
    assert.match(t.failures[0], /^Ports isn't running on lab, and there's no command here to reopen it/);
  } finally {
    overrides.clear();
    if (desktop === undefined) delete process.env.XDG_CURRENT_DESKTOP;
    else process.env.XDG_CURRENT_DESKTOP = desktop;
  }
});

// talpyDen.openIn = system: a new chat on an SSH host opens in your
// desktop's terminal (remote.py), as its other chats do
test("with openIn system, a new chat on an SSH host opens in the desktop's terminal", async () => {
  const stub = vscode as unknown as typeof import("./vscode-stub");
  const window = stub.window as unknown as Record<string, unknown>;
  stub.overrides.set("openIn", "system");
  const pickFolder = window.showQuickPick;
  window.showQuickPick = async (items: { folder?: { path: string } }[]) => items.find((i) => i.folder?.path === "/srv/app");
  try {
    const lab = {
      id: "l", title: "work", chatProfile: ".claude", profileKeys: [".claude"], sessions: [], homeChatCommand: "cd /home/me 2>/dev/null; claude",
      projects: [{ path: "/srv/app", short: "~/app", newChatCommand: "cd /srv/app 2>/dev/null; claude", trusted: true }],
    } as unknown as Group;
    const helpers: [string, string[]][] = [];
    const runs: string[] = [];
    const dash = { opened() {},
      demo: false,
      state: () => ({ status: { groups: [], cli: { installed: true } }, hosts: [{ name: "lab", result: { groups: [lab], cli: { installed: true } } }] }),
      setActionError: () => undefined,
      isVisible: () => true,
    };
    const actions = new Actions(
      { action: async (script: string, args: string[]) => (helpers.push([script, args]), { ok: true, message: "" }) } as unknown as Backend,
      dash as unknown as Dashboard,
      { run: async (_key: string, _name: string, command: string) => void runs.push(command) } as unknown as Terminals,
      { warn: () => undefined } as unknown as vscode.LogOutputChannel,
      {} as AccountSwitch,
    );
    await actions.newChat("l", "lab");
    assert.deepEqual(runs, [], "not in a VS Code terminal");
    assert.equal(helpers.length, 1);
    const [script, args] = helpers[0];
    assert.deepEqual([script, args.slice(0, 2)], ["remote.py", ["--open", "lab"]]);
    assert.match(args[2], /^cd \/srv\/app 2>\/dev\/null; claude/);
  } finally {
    window.showQuickPick = pickFolder;
    stub.overrides.delete("openIn");
  }
});
