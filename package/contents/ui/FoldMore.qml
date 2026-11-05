import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami
import "icons.mjs" as Icons

// Under a long text in Talpy Chat, folded (find.mjs foldOf: past about 40 lines, its first 24
// show): "Show more · 17 more lines", and "Show less" once it shows all of it, which folds it again
// with this kept under the pointer (ChatPane toggleFold). Read and made only for a long one, by a
// Loader in its row (what: "text", the message or reply; "out", a command's output; "tool", a
// step's output, ToolDetail.qml). VS Code chat.tsx FoldMore: the same words
RowLayout {
    id: more

    property string what: "text"
    readonly property string foldKey: what === "text" ? entry.key : entry.key + "/out"
    readonly property bool whole: what === "tool" ? detailBox.outWhole : what === "out" ? entry.outWhole : entry.whole
    readonly property int lines: what === "tool" ? (detailBox.outFold ? detailBox.outFold.more : 0)
                                 : !entry.foldData ? 0 : what === "out" ? entry.foldData.outMore : entry.foldData.more

    spacing: Kirigami.Units.smallSpacing

    Kirigami.Icon {
        Layout.preferredWidth: Kirigami.Units.iconSizes.small * 0.75
        Layout.preferredHeight: Layout.preferredWidth
        source: more.whole ? Icons.plasma.unfolded : Icons.plasma.folded
        color: pane.mutedColor
    }
    PlasmaComponents3.Label {
        textFormat: Text.PlainText
        text: more.whole ? i18n("Show less") : i18np("Show more · 1 more line", "Show more · %1 more lines", more.lines)
        color: hover.hovered ? Kirigami.Theme.textColor : pane.mutedColor
        font.family: pane.chatFamily
        font.pointSize: pane.pt * 0.85
    }
    HoverHandler {
        id: hover
        cursorShape: Qt.PointingHandCursor
    }
    TapHandler {
        gesturePolicy: TapHandler.ReleaseWithinBounds
        onTapped: pane.toggleFold(more.foldKey, more.whole, more)
    }
    PlasmaComponents3.ToolTip.text: (more.whole ? i18n("Fold it again") : i18n("Show all of it")) + " " + i18n("(Ctrl+O: unfold or fold every long one)")
    PlasmaComponents3.ToolTip.visible: hover.hovered
    PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
}
