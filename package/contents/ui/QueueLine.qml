import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami
import "icons.mjs" as Icons

// Under your message in Talpy Chat while it waits (sent while Claude works): held a moment, "Queued
// · goes to Claude in 5 s" with Edit, Send now and Cancel (↑ in the box takes it back too), then in
// Claude's queue till it takes it in at its next step. ChatPane.qml's row: read and made only for a
// message that waits, not for each of yours
RowLayout {
    spacing: Kirigami.Units.smallSpacing

    PlasmaComponents3.Label {
        Layout.fillWidth: true
        textFormat: Text.PlainText
        wrapMode: Text.Wrap
        text: youBand.held
              ? i18n("Queued · goes to Claude in %1 s", Math.max(1, Math.ceil((entry.until - pane.now) / 1000)))
              : i18n("Queued · Claude takes it in at its next step")
        color: pane.mutedColor
        font.family: pane.chatFamily
        font.pointSize: pane.pt * 0.85
    }
    // (framed thin, so they read as buttons; Cancel last, at the end)
    IconTextButton {
        visible: youBand.held
        Layout.preferredHeight: pane.queueButtonHeight
        icon.name: Icons.plasma.edit
        text: i18n("Edit")
        onClicked: pane.takeBack(entry.key, true)
        PlasmaComponents3.ToolTip.text: i18n("Back in the box, to change it (↑ in an empty box too)")
        PlasmaComponents3.ToolTip.visible: hovered
        PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
    }
    IconTextButton {
        visible: youBand.held
        Layout.preferredHeight: pane.queueButtonHeight
        icon.name: Icons.plasma.send
        text: i18n("Send now")
        onClicked: pane.release(entry.key)
        PlasmaComponents3.ToolTip.text: i18n("To Claude now: it takes it in at its next step (Ctrl+Enter, in an empty box)")
        PlasmaComponents3.ToolTip.visible: hovered
        PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
    }
    IconTextButton {
        visible: youBand.held
        Layout.preferredHeight: pane.queueButtonHeight
        icon.name: Icons.plasma.cancel
        icon.color: Icons.color("cancel", Kirigami.Theme)
        text: i18n("Cancel")
        onClicked: pane.takeBack(entry.key, false)
        PlasmaComponents3.ToolTip.text: i18n("Don't send it")
        PlasmaComponents3.ToolTip.visible: hovered
        PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
    }
}
