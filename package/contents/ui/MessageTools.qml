import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami

// On the message under the pointer in Talpy Chat (yours, or Claude's reply):
// its time ("14:32"; "Yesterday 14:32" for an earlier day) and Copy, over its
// top right corner, so nothing moves. ChatPane.qml makes one for the list the
// first time a message is hovered and moves it to the one hovered: a long chat
// has nothing more for each message, and a time is worked out only here. Copy
// puts a reply on the clipboard as Markdown, as the transcript has it (not as
// it's shown; all of it: one shown cut is read whole first, ChatPane copyItem),
// and yours as you wrote it (a command too); Copied says it for a moment in the
// same place, as wide, once it's on the clipboard. No MouseArea: hover stays the list's (its
// HoverHandler picks the message). VS Code chat.tsx HoverBar: the same words.
Rectangle {
    id: tools

    readonly property Item row: list.hoverRow
    readonly property bool copied: row !== null && pane.copiedKey === row.key
    readonly property real at: row !== null && row.index >= 0 && row.index < items.count ? items.get(row.index).at : 0

    parent: row || list.contentItem
    visible: row !== null
    z: 5
    x: row ? row.width - width - Kirigami.Units.smallSpacing : 0
    y: row ? row.gap + Kirigami.Units.smallSpacing * 0.5 : 0
    width: line.implicitWidth + Kirigami.Units.smallSpacing * 3
    height: line.implicitHeight + 2
    radius: Kirigami.Units.cornerRadius
    color: Kirigami.Theme.backgroundColor
    border.width: 1
    border.color: pane.borderColor

    RowLayout {
        id: line
        anchors.centerIn: parent
        spacing: Kirigami.Units.smallSpacing

        PlasmaComponents3.Label {
            visible: tools.at > 0
            textFormat: Text.PlainText
            text: tools.at > 0 ? pane.timeText(tools.at) : ""
            color: pane.mutedColor
            font.family: pane.chatFamily
            font.pointSize: pane.pt * 0.85
        }
        // Copy: framed thin while the pointer is on it, and while it says Copied (as a code block's)
        Rectangle {
            Layout.preferredWidth: Math.max(copyWord.advanceWidth, copiedWord.advanceWidth) + Kirigami.Units.smallSpacing * 3
            Layout.preferredHeight: copyLabel.implicitHeight
            radius: Kirigami.Units.cornerRadius
            color: "transparent"
            border.width: 1
            border.color: copyHover.hovered || tools.copied ? Kirigami.Theme.focusColor : "transparent"

            TextMetrics {
                id: copyWord
                font: copyLabel.font
                text: i18n("Copy")
            }
            TextMetrics {
                id: copiedWord
                font: copyLabel.font
                text: i18n("Copied")
            }
            PlasmaComponents3.Label {
                id: copyLabel
                anchors.centerIn: parent
                textFormat: Text.PlainText
                text: tools.copied ? copiedWord.text : copyWord.text
                color: copyHover.hovered || tools.copied ? Kirigami.Theme.textColor : pane.mutedColor
                font.family: pane.chatFamily
                font.pointSize: pane.pt * 0.85
            }
            HoverHandler {
                id: copyHover
                cursorShape: Qt.PointingHandCursor
            }
            TapHandler {
                gesturePolicy: TapHandler.ReleaseWithinBounds   // (the press is Copy's: no selection starts under it)
                onTapped: pane.copyItem(tools.row.key, tools.row.text, true)   // (all of it: Copied once it's on the clipboard)
            }
            PlasmaComponents3.ToolTip.text: tools.row && tools.row.thinking ? i18n("Copy this thinking line")
                                          : tools.row && tools.row.kind === "claude" ? i18n("Copy this reply, as Markdown") : i18n("Copy your message, as you wrote it")
            PlasmaComponents3.ToolTip.visible: copyHover.hovered
            PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
        }
    }

}
