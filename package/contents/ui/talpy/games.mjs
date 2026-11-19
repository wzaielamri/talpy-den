// Games with the big Talpy (talpy.mjs) on his stage: four quick clicks on him
// (he laughs, "Let's play!") or Play with Talpy in the menu start one, by
// name or picked at random (pickGame). The host ends one at once (stop) on
// Esc, a click outside the stage, a chat that needs you, or the stage going
// out of sight. The host ticks a game only while it's on, draws the holes it
// opens (drawHole in talpy.mjs: holes, each {x, open}, stage px and 0 to 1)
// under Talpy, and moves Talpy where it says.
//
// Peekaboo lasts 10 to 30 s and ends by itself: no scores, it's just play.
// Talpy's Run (Run, below) is a run you can lose: one bump ends it, with how
// far he got and the best (the only number kept).
//
//   const game = pickGame(talpy, host, name); game.start(now, wake) (name: 'peekaboo', 'run', '' at random)
//   every tick while game.on: game.tick(now), after talpy.tick(now)
//   a click on Talpy: game.hit() (true: the game took it)
//   game.stop(): over now (Talpy comes up where he is)
//
// host: {
//   stage(): { width, height, ground, unit (px a box unit), bodyWidth, bodyHeight, minX, maxX },
//   px(): where Talpy is (his centre); moveTo(x): he's there now (underground: no digging across);
//   say(what): his words for 'got' (you caught him), 'fun' (the game's over), 'bump', 'best' (the run's);
//   changed(): what shows changed (on, the holes; a run: every tick it moves);
//   the scored games' (scored.mjs): best(name): metres; saveBest(name, m): a new best; grow(on): the
//   stage taller (game.stageGu grid units, the status faded) for the game, or back; runOk(): false
//   where the Run and Deep Dig aren't offered }
//
// Plain ES2017 (see paths.mjs).

import { ACTIONS, COOKIE } from './actions.mjs';
import { FLAP_FRAMES, FRAMES } from './talpy.mjs';
import { Scored, DECOR as SCORED_DECOR, GRAB as SCORED_GRAB, SCORED as SCORED_GAMES } from './scored.mjs';
import { Dig } from './dig.mjs';

// (scored.mjs's, for the hosts that import this one: an export per line, GNOME 43's port can't re-export)
export const DECOR = SCORED_DECOR;
export const GRAB = SCORED_GRAB;
export const SCORED = SCORED_GAMES;

const rnd = (a, b) => a + Math.random() * (b - a);
const int = (a, b) => Math.floor(rnd(a, b + 1));
const sine = p => 0.5 - 0.5 * Math.cos(Math.PI * Math.max(0, Math.min(1, p)));

export const GAMES = ['peekaboo', 'run', 'dig'];

// A game by name, else at random; never the run where the host can't have it
export function pickGame(talpy, host, name) {
    const can = GAMES.filter(g => SCORED.indexOf(g) < 0 || !host.runOk || host.runOk());
    const which = can.indexOf(name) >= 0 ? name : can[Math.floor(Math.random() * can.length)];
    return which === 'run' ? new Run(talpy, host) : which === 'dig' ? new Dig(talpy, host) : new Peekaboo(talpy, host);
}

const OPEN_MS = 320;         // holes open (and close) that long
const POP_MS = 450;          // he takes that long to pop up (talpy.mjs DEPTH easing)
const MAX_MS = 26000;        // the game's over by then, whatever the rounds
// (a pose of his the game holds until it moves him on: Talpy's own end of a
// pose would bring him back up in the hole he's in, before he's off to the next)
const HOLD = 60000;

// Peekaboo holes: three holes open on the stage and he pops out of one at
// random; click him before he ducks. He's quicker each round, and after a few
// he dances and the holes close.
export class Peekaboo {
    constructor(talpy, host) {
        this.name = 'peekaboo';
        this.talpy = talpy;
        this.host = host;
        this.on = false;
        this.holes = [];         // [{ x, open }]: stage px, 0 (shut) to 1
        this.state = '';         // open, down, up, caught, ducked, dance, close
        this.at = 0;             // the hole he's in
        this.round = 0;
        this.rounds = 0;
        this.until = 0;          // the state's over then
        this.startAt = 0;
        this.now = 0;
        this.brain = true;       // (his own doings, back once it's over)
    }

