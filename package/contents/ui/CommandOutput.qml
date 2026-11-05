import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami
import "ansi.mjs" as Ansi

// What a command you ran printed (pane.py's commands.py), under it in Talpy Chat as
// Claude's terminal shows it: ⎿ and its output in the code font, a little smaller, with
// its colours (ansi.mjs); what went wrong in the negative colour. ChatPane.qml's youItem,
// a Loader: read and made only for a command that printed something (VS Code chat.tsx
// CommandOutput the same). A long one folds as a long message does (FoldMore.qml).
RowLayout {
    spacing: 0
    readonly property bool failed: !!entry.commandData.error

    PlasmaComponents3.Label {
        Layout.preferredWidth: pane.gutter
        Layout.alignment: Qt.AlignTop
        horizontalAlignment: Text.AlignHCenter
        textFormat: Text.PlainText
        text: "⎿"
        color: pane.mutedColor
        font.family: pane.monoFamily
        font.pointSize: pane.pt * 0.9
    }
    ColumnLayout {
    Layout.fillWidth: true
    spacing: 0
    TextEdit {
        objectName: "findText"
        Layout.fillWidth: true
        readOnly: true
        selectByMouse: true
        textFormat: TextEdit.RichText
        wrapMode: TextEdit.Wrap
        text: Ansi.html((entry.outWhole ? entry.commandData.output : entry.foldData.outCut) || "", {
            fg: pane.hex(parent.failed ? Kirigami.Theme.negativeTextColor : pane.mutedColor),
            bg: pane.hex(pane.mix(pane.textColor, 0)), dark: pane.dark })
        color: parent.failed ? Kirigami.Theme.negativeTextColor : pane.mutedColor
        selectionColor: Kirigami.Theme.focusColor
        selectedTextColor: Kirigami.Theme.highlightedTextColor
        font.family: pane.monoFamily
        font.pointSize: pane.pt * 0.9
    }
    // (a long one: Show more · N more lines, FoldMore.qml)
    Loader {
        active: !!entry.foldData && entry.foldData.outCut !== ""
        visible: active
        source: active ? "FoldMore.qml" : ""
        onLoaded: item.what = "out"
    }
    }
}
