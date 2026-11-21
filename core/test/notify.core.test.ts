import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, test } from "node:test";
import { AwayWatch } from "../src/away";
import { Notifier } from "../src/notify";
import { useSettingsHost } from "../src/settings";
import { demoState } from "../src/shared/demo";
import type { Session } from "../src/shared/types";
import { FakeHost } from "./fakeHost";

// (each test's cache, where the lead's file and away's mark go, is its own: gone after it, XDG_CACHE_HOME
// as it was)
const savedCache = process.env.XDG_CACHE_HOME;
const caches: string[] = [];
afterEach(() => {
  for (const dir of caches.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
  if (savedCache === undefined) delete process.env.XDG_CACHE_HOME;
  else process.env.XDG_CACHE_HOME = savedCache;
});

// The notifier talks to its host alone (no vscode): which window leads, and a question's buttons (a
// permission prompt's: vscode/test/notify.test.ts, through VsCodeHost)
const setup = () => {
  process.env.XDG_CACHE_HOME = fs.mkdtempSync(path.join(os.tmpdir(), "talpy-den-notify-core-"));
  caches.push(process.env.XDG_CACHE_HOME);
  const fake = new FakeHost();
  useSettingsHost(fake);
  const notifier = new Notifier(fake, { sound() {} } as never, () => undefined);
  return { fake, notifier };
};

test("an unfocused window that leads notifies; a focused one claims the lead", () => {
  const { fake, notifier } = setup();
  assert.equal(fake.focus.focused, false);
  assert.equal(notifier.isLeader(), true, "no one leads yet: this window takes it");
  // another window leads (a live process that isn't this one): this one doesn't speak until it is focused
  const other = fs.readFileSync(path.join(process.env.XDG_CACHE_HOME!, "talpy-den", "vscode-notify.json"), "utf8");
  assert.equal(JSON.parse(other).pid, process.pid);
  fs.writeFileSync(path.join(process.env.XDG_CACHE_HOME!, "talpy-den", "vscode-notify.json"), JSON.stringify({ pid: process.ppid, at: Date.now() }));
  assert.equal(notifier.isLeader(), false);
  fake.setFocused(true);
  assert.equal(notifier.isLeader(), true);
  notifier.dispose();
});

test("the host's use state drives the away watch: its first use marks the window used, nothing to sum up; in use again after it left, it came back", () => {
  const { fake } = setup();
  const mark = path.join(process.env.XDG_CACHE_HOME!, "talpy-den", "vscode-active.json");
  const backs: number[] = [];
  const watch = new AwayWatch(fake, (now) => backs.push(now));
  assert.equal(fs.existsSync(mark), false, "started in the background: not used yet");
  fake.setActive(true); // (the first use of a window that started in the background: nothing to sum up)
  assert.equal(JSON.parse(fs.readFileSync(mark, "utf8")).pid, process.pid, "marked: this window was in use");
  assert.deepEqual(backs, []);
  fake.setActive(false);
  assert.notEqual(watch.tracker.since, null, "left");
  fake.setActive(true);
  assert.equal(backs.length, 1, "back");
  watch.dispose();
});

test("a question with an option named Open: its own Open button opens the chat, the option answers", async () => {
  const { fake, notifier } = setup();
  const answers: unknown[] = [];
  const opened: string[] = [];
  notifier.panes = {
    answer: async (_c: unknown, d: string, _s: unknown, _n: string, a: unknown) => (answers.push([d, a]), { ok: true, message: "" }),
    open: (c: { name: string }) => opened.push(c.name),
  } as never;
  const q = { question: "Open the PR or draft it?", header: "PR", multiSelect: false, options: [{ label: "Open", description: "" }, { label: "Draft", description: "" }] };
  const s = {
    ...demoState(Date.now()).status!.groups[0].sessions[0], state: "waiting", name: "pr",
    permission: { tool: "AskUserQuestion", line: q.question, command: "", file: "", diff: [], always: "", questions: [q], request: "r1", answer: "hook" },
  } as unknown as Session;
  const notify = async () => {
    notifier.handle({ notices: [{ key: s.key, kind: "waiting", title: "pr asks you", body: "", session: s }], petEvents: [], sound: "", finished: [] });
    await new Promise((r) => setTimeout(r, 10));
  };
  fake.answer.message = () => 3; // the last button: Open
  await notify();
  assert.deepEqual(fake.recorded.messages[0].actions, ["Open", "Draft", "Other…", "Open"]);
  assert.deepEqual([opened.length, answers], [1, []], "Open opened the chat");
  fake.answer.message = () => 0; // the option: Open
  await notify();
  assert.deepEqual([opened.length, answers], [1, [["answer", { [q.question]: ["Open"] }]]], "the option answered");
  notifier.dispose();
});
