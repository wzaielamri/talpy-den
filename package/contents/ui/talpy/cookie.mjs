// A cookie for the big Talpy (talpy.mjs), on its stage. Double-click the
// stage a little away from it and a cookie pops up there, mostly chocolate
// chip, now and then another flavour (FLAVOURS in actions.mjs). Talpy sees
// it, jumps out of its burrow and goes after it on its feet. A cookie you
// don't hold floats down to the floor, a light one (it hops a little as it
// pops up; let go of it as you move it: it flies on the way you threw it),
// lands with a little squash and bounce; pick it up again whenever you like. Drag it about and Talpy
// follows, hold it up out of reach and it hops and stretches for it all the
// same (lower it a little as it jumps: it has it), within reach it jumps
// for it and takes it out of your hand. Once it has it, it eats it, tastes
// it its way, says thanks now and then, and digs in where it is. Kept away
// too long, it gets cross for a moment. The host draws the cookie
// (drawCookie in talpy.mjs) where `cookie` says and moves Talpy where this
// says. No tally, no prizes: every cookie is just a treat.
//
// Nothing here runs without a cookie: the host ticks it only while `on`.
//
//   const game = new CookieGame(talpy, host);
//   double-click at (x, y), stage pixels: game.place(x, y) (false: too close to it, or it's eating)
//   the cookie pressed, moved, let go: game.grab(x, y), game.drag(x, y), game.drop()
//   every tick while game.on: game.tick(now), after talpy.tick(now)
//   you pulled at Talpy or picked it up: game.picked(); it's down again (landed, or back
//     in its burrow): game.landed()
//
// host: {
//   stage(): { width, ground, unit (px a box unit), bodyWidth, bodyHeight, minX, maxX },
//   px(): where Talpy is (its centre); moveTo(x): it's there now (and digs nowhere else);
//   face(left): it turns;
//   say(what, flavour): its words for 'spot' 'wake' 'gimme' 'cross' 'aww', and once it has it 'yum';
//   leaveHole(open): it left its burrow (that open, as setHeld): draw that hole where it was,
//     until fillHole();
//   changed(): what shows changed (on, chasing, the cookie);
//   instant(): no running about (less motion): it just has it }
//
// Plain ES2017 (see paths.mjs).

import { pickFlavour } from './actions.mjs';

const R = 7;                 // the cookie's radius (box units)
const REACH = 26;            // how high its middle may be (box units over the floor) to take it standing,
const LEAP = 46;             // or jumping
const CROSS_MS = 9000;       // after it that long (and you keep moving it): cross for a moment
const POP_MS = 300;          // a new one pops up (grows) that long, then floats down
const HOP = 55;              // as it pops up it hops up a little (box units/s)
const G = 350;               // how fast it falls (box units/s²): a light one,
const AIR_S = 0.7;           // the air holding it back (it falls at most G × AIR_S)
const BOUNCE = 0.45;         // how much of its speed it bounces back with off the floor,
const SETTLE = 28;           // and slower than that (box units/s) it just stays down

const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
const outBack = p => {
    const c1 = 1.70158, c3 = c1 + 1;
    return 1 + c3 * Math.pow(p - 1, 3) + c1 * Math.pow(p - 1, 2);
};

export class CookieGame {
    constructor(talpy, host) {
        this.talpy = talpy;
        this.host = host;
        // { x, y (its middle, stage px), r, scale, angle (deg), sx, sy (squashed as it lands), held, flavour,
        //   vx, vy (px/s, falling), lean (its swing), landAt, hit (how hard it landed, 0 to 1), rock (-1, 1) }; null: none
        this.cookie = null;
        this.state = '';         // spot chase leap cross held eat, '' (nothing going on)
        this.on = false;         // something goes on: the host ticks it
        this.chasing = false;    // Talpy is on its feet after it (a host draws it live)
        this.now = 0;
        this.last = 0;
        this.v = 0;              // how fast it runs (px/s, + to the right)
        this.since = 0;          // when the state began
        this.chaseAt = 0;        // when it set off (cross after a while)
        this.standAt = 0;        // when it stood still under it
        this.leapAt = -1e9;      // when it last jumped for it
        this.tries = 0;          // jumps in a row for one out of reach
        this.movedAt = -1e9;     // when you last moved the cookie
        this.saidAt = {};        // when it last said what (not over and over)
        this.grip = null;        // where you hold it, from its middle
        this.dragV = 0;          // how fast you move it (px/s), for its swing and as you let go
        this.dragVy = 0;
        this.dragAt = 0;
        this.holeLeft = false;   // a hole it left shows: filled once it digs in again
        this.lastFlavour = '';   // (of the one it just had: its words)
    }

