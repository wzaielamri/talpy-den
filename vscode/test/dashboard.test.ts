// A reaction that fails (a pet, a notification) must not stop the dashboard
// from taking in new status: the widget froze at every plan-limit reset when
// its reset reaction threw before the status was stored.

import assert from "node:assert/strict";
import { mock, test } from "node:test";
import type * as vscode from "vscode";
import type { Backend } from "../src/backend";
import { Dashboard } from "../src/dashboard";
import type { Notifier } from "../src/notify";
import { demoState } from "../src/shared/demo";
import { chatRefOf, petKeyOf } from "../src/shared/model";
import type { Session, Status } from "../src/shared/types";

const NOW = 1_800_000_000_000;

// The focus view's Finished lines: a turn that ended (long enough to tell)
// stays there until you open that chat, also after you looked at the view;
// one its tab showed, one a limit broke off, or one that works again, doesn't
test("a finished chat stays on the focus view until you open it", () => {
  const log = { warn() {}, info() {}, error() {} } as unknown as vscode.LogOutputChannel;
  const dash = new Dashboard({} as unknown as Backend, { handle() {}, isLeader: () => true } as unknown as Notifier, log);
  const priv = dash as unknown as { status: Status; noteUnseen(c: unknown): void };
  try {
    const status = structuredClone(demoState(NOW).status!);
    priv.status = status;
    const chat = (id: string): Session => ({ ...status.groups[0].sessions[0], key: id, chatId: id, sessionId: id, state: "idle", stopped: null });
    const [a, b] = [chat("fin-a"), chat("fin-b")];
    status.groups[0].sessions.push(a, b);
    const id = (s: typeof a) => petKeyOf(s);
    const ended = (s: typeof a, took: number, stop = "") => priv.noteUnseen({ finished: [{ id: id(s), session: s, took, at: NOW, stop }] });
    ended(a, 600_000);
    ended(b, 1000); // (shorter than notifyDoneMinSeconds)
    assert.deepEqual(dash.state().finished, [id(a)]);
    dash.setVisible(true);
    assert.deepEqual(dash.state().finished, [id(a)], "showing the view leaves it");
    dash.opened(chatRefOf(a));
    assert.deepEqual(dash.state().finished, []);
    dash.lookingAt = (x) => x === id(a);
    ended(a, 600_000);
    assert.deepEqual(dash.state().finished, [], "its tab showed it");
    dash.lookingAt = () => false;
    ended(a, 600_000);
    ended(a, 600_000, "limit");
    assert.deepEqual(dash.state().finished, [], "a limit broke it off");
    ended(a, 600_000);
    a.state = "working";
    assert.deepEqual(dash.state().finished, [], "at work again");
  } finally {
    dash.dispose();
  }
});

// A reply queued for when an SSH host's chat ends its turn waits while the
// host's last check failed (its chat isn't gone, nor reachable), and goes
// once the host lists the chat as done
test("a reply after a host chat's turn waits while the host's check fails", () => {
  const actions: string[][] = [];
  const backend = { action: async (_s: string, args: string[]) => (actions.push(args), { ok: true, message: "" }) } as unknown as Backend;
  const log = { warn() {}, info() {}, error() {} } as unknown as vscode.LogOutputChannel;
  const dash = new Dashboard(backend, { handle() {}, isLeader: () => true } as unknown as Notifier, log);
  const priv = dash as unknown as { hosts: Map<string, unknown>; startDueTasks(s: Status): void; starting: Set<string> };
  try {
    const result = structuredClone(demoState(NOW).hosts[0].result!);
    // (its account not at a usage limit: a reply there would wait for the reset)
    Object.assign(result.groups[0], { limits: null, accountLimits: null, cap: null });
    for (const s of result.groups[0].sessions) s.stopped = null;
    const chat = result.groups[0].sessions[0];
    chat.state = "working";
    const status = { ...structuredClone(demoState(NOW).status!), queue: [
      { id: "q1", afterTurn: true, chat: chat.chatId || chat.sessionId, host: "lab", profile: result.groups[0].profileKeys[0] } as never] };
    priv.hosts.set("lab", { name: "lab", loading: false, ok: false, error: "timed out", result, updatedAt: NOW });
    priv.startDueTasks(status);
    priv.hosts.set("lab", { name: "lab", loading: false, ok: true, error: "", result, updatedAt: NOW });
    priv.startDueTasks(status);
    assert.equal(actions.length, 0, "not while the check failed, nor while it works");
    chat.state = "idle";
    priv.startDueTasks(status);
    assert.deepEqual(actions.map((a) => a.slice(0, 2)), [["--start-queued", "q1"]]);
  } finally {
    priv.starting.clear();
    dash.dispose();
  }
});

