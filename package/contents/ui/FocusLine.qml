import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.core as PlasmaCore
import org.kde.kirigami as Kirigami

// One chat in the focus view (FocusView.qml): its pet's color, a dot for its
// state, its name and what it does now (or that it finished), how long; a
// click opens its pane (or its window, as a click on a chat's name does)
Item {
    id: line

    property var item: null          // {key, session, host, account}
    property bool finished: false
    readonly property var s: item ? item.session : root.emptySession
    readonly property string doing: finished ? "" : root.doingText(s, item ? item.host : "")
    readonly property string what: finished ? (s.reason === "failed" ? i18n("Failed: look at what happened")
                                                                      : i18n("Finished: results to look at"))
                                            : doing || root.stateText(s)

    implicitHeight: row.implicitHeight + Kirigami.Units.smallSpacing

    HoverHandler {
        id: lineHover
    }
    HoverShade {
        target: line
        shown: lineHover.hovered
    }

    RowLayout {
        id: row
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.leftMargin: Kirigami.Units.smallSpacing
        anchors.rightMargin: Kirigami.Units.smallSpacing
        spacing: Kirigami.Units.smallSpacing

        Rectangle {
            Layout.preferredWidth: 3
            Layout.preferredHeight: nameLabel.implicitHeight
            radius: 1.5
            color: root.petColors[line.item ? line.item.key : ""] || "transparent"
        }
        Rectangle {
            Layout.preferredWidth: Kirigami.Units.smallSpacing * 2
            Layout.preferredHeight: Layout.preferredWidth
            radius: width / 2
            // (as its row's: the projects tab lists every open chat, not only working ones)
            color: line.finished ? Kirigami.Theme.positiveTextColor
                 : line.s.reason === "failed" || (line.s.stopped && !line.s.stopped.over) ? Kirigami.Theme.negativeTextColor
                 : root.stateColor(line.s.state)
        }
        PlasmaComponents3.Label {
            id: nameLabel
            textFormat: Text.PlainText
            Layout.maximumWidth: Kirigami.Units.gridUnit * 10
            text: (line.item && line.item.host ? root.hostLabel(line.item.host) + ": " : "") + line.s.name
            font.weight: Font.DemiBold
            elide: Text.ElideRight
        }
        PlasmaComponents3.Label {
            textFormat: Text.PlainText
            Layout.fillWidth: true
            text: line.what
            opacity: 0.8
            elide: Text.ElideRight
        }
        PlasmaComponents3.Label {
            textFormat: Text.PlainText
            visible: line.doing !== "" && line.s.since > 0   // (the state's text says how long itself)
            text: root.duration(root.now - line.s.since)
            font: Kirigami.Theme.smallFont
            opacity: 0.6
        }
    }

    PlasmaCore.ToolTipArea {
        textFormat: Text.PlainText
        anchors.fill: parent
        mainText: line.s.name
        subText: line.what + "\n" + i18n("Click to open this chat")
    }
    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: if (line.item) root.clickChat(line.s, line.item.host)
    }
}
