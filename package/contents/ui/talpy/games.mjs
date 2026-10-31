// Games with the big Talpy (talpy.mjs) on his stage: four quick clicks on him
// (he laughs, "Let's play!") or Play with Talpy in the menu start one, picked
// at random (pickGame). Each lasts 10 to 30 s and ends by itself; the host
// ends it at once (stop) on Esc, a click outside the stage, a chat that needs
// you, or the stage going out of sight. No scores, nothing counted: it's
// just play. The host ticks a game only while it's on, draws the holes it
// opens (drawHole in talpy.mjs: holes, each {x, open}, stage px and 0 to 1)
// under Talpy, and moves Talpy where it says.
//
//   const game = pickGame(talpy, host); game.start(now, wake) (he laughs first; wake: woken, he yawns)
//   every tick while game.on: game.tick(now), after talpy.tick(now)
//   a click on Talpy: game.hit() (true: the game took it)
//   game.stop(): over now (Talpy comes up where he is)
//
// host: {
//   stage(): { width, ground, unit (px a box unit), bodyWidth, bodyHeight, minX, maxX },
//   px(): where Talpy is (his centre); moveTo(x): he's there now (underground: no digging across);
//   say(what): his words for 'got' (you caught him), 'fun' (the game's over);
//   changed(): what shows changed (on, the holes) }
//
// Plain ES2017 (see paths.mjs).

import { ACTIONS } from './actions.mjs';

const rnd = (a, b) => a + Math.random() * (b - a);
const int = (a, b) => Math.floor(rnd(a, b + 1));
const sine = p => 0.5 - 0.5 * Math.cos(Math.PI * Math.max(0, Math.min(1, p)));

export const GAMES = ['peekaboo'];

// A game, at random (one for now)
export function pickGame(talpy, host) {
    return new Peekaboo(talpy, host);
}

const OPEN_MS = 320;         // holes open (and close) that long
const POP_MS = 450;          // he takes that long to pop up (talpy.mjs DEPTH easing)
const MAX_MS = 26000;        // the game's over by then, whatever the rounds

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
                                     t: POP_MS + up }] }, null, false);
            this.set('up', POP_MS + up);
            return;
        }
        case 'up':   // too slow: he ducks, giggling
            t.play({ steps: w => [{ depth: 'hidden', eyes: 'squint', mouth: 'smile',
                                    fx: [['text', 30, 30, { text: w('hihi'), size: 6, dy: -8, dur: 1 }]], t: 420 }] }, null, false);
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
            { depth: 'hidden', eyes: 'happy', mouth: 'open', t: 360 }] }, null, false);
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
