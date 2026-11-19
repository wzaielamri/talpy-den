"""Games with the big Talpy (talpy/games.mjs): four quick clicks on him (or
Play with Talpy in the menu) and he laughs, says "Let's play!" and a game
starts. Peekaboo holes: three holes open, he pops out of one at random, you
click him before he ducks, he's quicker each round, and after a few he
dances and the holes close. 10 to 30 s, ending by itself; Esc, a click
outside, a chat that needs you or the stage out of sight end it at once. No
scores. Ticked and drawn only while it runs."""
import claude_guard  # noqa: F401  (first: no test runs the real claude)
import json
import re
import unittest
from pathlib import Path

from test_pets import TALPY, run_node

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "package/contents/ui"

GAME = """
import { pickGame, GAMES } from %s;
const ctx = new Proxy({}, { get: () => () => ({ addColorStop() {} }) });
function play(hitEvery, stopAt) {
    const t = new Talpy({});
    let now = 1000, px = 280;
    t.tick(now);
    const said = [], xs = new Set();
    let changed = 0;
    const host = {
        stage: () => ({ width: 400, ground: 90, unit: 1.5, bodyWidth: 60, bodyHeight: 60, minX: 30, maxX: 370 }),
        px: () => px, moveTo: x => { px = x; xs.add(Math.round(x)); }, say: w => said.push(w), changed: () => changed++,
    };
    const g = pickGame(t, host, 'peekaboo');
    g.start(now);
    const brainDuring = t.brainOn;
    let ups = 0, last = '', downHits = 0, maxOpen = 0, holes = 0, downRise = 0, deepest = 0;
    while (g.on && now < 60000) {
        now += 16;
        t.tick(now);
        g.tick(now);
        t.draw(ctx);
        holes = Math.max(holes, g.holes.length);
        maxOpen = Math.max(maxOpen, ...g.holes.map(h => h.open));
        if (g.state !== last && g.state === 'up') ups++;
        last = g.state;
        if (g.state === 'down' && g.hit()) downHits++;    // (a click while he's down: the game's, nothing happens)
        if (g.state === 'down') {   // (how far back up he came meanwhile)
            deepest = Math.max(deepest, t.v.depth);
            downRise = Math.max(downRise, deepest - t.v.depth);
        } else
            deepest = 0;
        if (g.state === 'up' && hitEvery && now - g.since > 500 && ups %% hitEvery === 0) g.hit();
        if (stopAt && now - 1000 > stopAt) g.stop();
    }
    return { ms: now - 1000, rounds: g.round, ups, said, xs: xs.size, brainDuring, brainAfter: t.brainOn, holes, maxOpen,
             holesAfter: g.holes.length, changed, downRounds: g.round, downRise };
}
console.log(JSON.stringify({ games: GAMES, missed: play(0), caught: play(1), some: play(3), stopped: play(0, 3000) }));
""" % json.dumps(str(TALPY / "games.mjs"))


class PeekabooTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = run_node(GAME)

    def test_it_ends_by_itself_in_10_to_30_seconds_with_the_holes_shut(self):
        for name in ("missed", "caught", "some"):
            with self.subTest(name):
                g = self.r[name]
                self.assertGreaterEqual(g["ms"], 10000)
                self.assertLessEqual(g["ms"], 30000)
                self.assertGreaterEqual(g["rounds"], 6)
                self.assertEqual(g["holes"], 3)            # three holes open
                self.assertAlmostEqual(g["maxOpen"], 1, places=2)
                self.assertEqual(g["holesAfter"], 0)        # and none left over
                self.assertEqual(g["said"][-1], "fun")      # he says it was fun (and dances)

    def test_he_pops_out_of_holes_at_random_and_is_caught_only_while_up(self):
        self.assertGreaterEqual(self.r["missed"]["xs"], 2)
        self.assertEqual(self.r["caught"]["said"].count("got"), self.r["caught"]["rounds"])
        self.assertEqual(self.r["missed"]["said"].count("got"), 0)   # (clicks while he's down catch nothing)

    def test_between_pops_he_stays_down_till_hes_up_in_the_next_hole(self):
        # (caught or ducked, he stays down while he tunnels to the next hole: his
        # own pose ending brought him back up in the same hole first)
        for name in ("missed", "caught", "some"):
            with self.subTest(name):
                self.assertLess(self.r[name]["downRise"], 0.5)   # (on his way down, or down: never back up)

    def test_he_does_nothing_of_his_own_meanwhile_and_is_back_after(self):
        for name in ("missed", "stopped"):
            self.assertFalse(self.r[name]["brainDuring"])
            self.assertTrue(self.r[name]["brainAfter"])

    def test_stopped_its_over_at_once(self):
        g = self.r["stopped"]
        self.assertLess(g["ms"], 3100)
        self.assertEqual(g["holesAfter"], 0)

    def test_its_light_the_host_redraws_only_when_the_holes_move(self):
        # (open and shut: about 20 frames each, and start and end)
        for name in ("missed", "caught"):
            self.assertLess(self.r[name]["changed"], 60)

    def test_its_on_from_the_click_that_starts_it(self):
        # (a 5th quick click while he still laughed cut the laugh short, and
        # the game never came: it starts at once now, his laugh its first move,
        # and the clicks after it are the game's)
        out = run_node("""
import { pickGame } from %s;
const t = new Talpy({});
let now = 1000;
t.tick(now);
const g = pickGame(t, { stage: () => ({ width: 400, ground: 90, unit: 1.5, bodyWidth: 60, bodyHeight: 60, minX: 30, maxX: 370 }),
                        px: () => 200, moveTo() {}, say() {}, changed() {} }, 'peekaboo');
g.start(now);
const first = { on: g.on, body: t.st.body, eyes: t.st.eyes };
now += 200; t.tick(now); g.tick(now);
const hit = g.hit();
for (let i = 0; i < 300; i++) { now += 16; t.tick(now); g.tick(now); }
const t2 = new Talpy({});
t2.tick(1000);
const g2 = pickGame(t2, { stage: () => ({ width: 400, ground: 90, unit: 1.5, bodyWidth: 60, bodyHeight: 60, minX: 30, maxX: 370 }),
                          px: () => 200, moveTo() {}, say() {}, changed() {} }, 'peekaboo');
g2.start(1000, true);
console.log(JSON.stringify({ first, hit, after: g.state, on: g.on, woken: t2.st.mouth }));""" % json.dumps(str(TALPY / "games.mjs")))
        self.assertEqual(out["first"], {"on": True, "body": "shake", "eyes": "squint"})   # (laughing)
        self.assertTrue(out["hit"])                     # the next click: the game's, nothing cut short
        self.assertTrue(out["on"])
        self.assertIn(out["after"], ("down", "up", "ducked"))
        self.assertEqual(out["woken"], "yawn")          # (woken up for it from the menu: he yawns first)

    def test_he_gets_quicker_each_round(self):
        out = run_node("""
import { pickGame } from %s;
const g = pickGame(new Talpy({}), { stage: () => ({}), px: () => 0, moveTo() {}, say() {}, changed() {} }, 'peekaboo');
const ms = [];
for (let r = 0; r < 8; r++) { g.round = r; ms.push(Math.round(g.upMs())); }
console.log(JSON.stringify(ms));""" % json.dumps(str(TALPY / "games.mjs")))
        self.assertEqual(out, sorted(out, reverse=True))
        self.assertLess(out[-1], out[0])
        self.assertGreaterEqual(out[-1], 520)


