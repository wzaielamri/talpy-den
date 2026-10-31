import QtQuick
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami
import "icons.mjs" as Icons

// Small outlined label, e.g. the profile or "VS Code" next to a session name.
Rectangle {
    id: tag

    property alias text: label.text
    property string icon: ""        // an icon before the text (one of icons.mjs), as big as the buttons'
    property string tone: ""        // the meaning whose color the icon takes (icons.mjs TONES: failed red, done green…)
    property string tooltip
    property string tooltipTitle: label.text
    property bool active: false     // outlined in the highlight colour
    property bool warning: false    // outlined and written in the negative colour
    property bool clickable: false
    signal clicked()

    implicitWidth: (icon !== "" ? mark.width + (label.text !== "" ? Kirigami.Units.smallSpacing / 2 : 0) : 0)
                   + (label.text !== "" ? label.implicitWidth : 0) + Kirigami.Units.smallSpacing * 2
    implicitHeight: Math.max(label.implicitHeight, icon !== "" ? mark.height + 2 : 0)
    radius: Kirigami.Units.cornerRadius
    color: "transparent"
    border.width: 1
    border.color: warning ? Kirigami.Theme.negativeTextColor : active ? Kirigami.Theme.focusColor
                  : Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.3)

    Kirigami.Icon {
        id: mark
        visible: tag.icon !== ""
        source: tag.icon
        width: Kirigami.Units.iconSizes.small
        height: width
        anchors.verticalCenter: parent.verticalCenter
        x: label.text !== "" ? Kirigami.Units.smallSpacing : (parent.width - width) / 2
        // (its tone's color; else a plain icon takes the warning's color, as its text; a warning's own icon stays as it is)
        color: tag.tone !== "" ? Icons.color(tag.tone, Kirigami.Theme)
             : tag.warning && tag.icon !== Icons.plasma.warning ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.textColor
        opacity: tag.warning || tag.tone !== "" ? 1 : 0.8
    }
    PlasmaComponents3.Label {
        id: label
        anchors.verticalCenter: parent.verticalCenter
        x: tag.icon !== "" ? mark.x + mark.width + Kirigami.Units.smallSpacing / 2 : (parent.width - implicitWidth) / 2
        textFormat: Text.PlainText
        font: Kirigami.Theme.smallFont
        color: tag.warning ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.textColor
        opacity: tag.warning ? 1 : 0.8
    }

    TipArea {
        textFormat: Text.PlainText
        anchors.fill: parent
        active: tag.tooltip !== ""
        mainText: tag.tooltipTitle
        subText: tag.tooltip

        MouseArea {
            anchors.fill: parent
            enabled: tag.clickable
            cursorShape: tag.clickable ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: tag.clicked()
        }
    }
}
