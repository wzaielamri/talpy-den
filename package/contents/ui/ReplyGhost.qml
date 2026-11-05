import QtQuick
import org.kde.plasma.components as PlasmaComponents3

// What you type in Talpy Chat's reply box, completed in grey from your usual
// replies, right after it (ChatPane.qml, a Loader in the box at the end of its
// text: read and made only while one can be; Tab or → there takes it). The
// same rule as VS Code's (shared/pane.ts completionOf): the rest of the first
// of your usual replies (those after a turn that ended as this one did first)
// that starts with what you typed; none for a command or several lines.
PlasmaComponents3.Label {
    readonly property string rest: {
        const text = replyBox.text, yours = pane.usual, ended = pane.turnEnded
        if (!yours || text.trim() === "" || text.indexOf("\n") >= 0 || /^[\/!]/.test(text))
            return ""
        const low = text.toLowerCase()
        for (const r of ((ended && yours.chips && yours.chips[ended]) || []).concat(yours.ranked || []))
            if (r.length > text.length && r.toLowerCase().startsWith(low) && !pane.hiddenReplies[pane.replyKey(r)])
                return r.slice(text.length)
        return ""
    }
    textFormat: Text.PlainText
    text: rest
    color: pane.mutedColor
    font: replyBox.font
    elide: Text.ElideRight
}
