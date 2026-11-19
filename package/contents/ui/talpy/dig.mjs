// Deep Dig: Talpy digs straight down through the ground, what's buried comes
// up at him, and you steer him round it (design: 2026-11-19-deep-dig-design).
// A scored game (Scored, scored.mjs): the stage grows (STAGE_GU), the first
// touch with something ends it (how deep, the best, a press digs again), a
// cookie is worth BONUS metres more.
//
// He stays a quarter down the stage (his body's middle at TALPY_AT of its
// height), upright, his paws scooping below him; the earth goes up past him.
// He goes where you point (aim(x): the pointer over the stage; ←/→ held,
// press('left'|'right'), move it), eased there: a critically damped spring
// with a top speed and a top acceleration (MOVE), braking in time so he never
// passes it, slowing into the stage's sides, never bouncing; he leans into
// his way (turn, degrees: going right his paws lead, his head tilts back) and
// settles upright. Clods fly up off his paws (more as he turns hard), his
// tunnel goes up behind him along the path he took, his lamp lights round
// him (glow). Moves are made in steps of at most STEP_PX: nothing thin is
// stepped over in a long frame.
//
// What comes, comes in rows from below: each leaves a way through at least
// GAP of his body's widths wide, where he can get from the last row's in the
// time the earth takes to bring it up, at his top speed with a margin
// (REACH). What's in them changes with depth (LAYERS: topsoil, clay, rock),
// the earth's colour too (soil, talpy.mjs soilAt); beetles, from BEETLE_FROM
// metres, crawl sideways, alone in their rows. Decoration (specks, worms,
// crystals in the rock) is never in the way. For the host, besides Scored's:
// x (his middle, px), vx (px a second), cy (his body's middle, stage px),
// soil ('#rrggbb'), layer, rows (the rows on the stage: top, bottom, gapL,
// gapR, beetle, alone, clear), hint ('steer' at the start, then '').
//
// Plain ES2017 (see paths.mjs).

import { Scored, DECOR, GRAB } from './scored.mjs';
import { FRAMES, soilAt } from './talpy.mjs';

