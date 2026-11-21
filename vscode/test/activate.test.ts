// The whole extension, activated outside VS Code against a made-up home: every command and the view get
// registered, the first poll reaches the status bar, and what the commands are wired to is the extension's
// own (the accounts behind the account switch, the plan review behind Send Feedback). (No ./useHost here, on
// purpose: activate itself must set the settings host.)

import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { after, test, type TestContext } from "node:test";
import * as vscode from "vscode";
import { activate } from "../src/extension";

const stub = vscode as unknown as typeof import("./vscode-stub");
const linuxOnly = { skip: process.platform !== "linux" && "needs /proc" };

// Whether a helper the extension started still runs (a child of this process): a check that began before the
// extension was disposed still writes to the cache, and its answer is still handled here once it's done
function helperRunning(): boolean {
  if (!fs.existsSync("/proc")) return false;
  return fs.readdirSync("/proc").some((pid) => {
    try {
      const stat = fs.readFileSync(`/proc/${pid}/stat`, "utf8");
      const [state, ppid] = stat.slice(stat.lastIndexOf(")") + 2).split(" ");
      return Number(ppid) === process.pid && state !== "Z";
    } catch {
      return false; // (not a process, or gone meanwhile)
    }
  });
}

// A made-up home with these Claude config folders, HOME and the cache in it; each is removed once the file's
// tests are done and the extension has finished what it still did there
const homes: string[] = [];
after(async () => {
  for (let i = 0; i < 100 && helperRunning(); i++) await new Promise((r) => setTimeout(r, 100));
  await new Promise((r) => setTimeout(r, 200)); // (its answer handled)
  for (const home of homes.splice(0)) fs.rmSync(home, { recursive: true, force: true });
});
function madeUpHome(accounts: string[] = [".claude"]): string {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "talpy-den-test-"));
  homes.push(home);
  process.env.HOME = home;
  process.env.XDG_CACHE_HOME = path.join(home, ".cache");
  delete process.env.CLAUDE_CONFIG_DIR;
  for (const account of accounts) {
    fs.mkdirSync(path.join(home, account, "sessions"), { recursive: true });
    fs.mkdirSync(path.join(home, account, "projects"), { recursive: true });
  }
  return home;
}

// The extension activated as VS Code does it, its subscriptions disposed when the test ends (globalState says
// the old settings were carried over already: that step has its own tests)
function activated(t: TestContext): void {
  const manifest = JSON.parse(fs.readFileSync("package.json", "utf8"));
  const subscriptions: { dispose(): void }[] = [];
  const globalState = { get: () => true, update: async () => {} };
  activate({
    subscriptions, extensionPath: path.resolve("."), extensionUri: vscode.Uri.file(path.resolve(".")), globalState, extension: { packageJSON: manifest },
  } as unknown as vscode.ExtensionContext);
  t.after(() => {
    for (const s of subscriptions) s.dispose();
  });
}

// This computer's one account, as accounts.py --list says it
const MAIN = { key: ".claude", label: "main", folder: "~/.claude", main: true, account: "Me", plan: "Pro", loggedIn: true, checked: true,
               method: "claude.ai", email: null, chats: 0, vscode: true, default: true, commandName: null, command: false, notRemovable: "" };

// The python3 the extension's helpers run with (talpyDen.pythonPath, until the test ends): accounts.py answers
// with MAIN, talpy_den.py --fetch-usage fetches nothing, and jump.py --plan-feedback says it sent the feedback,
// writing what it was given to asked (each argument ended by a NUL); everything else is python3's own
function helpersIn(home: string, t: TestContext): { asked: string } {
  const asked = path.join(home, "asked");
  const python = path.join(home, "python3");
  const script = [
    "#!/bin/sh",
    'case "$2" in',
    `  */accounts.py) echo '${JSON.stringify({ ok: true, accounts: [MAIN], linked: true })}'; exit ;;`,
    `  */talpy_den.py) [ "$3" = --fetch-usage ] && { echo '{"ok": true, "started": []}'; exit; } ;;`,
    `  */jump.py) [ "$3" = --plan-feedback ] && { printf '%s\\0' "$@" > '${asked}'; echo '{"ok": true, "message": "Sent your feedback"}'; exit; } ;;`,
    "esac",
    'exec python3 "$@"',
  ];
  fs.writeFileSync(python, script.join("\n") + "\n", { mode: 0o755 });
  stub.overrides.set("pythonPath", python);
  t.after(() => stub.overrides.delete("pythonPath"));
  return { asked };
}