    // (it's on from the click that starts it: the next clicks are the game's,
    // also while he still laughs, or yawns when he was woken up for it)
    start(now, wake) {
        const s = this.host.stage(), t = this.talpy;
        const lo = s.minX, hi = Math.max(s.minX, s.maxX);
        const xs = [lo + (hi - lo) * 0.12, lo + (hi - lo) * 0.5, lo + (hi - lo) * 0.88];
        // (the hole nearest him is his own burrow, where he is)
        const px = this.host.px();
        let near = 0;
        for (let i = 1; i < 3; i++) {
            if (Math.abs(xs[i] - px) < Math.abs(xs[near] - px))
                near = i;
        }
        xs[near] = px;
        this.holes = xs.map(x => ({ x: x, open: 0 }));
        this.at = near;
        this.on = true;
        this.now = now;
        this.startAt = now;
        this.round = 0;
        this.rounds = int(6, 8);
        this.brain = t.brainOn;
        t.brainOn = false;
        t.cancel();
        const opening = ACTIONS[wake ? 'yawn' : 'laugh'].steps(t.words);
        const openingMs = opening.reduce((ms, step) => ms + (step.t || 600), 0);
        t.play({ steps: () => opening.concat([{ depth: 'hidden', eyes: 'closed', mouth: 'smile', plume: '', t: OPEN_MS + 200 }]) }, null, false);
        this.set('open', openingMs + OPEN_MS + 250);
        this.host.changed();
    }

    // He's quicker each round: up so long (ms)
    upMs() {
        return Math.max(520, 1350 * Math.pow(0.84, this.round));
    }

    set(state, ms) {
        this.state = state;
        this.since = this.now;
        this.until = this.now + ms;
    }

    tick(now) {
        if (!this.on)
            return;
        this.now = now;
        const t = this.talpy;
        // the holes open, or close
        const p = sine((now - this.since) / OPEN_MS);
        if (this.state === 'open')
            this.setOpen(p);
        else if (this.state === 'close')
            this.setOpen(1 - p);
        // (down between pops he stays down: a pose of his that ends would bring
        // him back up in the hole he's in, before he's off to the next)
        if (!t.run && (this.state === 'open' || this.state === 'caught' || this.state === 'ducked' || this.state === 'down'))
            t.play({ steps: () => [{ depth: 'hidden', eyes: 'closed', mouth: 'smile', plume: '', t: HOLD }] }, null, false);
        if (now < this.until)
            return;
        switch (this.state) {
        case 'open':
        case 'caught':
        case 'ducked':
            if (this.round >= this.rounds || now - this.startAt > MAX_MS) {
                this.finish();
                return;
            }
            this.set('down', rnd(350, 900) * Math.max(0.55, 1 - this.round * 0.08));
            return;
        case 'down': {
            // another hole, underground, then up he pops
            let next = int(0, 2);
            if (next === this.at)
                next = (next + int(1, 2)) % 3;
            this.at = next;
            this.host.moveTo(this.holes[next].x);
            const up = this.upMs();
            t.play({ steps: () => [{ depth: 'high', eyes: 'happy', mouth: 'open', plume: 'flick', look: [Math.random() < 0.5 ? -1.4 : 1.4, -0.4],
                                     t: HOLD }] }, null, false);
            this.set('up', POP_MS + up);
            return;
        }
        case 'up':   // too slow: he ducks, giggling, and stays down till he's up in the next hole
            t.play({ steps: w => [{ depth: 'hidden', eyes: 'squint', mouth: 'smile',
                                    fx: [['text', 30, 30, { text: w('hihi'), size: 6, dy: -8, dur: 1 }]], t: HOLD }] }, null, false);
            this.round += 1;
            this.set('ducked', 420);
            return;
        case 'dance':
            this.set('close', OPEN_MS);
            return;
        case 'close':
            this.end();
            return;
        }
    }