    // Where a cookie can be: over the floor, on the stage, never where Talpy
    // can't get under it
    fit(x, y) {
        const g = this.host.stage(), r = R * g.unit, reach = g.bodyWidth * 0.4;
        return { x: clamp(x, Math.max(r, g.minX - reach), Math.min(g.width - r, g.maxX + reach)), y: clamp(y, r, g.ground - r) };
    }

    // Where the cookie is from Talpy's eyes: ahead, and up (-) or down
    look() {
        const c = this.cookie, g = this.host.stage();
        if (!c)
            return [0, 0];
        const ahead = (c.x - this.host.px()) * (this.talpy.facingLeft ? -1 : 1) / g.bodyWidth;
        return [clamp(ahead * 2, -1.8, 1.8), clamp((22 - (g.ground - c.y) / g.unit) / 12, -2, 1.4)];
    }

    // (what, of the cookie that's out or just eaten)
    say(what, every) {
        if (every && this.now - (this.saidAt[what] || -1e9) < every)
            return;
        this.saidAt[what] = this.now;
        this.host.say(what, this.cookie ? this.cookie.flavour : this.lastFlavour);
    }

    // ------------------------------------------------------------ you

    // A double-click at (x, y): a cookie there (one already out moves there)
    place(x, y) {
        const t = this.talpy, g = this.host.stage();
        if (t.held || this.state === 'eat')
            return false;
        // (on it or right beside it: that's petting it)
        if (Math.abs(x - this.host.px()) < g.bodyWidth * 0.75 && y > g.ground - g.bodyHeight * 1.4)
            return false;
        const at = this.fit(x, y);
        const was = this.cookie;
        // (at: when it popped up, from its first tick: the game's clock stood still while none was out)
        this.cookie = { x: at.x, y: at.y, r: R * g.unit, scale: 0, angle: 0, sx: 1, sy: 1, held: false, at: -1,
                        flavour: was ? was.flavour : pickFlavour(), vx: 0, vy: -HOP * g.unit, lean: 0, landAt: -1e9, hit: 0, rock: 1 };
        this.grip = null;
        this.on = true;
        if (was) {
            this.movedAt = this.now;
            this.host.changed();
            return true;
        }
        this.host.face(at.x < this.host.px());
        this.say(t.mood === 'done' ? 'wake' : 'spot');
        if (this.host.instant()) {
            this.host.moveTo(clamp(at.x, g.minX, g.maxX));
            this.caught(false);
            return true;
        }
        this.state = 'spot';
        t.seeCookie(this.look(), ok => {
            if (ok && this.state === 'spot')
                this.go();
        });
        this.host.changed();
        return true;
    }

    // You took the cookie at (x, y): false if there's none to take
    grab(x, y) {
        const c = this.cookie;
        if (!c)
            return false;
        this.grip = { x: c.x - x, y: c.y - y };
        this.dragAt = Date.now();
        this.dragV = this.dragVy = 0;
        c.held = true;
        c.vx = c.vy = c.hit = 0;
        return true;
    }

    drag(x, y) {
        const c = this.cookie;
        if (!c || !this.grip)
            return;
        const at = this.fit(x + this.grip.x, y + this.grip.y), now = Date.now(), ms = Math.max(16, now - this.dragAt);
        this.dragV = 0.5 * this.dragV + 0.5 * (at.x - c.x) * 1000 / ms;
        this.dragVy = 0.5 * this.dragVy + 0.5 * (at.y - c.y) * 1000 / ms;
        this.dragAt = now;
        c.x = at.x;
        c.y = at.y;
        this.movedAt = this.now;
        this.host.changed();
    }

    // (it flies on from there the way your hand moved it, and floats down)
    drop() {
        const c = this.cookie;
        if (c && c.held) {
            const g = this.host.stage(), most = g.bodyWidth * 5, moving = Date.now() - this.dragAt <= 80;
            c.held = false;
            c.at = this.now - POP_MS;   // (popped up already)
            c.vx = moving ? clamp(this.dragV, -most, most) : 0;
            c.vy = moving ? clamp(this.dragVy, -most, most) : 0;
        }
        this.grip = null;
    }

    // You pulled at Talpy (talpy.tug) or picked it up (talpy.setHeld): it
    // goes after it again once down
    picked() {
        if (!this.on)
            return;
        this.chasing = false;
        this.v = 0;
        this.holeLeft = false;   // (the host fills it as it lands)
        this.state = this.cookie ? 'held' : '';
        this.on = this.cookie !== null;
        this.host.changed();
    }

