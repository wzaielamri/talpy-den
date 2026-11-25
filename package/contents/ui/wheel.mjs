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

// The screen's frame (ms): each scroller's own (its window's screen), in its clock. From the system when it
// can say: WheelScroll.qml asks code/screen_rate.py (Plasma's kscreen-doctor) for the refresh rate of its
// window's screen as it starts and when the window moves to another, and gives it here (rate()). Till then,
// or when the system can't say, a screen of 60 a second, changed only by what can't be anything else:
// - a faster screen: RUN frames in a row, each about one of a standard rate's frames, and on average
//   that frame (a window's frames can come no closer than its screen's: each waits for its vsync, but
//   for the second of a motion from rest, which is why one short gap teaches nothing);
// - a slower one: two whole motions whose frames all were (a run of frames missed while the window was
//   busy is a part of one motion, and two frames' way each is that window's real speed anyway).
// The standard rates are those below and the system's modes (rate()). A motion's first two gaps aren't
// counted: on Wayland its first frame is drawn at once, its second as soon as the first is handed on,
// a millisecond later, and its third at the first's frame callback (see frameStep)
export const RATES = [60, 75, 90, 100, 120, 144, 165, 240];
const RUN = 9;

function clockOf() {
    return { last: NaN, k: 0, period: 1000 / 60, system: false, rates: RATES.map(function (hz) { return 1000 / hz; }),
             run: [], gaps: [], slower: null, missed: false, late: false };
}

// (each scroller has a clock of its own, create(): nothing module-wide to forget; kept for older scripts)
export function resetFrames() {
}

export function create(y) {
    return { y: y, v: 0, curve: null, pad: null, fling: null, written: NaN, clock: clockOf() };
}

// The system's refresh rate for its window's screen (a second's frames, `hz`; 0: it couldn't say) and the
// rates of the screens' modes it knows (`rates`, also counted as standard): its frame from now on
export function rate(s, hz, rates) {
    const c = s.clock;
    const more = (rates || []).concat(hz > 0 ? [hz] : []).filter(function (r) { return r >= 20 && r <= 1000; });
    c.rates = RATES.concat(more).map(function (r) { return 1000 / r; });
    c.system = hz >= 20 && hz <= 1000;
    if (c.system)
        c.period = 1000 / hz;
    c.run = [];
    c.slower = null;
}

// Its screen's frame, ms
export function period(s) {
    return s.clock.period;
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
            padMove(s, dist, was && s.clock.late);
        else
            notch(s, dist, long, step, lo, hi);
        scrolled = true;
    }
    if (!moving(s))
        return { put: put(s, frame(s, 0, lo, hi)), starting: false, scrolled: scrolled };   // (no ease: there at once)
    if (!was) {
        begin(s.clock);
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
    if (!moving(s))
        return NaN;
    return put(s, frame(s, dt, lo, hi, s.clock.late));
}

// How far on its frame goes, in ms: the screen's frame for each vsync since its last, and one at least. On
// Wayland each frame its window draws is its own vsync: the render thread hands a frame on only once the
// frame before it was shown (qwaylandglcontext.cpp, swapBuffers: waitForFrameSync, then handleUpdate, which
// asks for the next frame callback, then eglSwapBuffers), and in Qt 6 every frame readied is drawn and
// handed on (qsgthreadedrenderloop.cpp, syncAndRender). The milliseconds between frames say how many vsyncs
// passed only once frames come at frame callbacks: a motion from rest draws its first frame at once, and
// its second a millisecond later, as the first is handed on (its update asked for in afterAnimating comes
// before that swap: qwaylandwindow.cpp requestUpdate, with no frame callback pending yet), its third at
// the first's frame callback, 0 to a frame later; all three are shown a vsync apart. So a frame goes the
// screen's frame however soon it came, and the vsyncs it stands for when it came two or more frames late
// (a frame the window missed, busy: the speed kept), but never further than the time that passed, and
// three frames at most after a frame on time: after a stall (this thread busy a few hundred ms) it goes on
// from where it was shown, not in a jump; six while the window keeps missing frames (one in four drawn)
function frameStep(c, now) {
    const last = c.last;
    const k = c.k;
    c.last = now;
    c.k = k + 1;
    c.late = false;
    if (!(now >= last)) {   // (its first frame)
        c.missed = false;
        return c.period;
    }
    const gap = now - last;
    if (k >= 3)
        learn(c, gap);
    const p = c.period;
    const n = Math.round(gap / p);
    const cap = c.missed ? 6 : 3;
    c.missed = n >= 2;
    c.late = gap > 2 * p;
    return n >= 2 ? Math.min(Math.min(n, cap) * p, gap) : p;
}