test("a reply after a chat's turn waits for its account's usage limit to reset, as a queued task does", () => {
  const actions: string[][] = [];
  const backend = { action: async (_s: string, args: string[]) => (actions.push(args), { ok: true, message: "" }) } as unknown as Backend;
  const log = { warn() {}, info() {}, error() {} } as unknown as vscode.LogOutputChannel;
  const dash = new Dashboard(backend, { handle() {}, isLeader: () => true } as unknown as Notifier, log);
  const priv = dash as unknown as { startDueTasks(s: Status): void; starting: Set<string> };
  try {
    const status = withFiveHour(100);
    const reset = Date.now() + 3600_000;
    status.groups[0].limits!.windows[0].resetsAt = reset;
    status.queue = [{ id: "q2", afterTurn: true, chat: "gone", profile: status.groups[0].profileKeys[0], startAt: 0 } as never];
    priv.startDueTasks(status);
    assert.deepEqual(actions.map((a) => a.slice(0, 4)), [["--requeue", "q2", "--at", String(reset + 60_000)]]);
    priv.starting.clear();
    actions.length = 0;
    status.queue = [{ ...status.queue[0], startAt: reset + 60_000 } as never]; // (requeued: it waits)
    priv.startDueTasks(status);
    assert.equal(actions.length, 0);
  } finally {
    priv.starting.clear();
    dash.dispose();
  }
});

// A task due here whose account is at its usage limit by lab's newer numbers
// (this computer's are from the morning) waits for the reset, as the
// account's bar says (shareUsage)
test("a due task waits for its account's usage limit by another machine's newer numbers", () => {
  const actions: string[][] = [];
  const backend = { action: async (_s: string, args: string[]) => (actions.push(args), { ok: true, message: "" }) } as unknown as Backend;
  const log = { warn() {}, info() {}, error() {} } as unknown as vscode.LogOutputChannel;
  const dash = new Dashboard(backend, { handle() {}, isLeader: () => true } as unknown as Notifier, log);
  const priv = dash as unknown as { hosts: Map<string, unknown>; startDueTasks(s: Status): void; starting: Set<string> };
  try {
    const status = withFiveHour(20);
    const g = status.groups[0];
    g.cap = null;
    for (const s of g.sessions) s.stopped = null;
    const reset = Date.now() + 3600_000;
    const lab = structuredClone(g);
    lab.limits = { ...lab.limits!, updatedAt: g.limits!.updatedAt + 3600_000, windows: [{ ...lab.limits!.windows[0], pct: 100, resetsAt: reset }] };
    priv.hosts.set("lab", { name: "lab", loading: false, ok: true, error: "", result: { ...structuredClone(demoState(NOW).hosts[0].result!), groups: [lab] }, updatedAt: NOW });
    dash.shownHosts = () => ["lab"];
    status.queue = [{ id: "q4", due: true, profile: g.profileKeys[0], startAt: 0 } as never];
    priv.startDueTasks(status);
    assert.deepEqual(actions.map((a) => a.slice(0, 4)), [["--requeue", "q4", "--at", String(reset + 60_000)]]);
  } finally {
    priv.starting.clear();
    dash.dispose();
  }
});

