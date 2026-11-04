import QtQuick
import QtQuick.Window
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.core as PlasmaCore
import org.kde.kirigami as Kirigami

// A tooltip over what it fills, for what shows both in the popup and in the
// chat pane: Plasma's in the popup; in the chat pane, a window of its own
// that Plasma's would show at the screen's edge, one drawn in that window,
// beside what you hover. Children (a MouseArea) as in PlasmaCore.ToolTipArea.
Item {
    id: tip

    property string mainText
    property string subText
    property bool active: true
    property int textFormat: Text.PlainText
    readonly property bool inPane: Window.window !== null && Window.window.objectName === "talpyDenChatPane"

    PlasmaCore.ToolTipArea {
        anchors.fill: parent
        active: tip.active && !tip.inPane
        textFormat: tip.textFormat
        mainText: tip.mainText
        subText: tip.subText
    }
    HoverHandler {
        id: hover
        enabled: tip.inPane
    }
    // (made only in the chat pane: in the popup it never shows, and one in
    // each tag made the popup's lists slow to open)
    Loader {
        anchors.fill: parent
        active: tip.inPane
        sourceComponent: Item {
            PlasmaComponents3.ToolTip {
                parent: tip
                visible: tip.inPane && tip.active && hover.hovered && (tip.mainText !== "" || tip.subText !== "")
                delay: Kirigami.Units.toolTipDelay
                textFormat: tip.textFormat   // (its label guesses rich text: a plan title's <img src=…> would be markup)
                text: tip.subText ? tip.mainText + "\n" + tip.subText : tip.mainText
            }
        }
    }
}