// a thing's size by his body's height (w × h; a root's and a pipe's w is the row's)
export const DIG_KINDS = {
    root: [1.6, 0.34], pebble: [0.6, 0.4], stone: [0.6, 0.62], pipe: [2.2, 0.42], bottle: [0.32, 0.72],
    boulder: [1.25, 0.85], beetle: [0.8, 0.46], cookie: [0.6, 0.6], plus: [0.7, 0.35],
    speck: [0.32, 0.2], worm: [0.62, 0.2], crystal: [0.5, 0.46], tunnel: [1, 0.5], clod: [0.13, 0.11], glow: [1.8, 1.8]
};
// how many looks a kind has (drawThing's variant: a root's curl and side, which way a pipe's open end or a
// beetle faces, a speck's, a crystal's colour, a clod's, a cookie's flavour)
export const DIG_VARIANTS = { root: 6, pipe: 2, beetle: 2, speck: 2, crystal: 2, clod: 3, cookie: 8 };
// how he moves: the spring (ω, a second), his top speed (his body's widths a second) and
// acceleration (widths a second²), his lean at the top speed (degrees) and how quickly it
// follows (a second), ←/→ moving where he goes at that much of his top speed
export const MOVE = { omega: 15, top: 7, accel: 60, lean: 20, leanOmega: 12, keys: 0.9 };
export const LAYERS = [[0, 'topsoil'], [100, 'clay'], [300, 'rock']];
const STAGE_GU = 16;           // the stage's height while he digs: room to see what comes
const TALPY_AT = 0.22;         // his body's middle, that far down the stage
const MIDDLE = 20;             // his body's middle above his floor, box units (talpy.mjs: 37 of 57)
const READY_MS = 2000;         // the hint, and nothing in his way yet
const RISE_MS = 600;           // ...he gets to his place meanwhile
const SPEED0 = 60;             // box units a second the earth goes up at the start
const SPEED_UP = 1.1;          // ×, every 100 m
const SPEED_CAP = 2;           // × the start, at most
const M_PER_S = 6;             // metres a second at the start
const GAP = 1.6, GAP_MORE = 0.6;   // a way through: that many of his body's widths, and up to that much more
const CLEAR = [1.4, 2.4];      // body heights between one row and the next
const REACH = 0.7;             // of what his top speed covers meanwhile: the next way through is that near
const SPACING = 0.35;          // body widths between two things side by side, at most (less than he is: a wall)
const BEETLE_FROM = 300, BEETLE_EVERY = 1 / 6, BEETLE_PACE = 1.5;   // metres; a row in…; his widths a second
const COOKIE_EVERY = 1 / 3;    // rows with a cookie in their way through
const TUNNEL_STEP = 0.6;       // of a piece's size, his way from one piece of his tunnel to the next (overlapping)
const STEP_PX = 4;             // a move's step, at most
const CLODS = 6, CLOD_MS = 600, CLOD_FALL = 9;   // a second (twice that turning hard); how long; body heights a second²
const BOB = 0.015;             // his bob as he digs, of his body's height
const BOB_MS = 340;            // (his paws' beat, both: talpy.mjs ARM_BEATS.scoop × 2)
const TWINKLE_MS = 140, WORM_MS = 140, LEGS_MS = 90;
const BOX_W = 0.6, BOX_H = 0.9;    // his hit box, by his body's width and height
const SHRINK = 0.15;           // a thing's hit box is that much inside its drawing, each side
const ROCKS = { topsoil: ['pebble', 'stone'], clay: ['pebble', 'bottle', 'stone'], rock: ['stone', 'boulder', 'pebble'] };
const LONG = { topsoil: ['root'], clay: ['pipe', 'root'], rock: [] };
const DECORS = { topsoil: ['speck', 'speck', 'worm'], clay: ['speck', 'worm'], rock: ['speck', 'crystal'] };
const POSES = {
    // (happy at it, the owner's wish: his eyes open, an open smile, rosy cheeks)
    dig: () => ({ depth: 'out', hole: 0, arms: 'scoop', eyes: 'open', mouth: 'open', blush: 1, plume: 'bob', tail: 'wag' }),
    bump: () => ({ depth: 'out', hole: 0, body: 'shake', eyes: 'squint', mouth: 'o', plume: 'wild', tail: 'droop',
                   fx: [['sparkle', 26, 14, { dy: -6 }], ['sparkle', 38, 12, { dy: -6, delay: 0.15 }]] })
};

const rnd = (a, b) => a + Math.random() * (b - a);
const int = (a, b) => Math.floor(rnd(a, b + 1));
const pick = list => list[int(0, list.length - 1)];
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

export class Dig extends Scored {
    constructor(talpy, host) {
        super(talpy, host, 'dig', STAGE_GU);
        this.poses = POSES;
        this.rows = [];            // the rows on the stage (kept, emptied, filled)
        this.x = 0;
        this.vx = 0;
        this.cy = 0;
        this.lean = 0;
        this.soil = soilAt(0);
        this.layer = 'topsoil';
        this.speed = 0;
        this.speedUp = 1;
        this.glowTh = null;
    }

    reset(now) {
        const s = this.s = this.host.stage();
        this.x = clamp(Number(this.host.px()) || s.width / 2, s.minX, s.maxX);
        this.host.moveTo(this.x);
        if (this.host.face)
            this.host.face(false);
        this.facingLeft = false;
        this.vx = 0;
        this.lean = 0;
        this.aimX = null;
        this.keyDir = 0;
        this.rows.length = 0;
        this.rowId = 0;
        this.lastGap = this.x;     // (the last way through's middle: the next is within reach of it)
        this.lastBeetle = false;
        this.lastBottom = null;    // (the last row's bottom, stage px, on the stage or not)
        this.nextRow = 0;          // (px of earth to go before the next row: set as the dig starts)
        this.decorDue = 0;
        this.lastTunnel = null;
        this.clodDue = 0;
        this.hint = 'steer';
        this.speeds();
        this.place(now);
        this.glowTh = this.add('glow', 0, 0);
        this.follow();
        this.setPose('dig');
    }

