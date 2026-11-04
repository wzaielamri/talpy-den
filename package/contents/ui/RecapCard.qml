import QtQuick
import QtQuick.Layouts
import "talpy/talpy.mjs" as T

// The Recap as a card to share (WeekView.qml: Share…): the period shown with
// Talpy, its main numbers, Claude's work day by day, and the projects if you
// want them named. Fixed colors (it's a picture, not part of the theme);
// saved at twice its size (grabToImage).
Rectangle {
    id: card

    property var recap: null
    property bool names: false          // the projects' names on it
    readonly property var total: recap && recap.sum ? recap.sum : ({})
    // its bars, oldest first; Overall's rows (a row per 7 days) come newest
    // first: its last 20 weeks, so they fit
    readonly property var days: !recap || !recap.days ? [] : span === "all" ? recap.days.slice(0, 20).reverse() : recap.days
    readonly property var projects: recap && recap.projects ? recap.projects.slice(0, 3) : []
    readonly property string span: recap && recap.span ? recap.span : "week"
    readonly property real maxDay: Math.max(1, ...days.map(d => d.workedMs || 0))

    width: 600
    height: 315
    radius: 18
    gradient: Gradient {
        GradientStop { position: 0; color: "#1d2042" }
        GradientStop { position: 1; color: "#3b2e6c" }
    }

    function hours(ms) {
        const h = (ms || 0) / 3600000
        return h >= 10 ? Math.round(h) + " h" : h >= 1 ? h.toFixed(1) + " h" : Math.round((ms || 0) / 60000) + " min"
    }
    function count(n) {
        return n >= 1e9 ? (n / 1e9).toFixed(1) + "B" : n >= 1e6 ? (n / 1e6).toFixed(1) + "M" : n >= 1e4 ? Math.round(n / 1e3) + "k" : String(n || 0)
    }
    function dates() {
        if (!recap)
            return ""
        const f = d => new Date(d + "T12:00:00").toLocaleDateString(Qt.locale(), "d MMM")
        return recap.from === recap.to ? f(recap.from) : f(recap.from) + " – " + f(recap.to)
    }

    // A few stars, as over the big Talpy at night
    Repeater {
        model: [[30, 26, 2], [120, 60, 1.5], [200, 22, 2.2], [262, 92, 1.4], [70, 120, 1.6], [560, 30, 1.8], [470, 18, 1.2]]
        delegate: Rectangle {
            required property var modelData
            x: modelData[0]
            y: modelData[1]
            width: modelData[2] * 2
            height: width
            radius: width / 2
            color: "#fff6c8"
            opacity: 0.7
        }
    }

    // Talpy, out of its burrow, happy
    Canvas {
        id: pet
        x: 10
        y: 70
        width: 230
        height: 230
        renderStrategy: Canvas.Immediate
        onPaint: {
            const ctx = getContext("2d")
            ctx.reset()
            const t = new T.Talpy({ brain: false, colors: T.LILAC, theme: { fx: "rgba(255,255,255,0.6)", text: "#ffffff" } })
            t.tick(1e6)
            t.pose({ depth: "high", arms: "up", eyes: "star", mouth: "grin", plume: "up", lamp: "done", blush: 1 })
            ctx.translate(15, 10)
            ctx.scale(200 / T.BOX, 200 / T.BOX)
            t.draw(ctx)
        }
    }

    ColumnLayout {
        x: 250
        y: 26
        width: card.width - x - 30
        spacing: 4

        Text {

            textFormat: Text.PlainText
            Layout.fillWidth: true
            text: card.span === "day" ? i18n("My day with Claude") : card.span === "all" ? i18n("Me and Claude, so far")
                : card.span === "month" ? i18n("My month with Claude") : i18n("My week with Claude")
            color: "#ffffff"
            font.pixelSize: 25
            font.bold: true
            elide: Text.ElideRight
        }
        Text {
            textFormat: Text.PlainText
            Layout.fillWidth: true
            text: card.dates()
            color: "#c9c4ee"
            font.pixelSize: 13
        }

        GridLayout {
            Layout.topMargin: 12
            columns: 2
            columnSpacing: 26
            rowSpacing: 8
            Repeater {
                model: [[card.hours(card.total.workedMs), i18n("Claude worked")], [card.hours(card.total.youMs), i18n("with me")],
                        [card.count(card.total.prompts), i18n("prompts")], [card.count(card.total.chats), i18n("chats")]]
                delegate: ColumnLayout {
                    required property var modelData
                    spacing: 0
                    Text {
                        textFormat: Text.PlainText
                        text: modelData[0]
                        color: "#ffffff"
                        font.pixelSize: 27
                        font.bold: true
                    }
                    Text {
                        textFormat: Text.PlainText
                        text: modelData[1]
                        color: "#b9b4e0"
                        font.pixelSize: 11
                    }
                }
            }
        }

        // Claude's work, day by day (or hour blocks of the day)
        Row {
            id: dayBars
            readonly property int gap: card.days.length > 20 ? 2 : 5   // (a month's 30 days fit in the same width)
            visible: card.days.length > 1
            Layout.topMargin: 10
            spacing: gap
            Repeater {
                model: card.days.length
                delegate: Rectangle {
                    required property int index
                    readonly property var day: card.days[index] || ({ workedMs: 0 })
                    anchors.bottom: parent.bottom
                    width: Math.max(3, Math.min(22, 250 / Math.max(1, card.days.length) - dayBars.gap))
                    height: 4 + 34 * (day.workedMs || 0) / card.maxDay
                    radius: Math.min(3, width / 2)
                    color: "#d97757"
                    opacity: 0.55 + 0.45 * (day.workedMs || 0) / card.maxDay
                }
            }
        }

        Text {

            textFormat: Text.PlainText
            Layout.fillWidth: true
            Layout.topMargin: 6
            text: card.count(card.total.tokenTotal) + " " + i18n("tokens") + (card.projects.length
                  ? " · " + (card.names ? card.projects.map(p => p.name).join(", ")
                                        : i18np("%1 project", "%1 projects", card.recap.projects.length)) : "")
            color: "#c9c4ee"
            font.pixelSize: 12
            elide: Text.ElideRight
        }
    }

    Text {

        textFormat: Text.PlainText
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: 14
        text: "Talpy Den"
        color: "#8f89c4"
        font.pixelSize: 11
    }
}
