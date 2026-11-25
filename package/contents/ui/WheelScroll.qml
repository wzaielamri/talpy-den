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
// it less than a pixel asks for nothing). A step goes the screen's frame for each vsync since the last,
// one at least (wheel.mjs tick(): on Wayland every frame drawn is a vsync of its own; a frame the window
// missed keeps the speed). The screen's frame is the system's (code/screen_rate.py: its refresh rate, as
// Plasma's kscreen-doctor gives it), asked as it starts and when its window moves to another screen;
// till it answers, or if it can't, 60 a second and what the frames show (wheel.mjs). Still, nothing
// listens or asks for frames.
WheelHandler {
    id: handler

    required property Flickable flickable   // (the list it's in)
    // (a notch: the desktop's scroll lines × 20 px, and its ease as long as Plasma's: Kirigami.WheelHandler's;
    // none with the desktop's animations or smooth scrolling off)
    readonly property real step: Application.styleHints.wheelScrollLines * 20
    readonly property int ease: Kirigami.Settings.smoothScroll ? Kirigami.Units.longDuration : 0
    property var motion: Wheel.create(0)
    property bool moving: false   // (it moves the list: a step each frame of its window)
    onMovingChanged: if (!moving) {
        watch.stop()
        checking = false
    }
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
            rearm()
            next()   // (its first step: the window's next frame)
        }
    }
    // A frame of its window, about to be drawn: its step, drawn in that frame (wheel.mjs tick())
    function frame() {
        const y = Wheel.tick(motion, Date.now(), flickable.contentY, top(), bottom())
        if (!isNaN(y) && flickable.contentY !== y)
            flickable.contentY = y
        if (Wheel.moving(motion)) {
            rearm()
            next()
        } else {
            moving = false
        }
    }
    // Its window stopped drawing it: there at once, where its frames would have taken it (wheel.mjs finish())
    function finish() {
        const y = Wheel.finish(motion, top(), bottom())
        if (flickable.contentY !== y)
            flickable.contentY = y
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

    // (no frame of its window for 100 ms: it may have been hidden, or minimized (Wayland: no frame callback
    // comes, and Qt takes a window with none for 100 ms for not shown, qwaylandwindow.cpp mFrameCallbackTimeout),
    // and its frames don't come: it finishes at once rather than wait, held, to jump on when shown. Or this
    // thread stalled (plasmashell loading chats, another widget): no frame came, but no timer ran either, and
    // the frame due comes right after. So it looks twice: no frame in 100 ms, it asks for one and looks again
    // two frames later; only no frame then either ends it, where it was going (a stall holds back both looks,
    // and the frame asked for comes after it: the motion goes on). Running only while it moves, again from
    // each frame)
    property bool checking: false   // (its second look: a frame asked for)
    function rearm() {
        checking = false
        watch.restart()
    }
    property Timer watch: Timer {
        interval: handler.checking ? Math.max(34, Math.round(2 * Wheel.period(handler.motion))) : 100
        onTriggered: {
            if (handler.checking) {
                handler.finish()
            } else {
                handler.checking = true
                handler.next()
                watch.restart()
            }
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

    // The refresh rate of its window's screen, from the system (code/screen_rate.py: Plasma's kscreen-doctor),
    // the length of the frames its steps go by (wheel.mjs rate()): asked as it starts and when its window moves
    // to another screen (Screen.name: the output's connector, eDP-1), never more; an answer for a screen it's no
    // longer on is left out
    readonly property string screenName: flickable.Screen.name || ""
    onScreenNameChanged: askRate()
    Component.onCompleted: askRate()
    property string rateAsked: "\n"   // (the screen it last asked for)
    property string rateSource: ""     // (and the command: only its answer is taken)
    readonly property string codeDir: decodeURIComponent(Qt.resolvedUrl("../code/").toString().replace(/^file:\/\//, ""))
    function quote(s) {
        return "'" + String(s).replace(/'/g, "'\\''") + "'"
    }
    function askRate() {
        if (screenName === rateAsked)
            return
        rateAsked = screenName
        rateSource = "python3 -I " + quote(codeDir + "screen_rate.py") + " " + quote(screenName) + " # " + Date.now()
        rateRunner.connectSource(rateSource)
    }
    property Exec rateRunner: Exec {
        onNewData: (source, data) => {
            if (source !== handler.rateSource)
                return
            let r = null
            try {
                r = JSON.parse(data.stdout)
            } catch (e) {
                return
            }
            if (r)
                Wheel.rate(handler.motion, r.ok ? Number(r.hz) : 0, Array.isArray(r.rates) ? r.rates.map(Number) : [])
        }
    }
}