    speeds() {
        this.speedUp = Math.min(SPEED_CAP, Math.pow(SPEED_UP, this.dist / 100));
        this.speed = SPEED0 * this.s.unit * this.speedUp;
        let layer = LAYERS[0][1];
        for (let i = 0; i < LAYERS.length && this.dist >= LAYERS[i][0]; i++)
            layer = LAYERS[i][1];
        this.layer = layer;
        this.soil = soilAt(this.dist);
    }

    // (a new go: he rises to his place from where he is, the floor or where the last dig ended)
    begin(now) {
        this.riseFrom = this.lift;
        super.begin(now);
    }

    // his place up and down: a quarter down the stage (rising there as a dig starts), bobbing
    place(now) {
        const s = this.s, u = s.unit;
        this.cy = s.height * TALPY_AT;
        const up = s.ground - this.cy - MIDDLE * u, from = this.riseFrom || 0;
        const p = this.state === 'ready' ? Math.min(1, (now - this.since) / RISE_MS) : 1;
        const bob = this.state === 'run' ? Math.sin(2 * Math.PI * now / BOB_MS) * BOB * s.bodyHeight : 0;
        this.lift = from + (up - from) * (0.5 - 0.5 * Math.cos(Math.PI * p)) + bob;
    }

    aim(x) {
        if (this.on && this.state !== 'over')
            this.aimX = x;
    }

    press(what) {
        if (!this.on)
            return;
        if (this.state === 'over') {
            if (what === 'jump')
                this.again();
            return;
        }
        if (what === 'left' || what === 'right')
            this.keyDir = what === 'left' ? -1 : 1;
    }

    release(what) {
        if ((what === 'left' && this.keyDir < 0) || (what === 'right' && this.keyDir > 0)) {
            this.keyDir = 0;
            // (where he'd stop braking as hard as he can: not on to where the key had taken his aim)
            const accel = MOVE.accel * this.s.bodyWidth;
            this.aimX = this.x + Math.sign(this.vx) * this.vx * this.vx / (2 * accel);
        }
    }

    tickGame(now, dt) {
        this.s = this.host.stage();   // (the stage may grow, or the view be resized)
        if (this.state === 'ready' && now - this.since >= READY_MS) {
            this.state = 'run';
            this.hint = '';
            this.nextRow = this.s.height * 0.15;
            this.hush();   // ("Let's play!" gone as play begins)
        }
        this.speeds();
        this.place(now);
        const s = this.s, step = this.speed * dt;
        this.dist += M_PER_S * this.speedUp * dt;
        this.score();
        // (in steps of at most STEP_PX, his way and the earth's)
        const n = Math.max(1, Math.ceil(Math.max(step, MOVE.top * s.bodyWidth * dt) / STEP_PX));
        for (let i = 0; i < n; i++) {
            this.steer(dt / n);
            this.earth(now, step / n, dt / n);
            if (this.state === 'run' && this.touch())
                return;
        }
        this.lifts(dt);
        this.follow();
        this.host.moveTo(this.x);
        if (this.host.face && Math.abs(this.vx) > 0.3 * MOVE.top * s.bodyWidth && (this.vx < 0) !== this.facingLeft) {
            this.facingLeft = this.vx < 0;   // (he looks where he goes, once he's well on his way)
            this.host.face(this.facingLeft);
        }
    }

