// The Recap tab's words and numbers (webview/components/WeekView.tsx), from
// the recap of the widget's week.py; here, so the tests can read them.

import { chatRefOf, clockText, dayLabel, hostLabel, plural, recentRef } from "./model";
import type {
  ChatRef, HostState, LimitAccount, LimitChange, LimitEvent, LimitHistory, LimitPeriod, LimitTokens, Status, WeekDay, WeekGrant, WeekModel, WeekNumbers,
  WeekPlanUse, WeekPlanWindow, WeekRecap, WeekRule, WeekShare, WeekSpan, WeekSum, WeekTip,
} from "./types";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const WEEKDAYS_LONG = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MONTHS_LONG = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
  "November", "December"];

// A local YYYY-MM-DD as a Date at local midnight
function localDate(day: string): Date {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(y, (m || 1) - 1, d || 1);
}

// 3h 5m, 45m: a week of work reads better in hours than in days
export function hoursText(ms: number): string {
  const m = Math.round(Math.max(0, ms) / 60000);
  return m < 60 ? `${m}m` : `${Math.floor(m / 60)}h ${m % 60}m`;
}

// The amounts are API prices in US dollars; in another currency (the
// talpyDen.recapCurrency setting) week.py sends the European Central
// Bank's rate of the day
export interface Currency {
  code: string;
  rate: number; // per US dollar
}

const USD: Currency = { code: "USD", rate: 1 };
const SYMBOLS: Record<string, string> = {
  USD: "$", EUR: "€", GBP: "£", JPY: "¥", CNY: "¥", INR: "₹", KRW: "₩", ILS: "₪", TRY: "₺", PHP: "₱", THB: "฿",
};
const WHOLE_UNITS = ["JPY", "KRW", "HUF", "ISK", "IDR"];

export function currencyOf(recap: Pick<WeekRecap, "currency">): Currency {
  const c = recap.currency;
  return c && !c.error && c.rate > 0 && /^[A-Z]{3}$/.test(c.code) ? c : USD;
}

export function moneyText(usd: number, cur: Currency = USD): string {
  const amount = (usd || 0) * cur.rate;
  const symbol = SYMBOLS[cur.code];
  const put = (text: string) => (symbol ? symbol + text : `${text} ${cur.code}`);
  if (!amount) return put("0");
  const whole = amount >= 100 || WHOLE_UNITS.includes(cur.code);
  if (amount < (whole ? 1 : 0.01)) return "<" + put(whole ? "1" : "0.01");
  const digits = whole ? 0 : 2;
  return put(amount.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits }));
}

// Where a moment is on its day's row, 0 to 1, by that day's own wall clock:
// on a day the clock changes (23 or 25 hours long) 18:00 is still at 3/4,
// under the 18 over the rows (the repeated hour drawn twice in one place, the
// skipped one empty)
export function dayPlace(d: Pick<WeekDay, "start" | "end">, ms: number): number {
  if (ms <= d.start) return 0;
  if (ms >= d.end) return 1;
  const t = new Date(ms);
  const s = new Date(d.start);
  const days = Math.round((Date.UTC(t.getFullYear(), t.getMonth(), t.getDate()) - Date.UTC(s.getFullYear(), s.getMonth(), s.getDate())) / 86400000);
  const hours = days * 24 + t.getHours() + t.getMinutes() / 60 + t.getSeconds() / 3600 + t.getMilliseconds() / 3600000;
  return Math.max(0, Math.min(1, hours / 24));
}

// The moment at a place on its day's row (dayPlace back)
export function dayMoment(d: Pick<WeekDay, "start" | "end">, place: number): number {
  const s = new Date(d.start);
  const ms = new Date(s.getFullYear(), s.getMonth(), s.getDate(), 0, 0, 0, Math.round(place * 24 * 3600000)).getTime();
  return Math.max(d.start, Math.min(d.end, ms));
}

// "24 Oct"
export function shortDay(day: string): string {
  const d = localDate(day);
  return `${d.getDate()} ${MONTHS[d.getMonth()]}`;
}

// "19 October"
function monthDay(day: string): string {
  const d = localDate(day);
  return `${d.getDate()} ${MONTHS_LONG[d.getMonth()]}`;
}

export function longDay(day: string): string {
  const d = localDate(day);
  return `${WEEKDAYS_LONG[d.getDay()]} ${d.getDate()} ${MONTHS_LONG[d.getMonth()]}`;
}

// "24 Oct 2026" (the widget's "d MMM yyyy")
export function dateText(day: string): string {
  const d = localDate(day);
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}

// "Sat 24": a timeline row's day ("19 Oct": a month's or Overall's 7 days)
export function rowDay(day: string, weeks = false, to = ""): string {
  if (!weeks) return dayLabel(day).split(" ").slice(0, 2).join(" ");
  return !to || to === day ? shortDay(day) : rangeText(day, to);
}

// "23–29 Oct", "30 Oct – 5 Nov": a row of 7 days (a month's oldest row and
// everything's fewer: "7–8 Oct")
export function rangeText(from: string, to: string): string {
  const a = localDate(from), b = localDate(to);
  return a.getMonth() === b.getMonth() ? `${a.getDate()}–${shortDay(to)}` : `${shortDay(from)} – ${shortDay(to)}`;
}

// "Wed 14:05": when a turn started
export function whenText(ms: number): string {
  return `${WEEKDAYS[new Date(ms).getDay()]} ${clockText(ms)}`;
}

export function periodText(recap: WeekRecap): string {
  if (recap.span === "day") {
    const day = rowDay(recap.from) + " " + shortDay(recap.from).split(" ")[1];
    return recap.back === 0 ? `Today · ${day}` : recap.back === 1 ? `Yesterday · ${day}` : day;
  }
  if (recap.span === "all") return recap.first ? `Everything since ${dateText(recap.first)}` : "Everything";
  const span = `${shortDay(recap.from)} – ${shortDay(recap.to)}`;
  return recap.back === 0 ? `${recap.span === "month" ? "Last 30 days" : "Last 7 days"} · ${span}` : span;
}

// What the period line says before the answer for a span comes
export function periodWaiting(span: WeekSpan, back: number): string {
  return back !== 0 ? "" : span === "day" ? "Today" : span === "all" ? "Everything" : span === "month" ? "Last 30 days" : "Last 7 days";
}