    // Down again: put down on the floor (talpy.land with stayOut), straight
    // after it; back in its burrow (you let go of it as it hung on), it sees
    // it again first
    landed() {
        if (this.state !== 'held' || !this.cookie)
            return;
        const t = this.talpy;
        this.host.face(this.cookie.x < this.host.px());
        if (t.onFloor) {
            this.go();
            return;
        }
        this.state = 'spot';
        t.seeCookie(this.look(), ok => {
            if (ok && this.state === 'spot')
                this.go();
        });
        this.host.changed();
    }

    // ------------------------------------------------------------ Talpy

    // Out of its burrow and after it (out already: on its feet at once)
    go() {
        const left = this.talpy.chase();
        if (left > 0) {
            this.host.leaveHole(left);
            this.holeLeft = true;
        }
        this.state = 'chase';
        this.chasing = true;
        this.since = this.chaseAt = this.standAt = this.now;
        if (this.talpy.chased !== 'out')
            this.since -= 450;
        this.v = 0;
        this.host.changed();
    }

    tick(now) {
        const dt = this.last ? clamp(now - this.last, 0, 100) / 1000 : 0;
        this.last = this.now = now;
        const c = this.cookie;
        if (c) {
            // it pops up, and swings as you move it (or it flies)
            const g = this.host.stage();
            if (c.at < 0)
                c.at = now;
            const p = clamp((now - c.at) / POP_MS, 0, 1);
            c.scale = p >= 1 ? 1 : outBack(p);
            if (Date.now() - this.dragAt > 60) {
                this.dragV *= Math.exp(-dt / 0.12);
                this.dragVy *= Math.exp(-dt / 0.12);
            }
            const swing = clamp((c.held ? this.dragV : c.vx) / g.unit * 0.12, -35, 35);
            c.lean += (swing - c.lean) * (1 - Math.exp(-dt / 0.08));
            if (!c.held && now - c.at >= POP_MS)
                this.fall(dt, c, g);
            // landed: squashed a little (springing back round) and rocking, both settling
            const s = (now - c.landAt) / 1000, squash = c.hit * Math.exp(-s / 0.09) * Math.cos(s * 2 * Math.PI / 0.3);
            c.sx = 1 + 0.14 * squash;
            c.sy = 1 - 0.2 * squash;
            c.angle = c.lean + c.rock * 9 * c.hit * Math.exp(-s / 0.22) * Math.sin(s * 2 * Math.PI / 0.26);
        }
        // it digs in again: the hole it left is filled
        if (this.state === 'eat' && this.holeLeft && this.talpy.holeOpen) {
            this.holeLeft = false;
            this.host.fillHole();
        }
        if (c && !c.held && c.vx === 0) {   // (a stage that got narrower brings it back in)
            c.x = this.fit(c.x, c.y).x;
        }
        // a look at it (or a landing) cut short by something else: it goes after it all the same
        const t = this.talpy;
        if (c && !this.chasing && (this.state === 'spot' || this.state === 'held') && t.run === null && !t.held && !t.tugging
            && !t.pushing)
            this.go();
        if (this.chasing && c)
            this.follow(dt, c);
        this.host.changed();
    }

    // Not in your hand: floats down to the floor (the air holds it back),
    // bounces a little, less each time, and slides to a stop if it came down
    // on the move (it stays where Talpy can get it)
    fall(dt, c, g) {
        const floor = g.ground - c.r;
        if (c.y < floor || c.vy < 0) {
            const air = Math.exp(-dt / AIR_S);
            c.vy = (c.vy + G * g.unit * dt) * air;
            c.vx *= air;
            c.y += c.vy * dt;
            if (c.y < c.r) {   // (thrown up to the stage's top)
                c.y = c.r;
                c.vy = Math.max(0, c.vy);
            }
            if (c.y >= floor) {
                const speed = c.vy / g.unit;
                c.y = floor;
                c.landAt = this.now;
                c.hit = Math.min(1, speed / 180);
                c.rock = c.vx > 0 ? 1 : c.vx < 0 ? -1 : Math.random() < 0.5 ? -1 : 1;
                c.vy = speed > SETTLE ? -c.vy * BOUNCE : 0;
            }
        } else {
            c.vx *= Math.exp(-dt / 0.15);
        }
        if (c.vx !== 0) {
            const x = this.fit(c.x + c.vx * dt, c.y).x;
            if (x !== c.x + c.vx * dt)
                c.vx = 0;
            c.x = x;
            if (Math.abs(c.vx) < g.unit)
                c.vx = 0;
        }
    }

