// Talpy Chat's conversation moved by the wheel and the touchpad (WheelScroll.qml), a step a frame:
// where it is at each frame. Kirigami's WheelHandler (every Plasma scroll view's) started an ease of
// its own at each event, from where the list was then: in a quick spin each notch threw the list forward
// again (a frame's step went 10, 20, 16, 13, 22, 18, 15, 24 px…), a touchpad's stream was a chain of
// 50 ms eases whose steps went up and down (and a frame now and then didn't move at all), and as the
// fingers lifted its glide began at less than half the speed. Here a notch adds to where the list is
// going and keeps how fast it goes (a cubic from where it is, at its speed, to the new end: one notch
// alone eases out as Kirigami's did, OutCubic over its 200 ms); a touchpad's moves are followed a
// couple of moves behind, at their own pace (counted in moves, not in the times they came: they come
// late and bunched when the window is busy), and its glide after the fingers lift starts at the speed
// it had. Distances are Kirigami's: a notch (120 eighths of a degree) is the desktop's scroll lines ×
// 20 px, and a touchpad's moves count the same way. Positions in px, times in ms. ES2017, no `?.`/`??`.

export const FLING_DECEL = 0.01;     // px/ms²: the glide after the fingers lift slows by this (Kirigami's 4000 × 2.5 px/s²)
export const PAD_LAG = 2;            // moves: a touchpad's moves are shown this many moves after they came, so every
                                     // frame falls between two that are there, even when they come late
export const PAD_RATE = 0.06;        // moves a ms (60 a second) at first, till the touch's own are counted
export const PAD_IDLE = 150;         // ms: no move for this long and no lift seen (X11's touchpads): it's over, no glide
export const PAD_GLIDE = 40;         // ms: lifted this soon after its last move, it glides on (later: the fingers had stopped)

export function create(y) {
    return { y: y, v: 0, curve: null, pad: null, fling: null };
}

// (a touch with no move yet doesn't move it: its first move does, at once)
export function moving(s) {
    return s.curve !== null || s.fling !== null || (s.pad !== null && s.pad.n > 0);
}

// Moved by something else (a jump, the scroll bar, a drag): it stops there
export function stop(s, y) {
    s.y = y;
    s.v = 0;
    s.curve = null;
    s.pad = null;
    s.fling = null;
}

// A wheel's notch, or a part of one: `dist` px further than where it was going (from where it is, at
// rest), in an ease of `long` ms for a notch of `step` px (Kirigami's: shorter for less, 50 ms at least,
// none for 2 px or less or when `long` is 0: the desktop's animations off)
export function notch(s, dist, long, step) {
    s.pad = null;
    s.fling = null;
    const target = (s.curve !== null ? s.curve.p1 : s.y) + dist;
    const r = target - s.y;
    const ms = Math.abs(r) <= 2 || long <= 0 ? 0 : Math.max(50, Math.min(Math.round(Math.abs(r) * long / step), long));
    if (ms === 0) {
        s.y = target;
        s.v = 0;
        s.curve = null;
        return;
    }
    let v0 = s.v;
    let d = ms;
    if (v0 * r <= 0)
        v0 = 3 * r / d;              // (at rest, or turned back: an ease out of its own, OutCubic)
    else if (Math.abs(v0) * d > 3 * Math.abs(r))
        d = 3 * r / v0;              // (faster than that ease would start: on at its speed, done sooner)
    s.curve = { p0: s.y, v0: v0, p1: target, d: d, t: 0 };
}

// The fingers down (a ScrollBegin; a first move without one begins it too). Down again before the
// last touch's moves were all shown: the same touch goes on
export function padBegin(s) {
    if (s.pad !== null) {
        s.pad.lift = -1;
        return;
    }
    s.curve = null;
    s.fling = null;
    s.pad = { base: s.y, hist: [[0, 0]], n: 0, c: 0, r: PAD_RATE, t: 0, last: 0, lift: -1, counts: [], started: false };
}

// A touchpad's move of `dist` px
export function padMove(s, dist) {
    padBegin(s);
    const p = s.pad;
    p.n++;
    p.hist.push([p.n, p.hist[p.hist.length - 1][1] + dist]);
    if (p.hist.length > 24)
        p.hist.shift();
    p.last = p.t;
}

// The fingers lifted (ScrollEnd)
export function padEnd(s) {
    if (s.pad !== null && s.pad.n === 0)
        s.pad = null;
    else if (s.pad !== null && s.pad.lift < 0)
        s.pad.lift = s.pad.t;
}

// Where the touch's moves had taken it at move x (between two moves: the line between them)
function padAt(hist, x) {
    const n = hist.length;
    if (x >= hist[n - 1][0])
        return hist[n - 1][1];
    if (x <= hist[0][0])
        return hist[0][1];
    let i = n - 1;
    while (i > 0 && hist[i - 1][0] > x)
        i--;
    const a = hist[i - 1];
    const b = hist[i];
    return a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0]);
}

