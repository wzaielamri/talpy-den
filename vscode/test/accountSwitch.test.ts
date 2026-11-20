// In a Remote-SSH window, the account switch shows and switches the host's
// Claude Code: VS Code keeps claudeCode.environmentVariables (a machine
// setting) per host, so the user setting written there is the host's. Its
// Add Account… and Claude Accounts… are the extension's own accounts'.

import assert from "node:assert/strict";
import * as fs from "node:fs";
import { test } from "node:test";
import * as vscode from "vscode";
import { host } from "./useHost";
import { AccountSwitch, type AccountsOpener } from "../../core/src/accountSwitch";
import type { Backend } from "../../core/src/agents/claudeCode/backend";
import type { Dashboard } from "../../core/src/dashboard";
import type { Group, ViewState } from "../../core/src/shared/types";
import { VsCodeEditor } from "../src/vscodeEditor";

const stub = vscode as unknown as typeof import("./vscode-stub");
const noAccounts: AccountsOpener = { add: async () => undefined, manage: async () => undefined };

function hostGroup(name: string, title: string, vscodeHere: boolean, configDir: string | null | undefined): Group {
  return { name, title, vscodeHere, configDir, host: "lab", id: name, plan: null, profiles: [], profileKeys: [], sessions: [],
           limits: null, tokens: null, chatProfile: `.claude-${name}`, shareProfile: null, projects: [], sharedHere: [], recent: [] };
}

test("a Remote-SSH window shows the host's account and switches it in the host's settings", async () => {
  const groups = [hostGroup("work", "work · Team", true, "/home/me/.claude"), hostGroup("personal", "personal · Pro", false, "/home/me/.claude-personal")];
  const state = { status: null, hosts: [{ name: "lab", result: { groups } }], demo: false } as unknown as ViewState;
  let refreshed = 0;
  const dash = { currentHost: "lab", state: () => state, refreshAll: () => void refreshed++ } as unknown as Dashboard;
  const updates: unknown[][] = [];
  const realConfig = stub.workspace.getConfiguration;
  stub.env.remoteName = "ssh-remote";
  stub.workspace.getConfiguration = (() => ({
    // what this window reads: the host's value (a machine setting), with a variable of its own
    get: () => [{ name: "FOO", value: "1" }, { name: "CLAUDE_CONFIG_DIR", value: "/home/me/.claude" }],
    update: async (...args: unknown[]) => void updates.push(args),
  })) as unknown as typeof stub.workspace.getConfiguration;
  try {
    const account = new AccountSwitch(host, new VsCodeEditor(), dash, noAccounts);
    // (named in Talpy Den's status bar item, its hover linking to the switch)
    const shown = account.update(state);
    assert.equal(shown?.name, "work");
    assert.equal(shown?.group, groups[0]);
    assert.equal(shown?.tip, "Claude Code on lab runs on work · Team.");
    assert.equal(await account.switchHost(groups[1]), true);
    assert.deepEqual(updates, [["environmentVariables",
      [{ name: "FOO", value: "1" }, { name: "CLAUDE_CONFIG_DIR", value: "/home/me/.claude-personal" }], stub.ConfigurationTarget.Global]]);
    assert.equal(refreshed, 1);
    // a plain ~/.claude runs without the variable; a host answer from an older backend can't be switched
    await account.switchHost(hostGroup("default", "default", false, null));
    assert.deepEqual(updates[1], ["environmentVariables", [{ name: "FOO", value: "1" }], stub.ConfigurationTarget.Global]);
    assert.equal(await account.switchHost(hostGroup("old", "old", false, undefined)), false);
    assert.equal(updates.length, 2);
  } finally {
    stub.env.remoteName = undefined;
    stub.workspace.getConfiguration = realConfig;
  }
});

test("making a host's account the default also points the host's ~/.claude there, then Claude Code there", async () => {
  const groups = [hostGroup("work", "work · Team", true, "/home/me/.claude"), hostGroup("personal", "personal · Pro", false, "/home/me/.claude-personal")];
  const state = { status: null, hosts: [{ name: "lab", result: { groups } }], demo: false } as unknown as ViewState;
  const dash = { currentHost: "lab", state: () => state, refreshAll: () => undefined } as unknown as Dashboard;
  const calls: unknown[][] = [];
  let answer: Record<string, unknown> = { ok: true, message: "", configDir: "/home/me/.claude" };
  const backend = { accounts: async (...args: unknown[]) => (calls.push(args), answer) } as unknown as Backend;
  const updates: unknown[][] = [];
  const realConfig = stub.workspace.getConfiguration;
  stub.env.remoteName = "ssh-remote";
  stub.workspace.getConfiguration = (() => ({
    get: () => [{ name: "CLAUDE_CONFIG_DIR", value: "/home/me/.claude" }],
    update: async (...args: unknown[]) => void updates.push(args),
  })) as unknown as typeof stub.workspace.getConfiguration;
  try {
    const account = new AccountSwitch(host, new VsCodeEditor(), dash, noAccounts, backend);
    assert.equal(await account.switchHost(groups[1], true), true);
    assert.deepEqual(calls, [[["--default", ".claude-personal", "--no-vscode"], "lab"]]);
    // what the host said Claude Code needs now: ~/.claude, which leads to personal
    assert.deepEqual(updates[0], ["environmentVariables", [{ name: "CLAUDE_CONFIG_DIR", value: "/home/me/.claude" }], stub.ConfigurationTarget.Global]);
    // refused there (a chat runs through ~/.claude): nothing changes here either
    answer = { ok: false, message: "personal isn't the default yet: a Claude process runs through ~/.claude" };
    assert.equal(await account.switchHost(groups[1], true), false);
    assert.equal(updates.length, 1);
    assert.match(stub.recorded.messages.at(-1)!, /runs through ~\/\.claude/);
    // a new chat's switch (not as the default) leaves the host's ~/.claude alone
    assert.equal(await account.switchHost(groups[1]), true);
    assert.equal(calls.length, 2);
  } finally {
    stub.env.remoteName = undefined;
    stub.workspace.getConfiguration = realConfig;
  }
});

// The switch's Add Account… and Claude Accounts… (one account, or the others hidden) are the extension's own
// accounts' (talpyDen.addAccount's and talpyDen.accounts'), the same window's host and editor as the rest
test("the switch opens the extension's accounts: Add Account… adds one, Claude Accounts… lists them", () => {
  const activate = fs.readFileSync("src/extension.ts", "utf8");
  assert.match(activate, /new AccountSwitch\(host, editor, dash, \{ add: \(\) => accounts\.add\(\), manage: \(\) => accounts\.manage\(\) \}, backend\)/);
  assert.match(activate, /const accounts = new Accounts\(host, backend, dash, terminals, account\);/);
  assert.match(activate, /registerCommand\("talpyDen\.accounts", \(\) => accounts\.manage\(\)\)/);
  assert.match(activate, /registerCommand\("talpyDen\.addAccount", \(\) => accounts\.add\(\)\)/);
});