RUN = """
import { pickGame, GAMES, DECOR, GRAB, KINDS, VARIANTS } from %s;
function seeded(seed) {   // (mulberry32: the same run each time)
    return () => { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed);
                   t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
}
const GROUND_KINDS = Object.keys(KINDS).filter(k => KINDS[k][2] === 0 && DECOR.indexOf(k) < 0 && GRAB.indexOf(k) < 0);
const solid = th => DECOR.indexOf(th.kind) < 0 && GRAB.indexOf(th.kind) < 0;
// A player who looks ahead: jumps a ground thing so he's at his highest over it, digs under a crow
function player(g, px, noDig) {
    let next = null;
    for (const th of g.things)
        if (solid(th) && th.x + th.w > px - 20 && (!next || th.x < next.x)) next = th;
    if (!next || next.kind === 'crowHigh') { if (g.digging) g.release('dig'); return; }
    const ahead = next.x - (px + 16);
    if (GROUND_KINDS.indexOf(next.kind) >= 0) {
        if (g.digging) g.release('dig');
        if (g.lift === 0 && ahead <= g.speed * 0.31 - (next.w + 33) / 2) g.press('jump');
    } else if (!noDig && ahead < g.speed * 0.15 + 12 && !g.digging) g.press('dig');
}
function play(o) {
    Math.random = seeded(o.seed || 1);
    let width = o.width || 400;
    const best = o.best === undefined ? 120 : o.best;
    const t = new Talpy({});
    let now = 1000, px = 200;
    t.tick(now);
    const said = [], saved = [], grows = [], faced = [], asked = [];
    const host = {
        stage: () => ({ width: width, height: 176, unit: 1.5, bodyWidth: 60, bodyHeight: 60, minX: 30, maxX: width - 30,
                        ground: o.growing ? Math.min(160, 90 + (now - 1000) / 4) : 160 }),   // (growing: its floor goes down for 280 ms)
        px: () => px, moveTo: x => { px = x; }, say: w => said.push(w), changed: () => {},
        best: name => { asked.push(name); return best; }, saveBest: (name, m) => { asked.push(name); saved.push(m); },
        grow: on => grows.push(on), face: left => faced.push(left),
    };
    t.facingLeft = true;   // (he faced the other way before)
    const g = pickGame(t, host, 'run');
    g.start(now);
    const r = { name: g.name, hintAtStart: g.hint, growAtStart: grows.slice(), facedAtStart: faced.slice(), things: g.things, sameArray: true, maxThings: 0,
                firstThingMs: null, firstCrowM: null, digHint: false, crowsPassed: 0, maxSpeedUp: 0, speedUpAt600: null,
                overMs: null, overMeters: null, onAtOver: null, hitBy: null, newBest: null, endMs: null, restarted: null };
    let crowNear = false;
    // (what comes: each thing keeps its own slot, below the game's slots; its look one of its kind's;
    // the kinds by distance; never the same kind twice in a row; the clouds up in the sky)
    const slotOf = new Map(), firstAt = {}, came = new Set();
    let slotsOk = true, variantsOk = true, sameTwice = 0, lastKind = '', cloudBottom = 0;
    // (cookies: where each is as it reaches him; the "+10"s; his steps' pace; a jump's stretch and squash)
    const cookieSeen = new Set(), plusSeen = new Set();
    let pluses = 0, cookieGaps = [], airCookies = [], walks = [], walkOk = true, lastWalk = 999, hopAt = -1, wasUp = false;
    let walkMoves = true;
    const cookieFrames = new Set();   // (a cookie twinkles: its pictures change)
    while (g.on && now < 1000 + (o.until || 180000)) {
        now += 16;
        t.tick(now);
        g.tick(now);
        if (g.things !== r.things) r.sameArray = false;
        r.maxThings = Math.max(r.maxThings, g.things.length);
        if (o.growing && !r.early && now - 1000 >= 400)   // (just after the stage grew: what it put there meanwhile)
            r.early = { kinds: g.things.map(th => th.kind), bottoms: g.things.map(th => Math.round(th.y + th.h)) };
        const hitting = g.things.filter(solid);
        for (const th of g.things) {
            if (th.kind === 'plus' && !plusSeen.has(th)) { plusSeen.add(th); pluses++; }
            if (th.kind === 'cookie') cookieFrames.add(th.frame);
            if (th.kind !== 'cookie' || cookieSeen.has(th) || th.x + th.w / 2 > px + 60) continue;
            cookieSeen.add(th);   // (a body's width before him, before it's taken: what's around it then)
            const mid = th.x + th.w / 2;
            if (th.air) {
                const under = hitting.find(o => Math.abs(o.x + o.w / 2 - mid) < 1);
                airCookies.push({ over: under ? under.kind : '', high: 160 - (th.y + th.h / 2) });
            } else {
                let left = 1e9, right = 1e9;
                for (const o of hitting) {
                    if (o.x + o.w <= th.x) left = Math.min(left, th.x - (o.x + o.w));
                    else if (o.x >= th.x + th.w) right = Math.min(right, o.x - (th.x + th.w));
                    else left = right = -1;   // (in a thing)
                }
                cookieGaps.push(Math.min(left, right));
            }
        }
        if (g.state === 'run') {
            const w = t.walkMs;
            if ([500, 420, 350, 290, 250].indexOf(w) < 0 || w > lastWalk) walkOk = false;
            lastWalk = w;
            if (!walks.length || walks[walks.length - 1][1] !== w) walks.push([Math.round(g.speedUp * 100) / 100, w]);
            if (g.lift === 0 && !g.digging && !t.moves().some(m => m[0] === 'walk' && m[1] === w / 2)) walkMoves = false;
        }
        const slots = new Set();
        for (const th of g.things) {
            if (slots.has(th.slot) || !(th.slot >= 0 && th.slot < g.slots) || (slotOf.has(th) && slotOf.get(th) !== th.slot)) slotsOk = false;
            slots.add(th.slot);
            slotOf.set(th, th.slot);
            if (!(th.variant >= 0 && th.variant < (VARIANTS[th.kind] || 1))) variantsOk = false;
            if (th.kind === 'cloud') cloudBottom = Math.max(cloudBottom, th.y + th.h);
        }
        for (const th of hitting)
            if (!came.has(th)) {
                came.add(th);
                if (th.kind === lastKind) sameTwice++;
                lastKind = th.kind;
                if (firstAt[th.kind] === undefined) firstAt[th.kind] = g.meters;
            }
        if (r.firstThingMs === null && hitting.length) r.firstThingMs = now - 1000;
        const crow = hitting.find(th => th.kind === 'crow');
        if (crow && r.firstCrowM === null) { r.firstCrowM = g.meters; r.digHint = g.hint === 'dig'; }
        if (crowNear && !crow) r.crowsPassed++;
        crowNear = !!crow;
        r.maxSpeedUp = Math.max(r.maxSpeedUp, g.speedUp);
        if (r.speedUpAt600 === null && g.meters >= 600) r.speedUpAt600 = g.speedUp;
        const auto = o.auto && (!o.autoUntil || g.meters < o.autoUntil);
        if (auto && g.state !== 'over') player(g, px, o.noDig);
        if (g.digging) r.dug = true;
        if (o.alwaysDig && g.state !== 'over' && !g.digging) g.press('dig');
        if (o.stopAt && now - 1000 >= o.stopAt) {
            r.metersAtStop = g.meters;
            g.stop();
            r.onAfterStop = g.on;
        }
        if (g.state === 'over' && r.overMs === null) {
            r.overMs = now - 1000; r.overMeters = g.meters; r.onAtOver = g.on; r.hitBy = g.hitBy; r.newBest = g.newBest;
            r.savedAtOver = saved.slice(); r.saidAtOver = said.slice();
        }
        // (a press just after the bump, as a late jump: the end stays a moment; one after that runs again)
        if (o.again && g.state === 'over' && now - 1000 - r.overMs >= 32 && r.tooSoon === undefined) {
            g.press('jump');
            r.tooSoon = g.state;
        }
        if (o.again && g.state === 'over' && now - 1000 - r.overMs > 700 && r.restarted === null) {
            g.press('jump');
            r.restarted = { state: g.state, meters: g.meters, on: g.on, hint: g.hint };
        }
        // (↓ pressed in the air and held: he digs in as he lands)
        if (o.airDig && g.state === 'run' && r.airDigAt === undefined) {
            g.press('jump');
            r.airDigAt = now;
        }
        if (o.airDig && r.airDigAt !== undefined && now - r.airDigAt === 320) {
            g.press('dig');
            r.diggingInAir = g.digging;
        }
        if (o.airDig && r.airDigAt !== undefined && now - r.airDigAt === 704) r.diggingAfterLanding = g.digging;
        // (the view widened mid-run: what comes next comes from beyond its new right edge)
        if (o.widen && now - 1000 === o.widen) width = 800;
        if (o.widen && now - 1000 > o.widen) {
            r.seen = r.seen || new Set(g.things);
            for (const th of g.things)
                if (!r.seen.has(th) && solid(th)) { r.seen.add(th); r.newX = Math.min(r.newX === undefined ? 1e9 : r.newX, th.x); }
        } else if (o.widen) r.seen = new Set(g.things);
        // (a second press: one long before landing, a double-click, isn't kept; one just before is)
        if (o.secondPress && g.state === 'run' && r.jumpAt === undefined && g.lift === 0) { g.press('jump'); r.jumpAt = now; }
        if (o.secondPress && r.jumpAt !== undefined && now - r.jumpAt === o.secondPress) g.press('jump');
        if (o.secondPress && r.jumpAt !== undefined && now - r.jumpAt === 704) r.liftAfterLanding = g.lift;
        // (a bump in the air: he comes down, not snapped to the floor)
        if (o.airBump && g.state === 'run' && r.bumpJumpAt === undefined) { g.press('jump'); r.bumpJumpAt = now; }
        if (o.airBump && r.bumpJumpAt !== undefined && now - r.bumpJumpAt === 48)
            g.things.push({ kind: 'crow', x: px - 20, y: 0, w: 36, h: 21, frame: 0, up: 63 });   // (at head height, where he is)
        if (o.airBump && g.state === 'over' && r.liftAtBump === undefined) { r.liftAtBump = g.lift; r.bumpOverAt = now; }
        if (o.airBump && r.bumpOverAt !== undefined && now - r.bumpOverAt === 608) r.liftLater = g.lift;
        if (o.airBump && r.bumpOverAt !== undefined) {   // (each tick's drop while he falls, and when he's down)
            r.lifts = r.lifts || [r.liftAtBump];
            if (r.lifts[r.lifts.length - 1] > 0) { r.lifts.push(g.lift); if (g.lift === 0) r.downMs = now - r.bumpOverAt; }
        }
        // (one jump, nothing near: he stretches as he takes off, squashes as he lands, a puff of dust there)
        if (o.hop && g.state === 'run' && hopAt < 0 && now - 1000 > 3000) {
            g.press('jump'); hopAt = now; r.stretchAtTakeoff = t.stretch;
        }
        if (o.hop && hopAt > 0) {
            if (g.lift > 0) wasUp = true;
            else if (wasUp && r.squashAtLanding === undefined) {
                r.squashAtLanding = t.squash; r.landedAt = now;
                r.dust = g.things.filter(th => th.kind === 'dust').map(th => ({ mid: th.x + th.w / 2 - px, bottom: th.y + th.h }));
            }
            if (r.landedAt !== undefined && now - r.landedAt === 400) { r.stretchLater = t.stretch; r.squashLater = t.squash; }
            if (r.landedAt !== undefined && now - r.landedAt === 608) { r.stretchEnd = t.stretch; r.squashEnd = t.squash; }
        }
    }
    r.endMs = g.on ? null : now - 1000;
    r.bottoms = g.things.map(th => Math.round(th.y + th.h));   // (ground things and tufts: on the floor)
    r.kinds = g.things.map(th => th.kind);
    r.meters = g.meters; r.said = said; r.saved = saved; r.grows = grows; r.things = null; r.seen = null;
    r.slotsOk = slotsOk; r.variantsOk = variantsOk; r.sameTwice = sameTwice; r.firstAt = firstAt; r.cloudBottom = cloudBottom;
    r.slots = g.slots; r.asked = Array.from(new Set(asked));
    r.grabbed = g.grabbed; r.dist = g.dist; r.pluses = pluses; r.cookieGaps = cookieGaps; r.airCookies = airCookies;
    r.walks = walks; r.walkOk = walkOk; r.walkMoves = walkMoves; r.cookieFrames = Array.from(cookieFrames).sort();
    return r;
}
const pick = () => { const t = new Talpy({}); return (name, ok) => pickGame(t, { stage: () => ({}), px: () => 0, moveTo() {}, say() {},
    changed() {}, best: () => 0, saveBest() {}, grow() {}, runOk: () => ok }, name).name; };
const p = pick();
const random = []; for (let i = 0; i < 200; i++) random.push(p('', false));
console.log(JSON.stringify({
    games: GAMES, byName: [p('run', true), p('peekaboo', true)], randomNoRun: random,
    idle: play({}), far: [1, 2, 3].map(seed => play({ seed: seed, auto: true, until: 150000 })),
    wide: play({ seed: 4, width: 900, auto: true, until: 150000 }),
    best: play({ seed: 5, auto: true, autoUntil: 150, best: 120 }),
    again: play({ again: true }), digging: play({ alwaysDig: true }), stopped: play({ stopAt: 5000, best: 0, auto: true }),
    growing: play({ growing: true, until: 2600 }),
    airDig: play({ airDig: true, until: 3200 }),
    widen: play({ seed: 6, auto: true, widen: 6000, until: 14000 }),
    early: play({ secondPress: 96, until: 3400 }), late: play({ secondPress: 512, until: 3400 }),
    airBump: play({ airBump: true, until: 3600 }),
    hop: play({ hop: true, until: 4600 }),
    noDig: play({ seed: 2, auto: true, noDig: true }),
}));
""" % json.dumps(str(TALPY / "games.mjs"))


