import QtQuick
import org.kde.kirigami as Kirigami
import "wheel.mjs" as Wheel

// Talpy Chat's conversation scrolled by the wheel and the touchpad at an even pace, a step a frame
// (wheel.mjs: where the list is at each frame, and why). A WheelHandler in the list (its Flickable): it
// takes the wheel's events with no key held before the scroll view's Kirigami.WheelHandler, whose eases
// went up and down in a spin and along a touchpad's stream; with a key held they go on as before (Ctrl:
// the text's size, the list's own handler; Shift: a page, Alt: sideways, Kirigami's). It moves the list
// on the frames (FrameAnimation) only while it moves, by whole pixels (every line moves the same:
// tests/test_scroll_crisp.py), and stops where anything else moved it (a jump, the scroll bar, a drag).
//
// Its clock is the screen's frames, as Qt's own animations' (a vsync a step): a FrameAnimation's frameTime
// is the computer's time between two steps, which comes a millisecond or two early or late, and a step
// sized by it went up and down by as much. A second step in the same frame (the loop steps again when a
// step changed nothing) moves nothing.
WheelHandler {
    id: handler

    required property Flickable flickable   // (the list it's in)
    // (a notch: the desktop's scroll lines × 20 px, and its ease as long as Plasma's: Kirigami.WheelHandler's;
    // none with the desktop's animations or smooth scrolling off)
    readonly property real step: Application.styleHints.wheelScrollLines * 20
    readonly property int ease: Kirigami.Settings.smoothScroll ? Kirigami.Units.longDuration : 0
    property var motion: Wheel.create(0)
    property real written: NaN       // (where it last put the list: moved since by anything else, it stops)
    property real frameMs: 1000 / 60    // (a frame of the screen's, as its frames came)
    property real seen: 0            // (when the step it last moved at came, Date.now())
    property bool first: false       // (the first step since it began to move: the frame after the one it began in)
    property int late: 0             // (steps in a row that came a frame or more late)
    readonly property bool moving: frames.running   // (it moves the list: a frame at a time)
    signal scrolled()                // (each event that scrolls the list)
    signal starting()                // (it begins to move the list, before its first step)

    acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
    acceptedModifiers: Qt.NoModifier
    orientation: Qt.Vertical
    onWheel: event => handler.take(event)

    // One event: a notch of the wheel (or part of one), or a touchpad's move, its fingers down or lifted
    // (Wayland gives a touchpad's phases; X11 its pixels only). Kirigami's distances: the angle in notches
    // (120 eighths of a degree) × a notch's px, the pixels only when there's no angle
    function take(event) {
        const angle = event.angleDelta.y
        const pixel = event.pixelDelta.y
        const touch = event.phase !== Qt.NoScrollPhase || (pixel !== 0 && pixel !== angle)
        follow()
        const was = Wheel.moving(motion)
        if (event.phase === Qt.ScrollBegin)
            Wheel.padBegin(motion)
        else if (event.phase === Qt.ScrollEnd)
            Wheel.padEnd(motion)
        else {
            const dist = -(angle !== 0 ? angle / 120 * step : pixel)
            if (dist === 0)
                return
            if (touch)
                Wheel.padMove(motion, dist)
            else
                Wheel.notch(motion, dist, ease, step)
            handler.scrolled()
        }
        if (!Wheel.moving(motion))
            put(Wheel.frame(motion, 0, top(), bottom()))   // (no ease: there at once)
        else if (!was) {
            // its first step now, shown in the frame that comes next (not one later: the animations step
            // after a frame is taken to be drawn)
            handler.starting()
            seen = Date.now()
            first = true
            put(Wheel.frame(motion, frameMs, top(), bottom()))
            frames.running = Wheel.moving(motion)
        }
    }
    // A step of the animations: a frame on, as Qt's own animations go (a vsync a step: a frame drawn late
    // or missed doesn't make it jump), none for another step in the same frame (it came less than half a
    // frame after the last: the loop steps again when a step changed nothing, and twice at once after a
    // stall); frames missed again and again (ten in a row: a busy computer), as many as passed
    function tick() {
        const now = Date.now()
        let n = 1
        if (first) {
            first = false
            late = 0
        } else {
            const k = (now - seen) / frameMs
            if (k < 0.5)
                return
            if (k > 0.75 && k < 1.25)
                frameMs += (now - seen - frameMs) * 0.05   // (the screen's frame, as its frames come)
            late = k > 1.5 ? late + 1 : 0
            if (late >= 10)
                n = Math.min(6, Math.round(k))
        }
        seen = now
        follow()
        if (Wheel.moving(motion))
            put(Wheel.frame(motion, n * frameMs, top(), bottom()))
        if (!Wheel.moving(motion))
            frames.running = false
    }
    function top() {
        return flickable.originY
    }
    function bottom() {
        return Math.max(flickable.originY, flickable.originY + flickable.contentHeight - flickable.height)
    }
    // (moved by anything else since it last put it there, or at rest: from where it is)
    function follow() {
        if (!(Math.abs(flickable.contentY - written) < 0.5))
            Wheel.stop(motion, flickable.contentY)
    }
    function put(y) {
        written = Math.round(y)
        if (flickable.contentY !== written)
            flickable.contentY = written
    }

    property FrameAnimation frames: FrameAnimation {
        running: false
        onTriggered: handler.tick()
    }
}
