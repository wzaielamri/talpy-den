import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM

// Settings, Usage & limits: the usage cap, and how old plan usage may get
// before Claude Code fetches it.
ConfigPage {
    id: page

    property int cfg_usageCap
    property alias cfg_usageRefreshMinutes: usageRefreshMinutes.value

    // Plasma passes every setting and its default to each page: declaring the
    // defaults of this page's settings avoids "SimpleKCM does not have a
    // property called cfg_…Default" warnings for them.
    property int cfg_usageCapDefault
    property int cfg_usageRefreshMinutesDefault

    Kirigami.FormLayout {
        // The usage cap: stop what an account has at work at N% of a plan window
        RowLayout {
            Kirigami.FormData.label: i18n("Usage cap:")
            QQC2.CheckBox {
                id: capOn
                text: i18n("Stop an account's chats at work when a plan limit reaches")
                checked: page.cfg_usageCap > 0
                onToggled: page.cfg_usageCap = checked ? capPct.value : 0
            }
            QQC2.SpinBox {
                id: capPct
                from: 10
                to: 100
                stepSize: 5
                value: page.cfg_usageCap > 0 ? page.cfg_usageCap : 90
                enabled: capOn.checked
                onValueModified: if (capOn.checked) page.cfg_usageCap = value
            }
            QQC2.Label {
                text: i18nc("percent sign after the usage cap", "%")
            }
        }

        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: i18n("Once an account's 5-hour or weekly window reaches it, the chats of that account that are at work on this computer are stopped, once in that window (in tmux and VS Code's Claude the turn is interrupted, the chat stays open). Queued tasks wait until the window resets, and chats that keep going go on then. Chats you start or answer yourself afterwards aren't stopped again.")
        }

        QQC2.SpinBox {
            id: usageRefreshMinutes
            Kirigami.FormData.label: i18n("Fetch plan usage older than (min):")
            from: 0
            to: 60
        }

        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: i18n("VS Code's Claude Code panel runs no status line, so its chats don't bring an account's plan usage up to date. While one of the account's chats works and its numbers are this old, Claude Code fetches them, as its /usage does (no tokens, no chat saved), at most this often. 0: never.")
        }
    }
}
