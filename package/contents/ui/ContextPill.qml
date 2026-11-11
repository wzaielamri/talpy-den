import QtQuick
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami

// "Context 31% used" in Talpy Chat's header: how far the chat's context has come toward where Claude
// compacts it on its own, with a small bar of it, in the colours of the rows' bars (main.qml
// usageColor: the accent, the warning colour from 70%, the negative one from 90% or once Claude Code
// says it's close). VS Code chat.tsx ContextPill: the same words and levels (shared/pane.ts
// contextText, contextLevel).
Rectangle {
    id: pill
    property var ctx: null        // pane.py's "context": {used, window, compactAt, left, near}
    property string tooltip: ""
    property bool open: false     // (its menu shows)
    readonly property int usedPct: ctx ? Math.max(0, Math.min(100, 100 - ctx.left)) : 0
    readonly property string level: ctx && (ctx.near || usedPct >= 90) ? "high" : usedPct >= 70 ? "medium" : "low"
    readonly property color tone: level === "high" ? Kirigami.Theme.negativeTextColor
                                : level === "medium" ? Kirigami.Theme.neutralTextColor : Kirigami.Theme.focusColor
    signal clicked()

    implicitWidth: row.implicitWidth + Kirigami.Units.smallSpacing * 2
    implicitHeight: label.implicitHeight
    radius: Kirigami.Units.cornerRadius
    color: hover.hovered || open ? Qt.rgba(tone.r, tone.g, tone.b, 0.14) : "transparent"
    border.width: 1
    border.color: tone
    Accessible.role: Accessible.Button
    Accessible.name: label.text

    Row {
        id: row
        anchors.centerIn: parent
        spacing: Kirigami.Units.smallSpacing
        Rectangle {   // (the bar: up to where Claude compacts it)
            anchors.verticalCenter: parent.verticalCenter
            width: Kirigami.Units.gridUnit * 1.6
            height: Math.max(3, Math.round(Kirigami.Units.gridUnit * 0.3))
            radius: height / 2
            color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.18)
            Rectangle {
                width: parent.width * pill.usedPct / 100
                height: parent.height
                radius: parent.radius
                color: pill.tone
            }
        }
        Text {
            id: label
            anchors.verticalCenter: parent.verticalCenter
            textFormat: Text.PlainText
            text: i18n("Context %1% used", pill.usedPct)
            font: Kirigami.Theme.smallFont
            color: pill.tone
        }
    }
    HoverHandler {
        id: hover
        cursorShape: Qt.PointingHandCursor
    }
    TapHandler {
        gesturePolicy: TapHandler.ReleaseWithinBounds
        onTapped: pill.clicked()
    }
    PlasmaComponents3.ToolTip.text: tooltip
    PlasmaComponents3.ToolTip.visible: hover.hovered && !open && tooltip !== ""
    PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
}
