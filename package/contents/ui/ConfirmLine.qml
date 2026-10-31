import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami
import "icons.mjs" as Icons

// "Do this?" with a button that does it and one that doesn't. The one that
// does it carries the icon of the button that asked (confirmIcon: its
// meaning in icons.mjs, colored as there), as the settings' and the
// Permissions tab's confirmations do.
RowLayout {
    id: confirm

    property alias text: question.text
    property string confirmText: i18n("Yes")
    property string confirmIcon: ""
    property string cancelText: i18n("Cancel")
    signal confirmed()
    signal cancelled()

    spacing: Kirigami.Units.smallSpacing

    PlasmaComponents3.Label {
        id: question
        textFormat: Text.PlainText
        Layout.fillWidth: true
        wrapMode: Text.Wrap
        color: Kirigami.Theme.neutralTextColor
    }
    PlasmaComponents3.Button {
        text: confirm.confirmText
        icon.name: confirm.confirmIcon ? Icons.plasma[confirm.confirmIcon] : ""
        icon.color: confirm.confirmIcon ? Icons.color(confirm.confirmIcon, Kirigami.Theme) : "transparent"
        onClicked: confirm.confirmed()
    }
    PlasmaComponents3.Button {
        text: confirm.cancelText
        onClicked: confirm.cancelled()
    }
}
