import QtQuick
import org.kde.kirigami as Kirigami
import "hub"
import "wheel.mjs" as Wheel

// Talpy Chat's conversation scrolled by the wheel and the touchpad at an even pace, a step a frame
// (wheel.mjs: where the list is at each frame, and why). A WheelHandler in the list (its Flickable): it
// takes the wheel's events with no key held before the scroll view's Kirigami.WheelHandler, whose eases
// went up and down in a spin and along a touchpad's stream; with a key held they go on as before (Ctrl:
// the text's size, the list's own handler; Shift: a page, Alt: sideways, Kirigami's). It moves the list
// a step each frame its window draws, only while it moves, by whole pixels (every line moves the same:
// tests/test_scroll_crisp.py), and stops where anything else moved it (a jump, the scroll bar, a drag).
//
// Its steps are its window's frames, not Qt's animations': plasmashell shows several windows (its panel,
// its desktop, a popup, Talpy Chat's), and then Qt's threaded loop steps its animations (a FrameAnimation
// too) on a timer of its own, int(1000 / the screen's rate) ms, not once a frame (qsgthreadedrenderloop.cpp,
// startOrStopAnimationTimer: vsync-driven only with one window shown); that timer and the frames drift
// apart, and about every 0.4 s at 60 a second a frame drew two steps (19, 38, 19 px) or none. So it takes
// its step as its window is about to draw a frame: the window's afterAnimating, which Qt emits on this
// thread once each time it readies that window's frame, after polishing and before syncing the scene
// (polishAndSync), so the list's place set there is in that frame; and while it moves it asks for the
// window's next frame (requestUpdate(): what the list's own change asks for too, but a frame that moved
// it less than a pixel asks for nothing). A step goes the screen's frame times the frames since the last
// (wheel.mjs tick(): learned from the frames' times; a frame the window missed keeps the speed). Still,
// nothing listens or asks for frames.
WheelHandler {
    id: handler

    required property Flickable flickable   // (the list it's in)
    // (a notch: the desktop's scroll lines × 20 px, and its ease as long as Plasma's: Kirigami.WheelHandler's;
    // none with the desktop's animations or smooth scrolling off)
    readonly property real step: Application.styleHints.wheelScrollLines * 20
    readonly property int ease: Kirigami.Settings.smoothScroll ? Kirigami.Units.longDuration : 0
    property var motion: Wheel.create(0)
    property bool moving: false   // (it moves the list: a step each frame of its window)
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
        if (r.starting)
            handler.starting()   // (before its first step: the hovered message is held)
        if (!isNaN(r.put) && flickable.contentY !== r.put)
            flickable.contentY = r.put
        if (r.starting) {
            moving = true
            next()   // (its first step: the window's next frame)
        }
    }
    // A frame of its window, about to be drawn: its step, drawn in that frame (wheel.mjs tick())
    function frame() {
        const y = Wheel.tick(motion, Date.now(), flickable.contentY, top(), bottom())
        if (!isNaN(y) && flickable.contentY !== y)
            flickable.contentY = y
        if (Wheel.moving(motion))
            next()
        else
            moving = false
    }
    function next() {
        const w = flickable.Window.window
        if (w)
            w.requestUpdate()
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

    // (its window about to draw a frame: listened to only while it moves)
    property Connections frames: Connections {
        target: handler.flickable.Window.window
        enabled: handler.moving
        function onAfterAnimating() {
            handler.frame()
        }
    }
    // (the screen locked: nothing of the widget shows, nothing moves, hub/Beat.qml; it stops where it is)
    property Connections lock: Connections {
        target: Beat
        enabled: handler.moving
        function onLockedChanged() {
            if (Beat.locked) {
                Wheel.stop(handler.motion, handler.flickable.contentY)
                handler.moving = false
            }
        }
    }
}