// The step back and on: "The day before", "The 30 days after", …
export function stepText(span: WeekSpan, after: boolean): string {
  const what = span === "day" ? "day" : span === "month" ? "30 days" : "week";
  return `The ${what} ${after ? "after" : "before"}`;
}

// The day, 7 or 30 days before, when there was anything in them
export function previousOf(recap: WeekRecap): WeekNumbers | null {
  const p = recap.previous;
  return p && (p.workedMs || p.prompts || p.cost) ? p : null;
}

// The change against the days before: "+4h 44m", "−$12"
export function deltaText(now: number, before: number | null, kind: Kind, cur: Currency = USD): string {
  if (before === null) return "";
  const d = now - before;
  const abs = Math.abs(d);
  if (kind === "time" ? abs < 60000 : kind === "money" ? abs < 0.01 : kind === "tokens" ? abs < 50 : d === 0) return "same as before";
  return (d > 0 ? "+" : "−") + amountText(abs, kind, cur);
}

type NumberKey = "youMs" | "workedMs" | "cost" | "tokenTotal" | "prompts";
type Kind = "time" | "money" | "tokens" | "count";

// A number of the tiles, in its own unit
function amountText(v: number, kind: Kind, cur: Currency): string {
  return kind === "time" ? hoursText(v) : kind === "money" ? moneyText(v, cur) : kind === "tokens" ? shortCount(v) : count(v);
}

// The Recap's sections under its tiles, top to bottom (the same in every
// front end): when (the day-by-day graph, chat by chat); what got done (by
// project, its chats with their commits and Claude's recaps, what Claude
// did in all under it); what it meant for your plan (and today, its windows
// now); then the money (by model at API prices, what could use less of
// your plan). Last, in Overall only: your plan's limits over time.
export const RECAP_SECTIONS = ["days", "lanes", "projects", "plan", "models", "tips", "limits"] as const;

// Spans whose timeline has a row per 7 days, not per day
export function weekRows(span: WeekSpan | undefined): boolean {
  return span === "month" || span === "all";
}
export type RecapSection = (typeof RECAP_SECTIONS)[number];

export interface WeekTile {
  label: string;
  value: string;
  delta: string;
  tip: string;
  trend: (number | null)[]; // the 5 weeks up to these days, these last (null: older than what's kept)
}

// One number over the weeks up to these days
export function trendOf(recap: WeekRecap, key: NumberKey): (number | null)[] {
  return (recap.trend ?? []).map((w) => (w ? w[key] ?? 0 : null));
}

export function weekTiles(recap: WeekRecap): WeekTile[] {
  const s = recap.sum;
  const p = previousOf(recap);
  const cur = currencyOf(recap);
  const shown = (v: number, kind: Kind) => amountText(v, kind, cur);
  const [beforeText, trendText] = recap.span === "day" ? ["The day before", "Day by day, this day last"]
    : recap.span === "month" ? ["The 30 days before", "30 days at a time, these 30 days last"]
      : ["The 7 days before", "Week by week, these 7 days last"];
  // (today isn't over: the days before are counted up to this time of day)
  const by = recap.sameTime ? ", by this time" : "";
  const trendSaid = recap.sameTime ? trendText.replace(/^([^,]+),/, "$1, each by this time,") : trendText;
  const before = (v: number, kind: Kind) => (p ? `\n${beforeText}${by}: ${shown(v, kind)}` : uncomparedText(recap));
  const weeks = (key: NumberKey, kind: Kind) => {
    const values = trendOf(recap, key);
    return values.length > 1
      ? `\n${trendSaid}: ${values.map((v) => (v === null ? "?" : shown(v, kind))).join(" · ")}`
      : "";
  };
  return [
    {
      label: "You were at it",
      value: hoursText(s.youMs),
      delta: deltaText(s.youMs, p ? p.youMs : null, "time"),
      tip:
        "The time you spent writing to Claude, reading its replies and answering its questions, in all your chats and " +
        "accounts: the time between your prompts and its replies counts when it's under 15 minutes." + before(p ? p.youMs : 0, "time") +
        weeks("youMs", "time"),
      trend: trendOf(recap, "youMs"),
    },
    {
      label: "Claude worked",
      value: hoursText(s.workedMs),
      delta: deltaText(s.workedMs, p ? p.workedMs : null, "time"),
      tip:
        "Claude's own count of its turns (its “Worked for …”), all chats added up: chats working at the same time each " +
        `count. On the clock it worked ${hoursText(s.busyMs)}, and it waited ${hoursText(s.waitMs)} for your answers.` +
        before(p ? p.workedMs : 0, "time") + weeks("workedMs", "time"),
      trend: trendOf(recap, "workedMs"),
    },
    {
      label: "Prompts",
      value: count(s.prompts),
      delta: deltaText(s.prompts, p ? p.prompts : null, "count"),
      tip: `${plural(s.chats, "In %1 chat", "In %1 chats")} · ${plural(s.turns, "%1 turn of Claude's", "%1 turns of Claude's")}` +
        before(p ? p.prompts : 0, "count") + weeks("prompts", "count"),
      trend: trendOf(recap, "prompts"),
    },
    {
      label: tokensLabel(s),
      value: shortCount(s.tokenTotal),
      delta: deltaText(s.tokenTotal, p ? p.tokenTotal : null, "tokens"),
      tip: tokensText(s.tokens) + before(p ? p.tokenTotal : 0, "tokens") + weeks("tokenTotal", "tokens"),
      trend: trendOf(recap, "tokenTotal"),
    },
    {
      label: "At API prices",
      value: moneyText(s.cost, cur),
      delta: deltaText(s.cost, p ? p.cost : null, "money", cur),
      tip:
        `What the same tokens would cost on Claude's API, at its list prices of ${dateText(recap.prices.asOf)}. ` +
        "Your plan isn't billed this way: this is the value of what you used." + guessedCostText(recap) + before(p ? p.cost : 0, "money") +
        weeks("cost", "money"),
      trend: trendOf(recap, "cost"),
    },
  ];
}

// The period before begins before the first chat the Recap has: not known
// whole, so not compared (week.py: beforeKept)
export function uncomparedText(recap: Pick<WeekRecap, "span" | "beforeKept" | "first">): string {
  if (recap.beforeKept !== false || !recap.first || recap.span === "all") return "";
  const what = recap.span === "day" ? "The day before" : recap.span === "month" ? "The 30 days before" : "The 7 days before";
  return `\n${what} can't be compared: the Recap has your chats only since ${shortDay(recap.first)}.`;
}