    // His x for h seconds: eased to where you point (keys move it), braking in time, his speed
    // changing no more than his acceleration allows (if where you point jumps nearer than he can
    // stop, he goes a little past it and comes back, as a body would)
    steer(h) {
        const s = this.s, top = MOVE.top * s.bodyWidth, accel = MOVE.accel * s.bodyWidth, w = MOVE.omega;
        if (this.keyDir !== 0)
            this.aimX = (this.aimX === null ? this.x : this.aimX) + this.keyDir * MOVE.keys * top * h;
        if (this.aimX !== null)
            this.aimX = clamp(this.aimX, s.minX, s.maxX);
        this.x = clamp(this.x, s.minX, s.maxX);
        const target = this.aimX === null ? this.x : this.aimX, d = target - this.x;
        let want = this.vx + (w * w * d - 2 * w * this.vx) * h;
        const brake = Math.sqrt(2 * accel * Math.abs(d)) * 0.98;   // (as fast as can still stop there)
        if (want * d > 0 && Math.abs(want) > brake)
            want = Math.sign(d) * brake;
        want = clamp(want, -top, top);
        let v = clamp(want, this.vx - accel * h, this.vx + accel * h);
        let x = this.x + v * h;
        if ((Math.abs(target - x) < 1 && Math.abs(v) < 20) || ((target - this.x) * (target - x) < 0 && Math.abs(v) <= accel * h * 1.5)) {
            x = target;   // (there, he's there: not creeping on in a spring's tail)
            v = 0;
        }
        if (x <= s.minX || x >= s.maxX) {   // (the stage's side: up to it, no bounce)
            x = clamp(x, s.minX, s.maxX);
            v = 0;
        }
        this.x = x;
        this.vx = v;
        const lean = MOVE.lean * clamp(v / top, -1, 1);
        this.lean += (lean - this.lean) * (1 - Math.exp(-MOVE.leanOmega * h));
        if (Math.abs(this.lean) < 0.001)
            this.lean = 0;
        this.turn = -this.lean;
    }

    // The earth goes up step px in h seconds: what's in it, his tunnel, the clods, what comes
    earth(now, step, h) {
        const s = this.s, B = s.bodyHeight, run = this.state === 'run';
        let k = 0;
        for (let i = 0; i < this.things.length; i++) {
            const th = this.things[i];
            if (th.kind === 'glow' || th.kind === 'plus') {
                this.things[k++] = th;
                continue;
            }
            th.y -= step;
            if (th.kind === 'clod') {
                th.vy += CLOD_FALL * B * h;
                th.x += th.vx * h;
                th.y += th.vy * h;
                if (now - th.born > CLOD_MS)
                    continue;
            } else if (th.kind === 'beetle') {
                th.x += th.dir * BEETLE_PACE * s.bodyWidth * h;
                if (th.x < 0 || th.x + th.w > s.width) {   // (it turns at the sides)
                    th.x = clamp(th.x, 0, Math.max(0, s.width - th.w));
                    th.dir = -th.dir;
                    th.variant = th.dir > 0 ? 1 : 0;
                }
                th.frame = Math.floor(now / LEGS_MS) % FRAMES.beetle;
            } else if (th.kind === 'worm')
                th.frame = Math.floor((now + th.seed) / WORM_MS) % FRAMES.worm;
            else if (th.kind === 'cookie')
                th.frame = Math.floor((now + th.seed) / TWINKLE_MS) % FRAMES.cookie;
            if (th.y + th.h > -B)
                this.things[k++] = th;
        }
        this.things.length = k;
        let r = 0;
        for (let i = 0; i < this.rows.length; i++) {
            const row = this.rows[i];
            row.top -= step;
            row.bottom -= step;
            if (row.bottom > 0)
                this.rows[r++] = row;
        }
        this.rows.length = r;
        if (this.lastBottom !== null)
            this.lastBottom -= step;
        // decoration, here and there
        this.decorDue -= step;
        if (this.decorDue <= 0) {
            const d = this.add(pick(DECORS[this.layer]), 0, s.height + B * 0.2);
            d.x = rnd(0, Math.max(0, s.width - d.w));
            this.decorDue = rnd(0.5, 1.2) * B;
        }
        if (!run)
            return;
        // his tunnel, along the path he takes: a piece each time he's moved on from the last one
        // (it went up with the earth), as many between as a quick move takes
        let last = this.lastTunnel;
        if (!last)
            last = this.lastTunnel = this.tunnelAt(this.x, this.cy);
        for (;;) {
            const lx = last.x + last.w / 2, ly = last.y + last.h / 2, dx = this.x - lx, dy = this.cy - ly;
            const far = Math.hypot(dx / (TUNNEL_STEP * last.w), dy / (TUNNEL_STEP * last.h));
            if (far < 1)
                break;
            last = this.lastTunnel = this.tunnelAt(lx + dx / far, ly + dy / far);
        }
        // clods off his paws
        const top = MOVE.top * s.bodyWidth;
        this.clodDue += CLODS * (1 + Math.min(1, Math.abs(this.vx) / top)) * h;
        while (this.clodDue >= 1) {
            this.clodDue -= 1;
            const side = Math.random() < 0.5 ? -1 : 1, c = this.add('clod', 0, 0);
            c.x = this.x + side * rnd(0.15, 0.4) * s.bodyWidth - c.w / 2;
            c.y = this.cy + B * 0.35;
            c.vx = side * rnd(0.4, 1.2) * s.bodyWidth + 0.3 * this.vx;
            c.vy = -rnd(1.6, 2.6) * B;
            c.born = now;
        }
        // what comes
        this.nextRow -= step;
        if (this.nextRow <= 0)
            this.row();
    }

