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

// The screen's frame (ms), as its window's frames come (WheelScroll.qml: the window's afterAnimating, once
// a frame it draws): the mean of the last 60 gaps between them that were about one frame (within a
// quarter of the middle of the last nine), NaN till it has seen one; one more gap moves it by a
// sixtieth, so a motion's steps stay even while it learns. A gap of over one and a half frames isn't
// learned from (frames the window missed, busy: two or three frames' way, not a longer frame), unless
// five in a row agree and aren't a whole number of frames (a slower screen than the one it knew: 60 a
// second after 144); a faster screen's are learned at once. One for the module (QML has one an engine:
// plasmashell's Talpy Chat windows learn it together, once). QML can't read the screen's refresh rate
// (Qt 6.11: Screen, Qt.application.screens and Window have none), so it's learned, not asked
const screen = { frame: NaN, gaps: [], odd: [] };

// (as plasmashell starts: nothing learned yet; for the tests)
export function resetFrames() {
    screen.frame = NaN;
    screen.gaps = [];
    screen.odd = [];
}

export function create(y) {
    return { y: y, v: 0, curve: null, pad: null, fling: null, written: NaN, clock: { last: NaN, k: 0 } };
}

// One event of the wheel or a touchpad, as WheelScroll.qml takes it: { angle, pixel, phase } (its
// angleDelta.y, pixelDelta.y, and "none", "begin", "update" or "end"), the list at `at` (its contentY),
// between `lo` and `hi`, a notch `step` px eased over `long` ms. What follows: { put: the list's place
// now (whole px; NaN: it stays), starting: it begins to move (its first step comes with the window's next
// frame: tick()), scrolled: the event moves the list }
export function input(s, ev, at, lo, hi, step, long) {
    follow(s, at);
    const was = moving(s);
    const touch = ev.phase !== "none" || (ev.pixel !== 0 && ev.pixel !== ev.angle);
    let scrolled = false;
    if (ev.phase === "begin") {
        padBegin(s);
    } else if (ev.phase === "end") {
        padEnd(s);
    } else {
        const dist = -(ev.angle !== 0 ? ev.angle / 120 * step : ev.pixel);
        if (dist === 0)
            return { put: NaN, starting: false, scrolled: false };
        if (touch)
            padMove(s, dist);
        else
            notch(s, dist, long, step, lo, hi);
        scrolled = true;
    }
    if (!moving(s))
        return { put: put(s, frame(s, 0, lo, hi)), starting: false, scrolled: scrolled };   // (no ease: there at once)
    if (!was) {
        s.clock.last = NaN;
        s.clock.k = 0;
        s.written = at;   // (it starts where the list is)
        return { put: NaN, starting: true, scrolled: scrolled };
    }
    return { put: NaN, starting: false, scrolled: scrolled };
}

// A frame of its window, about to be drawn (WheelScroll.qml: the window's afterAnimating), at `now`
// (Date.now(), ms), the list at `at`: the list's place in that frame (whole px), or NaN (it stays)
export function tick(s, now, at, lo, hi) {
    const dt = frameStep(s.clock, now);
    follow(s, at);
    if (!moving(s) || !(dt > 0))
        return NaN;
    return put(s, frame(s, dt, lo, hi));
}

// How far on its frame goes, in ms: the screen's frame times the frames since its last (a frame the
// window didn't draw, busy, keeps the speed: the next goes two), not the milliseconds between them, which
// come early or late by a millisecond or more (and in whole ms here). Its first frame, the first drawn after
// the event, goes a frame. Its second goes a frame at least: on a window at rest Qt Wayland draws the first
// at once (an update asked for with no frame callback pending, qwaylandwindow.cpp requestUpdate) and the
// second at the compositor's frame callback, 0 to a frame later, but the two are shown a vsync apart. Past
// those, two frames within half a frame go by their time (an extra frame, as on an expose: both shown in
// one vsync). Before any frame is known (the first motion since plasmashell began) it goes nothing till
// its third frame, whose gap is the first that is a frame. A stall goes six frames at most
function frameStep(c, now) {
    const last = c.last;
    const k = c.k;
    c.last = now;
    c.k = k + 1;
    if (!(now >= last))
        return isNaN(screen.frame) ? 0 : screen.frame;
    const gap = now - last;
    if (k === 1)
        return isNaN(screen.frame) ? 0 : Math.max(1, Math.min(6, Math.round(gap / screen.frame))) * screen.frame;
    if (isNaN(screen.frame)) {
        learn(gap);
        return gap;
    }
    const n = Math.round(gap / screen.frame);
    if (gap <= 1.5 * screen.frame) {
        screen.odd = [];
        learn(gap);
    } else if (n <= 6 && Math.abs(gap / screen.frame - n) > 0.2) {
        screen.odd.push(gap);
        const mid = screen.odd.slice().sort(function (x, y) { return x - y; })[screen.odd.length >> 1];
        if (!screen.odd.every(function (g) { return Math.abs(g - mid) <= 0.1 * mid; }))
            screen.odd = [gap];
        else if (screen.odd.length >= 5) {   // (another screen, slower: its frames from now on)
            screen.gaps = [];
            screen.odd.forEach(learn);
            screen.odd = [];
        }
    } else {
        screen.odd = [];
    }
    return n < 1 ? gap : Math.min(n, 6) * screen.frame;
}

