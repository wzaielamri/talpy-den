// Chats that keep going after each usage limit (the backend looks after them:
// this computer's check asks it to, in the window that notifies), the usage
// cap, the time a limit resets on hover, and the model and effort new chats
// start with.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { test } from "node:test";
import type * as vscode from "vscode";
import { chatOptionsText } from "../src/actions";
import type { Backend } from "../src/backend";
import { chatOptionArgs } from "../src/config";
import { Dashboard } from "../src/dashboard";
import type { Notifier } from "../src/notify";
import { demoState } from "../src/shared/demo";
import { clockText, findChatRef, findPlan, keptChat, keptTitle, limitReset, resetAtText, toLocalClock } from "../src/shared/model";
import type { Group, KeptChat } from "../src/shared/types";

const NOW = new Date(2026, 9, 24, 10, 0).getTime();

test("an account at the usage cap waits for that window, like one at its limit", () => {
  const g = { limits: { windows: [{ label: "5h", pct: 60, resetsAt: NOW + 3600_000 }] }, sessions: [], cap: null } as unknown as Group;
  assert.equal(limitReset(g, NOW), null);
  const capped = { ...g, cap: { pct: 50, label: "5h", key: "five_hour", resetsAt: NOW + 3600_000 } };
  assert.deepEqual(limitReset(capped, NOW), { at: NOW + 3600_000, label: "5h" });
});

test("hovering over “resets in …” says when, with the day when that isn't today", () => {
  // (in the locale's own clock: 14:20, or 02:20 PM)
  const at = new Date(2026, 9, 24, 14, 20).getTime();
  const tomorrow = new Date(2026, 9, 25, 14, 20).getTime();
  const later = new Date(2026, 9, 27, 14, 20).getTime();
  assert.equal(resetAtText(at, NOW), `Resets at ${clockText(at)}`);
  assert.equal(resetAtText(tomorrow, NOW), `Resets tomorrow at ${clockText(tomorrow)}`);
  assert.match(resetAtText(later, NOW), new RegExp(`^Resets on .+ at ${clockText(later)}$`));
});

test("the chats that keep going: found by their id, and what their tag says", () => {
  const k: KeptChat = { chat: "c1", profile: ".claude-work", name: "Fix it", since: NOW, wentOnAt: null, tries: 0, note: "", error: "" };
  assert.equal(keptChat({ keep: [k] }, "c1"), k);
  assert.equal(keptChat({ keep: [k] }, "c2"), null);
  assert.equal(keptChat({}, "c1"), null, "an older backend lists none");
  assert.match(keptTitle(k), /goes on by itself in the background a minute after the limit resets/);
  assert.match(keptTitle({ ...k, error: "Gave up after 5 tries: it didn't go on" }), /Gave up after 5 tries/);
  assert.match(keptTitle({ ...k, note: "Its account's login has expired" }), /login has expired/);
});