    follow(dt, c) {
        const t = this.talpy, g = this.host.stage(), now = this.now;
        const up = (g.ground - c.y) / g.unit;   // box units over the floor
        let px = this.host.px();
        if (this.state === 'chase' && now - this.since < 450) {
            t.chaseAs('out', this.look());   // (out of its burrow first)
            return;
        }
        if (this.state === 'leap') {
            const ms = now - this.since;
            if (ms > 200 && ms < 560 && Math.abs(c.x - px) < g.bodyWidth * 0.6 && up <= LEAP + 4) {
                this.caught(true);
                return;
            }
            if (ms < 800) {
                // (drifts its way in the air)
                const d = clamp(c.x, g.minX, g.maxX) - px;
                this.host.moveTo(px + clamp(d, -g.bodyWidth * 2 * dt, g.bodyWidth * 2 * dt));
                t.chaseAs(this.tries > 0 ? 'reach' : 'leap', this.look());
                return;
            }
            this.state = 'chase';
            this.standAt = now;
            if (this.tries > 0 && this.tries % 4 === 0) {
                this.state = 'cross';
                this.since = now;
                t.chaseAs('pout');
                this.say('cross', 4000);
                return;
            }
            this.say('aww', 4000);
        }
        if (this.state === 'cross') {
            if (now - this.since < 1400) {
                t.chaseAs('pout');
                return;
            }
            this.state = 'chase';
            this.chaseAt = this.standAt = now;
        }
        // Running there: quicker the further it is, turning round when it's behind
        const max = g.bodyWidth * 4.2, acc = g.bodyWidth * 16;
        const d = clamp(c.x, g.minX, g.maxX) - px;
        this.v += clamp(clamp(d * 5, -max, max) - this.v, -acc * dt, acc * dt);
        px = clamp(px + this.v * dt, g.minX, g.maxX);
        this.host.moveTo(px);
        const running = Math.abs(this.v) > g.bodyWidth * 0.6;
        const left = Math.abs(this.v) > g.bodyWidth * 0.25 ? this.v < 0
                   : Math.abs(c.x - px) > g.bodyWidth * 0.1 ? c.x < px : t.facingLeft;
        if (left !== t.facingLeft)
            this.host.face(left);
        const close = Math.abs(c.x - px) < g.bodyWidth * 0.55;
        // (to take it standing it steps right behind it, as far as it can go:
        // the cookie, drawn over it, turns into the one in its hands)
        if (close && up <= REACH && Math.abs(clamp(c.x, g.minX, g.maxX) - px) < g.bodyWidth * 0.12) {
            this.caught(false);
            return;
        }
        if (running || !close)
            this.standAt = now;
        // under it: it jumps for it; out of reach it tries all the same, now
        // and then, begging in between (and gets cross after a few)
        const high = up > LEAP;
        if (close && !running && now - this.standAt > 250 && now - this.leapAt > (high ? 900 : 0)) {
            this.state = 'leap';
            this.since = this.leapAt = now;
            this.v = 0;
            this.tries = high ? this.tries + 1 : 0;
            t.chaseAs(high ? 'reach' : 'leap', this.look());
            if (high && this.tries === 1)
                this.say('gimme', 6000);
            return;
        }
        if (close && !running && high) {
            t.chaseAs('beg', this.look());
        } else {
            t.chaseAs(Math.abs(this.v) > g.bodyWidth * (close ? 0.2 : 0.6) ? 'run' : 'stand', this.look());   // (its last steps too)
        }
        // kept away too long, you moving it about all the while
        if (now - this.chaseAt > CROSS_MS && now - this.movedAt < 1500) {
            this.state = 'cross';
            this.since = now;
            this.v = 0;
            t.chaseAs('pout');
            this.say('cross');
        }
    }

    // It has it (inAir: out of the air, or out of your hand)
    caught(inAir) {
        const flavour = this.lastFlavour = this.cookie.flavour;
        this.cookie = null;
        this.grip = null;
        this.chasing = false;
        this.v = 0;
        this.state = 'eat';
        this.talpy.eat(flavour, inAir, () => this.ended());
        this.say('yum');
        this.host.changed();
    }

    // (eaten, or you picked it up meanwhile)
    ended() {
        if (this.state !== 'eat')
            return;
        this.state = '';
        this.on = this.cookie !== null;
        if (this.holeLeft && !this.talpy.held)
            this.host.fillHole();   // (it didn't dig in; held, it's filled as it lands)
        this.holeLeft = false;
        this.host.changed();
    }
}