    // You clicked him: caught while he's up; true: the game took the click
    hit() {
        if (!this.on)
            return false;
        if (this.state !== 'up' || this.now - this.since < POP_MS * 0.4)
            return true;   // (down, or only just coming up: nothing, and no petting meanwhile)
        this.talpy.play({ steps: () => [
            { depth: 'high', eyes: 'wide', mouth: 'o', plume: 'up', body: 'jolt', fx: [['sparkle', 32, 18, { dy: -10 }], ['sparkle', 22, 22, { dy: -8, delay: 0.1 }]], t: 380 },
            { depth: 'hidden', eyes: 'happy', mouth: 'open', t: HOLD }] }, null, false);   // (down till he's up in the next hole)
        this.host.say('got');
        this.round += 1;
        this.set('caught', 740);
        return true;
    }

    // The last round: he comes out of his hole and dances; then the other holes close
    finish() {
        this.talpy.play('dance', null, false);
        this.host.say('fun');
        this.set('dance', 2400);
    }

    setOpen(v) {
        let any = false;
        for (let i = 0; i < this.holes.length; i++) {
            // (his own hole stays: it's his burrow now)
            const target = this.state === 'close' && i === this.at ? 1 : v;
            if (Math.abs(this.holes[i].open - target) > 0.001) {
                this.holes[i].open = target;
                any = true;
            }
        }
        if (any)
            this.host.changed();
    }

    // Over (by itself, or at once: stop): he comes up where he is, his own doings back
    end() {
        if (!this.on)
            return;
        this.on = false;
        this.state = '';
        this.holes = [];
        const t = this.talpy;
        t.brainOn = this.brain;
        if (t.run && t.run.name !== 'dance') {
            t.cancel();
            t.apply({});
        }
        this.host.changed();
    }

    stop() {
        this.end();
    }
}

// ------------------------------------------------------------ Talpy's Run
//
// He runs in place a fifth into his stage (grown taller for it: host.grow)
// and what's on his ground comes at him from the right, faster and closer
// together the further he gets. A press (press('jump')) and he jumps over it,
// at once; held ↓ or the right button (press('dig'), release('dig')) he digs
// in up to his eyes, under a crow; what stands on the ground still hits him
// there. The first bump ends the run (Scored, scored.mjs: how far, the best,
// a press runs again, the end); hint 'start', 'dig' or ''.
// A gap between two things is never shorter than a jump at that speed and
// room to land, so a run can always be cleared. What comes changes as he goes
// (UNLOCKS: more kinds the further he gets, each in its own colours, never
// the same kind twice in a row), and the ground's grass and the sky's clouds
// (DECOR: they go by behind, never in his way) keep it from looking the same.

const RUN_READY_MS = 2000;     // the hint, and nothing on his way yet
const JUMP_MS = 620;           // up and down again, whatever the speed
const JUMP_KEEP_MS = 150;      // a press this close to his landing is kept for it (not a double-click's)
const JUMP_HIGH = 1.6;         // that many of his body's height
// his jump's own gravity (its arc, 4 h p (1 − p), is a throw up under it), in body heights a second²:
// bumped in the air, he falls with it
const GRAVITY = 8 * JUMP_HIGH / Math.pow(JUMP_MS / 1000, 2);
const STRETCH = 0.6, SQUASH = 0.7;   // as he takes off, as he lands (Talpy eases them back)
const DUST_MS = 70;            // a landing's puff: a picture that long (FRAMES.dust of them)
// his steps' length (ms, both feet) by how fast the ground goes: 500 at the start, 250 at twice it;
// a few, so his pictures are kept (the nearest to 500 / the speed-up)
const WALKS = [500, 420, 350, 290, 250];
// cookies: about one gap in four has one, on the ground in its middle (a gap of at least two
// bodies' widths and the cookie), else now and then one over a ground thing, where his body's
// middle is at his jump's top (a jump that clears it takes it)
const COOKIE_GROUND = 0.15, COOKIE_AIR = 0.1, COOKIE_ABOVE = 0.42;
const TWINKLE_MS = 140;        // a treasure's shine: a picture that long (FRAMES.cookie of them)
const DIG_MS = 1000;           // up again by himself after that
const SPEED0 = 110;            // box units a second at the start
const SPEED_UP = 1.1;          // ×, every 100 m
const SPEED_CAP = 2;           // × the start, at most
const M_PER_S = 10;            // metres a second at the start
const CROWS_FROM = 200;        // metres
// what comes from how far (metres): a rock, a boulder, a flower pot, a
// hedgehog; a tree stump; birds; a log; a heap of rocks and birds flying high
const UNLOCKS = [[0, 'pebble', 'stone', 'pot', 'hedgehog'], [100, 'stump'], [CROWS_FROM, 'crow'], [300, 'log'],
                 [400, 'pebbles', 'crowHigh']];
