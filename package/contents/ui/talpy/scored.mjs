// What the games with a score (Talpy's Run in games.mjs, Deep Dig in
// dig.mjs) share: the stage taller while one is on (stageGu: its whole height
// in grid units, host.grow), what's on his way as plain data a host keeps a
// picture of (things, each with a slot of its own while it's there), a step a
// whole number of the host's frames long, the score (metres, and BONUS more
// for each cookie grabbed), the end (a bump: how far, the best, a press runs
// again; with none in RUN_END_MS the game's over) and the best (the host's,
// by the game's name: host.best(name), host.saveBest(name, m)).
//
// A game extends Scored with reset(now) (a new go: its things, its pose) and
// tickGame(now, dt) (one step while it's on and not over), and calls over(kind)
// when he bumps into something, grab(th) when he takes a cookie.
//
// For the host to draw: things (stage px: kind, x, y, w, h, frame, variant,
// slot, alpha; drawThing in talpy.mjs), lift (px he's above his floor), turn
// (degrees he's turned, 0 upright), meters, best, newBest, hint, state
// ('ready', 'run', 'over').
//
// Plain ES2017 (see paths.mjs).

export const RUN_END_MS = 5000;     // the end waits that long for a press (then back to work)
export const RUN_AGAIN_MS = 450;    // ...and takes none so soon after the bump (a press meant for the game)
export const BONUS = 10;            // metres a cookie is worth
export const SCORED = ['run', 'dig'];
export const DECOR = ['tuft', 'cloud', 'plus', 'dust', 'speck', 'worm', 'crystal', 'tunnel', 'clod', 'glow'];   // (drawn, never bumped into)
export const GRAB = ['cookie'];     // (taken, not bumped into)
const HOLD = 60000;                 // a pose held that long (the game moves him on before)
const PLUS_MS = 700;                // a "+10" rises and fades that long

export class Scored {
    constructor(talpy, host, name, stageGu) {
        this.name = name;
        this.talpy = talpy;
        this.host = host;
        this.stageGu = stageGu;
        this.on = false;
        this.holes = [];           // (none of the host's)
        this.things = [];          // one array all along (kept, emptied, filled)
        this.slots = 0;            // things' slots used so far (a host's pictures for them)
        this.frameMs = 1000 / 60;  // the host's ticks, as they come (an even step each: step)
        this.state = '';
        this.since = 0;
        this.now = 0;
        this.lift = 0;
        this.turn = 0;
        this.dist = 0;             // metres, not rounded
        this.bonus = 0;            // metres the cookies were worth
        this.grabbed = 0;          // cookies taken this go
        this.meters = 0;
        this.best = 0;
        this.newBest = false;
        this.hint = '';
        this.hitBy = '';
        this.pose = '';
        this.poses = {};           // the game's poses by name (setPose)
        this.brain = true;
    }

    start(now) {
        const t = this.talpy;
        this.on = true;
        this.brain = t.brainOn;
        t.brainOn = false;
        t.cancel();
        this.host.grow(true);
        this.best = Math.max(0, Math.floor(Number(this.host.best(this.name)) || 0));
        this.begin(now);
    }

    // a new go (the first, or again from the end)
    begin(now) {
        this.things.length = 0;
        this.state = 'ready';
        this.since = now;
        this.now = now;
        this.dist = 0;
        this.bonus = 0;
        this.grabbed = 0;
        this.meters = 0;
        this.newBest = false;
        this.hitBy = '';
        this.lift = 0;
        this.turn = 0;
        this.pose = '';
        this.reset(now);
        this.host.changed();
    }

    setPose(name) {
        if (this.pose === name)
            return;
        this.pose = name;
        const step = this.poses[name]();
        step.t = HOLD;
        this.talpy.play({ steps: () => [step] }, null, false);
    }

    // A press on the end, past RUN_AGAIN_MS: again (true: it was taken)
    again() {
        if (this.state !== 'over')
            return false;
        if (this.now - this.since >= RUN_AGAIN_MS)
            this.begin(this.now);
        return true;
    }

    hit() {
        return this.on;            // (a click on him is the game's: no petting meanwhile)
    }