// The Tokens tile's label: how much of them were cache reads, on the tile
// itself ("Tokens · 98% cache"), the whole split in its tooltip
export function tokensLabel(s: Pick<WeekSum, "tokens" | "tokenTotal">): string {
  return s.tokens.cacheRead > 0 && s.tokenTotal > 0 ? `Tokens · ${shareText(s.tokens.cacheRead / s.tokenTotal)} cache` : "Tokens";
}

// What the tokens were: all that Claude read and wrote, by kind
function tokensText(t: WeekSum["tokens"]): string {
  return `Everything Claude read and wrote: ${shortCount(t.input)} of new input, ${shortCount(t.cacheRead)} read from the cache, ` +
    `${shortCount(t.cacheWrite5m + t.cacheWrite1h)} written to the cache and ${shortCount(t.output)} that Claude wrote.`;
}

// What went on at ms, on its day's row. px: a pixel's ms, so a mark a pixel
// or two wide can be hit
export function hoverText(d: WeekDay, ms: number, now: number, px: number): string {
  const when = `${dayLabel(d.day)}, ${clockText(ms)}: `;
  if (ms > now) return when + "still to come";
  const at = <T extends number[]>(list: T[]): T | undefined =>
    list.find((s) => s[0] <= ms && ms < s[1]) ?? list.find((s) => s[1] - s[0] < 3 * px && s[0] - 2 * px <= ms && ms < s[1] + 2 * px);
  const span = (s: number[]) => `${clockText(s[0])}–${clockText(s[1])}`;
  const work = at(d.work);
  const wait = at(d.wait);
  const you = at(d.you);
  const parts: string[] = [];
  const limit = (d.limits ?? []).find((t) => Math.abs(t - ms) <= 3 * px);
  if (limit !== undefined) parts.push(`a usage limit stopped a chat at ${clockText(limit)}`);
  if (work) parts.push(work[2] > 1 ? `Claude worked ${span(work)}, ${work[2]} chats at once` : `Claude worked ${span(work)}`);
  else if (wait) parts.push(`Claude waited for your answer ${span(wait)}`);
  if (you) parts.push(`you were at it ${span(you)}`);
  return when + (parts.length ? parts.join(" · ") : "nothing went on");
}

// (recap: with its share of your week, Your plan)
export function dayTip(d: WeekDay, cur: Currency = USD, recap?: Pick<WeekRecap, "planUse" | "accounts">): string {
  const share = recap ? weekShareTip(d, recap, true) : "";
  return (
    `${d.to ? `${monthDay(d.day)} – ${monthDay(d.to)}` : longDay(d.day)}\nYou: ${hoursText(d.youMs)} · Claude worked ${hoursText(d.workedMs)} (on the clock ${hoursText(d.busyMs)}) · ` +
    `it waited ${hoursText(d.waitMs)} for you\n${plural(d.prompts, "%1 prompt", "%1 prompts")} · ${shortCount(d.tokenTotal)} tokens · ${moneyText(d.cost, cur)} at API prices` +
    (share ? `\n${share}` : "") + (d.chats?.length ? "\nClick for its chats" : "")
  );
}

function shortCount(n: number): string {
  return n >= 999.95e6 ? `${(n / 1e9).toFixed(1)}B` : n >= 999.95e3 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${(n / 1e3).toFixed(1)}k` : String(n);
}

function count(n: number): string {
  return (n || 0).toLocaleString("en-US");
}

// A model's part of the whole: "<1%", ">99%" (not a rounded "100%" beside
// another's "<1%"), as sharePercent
export function shareText(share: number): string {
  return share <= 0 ? "0%" : share < 0.01 ? "<1%" : share > 0.99 && share < 1 ? ">99%" : `${Math.round(share * 100)}%`;
}

// A model's amount and share, "≈" before a guessed price's
export function modelValue(m: WeekModel, cur: Currency = USD): string {
  return `${m.guessed ? "≈ " : ""}${moneyText(m.cost, cur)} · ${shareText(m.share)}`;
}

// A model with no list price yet: priced as the newest of its family
export function guessedModelTip(m: WeekModel): string {
  return m.pricedAs
    ? `${m.model} has no list price yet: it's priced as ${m.pricedAs}, the newest model of its family, so its amount is a guess.`
    : `${m.model} has no list price: it isn't in the amounts.`;
}

// How much of the amount rests on a guessed price (the cost tile's tooltip)
export function guessedCostText(recap: Pick<WeekRecap, "prices" | "sum" | "currency">): string {
  const p = recap.prices;
  if (!p.guessedCost || !recap.sum.cost) return "";
  return `\n${moneyText(p.guessedCost, currencyOf(recap))} of it (${shareText(p.guessedCost / recap.sum.cost)}) is priced by a guess: ` +
    `${p.guessed.join(", ")} has no list price yet, so it's at the price of the newest model of its family.`;
}

// A tip's icon (icons.mjs meanings, as Plasma's): the time chats waited for
// you, usage limits, else a tip of Claude Code's /usage
export function tipMeaning(key: string): "tipWaits" | "tipLimits" | "tip" {
  return key === "waits" ? "tipWaits" : key === "limits" ? "tipLimits" : "tip";
}

// What a tip's icon means: where the tip comes from
export function tipSource(key: string): string {
  return key === "waits" ? "From Talpy Den: the time Claude waited for your answers"
    : key === "limits" ? "From Talpy Den: the usage limits that stopped your chats"
      : key === "cold" ? "From Talpy Den: coming back to chats after their cache had expired"
        : "From Claude Code's /usage: a habit that took a good share of your usage";
}

// A tip's share: of the usage, as /usage weighs it; coming back to chats
// after their cache expired: of the amount at API prices (what writing their
// context again cost more than reading it)
export function tipShareText(t: Pick<WeekTip, "key" | "pct">): string {
  return t.pct === null ? "" : t.key === "cold" ? `${t.pct}% of the amount` : `${t.pct}% of usage`;
}

