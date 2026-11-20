import assert from "node:assert/strict";
import { test } from "node:test";
import { demoState } from "../src/shared/demo";
import {
  allGroups,
  changesTag,
  changesTitle,
  chatsNeedingYou,
  clockText,
  forecastTitle,
  forecastWarning,
  hasPeek,
  nextChatIndex,
  peekLine,
  tasksTitle,
  trackKey,
} from "../src/shared/model";
import type { LimitWindow, Session } from "../src/shared/types";

const NOW = 1_800_000_000_000;
const MIN = 60000;
const HOUR = 60 * MIN;

function chat(partial: Partial<Session>): Session {
  return { ...demoState(NOW).status!.groups[0].sessions[0], peek: null, tasks: null, changes: null, stats: null, detail: "", ...partial };
}

const peek = { activity: "Bash: npm test", prompt: "fix it", reply: "Fixed.\n\nMore.", replyLine: "Fixed.", at: NOW };

test("the peek line says what a chat does, needs or said last", () => {
  assert.deepEqual(peekLine(chat({ state: "working", peek })), { kind: "activity", text: "▸ Bash: npm test" });
  const tasks = { done: 1, total: 3, current: "Writing tests", items: [] };
  assert.deepEqual(peekLine(chat({ state: "working", peek: { ...peek, activity: "" }, tasks })), { kind: "activity", text: "▸ Writing tests" });
  assert.equal(peekLine(chat({ state: "working" })), null);
  assert.deepEqual(peekLine(chat({ state: "waiting", detail: "approve Bash: rm x", peek })), { kind: "needs", text: "approve Bash: rm x" });
  assert.deepEqual(peekLine(chat({ state: "waiting", peek })), { kind: "needs", text: "Bash: npm test" });
  assert.deepEqual(peekLine(chat({ state: "waiting", reason: "question" })), { kind: "needs", text: "Has a question for you" });
  assert.deepEqual(peekLine(chat({ state: "idle", peek })), { kind: "reply", text: "Claude: Fixed." });
  assert.deepEqual(peekLine(chat({ state: "done", detail: "All tests pass", peek })), { kind: "result", text: "All tests pass" });
  assert.deepEqual(peekLine(chat({ state: "done", peek })), { kind: "reply", text: "Claude: Fixed." });
  assert.equal(hasPeek(chat({ peek })), true);
  assert.equal(hasPeek(chat({ peek: { ...peek, prompt: "", reply: "" } })), false);
  assert.equal(hasPeek(chat({ changes: { count: 1, files: ["a.ts"] } })), true);
});

test("task and changed-file tooltips list them", () => {
  const t = { done: 1, total: 3, current: "Testing", items: [
    { subject: "Write", status: "completed" }, { subject: "Test", status: "in_progress" }, { subject: "Ship", status: "pending" }] };
  assert.equal(tasksTitle(t), "Tasks: 1 of 3 done · now: Testing\n✓ Write\n▸ Test\n○ Ship");
  const c = { count: 14, files: ["a.ts", "b.ts"] };
  assert.match(changesTitle(c), /^14 files changed:\na\.ts\nb\.ts\n…and 12 more\nClick to compare/);
  assert.match(changesTitle({ count: 1, files: ["a.ts"] }), /^1 file changed:\na\.ts\n/);
  assert.equal(changesTag(c), "±14");
  assert.match(changesTitle(c, "lab"), /They're on lab/);
});

function win(partial: Partial<LimitWindow>): LimitWindow {
  return { key: "five_hour", label: "5h", pct: 60, resetsAt: NOW + 2 * HOUR, reset: false, forecast: null, ...partial };
}

test("the forecast warns when the pace runs out before the reset", () => {
  const fast = win({ forecast: { evenPct: 60, rate: 30, atReset: 120, fullAt: NOW + 80 * MIN, basis: "hour" } });
  // (Plasma's words: the time between running out and the reset)
  assert.equal(forecastWarning(fast, NOW), "At this pace: full in 1h 20m, 40m before it resets");
  assert.equal(
    forecastTitle(fast, NOW),
    `Your pace over the last hour: 30.0% an hour.\nAt this pace it runs out at ${clockText(NOW + 80 * MIN)}, 40m before it resets.\nAn even pace through the window would be at 60% by now (the mark).`,
  );
  const slow = win({ forecast: { evenPct: 60, rate: 5.25, atReset: 70.5, fullAt: null, basis: "window" } });
  assert.equal(forecastWarning(slow, NOW), "");
  assert.match(forecastTitle(slow, NOW), /^Your pace in this window so far: 5\.3% an hour\.\nAt this pace: about 71% when it resets \(the faded part of the bar\)\.\n/);
  // a full window: nothing about where it would be
  assert.equal(forecastTitle(win({ pct: 100, forecast: slow.forecast }), NOW).split("\n").length, 2);
  assert.equal(forecastWarning(win({ reset: true, forecast: fast.forecast }), NOW), "");
  assert.equal(forecastTitle(win({}), NOW), "");
});

test("the shortcut goes to the chat waiting longest, then to finished ones you haven't seen", () => {
  const s = demoState(NOW);
  const groups = allGroups(s.status, s.hosts);
  const g = groups[0];
  const waiting = g.sessions.find((x) => x.state === "waiting")!,
    done = g.sessions.find((x) => x.state === "done")!;
  const extra: Session[] = [
    { ...waiting, key: "w-old", sessionId: "w-old", chatId: "w-old", name: "older wait", since: NOW - 20 * MIN },
    { ...done, key: "f-1", sessionId: "f-1", chatId: "f-1", name: "finished first", state: "done" },
    { ...done, key: "f-2", sessionId: "f-2", chatId: "f-2", name: "finished last", state: "idle" },
  ];
  groups[0] = { ...g, sessions: [...g.sessions, ...extra] };
  const host = groups[1];
  const unseen = new Map([
    [trackKey(extra[1]), NOW - 5 * MIN],
    [trackKey(extra[2]), NOW - MIN],
    ["gone|x", NOW],
  ]);
  const list = chatsNeedingYou(groups, unseen);
  assert.deepEqual(list.map((c) => c.session.name), ["older wait", "Release notes for 2.0", "finished last", "finished first"]);
  assert.equal(trackKey(host.sessions[0], host.host), `ssh:build-server|${host.sessions[0].profileDir}/demo-4`);
  assert.equal(nextChatIndex(list, null, NOW), 0);
  assert.equal(nextChatIndex(list, { id: list[0].id, at: NOW - 10000 }, NOW), 1);
  assert.equal(nextChatIndex(list, { id: list[3].id, at: NOW - 10000 }, NOW), 0, "round and round");
  assert.equal(nextChatIndex(list, { id: list[1].id, at: NOW - 60000 }, NOW), 0, "a while later: from the top");
  assert.equal(nextChatIndex([], null, NOW), -1);
});