const TUFTS = 3;               // grass tufts at a time, at most
const CLOUDS = 2;              // clouds at a time, at most
const CLOUD_PACE = 0.35;       // × the ground's speed (far off: slower)
const FLAP_MS = 50;            // a crow's wings: a picture that long (FLAP_FRAMES a flap)
// a thing's size by his body's (w × h) and how high its bottom is above the floor
export const KINDS = {
    pebble: [0.6, 0.4, 0], stone: [0.6, 0.62, 0], pot: [0.5, 0.82, 0], pebbles: [1, 0.45, 0], hedgehog: [0.7, 0.5, 0],
    stump: [0.62, 0.55, 0], log: [1, 0.4, 0], crow: [0.75, 0.5, 0.7], crowHigh: [0.75, 0.5, 1.85],
    tuft: [0.3, 0.22, 0], cloud: [1.4, 0.5, 0], cookie: [0.6, 0.6, 0.05], plus: [0.7, 0.35, 0], dust: [0.9, 0.3, 0]
};
// how many looks a kind has (drawThing's variant: a pot's flower, a hedgehog's quills, which bird, the grass)
export const VARIANTS = { pot: 4, hedgehog: 2, crow: 3, crowHigh: 3, tuft: 3, cloud: 2, cookie: 8 };
const SHRINK = 0.15;           // a thing's hit box is that much inside its drawing, each side
const BODY_W = 0.55, BODY_H = 0.85, DUG_H = 0.3;   // his hit box, by his body's size
const RUN_POSES = {
    run: () => COOKIE.chase.run(),
    jump: () => COOKIE.chase.leap(),
    dig: () => ({ depth: 'peek', hole: 1, eyes: 'squint', mouth: 'smile', plume: 'flick', tail: 'wag' }),
    bump: () => ({ depth: 'out', hole: 0, body: 'shake', eyes: 'squint', mouth: 'o', plume: 'wild', tail: 'droop',
                   fx: [['sparkle', 26, 14, { dy: -6 }], ['sparkle', 38, 12, { dy: -6, delay: 0.15 }]] })
};

export class Run extends Scored {
    constructor(talpy, host) {
        super(talpy, host, 'run', 11);   // (11 grid units: room for his jump and the high crows over it)
        this.poses = RUN_POSES;
        this.digging = false;
        this.speed = 0;            // px a second
        this.speedUp = 1;          // × the start
    }

    reset(now) {
        const s = this.host.stage();
        this.s = s;
        this.x = s.minX + (s.maxX - s.minX) * 0.2;
        this.host.moveTo(this.x);
        if (this.host.face)
            this.host.face(false);   // (towards what comes)
        this.hint = 'start';
        this.jumpAt = -1;
        this.queued = false;
        this.digging = false;
        this.digPending = false;
        this.crows = 0;
        this.gap = 0;              // px of ground still to go before the next thing
        this.tuftGap = 0;
        this.cloudGap = 0;
        this.last = '';            // the kind that came last (not the same again)
        this.speeds();
        this.add('cloud').x = rnd(0.35, 0.75) * this.s.width;   // (a sky with a cloud from the start)
        this.setPose('run');
    }

    speeds() {
        this.speedUp = Math.min(SPEED_CAP, Math.pow(SPEED_UP, this.dist / 100));
        this.speed = SPEED0 * this.s.unit * this.speedUp;
    }

    press(what) {
        if (!this.on)
            return;
        if (this.state === 'over') {
            if (what === 'jump')
                this.again();
            return;
        }
        if (what !== 'jump' && what !== 'dig')
            return;   // (another game's keys: ← and → steer Deep Dig, nothing here)
        if (what === 'dig') {
            if (this.jumpAt < 0) {
                this.digging = true;
                this.digAt = this.now;
            } else
                this.digPending = true;   // (in the air: he digs in as he lands, while it's held)
        } else if (this.jumpAt >= 0) {
            if (this.now - this.jumpAt >= JUMP_MS - JUMP_KEEP_MS)
                this.queued = true;    // (just before he lands: kept for that moment)
        }
        else
            this.takeOff(this.now);
    }

