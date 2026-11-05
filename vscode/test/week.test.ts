// The Recap tab: its words and numbers (src/shared/week.ts), and what the
// extension takes from the page's Week messages.

import assert from "node:assert/strict";
import { test } from "node:test";
import * as vscode from "vscode";
import { demoLimits, demoPerms, demoState, demoWeek } from "../src/shared/demo";
import { clockText } from "../src/shared/model";
import type { WeekDay } from "../src/shared/types";
import {
  coldText, currencyOf, dayTip, deltaText, factsText, fillPaths, footText, hoursText, hoverText, moneyText, periodText, planText, promptsText, ruleMeta,
  weekAsked, weekRevokeAsked, weekRuleAsked, weekTiles, RECAP_SECTIONS, windowSpan, workText, grantMeta, grantedIntro, ruleMeaning,
  shareText, tipMeaning,
  dateText, periodWaiting, rowDay, shortDay, stepText, weekRows,
  limitChangeText, limitDots, limitEventText, limitFillText, limitFootText, limitKeys, limitLabel, limitMix, limitMoney, limitShareText, limitTokensText,
  limitStart, limitWeekBars,
} from "../src/shared/week";
import { ViewHost } from "../src/view";

const MIN = 60000;
const HOUR = 60 * MIN;
const NOW = new Date(2026, 9, 24, 18, 0).getTime();

test("hours, money and changes against the week before", () => {
  assert.equal(hoursText(45 * MIN), "45m");
  assert.equal(hoursText(32 * HOUR + 6 * MIN), "32h 6m");
  assert.equal(moneyText(906.4), "$906");
  assert.equal(moneyText(1234.5), "$1,235");
  assert.equal(moneyText(23.8), "$23.80");
  assert.equal(moneyText(0.004), "<$0.01");
  assert.equal(moneyText(0), "$0");
  assert.equal(deltaText(18 * HOUR, 13 * HOUR + 16 * MIN, "time"), "+4h 44m");
  assert.equal(deltaText(397, 906, "money"), "−$509");
  assert.equal(deltaText(219, 219, "count"), "same as before");
  assert.equal(deltaText(219, null, "count"), "");
});

test("the days shown, and the week's facts", () => {
  const recap = demoWeek(NOW);
  assert.equal(periodText(recap), "Last 7 days · 18 Oct – 24 Oct");
  assert.equal(periodText(demoWeek(NOW, 1)), "11 Oct – 17 Oct");
  assert.match(factsText(recap.sum), /^longest turn 48m \(Port the date parser\) · up to 2 chats at once · busiest day \w+day · usage limits stopped you 2 times$/);
  const tiles = weekTiles(recap);
  assert.deepEqual(tiles.map((t) => t.label), ["You", "Claude worked", "Prompts", "Tokens", "At API prices"]);
  assert.match(tiles[1].tip, /On the clock it worked .*, and it waited 3h 18m for your answers\.\nThe 7 days before: /);
  assert.equal(weekTiles({ ...recap, previous: { youMs: 0, workedMs: 0, busyMs: 0, waitMs: 0, prompts: 0, cost: 0, tokenTotal: 0 } })[0].delta, "");
});

test("the Recap reads as a story: the tiles, what Claude did, when, where, then the money", () => {
  assert.deepEqual(weekTiles(demoWeek(NOW)).map((t) => t.label), ["You", "Claude worked", "Prompts", "Tokens", "At API prices"]);
  // (Turns that cost the most is gone: Chats it worked on most says it; the cold-cache note is with the tips)
  assert.deepEqual([...RECAP_SECTIONS], ["work", "days", "plan", "lanes", "projects", "chats", "models", "tips"]);
});