// (a motion begins: what the frames of the last one said of the screen, a slower one if two whole motions agree)
function begin(c) {
    const q = c.gaps.length >= 5 ? agreed(c, c.gaps) : NaN;
    if (!c.system && q > 1.005 * c.period) {
        if (c.slower !== null && Math.abs(c.slower.q - q) < 0.005 * q) {
            c.slower.n++;
            c.slower.gaps += c.gaps.length;
        } else {
            c.slower = { q: q, n: 1, gaps: c.gaps.length };
        }
        if (c.slower.n >= 2 && c.slower.gaps >= RUN)
            setPeriod(c, q);
    } else if (c.gaps.length > 0) {
        c.slower = null;
    }
    c.gaps = [];
    c.last = NaN;
    c.k = 0;
    c.missed = false;
    c.late = false;
}

// (a gap between two frames of a motion, its third on: a faster screen's, RUN in a row)
function learn(c, gap) {
    c.gaps.push(gap);
    if (c.gaps.length > 240)
        c.gaps.shift();
    c.run.push(gap);
    if (c.run.length > RUN)
        c.run.shift();
    if (c.run.length < RUN)
        return;
    const q = agreed(c, c.run);
    if (q < 0.995 * c.period)
        setPeriod(c, q);
}

// The standard frame all these gaps are (each within a ms and a half and rounding of it, and on average
// within 3 %), or NaN
function agreed(c, gaps) {
    const mean = gaps.reduce(function (a, b) { return a + b; }, 0) / gaps.length;
    let q = NaN;
    c.rates.forEach(function (r) {
        if (isNaN(q) || Math.abs(mean - r) / r < Math.abs(mean - q) / q)
            q = r;
    });
    if (!(Math.abs(mean - q) <= Math.max(0.03 * q, 0.35)))
        return NaN;
    return gaps.every(function (g) { return Math.abs(g - q) <= 1.5 + 0.05 * q; }) ? q : NaN;
}

// (its frames showed another screen's: a faster one even past the system's (its mode changed), the system's no more)
function setPeriod(c, q) {
    c.period = q;
    c.system = false;
    c.run = [];
    c.slower = null;
}

// Its window stopped drawing it (hidden, minimized, its frames no longer come): it goes to where its frames
// would have taken it, at once, and stops there. That place (whole px)
export function finish(s, lo, hi) {
    for (let k = 0; k < 2000 && moving(s); k++)
        frame(s, s.clock.period, lo, hi);
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
    s.pad = { base: s.y, hist: [[0, 0]], n: 0, c: 0, r: PAD_RATE, t: 0, last: 0, lift: -1, counts: [], started: false, held: 0, burst: false, seen: 0 };
}

