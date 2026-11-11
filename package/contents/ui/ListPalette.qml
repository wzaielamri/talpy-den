import QtQuick
import org.kde.kirigami as Kirigami

// The colors and fonts of a list's rows, read from the theme once where
// the list is (an account's section, the Projects tab…) and handed to its
// rows (their colors), which draw with plain Text and Rectangles from it.
// Every item that reads the theme itself (a PlasmaComponents3.Label, a
// Kirigami.Icon, a Rectangle colored from Kirigami.Theme) gets a theme of
// its own, which costs milliseconds to make and to take out of a popup that
// holds thousands of them: a long list's rows made the popup freeze for
// seconds. It takes no room (it isn't shown: a layout leaves it out).
Item {
    id: listPalette

    visible: false
    width: 0
    height: 0

    // The theme is the list's (its parent's), not its own: Plasma fills in an
    // item's colors only while the item shows, and this one never does, so
    // its own stayed as they start, black: the rows' text couldn't be read
    // in a dark panel's popup (a desktop with light apps and a dark Plasma
    // style; with light ones black looked right).
    readonly property Item themed: parent
    // (the theme's names: a part that takes either this or Kirigami.Theme reads them the same way)
    readonly property color textColor: themed ? themed.Kirigami.Theme.textColor : Kirigami.Theme.textColor
    readonly property color linkColor: themed ? themed.Kirigami.Theme.linkColor : Kirigami.Theme.linkColor
    readonly property color disabledTextColor: themed ? themed.Kirigami.Theme.disabledTextColor : Kirigami.Theme.disabledTextColor
    readonly property color negativeTextColor: themed ? themed.Kirigami.Theme.negativeTextColor : Kirigami.Theme.negativeTextColor
    readonly property color neutralTextColor: themed ? themed.Kirigami.Theme.neutralTextColor : Kirigami.Theme.neutralTextColor
    readonly property color positiveTextColor: themed ? themed.Kirigami.Theme.positiveTextColor : Kirigami.Theme.positiveTextColor
    readonly property color focusColor: themed ? themed.Kirigami.Theme.focusColor : Kirigami.Theme.focusColor
    // tints of the text's color: a bar's groove, a tag's frame, a line's hover shade, the peek's ground, a toggle that's on
    readonly property color groove: Qt.rgba(textColor.r, textColor.g, textColor.b, 0.15)
    readonly property color frame: Qt.rgba(textColor.r, textColor.g, textColor.b, 0.3)
    readonly property color shade: Qt.rgba(textColor.r, textColor.g, textColor.b, 0.06)
    readonly property color ground: Qt.rgba(textColor.r, textColor.g, textColor.b, 0.05)
    readonly property color tint: Qt.rgba(textColor.r, textColor.g, textColor.b, 0.08)
    readonly property font smallFont: themed ? themed.Kirigami.Theme.smallFont : Kirigami.Theme.smallFont
    // the smallest text with the weight of who said it in a chat's peek (SessionRow), and its widest word
    readonly property real whoWidth: Math.ceil(Math.max(whoFm.advanceWidth(i18nc("Claude's recap of the chat", "Recap")),
                                                        whoFm.advanceWidth(i18nc("your last prompt", "You")),
                                                        whoFm.advanceWidth(i18nc("Claude's last reply", "Claude"))))
    // "ctx 100%": the context's numbers are as wide, so every row's bar ends at one place
    readonly property real ctxWidth: Math.max(ctxFm.advanceWidth(i18nc("context window fill", "ctx %1%", 100)),
                                              ctxFm.advanceWidth(i18nc("context used toward where Claude compacts the chat", "%1% used", 100)))

    FontMetrics {
        id: whoFm
        font.pointSize: listPalette.smallFont.pointSize
        font.weight: Font.DemiBold
    }
    FontMetrics {
        id: ctxFm
        font: listPalette.smallFont
    }
}
