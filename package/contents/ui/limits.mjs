// The Recap's Advanced analyses (WeekView.qml, week.py --limits): the
// charts' places and the parts of what filled a window, as VS Code's
// src/shared/week.ts and GNOME's logic.js work them out. The words are
// WeekView.qml's (translated there).

const ORDER = ["five_hour", "seven_day", "seven_day_opus", "seven_day_sonnet"]
export const FAMILIES = ["fable", "mythos", "opus", "sonnet", "haiku"]

// The model family in a window's key ("seven_day_opus": "opus"), or ""
export function family(key) {
    return FAMILIES.find(f => String(key).includes(f)) || ""
}

// The dots of the 5-hour windows (x, y: 0 to 1), each week's median and each
// change of the limits, over the weeks kept; from a little under the
// smallest to a little over the largest
export function dots(a, now, start = null) {
    const from = start !== null ? start : a.periods.length ? a.periods[0].from : now
    const span = Math.max(1, now - from)
    const sizes = [...a.windows.map(w => w.full), ...a.periods.map(p => p.fiveHour ? p.fiveHour.cost : NaN)].filter(v => v > 0)
    const most = sizes.length ? Math.max(...sizes) : 1
    const least = sizes.length ? Math.min(...sizes) : 0
    const pad = Math.max((most - least) * 0.15, most * 0.05)
    const lo = Math.max(0, least - pad)
    const top = most + pad
    const x = ms => Math.max(0, Math.min(1, (ms - from) / span))
    const y = v => (v - lo) / (top - lo)
    return {
        dots: a.windows.map(w => ({ x: x(w.at), y: y(w.full), full: w.full })),
        medians: a.periods.filter(p => p.fiveHour).map(p => ({ x1: x(p.from), x2: x(Math.min(p.until, now)), y: y(p.fiveHour.cost) })),
        marks: (a.events || []).filter(e => e.at > from && e.at <= now).map(e => x(e.at)),
        lo,
        top,
    }
}

// The weeks' bars (the main weekly window) on the same time line as the
// dots (x1, x2: 0 to 1, from start to now), height 0 to 1 of the largest
export function weekBars(a, now, start = null) {
    const from = start !== null ? start : a.periods.length ? a.periods[0].from : now
    const span = Math.max(1, now - from)
    const x = ms => Math.max(0, Math.min(1, (ms - from) / span))
    const weeks = a.periods.filter(p => p.weeks.seven_day)
    const top = Math.max(1e-9, ...weeks.map(p => p.weeks.seven_day.cost))
    return weeks.map(p => ({ from: p.from, cost: p.weeks.seven_day.cost, x1: x(p.from), x2: x(Math.min(p.until, now)),
                             h: p.weeks.seven_day.cost / top, partial: !!p.weeks.seven_day.partial }))
}

// Where every account's charts begin: the earliest week any of them has, so
// a day is at the same place in each
export function start(accounts, now) {
    const starts = accounts.filter(a => a.periods.length).map(a => a.periods[0].from)
    return starts.length ? Math.min(...starts) : now
}

// The window keys an account has, in the order the Chats tab lists them
export function keys(a) {
    const found = ["five_hour", ...Object.keys(a.now.weeks)].filter(k => k === "five_hour" ? a.now.fiveHour : a.now.weeks[k])
    return found.sort((p, q) => (ORDER.indexOf(p) + 1 || 99) - (ORDER.indexOf(q) + 1 || 99))
}

// A window's size now ({cost, scaled}) and its change
export function now(a, key) {
    return { value: key === "five_hour" ? a.now.fiveHour : a.now.weeks[key], change: a.changes[key === "five_hour" ? "fiveHour" : key] }
}

// What filled a window: its parts, shares of all its tokens
export function mix(t) {
    const total = t ? t.cacheRead + t.fresh + t.output : 0
    if (!t || total <= 0)
        return { parts: [], total: 0 }
    return { parts: ["cacheRead", "fresh", "output"].map(kind => ({ kind, share: t[kind] / total })), total }
}

// The middle of a change's factors (each window's), or null (a plan change no reading saw)
export function eventFactor(e) {
    const fs = Object.values(e.factors || {}).sort((p, q) => p - q)
    return fs.length ? fs[Math.floor((fs.length - 1) / 2)] : null
}

// Is a change one to show as bad (the window holds less)?
export function bad(c) {
    return !!c && ((c.kind === "change" && (c.pct || 0) < 0) || (c.kind === "limits" && (c.factor || 1) < 0.9))
}
