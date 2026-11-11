import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami
import "icons.mjs" as Icons

// The context tag's menu (a click on "Context 31% used": ContextPill.qml): its numbers, Compact now
// (Claude's /compact, with what it must keep), or when the turn ends while Claude works, and Continue
// in a new chat (Claude writes a handoff note here, then a new chat in this folder opens with it in its
// box, for you to send). Made the first time it opens (ChatPane.qml: a Loader). VS Code chat.tsx
// .pane-ctx-menu: the same words (shared/pane.ts COMPACT_KEEP, compactLabel, HANDOFF_CAPTION…).
QQC2.Popup {
    id: menu
    property Item anchorItem: null
    readonly property var ctx: pane.contextLeft
    readonly property bool working: pane.chatState === "working"
    readonly property bool boxUsed: pane.replyText.trim() !== ""

    parent: anchorItem
    y: anchorItem ? anchorItem.height + Kirigami.Units.smallSpacing : 0
    width: Kirigami.Units.gridUnit * 19
    padding: Kirigami.Units.smallSpacing
    closePolicy: QQC2.Popup.CloseOnEscape | QQC2.Popup.CloseOnPressOutside
    onOpened: keepField.forceActiveFocus()
    onClosed: pane.compactMenuOpen = false

    background: Rectangle {
        color: Kirigami.Theme.backgroundColor
        border.width: 1
        border.color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.25)
        radius: Kirigami.Units.cornerRadius
    }

    contentItem: ColumnLayout {
        spacing: Kirigami.Units.smallSpacing
        PlasmaComponents3.Label {
            Layout.fillWidth: true
            Layout.leftMargin: Kirigami.Units.smallSpacing
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            visible: !!menu.ctx
            text: menu.ctx ? i18n("%1 of %2 tokens used · Claude compacts on its own at about %3", root.formatTokens(menu.ctx.used),
                                  root.formatTokens(menu.ctx.window), root.formatTokens(menu.ctx.compactAt)) : ""
            font.pointSize: pane.pt * 0.85
            opacity: 0.8
        }
        PlasmaComponents3.TextField {
            id: keepField
            Layout.fillWidth: true
            placeholderText: i18n("What it must keep (optional)")
            Accessible.name: placeholderText
            onAccepted: if (!menu.boxUsed) menu.compact()
        }
        PlasmaComponents3.Label {
            Layout.fillWidth: true
            Layout.leftMargin: Kirigami.Units.smallSpacing
            visible: menu.boxUsed
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            text: i18n("Your reply box has text: send it or clear it first.")
            font.pointSize: pane.pt * 0.85
            color: Kirigami.Theme.neutralTextColor
        }
        PlasmaComponents3.ToolButton {
            Layout.fillWidth: true
            enabled: !menu.boxUsed
            icon.name: Icons.plasma.compact
            text: menu.working ? i18n("Compact when this turn ends") : i18n("Compact now")
            onClicked: menu.compact()
            contentItem: RowLayout {   // (left-aligned, as a menu's items)
                Kirigami.Icon {
                    source: parent.parent.icon.name
                    implicitWidth: Kirigami.Units.iconSizes.small
                    implicitHeight: implicitWidth
                }
                PlasmaComponents3.Label {
                    Layout.fillWidth: true
                    textFormat: Text.PlainText
                    text: parent.parent.text
                }
            }
        }
        Kirigami.Separator {
            Layout.fillWidth: true
        }
        PlasmaComponents3.ToolButton {
            Layout.fillWidth: true
            enabled: !menu.boxUsed && !pane.handoffAsked
            icon.name: Icons.plasma.newChat
            text: pane.handoffAsked ? i18n("Waiting for Claude's handoff note…") : i18n("Continue in a new chat…")
            onClicked: {
                pane.continueInNewChat()
                menu.close()
            }
            contentItem: RowLayout {
                Kirigami.Icon {
                    source: parent.parent.icon.name
                    implicitWidth: Kirigami.Units.iconSizes.small
                    implicitHeight: implicitWidth
                }
                PlasmaComponents3.Label {
                    Layout.fillWidth: true
                    textFormat: Text.PlainText
                    text: parent.parent.text
                }
            }
        }
        PlasmaComponents3.Label {
            Layout.fillWidth: true
            Layout.leftMargin: Kirigami.Units.smallSpacing
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            text: i18n("Claude writes a handoff note here, then a new chat in this folder opens with it in its box, for you to send.")
            font.pointSize: pane.pt * 0.85
            opacity: 0.8
        }
    }

    function compact() {
        pane.compactNow(keepField.text)
        keepField.text = ""
        close()
    }
}