function learn(gap) {
    screen.gaps.push(gap);
    if (screen.gaps.length > 60)
        screen.gaps.shift();
    const last = screen.gaps.slice(-9).sort(function (x, y) { return x - y; });
    const mid = last[last.length >> 1];
    const one = screen.gaps.filter(function (g) { return Math.abs(g - mid) <= 0.25 * mid; });
    screen.frame = Math.max(3, Math.min(50, one.reduce(function (a, b) { return a + b; }, 0) / one.length));
}

// Its window stopped drawing it (hidden, minimized, its frames no longer come): it goes to where its frames
// would have taken it, at once, and stops there. That place (whole px)
export function finish(s, lo, hi) {
    for (let k = 0; k < 2000 && moving(s); k++)
        frame(s, isNaN(screen.frame) ? 1000 / 60 : screen.frame, lo, hi);
    stop(s, s.y);
    return put(s, s.y);
}

// (whole pixels: every line moves the same; remembered, so a move by anything else is seen)
function put(s, y) {
    s.written = Math.round(y);
    return s.written;
}

// (moved by anything else since it last put it there, or at rest: from where it is, a whole pixel, not
// where its last motion's arithmetic ended a fraction away)
function follow(s, at) {
    if (!moving(s) || !(Math.abs(at - s.written) < 0.5))
        stop(s, at);
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
// rest), but not past the list's ends `lo` and `hi` (it eases into an end, as Kirigami's did), in an ease
// of `long` ms for a notch of `step` px (Kirigami's: shorter for less, 50 ms at least, none for 2 px or
// less or when `long` is 0: the desktop's animations off)
export function notch(s, dist, long, step, lo, hi) {
    s.pad = null;
    s.fling = null;
    const target = Math.max(lo, Math.min(hi, (s.curve !== null ? s.curve.p1 : s.y) + dist));
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

function padFrame(s, dt, lo, hi) {
    const p = s.pad;
    const y0 = s.y;
    if (p.n === 0) {   // (fingers down, no move yet)
        p.t += dt;
        if (p.lift >= 0 || p.t > PAD_IDLE)
            s.pad = null;
        return;
    }
    // (it eases in: a quarter of the pace at first, all of it after 50 ms)
    const ease = function (t) { return Math.min(1, 0.25 + 0.25 * t / 16.67); };
    if (!p.started) {   // (its first frame: from where the touch began, its first frame's way on at the eased pace; moves that
                        // came bunched before it are caught up with as it goes, not jumped to)
        p.started = true;
        p.c = Math.min(0.5, p.r * dt * ease(dt / 2));
        p.t = dt;
    } else {
        // (its pace's constants are a frame's of 60 a second, taken by the time that passed: the same
        // follow on any screen)
        const f = dt / 16.67;
        const per = function (k) { return 1 - Math.pow(1 - k, f); };
        const t0 = p.t;
        p.t += dt;
        // the moves' pace, counted over the last 150 ms while they come (the touchpad's own rate)
        p.counts.push([p.t, p.n]);
        while (p.counts.length > 2 && p.t - p.counts[0][0] > 150)
            p.counts.shift();
        const a = p.counts[0];
        if (p.n - a[1] >= 2 && p.t > a[0])   // (its first 50 ms count for more: it learns the pace at once)
            p.r += ((p.n - a[1]) / (p.t - a[0]) - p.r) * per(p.t <= 50 ? 0.5 : Math.max(0.1, 16.67 / Math.min(p.t, 150)));
        p.c += p.r * dt * ease(t0 + dt / 2);
        // (kept PAD_LAG moves behind the last that came, a tenth of the way each 16.7 ms: falling behind, more
        // at first; ahead, as it starts with fewer than that, it's let back that far over its first frames,
        // so the start isn't held back and the lift, a move later, comes before it has shown the last. The
        // ease-in leaves it further behind the faster the moves come, and its catching up goes a little past
        // the pace: 60 moves a second on a 75 a second screen go 6, 9, 14, 18, then 15, 15, 16 (its pace 16).
        // Not shaped away: an ease-in as long as the moves' pace allows would need that pace before it's
        // counted, and pulling toward where the next move is due ran further past it)
        const behind = p.n - PAD_LAG - p.c;
        if (p.lift < 0)
            p.c += behind * per(behind > 0 ? Math.max(0.1, 0.5 * 16.67 / p.t) : 0.1);
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
            flingFrame(s, over, lo, hi);
        }
    } else {   // (the fingers stopped, or the next move is late: where the last one took it)
        p.c = p.n;
        s.y = p.base + p.hist[p.hist.length - 1][1];
    }
    s.v = dt > 0 ? (s.y - y0) / dt : 0;
}

// (slowing at FLING_DECEL; more, when that would take it past an end: it stops at the end)
function flingFrame(s, dt, lo, hi) {
    const v = s.fling;
    const room = v > 0 ? hi - s.y : s.y - lo;
    const decel = room > 0 && v * v / (2 * FLING_DECEL) > room ? v * v / (2 * room) : FLING_DECEL;
    const a = v > 0 ? decel : -decel;
    const t = Math.min(dt, Math.abs(v) / decel);
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
        padFrame(s, dt, lo, hi);
    else if (s.curve !== null)
        curveFrame(s, dt);
    else if (s.fling !== null)
        flingFrame(s, dt, lo, hi);
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
