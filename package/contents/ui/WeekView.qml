import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import QtCore
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.extras as PlasmaExtras
import org.kde.kirigami as Kirigami
import "hub"
import "icons.mjs" as Icons
import "limits.mjs" as Limits

// The Recap tab (main.qml: loadWeek, week.py): your last 7 days with Claude,
// as a story: the big picture (how long you were at it, how long Claude
// worked, your prompts, its tokens, the API prices), when (a day per row on
// a timeline, the day chat by chat), what got done (by project, its chats
// with their commits and Claude's recaps, and what Claude did in all), what
// it meant for your plan, where the usage went (by model at API prices,
// then as your plan's limits count it) and what would make it use less of
// your plan (the rules of Claude Code's own /usage, each with what acts on
// it); in Overall, last, your plan's limits over time. All of it read from
// the chat transcripts: no tokens, nothing sent.
PlasmaComponents3.ScrollView {
    id: view

    readonly property var recap: root.weekRecap
    readonly property string span: root.weekSpan   // the one picked (its answer may still come)
    readonly property bool weeks: !!recap && (recap.span === "month" || recap.span === "all")   // a row per 7 days, with their numbers
    readonly property var days: recap ? recap.days : []
    readonly property var sum: recap ? recap.sum : null
    readonly property var previous: recap && recap.previous && (recap.previous.workedMs || recap.previous.prompts
                                                                  || recap.previous.cost) ? recap.previous : null
    readonly property var accounts: recap ? recap.accounts : []
    readonly property var projects: recap ? recap.projects : []
    readonly property var models: recap ? recap.models : []
    readonly property var lanes: recap && recap.lanes ? recap.lanes : []   // (the Day view: chat by chat)
    // The Day with chats: one timeline (the lanes, with the day's own on top)
    // and the chats' numbers at their lanes' ends, rather than the day's row
    // saying it again
    readonly property bool dayLanes: !!recap && recap.span === "day" && lanes.length > 0
    readonly property var tips: recap ? recap.tips : []
    readonly property var trend: recap && recap.trend ? recap.trend : []
    // (today isn't over: the days before are counted up to this time of day)
    readonly property bool sameTime: !!recap && !!recap.sameTime
    readonly property var plan: recap && recap.plan ? recap.plan : []
    readonly property var spend: recap && recap.spend ? recap.spend : null
    readonly property var work: recap && recap.work ? recap.work : null
    readonly property var currency: recap && recap.currency ? recap.currency : ({ code: "USD", rate: 1, date: "", error: "" })
    readonly property bool hasData: !!sum && (sum.workedMs > 0 || sum.prompts > 0 || sum.cost > 0)
    readonly property real maxProject: Math.max(1, ...projects.map(p => p.workedMs))
    readonly property real weekMax: Math.max(1, ...days.map(d => Math.max(d.youMs, d.workedMs)))   // (Overall's busiest 7 days)
    readonly property real gu: Kirigami.Units.gridUnit
    property string openDay: ""       // the day whose chats are unfolded
    property string openProject: ""   // the project folder whose chats are unfolded: host|path

    // One hue for Claude's work (darker where several chats ran at once), the
    // text color for you, orange (as for a chat that needs you) for Claude
    // waiting on your answer
    readonly property color ink: Kirigami.Theme.textColor
    readonly property color grid: Qt.rgba(ink.r, ink.g, ink.b, 0.12)
    readonly property color youColor: Qt.rgba(ink.r, ink.g, ink.b, 0.45)
    readonly property color track: Qt.rgba(ink.r, ink.g, ink.b, 0.15)   // (a bar's, as an account's busiest folders')
    readonly property color workColor: Kirigami.Theme.focusColor
    readonly property color waitColor: Kirigami.Theme.neutralTextColor
    readonly property color limitColor: Kirigami.Theme.negativeTextColor

    readonly property real dayWidth: weeks ? Math.max(gu * 3.4, widest(days.map(d => rowLabel(d))) + Kirigami.Units.smallSpacing) : gu * 2.6

    // A timeline row's day ("Thu 5"), or the days of a row of 7 ("23–29 Oct",
    // "30 Oct – 5 Nov"; a month's oldest row and everything's fewer: "7–8 Oct")
    function rowLabel(d) {
        if (!d || !d.day)
            return ""
        if (!weeks)
            return Qt.locale().toString(date(d.day), "ddd d")
        const a = date(d.day), b = date(d.to || d.day)
        if (a.getTime() === b.getTime())
            return Qt.locale().toString(a, "d MMM")
        return a.getMonth() === b.getMonth()
             ? i18nc("from day – to day of one month", "%1–%2", Qt.locale().toString(a, "d"), Qt.locale().toString(b, "d MMM"))
             : i18nc("from day – to day", "%1 – %2", Qt.locale().toString(a, "d MMM"), Qt.locale().toString(b, "d MMM"))
    }
    readonly property real numWidth: gu * 2.9
    readonly property real youHeight: Math.round(gu * 0.25)
    readonly property real workHeight: Math.round(gu * 0.5)
    readonly property real laneGap: Math.round(gu * 0.15)
    property var hover: null   // what the mouse points at on the timeline: {row, x, ms}
    property string copied: ""   // a tip's command just copied

    readonly property var emptyDay: ({ day: "", start: 0, end: 1, you: [], work: [], wait: [], limits: [], youMs: 0,
                                       workedMs: 0, busyMs: 0, waitMs: 0, prompts: 0, cost: 0, chats: [] })
    readonly property var emptyProject: ({ name: "", path: "", host: "", workedMs: 0, cost: 0, prompts: 0, chats: [],
                                           chatCount: 0 })
    readonly property var emptyWindow: ({ key: "", label: "", resetsAt: 0, pct: 0, points: [] })
    readonly property var emptyModel: ({ model: "", cost: 0, tokens: 0, requests: 0, share: 0 })
    readonly property var emptyChat: ({ name: "", chatId: "", host: "", profileDir: "", folder: "", workedMs: 0, cost: 0,
                                        prompts: 0 })
    readonly property var emptyTip: ({ key: "", pct: null, title: "", detail: "", command: "" })

    // Fixed implicit size, as the Chats tab's list: deriving it from the
    // content would loop through the popup's width
    implicitWidth: gu * 28
    implicitHeight: gu * 26
    contentWidth: availableWidth
    contentHeight: sheet.implicitHeight
    PlasmaComponents3.ScrollBar.horizontal.policy: PlasmaComponents3.ScrollBar.AlwaysOff

    // What a plan window's bar says beside it: "45% · resets 20:10"
    function planText(win) {
        // (one past its reset, week.py plan_windows: "reset", as on the Chats tab)
        return Math.round(win.pct) + "%" + (win.reset ? " · " + i18n("reset") : win.resetsAt ? " · " + resetText(win.resetsAt) : "")
    }

    // 3h 05m, 45m: a week of work reads better in hours than in days
    function hours(ms) {
        const m = Math.round(Math.max(0, ms) / 60000)
        return m < 60 ? i18nc("duration in minutes", "%1m", m)
                      : i18nc("duration in hours and minutes", "%1h %2m", Math.floor(m / 60), m % 60)
    }

    // An amount of US dollars in the currency picked in the settings (week.py
    // sends the European Central Bank's rate of the day)
    readonly property var symbols: ({ USD: "$", EUR: "€", GBP: "£", JPY: "¥", CNY: "¥", INR: "₹", KRW: "₩", ILS: "₪",
                                      TRY: "₺", PHP: "₱", THB: "฿" })
    readonly property var wholeUnits: ["JPY", "KRW", "HUF", "ISK", "IDR"]

    function money(usd) {
        const amount = (usd || 0) * currency.rate
        const symbol = symbols[currency.code]
        const put = text => symbol ? symbol + text : text + " " + currency.code
        if (!amount)
            return put("0")
        const whole = amount >= 100 || wholeUnits.indexOf(currency.code) >= 0
        if (amount < (whole ? 1 : 0.01))
            return "<" + put(whole ? "1" : Number(0.01).toLocaleString(Qt.locale(), "f", 2))
        return put(Number(amount).toLocaleString(Qt.locale(), "f", whole ? 0 : 2))
    }

    function count(n) {
        return Number(n || 0).toLocaleString(Qt.locale(), "f", 0)
    }

    // A model's part of the whole: "<1%", ">99%" (not a rounded "100%"
    // beside another's "<1%"), as an account's models on the Chats tab
    function shareText(share) {
        return share <= 0 ? "0%" : share < 0.01 ? "<1%" : share > 0.99 && share < 1 ? ">99%" : Math.round(share * 100) + "%"
    }

    // What a list's lines say at their end, and the room the widest takes
    // (the column every line of the list gets: their bars or names all as
    // long, the numbers right-aligned)
    function numbersOf(row) {
        return hours(row.workedMs) + " · " + money(row.cost)
    }
    function modelNumbers(m) {
        return (m.guessed ? "≈ " : "") + money(m.cost) + " · " + shareText(m.share)
    }
    // A model with no list price yet: priced as the newest of its family
    function guessedModelTip(m) {
        return m.pricedAs ? i18n("%1 has no list price yet: it's priced as %2, the newest model of its family, so its amount is a guess.", m.model, m.pricedAs)
                          : i18n("%1 has no list price: it isn't in the amounts.", m.model)
    }
    // How much of the amount rests on a guessed price, for the cost tile's tooltip
    function guessedCostText() {
        const p = recap && recap.prices ? recap.prices : null
        if (!p || !p.guessedCost || !sum || !sum.cost)
            return ""
        return "\n" + i18n("%1 of it (%2) is priced by a guess: %3 has no list price yet, so it's at the price of the newest model of its family.",
                           money(p.guessedCost), shareText(p.guessedCost / sum.cost), p.guessed.join(", "))
    }
    function whereOf(chat) {
        return (chat.host ? root.hostLabel(chat.host) + ": " : "") + (chat.folder || "")
    }
    function widest(texts) {
        return Math.ceil(Math.max(0, ...texts.map(t => smallMetrics.advanceWidth(t)))) + 1
    }
    readonly property real projectNumbersWidth: widest(projects.map(projectNumbers))
    readonly property real projectDoneWidth: Math.min(gu * 7, widest(projects.map(doneText)))   // (1 when none got any)

    // 412.3M, 8.1k
    function tokens(n) {
        return root.formatTokens(n || 0)
    }

    // A number of the tiles, in its own unit
    function shown(value, kind) {
        return kind === "time" ? hours(value) : kind === "money" ? money(value) : kind === "tokens" ? tokens(value)
             : kind === "points" ? pointsText(value) : count(value)
    }

    // ---------------------------------------------------------------- your plan's limits over time
    // Overall's last section (week.py --limits, main.qml: loadLimits): the
    // same words as VS Code's src/shared/week.ts and GNOME's logic.js; the
    // charts' places from limits.mjs. Its numbers are asked for only once it
    // scrolls into view (the view's place against the section's: no timer),
    // again for another account and after a Refresh or the tab's 10-minute
    // read (root.limitsRound), never when the tab opens or the span changes
    // (y 0: not placed by the page's layout yet, its height its own: it never comes first)
    readonly property bool limitsInView: limitsSection.visible && limitsSection.y > 0
        && contentItem.contentY + height > page.y + limitsSection.y
        && contentItem.contentY < page.y + limitsSection.y + limitsSection.height
    readonly property string limitsWant: limitsInView ? root.weekAccount + "|" + root.limitsRound : ""
    onLimitsWantChanged: {
        if (limitsWant !== "" && limitsWant !== root.limitsAskedFor)
            root.loadLimits()
    }
    // (the last answer: while another is on its way, or it's another account's, dimmed)
    readonly property var limitsData: root.limitsData
    readonly property bool limitsDim: !!root.limitsData && (root.limitsBusy || root.limitsAccount !== root.weekAccount)
    readonly property var limitsShown: limitsData ? limitsData.accounts.filter(a => a.periods.length || (a.weeks && a.weeks.length)) : []
    readonly property bool limitsCompared: limitsShown.length > 1 && new Set(limitsShown.map(a => a.plan)).size > 1
    readonly property real limitsNow: limitsData ? limitsData.generatedAt : 0
    readonly property real limitsStart: Limits.start(limitsShown, limitsNow)
    readonly property var emptyLimits: ({ id: "", name: "", plan: "", periods: [], windows: [], events: [], changes: {},
                                          now: { fiveHour: null, share: null, fill: null, tokens: null, weeks: {} },
                                          equivalents: null, eras: [], weeks: [], since: 0 })
    readonly property var emptyLimitWeek: ({ from: 0, until: 0, pct: 0, ranOutAt: null, fiveFull: 0, fiveUsed: 0, now: false })

    // The windows as Your plan and the Chats tab's bars name them: "5-hour
    // window", "Week", "Opus week" (a plan's weekly window of one model)
    function limitLabel(key) {
        if (key === "five_hour")
            return i18n("5-hour window")
        if (key === "seven_day")
            return i18n("Week")
        const f = Limits.family(key)
        return f ? i18nc("a plan's weekly window of one model", "%1 week", f.charAt(0).toUpperCase() + f.slice(1))
                 : String(key).replace(/_/g, " ")
    }
    function limitDay(ms) {
        return Qt.locale().toString(new Date(ms), "d MMM")
    }

    // ---- how full your weeks got
    // "Ran out in 1 of 4 weeks · 12 of 40 5-hour windows ran full"
    function limitFitText(a) {
        const f = Limits.fit(a)
        const parts = [f.ranOut ? i18n("Ran out in %1 of %2", f.ranOut, i18np("%1 week", "%1 weeks", f.weeks.length))
                                : i18n("No week ran out; the fullest got to %1%", Math.round(f.fullest))]
        if (f.fiveUsed)
            parts.push(i18n("%1 of %2 5-hour windows ran full", f.fiveFull, f.fiveUsed))
        return parts.join(" · ")
    }
    function limitFitTip() {
        return i18n("How full each week got: the highest reading of your plan's week Talpy Den kept (after a change of your limits in it, since then). It ran out when the readings reached 100%, or when a usage limit stopped a chat until the week reset. A 5-hour window ran full when its readings reached 100%, or when a limit stopped a chat as it ended.")
               + " " + i18n("These are your plan's own readings: use on claude.ai, other computers and SSH hosts counts too.")
    }
    // A week's days: "3–10 Mar", "24 Feb – 3 Mar"
    function limitWeekLabel(w) {
        const a = new Date(w.from), b = new Date(w.until)
        return a.getMonth() === b.getMonth() ? i18nc("a week's days: 10–17 Nov", "%1–%2", a.getDate(), limitDay(w.until))
                                             : i18nc("a week's days across months", "%1 – %2", limitDay(w.from), limitDay(w.until))
    }
    function limitWeekPct(w) {
        return w.now && !w.ranOutAt ? i18nc("a week's use going on", "%1 so far", Math.round(w.pct) + "%") : Math.round(w.pct) + "%"
    }
    // Under a week's bar: when it ran out, and its 5-hour windows
    function limitWeekNote(w) {
        const parts = []
        if (w.ranOutAt)
            parts.push(i18n("ran out %1", whenText(w.ranOutAt)))
        if (w.fiveUsed)
            parts.push(i18n("%1 of %2 5-hour windows full", w.fiveFull, w.fiveUsed))
        const text = parts.join(" · ")
        return text.charAt(0).toUpperCase() + text.slice(1)
    }
    function limitWeekTip(w) {
        return (w.now ? i18n("This week, going on: %1 used so far; it resets %2.", Math.round(w.pct) + "%", whenText(w.until))
                      : i18n("%1 of the week was used by its reset.", Math.round(w.pct) + "%"))
               + (w.ranOutAt ? " " + i18n("It ran out on %1: chats waited for the reset, or went on another way.", whenText(w.ranOutAt)) : "")
               + (w.fiveUsed ? " " + i18np("%2 of the 5-hour window begun in it ran full.", "%2 of the %1 5-hour windows begun in it ran full.",
                                           w.fiveUsed, w.fiveFull) : "")
    }

    // ---- changes of your limits
    // "4 Nov 18:52 · your limits grew about 5× · Pro → Max 5×"
    function limitEventText(e) {
        const f = Limits.eventFactor(e)
        const what = f === null ? i18n("your plan changed")
                   : f >= 1.5 ? i18n("your limits grew about %1×", Number(f.toFixed(1)))
                   : Math.abs(f - 1) < 0.1 ? i18n("your limits stayed about the same")
                   : f > 1 ? i18n("your limits grew %1%", Math.round((f - 1) * 100))
                   : i18n("your limits shrank %1%", Math.round((1 - f) * 100))
        const plans = e.from && e.to && e.from !== e.to ? " · " + e.from + " → " + e.to
                    : !e.from && e.to ? " · " + i18nc("the plan now", "now %1", e.to) : ""
        return limitDay(e.at) + " " + root.clockText(e.at) + " · " + what + plans
    }
    function limitEventTip(e) {
        const ks = Object.keys(e.factors || {})
        return ks.length ? ks.map(k => i18n("%1: %2× what it held", limitLabel(k), Number(e.factors[k].toFixed(2)))).join("\n")
                           + "\n" + i18n("From your readings at that moment: the same usage read as a different share of the window.")
                         : i18n("Your windows' plan changed between two of them: what they held before and after tells by how much.")
    }
    // "No change seen since 12 Mar" (the last change, or the first reading)
    function limitNoChangeText(a) {
        const events = a.events || []
        return events.length ? i18n("No change seen since %1.", limitDay(events[events.length - 1].at))
                             : i18n("No change seen since %1, when the readings begin.", limitDay(a.since || limitsNow))
    }
    function limitNoChangeTip() {
        return i18n("A change shows in the readings: the same use reads as a different share of a window from one reading to the next, with nothing used between (a bigger or smaller plan, or Anthropic's change), or your windows' plan changed between two of them.")
    }

    // ---- what a window holds (estimates)
    // A window's size: "≈ $180" (one number when steady; "≈" as every
    // estimate here), or, from too few windows or ones too far apart
    // (rough), the range it rests on and how many ("$120–$170 · 5 windows")
    function limitValueText(key, v) {
        if (!v)
            return limitMoney(0)
        if (!v.rough || v.lo === undefined || v.hi === undefined)
            return "≈ " + limitMoney(v.cost)
        const range = v.hi > v.lo ? i18nc("a size from … to …", "%1–%2", limitMoney(v.lo), limitMoney(v.hi)) : limitMoney(v.cost)
        return range + (key === "five_hour" && v.n ? " · " + i18np("%1 window", "%1 windows", v.n) : "")
    }
    // How a size is worked out, in a sentence (and why a range)
    function limitSizeTip(key, a) {
        const v = Limits.size(a, key)
        if (!v)
            return ""
        const base = key === "five_hour"
            ? i18np("What a full 5-hour window holds at API prices: each window's use on this computer by a reading, over the share of the window the reading says was used. Use not seen here only makes a window look smaller, so it's the upper end of the %1 window measured since your limits last changed (the middle of its largest third).",
                    "What a full 5-hour window holds at API prices: each window's use on this computer by a reading, over the share of the window the reading says was used. Use not seen here only makes a window look smaller, so it's the upper end of the %1 windows measured since your limits last changed (the middle of their largest third).", v.n)
            : key === "seven_day" && v.how === "share"
            ? i18n("A full 5-hour window over its share of the week (from the readings): %1 full 5-hour windows.",
                   a.now.share ? Number((100 / a.now.share.pct).toFixed(1)) : "")
            : i18np("What a full %2 holds at API prices: your use on this computer by its readings, over the share of it they say was used, from %1 week.",
                    "What a full %2 holds at API prices: your use on this computer by its readings, over the share of it they say was used, the upper end of %1 weeks.",
                    v.n || 1, limitLabel(key).toLowerCase()) + (key === "seven_day" ? "" : " " + i18n("Only that model's usage counts."))
        return base + (v.scaled ? "\n" + i18n("None measured since your limits changed yet: what it held before, times %1.", Number(v.scaled.toFixed(2))) : "")
               + (v.rough ? "\n" + (key === "five_hour"
                   ? i18n("Too few windows, or ones too far apart, for one number: use not seen here (claude.ai, your phone, other computers, SSH hosts) fills some windows more than others.")
                   : i18n("Its readings tell sizes too far apart for one number: use not seen here (claude.ai, your phone, other computers, SSH hosts) counts in some of them.")) : "")
    }
    // "A full 5-hour window moves the week 18%: 6 of them fill it"
    function limitShareText(s) {
        if (!s || !(s.pct > 0))
            return ""
        const n = Math.max(1, Math.round(100 / s.pct))
        return s.how === "readings" ? i18n("A full 5-hour window moves the week %1%: %2 of them fill it", Math.round(s.pct), n)
                                    : i18n("A full 5-hour window is ≈ %1% of the week: %2 of them fill it", Math.round(s.pct), n)
    }
    function limitShareHow(s) {
        return !s ? "" : s.how === "readings" ? i18n("from the readings") : i18n("from the sizes")
    }
    function limitShareTip(s) {
        return !s ? "" : s.how === "readings"
            ? i18np("From the readings themselves: how far the week's reading moved while a 5-hour window filled, in the middle of %1 window. No prices: use not seen here moves both alike.",
                    "From the readings themselves: how far the week's reading moved while a 5-hour window filled, in the middle of %1 windows. No prices: use not seen here moves both alike.", s.n || 0)
            : i18n("From the two sizes, the 5-hour window's over the week's: too few windows told it from the readings yet.")
              + (s.rough ? " " + i18n("One of them is a range, so this is rough.") : "")
    }
    // How long a full window lasts at your pace
    function limitFillText(fill) {
        if (!fill)
            return ""
        return (fill.wallMs <= 5 * 3600000 ? i18n("A 5-hour window fills in ≈ %1 at your pace", hours(fill.wallMs))
                                           : i18n("At your pace a 5-hour window doesn't fill in its 5 hours"))
               + (fill.workMs >= 60000 ? " · " + i18n("Claude worked %1 in it, across chats", hours(fill.workMs)) : "")
    }
    function limitFillTip() {
        return i18n("The middle of the windows measured: from a window's first request to its reading, over the share it says was used, on the clock; Claude's work in it the same way, across the chats that worked at once.")
    }
    // "≈ 540M tokens fill a 5-hour window, in your mix"; its tooltip: the
    // same in one model's output tokens or cache reads
    function limitTokensText(a) {
        const t = a.now.tokens
        const n = t ? t.fresh + t.output + t.cacheRead : 0
        return n > 0 ? i18n("≈ %1 tokens fill a 5-hour window, in your mix", tokens(Math.round(n))) : ""
    }
    function limitTokensTip(a) {
        const e = a.equivalents
        const five = e ? e.fiveHour : null, week = e ? e.week : null
        return i18n("Your mix: the tokens of the windows measured, by kind, scaled to what a window holds.")
               + (e && five ? "\n" + i18n("In %1 output tokens alone: ≈ %2 a 5-hour window (or ≈ %3 cache reads)", e.model, tokens(five.output), tokens(five.cacheRead))
                              + (week ? i18n("; ≈ %1 a week", tokens(week.output)) : "") + "." : "")
    }
    // The legend under what fills a window: a part's words and its share of the API price
    function limitPartText(part) {
        return part.kind === "cacheRead" ? i18n("cache reads %1", shareText(part.share))
             : part.kind === "fresh" ? i18n("new input and cache writes %1", shareText(part.share))
             : i18n("output %1", shareText(part.share))
    }
    function limitPartColor(kind) {
        return kind === "output" ? workColor : kind === "fresh" ? waitColor : youColor
    }
    // A window's size: whole amounts from 10 up ("$48", "€1,180")
    function limitMoney(usd) {
        const amount = (usd || 0) * currency.rate
        if (amount < 10)
            return money(usd)
        const symbol = symbols[currency.code]
        const text = Number(Math.round(amount)).toLocaleString(Qt.locale(), "f", 0)
        return symbol ? symbol + text : text + " " + currency.code
    }
    // Over the chart: "Each 5-hour window since 12 Mar: $60–$195 · its line ≈ $180"
    function limitChartText(a, c) {
        const eras = a.eras || []
        const since = eras.length > 1 ? i18n(" since %1", limitDay(eras[eras.length - 1].from)) : ""
        return i18n("Each 5-hour window%1: %2", since, c.hi > c.lo ? i18nc("a size from … to …", "%1–%2", limitMoney(c.lo), limitMoney(c.hi)) : limitMoney(c.hi))
               + (c.estimate ? " · " + i18n("its line ≈ %1", limitMoney(c.estimate)) : "")
    }
    function limitChartTip(c) {
        return i18n("What each 5-hour window held by what this computer used (a dot each). Use not seen here makes a window look smaller, so the estimate is the upper end of them (the line).")
               + (c.older.length ? " " + i18n("Before your limits changed (dimmed), each stretch is drawn on its own scale: %1.",
                                             c.older.map(e => i18n("until %1, ≈ %2", limitDay(e.until), limitMoney(e.fiveHour.cost))).join(", ")) : "")
               + (c.marks.length ? " " + i18n("An orange line marks where your limits changed.") : "")
    }
    // The section's last line: what it's made from and what it can't see (the SSH hosts the Recap reads, by name)
    function limitFootText(h) {
        const hosts = recap ? recap.sources.filter(s => s.host).map(s => root.hostLabel(s.host)) : []
        return (h.since ? i18n("Estimated from this computer's chats and the limit readings Talpy Den kept since %1.", limitDay(h.since))
                        : i18n("Estimated from this computer's chats and the limit readings Talpy Den kept.")) + " "
               + (hosts.length ? i18n("Use on %1 (SSH hosts), claude.ai, your phone or other computers counts toward your limits but isn't seen here, so a window can look smaller than it is: the estimates go by the larger ones.", hosts.join(", "))
                               : i18n("Use on claude.ai, your phone, other computers or SSH hosts counts toward your limits but isn't seen here, so a window can look smaller than it is: the estimates go by the larger ones."))
    }

    // Wed 14:05
    function whenText(ms) {
        return Qt.locale().toString(new Date(ms), "ddd") + " " + root.clockText(ms)
    }

    function date(day) {
        const p = String(day).split("-").map(Number)
        return new Date(p[0], p[1] - 1, p[2])
    }
    // How many days before today's a day is (the Day's step back to it)
    function daysBack(day) {
        const t = new Date(root.now)
        return Math.round((new Date(t.getFullYear(), t.getMonth(), t.getDate()) - date(day)) / 86400000)
    }

    function periodText() {
        if (!recap || recap.span !== span)
            return root.weekBack !== 0 ? "" : span === "day" ? i18n("Today") : span === "all" ? i18n("Everything")
                                             : span === "month" ? i18n("Last 30 days") : i18n("Last 7 days")
        if (span === "day") {
            const day = Qt.locale().toString(date(recap.from), "ddd d MMM")
            return recap.back === 0 ? i18n("Today · %1", day) : recap.back === 1 ? i18n("Yesterday · %1", day) : day
        }
        if (span === "all")
            return recap.first ? i18n("Everything since %1", Qt.locale().toString(date(recap.first), "d MMM yyyy")) : i18n("Everything")
        const days = i18nc("from day – to day", "%1 – %2", Qt.locale().toString(date(recap.from), "d MMM"),
                           Qt.locale().toString(date(recap.to), "d MMM"))
        return recap.back !== 0 ? days : span === "month" ? i18n("Last 30 days · %1", days) : i18n("Last 7 days · %1", days)
    }

    // The step back and on: "The day before", "The 30 days after", …
    function stepText(after) {
        return span === "day" ? (after ? i18n("The day after") : i18n("The day before"))
             : span === "month" ? (after ? i18n("The 30 days after") : i18n("The 30 days before"))
             : (after ? i18n("The week after") : i18n("The week before"))
    }

    // The change against the 7 days before: +4h 44m, −$12
    function deltaText(now, before, kind) {
        if (!previous)
            return ""
        const d = now - before
        const amount = shown(Math.abs(d), kind)
        if (kind === "time" ? Math.abs(d) < 60000 : kind === "money" ? Math.abs(d) < 0.01 : kind === "tokens" ? Math.abs(d) < 50 : d === 0)
            return i18nc("no change against the 7 days before", "same as before")
        return (d > 0 ? "+" : "−") + amount
    }

    function beforeText(before, kind) {
        if (!previous)
            return uncomparedText()
        const value = shown(before, kind)
        if (sameTime)
            return "\n" + (span === "day" ? i18n("The day before, by this time: %1", value)
                          : span === "month" ? i18n("The 30 days before, by this time: %1", value)
                          : i18n("The 7 days before, by this time: %1", value))
        return "\n" + (span === "day" ? i18n("The day before: %1", value) : span === "month" ? i18n("The 30 days before: %1", value)
                                                                            : i18n("The 7 days before: %1", value))
    }

    // The period before begins before the first chat the Recap has: not
    // known whole, so not compared (week.py: beforeKept)
    function uncomparedText() {
        if (!recap || recap.beforeKept !== false || !recap.first || recap.span === "all")
            return ""
        const since = Qt.locale().toString(date(recap.first), "d MMM")
        return "\n" + (recap.span === "day" ? i18n("The day before can't be compared: the Recap has your chats only since %1.", since)
                      : recap.span === "month" ? i18n("The 30 days before can't be compared: the Recap has your chats only since %1.", since)
                      : i18n("The 7 days before can't be compared: the Recap has your chats only since %1.", since))
    }

    // The same number over the 5 weeks up to these days (a week older than
    // the widget keeps, even partly: unknown)
    function trendText(key, kind) {
        if (trend.length < 2)
            return ""
        const values = trend.map(w => !w ? "?" : shown(w[key], kind))
        if (sameTime)
            return "\n" + (span === "day" ? i18n("Day by day, each by this time, this day last: %1", values.join(" · "))
                          : span === "month" ? i18n("30 days at a time, each by this time, these 30 days last: %1", values.join(" · "))
                          : i18n("Week by week, each by this time, these 7 days last: %1", values.join(" · ")))
        return "\n" + (span === "day" ? i18n("Day by day, this day last: %1", values.join(" · "))
                      : span === "month" ? i18n("30 days at a time, these 30 days last: %1", values.join(" · "))
                      : i18n("Week by week, these 7 days last: %1", values.join(" · ")))
    }

    readonly property var tiles: !sum ? [] : [
        { label: i18n("You were at it"), key: "youMs", value: hours(sum.youMs),
          delta: deltaText(sum.youMs, previous ? previous.youMs : 0, "time"),
          tip: i18n("The time you spent writing to Claude, reading its replies and answering its questions, in all your chats and accounts: the time between your prompts and its replies counts when it's under 15 minutes.")
               + beforeText(previous ? previous.youMs : 0, "time") + trendText("youMs", "time") },
        { label: i18n("Claude worked"), key: "workedMs", value: hours(sum.workedMs),
          delta: deltaText(sum.workedMs, previous ? previous.workedMs : 0, "time"),
          tip: i18n("Claude's own count of its turns (its “Worked for …”), all chats added up: chats working at the same time each count. On the clock it worked %1, and it waited %2 for your answers.",
                    hours(sum.busyMs), hours(sum.waitMs)) + beforeText(previous ? previous.workedMs : 0, "time")
               + trendText("workedMs", "time") },
        { label: i18n("Prompts"), key: "prompts", value: count(sum.prompts),
          delta: deltaText(sum.prompts, previous ? previous.prompts : 0, "count"),
          tip: i18np("In %1 chat", "In %1 chats", sum.chats) + " · " + i18np("%1 turn of Claude's", "%1 turns of Claude's", sum.turns)
               + beforeText(previous ? previous.prompts : 0, "count") + trendText("prompts", "count") },
        { label: tokensLabel(), key: "tokenTotal", value: tokens(sum.tokenTotal),
          delta: deltaText(sum.tokenTotal, previous ? previous.tokenTotal : 0, "tokens"),
          tip: tokenText() + beforeText(previous ? previous.tokenTotal : 0, "tokens") + trendText("tokenTotal", "tokens") },
        { label: i18n("At API prices"), key: "cost", value: money(sum.cost),
          delta: deltaText(sum.cost, previous ? previous.cost : 0, "money"),
          tip: i18n("What the same tokens would cost on Claude's API, at its list prices of %1. Your plan isn't billed this way: this is the value of what you used.",
                    recap.prices ? Qt.locale().toString(date(recap.prices.asOf), "d MMMM yyyy") : "")
               + guessedCostText() + beforeText(previous ? previous.cost : 0, "money") + trendText("cost", "money") }
    ]

    // The Tokens tile's label: how much of them were cache reads, on the tile
    // itself ("Tokens · 98% cache"), the whole split in its tooltip
    function tokensLabel() {
        const t = sum ? sum.tokens : null
        return t && t.cacheRead > 0 && sum.tokenTotal > 0
             ? i18nc("the Tokens tile's label: the share of them read from the cache", "Tokens · %1 cache",
                     shareText(t.cacheRead / sum.tokenTotal))
             : i18n("Tokens")
    }

    // What the tokens were: all that Claude read and wrote, by kind
    function tokenText() {
        const t = sum.tokens
        return i18n("Everything Claude read and wrote: %1 of new input, %2 read from the cache, %3 written to the cache and %4 that Claude wrote.",
                    tokens(t.input), tokens(t.cacheRead), tokens(t.cacheWrite5m + t.cacheWrite1h), tokens(t.output))
    }

    // Where ms is on its day's row, 0 to 1: by that day's own clock, as the
    // hours over the rows say, so on a day the clock changes (23 or 25 hours)
    // 18:00 is under the 18 too (its hour that comes twice is drawn twice in
    // the same place, the one it skips not at all)
    function dayPlace(day, ms) {
        if (ms <= day.start)
            return 0
        if (ms >= day.end)
            return 1
        const t = new Date(ms)
        return (t.getHours() + (t.getMinutes() + (t.getSeconds() + t.getMilliseconds() / 1000) / 60) / 60) / 24
    }
    // and back: the moment at that place of its row
    function dayMoment(day, place) {
        return new Date(day.start).setHours(0, 0, 0, Math.round(Math.max(0, Math.min(1, place)) * 86400000))
    }

    // What went on at the moment the mouse points at, on its day's row
    function hoverText() {
        if (weeks)
            return i18n("Click a week for its chats.")
        if (!hover || !days[hover.row])
            return recap && recap.span === "week" ? i18n("Point at a day to see what went on then; click it for its chats, or its name for that day alone.")
                                                  : i18n("Point at a day to see what went on then; click it for its chats.")
        const d = days[hover.row]
        const when = Qt.locale().toString(date(d.day), "ddd d MMM") + ", " + root.clockText(hover.ms) + ": "
        if (hover.ms > root.now)
            return when + i18n("still to come")
        const px = (d.end - d.start) / Math.max(1, timelineWidth)   // (a mark a pixel or two wide is hard to hit)
        const at = list => list.find(s => s[0] <= hover.ms && hover.ms < s[1])
                           || list.find(s => s[1] - s[0] < 3 * px && s[0] - 2 * px <= hover.ms && hover.ms < s[1] + 2 * px)
        const work = at(d.work), wait = at(d.wait), you = at(d.you)
        const span = s => root.clockText(s[0]) + "–" + root.clockText(s[1])
        const parts = []
        if (work)
            parts.push(work[2] > 1 ? i18n("Claude worked %1, %2 chats at once", span(work), work[2])
                                   : i18n("Claude worked %1", span(work)))
        else if (wait)
            parts.push(i18n("Claude waited for your answer %1", span(wait)))
        if (you)
            parts.push(i18n("you were at it %1", span(you)))
        const limit = (d.limits || []).find(t => Math.abs(t - hover.ms) <= 3 * px)
        if (limit)
            parts.unshift(i18n("a usage limit stopped a chat at %1", root.clockText(limit)))
        return when + (parts.length ? parts.join(" · ") : i18n("nothing went on"))
    }

    // What Claude did, in a line: its tool calls, commands, edits, subagents
    // (of these days, or w: the period before's)
    function workText(w) {
        const work = w === undefined ? view.work : w
        if (!work || !work.toolCalls)
            return ""
        const parts = [i18np("%1 tool call", "%1 tool calls", work.toolCalls)]
        if (work.commands)
            parts.push(i18np("%1 command run", "%1 commands run", work.commands))
        if (work.edits)
            parts.push(i18np("%1 edit", "%1 edits", work.edits) + " "
                       + i18np("in %1 file", "in %1 files", work.files)
                       + " (+" + count(work.linesAdded) + " −" + count(work.linesRemoved) + ")")
        if (work.subagents)
            parts.push(i18np("%1 subagent started", "%1 subagents started", work.subagents))
        if (work.webSearches)
            parts.push(i18np("%1 web search", "%1 web searches", work.webSearches))
        if (work.webFetches)
            parts.push(i18np("%1 page fetched", "%1 pages fetched", work.webFetches))
        if (work.compactions)
            parts.push(i18np("%1 compaction", "%1 compactions", work.compactions))
        return parts.join(" · ")
    }
    // What Claude did in the period before, for that line's tooltip (none
    // when the Recap doesn't have that period whole: why)
    function workBeforeText() {
        const before = recap && recap.workBefore ? recap.workBefore : null
        if (!before)
            return uncomparedText().trim()
        const text = workText(before) || i18nc("what Claude did in a period: nothing", "nothing")
        if (sameTime)
            return span === "day" ? i18n("The day before, by this time: %1", text)
                 : span === "month" ? i18n("The 30 days before, by this time: %1", text) : i18n("The 7 days before, by this time: %1", text)
        return span === "day" ? i18n("The day before: %1", text) : span === "month" ? i18n("The 30 days before: %1", text)
                                                                    : i18n("The 7 days before: %1", text)
    }

    // What a project or chat got done: "14 commits · 212 files" (the files
    // Claude's edits changed), and its tooltip's line with their lines
    function doneText(x) {
        const parts = []
        if (x.commitCount)
            parts.push(i18np("%1 commit", "%1 commits", x.commitCount))
        if (x.files)
            parts.push(i18np("%1 file", "%1 files", x.files))
        return parts.join(" · ")
    }
    function doneTip(x) {
        const parts = []
        if (x.commitCount)
            parts.push(i18np("%1 commit", "%1 commits", x.commitCount))
        if (x.files)
            parts.push(i18np("Claude's edits changed %1 file", "Claude's edits changed %1 files", x.files)
                       + " (+" + count(x.linesAdded) + " −" + count(x.linesRemoved) + ")")
        return parts.length ? "\n" + parts.join(" · ") : ""
    }

    // A plan window's color: as its bar in the Chats tab
    function planColor(pct) {
        return pct >= 90 ? Kirigami.Theme.negativeTextColor : pct >= 70 ? Kirigami.Theme.neutralTextColor : workColor
    }

    // ---------------------------------------------------------------- your plan
    // What the days shown meant for each account's plan (week.py plan_use),
    // and a project's, chat's or day's share of its week: the same words as
    // VS Code's src/shared/week.ts
    readonly property var planUse: recap && recap.planUse ? recap.planUse : []
    // (its accounts: those with a line, then any with windows now and none)
    readonly property var planIds: planUse.map(u => u.account)
        .concat(plan.map(p => p.account).filter(id => !planUse.some(u => u.account === id)))

    // "28%", "<1%": points of a week
    function pointsText(v) {
        return v > 0 && v < 0.5 ? "<1%" : Math.round(v) + "%"
    }
    // How long chats stood stopped by a limit, in all: days when it's long ("10 days")
    function stoodText(ms) {
        return ms >= 2 * 86400000 ? i18np("%1 day", "%1 days", Math.round(ms / 86400000)) : hours(ms)
    }
    // Each week on its own (Month and Overall, or a sum over a whole week):
    // the points of each weekly window these days used, never added up
    function planWeeksShown(u) {
        return !!u.weekly && u.weekly.length > 0
               && (recap.span === "month" || recap.span === "all" || (u.weeks && u.weeks.seven_day || 0) > 100)
    }
    // An account's line: "66% of the week used in these days · 3 full 5-hour
    // windows · ran out 3 times, chats stood stopped 4h 10m in all"; several
    // weeks: "Weeks: 72% · 100% · 41% so far · …"
    function planUseText(u) {
        const parts = []
        const week = u.weeks ? u.weeks.seven_day : undefined
        const weeks = planWeeksShown(u) ? u.weekly.map(w => w.now ? i18nc("a week's use going on", "%1 so far", pointsText(w.pct))
                                                                  : pointsText(w.pct)).join(" · ") : ""
        if (u.readings && week !== undefined)
            parts.push(weeks ? (!u.covered && u.since ? i18n("Weeks since %1: %2", limitDay(u.since), weeks) : i18n("Weeks: %1", weeks))
                       : !u.covered && u.since ? i18n("%1 of the week used since %2", pointsText(week), limitDay(u.since))
                       : recap.span !== "day" ? i18n("%1 of the week used in these days", pointsText(week))
                       : recap.back === 0 ? i18n("%1 of the week used today", pointsText(week))
                       : i18n("%1 of the week used on this day", pointsText(week)))
        for (const key in (u.weeks || {})) {
            const f = Limits.family(key) || key
            if (key !== "seven_day" && u.weeks[key] > 0)
                parts.push(i18nc("a share of a plan's weekly window of one model", "%1 of the %2 week", pointsText(u.weeks[key]),
                                 f.charAt(0).toUpperCase() + f.slice(1)))
        }
        if (u.fiveFull)
            parts.push(i18np("%1 full 5-hour window", "%1 full 5-hour windows", u.fiveFull))
        else if (u.fiveUsed)
            parts.push(i18n("no full 5-hour window"))
        parts.push(!u.ranOut ? i18n("didn't run out")
                   : (u.ranOut === 1 ? i18n("ran out once") : i18n("ran out %1 times", count(u.ranOut)))
                     + (u.heldMs >= 60000 ? i18n(", chats stood stopped %1 in all", stoodText(u.heldMs)) : ""))
        if (!u.readings)
            parts.push(i18n("no readings of its plan here"))
        const text = parts.join(" · ")
        return text.charAt(0).toUpperCase() + text.slice(1)
    }
    // Its tooltip: how each part is worked out
    function planUseTip(u) {
        const lines = []
        if (u.readings && u.weeks && u.weeks.seven_day !== undefined)
            lines.push((planWeeksShown(u)
                        ? i18n("How much of each of your plan's weeks these days used, the newest last: how far Talpy Den's readings of it rose (kept on this computer), each week in its own limits.")
                          + " " + u.weekly.map(w => i18nc("a week, from … to …: the share of it used", "%1 to %2: %3", limitDay(w.from), limitDay(w.until),
                                                          w.now ? i18nc("a week's use going on", "%1 so far", pointsText(w.pct)) : pointsText(w.pct))).join(", ") + "."
                        : i18n("How much of your plan's week these days used: how far Talpy Den's readings of it rose (kept on this computer)."))
                       + " " + i18n("Use on claude.ai, other computers and SSH hosts counts too.")
                       + (!u.covered && u.since ? " " + i18n("The readings kept begin on %1: before that isn't known.", limitDay(u.since)) : ""))
        if (u.fiveUsed)
            lines.push(i18n("%1 of the %2 5-hour windows begun in these days ran full: their readings reached 100%, or a usage limit stopped a chat as one ended.",
                            u.fiveFull, u.fiveUsed))
        if (u.ranOut)
            lines.push(i18n("Your plan ran out %1 (%2). Chats stood stopped %3 in all: each from its stop until the limit reset, or until it went on another way (chats stopped at the same time count once).",
                            u.ranOut === 1 ? i18n("once") : i18n("%1 times", count(u.ranOut)),
                            i18np("%1 chat stopped", "%1 chats stopped", u.stopped), stoodText(u.heldMs)))
        if (!u.readings)
            lines.push(i18n("Talpy Den keeps readings of the plans of this computer's accounts only: %1's has none here, so what these days used of its week isn't known.", u.name))
        return lines.join("\n")
    }
    // A project's share of the week on its row: "≈ 28%" (its largest; "" for none)
    function weekShareShort(x) {
        const s = x.weekShare && x.weekShare.length ? x.weekShare[0] : null
        return !s ? "" : s.pct < 0.5 ? "<1%" : "≈ " + Math.round(s.pct) + "%"
    }
    // A project's, chat's or day's share of each account's week, for its
    // tooltip: how it's worked out (day: from the readings themselves), and
    // why one of its accounts' is missing
    function weekShareTip(x, day) {
        const name = id => {
            const u = planUse.find(v => v.account === id)
            const a = accounts.find(v => v.id === id)
            return u ? u.name : a ? a.name : id
        }
        const named = planUse.filter(u => u.readings).length > 1
        const shares = x.weekShare || []
        const lines = shares.map(s => (day ? "" : "≈ ") + (named ? i18n("%1 of %2's week", pointsText(s.pct), name(s.account))
                                                                 : i18n("%1 of your week", pointsText(s.pct))))
        if (lines.length)
            lines.push(day ? i18n("As the readings of your plan's week rose then.")
                           : i18n("An estimate: its part of these days' amount at API prices, times how much of the week these days used (Your plan)."))
        for (const id of (x.accounts || [])) {
            const u = planUse.find(v => v.account === id)
            if (shares.some(s => s.account === id))
                continue
            if (!u || !u.readings)
                lines.push(i18n("Its share of %1's week isn't known: no readings of that plan on this computer.", name(id)))
            else if (!u.covered && u.since)
                lines.push(i18n("Its share of %1's week isn't known: the readings of it kept begin on %2.", name(id), limitDay(u.since)))
        }
        return lines.join("\n")
    }
    // What a project's row says at its end: its time, amount and share of the week
    function projectNumbers(p) {
        const share = weekShareShort(p)
        return numbersOf(p) + (share ? " · " + share : "")
    }

    readonly property var windowMs: ({ five_hour: 5 * 3600000, seven_day: 7 * 86400000, seven_day_opus: 7 * 86400000,
                                       seven_day_sonnet: 7 * 86400000 })

    function resetText(ms) {
        if (!ms)
            return ""
        return ms - root.now < 86400000 ? i18n("resets %1", root.clockText(ms)) : i18n("resets %1", whenText(ms))
    }
    property real timelineWidth: 0

    function tipIcon(key) {
        return key === "waits" ? Icons.plasma.tipWaits : key === "limits" ? Icons.plasma.tipLimits : Icons.plasma.tip
    }
    // (what a tip's icon means: where the tip comes from)
    function tipSource(key) {
        return key === "waits" ? i18n("From Talpy Den: the time Claude waited for your answers")
             : key === "limits" ? i18n("From Talpy Den: the usage limits that stopped your chats")
             : key === "cold" ? i18n("From Talpy Den: coming back to chats after their cache had expired")
             : i18n("From Claude Code's /usage: a habit that took a good share of your usage")
    }
    // A tip's share: of the usage, as /usage weighs it; coming back to chats
    // after their cache expired: of the amount at API prices (what writing
    // their context again cost more than reading it)
    function tipShareText(t) {
        return t.key === "cold" ? i18nc("a tip's share of the amount at API prices", "%1% of the amount", t.pct || 0)
                                : i18nc("a tip's share of the usage", "%1% of usage", t.pct || 0)
    }
    function tipShareMain(t) {
        return t.key === "cold" ? i18n("%1% of the amount at API prices", t.pct || 0) : i18n("%1% of the usage shown", t.pct || 0)
    }
    function tipShareTip(t) {
        return (t.key === "cold"
             ? i18n("Writing the chats' context again cost %1 more than reading it from the cache. The cache keeps a chat's context an hour after its last reply.",
                    money(spend && spend.cold ? spend.cold.cost : 0))
             : i18n("Of the usage of these days, as Claude Code's /usage weighs it toward your plan's limits. A request can count for several of these."))
             + (t.before === null || t.before === undefined ? uncomparedText() : beforeText(t.before, "points"))
    }
    // Under a tip's share, how it moved: "was 64%" (none: not compared)
    function tipWas(t) {
        return t.pct === null || t.pct === undefined || t.before === null || t.before === undefined ? ""
             : i18nc("a share in the period before", "was %1", t.before + "%")
    }
    // A row of where the usage went that says a tip's share already (with how
    // it moved): its share isn't said again on the tip
    readonly property var mixOfTip: ({ long_context: "long_context", max_effort: "effort:max" })
    function tipShareShown(t) {
        return t.pct !== null && t.pct !== undefined && !(mixOfTip[t.key] && usageMix.some(p => p.key === mixOfTip[t.key]))
    }
    // The limits tip, once every chat it names keeps going, has nothing left to offer
    readonly property var tipsShown: tips.filter(t => !(t.key === "limits" && t.chats && t.chats.length && !t.more
                                                        && t.chats.every(c => !!root.keptChat(c.chatId, c.host || ""))))

    // ---------------------------------------------------------------- what a tip offers a chat
    // (the same rules as VS Code's src/shared/week.ts tipChatAct): the chat
    // as the chat list has it now ({row, group}: a row, else a recent chat),
    // or null
    function listedOf(c) {
        if (!c.chatId)
            return null
        let recent = null
        for (const g of root.hostGroups(c.host || "")) {
            const s = g.sessions.find(x => x.chatId === c.chatId || x.sessionId === c.chatId)
            if (s)
                return { row: s, group: g }
            const r = (g.recent || []).concat(g.starred || []).find(x => x.sessionId === c.chatId)
            if (r && !recent)
                recent = { row: r, group: g }
        }
        return recent
    }
    // Stop, for an idle chat with a process of its own (the tip about chats
    // that ran long: one at work is stopped from its row); Keep going, for one
    // at work or one a usage limit stopped that goes on once it resets (the
    // tip about limits; "kept": it keeps going already); else "" (its name
    // opens it). Watched with the status: root.status, root.keptChats.
    function tipChatAct(key, c) {
        const host = c.host || ""
        if (key === "limits" && root.keptChat(c.chatId, host))
            return "kept"
        const found = listedOf(c)
        const s = found ? found.row : null
        if (!s)
            return ""
        if (key === "long_running")
            return s.state === "idle" && s.pid !== undefined && s.pid !== null
                   && (s.kind === "interactive" || (s.kind === "bg" && (!host || !!s.stopCommand))) ? "stop" : ""
        if (key === "limits")
            return root.goOnAt(s) > 0 ? "keepAtReset" : root.canKeepGoing(s, host) ? "keep" : ""
        return ""
    }
    function tipChatDo(key, c) {
        const host = c.host || ""
        const found = listedOf(c)
        if (!found)
            return
        const act = tipChatAct(key, c)
        if (act === "keepAtReset")
            root.queueContinue(found.row, host, found.group.title, true)
        else if (act === "keep")
            root.keepGoing(found.row, true, host)
        else if (act === "stop")   // (as its row's Stop, for an idle chat: one that got busy since is left alone)
            stopIdle(found.row, host)
    }
    function stopIdle(s, host) {
        if (host && s.kind === "interactive")
            root.remoteEnd(host, s.sessionId, s.profileDir, false, "")
        else if (host)
            root.remoteStop(host, s.stopCommand)
        else
            root.stopSession(s.sessionId, s.profileDir, false, "")
    }
    // The question before Stop, in its row's words (SessionRow.qml)
    function stopAskText(c) {
        const found = listedOf(c)
        const s = found ? found.row : {}
        return s.kind === "interactive" && s.entrypoint === "claude-vscode"
             ? i18n("Stop “%1”? It's idle, so nothing is interrupted: its Claude process in VS Code quits. Its tab keeps the chat and goes on with your next message.", c.name)
             : s.kind === "interactive"
             ? i18n("Stop “%1”? It's idle, so nothing is interrupted: Claude quits and its terminal stays open. The chat is kept; reopen it from Recent chats.", c.name)
             : i18n("Stop “%1”? It's finished, so this only shuts down its idle process. The conversation is kept.", c.name)
    }
    property string stopAsked: ""   // the chat (host|id) whose Stop is asked under a tip

    // ---------------------------------------------------------------- where the usage went
    // (week.py usage_mix: by subagents, over 150k of context, by effort
    // level, weighed as /usage weighs it; the same words as VS Code's
    // src/shared/week.ts)
    readonly property var usageMix: recap && recap.usageMix ? recap.usageMix : []
    function mixLabel(key) {
        return key === "subagents" ? i18n("Subagents") : key === "long_context" ? i18n("Context over 150k")
             : key === "effort:" ? i18n("Effort not noted") : i18nc("a reasoning effort level, as Claude Code names it: Effort xhigh", "Effort %1", key.slice(7))
    }
    function mixNumbers(p) {
        return i18nc("a share of the usage", "%1 of usage", pointsText(p.pct))
             + (p.before === null || p.before === undefined ? "" : " · " + i18nc("a share in the period before", "was %1", pointsText(p.before)))
    }
    function mixTip(p) {
        const what = p.key === "subagents"
            ? i18n("Subagents' requests took %1 of the usage of these days, the main chats' %2.", pointsText(p.pct), pointsText(100 - p.pct))
            : p.key === "long_context"
            ? i18n("Requests that carried over 150k tokens of context took %1 of the usage: a long chat sends all of its context with each request.", pointsText(p.pct))
            : p.key === "effort:"
            ? i18n("%1 of the usage has no effort level noted: chats deleted before Talpy Den kept their levels (only max effort is known of them), and models with no effort setting.", pointsText(p.pct))
            : i18n("Requests at %1 effort took %2 of the usage.", p.key.slice(7), pointsText(p.pct))
        return what + "\n" + i18n("Weighed as Claude Code's /usage weighs it toward your plan's limits: a request's tokens by kind, times its model's weight.")
             + (p.before === null || p.before === undefined ? uncomparedText() : beforeText(p.before, "points"))
    }
    // A model's row: its amount and share, and its share the period before
    function modelRowText(m) {
        return modelNumbers(m) + (m.before === null || m.before === undefined ? "" : " · " + i18nc("a share in the period before", "was %1", shareText(m.before)))
    }
    readonly property real usageNumbersWidth: widest(models.map(modelRowText).concat(usageMix.map(mixNumbers)))

    FontMetrics {
        id: smallMetrics
        font: Kirigami.Theme.smallFont
    }
    FontMetrics {
        id: textMetrics
    }
    // Where Claude worked: the names' column as wide as the longest (bold:
    // the one unfolded), up to 10 units; the bars get the rest
    readonly property real projectNameWidth: Math.min(gu * 10, Math.max(gu * 6, Math.ceil(Math.max(0, ...projects.map(p =>
        textMetrics.advanceWidth((p.host ? root.hostLabel(p.host) + ": " : "") + p.name)))) * 1.08 + 1))

    // (a hidden text field: QML has no clipboard of its own)
    TextEdit {
        id: clipboard
        visible: false
        function put(text) {
            clipboard.text = text
            clipboard.selectAll()
            clipboard.copy()
        }
    }

    Timer {
        id: copiedTimer
        interval: 2000
        onTriggered: view.copied = ""
    }

    Item {
        id: sheet
        width: view.availableWidth
        implicitHeight: page.implicitHeight + Kirigami.Units.largeSpacing

    ColumnLayout {
        id: page
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.leftMargin: Kirigami.Units.smallSpacing
        anchors.rightMargin: Kirigami.Units.smallSpacing
        spacing: Kirigami.Units.largeSpacing
        // (while it reads again: what it said before, dimmed, no jump)
        opacity: root.weekBusy && view.recap ? 0.6 : 1

        // A day, 7 days or everything kept
        RowLayout {
            Layout.alignment: Qt.AlignHCenter
            Layout.topMargin: Kirigami.Units.smallSpacing
            spacing: Kirigami.Units.smallSpacing

            Repeater {
                model: [["day", i18n("Day")], ["week", i18n("Week")], ["month", i18n("Month")], ["all", i18n("Overall")]]
                delegate: PlasmaComponents3.ToolButton {
                    required property var modelData
                    text: modelData[1]
                    checkable: true
                    autoExclusive: true
                    checked: view.span === modelData[0]
                    onClicked: root.setWeekSpan(modelData[0])
                }
            }
        }

        // The days shown, one back or on, and whose chats
        RowLayout {
            Layout.fillWidth: true
            spacing: Kirigami.Units.smallSpacing

            PlasmaComponents3.ToolButton {
                icon.name: Icons.plasma.previous
                display: PlasmaComponents3.AbstractButton.IconOnly
                text: view.stepText(false)
                visible: view.span !== "all"
                enabled: root.weekBack < (view.recap ? view.recap.backMax : 0)
                onClicked: root.weekBack += 1

                PlasmaCore.ToolTipArea {
                    textFormat: Text.PlainText
                    anchors.fill: parent
                    mainText: parent.text
                }
            }
            PlasmaComponents3.Label {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignHCenter
                elide: Text.ElideRight
                font.bold: true
                text: view.periodText()
            }
            PlasmaComponents3.ToolButton {
                icon.name: Icons.plasma.next
                display: PlasmaComponents3.AbstractButton.IconOnly
                text: view.stepText(true)
                visible: view.span !== "all"
                enabled: root.weekBack > 0
                onClicked: root.weekBack -= 1

                PlasmaCore.ToolTipArea {
                    textFormat: Text.PlainText
                    anchors.fill: parent
                    mainText: parent.text
                }
            }
            // (none to read these days again: the popup's Refresh does)
            PlasmaComponents3.ToolButton {
                icon.name: Icons.plasma.share
                display: PlasmaComponents3.AbstractButton.IconOnly
                text: i18n("Share as a picture…")
                enabled: view.hasData
                onClicked: view.share()

                PlasmaCore.ToolTipArea {
                    textFormat: Text.PlainText
                    anchors.fill: parent
                    mainText: parent.text
                    subText: i18n("These days as a card with Talpy: save it or copy it, with your projects' names or without.")
                }
            }
        }

        // Whose chats: all, or one account's (a chat shared by hard links counts on each account that has it)
        Flow {
            Layout.fillWidth: true
            visible: view.accounts.length > 1
            spacing: Kirigami.Units.smallSpacing

            Repeater {
                model: view.accounts.length + 1
                delegate: PlasmaComponents3.ToolButton {
                    required property int index
                    readonly property var account: index > 0 ? view.accounts[index - 1] || null : null
                    readonly property string accountId: account ? account.id : ""
                    text: account ? account.name + (account.plan ? " · " + account.plan : "") : i18n("All accounts")
                    checkable: true
                    autoExclusive: true
                    checked: root.weekAccount === accountId
                    onClicked: root.weekAccount = accountId
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            visible: root.weekBusy && !view.recap
            spacing: Kirigami.Units.smallSpacing

            PlasmaComponents3.BusyIndicator {
                implicitWidth: Kirigami.Units.iconSizes.medium
                implicitHeight: Kirigami.Units.iconSizes.medium
                running: parent.visible
            }
            PlasmaComponents3.Label {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                text: i18n("Reading your chats of these days. The first time takes a few seconds; after that only what's new is read.")
                opacity: 0.8
            }
        }

        PlasmaComponents3.Label {
            textFormat: Text.PlainText
            Layout.fillWidth: true
            visible: root.weekError !== ""
            wrapMode: Text.Wrap
            color: Kirigami.Theme.negativeTextColor
            text: i18n("Couldn't read your week: %1", root.weekError)
        }

        PlasmaExtras.PlaceholderMessage {
            Layout.fillWidth: true
            visible: !!view.recap && !view.hasData
            iconName: Icons.plasma.recap
            text: view.span === "day" ? i18n("No Claude on this day") : view.span === "all" ? i18n("No Claude yet") : i18n("No Claude in these days")
            explanation: view.span === "day" ? i18n("None of your chats here (or on the SSH hosts shown) has a prompt or a reply on this day.")
                         : view.span === "all" ? i18n("None of your chats here (or on the SSH hosts shown) has a prompt or a reply yet.")
                         : view.span === "month" ? i18n("None of your chats here (or on the SSH hosts shown) has a prompt or a reply in these 30 days.")
                         : i18n("None of your chats here (or on the SSH hosts shown) has a prompt or a reply in these 7 days.")
        }

        // The numbers of the week, against the week before
        GridLayout {
            Layout.fillWidth: true
            visible: view.hasData
            columns: width > view.gu * 25 ? view.tiles.length : width > view.gu * 16 ? 3 : 2
            columnSpacing: Kirigami.Units.largeSpacing
            rowSpacing: Kirigami.Units.largeSpacing

            Repeater {
                model: view.tiles.length
                delegate: Item {
                    id: tile
                    required property int index
                    readonly property var info: view.tiles[index] || ({ label: "", key: "", value: "", delta: "", tip: "" })
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    implicitHeight: tileText.implicitHeight

                    ColumnLayout {
                        id: tileText
                        anchors.left: parent.left
                        anchors.right: parent.right
                        spacing: 0

                        PlasmaComponents3.Label {
                            textFormat: Text.PlainText
                            Layout.fillWidth: true
                            text: tile.info.label
                            elide: Text.ElideRight
                            font: Kirigami.Theme.smallFont
                            opacity: 0.7
                        }
                        PlasmaComponents3.Label {
                            textFormat: Text.PlainText
                            Layout.fillWidth: true
                            text: tile.info.value
                            elide: Text.ElideRight
                            // (a month's bigger numbers, "160h 23m": smaller to fit, not cut off)
                            fontSizeMode: Text.HorizontalFit
                            minimumPointSize: Kirigami.Theme.defaultFont.pointSize
                            font.pointSize: Kirigami.Theme.defaultFont.pointSize * 1.6
                            font.weight: Font.DemiBold
                        }
                        PlasmaComponents3.Label {
                            textFormat: Text.PlainText
                            Layout.fillWidth: true
                            visible: text !== ""
                            text: tile.info.delta
                            elide: Text.ElideRight
                            font: Kirigami.Theme.smallFont
                            opacity: 0.6
                        }
                        // the last 5 weeks, these 7 days last (a week the widget no longer has: a dot)
                        Row {
                            id: trendBars
                            readonly property var values: view.trend.map(w => w ? (w[tile.info.key] || 0) : null)
                            readonly property real highest: Math.max(1e-9, ...values.filter(v => v !== null))
                            Layout.topMargin: Math.round(view.gu * 0.2)
                            visible: view.trend.length > 1
                            spacing: Math.max(1, Math.round(view.gu * 0.12))

                            Repeater {
                                model: trendBars.values.length
                                delegate: Item {
                                    required property int index
                                    readonly property var value: trendBars.values[index]
                                    width: Math.round(view.gu * 0.5)
                                    height: Math.round(view.gu * 0.8)

                                    Rectangle {
                                        anchors.bottom: parent.bottom
                                        width: parent.width
                                        height: parent.value === null ? width : Math.max(1, parent.height * parent.value / trendBars.highest)
                                        radius: parent.value === null ? width / 2 : 1
                                        color: parent.index === trendBars.values.length - 1 ? view.workColor : view.youColor
                                        opacity: parent.value === null ? 0.3 : 1
                                    }
                                }
                            }
                        }
                    }
                    PlasmaCore.ToolTipArea {
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        mainText: tile.info.label
                        subText: tile.info.tip
                    }
                }
            }
        }

        // A day per row: when you were at it, when Claude worked, when it waited for you
        ColumnLayout {
            Layout.fillWidth: true
            visible: view.hasData && !view.dayLanes
            spacing: Math.round(view.gu * 0.2)

            SectionTitle {
                text: view.weeks ? i18n("Week by week") : view.recap && view.recap.span === "day" ? i18n("Through the day") : i18n("Day by day")
            }
            Flow {
                Layout.fillWidth: true
                spacing: Kirigami.Units.largeSpacing

                Repeater {
                    model: view.weeks ? [[view.youColor, i18n("You")], [view.workColor, i18n("Claude worked")]]
                           : [[view.youColor, i18n("You")], [view.workColor, i18n("Claude working")],
                              [view.waitColor, i18n("Waiting for you")]].concat(
                                 view.days.some(d => d.limits && d.limits.length) ? [[view.limitColor, i18n("A usage limit stopped a chat"), true]] : [])
                    delegate: RowLayout {
                        required property var modelData
                        spacing: Math.round(view.gu * 0.25)

                        Rectangle {
                            implicitWidth: modelData[2] ? 2 : Math.round(view.gu * 0.7)
                            implicitHeight: Math.round(view.gu * (modelData[2] ? 0.7 : 0.35))
                            radius: 1
                            color: modelData[0]
                        }
                        PlasmaComponents3.Label {
                            textFormat: Text.PlainText
                            text: modelData[1]
                            font: Kirigami.Theme.smallFont
                            opacity: 0.8
                        }
                    }
                }
            }

            // The hours, and what the two columns are
            RowLayout {
                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing

                Item {
                    Layout.preferredWidth: view.dayWidth
                }
                Item {
                    id: axis
                    Layout.fillWidth: true
                    implicitHeight: smallMetrics.height
                    onWidthChanged: view.timelineWidth = width

                    Repeater {
                        model: view.weeks ? [] : [0, 6, 12, 18, 24]
                        delegate: PlasmaComponents3.Label {
                            required property int modelData
                            textFormat: Text.PlainText
                            x: Math.max(0, Math.min(axis.width - width, axis.width * modelData / 24 - width / 2))
                            text: String(modelData)
                            font: Kirigami.Theme.smallFont
                            opacity: 0.6
                        }
                    }
                }
                PlasmaComponents3.Label {
                    textFormat: Text.PlainText
                    Layout.preferredWidth: view.numWidth
                    horizontalAlignment: Text.AlignRight
                    text: i18n("You")
                    font: Kirigami.Theme.smallFont
                    opacity: 0.6
                }
                PlasmaComponents3.Label {
                    textFormat: Text.PlainText
                    Layout.preferredWidth: view.numWidth
                    horizontalAlignment: Text.AlignRight
                    text: i18n("Claude")
                    font: Kirigami.Theme.smallFont
                    opacity: 0.6
                }
            }

            Repeater {
                model: view.days.length
                delegate: ColumnLayout {
                    id: dayRow
                    required property int index
                    readonly property var day: view.days[index] || view.emptyDay
                    readonly property bool today: index === (view.weeks ? 0 : view.days.length - 1) && !!view.recap && view.recap.back === 0
                    readonly property bool open: view.openDay !== "" && view.openDay === day.day
                    Layout.fillWidth: true
                    spacing: 0

                    function toggle() {
                        view.openDay = open || !day.chats.length ? "" : day.day
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.smallSpacing

                        PlasmaComponents3.Label {
                            textFormat: Text.PlainText
                            Layout.preferredWidth: view.dayWidth
                            text: view.rowLabel(dayRow.day)
                            elide: Text.ElideRight
                            font.pointSize: Kirigami.Theme.smallFont.pointSize
                            font.bold: dayRow.today || dayRow.open
                            font.underline: dayLabel.opensDay && dayLabel.containsMouse
                            opacity: dayRow.today || dayRow.open ? 0.9 : 0.7

                            MouseArea {
                                id: dayLabel
                                // (Week: its name opens that day alone, a Day; its row unfolds its chats)
                                readonly property bool opensDay: !!view.recap && view.recap.span === "week"
                                anchors.fill: parent
                                hoverEnabled: opensDay
                                cursorShape: opensDay || dayRow.day.chats.length ? Qt.PointingHandCursor : Qt.ArrowCursor
                                onClicked: opensDay ? root.showRecapDay(view.daysBack(dayRow.day.day)) : dayRow.toggle()
                            }
                        }
                        // (Overall: the 7 days' time, yours and Claude's, against the busiest 7 days)
                        Item {
                            visible: view.weeks
                            Layout.fillWidth: true
                            Layout.preferredHeight: view.youHeight + view.laneGap + view.workHeight + 2

                            Rectangle {
                                width: Math.max(dayRow.day.youMs > 0 ? 1 : 0, parent.width * dayRow.day.youMs / view.weekMax)
                                height: view.youHeight
                                radius: 1
                                color: view.youColor
                            }
                            Rectangle {
                                y: view.youHeight + view.laneGap
                                width: Math.max(dayRow.day.workedMs > 0 ? 1 : 0, parent.width * dayRow.day.workedMs / view.weekMax)
                                height: view.workHeight
                                radius: 1
                                color: view.workColor
                            }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: dayRow.day.chats.length ? Qt.PointingHandCursor : Qt.ArrowCursor
                                onClicked: dayRow.toggle()
                            }
                        }
                        Item {
                            id: track
                            visible: !view.weeks
                            Layout.fillWidth: true
                            Layout.preferredHeight: view.youHeight + view.laneGap + view.workHeight + 2

                            function xOf(ms) {
                                return view.dayPlace(dayRow.day, ms) * width
                            }

                            // the quarters of the day (6, 12 and 18 o'clock)
                            Repeater {
                                model: 3
                                delegate: Rectangle {
                                    required property int index
                                    x: Math.round(track.width * (index + 1) / 4)
                                    width: 1
                                    height: track.height
                                    color: view.grid
                                }
                            }
                            Rectangle {
                                anchors.bottom: parent.bottom
                                width: parent.width
                                height: 1
                                color: view.grid
                            }
                            Repeater {
                                model: dayRow.day.you.length
                                delegate: Rectangle {
                                    required property int index
                                    readonly property var stretch: dayRow.day.you[index] || [0, 0]
                                    x: track.xOf(stretch[0])
                                    width: Math.max(1, track.xOf(stretch[1]) - x)
                                    height: view.youHeight
                                    radius: 1
                                    color: view.youColor
                                }
                            }
                            Repeater {
                                model: dayRow.day.wait.length
                                delegate: Rectangle {
                                    required property int index
                                    readonly property var stretch: dayRow.day.wait[index] || [0, 0]
                                    x: track.xOf(stretch[0])
                                    y: view.youHeight + view.laneGap
                                    width: Math.max(1, track.xOf(stretch[1]) - x)
                                    height: view.workHeight
                                    radius: 1
                                    color: view.waitColor
                                    opacity: 0.8
                                }
                            }
                            Repeater {
                                model: dayRow.day.work.length
                                delegate: Rectangle {
                                    required property int index
                                    readonly property var stretch: dayRow.day.work[index] || [0, 0, 1]
                                    x: track.xOf(stretch[0])
                                    y: view.youHeight + view.laneGap
                                    width: Math.max(1, track.xOf(stretch[1]) - x)
                                    height: view.workHeight
                                    radius: 1
                                    color: view.workColor
                                    opacity: stretch[2] >= 3 ? 1 : stretch[2] === 2 ? 0.8 : 0.55
                                }
                            }
                            Repeater {   // where a usage limit stopped a chat
                                model: dayRow.day.limits ? dayRow.day.limits.length : 0
                                delegate: Rectangle {
                                    required property int index
                                    x: Math.round(track.xOf(dayRow.day.limits[index] || 0)) - 1
                                    width: 2
                                    height: track.height
                                    color: view.limitColor
                                }
                            }
                            Rectangle {   // now
                                visible: dayRow.today
                                x: Math.round(track.xOf(root.now))
                                width: 1
                                height: track.height
                                color: view.ink
                                opacity: 0.6
                            }
                            Rectangle {   // where the mouse points
                                visible: !!view.hover && view.hover.row === dayRow.index
                                x: view.hover ? Math.round(view.hover.x) : 0
                                width: 1
                                height: track.height
                                color: view.ink
                                opacity: 0.5
                            }
                            MouseArea {
                                anchors.fill: parent
                                anchors.topMargin: -2
                                anchors.bottomMargin: -2
                                hoverEnabled: true
                                cursorShape: dayRow.day.chats.length ? Qt.PointingHandCursor : Qt.ArrowCursor
                                onClicked: dayRow.toggle()
                                onPositionChanged: mouse => view.hover = { row: dayRow.index, x: mouse.x,
                                                                           ms: view.dayMoment(dayRow.day, mouse.x / Math.max(1, width)) }
                                onExited: {
                                    if (view.hover && view.hover.row === dayRow.index)
                                        view.hover = null
                                }
                            }
                        }
                        PlasmaComponents3.Label {
                            textFormat: Text.PlainText
                            Layout.preferredWidth: view.numWidth
                            horizontalAlignment: Text.AlignRight
                            text: dayRow.day.youMs >= 60000 ? view.hours(dayRow.day.youMs) : "–"
                            font: Kirigami.Theme.smallFont
                            opacity: 0.7
                        }
                        PlasmaComponents3.Label {
                            textFormat: Text.PlainText
                            Layout.preferredWidth: view.numWidth
                            horizontalAlignment: Text.AlignRight
                            text: dayRow.day.workedMs >= 60000 ? view.hours(dayRow.day.workedMs) : "–"
                            font: Kirigami.Theme.smallFont
                            opacity: 0.9

                            PlasmaCore.ToolTipArea {
                                textFormat: Text.PlainText
                                anchors.fill: parent
                                readonly property int length: dayRow.day.to ? Math.round((view.date(dayRow.day.to) - view.date(dayRow.day.day)) / 86400000) + 1 : 7
                                mainText: !dayRow.day.day ? "" : view.weeks
                                          ? i18nc("from day – to day", "%1 – %2", Qt.locale().toString(view.date(dayRow.day.day), "d MMMM"),
                                                  Qt.locale().toString(view.date(dayRow.day.to), "d MMMM"))
                                            + (length < 7 ? " · " + i18np("%1 day", "%1 days", length) : "")
                                          : Qt.locale().toString(view.date(dayRow.day.day), "dddd d MMMM")
                                subText: i18n("You: %1 · Claude worked %2 (on the clock %3) · it waited %4 for you",
                                              view.hours(dayRow.day.youMs), view.hours(dayRow.day.workedMs),
                                              view.hours(dayRow.day.busyMs), view.hours(dayRow.day.waitMs))
                                         + "\n" + i18np("%1 prompt", "%1 prompts", dayRow.day.prompts)
                                         + " · " + i18n("%1 tokens", view.tokens(dayRow.day.tokenTotal))
                                         + " · " + i18n("%1 at API prices", view.money(dayRow.day.cost))
                                         + (dayRow.day.weekShare && dayRow.day.weekShare.length ? "\n" + view.weekShareTip(dayRow.day, true) : "")
                            }
                        }
                    }

                    // the day's chats, unfolded with a click on its row
                    Repeater {
                        id: dayChats
                        readonly property var list: dayRow.open ? dayRow.day.chats : []
                        readonly property real whereWidth: Math.min(view.gu * 7, view.widest(list.map(view.whereOf)))
                        readonly property real numbersWidth: view.widest(list.map(view.numbersOf))
                        model: list.length
                        delegate: WeekChatLine {
                            required property int index
                            chat: dayChats.list[index] || view.emptyChat
                            indent: view.dayWidth
                            numbers: view.numbersOf(chat)
                            whereWidth: dayChats.whereWidth
                            numbersWidth: dayChats.numbersWidth
                        }
                    }
                }
            }

            PlasmaComponents3.Label {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                Layout.leftMargin: view.dayWidth + Kirigami.Units.smallSpacing
                elide: Text.ElideRight
                font: Kirigami.Theme.smallFont
                opacity: view.hover ? 0.9 : 0.5
                text: view.hoverText()
            }
        }

        // The day, chat by chat (week.py: day_lanes): when each chat worked,
        // waited for you (a permission, a question) or was paused (asleep, a
        // limit); between its turns it was your turn. A name opens its chat.
        ColumnLayout {
            id: lanesBox
            Layout.fillWidth: true
            visible: view.hasData && view.lanes.length > 0
            spacing: Math.round(view.gu * 0.2)
            // the day's own row (you, Claude working, waiting, the limits), drawn on top
            readonly property var day: view.dayLanes && view.days.length ? view.days[0] : view.emptyDay
            readonly property var dayParts: (day.you || []).concat(day.work || [], day.wait || [])
            readonly property real t0: !view.lanes.length ? 0
                : Math.min.apply(null, view.lanes.map(l => l.parts[0][0]).concat(dayParts.map(p => p[0])))
            readonly property real t1: !view.lanes.length ? 1
                : Math.max.apply(null, view.lanes.map(l => l.parts[l.parts.length - 1][1]).concat(dayParts.map(p => p[1])))
            readonly property real span: Math.max(60000, t1 - t0)
            readonly property real nameWidth: Math.round(view.gu * 9)
            readonly property real numbersWidth: view.widest(view.lanes.map(laneNumbers))
            readonly property bool paused: view.lanes.some(l => l.parts.some(p => p[2] === "p"))
            function laneNumbers(l) {
                const ms = l.claudeMs || 0
                return ms < 60000 && (l.cost || 0) < 0.01 ? "–"
                    : (ms < 60000 ? i18nc("under a minute", "<1m") : view.hours(ms)) + " · " + view.money(l.cost || 0)
            }
            function place(ms, width) {
                return (ms - t0) / span * width
            }
            // The whole hours on its axis: every 1, 2, 3, 4, 6 or 12 hours, at most 6 of them
            // (t0 and t1 can be a step apart while the lanes change: none then, not a tick per hour since 1970)
            readonly property var ticks: {
                const hour = 3600000
                if (!(t1 > t0 && t0 > 0) || t1 - t0 > 2 * 86400000)
                    return []
                const step = [1, 2, 3, 4, 6, 12].find(s => span / hour / s <= 6) || 24
                const out = []
                const first = new Date(t0)
                first.setMinutes(0, 0, 0)
                for (let t = first.getTime() + hour; t < t1; t += hour)
                    if (new Date(t).getHours() % step === 0)
                        out.push(t)
                return out
            }
            // What went on at the moment the mouse points at, chat by chat (lanesRows)
            function hoverText() {
                if (!lanesRows.pointing)
                    return i18n("Point at the chats to see what went on then; click a name to open its chat.")
                const ms = lanesRows.hoverMs
                const px = span / lanesRows.trackWidth   // (a mark a pixel or two wide is hard to hit)
                const near = p => (p[0] <= ms && ms < p[1]) || (p[1] - p[0] < 3 * px && p[0] - 2 * px <= ms && ms < p[1] + 2 * px)
                const of = kind => view.lanes.filter(l => l.parts.some(p => p[2] === kind && near(p)))
                                             .map(l => (l.host ? root.hostLabel(l.host) + ": " : "") + l.name)
                const worked = of("w"), waited = of("y"), paused = of("p")
                const parts = []
                const limit = (day.limits || []).find(t => Math.abs(t - ms) <= 3 * px)
                if (limit !== undefined)
                    parts.push(i18n("a usage limit stopped a chat at %1", root.clockText(limit)))
                if (worked.length)
                    parts.push(i18n("Claude worked in %1", worked.join(", ")))
                if (waited.length)
                    parts.push(i18n("waited for you in %1", waited.join(", ")))
                if (paused.length)
                    parts.push(i18n("paused in %1", paused.join(", ")))
                if ((day.you || []).some(near))
                    parts.push(i18n("you were at it"))
                return root.clockText(ms) + ": " + (parts.length ? parts.join(" · ") : i18n("nothing went on"))
            }
            function color(kind) {
                return kind === "w" ? Kirigami.Theme.focusColor : kind === "y" ? Kirigami.Theme.neutralTextColor
                                                                              : Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.3)
            }

            SectionTitle {
                text: i18n("Chat by chat")
            }
            RowLayout {
                spacing: Kirigami.Units.largeSpacing
                Repeater {
                    // (only what's drawn: you and the limits on the day's row, a pause on a chat's)
                    model: (lanesBox.dayParts.length ? [["u", i18n("You")]] : [])
                        .concat([["w", i18n("Claude worked")], ["y", i18n("Waited for you")]],
                                lanesBox.paused ? [["p", i18n("Paused (asleep, a limit)")]] : [],
                                (lanesBox.day.limits || []).length ? [["l", i18n("A usage limit stopped a chat")]] : [])
                    delegate: RowLayout {
                        required property var modelData
                        spacing: Kirigami.Units.smallSpacing
                        Rectangle {
                            width: modelData[0] === "l" ? 2 : view.gu * 0.6
                            height: view.gu * 0.6
                            radius: modelData[0] === "l" ? 1 : 2
                            color: modelData[0] === "u" ? view.youColor : modelData[0] === "l" ? view.limitColor : lanesBox.color(modelData[0])
                        }
                        PlasmaComponents3.Label {
                            textFormat: Text.PlainText
                            text: modelData[1]
                            font: Kirigami.Theme.smallFont
                            opacity: 0.8
                        }
                    }
                }
            }
            // The day's own row and the chats', on the same hours: the mouse's
            // moment (lanesRows.hoverMs: a line across them, the readout under them)
            ColumnLayout {
                id: lanesRows
                Layout.fillWidth: true
                spacing: lanesBox.spacing
                readonly property real trackX: lanesBox.nameWidth + Kirigami.Units.smallSpacing
                readonly property real trackWidth: Math.max(1, width - lanesBox.nameWidth - lanesBox.numbersWidth - 2 * Kirigami.Units.smallSpacing)
                readonly property real hoverX: lanesHover.hovered ? lanesHover.point.position.x - trackX : -1
                readonly property bool pointing: hoverX >= 0 && hoverX <= trackWidth
                readonly property real hoverMs: pointing ? lanesBox.t0 + hoverX / trackWidth * lanesBox.span : 0

                HoverHandler {
                    id: lanesHover
                }

            // The day's own row: when you were at it (the thin bar on top), when
            // Claude worked (darker where several chats did), when it waited
            // for you, and where a usage limit stopped a chat
            RowLayout {
                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing
                visible: lanesBox.dayParts.length > 0

                PlasmaComponents3.Label {
                    textFormat: Text.PlainText
                    Layout.preferredWidth: lanesBox.nameWidth
                    text: i18n("All chats")
                    elide: Text.ElideRight
                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                    font.bold: true
                }
                Item {
                    id: dayTrack
                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.round(view.gu * 0.75)

                    Rectangle {
                        anchors.fill: parent
                        radius: 3
                        color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.06)
                    }
                    Repeater {   // (the hours on the axis)
                        model: lanesBox.ticks.length
                        delegate: Rectangle {
                            required property int index
                            x: Math.round(lanesBox.place(lanesBox.ticks[index] || 0, dayTrack.width))
                            width: 1
                            height: dayTrack.height
                            color: view.grid
                        }
                    }
                    Repeater {
                        model: (lanesBox.day.wait || []).length
                        delegate: Rectangle {
                            required property int index
                            readonly property var part: lanesBox.day.wait[index] || [0, 0]
                            x: lanesBox.place(part[0], dayTrack.width)
                            y: dayTrack.height * 0.35
                            width: Math.max(1.5, lanesBox.place(part[1], dayTrack.width) - x)
                            height: dayTrack.height * 0.65
                            radius: 2
                            color: view.waitColor
                        }
                    }
                    Repeater {
                        model: (lanesBox.day.work || []).length
                        delegate: Rectangle {
                            required property int index
                            readonly property var part: lanesBox.day.work[index] || [0, 0, 1]
                            x: lanesBox.place(part[0], dayTrack.width)
                            y: dayTrack.height * 0.35
                            width: Math.max(1.5, lanesBox.place(part[1], dayTrack.width) - x)
                            height: dayTrack.height * 0.65
                            radius: 2
                            color: view.workColor
                            opacity: part[2] >= 3 ? 1 : part[2] === 2 ? 0.8 : 0.6
                        }
                    }
                    Repeater {
                        model: (lanesBox.day.you || []).length
                        delegate: Rectangle {
                            required property int index
                            readonly property var part: lanesBox.day.you[index] || [0, 0]
                            x: lanesBox.place(part[0], dayTrack.width)
                            width: Math.max(1.5, lanesBox.place(part[1], dayTrack.width) - x)
                            height: dayTrack.height * 0.25
                            radius: 1
                            color: view.youColor
                        }
                    }
                    Repeater {
                        model: (lanesBox.day.limits || []).length
                        delegate: Rectangle {
                            required property int index
                            x: lanesBox.place(lanesBox.day.limits[index] || 0, dayTrack.width) - 1
                            width: 2
                            height: dayTrack.height
                            color: view.limitColor
                        }
                    }
                    Rectangle {   // where the mouse points
                        visible: lanesRows.pointing
                        x: Math.round(lanesRows.hoverX)
                        width: 1
                        height: dayTrack.height
                        color: view.ink
                        opacity: 0.5
                    }
                    PlasmaCore.ToolTipArea {
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        mainText: i18n("All chats")
                        subText: i18n("You: %1 · Claude worked %2 (on the clock %3) · it waited %4 for you",
                                      view.hours(lanesBox.day.youMs || 0), view.hours(lanesBox.day.workedMs || 0),
                                      view.hours(lanesBox.day.busyMs || 0), view.hours(lanesBox.day.waitMs || 0))
                    }
                }
                Item {
                    Layout.preferredWidth: lanesBox.numbersWidth
                }
            }
            Repeater {
                model: view.lanes.length
                delegate: RowLayout {
                    id: laneRow
                    required property int index
                    readonly property var lane: view.lanes[index] || ({ name: "", parts: [], workedMs: 0, waitedMs: 0, id: "", host: "" })
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing

                    PlasmaComponents3.Label {
                        textFormat: Text.PlainText
                        Layout.preferredWidth: lanesBox.nameWidth
                        text: (laneRow.lane.host ? root.hostLabel(laneRow.lane.host) + ": " : "") + laneRow.lane.name
                        elide: Text.ElideRight
                        font: Kirigami.Theme.smallFont

                        MouseArea {
                            anchors.fill: parent
                            enabled: !laneRow.lane.host && !!laneRow.lane.id   // (an SSH host's chat: its row in the Chats tab opens it)
                            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                            onClicked: root.openChatById(laneRow.lane.id, laneRow.lane.profileDir || "", "", "", "", "")
                        }
                    }
                    Item {
                        id: laneTrack
                        Layout.fillWidth: true
                        Layout.preferredHeight: Math.round(view.gu * 0.75)

                        Rectangle {
                            anchors.fill: parent
                            radius: 3
                            color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.06)
                        }
                        Repeater {   // (the hours on the axis)
                            model: lanesBox.ticks.length
                            delegate: Rectangle {
                                required property int index
                                x: Math.round(lanesBox.place(lanesBox.ticks[index] || 0, laneTrack.width))
                                width: 1
                                height: laneTrack.height
                                color: view.grid
                            }
                        }
                        Repeater {
                            model: laneRow.lane.parts.length
                            delegate: Rectangle {
                                required property int index
                                readonly property var part: laneRow.lane.parts[index] || [0, 0, "w"]
                                x: (part[0] - lanesBox.t0) / lanesBox.span * laneTrack.width
                                width: Math.max(1.5, (part[1] - part[0]) / lanesBox.span * laneTrack.width)
                                height: laneTrack.height
                                radius: 2
                                color: lanesBox.color(part[2])
                            }
                        }
                        Rectangle {   // where the mouse points
                            visible: lanesRows.pointing
                            x: Math.round(lanesRows.hoverX)
                            width: 1
                            height: laneTrack.height
                            color: view.ink
                            opacity: 0.5
                        }
                        PlasmaCore.ToolTipArea {
                            textFormat: Text.PlainText
                            anchors.fill: parent
                            mainText: laneRow.lane.name
                            subText: i18n("Claude worked %1, waited for you %2", view.hours(laneRow.lane.workedMs), view.hours(laneRow.lane.waitedMs))
                                     + (laneRow.lane.project ? "\n" + laneRow.lane.project : "")
                        }
                    }
                    // (what Claude worked on it today, by its own count, and its cost)
                    PlasmaComponents3.Label {
                        textFormat: Text.PlainText
                        Layout.preferredWidth: lanesBox.numbersWidth
                        horizontalAlignment: Text.AlignRight
                        text: lanesBox.laneNumbers(laneRow.lane)
                        font: Kirigami.Theme.smallFont
                        opacity: 0.8
                    }
                }
            }
            }
            // The axis: its whole hours (none in between: its first and last times)
            Item {
                id: laneAxis
                Layout.fillWidth: true
                Layout.leftMargin: lanesBox.nameWidth + Kirigami.Units.smallSpacing
                Layout.rightMargin: lanesBox.numbersWidth + Kirigami.Units.smallSpacing
                Layout.preferredHeight: smallMetrics.height + 4
                readonly property var marks: lanesBox.ticks.length ? lanesBox.ticks : [lanesBox.t0, lanesBox.t1]

                Repeater {
                    model: laneAxis.marks.length
                    delegate: Item {
                        required property int index
                        readonly property real at: lanesBox.ticks.length ? lanesBox.place(laneAxis.marks[index] || 0, laneAxis.width)
                                                                         : index * laneAxis.width
                        Rectangle {
                            visible: lanesBox.ticks.length > 0
                            x: Math.round(parent.at)
                            width: 1
                            height: 3
                            color: view.ink
                            opacity: 0.4
                        }
                        Text {
                            textFormat: Text.PlainText
                            y: 4
                            x: Math.max(0, Math.min(laneAxis.width - implicitWidth, parent.at - implicitWidth / 2))
                            text: root.clockText(laneAxis.marks[index] || 0)
                            font: Kirigami.Theme.smallFont
                            color: view.ink
                            opacity: 0.6
                        }
                    }
                }
            }
            PlasmaComponents3.Label {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                Layout.leftMargin: lanesBox.nameWidth + Kirigami.Units.smallSpacing
                elide: Text.ElideRight
                font: Kirigami.Theme.smallFont
                opacity: lanesRows.pointing ? 0.9 : 0.5
                text: lanesBox.hoverText()
            }
        }

        // What got done, by project (a chat started in a subfolder of a
        // repository counts for the repository): its commits and the files
        // Claude's edits changed, its time and amount. A click unfolds its
        // chats in place, each with Claude's recap of it and its commits (here
        // and on an SSH host alike); the button at a row's end opens one of
        // this computer's in the Projects tab. Under the list, what Claude did
        // in all, dim.
        ColumnLayout {
            Layout.fillWidth: true
            visible: view.hasData && (view.projects.length > 0 || view.workText() !== "")
            spacing: Math.round(view.gu * 0.2)

            SectionTitle {
                text: i18n("What got done")
            }
            Repeater {
                model: view.projects.length
                delegate: ColumnLayout {
                    id: projectRow
                    required property int index
                    readonly property var project: view.projects[index] || view.emptyProject
                    readonly property string key: project.host + "|" + project.path
                    readonly property bool open: view.openProject === key
                    readonly property string shareTip: view.weekShareTip(project, false)   // (its share of your week)
                    Layout.fillWidth: true
                    spacing: 0

                    Item {
                        Layout.fillWidth: true
                        implicitHeight: projectLine.implicitHeight

                        MouseArea {   // (under the row's button: a click on it is the button's)
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: view.openProject = projectRow.open ? "" : projectRow.key

                            PlasmaCore.ToolTipArea {
                                textFormat: Text.PlainText
                                anchors.fill: parent
                                mainText: (projectRow.project.host ? root.hostLabel(projectRow.project.host) + ": " : "") + projectRow.project.path
                                subText: i18n("Claude worked %1 · %2 at API prices", view.hours(projectRow.project.workedMs),
                                              view.money(projectRow.project.cost))
                                         + "\n" + i18np("%1 prompt", "%1 prompts", projectRow.project.prompts)
                                         + " · " + i18np("%1 chat", "%1 chats", projectRow.project.chatCount)
                                         + view.doneTip(projectRow.project)
                                         + (projectRow.shareTip ? "\n" + projectRow.shareTip : "")
                                         + "\n\n" + (projectRow.open ? i18n("Click to fold its chats.") : i18n("Click for its chats: what each got done."))
                            }
                        }
                        RowLayout {
                            id: projectLine
                            anchors.left: parent.left
                            anchors.right: parent.right
                            spacing: Kirigami.Units.smallSpacing

                            Kirigami.Icon {
                                Layout.preferredWidth: Kirigami.Units.iconSizes.small
                                Layout.preferredHeight: Kirigami.Units.iconSizes.small
                                source: projectRow.open ? Icons.plasma.unfolded : Icons.plasma.folded
                                opacity: 0.6
                            }
                            PlasmaComponents3.Label {
                                textFormat: Text.PlainText
                                Layout.preferredWidth: view.projectNameWidth
                                text: (projectRow.project.host ? root.hostLabel(projectRow.project.host) + ": " : "") + projectRow.project.name
                                elide: Text.ElideMiddle
                                font.bold: projectRow.open
                            }
                            PlasmaComponents3.Label {
                                textFormat: Text.PlainText
                                Layout.preferredWidth: view.projectDoneWidth
                                visible: view.projectDoneWidth > 1
                                text: view.doneText(projectRow.project)
                                elide: Text.ElideRight
                                font: Kirigami.Theme.smallFont
                                opacity: 0.6
                            }
                            Rectangle {   // (its track: where all of it would end)
                                Layout.fillWidth: true
                                Layout.preferredHeight: Math.round(view.gu * 0.4)
                                radius: height / 2
                                color: view.track

                                Rectangle {
                                    width: Math.max(2, parent.width * projectRow.project.workedMs / view.maxProject)
                                    height: parent.height
                                    radius: height / 2
                                    color: view.workColor
                                    opacity: 0.8
                                }
                            }
                            PlasmaComponents3.Label {
                                textFormat: Text.PlainText
                                Layout.preferredWidth: view.projectNumbersWidth
                                horizontalAlignment: Text.AlignRight
                                text: view.projectNumbers(projectRow.project)
                                font: Kirigami.Theme.smallFont
                                opacity: 0.8
                            }
                            // (this computer's: to the Projects tab; an SSH host's has its room, so the numbers line up)
                            HoverButton {
                                id: toProjects
                                usable: !projectRow.project.host
                                opacity: usable ? 1 : 0
                                icon.name: Icons.plasma.project
                                text: i18n("Open in the Projects tab")
                                onClicked: root.showProject(projectRow.project.folder || projectRow.project.path)

                                PlasmaCore.ToolTipArea {
                                    textFormat: Text.PlainText
                                    anchors.fill: parent
                                    active: toProjects.usable
                                    mainText: i18n("Open in the Projects tab")
                                    subText: i18n("All its chats, plans and memories.")
                                }
                            }
                        }
                    }
                    Repeater {   // (made while it's unfolded)
                        id: projectChats
                        readonly property var list: projectRow.open ? projectRow.project.chats : []
                        readonly property real doneWidth: Math.min(view.gu * 7, view.widest(list.map(view.doneText)))
                        readonly property real numbersWidth: view.widest(list.map(view.numbersOf))
                        model: list.length
                        delegate: WeekDoneChat {
                            required property int index
                            chat: projectChats.list[index] || view.emptyChat
                            where: view.doneText(chat)
                            indent: Kirigami.Units.iconSizes.small + Kirigami.Units.smallSpacing
                            numbers: view.numbersOf(chat)
                            tip: view.weekShareTip(chat, false)
                            whereWidth: projectChats.doneWidth
                            numbersWidth: projectChats.numbersWidth
                        }
                    }
                    PlasmaComponents3.Label {
                        textFormat: Text.PlainText
                        Layout.fillWidth: true
                        Layout.leftMargin: Kirigami.Units.iconSizes.small + Kirigami.Units.smallSpacing * 2
                        visible: projectRow.open && projectRow.project.chatCount > projectRow.project.chats.length
                        text: i18np("and %1 more chat", "and %1 more chats",
                                    projectRow.project.chatCount - projectRow.project.chats.length)
                        font: Kirigami.Theme.smallFont
                        opacity: 0.6
                    }
                }
            }
            // What Claude did in all: its tool calls, commands, edits, subagents
            PlasmaComponents3.Label {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                Layout.topMargin: Math.round(view.gu * 0.2)
                visible: text !== ""
                wrapMode: Text.Wrap
                text: view.workText()
                font: Kirigami.Theme.smallFont
                opacity: 0.6

                PlasmaCore.ToolTipArea {
                    textFormat: Text.PlainText
                    anchors.fill: parent
                    mainText: i18n("What Claude did")
                    subText: view.workBeforeText()
                }
            }
        }

        // Your plan: what these days meant for each account's plan (week.py
        // plan_use: how much of its week they used, its full 5-hour windows,
        // how often it ran out and how long that held chats), its line's
        // tooltip how each is worked out; on today's Day its windows now
        // under it, how they filled up (the widget's usage history)
        ColumnLayout {
            id: planSection
            Layout.fillWidth: true
            visible: view.hasData && view.planIds.length > 0
            spacing: Math.round(view.gu * 0.2)
            // (the widest text beside the bars, for all of them: the bars get one length)
            readonly property real textWidth: {
                let w = 0
                for (const a of view.plan)
                    for (const win of a.windows)
                        w = Math.max(w, planFont.advanceWidth(view.planText(win)))
                return Math.ceil(w)
            }

            FontMetrics {
                id: planFont
                font: Kirigami.Theme.smallFont
            }
            SectionTitle {
                text: i18n("Your plan")
            }
            Repeater {
                model: view.planIds.length
                delegate: ColumnLayout {
                    id: planAccount
                    required property int index
                    readonly property string id: view.planIds[index] || ""
                    readonly property var use: view.planUse.find(u => u.account === id) || null
                    readonly property var account: view.plan.find(p => p.account === id) || ({ name: "", windows: [] })
                    readonly property var known: view.accounts.find(a => a.id === id) || null
                    readonly property string plan: use && use.plan ? use.plan : known && known.plan ? known.plan : ""
                    Layout.fillWidth: true
                    Layout.topMargin: index > 0 ? Math.round(view.gu * 0.3) : 0
                    spacing: Math.round(view.gu * 0.2)

                    PlasmaComponents3.Label {   // (two accounts or more: whose)
                        textFormat: Text.PlainText
                        Layout.fillWidth: true
                        visible: view.planIds.length > 1
                        text: (planAccount.use ? planAccount.use.name : planAccount.account.name)
                              + (planAccount.plan ? " · " + planAccount.plan : "")
                        font.bold: true
                        elide: Text.ElideRight
                    }
                    PlasmaComponents3.Label {
                        textFormat: Text.PlainText
                        Layout.fillWidth: true
                        visible: !!planAccount.use
                        text: planAccount.use ? view.planUseText(planAccount.use) : ""
                        wrapMode: Text.Wrap

                        PlasmaCore.ToolTipArea {
                            textFormat: Text.PlainText
                            anchors.fill: parent
                            mainText: i18n("Your plan")
                            subText: planAccount.use ? view.planUseTip(planAccount.use) : ""
                        }
                    }
                    Repeater {
                        model: planAccount.account.windows.length
                        delegate: RowLayout {
                            id: planRow
                            required property int index
                            readonly property var win: planAccount.account.windows[index] || view.emptyWindow
                            readonly property real from: win.resetsAt && view.windowMs[win.key] ? win.resetsAt - view.windowMs[win.key]
                                                                                              : (win.points.length ? win.points[0][0] : 0)
                            readonly property real until: Math.max(win.resetsAt || 0, from + 1)
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.smallSpacing

                            PlasmaComponents3.Label {
                                textFormat: Text.PlainText
                                Layout.preferredWidth: view.gu * 4
                                text: planRow.win.label
                                elide: Text.ElideRight
                            }
                            // how the window filled up, from its start to its reset
                            Canvas {
                                id: fillChart
                                Layout.fillWidth: true
                                Layout.preferredHeight: Math.round(view.gu * 1.1)
                                readonly property color lineColor: view.planColor(planRow.win.pct)
                                onWidthChanged: requestPaint()
                                onHeightChanged: requestPaint()
                                onLineColorChanged: requestPaint()
                                Connections {
                                    target: planRow
                                    function onWinChanged() {
                                        fillChart.requestPaint()
                                    }
                                }
                                onPaint: {
                                    const ctx = getContext("2d")
                                    ctx.reset()
                                    const w = width, h = height
                                    const x = ms => Math.max(0, Math.min(w, (ms - planRow.from) / (planRow.until - planRow.from) * w))
                                    const y = pct => h - 0.5 - Math.max(0, Math.min(100, pct)) / 100 * (h - 1)
                                    ctx.fillStyle = Qt.rgba(view.ink.r, view.ink.g, view.ink.b, 0.06)
                                    ctx.fillRect(0, 0, w, h)
                                    const points = planRow.win.points.filter(p => p[0] >= planRow.from)
                                    if (!points.length)
                                        return
                                    const end = Math.min(root.now, planRow.until)
                                    ctx.beginPath()
                                    ctx.moveTo(x(points[0][0]), h)
                                    for (const p of points)
                                        ctx.lineTo(x(p[0]), y(p[1]))
                                    ctx.lineTo(x(end), y(points[points.length - 1][1]))
                                    ctx.lineTo(x(end), h)
                                    ctx.closePath()
                                    const c = lineColor
                                    ctx.fillStyle = Qt.rgba(c.r, c.g, c.b, 0.3)
                                    ctx.fill()
                                    ctx.beginPath()
                                    ctx.moveTo(x(points[0][0]), y(points[0][1]))
                                    for (const p of points)
                                        ctx.lineTo(x(p[0]), y(p[1]))
                                    ctx.lineTo(x(end), y(points[points.length - 1][1]))
                                    ctx.strokeStyle = c
                                    ctx.lineWidth = 1.5
                                    ctx.stroke()
                                }

                                PlasmaCore.ToolTipArea {
                                    textFormat: Text.PlainText
                                    anchors.fill: parent
                                    mainText: i18n("%1: %2% used", planRow.win.label, Math.round(planRow.win.pct))
                                    subText: i18n("How this window of your plan filled up, from its start (on the left) to when it resets (on the right), as Talpy Den saw it.")
                                }
                            }
                            PlasmaComponents3.Label {
                                textFormat: Text.PlainText
                                Layout.preferredWidth: planSection.textWidth
                                horizontalAlignment: Text.AlignRight
                                text: view.planText(planRow.win)
                                font: Kirigami.Theme.smallFont
                                color: planRow.win.pct >= 90 ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.textColor
                                opacity: 0.8
                            }
                        }
                    }
                }
            }
        }

        // Where the usage went: by model (its amount at API prices), then
        // weighed as Claude Code's /usage weighs it toward your plan's limits
        // (subagents, over 150k of context, effort levels: week.py
        // usage_mix), each with its share the period before
        ColumnLayout {
            Layout.fillWidth: true
            visible: view.hasData && (view.models.length > 0 || view.usageMix.length > 0)
            spacing: Math.round(view.gu * 0.2)

            SectionTitle {
                text: i18n("Where the usage went")
            }
            Repeater {
                model: view.models.length
                delegate: RowLayout {
                    id: modelRow
                    required property int index
                    readonly property var entry: view.models[index] || view.emptyModel
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing

                    PlasmaComponents3.Label {
                        textFormat: Text.PlainText
                        Layout.preferredWidth: view.gu * 7
                        text: modelRow.entry.model
                        elide: Text.ElideRight
                    }
                    Rectangle {   // (its track: where all of it would end)
                        Layout.fillWidth: true
                        Layout.preferredHeight: Math.round(view.gu * 0.4)
                        radius: height / 2
                        color: view.track

                        Rectangle {
                            width: Math.max(2, parent.width * modelRow.entry.share)
                            height: parent.height
                            radius: height / 2
                            color: view.youColor
                        }
                    }
                    PlasmaComponents3.Label {
                        textFormat: Text.PlainText
                        Layout.preferredWidth: view.usageNumbersWidth
                        horizontalAlignment: Text.AlignRight
                        text: view.modelRowText(modelRow.entry)
                        font: Kirigami.Theme.smallFont
                        opacity: 0.8

                        PlasmaCore.ToolTipArea {
                            textFormat: Text.PlainText
                            anchors.fill: parent
                            mainText: modelRow.entry.model
                            subText: i18n("%1 at API prices, %2 of the amount of these days · %3", view.money(modelRow.entry.cost), view.shareText(modelRow.entry.share),
                                          i18np("%1 request", "%1 requests", modelRow.entry.requests))
                                     + (modelRow.entry.guessed ? "\n" + view.guessedModelTip(modelRow.entry) : "")
                                     + (modelRow.entry.before === null || modelRow.entry.before === undefined ? view.uncomparedText()
                                        : view.beforeText(100 * modelRow.entry.before, "points"))
                        }
                    }
                }
            }
            // (then weighed as your plan's limits count it: a request's tokens by kind, times its model's weight)
            PlasmaComponents3.Label {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                Layout.topMargin: Math.round(view.gu * 0.3)
                visible: view.usageMix.length > 0
                text: i18n("As your plan's limits count it (Claude Code's /usage):")
                elide: Text.ElideRight
                font: Kirigami.Theme.smallFont
                opacity: 0.6
            }
            Repeater {
                model: view.usageMix.length
                delegate: RowLayout {
                    id: mixRow
                    required property int index
                    readonly property var part: view.usageMix[index] || ({ key: "", pct: 0, before: null })
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing

                    PlasmaComponents3.Label {
                        textFormat: Text.PlainText
                        Layout.preferredWidth: view.gu * 7
                        text: view.mixLabel(mixRow.part.key)
                        elide: Text.ElideRight
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: Math.round(view.gu * 0.4)
                        radius: height / 2
                        color: view.track

                        Rectangle {
                            width: Math.max(mixRow.part.pct > 0 ? 2 : 0, parent.width * Math.min(1, mixRow.part.pct / 100))
                            height: parent.height
                            radius: height / 2
                            color: view.youColor
                        }
                    }
                    PlasmaComponents3.Label {
                        textFormat: Text.PlainText
                        Layout.preferredWidth: view.usageNumbersWidth
                        horizontalAlignment: Text.AlignRight
                        text: view.mixNumbers(mixRow.part)
                        font: Kirigami.Theme.smallFont
                        opacity: 0.8

                        PlasmaCore.ToolTipArea {
                            textFormat: Text.PlainText
                            anchors.fill: parent
                            mainText: view.mixLabel(mixRow.part.key)
                            subText: view.mixTip(mixRow.part)
                        }
                    }
                }
            }
        }

        // What would use less of your plan (Claude Code's /usage rules, coming
        // back to chats whose cache had expired, waits, limits), each with
        // what acts on it: a command to copy, the chats it names (a name
        // opens its chat; Stop, Keep going where the chat list has them), the
        // Permissions tab; too little in these days: a dim line instead
        // (week.py: tooLittle)
        ColumnLayout {
            id: tipsBox
            Layout.fillWidth: true
            visible: view.hasData
            spacing: Kirigami.Units.smallSpacing
            // (the commands in one column as wide as the widest, "Copied"
            // too: the shares before them line up; monospace, so the longest)
            readonly property real commandWidth: view.tipsShown.some(t => t.command) ? commandProbe.implicitWidth : 0

            PlasmaComponents3.ToolButton {
                id: commandProbe
                visible: false
                font.family: "monospace"
                font.pointSize: Kirigami.Theme.smallFont.pointSize
                // (the Permissions tab's button has its icon)
                icon.name: view.tipsShown.some(t => t.key === "waits") ? Icons.plasma.permissions : ""
                text: view.tipsShown.map(t => t.key === "waits" ? i18n("Permissions") : t.command || "").concat([i18n("Copied")])
                          .reduce((a, b) => b.length > a.length ? b : a, "")
            }
            SectionTitle {
                text: i18n("What could use less of your plan")
            }
            PlasmaComponents3.Label {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                visible: view.tipsShown.length === 0
                wrapMode: Text.Wrap
                opacity: 0.7
                text: view.recap && view.recap.tooLittle ? i18n("Too little here to go on: tips need 20 prompts or an hour of Claude's work.")
                                                         : i18n("Nothing stands out: no habit takes a tenth of the usage shown.")
            }
            Repeater {
                model: view.tipsShown.length
                delegate: RowLayout {
                    id: tipRow
                    required property int index
                    readonly property var tip: view.tipsShown[index] || view.emptyTip
                    readonly property var chats: tip.chats || []
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing

                    Kirigami.Icon {
                        Layout.alignment: Qt.AlignTop
                        Layout.preferredWidth: Kirigami.Units.iconSizes.small
                        Layout.preferredHeight: Kirigami.Units.iconSizes.small
                        source: view.tipIcon(tipRow.tip.key)
                        opacity: 0.8

                        PlasmaCore.ToolTipArea {
                            textFormat: Text.PlainText
                            anchors.fill: parent
                            mainText: view.tipSource(tipRow.tip.key)
                        }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 0

                        PlasmaComponents3.Label {
                            textFormat: Text.PlainText
                            Layout.fillWidth: true
                            wrapMode: Text.Wrap
                            text: tipRow.tip.title
                        }
                        PlasmaComponents3.Label {
                            textFormat: Text.PlainText
                            Layout.fillWidth: true
                            visible: text !== ""
                            wrapMode: Text.Wrap
                            text: tipRow.tip.detail
                            font: Kirigami.Theme.smallFont
                            opacity: 0.7
                        }
                        // the chats it names: a name opens its chat; Stop or
                        // Keep going where the chat list offers it now
                        Repeater {
                            model: tipRow.chats.length
                            delegate: ColumnLayout {
                                id: tipChat
                                required property int index
                                readonly property var chat: tipRow.chats[index] || view.emptyChat
                                readonly property string key: (chat.host || "") + "|" + chat.chatId
                                readonly property string act: view.tipChatAct(tipRow.tip.key, chat)
                                Layout.fillWidth: true
                                spacing: 0

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: Kirigami.Units.smallSpacing

                                    WeekChatLine {
                                        chat: tipChat.chat
                                        where: ""
                                        numbers: tipChat.chat.note || ""
                                        indent: Kirigami.Units.smallSpacing   // (under the tip, in the small font)
                                    }
                                    PlasmaComponents3.ToolButton {
                                        visible: tipChat.act === "stop" || tipChat.act === "keep" || tipChat.act === "keepAtReset"
                                        icon.name: tipChat.act === "stop" ? Icons.plasma.stop : Icons.plasma.keepGoing
                                        text: tipChat.act === "stop" ? i18n("Stop") : i18n("Keep going")
                                        font: Kirigami.Theme.smallFont
                                        onClicked: {
                                            if (tipChat.act === "stop")
                                                view.stopAsked = view.stopAsked === tipChat.key ? "" : tipChat.key
                                            else
                                                view.tipChatDo(tipRow.tip.key, tipChat.chat)
                                        }

                                        PlasmaCore.ToolTipArea {
                                            textFormat: Text.PlainText
                                            anchors.fill: parent
                                            mainText: tipChat.act === "stop" ? i18n("Stop this chat") : i18n("Keep going until it's done")
                                            subText: tipChat.act === "stop"
                                                ? i18n("Asks first. It's idle: Claude quits, and the chat is kept.")
                                                : tipChat.act === "keepAtReset"
                                                ? i18n("It goes on by itself a minute after the limit resets, in the background, and again after each later limit, until a turn of it ends by itself.")
                                                : i18n("When a usage limit stops this chat, it goes on by itself in the background a minute after the limit resets, and again after each later one, until a turn of it ends by itself.")
                                        }
                                    }
                                    PlasmaComponents3.Label {
                                        textFormat: Text.PlainText
                                        visible: tipChat.act === "kept"
                                        text: i18nc("a chat that goes on by itself after usage limits", "Keeps going")
                                        font: Kirigami.Theme.smallFont
                                        opacity: 0.6
                                    }
                                }
                                // Stop it? (made only while it's asked)
                                Loader {
                                    active: view.stopAsked === tipChat.key && tipChat.act === "stop"
                                    visible: active
                                    Layout.fillWidth: true
                                    sourceComponent: Kirigami.InlineMessage {
                                        visible: true   // (an InlineMessage is hidden till told: the Loader shows it only while it's wanted)
                                        type: Kirigami.MessageType.Warning
                                        text: "<span>" + root.escapeHtml(view.stopAskText(tipChat.chat)) + "</span>"
                                        actions: [
                                            Kirigami.Action {
                                                text: i18n("Stop")
                                                icon.name: Icons.plasma.stop
                                                onTriggered: {
                                                    view.stopAsked = ""
                                                    view.tipChatDo(tipRow.tip.key, tipChat.chat)
                                                }
                                            },
                                            Kirigami.Action {
                                                text: i18n("Cancel")
                                                onTriggered: view.stopAsked = ""
                                            }
                                        ]
                                    }
                                }
                            }
                        }
                        PlasmaComponents3.Label {
                            textFormat: Text.PlainText
                            visible: (tipRow.tip.more || 0) > 0
                            text: i18np("and %1 more chat", "and %1 more chats", tipRow.tip.more || 0)
                            font: Kirigami.Theme.smallFont
                            opacity: 0.6
                        }
                    }
                    ColumnLayout {
                        Layout.alignment: Qt.AlignTop
                        visible: view.tipShareShown(tipRow.tip)
                        spacing: 0

                        PlasmaComponents3.Label {
                            textFormat: Text.PlainText
                            Layout.alignment: Qt.AlignRight
                            text: view.tipShareText(tipRow.tip)
                            font: Kirigami.Theme.smallFont
                            opacity: 0.8

                            PlasmaCore.ToolTipArea {
                                textFormat: Text.PlainText
                                anchors.fill: parent
                                mainText: view.tipShareMain(tipRow.tip)
                                subText: view.tipShareTip(tipRow.tip)
                            }
                        }
                        PlasmaComponents3.Label {   // (how it moved)
                            textFormat: Text.PlainText
                            Layout.alignment: Qt.AlignRight
                            visible: text !== ""
                            text: view.tipWas(tipRow.tip)
                            font: Kirigami.Theme.smallFont
                            opacity: 0.6
                        }
                    }
                    Item {   // (no command: its room, so the share stands where the others do)
                        visible: tipRow.tip.command === "" && tipsBox.commandWidth > 0
                        Layout.preferredWidth: tipsBox.commandWidth
                    }
                    PlasmaComponents3.ToolButton {   // (Claude waited for your answers: the Permissions tab)
                        Layout.alignment: Qt.AlignTop
                        Layout.preferredWidth: tipsBox.commandWidth
                        visible: tipRow.tip.key === "waits"
                        icon.name: Icons.plasma.permissions
                        text: i18n("Permissions")
                        font.pointSize: Kirigami.Theme.smallFont.pointSize
                        onClicked: root.openPermissions()

                        PlasmaCore.ToolTipArea {
                            textFormat: Text.PlainText
                            anchors.fill: parent
                            mainText: i18n("Open the Permissions tab")
                            subText: i18n("The permission prompts you answered, and the rules that would let the same go without asking.")
                        }
                    }
                    PlasmaComponents3.ToolButton {
                        Layout.alignment: Qt.AlignTop
                        Layout.preferredWidth: tipsBox.commandWidth
                        visible: tipRow.tip.command !== "" && tipRow.tip.key !== "waits"
                        text: view.copied === tipRow.tip.command && tipRow.tip.command ? i18n("Copied") : tipRow.tip.command
                        font.family: "monospace"
                        font.pointSize: Kirigami.Theme.smallFont.pointSize
                        onClicked: {
                            clipboard.put(tipRow.tip.command)
                            view.copied = tipRow.tip.command
                            copiedTimer.restart()
                        }

                        PlasmaCore.ToolTipArea {
                            textFormat: Text.PlainText
                            anchors.fill: parent
                            mainText: i18n("Copy %1", tipRow.tip.command)
                            subText: i18n("Type it in a chat of yours.")
                        }
                    }
                }
            }
        }

        // Your plan's limits over time, Overall's last section (it's the same
        // whatever the span; the other spans' Your plan says what the plan
        // meant for their days), each account in three parts: how full its
        // weeks got (does the plan fit you?), the changes of its limits, and
        // what a window holds (one estimate: the sizes, the share of the
        // week, the tokens and the chart agree). Read only once it scrolls
        // into view (limitsWant); while its numbers come, a dim line with
        // room kept (what was read before stays, dimmed)
        ColumnLayout {
            id: limitsSection
            Layout.fillWidth: true
            visible: view.hasData && view.recap.span === "all"
            opacity: view.limitsDim ? 0.6 : 1
            spacing: Math.round(view.gu * 0.2)

            SectionTitle {
                text: i18n("Your plan's limits over time")
            }
            PlasmaComponents3.Label {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                Layout.preferredHeight: view.limitsData ? implicitHeight : view.gu * 8
                visible: !view.limitsData || root.limitsError !== ""
                verticalAlignment: Text.AlignTop
                text: root.limitsError ? i18n("Couldn't work it out: %1", root.limitsError)
                                       : i18n("Working out how full your plan's weeks got and how much its windows hold, from your chats and the limit readings kept.")
                color: root.limitsError ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.textColor
                opacity: root.limitsError ? 1 : 0.6
                wrapMode: Text.Wrap
            }
            PlasmaComponents3.Label {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                visible: !!view.limitsData && view.limitsShown.length === 0
                text: i18n("Not enough readings yet: a few 5-hour windows used past half tell how much one holds.")
                opacity: 0.6
                wrapMode: Text.Wrap
            }
            // (two plans or more: side by side)
            GridLayout {
                Layout.fillWidth: true
                visible: view.limitsCompared
                columns: 4
                columnSpacing: Kirigami.Units.largeSpacing
                rowSpacing: 0

                Repeater {
                    model: [i18n("Plan"), i18n("5-hour window"), i18n("Week"), i18n("5-hour share")]
                    delegate: PlasmaComponents3.Label {
                        required property var modelData
                        required property int index
                        textFormat: Text.PlainText
                        Layout.fillWidth: index === 0
                        horizontalAlignment: index ? Text.AlignRight : Text.AlignLeft
                        text: modelData
                        font.bold: true
                        opacity: 0.75
                    }
                }
                Repeater {
                    model: view.limitsCompared ? view.limitsShown.length * 4 : 0
                    delegate: PlasmaComponents3.Label {
                        required property int index
                        readonly property var account: view.limitsShown[Math.floor(index / 4)] || view.emptyLimits
                        readonly property int column: index % 4
                        textFormat: Text.PlainText
                        Layout.fillWidth: column === 0
                        horizontalAlignment: column ? Text.AlignRight : Text.AlignLeft
                        elide: Text.ElideRight
                        text: column === 0 ? account.name + " · " + (account.plan || "?")
                            : column === 1 ? (account.now.fiveHour ? view.limitValueText("", account.now.fiveHour) : "–")
                            : column === 2 ? (account.now.weeks.seven_day ? view.limitValueText("", account.now.weeks.seven_day) : "–")
                            : (account.now.share ? (account.now.share.how === "readings" ? "" : "≈ ") + Math.round(account.now.share.pct) + "%" : "–")
                    }
                }
            }
            Repeater {
                model: view.limitsShown.length
                delegate: ColumnLayout {
                    id: limitsOf
                    required property int index
                    readonly property var account: view.limitsShown[index] || view.emptyLimits
                    readonly property var fit: Limits.fit(account)
                    // (every account's chart on one time line: a day is at the same place in each)
                    readonly property var chart: Limits.dots(account, view.limitsNow, view.limitsStart)
                    readonly property var mix: Limits.mix(account.now.costs, account.now.tokens)
                    // (the sizes' column: as wide as the widest, a range with its count too)
                    readonly property real valueWidth: Math.max(view.gu * 4.5, Math.ceil(Math.max(0, ...Limits.keys(account).map(k =>
                        textMetrics.advanceWidth(view.limitValueText(k, Limits.size(account, k)))))) * 1.08 + 1)
                    Layout.fillWidth: true
                    Layout.topMargin: Math.round(view.gu * 0.2)
                    spacing: Math.round(view.gu * 0.2)

                    component Part: RowLayout {   // (a part's heading: what's in it)
                        property alias text: partTitle.text
                        property string note: ""
                        Layout.fillWidth: true
                        Layout.topMargin: Math.round(view.gu * 0.35)
                        spacing: Kirigami.Units.smallSpacing

                        PlasmaComponents3.Label {
                            id: partTitle
                            textFormat: Text.PlainText
                            font.bold: true
                            opacity: 0.8
                        }
                        PlasmaComponents3.Label {
                            textFormat: Text.PlainText
                            Layout.fillWidth: true
                            visible: parent.note !== ""
                            text: "· " + parent.note
                            elide: Text.ElideRight
                            font: Kirigami.Theme.smallFont
                            opacity: 0.6
                        }
                    }
                    component Line: PlasmaComponents3.Label {   // (a line of a part, with how it's worked out)
                        property string tip: ""
                        textFormat: Text.PlainText
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        visible: text !== ""

                        PlasmaCore.ToolTipArea {
                            anchors.fill: parent
                            textFormat: Text.PlainText
                            active: parent.tip !== ""
                            mainText: parent.text
                            subText: parent.tip
                        }
                    }

                    PlasmaComponents3.Label {
                        textFormat: Text.PlainText
                        Layout.fillWidth: true
                        visible: text !== ""
                        text: (view.limitsShown.length > 1 ? limitsOf.account.name + " · " : "") + (limitsOf.account.plan || "")
                        font.bold: true
                        elide: Text.ElideRight
                    }

                    // ---- how full your weeks got: a bar per week, newest first
                    Part {
                        visible: limitsOf.fit.weeks.length > 0
                        text: i18n("How full your weeks got")
                    }
                    Line {
                        visible: limitsOf.fit.weeks.length > 0
                        text: view.limitFitText(limitsOf.account)
                        tip: view.limitFitTip()
                    }
                    Repeater {
                        model: limitsOf.fit.weeks.length
                        delegate: Item {
                            id: weekRow
                            required property int index
                            readonly property var week: limitsOf.fit.weeks[index] || view.emptyLimitWeek
                            Layout.fillWidth: true
                            implicitHeight: weekCol.implicitHeight

                            ColumnLayout {
                                id: weekCol
                                anchors.left: parent.left
                                anchors.right: parent.right
                                spacing: 0

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: Kirigami.Units.smallSpacing

                                    PlasmaComponents3.Label {
                                        id: weekName
                                        textFormat: Text.PlainText
                                        Layout.preferredWidth: view.gu * 5.5
                                        text: view.limitWeekLabel(weekRow.week)
                                        font.bold: weekRow.week.now
                                        elide: Text.ElideRight
                                    }
                                    Rectangle {
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: Math.round(view.gu * 0.4)
                                        radius: height / 2
                                        color: view.track

                                        Rectangle {
                                            width: Math.max(weekRow.week.pct > 0 ? 2 : 0, parent.width * Math.min(1, weekRow.week.pct / 100))
                                            height: parent.height
                                            radius: height / 2
                                            color: view.planColor(weekRow.week.pct)
                                        }
                                        Rectangle {   // (it ran out: a red mark, as the timeline's)
                                            visible: !!weekRow.week.ranOutAt
                                            x: parent.width - width
                                            anchors.verticalCenter: parent.verticalCenter
                                            width: 2
                                            height: Math.round(view.gu * 0.8)
                                            color: view.limitColor
                                        }
                                    }
                                    PlasmaComponents3.Label {
                                        textFormat: Text.PlainText
                                        Layout.preferredWidth: view.gu * 4.5
                                        horizontalAlignment: Text.AlignRight
                                        text: view.limitWeekPct(weekRow.week)
                                        font: Kirigami.Theme.smallFont
                                        color: weekRow.week.pct >= 90 ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.textColor
                                        opacity: weekRow.week.pct >= 90 ? 1 : 0.8
                                    }
                                }
                                PlasmaComponents3.Label {
                                    textFormat: Text.PlainText
                                    Layout.fillWidth: true
                                    Layout.leftMargin: weekName.width + Kirigami.Units.smallSpacing
                                    visible: text !== ""
                                    text: view.limitWeekNote(weekRow.week)
                                    font: Kirigami.Theme.smallFont
                                    opacity: 0.6
                                    elide: Text.ElideRight
                                }
                            }
                            PlasmaCore.ToolTipArea {
                                anchors.fill: parent
                                textFormat: Text.PlainText
                                mainText: view.limitWeekLabel(weekRow.week)
                                subText: view.limitWeekTip(weekRow.week)
                            }
                        }
                    }

                    // ---- changes of your limits: each change, then since when none
                    Part {
                        text: i18n("Changes of your limits")
                    }
                    Repeater {
                        model: limitsOf.account.events.length
                        delegate: RowLayout {
                            id: eventLine
                            required property int index
                            readonly property var event: limitsOf.account.events[index]
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.smallSpacing

                            Rectangle {
                                Layout.preferredWidth: 2
                                Layout.fillHeight: true
                                color: view.waitColor
                            }
                            Line {
                                text: view.limitEventText(eventLine.event)
                                tip: view.limitEventTip(eventLine.event)
                                font: Kirigami.Theme.smallFont
                            }
                        }
                    }
                    Line {
                        text: view.limitNoChangeText(limitsOf.account)
                        tip: view.limitNoChangeTip()
                        font: Kirigami.Theme.smallFont
                        opacity: 0.7
                    }

                    // ---- what a window holds: the estimate, its share of the week, how long it lasts, in tokens, the windows
                    Part {
                        visible: Limits.keys(limitsOf.account).length > 0
                        text: i18n("What a window holds")
                        note: i18n("estimates")
                    }
                    Repeater {
                        model: Limits.keys(limitsOf.account)
                        delegate: Item {
                            id: sizeLine
                            required property var modelData
                            readonly property var size: Limits.size(limitsOf.account, modelData)
                            Layout.fillWidth: true
                            implicitHeight: sizeRow.implicitHeight

                            RowLayout {
                                id: sizeRow
                                anchors.left: parent.left
                                anchors.right: parent.right
                                spacing: Kirigami.Units.smallSpacing

                                PlasmaComponents3.Label {
                                    textFormat: Text.PlainText
                                    Layout.preferredWidth: view.gu * 7
                                    text: view.limitLabel(sizeLine.modelData)
                                    elide: Text.ElideRight
                                }
                                PlasmaComponents3.Label {
                                    textFormat: Text.PlainText
                                    Layout.preferredWidth: limitsOf.valueWidth
                                    horizontalAlignment: Text.AlignRight
                                    text: view.limitValueText(sizeLine.modelData, sizeLine.size)
                                    font.bold: !(sizeLine.size && sizeLine.size.rough)
                                }
                                Item {
                                    Layout.fillWidth: true
                                }
                            }
                            PlasmaCore.ToolTipArea {
                                anchors.fill: parent
                                textFormat: Text.PlainText
                                mainText: view.limitLabel(sizeLine.modelData)
                                subText: view.limitSizeTip(sizeLine.modelData, limitsOf.account)
                            }
                        }
                    }
                    Line {   // (a full 5-hour window's share of the week, and where it's from)
                        text: limitsOf.account.now.share ? view.limitShareText(limitsOf.account.now.share) + " · "
                                                           + view.limitShareHow(limitsOf.account.now.share) : ""
                        tip: view.limitShareTip(limitsOf.account.now.share)
                    }
                    Line {
                        text: view.limitFillText(limitsOf.account.now.fill)
                        tip: view.limitFillTip()
                    }
                    Line {
                        text: view.limitTokensText(limitsOf.account)
                        tip: view.limitTokensTip(limitsOf.account)
                    }
                    // what fills a window, by API price: a bar the section's width (each
                    // part at least a few pixels, so a small one still shows), its legend under it
                    ColumnLayout {
                        Layout.fillWidth: true
                        visible: limitsOf.mix.parts.length > 0
                        spacing: 3

                        Row {
                            id: mixBar
                            Layout.fillWidth: true
                            readonly property real room: width - 2 * Math.max(0, limitsOf.mix.parts.length - 1) - 4 * limitsOf.mix.parts.length
                            spacing: 2

                            Repeater {
                                model: limitsOf.mix.parts.length
                                delegate: Rectangle {
                                    required property int index
                                    readonly property var part: limitsOf.mix.parts[index]
                                    width: 4 + part.share * Math.max(0, mixBar.room)
                                    height: Math.round(view.gu * 0.3)
                                    radius: height / 2
                                    color: view.limitPartColor(part.kind)
                                }
                            }
                        }
                        Flow {
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.largeSpacing

                            Repeater {
                                model: limitsOf.mix.parts.length
                                delegate: Row {
                                    required property int index
                                    readonly property var part: limitsOf.mix.parts[index]
                                    spacing: Kirigami.Units.smallSpacing

                                    Rectangle {
                                        anchors.verticalCenter: parent.verticalCenter
                                        width: Math.round(view.gu * 0.45)
                                        height: width
                                        radius: 2
                                        color: view.limitPartColor(parent.part.kind)
                                    }
                                    PlasmaComponents3.Label {
                                        textFormat: Text.PlainText
                                        text: view.limitPartText(parent.part)
                                        font: Kirigami.Theme.smallFont
                                        opacity: 0.6
                                    }
                                }
                            }
                            PlasmaComponents3.Label {
                                textFormat: Text.PlainText
                                text: i18n("by API price")
                                font: Kirigami.Theme.smallFont
                                opacity: 0.6
                            }
                        }
                    }
                    // the 5-hour windows: a dot each at what it held, the line
                    // at the estimate, each stretch of the same limits on its own scale
                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.topMargin: Math.round(view.gu * 0.2)
                        visible: limitsOf.chart.dots.length > 0
                        spacing: 2

                        PlasmaComponents3.Label {
                            textFormat: Text.PlainText
                            Layout.fillWidth: true
                            text: view.limitChartText(limitsOf.account, limitsOf.chart)
                            font: Kirigami.Theme.smallFont
                            opacity: 0.6
                            elide: Text.ElideRight
                        }
                        Canvas {
                            id: dotsChart
                            Layout.fillWidth: true
                            Layout.preferredHeight: Math.round(view.gu * 2.6)
                            onWidthChanged: requestPaint()
                            Connections {
                                target: limitsOf
                                function onChartChanged() {
                                    dotsChart.requestPaint()
                                }
                            }
                            onPaint: {
                                const ctx = getContext("2d")
                                ctx.reset()
                                const w = width, h = height, c = limitsOf.chart
                                const y = v => h - 3.5 - v * (h - 7)
                                ctx.fillStyle = view.grid
                                ctx.fillRect(0, 0, w, h)
                                ctx.fillStyle = view.waitColor
                                for (const x of c.marks)
                                    ctx.fillRect(Math.round(x * w), 0, 1, h)
                                ctx.strokeStyle = view.youColor
                                ctx.lineWidth = 2
                                for (const l of c.lines) {
                                    ctx.globalAlpha = l.dim ? 0.4 : 1
                                    ctx.beginPath()
                                    ctx.moveTo(l.x1 * w, y(l.y))
                                    ctx.lineTo(l.x2 * w, y(l.y))
                                    ctx.stroke()
                                }
                                ctx.fillStyle = view.workColor
                                for (const d of c.dots) {
                                    ctx.globalAlpha = d.dim ? 0.35 : 1
                                    ctx.beginPath()
                                    ctx.arc(Math.max(3.5, Math.min(w - 3.5, d.x * w)), y(d.y), 3.5, 0, 2 * Math.PI)
                                    ctx.fill()
                                }
                                ctx.globalAlpha = 1
                            }
                            PlasmaCore.ToolTipArea {
                                anchors.fill: parent
                                textFormat: Text.PlainText
                                mainText: i18n("5-hour windows")
                                subText: view.limitChartTip(limitsOf.chart)
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true

                            PlasmaComponents3.Label {
                                textFormat: Text.PlainText
                                Layout.fillWidth: true
                                text: view.limitDay(view.limitsStart)
                                font: Kirigami.Theme.smallFont
                                opacity: 0.6
                            }
                            PlasmaComponents3.Label {
                                textFormat: Text.PlainText
                                text: i18n("today")
                                font: Kirigami.Theme.smallFont
                                opacity: 0.6
                            }
                        }
                    }
                }
            }
            PlasmaComponents3.Label {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                Layout.topMargin: Math.round(view.gu * 0.3)
                visible: view.limitsShown.length > 0
                text: view.limitsData ? view.limitFootText(view.limitsData) : ""
                font: Kirigami.Theme.smallFont
                opacity: 0.6
                wrapMode: Text.Wrap
            }
        }

        // Where it all comes from
        PlasmaComponents3.Label {
            textFormat: Text.PlainText
            Layout.fillWidth: true
            visible: !!view.recap
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.55
            text: {
                if (!view.recap)
                    return ""
                const failed = view.recap.sources.filter(s => !s.ok)
                // (the hosts whose chats it was read from: not one left out or that couldn't be read)
                const hosts = view.recap.sources.filter(s => s.host && s.ok).map(s => root.hostLabel(s.host))
                let text = i18n("Read from the chats on this computer%1, without using any tokens. Prices: Claude's API list prices of %2%3.",
                                hosts.length ? i18n(" and on %1", hosts.join(", ")) : "",
                                Qt.locale().toString(view.date(view.recap.prices.asOf), "d MMM yyyy"),
                                view.recap.prices.guessed.length
                                    ? i18n(" (%1 at the price of its family's newest model)", view.recap.prices.guessed.join(", ")) : "")
                const cur = view.currency
                if (cur.error)
                    text += "\n" + i18n("Amounts in US dollars: %1.", cur.error)
                else if (cur.code !== "USD")
                    text += "\n" + i18n("Amounts in %1 at the European Central Bank's rate of %2: 1 USD = %3 %1.", cur.code,
                                        Qt.locale().toString(view.date(cur.date), "d MMM yyyy"),
                                        Number(cur.rate).toLocaleString(Qt.locale(), "f", 4))
                for (const s of failed)
                    text += "\n" + i18n("%1 couldn't be read: %2", root.hostLabel(s.host), s.error)
                return text
            }
        }
    }
    }

    function share() {
        sharing.open()
    }

    // The Recap as a card to share (RecapCard.qml): saved in your Pictures
    // folder, or copied (jump.py --copy-image), at twice its size
    QQC2.Popup {
        id: sharing
        parent: QQC2.Overlay.overlay
        modal: true
        anchors.centerIn: parent
        width: Math.min(parent ? parent.width - Kirigami.Units.gridUnit : 600, 600 + Kirigami.Units.largeSpacing * 2)
        padding: Kirigami.Units.largeSpacing
        property string said: ""
        onOpened: said = ""

        function fileName() {
            const r = view.recap
            return "claude-" + (r && r.span ? r.span : "week") + "-" + (r ? r.to : "recap") + ".png"
        }
        function localPath(url) {
            return decodeURIComponent(String(url).replace(/^file:\/\//, ""))
        }
        function save() {
            const folder = localPath(StandardPaths.writableLocation(StandardPaths.PicturesLocation))
            const path = folder + "/" + fileName()
            shareCard.grabToImage(result => {
                sharing.said = result.saveToFile(path) ? i18n("Saved: %1", path) : i18n("Couldn't save it in %1", folder)
            }, Qt.size(1200, 630))
        }
        // (by way of a file in Talpy Den's own cache folder, which only you can
        // read, not /tmp: gone once it's on the clipboard)
        function copy() {
            const path = localPath(StandardPaths.writableLocation(StandardPaths.GenericCacheLocation)) + "/talpy-den/" + fileName()
            shareCard.grabToImage(result => {
                if (!result.saveToFile(path)) {
                    sharing.said = i18n("Couldn't copy it")
                    return
                }
                copier.connectSource("python3 -I " + root.shellQuote(root.codeDir + "jump.py") + " --copy-image " + root.shellQuote(path)
                                     + "; rm -f -- " + root.shellQuote(path) + " # " + Date.now())
            }, Qt.size(1200, 630))
        }
        Exec {
            id: copier
            onNewData: (source, data) => {
                disconnectSource(source)
                sharing.said = root.helperResult(data).message || ""
            }
        }

        contentItem: ColumnLayout {
            spacing: Kirigami.Units.smallSpacing

            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: shareCard.height * shareCard.scale
                RecapCard {
                    id: shareCard
                    recap: view.recap
                    names: nameProjects.checked
                    scale: Math.min(1, parent.width / width)
                    transformOrigin: Item.TopLeft
                }
            }
            PlasmaComponents3.CheckBox {
                id: nameProjects
                text: i18n("Name the projects on it")
            }
            RowLayout {
                Layout.fillWidth: true
                PlasmaComponents3.Label {
                    textFormat: Text.PlainText
                    Layout.fillWidth: true
                    text: sharing.said
                    wrapMode: Text.Wrap
                    font: Kirigami.Theme.smallFont
                    opacity: 0.8
                }
                PlasmaComponents3.Button {
                    icon.name: Icons.plasma.save
                    text: i18n("Save")
                    onClicked: sharing.save()
                }
                PlasmaComponents3.Button {
                    icon.name: Icons.plasma.copy
                    text: i18n("Copy")
                    onClicked: sharing.copy()
                }
                PlasmaComponents3.Button {
                    icon.name: Icons.plasma.close
                    text: i18n("Close")
                    onClicked: sharing.close()
                }
            }
        }
    }
}
