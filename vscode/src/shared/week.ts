// The Recap tab's words and numbers (webview/components/WeekView.tsx), from
// the recap of the widget's week.py; here, so the tests can read them.

import { clockText, dayLabel, plural } from "./model";
import type {
  LimitAccount, LimitChange, LimitEvent, LimitHistory, LimitPeriod, LimitTokens, WeekDay, WeekGrant, WeekNumbers, WeekPlanWindow, WeekRecap, WeekRule,
  WeekSpan, WeekSum,
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

// "Sat 24": a timeline row's day ("19 Oct": Overall's 7 days)
export function rowDay(day: string, weeks = false): string {
  return weeks ? shortDay(day) : dayLabel(day).split(" ").slice(0, 2).join(" ");
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
// front end): what Claude did; when (the day-by-day graph, your plan's
// limits now and, folded, the advanced analyses of them; chat by chat); where (by
// project, the chats it worked on most); then the money (at API prices,
// what could use less of your plan)
export const RECAP_SECTIONS = ["work", "days", "plan", "limits", "lanes", "projects", "chats", "models", "tips"] as const;
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
  const before = (v: number, kind: Kind) => (p ? `\n${beforeText}: ${shown(v, kind)}` : "");
  const weeks = (key: NumberKey, kind: Kind) => {
    const values = trendOf(recap, key);
    return values.length > 1
      ? `\n${trendText}: ${values.map((v) => (v === null ? "?" : shown(v, kind))).join(" · ")}`
      : "";
  };
  return [
    {
      label: "You",
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
      label: "Tokens",
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
        "Your plan isn't billed this way: this is the value of what you used." + before(p ? p.cost : 0, "money") + weeks("cost", "money"),
      trend: trendOf(recap, "cost"),
    },
  ];
}

// What the tokens were: all that Claude read and wrote, by kind
function tokensText(t: WeekSum["tokens"]): string {
  return `Everything Claude read and wrote: ${shortCount(t.input)} of new input, ${shortCount(t.cacheRead)} read from the cache, ` +
    `${shortCount(t.cacheWrite5m + t.cacheWrite1h)} written to the cache and ${shortCount(t.output)} that Claude wrote.`;
}

export function factsText(s: WeekSum): string {
  const parts: string[] = [];
  if (s.longestTurn && s.longestTurn.workedMs >= 60000) parts.push(`longest turn ${hoursText(s.longestTurn.workedMs)} (${s.longestTurn.name || "?"})`);
  if (s.peakAtOnce > 1) parts.push(`up to ${s.peakAtOnce} chats at once`);
  if (s.busiestDay) parts.push(`busiest day ${WEEKDAYS_LONG[localDate(s.busiestDay).getDay()]}`);
  if (s.limits) parts.push(s.limits === 1 ? "a usage limit stopped you once" : `usage limits stopped you ${s.limits} times`);
  return parts.join(" · ");
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

export function dayTip(d: WeekDay, cur: Currency = USD): string {
  return (
    `${d.to ? `${monthDay(d.day)} – ${monthDay(d.to)}` : longDay(d.day)}\nYou: ${hoursText(d.youMs)} · Claude worked ${hoursText(d.workedMs)} (on the clock ${hoursText(d.busyMs)}) · ` +
    `it waited ${hoursText(d.waitMs)} for you\n${plural(d.prompts, "%1 prompt", "%1 prompts")} · ${shortCount(d.tokenTotal)} tokens · ${moneyText(d.cost, cur)} at API prices` +
    (d.chats?.length ? "\nClick for its chats" : "")
  );
}

export function cacheText(recap: WeekRecap): string {
  const t = recap.sum.tokens;
  const input = t.input + t.cacheRead + t.cacheWrite5m + t.cacheWrite1h;
  if (!t.cacheRead) return "";
  const pct = Math.round((100 * t.cacheRead) / Math.max(1, input));
  return `${pct}% of the ${shortCount(input)} input tokens came from the cache: it saved ${moneyText(recap.cacheSaved, currencyOf(recap))}. ` +
    `Claude wrote ${shortCount(t.output)} tokens.`;
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

// A tip's icon (icons.mjs meanings, as Plasma's): the time chats waited for
// you, usage limits, else a tip of Claude Code's /usage
export function tipMeaning(key: string): "tipWaits" | "tipLimits" | "tip" {
  return key === "waits" ? "tipWaits" : key === "limits" ? "tipLimits" : "tip";
}

// What Claude did, in a line: its tool calls, commands, edits, subagents
export function workText(w: WeekRecap["work"] | undefined): string {
  if (!w || !w.toolCalls) return "";
  const n = (v: number, one: string, many: string) => (v === 1 ? one : many).replace("%1", count(v));
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

export function toolsText(w: WeekRecap["work"] | undefined): string {
  return w && w.tools.length ? `Its tools: ${w.tools.map(([name, n]) => `${name} ${count(n)}`).join(" · ")}` : "";
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
  if (!granted.length) return `Nothing lets chats on ${host || "this computer"} skip a permission prompt: they ask you each time.`;
  return host
    ? `What lets chats on ${host} go without asking you, as listed there: its settings, its trusted folders, and the .claude ` +
      `settings of the folders Claude ran in. Revoke takes one out of its file on ${host}.`
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

// The SSH host a permission message is for: a plain name or "" (this
// computer); the extension acts on it only if it's one of the hosts shown
export function permsHost(host: unknown): string | null {
  if (host === undefined || host === "") return "";
  return typeof host === "string" && /^[A-Za-z0-9_.@-]{1,255}$/.test(host) && !host.startsWith("-") ? host : null;
}

export function ruleMeta(r: WeekRule): string {
  return [plural(r.count, "%1 prompt", "%1 prompts"), r.waitMs >= 60000 ? `waited ${hoursText(r.waitMs)} for you` : "", `e.g. ${r.example}`]
    .filter(Boolean).join(" · ");
}

export function coldText(recap: WeekRecap): string {
  const cold = recap.spend?.cold;
  if (!cold || !cold.count) return "";
  const cur = currencyOf(recap);
  const most = cold.chats.map((c) => `${c.name} (${c.resumes ?? 0}×, ${moneyText(c.cost, cur)})`).join(", ");
  return (cold.count === 1
    ? "You came back to a chat after its cache had expired (an hour without a reply) once: writing its context again cost " +
      `${moneyText(cold.cost, cur)} more than reading it from the cache.`
    : `You came back to chats after their cache had expired (an hour without a reply) ${cold.count} times: writing their ` +
      `context again cost ${moneyText(cold.cost, cur)} more than reading it from the cache.`) + (most ? ` Most in: ${most}.` : "");
}

export function footText(recap: WeekRecap): string {
  const hosts = recap.sources.filter((s) => s.host && s.ok).map((s) => s.host);
  const guessed = recap.prices.guessed.length ? ` (${recap.prices.guessed.join(", ")} at the price of its family's newest model)` : "";
  const lines = [
    `Read from the chats on this computer${hosts.length ? ` and on ${hosts.join(", ")}` : ""}, without using any tokens. ` +
      `Prices: Claude's API list prices of ${dateText(recap.prices.asOf)}${guessed}.`,
  ];
  const c = recap.currency;
  if (c?.error) lines.push(`Amounts in US dollars: ${c.error}.`);
  else if (c && c.code !== "USD" && c.date)
    lines.push(`Amounts in ${c.code} at the European Central Bank's rate of ${dateText(c.date)}: 1 USD = ${c.rate.toFixed(4)} ${c.code}.`);
  for (const s of recap.sources) if (!s.ok) lines.push(`${s.host} couldn't be read: ${s.error}`);
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
  return "too few readings to compare yet";
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
export function limitShareText(pct: number): string {
  return pct > 0 ? `${Math.round(pct)}% of the week · about ${Math.max(1, Math.round(100 / pct))} full windows a week` : "";
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

// What filled a window: its parts (shares of all its tokens) and the line for them
export function limitMix(t: LimitPeriod["tokens"]): { parts: { kind: "cacheRead" | "fresh" | "output"; share: number }[]; text: string } {
  const total = t ? t.cacheRead + t.fresh + t.output : 0;
  if (!t || total <= 0) return { parts: [], text: "" };
  const parts = (["cacheRead", "fresh", "output"] as const).map((kind) => ({ kind, share: t[kind] / total }));
  return {
    parts,
    text: `${shortCount(total)} tokens filled one: ${shareText(parts[0].share)} cache reads, ` +
      `${shareText(parts[1].share)} new input and cache writes, ${shareText(parts[2].share)} output`,
  };
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
export function limitDots(a: LimitAccount, now: number): {
  dots: { x: number; y: number; full: number; tip: string }[];
  medians: { x1: number; x2: number; y: number }[];
  marks: number[]; // (x of each change of the limits)
  lo: number;
  top: number;
} {
  const from = a.periods.length ? a.periods[0].from : now;
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
export function limitWeekBars(a: LimitAccount): { from: number; cost: number; h: number; partial: boolean }[] {
  const weeks = a.periods.filter((p) => p.weeks.seven_day);
  const top = Math.max(1e-9, ...weeks.map((p) => p.weeks.seven_day.cost));
  return weeks.map((p) => ({ from: p.from, cost: p.weeks.seven_day.cost, h: p.weeks.seven_day.cost / top, partial: !!p.weeks.seven_day.partial }));
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
  const scaled = (key === "five_hour" ? a.now.fiveHour?.scaled : a.now.weeks[key]?.scaled) ?? null;
  const since = scaled ? `\nNone measured since your limits changed yet: what it held before, times ${Number(scaled.toFixed(2))}.` : "";
  if (key === "five_hour") {
    const f = a.now.fiveHour;
    return f ? `What a full 5-hour window held: the API price of what your chats used by a reading, over the share of the window ` +
      `it said was used. The middle of ${plural(f.n, "%1 window", "%1 windows")} in the newest week` +
      (f.n > 1 ? ` (${moneyText(f.lo, cur)} to ${moneyText(f.hi, cur)})` : "") + "." + since : "";
  }
  return `What a full ${limitLabel(key).toLowerCase()} held: the API price of what your chats used by its readings, over the ` +
    `share of it they said was used` + (key === "seven_day" ? "." : ` (only that model's usage counts).`) + since;
}
