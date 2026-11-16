import QtQuick
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami
import "sides.mjs" as Sides
import "icons.mjs" as Icons

// "Explain this", right after "Reply to this" where a selection's drag ended in Talpy Chat (ChatPane.qml:
// made only then, not in a new chat): what you selected, quoted, asked as a side question (Sides.qml
// explain) in the panel, which opens if it's closed; nothing is added to the chat. The right-click menu
// has it too (EditMenu.qml). VS Code chat.tsx: the same words.
PlasmaComponents3.Button {
    icon.source: root.iconDir + Icons.plasma.explain
    text: Sides.EXPLAIN_BUTTON
    focusPolicy: Qt.NoFocus
    onClicked: pane.explain(pane.selectionText())
    PlasmaComponents3.ToolTip.text: Sides.EXPLAIN_TIP
    PlasmaComponents3.ToolTip.visible: hovered
    PlasmaComponents3.ToolTip.delay: Kirigami.Units.toolTipDelay
}