class RunTests(unittest.TestCase):
    """Talpy's Run (games.mjs Run): an endless run, jump over what's on the ground, dig under crows."""

    @classmethod
    def setUpClass(cls):
        cls.r = run_node(RUN)

    def test_games_by_name_and_at_random(self):
        self.assertEqual(self.r["games"], ["peekaboo", "run", "dig"])
        self.assertEqual(self.r["byName"], ["run", "peekaboo"])
        self.assertEqual(set(self.r["randomNoRun"]), {"peekaboo"})   # (not where it isn't offered)

    def test_he_faces_what_comes(self):
        self.assertEqual(self.r["idle"]["facedAtStart"], [False])   # (he faced the other way before)

    def test_a_dig_pressed_in_the_air_digs_as_he_lands(self):
        a = self.r["airDig"]
        self.assertFalse(a["diggingInAir"])
        self.assertTrue(a["diggingAfterLanding"])

    def test_widened_mid_run_what_comes_comes_from_its_new_edge(self):
        w = self.r["widen"]
        self.assertIsNone(w["overMs"])
        self.assertGreater(w["newX"], 790)              # (beyond 800 px, less a frame's step)

    def test_cookies_are_worth_10_m(self):
        for r in self.r["far"] + [self.r["wide"]]:
            with self.subTest(seed=r):
                self.assertGreater(r["grabbed"], 0)
                self.assertEqual(r["meters"], int(r["dist"]) + 10 * r["grabbed"])
                self.assertEqual(r["pluses"], r["grabbed"])   # (a "+10" rising from each)
                self.assertEqual(r["cookieFrames"], [0, 1, 2, 3])   # (it twinkles: not a bug or a stone)

    def test_cookies_never_lure_into_a_bump(self):
        # on the ground: in a gap, at least his body's width from both sides; in the air: over a thing
        # on the ground, at the height of his body's middle at his jump's top (a jump that clears it grabs it)
        for r in self.r["far"] + [self.r["wide"]]:
            with self.subTest(seed=r):
                self.assertTrue(r["cookieGaps"])
                self.assertTrue(r["airCookies"])
                for gap in r["cookieGaps"]:
                    self.assertGreaterEqual(gap, 60)     # (bodyWidth 60)
                for c in r["airCookies"]:
                    self.assertTrue(c["over"])
                    self.assertAlmostEqual(c["high"], (1.6 + 0.42) * 60, delta=6)
                self.assertIsNone(r["overMs"])           # (the player who grabs them never bumps)

    def test_bumped_in_the_air_he_falls_with_gravity(self):
        lifts = self.r["airBump"]["lifts"]
        drops = [a - b for a, b in zip(lifts, lifts[1:])][:-1]   # (the last one: clamped at the floor)
        self.assertGreater(len(drops), 2)
        for a, b in zip(drops, drops[1:]):
            self.assertGreater(b, a)                    # (faster and faster: gravity, not a steady speed)
        self.assertLessEqual(self.r["airBump"]["downMs"], 310 + 16)   # (JUMP_MS / 2 and a frame)

    def test_he_stretches_up_and_squashes_down(self):
        h = self.r["hop"]
        self.assertGreater(h["stretchAtTakeoff"], 0.3)
        self.assertGreater(h["squashAtLanding"], 0.3)
        self.assertLess(h["stretchLater"], 0.01)
        self.assertLess(h["squashLater"], 0.01)
        self.assertEqual((h["stretchEnd"], h["squashEnd"]), (0, 0))
        self.assertEqual(len(h["dust"]), 1)               # (a puff where he landed, on the floor)
        self.assertLess(abs(h["dust"][0]["mid"]), 30)
        self.assertAlmostEqual(h["dust"][0]["bottom"], 160, delta=1)

    def test_his_steps_keep_pace_with_the_ground(self):
        for r in self.r["far"]:
            with self.subTest(seed=r):
                self.assertTrue(r["walkOk"])             # (from the set, never slower as he speeds up)
                self.assertEqual(r["walks"][0][1], 500)
                self.assertEqual(r["walks"][-1][1], 250)       # (the quickest steps, from about 1.85 × the start)
                self.assertGreaterEqual(r["walks"][-1][0], 1.8)
                self.assertTrue(r["walkMoves"])          # (his pictures step at that pace: the walk is a move)

    def test_a_double_click_is_one_jump(self):
        self.assertEqual(self.r["early"]["liftAfterLanding"], 0)   # (a second press long before landing: dropped)
        self.assertGreater(self.r["late"]["liftAfterLanding"], 0)  # (one just before landing: he jumps again)

    def test_a_bump_in_the_air_comes_down(self):
        b = self.r["airBump"]
        self.assertEqual(b["hitBy"], "crow")
        self.assertGreater(b["liftAtBump"], 0)          # (where he was hit, not on the floor at once)
        self.assertEqual(b["liftLater"], 0)             # (down a moment later)

    def test_it_grows_the_stage_and_waits_2_s_before_the_first_obstacle(self):
        idle = self.r["idle"]
        self.assertEqual(idle["name"], "run")
        self.assertEqual(idle["growAtStart"], [True])
        self.assertEqual(idle["hintAtStart"], "start")
        self.assertGreaterEqual(idle["firstThingMs"], 2000)

    def test_with_no_input_the_first_obstacle_ends_it(self):
        idle = self.r["idle"]
        self.assertGreater(idle["overMeters"], 0)
        self.assertTrue(idle["onAtOver"])                 # (the end screen: the game's still on)
        self.assertIn(idle["hitBy"], ["pebble", "stone", "pot", "hedgehog"])   # (what comes from the start)
        self.assertIn("bump", idle["saidAtOver"])
        self.assertEqual(idle["savedAtOver"], [])         # (short of the best of 120 m)

    def test_a_player_who_jumps_and_digs_runs_far_and_faster(self):
        for r in self.r["far"] + [self.r["wide"]]:
            with self.subTest(seed=r):
                self.assertIsNone(r["overMs"], f"bumped into {r['hitBy']} at {r['overMeters']} m")
                self.assertGreaterEqual(r["meters"], 1000)
                self.assertGreaterEqual(r["firstCrowM"], 200)
                self.assertTrue(r["digHint"])             # (the first crow comes with the dig hint)
                self.assertGreater(r["crowsPassed"], 0)   # (dug under: a crow doesn't end it)
                self.assertGreaterEqual(r["speedUpAt600"], 1.5)
                self.assertLessEqual(r["maxSpeedUp"], 2.05)

    def test_dig_passes_under_crows_not_ground_things(self):
        digging = self.r["digging"]
        self.assertTrue(digging["dug"])
        self.assertIsNotNone(digging["overMs"])
        self.assertIn(digging["hitBy"], ["pebble", "stone", "pot", "hedgehog"])   # (in up to his eyes, a pot still hits him)
        # a crow at head height can't be run under or jumped: only dug under
        no_dig = self.r["noDig"]
        self.assertFalse(no_dig.get("dug"))
        self.assertEqual(no_dig["hitBy"], "crow")

    def test_scored_base_is_shared(self):
        # the Run is a scored game (scored.mjs): the end, its waits and the bonus are shared with Deep Dig
        out = run_node("""
import { pickGame } from %s;
import { Scored, RUN_END_MS, RUN_AGAIN_MS, BONUS } from %s;
const g = pickGame(new Talpy({}), { stage: () => ({}), px: () => 0, moveTo() {}, say() {}, changed() {}, best: () => 0,
                                    saveBest() {}, grow() {}, runOk: () => true }, 'run');
console.log(JSON.stringify({ scored: g instanceof Scored, end: RUN_END_MS, again: RUN_AGAIN_MS, bonus: BONUS, gu: g.stageGu, turn: g.turn }));
""" % (json.dumps(str(TALPY / "games.mjs")), json.dumps(str(TALPY / "scored.mjs"))))
        self.assertEqual(out, {"scored": True, "end": 5000, "again": 450, "bonus": 10, "gu": 11, "turn": 0})
        self.assertEqual(self.r["best"]["asked"], ["run"])   # (its best is the Run's: best('run'), saveBest('run', m))

    def test_a_new_best(self):
        b = self.r["best"]
        self.assertGreater(b["overMeters"], 120)
        self.assertTrue(b["newBest"])
        self.assertEqual(b["savedAtOver"], [b["overMeters"]])
        self.assertIn("best", b["saidAtOver"])

    def test_the_end_screen_runs_again_or_ends(self):
        again = self.r["again"]["restarted"]
        self.assertEqual((again["state"], again["meters"], again["on"], again["hint"]), ("ready", 0, True, "start"))
        self.assertEqual(self.r["again"]["tooSoon"], "over")   # (a late jump, just after the bump: the end stays)
        idle = self.r["idle"]
        self.assertGreaterEqual(idle["endMs"] - idle["overMs"], 4500)   # (5 s for another run, then back to work)
        self.assertLessEqual(idle["endMs"] - idle["overMs"], 5500)
        self.assertEqual(idle["grows"][-1], False)        # (the stage back to its size)

    def test_stopped_its_over_at_once_and_counts(self):
        s = self.r["stopped"]
        self.assertIsNone(s["overMs"])                     # (still running when stopped: no bump saved it)
        self.assertFalse(s["onAfterStop"])
        self.assertEqual(s["grows"], [True, False])
        self.assertEqual(s["saved"], [s["metersAtStop"]])   # (it beat a best of 0: it counts)

    def test_its_things_stand_on_the_floor_of_the_grown_stage(self):
        # the stage grows as it starts (host.grow): a tuft or a pebble put there meanwhile goes down with its floor
        g = self.r["growing"]["early"]
        self.assertTrue(g["kinds"])
        for kind, bottom in zip(g["kinds"], g["bottoms"]):
            if kind not in ("crow", "crowHigh", "cloud"):
                self.assertEqual(bottom, 160, kind)

    def test_its_light(self):
        for r in self.r["far"] + [self.r["wide"]]:
            self.assertTrue(r["sameArray"])                # (one array all run)
            self.assertLessEqual(r["maxThings"], 12)
            self.assertLessEqual(r["slots"], 12)           # (a host's pictures for them: as few)

    def test_what_comes_changes_as_he_goes(self):
        # more kinds the further he gets, each in its looks, never the same twice in a row; each
        # keeps its slot (Plasma's picture for it); the clouds go by up in the sky, behind
        for r in self.r["far"] + [self.r["wide"]]:
            with self.subTest(seed=r):
                first = r["firstAt"]
                self.assertEqual(set(first), {"pebble", "stone", "pot", "hedgehog", "stump", "crow", "log", "pebbles", "crowHigh"})
                self.assertLess(min(first[kind] for kind in ("pebble", "stone", "pot", "hedgehog")), 50)   # (from the start)
                for kind, metres in (("stump", 100), ("crow", 200), ("log", 300), ("pebbles", 400), ("crowHigh", 400)):
                    self.assertGreaterEqual(first[kind], metres, kind)
                self.assertEqual(r["sameTwice"], 0)
                self.assertTrue(r["slotsOk"])
                self.assertTrue(r["variantsOk"])
                self.assertGreater(r["cloudBottom"], 0)
                self.assertLessEqual(r["cloudBottom"], 60 * 1.2 + 1)   # (bodyHeight 60: the sky's top part)

    def test_every_thing_draws_inside_its_box(self):
        # drawThing (talpy.mjs) draws each kind in its w × h box, top left at the origin, every look
        # and every picture of a bird's flap (its shading, cut to its own outline by a clip, isn't
        # counted: the outline is)
        out = run_node("""
import { drawThing, FRAMES } from %s;
import { KINDS as RUN_KINDS, VARIANTS as RUN_VARIANTS } from %s;
import { DIG_KINDS, DIG_VARIANTS } from %s;
const KINDS = Object.assign({}, RUN_KINDS, DIG_KINDS), VARIANTS = Object.assign({}, RUN_VARIANTS, DIG_VARIANTS);
const result = {};
for (const kind of Object.keys(KINDS)) for (let variant = 0; variant < (VARIANTS[kind] || 1); variant++)
for (let frame = 0; frame < (FRAMES[kind] || 1); frame++) for (const dark of [false, true]) {
    const pts = [], paint = { n: 0 }, saved = [];
    let depth = 0, clipped = false, open = 0, moved = false;
    // (points under a transform kept inside save/restore, as drawCookie's scaled cookie, aren't in box px: not counted)
    const at = (...xy) => { if (!clipped && !moved) for (let i = 0; i < xy.length; i += 2) pts.push([xy[i], xy[i + 1]]); };
    const ctx = new Proxy({}, { get: (_, name) => {
        if (name === 'save') return () => { saved.push([clipped, moved]); open++; };
        if (name === 'restore') return () => { const was = saved.pop(); clipped = was[0]; moved = was[1]; open--; };
        if (name === 'clip') return () => { clipped = true; };
        if (['moveTo', 'lineTo'].indexOf(name) >= 0) return (x, y) => at(x, y);
        if (name === 'bezierCurveTo') return (a, b, c, d, x, y) => at(a, b, c, d, x, y);
        if (name === 'quadraticCurveTo') return (a, b, x, y) => at(a, b, x, y);
        if (name === 'arc') return (x, y, r) => at(x - r, y - r, x + r, y + r);
        if (name === 'fill' || name === 'stroke') return () => { paint.n++; };
        if (name === 'translate' || name === 'scale' || name === 'rotate' || name === 'setTransform' || name === 'transform')
            return () => { if (open > 0) moved = true; else depth++; };   // (one left on the context: not allowed)
        return () => ({ addColorStop() {} });
    }, set: () => true });
    const w = KINDS[kind][0] * 60, h = KINDS[kind][1] * 60;   // (its size by a body 60 px high)
    drawThing(ctx, { kind: kind, x: 0, y: 0, w: w, h: h, frame: frame, variant: variant }, dark);
    const out = pts.filter(p => p[0] < -1.5 || p[0] > w + 1.5 || p[1] < -1.5 || p[1] > h + 1.5);
    result[kind + variant + '.' + frame + (dark ? 'd' : '')] = { painted: paint.n, points: pts.length, outside: out.length, moved: depth };
}
console.log(JSON.stringify(result));
""" % (json.dumps(str(TALPY / "talpy.mjs")), json.dumps(str(TALPY / "games.mjs")), json.dumps(str(TALPY / "dig.mjs"))))
        for kind in ("root", "pipe", "bottle", "boulder", "beetle", "speck", "worm", "crystal", "tunnel", "clod", "glow"):
            self.assertIn(kind + "0.0", out)   # (Deep Dig's things, every one drawn)
        for name, r in out.items():
            with self.subTest(name):
                self.assertGreater(r["painted"], 0)
                self.assertGreater(r["points"], 0)
                self.assertEqual(r["outside"], 0)
                self.assertEqual(r["moved"], 0)   # (in its box's own px: no transforms to undo)

    def test_he_scoops_earth_with_both_paws(self):
        # Deep Dig: upright, his paws reach down and scoop, one out as the other comes in, quickly
        out = run_node("""
const t = new Talpy({});
t.brainOn = false;
t.play({ steps: () => [{ depth: 'out', hole: 0, arms: 'scoop', t: 1e9 }] }, null, false);
const ls = [], rs = [];
for (let now = 0; now <= 1200; now += 16) { t.tick(now); if (now > 600) { ls.push(t.v.armL); rs.push(t.v.armR); } }
console.log(JSON.stringify({ l: [Math.min(...ls), Math.max(...ls)], r: [Math.min(...rs), Math.max(...rs)],
                             beat: (t.moves().find(m => m[0] === 'arms') || [])[1] }));
""")
        self.assertGreaterEqual(out["l"][0], -30)
        self.assertLessEqual(out["l"][1], 50)
        self.assertGreater(out["l"][1] - out["l"][0], 30)     # (a real scoop, not a twitch)
        self.assertGreaterEqual(out["r"][0], -50)
        self.assertLessEqual(out["r"][1], 30)
        self.assertLessEqual(out["beat"], 200)                # (quick: he digs)

    def test_soil_shifts_smoothly(self):
        # Deep Dig's earth: topsoil, clay from 100 m, rock from 300 m, each blended into over 30 m
        out = run_node("""
import { soilAt, SOIL } from %s;
const rgb = c => [1, 3, 5].map(i => parseInt(c.slice(i, i + 2), 16));
let most = 0, prev = rgb(soilAt(0));
for (let m = 0.5; m <= 400; m += 0.5) {
    const now = rgb(soilAt(m));
    most = Math.max(most, ...now.map((v, i) => Math.abs(v - prev[i]) * 2));   // (per metre)
    prev = now;
}
console.log(JSON.stringify({ at0: soilAt(0), at130: soilAt(130), at330: soilAt(330), at1000: soilAt(1000), soil: SOIL, most: most }));
""" % json.dumps(str(TALPY / "talpy.mjs")))
        self.assertEqual(out["at0"], out["soil"]["topsoil"])
        self.assertEqual(out["at130"], out["soil"]["clay"])
        self.assertEqual(out["at330"], out["soil"]["rock"])
        self.assertEqual(out["at1000"], out["soil"]["rock"])
        self.assertLessEqual(out["most"], 6)

    def test_a_crow_shows_on_a_dark_stage(self):
        # a dark crow with an ink outline vanished on a dark theme's stage: there it has a light outline
        out = run_node("""
import { drawThing } from %s;
const lum = c => { const m = /^#([0-9a-f]{6})$/i.exec(c); if (!m) return null; const n = parseInt(m[1], 16);
                   return (0.299 * (n >> 16) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255; };
const result = {};
for (const dark of [false, true]) {
    const strokes = [];
    const ctx = new Proxy({}, { get: () => () => ({ addColorStop() {} }),
                                set: (_, name, v) => { if (name === 'strokeStyle') strokes.push(lum(v)); return true; } });
    drawThing(ctx, { kind: 'crow', x: 0, y: 0, w: 36, h: 21, frame: 0 }, dark);
    result[dark ? 'dark' : 'light'] = Math.max(...strokes.filter(l => l !== null));
}
console.log(JSON.stringify(result));
""" % json.dumps(str(TALPY / "talpy.mjs")))
        self.assertLess(out["light"], 0.3)    # (ink on a light stage)
        self.assertGreater(out["dark"], 0.7)  # (a light outline on a dark one)