    takeOff(now) {
        this.digging = false;
        this.jumpAt = now;
        this.talpy.stretch = STRETCH;   // (drawn out as he springs up)
    }

    release(what) {
        if (what === 'dig')
            this.digging = this.digPending = false;
    }

    // bumped in the air: he falls, faster and faster (his jump's gravity)
    overTick(now, dt) {
        if (this.lift <= 0)
            return false;
        this.fallV += GRAVITY * this.s.bodyHeight * dt;
        this.lift = Math.max(0, this.lift - this.fallV * dt);
        return true;
    }

    tickGame(now, dt) {
        if (this.state === 'ready' && now - this.since >= RUN_READY_MS) {
            this.state = 'run';
            this.hint = '';
            this.hush();   // ("Let's play!" gone as play begins)
        } else if (this.state === 'ready')
            this.s = this.host.stage();   // (it grows meanwhile: his floor goes down with it)
        const B = this.s.bodyHeight;
        // he: up and down, or in and out
        if (this.jumpAt >= 0) {
            const p = (now - this.jumpAt) / JUMP_MS;
            if (p >= 1) {
                this.lift = 0;
                this.land(now);
                this.jumpAt = -1;
                if (this.queued)
                    this.takeOff(now);
                this.queued = false;
                if (this.jumpAt < 0 && this.digPending) {   // (↓ pressed in the air, still held)
                    this.digging = true;
                    this.digAt = now;
                }
                this.digPending = false;
            } else
                this.lift = 4 * JUMP_HIGH * B * p * (1 - p);
        }
        if (this.digging && now - this.digAt > DIG_MS)
            this.digging = false;
        this.setPose(this.jumpAt >= 0 ? 'jump' : this.digging ? 'dig' : 'run');
        this.talpy.walkMs = this.walkMs();
        // the ground goes by
        const step = this.speed * dt;
        this.dist += M_PER_S * this.speedUp * dt;
        this.score();
        this.speeds();
        let n = 0, crowNear = false;
        for (let i = 0; i < this.things.length; i++) {
            const th = this.things[i];
            th.x -= th.kind === 'cloud' ? step * CLOUD_PACE : step;
            th.y = th.sky >= 0 ? th.sky : this.s.ground - th.up;
            if (th.kind === 'crow' || th.kind === 'crowHigh')
                th.frame = Math.floor((now + th.seed) / FLAP_MS) % FLAP_FRAMES;
            else if (th.kind === 'dust')
                th.frame = Math.floor((now - th.born) / DUST_MS);
            else if (th.kind === 'cookie')
                th.frame = Math.floor((now + th.seed) / TWINKLE_MS) % FRAMES.cookie;
            if (th.x + th.w > 0 && !(th.kind === 'dust' && th.frame >= FRAMES.dust)) {
                this.things[n++] = th;
                if (th.kind === 'crow' && th.x + th.w > this.x)
                    crowNear = true;
            }
        }
        this.things.length = n;
        if (this.hint === 'dig' && !crowNear)
            this.hint = '';
        this.lifts(dt);
        this.spawn(step);
        // a cookie taken? (his whole box: generous)
        const hb = this.box();
        for (let i = this.things.length - 1; i >= 0; i--) {
            const th = this.things[i];
            if (GRAB.indexOf(th.kind) >= 0 && th.x < hb[2] && th.x + th.w > hb[0] && th.y < hb[3] && th.y + th.h > hb[1])
                this.grab(th);
        }
        // a bump?
        for (let i = 0; i < this.things.length; i++) {
            const th = this.things[i];
            if (DECOR.indexOf(th.kind) >= 0 || GRAB.indexOf(th.kind) >= 0)
                continue;
            const dx = th.w * SHRINK, dy = th.h * SHRINK;
            if (th.x + dx < hb[2] && th.x + th.w - dx > hb[0] && th.y + dy < hb[3] && th.y + th.h - dy > hb[1]) {
                this.over(th.kind);
                return;
            }
        }
    }

    // he lands: squashed a moment, a puff of dust at his feet
    land(now) {
        this.talpy.squash = SQUASH;
        const d = this.add('dust');
        d.x = this.x - d.w / 2;
        d.born = now;
    }