export function tipShareTip(t: Pick<WeekTip, "key" | "pct">, recap: Pick<WeekRecap, "spend" | "currency">): string {
  if (t.key !== "cold")
    return `${t.pct}% of the usage shown: of the usage of these days, as Claude Code's /usage weighs it toward your plan's limits. ` +
      "A request can count for several of these.";
  return `${t.pct}% of the amount at API prices: writing the chats' context again cost ${moneyText(recap.spend?.cold?.cost ?? 0, currencyOf(recap))} ` +
    "more than reading it from the cache. The cache keeps a chat's context an hour after its last reply.";
}

// Too little in the period for tips (week.py: tooLittle)
export const TIPS_TOO_LITTLE = "Too little here to go on: tips need 20 prompts or an hour of Claude's work.";

// A count in words: "1 commit", "1,204 files"
function counted(v: number, one: string, many: string): string {
  return (v === 1 ? one : many).replace("%1", count(v));
}

// What a project or chat got done: "14 commits · 212 files" (the files
// Claude's edits changed); "" for none (or an older week.py's)
export function doneText(x: { commitCount?: number; files?: number }): string {
  const parts: string[] = [];
  if (x.commitCount) parts.push(counted(x.commitCount, "%1 commit", "%1 commits"));
  if (x.files) parts.push(counted(x.files, "%1 file", "%1 files"));
  return parts.join(" · ");
}

// Its tooltip's line: the commits, the files with their lines
export function doneTip(x: { commitCount?: number; files?: number; linesAdded?: number; linesRemoved?: number }): string {
  const parts: string[] = [];
  if (x.commitCount) parts.push(counted(x.commitCount, "%1 commit", "%1 commits"));
  if (x.files)
    parts.push(`${counted(x.files, "Claude's edits changed %1 file", "Claude's edits changed %1 files")} (+${count(x.linesAdded ?? 0)} −${count(x.linesRemoved ?? 0)})`);
  return parts.join(" · ");
}

// A Recap chat as the chat list has it (its row now, or a recent one), for
// what opens its tab: null when it isn't listed (an older one)
export function listedChatRef(status: Status | null | undefined, hosts: HostState[], chatId: string, host = ""): ChatRef | null {
  const where = host ? hosts.find((h) => h.name === host)?.result : status;
  const h = host || undefined;
  for (const g of where?.groups ?? []) {
    const s = (g.sessions ?? []).find((x) => x.chatId === chatId || x.sessionId === chatId);
    if (s) return chatRefOf(s, h);
    const c = [...(g.recent ?? []), ...(g.starred ?? [])].find((x) => x.sessionId === chatId);
    if (c) return recentRef(c, h);
  }
  return null;
}

// A chat's commits shown under it: the newest three, and how many more
export function commitsShown(c: { commits?: [string, string][]; commitCount?: number }): { shown: [string, string][]; more: number } {
  const shown = (c.commits ?? []).slice(0, 3);
  return { shown, more: Math.max(0, (c.commitCount ?? shown.length) - shown.length) };
}

// What Claude did in the period before, for that line's tooltip (when the
// Recap doesn't have that period whole: why it isn't there)
export function workBeforeText(recap: Pick<WeekRecap, "span" | "beforeKept" | "first" | "sameTime" | "workBefore">): string {
  if (!recap.workBefore) return uncomparedText(recap).trim();
  const what = recap.span === "day" ? "The day before" : recap.span === "month" ? "The 30 days before" : "The 7 days before";
  return `${what}${recap.sameTime ? ", by this time" : ""}: ${workText(recap.workBefore) || "nothing"}`;
}

// What Claude did, in a line: its tool calls, commands, edits, subagents
export function workText(w: WeekRecap["work"] | null | undefined): string {
  if (!w || !w.toolCalls) return "";
  const n = counted;
  const parts = [n(w.toolCalls, "%1 tool call", "%1 tool calls")];
  if (w.commands) parts.push(n(w.commands, "%1 command run", "%1 commands run"));
  if (w.edits)
    parts.push(`${n(w.edits, "%1 edit", "%1 edits")} ${n(w.files, "in %1 file", "in %1 files")} (+${count(w.linesAdded)} −${count(w.linesRemoved)})`);
  if (w.subagents) parts.push(n(w.subagents, "%1 subagent started", "%1 subagents started"));
  if (w.webSearches) parts.push(n(w.webSearches, "%1 web search", "%1 web searches"));
  if (w.webFetches) parts.push(n(w.webFetches, "%1 page fetched", "%1 pages fetched"));
  if (w.compactions) parts.push(n(w.compactions, "%1 compaction", "%1 compactions"));
  return parts.join(" · ");
}

// ---------------------------------------------------------------- your plan
// What the days shown meant for each account's plan (week.py plan_use), and
// a project's, chat's or day's share of its week; the same words as Plasma's
// WeekView.qml

// "28%", "<1%": points of a week
function pointsText(v: number): string {
  return v > 0 && v < 0.5 ? "<1%" : `${Math.round(v)}%`;
}

function familyOf(key: string): string {
  const f = FAMILIES.find((x) => key.includes(x)) ?? key;
  return f.charAt(0).toUpperCase() + f.slice(1);
}

