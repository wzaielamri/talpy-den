// A chat opened in a terminal of a Remote-SSH window runs on the window's
// host, where VS Code can't look at the terminal's shell: until the host's
// next check lists the chat, a second click shows that terminal instead of
// resuming the chat again next to it.

import assert from "node:assert/strict";
import { mock, test } from "node:test";
import * as vscode from "vscode";
import type { Backend } from "../src/backend";
import { Dashboard } from "../src/dashboard";
import type { Notifier } from "../src/notify";
import { demoState } from "../src/shared/demo";
import { asPaste, Terminals } from "../src/terminals";

const stub = vscode as unknown as typeof import("./vscode-stub");
const NOW = 1_800_000_000_000;

test("a chat's terminal on the window's host counts as running it until a check of the host has answered", async (t) => {
  mock.timers.enable({ apis: ["Date"], now: NOW });
  const window = stub.window as unknown as { createTerminal?: unknown };
  const made: { n: number; shown: number }[] = [];
  window.createTerminal = () => {
    const term = { n: made.length + 1, shown: 0, processId: Promise.resolve(700 + made.length), exitStatus: undefined, show: () => void term.shown++ };
    made.push(term);
    return term;
  };
  stub.env.remoteName = "ssh-remote";
  t.after(() => {
    delete window.createTerminal;
    stub.env.remoteName = undefined;
    mock.timers.reset();
  });
  let answeredFrom = 0; // when the host's last check that answered started
  const terminals = new Terminals((host, since) => host === "lab" && answeredFrom >= since);
  const open = async () => ((await terminals.run("lab|c1", "c1", "claude --resume c1", { kind: "windowHost" }, { chatOn: "lab" })) as unknown as { n: number }).n;
  const at = (s: number) => mock.timers.setTime(NOW + s * 1000);

  assert.equal(await open(), 1);
  at(15);
  assert.equal(await open(), 1, "15 s later, before the host was checked again");
  answeredFrom = NOW + 5000; // a check that started before the chat had its time to start
  at(20);
  assert.equal(await open(), 1);
  answeredFrom = NOW + 25000; // one that would list it: not running there any more
  at(30);
  assert.equal(await open(), 2);
  // checks that keep failing: two minutes at most
  at(30 + 119);
  assert.equal(await open(), 2);
  at(30 + 121);
  assert.equal(await open(), 3);
  assert.deepEqual(
    made.map((m) => m.shown),
    [3, 2, 1],
  );

  // a login there is not a chat: 10 s, as before
  const login = async () => ((await terminals.run("login|lab|a", "log in", "claude /login", { kind: "windowHost" }, { private: true })) as unknown as { n: number }).n;
  assert.equal(await login(), 4);
  at(30 + 121 + 11);
  assert.equal(await login(), 5);
  terminals.dispose();
});

test("the dashboard knows when a check of a host that answered started", async () => {
  mock.timers.enable({ apis: ["Date"], now: NOW });
  let answer: unknown = { ok: false, error: "no answer" };
  const backend = { hostStatus: async () => answer } as unknown as Backend;
  const log = { warn() {}, info() {}, error() {} } as unknown as vscode.LogOutputChannel;
  const dash = new Dashboard(backend, { handle() {}, isLeader: () => true } as unknown as Notifier, log);
  try {
    (dash as unknown as { hosts: Map<string, unknown> }).hosts.set("lab", { name: "lab", loading: false, ok: false, error: "", result: null, updatedAt: 0, current: true });
    await dash.pollHost("lab");
    assert.equal(dash.hostCheckedSince("lab", NOW), false, "a check that failed");
    mock.timers.setTime(NOW + 30000);
    answer = { ok: true, result: structuredClone(demoState(NOW + 30000).status!) };
    await dash.pollHost("lab");
    assert.equal(dash.hostCheckedSince("lab", NOW + 30000), true);
    assert.equal(dash.hostCheckedSince("lab", NOW + 30001), false, "one that started later");
    assert.equal(dash.hostCheckedSince("other", 0), false);
  } finally {
    dash.dispose();
    mock.timers.reset();
  }
});

// A plan's line (or a reply) typed into a chat's terminal as a paste can't
// end the paste and press keys: Ctrl+C, then a !command Talpy Den's Enter runs
test("text typed into a chat's terminal is one paste, whatever it holds", () => {
  const plan = "3. Run the tests\x1b[201~\x03!touch /tmp/pwned-by-plan\x1b[200~\u009b201~\r\n4.\tShip\r5. Done";
  assert.equal(asPaste(plan), "\x1b[200~3. Run the tests[201~!touch /tmp/pwned-by-plan[200~201~\n4.\tShip\n5. Done\x1b[201~");
});
