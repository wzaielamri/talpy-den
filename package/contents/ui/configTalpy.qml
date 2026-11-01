import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM

// Settings, Talpy: the pet, Playful Talpy, and the chats' pets.
KCM.SimpleKCM {
    id: page

    property alias cfg_showPet: showPet.checked
    property alias cfg_playful: playful.checked
    property alias cfg_chatPets: chatPets.value

    // Plasma passes every setting and its default to each page: declaring the
    // defaults of this page's settings avoids "SimpleKCM does not have a
    // property called cfg_…Default" warnings for them.
    property bool cfg_showPetDefault
    property bool cfg_playfulDefault
    property int cfg_chatPetsDefault

    Kirigami.FormLayout {
        QQC2.CheckBox {
            id: showPet
            Kirigami.FormData.label: i18n("Pet:")
            text: i18n("Show Talpy, the pet, in the popup and in notifications")
        }

        QQC2.CheckBox {
            id: playful
            enabled: showPet.checked
            text: i18n("Playful Talpy: tricks and props, jokes, cookies and games")
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.text: i18n("Off, Talpy only shows what your chats do: his moods, his lamp and quiet moves (looking around, typing, thinking, sleeping). Notifications and badges stay as they are.")
        }

        QQC2.SpinBox {
            id: chatPets
            Kirigami.FormData.label: i18n("Chat pets per account, at most:")
            enabled: showPet.checked
            from: 0
            to: 8
        }
    }
}
