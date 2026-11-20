pragma Singleton
import QtQuick

// One beat for what keeps moving while Claude works, in every window of every
// copy of the widget (they share this engine, so they share this): Talpy's
// glyphs (TalpyIcon.qml: the panel's, the popup's, each Talpy Chat window's)
// and Talpy Chat's blinking dots (a tool call still going). What moves in a
// window then moves in the same frame, so the window is drawn again once a
// beat, not once for each thing in it: a dot that faded on its own clock had
// its whole Talpy Chat window drawn at the screen's rate (60 times a second)
// for as long as a tool ran, and each glyph's timer, with a phase of its own,
// added frames of its own. It ticks only while something follows it
// (OnBeat.qml), and not while the screen is locked.
QtObject {
    id: beat

    readonly property int ms: 40       // 25 a second: a dot's fade; a glyph moves every other beat (80 ms)
    property real now: 0               // when the last beat came (Date.now())
    property int count: 0              // beats so far
    property int followers: 0          // OnBeat.qml: things that move with it now

    // The screen is locked (LockWatch.qml; never where Plasma's D-Bus module
    // isn't): no window of the widget shows, so nothing moves, and main.qml
    // takes every copy for covered (the pets' clock stops, a desktop's
    // dashboard holds its answers). Locked and dark, plasmashell went on
    // ticking the pets at 60 a second for nobody, with no frame drawn.
    readonly property bool locked: lockWatch.item !== null && lockWatch.item.locked
    property Loader lockWatch: Loader {
        source: "LockWatch.qml"
    }

    // A blinking dot's brightness at this beat, since its blinking began:
    // down to a quarter and back up in 1.2 s, eased in and out (the curve the
    // dot's own animation drew, Easing.InOutSine there and back, now taken
    // once a beat). A binding that calls it follows the beat.
    function fade(since) {
        return 0.625 + 0.375 * Math.cos(Math.PI * Math.max(0, now - since) / 600)
    }

    property Timer timer: Timer {
        interval: beat.ms
        repeat: true
        running: beat.followers > 0 && !beat.locked
        onTriggered: {
            beat.now = Date.now()
            beat.count++
        }
    }
}