// An account's line in Your plan: "66% of the week used in these days · 3
// full 5-hour windows · ran out 3 times, chats held 4h 10m"
export function planUseText(u: WeekPlanUse, recap: Pick<WeekRecap, "span" | "back">): string {
  const parts: string[] = [];
  const week = u.weeks?.seven_day;
  if (u.readings && week !== undefined) {
    const when = !u.covered && u.since ? `since ${limitDay(u.since)}`
      : recap.span === "day" ? (recap.back === 0 ? "today" : "on this day") : "in these days";
    parts.push(`${pointsText(week)} of the week used ${when}`);
  }
  for (const [key, v] of Object.entries(u.weeks ?? {}))
    if (key !== "seven_day" && v > 0) parts.push(`${pointsText(v)} of the ${familyOf(key)} week`);
  if (u.fiveFull) parts.push(counted(u.fiveFull, "%1 full 5-hour window", "%1 full 5-hour windows"));
  else if (u.fiveUsed) parts.push("no full 5-hour window");
  parts.push(!u.ranOut ? "didn't run out"
    : (u.ranOut === 1 ? "ran out once" : `ran out ${count(u.ranOut)} times`) + (u.heldMs >= 60000 ? `, chats held ${hoursText(u.heldMs)}` : ""));
  if (!u.readings) parts.push("no readings of its plan here");
  const text = parts.join(" · ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

// Its tooltip: how each part is worked out
export function planUseTip(u: WeekPlanUse): string {
  const lines: string[] = [];
  if (u.readings && u.weeks?.seven_day !== undefined)
    lines.push("How much of your plan's week these days used: how far Talpy Den's readings of it rose (kept on this computer). " +
      "Use on claude.ai, other computers and SSH hosts counts too." +
      (!u.covered && u.since ? ` The readings kept begin on ${limitDay(u.since)}: before that isn't known.` : ""));
  if (u.fiveUsed)
    lines.push(`${u.fiveFull} of the ${u.fiveUsed} 5-hour windows begun in these days ran full: their readings reached 100%, ` +
      "or a usage limit stopped a chat as one ended.");
  if (u.ranOut)
    lines.push(`Your plan ran out ${u.ranOut === 1 ? "once" : `${count(u.ranOut)} times`} (${counted(u.stopped, "%1 chat stopped", "%1 chats stopped")}). ` +
      `From each stop until the limit reset, or until the chat went on another way, chats were held ${hoursText(u.heldMs)} in all, on the clock.`);
  if (!u.readings)
    lines.push(`Talpy Den keeps readings of the plans of this computer's accounts only: ${u.name}'s has none here, so what these days used of its week isn't known.`);
  return lines.join("\n");
}

// A project's share of the week on its row: "≈ 28%" (its largest; "" for none)
export function weekShareShort(x: { weekShare?: WeekShare[] }): string {
  const s = x.weekShare?.[0];
  return !s ? "" : s.pct < 0.5 ? "<1%" : `≈ ${Math.round(s.pct)}%`;
}

// A project's, chat's or day's share of each account's week, for its
// tooltip: how it's worked out (day: from the readings themselves), and why
// one of its accounts' is missing
export function weekShareTip(x: { weekShare?: WeekShare[]; accounts?: string[] }, recap: Pick<WeekRecap, "planUse" | "accounts">, day = false): string {
  const uses = recap.planUse ?? [];
  const name = (id: string) => uses.find((u) => u.account === id)?.name ?? recap.accounts.find((a) => a.id === id)?.name ?? id;
  const named = uses.filter((u) => u.readings).length > 1;
  const shares = x.weekShare ?? [];
  const lines = shares.map((s) => `${day ? "" : "≈ "}${pointsText(s.pct)} of ${named ? `${name(s.account)}'s week` : "your week"}`);
  if (lines.length)
    lines.push(day ? "As the readings of your plan's week rose then."
      : "An estimate: its part of these days' amount at API prices, times how much of the week these days used (Your plan).");
  for (const id of x.accounts ?? []) {
    const u = uses.find((v) => v.account === id);
    if (shares.some((s) => s.account === id)) continue;
    if (!u || !u.readings) lines.push(`Its share of ${name(id)}'s week isn't known: no readings of that plan on this computer.`);
    else if (!u.covered && u.since) lines.push(`Its share of ${name(id)}'s week isn't known: the readings of it kept begin on ${limitDay(u.since)}.`);
  }
  return lines.join("\n");
}

// A plan window, from its start (its reset less its length) to its reset
const WINDOW_MS: Record<string, number> = {
  five_hour: 5 * 3600000, seven_day: 7 * 86400000, seven_day_opus: 7 * 86400000, seven_day_sonnet: 7 * 86400000,
};

export function windowSpan(w: WeekPlanWindow): [number, number] {
  const from = w.resetsAt && WINDOW_MS[w.key] ? w.resetsAt - WINDOW_MS[w.key] : w.points.length ? w.points[0][0] : 0;
  return [from, Math.max(w.resetsAt ?? 0, from + 1)];
}

// The window's fill as SVG paths in a width × height box: the line, and the
// area under it (up to now)
export function fillPaths(w: WeekPlanWindow, now: number, width: number, height: number): { line: string; area: string } {
  const [from, until] = windowSpan(w);
  const points = w.points.filter((p) => p[0] >= from);
  if (!points.length) return { line: "", area: "" };
  const x = (ms: number) => Math.max(0, Math.min(width, ((ms - from) / (until - from)) * width)).toFixed(1);
  const y = (pct: number) => (height - 0.5 - (Math.max(0, Math.min(100, pct)) / 100) * (height - 1)).toFixed(1);
  const end = Math.min(now, until);
  const last = points[points.length - 1][1];
  const line = points.map((p, i) => `${i ? "L" : "M"}${x(p[0])},${y(p[1])}`).join(" ") + ` L${x(end)},${y(last)}`;
  return { line, area: `M${x(points[0][0])},${height} L${line.slice(1)} L${x(end)},${height} Z` };
}

// The Day with chats: one timeline (the lanes, with the day's own row on
// top) and the chats' numbers at their lanes' ends, rather than the day's
// row and Chats it worked on most saying it again
export function dayLanes(recap: Pick<WeekRecap, "span" | "lanes">): boolean {
  return recap.span === "day" && (recap.lanes?.length ?? 0) > 0;
}

// At a lane's end: what Claude worked on that chat, by its own count, and
// its cost ("7h 33m · $258", "<1m · $0.05"; "–" for neither)
export function laneNumbers(l: { claudeMs?: number; cost?: number }, cur: Currency = USD): string {
  const ms = l.claudeMs ?? 0;
  const cost = l.cost ?? 0;
  if (ms < 60000 && cost < 0.01) return "–";
  return `${ms < 60000 ? "<1m" : hoursText(ms)} · ${moneyText(cost, cur)}`;
}

export function resetText(ms: number | null, now: number): string {
  if (!ms) return "";
  return `resets ${ms - now < 86400000 ? clockText(ms) : whenText(ms)}`;
}

// What a plan window's line says beside its fill: "60% · resets 14:00", "0% · reset"
export function planText(w: WeekPlanWindow, now: number): string {
  return `${Math.round(w.pct)}%` + (w.reset ? " · reset" : w.resetsAt ? ` · ${resetText(w.resetsAt, now)}` : "");
}

export function promptsText(p: WeekRecap["prompts"] | undefined): string {
  if (!p || !p.answered) return "";
  const answered = plural(p.answered, "%1 permission prompt", "%1 permission prompts");
  return (p.refused ? `You answered ${answered} and refused ${p.refused} of them.` : `You answered ${answered}.`) +
    (p.waitMs >= 60000 ? ` They waited for your answer ${hoursText(p.waitMs)} in all.` : "");
}

// The permissions you gave: the first few, until you ask for all
export const GRANTED_FEW = 8;

// A permission's kind, as an icon (icons.mjs meanings, as Plasma's PermsView
// grantIcon): a trusted folder, an MCP server, a loosened check, a folder to
// read, a mode, the web, a command
export function grantMeaning(g: { kind: string; value: string }): "trusted" | "mcp" | "warning" | "folder" | "edit" | "webAccess" | "terminal" | "allowed" {
  if (g.kind === "trust") return "trusted";
  if (g.kind === "mcp") return "mcp";
  if (g.kind === "flag") return "warning";
  if (g.kind === "dir") return "folder";
  if (g.kind === "mode") return g.value === "acceptEdits" ? "edit" : "warning";
  if (g.value.startsWith("WebFetch") || g.value === "WebSearch") return "webAccess";
  return g.value.startsWith("Bash") ? "terminal" : "allowed";
}

// A rule it suggests for the prompts you answered, as an icon (as Plasma's):
// a folder to read, edits in the chats' folder, the web, a command
export function ruleMeaning(r: { kind: string; value: string }): "folder" | "edit" | "webAccess" | "terminal" {
  return r.kind === "dir" ? "folder" : r.kind === "edits" ? "edit" : r.value.startsWith("WebFetch") ? "webAccess" : "terminal";
}

export function grantedIntro(granted: WeekGrant[], host = ""): string {
  const name = host ? hostLabel(host) : "";
  if (!granted.length) return `Nothing lets chats on ${name || "this computer"} skip a permission prompt: they ask you each time.`;
  return host
    ? `What lets chats on ${name} go without asking you, as listed there: its settings, its trusted folders, and the .claude ` +
      `settings of the folders Claude ran in. Revoke takes one out of its file on ${name}.`
    : "What lets chats on this computer go without asking you: your settings and your administrator's, the folders you " +
      "trusted, the .claude settings of the folders Claude ran in, and what you approved in them. Revoke takes one out of its file.";
}

export function grantMeta(g: WeekGrant): string {
  return `${g.place} · ${g.where}`;
}

// A revoke message from the page, as the extension takes it: an id of
// week.py's list (which checks again that it's one of it)
export function weekRevokeAsked(id: unknown): string | null {
  return typeof id === "string" && /^[0-9a-f]{12}$/.test(id) ? id : null;
}

// The SSH host or container a permission message is for: a name as
// remote.py takes it (its HOST_NAME: docker:web@lab too) or "" (this
// computer); the extension acts on it only if it's one of the hosts shown
export function permsHost(host: unknown): string | null {
  if (host === undefined || host === "") return "";
  return typeof host === "string" && /^[A-Za-z0-9_.@][A-Za-z0-9_.@:-]{0,254}$/.test(host) ? host : null;
}

export function ruleMeta(r: WeekRule): string {
  return [plural(r.count, "%1 prompt", "%1 prompts"), r.waitMs >= 60000 ? `waited ${hoursText(r.waitMs)} for you` : "", `e.g. ${r.example}`]
    .filter(Boolean).join(" · ");
}

export function footText(recap: WeekRecap): string {
  const hosts = recap.sources.filter((s) => s.host && s.ok).map((s) => hostLabel(s.host));
  const guessed = recap.prices.guessed.length ? ` (${recap.prices.guessed.join(", ")} at the price of its family's newest model)` : "";
  const lines = [
    `Read from the chats on this computer${hosts.length ? ` and on ${hosts.join(", ")}` : ""}, without using any tokens. ` +
      `Prices: Claude's API list prices of ${dateText(recap.prices.asOf)}${guessed}.`,
  ];
  const c = recap.currency;
  if (c?.error) lines.push(`Amounts in US dollars: ${c.error}.`);
  else if (c && c.code !== "USD" && c.date)
    lines.push(`Amounts in ${c.code} at the European Central Bank's rate of ${dateText(c.date)}: 1 USD = ${c.rate.toFixed(4)} ${c.code}.`);
  for (const s of recap.sources) if (!s.ok) lines.push(`${hostLabel(s.host)} couldn't be read: ${s.error}`);
  return lines.join("\n");
}

// Week messages from the page, as the extension takes them: a span, days or
// weeks back (any: week.py stops at the first chat kept), an account id or all
export function weekAsked(back: unknown, account: unknown, span: unknown = "week"): { back: number; account: string; span: WeekSpan } {
  const b = typeof back === "number" && Number.isInteger(back) ? Math.min(3650, Math.max(0, back)) : 0;
  const a = typeof account === "string" && /^[0-9a-f]{12}$/.test(account) ? account : "";
  const sp: WeekSpan = span === "day" || span === "month" || span === "all" ? span : "week";
  return { back: b, account: a, span: sp };
}

export type WeekRuleAsk = { allow: true; kind: string; value: string; project: string } | { allow: false; id: string };

// A rule message from the page, as the extension takes it (week.py checks
// again that it's a rule the tab offers, for a folder a chat started in)
export function weekRuleAsked(m: { allow?: unknown; kind?: unknown; value?: unknown; project?: unknown; id?: unknown }): WeekRuleAsk | null {
  const plain = (v: unknown): v is string => typeof v === "string" && v.length > 0 && v.length <= 1000 && !/[\0\n\r]/.test(v);
  if (m.allow === true) {
    if (typeof m.kind !== "string" || !["dir", "edits", "allow"].includes(m.kind)) return null;
    if (!plain(m.value) || !plain(m.project) || !m.project.startsWith("/")) return null;
    return { allow: true, kind: m.kind, value: m.value, project: m.project };
  }
  if (m.allow === false && typeof m.id === "string" && /^[0-9a-f]{12}$/.test(m.id)) return { allow: false, id: m.id };
  return null;
}

// ---------------------------------------------------------------- advanced analyses: how your limits changed
// (the Recap's folded section, week.py --limits; the same words as GNOME's
// logic.js and Plasma's WeekView.qml)

const FAMILIES = ["fable", "mythos", "opus", "sonnet", "haiku"];

// "5-hour window", "Week", "Week · Opus" (a plan's weekly window of one model)
export function limitLabel(key: string): string {
  if (key === "five_hour") return "5-hour window";
  if (key === "seven_day") return "Week";
  const family = FAMILIES.find((f) => key.includes(f));
  return family ? `Week · ${family.charAt(0).toUpperCase()}${family.slice(1)}` : key.replace(/_/g, " ");
}

// "about 5×", "▲ 20%", "▼ 80%", "about the same": how many times what a window held it holds now
function factorText(f: number): string {
  if (f >= 1.5) return `about ${Number(f.toFixed(1))}×`;
  const pct = Math.round(Math.abs(f - 1) * 100);
  return pct < 10 ? "about the same" : `${f > 1 ? "▲" : "▼"} ${pct}%`;
}

// "▼ 14% vs the week before", "about the same as the week before", "new this week", "about 5× since 4 Nov", …
export function limitChangeText(c: LimitChange | null | undefined): string {
  if (!c) return "";
  if (c.kind === "change") return `${(c.pct ?? 0) < 0 ? "▼" : "▲"} ${Math.abs(c.pct ?? 0)}% vs the week before`;
  if (c.kind === "same") return "about the same as the week before";
  if (c.kind === "new") return "new this week";
  if (c.kind === "limits") {
    const day = c.at ? limitDay(c.at) : "";
    return c.factor ? `${factorText(c.factor)} since ${day}` : `your plan changed on ${day}`;
  }
  if (c.kind === "rough") return "readings too far apart to compare yet";
  return "too few readings to compare yet";
}

// A window's size as the section shows it: one number ("$164", "≈ $820"
// before one measured since the limits changed), or, from too few windows
// or ones too far apart (rough), their range and how many ("$37–$215 · 5
// windows"; a week's: its readings' range), not bold
export function limitValueText(key: string, v: { cost: number; lo?: number; hi?: number; n?: number; scaled?: number; rough?: boolean } | null | undefined,
  cur: Currency = USD): { text: string; rough: boolean } {
  if (!v) return { text: limitMoney(0, cur), rough: false };
  if (!v.rough || v.lo === undefined || v.hi === undefined) return { text: (v.scaled ? "≈ " : "") + limitMoney(v.cost, cur), rough: false };
  const range = v.hi > v.lo ? `${limitMoney(v.lo, cur)}–${limitMoney(v.hi, cur)}` : limitMoney(v.cost, cur);
  return { text: (v.scaled ? "≈ " : "") + range + (key === "five_hour" && v.n ? ` · ${plural(v.n, "%1 window", "%1 windows")}` : ""), rough: true };
}

// A change of the plan's limits, in a line: "4 Nov 18:52 · your limits grew about 5× · Pro → Max 5×"
export function limitEventText(e: LimitEvent): string {
  const fs = Object.values(e.factors).sort((p, q) => p - q);
  const f = fs.length ? fs[Math.floor((fs.length - 1) / 2)] : null;
  const what = f === null ? "your plan changed"
    : f >= 1.5 ? `your limits grew about ${Number(f.toFixed(1))}×`
      : Math.abs(f - 1) < 0.1 ? "your limits stayed about the same"
        : `your limits ${f > 1 ? "grew" : "shrank"} ${Math.round(Math.abs(f - 1) * 100)}%`;
  const plans = e.from && e.to && e.from !== e.to ? ` · ${e.from} → ${e.to}` : !e.from && e.to ? ` · now ${e.to}` : "";
  return `${limitDay(e.at)} ${clockText(e.at)} · ${what}${plans}`;
}

// An event's tooltip: by how much each window changed, and how that's known
export function limitEventTip(e: LimitEvent): string {
  const keys = Object.keys(e.factors);
  return keys.length
    ? keys.map((k) => `${limitLabel(k)}: ${Number(e.factors[k].toFixed(2))}× what it held`).join("\n") +
      "\nFrom your readings at that moment: the same usage read as a different share of the window."
    : "Your windows' plan changed between two of them: what they held before and after tells by how much.";
}

// "17% of the week · about 6 full windows a week"
// Why a size is shown as a range
export function limitRoughTip(key: string): string {
  return key === "five_hour"
    ? "Too few windows, or ones too far apart, for one number: use not seen here (claude.ai, your phone, other computers, " +
      "SSH hosts) fills some windows more than others. No change is told from it."
    : "Its readings tell sizes too far apart for one number: use not seen here (claude.ai, your phone, other computers, " +
      "SSH hosts) counts in some of them. No change is told from it.";
}

export function limitShareText(pct: number, rough = false): string {
  return pct > 0 ? `${rough ? "≈ " : ""}${Math.round(pct)}% of the week · about ${Math.max(1, Math.round(100 / pct))} full windows a week` : "";
}

// How long a full 5-hour window lasted at your pace
export function limitFillText(fill: LimitPeriod["fill"]): string {
  if (!fill) return "";
  const work = fill.workMs >= 60000 ? ` · Claude worked ${hoursText(fill.workMs)} in it, across chats` : "";
  return (fill.wallMs <= 5 * 3600000 ? `Full after about ${hoursText(fill.wallMs)} at your pace`
    : "At your pace a 5-hour window doesn't fill in its 5 hours") + work;
}

// What a full window is worth in tokens, at the API price of the model used most:
// "2.1M output tokens of Opus 5.5 (or 210.0M cache reads) fill a 5-hour window; 12.2M a week"
export function limitTokensText(a: LimitAccount): string {
  const e = a.equivalents;
  const five: LimitTokens | null = e?.fiveHour ?? null;
  const week: LimitTokens | null = e?.week ?? null;
  if (!e || !(five || week)) return "";
  const first = five ?? week!;
  return `${shortCount(first.output)} output tokens of ${e.model} (or ${shortCount(first.cacheRead)} cache reads) fill ` +
    (five ? "a 5-hour window" : "a week") + (five && week ? `; ${shortCount(week.output)} a week` : "") + ", at API prices";
}

// A window's size: whole amounts from 10 up ("$48", "€1,180"), as moneyText below
export function limitMoney(usd: number, cur: Currency = USD): string {
  const amount = (usd || 0) * cur.rate;
  if (amount < 10) return moneyText(usd, cur);
  const symbol = SYMBOLS[cur.code];
  const text = Math.round(amount).toLocaleString("en-US");
  return symbol ? symbol + text : `${text} ${cur.code}`;
}

// What filled a window: its parts (shares of their API price, each with its
// legend's words; by count, cache reads are nearly all of it) and the line
// under them, with how many tokens that is
export function limitMix(c: LimitPeriod["costs"] | undefined, t?: LimitPeriod["tokens"]): {
  parts: { kind: "cacheRead" | "fresh" | "output"; share: number; label: string }[];
  text: string;
} {
  const total = c ? c.cacheRead + c.fresh + c.output : 0;
  if (!c || total <= 0) return { parts: [], text: "" };
  const names = { cacheRead: "cache reads", fresh: "new input and cache writes", output: "output" };
  const parts = (["cacheRead", "fresh", "output"] as const).map((kind) => ({ kind, share: c[kind] / total,
    label: `${names[kind]} ${shareText(c[kind] / total)}` }));
  const count = t ? t.cacheRead + t.fresh + t.output : 0;
  return { parts, text: count > 0 ? `by API price; ${shortCount(count)} tokens fill a 5-hour window` : "by API price" };
}

// "24 Oct": when a week began
export function limitDay(ms: number): string {
  const d = new Date(ms);
  return `${d.getDate()} ${MONTHS[d.getMonth()]}`;
}

// The dots of the 5-hour windows (x, y: 0 to 1) and each week's median, over
// the weeks kept; from a little under the smallest to a little over the
// largest (from 0 they'd all sit at the top, a change unseen: the caption
// says the range)
export function limitDots(a: LimitAccount, now: number, start?: number): {
  dots: { x: number; y: number; full: number; tip: string }[];
  medians: { x1: number; x2: number; y: number }[];
  marks: number[]; // (x of each change of the limits)
  lo: number;
  top: number;
} {
  const from = start ?? (a.periods.length ? a.periods[0].from : now);
  const span = Math.max(1, now - from);
  const sizes = [...a.windows.map((w) => w.full), ...a.periods.map((p) => p.fiveHour?.cost ?? NaN)].filter((v) => v > 0);
  const most = sizes.length ? Math.max(...sizes) : 1;
  const least = sizes.length ? Math.min(...sizes) : 0;
  const pad = Math.max((most - least) * 0.15, most * 0.05);
  const lo = Math.max(0, least - pad);
  const top = most + pad;
  const x = (ms: number) => Math.max(0, Math.min(1, (ms - from) / span));
  const y = (v: number) => (v - lo) / (top - lo);
  return {
    dots: a.windows.map((w) => ({ x: x(w.at), y: y(w.full), full: w.full,
      tip: `${whenText(w.start)}: ${Math.round(w.pct)}% used by ${clockText(w.at)}` })),
    medians: a.periods.filter((p) => p.fiveHour).map((p) => ({ x1: x(p.from), x2: x(Math.min(p.until, now)), y: y(p.fiveHour!.cost) })),
    marks: (a.events ?? []).filter((e) => e.at > from && e.at <= now).map((e) => x(e.at)),
    lo,
    top,
  };
}

// The weeks' bars (the main weekly window): height 0 to 1, the newest marked
// The weeks' bars (the main weekly window) on the same time line as the
// dots (x1, x2: 0 to 1, from start to now), height 0 to 1 of the largest
export function limitWeekBars(a: LimitAccount, now: number, start?: number): { from: number; cost: number; x1: number; x2: number; h: number; partial: boolean }[] {
  const from = start ?? (a.periods.length ? a.periods[0].from : now);
  const span = Math.max(1, now - from);
  const x = (ms: number) => Math.max(0, Math.min(1, (ms - from) / span));
  const weeks = a.periods.filter((p) => p.weeks.seven_day);
  const top = Math.max(1e-9, ...weeks.map((p) => p.weeks.seven_day.cost));
  return weeks.map((p) => ({ from: p.from, cost: p.weeks.seven_day.cost, x1: x(p.from), x2: x(Math.min(p.until, now)),
    h: p.weeks.seven_day.cost / top, partial: !!p.weeks.seven_day.partial }));
}

// Where every account's charts begin: the earliest week any of them has, so
// a day is at the same place in each
export function limitStart(accounts: LimitAccount[], now: number): number {
  const starts = accounts.filter((a) => a.periods.length).map((a) => a.periods[0].from);
  return starts.length ? Math.min(...starts) : now;
}

// The window keys an account has, in the order the Chats tab lists them
export function limitKeys(a: LimitAccount): string[] {
  const order = ["five_hour", "seven_day", "seven_day_opus", "seven_day_sonnet"];
  const keys = ["five_hour", ...Object.keys(a.now.weeks)].filter((k) => k === "five_hour" ? a.now.fiveHour : a.now.weeks[k]);
  return keys.sort((p, q) => (order.indexOf(p) + 1 || 99) - (order.indexOf(q) + 1 || 99));
}

// The section's last line: what it's made from and what it can't see
export function limitFootText(h: Pick<LimitHistory, "since">): string {
  return `Estimated from this computer's chats and the limit readings Talpy Den kept` +
    (h.since ? ` since ${limitDay(h.since)}` : "") + ". Use on claude.ai, your phone, other computers or SSH hosts counts " +
    "toward your limits but isn't seen here, so a limit can look smaller than it is.";
}

export const LIMIT_EMPTY = "Not enough readings yet: a few 5-hour windows used past half tell how much one holds.";

// A size's tooltip: how it's worked out
export function limitSizeTip(key: string, a: LimitAccount, cur: Currency): string {
  const v = key === "five_hour" ? a.now.fiveHour : a.now.weeks[key];
  const scaled = v?.scaled ?? null;
  const since = (scaled ? `\nNone measured since your limits changed yet: what it held before, times ${Number(scaled.toFixed(2))}.` : "") +
    (v?.rough ? `\n${limitRoughTip(key)}` : "");
  if (key === "five_hour") {
    const f = a.now.fiveHour;
    return f ? `What a full 5-hour window held: the API price of what your chats used by a reading, over the share of the window ` +
      `it said was used. The middle of ${plural(f.n, "%1 window", "%1 windows")} in the newest week` +
      (f.n > 1 ? ` (${moneyText(f.lo, cur)} to ${moneyText(f.hi, cur)})` : "") + "." + since : "";
  }
  return `What a full ${limitLabel(key).toLowerCase()} held: the API price of what your chats used by its readings, over the ` +
    `share of it they said was used` + (key === "seven_day" ? "." : ` (only that model's usage counts).`) + since;
}