    // Seconds since the last tick, a whole number of the host's ticks: what goes
    // by steps the same each frame, not by when the frame's tick happened to
    // run; one sooner than half a tick: as it came
    step(now) {
        const raw = Math.max(0, now - this.now), ticks = Math.round(raw / this.frameMs);
        if (raw > 4 && raw < 50)
            this.frameMs += (raw - this.frameMs) * 0.05;
        this.now = now;
        return Math.min(0.1, (ticks >= 1 ? ticks * this.frameMs : raw) / 1000);
    }

    tick(now) {
        if (!this.on)
            return;
        const dt = this.step(now);
        if (this.state === 'over') {
            if (now - this.since > RUN_END_MS)
                this.end();
            else if (this.overTick(now, dt))
                this.host.changed();
            return;
        }
        this.tickGame(now, dt);
        if (this.state !== 'over')
            this.host.changed();
    }

    // one step on the end (true: something moved); the game's own, if any
    overTick(now, dt) {
        return false;
    }

    // the score shown: metres dug or run, and the cookies' bonus
    score() {
        this.meters = Math.floor(this.dist) + this.bonus;
    }

    count(kind) {
        let n = 0;
        for (let i = 0; i < this.things.length; i++)
            n += this.things[i].kind === kind ? 1 : 0;
        return n;
    }

    // the lowest slot no thing has now (slots only grows: a host's pictures for them are kept)
    freeSlot() {
        let slot = 0;
        while (this.things.some(th => th.slot === slot))
            slot++;
        this.slots = Math.max(this.slots, slot + 1);
        return slot;
    }

    // He bumped into something: the end, how far, the best
    over(kind) {
        this.state = 'over';
        this.since = this.now;
        this.hitBy = kind;
        this.hint = '';
        this.bumped();
        if (this.meters > this.best) {
            this.newBest = true;
            this.best = this.meters;
            this.host.saveBest(this.name, this.meters);
            this.host.say('best');
        } else
            this.host.say('bump');
        this.host.changed();
    }

    // the game's own, as he bumps (his pose)
    bumped() {
    }

    // He took a cookie: BONUS metres, a "+10" rising from it
    grab(th) {
        this.grabbed++;
        this.bonus += BONUS;
        this.score();
        const i = this.things.indexOf(th);
        if (i >= 0)
            this.things.splice(i, 1);
        this.things.push({ kind: 'plus', x: th.x + th.w / 2 - th.h * 0.6, y: th.y, sky: th.y, w: th.h * 1.2, h: th.h * 0.6,
                           frame: 0, variant: 0, slot: this.freeSlot(), alpha: 1, born: this.now, up: 0 });
    }

    // the "+10"s: up and fading, then gone (each tick, from the game's own; sky:
    // px from the stage's top, so the game's own moves leave its height alone)
    lifts(dt) {
        let n = 0;
        for (let i = 0; i < this.things.length; i++) {
            const th = this.things[i];
            if (th.kind === 'plus') {
                const p = (this.now - th.born) / PLUS_MS;
                if (p >= 1)
                    continue;
                th.sky -= th.h * 2 * dt;
                th.y = th.sky;
                th.alpha = 1 - p * p;
            }
            this.things[n++] = th;
        }
        this.things.length = n;
    }

    // Over (by itself, or at once: stop): he comes up where he is, his own doings back
    end() {
        if (!this.on)
            return;
        this.on = false;
        this.state = '';
        this.things.length = 0;
        this.lift = 0;
        this.turn = 0;
        this.hint = '';
        this.ended();
        const t = this.talpy;
        t.brainOn = this.brain;
        t.cancel();
        t.apply({});
        this.host.grow(false);
        this.host.changed();
    }

    // the game's own, as it's over
    ended() {
    }

    // At once (Esc, a click outside, a chat that needs you, out of sight): a go
    // cut short still counts for the best
    stop() {
        if (this.on && this.state !== 'over' && this.meters > this.best) {
            this.best = this.meters;
            this.host.saveBest(this.name, this.meters);
        }
        this.end();
    }
}
