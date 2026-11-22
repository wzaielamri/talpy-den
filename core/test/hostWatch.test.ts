// (2026-11-06) Talpy Chat's watcher of an SSH host or a container (hostWatch.ts):
// remote.py --watch again and again while it's wanted, what changed handed on,
// failures backed off, one that couldn't reach the host waiting for its next check.

import assert from "node:assert/strict";
import { test } from "node:test";
import { useSettingsHost } from "../src/settings";
import { FakeHost } from "./fakeHost";
import { HostWatch, watchName, type WatchAnswer } from "../src/agents/claudeCode/hostWatch";
import { hookedAtWork } from "../src/shared/model";

useSettingsHost(new FakeHost());

const tick = (ms = 10) => new Promise((r) => setTimeout(r, ms));
const fast = { retry: 20, retryLong: 60, again: 5 };   // (again: never a tight loop of answers at once)

test("a watcher runs again at once, hands on what changed, and stops when it's no longer wanted", async () => {
  const asked: string[][] = [];
  const answers: WatchAnswer[] = [
    { ok: true, sessions: true, requests: true, changed: [] },
    { ok: true, sessions: false, requests: true, changed: ["chat-1"] },
    { ok: true, timeout: true },
  ];
  const got: [string, WatchAnswer][] = [];
  let stop: () => void = () => undefined;
  const w = new HostWatch("lab", async (args) => {
    asked.push(args);
    await tick(5);
    const a = answers.shift();
    if (!a) {
      stop();
      return { ok: true, timeout: true };
    }
    return a;
  }, "a1b2c3d4e5f6", (host, a) => got.push([host, a]), undefined, fast);
  stop = () => w.stop();
  w.start();
  await tick(100);
  assert.deepEqual(asked[0], ["remote.py", "--watch", "lab", "--as", "a1b2c3d4e5f6"]);
  assert.equal(asked.length, 4, "again at once after each answer, till it was stopped");
  assert.deepEqual(got.map(([h, a]) => [h, a.requests, a.changed]), [["lab", true, []], ["lab", true, ["chat-1"]]], "a timeout hands nothing on");
});

test("failures back off; three in a row say why; one that couldn't reach the host waits for its next check", async () => {
  let calls = 0;
  const troubles: string[] = [];
  let next: WatchAnswer = { ok: false, error: "lab: kex_exchange_identification" };
  const w = new HostWatch("lab", async () => (calls++, next), "a1b2c3d4e5f6", () => undefined, (_h, t) => troubles.push(t), fast);
  w.start();
  await tick(70);
  assert.ok(calls >= 3 && calls <= 4, `backed off: ${calls}`);
  assert.deepEqual(troubles, ["lab: kex_exchange_identification"]);
  assert.equal(w.running, true);
  next = { ok: false, reached: false, error: "Can't reach lab" };
  await tick(100);
  assert.equal(w.trouble, "check");
  assert.equal(w.running, false, "it waits for the host's next check");
  const before = calls;
  await tick(100);
  assert.equal(calls, before, "nothing runs meanwhile");
  next = { ok: true, timeout: true };
  w.checked();
  await tick(30);
  assert.ok(calls > before);
  assert.equal(w.trouble, "");
  w.stop();
});

test("a watcher's name is a hash of the window's own (it shows in the host's process list)", () => {
  assert.match(watchName("session-1"), /^[0-9a-f]{12}$/);
  assert.equal(watchName("session-1"), watchName("session-1"));
  assert.notEqual(watchName("session-1"), watchName("session-2"), "two windows don't share what they were told");
});

test("the chats whose prompts only Talpy Den can show: the window that notifies watches their host", () => {
  assert.equal(hookedAtWork({ hooked: true, state: "working", permission: null }), true);
  assert.equal(hookedAtWork({ hooked: true, state: "idle", permission: null }), false);
  assert.equal(hookedAtWork({ hooked: false, state: "working", permission: null }), false, "a terminal's asks in its terminal");
  assert.equal(hookedAtWork({ hooked: false, state: "waiting", permission: { answer: "hook" } as never }), true, "the hook for every chat");
});

// (2026-11-22) The chats of the tabs that show there go along (--chats): it says when one was written ("wrote"),
// so a tab reads its conversation then, not every few seconds in case. Other chats: the run on its way ends (it
// can't take them in) and it runs again with them at once, which isn't a failure
test("the chats of the tabs that show go along; other chats end the run on its way and it runs again with them", async () => {
  const asked: string[][] = [];
  const ended: string[][] = [];
  const got: WatchAnswer[] = [];
  const answers: WatchAnswer[] = [{ ok: true, sessions: false, requests: false, changed: [], wrote: ["c1"] }];
  const w = new HostWatch("lab", (args, _ms, signal) => {
    asked.push(args);
    const a = answers.shift();
    if (a) return Promise.resolve(a);
    return new Promise((resolve) => {
      signal?.addEventListener("abort", () => (ended.push(args), resolve({ ok: false, message: "the helper gave no answer" })));
    });
  }, "a1b2c3d4e5f6", (_h, a) => got.push(a), undefined, fast);
  w.setChats(["c2", "c1"]);
  w.start();
  await tick(30);
  const line = ["remote.py", "--watch", "lab", "--as", "a1b2c3d4e5f6", "--chats", "c1,c2"];
  assert.deepEqual(asked, [line, line]);
  assert.deepEqual(got.map((a) => a.wrote), [["c1"]], "a chat written is handed on");
  assert.equal(w.watches("c2"), true);
  w.setChats(["c1", "c2"]);
  await tick();
  assert.equal(asked.length, 2, "the same chats: it goes on");
  w.setChats(["c1"]);
  await tick();
  assert.deepEqual(ended, [line], "the run for the chats before ended");
  assert.deepEqual(asked[2], ["remote.py", "--watch", "lab", "--as", "a1b2c3d4e5f6", "--chats", "c1"]);
  assert.equal(w.watches("c2"), false);
  assert.equal(w.trouble, "", "not a failure");
  w.setChats([]);
  await tick();
  assert.deepEqual(asked[3], ["remote.py", "--watch", "lab", "--as", "a1b2c3d4e5f6"]);
  w.stop();
  await tick();
  assert.equal(ended.length, 3, "stopped: the run on its way ends too");
});
