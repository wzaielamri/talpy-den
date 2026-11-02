import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami

// One of a line's buttons (HoverButtons.qml; a project's, in its tab): its
// icon only, drawn at 16 px as the line's own icons (its kind, a starred
// one's ★) and as VS Code's, in a box 20 px wide and 22 high, packed close:
// 2 px each side. The theme's button margins (5 px each side) left a 20 px
// box 10 px for the icon, which Plasma drew at 8 to 10 px.
PlasmaComponents3.ToolButton {
    id: button

    // false: greyed out in its place (so every line's buttons stay in the
    // same columns), its icon at 40% as VS Code's disabled buttons, with no
    // click, hover or focus; its tooltip still says why, as VS Code's.
    // (enabled: false drew the icon at 13%, all but gone, with no tooltip.)
    property bool usable: true
    readonly property real iconSize: Kirigami.Units.iconSizes.small

    display: PlasmaComponents3.AbstractButton.IconOnly
    icon.width: iconSize
    icon.height: iconSize
    Layout.preferredWidth: iconSize + 4
    Layout.preferredHeight: Math.round(iconSize * 1.375)
    leftPadding: (Layout.preferredWidth - iconSize) / 2
    rightPadding: leftPadding
    topPadding: Math.floor((Layout.preferredHeight - iconSize) / 2)
    bottomPadding: Layout.preferredHeight - iconSize - topPadding
    hoverEnabled: usable && !Kirigami.Settings.tabletMode
    focusPolicy: usable ? Qt.StrongFocus : Qt.NoFocus
    Kirigami.MnemonicData.enabled: usable && enabled && visible

    // (the icon alone, at its size: the button's own content, a row for an
    // icon and its words, sizes the icon by the room the margins leave)
    contentItem: Kirigami.Icon {
        implicitWidth: button.iconSize
        implicitHeight: button.iconSize
        source: button.icon.name !== "" ? button.icon.name : button.icon.source
        color: button.icon.color
        opacity: button.usable ? 1 : 0.4
    }

    MouseArea {   // (not usable: its clicks stop here)
        anchors.fill: parent
        z: 1
        enabled: !button.usable
        acceptedButtons: Qt.AllButtons
    }
}
