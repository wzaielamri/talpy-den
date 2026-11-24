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
// sized by it went up and down by as much; a step about a frame after the last goes a frame, one well
// within a frame (the loop stepping again, or a screen faster than the frame known so far) goes the time
// it took (wheel.mjs tick()). Its first step goes a frame on when a frame was drawn since its first move
// (`drawn`, from the window's afterAnimating: the scene is synced to draw right after it), else the time
// since the event: plasmashell shows several windows, and then Qt steps the animations on a timer of
// their own, which can come before the frame that shows the first move.
WheelHandler {
    id: handler

    required property Flickable flickable   // (the list it's in)
    // (a notch: the desktop's scroll lines × 20 px, and its ease as long as Plasma's: Kirigami.WheelHandler's;
    // none with the desktop's animations or smooth scrolling off)
    readonly property real step: Application.styleHints.wheelScrollLines * 20
    readonly property int ease: Kirigami.Settings.smoothScroll ? Kirigami.Units.longDuration : 0
    property var motion: Wheel.create(0)
    property bool drawn: false   // (a frame drawn since it began to move)
    readonly property bool moving: frames.running   // (it moves the list: a frame at a time)
    // (a scroll in progress: while it moves the list and 400 ms after its last event, Kirigami's)
    readonly property bool latched: moving || latch.running
    signal scrolled()                // (each event that scrolls the list)
    signal starting()                // (it begins to move the list, before its first step)

    acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
    acceptedModifiers: Qt.NoModifier
    orientation: Qt.Vertical
    onWheel: event => handler.take(event)

    // One event: a notch of the wheel (or part of one), or a touchpad's move, its fingers down or lifted
    // (Wayland gives a touchpad's phases; X11 its pixels only): wheel.mjs input()
    function take(event) {
        latch.restart()
        const r = Wheel.input(motion, { angle: event.angleDelta.y, pixel: event.pixelDelta.y,
                                        phase: event.phase === Qt.ScrollBegin ? "begin" : event.phase === Qt.ScrollEnd ? "end"
                                             : event.phase === Qt.NoScrollPhase ? "none" : "update" },
                              flickable.contentY, top(), bottom(), step, ease)
        if (r.scrolled)
            handler.scrolled()
        if (r.starting) {
            handler.drawn = false
            handler.starting()   // (before its first step: the hovered message is held)
        }
        if (!isNaN(r.put) && flickable.contentY !== r.put)
            flickable.contentY = r.put
        if (r.starting)
            frames.running = Wheel.moving(motion)
    }
    // A step of the animations: wheel.mjs tick()
    function tick(gap) {
        const y = Wheel.tick(motion, gap, flickable.contentY, top(), bottom(), handler.drawn)
        handler.drawn = true
        if (!isNaN(y) && flickable.contentY !== y)
            flickable.contentY = y
        if (!Wheel.moving(motion))
            frames.running = false
    }
    function top() {
        return flickable.originY
    }
    function bottom() {
        return Math.max(flickable.originY, flickable.originY + flickable.contentHeight - flickable.height)
    }

    // A scroll in progress stays the list's: an item over its content, enabled while it scrolls and 400 ms
    // after its last event, takes the wheel before anything in the list does, so a spin or a touchpad's
    // swipe that brings a scroll view of its own under the pointer (a plan or a page shown in the chat,
    // MadeLine.qml) goes on scrolling the list (Kirigami's WheelHandler does the same: its filter item,
    // m_wheelScrollingDuration). Disabled, it's nothing: the pointer's hover and clicks go through it.
    // Still Kirigami's own ease (it restarts at each event): the wheel over the scroll bar, and with Shift
    // or Alt held; a Kirigami ease that runs moves the list, and this one, moved by it, stops (follow())
    property Timer latch: Timer {
        interval: 400
    }
    property Item cover: Item {
        parent: handler.flickable
        anchors.fill: parent
        z: (handler.flickable.contentItem ? handler.flickable.contentItem.z : 0) + 1
        enabled: handler.latched
        WheelHandler {
            acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
            acceptedModifiers: Qt.NoModifier
            orientation: Qt.Vertical
            onWheel: event => handler.take(event)
        }
    }

    // (the window about to draw a frame: afterAnimating comes on this thread just before the scene is
    // synced for it; listened to only from its first move to its first step)
    property Connections frameDrawn: Connections {
        target: handler.flickable.Window.window
        enabled: handler.frames.running && !handler.drawn
        function onAfterAnimating() {
            handler.drawn = true
        }
    }

    property FrameAnimation frames: FrameAnimation {
        running: false
        onTriggered: handler.tick(frameTime * 1000)
    }
}
