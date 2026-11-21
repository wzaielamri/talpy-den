// The dashboard on its host alone (no vscode): the state it builds names each chat's and account's agent,
// the pace of this computer's checks follows the window's focus as the host tells it, and so does what it
// clears when you look. (What it sums up when you come back: comingBack.ts, run on VsCodeHost by
// vscode/test/vscodeHost.test.ts.)

import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { after, before, mock, test } from "node:test";
import type { Backend } from "../src/agents/claudeCode/backend";
import { Dashboard } from "../src/dashboard";
import type { Notifier } from "../src/notify";
import type { EditorPort } from "../src/ports";
import { useSettingsHost } from "../src/settings";
import { demoState } from "../src/shared/demo";
import { petKeyOf } from "../src/shared/model";
import type { Session, Status } from "../src/shared/types";
import type { Changes } from "../src/transitions";
import { FakeHost } from "./fakeHost";

const NOW = 1_800_000_000_000;

// (a home and a cache of the tests' own: the live watch, and away's mark file, go there; HOME and
// XDG_CACHE_HOME as they were after)
const saved = { HOME: process.env.HOME, XDG_CACHE_HOME: process.env.XDG_CACHE_HOME };
let home = "";
before(() => {
  home = fs.mkdtempSync(path.join(os.tmpdir(), "talpy-den-dashboard-core-"));
  process.env.HOME = home;
  process.env.XDG_CACHE_HOME = path.join(home, ".cache");
});
after(() => {
  for (const [k, v] of Object.entries(saved)) if (v === undefined) delete process.env[k]; else process.env[k] = v;
  fs.rmSync(home, { recursive: true, force: true });
});

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
  const advance = async (ms: number) => {
    mock.timers.tick(ms);
    await settle();
  };
  try {
    await dash.start();
    dash.setVisible(true);
    await advance(0);
    assert.equal(polls, 1);
    assert.equal(dash.watching, true, "the chats' session files are watched");
    assert.equal(fake.focus.focused, false);
    await advance(5999);
    assert.equal(polls, 1, "not at pollInterval: the window isn't focused");
    await advance(1);
    assert.equal(polls, 2, "6 s after the last check");
    fake.setFocused(true);
    await advance(6000); // (this check was set before the focus came)
    assert.equal(polls, 3);
    await advance(2000);
    assert.equal(polls, 4, "focused: pollInterval");
  } finally {
    dash.dispose();
    mock.timers.reset();
  }
});

// The dashboard's reaction to the focus: a chat that finished while you weren't looking stays unseen until the
// window has the focus with the view open
test("what finished unseen is cleared once the window has the focus with the view open", () => {
  const { fake, editor, notifier } = setup();
  const dash = new Dashboard(fake, editor, {} as Backend, notifier);
  const priv = dash as unknown as { status: Status; noteUnseen(c: Pick<Changes, "finished">): void };
  try {
    const status = structuredClone(demoState(NOW).status!);
    const done: Session = { ...status.groups[0].sessions[0], key: "fin", chatId: "fin", sessionId: "fin", state: "idle", stopped: null };
    status.groups[0].sessions.push(done);
    priv.status = status;
    priv.noteUnseen({ finished: [{ id: petKeyOf(done), session: done, took: 600_000, at: NOW, stop: "" }] });
    assert.equal(dash.unseenCount(), 1);
    fake.setFocused(true);
    assert.equal(dash.unseenCount(), 1, "the view closed: not seen");
    fake.setFocused(false);
    dash.setVisible(true);
    assert.equal(dash.unseenCount(), 1, "the view open in a window without the focus: not seen");
    fake.setFocused(true);
    assert.equal(dash.unseenCount(), 0, "seen");
  } finally {
    dash.dispose();
  }
});
