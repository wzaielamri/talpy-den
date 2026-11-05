import QtQuick
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
    property bool caution: false    // outlined and written in the warning colour (close to something: the context to its compaction)
    property bool clickable: false
    // In a list's row: the row's colors (ListPalette.qml), so the tag has no
    // theme of its own (one each made a long list slow to make); elsewhere
    // the theme's
    property var colors: null
    readonly property var theme: colors || Kirigami.Theme
    signal clicked()

    implicitWidth: (icon !== "" ? mark.width + (label.text !== "" ? Kirigami.Units.smallSpacing / 2 : 0) : 0)
                   + (label.text !== "" ? label.implicitWidth : 0) + Kirigami.Units.smallSpacing * 2
    implicitHeight: Math.max(label.implicitHeight, icon !== "" ? mark.height + 2 : 0)
    radius: Kirigami.Units.cornerRadius
    color: "transparent"
    border.width: 1
    border.color: warning ? theme.negativeTextColor : caution ? theme.neutralTextColor : active ? theme.focusColor
                  : Qt.rgba(theme.textColor.r, theme.textColor.g, theme.textColor.b, 0.3)

    Loader {   // (made only on a tag with an icon: most have none)
        id: mark
        active: tag.icon !== ""
        visible: active
        width: Kirigami.Units.iconSizes.small
        height: width
        anchors.verticalCenter: parent.verticalCenter
        x: label.text !== "" ? Kirigami.Units.smallSpacing : (parent.width - width) / 2
        sourceComponent: Kirigami.Icon {
            source: tag.icon
            // (its tone's color; else a plain icon takes the warning's color, as its text; a warning's own icon stays as it is)
            color: tag.tone !== "" ? Icons.color(tag.tone, tag.theme)
                 : tag.warning && tag.icon !== Icons.plasma.warning ? tag.theme.negativeTextColor : tag.theme.textColor
            opacity: tag.warning || tag.tone !== "" ? 1 : 0.8
        }
    }
    // (as a PlasmaComponents3.Label draws it)
    Text {
        id: label
        anchors.verticalCenter: parent.verticalCenter
        x: tag.icon !== "" ? mark.x + mark.width + Kirigami.Units.smallSpacing / 2 : (parent.width - implicitWidth) / 2
        textFormat: Text.PlainText
        font: tag.theme.smallFont
        color: tag.warning ? tag.theme.negativeTextColor : tag.caution ? tag.theme.neutralTextColor : tag.theme.textColor
        opacity: tag.warning || tag.caution ? 1 : 0.8
        Accessible.role: Accessible.StaticText
        Accessible.name: text
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
