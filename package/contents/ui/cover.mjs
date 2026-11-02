// What windows leave to see of a part of the widget (CoverWatch.qml): one
// window or several together can cover it. Rectangles are {x, y, width,
// height} in the same coordinates.

// The pieces of r that none of the rects covers. A sliver thinner than
// `slack` px is dropped: the gap between two tiled windows shows nothing of
// the pets under them.
export function uncovered(r, rects, slack = 4) {
    let left = r.width > 0 && r.height > 0 ? [r] : []
    for (const w of rects) {
        const next = []
        for (const p of left) {
            const pr = p.x + p.width, pb = p.y + p.height
            const wr = w.x + w.width, wb = w.y + w.height
            if (w.x >= pr || wr <= p.x || w.y >= pb || wb <= p.y) {
                next.push(p)
                continue
            }
            // what sticks out above and below the window, then left and right of it
            const top = Math.max(p.y, w.y), bottom = Math.min(pb, wb)
            const cut = [{ x: p.x, y: p.y, width: p.width, height: w.y - p.y },
                         { x: p.x, y: wb, width: p.width, height: pb - wb },
                         { x: p.x, y: top, width: w.x - p.x, height: bottom - top },
                         { x: wr, y: top, width: pr - wr, height: bottom - top }]
            for (const c of cut)
                if (c.width >= slack && c.height >= slack)
                    next.push(c)
        }
        left = next
        if (left.length === 0)
            break
    }
    return left
}

// Whether the rects cover all of r (nothing of it is left to see)
export function covers(rects, r, slack = 4) {
    return rects.length > 0 && uncovered(r, rects, slack).length === 0
}

// The part of r inside `within` (an empty one when they don't meet)
export function clip(r, within) {
    const x = Math.max(r.x, within.x), y = Math.max(r.y, within.y)
    const right = Math.min(r.x + r.width, within.x + within.width)
    const bottom = Math.min(r.y + r.height, within.y + within.height)
    return { x, y, width: Math.max(0, right - x), height: Math.max(0, bottom - y) }
}

export function meets(a, b) {
    return a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height
}
