import QtQuick

// A line of text in a list's row, drawn as a PlasmaComponents3.Label draws
// it, with the row's colors (a ListPalette) instead of a theme of its own:
// a Label costs milliseconds to make and to take out of a popup that holds a
// long list, a Text a tenth of one.
Text {
    property var colors: null   // the row's ListPalette (an Item's own palette is Qt's)

    color: colors ? colors.textColor : "black"
    linkColor: colors ? colors.linkColor : "blue"
    textFormat: Text.PlainText
    opacity: enabled ? 1 : 0.75   // (as a Label's)

    Accessible.role: Accessible.StaticText
    Accessible.name: text
}
