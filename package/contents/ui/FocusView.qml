import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.core as PlasmaCore
import org.kde.kirigami as Kirigami
import "icons.mjs" as Icons

// The focus view (the header's filter button, root.focusView): only what
// needs you, as full rows (their questions, Allow / Deny, Go on), the chats
// that finished a turn you haven't looked at yet, one line for each chat at work with
// what it does now, and how the rest stands; Show everything goes back to
// the whole dashboard.
ColumnLayout {
    id: fv

    readonly property var lists: root.focusLists
    spacing: Kirigami.Units.smallSpacing

    ListPalette {   // (its rows' colors: SessionRow)
        id: focusColors
    }

    // ------------------------------------------------------------ what needs you

    Kirigami.Heading {
        level: 4
        textFormat: Text.PlainText
        Layout.fillWidth: true
        Layout.leftMargin: Kirigami.Units.smallSpacing
        text: fv.lists.needs.length ? i18np("Needs you", "%1 need you", fv.lists.needs.length) : i18n("Nothing needs you")
        color: fv.lists.needs.length ? Kirigami.Theme.neutralTextColor : Kirigami.Theme.positiveTextColor
    }
    Repeater {
        model: fv.lists.needs.length
        delegate: SessionRow {
            required property int index
            readonly property var item: fv.lists.needs[index] || null
            Layout.fillWidth: true
            colors: focusColors
            session: item ? item.session : root.emptySession
            showProfile: item ? item.multi : false
            remoteHost: item ? item.host : ""
            account: item ? item.account : ""
        }
    }

    // Finished, and you haven't looked at it yet: one line each (click: its pane)
    Repeater {
        model: fv.lists.finished.length
        delegate: FocusLine {
            required property int index
            Layout.fillWidth: true
            item: fv.lists.finished[index] || null
            finished: true
        }
    }

    // ------------------------------------------------------------ at work

    Kirigami.Heading {
        visible: fv.lists.working.length > 0
        level: 4
        textFormat: Text.PlainText
        Layout.fillWidth: true
        Layout.leftMargin: Kirigami.Units.smallSpacing
        Layout.topMargin: Kirigami.Units.smallSpacing
        text: i18np("Working", "%1 working", fv.lists.working.length)
    }
    Repeater {
        model: fv.lists.working.length
        delegate: FocusLine {
            required property int index
            Layout.fillWidth: true
            item: fv.lists.working[index] || null
        }
    }

    // ------------------------------------------------------------ the rest

    Kirigami.Separator {
        Layout.fillWidth: true
        Layout.topMargin: Kirigami.Units.smallSpacing
    }
    PlasmaComponents3.Label {
        textFormat: Text.PlainText
        Layout.fillWidth: true
        Layout.leftMargin: Kirigami.Units.smallSpacing
        visible: text !== ""
        text: fv.lists.rest
        opacity: 0.75
        wrapMode: Text.Wrap
    }
    // Each account's plan usage, one short line
    PlasmaComponents3.Label {
        textFormat: Text.PlainText
        Layout.fillWidth: true
        Layout.leftMargin: Kirigami.Units.smallSpacing
        visible: text !== ""
        text: fv.lists.usage
        font: Kirigami.Theme.smallFont
        opacity: 0.75
        wrapMode: Text.Wrap
    }
    PlasmaComponents3.Button {
        Layout.alignment: Qt.AlignHCenter
        icon.name: Icons.plasma.showAll
        text: i18n("Show everything")
        onClicked: root.setFocusView(false)
    }
}