DIG = """
import { pickGame, GAMES, DECOR, GRAB } from %s;
import { Dig, MOVE, LAYERS } from %s;
function seeded(seed) {   // (mulberry32: the same dig each time)
    return () => { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed);
                   t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
}
const BW = 60, BH = 60;   // (his body: 60 × 60 px; the stage 16 grid units: 260 px)
function host(o, state) {
    return {
        stage: () => ({ width: state.width, height: 260, ground: 245, unit: 1.5, bodyWidth: BW, bodyHeight: BH,
                        minX: 30, maxX: state.width - 30 }),
        px: () => state.px, moveTo: x => { state.px = x; }, say: w => state.said.push(w), changed: () => {},
        best: name => { state.asked.push(name); return o.best || 0; }, saveBest: (name, m) => { state.asked.push(name); state.saved.push(m); },
        grow: on => state.grows.push(on), face: left => state.faced.push(left), runOk: () => true,
    };
}
function start(o) {
    Math.random = seeded(o.seed || 1);
    const t = new Talpy({});
    const state = { width: o.width || 500, px: 200, said: [], saved: [], grows: [], faced: [], asked: [] };
    let now = 1000;
    t.tick(now);
    const g = pickGame(t, host(o, state), 'dig');
    g.start(now);
    return { t, g, state, tick: (ms) => { now += ms || 16; t.tick(now); g.tick(now); return now; }, now: () => now };
}
// The player: in the next row's way through (the one nearest below him); a beetle's row: the
// side it won't be on as it gets to him (where it'll be then, turning at the sides)
function steer(g, W) {
    const top = g.cy - BH * 0.45;
    let next = null;
    for (const r of g.rows)
        if (r.bottom > top && (!next || r.top < next.top)) next = r;
    if (!next) return;
    if (next.beetle) {
        // (the nearest place he can get to before its row does that it won't cross while it goes by)
        const b = g.things.find(th => th.kind === 'beetle' && th.row === next.id);
        if (!b) return;
        const box = BW * 0.3, t0 = Math.max(0, (next.top - (g.cy + BH * 0.45)) / g.speed);
        const t1 = (next.bottom - (g.cy - BH * 0.45)) / g.speed, pace = 1.5 * BW, top = 7 * BW;
        let x = b.x, dir = b.dir, lo = 1e9, hi = -1e9;
        for (let t = 0; t <= t1; t += 0.01) {
            if (t >= t0) { lo = Math.min(lo, x); hi = Math.max(hi, x + b.w); }
            x += dir * pace * 0.01;
            if (x < 0 || x + b.w > W) { x = Math.max(0, Math.min(W - b.w, x)); dir = -dir; }
        }
        let best = null, late = null;
        for (let c = 30; c <= W - 30; c += 5) {
            if (c + box > lo - 4 && c - box < hi + 4) continue;   // (it'll be there)
            if (Math.abs(c - g.x) / top + 0.12 <= t0) {
                if (best === null || Math.abs(c - g.x) < Math.abs(best - g.x)) best = c;
            } else if (late === null || Math.abs(c - g.x) < Math.abs(late - g.x)) late = c;
        }
        if (best !== null || late !== null) g.aim(best !== null ? best : late);
    } else g.aim((next.gapL + next.gapR) / 2);
}
// (the physics on their own: nothing comes)
const calm = g => { g.nextRow = 1e9; };
function far(o) {
    const s = start(o), g = s.g, r = { overMs: null, layersAt: {}, rows: [], cookies: 0, meters: 0 };
    const seen = new Set();
    while (g.on && g.dist < 1000 && s.now() < 1000 + 400000) {
        s.tick();
        if (g.state === 'run') steer(g, s.state.width);
        if (!(g.layer in r.layersAt)) r.layersAt[g.layer] = Math.round(g.dist);
        if (g.dist >= 50 && r.soil50 === undefined) r.soil50 = g.soil;
        if (g.dist >= 400 && r.soil400 === undefined) r.soil400 = g.soil;
        for (const row of g.rows)
            if (!seen.has(row)) { seen.add(row); r.rows.push({ gapL: row.gapL, gapR: row.gapR, beetle: row.beetle, alone: row.alone,
                                                                clear: row.clear, speed: g.speed, mid: (row.gapL + row.gapR) / 2 }); }
        if (g.state === 'over') { r.overMs = s.now(); r.hitBy = g.hitBy; r.overAt = g.dist; break; }
    }
    r.meters = g.meters; r.dist = g.dist; r.grabbed = g.grabbed; r.vmax = MOVE.top * BW; r.boxH = BH * 0.9;
    return r;
}
const out = { games: GAMES, layers: LAYERS };
// (he eases to where you point: never a jump, never past it, settled in a second)
{
    const s = start({}), g = s.g;
    while (g.state !== 'run') s.tick();
    calm(g);
    const x0 = g.x, aim = s.state.width - 60, xs = [], vs = [];
    g.aim(aim);
    for (let i = 0; i < 90; i++) { s.tick(); xs.push(g.x); vs.push(g.vx); }
    out.ease = { x0, aim, xs, vs, vmax: MOVE.top * BW, amax: MOVE.accel * BW, ok: g.state };
    // (lean: + going right, back to upright as he stops)
    const turns = [];
    g.aim(60);
    for (let i = 0; i < 120; i++) { s.tick(); turns.push([g.vx, g.turn]); }
    out.lean = turns;
}
// (no aim: he stays; ← held: the same physics)
{
    const s = start({ seed: 2 }), g = s.g;
    while (g.state !== 'run') s.tick();
    calm(g);
    const x0 = g.x;
    for (let i = 0; i < 30; i++) s.tick();
    out.keys = { still: Math.abs(g.x - x0) };
    g.press('left');
    const xs = [];
    for (let i = 0; i < 60; i++) { s.tick(); xs.push(g.x); }
    g.release('left');
    out.keys.xs = xs;
    // (into the wall: up to it, no bounce)
    g.aim(10000);
    const wall = [];
    for (let i = 0; i < 120; i++) { s.tick(); wall.push([g.x, g.vx]); }
    out.wall = { xs: wall, limit: s.state.width - 30 };
}
// (clods: thrown up, falling back, gone; more when he turns hard)
{
    const s = start({ seed: 3 }), g = s.g;
    while (g.state !== 'run') s.tick();
    calm(g);
    const clods = new Map(), count = { still: 0, turning: 0 };
    const watch = (key, ticks) => {
        for (let i = 0; i < ticks; i++) {
            s.tick();
            for (const th of g.things)
                if (th.kind === 'clod') {
                    if (!clods.has(th)) { clods.set(th, { born: s.now(), vys: [] }); count[key]++; }
                    clods.get(th).vys.push(th.vy);
                }
            for (const [th, c] of clods) if (c.gone === undefined && g.things.indexOf(th) < 0) c.gone = s.now() - c.born;
        }
    };
    watch('still', 62);                       // (a second, steady)
    for (let i = 0; i < 4; i++) { g.aim(i %% 2 ? 60 : s.state.width - 60); watch('turning', 16); }   // (a second, turning hard)
    out.clods = { count, list: Array.from(clods.values()).slice(0, 12) };
}
// (his tunnel: where he was, going up with the earth)
{
    const s = start({ seed: 4 }), g = s.g;
    while (g.state !== 'run') s.tick();
    calm(g);
    const laid = [];
    const known = new Set(g.things.filter(th => th.kind === 'tunnel'));
    g.aim(s.state.width - 80);
    for (let i = 0; i < 80; i++) {
        s.tick();
        for (const th of g.things)
            if (th.kind === 'tunnel' && !known.has(th)) { known.add(th); laid.push({ off: th.x + th.w / 2 - g.x, y: th.y }); }
    }
    out.tunnel = laid;
}
// (far, at any width; the rows fair; cookies; the end, the Run's way)
out.far = [];
for (const width of [380, 500, 900]) for (const seed of [1, 2, 3]) out.far.push(Object.assign({ width, seed }, far({ seed, width })));
// (a long frame at the top speed: a pipe right under him still hits him)
{
    const s = start({ seed: 5 }), g = s.g;
    while (g.state !== 'run') s.tick();
    g.dist = 900;   // (twice the start's speed)
    s.tick();
    g.things.length = 0;
    g.rows.length = 0;
    const p = { kind: 'pipe', x: 0, y: g.cy + BH * 0.5, w: s.state.width, h: BH * 0.42, frame: 0, variant: 0, slot: 0 };
    g.things.push(p);
    s.tick(100);
    out.long = { state: g.state, hitBy: g.hitBy };
}
// (resized mid-dig: he and his aim inside at once)
{
    const s = start({ seed: 6, width: 900 }), g = s.g;
    while (g.state !== 'run') s.tick();
    calm(g);
    g.aim(860);
    for (let i = 0; i < 60; i++) s.tick();
    s.state.width = 400;
    s.tick();
    out.resized = { x: g.x, limit: 400 - 30 };
}
// (the end: 5 s, again after 450 ms, its own best)
{
    const s = start({ seed: 7, best: 0 }), g = s.g;
    while (g.state !== 'over' && s.now() < 60000) s.tick();
    const overAt = s.now();
    s.tick(32); g.press('jump'); const tooSoon = g.state;
    let again = null;
    for (let i = 0; i < 40 && again === null; i++) { s.tick(); if (s.now() - overAt > 500) { g.press('jump'); again = g.state; } }
    out.end = { tooSoon, again, asked: Array.from(new Set(s.state.asked)), saved: s.state.saved, grows: s.state.grows.slice() };
    while (g.state !== 'over' && s.now() < 200000) s.tick();
    const o2 = s.now();
    while (g.on && s.now() < o2 + 8000) s.tick();
    out.end.endedAfter = s.now() - o2;
}
const pick = (ok) => { const t = new Talpy({}); return pickGame(t, { stage: () => ({}), px: () => 0, moveTo() {}, say() {}, changed() {},
    best: () => 0, saveBest() {}, grow() {}, runOk: () => ok }, '').name; };
out.randomNoDig = []; for (let i = 0; i < 100; i++) out.randomNoDig.push(pick(false));
console.log(JSON.stringify(out));
""" % (json.dumps(str(TALPY / "games.mjs")), json.dumps(str(TALPY / "dig.mjs")))


