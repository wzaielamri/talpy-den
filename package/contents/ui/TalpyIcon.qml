import QtQuick
import "hub"
import "talpy/glyph.mjs" as G

// The panel icon: Talpy peeking up through the panel's edge (talpy/glyph.mjs),
// in the state's color. It pops up when a chat needs you, glances around while
// Claude works, smiles when it's your turn and sleeps when nothing runs.
Canvas {
    id: icon

    property color color: "#3daee9"
    property string mode: "none"      // root.overall: waiting working idle none
    property bool moving: true        // false: holds still (e.g. under a window)

    renderStrategy: Canvas.Cooperative
    onColorChanged: requestPaint()
    onModeChanged: requestPaint()
    onWidthChanged: requestPaint()

    // A few frames a second are enough for a panel icon that may move for
    // hours: every other beat (hub/Beat.qml, 80 ms), with every other glyph
    // and blinking dot, so a window with several is drawn once for all of them
    OnBeat {
        id: moves
        active: icon.moving && icon.visible && G.glyphMoves(icon.mode)
    }
    Connections {
        target: Beat
        enabled: moves.active
        function onCountChanged() {
            if (Beat.count % 2 === 0)
                icon.requestPaint()
        }
    }

    onPaint: {
        const ctx = getContext("2d")
        ctx.reset()
        const k = Math.min(width, height) / 24
        ctx.translate((width - 24 * k) / 2, (height - 24 * k) / 2)
        ctx.scale(k, k)
        G.drawGlyph(ctx, mode, "rgba(" + Math.round(color.r * 255) + "," + Math.round(color.g * 255) + ","
                                 + Math.round(color.b * 255) + "," + color.a + ")", Date.now())
    }
}
