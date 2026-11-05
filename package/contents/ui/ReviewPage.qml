import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami
import "icons.mjs" as Icons

// Talpy Chat's Review tab: the files the chat changed since it started, each with its change
// (DiffView), Undo (asked first), Commit these files… and Reviewed. ChatPane.qml's Loader makes it
// the first time the tab shows (a window opens as quickly), then keeps it; what it shows and does
// is ChatPane's (review, openFiles, undo, commitMessage…). VS Code chat.tsx: the same words
ColumnLayout {
    spacing: Kirigami.Units.smallSpacing

    PlasmaComponents3.ScrollView {
        Layout.fillWidth: true
        Layout.fillHeight: true
        contentWidth: availableWidth
        PlasmaComponents3.ScrollBar.horizontal.policy: PlasmaComponents3.ScrollBar.AlwaysOff

        ColumnLayout {
            width: parent.width
            spacing: Kirigami.Units.smallSpacing

            PlasmaComponents3.Label {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                visible: pane.review === null
                text: pane.reviewLoading ? i18n("Comparing its files with how they were before the chat…")
                                         : pane.reviewError || i18n("Nothing to review yet")
                color: pane.reviewError ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.textColor
                font.pointSize: pane.pt
                opacity: 0.7
                wrapMode: Text.Wrap
            }
            PlasmaComponents3.Label {
                textFormat: Text.PlainText
                Layout.fillWidth: true
                visible: pane.review !== null && pane.review.files.length === 0
                text: i18n("No changed files: they're as they were before this chat.")
                font.pointSize: pane.pt
                opacity: 0.7
                wrapMode: Text.Wrap
            }

            // the files, +/- lines, their diffs
            RowLayout {
                visible: pane.review !== null && pane.review.files.length > 0
                Layout.fillWidth: true

                PlasmaComponents3.Label {
                    textFormat: Text.PlainText
                    Layout.fillWidth: true
                    readonly property var sums: pane.totals(pane.review ? pane.review.files : [])
                    text: pane.review ? i18np("%1 file changed since the chat started", "%1 files changed since the chat started",
                                             pane.review.files.length) + "  +" + sums[0] + " −" + sums[1] : ""
                    font.bold: true
                    font.pointSize: pane.pt
                }
                TestsBadge {
                    review: pane.row ? pane.row.review : (pane.review ? { tests: pane.review.tests } : null)
                }
                PlasmaComponents3.ToolButton {
                    icon.name: Icons.plasma.sideBySide
                    checkable: true
                    checked: Plasmoid.configuration.diffSideBySide
                    display: PlasmaComponents3.AbstractButton.IconOnly
                    text: i18n("Side by side")
                    onToggled: Plasmoid.configuration.diffSideBySide = checked

                    TipArea {
                        textFormat: Text.PlainText
                        anchors.fill: parent
                        mainText: i18n("Side by side")
                        subText: i18n("Each change as before | after, where the window is wide enough; else removed and added lines one after the other.")
                    }
                }
            }
            Repeater {
                model: pane.review ? pane.review.files.length : 0
                delegate: ColumnLayout {
                    id: fileItem
                    required property int index
                    readonly property var file: pane.review && pane.review.files[index] ? pane.review.files[index] : ({ label: "", path: "", diff: [] })
                    readonly property bool unfolded: pane.openFiles[file.path] === true
                    Layout.fillWidth: true
                    spacing: 0

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.smallSpacing

                        Kirigami.Icon {
                            source: fileItem.unfolded ? Icons.plasma.unfolded : Icons.plasma.folded
                            Layout.preferredWidth: Kirigami.Units.iconSizes.small
                            Layout.preferredHeight: Layout.preferredWidth
                            opacity: 0.6
                        }
                        PlasmaComponents3.Label {
                            textFormat: Text.PlainText
                            Layout.fillWidth: true
                            text: fileItem.file.label + (fileItem.file.created ? "  " + i18nc("a file the chat made", "(new)") : "")
                                  + (fileItem.file.deleted ? "  " + i18nc("a file the chat removed", "(removed)") : "")
                            elide: Text.ElideMiddle
                            font.family: pane.monoFamily
                            font.pointSize: pane.pt

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    const next = Object.assign({}, pane.openFiles)
                                    next[fileItem.file.path] = !fileItem.unfolded
                                    pane.openFiles = next
                                }
                            }
                        }
                        PlasmaComponents3.Label {
                            textFormat: Text.PlainText
                            visible: fileItem.file.added !== null && fileItem.file.added !== undefined
                            text: "+" + fileItem.file.added
                            color: Kirigami.Theme.positiveTextColor
                            font.family: pane.monoFamily
                            font.pointSize: pane.pt
                        }
                        PlasmaComponents3.Label {
                            textFormat: Text.PlainText
                            visible: fileItem.file.removed !== null && fileItem.file.removed !== undefined
                            text: "−" + fileItem.file.removed
                            color: Kirigami.Theme.negativeTextColor
                            font.family: pane.monoFamily
                            font.pointSize: pane.pt
                        }
                        PlasmaComponents3.Label {
                            textFormat: Text.PlainText
                            visible: !!fileItem.file.binary || !!fileItem.file.unknown
                            text: fileItem.file.binary ? i18n("binary") : i18n("no earlier version kept")
                            opacity: 0.6
                            font.pointSize: pane.pt * 0.85
                        }
                        PlasmaComponents3.ToolButton {
                            visible: !fileItem.file.unknown
                            icon.name: Icons.plasma.undo
                            display: PlasmaComponents3.AbstractButton.IconOnly
                            text: i18n("Undo this file")
                            onClicked: pane.undoAsk = fileItem.file.path

                            TipArea {
                                textFormat: Text.PlainText
                                anchors.fill: parent
                                mainText: i18n("Undo this file")
                                subText: i18n("Asks first. Puts it back as it was before this chat.")
                            }
                        }
                    }
                    ConfirmLine {
                        visible: pane.undoAsk === fileItem.file.path
                        Layout.fillWidth: true
                        text: fileItem.file.created ? i18n("Delete %1 for good? The chat made it; what you changed in it since is lost too.", fileItem.file.label)
                                                    : i18n("Put %1 back as it was before this chat? Later changes to it are lost too.", fileItem.file.label)
                        confirmText: i18n("Undo")
                        confirmIcon: "undo"
                        onConfirmed: pane.undo(fileItem.file.path)
                        onCancelled: pane.undoAsk = ""
                    }
                    PlasmaComponents3.Label {
                        visible: fileItem.unfolded && !!fileItem.file.unknown && !!fileItem.file.now && fileItem.file.now.length > 0
                        Layout.fillWidth: true
                        Layout.leftMargin: Kirigami.Units.gridUnit
                        textFormat: Text.PlainText
                        text: i18n("No earlier version was kept, so this is how it is now:")
                        font.pointSize: pane.pt * 0.85
                        opacity: 0.7
                        wrapMode: Text.Wrap
                    }
                    Loader {
                        active: fileItem.unfolded && ((fileItem.file.diff || []).length > 0 || (fileItem.file.now || []).length > 0)
                        visible: active
                        Layout.fillWidth: true
                        Layout.leftMargin: Kirigami.Units.gridUnit
                        sourceComponent: DiffView {
                            lines: fileItem.file.diff || []
                            now: fileItem.file.unknown ? fileItem.file.now || [] : []
                            path: fileItem.file.path
                            pt: pane.pt
                            mono: pane.monoFamily
                            base: pane.mdStyle.blockBg
                        }
                    }
                }
            }
        }
    }
    // Commit only these files, with a message from its name and recap
    // (over the buttons that open them, not at the end of a long list, out of sight)
    ColumnLayout {
        visible: pane.commitOpen && pane.review !== null
        Layout.fillWidth: true

        PlasmaComponents3.Label {
            textFormat: Text.PlainText
            Layout.fillWidth: true
            text: pane.review && pane.review.repos.length
                  ? i18n("Commit only these files in %1 (yours that aren't this chat's stay as they are):", pane.review.repos.join(", "))
                  : i18n("None of these files is in a git repository.")
            wrapMode: Text.Wrap
            font.pointSize: pane.pt
        }
        PlasmaComponents3.TextArea {
            id: commitText
            Layout.fillWidth: true
            Layout.preferredHeight: Kirigami.Units.gridUnit * 6
            wrapMode: TextEdit.Wrap
            font.family: pane.monoFamily
            font.pointSize: pane.pt
            text: pane.commitMessage
            onTextChanged: if (activeFocus) {
                pane.commitEdited = true
                pane.commitMessage = text
            }
        }
        RowLayout {
            Item {
                Layout.fillWidth: true
            }
            PlasmaComponents3.Button {
                text: i18n("Cancel")
                onClicked: pane.commitOpen = false
            }
            PlasmaComponents3.Button {
                enabled: commitText.text.trim() !== "" && pane.reviewIsThis && pane.review.repos.length > 0
                icon.name: Icons.plasma.commit
                text: i18n("Commit")
                onClicked: pane.run("commit", "--commit " + root.shellQuote(pane.chatId) + " --message "
                                    + root.shellQuote(commitText.text) + pane.paneArgs())
            }
        }
    }
    ConfirmLine {
        visible: pane.undoAsk === "*"
        Layout.fillWidth: true
        text: i18n("Put all of them back as they were before this chat? Files it made are deleted for good; later changes to them are lost too.")
        confirmText: i18n("Undo all")
        confirmIcon: "undo"
        onConfirmed: pane.undo("*")
        onCancelled: pane.undoAsk = ""
    }
    RowLayout {
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing

        PlasmaComponents3.ToolButton {
            icon.name: Icons.plasma.refresh
            display: PlasmaComponents3.AbstractButton.IconOnly
            text: i18n("Compare again")
            onClicked: pane.loadReview()
        }
        Item {
            Layout.fillWidth: true
        }
        PlasmaComponents3.Button {
            enabled: pane.reviewIsThis && pane.review.files.length > 0
            icon.name: Icons.plasma.undo
            text: i18n("Undo all…")
            onClicked: pane.undoAsk = "*"
        }
        PlasmaComponents3.Button {
            enabled: pane.reviewIsThis && pane.review.files.length > 0 && pane.review.repos.length > 0
            icon.name: Icons.plasma.commit
            text: i18n("Commit these files…")
            onClicked: pane.commitOpen = !pane.commitOpen
        }
        PlasmaComponents3.Button {
            // (by the mark itself: while the chat works it isn't "to review", nor reviewed)
            readonly property bool marked: !!pane.row && !!pane.row.review && root.reviewSeen(pane.row, pane.host)
            icon.name: marked ? Icons.plasma.reviewed : Icons.plasma.markReviewed
            icon.color: marked ? Icons.color("reviewed", Kirigami.Theme) : "transparent"
            text: marked ? i18n("Reviewed") : i18n("Mark reviewed")
            checkable: false
            onClicked: pane.run("reviewed", "--reviewed " + root.shellQuote(pane.chatId) + (marked ? " --off" : "")
                                + (pane.host ? " --host " + root.shellQuote(pane.host) : "") + root.configDirArgs)

            TipArea {
                textFormat: Text.PlainText
                anchors.fill: parent
                mainText: parent.marked ? i18n("Reviewed") : i18n("Mark reviewed")
                subText: parent.marked ? i18n("Click to mark it not reviewed.")
                                       : i18n("Its row stops saying \"to review\", until it changes files again.")
            }
        }
    }
}
