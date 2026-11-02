import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.core as PlasmaCore
import org.kde.kirigami as Kirigami
import "icons.mjs" as Icons

// A chat that keeps going, or a task queued, on an SSH host or in a
// container that isn't shown (main.qml unseenHostItems). It goes on all the
// same, from here over ssh, so it's said where the hosts go, lest you forget
// it: Show (the host joins the list, with all its buttons) and Stop (Keep
// going off, its queued go-on cancelled) or Cancel. A task you wrote is
// cancelled where it shows, which asks first: here it has Show only.
RowLayout {
    id: line

    property var item: null
    readonly property string host: item ? item.host : ""
    readonly property var task: item ? item.task : null
    readonly property var kept: item ? item.kept : null
    readonly property bool wrote: !!task && !task.chat
    readonly property string where: root.hostLabel(host)
    readonly property real lineHeight: Math.max(what.implicitHeight + Kirigami.Units.smallSpacing, Kirigami.Units.iconSizes.small + 2)

    spacing: Kirigami.Units.smallSpacing
    Layout.leftMargin: Kirigami.Units.smallSpacing
    Layout.rightMargin: Kirigami.Units.smallSpacing

    Kirigami.Icon {
        source: line.kept ? Icons.plasma.keepGoing : Icons.plasma.goOnAt
        Layout.preferredWidth: Kirigami.Units.iconSizes.small
        Layout.preferredHeight: Layout.preferredWidth
        Layout.alignment: Qt.AlignTop   // (beside its first line, also with why it couldn't start under it)
        Layout.topMargin: Math.max(0, (what.implicitHeight - Kirigami.Units.iconSizes.small) / 2)
        opacity: 0.8
    }
    ColumnLayout {
        Layout.fillWidth: true
        spacing: 0

        PlasmaComponents3.Label {
            id: what
            Layout.fillWidth: true
            textFormat: Text.PlainText
            elide: Text.ElideRight
            font: Kirigami.Theme.smallFont
            text: (line.kept ? i18n("“%1” keeps going on %2, which isn't shown", line.item.name, line.where)
                   : line.task && line.task.afterTurn ? i18n("Your message to “%1” on %2, which isn't shown", line.item.name, line.where)
                   : line.task && line.task.chat ? i18n("“%1” goes on by itself on %2, which isn't shown", line.item.name, line.where)
                   : i18n("A task queued on %1, which isn't shown", line.where))
                  + (line.task && !line.task.error && !line.task.afterTurn
                     ? " · " + (line.task.chat ? i18n("goes on at %1", root.startText(line.task.startAt))
                                               : i18n("starts at %1", root.startText(line.task.startAt))) : "")

            PlasmaCore.ToolTipArea {
                textFormat: Text.PlainText
                anchors.fill: parent
                mainText: what.text
                subText: i18n("It goes on all the same: Talpy Den starts it from here, over ssh. Show %1 to see it with all its buttons.", line.where)
                         + (line.kept ? " " + i18n("Stop: it doesn't keep going any more, and its queued go-on is cancelled.") : "")
            }
        }
        // (its go-on couldn't start: why, e.g. … It starts once lab answers again)
        PlasmaComponents3.Label {
            id: why
            visible: !!line.task && !!line.task.error
            Layout.fillWidth: true
            textFormat: Text.PlainText
            elide: Text.ElideRight
            font: Kirigami.Theme.smallFont
            color: Kirigami.Theme.negativeTextColor
            text: line.task && line.task.error ? line.task.error : ""

            PlasmaCore.ToolTipArea {
                textFormat: Text.PlainText
                anchors.fill: parent
                active: why.truncated
                mainText: i18n("It couldn't start")
                subText: why.text
            }
        }
    }
    IconTextButton {
        icon.name: root.isContainer(line.host) ? "" : Icons.plasma.host
        icon.source: root.isContainer(line.host) ? root.hostIcon(line.host) : ""
        text: i18n("Show %1", line.where)
        Layout.preferredHeight: line.lineHeight
        Layout.alignment: Qt.AlignTop
        onClicked: root.showHost(line.host)
    }
    IconTextButton {
        visible: !line.wrote
        icon.name: Icons.plasma.cancel
        icon.color: Icons.color("cancel", Kirigami.Theme)
        text: line.kept ? i18n("Stop") : i18n("Cancel")
        Layout.preferredHeight: line.lineHeight
        Layout.alignment: Qt.AlignTop
        onClicked: {
            if (line.task)
                root.unqueue(line.task)   // (a kept chat's go-on: Keep going goes off with it, jump.py --unqueue)
            else if (line.kept)
                root.keepGoing({ chatId: line.kept.chat, sessionId: line.kept.chat }, false, line.host)
        }

        PlasmaCore.ToolTipArea {
            textFormat: Text.PlainText
            anchors.fill: parent
            mainText: line.kept ? i18n("Stop keeping it going") : i18n("Cancel it")
            subText: line.kept ? i18n("It doesn't go on by itself after usage limits any more; its queued go-on is cancelled.")
                               : i18n("It doesn't go on by itself.")
        }
    }
}