// A chat's go-on that waits for its background commands says so once, as it
// starts waiting, and once it ends them and goes on; a normal go-on, or one
// that waits on, is told as before (by the Done setting) or not at all
test("a go-on that waits for a chat's background commands is told once, and when it ends them", async () => {
  const vscode = (await import("vscode")) as unknown as typeof import("./vscode-stub");
  const window = vscode.window as unknown as Record<string, unknown>;
  const was = { warning: window.showWarningMessage, info: window.showInformationMessage };
  const shown: string[] = [];
  window.showWarningMessage = async (m: string) => (shown.push(`warning: ${m}`), undefined);
  window.showInformationMessage = async (m: string) => (shown.push(`info: ${m}`), undefined);
  const answers: Record<string, unknown>[] = [];
  const backend = { action: async () => answers.shift(), status: async () => ({ status: null }) } as unknown as Backend;
  const log = { warn() {}, info() {}, error() {} } as unknown as vscode.LogOutputChannel;
  const dash = new Dashboard(backend, { handle() {}, isLeader: () => true } as unknown as Notifier, log);
  const task = { id: "q3", chat: "e3de1242", name: "Fix it", host: "", profile: ".claude-work", account: "work", prompt: "" } as never;
  const waits = "Waits for its background command “npm run dev” to finish before it goes on; at 01:55 it ends it";
  try {
    answers.push({ ok: true, message: "“Fix it” waits for its background command “npm run dev” to finish before it goes on; at 01:55 it ends it", waits, notify: true });
    await dash.startQueued(task);
    assert.deepEqual(shown, ["warning: “Fix it” waits for its background command “npm run dev” to finish before it goes on; at 01:55 it ends it"]);
    assert.equal(dash.state().actionError, "");
    answers.push({ ok: true, message: "…", waits, notify: false }); // (a minute later: it waits on)
    await dash.startQueued(task);
    assert.equal(shown.length, 1, "told once");
    answers.push({ ok: true, message: "“Fix it” ended its background command “npm run dev” and went on in the background on work (1a2b3c4d)", ended: ["npm run dev"], notify: true });
    await dash.startQueued(task);
    assert.deepEqual(shown.slice(1), ["info: “Fix it” ended its background command “npm run dev” and went on in the background on work (1a2b3c4d)"]);
  } finally {
    Object.assign(window, { showWarningMessage: was.warning, showInformationMessage: was.info });
    dash.dispose();
  }
});

function withFiveHour(pct: number): Status {
  const status = structuredClone(demoState(NOW).status!);
  const windows = status.groups[0].limits!.windows;
  windows[0] = { ...windows[0], pct };
  return status;
}

test("the status keeps updating after a reaction to a limit reset throws", async () => {
  let next = withFiveHour(80);
  const backend = { status: async () => ({ status: next }) } as unknown as Backend;
  const notifier = { handle() {}, isLeader: () => true } as unknown as Notifier;
  const errors: string[] = [];
  const log = { warn() {}, info() {}, error: (m: string) => errors.push(m) } as unknown as vscode.LogOutputChannel;
  const dash = new Dashboard(backend, notifier, log);
  const resets: string[] = [];
  dash.onPetEvent((e) => {
    resets.push(e.kind);
    throw new Error("a pet fell over");
  });
  const fiveHour = () => dash.state().status!.groups[0].limits!.windows[0].pct;

  await dash.refresh();
  assert.equal(fiveHour(), 80);
  next = withFiveHour(2); // the 5-hour limit resets: the pets celebrate, and one throws
  await dash.refresh();
  assert.deepEqual(resets, ["reset"]);
  assert.equal(fiveHour(), 2, "the reset's status is stored");
  assert.equal(errors.length, 1, "the failure is logged");
  next = withFiveHour(3);
  await dash.refresh();
  assert.equal(fiveHour(), 3, "later polls still update");
  dash.dispose();
});

test("opening the view doesn't cancel the next try of a Python that didn't work", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });
  try {
    let checks = 0;
    const backend = {
      checkPython: async () => (++checks === 1 ? "python3 doesn't work" : ""),
      status: async () => ({ status: demoState(NOW).status! }),
    } as unknown as Backend;
    const log = { warn() {}, info() {}, error() {} } as unknown as vscode.LogOutputChannel;
    const dash = new Dashboard(backend, { handle() {}, isLeader: () => true } as unknown as Notifier, log);
    await dash.start();
    dash.setVisible(true); // polls right away (its timer used to be the retry's too)
    mock.timers.tick(30000);
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(checks, 2, "Python is checked again");
    dash.dispose();
  } finally {
    mock.timers.reset();
  }
});