test("activates, registers everything, and shows the first poll", linuxOnly, async () => {
  const home = madeUpHome();
  const child = spawn("sleep", ["60"], { env: { PATH: process.env.PATH, HOME: home }, stdio: "ignore" });
  try {
    const cfg = path.join(home, ".claude");
    fs.mkdirSync(path.join(cfg, "sessions"), { recursive: true });
    fs.mkdirSync(path.join(cfg, "projects"), { recursive: true });
    fs.writeFileSync(
      path.join(cfg, "sessions", `${child.pid}.json`),
      JSON.stringify({ pid: child.pid, kind: "interactive", sessionId: "33333333-3333-4333-8333-333333333333", cwd: home, status: "waiting", waitingFor: "permission prompt", name: "Deploy", startedAt: Date.now() }),
    );
    const manifest = JSON.parse(fs.readFileSync("package.json", "utf8"));
    const subscriptions: { dispose(): void }[] = [];
    const contexts: [string, unknown][] = [];
    const commands = stub.commands as unknown as Record<string, unknown>;
    const execute = commands.executeCommand;
    commands.executeCommand = async (id: string, key: string, value: unknown) => void (id === "setContext" && contexts.push([key, value]));
    // (globalState says the old settings were carried over already: that step has its own tests)
    const globalState = { get: () => true, update: async () => {} };
    activate({
      subscriptions, extensionPath: path.resolve("."), extensionUri: vscode.Uri.file(path.resolve(".")), globalState, extension: { packageJSON: manifest },
    } as unknown as vscode.ExtensionContext);

    for (const c of manifest.contributes.commands) assert.ok(stub.recorded.commands.has(c.command), `command ${c.command} registered`);
    assert.ok(stub.recorded.viewProviders.has("talpyDen.view"));
    // Send Feedback's button on plans of the extra config folders too
    assert.deepEqual(contexts.filter(([k]) => k === "talpyDen.planFolders").at(-1), ["talpyDen.planFolders", []]);
    stub.overrides.set("extraConfigDirs", ["/data/claude-alt"]);
    stub.changeSettings("talpyDen.extraConfigDirs");
    stub.overrides.delete("extraConfigDirs");
    assert.deepEqual(contexts.filter(([k]) => k === "talpyDen.planFolders").at(-1), ["talpyDen.planFolders", ["/data/claude-alt/plans"]]);
    commands.executeCommand = execute;

    const item = stub.recorded.statusBarItems[0];
    for (let i = 0; i < 100 && !item.text.includes("talpy-den-waiting"); i++) await new Promise((r) => setTimeout(r, 100));
    assert.equal(item.text, "$(talpy-den-waiting) 1", "the waiting chat shows in the status bar");
    assert.deepEqual(item.backgroundColor, new stub.ThemeColor("statusBarItem.warningBackground"));
    for (const s of subscriptions) s.dispose();
  } finally {
    child.kill();
  }
});

