import QtQuick

// A HoverButton's icon, as a button's icon group: its name (or a file), and
// a colour for what it means (icons.mjs TONES), else transparent: as drawn.
QtObject {
    property string name
    property url source
    property color color: "transparent"
}