class DigTests(unittest.TestCase):
    """Deep Dig (dig.mjs Dig): he digs down, what's buried comes up, you steer him round it."""

    @classmethod
    def setUpClass(cls):
        cls.r = run_node(DIG)

    def test_it_is_a_game_not_where_scored_games_arent(self):
        self.assertEqual(self.r["games"], ["peekaboo", "run", "dig"])
        self.assertEqual(set(self.r["randomNoDig"]), {"peekaboo"})
        self.assertEqual([l[0] for l in self.r["layers"]], [0, 100, 300])

    def test_he_eases_to_where_you_point(self):
        e = self.r["ease"]
        xs, vs, dt = [e["x0"]] + e["xs"], [0] + e["vs"], 0.016
        for a, b in zip(xs, xs[1:]):
            self.assertLessEqual(abs(b - a), e["vmax"] * dt + 0.5)          # (never a jump)
        for a, b in zip(vs, vs[1:]):
            self.assertLessEqual(abs(b - a), e["amax"] * dt * 1.05 + 1)     # (no kick: limited acceleration)
        self.assertTrue(all(x <= e["aim"] + 1e-6 for x in xs))             # (never past where you point)
        settled = next(i for i, x in enumerate(xs) if abs(x - e["aim"]) < 0.5)
        self.assertLess(settled * 16, 1000 * abs(e["aim"] - e["x0"]) / e["vmax"] + 400)   # (as quick as his top speed allows)
        self.assertEqual(xs[-1], e["aim"])                                                # (there: not creeping on)

    def test_he_leans_into_turns_and_back(self):
        turns = self.r["lean"]
        for vx, turn in turns:
            self.assertLessEqual(abs(turn), 20.01)
            if vx < -30:
                self.assertGreater(turn, 0)          # (going left: his paws lead left, his head tilts right)
        signs = [1 if t > 0.01 else -1 if t < -0.01 else 0 for vx, t in turns if abs(vx) > 1]
        self.assertTrue(all(s >= 0 for s in signs) or all(s <= 0 for s in signs))   # (no flip while going one way)
        self.assertLess(abs(turns[-1][1]), 0.5)       # (upright again as he stops)
        tail = [t for vx, t in turns[-40:]]
        self.assertTrue(all(t >= -0.01 for t in tail))   # (no swing past upright)

    def test_keys_steer_with_the_same_physics(self):
        k = self.r["keys"]
        self.assertLess(k["still"], 0.01)              # (no aim: he stays where he is)
        xs = k["xs"]
        self.assertLess(xs[-1], xs[0] - 40)            # (← held: he goes left)
        for a, b in zip(xs, xs[1:]):
            self.assertLessEqual(a - b, 7 * 60 * 0.016 + 0.5)

    def test_into_a_wall_he_slows_never_bounces(self):
        w = self.r["wall"]
        self.assertAlmostEqual(w["xs"][-1][0], w["limit"], delta=0.5)
        self.assertTrue(all(vx >= -1e-6 for x, vx in w["xs"]))   # (never back off it)
        self.assertTrue(all(x <= w["limit"] + 1e-6 for x, vx in w["xs"]))

    def test_clods_fly_and_fall(self):
        c = self.r["clods"]
        self.assertGreater(c["count"]["still"], 2)
        self.assertGreater(c["count"]["turning"], c["count"]["still"])   # (more as he turns hard)
        for clod in c["list"]:
            vys = clod["vys"]
            self.assertLess(vys[0], 0)                                     # (thrown up)
            for a, b in zip(vys, vys[1:]):
                self.assertGreater(b, a)                                   # (gravity: down faster and faster)
            self.assertLessEqual(clod.get("gone", 0), 600 + 16)

    def test_the_tunnel_follows_his_path(self):
        laid = self.r["tunnel"]
        self.assertGreater(len(laid), 4)   # (a piece every 0.3 of his height, each half his height: overlapping)
        for t in laid:
            self.assertLess(abs(t["off"]), 0.5 + 7 * 60 * 0.016)   # (where he is as it's laid: at most a tick's move behind)

    def test_every_row_has_a_reachable_way(self):
        for r in self.r["far"]:
            with self.subTest(width=r["width"], seed=r["seed"]):
                rows = [x for x in r["rows"]]
                self.assertGreater(len(rows), 20)
                prev, beetle = None, False
                for row in rows:
                    if row["beetle"]:
                        self.assertTrue(row["alone"])                      # (a beetle has its row to itself)
                        beetle = True
                        continue
                    self.assertGreaterEqual(row["gapR"] - row["gapL"], 1.6 * 60 - 1e-6)
                    reach = r["vmax"] * max(0, row["clear"] - r["boxH"]) / row["speed"] * 0.7
                    if beetle:   # (he may be anywhere after dodging a beetle: reachable from either side)
                        self.assertLessEqual(max(row["mid"] - 30, r["width"] - 30 - row["mid"]), reach + 1)
                    elif prev is not None:
                        self.assertLessEqual(abs(row["mid"] - prev), reach + 1)
                    prev, beetle = row["mid"], False

    def test_a_steering_player_digs_far_at_any_width(self):
        for r in self.r["far"]:
            with self.subTest(width=r["width"], seed=r["seed"]):
                self.assertIsNone(r["overMs"], f"bumped into {r.get('hitBy')} at {r.get('overAt')} m")
                self.assertGreaterEqual(r["dist"], 1000)
                self.assertEqual(r["layersAt"], {"topsoil": 0, "clay": 100, "rock": 300})
                self.assertEqual(r["soil50"], "#7a5634")
                self.assertEqual(r["soil400"], "#3c3443")

    def test_cookies_add_10_m_each(self):
        for r in self.r["far"]:
            with self.subTest(width=r["width"], seed=r["seed"]):
                self.assertGreater(r["grabbed"], 0)
                self.assertEqual(r["meters"], int(r["dist"]) + 10 * r["grabbed"])

    def test_a_long_frame_still_hits_a_thin_thing(self):
        self.assertEqual(self.r["long"], {"state": "over", "hitBy": "pipe"})

    def test_resized_mid_dig_he_stays_inside(self):
        self.assertLessEqual(self.r["resized"]["x"], self.r["resized"]["limit"] + 1e-6)

    def test_a_bump_ends_it_the_run_way(self):
        e = self.r["end"]
        self.assertEqual(e["tooSoon"], "over")
        self.assertEqual(e["again"], "ready")
        self.assertEqual(e["asked"], ["dig"])
        self.assertTrue(e["saved"])
        self.assertEqual(e["grows"], [True])
        self.assertGreaterEqual(e["endedAfter"], 5000 - 16)
        self.assertLessEqual(e["endedAfter"], 5000 + 32)


