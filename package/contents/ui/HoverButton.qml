import QtQuick
import QtQuick.Layouts
import org.kde.ksvg as KSvg
import org.kde.kirigami as Kirigami

// One of a line's buttons (HoverButtons.qml; a project's, in its tab): its
// icon only, drawn at 16 px as the line's own icons (its kind, a starred
// one's ★) and as VS Code's, in a box 20 px wide and 22 high, packed close:
// 2 px each side. The theme's button margins (5 px each side) left a 20 px
// box 10 px for the icon, which Plasma drew at 8 to 10 px.
// Drawn as Plasma's flat tool buttons are (the theme's hover, press and
// focus frames, made only while one shows), but of plain items: a line makes
// its buttons the first time it's hovered, and a PlasmaComponents3.ToolButton
// took milliseconds to make in a popup that holds a long list (scrolling
// under a still pointer stuttered at each line that came under it).
// Children (a PlasmaCore.ToolTipArea) go over it, as on a button.
Item {
    id: button

    // false: greyed out in its place (so every line's buttons stay in the
    // same columns), its icon at 40% as VS Code's disabled buttons, with no
    // click, hover or focus; its tooltip still says why, as VS Code's.
    // (enabled: false drew the icon at 13%, all but gone, with no tooltip.)
    property bool usable: true
    property string text
    property bool checked: false
    readonly property HoverIcon icon: HoverIcon {}
    readonly property real iconSize: Kirigami.Units.iconSizes.small
    readonly property bool hoverEnabled: usable && !Kirigami.Settings.tabletMode
    readonly property bool hovered: mouse.containsMouse
    readonly property bool down: mouse.pressed || spaceDown
    property bool spaceDown: false
    // (the keyboard's focus, as a button shows it: by Tab, not by a click)
    readonly property bool visualFocus: activeFocus && !mouseFocus
    property bool mouseFocus: false
    readonly property alias contentItem: iconItem
    default property alias content: mouse.data
    signal clicked()

    implicitWidth: iconSize + 4
    implicitHeight: Math.round(iconSize * 1.375)
    Layout.preferredWidth: iconSize + 4
    Layout.preferredHeight: Math.round(iconSize * 1.375)
    readonly property real leftPadding: (Layout.preferredWidth - iconSize) / 2
    readonly property real topPadding: Math.floor((Layout.preferredHeight - iconSize) / 2)
    activeFocusOnTab: usable
    focusPolicy: usable ? Qt.StrongFocus : Qt.NoFocus

    Accessible.role: Accessible.Button
    Accessible.name: text
    Accessible.onPressAction: if (button.usable) button.clicked()
    Keys.onPressed: event => {
        if (event.key === Qt.Key_Space && !event.isAutoRepeat && button.usable) {
            button.spaceDown = true
            event.accepted = true
        } else if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && button.usable) {
            button.clicked()
            event.accepted = true
        }
    }
    Keys.onReleased: event => {
        if (event.key === Qt.Key_Space && !event.isAutoRepeat && button.spaceDown) {
            button.spaceDown = false
            event.accepted = true
            button.clicked()
        }
    }
    onActiveFocusChanged: {
        if (!activeFocus) {
            spaceDown = false
            mouseFocus = false
        }
    }

    // the theme's frames of a flat tool button: hovered, pressed (or on), the keyboard's focus
    Loader {
        anchors.fill: parent
        active: button.usable && (button.hovered || button.down || button.checked || button.visualFocus)
        sourceComponent: Item {
            KSvg.FrameSvgItem {
                anchors.fill: parent
                imagePath: "widgets/button"
                prefix: ["toolbutton-hover", "normal"]
                visible: button.hovered
            }
            KSvg.FrameSvgItem {
                anchors.fill: parent
                imagePath: "widgets/button"
                prefix: ["toolbutton-pressed", "pressed"]
                opacity: button.checked || button.down ? 1 : 0
            }
            KSvg.FrameSvgItem {
                anchors.fill: parent
                anchors.leftMargin: -margins.left
                anchors.topMargin: -margins.top
                anchors.rightMargin: -margins.right
                anchors.bottomMargin: -margins.bottom
                imagePath: "widgets/button"
                prefix: ["toolbutton-focus", "focus"]
                opacity: button.visualFocus && !button.down ? 1 : 0
            }
        }
    }

    // (the icon alone, at its size)
    Kirigami.Icon {
        id: iconItem
        x: button.leftPadding
        y: button.topPadding
        width: button.iconSize
        height: button.iconSize
        implicitWidth: button.iconSize
        implicitHeight: button.iconSize
        source: button.icon.name !== "" ? button.icon.name : button.icon.source
        color: button.icon.color
        opacity: button.usable ? 1 : 0.4
    }

    MouseArea {   // (not usable: its clicks stop here)
        id: mouse
        anchors.fill: parent
        hoverEnabled: button.hoverEnabled
        acceptedButtons: button.usable ? Qt.LeftButton : Qt.AllButtons
        onPressed: button.mouseFocus = true
        // (a press that didn't give it the focus: the next Tab that does shows it)
        onReleased: if (!button.activeFocus) button.mouseFocus = false
        onCanceled: if (!button.activeFocus) button.mouseFocus = false
        onClicked: if (button.usable) button.clicked()
    }
}
