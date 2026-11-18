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
import { pickGame, GAMES } from %s;
function seeded(seed) {   // (mulberry32: the same run each time)
    return () => { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed);
                   t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
}
const GROUND_KINDS = ['pebble', 'stone', 'pot', 'pebbles'];
// A player who looks ahead: jumps a ground thing so he's at his highest over it, digs under a crow
function player(g, px, noDig) {
    let next = null;
    for (const th of g.things)
        if (th.kind !== 'tuft' && th.x + th.w > px - 20 && (!next || th.x < next.x)) next = th;
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
    const said = [], saved = [], grows = [], faced = [];
    const host = {
        stage: () => ({ width: width, height: 176, unit: 1.5, bodyWidth: 60, bodyHeight: 60, minX: 30, maxX: width - 30,
                        ground: o.growing ? Math.min(160, 90 + (now - 1000) / 4) : 160 }),   // (growing: its floor goes down for 280 ms)
        px: () => px, moveTo: x => { px = x; }, say: w => said.push(w), changed: () => {},
        best: () => best, saveBest: m => saved.push(m), grow: on => grows.push(on), face: left => faced.push(left),
    };
    t.facingLeft = true;   // (he faced the other way before)
    const g = pickGame(t, host, 'run');
    g.start(now);
    const r = { name: g.name, hintAtStart: g.hint, growAtStart: grows.slice(), facedAtStart: faced.slice(), things: g.things, sameArray: true, maxThings: 0,
                firstThingMs: null, firstCrowM: null, digHint: false, crowsPassed: 0, maxSpeedUp: 0, speedUpAt600: null,
                overMs: null, overMeters: null, onAtOver: null, hitBy: null, newBest: null, endMs: null, restarted: null };
    let crowNear = false;
    while (g.on && now < 1000 + (o.until || 180000)) {
        now += 16;
        t.tick(now);
        g.tick(now);
        if (g.things !== r.things) r.sameArray = false;
        r.maxThings = Math.max(r.maxThings, g.things.length);
        if (o.growing && !r.early && now - 1000 >= 400)   // (just after the stage grew: what it put there meanwhile)
            r.early = { kinds: g.things.map(th => th.kind), bottoms: g.things.map(th => Math.round(th.y + th.h)) };
        const hitting = g.things.filter(th => th.kind !== 'tuft');
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
                if (!r.seen.has(th)) { r.seen.add(th); r.newX = Math.min(r.newX === undefined ? 1e9 : r.newX, th.x); }
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
    }
    r.endMs = g.on ? null : now - 1000;
    r.bottoms = g.things.map(th => Math.round(th.y + th.h));   // (ground things and tufts: on the floor)
    r.kinds = g.things.map(th => th.kind);
    r.meters = g.meters; r.said = said; r.saved = saved; r.grows = grows; r.things = null; r.seen = null;
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
    noDig: play({ seed: 2, auto: true, noDig: true }),
}));
""" % json.dumps(str(TALPY / "games.mjs"))


class RunTests(unittest.TestCase):
    """Talpy's Run (games.mjs Run): an endless run, jump over what's on the ground, dig under crows."""

    @classmethod
    def setUpClass(cls):
        cls.r = run_node(RUN)

    def test_games_by_name_and_at_random(self):
        self.assertEqual(self.r["games"], ["peekaboo", "run"])
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
        self.assertIn(idle["hitBy"], ["pebble", "stone", "pot"])
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
        self.assertIn(digging["hitBy"], ["pebble", "stone", "pot"])   # (in up to his eyes, a pot still hits him)
        # a crow at head height can't be run under or jumped: only dug under
        no_dig = self.r["noDig"]
        self.assertFalse(no_dig.get("dug"))
        self.assertEqual(no_dig["hitBy"], "crow")

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
        self.assertGreaterEqual(idle["endMs"] - idle["overMs"], 9000)
        self.assertLessEqual(idle["endMs"] - idle["overMs"], 11000)
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
            if kind not in ("crow", "crowHigh"):
                self.assertEqual(bottom, 160, kind)

    def test_its_light(self):
        for r in self.r["far"] + [self.r["wide"]]:
            self.assertTrue(r["sameArray"])                # (one array all run)
            self.assertLessEqual(r["maxThings"], 10)

    def test_every_thing_draws_inside_its_box(self):
        # drawThing (talpy.mjs) draws each kind in its w × h box, top left at the origin
        out = run_node("""