test("the tokens used: a tile with its change and trend, and a row's tokens", () => {
  assert.equal(deltaText(226_300_000, 400_000_000, "tokens"), "−173.7M");
  assert.equal(deltaText(1_500, 0, "tokens"), "+1.5k");
  assert.equal(deltaText(1_000_020, 1_000_000, "tokens"), "same as before");
  const recap = demoWeek(NOW);
  const tile = weekTiles(recap)[3];
  assert.equal(tile.label, "Tokens");
  assert.equal(tile.value, "626.3M");
  assert.equal(tile.delta, "+156.6M");
  assert.match(tile.tip, /^Everything Claude read and wrote: 41\.2k of new input, 612\.0M read from the cache, 11\.9M written to the cache and 2\.3M that Claude wrote\.\nThe 7 days before: 469\.7M\nWeek by week, these 7 days last: .* · 626\.3M$/);
  assert.equal(tile.trend[4], recap.sum.tokenTotal);
  assert.equal(recap.days.reduce((sum, d) => sum + d.tokenTotal, 0), recap.sum.tokenTotal);
  assert.match(dayTip(recap.days[5]), /31 prompts · 118\.6M tokens · \$64\.00 at API prices/);
  const day = weekTiles(demoWeek(NOW, 0, "", "day"));
  assert.match(day[3].tip, /\nThe day before: .*\nDay by day, this day last: /);
  const all = demoWeek(NOW, 0, "", "all");
  assert.equal(all.sum.tokenTotal, all.days[0].tokenTotal + all.days[1].tokenTotal);
});

test("pointing at a day says what went on then", () => {
  const start = new Date(2026, 9, 24).getTime();
  const at = (h: number) => start + h * HOUR;
  const day: WeekDay = {
    day: "2026-10-24", start, end: start + 24 * HOUR, you: [[at(9), at(10)]], work: [[at(9.5), at(11), 2]], wait: [[at(1), at(9)]],
    youMs: HOUR, workedMs: 3 * HOUR, busyMs: 1.5 * HOUR, waitMs: 8 * HOUR, prompts: 3, cost: 4, tokenTotal: 2_500_000, limits: [at(10.5)], chats: [],
  };
  const px = (24 * HOUR) / 400;
  assert.match(hoverText(day, at(10.5), NOW, px), /: a usage limit stopped a chat at .* · Claude worked /);
  assert.match(hoverText(day, at(3), NOW, px), /^Sat 24 Oct, .*: Claude waited for your answer .*–.*$/);
  assert.match(hoverText(day, at(9.75), NOW, px), /Claude worked .*, 2 chats at once · you were at it /);
  assert.match(hoverText(day, at(14), NOW, px), /nothing went on$/);
  assert.match(hoverText(day, at(20), NOW, px), /still to come$/);
});