test("a slow pollInterval isn't made faster while the view is hidden", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });
  const { overrides } = await import("./vscode-stub");
  overrides.set("pollInterval", 30000);
  try {
    let polls = 0;
    const backend = {
      checkPython: async () => "",
      status: async () => (polls++, { status: demoState(NOW).status! }),
    } as unknown as Backend;
    const log = { warn() {}, info() {}, error() {} } as unknown as vscode.LogOutputChannel;
    const dash = new Dashboard(backend, { handle() {}, isLeader: () => true } as unknown as Notifier, log);
    await dash.start();
    mock.timers.tick(0);
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(polls, 1);
    mock.timers.tick(10000); // hidden: not sooner than the setting
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(polls, 1, "no poll after 10 s");
    mock.timers.tick(20000);
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(polls, 2);
    dash.dispose();
  } finally {
    overrides.clear();
    mock.timers.reset();
  }
});

// Keep going and the queue go by a host's last answer: one that isn't shown is
// still checked while a chat of it keeps going or a task of it is queued here
// (else its go-on never comes), and only then; a stopped container isn't
test("a host that isn't shown is checked while something of it keeps going or is queued, and only then", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });
  const { overrides } = await import("./vscode-stub");
  overrides.set("sshHosts", []);
  overrides.set("remotePollSeconds", 30);
  const asked: string[] = [];
  const backend = {
    hostStatus: async (host: string) => (asked.push(host), host.startsWith("docker:") ? { ok: false, error: "web is stopped.", stopped: true } : { ok: false, error: "x" }),
  } as unknown as Backend;
  const log = { warn() {}, info() {}, error() {} } as unknown as vscode.LogOutputChannel;
  const dash = new Dashboard(backend, { handle() {}, isLeader: () => true } as unknown as Notifier, log);
  const priv = dash as unknown as { status: Status; scheduleHosts(delay?: number): void };
  const tick = async (ms: number) => {
    mock.timers.tick(ms);
    for (let i = 0; i < 5; i++) await new Promise((resolve) => setImmediate(resolve));
  };
  try {
    const status = structuredClone(demoState(NOW).status!);
    Object.assign(status, { keep: [], queue: [] });
    priv.status = status;
    priv.scheduleHosts(0);
    await tick(0);
    assert.deepEqual(asked, [], "nothing of it kept or queued: no ssh");
    Object.assign(status, { keep: [{ host: "lab", chat: "c1", name: "fix", profile: ".claude" }],
                            queue: [{ id: "t1", host: "docker:web", chat: null, startAt: NOW, error: "" }] });
    await tick(30000);
    assert.deepEqual(asked.splice(0), ["lab", "docker:web"]);
    await tick(30000);
    assert.deepEqual(asked.splice(0), ["lab"], "a stopped container isn't checked again");
  } finally {
    overrides.clear();
    dash.dispose();
    mock.timers.reset();
  }
});

test("a host listed twice in the settings is one host", async () => {
  const { overrides } = await import("./vscode-stub");
  const { settings } = await import("../src/config");
  overrides.set("sshHosts", ["a", " b ", "a", ""]);
  try {
    assert.deepEqual(settings.sshHosts(), ["a", "b"]);
  } finally {
    overrides.clear();
  }
});

test("with Show containers off, a Dev Containers window's own container isn't shown or checked either", async () => {
  const { overrides } = await import("./vscode-stub");
  const log = { warn() {}, info() {}, error() {} } as unknown as vscode.LogOutputChannel;
  const dash = new Dashboard({} as unknown as Backend, { handle() {}, isLeader: () => true } as unknown as Notifier, log);
  (dash as unknown as { windowHost: string }).windowHost = "docker:web";
  overrides.set("sshHosts", ["lab"]);
  try {
    assert.deepEqual(dash.shownHosts(), ["docker:web", "lab"]);
    overrides.set("showContainers", false);
    assert.deepEqual(dash.shownHosts(), ["lab"]);
  } finally {
    overrides.clear();
    dash.dispose();
  }
});

