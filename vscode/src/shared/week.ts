// The Recap tab's words and numbers (webview/components/WeekView.tsx), from
// the recap of the widget's week.py; here, so the tests can read them.

import { canEndChat, chatRefOf, clockText, dayLabel, goOnAt, hostLabel, keptChat, plural, recentRef } from "./model";
import type {
  ChatRef, HostState, LimitAccount, LimitEra, LimitEvent, LimitHistory, LimitPeriod, LimitShare, LimitTokens, LimitWeek, RecentChat, Session, Status, WeekDay, WeekGrant,
  WeekLane, WeekMix, WeekModel, WeekNumbers, WeekPlanUse, WeekPlanWindow, WeekRecap, WeekRule, WeekShare, WeekSpan, WeekSum, WeekTip, WeekTipChat,
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
// now); then where the usage went (by model at API prices, then as your
// plan's limits count it) and what could use less of your plan. Last, in
// Overall only: your plan's limits over time.
export const RECAP_SECTIONS = ["days", "lanes", "projects", "plan", "usage", "tips", "limits"] as const;

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

// A tooltip's line with a share the period before ("\nThe 7 days before, by
// this time: 64%"), or why it isn't compared
function beforeLine(recap: Pick<WeekRecap, "span" | "sameTime" | "beforeKept" | "first">, value: string | null): string {
  if (value === null) return uncomparedText(recap);
  const what = recap.span === "day" ? "The day before" : recap.span === "month" ? "The 30 days before" : "The 7 days before";
  return `\n${what}${recap.sameTime ? ", by this time" : ""}: ${value}`;
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

// (the subagents tip's share isn't the Subagents row's: /usage counts whole chats there)
const SUBAGENT_HEAVY_HOW = "This one is all the usage of the chats where subagents did most of the work, their main chat's requests too; the Subagents row counts only the subagents' own.";

export function tipShareTip(t: Pick<WeekTip, "key" | "pct" | "before">,
                            recap: Pick<WeekRecap, "spend" | "currency" | "span" | "sameTime" | "beforeKept" | "first">): string {
  const before = beforeLine(recap, t.before === null || t.before === undefined ? null : `${t.before}%`);
  if (t.key !== "cold")
    return `${t.pct}% of the usage shown: of the usage of these days, as Claude Code's /usage weighs it toward your plan's limits. ` +
      (t.key === "subagent_heavy" ? SUBAGENT_HEAVY_HOW + " " : "") + "A request can count for several of these." + before;
  return `${t.pct}% of the amount at API prices: writing the chats' context again cost ${moneyText(recap.spend?.cold?.cost ?? 0, currencyOf(recap))} ` +
    "more than reading it from the cache. The cache keeps a chat's context an hour after its last reply." + before;
}

// Under a tip's share, how it moved: "was 64%" (none: not compared)
export function tipWas(t: Pick<WeekTip, "pct" | "before">): string {
  return t.pct === null || t.before === null || t.before === undefined ? "" : `was ${t.before}%`;
}

// The row of where the usage went that says a tip's share already (with how
// it moved): its share isn't said again on the tip
const MIX_OF_TIP: Record<string, string> = { long_context: "long_context", max_effort: "effort:max" };
export function tipShareShown(t: Pick<WeekTip, "key" | "pct">, mix: WeekMix[] | undefined): boolean {
  return t.pct !== null && !(MIX_OF_TIP[t.key] && (mix ?? []).some((p) => p.key === MIX_OF_TIP[t.key]));
}

// The tips shown: the limits tip, once every chat it names keeps going, has
// nothing left to offer
export function tipsShown(tips: WeekTip[], status: Pick<Status, "keep"> | null | undefined): WeekTip[] {
  return tips.filter((t) => !(t.key === "limits" && t.chats?.length && !t.more && t.chats.every((c) => keptChat(status, c.chatId, c.host || undefined))));
}

// What a tip offers one of the chats it names, as the chat list would now:
// "stop" for an idle chat with a process of its own (the tip about chats that
// ran long: one at work is stopped from its row); "keep" (Keep going) for one
// at work, "keepAtReset" for one a usage limit stopped that goes on once it
// resets, "kept" for one that keeps going already (the tip about limits);
// else "" (its name opens it). ref: the chat as the extension finds it.
export type TipAct = "stop" | "keep" | "keepAtReset" | "kept" | "";
export function tipChatAct(key: string, c: Pick<WeekTipChat, "chatId" | "host">, status: Status | null | undefined, hosts: HostState[]):
  { act: TipAct; ref: ChatRef | null } {
  const host = c.host || undefined;
  if (key === "limits" && keptChat(status, c.chatId, host)) return { act: "kept", ref: null };
  const where = host ? hosts.find((h) => h.name === host)?.result : status;
  let session: Session | undefined;
  let recent: RecentChat | undefined;
  for (const g of where?.groups ?? []) {
    session = (g.sessions ?? []).find((x) => x.chatId === c.chatId || x.sessionId === c.chatId);
    if (session) break;
    recent = recent ?? [...(g.recent ?? []), ...(g.starred ?? [])].find((x) => x.sessionId === c.chatId);
  }
  const ref = session ? chatRefOf(session, host) : recent ? recentRef(recent, host) : null;
  const item = session ?? recent;
  if (!item || !c.chatId) return { act: "", ref: null };
  if (key === "long_running" && session)
    // (as the chat list's canStop)
    return { act: session.state === "idle" && (canEndChat(session) || !!session.stopCommand || (!host && !!session.jobId && session.pid != null)) ? "stop" : "", ref };
  if (key === "limits")
    return { act: goOnAt(item) > 0 ? "keepAtReset" : session && session.state === "working" && session.entrypoint !== "claude-vscode" ? "keep" : "", ref };
  return { act: "", ref };
}

// ---------------------------------------------------------------- where the usage went
// By model (at API prices), then weighed as Claude Code's /usage weighs it
// toward your plan's limits (week.py usage_mix); the same words as Plasma's
// WeekView.qml

export function mixLabel(key: string): string {
  return key === "subagents" ? "Subagents" : key === "long_context" ? "Context over 150k" : key === "effort:" ? "Effort not noted" : `Effort ${key.slice(7)}`;
}

// "71% of usage · was 64%"
export function mixValue(p: WeekMix): string {
  return `${pointsText(p.pct)} of usage${p.before === null ? "" : ` · was ${pointsText(p.before)}`}`;
}

export function mixTip(p: WeekMix, recap: Pick<WeekRecap, "span" | "sameTime" | "beforeKept" | "first">): string {
  const what = p.key === "subagents" ? `Subagents' requests took ${pointsText(p.pct)} of the usage of these days, the main chats' ${pointsText(100 - p.pct)}.`
    : p.key === "long_context" ? `Requests that carried over 150k tokens of context took ${pointsText(p.pct)} of the usage: a long chat sends all of its context with each request.`
      : p.key === "effort:" ? `${pointsText(p.pct)} of the usage has no effort level noted: chats deleted before Talpy Den kept their levels (only max effort is known of them), and models with no effort setting.`
        : `Requests at ${p.key.slice(7)} effort took ${pointsText(p.pct)} of the usage.`;
  return `${what}\nWeighed as Claude Code's /usage weighs it toward your plan's limits: a request's tokens by kind, times its model's weight.` +
    beforeLine(recap, p.before === null ? null : pointsText(p.before));
}

// A model's row: its amount and share, and its share the period before
export function modelRowText(m: WeekModel, cur: Currency = USD): string {
  return modelValue(m, cur) + (m.before === null || m.before === undefined ? "" : ` · was ${shareText(m.before)}`);
}

export function modelTip(m: WeekModel, recap: Pick<WeekRecap, "span" | "sameTime" | "beforeKept" | "first" | "currency">): string {
  return `${moneyText(m.cost, currencyOf(recap))} at API prices, ${shareText(m.share)} of the amount of these days · ${plural(m.requests, "%1 request", "%1 requests")}` +
    (m.guessed ? `\n${guessedModelTip(m)}` : "") + beforeLine(recap, m.before === null || m.before === undefined ? null : pointsText(100 * m.before));
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

// How long chats stood stopped by a limit, in all: days when it's long ("10 days")
export function stoodText(ms: number): string {
  return ms >= 2 * 86400000 ? `${Math.round(ms / 86400000)} days` : hoursText(ms);
}

// Each week on its own (Month and Overall, or a sum over a whole week): the
// points of each weekly window these days used, never added up
export function planWeeksShown(u: Pick<WeekPlanUse, "weeks" | "weekly">, recap: Pick<WeekRecap, "span">): boolean {
  return !!u.weekly?.length && (recap.span === "month" || recap.span === "all" || (u.weeks?.seven_day ?? 0) > 100);
}

// An account's line in Your plan: "66% of the week used in these days · 3
// full 5-hour windows · ran out 3 times, chats stood stopped 4h 10m in all";
// several weeks: "Weeks: 72% · 100% · 41% so far · …"
export function planUseText(u: WeekPlanUse, recap: Pick<WeekRecap, "span" | "back">): string {
  const parts: string[] = [];
  const week = u.weeks?.seven_day;
  if (u.readings && week !== undefined) {
    const when = !u.covered && u.since ? `since ${limitDay(u.since)}`
      : recap.span === "day" ? (recap.back === 0 ? "today" : "on this day") : "in these days";
    parts.push(planWeeksShown(u, recap)
      ? `Weeks${!u.covered && u.since ? ` since ${limitDay(u.since)}` : ""}: ` +
        u.weekly!.map((w) => pointsText(w.pct) + (w.now ? " so far" : "")).join(" · ")
      : `${pointsText(week)} of the week used ${when}`);
  }
  for (const [key, v] of Object.entries(u.weeks ?? {}))
    if (key !== "seven_day" && v > 0) parts.push(`${pointsText(v)} of the ${familyOf(key)} week`);
  if (u.fiveFull) parts.push(counted(u.fiveFull, "%1 full 5-hour window", "%1 full 5-hour windows"));
  else if (u.fiveUsed) parts.push("no full 5-hour window");
  parts.push(!u.ranOut ? "didn't run out"
    : (u.ranOut === 1 ? "ran out once" : `ran out ${count(u.ranOut)} times`) +
      (u.heldMs >= 60000 ? `, chats stood stopped ${stoodText(u.heldMs)} in all` : ""));
  if (!u.readings) parts.push("no readings of its plan here");
  const text = parts.join(" · ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

// Its tooltip: how each part is worked out
export function planUseTip(u: WeekPlanUse, recap?: Pick<WeekRecap, "span">): string {
  const lines: string[] = [];
  if (u.readings && u.weeks?.seven_day !== undefined)
    lines.push((recap && planWeeksShown(u, recap)
      ? "How much of each of your plan's weeks these days used, the newest last: how far Talpy Den's readings of it rose " +
        "(kept on this computer), each week in its own limits. " +
        u.weekly!.map((w) => `${limitDay(w.from)} to ${limitDay(w.until)}: ${pointsText(w.pct)}${w.now ? " so far" : ""}`).join(", ") + ". "
      : "How much of your plan's week these days used: how far Talpy Den's readings of it rose (kept on this computer). ") +
      "Use on claude.ai, other computers and SSH hosts counts too." +
      (!u.covered && u.since ? ` The readings kept begin on ${limitDay(u.since)}: before that isn't known.` : ""));
  if (u.fiveUsed)
    lines.push(`${u.fiveFull} of the ${u.fiveUsed} 5-hour windows begun in these days ran full: their readings reached 100%, ` +
      "or a usage limit stopped a chat as one ended.");
  if (u.ranOut)
    lines.push(`Your plan ran out ${u.ranOut === 1 ? "once" : `${count(u.ranOut)} times`} (${counted(u.stopped, "%1 chat stopped", "%1 chats stopped")}). ` +
      `Chats stood stopped ${stoodText(u.heldMs)} in all: each from its stop until the limit reset, or until it went on another way ` +
      "(chats stopped at the same time count once).");
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

// The Day's lanes, their whole hours on the axis: every 1, 2, 3, 4, 6 or 12
// hours, at most 6 of them (by the local clock)
export function laneTicks(t0: number, t1: number): number[] {
  const hour = 3600000;
  if (!(t1 > t0 && t0 > 0) || t1 - t0 > 2 * 86400000) return []; // (not a day's: none)
  const step = [1, 2, 3, 4, 6, 12].find((s) => (t1 - t0) / hour / s <= 6) ?? 24;
  const first = new Date(t0);
  first.setMinutes(0, 0, 0);
  const out: number[] = [];
  for (let t = first.getTime() + hour; t < t1; t += hour) if (new Date(t).getHours() % step === 0) out.push(t);
  return out;
}

// What went on at ms, chat by chat (the Day's lanes, the day's own row). px:
// a pixel's ms, so a mark a pixel or two wide can be hit
export function laneHoverText(lanes: WeekLane[], day: Pick<WeekDay, "you" | "limits"> | undefined, ms: number, px: number): string {
  const near = (a: number, b: number) => (a <= ms && ms < b) || (b - a < 3 * px && a - 2 * px <= ms && ms < b + 2 * px);
  const of = (kind: string) => lanes.filter((l) => l.parts.some((p) => p[2] === kind && near(p[0], p[1]))).map((l) => (l.host ? hostLabel(l.host) + ": " : "") + l.name);
  const parts: string[] = [];
  const limit = (day?.limits ?? []).find((t) => Math.abs(t - ms) <= 3 * px);
  if (limit !== undefined) parts.push(`a usage limit stopped a chat at ${clockText(limit)}`);
  const worked = of("w"), waited = of("y"), paused = of("p");
  if (worked.length) parts.push(`Claude worked in ${worked.join(", ")}`);
  if (waited.length) parts.push(`waited for you in ${waited.join(", ")}`);
  if (paused.length) parts.push(`paused in ${paused.join(", ")}`);
  if ((day?.you ?? []).some(([a, b]) => near(a, b))) parts.push("you were at it");
  return `${clockText(ms)}: ${parts.length ? parts.join(" · ") : "nothing went on"}`;
}
export const LANES_HINT = "Point at the chats to see what went on then; click a name to open its chat.";

// How many days before today's a day is (the Day's step back to it, from a day of the Week)
export function daysBack(day: string, now: number): number {
  const t = new Date(now);
  return Math.round((new Date(t.getFullYear(), t.getMonth(), t.getDate()).getTime() - localDate(day).getTime()) / 86400000);
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

// ---------------------------------------------------------------- your plan's limits over time
// (the Recap's Overall, last: week.py --limits; the same words as Plasma's
// WeekView.qml): how full each week got, the changes of the limits, and
// what a window holds (one estimate: the sizes, the share of the week, the
// tokens and the chart agree)

const FAMILIES = ["fable", "mythos", "opus", "sonnet", "haiku"];

// The windows as Your plan and the Chats tab's bars name them: "5-hour
// window", "Week", "Opus week" (a plan's weekly window of one model)
export function limitLabel(key: string): string {
  if (key === "five_hour") return "5-hour window";
  if (key === "seven_day") return "Week";
  const family = FAMILIES.find((f) => key.includes(f));
  return family ? `${family.charAt(0).toUpperCase()}${family.slice(1)} week` : key.replace(/_/g, " ");
}

// "24 Oct": a day of the section
export function limitDay(ms: number): string {
  const d = new Date(ms);
  return `${d.getDate()} ${MONTHS[d.getMonth()]}`;
}

// ---- how full your weeks got

// The weeks, newest first, and in all: how many ran out of the weeks that
// could have (not one counted only from later, unless it ran out), the
// fullest of those, the 5-hour windows that ran full of those used (all)
export function limitFit(a: Pick<LimitAccount, "weeks">): { weeks: LimitWeek[]; counted: number; ranOut: number; fullest: number; fiveFull: number; fiveUsed: number } {
  const weeks = [...(a.weeks ?? [])].reverse();
  const whole = weeks.filter((w) => !w.countedFrom || w.ranOutAt);
  return { weeks, counted: whole.length, ranOut: weeks.filter((w) => w.ranOutAt).length,
    fullest: Math.max(0, ...(whole.length ? whole : weeks).map((w) => w.pct)),
    fiveFull: weeks.reduce((n, w) => n + w.fiveFull, 0), fiveUsed: weeks.reduce((n, w) => n + w.fiveUsed, 0) };
}

// "Ran out in 1 of 4 weeks · 12 of 40 5-hour windows ran full"
export function limitFitText(a: Pick<LimitAccount, "weeks">): string {
  const f = limitFit(a);
  const parts = [f.ranOut ? `Ran out in ${f.ranOut} of ${plural(f.counted, "%1 week", "%1 weeks")}`
    : `No week ran out; the fullest got to ${Math.round(f.fullest)}%`];
  if (f.fiveUsed) parts.push(`${f.fiveFull} of ${f.fiveUsed} 5-hour windows ran full`);
  return parts.join(" · ");
}

export const LIMIT_FIT_TIP = "How full each week got: the highest reading of your plan's week Talpy Den kept (after a change of your limits " +
  "in it, since then). It ran out when the readings reached 100%, or when a usage limit stopped a chat until the week reset. A 5-hour " +
  "window ran full when its readings reached 100%, or when a limit stopped a chat as it ended. A week the weekly limit began during " +
  "(its readings begin later, at 0%) is counted from then, and is one of the weeks that could run out only if it did. These are your " +
  "plan's own readings: use on claude.ai, other computers and SSH hosts counts too.";

// A week's days: "3–10 Mar", "24 Feb – 3 Mar"
export function limitWeekLabel(w: Pick<LimitWeek, "from" | "until">): string {
  const a = new Date(w.from), b = new Date(w.until);
  return a.getMonth() === b.getMonth() ? `${a.getDate()}–${limitDay(w.until)}` : `${limitDay(w.from)} – ${limitDay(w.until)}`;
}

export function limitWeekPct(w: Pick<LimitWeek, "pct" | "now" | "ranOutAt">): string {
  return `${Math.round(w.pct)}%${w.now && !w.ranOutAt ? " so far" : ""}`;
}

// Under a week's bar: from when it was counted (the weekly limit began
// during it), when it ran out, and its 5-hour windows
export function limitWeekNote(w: LimitWeek): string {
  const parts: string[] = [];
  if (w.countedFrom) parts.push(`counted from ${WEEKDAYS[new Date(w.countedFrom).getDay()]} ${limitDay(w.countedFrom)}`);
  if (w.ranOutAt) parts.push(`ran out ${whenText(w.ranOutAt)}`);
  if (w.fiveUsed) parts.push(`${w.fiveFull} of ${w.fiveUsed} 5-hour windows full`);
  const text = parts.join(" · ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function limitWeekTip(w: LimitWeek): string {
  const from = w.countedFrom ? `${WEEKDAYS[new Date(w.countedFrom).getDay()]} ${limitDay(w.countedFrom)} ${clockText(w.countedFrom)}` : "";
  return (w.now ? `This week, going on: ${Math.round(w.pct)}% used so far; it resets ${whenText(w.until)}.`
    : `${Math.round(w.pct)}% of the week was used by its reset.`) +
    (from ? ` Its readings begin at 0% on ${from}: the weekly limit counted from then, so the days before aren't in its ${Math.round(w.pct)}%.` : "") +
    (w.ranOutAt ? ` It ran out on ${whenText(w.ranOutAt)}: chats waited for the reset, or went on another way.` : "") +
    (w.fiveUsed ? (w.fiveUsed === 1 ? ` ${w.fiveFull} of the 5-hour window begun in it ran full.`
      : ` ${w.fiveFull} of the ${w.fiveUsed} 5-hour windows begun in it ran full.`) : "");
}

// ---- changes of your limits

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

// "No change seen since 12 Mar." (the last change, or the first reading)
export function limitNoChangeText(a: Pick<LimitAccount, "events" | "since">, now: number): string {
  const events = a.events ?? [];
  return events.length ? `No change seen since ${limitDay(events[events.length - 1].at)}.`
    : `No change seen since ${limitDay(a.since ?? now)}, when the readings begin.`;
}

export const LIMIT_NO_CHANGE_TIP = "A change shows in the readings: the same use reads as a different share of a window from one reading " +
  "to the next, with nothing used between (a bigger or smaller plan, or Anthropic's change), or your windows' plan changed between two of them.";

// ---- what a window holds (estimates)

type LimitSize = { cost: number; lo?: number; hi?: number; n?: number; scaled?: number; rough?: boolean; how?: string };

// A window's size: "≈ $180" (one number when steady; "≈" as every estimate
// here), or, from too few windows or ones too far apart (rough), the range
// it rests on and how many ("$120–$170 · 5 windows")
export function limitValueText(key: string, v: LimitSize | null | undefined, cur: Currency = USD): { text: string; rough: boolean } {
  if (!v) return { text: limitMoney(0, cur), rough: false };
  if (!v.rough || v.lo === undefined || v.hi === undefined) return { text: `≈ ${limitMoney(v.cost, cur)}`, rough: false };
  const range = v.hi > v.lo ? `${limitMoney(v.lo, cur)}–${limitMoney(v.hi, cur)}` : limitMoney(v.cost, cur);
  return { text: range + (key === "five_hour" && v.n ? ` · ${plural(v.n, "%1 window", "%1 windows")}` : ""), rough: true };
}

// A size's tooltip: how it's worked out, in a sentence (and why a range)
export function limitSizeTip(key: string, a: LimitAccount): string {
  const v: LimitSize | null = key === "five_hour" ? a.now.fiveHour : a.now.weeks[key];
  if (!v) return "";
  const n = v.n ?? 1;
  const base = key === "five_hour"
    ? "What a full 5-hour window holds at API prices: each window's use on this computer by a reading, over the share of the window the " +
      "reading says was used. Use not seen here only makes a window look smaller, so it's the upper end of the " +
      `${plural(n, "%1 window", "%1 windows")} measured since your limits last changed (the middle of ${n === 1 ? "its" : "their"} largest third).`
    : key === "seven_day" && v.how === "share"
      ? `A full 5-hour window over its share of the week (from the readings): ${a.now.share ? Number((100 / a.now.share.pct).toFixed(1)) : ""} full 5-hour windows.`
      : `What a full ${limitLabel(key).toLowerCase()} holds at API prices: your use on this computer by its readings, over the share of it ` +
        `they say was used, ${n === 1 ? "from 1 week" : `the upper end of ${n} weeks`}.` + (key === "seven_day" ? "" : " Only that model's usage counts.");
  return base + (v.scaled ? `\nNone measured since your limits changed yet: what it held before, times ${Number(v.scaled.toFixed(2))}.` : "") +
    (v.rough ? (key === "five_hour"
      ? "\nToo few windows, or ones too far apart, for one number: use not seen here (claude.ai, your phone, other computers, SSH hosts) fills some windows more than others."
      : "\nIts readings tell sizes too far apart for one number: use not seen here (claude.ai, your phone, other computers, SSH hosts) counts in some of them.") : "");
}

// "A full 5-hour window moves the week 18%: 6 of them fill it · from the readings"
export function limitShareText(s: LimitShare | null | undefined): string {
  if (!s || !(s.pct > 0)) return "";
  const n = Math.max(1, Math.round(100 / s.pct));
  return s.how === "readings" ? `A full 5-hour window moves the week ${Math.round(s.pct)}%: ${n} of them fill it · from the readings`
    : `A full 5-hour window is ≈ ${Math.round(s.pct)}% of the week: ${n} of them fill it · from the sizes`;
}

export function limitShareTip(s: LimitShare | null | undefined): string {
  if (!s) return "";
  return s.how === "readings"
    ? `From the readings themselves: how far the week's reading moved while a 5-hour window filled, in the middle of ${plural(s.n ?? 0, "%1 window", "%1 windows")}. ` +
      "No prices: use not seen here moves both alike."
    : "From the two sizes, the 5-hour window's over the week's: too few windows told it from the readings yet." + (s.rough ? " One of them is a range, so this is rough." : "");
}

// How long a full 5-hour window lasts at your pace
export function limitFillText(fill: LimitPeriod["fill"]): string {
  if (!fill) return "";
  const work = fill.workMs >= 60000 ? ` · Claude worked ${hoursText(fill.workMs)} in it, across chats` : "";
  return (fill.wallMs <= 5 * 3600000 ? `A 5-hour window fills in ≈ ${hoursText(fill.wallMs)} at your pace`
    : "At your pace a 5-hour window doesn't fill in its 5 hours") + work;
}

export const LIMIT_FILL_TIP = "The middle of the windows measured: from a window's first request to its reading, over the share it says " +
  "was used, on the clock; Claude's work in it the same way, across the chats that worked at once.";

// "≈ 540M tokens fill a 5-hour window, in your mix"; its tooltip: the same
// in one model's output tokens or cache reads
export function limitTokensText(a: Pick<LimitAccount, "now">): string {
  const t = a.now.tokens;
  const n = t ? t.fresh + t.output + t.cacheRead : 0;
  return n > 0 ? `≈ ${shortCount(n)} tokens fill a 5-hour window, in your mix` : "";
}

export function limitTokensTip(a: Pick<LimitAccount, "equivalents">): string {
  const e = a.equivalents;
  const five: LimitTokens | null = e?.fiveHour ?? null;
  const week: LimitTokens | null = e?.week ?? null;
  return "Your mix: the tokens of the windows measured, by kind, scaled to what a window holds." +
    (e && five ? `\nIn ${e.model} output tokens alone: ≈ ${shortCount(five.output)} a 5-hour window (or ≈ ${shortCount(five.cacheRead)} cache reads)` +
      (week ? `; ≈ ${shortCount(week.output)} a week` : "") + "." : "");
}

// A window's size: whole amounts from 10 up ("$48", "€1,180"), as moneyText below
export function limitMoney(usd: number, cur: Currency = USD): string {
  const amount = (usd || 0) * cur.rate;
  if (amount < 10) return moneyText(usd, cur);
  const symbol = SYMBOLS[cur.code];
  const text = Math.round(amount).toLocaleString("en-US");
  return symbol ? symbol + text : `${text} ${cur.code}`;
}

// What fills a window: its parts (shares of their API price, each with its
// legend's words; by count, cache reads are nearly all of it)
export function limitMix(c: LimitPeriod["costs"] | undefined): {
  parts: { kind: "cacheRead" | "fresh" | "output"; share: number; label: string }[];
} {
  const total = c ? c.cacheRead + c.fresh + c.output : 0;
  if (!c || total <= 0) return { parts: [] };
  const names = { cacheRead: "cache reads", fresh: "new input and cache writes", output: "output" };
  return { parts: (["cacheRead", "fresh", "output"] as const).map((kind) => ({ kind, share: c[kind] / total,
    label: `${names[kind]} ${shareText(c[kind] / total)}` })) };
}

// The 5-hour windows' chart (x, y: 0 to 1): a dot each, at what it held over
// its limits' estimate (each stretch of the same limits on its own scale: a
// size of before a change is never drawn on the scale of after), a line at
// each estimate, a mark at each change; the older stretches dimmed. lo, hi:
// the newest stretch's dots' range; estimate: its line's
export function limitDots(a: LimitAccount, now: number, start?: number): {
  dots: { x: number; y: number; full: number; dim: boolean; tip: string }[];
  lines: { x1: number; x2: number; y: number; dim: boolean }[];
  marks: number[];
  lo: number;
  hi: number;
  estimate: number;
  older: LimitEra[];
} {
  const eras = a.eras ?? [];
  const from = start ?? (eras.length ? eras[0].from : now);
  const span = Math.max(1, now - from);
  const x = (ms: number) => Math.max(0, Math.min(1, (ms - from) / span));
  const est = (k: number) => eras[k]?.fiveHour?.cost ?? 0;
  const newest = eras.length - 1;
  const shown = a.windows.filter((w) => est(w.era ?? 0) > 0);
  // (from 0 to a little over the largest, at most 1.6 times an estimate: a wild one sits at the top)
  const top = Math.min(1.6, Math.max(1.15, ...shown.map((w) => (w.full / est(w.era ?? 0)) * 1.05)));
  const y = (v: number) => Math.min(1, v / top);
  const mine = shown.filter((w) => (w.era ?? 0) === newest).map((w) => w.full);
  return {
    dots: shown.map((w) => ({ x: x(w.at), y: y(w.full / est(w.era ?? 0)), full: w.full, dim: (w.era ?? 0) !== newest,
      tip: `${whenText(w.start)}: ${Math.round(w.pct)}% used by ${clockText(w.at)}` })),
    lines: eras.map((e, k) => ({ x1: x(e.from), x2: x(Math.min(e.until, now)), y: y(1), dim: k !== newest, k }))
      .filter((l) => est(l.k) > 0 && l.x2 > l.x1).map(({ k: _k, ...l }) => l),
    marks: (a.events ?? []).filter((e) => e.at > from && e.at <= now).map((e) => x(e.at)),
    lo: mine.length ? Math.min(...mine) : 0,
    hi: mine.length ? Math.max(...mine) : 0,
    estimate: est(newest),
    older: eras.slice(0, -1).filter((e) => e.fiveHour),
  };
}

// Over the chart: "Each 5-hour window since 12 Mar: $60–$195 · its line ≈ $180"
export function limitChartText(a: Pick<LimitAccount, "eras">, c: Pick<ReturnType<typeof limitDots>, "lo" | "hi" | "estimate">, cur: Currency = USD): string {
  const eras = a.eras ?? [];
  const since = eras.length > 1 ? ` since ${limitDay(eras[eras.length - 1].from)}` : "";
  return `Each 5-hour window${since}: ${c.hi > c.lo ? `${limitMoney(c.lo, cur)}–${limitMoney(c.hi, cur)}` : limitMoney(c.hi, cur)}` +
    (c.estimate ? ` · its line ≈ ${limitMoney(c.estimate, cur)}` : "");
}

export function limitChartTip(c: Pick<ReturnType<typeof limitDots>, "older" | "marks">, cur: Currency = USD): string {
  return "What each 5-hour window held by what this computer used (a dot each). Use not seen here makes a window look smaller, so the " +
    "estimate is the upper end of them (the line)." +
    (c.older.length ? ` Before your limits changed (dimmed), each stretch is drawn on its own scale: ${c.older
      .map((e) => `until ${limitDay(e.until)}, ≈ ${limitMoney(e.fiveHour!.cost, cur)}`).join(", ")}.` : "") +
    (c.marks.length ? " An orange line marks where your limits changed." : "");
}

// Where every account's chart begins: the earliest reading any of them has,
// so a day is at the same place in each
export function limitStart(accounts: LimitAccount[], now: number): number {
  const starts = accounts.map((a) => (a.eras?.length ? a.eras[0].from : a.periods.length ? a.periods[0].from : null)).filter((v): v is number => v !== null);
  return starts.length ? Math.min(...starts) : now;
}

// The window keys an account has, in the order the Chats tab lists them
export function limitKeys(a: LimitAccount): string[] {
  const order = ["five_hour", "seven_day", "seven_day_opus", "seven_day_sonnet"];
  const keys = ["five_hour", ...Object.keys(a.now.weeks)].filter((k) => k === "five_hour" ? a.now.fiveHour : a.now.weeks[k]);
  return keys.sort((p, q) => (order.indexOf(p) + 1 || 99) - (order.indexOf(q) + 1 || 99));
}

// The accounts the section shows: with weeks or windows measured
export function limitShown(h: LimitHistory | null): LimitAccount[] {
  return (h?.accounts ?? []).filter((a) => a.periods.length || a.weeks?.length);
}

// The section's last line: what it's made from and what it can't see (the
// SSH hosts the Recap reads, by name)
export function limitFootText(h: Pick<LimitHistory, "since">, hosts: string[] = []): string {
  return `Estimated from this computer's chats and the limit readings Talpy Den kept${h.since ? ` since ${limitDay(h.since)}` : ""}. ` +
    (hosts.length ? `Use on ${hosts.join(", ")} (SSH hosts), claude.ai, your phone or other computers` : "Use on claude.ai, your phone, other computers or SSH hosts") +
    " counts toward your limits but isn't seen here, so a window can look smaller than it is: the estimates go by the larger ones.";
}

export const LIMIT_EMPTY = "Not enough readings yet: a few 5-hour windows used past half tell how much one holds.";