class HostTests(unittest.TestCase):
    pet = (UI / "Pet.qml").read_text()
    ts = (ROOT / "vscode/webview/pets/pet.ts").read_text()

    def test_four_quick_clicks_start_a_game_the_third_still_says_stop_it(self):
        for text in (self.pet, self.ts):
            block = text[text.index("quickClicks >= 4"):]
            block = block[:block.index("quickClicks === 3")]
            self.assertIn("wantsToPlay()", block)
            self.assertIn("Hehe, that tickles!", block)            # (not now: the tickle, as before)
            self.assertIn("Aww, stop it…", text[text.index("quickClicks === 3"):][:300])
            self.assertIn("Let's play!", text)

    def test_asleep_he_grumbles_then_wakes_up_for_it_never_while_a_chat_needs_you(self):
        for text in (self.pet, self.ts):
            wants = text[text.index("wantsToPlay()"):]
            wants = wants[:re.search(r"(function |private )startGame\(wake", wants).start()]
            self.assertRegex(wants, r'mood === "needs"\)? ?\{?\s*\n?\s*(this\.talpy\.)?react\("sign"\)')   # he points at the chat
            self.assertRegex(wants, r'!(root|world)\.playful')                                         # Playful off: only the tickle
            self.assertNotIn('mood === "done" &&', wants)                                              # asleep too (clicks or the menu),
            self.assertRegex(wants, r'startGame\((this\.)?mood === "done", name\)')                         # woken up: he yawns first
            self.assertIn("Okay, okay… let's play!", wants)
        # asleep, clicks 1 and 2 "let me sleep", the 3rd "I said let me SLEEP!", the 4th a game
        for text in (self.pet, self.ts):
            pet_it = text[text.index("petIt()"):] if "function petIt" not in text else text[text.index("function petIt"):]
            sleepy = pet_it[:pet_it.index("quickClicks += 1")]
            self.assertRegex(sleepy, r"sleepyClicks >= 4\) \{\s*\n\s*(this\.)?sleepyClicks = 0;?\s*\n\s*if \(!(this\.)?wantsToPlay\(\)\)")
            self.assertLess(sleepy.index("sleepyClicks === 3"), sleepy.index("I said let me SLEEP!"))
            self.assertIn("let me sleep", sleepy)

    def test_it_ends_at_once(self):
        # a chat that needs you, out of sight, a drag, Playful off, Esc, a click outside the stage
        self.assertRegex(self.pet, r'if \(gameOn && mood === "needs"\) \{\s*\n\s*stopGame\(\)')
        self.assertRegex(self.pet, r'onPlayingChanged: \{\s*\n\s*if \(!playing\)\s*\n\s*stopGame\(\)')
        self.assertRegex(self.pet, r"function pull\(\) \{\s*\n\s*stopGame\(\)")
        self.assertRegex(self.pet, r"function push\(\) \{\s*\n\s*stopGame\(\)")
        self.assertIn("sequences: [StandardKey.Cancel]", self.pet)
        full = (UI / "FullRepresentation.qml").read_text()
        self.assertIn("active: root.gameStage !== null", full)
        self.assertIn("root.gameStopWanted = true", full)
        self.assertIn("mouse.accepted = false", full[full.index("root.gameStopWanted = true") - 600:])   # (the click still does its thing)
        self.assertRegex(self.ts, r'if \(this\.play\?\.on && mood === "needs"\) \{\s*\n\s*this\.stopGame\(\)')
        self.assertRegex(self.ts, r"if \(!this\.stage\.live\) \{\s*\n\s*this\.stopGame\(\)")
        self.assertIn('e.key === "Escape"', self.ts)
        self.assertIn("this.stage.root.contains(e.target as Node)", self.ts)
        self.assertRegex((ROOT / "vscode/webview/pets/stage.ts").read_text(), r"if \(world\.playful\) continue;\n\s+p\.stopGame\(\);")

    def test_a_quick_second_click_is_the_games_too(self):
        # (a click soon after the one before comes as a double click: he'd
        # dance, but while a game is on it's a click on him, caught or not)
        for text in (self.pet, self.ts):
            dance = text[text.index("dance()"):] if "function dance()" not in text else text[text.index("function dance()"):]
            dance = dance[:dance.index("Cookie first!")]
            self.assertRegex(dance, r"if \((gameOn|this\.play\?\.on)\) \{")
            self.assertRegex(dance, r"(playGame|this\.play)\.hit\(\)")

    def test_its_only_ticked_and_drawn_while_on(self):
        self.assertIn("enabled: pet.gameOn && pet.playing", self.pet)
        self.assertIn("model: pet.gameOn && !pet.scoredOn ? 3 : 0", self.pet)
        self.assertIn("if (this.play?.on) this.play.tick(now);", self.ts)

    def test_play_with_talpy_in_the_menus(self):
        # one entry a game (Plasma's menu has no submenus); the run only where it's offered
        main = (UI / "main.qml").read_text()
        peekaboo = main[main.index('text: i18n("Play Peekaboo with Talpy")') - 100:][:500]
        self.assertIn('root.playWithTalpy("peekaboo")', peekaboo)
        self.assertIn("visible: Plasmoid.configuration.showPet && root.playful", peekaboo)
        run = main[main.index('text: i18n("Run with Talpy")') - 100:][:500]
        self.assertIn('root.playWithTalpy("run")', run)
        self.assertIn("visible: Plasmoid.configuration.showPet && root.playful && root.runOk", run)
        self.assertIn("readonly property bool runOk: !onDesktop && !lessMotion", main)
        self.assertNotIn('text: i18n("Play with Talpy")', main)
        pkg = json.loads((ROOT / "vscode/package.json").read_text())
        menus = {m["command"]: m["when"] for m in pkg["contributes"]["menus"]["view/title"]}
        titles = {c["command"]: c["title"] for c in pkg["contributes"]["commands"]}
        for command, title in (("talpyDen.playPeekaboo", "Play Peekaboo with Talpy"), ("talpyDen.runWithTalpy", "Run with Talpy")):
            self.assertIn("config.talpyDen.playfulTalpy", menus[command])
            self.assertEqual(titles[command], title)
        self.assertNotIn("talpyDen.playWithTalpy", menus)
        self.assertIn('case "playWithTalpy":', (ROOT / "vscode/webview/main.tsx").read_text())
        self.assertIn("pets.play(msg.game)", (ROOT / "vscode/webview/main.tsx").read_text())


