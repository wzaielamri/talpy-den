// The dashboard on its host alone (no vscode): the state it builds names each chat's and account's agent,
// and the pace of this computer's checks follows the window's focus as the host tells it.

import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { after, mock, test } from "node:test";
import type { Backend } from "../src/agents/claudeCode/backend";
import { Dashboard } from "../src/dashboard";
import type { Notifier } from "../src/notify";
import type { EditorPort } from "../src/ports";
import { useSettingsHost } from "../src/settings";
import { demoState } from "../src/shared/demo";
import { FakeHost } from "./fakeHost";

const NOW = 1_800_000_000_000;

// (a home and a cache of the test's own: the live watch, and away's mark file, go there)
const home = fs.mkdtempSync(path.join(os.tmpdir(), "talpy-den-dashboard-core-"));
process.env.HOME = home;
process.env.XDG_CACHE_HOME = path.join(home, ".cache");
after(() => fs.rmSync(home, { recursive: true, force: true }));

const setup = () => {
  const fake = new FakeHost();
  useSettingsHost(fake);
  // (no Claude Code panel here)
  const editor = { claudePanelAvailable: async () => false, onDidChangeClaudePanel: () => ({ dispose() {} }), localPanelProfileKey: () => "" } as unknown as EditorPort;
  const notifier = { handle() {}, isLeader: () => true } as unknown as Notifier;
  return { fake, editor, notifier };
};

const settle = async () => {
  for (let i = 0; i < 5; i++) await new Promise((resolve) => setImmediate(resolve));
};

test('with FakeHost and the demo data, the state carries every chat with agent "claude-code"', () => {
  const { fake, editor, notifier } = setup();
  const dash = new Dashboard(fake, editor, {} as Backend, notifier);
  try {
    dash.toggleDemo();
    const state = dash.state();
    const groups = [...(state.status?.groups ?? []), ...state.hosts.flatMap((h) => h.result?.groups ?? [])];
    assert.ok(groups.length > 1 && groups.every((g) => g.sessions.length > 0), "this computer's accounts and a host's, each with chats");
    for (const g of groups) {
      assert.equal(g.agent, "claude-code", g.id);
      for (const s of g.sessions) assert.equal(s.agent, "claude-code", s.key);
    }
  } finally {
    dash.dispose();
  }
});

// A chat at work, the view open, the chats watched (no live hook): a focused window checks at pollInterval
// (2 s), one that isn't at the working pace, 6 s
test("an unfocused window polls at the working interval", async () => {
  const { fake, editor, notifier } = setup();
  mock.timers.enable({ apis: ["setTimeout"] });
  let polls = 0;
  const backend = {
    checkPython: async () => "",
    status: async () => (polls++, { status: structuredClone(demoState(NOW).status!) }), // (one chat works)
  } as unknown as Backend;
  const dash = new Dashboard(fake, editor, backend, notifier);
  const after = async (ms: number) => {
    mock.timers.tick(ms);
    await settle();
  };
  try {
    await dash.start();
    dash.setVisible(true);
    await after(0);
    assert.equal(polls, 1);
    assert.equal(dash.watching, true, "the chats' session files are watched");
    assert.equal(fake.focus.focused, false);
    await after(5999);
    assert.equal(polls, 1, "not at pollInterval: the window isn't focused");
    await after(1);
    assert.equal(polls, 2, "6 s after the last check");
    fake.setFocused(true);
    await after(6000); // (this check was set before the focus came)
    assert.equal(polls, 3);
    await after(2000);
    assert.equal(polls, 4, "focused: pollInterval");
  } finally {
    dash.dispose();
    mock.timers.reset();
  }
});
