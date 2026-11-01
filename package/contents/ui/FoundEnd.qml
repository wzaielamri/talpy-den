import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami

// The end of a line of what "Find a chat" found (SearchResults.qml,
// FoundLine.qml): its folder and how long ago, right-aligned in columns as
// wide as a recent chat's (RecentLine.qml), the room of a starred one's ★
// between them, so they line up from line to line and with the account's lists.
RowLayout {
    id: end

    property string folder
    property string ago

    spacing: Kirigami.Units.smallSpacing

    PlasmaComponents3.Label {
        Layout.preferredWidth: Kirigami.Units.gridUnit * 8   // (GroupSection.folderWidth)
        horizontalAlignment: Text.AlignRight
        textFormat: Text.PlainText
        text: end.folder
        opacity: 0.6
        font: Kirigami.Theme.smallFont
        elide: Text.ElideMiddle
    }
    Item {   // (where a starred chat's ★ stands: StarMark.qml)
        Layout.preferredWidth: Kirigami.Units.iconSizes.small
    }
    PlasmaComponents3.Label {
        Layout.preferredWidth: root.agoWidth
        horizontalAlignment: Text.AlignRight
        textFormat: Text.PlainText
        text: end.ago
        opacity: 0.6
        font: Kirigami.Theme.smallFont
    }
}