import { drawThing } from %s;
const KINDS = ['pebble', 'stone', 'pot', 'pebbles', 'crow', 'crowHigh', 'tuft'];
const result = {};
for (const kind of KINDS) for (const frame of [0, 1]) {
    const pts = [], paint = { n: 0 };
    let depth = 0;
    const ctx = new Proxy({}, { get: (_, name) => {
        if (['moveTo', 'lineTo'].indexOf(name) >= 0) return (x, y) => pts.push([x, y]);
        if (name === 'bezierCurveTo') return (a, b, c, d, x, y) => pts.push([a, b], [c, d], [x, y]);
        if (name === 'quadraticCurveTo') return (a, b, x, y) => pts.push([a, b], [x, y]);
        if (name === 'arc') return (x, y, r) => pts.push([x - r, y - r], [x + r, y + r]);
        if (name === 'fill' || name === 'stroke') return () => { paint.n++; };
        if (name === 'translate' || name === 'scale' || name === 'rotate' || name === 'setTransform' || name === 'transform')
            return () => { depth++; };
        return () => ({ addColorStop() {} });
    }, set: () => true });
    drawThing(ctx, { kind: kind, x: 0, y: 0, w: 40, h: 24, frame: frame });
    const out = pts.filter(p => p[0] < -1.5 || p[0] > 41.5 || p[1] < -1.5 || p[1] > 25.5);
    result[kind + frame] = { painted: paint.n, points: pts.length, outside: out.length, moved: depth };
}
console.log(JSON.stringify(result));
""" % json.dumps(str(TALPY / "talpy.mjs")))
        for name, r in out.items():
            with self.subTest(name):
                self.assertGreater(r["painted"], 0)
                self.assertGreater(r["points"], 0)
                self.assertEqual(r["outside"], 0)
                self.assertEqual(r["moved"], 0)   # (in its box's own px: no transforms to undo)

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
        self.assertIn("model: pet.gameOn && !pet.runOn ? 3 : 0", self.pet)
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
        save = self.main[self.main.index("function saveRunBest("):][:300]
        self.assertIn("Math.max(", save)
        self.assertIn("saveBest: m => root.saveRunBest(m)", self.pet)
        self.assertIn("best: () => root.runBest", self.pet)

    def test_the_stage_grows_and_its_status_fades_while_running(self):
        self.assertIn("implicitHeight: (hero ? gu * 6 : gu * 4.5) + (running ? gu * 5 : 0)", self.strip)
        self.assertRegex(self.strip, r"Behavior on implicitHeight \{")
        status = self.strip[self.strip.index("// The hero's headline"):][:700]
        self.assertIn("opacity: strip.running ? 0 : 1", status)
        self.assertIn("enabled: !strip.running", status)          # (its clicks: the game's meanwhile)
        self.assertIn("grow: on => { strip.running = on }", self.pet)
        self.assertIn("height: strip.height", self.pet)          # (the grown stage, for the run)

    def test_presses_and_keys_are_the_games_only_while_running(self):
        overlay = self.strip[self.strip.index("// Talpy's Run: every press on the stage"):][:2200]
        self.assertIn("enabled: strip.running", overlay)
        self.assertIn("acceptedButtons: Qt.LeftButton | Qt.RightButton", overlay)
        self.assertIn('runPress(mouse.button === Qt.RightButton ? "dig" : "jump")', overlay)
        self.assertIn('runRelease("dig")', overlay)
        self.assertIn("swiped", overlay)                          # (touch: a swipe down digs)
        keys = self.strip[self.strip.index("// Talpy's Run: its keys"):][:1600]
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
        self.assertIn("T.drawThing(ctx, th, strip.darkTheme)", self.pet)
        # (built only while a run is on: no run UI in every pet)
        run_ui = self.pet[self.pet.index("    // Talpy's Run: what's on his way"):][:500]
        self.assertRegex(run_ui, r"Loader \{\s+active: pet.runOn")
        self.assertIn("model: pet.gameOn && !pet.runOn ? 3 : 0", self.pet)   # (Peekaboo's holes not made for a run)
        # (he runs facing what comes: not turned to the mouse meanwhile)
        self.assertIn("!pet.held && !pet.cookieOn && !pet.gameOn && pet.mood !== \"done\"", self.pet)
        self.assertIn("face: left => { view.facingLeft = left },\n            // Talpy's Run's", self.pet)
        self.assertIn("visible: pet.runOn", self.pet)
        self.assertIn("- pet.runLift - floorY", self.pet)        # (up in his jump)
        for words in ('i18nc("metres run", "%1 m"', 'i18n("Click to jump · ↓ or right-click to dig")',
                      'i18n("↓ or right-click: dig")', 'i18n("New best! %1 m"', 'i18n("%1 m · best %2 m"',
                      'i18n("Click to run again")'):
            self.assertIn(words, self.pet)

    def test_it_starts_by_name_and_ends_when_a_chat_needs_you(self):
        self.assertIn("G.pickGame(talpy, {", self.pet)
        self.assertIn("}, name || \"\")", self.pet)
        self.assertIn("runOk: () => root.runOk", self.pet)
        self.assertIn("pet.wantsToPlay(root.playName)", self.pet)
        self.assertIn('runOn = gameOn && playGame.name === "run"', self.pet)
        self.assertRegex(self.pet, r'if \(gameOn && mood === "needs"\) \{\s+stopGame\(\)')


class VsCodeRunTests(unittest.TestCase):
    """Talpy's Run in VS Code: pet.ts hosts it, stage.ts and pets.css grow the stage, view.ts keeps the best."""
    ts = (ROOT / "vscode/webview/pets/pet.ts").read_text()
    stage = (ROOT / "vscode/webview/pets/stage.ts").read_text()
    css = (ROOT / "vscode/webview/pets/pets.css").read_text()
    view = (ROOT / "vscode/src/view.ts").read_text()

    def test_keys_and_presses_are_the_games_only_while_running(self):
        listen = self.ts[self.ts.index("private listenToRun("):][:3200]
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
        self.assertIn("grow: (on) => this.stage.setRunning(on)", self.ts)
        grown = self.css[self.css.index(".td-stage--hero.td-running {"):][:300]
        self.assertIn("min-height: calc(var(--td-gu, 16px) * 11)", grown)
        self.assertIn("transition: min-height", self.css)
        faded = self.css[self.css.index(".td-running .td-hero-text"):][:300]
        self.assertIn("opacity: 0", faded)
        self.assertIn("pointer-events: none", faded)
        self.assertIn("touch-action: none", grown)   # (a swipe down digs: not a scroll of the view)

    def test_it_draws_the_run(self):
        self.assertIn("drawThing(ctx, th, world.dark)", self.ts)
        self.assertIn("ctx && this.runDrawn !== this.runMoves", self.ts)   # (redrawn only when it moved)
        self.assertIn("this.runMoves++", self.ts)
        self.assertIn("!this.cookieOn && !this.play?.on && mood !== \"done\"", self.ts)   # (not turned to the mouse in a game)
        self.assertIn("face: (left) => (this.talpy.facingLeft = left),\n      // Talpy's Run's", self.ts)
        self.assertIn("ground - lift - this.runLift() - s.floorY", self.ts)
        for words in ("m`", "Click to jump · ↓ or right-click to dig", "↓ or right-click: dig", "New best! ", " m · best ",
                      "Click to run again"):
            self.assertIn(words, self.ts)

    def test_not_with_reduced_motion(self):
        self.assertIn("runOk: () => !reducedMotion()", self.ts)
        self.assertIn('this.lastMood === "done" && mood !== "done" && !this.leaving && !this.play?.on', self.ts)
        # (the old command id still starts a game, either: keybindings to it go on working)
        self.assertIn('["talpyDen.playWithTalpy", undefined]', (ROOT / "vscode/src/extension.ts").read_text())
        self.assertIn('if (name === "run" && reducedMotion())', self.ts)
        self.assertIn("No running with reduced motion on", self.ts)

    def test_the_best_is_kept_by_the_extension_and_only_grows(self):
        self.assertIn('const RUN_BEST_KEY = "talpyDen.runBest"', self.view)
        self.assertIn("nextBest(this.memento?.get(RUN_BEST_KEY), m.best)", self.view)
        self.assertIn('{ type: "runBest", best: this.runBest() }', self.view)
        self.assertIn("saveBest: (m) => world.saveRunBest(m)", self.ts)


if __name__ == "__main__":
    unittest.main()
