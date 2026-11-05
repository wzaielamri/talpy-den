import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.extras as PlasmaExtras
import org.kde.kirigami as Kirigami
import "icons.mjs" as Icons

PlasmaExtras.Representation {
    id: full

    // (no narrower than the header's tabs and buttons, which went off its right edge)
    Layout.minimumWidth: Math.max(Kirigami.Units.gridUnit * 22, header.implicitWidth)
    Layout.minimumHeight: Kirigami.Units.gridUnit * 14
    Layout.preferredWidth: Kirigami.Units.gridUnit * 28
    Layout.preferredHeight: Kirigami.Units.gridUnit * 30

    collapseMarginsHint: true

    // The tabs, in the order they stand: your chats now, then the rest of your
    // work by project, the permissions you gave, and the Recap of your days
    readonly property var tabOrder: ["chats", "projects", "perms", "week"]

    header: PlasmaExtras.PlasmoidHeading {
        RowLayout {
            anchors.fill: parent
            spacing: Kirigami.Units.smallSpacing

            // In the system tray, the tray's own heading names the widget
            TalpyIcon {
                id: headerIcon
                visible: !root.inTray
                Layout.preferredWidth: Kirigami.Units.iconSizes.small
                Layout.preferredHeight: Kirigami.Units.iconSizes.small
                color: root.stateColor(root.overall)
                mode: root.overall
                moving: root.dashboardShown && !root.coveredByWindow && !root.underWindows(headerIcon)
            }
            // The app's name is the first tab: your chats now. The others: your
            // projects (ProjectsView.qml), the permissions you gave
            // (PermsView.qml), your last 7 days with Claude (WeekView.qml)
            PlasmaComponents3.TabBar {
                id: tabs
                // (squeezed, it shares out what's left, and "Recap" broke onto two lines)
                Layout.minimumWidth: implicitWidth
                // (set by a click, not by the bar's own index: a new popup
                // starts at its first tab, which mustn't undo the one shown)
                currentIndex: full.tabOrder.indexOf(root.popupTab)

                PlasmaComponents3.TabButton {
                    width: implicitWidth   // (else the bar gives each the same share)
                    text: i18n("Talpy Den")
                    onClicked: root.popupTab = "chats"
                }
                PlasmaComponents3.TabButton {
                    width: implicitWidth
                    text: i18n("Projects")
                    onClicked: root.popupTab = "projects"
                }
                PlasmaComponents3.TabButton {
                    width: implicitWidth
                    text: i18n("Permissions")
                    onClicked: root.popupTab = "perms"
                }
                PlasmaComponents3.TabButton {
                    width: implicitWidth
                    text: i18n("Recap")
                    onClicked: root.popupTab = "week"
                }
                Connections {
                    target: root
                    function onPopupTabChanged() {
                        tabs.currentIndex = full.tabOrder.indexOf(root.popupTab)
                    }
                }
            }
            PlasmaComponents3.Label {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                Layout.preferredWidth: 0   // (what's left: it elides rather than widen the popup)
                horizontalAlignment: Text.AlignRight
                text: hero.visible ? "" : root.summaryText()   // the big Talpy's headline says it
                opacity: 0.8
                elide: Text.ElideRight
            }
            PlasmaComponents3.ToolButton {
                visible: root.popupTab === "chats"
                icon.name: Icons.plasma.focus
                checkable: true
                checked: root.focusView
                display: PlasmaComponents3.AbstractButton.IconOnly
                text: i18n("Focus")
                onClicked: root.setFocusView(!root.focusView)

                PlasmaCore.ToolTipArea {
                    textFormat: Text.PlainText
                    anchors.fill: parent
                    mainText: root.focusView ? i18n("Show everything") : i18n("Focus")
                    subText: root.focusView ? i18n("Back to every account, chat, pet and usage bar.")
                                            : i18n("Only what needs you, the chats that finished a turn you haven't looked at yet, and one line for each chat at work.")
                }
            }
            PlasmaComponents3.ToolButton {
                visible: root.popupTab === "chats"
                icon.name: Icons.plasma.search
                checkable: true
                checked: root.searchOpen
                display: PlasmaComponents3.AbstractButton.IconOnly
                text: i18n("Find a chat")
                onClicked: root.toggleSearch()

                PlasmaCore.ToolTipArea {
                    textFormat: Text.PlainText
                    anchors.fill: parent
                    mainText: i18n("Find a chat")
                    subText: i18n("Every chat of your accounts (and of the SSH hosts shown) with all the words you type in its name, its folder or your prompts.")
                }
            }
            PlasmaComponents3.ToolButton {
                id: hostsButton
                icon.name: Icons.plasma.host
                text: root.shownHosts.length > 0 ? String(root.shownHosts.length) : ""
                display: root.shownHosts.length > 0 ? PlasmaComponents3.AbstractButton.TextBesideIcon
                                                    : PlasmaComponents3.AbstractButton.IconOnly
                Accessible.name: root.showContainers ? i18n("SSH hosts and containers") : i18n("SSH hosts")   // (its text is only the count)
                onClicked: root.openHostsMenu(hostsButton)

                PlasmaCore.ToolTipArea {
                    textFormat: Text.PlainText
                    anchors.fill: parent
                    mainText: root.showContainers ? i18n("Show Claude on SSH hosts and in containers") : i18n("Show Claude on SSH hosts")
                    subText: root.shownHosts.length > 0
                             ? (root.showContainers ? i18n("Showing Claude on %1. Click to pick hosts from ~/.ssh/config and containers.", root.shownHosts.map(h => root.hostLabel(h)).join(", "))
                                                    : i18n("Showing Claude on %1. Click to pick hosts from ~/.ssh/config.", root.shownHosts.join(", ")))
                             : root.showContainers ? i18n("Show the Claude chats of your SSH hosts (from ~/.ssh/config) and of your Docker, Podman or nerdctl containers here too.")
                             : i18n("Show the Claude chats of your SSH hosts (from ~/.ssh/config) here too.")
                }
            }
            PlasmaComponents3.ToolButton {
                icon.name: Icons.plasma.refresh
                display: PlasmaComponents3.AbstractButton.IconOnly
                text: i18n("Refresh")
                onClicked: {
                    root.refresh()
                    root.fetchUsage()   // (the plan usage too, when it's over a minute old)
                    for (const host of root.shownHosts)
                        root.pollHost(host)
                    root.loadWeek()   // (on the Recap tab)
                    root.loadPerms()  // (on the Permissions tab)
                    if (root.popupTab === "projects")
                        root.loadProjects()
                }

                PlasmaCore.ToolTipArea {
                    textFormat: Text.PlainText
                    anchors.fill: parent
                    mainText: i18n("Refresh")
                }
            }
            // (in the system tray, the tray's own heading has the settings button)
            PlasmaComponents3.ToolButton {
                visible: !root.inTray
                icon.source: root.iconDir + "settings-symbolic.svg"   // (a gear, as in GNOME and VS Code)
                display: PlasmaComponents3.AbstractButton.IconOnly
                text: i18n("Settings")
                onClicked: Plasmoid.internalAction("configure").trigger()

                PlasmaCore.ToolTipArea {
                    textFormat: Text.PlainText
                    anchors.fill: parent
                    mainText: i18n("Settings")
                }
            }
        }
    }

    // What's past its edges isn't drawn: Representation gives the content
    // negative padding out to the frame's inner edge (collapseMarginsHint), so
    // this is where the popup ends; a tab sliding in comes from there (it was
    // drawn over the desktop beside the popup on its way, and clipping the
    // popup itself cut the sections, which reach out to the frame)
    contentItem: Item {
        clip: true
        implicitWidth: tabContent.implicitWidth
        implicitHeight: tabContent.implicitHeight

        ColumnLayout {
            id: tabContent
            anchors.fill: parent
            spacing: Kirigami.Units.smallSpacing
            // A tab slides in from the side it's on (Talpy Den | Projects | Permissions | Recap), as in VS Code
            transform: Translate { id: tabSlide }
            property int tabIndex: full.tabOrder.indexOf(root.popupTab)
            onTabIndexChanged: {
                if (!root.animateRows)
                    return
                const from = tabIndex > shownTab ? 1 : -1
                shownTab = tabIndex
                tabSlideIn.stop()
                tabSlide.x = from * Kirigami.Units.gridUnit * 1.5
                tabContent.opacity = 0.35
                tabSlideIn.start()
            }
            property int shownTab: tabIndex
            ParallelAnimation {
                id: tabSlideIn
                NumberAnimation { target: tabSlide; property: "x"; to: 0; duration: Kirigami.Units.longDuration; easing.type: Easing.OutQuint }
                NumberAnimation { target: tabContent; property: "opacity"; to: 1; duration: Kirigami.Units.longDuration; easing.type: Easing.OutQuint }
                onStopped: { tabSlide.x = 0; tabContent.opacity = 1 }
            }

            // The big Talpy: the whole dashboard at a glance (stays put while the list scrolls)
            PetStrip {
                id: hero
                hero: true
                visible: Plasmoid.configuration.showPet && root.popupTab === "chats"
                Layout.fillWidth: true
                Layout.preferredHeight: implicitHeight
                Layout.topMargin: Kirigami.Units.smallSpacing
                Layout.leftMargin: Kirigami.Units.smallSpacing
                Layout.rightMargin: Kirigami.Units.smallSpacing
            }

            // Find a chat (the magnifier above): its words, then what matched
            PlasmaExtras.SearchField {
                id: searchField
                visible: root.searchOpen && root.popupTab === "chats"
                Layout.fillWidth: true
                Layout.leftMargin: Kirigami.Units.smallSpacing
                Layout.rightMargin: Kirigami.Units.smallSpacing
                placeholderText: i18n("Find a chat: words in its name, folder or your prompts")
                onTextChanged: root.searchQuery = text
                onVisibleChanged: {
                    if (visible) {
                        text = root.searchQuery
                        forceActiveFocus()
                    }
                }
                Keys.onEscapePressed: root.toggleSearch()

                Connections {   // (cleared when the search closes)
                    target: root
                    function onSearchQueryChanged() {
                        if (searchField.text !== root.searchQuery)
                            searchField.text = root.searchQuery
                    }
                }
            }

            // (made only while their tab is open)
            Loader {
                active: root.popupTab === "week"
                visible: active
                Layout.fillWidth: true
                Layout.fillHeight: true
                source: "WeekView.qml"
            }
            // (kept once made while the popup lives: back to the Chats tab, taking it away cost seconds)
            Loader {
                property bool made: false
                active: root.popupTab === "projects" || made
                visible: root.popupTab === "projects"
                onLoaded: made = true
                Layout.fillWidth: true
                Layout.fillHeight: true
                source: "ProjectsView.qml"
            }
            Loader {
                active: root.popupTab === "perms"
                visible: active
                Layout.fillWidth: true
                Layout.fillHeight: true
                source: "PermsView.qml"
            }

            PlasmaComponents3.ScrollView {
                id: scroll
                visible: root.popupTab === "chats"
                // Fixed implicit size: deriving it from the content would loop
                // through the popup's width.
                implicitWidth: Kirigami.Units.gridUnit * 28
                implicitHeight: Kirigami.Units.gridUnit * 26
                Layout.fillWidth: true
                Layout.fillHeight: true
                contentWidth: availableWidth
                contentHeight: content.implicitHeight
                PlasmaComponents3.ScrollBar.horizontal.policy: PlasmaComponents3.ScrollBar.AlwaysOff

                ColumnLayout {
                    id: content
                    width: scroll.availableWidth
                    spacing: Kirigami.Units.largeSpacing
                    Component.onCompleted: root.rowSpace = content

                    PlasmaComponents3.Label {
                        textFormat: Text.PlainText
                        Layout.fillWidth: true
                        Layout.margins: Kirigami.Units.smallSpacing
                        visible: root.actionError !== ""
                        text: root.actionError
                        color: Kirigami.Theme.negativeTextColor
                        wrapMode: Text.Wrap
                    }

                    PlasmaComponents3.Label {
                        textFormat: Text.PlainText
                        Layout.fillWidth: true
                        Layout.margins: Kirigami.Units.smallSpacing
                        visible: root.actionInfo !== ""
                        text: root.actionInfo
                        color: Kirigami.Theme.positiveTextColor
                        wrapMode: Text.Wrap
                    }

                    // What happened while you were away (main.qml: sendDigest), until you've seen it
                    Kirigami.InlineMessage {
                        Layout.fillWidth: true
                        Layout.margins: Kirigami.Units.smallSpacing
                        visible: root.awayDigest !== null
                        type: Kirigami.MessageType.Information
                        icon.name: Icons.plasma.away
                        text: root.awayDigest ? "<b>" + root.escapeHtml(root.awayDigest.title) + "</b><br>"
                                                + root.awayDigest.lines.map(root.escapeHtml).join("<br>") : ""
                        actions: [
                            Kirigami.Action {
                                text: i18n("Dismiss")
                                icon.name: Icons.plasma.close
                                onTriggered: root.awayDigest = null
                            }
                        ]
                    }

                    // (made the first time you search, then kept)
                    Loader {
                        readonly property bool shown: root.searchOpen && root.searchQuery.trim().length >= 2
                        property bool made: false
                        active: shown || made
                        visible: shown
                        onLoaded: made = true
                        Layout.fillWidth: true
                        sourceComponent: SearchResults {}
                    }

                    PlasmaComponents3.Label {
                        textFormat: Text.PlainText
                        Layout.fillWidth: true
                        Layout.margins: Kirigami.Units.smallSpacing
                        visible: root.errorText !== ""
                        text: root.errorText
                        color: Kirigami.Theme.negativeTextColor
                        wrapMode: Text.Wrap
                    }

                    // Only what needs you and what works (the header's filter button)
                    // (made the first time it's on, then kept)
                    Loader {
                        property bool made: false
                        active: root.focusView || made
                        visible: root.focusView && !(root.searchOpen && root.searchQuery.trim().length >= 2)
                        onLoaded: made = true
                        Layout.fillWidth: true
                        sourceComponent: FocusView {}
                    }

                    // Indexed by position so rows survive each poll (a new array every
                    // 2 s would rebuild them and drop their state).
                    Repeater {
                        model: root.groups.length
                        delegate: GroupSection {
                            required property int index
                            visible: !root.focusView   // (kept, with their pets and what's open, while the focus view shows)
                            Layout.fillWidth: true
                            group: root.groups[index] || root.emptyGroup
                            accounts: root.groups.length
                            last: index === root.groups.length - 1
                        }
                    }

                    // Kept chats and queued tasks of hosts and containers that aren't
                    // shown: they go on all the same (UnseenLine.qml)
                    Repeater {
                        model: root.focusView ? 0 : root.unseenHostItems.length
                        delegate: UnseenLine {
                            required property int index
                            Layout.fillWidth: true
                            item: root.unseenHostItems[index] || null
                        }
                    }

                    // No account here, but SSH hosts shown: one quiet line where this
                    // computer's accounts go (a computer that only watches its hosts is fine)
                    PlasmaComponents3.Label {
                        textFormat: Text.PlainText
                        Layout.fillWidth: true
                        Layout.margins: Kirigami.Units.smallSpacing
                        visible: root.status !== null && root.groups.length === 0 && root.shownHosts.length > 0 && !root.focusView
                        text: i18n("No Claude Code config on this computer")
                        opacity: 0.6
                        elide: Text.ElideRight
                    }

                    // SSH hosts you picked, after this computer's accounts
                    Repeater {
                        model: root.shownHosts.length
                        delegate: HostSection {
                            required property int index
                            visible: !root.focusView
                            Layout.fillWidth: true
                            host: root.shownHosts[index] || ""
                        }
                    }

                    PlasmaExtras.PlaceholderMessage {
                        Layout.fillWidth: true
                        Layout.margins: Kirigami.Units.gridUnit
                        visible: root.status !== null && root.groups.length === 0 && root.shownHosts.length === 0
                        iconName: Icons.plasma.chats   // (the tab's, as the Projects and Recap tabs' have theirs)
                        text: i18n("No Claude Code chats yet")
                        explanation: i18n("Your Claude Code chats show up here once you start claude in a terminal or open Claude in VS Code. Talpy Den looks in ~/.claude and ~/.claude-*; other folders go in its settings (Extra config dirs).")
                    }

                    // (some room under the last line, scrolled to the end too)
                    Item {
                        implicitHeight: Kirigami.Units.smallSpacing
                    }
                }
            }
        }
    }

    // While a game with the big Talpy is on, a click outside his stage ends it
    // (and still does what it does)
    Loader {
        parent: full
        anchors.fill: parent
        z: 999
        active: root.gameStage !== null
        sourceComponent: MouseArea {
            acceptedButtons: Qt.AllButtons
            onPressed: mouse => {
                const stage = root.gameStage
                const p = stage ? mapToItem(stage, mouse.x, mouse.y) : null
                if (!p || p.x < 0 || p.y < 0 || p.x >= stage.width || p.y >= stage.height)
                    root.gameStopWanted = true
                mouse.accepted = false
            }
        }
    }

    // On the desktop, a right-click anywhere on it opens the widget's menu, as
    // on the panel icon (MenuCatcher.qml); over the whole page, its heading too
    Loader {
        parent: full
        anchors.fill: parent
        z: 1000
        active: root.onDesktop
        sourceComponent: MenuCatcher {
            covers: full
            onMenu: at => root.openWidgetMenu(this, at.x, at.y)
        }
    }

    // While a plan's Move question shows (MoveAsk.qml), a press anywhere else
    // only lets it be (nothing moves); on the question itself it goes through
    // to its buttons, and its list of projects (a popup) is above this. The
    // wheel still scrolls.
    Loader {
        parent: full
        anchors.fill: parent
        z: 1001
        active: root.moveAsk.key !== ""
        sourceComponent: MouseArea {
            acceptedButtons: Qt.AllButtons
            onPressed: mouse => {
                const box = root.moveAskItem
                const p = box ? mapToItem(box, mouse.x, mouse.y) : null
                if (p && p.x >= 0 && p.y >= 0 && p.x < box.width && p.y < box.height) {
                    mouse.accepted = false
                    return
                }
                Qt.callLater(root.cancelMove)   // (not from inside this press: the question's going takes this away)
            }
        }
    }
}