    // A row from below: a way through within his reach, the rest walled; or a beetle alone
    row() {
        const s = this.s, B = s.bodyHeight, bw = s.bodyWidth, W = s.width;
        const top = s.height + B * 0.25;
        // (the earth between the row above and this one, as it is: what he has to get to its way
        // through; the row above may be off the stage by now)
        const clear = this.lastBottom === null ? s.height : top - this.lastBottom;
        const id = ++this.rowId;
        let bottom = top;
        if (this.layer === 'rock' && this.dist >= BEETLE_FROM && !this.lastBeetle && Math.random() < BEETLE_EVERY) {
            const b = this.add('beetle', 0, top);
            b.x = rnd(0, Math.max(0, W - b.w));
            b.dir = Math.random() < 0.5 ? -1 : 1;
            b.variant = b.dir > 0 ? 1 : 0;
            b.row = id;
            this.rows.push({ id: id, top: top, bottom: top + b.h, gapL: 0, gapR: W, beetle: true, alone: true, clear: clear });
            this.lastBottom = top + b.h;
            this.lastBeetle = true;
            // (after it he may be anywhere, dodging it: the next way through is mid-stage, and the
            // earth before it enough for him to get there from either side, at the speed by then)
            this.nextRow = b.h + Math.max(rnd(CLEAR[0], CLEAR[1]) * B,
                                          BOX_H * B + (W / 2 - s.minX) * this.speed * 1.05 / (MOVE.top * bw * REACH));
            return;
        }
        // its way through: within reach of the last one (brought inside the stage first: it may have narrowed)
        this.lastGap = clamp(this.lastGap, s.minX, s.maxX);
        const reach = MOVE.top * bw * Math.max(0, clear - BOX_H * B) / this.speed * REACH;
        const gw = (GAP + rnd(0, GAP_MORE)) * bw;
        const mid = this.lastBeetle ? W / 2 : clamp(rnd(this.lastGap - reach, this.lastGap + reach),
                                                    Math.max(s.minX, this.lastGap - reach), Math.min(s.maxX, this.lastGap + reach));
        const gapL = mid - gw / 2, gapR = mid + gw / 2;
        const wall = (a, b, left) => {   // (from a to b: one long thing from the side, or rocks packed)
            if (b - a < bw * BOX_W)
                return;
            const longs = LONG[this.layer];
            if (longs.length && Math.random() < 0.55) {
                const kind = pick(longs), th = this.add(kind, 0, top);
                th.x = a;
                th.w = b - a;
                if (kind === 'pipe')
                    th.variant = left ? 0 : 1;   // (its open end towards the way through)
                else if (kind === 'root')
                    th.variant = int(0, 2) + (left ? 0 : 3);   // (thick where it comes from: its side)
                th.row = id;
                bottom = Math.max(bottom, top + th.h);
                return;
            }
            // (from the side inwards, never into the way through: what's left by it only widens it)
            const kinds = ROCKS[this.layer];
            for (let room = b - a; room > 0;) {
                let kind = pick(kinds);
                if (DIG_KINDS[kind][0] * B > room)
                    kind = kinds.filter(k => DIG_KINDS[k][0] * B <= room)[0];
                if (!kind)
                    break;
                const th = this.add(kind, 0, top + rnd(0, 0.15) * B);
                th.x = left ? b - room : a + room - th.w;
                th.row = id;
                bottom = Math.max(bottom, th.y + th.h);
                room -= th.w + rnd(0, SPACING) * bw;
            }
        };
        wall(0, gapL, true);
        wall(gapR, W, false);
        if (Math.random() < COOKIE_EVERY) {
            const c = this.add('cookie', 0, top);
            c.x = clamp(mid, s.minX, s.maxX) - c.w / 2;
            c.row = id;
        }
        this.rows.push({ id: id, top: top, bottom: bottom, gapL: gapL, gapR: gapR, beetle: false, alone: false, clear: clear });
        this.lastBottom = bottom;
        this.lastGap = mid;
        this.lastBeetle = false;
        this.nextRow = bottom - top + rnd(CLEAR[0], CLEAR[1]) * B;
    }

