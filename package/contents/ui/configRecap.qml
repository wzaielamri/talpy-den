import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM
import "hub"
import "icons.mjs" as Icons

// Settings, Recap: the Monday recap, the Recap's currency, its kept history,
// and the Permissions tab's suggested rules.
KCM.SimpleKCM {
    id: page

    property alias cfg_mondayRecap: mondayRecap.checked
    property string cfg_recapCurrency
    property alias cfg_recapRules: recapRules.checked

    // Plasma passes every setting and its default to each page: declaring the
    // defaults of this page's settings avoids "SimpleKCM does not have a
    // property called cfg_…Default" warnings for them.
    property bool cfg_mondayRecapDefault
    property string cfg_recapCurrencyDefault
    property bool cfg_recapRulesDefault

    readonly property string codeDir: decodeURIComponent(Qt.resolvedUrl("../code/").toString().replace(/^file:\/\//, ""))

    // The Recap's history (week.py --history-status, --history on|off,
    // --forget): one choice for every copy of the widget and the VS Code
    // extension, kept next to their cache, so it changes at once (not with Apply)
    property var history: null        // {keep, since, deletedChats, sizeKB}
    property string historyMessage: ""
    property bool forgetAsking: false
    property bool historyOffAsking: false   // (off forgets the chats Claude deleted: asked first)

    Exec {
        id: historyHelper
        onNewData: (source, data) => {
            disconnectSource(source)
            let result = null
            try {
                result = JSON.parse(data["stdout"])
            } catch (e) {
                page.historyMessage = i18n("Couldn't ask the Recap about its history")
                return
            }
            if (result.keep !== undefined) {
                page.history = result
            } else {
                page.historyMessage = result.message || ""
                page.runHistory(["--history-status"])
            }
        }
    }

    function runHistory(args) {
        const q = s => "'" + String(s).replace(/'/g, "'\\''") + "'"
        historyHelper.connectSource("python3 -I " + q(codeDir + "week.py") + " " + args.map(q).join(" ") + " # " + Date.now())
    }

    Component.onCompleted: runHistory(["--history-status"])

    Kirigami.FormLayout {
        QQC2.CheckBox {
            id: mondayRecap
            Kirigami.FormData.label: i18n("Every week:")
            text: i18n("On Mondays, sum up the last 7 days in a notification (it opens the Recap)")
        }

        QQC2.ComboBox {
            id: recapCurrency
            // (the currencies of the European Central Bank's reference rates)
            readonly property var values: ["USD", "EUR", "GBP", "CHF", "JPY", "CNY", "INR", "CAD", "AUD", "NZD", "SEK", "NOK",
                                           "DKK", "PLN", "CZK", "HUF", "RON", "ISK", "TRY", "BRL", "MXN", "ZAR", "KRW", "SGD",
                                           "HKD", "ILS", "IDR", "MYR", "PHP", "THB"]
            Kirigami.FormData.label: i18n("Amounts in:")
            model: [i18n("US dollars (USD)"), i18n("Euros (EUR)"), i18n("Pounds sterling (GBP)"), i18n("Swiss francs (CHF)"),
                    i18n("Japanese yen (JPY)"), i18n("Chinese yuan (CNY)"), i18n("Indian rupees (INR)"),
                    i18n("Canadian dollars (CAD)"), i18n("Australian dollars (AUD)"), i18n("New Zealand dollars (NZD)"),
                    i18n("Swedish kronor (SEK)"), i18n("Norwegian kroner (NOK)"), i18n("Danish kroner (DKK)"),
                    i18n("Polish złoty (PLN)"), i18n("Czech koruny (CZK)"), i18n("Hungarian forints (HUF)"),
                    i18n("Romanian lei (RON)"), i18n("Icelandic krónur (ISK)"), i18n("Turkish lira (TRY)"),
                    i18n("Brazilian reais (BRL)"), i18n("Mexican pesos (MXN)"), i18n("South African rand (ZAR)"),
                    i18n("South Korean won (KRW)"), i18n("Singapore dollars (SGD)"), i18n("Hong Kong dollars (HKD)"),
                    i18n("Israeli shekels (ILS)"), i18n("Indonesian rupiah (IDR)"), i18n("Malaysian ringgit (MYR)"),
                    i18n("Philippine pesos (PHP)"), i18n("Thai baht (THB)")]
            currentIndex: Math.max(0, values.indexOf(page.cfg_recapCurrency))
            onActivated: page.cfg_recapCurrency = values[currentIndex]
        }

        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: i18n("Claude's API prices are in US dollars. For another currency, the Recap tab downloads the European Central Bank's reference rates of the day from ecb.europa.eu, at most every 6 hours and only while the tab is open; offline, it uses the last rates it has. Nothing about your chats is sent.")
        }

        QQC2.CheckBox {
            id: recapHistory
            Kirigami.FormData.label: i18n("History:")
            text: i18n("Keep a history beyond Claude's 30 days")
            enabled: page.history !== null
            checked: page.history ? page.history.keep : true
            onToggled: {
                if (!checked && page.history && page.history.deletedChats > 0)
                    page.historyOffAsking = true   // (the numbers of chats Claude deleted go: asked first)
                else
                    page.runHistory(["--history", checked ? "on" : "off"])
                checked = Qt.binding(() => page.history ? page.history.keep : true)   // (it shows what the Recap keeps)
            }
        }

        RowLayout {
            visible: page.historyOffAsking
            spacing: Kirigami.Units.smallSpacing

            QQC2.Label {
                Layout.maximumWidth: Kirigami.Units.gridUnit * 14
                wrapMode: Text.Wrap
                color: Kirigami.Theme.neutralTextColor   // (a question: as every one, ConfirmLine)
                text: i18np("Stop keeping the history? The Recap forgets the numbers of the %1 chat Claude has deleted, for good.",
                            "Stop keeping the history? The Recap forgets the numbers of the %1 chats Claude has deleted, for good.",
                            page.history ? page.history.deletedChats : 0)
            }
            QQC2.Button {
                icon.name: Icons.plasma.erase
                icon.color: Icons.color("erase", Kirigami.Theme)
                text: i18n("Stop Keeping It")
                onClicked: {
                    page.historyOffAsking = false
                    page.runHistory(["--history", "off"])
                }
            }
            QQC2.Button {
                text: i18n("Cancel")
                onClicked: page.historyOffAsking = false
            }
        }

        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: i18n("Claude Code deletes chats after 30 days (its cleanupPeriodDays setting). The Recap's Overall keeps their numbers past that, in ~/.cache/talpy-den: times, tokens, costs, folders and chat names. Off, it keeps only what Claude still has. This changes at once, for the VS Code extension too.")
                  + (!page.history ? "" : "\n" + (page.history.since
                         ? i18np("Kept since %2, with %1 chat Claude has deleted · %3 KB", "Kept since %2, with %1 chats Claude has deleted · %3 KB",
                                 page.history.deletedChats, Qt.locale().toString(new Date(page.history.since + "T00:00"), "d MMM yyyy"),
                                 page.history.sizeKB)
                         : i18n("Nothing kept yet.")))
        }

        RowLayout {
            spacing: Kirigami.Units.smallSpacing

            QQC2.Button {
                visible: !page.forgetAsking
                enabled: page.history !== null && !!page.history.since
                icon.name: Icons.plasma.erase
                icon.color: Icons.color("erase", Kirigami.Theme)
                text: i18n("Delete Saved History…")
                onClicked: page.forgetAsking = true
            }
            QQC2.Label {
                visible: page.forgetAsking
                Layout.maximumWidth: Kirigami.Units.gridUnit * 14
                wrapMode: Text.Wrap
                color: Kirigami.Theme.neutralTextColor   // (a question: as every one, ConfirmLine)
                text: i18n("Delete the Recap's saved history? It starts again from the chats Claude still has.")
            }
            QQC2.Button {
                visible: page.forgetAsking
                icon.name: Icons.plasma.erase
                icon.color: Icons.color("erase", Kirigami.Theme)
                text: i18n("Delete")
                onClicked: {
                    page.forgetAsking = false
                    page.runHistory(["--forget"])
                }
            }
            QQC2.Button {
                visible: page.forgetAsking
                text: i18n("Cancel")
                onClicked: page.forgetAsking = false
            }
        }

        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            visible: page.historyMessage !== ""
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            text: page.historyMessage
        }

        QQC2.CheckBox {
            id: recapRules
            Kirigami.FormData.label: i18n("Suggested rules:")
            text: i18n("Suggest rules for the permission prompts you answered")
        }

        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 20
            wrapMode: Text.Wrap
            font: Kirigami.Theme.smallFont
            opacity: 0.7
            text: i18n("The Permissions tab offers rules that would have let those prompts go without asking, each with an Allow… button. Off, it only counts the prompts, and there's nothing to allow by mistake. Either way it lists the permissions you gave, to revoke them.")
        }
    }
}
