import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.core as PlasmaCore
import org.kde.kirigami as Kirigami
import "icons.mjs" as Icons

// One of Claude's memories (<config>/projects/<folder>/memory), or an
// account's CLAUDE.md (type "account": your instructions for every chat on
// it): click to read it; on hover (or Tab, or a finger's hold) its
// buttons: edit, delete, hide (CLAUDE.md: edit only). In its project
// (ProjectsView.qml); an account's CLAUDE.md under the account.
ColumnLayout {
    id: memoryLine

    property var memory: ({ key: "", name: "", description: "", type: "", path: "", folder: "", folderShort: "", updatedAt: 0, folderGone: false })
    property string remoteHost: ""
    property string accountTag: ""   // (in a project on several accounts: the one it's on)
    property string project: ""   // (in a project: its folder; the line's folder says only the part below it)
    property real folderWidth: Kirigami.Units.gridUnit * 8
    readonly property real endWidth: folderWidth + Kirigami.Units.smallSpacing + root.agoWidth
    // an SSH host's opens in VS Code (Remote-SSH), to change it
    readonly property bool canOpen: !memoryLine.remoteHost || root.vscodeInstalled
    readonly property string itemKey: memory.key ? (memoryLine.remoteHost ? memoryLine.remoteHost + "|" : "") + memory.key : ""

    Layout.fillWidth: true
    Layout.rightMargin: Kirigami.Units.smallSpacing
    spacing: 0

    HoverHandler {
        id: memoryHover
    }
    TouchHold {
        buttons: memoryButtons
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing

        Kirigami.Icon {
            source: root.memoryIcon(memoryLine.memory.type)
            Layout.preferredWidth: Kirigami.Units.iconSizes.small
            Layout.preferredHeight: Layout.preferredWidth
            opacity: 0.7
        }
        PlasmaComponents3.Label {
            id: memoryName
            textFormat: Text.PlainText
            text: memoryLine.memory.description || memoryLine.memory.name
            font.underline: memoryMouse.containsMouse || activeFocus
            opacity: memoryLine.canOpen ? 1 : 0.7
            elide: Text.ElideRight
            Layout.fillWidth: true
            // (Tab: its buttons show; Enter: as a click)
            activeFocusOnTab: true
            Keys.onReturnPressed: if (memoryLine.canOpen) root.openMemory(memoryLine.memory, memoryLine.remoteHost, false)
            Keys.onEnterPressed: if (memoryLine.canOpen) root.openMemory(memoryLine.memory, memoryLine.remoteHost, false)

            PlasmaCore.ToolTipArea {
                textFormat: Text.PlainText
                width: memoryName.contentWidth
                height: parent.height
                mainText: memoryLine.memory.name
                subText: (memoryLine.memory.description ? memoryLine.memory.description + "\n\n" : "")
                         + (memoryLine.memory.type ? i18n("Kind: %1", memoryLine.memory.type) + "\n" : "")
                         + (memoryLine.memory.folder ? (memoryLine.memory.folderGone ? i18n("Folder: %1 (not there any more)", (memoryLine.remoteHost ? memoryLine.remoteHost + ":" : "") + memoryLine.memory.folder)
                                                                                     : i18n("Folder: %1", (memoryLine.remoteHost ? memoryLine.remoteHost + ":" : "") + memoryLine.memory.folder)) + "\n" : "")
                         + (memoryLine.remoteHost ? (memoryLine.canOpen ? i18n("Click to open its file on %1 in VS Code (Remote - SSH).", memoryLine.remoteHost)
                                                                     : i18n("Needs VS Code (Remote - SSH) to open a memory on %1.", memoryLine.remoteHost))
                                               : i18n("Click to read it, rendered."))

                MouseArea {
                    id: memoryMouse
                    anchors.fill: parent
                    enabled: memoryLine.canOpen
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: if (!memoryButtons.holding) root.openMemory(memoryLine.memory, memoryLine.remoteHost, false)

                    TouchHold {
                        buttons: memoryButtons
                    }
                }
            }
        }
        Loader {   // (made only where there is one: in a project on several accounts)
            active: memoryLine.accountTag !== ""
            visible: active
            sourceComponent: AccountTag {
                text: memoryLine.accountTag
            }
        }
        // its folder and how long ago, at the line's end
        CoveredEnd {
            id: memoryEnd
            covered: memoryButtons.covering
            Layout.preferredWidth: memoryLine.endWidth
            implicitHeight: memoryWhen.implicitHeight

            RowLayout {
                width: memoryEnd.width
                spacing: Kirigami.Units.smallSpacing

                PlasmaComponents3.Label {
                    id: memoryWhen
                    Layout.preferredWidth: memoryLine.folderWidth
                    horizontalAlignment: Text.AlignRight
                    textFormat: Text.PlainText
                    text: memoryLine.memory.type === "account" ? i18n("every folder")
                          : root.folderIn(memoryLine.memory.folder, memoryLine.project, memoryLine.memory.folderShort || "")
                    opacity: 0.6
                    font: Kirigami.Theme.smallFont
                    elide: Text.ElideMiddle
                }
                PlasmaComponents3.Label {
                    Layout.preferredWidth: root.agoWidth
                    horizontalAlignment: Text.AlignRight
                    textFormat: Text.PlainText
                    text: root.ago(root.now - memoryLine.memory.updatedAt)
                    opacity: 0.6
                    font: Kirigami.Theme.smallFont
                }
            }
        }
        // on hover, over the line's end
        HoverButtons {
            id: memoryButtons
            lineHeight: memoryName.implicitHeight
            shown: memoryHover.hovered || memoryName.activeFocus || memoryButtons.focused || memoryButtons.held
                   || (memoryLine.itemKey !== "" && root.deleteAsk.key === memoryLine.itemKey)
            under: memoryEnd

            RowLayout {   // (made the first time they show)
                spacing: 0

                PlasmaComponents3.ToolButton {
                    visible: !memoryLine.remoteHost   // (an SSH host's opens to change it with a click: VS Code)
                    icon.name: Icons.plasma.edit
                    display: PlasmaComponents3.AbstractButton.IconOnly
                    text: memoryLine.memory.type === "account" ? i18n("Edit your instructions") : i18n("Edit this memory")
                    Layout.preferredHeight: memoryButtons.buttonSize
                    icon.width: Kirigami.Units.iconSizes.small
                    icon.height: Kirigami.Units.iconSizes.small
                    Layout.preferredWidth: memoryButtons.buttonWidth
                    onClicked: root.openMemory(memoryLine.memory, memoryLine.remoteHost, true)

                    PlasmaCore.ToolTipArea {
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        mainText: parent.text
                        subText: memoryLine.memory.type === "account"
                                 ? i18n("Opens its CLAUDE.md in your text editor (VS Code, if the settings open plans there). Claude reads it in every new chat on this account.")
                                 : i18n("Opens its file in your text editor (VS Code, if the settings open plans there). What you change there is what Claude remembers; Claude reads it in new chats in that folder.")
                    }
                }
                PlasmaComponents3.ToolButton {
                    // to the Trash, after a question (DeleteAsk under the line); not the account's CLAUDE.md
                    visible: memoryLine.memory.type !== "account"
                    icon.name: Icons.plasma.delete
                    icon.color: Icons.color("delete", Kirigami.Theme)
                    display: PlasmaComponents3.AbstractButton.IconOnly
                    text: i18n("Delete…")
                    Layout.preferredHeight: memoryButtons.buttonSize
                    icon.width: Kirigami.Units.iconSizes.small
                    icon.height: Kirigami.Units.iconSizes.small
                    Layout.preferredWidth: memoryButtons.buttonWidth
                    onClicked: root.askDelete(memoryLine.itemKey, "memory", memoryLine.memory.key, "", memoryLine.remoteHost,
                                              memoryLine.memory.folderShort)

                    PlasmaCore.ToolTipArea {
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        mainText: i18n("Delete this memory…")
                        subText: root.deleteHint("memory")
                    }
                }
                PlasmaComponents3.ToolButton {
                    // hide it here (nothing is deleted); not the account's CLAUDE.md, which has a line of its own
                    visible: memoryLine.memory.type !== "account"
                    icon.name: Icons.plasma.hide
                    display: PlasmaComponents3.AbstractButton.IconOnly
                    text: i18n("Hide this memory")
                    Layout.preferredHeight: memoryButtons.buttonSize
                    icon.width: Kirigami.Units.iconSizes.small
                    icon.height: Kirigami.Units.iconSizes.small
                    Layout.preferredWidth: memoryButtons.buttonWidth
                    onClicked: root.hideItem("memories", memoryLine.memory.key, memoryLine.remoteHost)

                    PlasmaCore.ToolTipArea {
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        mainText: i18n("Hide this memory")
                        subText: root.hideHint("memories", memoryLine.remoteHost)
                    }
                }
            }
        }
    }

    DeleteAsk {
        Layout.fillWidth: true
        itemKey: memoryLine.itemKey
    }
}
