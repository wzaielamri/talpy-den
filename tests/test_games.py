"""Games with the big Talpy (talpy/games.mjs): four quick clicks on him (or
Play with Talpy in the menu) and he laughs, says "Let's play!" and a game
starts. Peekaboo holes: three holes open, he pops out of one at random, you
click him before he ducks, he's quicker each round, and after a few he
dances and the holes close. 10 to 30 s, ending by itself; Esc, a click
outside, a chat that needs you or the stage out of sight end it at once. No
scores. Ticked and drawn only while it runs."""
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
    const g = pickGame(t, host);
    g.start(now);
    const brainDuring = t.brainOn;
    let ups = 0, last = '', downHits = 0, maxOpen = 0, holes = 0;
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
        if (g.state === 'up' && hitEvery && now - g.since > 500 && ups %% hitEvery === 0) g.hit();
        if (stopAt && now - 1000 > stopAt) g.stop();
    }
    return { ms: now - 1000, rounds: g.round, ups, said, xs: xs.size, brainDuring, brainAfter: t.brainOn, holes, maxOpen,
             holesAfter: g.holes.length, changed, downRounds: g.round };
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
                        px: () => 200, moveTo() {}, say() {}, changed() {} });
g.start(now);
const first = { on: g.on, body: t.st.body, eyes: t.st.eyes };
now += 200; t.tick(now); g.tick(now);
const hit = g.hit();
for (let i = 0; i < 300; i++) { now += 16; t.tick(now); g.tick(now); }
const t2 = new Talpy({});
t2.tick(1000);
const g2 = pickGame(t2, { stage: () => ({ width: 400, ground: 90, unit: 1.5, bodyWidth: 60, bodyHeight: 60, minX: 30, maxX: 370 }),
                          px: () => 200, moveTo() {}, say() {}, changed() {} });
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
const g = pickGame(new Talpy({}), { stage: () => ({}), px: () => 0, moveTo() {}, say() {}, changed() {} });
const ms = [];
for (let r = 0; r < 8; r++) { g.round = r; ms.push(Math.round(g.upMs())); }
console.log(JSON.stringify(ms));""" % json.dumps(str(TALPY / "games.mjs")))
        self.assertEqual(out, sorted(out, reverse=True))
        self.assertLess(out[-1], out[0])
        self.assertGreaterEqual(out[-1], 520)


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

    def test_not_while_he_sleeps_and_never_while_a_chat_needs_you(self):
        for text in (self.pet, self.ts):
            wants = text[text.index("wantsToPlay(fromMenu"):]
            wants = wants[:re.search(r"(function |private )startGame\(wake", wants).start()]
            self.assertRegex(wants, r'mood === "needs"\)? ?\{?\s*\n?\s*(this\.talpy\.)?react\("sign"\)')   # he points at the chat
            self.assertRegex(wants, r'!(root|world)\.playful')                                         # Playful off: only the tickle
            self.assertRegex(wants, r'mood === "done" && !fromMenu')                                   # asleep: clicks don't
            self.assertRegex(wants, r'startGame\((this\.)?mood === "done"\)')                         # the menu wakes him
        # (a click while he sleeps stays grumpy: petIt's sleepy branch comes before the clicks are counted)
        for text in (self.pet, self.ts):
            pet_it = text[text.index("petIt()"):] if "function petIt" not in text else text[text.index("function petIt"):]
            self.assertLess(pet_it.index("let me sleep"), pet_it.index("quickClicks += 1"))

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
        self.assertIn("if (!world.playful) p.stopGame()", (ROOT / "vscode/webview/pets/stage.ts").read_text())

    def test_its_only_ticked_and_drawn_while_on(self):
        self.assertIn("enabled: pet.gameOn && pet.playing", self.pet)
        self.assertIn("model: pet.gameOn ? 3 : 0", self.pet)
        self.assertIn("if (this.play?.on) this.play.tick(now);", self.ts)

    def test_play_with_talpy_in_the_menus(self):
        main = (UI / "main.qml").read_text()
        action = main[main.index('text: i18n("Play with Talpy")') - 100:][:500]
        self.assertIn("root.playWithTalpy()", action)
        self.assertIn("visible: Plasmoid.configuration.showPet && root.playful", action)
        pkg = json.loads((ROOT / "vscode/package.json").read_text())
        menus = {m["command"]: m["when"] for m in pkg["contributes"]["menus"]["view/title"]}
        self.assertIn("config.talpyDen.playfulTalpy", menus["talpyDen.playWithTalpy"])
        self.assertIn('case "playWithTalpy":', (ROOT / "vscode/webview/main.tsx").read_text())


if __name__ == "__main__":
    unittest.main()