test("amounts in another currency, at the rate week.py sends", () => {
  const eur = { code: "EUR", rate: 0.8934 };
  assert.equal(moneyText(941, eur), "€841");
  assert.equal(moneyText(23.8, eur), "€21.26");
  assert.equal(moneyText(0.004, eur), "<€0.01");
  assert.equal(moneyText(12, { code: "JPY", rate: 152.3 }), "¥1,828");
  assert.equal(moneyText(12, { code: "CHF", rate: 0.8 }), "9.60 CHF");
  assert.equal(deltaText(397, 906, "money", eur), "−€455");
  const recap = { ...demoWeek(NOW), currency: { code: "EUR", rate: 0.9, date: "2026-10-23", error: "" } };
  assert.deepEqual(currencyOf(recap), recap.currency);
  assert.match(weekTiles(recap)[4].value, /^€/);
  assert.match(footText(recap), /Amounts in EUR at the European Central Bank's rate of 23 Oct 2026: 1 USD = 0\.9000 EUR\./);
  const failed = { ...recap, currency: { code: "USD", rate: 1, date: "", error: "no EUR rate from the European Central Bank yet" } };
  assert.equal(currencyOf(failed).code, "USD");
  assert.match(footText(failed), /Amounts in US dollars: no EUR rate/);
});

test("trend lines, what Claude did, where the money went, the prompts you answered", () => {
  const recap = demoWeek(NOW);
  const tiles = weekTiles(recap);
  assert.equal(tiles[1].trend.length, 5);
  assert.equal(tiles[1].trend[4], recap.sum.workedMs);
  assert.match(tiles[1].tip, /\nWeek by week, these 7 days last: .* · .* · .* · .* · /);
  assert.deepEqual(weekTiles(demoWeek(NOW, 3))[0].trend.slice(0, 2), [null, null]);
  assert.match(weekTiles(demoWeek(NOW, 3))[0].tip, /these 7 days last: \? · \? · /);
  assert.equal(workText(recap.work), "3,184 tool calls · 1,410 commands run · 699 edits in 143 files (+9,412 −2,210) · 21 subagents started · 6 web searches · 9 pages fetched · 3 compactions");
  assert.equal(workText({ ...recap.work, toolCalls: 1, commands: 1, edits: 1, files: 1, subagents: 0, webSearches: 0, webFetches: 0, compactions: 0 }),
    "1 tool call · 1 command run · 1 edit in 1 file (+9,412 −2,210)");
  assert.match(coldText(recap), /^You came back to chats after their cache had expired \(an hour without a reply\) 5 times: .*\$11\.40 more .* Most in: Release notes for 2\.0 \(3×, \$7\.10\)\.$/);
  assert.equal(promptsText(recap.prompts), "You answered 148 permission prompts and refused 2 of them. They waited for your answer 3h 18m in all.");
  assert.equal(ruleMeta(recap.prompts.rules[0]), "24 prompts · waited 2h 6m for you · e.g. ~/projects/shared-ui/src/button.tsx");
});

test("a plan window's fill, from its start to its reset", () => {
  const w = { key: "five_hour", label: "5h", resetsAt: NOW + 2 * HOUR, pct: 60, points: [[NOW - 4 * HOUR, 0], [NOW - 3 * HOUR, 30], [NOW - HOUR, 60]] as [number, number][] };
  assert.deepEqual(windowSpan(w), [NOW - 3 * HOUR, NOW + 2 * HOUR]);
  const { line, area } = fillPaths(w, NOW, 100, 20);
  assert.equal(line, "M0.0,13.8 L40.0,8.1 L60.0,8.1"); // (the point before the window's start left out; level up to now)
  assert.equal(area, "M0.0,20 L0.0,13.8 L40.0,8.1 L60.0,8.1 L60.0,20 Z");
  assert.deepEqual(fillPaths({ ...w, points: [] }, NOW, 100, 20), { line: "", area: "" });
  assert.equal(planText(w, NOW), `60% · resets ${new Date(NOW + 2 * HOUR).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`);
  // one past its reset (week.py: plan_windows) says so, as on the Chats tab
  assert.equal(planText({ ...w, pct: 0, resetsAt: null, reset: true, points: [] }, NOW), "0% · reset");
});

test("a rule message is taken only in the shapes the tab sends", () => {
  assert.deepEqual(weekRuleAsked({ allow: true, kind: "dir", value: "/w/lib", project: "/w/app" }),
    { allow: true, kind: "dir", value: "/w/lib", project: "/w/app" });
  assert.deepEqual(weekRuleAsked({ allow: false, id: "a1b2c3d4e5f6" }), { allow: false, id: "a1b2c3d4e5f6" });
  assert.equal(weekRuleAsked({ allow: true, kind: "shell", value: "x", project: "/a" }), null);
  assert.equal(weekRuleAsked({ allow: true, kind: "allow", value: "Bash(ls *)", project: "relative" }), null);
  assert.equal(weekRuleAsked({ allow: true, kind: "allow", value: "Bash(ls *)\nrm", project: "/a" }), null);
  assert.equal(weekRuleAsked({ allow: "yes", kind: "allow", value: "Bash(ls *)", project: "/a" }), null);
  assert.equal(weekRuleAsked({ allow: false, id: "../x" }), null);
});

test("a day and everything: what the period line says, Overall's rows", () => {
  const day = demoWeek(NOW, 0, "", "day");
  assert.equal(day.days.length, 1);
  assert.match(periodText(day), /^Today · \w{3} \d+ \w{3}$/);
  assert.match(periodText({ ...day, back: 1 }), /^Yesterday · /);
  const all = demoWeek(NOW, 0, "", "all");
  assert.equal(all.previous, null);
  assert.equal(all.days.length, 2);
  assert.equal(all.sum.workedMs, all.days[0].workedMs + all.days[1].workedMs);
  assert.equal(periodText(all), `Everything since ${dateText(all.first!)}`);
  assert.deepEqual([periodWaiting("day", 0), periodWaiting("all", 0), periodWaiting("week", 1)], ["Today", "Everything", ""]);
  assert.equal(rowDay(all.days[0].day, true), shortDay(all.days[0].day));
  assert.equal(weekTiles(all)[0].delta, "");
});

test("a month: the last 30 days, a row per 7 days, against the 30 before", () => {
  const month = demoWeek(NOW, 0, "", "month");
  assert.equal(month.days.length, 5);
  assert.ok(month.days[0].start > month.days[1].start); // (newest first)
  assert.deepEqual([weekRows("month"), weekRows("all"), weekRows("week"), weekRows("day")], [true, true, false, false]);
  assert.match(periodText(month), /^Last 30 days · \d+ \w{3} – \d+ \w{3}$/);
  assert.doesNotMatch(periodText({ ...month, back: 1 }), /^Last/);
  assert.equal(periodWaiting("month", 0), "Last 30 days");
  assert.deepEqual([stepText("month", false), stepText("month", true), stepText("day", false), stepText("week", true)],
    ["The 30 days before", "The 30 days after", "The day before", "The week after"]);
  assert.ok(month.sum.workedMs > 0);
  const tip = weekTiles(month)[0].tip;
  assert.match(tip, /\nThe 30 days before: /);
  assert.match(tip, /\n30 days at a time, these 30 days last: /);
});

test("a permission you gave is revoked only by an id of week.py's list", () => {
  assert.equal(weekRevokeAsked("a1b2c3d4e5f6"), "a1b2c3d4e5f6");
  for (const bad of ["../x", "A1B2C3D4E5F6", "a1b2c3d4e5f", 12, null]) assert.equal(weekRevokeAsked(bad), null);
  const g = demoPerms(NOW).granted[1];
  assert.equal(grantMeta(g), "chats started in date-parser · ~/projects/date-parser/.claude/settings.local.json");
  assert.equal(grantedIntro([]), "Nothing lets chats on this computer skip a permission prompt: they ask you each time.");
  // a rule it suggests has its kind's icon, as Plasma's
  assert.deepEqual([{ kind: "dir", value: "/h/lib" }, { kind: "edits", value: "/h/app" }, { kind: "allow", value: "WebFetch(domain:x.org)" },
    { kind: "allow", value: "Bash(git status *)" }].map(ruleMeaning), ["folder", "edit", "webAccess", "terminal"]);
});

function setup() {
  const calls: { name: string; args: unknown[] }[] = [];
  const posted: unknown[] = [];
  const record = (name: string) => (...args: unknown[]) => {
    calls.push({ name, args });
    return Promise.resolve(name === "weekRule" || name === "weekRevoke" ? { ok: true, message: "done" }
      : name === "perms" ? { data: demoPerms(NOW) } : { recap: demoWeek(NOW) });
  };
  const state = demoState(NOW);
  const actions = new Proxy({}, { get: (_target, name: string) => record(name) });
  const dash = {
    onState: () => ({ dispose() {} }),
    onPetEvent: () => ({ dispose() {} }),
    onLive: () => ({ dispose() {} }), onUsageCameIn: () => ({ dispose() {} }),
    state: () => state,
    setVisible() {},
    week: record("week"),
    weekRule: record("weekRule"),
    weekRevoke: record("weekRevoke"),
    perms: record("perms"),
  };
  const host = new ViewHost(vscode.Uri.file("/ext") as never, dash as never, actions as never);
  const priv = host as unknown as { receive(webview: unknown, m: unknown): void };
  const webview = { postMessage: (m: unknown) => (posted.push(m), Promise.resolve(true)) };
  return { calls, posted, receive: (m: unknown) => priv.receive(webview, m) };
}

test("the page asks for a span, days or weeks back, for an account id or all", async () => {
  assert.deepEqual(weekAsked(2, "0123456789ab"), { back: 2, account: "0123456789ab", span: "week" });
  assert.deepEqual(weekAsked(99, "../../etc", "day"), { back: 99, account: "", span: "day" });
  assert.deepEqual(weekAsked(-3, null, "all"), { back: 0, account: "", span: "all" });
  assert.deepEqual(weekAsked(1, null, "month"), { back: 1, account: "", span: "month" });
  assert.deepEqual(weekAsked("1", null, "../x"), { back: 0, account: "", span: "week" });
  assert.deepEqual(weekAsked(1e9, ""), { back: 3650, account: "", span: "week" });
  const { calls, posted, receive } = setup();
  receive({ type: "week", back: 1, account: "ba9876543210" });
  assert.deepEqual(calls, [{ name: "week", args: [1, "ba9876543210", "week"] }]);
  await new Promise((r) => setTimeout(r, 0));
  const answer = posted[0] as { type: string; back: number; account: string; recap: unknown };
  assert.equal(answer.type, "week");
  assert.equal(answer.back, 1);
  assert.equal(answer.account, "ba9876543210");
  assert.ok(answer.recap);
});

test("Allow and Undo reach the backend only as rules; the answer goes back to the page", async () => {
  const { calls, posted, receive } = setup();
  receive({ type: "weekRule", allow: true, kind: "allow", value: "Bash(git status *)", project: "/w/app", id: "" });
  receive({ type: "weekRule", allow: true, kind: "allow", value: "Bash(git status *)", project: "../app", id: "" });
  receive({ type: "weekRule", allow: false, kind: "", value: "", project: "", id: "a1b2c3d4e5f6" });
  receive({ type: "weekRule", allow: false, kind: "", value: "", project: "", id: "a1b2c3d4e5f6", host: "lab" });
  receive({ type: "weekRule", allow: false, kind: "", value: "", project: "", id: "a1b2c3d4e5f6", host: "-oProxyCommand=x" });
  assert.deepEqual(calls, [
    { name: "weekRule", args: [{ allow: true, kind: "allow", value: "Bash(git status *)", project: "/w/app" }, ""] },
    { name: "weekRule", args: [{ allow: false, id: "a1b2c3d4e5f6" }, ""] },
    { name: "weekRule", args: [{ allow: false, id: "a1b2c3d4e5f6" }, "lab"] }, // (the dashboard acts only on a host shown)
  ]);
  await new Promise((r) => setTimeout(r, 0));
  // (what it refuses is answered too, at once: the page's buttons wait for an answer)
  const refused = "that isn't something Talpy Den can change";
  assert.deepEqual(posted, [
    { type: "weekRule", id: "", host: "", ok: false, message: refused },
    { type: "weekRule", id: "a1b2c3d4e5f6", host: "-oProxyCommand=x", ok: false, message: refused },
    { type: "weekRule", id: "", host: "", ok: true, message: "done" },
    { type: "weekRule", id: "a1b2c3d4e5f6", host: "", ok: true, message: "done" },
    { type: "weekRule", id: "a1b2c3d4e5f6", host: "lab", ok: true, message: "done" },
  ]);
});

test("the Permissions tab asks for what it shows; the answer goes back to the page", async () => {
  const { calls, posted, receive } = setup();
  receive({ type: "perms" });
  assert.deepEqual(calls, [{ name: "perms", args: [] }]);
  await new Promise((r) => setTimeout(r, 0));
  const answer = posted[0] as { type: string; data: { prompts: unknown; granted: unknown[]; hosts: { host: string }[] } | null; error: string };
  assert.equal(answer.type, "perms");
  assert.equal(answer.data?.granted.length, 5);
  assert.deepEqual(answer.data?.hosts.map((h) => h.host), ["build-server"]);
  assert.equal(answer.error, "");
});

test("Revoke reaches the backend only as an id; the answer goes back to the page", async () => {
  const { calls, posted, receive } = setup();
  receive({ type: "weekRevoke", id: "../../.ssh" });
  receive({ type: "weekRevoke", id: "a1b2c3d4e5f6" });
  receive({ type: "weekRevoke", id: "a1b2c3d4e5f6", host: "lab" });
  receive({ type: "weekRevoke", id: "a1b2c3d4e5f6", host: "a b" });
  receive({ type: "weekRevoke", id: "a1b2c3d4e5f6", host: "podman:web@lab" }); // (a container's section)
  assert.deepEqual(calls, [{ name: "weekRevoke", args: ["a1b2c3d4e5f6", ""] }, { name: "weekRevoke", args: ["a1b2c3d4e5f6", "lab"] },
    { name: "weekRevoke", args: ["a1b2c3d4e5f6", "podman:web@lab"] }]);
  await new Promise((r) => setTimeout(r, 0));
  const refused = "that isn't something Talpy Den can change";
  assert.deepEqual(posted, [{ type: "weekRevoke", id: "", host: "", ok: false, message: refused },
    { type: "weekRevoke", id: "a1b2c3d4e5f6", host: "a b", ok: false, message: refused },
    { type: "weekRevoke", id: "a1b2c3d4e5f6", host: "", ok: true, message: "done" },
    { type: "weekRevoke", id: "a1b2c3d4e5f6", host: "lab", ok: true, message: "done" },
    { type: "weekRevoke", id: "a1b2c3d4e5f6", host: "podman:web@lab", ok: true, message: "done" }]);
});

test("a week's chat opens only with an id and account folder that are ones; a tip's command is all that's copied", () => {
  const { calls, receive } = setup();
  receive({ type: "openWeekChat", chatId: "../../x", profileDir: ".claude", name: "x" });
  receive({ type: "openWeekChat", chatId: "abc", profileDir: "../.ssh", name: "x" });
  assert.equal(calls.length, 0);
  receive({ type: "openWeekChat", chatId: "c76cd817-da30", profileDir: ".claude-work", name: "Ports", cwd: "/w/app" });
  assert.deepEqual(calls, [{ name: "openWeekChat", args: ["c76cd817-da30", ".claude-work", "Ports", "/w/app"] }]);
  const stub = vscode as unknown as { clipboardWrites: string[] };
  stub.clipboardWrites.length = 0;
  receive({ type: "copy", text: "/compact" });
  receive({ type: "copy", text: "/effort xhigh" });
  receive({ type: "copy", text: "rm -rf ~" });
  receive({ type: "copy", text: "/clear; curl evil" });
  assert.deepEqual(stub.clipboardWrites, ["/compact", "/effort xhigh"]);
});

test("the Recap's card draws the period shown, the projects named only when asked", async () => {
  const { drawCard, CARD_W } = await import("../webview/util/card");
  const { demoWeek } = await import("../src/shared/demo");
  const texts: string[] = [];
  const ctx = new Proxy({} as Record<string | symbol, unknown>, {
    get: (t, k) => (k in t ? t[k] : k === "createLinearGradient" || k === "createRadialGradient" ? () => ({ addColorStop() {} })
      : k === "measureText" ? (s: string) => ({ width: s.length * 14 }) : k === "fillText" ? (s: string) => void texts.push(s) : () => undefined),
    set: (t, k, v) => ((t[k] = v), true),
  });
  const canvas = { width: 0, height: 0, getContext: () => ctx } as unknown as HTMLCanvasElement;
  const recap = demoWeek(Date.now());
  drawCard(canvas, recap, false);
  assert.equal(canvas.width, CARD_W);
  assert.ok(texts.includes("My week with Claude"));
  assert.ok(texts.some((t) => /\d+ projects?$/.test(t)), texts.join(" | "));
  assert.ok(!texts.some((t) => t.includes(recap.projects[0].name)));
  texts.length = 0;
  drawCard(canvas, recap, true);
  assert.ok(texts.some((t) => t.includes(recap.projects[0].name)));
  // Overall: a row per 7 days, newest first; the card draws its last 20 weeks oldest first, so they fit
  const bars: number[][] = [];
  ctx.roundRect = (...a: number[]) => void (ctx.fillStyle === "#d97757" && bars.push(a));
  const weeks = Array.from({ length: 52 }, (_, i) => ({ ...recap.days[0], workedMs: i ? HOUR : 9 * HOUR }));
  drawCard(canvas, { ...recap, span: "all", days: weeks }, false);
  assert.equal(bars.length, 20);
  assert.ok(bars[19][3] > bars[0][3], "the newest week is the last bar");
  assert.ok(bars[19][0] + bars[19][2] - bars[0][0] <= 320 * 2, "within the card's column (drawn at twice its size)");
});

test("the Recap's card is copied from a folder of its own, removed after; a failure is said, not thrown", async () => {
  const fs = await import("node:fs");
  const os = await import("node:os");
  const path = await import("node:path");
  const { Actions } = await import("../src/actions");
  const { recorded } = await import("./vscode-stub");
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "talpy-den-cards-"));
  const saved = process.env.TMPDIR;
  process.env.TMPDIR = tmp; // (os.tmpdir())
  try {
    const name = "claude-week-2026-10-20.png";
    fs.writeFileSync(path.join(tmp, name), "someone else's"); // (another user's card of that day)
    const copied: { file: string; bytes: string }[] = [];
    let answer = { ok: true, message: "Copied" };
    const backend = { copyImage: async (file: string) => (copied.push({ file, bytes: fs.readFileSync(file, "utf8") }), answer) };
    const actions = new Actions(backend as never, {} as never, {} as never, { warn() {} } as never, {} as never);
    const png = Buffer.from("PNG!").toString("base64");
    await actions.shareCard("copy", name, png);
    assert.equal(copied[0].bytes, "PNG!");
    assert.equal(path.basename(copied[0].file), name);
    assert.ok(path.dirname(copied[0].file).startsWith(path.join(tmp, "talpy-den-card-")), copied[0].file);
    assert.equal(fs.existsSync(path.dirname(copied[0].file)), false, "its folder is removed");
    assert.equal(fs.readFileSync(path.join(tmp, name), "utf8"), "someone else's", "another's file is left alone");
    assert.match(recorded.messages.at(-1)!, /The card is copied/);
    answer = { ok: false, message: "To copy pictures, install wl-clipboard (or xclip)" };
    await actions.shareCard("copy", name, png);
    assert.equal(recorded.messages.at(-1), "Talpy Den: couldn't copy the card: To copy pictures, install wl-clipboard (or xclip)");
    assert.equal(fs.existsSync(path.dirname(copied[1].file)), false);
    process.env.TMPDIR = path.join(tmp, "gone"); // (nowhere to write it)
    await actions.shareCard("copy", name, png);
    assert.match(recorded.messages.at(-1)!, /^Talpy Den: couldn't copy the card: ENOENT/);
    assert.equal(copied.length, 2);
  } finally {
    if (saved === undefined) delete process.env.TMPDIR;
    else process.env.TMPDIR = saved;
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test("a day the clock changes on draws its times by its own clock: 18:00 under the 18 over the rows", async () => {
  const { dayMoment, dayPlace } = await import("../src/shared/week");
  const was = process.env.TZ;
  try {
    for (const [tz, y, m, d, hours] of [["Europe/Berlin", 2026, 9, 25, 25], ["Europe/Berlin", 2026, 2, 29, 23], ["America/New_York", 2026, 2, 8, 23], ["UTC", 2026, 9, 25, 24]] as const) {
      process.env.TZ = tz;
      const day = { start: new Date(y, m, d).getTime(), end: new Date(y, m, d + 1).getTime() };
      assert.equal((day.end - day.start) / 3600000, hours, `${tz}: the day's length`);
      for (const h of [6, 12, 18]) {
        const at = new Date(y, m, d, h).getTime();
        assert.equal(dayPlace(day, at), h / 24, `${tz}: ${h}:00`);
        assert.equal(dayMoment(day, h / 24), at, `${tz}: back to ${h}:00`);
      }
      assert.equal(dayPlace(day, day.start), 0);
      assert.equal(dayPlace(day, day.end), 1);
    }
  } finally {
    if (was === undefined) delete process.env.TZ;
    else process.env.TZ = was;
  }
});

test("a model's share, a tip's icon and Overall's row tooltip say it as Plasma's", () => {
  assert.deepEqual([0, 0.004, 0.42, 0.996, 1].map(shareText), ["0%", "<1%", "42%", ">99%", "100%"]);
  assert.deepEqual(["waits", "limits", "clear"].map(tipMeaning), ["tipWaits", "tipLimits", "tip"]);
  const row = { day: "2026-10-19", to: "2026-10-25", start: 0, end: 1, you: [], work: [], wait: [], limits: [], youMs: 0, workedMs: 0,
    busyMs: 0, waitMs: 0, prompts: 1, cost: 0, tokenTotal: 0, chats: [] };
  assert.match(dayTip(row as never), /^19 October – 25 October\n/);
  assert.match(dayTip(row as never), /\n1 prompt · /);
});

test("advanced analyses: how a plan's limits changed, in words", () => {
  assert.equal(limitLabel("five_hour"), "5-hour window");
  assert.equal(limitLabel("seven_day"), "Week");
  assert.equal(limitLabel("seven_day_opus"), "Week · Opus");
  assert.equal(limitLabel("seven_day_something_new"), "seven day something new");
  assert.equal(limitChangeText({ kind: "change", pct: -14 }), "▼ 14% vs the week before");
  assert.equal(limitChangeText({ kind: "change", pct: 8 }), "▲ 8% vs the week before");
  assert.equal(limitChangeText({ kind: "same", pct: 3 }), "about the same as the week before");
  assert.equal(limitChangeText({ kind: "new" }), "new this week");
  const day = new Date(2026, 10, 4, 18, 52).getTime();
  assert.equal(limitChangeText({ kind: "limits", factor: 5, at: day }), "about 5× since 4 Nov");
  assert.equal(limitChangeText({ kind: "limits", factor: 4.71, at: day }), "about 4.7× since 4 Nov");
  assert.equal(limitChangeText({ kind: "limits", factor: 0.2, at: day }), "▼ 80% since 4 Nov");
  assert.equal(limitChangeText({ kind: "limits", factor: 1.04, at: day }), "about the same since 4 Nov");
  assert.equal(limitChangeText({ kind: "limits", factor: null, at: day }), "your plan changed on 4 Nov");
  assert.equal(limitEventText({ at: day, factors: { five_hour: 5, seven_day: 4.71 }, from: "Pro", to: "Max 5×" }),
    `4 Nov ${clockText(day)} · your limits grew about 4.7× · Pro → Max 5×`);
  assert.equal(limitEventText({ at: day, factors: { five_hour: 0.2, seven_day: 0.2 }, from: null, to: "Pro" }),
    `4 Nov ${clockText(day)} · your limits shrank 80% · now Pro`);
  assert.equal(limitEventText({ at: day, factors: {}, from: "Pro", to: "Max 5×" }), `4 Nov ${clockText(day)} · your plan changed · Pro → Max 5×`);
  assert.equal(limitChangeText({ kind: "few" }), "too few readings to compare yet");
  assert.equal(limitChangeText(null), "");
  assert.equal(limitShareText(17.2), "17% of the week · about 6 full windows a week");
  assert.equal(limitShareText(0), "");
  assert.equal(limitMoney(47.6), "$48");
  assert.equal(limitMoney(1180.4), "$1,180");
  assert.equal(limitMoney(4.5), "$4.50");
  assert.equal(limitMoney(47.6, { code: "EUR", rate: 0.9 }), "€43");
  assert.equal(limitFillText({ wallMs: 97 * MIN, workMs: 155 * MIN }), "Full after about 1h 37m at your pace · Claude worked 2h 35m in it, across chats");
  assert.match(limitFillText({ wallMs: 6 * HOUR, workMs: 0 }), /doesn't fill in its 5 hours$/);
  const mix = limitMix({ fresh: 2e6, output: 0.4e6, cacheRead: 112e6 });
  assert.deepEqual(mix.parts.map((p) => p.kind), ["cacheRead", "fresh", "output"]);
  assert.deepEqual(mix.parts.map((p) => p.label), ["cache reads 98%", "new input and cache writes 2%", "output <1%"]);
  assert.equal(mix.text, "114.4M tokens fill a 5-hour window");
  assert.match(limitFootText({ since: NOW }), /since 24 Oct\. Use on claude\.ai/);
});

test("advanced analyses: the demo's accounts, their charts and tokens", () => {
  const { accounts } = demoLimits(NOW);
  const [max, team] = accounts;
  assert.deepEqual(limitKeys(max), ["five_hour", "seven_day", "seven_day_opus"]);
  assert.deepEqual(limitKeys(team), ["five_hour", "seven_day"]);
  assert.equal(team.changes.seven_day?.kind, "same");
  const dots = limitDots(max, NOW);
  assert.ok(dots.dots.length > 10 && dots.dots.every((d) => d.x >= 0 && d.x <= 1 && d.y > 0 && d.y < 1));
  assert.ok(dots.lo > 0 && dots.top > dots.lo);
  assert.deepEqual(limitWeekBars(team, NOW).map((b) => b.cost), [297, 291, 288]);
  // (both accounts on one time line: a week is at the same place in each)
  const start = limitStart(accounts, NOW);
  const [maxBars, teamBars] = [limitWeekBars(max, NOW, start), limitWeekBars(team, NOW, start)];
  assert.equal(maxBars[maxBars.length - 1].x1, teamBars[teamBars.length - 1].x1);
  assert.ok(teamBars[0].x1 > 0 && maxBars[0].x1 === 0);
  assert.equal(start, Math.min(max.periods[0].from, team.periods[0].from));
  assert.equal(limitStart([], NOW), NOW);
  assert.match(limitTokensText(team), /^2\.5M output tokens of Opus 5\.5 \(or 245\.0M cache reads\) fill a 5-hour window; 14\.4M a week, at API prices$/);
  assert.equal(demoLimits(NOW, team.id).accounts.length, 1);
});
