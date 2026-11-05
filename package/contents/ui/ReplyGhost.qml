import QtQuick
import org.kde.plasma.components as PlasmaComponents3

// What you type in Talpy Chat's reply box, completed in grey from your usual
// replies, right after it (ChatPane.qml, a Loader in the box at the end of its
// text: made only while there's a completion; Tab or → takes it)
PlasmaComponents3.Label {
    textFormat: Text.PlainText
    text: pane.ghost
    color: pane.mutedColor
    font: replyBox.font
    elide: Text.ElideRight
}