    // a piece of his tunnel, its middle at (x, y)
    tunnelAt(x, y) {
        const t = this.add('tunnel', 0, 0);
        t.w = this.s.bodyWidth * 0.95;
        t.x = x - t.w / 2;
        t.y = y - t.h / 2;
        return t;
    }

    add(kind, x, y) {
        const B = this.s.bodyHeight, k = DIG_KINDS[kind];
        const th = { kind: kind, x: x, y: y, w: k[0] * B, h: k[1] * B, frame: 0, variant: int(0, (DIG_VARIANTS[kind] || 1) - 1),
                     seed: int(0, 1000), slot: this.freeSlot() };
        this.things.push(th);
        return th;
    }

    // his lamp's light round him
    follow() {
        const g = this.glowTh;
        if (!g)
            return;
        g.x = this.x - g.w / 2 + this.lean * 0.6;
        g.y = this.cy - this.s.bodyHeight * 0.55 - g.h / 2;
    }

    // a touch: a cookie taken, or the end (true)
    touch() {
        const s = this.s, w = s.bodyWidth * BOX_W / 2, hh = s.bodyHeight * BOX_H / 2;
        const box = [this.x - w, this.cy - hh, this.x + w, this.cy + hh];
        for (let i = this.things.length - 1; i >= 0; i--) {
            const th = this.things[i];
            if (DECOR.indexOf(th.kind) >= 0)
                continue;
            if (GRAB.indexOf(th.kind) >= 0) {
                if (th.x < box[2] && th.x + th.w > box[0] && th.y < box[3] && th.y + th.h > box[1])
                    this.grab(th);
                continue;
            }
            const sh = Math.min(th.w, th.h) * SHRINK;   // (a root's or a pipe's ends: where they're drawn)
            if (th.x + sh < box[2] && th.x + th.w - sh > box[0] && th.y + sh < box[3] && th.y + th.h - sh > box[1]) {
                this.over(th.kind);
                return true;
            }
        }
        return false;
    }

    bumped() {
        this.vx = 0;
        this.keyDir = 0;
        this.setPose('bump');
    }

    ended() {
        this.rows.length = 0;
        this.glowTh = null;
    }
}
