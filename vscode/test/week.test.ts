// The Recap tab: its words and numbers (src/shared/week.ts), and what the
// extension takes from the page's Week messages.

import assert from "node:assert/strict";
import { test } from "node:test";
import * as vscode from "vscode";
import { demoLimits, demoPerms, demoState, demoWeek } from "../src/shared/demo";
import { clockText } from "../src/shared/model";
import type { Session, Status, Stop, WeekDay, WeekLane } from "../src/shared/types";
import {
  tipShareText, tipShareTip, currencyOf, dayTip, deltaText, fillPaths, footText, hoursText, hoverText, moneyText, periodText, planText, promptsText, ruleMeta,
  weekAsked, weekRevokeAsked, weekRuleAsked, weekTiles, RECAP_SECTIONS, windowSpan, workText, grantMeta, grantedIntro, ruleMeaning,
  shareText, tipMeaning, tipSource, guessedCostText, guessedModelTip, modelValue, tokensLabel,
  dateText, periodWaiting, rowDay, shortDay, stepText, weekRows, dayLanes, laneNumbers,
  limitChartText, limitChartTip, limitDots, limitEventText, limitFillText, limitFitText, limitFootText, limitKeys, limitLabel, limitMix, limitMoney,
  limitNoChangeText, limitShareText, limitShareTip, limitShown, limitSizeTip, limitTokensText, limitTokensTip, limitWeekLabel, limitWeekNote,
  limitWeekPct, limitStart, limitValueText, doneText, doneTip, commitsShown, workBeforeText, listedChatRef,
  planUseText, planUseTip, planWeeksShown, weekShareShort, weekShareTip,
  daysBack, laneHoverText, laneTicks, mixLabel, mixTip, mixValue, modelRowText, tipChatAct, tipsShown, tipShareShown, tipWas,
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

test("the days shown, and the week's tiles", () => {
  const recap = demoWeek(NOW);
  assert.equal(periodText(recap), "Last 7 days · 18 Oct – 24 Oct");
  assert.equal(periodText(demoWeek(NOW, 1)), "11 Oct – 17 Oct");
  const tiles = weekTiles(recap);
  assert.deepEqual(tiles.map((t) => t.label), ["You were at it", "Claude worked", "Prompts", "Tokens · 98% cache", "At API prices"]);
  assert.match(tiles[1].tip, /On the clock it worked .*, and it waited 3h 18m for your answers\.\nThe 7 days before: /);
  assert.equal(weekTiles({ ...recap, previous: { youMs: 0, workedMs: 0, busyMs: 0, waitMs: 0, prompts: 0, cost: 0, tokenTotal: 0 } })[0].delta, "");
  // the 30 days before begin before the first chat kept: no change, and the tip says why
  const month = { ...demoWeek(NOW, 0, "", "month"), previous: null, beforeKept: false, first: "2026-10-03" };
  assert.equal(weekTiles(month)[2].delta, "");
  assert.match(weekTiles(month)[2].tip, /\nThe 30 days before can't be compared: the Recap has your chats only since 3 Oct\.\n/);
});

test("the Recap reads as a story: the tiles, when, what got done, then the money", () => {
  assert.deepEqual(weekTiles(demoWeek(NOW)).map((t) => t.label), ["You were at it", "Claude worked", "Prompts", "Tokens · 98% cache", "At API prices"]);
  // (what Claude did is What got done's last line; its projects' chats are the list of chats)
  // (your plan after what got done; its limits over time last, in Overall)
  // (where the usage went, before what could use less of it)
  assert.deepEqual([...RECAP_SECTIONS], ["days", "lanes", "projects", "plan", "usage", "tips", "limits"]);
});

test("where the usage went: each part's share, how it moved, and the tips' as theirs", () => {
  const recap = demoWeek(NOW);
  const mix = recap.usageMix!;
  assert.deepEqual(mix.map((p) => `${mixLabel(p.key)}: ${mixValue(p)}`), [
    "Subagents: 31% of usage · was 24%", "Context over 150k: 41% of usage · was 52%", "Effort xhigh: 71% of usage · was 58%",
    "Effort max: 22% of usage · was 39%", "Effort medium: 7% of usage · was 3%",
  ]);
  assert.equal(mixValue({ key: "effort:", pct: 0.3, before: null }), "<1% of usage"); // (not compared: no "was")
  assert.equal(mixLabel("effort:"), "Effort not noted");
  assert.match(mixTip(mix[0], recap), /^Subagents' requests took 31% of the usage of these days, the main chats' 69%\.\nWeighed as .*\nThe 7 days before: 24%$/);
  assert.match(mixTip({ ...mix[0], before: null }, { ...recap, beforeKept: false, first: "2026-10-20" }), /\nThe 7 days before can't be compared: /);
  assert.equal(modelRowText(recap.models[0]), "$" + Math.round(recap.models[0].cost) + " · 88% · was 91%");
  assert.equal(modelRowText({ ...recap.models[0], before: null }).includes("was"), false);
  // a tip's share, and under it what it was
  assert.equal(tipWas(recap.tips[0]), "was 52%");
  assert.equal(tipWas({ pct: 41, before: null }), "");
  assert.equal(tipWas({ pct: null, before: null }), "");
  // a tip whose share a row above says (context over 150k, effort max) doesn't say it again; the others do
  const shown = recap.tips.filter((t) => tipShareShown(t, mix)).map((t) => t.key);
  assert.deepEqual(shown, ["long_running", "cold"]);
  assert.equal(tipShareShown(recap.tips[0], []), true);
});

test("a tip acts on the chats it names as the chat list would: Stop, Keep going, or only their name", () => {
  const status = demoState(NOW).status!;
  const g = status.groups[0];
  const row = (over: Partial<Session>): Session => ({ ...g.sessions[0], chatId: "c1", sessionId: "c1", kind: "interactive", pid: 7, entrypoint: "cli", stopped: null, ...over });
  const listing = (sessions: Session[], keep: Status["keep"] = []): Status => ({ ...status, groups: [{ ...g, sessions, recent: [], starred: [] }], keep });
  const c = { chatId: "c1", host: "" };
  const act = (key: string, st: Status) => tipChatAct(key, c, st, []).act;
  // a chat that ran long: Stop while it's idle with a process of its own (one at work: from its row)
  assert.equal(act("long_running", listing([row({ state: "idle" })])), "stop");
  assert.equal(act("long_running", listing([row({ state: "working" })])), "");
  assert.equal(act("long_running", listing([row({ state: "idle", pid: null })])), "");
  // a chat a limit stopped: Keep going from the reset; at work: Keep going; one that keeps going says so
  const stopped: Stop = { kind: "limit", window: "five_hour", text: "", at: NOW - MIN, resetsAt: NOW + HOUR, over: false };
  assert.equal(act("limits", listing([row({ state: "idle", stopped })])), "keepAtReset");
  assert.equal(act("limits", listing([row({ state: "working" })])), "keep");
  assert.equal(act("limits", listing([row({ state: "working", entrypoint: "claude-vscode" })])), "");
  const kept = [{ chat: "c1", profile: ".claude", name: "c1", since: NOW, wentOnAt: null, tries: 0, note: "", error: "" }];
  assert.equal(act("limits", listing([], kept)), "kept");
  // not listed (an older chat): its name only; the context tip: its name only
  assert.equal(act("limits", listing([])), "");
  assert.equal(act("long_context", listing([row({ state: "idle" })])), "");
  assert.equal(tipChatAct("long_running", c, listing([row({ state: "idle" })]), []).ref?.key, g.sessions[0].key);
  // the limits tip, once every chat it names keeps going, isn't shown
  const limits = { key: "limits", pct: null, title: "", detail: "", command: "", chats: [{ ...c, name: "", profileDir: "", folder: "", cwd: "", note: "" }], more: 0 };
  assert.equal(tipsShown([limits], listing([], kept)).length, 0);
  assert.equal(tipsShown([limits], listing([])).length, 1);
  assert.equal(tipsShown([{ ...limits, more: 2 }], listing([], kept)).length, 1); // (chats it doesn't name may not)
});

test("the Day, chat by chat: its hours on the axis, and what went on where the mouse points", () => {
  const at = (h: number, m = 0) => new Date(2026, 9, 24, h, m).getTime();
  assert.deepEqual(laneTicks(at(9, 56), at(12, 55)), [at(10), at(11), at(12)]);
  assert.deepEqual(laneTicks(at(7, 10), at(22, 40)), [at(9), at(12), at(15), at(18), at(21)]); // (every 3 hours: at most 6)
  assert.deepEqual(laneTicks(at(10, 5), at(10, 50)), []); // (no whole hour in between: its first and last times)
  const lanes: WeekLane[] = [
    { key: "|a", id: "a", host: "", name: "Fix the parser", project: "app", parts: [[at(10), at(11), "w"], [at(11), at(11, 30), "y"]], workedMs: 0, waitedMs: 0 },
    { key: "|b", id: "b", host: "", name: "Release notes", project: "app", parts: [[at(10, 30), at(12), "w"]], workedMs: 0, waitedMs: 0 },
  ];
  const day = { you: [[at(10, 40), at(10, 50)]] as [number, number][], limits: [at(11, 45)] };
  assert.equal(laneHoverText(lanes, day, at(10, 45), 60000), `${clockText(at(10, 45))}: Claude worked in Fix the parser, Release notes · you were at it`);
  assert.equal(laneHoverText(lanes, day, at(11, 15), 60000), `${clockText(at(11, 15))}: Claude worked in Release notes · waited for you in Fix the parser`);
  assert.match(laneHoverText(lanes, day, at(11, 46), 60000), /: a usage limit stopped a chat at .* · Claude worked in Release notes$/);
  assert.equal(laneHoverText(lanes, day, at(12, 30), 60000), `${clockText(at(12, 30))}: nothing went on`);
  // a day of the Week's, opened alone: how many days back it is
  assert.equal(daysBack("2026-10-24", NOW), 0);
  assert.equal(daysBack("2026-10-18", NOW), 6);
});

test("your plan: what these days meant for each account's plan, and the shares of its week", () => {
  const recap = demoWeek(NOW);
  const [personal, work] = recap.planUse!;
  assert.equal(planUseText(work, recap),
    "66% of the week used in these days · 23% of the Opus week · 3 full 5-hour windows · ran out 2 times, chats stood stopped 4h 10m in all");
  assert.equal(planUseText(personal, recap), "41% of the week used in these days · no full 5-hour window · didn't run out");
  assert.equal(planUseText({ ...work, ranOut: 1, heldMs: 0, fiveFull: 1 }, { span: "day", back: 0 }),
    "66% of the week used today · 23% of the Opus week · 1 full 5-hour window · ran out once");
  // the readings kept begin after these days began: from then; an account with none here (an SSH host's)
  assert.match(planUseText({ ...work, covered: false, since: new Date(2026, 10, 3, 10).getTime() }, recap), /^66% of the week used since 3 Nov · /);
  const host = { ...work, name: "lab", readings: false, since: null, weeks: {}, fiveFull: 0, fiveUsed: 0 };
  assert.equal(planUseText(host, recap), "Ran out 2 times, chats stood stopped 4h 10m in all · no readings of its plan here");
  // a limit that held a chat for days says days
  assert.match(planUseText({ ...host, heldMs: 10.2 * 86400000 }, recap), /chats stood stopped 10 days in all/);
  // several weeks (Month, Overall): each week on its own, never added up
  const month = demoWeek(NOW, 0, "", "month");
  const [, workMonth] = month.planUse!;
  assert.equal(planWeeksShown(workMonth, month), true);
  assert.match(planUseText(workMonth, month), /^Weeks: 22% · 100% · 64% · 100% · 30% so far · 12 full 5-hour windows · /);
  assert.match(planUseTip(workMonth, month), /^How much of each of your plan's weeks these days used, .*: 22%, .*: 100%, .*: 30% so far\. /);
  // a week's days that add up to over a week (two windows): each on its own too
  assert.equal(planWeeksShown({ weeks: { seven_day: 130 }, weekly: [{ from: 0, until: 1, pct: 60, full: 60, now: false }, { from: 1, until: 2, pct: 70, full: 70, now: true }] }, recap), true);
  assert.equal(planWeeksShown(work, recap), false);
  assert.match(planUseTip(host), /lab's has none here/);
  assert.match(planUseTip(work), /^How much of your plan's week these days used: .*\n3 of the 12 5-hour windows .*\nYour plan ran out 2 times \(5 chats stopped\)\./);
  // a project's share on its row, and in its tooltip how it's worked out (two accounts with readings: whose week)
  const [webapp] = recap.projects;
  assert.equal(weekShareShort(webapp), "≈ 44%");
  assert.equal(weekShareShort({ weekShare: [{ account: "a", pct: 0.3 }] }), "<1%");
  assert.equal(weekShareShort({}), "");
  assert.match(weekShareTip(webapp, recap), /^≈ 44% of work's week\nAn estimate: its part of these days' amount at API prices/);
  assert.match(weekShareTip(recap.days[1], recap, true), /^11% of work's week\n6% of personal's week\nAs the readings of your plan's week rose then\.$/);
  // one account with readings: your week; one of its accounts with none, or whose readings begin later: why it's missing
  const one = { ...recap, planUse: [work, { ...personal, readings: false }] };
  assert.equal(weekShareTip({ weekShare: [{ account: work.account, pct: 12 }], accounts: [work.account, personal.account] }, one),
    "≈ 12% of your week\nAn estimate: its part of these days' amount at API prices, times how much of the week these days used (Your plan).\n" +
    "Its share of personal's week isn't known: no readings of that plan on this computer.");
  assert.match(weekShareTip({ weekShare: [], accounts: [work.account] }, { ...recap, planUse: [{ ...work, covered: false, since: new Date(2026, 10, 3).getTime() }] }),
    /^Its share of work's week isn't known: the readings of it kept begin on 3 Nov\.$/);
  assert.match(dayTip(recap.days[1], currencyOf(recap), recap), /\n11% of work's week\n/);
});

test("what got done: a project's and a chat's commits and files, what Claude did the period before", () => {
  const recap = demoWeek(NOW);
  const [webapp] = recap.projects;
  assert.equal(doneText(webapp), "14 commits · 212 files");
  assert.equal(doneText({ commitCount: 1, files: 1 }), "1 commit · 1 file");
  assert.equal(doneText({ files: 1204 }), "1,204 files");
  assert.equal(doneText({}), ""); // (none, or an older week.py's)
  assert.equal(doneTip(webapp), "14 commits · Claude's edits changed 212 files (+4,810 −1,190)");
  const signIn = webapp.chats[1];
  assert.deepEqual(commitsShown(signIn), { shown: signIn.commits!.slice(0, 3), more: 9 });
  assert.deepEqual(commitsShown({ commits: [["", "One"]], commitCount: 1 }), { shown: [["", "One"]], more: 0 });
  assert.equal(workBeforeText(recap), "The 7 days before: 2,410 tool calls · 1,102 commands run · 512 edits in 98 files (+6,120 −1,630) · 12 subagents started · 4 web searches · 3 pages fetched · 2 compactions");
  assert.match(workBeforeText({ ...recap, sameTime: true }), /^The 7 days before, by this time: 2,410 tool calls/);
  assert.equal(workBeforeText({ ...recap, workBefore: null, beforeKept: false, first: "2026-10-20" }),
    "The 7 days before can't be compared: the Recap has your chats only since 20 Oct.");
  assert.equal(workBeforeText({ ...recap, span: "all", workBefore: null }), "");
});

test("a Recap chat opens its tab as the chat list has it: its row, or a recent one", () => {
  const state = demoState(NOW);
  const g = state.status!.groups[0];
  const recent = g.recent[0];
  assert.equal(listedChatRef(state.status, state.hosts, recent.sessionId)?.key, recent.key);
  const row = g.sessions[0];
  assert.equal(listedChatRef(state.status, state.hosts, row.chatId || row.sessionId)?.state, row.state);
  assert.equal(listedChatRef(state.status, state.hosts, "no-such-chat"), null);
});

test("the tokens used: a tile with its change and trend, and a row's tokens", () => {
  assert.equal(deltaText(226_300_000, 400_000_000, "tokens"), "−173.7M");
  assert.equal(deltaText(1_500, 0, "tokens"), "+1.5k");
  assert.equal(deltaText(1_000_020, 1_000_000, "tokens"), "same as before");
  const recap = demoWeek(NOW);
  const tile = weekTiles(recap)[3];
  assert.equal(tile.label, "Tokens · 98% cache"); // (612.0M of 626.3M: cache reads)
  assert.equal(tokensLabel({ tokenTotal: 1000, tokens: { ...recap.sum.tokens, cacheRead: 0 } }), "Tokens");
  assert.equal(tokensLabel({ tokenTotal: 1000, tokens: { ...recap.sum.tokens, cacheRead: 999 } }), "Tokens · >99% cache");
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

test("a model priced by a guess is marked, and the amount says how much rests on it", () => {
  const recap = demoWeek(NOW);
  const fable = recap.models.find((m) => m.guessed)!;
  assert.match(modelValue(fable), /^≈ \$\d/);
  assert.match(modelValue(recap.models[0]), /^\$\d/);
  assert.equal(guessedModelTip(fable), "Fable 5.3 has no list price yet: it's priced as Fable 5.2, the newest model of its family, so its amount is a guess.");
  assert.match(weekTiles(recap)[4].tip, /\n\$\d+(\.\d\d)? of it \(5%\) is priced by a guess: Fable 5\.3 has no list price yet/);
  assert.equal(guessedCostText({ ...recap, prices: { asOf: "2026-11-18", guessed: [] } }), "");
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
  // today isn't over: the days before are counted up to this time of day, and say so
  const soFar = weekTiles({ ...recap, sameTime: true })[1].tip;
  assert.match(soFar, /\nThe 7 days before, by this time: .*\nWeek by week, each by this time, these 7 days last: /);
  assert.deepEqual(weekTiles(demoWeek(NOW, 3))[0].trend.slice(0, 2), [null, null]);
  assert.match(weekTiles(demoWeek(NOW, 3))[0].tip, /these 7 days last: \? · \? · /);
  assert.equal(workText(recap.work), "3,184 tool calls · 1,410 commands run · 699 edits in 143 files (+9,412 −2,210) · 21 subagents started · 6 web searches · 9 pages fetched · 3 compactions");
  assert.equal(workText({ ...recap.work, toolCalls: 1, commands: 1, edits: 1, files: 1, subagents: 0, webSearches: 0, webFetches: 0, compactions: 0 }),
    "1 tool call · 1 command run · 1 edit in 1 file (+9,412 −2,210)");
  // coming back after the cache expired is a tip: its share is of the amount, its tooltip says how much
  const cold = recap.tips.find((t) => t.key === "cold")!;
  assert.deepEqual([tipShareText(cold), tipShareText(recap.tips[0])], ["11% of the amount", "41% of usage"]);
  assert.match(tipShareTip(cold, recap), /^11% of the amount at API prices: writing the chats' context again cost \$37\.\d\d more than reading it/);
  assert.equal(tipSource("cold").split(":")[0], "From Talpy Den");
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
  // a row of 7 days says them; a short one fewer
  assert.deepEqual([rowDay("2026-10-23", true, "2026-10-29"), rowDay("2026-10-30", true, "2026-11-05"), rowDay("2026-10-07", true, "2026-10-08")],
    ["23–29 Oct", "30 Oct – 5 Nov", "7–8 Oct"]);
  assert.equal(weekTiles(all)[0].delta, "");
});

// The Day with chats: one timeline, the chats' numbers at their lanes' ends
test("the Day's lanes: the day's own row on top, each chat's time and cost at its end", () => {
  const day = demoWeek(NOW, 0, "", "day");
  assert.ok(dayLanes(day));
  assert.ok(!dayLanes(demoWeek(NOW)) && !dayLanes({ span: "day", lanes: [] }));
  assert.deepEqual([laneNumbers({ claudeMs: 27_180_000, cost: 258.2 }), laneNumbers({ claudeMs: 20_000, cost: 0.05 }), laneNumbers({ claudeMs: 30_000, cost: 0 }), laneNumbers({})],
    ["7h 33m · $258", "<1m · $0.05", "–", "–"]);
  assert.match(laneNumbers(day.lanes![0]), /^\d+h \d+m · \$\d/);
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
  // (an icon says where its tip comes from)
  assert.deepEqual(["waits", "limits", "clear"].map((k) => tipSource(k).split(":")[0]), ["From Talpy Den", "From Talpy Den", "From Claude Code's /usage"]);
  const row = { day: "2026-10-19", to: "2026-10-25", start: 0, end: 1, you: [], work: [], wait: [], limits: [], youMs: 0, workedMs: 0,
    busyMs: 0, waitMs: 0, prompts: 1, cost: 0, tokenTotal: 0, chats: [] };
  assert.match(dayTip(row as never), /^19 October – 25 October\n/);
  assert.match(dayTip(row as never), /\n1 prompt · /);
});

test("your plan's limits over time, in words", () => {
  assert.equal(limitLabel("five_hour"), "5-hour window");
  assert.equal(limitLabel("seven_day"), "Week");
  assert.equal(limitLabel("seven_day_opus"), "Opus week");
  assert.equal(limitLabel("seven_day_something_new"), "seven day something new");
  // one estimate, "≈" as every estimate; from too few windows or ones far apart: the range it rests on and how many
  assert.deepEqual(limitValueText("five_hour", { cost: 180, n: 11, lo: 172, hi: 184 }), { text: "≈ $180", rough: false });
  assert.deepEqual(limitValueText("five_hour", { cost: 120, n: 5, lo: 31, hi: 190, rough: true }), { text: "$31–$190 · 5 windows", rough: true });
  assert.deepEqual(limitValueText("five_hour", { cost: 66, n: 1, lo: 66, hi: 66, rough: true }), { text: "$66 · 1 window", rough: true });
  assert.deepEqual(limitValueText("seven_day", { cost: 700, lo: 520, hi: 990, rough: true }), { text: "$520–$990", rough: true });
  assert.deepEqual(limitValueText("five_hour", { cost: 210, n: 4, lo: 200, hi: 225, scaled: 5 }), { text: "≈ $210", rough: false });
  // a full 5-hour window's share of the week: from the readings, or from the sizes, and the section says which
  assert.equal(limitShareText({ pct: 17.6, how: "readings", n: 9 }), "A full 5-hour window moves the week 18%: 6 of them fill it · from the readings");
  assert.equal(limitShareText({ pct: 22.1, how: "sizes", rough: true }), "A full 5-hour window is ≈ 22% of the week: 5 of them fill it · from the sizes");
  assert.equal(limitShareText({ pct: 0, how: "sizes" }), "");
  assert.match(limitShareTip({ pct: 17.6, how: "readings", n: 9 }), /^From the readings themselves: .* of 9 windows\. No prices/);
  const day = new Date(2026, 2, 12, 9, 40).getTime();
  assert.equal(limitEventText({ at: day, factors: { five_hour: 5, seven_day: 4.71 }, from: "Pro", to: "Max 5×" }),
    `12 Mar ${clockText(day)} · your limits grew about 4.7× · Pro → Max 5×`);
  assert.equal(limitEventText({ at: day, factors: { five_hour: 0.2, seven_day: 0.2 }, from: null, to: "Pro" }),
    `12 Mar ${clockText(day)} · your limits shrank 80% · now Pro`);
  assert.equal(limitEventText({ at: day, factors: {}, from: "Pro", to: "Max 5×" }), `12 Mar ${clockText(day)} · your plan changed · Pro → Max 5×`);
  // with none since the first reading or the last change, one line says so
  assert.equal(limitNoChangeText({ events: [{ at: day, factors: {}, from: "Pro", to: "Max 5×" }], since: day - 9 * 86400000 }, NOW), "No change seen since 12 Mar.");
  assert.equal(limitNoChangeText({ events: [], since: day }, NOW), "No change seen since 12 Mar, when the readings begin.");
  assert.equal(limitMoney(47.6), "$48");
  assert.equal(limitMoney(1180.4), "$1,180");
  assert.equal(limitMoney(4.5), "$4.50");
  assert.equal(limitMoney(47.6, { code: "EUR", rate: 0.9 }), "€43");
  assert.equal(limitFillText({ wallMs: 97 * MIN, workMs: 155 * MIN }), "A 5-hour window fills in ≈ 1h 37m at your pace · Claude worked 2h 35m in it, across chats");
  assert.match(limitFillText({ wallMs: 6 * HOUR, workMs: 0 }), /doesn't fill in its 5 hours$/);
  // what fills a window: shares of its API price (by count, cache reads would be 98% of it)
  const mix = limitMix({ fresh: 13, output: 8, cacheRead: 22.4 });
  assert.deepEqual(mix.parts.map((p) => p.label), ["cache reads 52%", "new input and cache writes 30%", "output 18%"]);
  assert.deepEqual(limitMix(null).parts, []); // (an older week.py: no bar)
  // what it can't see, the SSH hosts the Recap reads by name
  assert.match(limitFootText({ since: NOW }), /since 24 Oct\. Use on claude\.ai, your phone, other computers or SSH hosts counts/);
  assert.match(limitFootText({ since: NOW }, ["build-server"]), /\. Use on build-server \(SSH hosts\), claude\.ai, your phone or other computers counts/);
  // how full a week got: its days, its percent, when it ran out and its 5-hour windows
  const w = { from: new Date(2026, 9, 10, 22).getTime(), until: new Date(2026, 9, 17, 22).getTime(), pct: 100,
    ranOutAt: new Date(2026, 9, 15, 14, 20).getTime(), fiveFull: 4, fiveUsed: 15, now: false };
  assert.equal(limitWeekLabel(w), "10–17 Oct");
  assert.equal(limitWeekLabel({ from: new Date(2026, 1, 24).getTime(), until: new Date(2026, 2, 3).getTime() }), "24 Feb – 3 Mar");
  assert.equal(limitWeekPct(w), "100%");
  assert.equal(limitWeekPct({ ...w, pct: 41.4, ranOutAt: null, now: true }), "41% so far");
  assert.equal(limitWeekNote(w), `Ran out Thu ${clockText(w.ranOutAt)} · 4 of 15 5-hour windows full`);
  assert.equal(limitWeekNote({ ...w, ranOutAt: null, fiveUsed: 0 }), "");
  assert.equal(limitFitText({ weeks: [w, { ...w, pct: 64, ranOutAt: null }] }), "Ran out in 1 of 2 weeks · 8 of 30 5-hour windows ran full");
  assert.equal(limitFitText({ weeks: [{ ...w, pct: 64, ranOutAt: null, fiveUsed: 0 }] }), "No week ran out; the fullest got to 64%");
  // a week the weekly limit began during: counted from then, not one that could have run out unless it did
  const late = { ...w, pct: 38, ranOutAt: null, fiveFull: 13, fiveUsed: 14, countedFrom: new Date(2026, 9, 16, 10).getTime() };
  assert.equal(limitWeekNote(late), "Counted from Fri 16 Oct · 13 of 14 5-hour windows full");
  assert.equal(limitFitText({ weeks: [late, w] }), "Ran out in 1 of 1 week · 17 of 29 5-hour windows ran full");
  assert.equal(limitFitText({ weeks: [late, { ...w, pct: 64, ranOutAt: null }] }), "No week ran out; the fullest got to 64% · 17 of 29 5-hour windows ran full");
  assert.equal(limitFitText({ weeks: [{ ...late, pct: 100, ranOutAt: w.ranOutAt }, w] }), "Ran out in 2 of 2 weeks · 17 of 29 5-hour windows ran full");
});

test("your plan's limits over time: the demo's accounts, one estimate everywhere, the chart", () => {
  const { accounts } = demoLimits(NOW);
  const [max, team] = accounts;
  assert.deepEqual(limitKeys(max), ["five_hour", "seven_day", "seven_day_opus"]);
  assert.deepEqual(limitKeys(team), ["five_hour", "seven_day"]);
  assert.match(limitFitText(max), /^Ran out in 2 of 6 weeks · \d+ of \d+ 5-hour windows ran full$/);
  // the week from the 5-hour window and its share of the week (from the readings): they agree
  const five = max.now.fiveHour!, seven = max.now.weeks.seven_day!;
  assert.equal(seven.how, "share");
  assert.ok(Math.abs(seven.cost - (five.cost * 100) / max.now.share!.pct) <= 1);
  assert.match(limitSizeTip("seven_day", max), /^A full 5-hour window over its share of the week \(from the readings\): 5\.7 full 5-hour windows\.$/);
  assert.match(limitSizeTip("five_hour", max), /upper end of the \d+ windows measured since your limits last changed/);
  // (the Team account's windows far apart: a range, and so is the share from the sizes)
  assert.deepEqual([limitValueText("five_hour", team.now.fiveHour).rough, team.now.share?.how], [true, "sizes"]);
  // the chart: each stretch of the same limits on its own scale, the older dimmed, its label the newest's range
  const dots = limitDots(max, NOW);
  assert.ok(dots.dots.length > 10 && dots.dots.every((d) => d.x >= 0 && d.x <= 1 && d.y > 0 && d.y <= 1));
  assert.ok(dots.dots.some((d) => d.dim) && dots.dots.some((d) => !d.dim));
  assert.deepEqual(dots.lines.map((l) => l.dim), [true, false]);
  assert.equal(dots.lines[0].y, dots.lines[1].y); // (each estimate at the same height: its own scale)
  const mine = max.windows.filter((w) => w.era === 1).map((w) => w.full);
  assert.deepEqual([dots.lo, dots.hi, dots.estimate], [Math.min(...mine), Math.max(...mine), five.cost]);
  assert.match(limitChartText(max, dots), /^Each 5-hour window since \d+ \w+: \$\d+–\$\d+ · its line ≈ \$\d+$/);
  assert.match(limitChartTip(dots), /Before your limits changed \(dimmed\), each stretch is drawn on its own scale: until \d+ \w+, ≈ \$\d+\./);
  // (both accounts on one time line: a day is at the same place in each)
  assert.equal(limitStart(accounts, NOW), Math.min(max.eras![0].from, team.eras![0].from));
  assert.equal(limitStart([], NOW), NOW);
  // one token figure, in your own mix; the one model's equivalence in its tooltip
  assert.match(limitTokensText(max), /^≈ [\d.]+M tokens fill a 5-hour window, in your mix$/);
  assert.match(limitTokensTip(max), /\nIn Opus 5\.5 output tokens alone: ≈ [\d.]+M a 5-hour window \(or ≈ [\d.]+M cache reads\); ≈ [\d.]+M a week\.$/);
  assert.equal(limitShown({ ok: true, generatedAt: NOW, since: null, accounts }).length, 2);
  assert.equal(demoLimits(NOW, team.id).accounts.length, 1);
});