function padFrame(s, dt) {
    const p = s.pad;
    const y0 = s.y;
    if (p.n === 0) {   // (fingers down, no move yet)
        p.t += dt;
        if (p.lift >= 0 || p.t > PAD_IDLE)
            s.pad = null;
        return;
    }
    if (!p.started) {   // (its first frame: what came so far, PAD_LAG moves back, and half a move on: it moves at once)
        p.started = true;
        p.c = Math.max(0, p.n - PAD_LAG) + Math.min(0.5, p.r * dt);
    } else {
        p.t += dt;
        // the moves' pace, counted over the last frames while they come (the touchpad's own rate)
        p.counts.push([p.t, p.n]);
        if (p.counts.length > 9)
            p.counts.shift();
        const a = p.counts[0];
        if (p.n - a[1] >= 2 && p.t > a[0])   // (the first frames' count for more: it learns the pace at once)
            p.r += ((p.n - a[1]) / (p.t - a[0]) - p.r) * (p.counts.length <= 3 ? 0.5 : Math.max(0.1, 1 / p.counts.length));
        p.c += p.r * dt * Math.min(1, 0.25 + 0.25 * p.counts.length);   // (half, then three quarters of the pace: it eases in)
        // (kept PAD_LAG moves behind the last that came, a tenth of the way a frame: falling behind, more at
        // first; ahead, as it starts with fewer than that, it's let back that far over its first frames, so
        // the start isn't held back and the lift, a move later, comes before it has shown the last)
        const behind = p.n - PAD_LAG - p.c;
        if (p.lift < 0)
            p.c += behind * (behind > 0 ? Math.max(0.1, 0.5 / p.counts.length) : 0.1);
    }
    if (p.c < p.n) {
        s.y = p.base + padAt(p.hist, p.c);
    } else if (p.lift >= 0 || p.t - p.last > PAD_IDLE) {
        // all shown, and over: lifted while it moved, it glides on at the pace of its last moves, from the
        // time it showed the last one (this frame shows the part of the glide since)
        const h = p.hist;
        const pace = h.length > 3 ? (h[h.length - 1][1] - h[h.length - 4][1]) / 3 * p.r : 0;
        const v = p.lift >= 0 && p.n >= 3 && p.lift - p.last <= PAD_GLIDE ? pace : 0;
        const over = p.r > 0 ? Math.min(dt, (p.c - p.n) / p.r) : 0;
        s.y = p.base + h[h.length - 1][1];
        s.pad = null;
        if (Math.abs(v) > 0.02) {
            s.fling = v;
            flingFrame(s, over);
        }
    } else {   // (the fingers stopped, or the next move is late: where the last one took it)
        p.c = p.n;
        s.y = p.base + p.hist[p.hist.length - 1][1];
    }
    s.v = dt > 0 ? (s.y - y0) / dt : 0;
}

function flingFrame(s, dt) {
    const v = s.fling;
    const a = v > 0 ? FLING_DECEL : -FLING_DECEL;
    const t = Math.min(dt, Math.abs(v) / FLING_DECEL);
    s.y += v * t - a * t * t / 2;
    s.v = v - a * t;
    if (t < dt || Math.abs(s.v) < 1e-6) {
        s.fling = null;
        s.v = 0;
    } else {
        s.fling = s.v;
    }
}

function curveFrame(s, dt) {
    const c = s.curve;
    c.t += dt;
    const u = Math.min(1, c.t / c.d);
    const r = c.p1 - c.p0;
    // (Hermite: from p0 at v0 to p1 at rest, in d ms)
    s.y = c.p0 + (u * u * u - 2 * u * u + u) * c.v0 * c.d + (3 * u * u - 2 * u * u * u) * r;
    s.v = (3 * u * u - 4 * u + 1) * c.v0 + (6 * u - 6 * u * u) * r / c.d;
    if (u >= 1) {
        s.y = c.p1;
        s.v = 0;
        s.curve = null;
    }
}

// The next frame, `dt` ms after the one before, the list between `lo` and `hi`: where it is to be (not
// rounded). An end reached stops it there; a touch goes on from there, back the other way at once
export function frame(s, dt, lo, hi) {
    if (s.pad !== null)
        padFrame(s, dt);
    else if (s.curve !== null)
        curveFrame(s, dt);
    else if (s.fling !== null)
        flingFrame(s, dt);
    const y = Math.max(lo, Math.min(hi, s.y));
    if (y !== s.y) {
        if (s.pad !== null)
            s.pad.base += y - s.y;
        s.curve = null;
        s.fling = null;
        s.v = 0;
        s.y = y;
    }
    return s.y;
}
