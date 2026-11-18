// The Recap's plan limits over time (WeekView.qml, week.py --limits): the
// chart's places and the parts of what fills a window, as VS Code's
// src/shared/week.ts works them out. The words are WeekView.qml's
// (translated there).

const ORDER = ["five_hour", "seven_day", "seven_day_opus", "seven_day_sonnet"]
export const FAMILIES = ["fable", "mythos", "opus", "sonnet", "haiku"]

// The model family in a window's key ("seven_day_opus": "opus"), or ""
export function family(key) {
    return FAMILIES.find(f => String(key).includes(f)) || ""
}

// The 5-hour windows' chart (x, y: 0 to 1): a dot each, at what it held
// over what its limits' estimate is (each stretch of the same limits on its
// own scale: a size of before a change is never drawn on the scale of
// after), a line at each estimate, a mark at each change; the older
// stretches dimmed. now: the newest stretch's dots' range and estimate.
export function dots(a, now, start = null) {
    const eras = a.eras || []
    const from = start !== null ? start : eras.length ? eras[0].from : now
    const span = Math.max(1, now - from)
    const x = ms => Math.max(0, Math.min(1, (ms - from) / span))
    const est = k => eras[k] && eras[k].fiveHour ? eras[k].fiveHour.cost : 0
    const newest = eras.length - 1
    const shown = a.windows.filter(w => est(w.era) > 0)
    // (from 0 to a little over the largest, at most 1.6 times an estimate: a wild one sits at the top)
    const top = Math.min(1.6, Math.max(1.15, ...shown.map(w => w.full / est(w.era) * 1.05)))
    const y = v => Math.min(1, v / top)
    const mine = shown.filter(w => w.era === newest).map(w => w.full)
    return {
        dots: shown.map(w => ({ x: x(w.at), y: y(w.full / est(w.era)), full: w.full, dim: w.era !== newest })),
        lines: eras.map((e, k) => ({ x1: x(e.from), x2: x(Math.min(e.until, now)), y: y(1), dim: k !== newest, k }))
                   .filter(l => est(l.k) > 0 && l.x2 > l.x1),
        marks: (a.events || []).filter(e => e.at > from && e.at <= now).map(e => x(e.at)),
        lo: mine.length ? Math.min(...mine) : 0,
        hi: mine.length ? Math.max(...mine) : 0,
        estimate: est(newest),
        older: eras.slice(0, -1).filter(e => e.fiveHour),
    }
}

// Where every account's chart begins: the earliest reading any of them has,
// so a day is at the same place in each
export function start(accounts, now) {
    const starts = accounts.map(a => a.eras && a.eras.length ? a.eras[0].from : a.periods.length ? a.periods[0].from : null)
                           .filter(v => v !== null)
    return starts.length ? Math.min(...starts) : now
}

// The window keys an account has, in the order the Chats tab lists them
export function keys(a) {
    const found = ["five_hour", ...Object.keys(a.now.weeks)].filter(k => k === "five_hour" ? a.now.fiveHour : a.now.weeks[k])
    return found.sort((p, q) => (ORDER.indexOf(p) + 1 || 99) - (ORDER.indexOf(q) + 1 || 99))
}

// A window's size now ({cost, scaled, rough, …})
export function size(a, key) {
    return key === "five_hour" ? a.now.fiveHour : a.now.weeks[key]
}

// What filled a window: its parts, shares of their API price (costs: week.py's
// now.costs; by count, cache reads are nearly all of it), and how many tokens
export function mix(costs, tokens) {
    const total = costs ? costs.cacheRead + costs.fresh + costs.output : 0
    if (!costs || total <= 0)
        return { parts: [], total: 0, tokens: 0 }
    return { parts: ["cacheRead", "fresh", "output"].map(kind => ({ kind, share: costs[kind] / total })), total,
             tokens: tokens ? tokens.cacheRead + tokens.fresh + tokens.output : 0 }
}

// The middle of a change's factors (each window's), or null (a plan change no reading saw)
export function eventFactor(e) {
    const fs = Object.values(e.factors || {}).sort((p, q) => p - q)
    return fs.length ? fs[Math.floor((fs.length - 1) / 2)] : null
}

// How full each week got, newest first, and in all: the weeks that ran
// out of those that could have (not one counted only from later, unless
// it ran out), the fullest of those, the 5-hour windows that ran full of
// those used (all)
export function fit(a) {
    const weeks = (a.weeks || []).slice().reverse()
    const whole = weeks.filter(w => !w.countedFrom || w.ranOutAt)
    return { weeks, counted: whole.length, ranOut: weeks.filter(w => w.ranOutAt).length,
             fullest: Math.max(0, ...(whole.length ? whole : weeks).map(w => w.pct)),
             fiveFull: weeks.reduce((n, w) => n + w.fiveFull, 0), fiveUsed: weeks.reduce((n, w) => n + w.fiveUsed, 0) }
}