test("an SSH host's and a container's chats keep going too, each found under its own host", () => {
  // (2026-11-02: kept here, with their host; this computer's status lists them all)
  const here: KeptChat = { chat: "c1", profile: ".claude-work", name: "Fix it", since: NOW, wentOnAt: null, tries: 0, note: "", error: "" };
  const lab: KeptChat = { ...here, profile: ".claude", host: "lab" };
  const web: KeptChat = { ...here, profile: ".claude", host: "docker:web@lab" };
  const status = { keep: [here, lab, web] };
  assert.equal(keptChat(status, "c1"), here);
  assert.equal(keptChat(status, "c1", ""), here);
  assert.equal(keptChat(status, "c1", "lab"), lab);
  assert.equal(keptChat(status, "c1", "docker:web@lab"), web);
  assert.equal(keptChat({ keep: [here] }, "c1", "lab"), null, "this computer's isn't the host's");
  assert.deepEqual(keptChat({ keep: [{ ...here, host: "" }] }, "c1"), { ...here, host: "" });
  // the buttons and the extension don't leave a host's chat out any more
  const src = (f: string) => readFileSync(path.join(path.resolve(__dirname, "..", ".."), f), "utf8");
  const row = src("webview/components/SessionRow.tsx");
  assert.match(row, /const kept = keptChat\(view\.status, s\.chatId \|\| s\.sessionId, host\);/);
  assert.match(row, /const canKeep = !kept && s\.state === "working"/);
  assert.match(row, /\{goOn && !goingOn && !kept \? \(/);
  assert.doesNotMatch(row, /!host && !kept|kept && !host|host \? null : keptChat/);
  const recent = src("webview/components/RecentLine.tsx");
  assert.match(recent, /const kept = keptChat\(view\.status, c\.sessionId, group\.host\);/);
  assert.match(recent, /const canKeep = !kept && !goingOn && goOn > 0;/);
  assert.match(src("webview/components/QueuedTasks.tsx"), /keptChat\(view\.status, t\.chat, t\.host\)/);
  const actions = src("src/actions.ts");
  assert.match(actions, /\.\.\.\(keep \? \["--keep"\] : \[\]\)/);
  assert.match(actions, /"--keep-off", id, \.\.\.host,/);
  assert.match(actions, /\["--end", chat\.host, .*\.\.\.off\]/);
  assert.match(src("src/view.ts"), /if \(chat\) void this\.actions\.keepGoing\(chat, m\.on === true\);/);
  assert.match(src("src/dashboard.ts"), /kept: \(chat: string\) => !!keptChat\(this\.status, chat, host\)/);
});

test("new chats start with the model, effort and permission mode picked: Opus, extra high and Claude's own mode to begin with", async () => {
  const { overrides } = await import("./vscode-stub");
  try {
    assert.deepEqual(chatOptionArgs(), ["--model", "opus", "--effort", "xhigh"]);
    overrides.set("newChatModel", "sonnet");
    overrides.set("newChatEffort", "");
    assert.deepEqual(chatOptionArgs(), ["--model", "sonnet"], "Claude's own default effort");
    overrides.set("newChatMode", "plan");
    assert.deepEqual(chatOptionArgs(), ["--model", "sonnet", "--permission-mode", "plan"]);
    assert.equal(chatOptionsText("sonnet", ""), "Sonnet · Claude's default effort · Claude's default mode");
    assert.equal(chatOptionsText("opus", "xhigh", "auto"), "Opus · Extra high effort · Auto mode");
  } finally {
    overrides.clear();
  }
});

test("a starred chat or plan under Starred is one the extension knows, and an SSH host's is on this computer's clock", () => {
  const status = demoState(NOW).status!;
  const g = status.groups[0];
  const recent = g.recent[0];
  const plan = g.plans![0];
  g.starred = [{ ...recent, key: "old|starred", sessionId: "old", lastActive: NOW - 86400_000, starred: true }];
  g.starredPlans = [{ ...plan, key: "old-plan|starred", slug: "old-plan", updatedAt: NOW - 86400_000, starred: true }];
  assert.equal(findChatRef(status, [], undefined, "old|starred")?.sessionId, "old");
  assert.equal(findPlan(status, [], undefined, g.id, "old-plan|starred")?.plan.slug, "old-plan");
  assert.equal(findChatRef(status, [], undefined, "nope|starred"), null);
  const shifted = toLocalClock(status, 60_000);
  assert.equal(shifted.groups[0].starred![0].lastActive, NOW - 86400_000 + 60_000);
  assert.equal(shifted.groups[0].starredPlans![0].updatedAt, NOW - 86400_000 + 60_000);
});

test("this computer's check has the usage cap, and the window that notifies looks after the chats that keep going", async () => {
  const { overrides } = await import("./vscode-stub");
  const calls: string[][] = [];
  const backend = { status: async (args: string[]) => (calls.push(args), { status: demoState(NOW).status! }) } as unknown as Backend;
  let leader = true;
  const notifier = { handle() {}, isLeader: () => leader } as unknown as Notifier;
  const log = { warn() {}, info() {}, error() {} } as unknown as vscode.LogOutputChannel;
  const dash = new Dashboard(backend, notifier, log);
  try {
    await dash.refresh();
    assert.ok(calls[0].includes("--keep-going"));
    assert.ok(!calls[0].includes("--usage-cap"), "no cap: none asked for");
    overrides.set("usageCap", 90);
    leader = false;
    await dash.refresh();
    const args = calls[1];
    assert.deepEqual(args.slice(args.indexOf("--usage-cap"), args.indexOf("--usage-cap") + 2), ["--usage-cap", "90"]);
    assert.ok(!args.includes("--keep-going"), "another window does it");
    // plan usage this old is fetched while a chat works (5 minutes unless set; 0: never)
    const fetchAfter = (a: string[]) => a.slice(a.indexOf("--usage-refresh"), a.indexOf("--usage-refresh") + 2);
    assert.deepEqual(fetchAfter(calls[0]), ["--usage-refresh", "5"]);
    overrides.set("usageRefreshMinutes", 0);
    await dash.refresh();
    assert.deepEqual(fetchAfter(calls[2]), ["--usage-refresh", "0"]);
    overrides.set("usageRefreshMinutes", 600);
    await dash.refresh();
    assert.deepEqual(fetchAfter(calls[3]), ["--usage-refresh", "60"], "(60 at most)");
  } finally {
    overrides.clear();
    dash.dispose();
  }
});
