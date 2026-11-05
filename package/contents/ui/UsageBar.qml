import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.core as PlasmaCore
import org.kde.kirigami as Kirigami

// One plan window: how much is used, and where it's heading at your pace
// (talpy_den.py: usage_forecast): a faded stretch up to where it would
// be when the window resets, a mark where an even pace would be by now, and
// a warning when it would run out before it resets.
ColumnLayout {
    id: bar

    property string label
    property real pct: 0
    property string detail
    property var forecast: null
    property real resetsAt: 0

    readonly property real atReset: forecast ? Math.min(100, Math.max(pct, forecast.atReset)) : pct
    readonly property bool runsOut: !!forecast && !!forecast.fullAt
    // What's drawn glides to a new value (Plasma's animation speed: instant, it jumps)
    property real shownPct: pct
    property real shownAtReset: atReset
    Behavior on shownPct {
        NumberAnimation { duration: Kirigami.Units.veryLongDuration; easing.type: Easing.OutCubic }
    }
    Behavior on shownAtReset {
        NumberAnimation { duration: Kirigami.Units.veryLongDuration; easing.type: Easing.OutCubic }
    }

    spacing: 0

    RowLayout {
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing

        PlasmaComponents3.Label {
            textFormat: Text.PlainText
            text: bar.label
            Layout.preferredWidth: root.usageLabelWidth
            elide: Text.ElideRight
        }

        Rectangle {
            id: track
            Layout.fillWidth: true
            Layout.preferredHeight: Math.round(Kirigami.Units.gridUnit * 0.5)
            radius: height / 2
            color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.15)

            // Where it would be when the window resets, at this pace
            Rectangle {
                visible: bar.forecast !== null && bar.atReset > bar.pct
                width: parent.width * bar.shownAtReset / 100
                height: parent.height
                radius: parent.radius
                color: root.usageColor(bar.atReset)
                opacity: 0.35
            }
            Rectangle {
                width: parent.width * Math.min(100, Math.max(0, bar.shownPct)) / 100
                height: parent.height
                radius: parent.radius
                color: root.usageColor(bar.pct)
            }
            // Where an even pace through the window would be by now
            Rectangle {
                visible: bar.forecast !== null
                x: Math.round(parent.width * Math.min(100, bar.forecast ? bar.forecast.evenPct : 0) / 100) - 1
                y: -2
                width: 2
                height: parent.height + 4
                radius: 1
                color: Kirigami.Theme.textColor
                opacity: 0.55
            }

            PlasmaCore.ToolTipArea {
                textFormat: Text.PlainText
                anchors.fill: parent
                active: bar.forecast !== null || bar.resetsAt > root.now
                // (worked out while the pointer is on it: not at every check)
                mainText: !containsMouse ? "" : i18nc("usage window, percent used", "%1: %2% used", bar.label, Math.round(bar.pct))
                subText: !containsMouse ? "" : [bar.resetsAt > root.now ? root.resetAtText(bar.resetsAt) + "." : "",
                                                root.forecastText(bar.forecast, bar.pct, bar.resetsAt)].filter(t => t).join("\n")
            }
        }

        PlasmaComponents3.Label {
            textFormat: Text.PlainText
            text: Math.round(bar.shownPct) + "%"
            Layout.preferredWidth: Kirigami.Units.gridUnit * 2.2
            horizontalAlignment: Text.AlignRight
        }

        PlasmaComponents3.Label {
            textFormat: Text.PlainText
            text: bar.detail
            Layout.preferredWidth: root.usageResetWidth   // (kept with no reset to say: the bars stay alike)
            horizontalAlignment: Text.AlignRight
            opacity: 0.7
            font: Kirigami.Theme.smallFont
            elide: Text.ElideRight

            PlasmaCore.ToolTipArea {
                textFormat: Text.PlainText
                anchors.fill: parent
                active: bar.resetsAt > root.now
                mainText: active && containsMouse ? root.resetAtText(bar.resetsAt) : ""
            }
        }
    }

    PlasmaComponents3.Label {
        textFormat: Text.PlainText
        visible: bar.runsOut
        Layout.fillWidth: true
        Layout.leftMargin: root.usageLabelWidth + Kirigami.Units.smallSpacing
        text: bar.runsOut ? i18n("At this pace: full in %1, %2 before it resets",
                                 root.duration(bar.forecast.fullAt - root.now), root.duration(bar.resetsAt - bar.forecast.fullAt)) : ""
        color: Kirigami.Theme.neutralTextColor   // (orange, as in the VS Code extension)
        font: Kirigami.Theme.smallFont
        elide: Text.ElideRight
    }
}
