import QtQuick

// Follows the beat (Beat.qml) while active: the beat ticks while anything
// follows it, and stops when nothing does (gone with what it's in, too).
QtObject {
    property bool active: false
    property bool counted: false       // (counted among Beat's followers)

    onActiveChanged: follow()
    Component.onCompleted: follow()
    Component.onDestruction: if (counted) Beat.followers--

    function follow() {
        if (active === counted)
            return
        counted = active
        Beat.followers += active ? 1 : -1
    }
}
