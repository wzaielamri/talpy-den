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
//   the run's: best(): metres; saveBest(m): a new best; grow(on): the stage taller (the
//   status faded) for the run, or back; runOk(): false where the run isn't offered }
//
// Plain ES2017 (see paths.mjs).

import { ACTIONS, COOKIE } from './actions.mjs';

const rnd = (a, b) => a + Math.random() * (b - a);
const int = (a, b) => Math.floor(rnd(a, b + 1));
const sine = p => 0.5 - 0.5 * Math.cos(Math.PI * Math.max(0, Math.min(1, p)));

export const GAMES = ['peekaboo', 'run'];

// A game by name, else at random; never the run where the host can't have it
export function pickGame(talpy, host, name) {
    const can = GAMES.filter(g => g !== 'run' || !host.runOk || host.runOk());
    const which = can.indexOf(name) >= 0 ? name : can[Math.floor(Math.random() * can.length)];
    return which === 'run' ? new Run(talpy, host) : new Peekaboo(talpy, host);
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
// there. The first bump ends the run: how far (meters), the best (host.best;
// a new one host.saveBest, said 'best'), and a press runs again; with no press
// in RUN_END_MS the game's over. For the host to draw: things (stage px:
// kind, x, y, w, h, frame; drawThing in talpy.mjs), lift (px he's up), meters,
// best, newBest, hint ('start', 'dig' or ''), state ('ready', 'run', 'over').
// A gap between two things is never shorter than a jump at that speed and
// room to land, so a run can always be cleared.

const RUN_READY_MS = 2000;     // the hint, and nothing on his way yet
const RUN_END_MS = 10000;      // the end waits that long for a press
const JUMP_MS = 620;           // up and down again, whatever the speed
const JUMP_HIGH = 1.6;         // that many of his body's height
const DIG_MS = 1000;           // up again by himself after that
const SPEED0 = 110;            // box units a second at the start
const SPEED_UP = 1.1;          // ×, every 100 m
const SPEED_CAP = 2;           // × the start, at most
const M_PER_S = 10;            // metres a second at the start
const CROWS_FROM = 200;        // metres
const MORE_FROM = 400;         // two pebbles, crows flying high
const TUFTS = 3;               // grass tufts at a time, at most
// a thing's size by his body's (w × h) and how high its bottom is above the floor
const KINDS = {
    pebble: [0.35, 0.25, 0], stone: [0.45, 0.5, 0], pot: [0.35, 0.75, 0], pebbles: [0.9, 0.25, 0],
    crow: [0.6, 0.35, 0.7], crowHigh: [0.6, 0.35, 1.85], tuft: [0.25, 0.15, 0]
};
const SHRINK = 0.15;           // a thing's hit box is that much inside its drawing, each side
const BODY_W = 0.55, BODY_H = 0.85, DUG_H = 0.3;   // his hit box, by his body's size
const RUN_POSES = {
    run: () => COOKIE.chase.run(),
    jump: () => COOKIE.chase.leap(),
    dig: () => ({ depth: 'peek', hole: 1, eyes: 'squint', mouth: 'smile', plume: 'flick', tail: 'wag' }),
    bump: () => ({ depth: 'out', hole: 0, body: 'shake', eyes: 'squint', mouth: 'o', plume: 'wild', tail: 'droop',
                   fx: [['sparkle', 26, 14, { dy: -6 }], ['sparkle', 38, 12, { dy: -6, delay: 0.15 }]] })
};

export class Run {
    constructor(talpy, host) {
        this.name = 'run';
        this.talpy = talpy;
        this.host = host;
        this.on = false;
        this.holes = [];           // (none of the host's: he digs in his own hole)
        this.things = [];          // one array all along (kept, emptied, filled)
        this.state = '';
        this.lift = 0;
        this.digging = false;
        this.meters = 0;
        this.best = 0;
        this.newBest = false;
        this.hint = '';
        this.hitBy = '';
        this.speed = 0;            // px a second
        this.speedUp = 1;          // × the start
        this.now = 0;
        this.brain = true;
    }

    start(now) {
        const t = this.talpy;
        this.on = true;
        this.brain = t.brainOn;
        t.brainOn = false;
        t.cancel();
        this.host.grow(true);
        this.best = Math.max(0, Math.floor(Number(this.host.best()) || 0));
        this.reset(now);
    }

    reset(now) {
        const s = this.host.stage();
        this.s = s;
        this.x = s.minX + (s.maxX - s.minX) * 0.2;
        this.host.moveTo(this.x);
        this.things.length = 0;
        this.state = 'ready';
        this.since = now;
        this.now = now;
        this.dist = 0;             // metres, not rounded
        this.meters = 0;
        this.newBest = false;
        this.hint = 'start';
        this.hitBy = '';
        this.lift = 0;
        this.jumpAt = -1;
        this.queued = false;
        this.digging = false;
        this.crows = 0;
        this.gap = 0;              // px of ground still to go before the next thing
        this.tuftGap = 0;
        this.pose = '';
        this.speeds();
        this.setPose('run');
        this.host.changed();
    }

    speeds() {
        this.speedUp = Math.min(SPEED_CAP, Math.pow(SPEED_UP, this.dist / 100));
        this.speed = SPEED0 * this.s.unit * this.speedUp;
    }

    setPose(name) {
        if (this.pose === name)
            return;
        this.pose = name;
        const step = RUN_POSES[name]();
        step.t = HOLD;
        this.talpy.play({ steps: () => [step] }, null, false);
    }

    press(what) {
        if (!this.on)
            return;
        if (this.state === 'over') {
            if (what === 'jump')
                this.reset(this.now);
            return;
        }
        if (what === 'dig') {
            if (this.jumpAt < 0) {
                this.digging = true;
                this.digAt = this.now;
            }
        } else if (this.jumpAt >= 0)
            this.queued = true;    // (kept for the moment he lands)
        else {
            this.digging = false;
            this.jumpAt = this.now;
        }
    }

    release(what) {
        if (what === 'dig')
            this.digging = false;
    }

    hit() {
        return this.on;            // (a click on him is the game's: no petting meanwhile)
    }

    tick(now) {
        if (!this.on)
            return;
        const dt = Math.min(0.1, Math.max(0, (now - this.now) / 1000));
        this.now = now;
        if (this.state === 'over') {
            if (now - this.since > RUN_END_MS)
                this.end();
            return;
        }
        if (this.state === 'ready' && now - this.since >= RUN_READY_MS) {
            this.state = 'run';
            this.hint = '';
        } else if (this.state === 'ready')
            this.s = this.host.stage();   // (it grows meanwhile: his floor goes down with it)
        const B = this.s.bodyHeight;
        // he: up and down, or in and out
        if (this.jumpAt >= 0) {
            const p = (now - this.jumpAt) / JUMP_MS;
            if (p >= 1) {
                this.lift = 0;
                this.jumpAt = this.queued ? now : -1;
                this.queued = false;
            } else
                this.lift = 4 * JUMP_HIGH * B * p * (1 - p);
        }
        if (this.digging && now - this.digAt > DIG_MS)
            this.digging = false;
        this.setPose(this.jumpAt >= 0 ? 'jump' : this.digging ? 'dig' : 'run');
        // the ground goes by
        const step = this.speed * dt;
        this.dist += M_PER_S * this.speedUp * dt;
        this.meters = Math.floor(this.dist);
        this.speeds();
        let n = 0, crowNear = false;
        for (let i = 0; i < this.things.length; i++) {
            const th = this.things[i];
            th.x -= step;
            th.y = this.s.ground - th.up;
            th.frame = Math.floor(now / 150) % 2;
            if (th.x + th.w > 0) {
                this.things[n++] = th;
                if (th.kind === 'crow' && th.x + th.w > this.x)
                    crowNear = true;
            }
        }
        this.things.length = n;
        if (this.hint === 'dig' && !crowNear)
            this.hint = '';
        this.spawn(step);
        // a bump?
        const hb = this.box();
        for (let i = 0; i < this.things.length; i++) {
            const th = this.things[i];
            if (th.kind === 'tuft')
                continue;
            const dx = th.w * SHRINK, dy = th.h * SHRINK;
            if (th.x + dx < hb[2] && th.x + th.w - dx > hb[0] && th.y + dy < hb[3] && th.y + th.h - dy > hb[1]) {
                this.bump(th.kind);
                return;
            }
        }
        this.host.changed();
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
            let tufts = 0;
            for (let i = 0; i < this.things.length; i++)
                tufts += this.things[i].kind === 'tuft' ? 1 : 0;
            if (tufts < TUFTS)
                this.add('tuft');
            this.tuftGap = rnd(0.2, 0.5) * s.width;
        }
        if (this.state !== 'run')
            return;
        this.gap -= step;
        if (this.gap > 0)
            return;
        const m = this.meters;
        const kinds = ['pebble', 'stone', 'pot'];
        if (m >= CROWS_FROM)
            kinds.push('crow');
        if (m >= MORE_FROM)
            kinds.push('pebbles', 'crowHigh');
        const kind = kinds[int(0, kinds.length - 1)];
        if (kind === 'crow' && this.crows++ === 0)
            this.hint = 'dig';     // (the first one of the run: how to get past it)
        const th = this.add(kind);
        // never shorter than a jump at this speed and room to land after it
        const least = this.speed * JUMP_MS / 1000 + s.bodyWidth + B * 0.3;
        this.gap = th.w + least * rnd(1, 2.2);
    }

    add(kind) {
        const s = this.s, B = s.bodyHeight, k = KINDS[kind];
        // (up: its top above the floor, so it stays on the floor as the stage grows)
        const th = { kind: kind, x: s.width + B * 0.2, y: 0, w: k[0] * B, h: k[1] * B, frame: 0, up: (k[2] + k[1]) * B };
        th.y = s.ground - th.up;
        this.things.push(th);
        return th;
    }

    bump(kind) {
        this.state = 'over';
        this.since = this.now;
        this.hitBy = kind;
        this.lift = 0;
        this.jumpAt = -1;
        this.digging = false;
        this.hint = '';
        this.setPose('bump');
        if (this.meters > this.best) {
            this.newBest = true;
            this.best = this.meters;
            this.host.saveBest(this.meters);
            this.host.say('best');
        } else
            this.host.say('bump');
        this.host.changed();
    }

    // Over (by itself, or at once: stop): he comes up where he is, his own doings back
    end() {
        if (!this.on)
            return;
        this.on = false;
        this.state = '';
        this.things.length = 0;
        this.lift = 0;
        this.digging = false;
        this.hint = '';
        const t = this.talpy;
        t.brainOn = this.brain;
        t.cancel();
        t.apply({});
        this.host.grow(false);
        this.host.changed();
    }

    // At once (Esc, a click outside, a chat that needs you, out of sight): a run
    // cut short still counts for the best
    stop() {
        if (this.on && this.state !== 'over' && this.meters > this.best) {
            this.best = this.meters;
            this.host.saveBest(this.meters);
        }
        this.end();
    }
}