test("the Claude Code extension starting after this one is found without a reload", async () => {
  mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const stub = await import("./vscode-stub");
  const getCommands = stub.commands.getCommands;
  let registered: string[] = []; // both start on onStartupFinished, in no set order
  stub.commands.getCommands = async () => registered;
  const settle = async () => {
    for (let i = 0; i < 5; i++) await new Promise((resolve) => setImmediate(resolve));
  };
  try {
    const backend = { checkPython: async () => "", status: async () => ({ status: demoState(NOW).status! }) } as unknown as Backend;
    const log = { warn() {}, info() {}, error() {} } as unknown as vscode.LogOutputChannel;
    const dash = new Dashboard(backend, { handle() {}, isLeader: () => true } as unknown as Notifier, log);
    dash.setVisible(true);
    await dash.start();
    await settle();
    assert.equal(dash.claudeCodeInfo().available, false);
    registered = ["claude-vscode.editor.open"]; // its activate ran a moment later
    for (let s = 0; s < 10; s++) {
      mock.timers.tick(2000);
      await settle();
    }
    assert.equal(dash.claudeCodeInfo().available, true, "a Claude Code panel can reopen chats");
    dash.dispose();
  } finally {
    stub.commands.getCommands = getCommands;
    mock.timers.reset();
  }
});

test("a setting checks again only what it changes: the chat tab's text size or a sound just redraws", async () => {
  const { changeSettings, overrides } = await import("./vscode-stub");
  const backend = { status: async () => ({ status: demoState(NOW).status! }), hostStatus: async () => ({ ok: false, error: "x" }) } as unknown as Backend;
  const log = { warn() {}, info() {}, error() {} } as unknown as vscode.LogOutputChannel;
  const dash = new Dashboard(backend, { handle() {}, isLeader: () => true } as unknown as Notifier, log);
  const checks: string[] = [];
  const d = dash as unknown as { scheduleLocal(delay?: number): void; scheduleHosts(delay?: number): void };
  d.scheduleLocal = (delay?: number) => void checks.push(`here ${delay ?? "at its pace"}`);
  d.scheduleHosts = (delay?: number) => void checks.push(`hosts ${delay ?? "at their pace"}`);
  let redraws = 0;
  dash.onState(() => redraws++);
  const change = (key: string, value: unknown) => {
    overrides.set(key, value);
    changeSettings(`talpyDen.${key}`);
    const done = checks.splice(0);
    return done;
  };
  try {
    for (const [key, value] of [["chatTextScale", 1.5], ["diffSideBySide", false], ["soundVolume", 20], ["showPet", false], ["notifyDone", false], ["sshUsage", "all"]] as const)
      assert.deepEqual(change(key, value), [], key);
    assert.equal(redraws, 6, "the view and the status bar take the new settings");
    assert.deepEqual(change("keepDoneHours", 48), ["here 0", "hosts 0"]);
    assert.deepEqual(change("showTokens", false), ["here 0", "hosts 0"]);
    assert.deepEqual(change("usageCap", 80), ["here 0"]);
    assert.deepEqual(change("usageRefreshMinutes", 15), ["here 0", "hosts 0"]);
    assert.deepEqual(change("extraConfigDirs", ["/srv/claude-team"]), ["here 0"]);
    assert.deepEqual(change("sshHosts", ["lab"]), ["hosts 0"]);
    assert.deepEqual(change("includeCurrentRemote", false), [], "(no window host here)");
    assert.deepEqual(change("pollInterval", 5000), ["here at its pace"]);
    assert.deepEqual(change("remotePollSeconds", 60), ["hosts at their pace"]);
    assert.deepEqual(change("pythonPath", "/usr/bin/python3.12"), ["here 0", "hosts 0"]);
    assert.deepEqual(change("pythonPath", "/usr/bin/python3.12"), [], "set again as it was");
  } finally {
    overrides.clear();
    dash.dispose();
  }
});
