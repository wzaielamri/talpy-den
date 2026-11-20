import assert from "node:assert/strict";
import { test } from "node:test";
import { demoState } from "../src/shared/demo";
import { dayLabel, dayTitle, hasPeek, modelShares, recapText, recapTitle, sharePercent, statsSummary, weekdayLetter, weekdayShort } from "../src/shared/model";
import type { ChatStats, StatsDay, UsageStats } from "../src/shared/types";

const NOW = new Date(2026, 9, 18, 15, 0).getTime();
const MIN = 60000;

test("days read as local weekdays and dates", () => {
  assert.equal(weekdayShort("2026-10-18"), "Sun");
  assert.equal(weekdayShort("2026-10-15"), "Thu");
  assert.equal(dayLabel("2026-10-15"), "Thu 15 Oct");
});

test("every bar has its weekday's letter", () => {
  assert.equal(weekdayLetter("2026-10-18"), "S");
  assert.equal(weekdayLetter("2026-10-15"), "T");
});

test("shares: whole percents, under one percent and over 99 shown as such", () => {
  assert.equal(sharePercent(99, 100), "99%");
  assert.equal(sharePercent(997, 1000), ">99%");
  assert.equal(sharePercent(100, 100), "100%");
  assert.equal(sharePercent(1, 1000), "<1%");
  assert.equal(sharePercent(0, 100), "0%");
  assert.equal(modelShares([{ model: "Opus 5.5", total: 9970 }, { model: "Sonnet 5.5", total: 30 }]), "Opus 5.5 >99% · Sonnet 5.5 <1%");
});

test("a day's bar and the summary say it in words", () => {
  const day: StatsDay = { day: "2026-10-15", total: 446_759_436, output: 1_711_830, messages: 1222, chats: 6, prompts: 73 };
  assert.equal(dayTitle(day), "Thu 15 Oct: 446.8M tokens (1.7M out) · 6 chats · 73 prompts");
  assert.equal(dayTitle({ ...day, total: 0, prompts: 0, chats: 0, output: 0 }), "Thu 15 Oct: nothing");
  assert.equal(dayTitle({ ...day, chats: 1, prompts: 1 }), "Thu 15 Oct: 446.8M tokens (1.7M out) · 1 chat · 1 prompt");
  const stats: UsageStats = {
    days: Array.from({ length: 14 }, () => day),
    projects: [],
    models: [],
    sum: { total: 997_417_549, output: 3_218_060, chats: 15, prompts: 253, activeDays: 5 },
  };
  assert.equal(statsSummary(stats), "14 days: 997.4M tokens (3.2M out) · 15 chats · 253 prompts · 5 active days");
});

const recap: ChatStats = {
  prompts: 3,
  toolCalls: 278,
  tools: [["Bash", 236], ["Read", 23], ["Write", 5], ["Agent", 4], ["Edit", 4]],
  tokens: { input: 536, output: 248_717, cacheRead: 84_294_022, cacheWrite: 711_117, total: 85_254_392 },
  workedMs: 51 * MIN,
  startedAt: NOW - 62 * MIN,
  lastAt: NOW - 2 * MIN,
};

test("a chat's recap: prompts, time worked, tool calls, tokens, cost", () => {
  assert.equal(recapText(recap), "3 prompts · worked 51m · 278 tool calls (Bash 236, Read 23, Write 5) · 85.3M tokens (248.7k out)");
  assert.equal(recapText(recap, 12.4), "3 prompts · worked 51m · 278 tool calls (Bash 236, Read 23, Write 5) · 85.3M tokens (248.7k out) · $12.40 at API prices");
  assert.equal(recapText({ ...recap, prompts: 1, toolCalls: 0, tools: [], workedMs: 0, tokens: { ...recap.tokens, total: 0 } }), "1 prompt");
  const title = recapTitle(recap, NOW);
  assert.match(title, /^Started 13:58\nLast activity 14:58 \(2m ago\)\nClaude worked 51m/);
  assert.match(title, /input 536 · output 248\.7k · cache read 84\.3M · cache write 711\.1k$/);
  assert.match(recapTitle({ ...recap, startedAt: NOW - 30 * 3600000 }, NOW), /^Started Sat 17 Oct 09:00\n/);
});

test("a recap alone is something to unfold", () => {
  assert.equal(hasPeek({ peek: null, tasks: null, changes: null, stats: recap }), true);
  assert.equal(hasPeek({ peek: null, tasks: null, changes: null, stats: null }), false);
});

test("the demo has stats for every account and recaps", () => {
  const groups = demoState(NOW).status!.groups;
  for (const g of groups) {
    assert.equal(g.stats?.days.length, 14);
    assert.equal(g.stats?.days[13].day, "2026-10-18");
  }
  assert.ok(groups[0].sessions.some((s) => s.stats));
});