class PlasmaRunTests(unittest.TestCase):
    """Talpy's Run in the Plasma widget: Pet.qml hosts it, PetStrip.qml grows for it."""
    pet = (UI / "Pet.qml").read_text()
    strip = (UI / "PetStrip.qml").read_text()
    main = (UI / "main.qml").read_text()

    def test_the_best_is_shared_and_only_grows(self):
        self.assertIn('<entry name="runBest" type="Int">', (UI.parent / "config/main.xml").read_text())
        shared = self.main[self.main.index("readonly property var sharedKeys"):][:900]
        self.assertIn('"runBest"', shared)
        save = self.main[self.main.index("function saveGameBest("):][:400]
        self.assertIn("Math.max(", save)
        self.assertIn('readonly property var bestKeys: ({ run: "runBest", dig: "digBest" })', self.main)   # (the Run's key kept)
        self.assertIn("saveBest: (name, m) => root.saveGameBest(name, m)", self.pet)
        self.assertIn("best: name => root.gameBest(name)", self.pet)

    def test_the_stage_grows_and_its_status_fades_while_running(self):
        self.assertIn("implicitHeight: running ? gu * runGu : (hero ? gu * 6 : gu * 4.5)", self.strip)
        self.assertRegex(self.strip, r"Behavior on implicitHeight \{")
        status = self.strip[self.strip.index("// The hero's headline"):][:700]
        self.assertIn("opacity: strip.running ? 0 : 1", status)
        self.assertIn("enabled: !strip.running", status)          # (its clicks: the game's meanwhile)
        self.assertIn("grow: on => { strip.runGu = playGame.stageGu; strip.running = on }", self.pet)   # (its height: the game's)
        self.assertIn("height: strip.height", self.pet)          # (the grown stage, for the run)

    def test_presses_and_keys_are_the_games_only_while_running(self):
        overlay = self.strip[self.strip.index("// A scored game: every press on the stage"):][:2400]
        self.assertIn("enabled: strip.running", overlay)
        self.assertIn("acceptedButtons: Qt.LeftButton | Qt.RightButton", overlay)
        self.assertIn('gamePress(mouse.button === Qt.RightButton ? "dig" : "jump")', overlay)
        self.assertIn('gameRelease("dig")', overlay)
        self.assertIn("swiped", overlay)                          # (touch: a swipe down digs)
        keys = self.strip[self.strip.index("// A scored game: its keys"):][:1800]
        self.assertIn("focus: strip.running", keys)
        for key in ("Qt.Key_Space", "Qt.Key_Up", "Qt.Key_Down"):
            self.assertIn(key, keys)
        self.assertIn("event.isAutoRepeat", keys)
        self.assertIn("forceActiveFocus()", self.strip)
        # (the focus it took is given back as the run ends: the search field, say)
        self.assertIn("focusBefore = Window.activeFocusItem", self.strip)
        self.assertIn("f.forceActiveFocus()", self.strip)
        # (no wake-up yawn over his run: it would take his running pose)
        self.assertIn('lastMood === "done" && mood !== "done" && !leaving && !gameOn', self.pet)

    def test_it_draws_the_run(self):
        # (built only while a run is on: no run UI in every pet)
        run_ui = self.pet[self.pet.index("    // A scored game's things (Talpy's Run, Deep Dig)"):][:5600]
        self.assertRegex(run_ui, r"Loader \{\s+active: pet.scoredOn")
        # each thing a picture drawn once, moved each frame: a slot's (the game's), kept between two things,
        # painted again only when its look changes; no canvas painted every frame
        self.assertIn("model: pet.gameSlots", run_ui)
        self.assertIn("pet.gameThing(index)", run_ui)
        self.assertIn("function onGameFrameChanged() { slot.place() }", run_ui)   # (set once a move: no bindings each frame)
        self.assertIn("x = t.x - pet.spritePad", run_ui)
        self.assertIn("if (l === look)", run_ui)
        self.assertIn("T.drawThing(ctx, { kind: d.kind, w: d.w, h: d.h, frame: f, variant: d.variant }, d.dark)", run_ui)
        self.assertIn("sprite.x = -(t.frame % sprite.frames) * sprite.cellW", run_ui)   # (a bird's flap: its pictures side by side)
        self.assertNotIn("onRunFrameChanged", self.pet)
        self.assertIn("gameSlots = playGame.slots", self.pet)
        self.assertIn("clip: true", run_ui)   # (what comes from beyond the stage's edge isn't seen there)
        self.assertIn("model: pet.gameOn && !pet.scoredOn ? 3 : 0", self.pet)   # (Peekaboo's holes not made for a run)
        # (he runs facing what comes: not turned to the mouse meanwhile)
        self.assertIn("!pet.held && !pet.cookieOn && !pet.gameOn && pet.mood !== \"done\"", self.pet)
        self.assertIn("face: left => { view.facingLeft = left },\n            // a scored game's", self.pet)
        self.assertIn("visible: pet.scoredOn", self.pet)
        self.assertIn("- pet.gameLift - floorY", self.pet)        # (up in his jump)
        # (a game may turn him: Deep Dig head-down, about his body's middle)
        self.assertIn("angle: pet.gameTurn !== 0 ? pet.gameTurn : (pet.upright ? 0 : pet.tilt)", self.pet)
        self.assertIn("pet.gameTurn !== 0 ? view.boxY + pet.box * 37 / 64 : view.boxY + pet.box * 30 / 64", self.pet)
        for words in ('i18nc("metres run", "%1 m"', 'i18n("Click to jump · ↓ or right-click to dig")',
                      'i18n("↓ or right-click: dig")', 'i18n("New best! %1 m"', 'i18n("%1 m · best %2 m"',
                      'i18n("Click to run again")'):
            self.assertIn(words, self.pet)

    def test_pictures_follow_the_theme(self):
        # (Review Focus: the theme switched mid-game: every thing's picture drawn again for it)
        self.assertIn("function onGameDarkChanged() { sprite.relook() }", self.pet)   # (the theme's, or Deep Dig's earth)
        self.assertIn(": strip.darkTheme", self.pet[self.pet.index("readonly property bool gameDark:"):][:200])
        ts = (ROOT / "vscode/webview/pets/pet.ts").read_text()
        sprite = ts[ts.index("private thingSprite("):][:400]
        self.assertIn("${dark ? 1 : 0}", sprite)
        self.assertIn("const dark = g.soil ? earthDark(g.soil) : world.dark;", ts)   # (the theme's, or Deep Dig's earth)

    def test_it_starts_by_name_and_ends_when_a_chat_needs_you(self):
        self.assertIn("G.pickGame(talpy, {", self.pet)
        self.assertIn("}, name || \"\")", self.pet)
        self.assertIn("runOk: () => root.runOk", self.pet)
        self.assertIn("pet.wantsToPlay(root.playName)", self.pet)
        self.assertIn("scoredOn = gameOn && G.SCORED.indexOf(playGame.name) >= 0", self.pet)
        self.assertRegex(self.pet, r'if \(gameOn && mood === "needs"\) \{\s+stopGame\(\)')


