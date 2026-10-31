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

// The Recap tab (main.qml: loadWeek, week.py): your last 7 days with Claude,
// as a story: the big picture (how long you were at it, how long Claude
// worked, your prompts, its tokens, the API prices), what Claude did, when
// (a day per row on a timeline, your plan's limits over the same days, the
// day chat by chat), where (by project, the chats it worked on most), then
// the money (at API prices, and what would make it use less of your plan:
// the rules of Claude Code's own /usage). All of it read from the chat
// transcripts: no tokens, nothing sent.
PlasmaComponents3.ScrollView {
    id: view

    readonly property var recap: root.weekRecap
    readonly property string span: root.weekSpan   // the one picked (its answer may still come)
    readonly property bool weeks: !!recap && recap.span === "all"   // a row per 7 days, with their numbers
    readonly property var days: recap ? recap.days : []
    readonly property var sum: recap ? recap.sum : null
    readonly property var previous: recap && recap.previous && (recap.previous.workedMs || recap.previous.prompts
                                                                  || recap.previous.cost) ? recap.previous : null
    readonly property var accounts: recap ? recap.accounts : []
    readonly property var projects: recap ? recap.projects : []
    readonly property var models: recap ? recap.models : []
    readonly property var chats: recap ? recap.chats : []
    readonly property var lanes: recap && recap.lanes ? recap.lanes : []   // (the Day view: chat by chat)
    readonly property var tips: recap ? recap.tips : []
    readonly property var trend: recap && recap.trend ? recap.trend : []
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
    readonly property color workColor: Kirigami.Theme.focusColor
    readonly property color waitColor: Kirigami.Theme.neutralTextColor
    readonly property color limitColor: Kirigami.Theme.negativeTextColor

    readonly property real dayWidth: gu * (weeks ? 3.4 : 2.6)
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

    // 412.3M, 8.1k
    function tokens(n) {
        return root.formatTokens(n || 0)
    }

    // A number of the tiles, in its own unit
    function shown(value, kind) {
        return kind === "time" ? hours(value) : kind === "money" ? money(value) : kind === "tokens" ? tokens(value) : String(value)
    }

    // Wed 14:05
    function whenText(ms) {
        return Qt.locale().toString(new Date(ms), "ddd") + " " + root.clockText(ms)
    }

    function date(day) {
        const p = String(day).split("-").map(Number)
        return new Date(p[0], p[1] - 1, p[2])
    }

    function periodText() {
        if (!recap || recap.span !== span)
            return root.weekBack !== 0 ? "" : span === "day" ? i18n("Today") : span === "all" ? i18n("Everything") : i18n("Last 7 days")
        if (span === "day") {
            const day = Qt.locale().toString(date(recap.from), "ddd d MMM")
            return recap.back === 0 ? i18n("Today · %1", day) : recap.back === 1 ? i18n("Yesterday · %1", day) : day
        }
        if (span === "all")
            return recap.first ? i18n("Everything since %1", Qt.locale().toString(date(recap.first), "d MMM yyyy")) : i18n("Everything")
        const days = i18nc("from day – to day", "%1 – %2", Qt.locale().toString(date(recap.from), "d MMM"),
                           Qt.locale().toString(date(recap.to), "d MMM"))
        return recap.back === 0 ? i18n("Last 7 days · %1", days) : days
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
            return ""
        const value = shown(before, kind)
        return "\n" + (span === "day" ? i18n("The day before: %1", value) : i18n("The 7 days before: %1", value))
    }

    // The same number over the 5 weeks up to these days (a week older than
    // the widget keeps: unknown)
    function trendText(key, kind) {
        if (trend.length < 2)
            return ""
        const values = trend.map(w => !w ? "?" : shown(w[key], kind))
        return "\n" + (span === "day" ? i18n("Day by day, this day last: %1", values.join(" · "))
                                      : i18n("Week by week, these 7 days last: %1", values.join(" · ")))
    }

    readonly property var tiles: !sum ? [] : [
        { label: i18n("You"), key: "youMs", value: hours(sum.youMs),
          delta: deltaText(sum.youMs, previous ? previous.youMs : 0, "time"),
          tip: i18n("The time you spent writing to Claude, reading its replies and answering its questions, in all your chats and accounts: the time between your prompts and its replies counts when it's under 15 minutes.")
               + beforeText(previous ? previous.youMs : 0, "time") + trendText("youMs", "time") },
        { label: i18n("Claude worked"), key: "workedMs", value: hours(sum.workedMs),
          delta: deltaText(sum.workedMs, previous ? previous.workedMs : 0, "time"),
          tip: i18n("Claude's own count of its turns (its “Worked for …”), all chats added up: chats working at the same time each count. On the clock it worked %1, and it waited %2 for your answers.",
                    hours(sum.busyMs), hours(sum.waitMs)) + beforeText(previous ? previous.workedMs : 0, "time")
               + trendText("workedMs", "time") },
        { label: i18n("Prompts"), key: "prompts", value: String(sum.prompts),
          delta: deltaText(sum.prompts, previous ? previous.prompts : 0, "count"),
          tip: i18np("In %1 chat", "In %1 chats", sum.chats) + " · " + i18np("%1 turn of Claude's", "%1 turns of Claude's", sum.turns)
               + beforeText(previous ? previous.prompts : 0, "count") + trendText("prompts", "count") },
        { label: i18n("Tokens"), key: "tokenTotal", value: tokens(sum.tokenTotal),
          delta: deltaText(sum.tokenTotal, previous ? previous.tokenTotal : 0, "tokens"),
          tip: tokenText() + beforeText(previous ? previous.tokenTotal : 0, "tokens") + trendText("tokenTotal", "tokens") },
        { label: i18n("At API prices"), key: "cost", value: money(sum.cost),
          delta: deltaText(sum.cost, previous ? previous.cost : 0, "money"),
          tip: i18n("What the same tokens would cost on Claude's API, at its list prices of %1. Your plan isn't billed this way: this is the value of what you used.",
                    recap.prices ? Qt.locale().toString(date(recap.prices.asOf), "d MMMM yyyy") : "")
               + beforeText(previous ? previous.cost : 0, "money") + trendText("cost", "money") }
    ]

    // What the tokens were: all that Claude read and wrote, by kind
    function tokenText() {
        const t = sum.tokens
        return i18n("Everything Claude read and wrote: %1 of new input, %2 read from the cache, %3 written to the cache and %4 that Claude wrote.",
                    tokens(t.input), tokens(t.cacheRead), tokens(t.cacheWrite5m + t.cacheWrite1h), tokens(t.output))
    }

    function factsText() {
        if (!sum)
            return ""
        const parts = []
        if (sum.longestTurn && sum.longestTurn.workedMs >= 60000)
            parts.push(i18n("longest turn %1 (%2)", hours(sum.longestTurn.workedMs), sum.longestTurn.name || "?"))
        if (sum.peakAtOnce > 1)
            parts.push(i18n("up to %1 chats at once", sum.peakAtOnce))
        if (sum.busiestDay)
            parts.push(i18n("busiest day %1", Qt.locale().toString(date(sum.busiestDay), "dddd")))
        if (sum.limits)
            parts.push(i18np("a usage limit stopped you once", "usage limits stopped you %1 times", sum.limits))
        return parts.join(" · ")
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
            return i18n("Point at a day to see what went on then; click it for its chats.")
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
    function workText() {
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

    // A plan window's color: as its bar in the Chats tab
    function planColor(pct) {
        return pct >= 90 ? Kirigami.Theme.negativeTextColor : pct >= 70 ? Kirigami.Theme.neutralTextColor : workColor
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
        return key === "waits" ? "chronometer" : key === "limits" ? "speedometer" : "help-hint"
    }

    FontMetrics {
        id: smallMetrics
        font: Kirigami.Theme.smallFont
    }

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
                model: [["day", i18n("Day")], ["week", i18n("Week")], ["all", i18n("Overall")]]
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
                text: view.span === "day" ? i18n("The day before") : i18n("The week before")
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
                text: view.span === "day" ? i18n("The day after") : i18n("The week after")
                visible: view.span !== "all"
                enabled: root.weekBack > 0
                onClicked: root.weekBack -= 1

                PlasmaCore.ToolTipArea {
                    textFormat: Text.PlainText
                    anchors.fill: parent
                    mainText: parent.text
                }
            }
            PlasmaComponents3.ToolButton {
                icon.name: Icons.plasma.refresh
                display: PlasmaComponents3.AbstractButton.IconOnly
                text: i18n("Read again")
                enabled: !root.weekBusy
                onClicked: root.loadWeek()

                PlasmaCore.ToolTipArea {
                    textFormat: Text.PlainText
                    anchors.fill: parent
                    mainText: parent.text
                    subText: i18n("These days read again from your chats now.")
                }
            }
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

        PlasmaComponents3.Label {
            textFormat: Text.PlainText
            Layout.fillWidth: true
            visible: view.hasData && text !== ""
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: view.factsText()
        }

        // What Claude did: its tool calls, commands, edits, subagents
        ColumnLayout {
            Layout.fillWidth: true
            visible: view.hasData && !!view.work && view.work.toolCalls > 0
            spacing: Math.round(view.gu * 0.2)

            SectionTitle {
                text: i18n("What Claude did")
            }
            PlasmaComponents3.Label {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                text: view.workText()
            }
            PlasmaComponents3.Label {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                visible: !!view.work && view.work.tools.length > 0
                wrapMode: Text.Wrap
                font: Kirigami.Theme.smallFont
                opacity: 0.7
                text: !view.work ? "" : i18n("Its tools: %1", view.work.tools.map(t => t[0] + " " + view.count(t[1])).join(" · "))
            }
        }

        // A day per row: when you were at it, when Claude worked, when it waited for you
        ColumnLayout {
            Layout.fillWidth: true
            visible: view.hasData
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
                            text: !dayRow.day.day ? "" : Qt.locale().toString(view.date(dayRow.day.day), view.weeks ? "d MMM" : "ddd d")
                            elide: Text.ElideRight
                            font.pointSize: Kirigami.Theme.smallFont.pointSize
                            font.bold: dayRow.today || dayRow.open
                            opacity: dayRow.today || dayRow.open ? 0.9 : 0.7

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: dayRow.day.chats.length ? Qt.PointingHandCursor : Qt.ArrowCursor
                                onClicked: dayRow.toggle()
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
                                mainText: !dayRow.day.day ? "" : view.weeks
                                          ? i18nc("from day – to day", "%1 – %2", Qt.locale().toString(view.date(dayRow.day.day), "d MMMM"),
                                                  Qt.locale().toString(view.date(dayRow.day.to), "d MMMM"))
                                          : Qt.locale().toString(view.date(dayRow.day.day), "dddd d MMMM")
                                subText: i18n("You: %1 · Claude worked %2 (on the clock %3) · it waited %4 for you",
                                              view.hours(dayRow.day.youMs), view.hours(dayRow.day.workedMs),
                                              view.hours(dayRow.day.busyMs), view.hours(dayRow.day.waitMs))
                                         + "\n" + i18np("%1 prompt", "%1 prompts", dayRow.day.prompts)
                                         + " · " + i18n("%1 tokens", view.tokens(dayRow.day.tokenTotal))
                                         + " · " + i18n("%1 at API prices", view.money(dayRow.day.cost))
                            }
                        }
                    }

                    // the day's chats, unfolded with a click on its row
                    Repeater {
                        model: dayRow.open ? dayRow.day.chats.length : 0
                        delegate: WeekChatLine {
                            required property int index
                            chat: dayRow.day.chats[index] || view.emptyChat
                            indent: view.dayWidth
                            numbers: view.hours(chat.workedMs) + " · " + view.money(chat.cost)
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

        // How full your plan's windows are now, and how they filled up
        // (the widget's usage history); a limit that stopped a chat is a
        // red mark on the days above
        ColumnLayout {
            id: planSection
            Layout.fillWidth: true
            visible: view.hasData && view.plan.length > 0
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
                text: i18n("Your plan's limits now")
            }
            Repeater {
                model: view.plan.length
                delegate: ColumnLayout {
                    id: planAccount
                    required property int index
                    readonly property var account: view.plan[index] || ({ name: "", windows: [] })
                    Layout.fillWidth: true
                    spacing: Math.round(view.gu * 0.2)

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
                                Layout.preferredWidth: view.gu * 7
                                text: (view.plan.length > 1 ? planAccount.account.name + " · " : "") + planRow.win.label
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

        // The day, chat by chat (week.py: day_lanes): when each chat worked,
        // waited for you (a permission, a question) or was paused (asleep, a
        // limit); between its turns it was your turn. A name opens its chat.
        ColumnLayout {
            id: lanesBox
            Layout.fillWidth: true
            visible: view.hasData && view.lanes.length > 0
            spacing: Math.round(view.gu * 0.2)
            readonly property real t0: view.lanes.length ? Math.min.apply(null, view.lanes.map(l => l.parts[0][0])) : 0
            readonly property real t1: view.lanes.length ? Math.max.apply(null, view.lanes.map(l => l.parts[l.parts.length - 1][1])) : 1
            readonly property real span: Math.max(60000, t1 - t0)
            readonly property real nameWidth: Math.round(view.gu * 9)
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
                    model: [["w", i18n("Claude worked")], ["y", i18n("Waited for you")], ["p", i18n("Paused (asleep, a limit)")]]
                    delegate: RowLayout {
                        required property var modelData
                        spacing: Kirigami.Units.smallSpacing
                        Rectangle {
                            width: view.gu * 0.6
                            height: width
                            radius: 2
                            color: lanesBox.color(modelData[0])
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
                        text: (laneRow.lane.host ? laneRow.lane.host + ": " : "") + laneRow.lane.name
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
                        PlasmaCore.ToolTipArea {
                            textFormat: Text.PlainText
                            anchors.fill: parent
                            mainText: laneRow.lane.name
                            subText: i18n("Claude worked %1, waited for you %2", view.hours(laneRow.lane.workedMs), view.hours(laneRow.lane.waitedMs))
                                     + (laneRow.lane.project ? "\n" + laneRow.lane.project : "")
                        }
                    }
                }
            }
            RowLayout {
                Layout.leftMargin: lanesBox.nameWidth + Kirigami.Units.smallSpacing
                PlasmaComponents3.Label {
                    textFormat: Text.PlainText
                    text: root.clockText(lanesBox.t0)
                    font: Kirigami.Theme.smallFont
                    opacity: 0.6
                }
                Item {
                    Layout.fillWidth: true
                }
                PlasmaComponents3.Label {
                    textFormat: Text.PlainText
                    text: root.clockText(lanesBox.t1)
                    font: Kirigami.Theme.smallFont
                    opacity: 0.6
                }
            }
        }

        // The project folders Claude worked in most (a chat started in a
        // subfolder of a repository counts for the repository): click one
        // to open it in the Projects tab (an SSH host's: for its chats here)
        ColumnLayout {
            Layout.fillWidth: true
            visible: view.hasData && view.projects.length > 0
            spacing: Math.round(view.gu * 0.2)

            SectionTitle {
                text: i18n("Where Claude worked")
            }
            Repeater {
                model: view.projects.length
                delegate: ColumnLayout {
                    id: projectRow
                    required property int index
                    readonly property var project: view.projects[index] || view.emptyProject
                    readonly property string key: project.host + "|" + project.path
                    readonly property bool open: view.openProject === key
                    Layout.fillWidth: true
                    spacing: 0

                    Item {
                        Layout.fillWidth: true
                        implicitHeight: projectLine.implicitHeight

                        RowLayout {
                            id: projectLine
                            anchors.left: parent.left
                            anchors.right: parent.right
                            spacing: Kirigami.Units.smallSpacing

                            Kirigami.Icon {
                                Layout.preferredWidth: Kirigami.Units.iconSizes.small
                                Layout.preferredHeight: Kirigami.Units.iconSizes.small
                                source: !projectRow.project.host ? Icons.plasma.goTo   // (to the Projects tab)
                                        : projectRow.open ? Icons.plasma.unfolded : Icons.plasma.folded
                                opacity: 0.6
                            }
                            PlasmaComponents3.Label {
                                textFormat: Text.PlainText
                                Layout.preferredWidth: view.gu * 6
                                text: (projectRow.project.host ? projectRow.project.host + ": " : "") + projectRow.project.name
                                elide: Text.ElideMiddle
                                font.bold: projectRow.open
                            }
                            Item {
                                Layout.fillWidth: true
                                Layout.preferredHeight: Math.round(view.gu * 0.4)

                                Rectangle {
                                    width: Math.max(2, parent.width * projectRow.project.workedMs / view.maxProject)
                                    height: parent.height
                                    radius: Math.min(2, height / 2)
                                    color: view.workColor
                                    opacity: 0.8
                                }
                            }
                            PlasmaComponents3.Label {
                                textFormat: Text.PlainText
                                text: view.hours(projectRow.project.workedMs) + " · " + view.money(projectRow.project.cost)
                                font: Kirigami.Theme.smallFont
                                opacity: 0.8
                            }
                        }
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                if (projectRow.project.host)
                                    view.openProject = projectRow.open ? "" : projectRow.key
                                else
                                    root.showProject(projectRow.project.path)
                            }

                            PlasmaCore.ToolTipArea {
                                textFormat: Text.PlainText
                                anchors.fill: parent
                                mainText: (projectRow.project.host ? projectRow.project.host + ": " : "") + projectRow.project.path
                                subText: i18n("Claude worked %1 · %2 at API prices", view.hours(projectRow.project.workedMs),
                                              view.money(projectRow.project.cost))
                                         + "\n" + i18np("%1 prompt", "%1 prompts", projectRow.project.prompts)
                                         + " · " + i18np("%1 chat", "%1 chats", projectRow.project.chatCount)
                                         + "\n\n" + (projectRow.project.host ? i18n("Click for its chats.")
                                                                         : i18n("Click to open it in the Projects tab: its chats, plans and memories."))
                            }
                        }
                    }
                    Repeater {
                        model: projectRow.open ? projectRow.project.chats.length : 0
                        delegate: WeekChatLine {
                            required property int index
                            chat: projectRow.project.chats[index] || view.emptyChat
                            where: ""
                            indent: Kirigami.Units.iconSizes.small + Kirigami.Units.smallSpacing
                            numbers: view.hours(chat.workedMs) + " · " + view.money(chat.cost)
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
        }

        // The chats Claude worked on most: click one to bring it up
        ColumnLayout {
            Layout.fillWidth: true
            visible: view.hasData && view.chats.length > 0
            spacing: 0

            SectionTitle {
                text: i18n("Chats it worked on most")
                Layout.bottomMargin: Math.round(view.gu * 0.2)
            }
            Repeater {
                model: view.chats.length
                delegate: WeekChatLine {
                    required property int index
                    chat: view.chats[index] || view.emptyChat
                    numbers: view.hours(chat.workedMs) + " · " + view.money(chat.cost)
                }
            }
        }

        // What it'd cost on the API, by model, and what the cache saved
        ColumnLayout {
            Layout.fillWidth: true
            visible: view.hasData && view.models.length > 0
            spacing: Math.round(view.gu * 0.2)

            SectionTitle {
                text: i18n("At API prices")
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
                    Item {
                        Layout.fillWidth: true
                        Layout.preferredHeight: Math.round(view.gu * 0.4)

                        Rectangle {
                            width: Math.max(2, parent.width * modelRow.entry.share)
                            height: parent.height
                            radius: Math.min(2, height / 2)
                            color: view.youColor
                        }
                    }
                    PlasmaComponents3.Label {
                        textFormat: Text.PlainText
                        text: view.money(modelRow.entry.cost) + " · "
                              + (modelRow.entry.share < 0.01 ? "<1%" : Math.round(modelRow.entry.share * 100) + "%")
                        font: Kirigami.Theme.smallFont
                        opacity: 0.8
                    }
                }
            }
            PlasmaComponents3.Label {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                visible: !!view.sum && view.sum.tokens.cacheRead > 0
                wrapMode: Text.Wrap
                font: Kirigami.Theme.smallFont
                opacity: 0.7
                text: {
                    if (!view.sum)
                        return ""
                    const t = view.sum.tokens
                    const input = t.input + t.cacheRead + t.cacheWrite5m + t.cacheWrite1h
                    return i18n("%1 of the %2 input tokens came from the cache: it saved %3. Claude wrote %4 tokens.",
                                Math.round(100 * t.cacheRead / Math.max(1, input)) + "%", root.formatTokens(input),
                                view.money(view.recap.cacheSaved), root.formatTokens(t.output))
                }
            }
        }

        // What would use less of your plan (Claude Code's /usage rules), and
        // what coming back to chats whose cache had expired cost
        ColumnLayout {
            Layout.fillWidth: true
            visible: view.hasData
            spacing: Kirigami.Units.smallSpacing

            SectionTitle {
                text: i18n("What could use less of your plan")
            }
            PlasmaComponents3.Label {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                visible: view.tips.length === 0 && !(view.spend && view.spend.cold.count > 0)
                wrapMode: Text.Wrap
                opacity: 0.7
                text: i18n("Nothing stands out: no habit takes a tenth of the usage shown.")
            }
            Repeater {
                model: view.tips.length
                delegate: RowLayout {
                    id: tipRow
                    required property int index
                    readonly property var tip: view.tips[index] || view.emptyTip
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing

                    Kirigami.Icon {
                        Layout.alignment: Qt.AlignTop
                        Layout.preferredWidth: Kirigami.Units.iconSizes.small
                        Layout.preferredHeight: Kirigami.Units.iconSizes.small
                        source: view.tipIcon(tipRow.tip.key)
                        opacity: 0.8
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
                    }
                    PlasmaComponents3.Label {
                        textFormat: Text.PlainText
                        Layout.alignment: Qt.AlignTop
                        visible: tipRow.tip.pct !== null && tipRow.tip.pct !== undefined
                        text: (tipRow.tip.pct || 0) + "%"
                        font: Kirigami.Theme.smallFont
                        opacity: 0.8

                        PlasmaCore.ToolTipArea {
                            textFormat: Text.PlainText
                            anchors.fill: parent
                            mainText: i18n("%1% of the usage shown", tipRow.tip.pct || 0)
                            subText: i18n("Of the usage of these days, as Claude Code's /usage weighs it toward your plan's limits. A request can count for several of these.")
                        }
                    }
                    PlasmaComponents3.ToolButton {
                        Layout.alignment: Qt.AlignTop
                        visible: tipRow.tip.command !== ""
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
            // coming back to chats whose cache had expired: what writing it again cost
            PlasmaComponents3.Label {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                visible: !!view.spend && view.spend.cold.count > 0
                wrapMode: Text.Wrap
                font: Kirigami.Theme.smallFont
                opacity: 0.7
                text: {
                    if (!view.spend || !view.spend.cold.count)
                        return ""
                    const cold = view.spend.cold
                    return i18np("You came back to a chat after its cache had expired (an hour without a reply) once: writing its context again cost %2 more than reading it from the cache.",
                                 "You came back to chats after their cache had expired (an hour without a reply) %1 times: writing their context again cost %2 more than reading it from the cache.",
                                 cold.count, view.money(cold.cost))
                           + (cold.chats.length ? " " + i18n("Most in: %1.", cold.chats.map(c => i18n("%1 (%2×, %3)", c.name, c.resumes, view.money(c.cost))).join(", ")) : "")
                }
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
                const hosts = view.recap.sources.filter(s => s.host && s.ok).map(s => s.host)
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
                    text += "\n" + i18n("%1 couldn't be read: %2", s.host, s.error)
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
