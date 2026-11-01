import QtQuick

// Asks before a shared chat is kept on one account only (the others lose
// it), as every question: ConfirmLine, its do-it button with the arrow of the
// Keep only on … that asked. Made only while it's asked (shown): one under
// every line made a list slow to open.
Loader {
    id: keep

    property bool shown: false

    active: shown
    visible: shown

    sourceComponent: ConfirmLine {
        text: i18n("Keep “%1” only on %2? It leaves the chat lists of %3; the conversation stays on %2. It can't be open in Claude meanwhile.",
                   root.shareConfirm.name, root.shareConfirm.account, root.shareConfirm.others)
        confirmText: i18n("Keep only on %1", root.shareConfirm.account)
        confirmIcon: "moveTo"
        onConfirmed: root.confirmKeepOnly()
        onCancelled: root.shareConfirm = root.noShareConfirm
    }
}