class PlasmaDigTests(unittest.TestCase):
    """Deep Dig in the Plasma widget: its menu entry, its best, the earth, the pointer and ←/→ steering."""
    pet = (UI / "Pet.qml").read_text()
    strip = (UI / "PetStrip.qml").read_text()
    main = (UI / "main.qml").read_text()

    def test_its_menu_entry_and_best(self):
        dig = self.main[self.main.index('text: i18n("Dig with Talpy")') - 100:][:500]
        self.assertIn('root.playWithTalpy("dig")', dig)
        self.assertIn("visible: Plasmoid.configuration.showPet && root.playful && root.runOk", dig)
        self.assertIn('<entry name="digBest" type="Int">', (UI.parent / "config/main.xml").read_text())
        shared = self.main[self.main.index("readonly property var sharedKeys"):][:1400]
        self.assertLess(shared.index('"digBest"'), shared.index('"suggestReplies"'))
        self.assertIn("property var cfg_digBest", (UI / "ConfigPage.qml").read_text())

    def test_the_pointer_and_keys_steer_him(self):
        overlay = self.strip[self.strip.index("// A scored game: every press on the stage"):][:2600]
        self.assertIn("hoverEnabled: strip.running", overlay)
        self.assertIn("hero.gameAim(mouse.x)", overlay)
        self.assertEqual(overlay.count("hero.gameAim(mouse.x)"), 2)   # (moving, and a tap or click)
        keys = self.strip[self.strip.index("// A scored game: its keys"):][:2200]
        self.assertIn('event.key === Qt.Key_Left ? "left" : "right"', keys)
        self.assertIn("hero.gameRelease(event.key === Qt.Key_Left", keys)

    def test_the_earth_its_words_and_whats_behind(self):
        ui = self.pet[self.pet.index("    // A scored game's things (Talpy's Run, Deep Dig)"):][:6000]
        self.assertIn("color: pet.gameSoil", ui)                # (the earth's colour, as deep as he is)
        self.assertIn('visible: pet.gameSoil !== ""', ui)
        self.assertIn("z = t && G.DECOR.indexOf(t.kind) >= 0 ? 0 : 1", ui)   # (decoration and his tunnel behind)
        self.assertIn("pet.gameDark", ui)                       # (outlines for the earth's colour, not the theme's)
        for words in ('i18n("Move the mouse to steer")', 'i18n("← → to steer")'):
            self.assertIn(words, self.pet)
        self.assertIn("gameSoil = playGame.soil || \"\"", self.pet)


class VsCodeRunTests(unittest.TestCase):
    """Talpy's Run in VS Code: pet.ts hosts it, stage.ts and pets.css grow the stage, view.ts keeps the best."""
    ts = (ROOT / "vscode/webview/pets/pet.ts").read_text()
    stage = (ROOT / "vscode/webview/pets/stage.ts").read_text()
    css = (ROOT / "vscode/webview/pets/pets.css").read_text()
    view = (ROOT / "vscode/src/view.ts").read_text()

    def test_keys_and_presses_are_the_games_only_while_running(self):
        listen = self.ts[self.ts.index("private listenToGame("):][:3600]
        self.assertIn('document.addEventListener("keydown", key, true)', listen)
        self.assertIn('document.addEventListener("keyup", key, true)', listen)
        self.assertIn('document.removeEventListener("keydown", key, true)', listen)
        self.assertIn("typing(e)", listen)                          # (never a key meant for a text field)
        self.assertIn('root.addEventListener("contextmenu", noMenu)', listen)
        self.assertIn('root.addEventListener("pointerdown", press, true)', listen)   # (first: a press on him jumps, isn't a grab)
        self.assertIn('e.button === 2 ? "dig" : "jump"', listen)
        self.assertIn('e.pointerType === "touch"', listen)          # (a touch swiped down digs)
        typing = self.ts[self.ts.index("function typing("):][:500]
        for kind in ("HTMLInputElement", "HTMLTextAreaElement", "isContentEditable"):
            self.assertIn(kind, typing)

    def test_the_stage_grows_and_its_status_fades(self):
        self.assertIn('this.root.classList.toggle("td-running", on)', self.stage)
        self.assertIn("grow: (on) => this.stage.setRunning(on, this.play?.stageGu ?? 11)", self.ts)
        self.assertIn('this.root.style.setProperty("--td-run-gu", String(gu))', self.stage)
        grown = self.css[self.css.index(".td-stage--hero.td-running {"):][:300]
        self.assertIn("min-height: calc(var(--td-gu, 16px) * var(--td-run-gu, 11))", grown)
        self.assertIn("transition: min-height", self.css)
        faded = self.css[self.css.index(".td-running .td-hero-text"):][:300]
        self.assertIn("opacity: 0", faded)
        self.assertIn("pointer-events: none", faded)
        self.assertIn("touch-action: none", grown)   # (a swipe down digs: not a scroll of the view)

    def test_it_draws_the_run(self):
        self.assertIn("drawThing(ctx, th, dark)", self.ts)
        # (each look a picture drawn once, put where the thing is each frame)
        self.assertIn("ctx.drawImage(this.thingSprite(th, k, dark), k * (th.x - SPRITE_PAD), k * (th.y - SPRITE_PAD))", self.ts)
        self.assertIn("let c = this.thingSprites.get(key);", self.ts)
        self.assertIn("ctx && this.gameDrawn !== this.gameMoves", self.ts)   # (redrawn only when it moved)
        self.assertIn("this.gameMoves++", self.ts)
        self.assertIn("!this.cookieOn && !this.play?.on && mood !== \"done\"", self.ts)   # (not turned to the mouse in a game)
        self.assertIn("face: (left) => (this.talpy.facingLeft = left),\n      // a scored game's", self.ts)
        self.assertIn("ground - lift - this.gameLift() - s.floorY", self.ts)
        self.assertIn("const turn = this.gameTurn();", self.ts)   # (a game may turn him: Deep Dig head-down)
        for words in ("m`", "Click to jump · ↓ or right-click to dig", "↓ or right-click: dig", "New best! ", " m · best ",
                      "Click to run again"):
            self.assertIn(words, self.ts)

    def test_not_with_reduced_motion(self):
        self.assertIn("runOk: () => !reducedMotion()", self.ts)
        self.assertIn('this.lastMood === "done" && mood !== "done" && !this.leaving && !this.play?.on', self.ts)
        # (the old command id still starts a game, either: keybindings to it go on working)
        self.assertIn('["talpyDen.playWithTalpy", undefined]', (ROOT / "vscode/src/extension.ts").read_text())
        self.assertIn('if ((name === "run" || name === "dig") && reducedMotion())', self.ts)
        self.assertIn("No running with reduced motion on", self.ts)

    def test_the_best_is_kept_by_the_extension_and_only_grows(self):
        self.assertIn('const RUN_BEST_KEY = "talpyDen.runBest"', self.view)
        self.assertIn("nextBest(this.memento?.get(BEST_KEYS[m.game]), m.best)", self.view)
        self.assertIn('run: RUN_BEST_KEY', self.view)
        self.assertIn('{ type: "gameBest", game: "run", best: this.gameBest("run") }', self.view)
        self.assertIn("saveBest: (name, m) => world.saveBest(name, m)", self.ts)
        self.assertIn("best: (name) => world.best[name]", self.ts)



class VsCodeDigTests(unittest.TestCase):
    """Deep Dig in VS Code: its command, its best, the pointer and ←/→ steering, the earth."""
    ts = (ROOT / "vscode/webview/pets/pet.ts").read_text()
    view = (ROOT / "vscode/src/view.ts").read_text()
    css = (ROOT / "vscode/webview/pets/pets.css").read_text()

    def test_its_command_menu_entry_and_best(self):
        pkg = json.loads((ROOT / "vscode/package.json").read_text())
        titles = {c["command"]: c["title"] for c in pkg["contributes"]["commands"]}
        menus = {m["command"]: m for m in pkg["contributes"]["menus"]["view/title"]}
        self.assertEqual(titles["talpyDen.digWithTalpy"], "Dig with Talpy")
        self.assertEqual(menus["talpyDen.digWithTalpy"]["when"], menus["talpyDen.runWithTalpy"]["when"])
        self.assertIn('["talpyDen.digWithTalpy", "dig"]', (ROOT / "vscode/src/extension.ts").read_text())
        self.assertIn('const DIG_BEST_KEY = "talpyDen.digBest"', self.view)
        self.assertIn('{ type: "gameBest", game: "dig", best: this.gameBest("dig") }', self.view)

    def test_the_pointer_and_keys_steer_him(self):
        listen = self.ts[self.ts.index("private listenToGame("):][:4200]
        self.assertEqual(listen.count("g.aim?.(e.clientX - root.getBoundingClientRect().left)"), 2)   # (moving, and a tap or click)
        self.assertIn("while (this.thingSprites.size >= 160) this.thingSprites.delete(", self.ts)   # (the oldest go, not all at once)
        self.assertIn('e.key === "ArrowLeft" || e.key === "ArrowRight"', listen)
        self.assertIn('if ((name === "run" || name === "dig") && reducedMotion())', self.ts)

    def test_the_earth_its_words_and_whats_behind(self):
        self.assertIn('this.put(c, "soil", "background", g.soil ?? "")', self.ts)   # (the earth's colour)
        self.assertIn("for (const back of [true, false])", self.ts)   # (decoration and his tunnel drawn first: behind)
        self.assertIn("Move the mouse to steer · ← → to steer", self.ts)
        self.assertIn("Click to dig again", self.ts)
        self.assertIn(".td-run-text--earth", self.css)


if __name__ == "__main__":
    unittest.main()
