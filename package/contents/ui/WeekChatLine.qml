import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami

// A chat in the Recap tab's lists (WeekView.qml): its name, where (or when),
// and its numbers, the last two right-aligned in columns as wide as the
// list's widest (whereWidth, numbersWidth; -1: its own). Click it to bring
// the chat up.
PlasmaComponents3.ItemDelegate {
    id: line

    property var chat: ({ name: "", chatId: "", host: "", profileDir: "", folder: "", cwd: "" })
    property string where: (chat.host ? chat.host + ": " : "") + (chat.folder || "")
    property string numbers: ""
    property real indent: 0
    property real whereWidth: -1
    property real numbersWidth: -1

    Layout.fillWidth: true
    leftPadding: Kirigami.Units.smallSpacing + indent
    topPadding: Math.round(Kirigami.Units.smallSpacing / 2)
    bottomPadding: Math.round(Kirigami.Units.smallSpacing / 2)
    enabled: !chat.host && !!chat.chatId   // (an SSH host's chat: its row in the Chats tab opens it)
    onClicked: root.openChatById(chat.chatId, chat.profileDir, chat.cwd || "", "", "", "")

    contentItem: RowLayout {
        spacing: Kirigami.Units.smallSpacing

        PlasmaComponents3.Label {
            textFormat: Text.PlainText
            Layout.fillWidth: true
            text: line.chat.name
            elide: Text.ElideRight
            font: line.indent > 0 ? Kirigami.Theme.smallFont : Kirigami.Theme.defaultFont
        }
        PlasmaComponents3.Label {
            textFormat: Text.PlainText
            Layout.preferredWidth: line.whereWidth
            Layout.maximumWidth: Kirigami.Units.gridUnit * 7
            visible: text !== "" || line.whereWidth > 1
            horizontalAlignment: Text.AlignRight
            text: line.where
            elide: Text.ElideMiddle
            font: Kirigami.Theme.smallFont
            opacity: 0.6
        }
        PlasmaComponents3.Label {
            textFormat: Text.PlainText
            Layout.preferredWidth: line.numbersWidth
            horizontalAlignment: Text.AlignRight
            text: line.numbers
            font: Kirigami.Theme.smallFont
            opacity: 0.8
        }
    }
}