// A touchpad's move of `dist` px; `burst`: it came after a frame that came late (tick()), with the others that
// came as the window was busy: Qt may hand on that frame before them
export function padMove(s, dist, burst) {
    padBegin(s);
    const p = s.pad;
    p.n++;
    if (burst === true)
        p.burst = true;
    p.hist.push([p.n, p.hist[p.hist.length - 1][1] + dist]);
    if (p.hist.length > 2000)   // (those not shown yet are kept: padFrame lets go of the others)
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

// (`late`: this frame came over two frames after the one before: the moves that came meanwhile came together
// as the window was busy, before this frame or just after it (padMove's burst))
function padFrame(s, dt, lo, hi, frameLate) {
    const p = s.pad;
    const y0 = s.y;
    const late = frameLate || p.burst;
    p.burst = false;
    if (p.n === 0) {   // (fingers down, no move yet)
        p.t += dt;
        if (p.lift >= 0 || p.t > PAD_IDLE)
            s.pad = null;
        return;
    }
    // (it eases in: a quarter of the pace at first, all of it after 50 ms)
    const ease = function (t) { return Math.min(1, 0.25 + 0.25 * t / 16.67); };
    // (its pace's constants are a frame's of 60 a second, taken by the time that passed: the same follow on any screen)
    const f = dt / 16.67;
    const per = function (k) { return 1 - Math.pow(1 - k, f); };
    const first = !p.started;
    if (first) {   // (its first frame: from where the touch began, its first frame's way on at the eased pace; moves that
                   // came bunched before it are caught up with as it goes, not jumped to)
        p.started = true;
        p.c = Math.min(0.5, p.r * dt * ease(dt / 2));
        p.t = dt;
    } else {
        const t0 = p.t;
        p.t += dt;
        // the moves' pace, counted over the last 150 ms while they come (the touchpad's own rate); not from a frame
        // that came late (the window busy: the moves meanwhile came together, after it, and counted against its
        // frames' time (a stall's: three frames') they made a pace many times the fingers', and the list went
        // hundreds of px past where they took it): counted afresh from there
        // (and not once the fingers lifted: no move comes then, what's left is shown at the pace they had)
        p.counts.push([p.t, p.n]);
        if (late)
            p.counts = [[p.t, p.n]];
        while (p.counts.length > 2 && p.t - p.counts[0][0] > 150)
            p.counts.shift();
        const a = p.counts[0];
        if (p.lift < 0 && p.n - a[1] >= 2 && p.t > a[0])   // (its first 50 ms count for more: it learns the pace at once)
            p.r += ((p.n - a[1]) / (p.t - a[0]) - p.r) * per(p.t <= 50 ? 0.5 : Math.max(0.1, 16.67 / Math.min(p.t, 150)));
        p.c += p.r * dt * ease(t0 + dt / 2);
    }
    // (the moves that came together after a stall, past the frame's way at the pace (three at most), are kept as
    // more of a lag, not raced to: it goes on at the fingers' pace from where it was shown, a tenth faster till it
    // has caught up with them, and what's left is shown after they lift, before its glide)
    if (late)
        p.held += Math.max(0, p.n - p.seen - p.r * dt);
    else
        p.held = Math.max(0, p.held - 0.1 * p.r * dt);
    p.seen = p.n;
    if (!first) {
        // (kept PAD_LAG moves behind the last that came, a tenth of the way each 16.7 ms: falling behind, more
        // at first; ahead, as it starts with fewer than that, it's let back that far over its first frames,
        // so the start isn't held back and the lift, a move later, comes before it has shown the last. The
        // ease-in leaves it further behind the faster the moves come, and its catching up goes a little past
        // the pace: 60 moves a second on a 75 a second screen go 6, 9, 14, 18, then 15, 15, 16 (its pace 16).
        // Not shaped away: an ease-in as long as the moves' pace allows would need that pace before it's
        // counted, and pulling toward where the next move is due ran further past it)
        const behind = p.n - PAD_LAG - p.held - p.c;
        if (p.lift < 0)
            p.c += behind * per(behind > 0 ? Math.max(0.1, 0.5 * 16.67 / p.t) : 0.1);
    }
    while (p.hist.length > 4 && p.hist[1][0] < p.c)   // (the moves shown: the last 3 kept for the glide's pace)
        p.hist.shift();
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
// rounded); `late`: it came over two frames after the one before (tick()). An end reached stops it there; a
// touch goes on from there, back the other way at once
export function frame(s, dt, lo, hi, late) {
    if (s.pad !== null)
        padFrame(s, dt, lo, hi, late === true);
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