    // his steps' length now: the nearest of WALKS to 500 at the start's speed
    walkMs() {
        const want = 500 / this.speedUp;
        let best = WALKS[0];
        for (let i = 1; i < WALKS.length; i++) {
            if (Math.abs(WALKS[i] - want) < Math.abs(best - want))
                best = WALKS[i];
        }
        return best;
    }

    // his hit box: [left, top, right, bottom], stage px
    box() {
        const s = this.s, w = s.bodyWidth * BODY_W / 2;
        const bottom = s.ground - this.lift;
        return [this.x - w, bottom - s.bodyHeight * (this.digging ? DUG_H : BODY_H), this.x + w, bottom];
    }

    spawn(step) {
        const s = this.s, B = s.bodyHeight;
        this.tuftGap -= step;
        if (this.tuftGap <= 0) {
            if (this.count('tuft') < TUFTS)
                this.add('tuft');
            this.tuftGap = rnd(0.2, 0.5) * s.width;
        }
        this.cloudGap -= step * CLOUD_PACE;
        if (this.cloudGap <= 0) {
            if (this.count('cloud') < CLOUDS)
                this.add('cloud');
            this.cloudGap = rnd(0.5, 1.1) * s.width;
        }
        if (this.state !== 'run')
            return;
        this.gap -= step;
        if (this.gap > 0)
            return;
        const m = this.dist, kinds = [];
        for (let i = 0; i < UNLOCKS.length && m >= UNLOCKS[i][0]; i++)
            kinds.push.apply(kinds, UNLOCKS[i].slice(1));
        let kind = kinds[int(0, kinds.length - 1)];
        if (kind === this.last)   // (never the same twice in a row)
            kind = kinds[(kinds.indexOf(kind) + int(1, kinds.length - 1)) % kinds.length];
        this.last = kind;
        if (kind === 'crow' && this.crows++ === 0)
            this.hint = 'dig';     // (the first one of the run: how to get past it)
        const th = this.add(kind);
        // never shorter than a jump at this speed and room to land after it
        const least = this.speed * JUMP_MS / 1000 + s.bodyWidth + B * 0.3;
        this.gap = th.w + least * rnd(1, 2.2);
        this.cookieFor(th);
    }

    // now and then a cookie with the thing that just came: in the gap after
    // it, or over it at his jump's top (never where it would lure him into it)
    cookieFor(th) {
        const s = this.s, B = s.bodyHeight, k = KINDS.cookie, cw = k[0] * B, r = Math.random();
        const free = this.gap - th.w;
        if (r < COOKIE_AIR && KINDS[th.kind][2] === 0) {
            const c = this.add('cookie');
            c.air = true;
            c.x = th.x + th.w / 2 - c.w / 2;
            c.up = (JUMP_HIGH + COOKIE_ABOVE) * B + c.h / 2;   // (its middle where his is at his jump's top)
            c.y = s.ground - c.up;
        } else if (r < COOKIE_AIR + COOKIE_GROUND && free >= 2 * s.bodyWidth + cw) {
            const c = this.add('cookie');
            c.x = th.x + th.w + (free - cw) / 2;
        }
    }

    add(kind) {
        // (the stage read again as a thing comes: the view may have been widened meanwhile)
        const s = this.s = this.host.stage(), B = s.bodyHeight, k = KINDS[kind];
        // (up: its top above the floor, so it stays on the floor as the stage grows)
        const th = { kind: kind, x: s.width + B * 0.2, y: 0, w: k[0] * B, h: k[1] * B, frame: 0, up: (k[2] + k[1]) * B,
                     variant: int(0, (VARIANTS[kind] || 1) - 1), seed: int(0, FLAP_MS * FLAP_FRAMES), slot: this.freeSlot() };
        if (kind === 'cloud')   // (px from the stage's top, in the sky's top part: not on the floor as it grows)
            th.sky = rnd(2, Math.max(2, B * 1.2 - th.h));
        th.y = th.sky >= 0 ? th.sky : s.ground - th.up;
        this.things.push(th);
        return th;
    }

    bumped() {
        this.jumpAt = -1;   // (in the air, he falls from where he was hit: overTick)
        this.fallV = 0;
        this.digging = false;
        this.setPose('bump');
    }

    ended() {
        this.digging = false;
        this.talpy.walkMs = 500;
    }
}
