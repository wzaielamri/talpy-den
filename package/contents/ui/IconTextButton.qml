import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami

// A small button with its words beside its icon (a chat's Continue on…, Go
// on at…, Keep going), as tight as a Tag beside it and as VS Code's
// (IconButton text-btn): the icon at 16 px, 2 px from its words, 3 px in
// from the left and 6 from the right. With the theme's margins (5 px each
// side) the icon took a 22 px slot squeezed to what the line's height left,
// drawn at 8 to 11 px with room on each side, and 4 px more before its words.
// Give it a Layout.preferredHeight: the icon is centered in it.
PlasmaComponents3.ToolButton {
    readonly property real iconSize: Kirigami.Units.iconSizes.small

    font: Kirigami.Theme.smallFont
    icon.width: iconSize
    icon.height: iconSize
    spacing: Kirigami.Units.smallSpacing / 2
    leftPadding: Math.round(Kirigami.Units.smallSpacing * 0.75)
    rightPadding: Math.round(Kirigami.Units.smallSpacing * 1.5)
    topPadding: Math.max(0, Math.floor((Layout.preferredHeight - iconSize) / 2))
    bottomPadding: Math.max(0, Layout.preferredHeight - iconSize - topPadding)
}
