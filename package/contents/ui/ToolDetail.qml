import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import "codehtml.mjs" as Code

// A step's details in Talpy Chat, unfolded (a click on its line, or Ctrl+O for every one): the
// command and what it printed, the lines it read (numbered, in the file's colours), or what it was
// asked and got (codehtml.mjs; an edit's change is above it, in its row). ChatPane.qml's tool row
// makes it as it's opened, by a Loader (asynchronous when Ctrl+O opens them all: a few a frame), so
// a window opens as quickly. Long output folds as a long message does (FoldMore.qml)
Rectangle {
    id: detailBox

    readonly property string args: entry.line.indexOf(entry.name + ": ") === 0 ? entry.line.slice(entry.name.length + 2) : ""
    readonly property var outFold: entry.output !== "" ? pane.foldText(entry.output, "plain") : null
    readonly property bool outWhole: !outFold || (pane.openTools[entry.key + "/out"] !== undefined ? pane.openTools[entry.key + "/out"] : pane.allOpen)

    implicitHeight: column.implicitHeight + Kirigami.Units.largeSpacing * 1.5
    radius: Kirigami.Units.cornerRadius
    color: pane.mdStyle.blockBg
    border.width: 1
    border.color: pane.borderColor

    ColumnLayout {
        id: column
        anchors.fill: parent
        anchors.margins: Kirigami.Units.largeSpacing * 0.75
        spacing: Kirigami.Units.smallSpacing

        TextEdit {
            objectName: "findText"
            Layout.fillWidth: true
            text: Code.toolHtml({ name: entry.name, input: entry.input, output: detailBox.outWhole ? entry.output : detailBox.outFold.shown,
                                  status: entry.status }, detailBox.args, pane.codeStyle)
            textFormat: TextEdit.RichText
            readOnly: true
            selectByMouse: true
            wrapMode: TextEdit.Wrap
            color: Kirigami.Theme.textColor
            selectionColor: Kirigami.Theme.focusColor
            selectedTextColor: Kirigami.Theme.highlightedTextColor
        }
        Loader {
            active: detailBox.outFold !== null
            visible: active
            source: active ? "FoldMore.qml" : ""
            onLoaded: item.what = "tool"
        }
    }
}
