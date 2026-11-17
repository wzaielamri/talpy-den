import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami
import "icons.mjs" as Icons

// What a chat runs in the background now, under Talpy Chat's working line (ChatPane.qml's list
// footer: read and made only while it works and runs one; pane.shells, from pane.py
// --conversation: shells.py), so you see what it waits on and not only Working…. The Chat tab:
// a line for each (the first three, then how many more), its command's first line cut to fit,
// and since when. The Steps tab: each one's whole command and what Claude called it, a long one
// folded (Show more · N more lines, Show less: as a long reply's). VS Code chat.tsx ShellLines:
// the same.
ColumnLayout {
    id: lines

    readonly property int most: 3     // (lines on the Chat tab)
    readonly property int fold: 6     // (a command's lines shown folded on the Steps tab)
    readonly property bool steps: pane.listTab === "steps"
    readonly property var shown: steps ? pane.shells : pane.shells.slice(0, most)
    property var whole: ({})          // (a long command shown whole: by its shell's id)

    spacing: Kirigami.Units.smallSpacing / 2

    Repeater {
        model: lines.shown
        delegate: ColumnLayout {
            id: shell

            required property var modelData
            readonly property string command: (modelData.command || "").replace(/\s+$/, "")
            readonly property var commandLines: command.split("\n")
            readonly property string firstLine: (commandLines.find(l => l.trim() !== "") || "").trim()
            readonly property bool long: lines.steps && commandLines.length > lines.fold + 2
            readonly property bool open: !long || !!lines.whole[modelData.id]

            Layout.fillWidth: true
            spacing: 0

            RowLayout {
                Layout.fillWidth: true
                spacing: 0

                Kirigami.Icon {
                    Layout.preferredWidth: pane.gutter
                    Layout.preferredHeight: Math.round(fm.height * 0.8)
                    source: Icons.plasma.terminal
                    color: pane.mutedColor
                }
                // Chat tab: the command, cut; Steps tab: what Claude called it (the command's under it)
                PlasmaComponents3.Label {
                    Layout.fillWidth: true
                    textFormat: Text.PlainText
                    text: lines.steps ? (shell.modelData.description || i18n("Background shell"))
                                      : shell.firstLine || shell.modelData.description || i18n("A background shell")
                    elide: Text.ElideRight
                    maximumLineCount: 1
                    color: pane.mutedColor
                    font.family: lines.steps ? Kirigami.Theme.defaultFont.family : pane.chatFamily
                    font.pointSize: pane.pt * 0.9
                }
                PlasmaComponents3.Label {
                    visible: shell.modelData.started > 0
                    Layout.leftMargin: Kirigami.Units.smallSpacing
                    textFormat: Text.PlainText
                    text: lines.steps ? i18nc("a background shell's start", "background shell, since %1", pane.timeText(shell.modelData.started))
                                      : i18nc("a background shell's start", "since %1", pane.timeText(shell.modelData.started))
                    color: pane.mutedColor
                    font.pointSize: pane.pt * 0.85
                }
            }
            // Steps tab: the whole command (folded past `fold` lines), selectable
            TextEdit {
                visible: lines.steps && shell.command !== ""
                Layout.fillWidth: true
                Layout.leftMargin: pane.gutter
                readOnly: true
                selectByMouse: true
                textFormat: TextEdit.PlainText
                wrapMode: TextEdit.WrapAnywhere
                text: shell.open ? shell.command : shell.commandLines.slice(0, lines.fold).join("\n")
                color: Kirigami.Theme.textColor
                font.family: pane.monoFamily
                font.pointSize: pane.pt * 0.9
            }
            RowLayout {
                visible: shell.long
                Layout.leftMargin: pane.gutter
                spacing: Kirigami.Units.smallSpacing

                Kirigami.Icon {
                    Layout.preferredWidth: Kirigami.Units.iconSizes.small * 0.75
                    Layout.preferredHeight: Layout.preferredWidth
                    source: shell.open ? Icons.plasma.unfolded : Icons.plasma.folded
                    color: pane.mutedColor
                }
                PlasmaComponents3.Label {
                    textFormat: Text.PlainText
                    text: shell.open ? i18n("Show less")
                                     : i18np("Show more · 1 more line", "Show more · %1 more lines", shell.commandLines.length - lines.fold)
                    color: foldHover.hovered ? Kirigami.Theme.textColor : pane.mutedColor
                    font.family: pane.chatFamily
                    font.pointSize: pane.pt * 0.85
                }
                HoverHandler {
                    id: foldHover
                    cursorShape: Qt.PointingHandCursor
                }
                TapHandler {
                    onTapped: {
                        const now = Object.assign({}, lines.whole)
                        now[shell.modelData.id] = !shell.open
                        lines.whole = now
                    }
                }
            }
        }
    }
    PlasmaComponents3.Label {
        visible: !lines.steps && pane.shells.length > lines.most
        Layout.leftMargin: pane.gutter
        textFormat: Text.PlainText
        text: i18np("and 1 more in the background (the Steps tab lists them)", "and %1 more in the background (the Steps tab lists them)",
                    pane.shells.length - lines.most)
        color: pane.mutedColor
        font.pointSize: pane.pt * 0.85
    }
}