// Claude Accounts as the extension wires them: Add Account… (talpyDen.addAccount; the switch's button with one
// account, its list's last row with more) asks for the new account's name, and Claude Accounts…
// (talpyDen.accounts; the switch's button when the other accounts are hidden) lists the accounts
test("Add Account… and Claude Accounts…, from their commands and from the account switch, open the extension's accounts", linuxOnly, async (t) => {
  const home = madeUpHome([".claude", ".claude-work"]);
  const hidden = path.join(home, ".cache", "talpy-den", "hidden.json");
  fs.mkdirSync(path.dirname(hidden), { recursive: true });
  fs.writeFileSync(hidden, JSON.stringify({ accounts: { ".claude-work": 1 } })); // (work hidden, as Claude Accounts → Hide does)
  helpersIn(home, t);
  stub.installedExtensions.add("anthropic.claude-code"); // (the switch is VS Code's Claude's)
  t.after(() => {
    stub.installedExtensions.clear();
    stub.answers.clear();
  });
  activated(t);
  const run = (command: string) => stub.recorded.commands.get(command)!() as Promise<void>;
  // the titles of the input boxes and pick lists shown since from
  const opened = (from: number) => stub.calls.slice(from).filter((c) => c.method === "showInputBox" || c.method === "showQuickPick")
    .map((c) => (c.args.at(-1) as { title?: string }).title);
  // what the switch offers, nothing picked: its message's buttons, or its pick list's title
  const offered = async (): Promise<unknown[]> => {
    const from = stub.calls.length;
    await run("talpyDen.switchAccount");
    const shown = stub.calls.slice(from).find((c) => c.method === "showInformationMessage" || c.method === "showQuickPick");
    return !shown ? [] : shown.method === "showQuickPick" ? [(shown.args[1] as { title: string }).title] : shown.args.slice(2);
  };
  // (until a check has brought the accounts in; again: what makes one)
  const until = async (wanted: string, again = () => {}) => {
    for (let i = 0; i < 100; i++) {
      if ((await offered()).includes(wanted)) return;
      again();
      await new Promise((r) => setTimeout(r, 100));
    }
    assert.fail(`the switch never offered ${wanted}`);
  };

  let from = stub.calls.length;
  await run("talpyDen.addAccount");
  await run("talpyDen.accounts");
  assert.deepEqual(opened(from), ["Add a Claude Account (1/3)", "Claude Accounts"]);

  // work is hidden: the switch's Claude Accounts… lists the accounts
  await until("Claude Accounts…");
  stub.answers.set("showInformationMessage", (_text: string, _o: unknown, ...buttons: string[]) => buttons.find((b) => b === "Claude Accounts…"));
  from = stub.calls.length;
  await run("talpyDen.switchAccount");
  assert.deepEqual(opened(from), ["Claude Accounts"]);
  stub.answers.delete("showInformationMessage");

  // work shown again: the switch lists both, and its last row adds an account
  fs.writeFileSync(hidden, JSON.stringify({ accounts: {} }));
  await until("Default Claude account", () => void run("talpyDen.refresh"));
  stub.answers.set("showQuickPick", (items: { label: string }[]) => items.find((i) => i.label === "$(person-add) Add Account…"));
  from = stub.calls.length;
  await run("talpyDen.switchAccount");
  assert.deepEqual(opened(from), ["Default Claude account", "Add a Claude Account (1/3)"]);
});

// Send Feedback as the extension wires it: a comment added on a plan's line (talpyDen.planComment.add, the plan
// review's) goes with the feedback the actions send (jump.py --plan-feedback --comments), and once it's sent the
// comment is gone
test("a comment added on a plan's line goes with Send Feedback, and is gone once it's sent", linuxOnly, async (t) => {
  const home = madeUpHome();
  const { asked } = helpersIn(home, t);
  const plan = path.join(home, ".claude", "plans", "calm-red-owl.md");
  fs.mkdirSync(path.dirname(plan), { recursive: true });
  fs.writeFileSync(plan, "# Plan\n\n1. Parse the file\n2. Ship it\n");
  stub.stubFiles.set(plan, fs.readFileSync(plan, "utf8")); // (the document VS Code would open)
  t.after(() => stub.stubFiles.delete(plan));
  activated(t);
  let disposed = 0;
  const thread = { uri: vscode.Uri.file(plan), range: new vscode.Range(2, 0, 3, 0), comments: [] as vscode.Comment[], dispose: () => void disposed++ };
  stub.recorded.commands.get("talpyDen.planComment.add")!({ thread, text: "Run the tests before shipping" });
  stub.recorded.commands.get("talpyDen.sendPlanFeedback")!(vscode.Uri.file(plan));
  for (let i = 0; i < 100 && !disposed; i++) await new Promise((r) => setTimeout(r, 100));

  const args = fs.readFileSync(asked, "utf8").split("\0").slice(2, -1); // (after -I and jump.py)
  assert.deepEqual(args.slice(0, 7), ["--plan-feedback", "calm-red-owl", "--profile", path.join(home, ".claude"), "--chat", "-", "--comments"]);
  assert.deepEqual(JSON.parse(args[7]), [{ from: 3, to: 4, quote: "1. Parse the file\n2. Ship it", text: "Run the tests before shipping" }]);
  assert.equal(disposed, 1, "sent: the comment is gone");
});
