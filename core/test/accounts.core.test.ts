// Accounts and the account switch on their host alone (no vscode): what adding an account asks and where the
// wait for the accounts' list shows; the switch's ways to Claude Accounts, its reload offer and Make Default's
// setting. Account folders are a temporary home's, never yours. (Dictation's: dictation.core.test.ts.)

import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { test } from "node:test";
import { Accounts, type AccountInfo } from "../src/accounts";
import { AccountSwitch, type AccountsOpener } from "../src/accountSwitch";
import type { Backend } from "../src/agents/claudeCode/backend";
import type { Dashboard } from "../src/dashboard";
import type { EditorPort, Place, TerminalHandle, TerminalPort } from "../src/ports";
import { useSettingsHost } from "../src/settings";
import type { Group, ViewState } from "../src/shared/types";
import { FakeHost } from "./fakeHost";

// The terminals started, in order
class FakeTerminals implements TerminalPort {
  runs: { key: string; name: string; command: string; place: Place; opts?: { private?: boolean; chatOn?: string } }[] = [];
  async find(): Promise<TerminalHandle | undefined> {
    return undefined;
  }
  async run(key: string, name: string, command: string, place: Place, opts?: { private?: boolean; chatOn?: string }): Promise<TerminalHandle> {
    this.runs.push({ key, name, command, place, opts });
    return { show() {}, sendText() {} };
  }
}

// This computer's one account, as accounts.py --list says it
const main: AccountInfo = {
  key: ".claude", label: "main", folder: "~/.claude", main: true, account: "Me", plan: "Pro", loggedIn: true, checked: true,
  method: "claude.ai", email: null, chats: 0, vscode: true, default: true, commandName: null, command: false, notRemovable: "",
};

// Add Account… on this computer: the list (accounts.py --list --check) while the window's status bar says so,
// the name asked, the settings and command picked, then the login in a terminal of its own
test("adding an account asks for its name and shows progress in the window", async () => {
  const fake = new FakeHost();
  useSettingsHost(fake);
  const calls: string[][] = [];
  const backend = {
    accounts: async (args: string[]) => {
      calls.push(args.filter((a, i) => a !== "--config-dir" && args[i - 1] !== "--config-dir"));
      return args[0] === "--list" ? { ok: true, accounts: [main], linked: true }
        : { ok: true, message: "Added work.", key: ".claude-work", command: "claude-work-login" };
    },
  } as unknown as Backend;
  let refreshed = 0;
  const dash = { currentHost: undefined, refreshAll: () => void refreshed++, state: () => ({ hosts: [] }) } as unknown as Dashboard;
  const terminals = new FakeTerminals();
  fake.answer.input = () => " work ";
  fake.answer.pick = (items) => items.find((i) => i.label === "Claude's defaults, nothing shared" || i.label === "Add a claude-work command");
  await new Accounts(fake, backend, dash, terminals, {} as AccountSwitch).add();

  assert.deepEqual(fake.recorded.progress, [{ where: "window", title: "Claude accounts…" }]);
  assert.equal(fake.recorded.inputs.length, 1);
  const name = fake.recorded.inputs[0];
  assert.equal(name.title, "Add a Claude Account (1/3)");
  assert.equal(name.prompt, "Its name. The account's folder is ~/.claude-NAME.");
  assert.equal(name.validateInput?.("work"), null);
  assert.match(String(name.validateInput?.("main")), /is taken/);
  assert.deepEqual(fake.recorded.picks.map((p) => p.options?.title), ["Add a Claude Account (2/3): settings", "Add a Claude Account (3/3)"]);
  assert.deepEqual(calls, [["--list", "--check"], ["--add", "work", "--command", "--print-command"]]);
  assert.equal(refreshed, 1);
  assert.deepEqual(terminals.runs, [{ key: "login||.claude-work", name: "log in to work", command: "claude-work-login", place: { kind: "local" }, opts: { private: true } }]);
  assert.deepEqual(fake.recorded.messages.map((m) => [m.level, m.text]), [
    ["info", "Added work."],
    ["info", "Log in to work in the terminal: sign in in your browser with the other account. Afterwards, Claude Accounts → work → Make Default makes it the account VS Code's Claude and plain claude run on."],
  ]);
});

// This computer's accounts as the status says them: a group per account, its folder's name its profile key
const account = (name: string, more: Partial<Group> = {}) =>
  ({ id: name, name, title: name, chatProfile: `.claude-${name}`, profileKeys: [`.claude-${name}`], sessions: [], ...more }) as unknown as Group;

// A temporary home with these account folders (settings.json: a profile), and no CLAUDE_CONFIG_DIR, until the
// test ends
function tempHome(t: { after(fn: () => void): void }, names: string[]): string {
  const home = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "talpy-den-switch-")));
  for (const n of names) {
    fs.mkdirSync(path.join(home, n));
    fs.writeFileSync(path.join(home, n, "settings.json"), "{}");
  }
  const saved = { HOME: process.env.HOME, CLAUDE_CONFIG_DIR: process.env.CLAUDE_CONFIG_DIR };
  process.env.HOME = home;
  delete process.env.CLAUDE_CONFIG_DIR;
  t.after(() => {
    for (const [k, v] of Object.entries(saved)) if (v === undefined) delete process.env[k]; else process.env[k] = v;
    fs.rmSync(home, { recursive: true, force: true });
  });
  return home;
}

// claudeCode.environmentVariables with the panel on dir, and a variable of the user's own
const panelOn = (dir: string) => [{ name: "FOO", value: "1" }, { name: "CLAUDE_CONFIG_DIR", value: dir }];

