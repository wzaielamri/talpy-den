import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.core as PlasmaCore
import org.kde.kirigami as Kirigami
import "icons.mjs" as Icons

// A chat in What got done (WeekView.qml), unfolded under its project: its
// line (its name, what it got done, its time and amount; a click brings it
// up), then Claude's recap of what it did then (one line, the whole in its
// tooltip) and its commits' subjects, the newest first: three, then how
// many more (week.py chat_done). Made only while its project is unfolded.
ColumnLayout {
    id: done

    property var chat: ({ name: "", chatId: "", host: "", profileDir: "", folder: "", cwd: "", commits: [],
                          commitCount: 0, recap: null })
    property string where: ""
    property string numbers: ""
    property string tip: ""   // (its share of your week, for its line's tooltip)
    property real indent: 0
    property real whereWidth: -1
    property real numbersWidth: -1
    readonly property var commits: (chat.commits || []).slice(0, 3)
    readonly property int moreCommits: (chat.commitCount || 0) - commits.length
    // (under the chat's name)
    readonly property real textIndent: indent + Kirigami.Units.smallSpacing * 2

    Layout.fillWidth: true
    spacing: 0

    WeekChatLine {
        chat: done.chat
        where: done.where
        indent: done.indent
        numbers: done.numbers
        tip: done.tip
        whereWidth: done.whereWidth
        numbersWidth: done.numbersWidth
    }
    PlasmaComponents3.Label {
        textFormat: Text.PlainText
        Layout.fillWidth: true
        Layout.leftMargin: done.textIndent
        visible: !!done.chat.recap
        text: done.chat.recap ? done.chat.recap.text.replace(/\s+/g, " ") : ""
        elide: Text.ElideRight
        maximumLineCount: 1
        font: Kirigami.Theme.smallFont
        opacity: 0.7

        PlasmaCore.ToolTipArea {
            textFormat: Text.PlainText
            anchors.fill: parent
            mainText: i18n("Claude's recap")
            subText: done.chat.recap ? done.chat.recap.text : ""
        }
    }
    Repeater {
        model: done.commits.length
        delegate: RowLayout {
            id: commitLine
            required property int index
            readonly property var commit: done.commits[index] || ["", ""]
            Layout.fillWidth: true
            Layout.leftMargin: done.textIndent
            spacing: Math.round(Kirigami.Units.smallSpacing / 2)

            Kirigami.Icon {
                Layout.preferredWidth: Math.round(Kirigami.Units.iconSizes.small * 0.75)
                Layout.preferredHeight: Layout.preferredWidth
                source: Icons.plasma.commit
                opacity: 0.6
            }
            PlasmaComponents3.Label {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                text: commitLine.commit[1]
                elide: Text.ElideRight
                font: Kirigami.Theme.smallFont
                opacity: 0.8

                PlasmaCore.ToolTipArea {
                    textFormat: Text.PlainText
                    anchors.fill: parent
                    mainText: commitLine.commit[1]
                    subText: commitLine.commit[0] ? i18n("Commit %1", commitLine.commit[0]) : ""
                }
            }
            PlasmaComponents3.Label {
                textFormat: Text.PlainText
                visible: commitLine.index === done.commits.length - 1 && done.moreCommits > 0
                text: i18np("and %1 more", "and %1 more", done.moreCommits)
                font: Kirigami.Theme.smallFont
                opacity: 0.6
            }
        }
    }
}
