import QtQuick
import "find.mjs" as Find

// Where a long text in Talpy Chat folds (find.mjs foldOf: VS Code's the same), for ChatPane.qml's
// foldText: a file of its own, read only once a text may be long, so a window opens as quickly
QtObject {
    function foldOf(text, how) {
        return Find.foldOf(text, how)
    }
}