// Add Account… and Claude Accounts… in the switch open the accounts' own dialogs (extension.ts hands them in)
test("the account switch's Add Account… and Claude Accounts… open the accounts", async (t) => {
  const home = tempHome(t, [".claude-work"]);
  const fake = new FakeHost();
  useSettingsHost(fake);
  fake.others.set("claudeCode.environmentVariables", panelOn(path.join(home, ".claude-work")));
  const opened: string[] = [];
  const opener: AccountsOpener = { add: async () => void opened.push("add"), manage: async () => void opened.push("manage") };
  let groups = [account("work")];
  let hiddenGroups: Group[] = [];
  const dash = { state: () => ({ status: { groups, hiddenGroups } }) } as unknown as Dashboard;
  let installed = true;
  const editor = { claudeCodeInstalled: () => installed, localPanelProfileKey: () => ".claude-work" } as unknown as EditorPort;
  fake.answer.message = (_text, actions) => actions[0];
  const sw = new AccountSwitch(fake, editor, dash, opener);

  await sw.switch(); // one account: Add Account…
  hiddenGroups = [account("personal")];
  await sw.switch(); // the other one hidden: Claude Accounts…
  assert.deepEqual(fake.recorded.messages.map((m) => [m.level, m.actions]), [["info", ["Add Account…"]], ["info", ["Claude Accounts…"]]]);
  groups = [account("work"), account("personal")];
  hiddenGroups = [];
  const addRow = "$(person-add) Add Account…";
  fake.answer.pick = (items) => items.find((i) => i.label === addRow);
  await sw.switch(); // the list's last row
  assert.deepEqual(fake.recorded.picks[0].items.map((i) => [i.label, !!i.separator]),
    [["work", false], ["personal", false], ["", true], [addRow, false]]);
  assert.deepEqual(opened, ["add", "manage", "add"]);

  installed = false;
  await sw.switch();
  assert.equal(fake.recorded.messages.at(-1)?.text, "The Claude Code extension isn't installed, so there's no VS Code Claude to switch.");
  assert.equal(opened.length, 3);
});

// Another window (or a hand edit) moved the panel to another account: this window's panel runs on the old one
// until it reloads, so Reload Window is offered, once
test("a panel switched to another account elsewhere offers to reload the window", async (t) => {
  const home = tempHome(t, [".claude-work", ".claude-personal"]);
  const fake = new FakeHost();
  useSettingsHost(fake);
  fake.others.set("claudeCode.environmentVariables", panelOn(path.join(home, ".claude-work")));
  let key = ".claude-work";
  const editor = { localPanelProfileKey: () => key } as unknown as EditorPort;
  const state = { demo: false, status: { groups: [account("work"), account("personal")] }, hosts: [] } as unknown as ViewState;
  const sw = new AccountSwitch(fake, editor, {} as Dashboard, {} as AccountsOpener);
  assert.equal(sw.update(state)?.name, "work");
  assert.equal(fake.recorded.messages.length, 0);

  fake.setOther("claudeCode.environmentVariables", panelOn(path.join(home, ".claude-personal")));
  key = ".claude-personal";
  fake.answer.message = () => "Reload Window";
  assert.equal(sw.update(state)?.name, "personal");
  await new Promise((r) => setImmediate(r));
  assert.deepEqual(fake.recorded.messages.map((m) => [m.level, m.text, m.actions]),
    [["info", "VS Code's Claude runs on personal now. Reload this window so its Claude Code panel does too.", ["Reload Window"]]]);
  assert.equal(fake.recorded.reloads, 1);
  sw.update(state);
  assert.equal(fake.recorded.messages.length, 1, "offered once");
});

// Make Default on this computer: Claude Code's setting written globally (VS Code's user settings) with the
// account's folder, its other variables kept; 300 ms later the window reloads, its panel on that account
test("making another account the default writes Claude Code's setting globally and reloads the window", async (t) => {
  const home = tempHome(t, [".claude-work", ".claude-personal"]);
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const fake = new FakeHost();
  useSettingsHost(fake);
  fake.others.set("claudeCode.environmentVariables", panelOn(path.join(home, ".claude-work")));
  const editor = { localPanelProfileKey: () => ".claude-work" } as unknown as EditorPort;
  const groups = [account("work"), account("personal")];
  const dash = { state: () => ({ status: { groups } }), refreshAll() {} } as unknown as Dashboard;
  fake.answer.message = (_text, actions) => (actions.includes("Make Default") ? "Make Default" : undefined);
  const sw = new AccountSwitch(fake, editor, dash, {} as AccountsOpener);
  await sw.switchTo(groups[1]);

  const asked = fake.recorded.messages[0];
  assert.deepEqual([asked.level, asked.text, asked.options?.modal, asked.actions], ["warning", "Make personal the default account?", true, ["Make Default"]]);
  assert.match(asked.options?.detail ?? "", /this window reloads/);
  assert.deepEqual(fake.recorded.updates, [{ section: "claudeCode", key: "environmentVariables", value: panelOn(path.join(home, ".claude-personal")), scope: "global" }]);
  // (its own switch: no Reload Window offered as well)
  sw.update({ demo: false, status: { groups }, hosts: [] } as unknown as ViewState);
  assert.equal(fake.recorded.messages.length, 1);
  assert.equal(fake.recorded.reloads, 0);
  t.mock.timers.tick(300);
  assert.equal(fake.recorded.reloads, 1);
});
