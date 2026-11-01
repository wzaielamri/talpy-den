"""Talpy, the pet: what the widget asks of it exists, its shared code runs in
every host, and its rules hold (run in Node where it's installed)."""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "package/contents"
PETS = ROOT / "pets"
TALPY = ROOT / "ui/talpy"
# The settings' categories (every front end, this order) and Plasma's page for each
CATEGORIES = ["General", "Chats", "Notifications", "Usage & limits", "Talpy", "Recap", "Hosts", "Advanced"]
SETTINGS_PAGES = ["configGeneral.qml", "configChats.qml", "configNotifications.qml", "configUsage.qml", "configTalpy.qml",
                  "configRecap.qml", "configHosts.qml", "configAdvanced.qml"]


def quoted(text):
    return set(re.findall(r'"([a-zA-Z][\w-]*)"', text))


def talpy_names():
    text = (TALPY / "actions.mjs").read_text()
    actions = text[text.index("export const ACTIONS = {"):text.index("export const MOODS")]
    moods = text[text.index("export const MOODS"):]
    pools = re.findall(r"pool: \{([^}]*)\}", moods)
    return (set(re.findall(r"^    (\w+): \{", actions, re.M)) | {"comego"} - {"comego"},
            set(re.findall(r"^    (\w+): \{ base", moods, re.M)),
            {n for pool in pools for n in re.findall(r"(\w+):", pool)})


def run_node(script):
    """Runs a module script in Node with Talpy imported; returns its JSON output."""
    if not shutil.which("node"):
        raise unittest.SkipTest("node isn't installed")
    code = (f"import {{ Talpy }} from {json.dumps(str(TALPY / 'talpy.mjs'))};\n"
            f"import {{ ACTIONS, MOODS }} from {json.dumps(str(TALPY / 'actions.mjs'))};\n"
            f"import {{ Pictures }} from {json.dumps(str(TALPY / 'pictures.mjs'))};\n"
            f"import {{ Films }} from {json.dumps(str(TALPY / 'films.mjs'))};\n" + script)
    out = subprocess.run(["node", "--input-type=module", "-e", code], capture_output=True, text=True, timeout=120)
    if out.returncode:
        raise AssertionError(out.stderr)
    return json.loads(out.stdout)


NEEDS_PLASMA5SUPPORT = unittest.skipUnless(shutil.which("python3") and subprocess.run(
    ["python3", "-c", "import PySide6.QtQuick, PySide6.QtCore as c, os; os.stat(os.path.join("
     "c.QLibraryInfo.path(c.QLibraryInfo.LibraryPath.QmlImportsPath), 'org/kde/plasma/plasma5support'))"],
    capture_output=True).returncode == 0, "needs PySide6 and Plasma's plasma5support QML module")
NEEDS_PLASMA_QML = unittest.skipUnless(shutil.which("python3") and subprocess.run(
    ["python3", "-c", "import PySide6.QtQuick, PySide6.QtCore as c, os; q = c.QLibraryInfo.path("
     "c.QLibraryInfo.LibraryPath.QmlImportsPath); [os.stat(os.path.join(q, m)) for m in "
     "('org/kde/plasma/components', 'org/kde/plasma/core', 'org/kde/kirigami')]"],
    capture_output=True).returncode == 0, "needs PySide6 and Plasma's and Kirigami's QML modules")


def run_hub(body, ms):
    """Runs hub/Hub.qml offscreen for ms, with body added to an Item (t) whose
    t.command (a status check) and t.live (a live.py) count their runs; another
    DataSource holds Plasma's executable engine all along, as in plasmashell.
    Returns (status answers the copies got, runs of t.command, runs of t.live,
    answers of the live watcher, stderr)."""
    import os
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for name, wait, answer in (("check", "0.15", '{"ok": true}'), ("live", "0.3", '{"ok": true, "sessions": true}')):
            (tmp / f"{name}.sh").write_text(f"#!/bin/sh\necho x >> {tmp}/{name}.runs\nsleep {wait}\necho '{answer}'\n")
        (tmp / "t.qml").write_text(
            f'import QtQuick\nimport "{(ROOT / "ui/hub").as_uri()}"\nItem {{\n  id: t\n'
            '  property int outputs: 0\n  property int liveAnswers: 0\n'
            f'  readonly property string command: "sh {tmp}/check.sh"\n'
            f'  readonly property string live: "sh {tmp}/live.sh"\n'
            '  Connections { target: Hub; function onOutput(c, out, err) { t.outputs++ } }\n'
            '  Connections { target: Hub.liveRunner; function onNewData(s, d) { t.liveAnswers++ } }\n'
            '  Exec { Component.onCompleted: connectSource("sleep 30") }\n'
            f'{body}\n}}\n')
        script = (
            "import sys\n"
            "from PySide6.QtCore import QUrl, QTimer\n"
            "from PySide6.QtGui import QGuiApplication\n"
            "from PySide6.QtQuick import QQuickView\n"
            "app = QGuiApplication(sys.argv)\n"
            "view = QQuickView()\n"
            "view.setSource(QUrl.fromLocalFile(sys.argv[1]))\n"
            "r = view.rootObject()\n"
            "QTimer.singleShot(int(sys.argv[2]), app.quit)\n"
            "app.exec()\n"
            "print(r.property('outputs'), r.property('liveAnswers'))\n")
        out = subprocess.run(["python3", "-c", script, str(tmp / "t.qml"), str(ms)], capture_output=True, text=True,
                             timeout=60, env=dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_FORCE_STDERR_LOGGING="1"))
        runs = [len((tmp / f"{name}.runs").read_text().split()) if (tmp / f"{name}.runs").exists() else 0
                for name in ("check", "live")]
    if not out.stdout.split():
        raise AssertionError(out.stderr[-2000:])
    outputs, live_answers = (int(n) for n in out.stdout.split()[-2:])
    return outputs, runs[0], runs[1], live_answers, out.stderr


# A canvas that draws nothing, for running Talpy's drawing code (and one
# that counts what it's asked to draw)
CALL_COUNTER = """
let calls = 0;
const ctx = new Proxy({}, { get: (t, k) => k === 'createLinearGradient' || k === 'createRadialGradient' ? () => ({ addColorStop() {} })
    : k in t ? t[k] : () => { calls++; }, set: (t, k, v) => { t[k] = v; return true; } });
"""
NULL_CANVAS = """
const ctx = new Proxy({}, { get: (t, k) => k === 'createLinearGradient' ? () => ({ addColorStop() {} })
    : k in t ? t[k] : () => {}, set: (t, k, v) => { t[k] = v; return true; } });
"""


class TalpyTests(unittest.TestCase):
    def test_every_action_and_mood_the_widget_asks_for_exists(self):
        actions, moods, pools = talpy_names()
        pet = (ROOT / "ui/Pet.qml").read_text()
        asked = set()
        for call in re.findall(r"react\(([^)]*)\)", pet):
            asked |= quoted(call)
        events = pet[pet.index("const action = {"):]
        asked |= quoted(events[:events.index("\n")])
        self.assertEqual(sorted(asked - actions), [], "actions Pet.qml asks for that Talpy doesn't have")
        self.assertLessEqual(pools, actions, "a mood picks an action that doesn't exist")
        block = pet[pet.index("readonly property string mood:"):]
        main = (ROOT / "ui/main.qml").read_text()
        mood = main[main.index("readonly property string petMood"):]
        used = quoted(block[:block.index("\n\n")]) | quoted(mood[:mood.index("\n    }\n")])
        used -= {"waiting", "working", "idle", "failed"} - moods   # (the chat states it reads)
        self.assertEqual(sorted(used - moods - {"waiting"}), [], "moods the widget sets that Talpy doesn't have")

    def test_the_shared_code_runs_in_every_host(self):
        # Qt's and GNOME Shell's JavaScript engines: no optional chaining, no
        # nullish operator, no class fields; imports only of its own modules
        for path in TALPY.glob("*.mjs"):
            text = re.sub(r"//.*", "", path.read_text())
            self.assertNotRegex(text, r"\?\.[\w(\[]|\?\?", path.name)
            for body in re.findall(r"(?ms)^(?:export )?class \w+ \{\n(.*?)^\}", text):
                self.assertNotRegex(body, r"(?m)^    (static\s+)?#?\w+\s*=", path.name)
            for spec in re.findall(r"from '([^']+)'", text):
                self.assertRegex(spec, r"^\./\w+\.mjs$", path.name)

    def test_every_action_runs_to_its_end_and_draws(self):
        result = run_node(NULL_CANVAS + """
const out = {};
for (const name of Object.keys(ACTIONS)) {
    const t = new Talpy({ travels: true });
    t.onTravel = () => {};
    let now = 1000, ended = null;
    t.tick(now);
    t.react(name, ok => { ended = ok; });
    for (let i = 0; i < 600 && ended === null; i++) { now += 50; t.tick(now); t.draw(ctx); }
    out[name] = ended;
}
console.log(JSON.stringify(out));""")
        self.assertEqual({k for k, v in result.items() if v is not True}, set())

    def test_while_held_nothing_else_moves_it(self):
        # It was petted, then grabbed while the petting went on: the action
        # ending gave the brain its turn, and it dug a burrow in mid-air
        # (seen on the design page, 2026-10-23). Held, it waits; dropped, it
        # lands and digs in where it landed. (Its depth is taken as the landing
        # ends: a while later its brain may well have taken it out again, at
        # random.)
        result = run_node(NULL_CANVAS + """
const t = new Talpy({ travels: true });
t.onTravel = () => {};
let now = 1000;
t.tick(now);
t.react('pet');
for (let i = 0; i < 8; i++) { now += 50; t.tick(now); }
t.setHeld(true);
t.setMood('working');
const held = [];
for (let i = 0; i < 120; i++) { now += 50; t.tick(now); t.draw(ctx); held.push([t.st.depth, t.st.held, !!t.run]); }
let landed = null, depth = null;
t.land(50, ok => { landed = ok; depth = t.st.depth; });
for (let i = 0; i < 120; i++) { now += 50; t.tick(now); }
console.log(JSON.stringify({ held: held, landed: landed, depth: depth, after: t.held }));""")
        self.assertEqual({tuple(h) for h in result["held"]}, {("out", "1", False)})
        self.assertTrue(result["landed"])
        self.assertNotEqual(result["depth"], "out")
        self.assertFalse(result["after"])

    def test_the_hole_stays_where_it_was_when_you_pull_it_out(self):
        # The hole shrank (350 ms) while it followed the pet you pulled out of
        # it, as if carried along (2026-10-26). Now the pet has none from the
        # moment you grab it, setHeld says how much of its hole is left behind,
        # and the widget keeps drawing that where it was until the pet landed.
        result = run_node("""
import { drawHole } from %s;
const left = {};
for (const [name, setup] of [
    ['in its burrow', t => t.tick(1040)],
    ['half dug in', t => { t.react('arrive'); t.tick(1040); }],
    ['tunnelling', t => { t.onTravel = () => {}; t.react('dig'); for (let i = 0; i < 30; i++) t.tick(1040 + i * 50); }],
    ['away', t => { t.react('leave'); for (let i = 0; i < 80; i++) t.tick(1040 + i * 50); }]]) {
    const t = new Talpy({ brain: false });
    t.tick(1000); setup(t);
    const was = t.v.hole;
    const open = t.setHeld(true);
    left[name] = [Number(was.toFixed(2)), Number(open.toFixed(2)), t.v.hole];
}
const drawn = [];
const ctx = new Proxy({}, { get: (t, k) => k === 'fill' || k === 'stroke' ? () => drawn.push(k)
    : k in t ? t[k] : () => {}, set: (t, k, v) => { t[k] = v; return true; } });
drawHole(ctx, 1);
const t = new Talpy({ brain: false });
console.log(JSON.stringify({ left: left, drawn: drawn.length, again: t.setHeld(false) }));""" % json.dumps(str(TALPY / "talpy.mjs")))
        self.assertEqual(result["left"]["in its burrow"][1:3], [1, 0])
        for name, (was, open, hole) in result["left"].items():
            self.assertEqual(hole, 0, name + ": its hole stays behind")
            self.assertEqual(open > 0, was > 0.02 and name != "tunnelling", name)
        self.assertGreater(result["drawn"], 10)
        self.assertEqual(result["again"], 0)
        pet = (ROOT / "ui/Pet.qml").read_text()
        self.assertIn("const open = talpy.setHeld(true)", pet)
        self.assertIn("T.drawHole(ctx, open)", pet)
        # (the one it left under the pet, filled in once it has landed)
        self.assertLess(pet.index("id: leftHole"), pet.index("id: view"))
        landed = pet[pet.index("function landed("):]
        self.assertIn("closeHole.restart()", landed[:landed.index("talpy.land(")])

    def test_it_asks_to_be_drawn_only_as_often_as_it_changes(self):
        # Drawing every pet 30 times a second made Plasma Shell busy (four
        # desktop dashboards: 90% of a core, 2026-10-23). At rest it asks for
        # 5 pictures a second; quick moves (held, digging) get 25.
        result = run_node("""
const t = new Talpy({ brain: false });
let now = 1000;
t.tick(now);
t.pose({ eyes: 'closed', mouth: 'small', depth: 'low' });   // asleep: no blinking
const rest = [];
for (let i = 0; i < 40; i++) { now += 40; t.tick(now); rest.push(t.frameMs); }
t.setHeld(true);
now += 40; t.tick(now);
const held = t.frameMs;
t.land(10, null);
const landing = [];
for (let i = 0; i < 10; i++) { now += 40; t.tick(now); landing.push(t.frameMs); }
console.log(JSON.stringify({ rest: rest.slice(10), held: held, landing: landing }));""")
        self.assertEqual(set(result["rest"]), {200})
        self.assertEqual(result["held"], 40)
        self.assertIn(40, result["landing"])

    def test_a_pet_whose_spot_moves_hurries_there(self):
        # A new chat makes room in the row: the others dig over quicker than
        # when the hero wanders off by itself
        result = run_node("""
const length = name => { const steps = ACTIONS[name].steps(s => s); return steps.reduce((sum, s) => sum + (s.t || 600), 0); };
console.log(JSON.stringify({ scoot: length('scoot'), dig: length('dig'),
                             travels: ACTIONS.scoot.steps(s => s).some(s => s.travel) }));""")
        self.assertTrue(result["travels"])
        self.assertLess(result["scoot"], result["dig"] * 0.6)
        pet = (ROOT / "ui/Pet.qml").read_text()
        self.assertIn("digTo(homeX, true)", pet)
        self.assertIn('react(quick ? "scoot" : "dig")', pet)

    def test_the_hero_walks_anywhere_on_its_stage_over_the_headline(self):
        # The user wanted the big Talpy free to go left too, not kept to the
        # right half clear of the headline: it walks in front of the words
        pet = (ROOT / "ui/Pet.qml").read_text()
        strip = (ROOT / "ui/PetStrip.qml").read_text()
        gnome = (ROOT.parent.parent / "gnome/extension/ui/pets.js").read_text()
        self.assertIn("readonly property real minX: reach\n", pet)
        self.assertNotIn("strip.width * 0.5", pet)
        self.assertNotIn("stage.width * 0.5", gnome)
        self.assertIn("z: pets.parent.hero ? 2 : 0", strip)

    def test_the_pets_stand_in_the_order_of_the_list(self):
        # The user got confused when the pets stood in the order their chats
        # came, not in the list's
        strip = (ROOT / "ui/PetStrip.qml").read_text()
        section = (ROOT / "ui/GroupSection.qml").read_text()
        self.assertIn("order: out.length", section)
        self.assertIn("shownChats.slice().sort((a, b) => a.order - b.order)", strip)

    def test_a_new_pet_waits_while_another_digs_away(self):
        # none tunnels over a pet that waves goodbye or digs up where it still
        # stands; once it's gone the others move up and the new one comes
        strip = (ROOT / "ui/PetStrip.qml").read_text()
        stage = (ROOT.parent.parent / "vscode/webview/pets/stage.ts").read_text()
        gnome = (ROOT.parent.parent / "gnome/extension/ui/pets.js").read_text()
        self.assertLess(strip.index("if (petModel.get(i).leaving)"), strip.index("petModel.append({ petKey: c.key"))
        self.assertLess(stage.index("if (!this.pets.some((p) => p.leaving)) {"), stage.index("this.pets.push(new Pet(this, c.key"))
        chats = gnome[gnome.index("    setChats(chats) {"):]
        self.assertLess(chats.index("if (!this._anyLeaving) {"), chats.index("this.order = "))
        self.assertLess(chats.index("if (!this._anyLeaving) {"), chats.index("new Pet(this, c.key"))
        self.assertIn("this.setChats(this.chats);", gnome[gnome.index("    removePet(key) {"):][:900])
        # (and the tooltip of +N says 1 more chat, as Plasma's i18np)
        self.assertIn("L.plural(this.hidden, '%1 more chat', '%1 more chats')", gnome)

    def test_whatever_is_in_the_burrow_has_its_hole_around_it(self):
        # A new pet sank first while its hole shrank away, jumping out of the
        # burrow closed the hole under it, digging in after a drop began in a
        # hole still opening: bits of it showed where there was no hole
        # (2026-10-23). Now, whenever some of it is down in the burrow (and
        # not all of it, lamp included), the hole is all there.
        result = run_node("""
const t = new Talpy({ brain: false });
t.onTravel = () => {};
let now = 1000, bad = [];
const watch = (name, ms) => {
    for (let i = 0; i < ms / 20; i++) {
        now += 20; t.tick(now);
        const v = t.v;
        if (v.depth > 0 && v.depth < 52 && v.hole < 0.95 && t.st.tunnel !== '1')
            bad.push(name + ' at ' + (i * 20) + ' ms: depth ' + v.depth.toFixed(1) + ', hole ' + v.hole.toFixed(2));
    }
};
t.tick(now); t.setMood('working'); watch('rest', 500);
t.react('arrive'); watch('arrive', 3500);
t.react('finished'); watch('finished', 2500);
t.react('celebrate'); watch('celebrate', 4000);
t.react('sneeze'); watch('sneeze', 3500);
t.react('dig'); watch('dig', 4500);
t.setHeld(true); watch('held', 600);
t.land(30, null); watch('land', 3500);
t.react('leave'); watch('leave', 3000);
watch('after leaving', 3000);    // (down there until it arrives again)
const away = t.v.depth;
t.react('arrive'); watch('back', 3500);
console.log(JSON.stringify({ bad: bad.slice(0, 5), away: away, back: t.v.depth }));""")
        self.assertEqual(result["bad"], [])
        self.assertGreater(result["away"], 60)
        self.assertLess(result["back"], 15)

    def test_it_never_clips_inside_a_clip(self):
        # Qt's canvas puts a clip back under the wrong transform once a clip
        # made inside it is undone: Talpy's cut slid down by its depth and its
        # hands showed under the burrow in Plasma (2026-10-23). So its drawing
        # makes at most one clip at a time.
        result = run_node("""
let depth = 0, clipped = [false], nested = 0;
const ctx = new Proxy({}, { get: (t, k) => {
    if (k === 'save') return () => clipped.push(clipped[clipped.length - 1]);
    if (k === 'restore') return () => { if (clipped.length > 1) clipped.pop(); };
    if (k === 'clip') return () => { if (clipped[clipped.length - 1]) nested++; clipped[clipped.length - 1] = true; };
    if (k === 'createLinearGradient') return () => ({ addColorStop() {} });
    return k in t ? t[k] : () => {};
}, set: (t, k, v) => { t[k] = v; return true; } });
let now = 1000;
for (const name of Object.keys(ACTIONS)) {
    const t = new Talpy({ brain: false });
    t.onTravel = () => {};
    t.tick(now); t.react(name);
    for (let i = 0; i < 200 && t.run; i++) { now += 50; t.tick(now); t.draw(ctx); }
}
console.log(JSON.stringify({ nested: nested }));""")
        self.assertEqual(result["nested"], 0)

    def test_how_it_looks_after_a_fall_is_what_it_says(self):
        # "Ugh… I don't feel so good." came with a happy face: the widget
        # judged the height its own way. Now Talpy says how it feels.
        result = run_node("""
const out = {};
for (const h of [5, 20, 35]) {
    const t = new Talpy({ brain: false });
    t.tick(1000); t.setHeld(true); t.tick(1040);
    const feel = t.land(h, null); t.tick(1080);
    out[h] = [feel, t.st.eyes];
}
console.log(JSON.stringify(out));""")
        self.assertEqual(result["5"], ["fine", "happy"])
        self.assertEqual(result["20"], ["dizzy", "spiral"])
        self.assertEqual(result["35"], ["sick", "spiral"])
        pet = (ROOT / "ui/Pet.qml").read_text()
        self.assertIn('const feel = talpy.land(', pet)
        self.assertIn('if (feel === "sick")', pet)

    def test_a_chats_pet_as_pictures_shows_every_action(self):
        # Only the big Talpy is drawn every frame; a chat's pet shows pictures
        # (stillKey / drawStill), drawn when what it shows changes. Every
        # action still shows each of its poses, a quick move as two pictures.
        result = run_node(NULL_CANVAS + """
let now = 1000;
const out = { shown: {}, typing: new Set(), quiet: 0 };
for (const name of Object.keys(ACTIONS)) {
    const t = new Talpy({ brain: false });
    t.onTravel = () => {};
    t.tick(now); t.react(name);
    const poses = new Set(), steps = new Set();
    for (let i = 0; i < 400 && t.run; i++) {
        now += 40; t.tick(now);
        if (!t.run) break;
        steps.add(t.run.i);
        const key = t.stillKey();
        poses.add(key.split('#')[0]);
        t.drawStill(ctx);
        if (name === 'typing' && t.st.arms === 'type') out.typing.add(key);
    }
    out.shown[name] = poses.size >= 1 && poses.size >= Math.min(steps.size, 1);
}
// resting, asleep, it changes its picture only now and then
const t = new Talpy({}); t.tick(now); t.setMood('done');
let last = '';
for (let i = 0; i < 250; i++) { now += 40; t.tick(now); const k = t.stillKey(); if (k !== last) { out.quiet++; last = k; } }
out.typing = out.typing.size;
console.log(JSON.stringify(out));""")
        self.assertEqual([n for n, ok in result["shown"].items() if not ok], [])
        self.assertGreaterEqual(result["typing"], 2)          # the hands go up and down
        self.assertLess(result["quiet"], 25)                   # 10 s asleep: a few pictures, not 250
        pet = (ROOT / "ui/Pet.qml").read_text()
        self.assertIn("live: pet.landing", pet)

    def test_a_new_pose_mixes_in_and_never_shows_the_background(self):
        # Pictures faded half see-through one over the other let a quarter of
        # the background through: chat pets went darker, then lighter again,
        # at every new pose (2026-10-25). A pose now fades in mixed with the
        # one in front, added up, and both pictures are there all along.
        result = run_node(NULL_CANVAS + """
let seed = 7;
Math.random = () => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648; };
const out = { fades: 0, bad: [] };
for (const mood of ['working', 'agents', 'needs', 'idle', 'done', 'failed', 'limit']) {
    const t = new Talpy({}); let now = 1e12; t.tick(now); t.setMood(mood);
    const p = new Pictures(t, 5);
    let fading = false;
    for (let i = 0; i < 3000; i++) {
        now += 40; t.tick(now); p.tick(now);
        for (const s of p.sheets) if (s.paint) { s.paint = false; p.paint(s, ctx); }
        if (p.coming) {
            if (!fading) out.fades++;
            if (!p.coming.ready || !p.front.ready || p.coming === p.front || !(p.mix >= 0 && p.mix < 1))
                out.bad.push([mood, i, p.mix]);
        }
        fading = p.coming !== null;
    }
}
console.log(JSON.stringify(out));""")
        self.assertEqual(result["bad"], [])
        self.assertGreater(result["fades"], 50)
        # GNOME adds the two up (not one over the other); the widget plays films
        gnome = (ROOT.parent.parent / "gnome/extension/ui/pets.js").read_text()
        self.assertIn("cr.setOperator(Cairo.Operator.ADD)", gnome)

    def test_a_quick_move_goes_round_its_pictures_without_drawing_them_again(self):
        # Typing showed two pictures a beat apart (choppy); now four, each
        # drawn once and then shown again as the hands go round
        result = run_node(NULL_CANVAS + """
const t = new Talpy({ brain: false }); let now = 1e12; t.tick(now);
t.pose({ arms: 'type', prop: 'laptop', depth: 'high', look: [0, 1.6], mouth: 'none' });
const p = new Pictures(t, 5);
const paints = [], shown = new Set();
for (let i = 0; i < 100; i++) {
    now += 40; t.tick(now); p.tick(now);
    for (const s of p.sheets) if (s.paint) { s.paint = false; p.paint(s, ctx); paints.push(i); }
    if (p.front.ready) shown.add(p.front.key);
}
console.log(JSON.stringify({ shown: shown.size, late: paints.filter(i => i > 30).length, all: paints.length }));""")
        self.assertGreaterEqual(result["shown"], 3)    # the hands down, halfway, up
        self.assertLessEqual(result["all"], 5)
        self.assertEqual(result["late"], 0)             # after the first round: no drawing

    def test_a_big_move_is_drawn_live_and_whatever_flies_lands_first(self):
        # A jump, popping out of the burrow: no picture shows those, so
        # they're drawn live (12 a second), and the confetti lands before
        # there are pictures again
        result = run_node(NULL_CANVAS + """
const t = new Talpy({}); let now = 1e12; t.tick(now); t.setMood('working');
for (let i = 0; i < 10; i++) { now += 40; t.tick(now); }
const p = new Pictures(t, 5);
t.react('finished');
let live = 0, paints = 0, confettiAtEnd = -1;
for (let i = 0; i < 120; i++) {
    now += 40; t.tick(now); p.tick(now);
    for (const s of p.sheets) if (s.paint) { s.paint = false; p.paint(s, ctx); if (s.key === '') paints++; }
    if (p.front.key === '') {
        live++;
        confettiAtEnd = t.fx.filter(f => f.kind === 'confetti' && now - f.born < f.o.dur * 1000).length;
    }
}
console.log(JSON.stringify({ live: live, paints: paints, confetti: confettiAtEnd, still: p.front.key !== '' }));""")
        self.assertGreater(result["live"], 20)                            # the jump (800 ms) and the confetti
        self.assertLessEqual(result["paints"], result["live"] / 2 + 2)   # at most every 80 ms
        self.assertLessEqual(result["confetti"], 1)
        self.assertTrue(result["still"])

    def test_pictures_cost_about_what_they_did(self):
        # Pictures are there to keep Plasma Shell quiet (four desktop
        # dashboards): drawings per second per pet, by mood (before smooth
        # moves and mixing in: 1.0 to 2.6)
        result = run_node(NULL_CANVAS + """
let seed = 7;
Math.random = () => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648; };
const out = {};
for (const mood of ['working', 'agents', 'needs', 'idle', 'done', 'failed', 'limit']) {
    seed = 7;
    const t = new Talpy({}); let now = 1e12; t.tick(now); t.setMood(mood);
    const p = new Pictures(t, 5);
    let paints = 0;
    for (let i = 0; i < 4500; i++) {
        now += 40; t.tick(now); p.tick(now);
        for (const s of p.sheets) if (s.paint) { s.paint = false; p.paint(s, ctx); paints++; }
    }
    out[mood] = paints / 180;
}
console.log(JSON.stringify(out));""")
        limits = {"working": 2, "agents": 2.5, "needs": 4, "idle": 4, "done": 1.6, "failed": 3, "limit": 1.6}
        for mood, most in limits.items():
            self.assertLess(result[mood], most, mood)

    # ------------------------------------------------------------ films (films.mjs)

    def test_a_film_plays_a_quick_move_as_it_is_and_draws_each_picture_once(self):
        # Four pictures a move looked like a flip book; a film has a picture
        # every frame of the move's round (at most maxFrames), each drawn once
        result = run_node(NULL_CANVAS + """
const t = new Talpy({ brain: false }); let now = 1e12; t.tick(now);
t.pose({ arms: 'wave', depth: 'high', eyes: 'happy' });
const f = new Films(t, { frameMs: 33.3, maxFrames: 24, sheets: 26 });
const paints = [], shown = new Set();
for (let i = 0; i < 120; i++) {
    now += 33.3; t.tick(now); f.tick(now);
    for (const s of f.sheets) if (s.paint) { f.paint(s, ctx); paints.push(i); }
    shown.add(f.front.key);
}
console.log(JSON.stringify({ shown: shown.size, late: paints.filter(i => i > 30).length, all: paints.length }));""")
        self.assertGreaterEqual(result["shown"], 10)    # a wave's round (760 ms): 23 frames, mirrored
        self.assertLessEqual(result["all"], result["shown"])
        self.assertEqual(result["late"], 0)              # after the first round: none drawn

    def test_a_new_pose_moves_there_through_pictures_in_between(self):
        # A chat's pet faded from pose to pose; now its arms, depth and lamp
        # move there in pictures in between, and only when something moves
        result = run_node(NULL_CANVAS + """
const t = new Talpy({ brain: false }); let now = 1e12; t.tick(now);
t.pose({ depth: 'half', eyes: 'open' });
const f = new Films(t, { frameMs: 33.3, tweenMs: 200, tweens: 4, sheets: 20 });
const between = [], arms = [];
const run = (ms) => { for (let i = 0; i < ms / 33.3; i++) { now += 33.3; t.tick(now); f.tick(now);
    for (const s of f.sheets) if (s.paint) { if (s.from) { between.push(s.p); arms.push(t.posed(s.from).v.armR); } f.paint(s, ctx); } } };
run(300);
t.play({ steps: () => [{ depth: 'half', arms: 'up', eyes: 'happy', t: 600 }] }, null, false);
run(500);
const tweensBefore = between.length;
t.play({ steps: () => [{ depth: 'half', arms: 'up', eyes: 'wide', mouth: 'o', t: 600 }] }, null, false);
run(500);
console.log(JSON.stringify({ between: between.slice(0, tweensBefore), eyesOnly: between.length - tweensBefore }));""")
        self.assertEqual(len(result["between"]), 4)
        self.assertEqual(result["between"], sorted(result["between"]))   # on its way, in order
        self.assertTrue(all(0 < p < 1 for p in result["between"]))
        self.assertEqual(result["eyesOnly"], 0)                           # only the eyes changed: it just shows

    def test_the_big_talpy_is_drawn_live_until_a_new_pose_has_settled(self):
        result = run_node(NULL_CANVAS + """
const t = new Talpy({ brain: false }); let now = 1e12; t.tick(now);
t.pose({ depth: 'half' });
const f = new Films(t, { frameMs: 16.7, tweenMs: 0, maxFrames: 24, sheets: 26 });
for (let i = 0; i < 30; i++) { now += 16.7; t.tick(now); f.tick(now); for (const s of f.sheets) if (s.paint) f.paint(s, ctx); }
t.play({ steps: () => [{ depth: 'high', arms: 'up', t: 900 }] }, null, false);
const live = [];
for (let i = 0; i < 50; i++) { now += 16.7; t.tick(now); f.tick(now); live.push(f.front.key === '' ? 1 : 0);
    for (const s of f.sheets) if (s.paint) f.paint(s, ctx); }
console.log(JSON.stringify({ first: live.slice(0, 12), last: live.slice(-10) }));""")
        self.assertEqual(result["first"], [1] * 12)   # 200 ms: still on its way, every frame drawn
        self.assertEqual(result["last"], [0] * 10)    # settled: its picture

    def test_a_move_that_happens_once_plays_out(self):
        # A yawn's stretch, a throw, a twirl of the lamp have no pictures: a
        # film showed them done at once (cut short); they're drawn live
        result = run_node(NULL_CANVAS + """
const t = new Talpy({ brain: false }); let now = 1e12; t.tick(now);
const out = {};
for (const step of [{ body: 'stretch' }, { arms: 'throw' }, { plume: 'twirl', it: 2 }]) {
    t.play({ steps: () => [Object.assign({ t: 3000 }, step)] }, null, false);
    const live = [];
    for (let i = 0; i < 60; i++) { now += 40; t.tick(now); live.push(t.still(33, 12) === null ? 1 : 0); }
    out[Object.values(step)[0]] = (live.indexOf(0) + 1) * 40;
}
console.log(JSON.stringify(out));""")
        self.assertGreaterEqual(result["stretch"], 1300)
        self.assertGreaterEqual(result["throw"], 550)
        self.assertGreaterEqual(result["twirl"], 1600)

    def test_what_flies_about_is_drawn_on_its_own_and_slowly_for_zs(self):
        result = run_node(NULL_CANVAS + """
const t = new Talpy({ brain: false }); let now = 1e12; t.tick(now);
const f = new Films(t, { frameMs: 33.3, sheets: 20 });
t.react('pet');
let quick = 0, sheets = 0;
for (let i = 0; i < 30; i++) { now += 33.3; t.tick(now); f.tick(now); if (f.fx.paint) { quick++; f.paintFx(ctx); }
    for (const s of f.sheets) if (s.paint) { sheets++; f.paint(s, ctx); } }
for (let i = 0; i < 100; i++) { now += 33.3; t.tick(now); f.tick(now); if (f.fx.paint) f.paintFx(ctx); }
const off = !f.fx.on;
t.play({ steps: () => [{ eyes: 'closed', fx: [['z', 44, 34, { dx: 6, dy: -14, dur: 2.2 }]], t: 3000 }] }, null, false);
let zs = 0;
for (let i = 0; i < 60; i++) { now += 33.3; t.tick(now); f.tick(now); if (f.fx.paint) { zs++; f.paintFx(ctx); } }
console.log(JSON.stringify({ quick: quick, off: off, zs: zs }));""")
        self.assertGreater(result["quick"], 20)    # hearts: every frame
        self.assertTrue(result["off"])              # gone: its canvas hides
        self.assertLessEqual(result["zs"], 11)      # z's float up: 5 a second

    def test_the_open_hole_can_come_from_the_hosts_sheet(self):
        # Half of a picture's drawing was its hole; a host draws the open hole
        # once (drawHoleSide) and Talpy copies it in
        result = run_node("""
import { drawHoleSide } from %s;
let calls = 0; const images = [];
const ctx = new Proxy({}, { get: (t, k) => k === 'drawImage' ? (img) => { images.push(img); calls++; }
    : k === 'createLinearGradient' || k === 'createRadialGradient' ? () => ({ addColorStop() {} })
    : k in t ? t[k] : () => { calls++; }, set: (t, k, v) => { t[k] = v; return true; } });
const t = new Talpy({ brain: false }); t.tick(1e12); t.pose({ depth: 'half' });
t.draw(ctx); const drawn = calls; calls = 0;
t.holeImage = (part, left) => part + (left ? '-left' : '-right');
t.draw(ctx); const copied = calls; calls = 0;
drawHoleSide(ctx, 'front', true); const side = calls;
t.facingLeft = true; images.length = 0; t.draw(ctx);
console.log(JSON.stringify({ drawn: drawn, copied: copied, side: side, images: images }));""" % json.dumps(str(TALPY / "talpy.mjs")))
        self.assertLess(result["copied"], result["drawn"] * 0.6)
        self.assertGreater(result["side"], 50)
        self.assertEqual(result["images"], ["back-left", "front-left"])

    def test_films_cost_the_desktop_about_what_pictures_did(self):
        # Four desktop dashboards (2026-10-23): what the pets draw a second
        # (canvas calls) mustn't grow; the big Talpy draws much less than
        # live, and a chat's pet at most a little more than with pictures.
        # (Slow moves are drawn live since 2026-10-27, so they don't step: a
        # mood full of them, out of steam at a limit, costs a bit more.)
        result = run_node(CALL_COUNTER + """
let seed = 7;
Math.random = () => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648; };
const out = {};
for (const lone of [true, false]) for (const mood of ['working', 'agents', 'needs', 'idle', 'done', 'failed', 'limit']) {
    const cost = films => {
        seed = 7; calls = 0;
        const t = new Talpy({ travels: lone }); t.onTravel = lone ? () => {} : null; let now = 1e12; t.tick(now); t.setMood(mood);
        const tick = films ? 33.33 : 40;
        let f = null, p = null;
        if (films) { t.holeImage = () => ({});
            f = lone ? new Films(t, { frameMs: tick, maxFrames: 32, sheets: 36, tweenMs: 0, restMs: 200, smooth: true, clockMs: tick })
                     : new Films(t, { frameMs: 2 * tick, maxFrames: 32, sheets: 32, tweenMs: 200, tweens: 3, smooth: true, clockMs: tick }); }
        else { p = new Pictures(t, lone ? 1 : 5); p.pictures = !lone; }
        for (let i = 0; i < 120000 / tick; i++) {
            now += tick; t.tick(now);
            if (f) { f.tick(now); for (const s of f.sheets) if (s.paint) f.paint(s, ctx); if (f.fx.paint) f.paintFx(ctx); }
            else { p.tick(now); for (const s of p.sheets) if (s.paint) { s.paint = false; p.paint(s, ctx); } if (p.coming) calls += 4; }
        }
        return calls;
    };
    out[(lone ? 'hero ' : 'chat ') + mood] = cost(true) / cost(false);
}
console.log(JSON.stringify(out));""")
        for name, ratio in result.items():
            self.assertLess(ratio, 0.85 if name.startswith("hero") else 1.9, name)
        hero = [ratio for name, ratio in result.items() if name.startswith("hero")]
        self.assertLess(sum(hero) / len(hero), 0.6)

    def test_a_slow_move_doesnt_step(self):
        # A nod or a float has more pictures a round than a film keeps: they
        # showed for 3 ticks each (6 a second in the popup, it looked like
        # lag). Smooth films draw such a move live, a new picture every tick;
        # a quicker one keeps a picture per tick, the same number of ticks each
        result = run_node(NULL_CANVAS + """
const out = {};
for (const smooth of [true, false]) for (const body of ['nod', 'float', 'sway']) {
    const t = new Talpy({ brain: false }); let now = 1e12; t.tick(now);
    t.play({ steps: () => [{ depth: 'half', body: body, t: 8000 }] });
    const f = new Films(t, { frameMs: 33.3, maxFrames: 32, sheets: 32, tweenMs: 200, smooth: smooth });
    let sig = '', at = 0, holds = {};
    for (let i = 0; i < 150; i++) {
        now += 100 / 3; t.tick(now); f.tick(now);
        for (const s of f.sheets) if (s.paint) f.paint(s, ctx);
        const was = sig; sig = f.front.index + '|' + f.front.key + '|' + f.liveAt;
        if (i > 30 && sig !== was) { holds[i - at] = (holds[i - at] || 0) + 1; }
        if (sig !== was) at = i;
    }
    out[body + (smooth ? ' smooth' : '')] = Object.keys(holds).map(Number);
}
console.log(JSON.stringify(out));""")
        for name, holds in result.items():
            if name.endswith("smooth") or name.startswith("sway"):
                self.assertEqual(holds, [1], name)
            else:
                self.assertGreater(max(holds), 2, name)   # (what it was: the test can tell)

    def test_a_jittery_clock_shows_each_picture_as_long(self):
        # The clock's ticks come a millisecond or two early or late: a
        # picture of a move still shows for its whole number of frames (by
        # time alone, one due right at a tick showed for 1 frame, then 3)
        result = run_node(NULL_CANVAS + """
let seed = 3;
const jitter = () => { seed = (seed * 1103515245 + 12345) % 2147483648; return (seed / 2147483648 - 0.5) * 4; };
const out = {};
for (const [name, move, frameMs] of [['typing', { arms: 'type' }, 33.3], ['bounce', { body: 'bounce' }, 33.3], ['wave', { arms: 'wave' }, 16.7]]) {
    const t = new Talpy({ brain: false }); const start = 1e12; t.tick(start);
    t.play({ steps: () => [Object.assign({ depth: 'half', eyes: 'happy', t: 9000 }, move)] });   // (no blinks: pictures of their own)
    const f = new Films(t, { frameMs: frameMs, maxFrames: 32, sheets: 32, tweenMs: 200, clockMs: 1000 / 60 });
    let sig = '', at = 0; const holds = {};
    for (let i = 1; i < 400; i++) {
        const now = start + i * 1000 / 60 + jitter(); t.tick(now); f.tick(now);
        for (const s of f.sheets) if (s.paint) f.paint(s, ctx);
        const was = sig; sig = f.front.index + '|' + f.front.key + '|' + f.liveAt;
        if (i > 60 && sig !== was) holds[i - at] = (holds[i - at] || 0) + 1;
        if (sig !== was) at = i;
    }
    out[name] = Object.keys(holds).map(Number);
}
console.log(JSON.stringify(out));""")
        self.assertEqual(result, {"typing": [2], "bounce": [2], "wave": [2]})

    def test_nothing_shows_under_the_burrows_lip(self):
        # Talpy and what it holds are cut along the same edge the lip is drawn
        # up to, so nothing peeks out between the lip's lumps
        art = (TALPY / "art.mjs").read_text()
        edge = re.search(r"export const EDGE = '([^']*)'", art).group(1)
        front = re.search(r"V55\.6(A[^V]*)V", edge).group(1)   # the opening's front edge
        self.assertIn("L53.5 55.6" + front + "Z', DIRT", art)

    def test_notification_icons_use_colors_qt_can_read(self):
        # Qt's SVG renderer paints rgba() black: the notifications showed a
        # black Talpy
        for p in PETS.glob("*.svg"):
            self.assertNotIn("rgba(", p.read_text(), p.name)

    def test_notification_icons_exist(self):
        main = (ROOT / "ui/main.qml").read_text()
        block = main[main.index("const pose = kind"):]
        block = block[:block.index("\n\n")]
        for pose in set(re.findall(r'"([a-z0-9-]+)"', block)) - {"done", "failed", "waiting", "notify-"}:
            self.assertTrue((PETS / f"notify-{pose}.svg").is_file(), pose)

    def test_icons_have_no_external_content(self):
        for p in PETS.glob("*.svg"):
            self.assertNotRegex(p.read_text(), r"(?i)<script|<image|<foreignObject|href=\"(?!#)|url\((?!#)|@import", p.name)

    def test_no_clawd_left(self):
        # Talpy replaced Clawd (Anthropic's mascot) everywhere
        repo = ROOT.parent.parent
        for path in list((repo / "package").rglob("*")) + list((repo / "gnome/extension").rglob("*")) + [repo / "README.md"] + list((repo / "docs").glob("*.md")):
            if path.is_file() and path.suffix in {".qml", ".js", ".mjs", ".py", ".xml", ".md", ".svg", ".json", ".css"}:
                self.assertNotRegex(path.read_text(errors="ignore"), r"(?i)clawd", str(path.relative_to(repo)))


class TugTests(unittest.TestCase):
    """Pulled at in its burrow, Talpy hangs on to the rim for a moment."""

    def test_pulled_at_in_its_burrow_it_hangs_on_then_comes_out(self):
        r = run_node(NULL_CANVAS + """
const t = new Talpy({ brain: false });
let now = 1000;
t.tick(now);
const run = (ms, until) => { for (const end = now + ms; now < end;) { now += 16; t.tick(now); t.draw(ctx); if (until && until()) break; } };
run(600);
let out = null;
const began = t.tug(ok => { out = [ok, now]; });
const at = now;
run(300);
const hanging = { tugging: t.tugging, busy: t.busy, depth: t.st.depth, arms: t.st.arms, body: t.st.body };
let reacted = null;
t.react('wave', ok => { reacted = ok; });
run(2000, () => out !== null);
const open = t.setHeld(true);
console.log(JSON.stringify({ began, hanging, reacted, ok: out[0], ms: out[1] - at, tugging: t.tugging, held: t.held, open }));""")
        self.assertTrue(r["began"])
        self.assertEqual(r["hanging"], {"tugging": True, "busy": True, "depth": "high", "arms": "rim", "body": "tug"})
        self.assertFalse(r["reacted"])   # (nothing else moves it meanwhile)
        self.assertTrue(r["ok"])
        self.assertGreaterEqual(r["ms"], 1000)
        self.assertLess(r["ms"], 1100)
        self.assertEqual((r["tugging"], r["held"]), (False, True))
        self.assertGreater(r["open"], 0.9)   # (its burrow stays where it was)

    def test_hanging_on_it_leans_towards_your_hand(self):
        # Pulled up and to the right it leans right (more as it stretches),
        # to the left left; straight up not at all; once out, no lean
        r = run_node(NULL_CANVAS + """
const t = new Talpy({ brain: false });
let now = 1000;
t.tick(now);
const run = ms => { for (const end = now + ms; now < end;) { now += 16; t.tick(now); t.draw(ctx); } };
run(600);
const lean = [];
t.tug(() => {});
t.tugToward(40, -20);
run(500);
lean.push(t.tugLean);
t.tugToward(-40, -20);
run(400);
lean.push(t.tugLean);
t.tugToward(0, -30);
run(90);
t.setHeld(true);
run(800);
lean.push(t.tugLean);
console.log(JSON.stringify(lean.map(v => Math.round(v))));""")
        self.assertGreater(r[0], 25)
        self.assertLess(r[1], -25)
        self.assertEqual(r[2], 0)

    def test_let_go_of_early_it_drops_back_in(self):
        r = run_node(NULL_CANVAS + """
const t = new Talpy({ brain: false });
let now = 1000;
t.tick(now);
const run = ms => { for (const end = now + ms; now < end;) { now += 16; t.tick(now); t.draw(ctx); } };
run(600);
let tug = null, back = null;
t.tug(ok => { tug = ok; });
run(400);
t.letGo(ok => { back = ok; });
run(1200);
console.log(JSON.stringify({ tug, back, tugging: t.tugging, held: t.held, depth: t.st.depth, hole: t.v.hole }));""")
        self.assertEqual(r, {"tug": False, "back": True, "tugging": False, "held": False, "depth": "half", "hole": 1})

    def test_out_of_its_burrow_it_is_taken_at_once(self):
        # Held, out on the floor after a cookie, jumping clear of it, or
        # tunnelling: no rim to hang on to
        r = run_node(NULL_CANVAS + """
const t = new Talpy({ brain: false });
let now = 1000;
t.tick(now);
const run = ms => { for (const end = now + ms; now < end;) { now += 16; t.tick(now); } };
run(600);
const out = [];
t.setHeld(true);
out.push(t.tug());
t.land(0, () => { t.chase(); out.push(t.chased, t.tug()); }, true);
run(1500);
t.eat('choc', false);
run(12000);
t.react('flip');
run(500);
out.push(t.st.depth, t.tug());
run(3000);
t.react('dig');
run(1200);
out.push(t.st.tunnel, t.tug());
console.log(JSON.stringify(out));""")
        self.assertEqual(r, [False, "stand", False, "out", False, "1", False])

    def test_pushed_down_it_hangs_on_then_gives_in_and_peeks_out(self):
        # A drag that starts downward while it's in its burrow pushes it in:
        # squashed, it grabs the rim and pushes back, sinking less the
        # further you push and shoving up now and then; held down a second,
        # as long as a tug takes, it gives in (once, and says so) and ducks
        # all the way; let go, it stays down a moment, peeks out and is back
        r = run_node(NULL_CANVAS + """
const t = new Talpy({ brain: false });
let now = 1000;
t.tick(now);
const run = (ms, until) => { for (const end = now + ms; now < end;) { now += 16; t.tick(now); t.draw(ctx); if (until && until()) break; } };
run(600);
const from = t.v.depth;
let gives = 0;
const began = t.push(false, () => { gives += 1; });
const look = { body: t.st.body, eyes: t.st.eyes, arms: t.st.arms, fx: t.fx.filter(p => p.kind === 'clod').length > 0 };
t.pushTo(20);
const at = now;
run(400);
const first = t.v.depth - from;
const notYet = t.pushTo(39);
run(350);
const second = t.v.depth - from - first;
let top = 99, bottom = 0, squashed = 0, gaveAt = 0;
run(1000, () => {
    if (t.gaveIn) { gaveAt = now - at; return true; }
    top = Math.min(top, t.v.depth); bottom = Math.max(bottom, t.v.depth); squashed = Math.max(squashed, t.squash);
});
const again = t.pushTo(80);
run(800);
const deep = { depth: t.v.depth >= 40, run: !!t.run, pushing: t.pushing, gaveIn: t.gaveIn };
let back = null;
const left = now;
const how = t.pushed(false, ok => { back = [ok, now - left]; });
run(700);
const down = t.v.depth;
run(5000, () => back !== null);
console.log(JSON.stringify({ began, look, first, second, shoves: bottom - top, squashed, notYet, gaveAt, gives, again, deep, how, down,
                             back, depth: t.st.depth, pushing: t.pushing }));""")
        self.assertTrue(r["began"])
        self.assertEqual(r["look"], {"body": "push", "eyes": "squint", "arms": "rim", "fx": True})   # (a dirt puff)
        self.assertGreater(r["first"], 2)                         # it sinks as you push,
        self.assertLess(r["first"], 12)                           # much less than your hand went (20)
        self.assertLess(r["second"], r["first"])                  # and less the further you push
        self.assertGreater(r["shoves"], 1)                        # it shoves up against your hand now and then
        self.assertGreater(r["squashed"], 0.6)
        self.assertFalse(r["notYet"])
        self.assertGreaterEqual(r["gaveAt"], 1000)                # held down as long as a tug takes, it gives in
        self.assertLess(r["gaveAt"], 1050)
        self.assertEqual((r["gives"], r["again"]), (1, False))   # once
        self.assertEqual(r["deep"], {"depth": True, "run": False, "pushing": True, "gaveIn": True})   # all the way, nothing else meanwhile
        self.assertEqual(r["how"], "down")
        self.assertGreaterEqual(r["down"], 40)                    # let go: it stays down a moment
        self.assertTrue(r["back"][0])
        self.assertGreater(r["back"][1], 2500)                    # (down, peeks left and right, out)
        self.assertEqual((r["depth"], r["pushing"]), ("half", False))

    def test_pushed_on_far_it_gives_in_at_once(self):
        # 40 box units down: no waiting for the second
        r = run_node(NULL_CANVAS + """
const t = new Talpy({ brain: false });
let now = 1000;
t.tick(now);
const run = ms => { for (const end = now + ms; now < end;) { now += 16; t.tick(now); t.draw(ctx); } };
run(600);
let gives = 0;
t.push(false, () => { gives += 1; });
const out = [t.pushTo(20), t.gaveIn];
run(100);
out.push(t.pushTo(39), t.pushTo(40), t.gaveIn, gives, t.pushTo(80), gives);
run(1500);
out.push(gives);
console.log(JSON.stringify(out));""")
        self.assertEqual(r, [False, False, False, True, True, 1, False, 1, 1])

    def test_held_down_the_second_starts_again_when_your_hand_comes_back_up(self):
        # the second counts from when your hand first went PUSH_HOLD (6) down;
        # back above that it starts again; a little push alone never gives in
        r = run_node(NULL_CANVAS + """
const t = new Talpy({ brain: false });
let now = 1000;
t.tick(now);
const run = ms => { for (const end = now + ms; now < end;) { now += 16; t.tick(now); t.draw(ctx); } };
run(600);
let gives = 0;
t.push(false, () => { gives += 1; });
t.pushTo(4);
run(1500);
const little = t.gaveIn;
t.pushTo(20);
run(700);
t.pushTo(3);    // back up above it
run(300);
t.pushTo(20);   // down again: the second starts again
run(800);
const notYet = t.gaveIn;
t.pushTo(25);   // (further down within it: still the same second)
run(300);
console.log(JSON.stringify({ little, notYet, gaveIn: t.gaveIn, gives }));""")
        self.assertEqual(r, {"little": False, "notYet": False, "gaveIn": True, "gives": 1})

    def test_let_go_before_it_gives_in_it_springs_back_up(self):
        # boing: up past where it was, then it settles where it was, unsquashed
        r = run_node(NULL_CANVAS + """
const t = new Talpy({ brain: false });
let now = 1000;
t.tick(now);
const run = (ms, until) => { for (const end = now + ms; now < end;) { now += 16; t.tick(now); t.draw(ctx); if (until && until()) break; } };
run(600);
const from = t.v.depth;
t.push();
t.pushTo(30);
run(600);
const pushed = t.v.depth;
let back = null, top = 99;
const at = now;
const how = t.pushed(false, ok => { back = [ok, now - at]; });
run(3000, () => { top = Math.min(top, t.v.depth); return back !== null; });
run(600);
console.log(JSON.stringify({ from, pushed, how, top, back, depth: t.v.depth, squash: t.squash, st: t.st.depth }));""")
        self.assertGreater(r["pushed"], r["from"] + 2)
        self.assertEqual(r["how"], "boing")
        self.assertLess(r["top"], r["from"] - 3)                  # up past where it was
        self.assertTrue(r["back"][0])
        self.assertLess(r["back"][1], 1500)
        self.assertAlmostEqual(r["depth"], r["from"], delta=0.05)  # and settled there
        self.assertEqual(r["squash"], 0)

    def test_pushed_then_pulled_it_comes_up_from_there_into_the_tug(self):
        # Your hand goes back up (or off to a side): the host pulls instead,
        # and it rises from where it was pushed to, its squash easing off: no
        # jump from one to the other
        r = run_node(NULL_CANVAS + """
const t = new Talpy({ brain: false });
let now = 1000;
t.tick(now);
const run = (ms, each) => { for (const end = now + ms; now < end;) { now += 16; t.tick(now); t.draw(ctx); if (each) each(); } };
run(600);
t.push();
t.pushTo(30);
run(800);
const pushed = t.v.depth, squash = t.squash;
let out = null;
const tugs = t.tug(ok => { out = ok; });
const state = { pushing: t.pushing, tugging: t.tugging, body: t.st.body };
let last = t.v.depth, jump = 0;
run(16);
const firstSquash = t.squash;
run(1200, () => { jump = Math.max(jump, Math.abs(t.v.depth - last)); last = t.v.depth; });
console.log(JSON.stringify({ pushed, squash, tugs, state, firstSquash, jump, out, after: t.squash }));""")
        self.assertTrue(r["tugs"])
        self.assertEqual(r["state"], {"pushing": False, "tugging": True, "body": "tug"})
        self.assertGreater(r["firstSquash"], r["squash"] * 0.5)   # (eased off, not gone at once)
        self.assertLess(r["jump"], 4)                             # (as it pops up any time: a few units a frame)
        self.assertTrue(r["out"])                                 # it hangs on, then comes out
        self.assertEqual(r["after"], 0)

    def test_pulled_then_pushed_back_down_it_sinks_from_there_into_the_push(self):
        # Your hand back down past where you began before it came out: the
        # host pushes instead; the tug ends (done(false): the host doesn't
        # take it), and it sinks from where it is, drawn out easing into
        # squashed: no jump in its depth or its body's size; then it still
        # gives in, by time or by distance
        r = run_node(NULL_CANVAS + """
const t = new Talpy({ brain: false });
let now = 1000;
t.tick(now);
const run = (ms, each) => { for (const end = now + ms; now < end;) { now += 16; t.tick(now); t.draw(ctx); if (each) each(); } };
run(600);
let tug = null;
t.tug(ok => { tug = ok; });
t.tugToward(20, -30);
run(500);
const before = { depth: t.v.depth, stretch: t.stretch, lean: t.tugLean };
// (how the body's drawn: wide and tall, from draw's stretch and squash)
const sy = () => (1 + 0.2 * t.stretch) * (1 - 0.12 * t.squash), sx = () => (1 - 0.1 * t.stretch) * (1 + 0.13 * t.squash);
let lastD = t.v.depth, lastX = sx(), lastY = sy(), lastL = t.tugLean, jump = 0, scale = 0, lean = 0;
const track = () => {
    if (t.gaveIn)
        return;   // (then it ducks all the way, quickly)
    jump = Math.max(jump, Math.abs(t.v.depth - lastD)); scale = Math.max(scale, Math.abs(sx() - lastX), Math.abs(sy() - lastY));
    lean = Math.max(lean, Math.abs(t.tugLean - lastL));
    lastD = t.v.depth; lastX = sx(); lastY = sy(); lastL = t.tugLean;
};
let gives = 0;
const pushes = t.push(false, () => { gives += 1; });
const state = { tug, tugging: t.tugging, pushing: t.pushing, body: t.st.body, from: Math.abs(t.pushFrom - before.depth) < 0.01 };
t.pushTo(4);
run(16, track);
const firstStretch = t.stretch;
t.pushTo(12);
run(500, track);
const mid = { stretch: t.stretch, squash: t.squash > 0.3, lean: Math.abs(t.tugLean) < 1, sank: t.v.depth > before.depth + 2 };
run(700, track);
const held = { gaveIn: t.gaveIn, gives };
let out = null;
const tugAgain = t.tug(ok => { out = ok; });
run(300);
const back = t.push(false, () => { gives += 1; });
const far = t.pushTo(45);
run(16);
console.log(JSON.stringify({ before, pushes, state, firstStretch, mid, jump, scale, lean, held, tugAgain, out, back, far, gives,
                             tugging: t.tugging, deep: t.gaveIn }));""")
        self.assertGreater(r["before"]["stretch"], 0.5)             # (drawn out as it hangs on)
        self.assertGreater(r["before"]["lean"], 10)
        self.assertTrue(r["pushes"])
        self.assertEqual(r["state"], {"tug": False, "tugging": False, "pushing": True, "body": "push", "from": True})
        self.assertGreater(r["firstStretch"], r["before"]["stretch"] * 0.5)   # (eased off, not gone at once)
        self.assertEqual(r["mid"], {"stretch": 0, "squash": True, "lean": True, "sank": True})
        self.assertLess(r["jump"], 2)                               # its depth goes on from where it was,
        self.assertLess(r["scale"], 0.03)                           # its body from drawn out to squashed,
        self.assertLess(r["lean"], 6)                               # its lean easing back
        self.assertEqual(r["held"], {"gaveIn": True, "gives": 1})   # held down a second: it gives in
        self.assertTrue(r["tugAgain"])                              # (and pulled at again, down again,
        self.assertEqual((r["out"], r["back"], r["far"], r["gives"]), (False, True, True, 2))   # it gives in pushed on far)
        self.assertEqual((r["tugging"], r["deep"]), (False, True))

    def test_with_less_motion_its_down_at_once(self):
        r = run_node(NULL_CANVAS + """
const t = new Talpy({ brain: false });
let now = 1000;
t.tick(now);
for (let i = 0; i < 40; i++) { now += 16; t.tick(now); }
const began = t.push(true);
now += 16; t.tick(now);
console.log(JSON.stringify({ began, depth: t.v.depth, gaveIn: t.gaveIn, more: t.pushTo(100), squash: t.squash,
                             how: t.pushed(false) }));""")
        self.assertEqual(r, {"began": True, "depth": 42, "gaveIn": True, "more": False, "squash": 0, "how": "down"})

    def test_pushed_down_while_a_chat_needs_you_it_pops_straight_up(self):
        r = run_node(NULL_CANVAS + """
const t = new Talpy({ brain: false });
let now = 1000;
t.tick(now);
const run = (ms, until) => { for (const end = now + ms; now < end;) { now += 16; t.tick(now); t.draw(ctx); if (until && until()) break; } };
t.setMood('needs');
run(600);
t.push();
t.pushTo(100);
run(200);
let back = null;
const at = now;
const how = t.pushed(true, ok => { back = [ok, now - at]; });
run(2000, () => back !== null);
console.log(JSON.stringify({ how, back, depth: t.st.depth }));""")
        self.assertEqual(r["how"], "up")
        self.assertTrue(r["back"][0])
        self.assertLess(r["back"][1], 800)
        self.assertEqual(r["depth"], "high")

    def test_out_of_its_burrow_it_cant_be_pushed(self):
        r = run_node(NULL_CANVAS + """
const t = new Talpy({ brain: false });
let now = 1000;
t.tick(now);
const run = ms => { for (const end = now + ms; now < end;) { now += 16; t.tick(now); } };
run(600);
const out = [];
t.setHeld(true);
out.push(t.push());
t.land(0, () => { t.chase(); out.push(t.chased, t.push()); }, true);
run(1500);
t.eat('choc', false);
run(12000);
t.react('dig');
run(1200);
out.push(t.st.tunnel, t.push());
console.log(JSON.stringify(out));""")
        self.assertEqual(r, [False, "stand", False, "1", False])

    def test_both_hosts_push_on_a_downward_drag_and_pull_on_any_other(self):
        pet = (ROOT / "ui/Pet.qml").read_text()
        ts = (ROOT.parent.parent / "vscode/webview/pets/pet.ts").read_text()
        # within 45° of straight down, while it's in its burrow (push() says)
        self.assertIn("p.y - pressedAt.y > 0 && Math.abs(p.x - pressedAt.x) <= p.y - pressedAt.y && pet.push()", pet)
        self.assertIn("dy > 0 && Math.abs(dx) <= dy && this.push()", ts)
        # (less motion: down at once; it gives in, held down a second or pushed on far, and says so)
        self.assertIn('talpy.push(root.lessMotion, () => pet.say(i18n("Okay, okay!")))', pet)
        self.assertIn('talpy.push(reducedMotion(), () => { if (!this.destroyed) this.say("Okay, okay!"); })', ts)
        for text in (pet, ts):
            self.assertRegex(text, r"talpy\.pushTo\(")
            self.assertRegex(text, r'talpy\.pushed\((this\.)?mood === "needs"')
            self.assertRegex(text, r'react\("sign"\)')             # (a chat needs you: its sign)
            # then back up past where it began, or off to a side: pulled out after all
            block = text[text.index("pushToward(p"):]
            block = block[:block.index("pushInstead(p")]
            self.assertIn("!(dy > 0 && Math.abs(dx) <= dy)", block)
            self.assertRegex(block, r"pushing = false;?\s*\n\s*(this\.|pet\.)?pull\(\)")
            self.assertRegex(block, r"talpy\.pushTo\(dy / ")
            # pulled, then back down past where it began before it came out: pushed in after all,
            # the tug over first (its callback then takes nothing), as one move
            block = text[text.index("pushInstead(p"):]
            block = block[:block.index("tugToward(p")]
            self.assertRegex(block, r"dy > (this\.stage\.)?gu \* 0\.5 && Math\.abs\(dx\) <= dy")
            self.assertRegex(block, r"tugging = false;?\s*\n\s*if \(!(this\.)?push\(\)\)")
            self.assertRegex(block, r"(this\.)?pushToward\(p\);?\s*\n\s*return true")
            # it says something: as you push, when it gives in, when it springs back
            self.assertIn("No pushing!", text)
            self.assertIn('how === "boing"', text)
            self.assertIn("Hmpf!", text)
        self.assertIn("live: pet.landing || pet.chasing || pet.tugging || pet.pushing", pet)
        self.assertIn("!this.pushing", ts[ts.index("f.on ="):])
        # (as the hand moves while it hangs on)
        self.assertIn("if (!pet.pushInstead(p))   // (back down past where you began: pushed in after all)\n"
                      "                    pet.tugToward(p)", pet)
        self.assertIn("if (!this.pushInstead(p)) this.tugToward(p);", ts)
        for text in (pet, ts):
            self.assertRegex(text, r"talpy\.tug\(\(?ok\)? => \{ if \(ok && (pet|this)\.tugging\)")   # (a tug cut short takes nothing)

    def test_both_hosts_pull_and_let_go_through_it(self):
        # A drag that starts pulls (tug: false, it's taken at once); let go of
        # while it hangs on, it drops back in (letGo); drawn live meanwhile
        pet = (ROOT / "ui/Pet.qml").read_text()
        ts = (ROOT.parent.parent / "vscode/webview/pets/pet.ts").read_text()
        self.assertIn("pet.pull()", pet)
        self.assertIn("this.pull();", ts)
        self.assertIn("pet.tugToward(p)", pet)   # (it leans towards your hand as you move it)
        self.assertIn("this.tugToward(p);", ts)
        for text in (pet, ts):
            self.assertRegex(text, r"talpy\.tug\(")
            self.assertRegex(text, r"talpy\.letGo\(")
            self.assertRegex(text, r"tugging\)\s*(\{\s*)?\n?\s*(pet\.|this\.)?letGo\(\)")
        self.assertIn("live: pet.landing || pet.chasing || pet.tugging", pet)
        self.assertIn("!this.tugging", ts[ts.index("f.on ="):])


# Talpy on a stage with a cookie game (talpy/cookie.mjs), as a host has it:
# run(ms, until) ticks both (and draws Talpy) every 16 ms; states: what the
# game and Talpy did, in turn ("chase:run": chasing, running)
COOKIE_STAGE = NULL_CANVAS + """
import { CookieGame } from %s;
import { COOKIE, FLAVOURS, THANKS_NAMES } from %s;
import { drawCookie } from %s;
const gu = 16, box = gu * 5.6, unit = box / 64, bw = box * 38 / 64, bh = box * 31 / 64, W = 400, H = gu * 6;
const said = [], holes = [], states = [], flavours = [];
let px = W * 0.76, eaten = 0, now = 1000;   // (eaten: as it says yum)
const t = new Talpy({ travels: true });
t.onTravel = () => {};
const host = {
    stage: () => ({ width: W, ground: H - gu * 0.55, unit, bodyWidth: bw, bodyHeight: bh, minX: box * 27 / 64 + 4, maxX: W - box * 27 / 64 - 4 }),
    px: () => px, moveTo: x => { px = x; }, face: left => { t.facingLeft = left; },
    say: (what, flavour) => { said.push(what); flavours.push(flavour); if (what === 'yum') eaten += 1; },
    leaveHole: open => holes.push('leave ' + Math.round(open * 100) / 100), fillHole: () => holes.push(t.holeOpen ? 'fill' : 'fill early'),
    changed: () => {}, instant: () => false };
const game = new CookieGame(t, host);
const run = (ms, until) => {
    for (const end = now + ms; now < end;) {
        now += 16;
        t.tick(now);
        if (game.on)
            game.tick(now);
        t.draw(ctx);
        const s = game.state + (t.chasing ? ':' + t.chased : '');
        if (states[states.length - 1] !== s)
            states.push(s);
        if (until && until())
            break;
    }
};
t.tick(now);
run(500);
""" % (json.dumps(str(TALPY / "cookie.mjs")), json.dumps(str(TALPY / "actions.mjs")), json.dumps(str(TALPY / "talpy.mjs")))


class CookieTests(unittest.TestCase):
    """A cookie for the big Talpy: double-click its stage away from it."""

    def test_a_cookie_away_from_it_is_seen_chased_and_eaten(self):
        # It sees it first, jumps out of its burrow (which stays where it
        # was: the host draws it) and runs there; it eats it, digs a new
        # burrow right there, and the old one is filled once it does
        r = run_node(COOKIE_STAGE + """
const placed = game.place(40, 70);
const flavour = game.cookie.flavour;
run(20000, () => !game.on);
console.log(JSON.stringify({ placed, states, said, flavours, flavour, holes, eaten, on: game.on, chasing: t.chasing, px: Math.round(px),
                             depth: t.st.depth, hole: t.v.hole }));""")
        self.assertTrue(r["placed"])
        self.assertEqual(r["states"][:4], ["", "spot", "chase:out", "chase:stand"])
        self.assertIn("chase:run", r["states"])
        self.assertEqual(r["states"][-2:], ["eat", ""])
        self.assertEqual(r["said"], ["spot", "yum"])
        self.assertEqual(r["flavours"], [r["flavour"]] * 2)   # (its words are for that one)
        self.assertEqual(r["holes"], ["leave 1", "fill"])
        self.assertEqual(r["eaten"], 1)
        self.assertFalse(r["on"] or r["chasing"])
        self.assertLess(r["px"], 80)
        self.assertEqual((r["depth"], r["hole"]), ("half", 1))

    def test_pushed_down_as_it_spots_one_it_stays_yours_till_you_let_go(self):
        # (a push sets no run: the game took that for a look cut short and
        # sent it after the cookie under your hand; and nothing else reacts
        # meanwhile, a chat starting or a reminder)
        r = run_node(COOKIE_STAGE + """
game.place(40, 30);
run(100);
const spotting = game.state;
const pushed = t.push();
game.picked();
run(600);
const during = { chasing: t.chasing, busy: t.busy, run: t.run !== null };
t.react('mindblown');
t.setMood('working');
const after = { run: t.run !== null, pushing: t.pushing, eyes: t.st.eyes };
t.pushed(false, ok => { if (ok) game.landed(); });
run(5000, () => t.chasing);
console.log(JSON.stringify({ spotting, pushed, during, after, chasing: t.chasing }));""")
        self.assertEqual(r["spotting"], "spot")
        self.assertTrue(r["pushed"])
        self.assertEqual(r["during"], {"chasing": False, "busy": True, "run": False})
        self.assertEqual(r["after"], {"run": False, "pushing": True, "eyes": "squint"})   # (still pushed, as it looked)
        self.assertTrue(r["chasing"])                                                     # let go: after it

    def test_a_double_click_on_it_or_right_beside_it_pets_it_instead(self):
        r = run_node(COOKIE_STAGE + """
console.log(JSON.stringify([game.place(px + 10, H - 20), game.place(px - bw * 0.5, H - 30), game.on, said]));""")
        self.assertEqual(r, [False, False, False, []])

    def test_held_out_of_reach_it_jumps_for_it_and_takes_it_lowered(self):
        # Out of reach it begs and keeps jumping for it all the same; lowered
        # a little, it has it out of the air (or out of your hand)
        r = run_node(COOKIE_STAGE + """
game.place(40, 0);
game.grab(game.cookie.x, game.cookie.y);
run(9000);
const tries = states.filter(s => s === 'leap:reach').length;
game.drag(game.cookie.x, 45);
run(1500, () => game.state === 'eat');
const before = states[states.length - 2];
game.drop();
console.log(JSON.stringify({ tries, said, before, state: game.state, cookie: game.cookie }));""")
        self.assertGreaterEqual(r["tries"], 4)
        self.assertEqual(r["said"][:3], ["spot", "gimme", "aww"])
        self.assertIn("cross", r["said"])
        self.assertEqual(r["state"], "eat")
        self.assertTrue(r["before"].startswith("leap"), r["before"])
        self.assertIsNone(r["cookie"])

    def test_it_takes_one_standing_from_right_behind_it(self):
        # (the cookie is drawn over it: it shows whole as it gets there, and
        # turns into the one in its hands where it is)
        r = run_node(COOKIE_STAGE + """
game.place(60, H - 20);
let x = null;
run(20000, () => { if (game.cookie) x = game.cookie.x; return game.state === 'eat'; });
console.log(JSON.stringify({ off: Math.abs(x - px) / bw }));""")
        self.assertLess(r["off"], 0.12)

    def test_one_left_alone_falls_and_it_has_it(self):
        # Popped up high, out of its reach, and never touched: it falls to
        # the floor and Talpy has it; the game ends
        r = run_node(COOKIE_STAGE + """
game.place(40, 0);
run(20000, () => !game.on);
console.log(JSON.stringify({ on: game.on, eaten, said }));""")
        self.assertEqual((r["on"], r["eaten"]), (False, 1))
        self.assertNotIn("gimme", r["said"])

    def test_a_cookie_is_light_it_pops_hops_floats_down_and_bounces(self):
        # (Talpy stays put: just the cookie) It grows as it pops up (also
        # long after the last one: the game's clock stood still meanwhile),
        # hops up a little, floats down (the air holds it back), lands with
        # a squash and a rock, bounces less each time, and settles round
        r = run_node(COOKIE_STAGE + """
t.chase = () => 0;
t.seeCookie = () => {};
game.go = () => {};   // (a look cut short sends it after the cookie all the same: not here)
run(5000);
const floor = H - gu * 0.55 - 7 * unit, start = now;
game.place(40, 45);
const path = [];
let grew = [], landed = [], last = -1e9, minSy = 1;
run(3000, () => {
    const c = game.cookie;
    if (now - start <= 320) grew.push(c.scale);
    path.push([now - start, (floor - c.y) / unit]);
    if (c.landAt !== last) { landed.push(now - start); last = c.landAt; }
    minSy = Math.min(minSy, c.sy);
    return false;
});
const c = game.cookie;
console.log(JSON.stringify({ grew: [grew[0], Math.max(...grew), grew[grew.length - 1]], start: path[0][1],
                             top: Math.max(...path.map(p => p[1])), landed, minSy, end: [c.sx, c.sy, c.angle, c.vy].map(v => Math.round(v * 100) / 100),
                             bounced: path.some(p => p[0] > landed[0] && p[1] > 1) }));""")
        self.assertLess(r["grew"][0], 0.2)
        self.assertGreater(r["grew"][1], 1)   # (a little over on the way)
        self.assertGreater(r["top"], r["start"] + 1)   # (the hop)
        self.assertGreater(r["landed"][0], 650)   # (floating: not dropped like a stone)
        self.assertLess(r["landed"][-1], 1600)
        self.assertGreaterEqual(len(r["landed"]), 2)
        self.assertTrue(r["bounced"])
        self.assertLess(r["minSy"], 0.92)
        self.assertEqual(r["end"], [1, 1, 0, 0])

    def test_let_go_of_on_the_move_it_flies_on_and_stops_where_it_can_be_had(self):
        r = run_node(COOKIE_STAGE + """
game.place(200, 30);
run(400);
game.grab(game.cookie.x, game.cookie.y);
for (let i = 0; i < 8; i++) { now += 16; game.drag(game.cookie.x + 12, game.cookie.y); t.tick(now); game.tick(now); }
const from = game.cookie.x;
game.drop();
run(300);
const flying = game.cookie ? game.cookie.x - from : null;
const stage = host.stage();
run(20000, () => !game.on);
const thrown = [];
game.place(200, 60);
run(400);
game.grab(game.cookie.x, game.cookie.y);
for (let i = 0; i < 6; i++) { now += 16; game.drag(game.cookie.x, game.cookie.y - 6); t.tick(now); game.tick(now); }
const y0 = game.cookie.y;
game.drop();
run(120);
console.log(JSON.stringify({ flying, eaten, up: y0 - game.cookie.y }));""")
        self.assertGreater(r["flying"], 10)   # (on the way you moved it)
        self.assertGreater(r["up"], 3)        # (thrown up: up it goes first)
        self.assertGreaterEqual(r["eaten"], 1)

    def test_a_cookie_on_the_floor_can_be_picked_up_again(self):
        r = run_node(COOKIE_STAGE + """
game.place(40, 0);
run(2500, () => game.cookie.vy === 0 && game.cookie.y === H - gu * 0.55 - 7 * unit);
const c = game.cookie, onFloor = Math.round(c.y) === Math.round(H - gu * 0.55 - 7 * unit);
const took = game.grab(c.x, c.y);
game.drag(c.x, 10);
run(600);
const held = [game.cookie.held, Math.round(game.cookie.y)];
game.drop();
run(20000, () => !game.on);
console.log(JSON.stringify({ onFloor, took, held, eaten }));""")
        self.assertTrue(r["onFloor"] and r["took"])
        self.assertEqual(r["held"], [True, 10])   # (in your hand it doesn't fall)
        self.assertEqual(r["eaten"], 1)

    def test_picked_up_while_after_it_it_goes_after_it_again_once_down(self):
        # Put down with a cookie out it doesn't dig in first: it's straight
        # after it (talpy.land with stayOut, as both hosts call it)
        r = run_node(COOKIE_STAGE + """
game.place(40, 70);
run(5000, () => t.chased === 'run');
t.setHeld(true);
game.picked();
const held = [game.state, game.on, t.chasing];
t.land(0, () => game.landed(), true);
const from = states.length;
run(20000, () => !game.on);
console.log(JSON.stringify({ held, holes, eaten, after: states.slice(from) }));""")
        self.assertEqual(r["held"], ["held", True, False])
        # (its first burrow is the host's to fill as it lands; it dug none since)
        self.assertEqual(r["holes"], ["leave 1"])
        self.assertNotIn("spot", r["after"])
        self.assertNotIn("chase:out", r["after"])
        self.assertEqual(r["eaten"], 1)

    def test_let_go_of_as_it_hung_on_it_sees_it_again(self):
        # Pulled at while it looked at it: it stops; let go before it came
        # out, it drops back in, sees it again and goes after it
        r = run_node(COOKIE_STAGE + """
game.place(40, 70);
run(200);
const tugged = t.tug(() => {});
game.picked();
run(400);
let back = null;
t.letGo(ok => { back = ok; if (ok) game.landed(); });
run(20000, () => !game.on);
console.log(JSON.stringify({ tugged, back, eaten, states }));""")
        self.assertTrue(r["tugged"] and r["back"])
        self.assertEqual(r["eaten"], 1)
        self.assertEqual(r["states"].count("spot"), 2)

    def test_nothing_else_moves_it_while_it_runs_after_it(self):
        r = run_node(COOKIE_STAGE + """
game.place(40, 70);
run(5000, () => t.chased === 'run');
let reacted = null;
t.react('wave', ok => { reacted = ok; });
t.setMood('needs');
const after = [t.chased, t.st.walk, t.run === null, t.busy];
console.log(JSON.stringify({ reacted, after }));""")
        self.assertEqual(r, {"reacted": False, "after": ["run", "1", True, True]})

    def test_every_flavour_and_every_thanks_runs_to_its_end_and_draws(self):
        # Each flavour tasted its way, with each thanks (or none), drawn as
        # it goes; ends dug in. Mostly chocolate chip, the rest now and then
        r = run_node(COOKIE_STAGE + """
const ends = [];
for (const flavour of Object.keys(FLAVOURS)) {
    drawCookie(ctx, flavour);
    for (const thanks of THANKS_NAMES.concat([''])) {
        let ok = null;
        t.play({ steps: COOKIE.eat(flavour, false, thanks) }, done => { ok = done; }, false);
        const props = new Set();
        run(15000, () => { props.add(t.st.prop + ':' + t.st.treat); return ok !== null; });
        ends.push([flavour, thanks, ok, t.st.depth, [...props].includes('cookie:' + flavour)]);
    }
}
const picked = {};
for (let i = 0; i < 2000; i++) {
    game.place(40, 70);
    picked[game.cookie.flavour] = (picked[game.cookie.flavour] || 0) + 1;
    game.cookie = null; game.on = false; game.state = '';
}
console.log(JSON.stringify({ ends, picked }));""")
        self.assertGreaterEqual(len({e[0] for e in r["ends"]}), 8)
        for flavour, thanks, ok, depth, held in r["ends"]:
            self.assertEqual((ok, depth, held), (True, "half", True), (flavour, thanks))
        self.assertEqual(set(r["picked"]), {e[0] for e in r["ends"]})
        self.assertGreater(r["picked"]["choc"], 2000 / 4)
        self.assertLess(r["picked"]["choc"], 2000 / 2)

    def test_the_headline_the_ticker_and_the_pet_keep_their_clicks(self):
        # A double-click anywhere else on the hero's stage is a cookie: in
        # Plasma its MouseArea lies under the headline's column (z 1), the
        # ticker in it, and the pets; in VS Code the stage skips those
        strip = (ROOT / "ui/PetStrip.qml").read_text()
        area = strip[strip.index("    MouseArea {\n        anchors.fill: parent\n        enabled: strip.hero"):]
        area = area[:area.index("\n    }\n")]
        self.assertIn("onDoubleClicked", area)
        self.assertNotIn("z:", area)
        column = strip[strip.index("    ColumnLayout {\n        visible: strip.hero"):]
        self.assertIn("z: 1", column[:column.index("PlasmaComponents3.Label")])
        stage = (ROOT.parent.parent / "vscode/webview/pets/stage.ts").read_text()
        click = stage[stage.index('addEventListener("dblclick"'):]
        click = click[:click.index("});")]
        for skipped in (".cs-hero-headline.cs-clickable", ".cs-hero-ticker", ".cs-pet-grab", ".cs-cookie"):
            self.assertIn(skipped, click)

    def test_the_cookie_is_drawn_over_talpy_and_pressed_first(self):
        # As Talpy gets there it's behind the cookie, which shows whole; and
        # a cookie over it is picked up, not Talpy
        pet = (ROOT / "ui/Pet.qml").read_text()
        self.assertGreater(pet.index("    Canvas {\n        id: cookie"), pet.index("    MouseArea {\n        id: grab"))
        self.assertLess(pet.index("    Rectangle {\n        readonly property real over"), pet.index("    TalpyView {"))
        ts = (ROOT.parent.parent / "vscode/webview/pets/pet.ts").read_text()
        append = ts[ts.index("stage.petLayer.append("):]
        append = append[:append.index(";")]
        self.assertLess(append.index("this.cookieShadow"), append.index("this.sheets"))
        self.assertGreater(append.index("this.cookie]"), append.index("this.grab"))

    def test_both_hosts_tell_the_game_when_you_pick_it_up_and_it_lands(self):
        # (also as you pull at it, and as it drops back in, let go of; put
        # down with a cookie out, it stays out: land's stayOut)
        pet = (ROOT / "ui/Pet.qml").read_text()
        ts = (ROOT.parent.parent / "vscode/webview/pets/pet.ts").read_text()
        for text, fn, land, end in ((pet, "function ", "const feel = talpy.land(", "\n    }\n"),
                                    (ts, "private ", "const feel = this.talpy.land(", "\n  }\n")):
            for name, call in (("pickUp()", "picked"), ("pull()", "picked"), ("letGo()", "landed")):
                body = text[text.index(fn + name):]
                self.assertRegex(body[:body.index(end)], r"game\??\.%s\(\)" % call, name)
            landed = text[text.index(land):]
            landed = landed[:landed.index("if (feel")]
            self.assertRegex(landed, r"game\??\.landed\(\)")
            self.assertRegex(landed, r"game(\?\.| !== null && game\.)cookie")

    def test_playful_off_while_it_runs_after_one_the_cookie_vanishes_and_it_digs_in_where_it_is(self):
        # stop(): the cookie gone at once, a puff where it was for a moment
        # (then the game is off), Talpy digs in where he is (the hole he left
        # closes), and nothing more: no eating, no words
        r = run_node(COOKIE_STAGE + """
t.brainOn = false;   // (nothing of its own after)
game.place(40, 70);
run(4000, () => game.state === 'chase' && t.chased === 'run');
const where = { x: Math.round(game.cookie.x), y: Math.round(game.cookie.y), r: game.cookie.r };
const at = Math.round(px);
game.stop();
const puff = game.puff && { x: Math.round(game.puff.x), y: Math.round(game.puff.y), r: game.puff.r, p: game.puff.p };
const right = { cookie: game.cookie, state: game.state, chasing: game.chasing, talpy: t.chasing, on: game.on, holes: holes.slice() };
let grown = 0;
run(200);
grown = game.puff ? game.puff.p : -1;
run(400);
const after = { puff: game.puff, on: game.on };
run(3000);
console.log(JSON.stringify({ where, puff, right, grown, after, moved: Math.abs(Math.round(px) - at), said, eaten,
                             depth: t.st.depth, hole: t.v.hole, run: !!t.run }));""")
        self.assertEqual(r["puff"], dict(r["where"], p=0))   # (where it was, as big)
        self.assertEqual(r["right"], {"cookie": None, "state": "", "chasing": False, "talpy": False, "on": True,
                                      "holes": ["leave 1", "fill"]})   # (the hole it left closes as it digs in here)
        self.assertGreater(r["grown"], 0.3)
        self.assertLess(r["grown"], 0.6)
        self.assertEqual(r["after"], {"puff": None, "on": False})   # a puff for a moment, then the game's off
        self.assertLess(r["moved"], 2)                               # (where it is)
        self.assertEqual((r["said"], r["eaten"]), (["spot"], 0))
        self.assertEqual((r["depth"], r["hole"]), ("half", 1))   # back in its burrow, to its mood

    def test_playful_off_as_it_spots_one_or_eats_one_or_you_hold_it(self):
        # spotting it from its burrow: it's back to its mood there, never
        # after it; eating it: the cookie in its hands puffs away and it digs
        # in; held: yours till you let go, then it digs in where it lands
        r = run_node(COOKIE_STAGE + """
t.brainOn = false;   // (nothing of its own after)
const out = {};
game.place(40, 70);
run(200);
game.stop();
run(3000);
out.spot = { states: states.slice(-3), chasing: t.chasing, depth: t.st.depth, on: game.on, holes: holes.slice() };
game.place(px + 6 * gu, 70);
run(20000, () => game.state === 'eat' && t.st.bite === '2');
const hands = { x: Math.round(px), y: Math.round(H - gu * 0.55 - 9.6 * unit) };
game.stop();
out.eat = { puff: game.puff && { x: Math.round(game.puff.x), y: Math.round(game.puff.y) }, hands, state: game.state, prop: t.st.prop };
run(3000);
out.eat.after = { eaten, depth: t.st.depth, on: game.on, prop: t.st.prop };
game.place(40, 70);
run(4000, () => game.state === 'chase' && t.chased === 'run');
t.setHeld(true);
game.picked();
game.stop();
out.held = { held: t.held, cookie: game.cookie, state: game.state, puff: !!game.puff };
t.land(0, () => {}, game.cookie !== null);   // (as the hosts put it down)
run(3000);
out.landed = { depth: t.st.depth, hole: t.v.hole, on: game.on };
console.log(JSON.stringify(out));""")
        self.assertEqual(r["spot"]["chasing"], False)
        self.assertNotIn("chase:out", r["spot"]["states"])
        self.assertEqual((r["spot"]["depth"], r["spot"]["on"], r["spot"]["holes"]), ("half", False, []))
        self.assertEqual(r["eat"]["puff"], r["eat"]["hands"])   # (the one in its hands)
        self.assertEqual((r["eat"]["state"], r["eat"]["prop"]), ("", ""))
        self.assertEqual(r["eat"]["after"], {"eaten": 1, "depth": "half", "on": False, "prop": ""})
        self.assertEqual(r["held"], {"held": True, "cookie": None, "state": "", "puff": True})
        self.assertEqual(r["landed"], {"depth": "half", "hole": 1, "on": False})

    def test_both_hosts_end_the_cookie_when_playful_talpy_goes_off(self):
        pet = (ROOT / "ui/Pet.qml").read_text()
        ts = (ROOT.parent.parent / "vscode/webview/pets/pet.ts").read_text()
        stage = (ROOT.parent.parent / "vscode/webview/pets/stage.ts").read_text()
        self.assertRegex(pet, r"function onPlayfulChanged\(\) \{\n\s+if \(root\.playful\)\n\s+return\n\s+pet\.stopGame\(\)\n"
                              r"\s+if \(pet\.game\)\n\s+pet\.game\.stop\(\)")
        self.assertRegex(stage, r"if \(world\.playful\) continue;\n\s+p\.stopGame\(\);\n\s+p\.stopCookie\(\);")
        self.assertIn("this.game?.stop();", ts)
        # the puff drawn where the game says, as it goes
        self.assertIn("T.drawPuff(ctx, p, flavour)", pet)
        self.assertIn("puff.p = f.p", pet)
        self.assertIn("drawPuff(ctx, f.p, f.flavour);", ts)
        self.assertIn("const f = this.game?.puff ?? null", ts)

    def test_the_game_runs_only_with_a_cookie(self):
        # (an add-on: nothing more each frame unless a cookie is out or eaten)
        pet = (ROOT / "ui/Pet.qml").read_text()
        self.assertRegex(pet, r"enabled: pet\.cookieOn && pet\.playing && pet\.game !== null\n\s+function onPetFrame\(now\) \{\n\s+pet\.game\.tick\(now\)")
        ts = (ROOT.parent.parent / "vscode/webview/pets/pet.ts").read_text()
        self.assertIn("if (this.game?.on) this.game.tick(now);", ts)


class ThemeTests(unittest.TestCase):
    def test_state_colors_use_the_accent(self):
        # In a Plasma 6 popup, Kirigami.Theme.highlightColor is a pale selection
        # tint (light blue on light themes, navy on dark ones): working dots,
        # usage bars and the hero's light would hardly show. focusColor is the accent.
        for p in (ROOT / "ui").glob("*.qml"):
            self.assertIsNone(re.search(r"Theme\.highlightColor", p.read_text()), p.name)


class PetEventTests(unittest.TestCase):
    def test_every_pet_event_passes_kind_text_and_key(self):
        # petEvent(kind, text, key) called with two arguments throws "Insufficient
        # arguments": at a limit reset that stopped every later poll from being
        # shown (the popup froze until Plasma restarted).
        for p in (ROOT / "ui").glob("*.qml"):
            text = p.read_text()
            for m in re.finditer(r"\bpetEvent\(", text):
                if text[:m.start()].rstrip().endswith("signal"):
                    continue
                depth, args, i = 1, 1, m.end()
                while depth:
                    c = text[i]
                    if c in "([{":
                        depth += 1
                    elif c in ")]}":
                        depth -= 1
                    elif c == "," and depth == 1:
                        args += 1
                    elif c == '"':   # skip string literals (they may hold commas)
                        i = text.index('"', i + 1)
                    i += 1
                line = text.count("\n", 0, m.start()) + 1
                self.assertEqual(args, 3, f"{p.name}:{line}: petEvent needs (kind, text, key)")


if __name__ == "__main__":
    unittest.main()


class PlainTextTests(unittest.TestCase):
    """Chat names, agent activity and other text from transcripts are shown
    as plain text: as rich text, "Fix <div> centering" lost its tag and an
    <img src=…> in an agent's activity made plasmashell fetch the URL."""

    def test_every_label_and_tooltip_is_plain_text(self):
        missing = []
        for path in sorted((ROOT / "ui").glob("*.qml")):
            if path.name in SETTINGS_PAGES:  # fixed texts only
                continue
            lines = path.read_text().split("\n")
            for i, line in enumerate(lines):
                m = re.match(r"(\s*)(PlasmaComponents3\.Label|Text|Kirigami\.Heading|PlasmaCore\.ToolTipArea)\s*\{\s*$", line)
                if not m:
                    continue
                own, depth = [], 0
                for j in range(i, len(lines)):
                    depth += lines[j].count("{") - lines[j].count("}")
                    if j > i and re.match(m.group(1) + r"    \S", lines[j]):
                        own.append(lines[j])
                    if depth <= 0 and j > i:
                        break
                if any(re.match(r"\s*(text|mainText|subText):", l) for l in own) and not any("textFormat" in l for l in own):
                    missing.append(f"{path.name}:{i + 1}")
        self.assertEqual(missing, [])

    def test_inline_messages_escape_what_they_quote(self):
        for name in ("SessionRow.qml",):
            text = (ROOT / "ui" / name).read_text()
            block = text[text.index("Kirigami.InlineMessage {"):]
            block = block[:block.index("actions:")]
            self.assertIn('"<span>"', block, name)
            self.assertNotRegex(block, r"[^(]row\.session\.name\)|shareConfirm\.name,", name)
        # (the keep-only question is a ConfirmLine: its label is plain text)
        self.assertIn("textFormat: Text.PlainText", (ROOT / "ui/ConfirmLine.qml").read_text())
        self.assertIn("sourceComponent: ConfirmLine {", (ROOT / "ui/KeepOnlyMessage.qml").read_text())


class SeveralCopiesTests(unittest.TestCase):
    """Five copies (panel and one dashboard per screen) each ran the status
    check every 2 s and kept their pets moving under maximized windows:
    plasmashell took most of a core (2026-10-20)."""

    def test_the_status_check_runs_once_for_all_copies(self):
        # main.qml asks hub/Hub.qml (a singleton, shared by the copies in
        # plasmashell); only the hub runs talpy_den.py and names the copy
        main = (ROOT / "ui/main.qml").read_text()
        hub = (ROOT / "ui/hub/Hub.qml").read_text()
        self.assertNotIn("\" --instance", main)
        self.assertNotRegex(main, r"connectSource\(\s*command\b")
        self.assertIn("pragma Singleton", hub)
        self.assertIn("singleton Hub 1.0 Hub.qml", (ROOT / "ui/hub/qmldir").read_text())
        self.assertIn('--instance " + shellQuote(instanceName)', hub)

    def test_the_pets_wake_at_once_when_you_look(self):
        # Showing the desktop hides the windows without minimizing them, and a
        # 5 s re-check woke one copy after the other: you saw some dashboards
        # still while looking at all of them (2026-10-20). It's a binding now,
        # and with the mouse on a dashboard it can't be covered either.
        watch = (ROOT / "ui/CoverWatch.qml").read_text()
        main = (ROOT / "ui/main.qml").read_text()
        self.assertIn("readonly property bool covered: windowCovers && !KWindowSystem.showingDesktop", watch)
        self.assertRegex(main, r"coveredByWindow: .*covered && !mouseOnWidget\.hovered")

    def test_a_dashboard_on_the_desktop_keeps_its_pets_after_a_click(self):
        # Opening a chat "closes the popup" (expanded = false), but a dashboard
        # on the desktop stays on screen: its pets froze (seen on one screen,
        # 2026-10-20). What moves goes by dashboardShown, not by expanded.
        strip = (ROOT / "ui/PetStrip.qml").read_text()
        full = (ROOT / "ui/FullRepresentation.qml").read_text()
        self.assertIn("readonly property bool live: visible && root.dashboardShown", strip)
        self.assertNotIn("root.expanded", strip + (ROOT / "ui/Pet.qml").read_text())
        self.assertIn("root.dashboardShown && !root.coveredByWindow", full)

    def test_each_ssh_host_is_checked_once_for_all_copies(self):
        # (Plasma merged identical checks that started at the same moment,
        # which held only while the copies' timers kept in step)
        main = (ROOT / "ui/main.qml").read_text()
        self.assertIn('Hub.want(instanceId, "ssh:" + host, next[host], interval, false)', main)
        self.assertNotIn("remotePoller", main)
        self.assertNotRegex(main, r'connectSource\([^)]*--status')

    def test_commands_run_in_a_datasource_of_their_own(self):
        # Plasma tells every executable DataSource in plasmashell about each
        # command that ends, and each keeps a property for its name for good:
        # with ~30 DataSources a copy and names that never repeat, each new
        # command took plasmashell longer, a second after a few hours, and
        # the panel and the chat pane froze (2026-10-26). Only hub/Exec.qml
        # makes DataSources, one per command, gone with its answer.
        for path in sorted((ROOT / "ui").rglob("*.qml")):
            if path.name != "Exec.qml":
                self.assertFalse(re.search(r"plasma5support|DataSource \{", path.read_text()), path.name)
        exec_ = (ROOT / "ui/hub/Exec.qml").read_text()
        self.assertIn("runner.createObject(exec)", exec_)
        self.assertRegex(exec_, r"disconnectSource\(source\)\s+destroy\(\)")
        self.assertIn("Exec 1.0 Exec.qml", (ROOT / "ui/hub/qmldir").read_text())
        # what runs on a clock goes under the same name each time
        main = (ROOT / "ui/main.qml").read_text()
        self.assertRegex(main, r'ScreenSaver\.GetActive"\)')
        self.assertIn('(kind === "conversation" ? "" : " # " + Date.now())', (ROOT / "ui/ChatPane.qml").read_text())

    @NEEDS_PLASMA5SUPPORT
    def test_a_command_costs_the_same_after_thousands(self):
        # 20 idle copies beside one that runs 1500 commands with new names:
        # a DataSource each took 0.8 ms a command at first and 112 ms at the
        # end; with Exec it stays under a millisecond
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            qml = Path(tmp) / "t.qml"
            qml.write_text(('import QtQuick\nimport "HUB"\nItem {\n  id: t\n'
                            '  property int done: 0\n  signal batch()\n'
                            '  Repeater { model: 20; Item { Exec {} } }\n'
                            '  Exec { id: one; onNewData: (source, data) => { disconnectSource(source);'
                            ' if (++t.done % 300 === 0) t.batch(); if (t.done < 1500) Qt.callLater(t.next) } }\n'
                            '  function next() { one.connectSource("true # " + Date.now() + "." + done) }\n}\n')
                           .replace("HUB", (ROOT / "ui/hub").as_uri()))
            script = (
                "import sys, time\n"
                "from PySide6.QtCore import QUrl, QTimer\n"
                "from PySide6.QtGui import QGuiApplication\n"
                "from PySide6.QtQuick import QQuickView\n"
                "app = QGuiApplication(sys.argv)\n"
                "view = QQuickView()\n"
                "view.setSource(QUrl.fromLocalFile(sys.argv[1]))\n"
                "r = view.rootObject()\n"
                "last = [time.thread_time()]\n"
                "def batch():\n"
                "    t = time.thread_time(); print(1000 * (t - last[0]) / 300, flush=True); last[0] = t\n"
                "    r.property('done') >= 1500 and app.quit()\n"
                "r.batch.connect(batch)\n"
                "QTimer.singleShot(0, r.next)\n"
                "QTimer.singleShot(120000, app.quit)\n"
                "app.exec()\n")
            out = subprocess.run(["python3", "-c", script, str(qml)], capture_output=True, text=True, timeout=180,
                                 env=dict(__import__("os").environ, QT_QPA_PLATFORM="offscreen"))
        costs = [float(line) for line in out.stdout.split()]
        self.assertEqual(len(costs), 5, out.stderr[-2000:])
        self.assertLess(costs[-1], 2 * costs[0] + 1, costs)

    @NEEDS_PLASMA5SUPPORT
    def test_a_check_whose_datasource_is_gone_runs_again(self):
        # A check's DataSource gone with no answer counted as running: each
        # try to run it again threw ("Property 'destroy' of object … is not
        # a function") before it was replaced, for good, and the widget
        # showed what it saw last until plasmashell restarted, Refresh too
        # (2026-10-27). It runs again at the next check, not a minute later.
        outputs, runs, _, _, stderr = run_hub(
            '  Component.onCompleted: Hub.want("c0", "status", t.command, 500, true)\n'
            '  Timer { interval: 60; running: true; onTriggered:'
            ' { for (const c in Hub.poller.running) Hub.poller.running[c].source.destroy() } }', 2500)
        self.assertNotIn("check didn't start", stderr)
        self.assertGreaterEqual(outputs, 2, stderr[-2000:])

    @NEEDS_PLASMA5SUPPORT
    def test_a_check_asked_for_while_one_runs_runs_after_it(self):
        # Refresh while a check ran did nothing, and a check run again once
        # it answered (a chat changed meanwhile) got that answer back, which
        # Plasma keeps a moment: nothing ran
        for ask in ("Hub.refresh(t.command)", "Hub.checkNow()"):
            outputs, runs, _, _, stderr = run_hub(
                '  Component.onCompleted: Hub.want("c0", "status", t.command, 60000, true)\n'
                f'  Timer {{ interval: 60; running: true; onTriggered: {ask} }}', 1500)
            self.assertEqual((outputs, runs), (2, 2), ask)

    @NEEDS_PLASMA5SUPPORT
    def test_a_copy_with_a_popup_notifies(self):
        # On the desktop and in a panel, the desktop copy here first sent the
        # notifications: Open the Recap only switched the tab of the dashboard
        # under your windows. Alone, a copy notifies whatever it is.
        _, _, _, _, stderr = run_hub(
            '  Component.onCompleted: {\n'
            '    const seen = []\n'
            '    Hub.want("desk", "status", t.command, 60000, true); Hub.placed("desk", false)\n'
            '    seen.push(Hub.leaderId)\n'
            '    Hub.want("panel", "status", t.command, 60000, true); Hub.placed("panel", true)\n'
            '    seen.push(Hub.leaderId)\n'
            '    Hub.want("tray", "status", t.command, 60000, true); Hub.placed("tray", true)\n'
            '    Hub.want("desk2", "status", t.command, 60000, true); Hub.placed("desk2", false)\n'
            '    seen.push(Hub.leaderId)\n'
            '    Hub.drop("panel"); Hub.drop("tray"); Hub.placed("panel", true)\n'
            '    seen.push(Hub.leaderId)\n'
            '    console.warn("leaders " + seen.join(" "))\n'
            '  }', 300)
        self.assertIn("leaders desk panel panel desk", stderr, stderr[-2000:])

    @NEEDS_PLASMA5SUPPORT
    def test_the_live_watcher_answers_once_a_run(self):
        # Started again the moment it answered, live.py's watcher got that
        # answer back from Plasma ~90 times in a row, each a status check
        outputs, runs, live_runs, live_answers, stderr = run_hub(
            '  Component.onCompleted: { Hub.want("c0", "status", t.command, 60000, true); Hub.wantLive("c0", t.live) }',
            2500)
        self.assertGreater(live_runs, 3, stderr[-2000:])
        self.assertLessEqual(live_answers, live_runs)
        self.assertLessEqual(outputs, runs)

    def test_less_motion_calms_the_pets_as_in_vscode(self):
        # VS Code's pets keep still for a desktop that asks for less motion
        # (prefers-reduced-motion); Plasma's, with its animation speed set to
        # instant, dug about, hung on to the burrow and ran after a cookie.
        # (Instant makes Kirigami's durations 1 ms: animateRows' > 0 never
        # saw it either.)
        vscode = ROOT.parent.parent / "vscode/webview/pets"
        pet_ts, stage_ts = (vscode / "pet.ts").read_text(), (vscode / "stage.ts").read_text()
        pet, strip = (ROOT / "ui/Pet.qml").read_text(), (ROOT / "ui/PetStrip.qml").read_text()
        main = (ROOT / "ui/main.qml").read_text()
        self.assertIn("readonly property bool lessMotion: Kirigami.Units.longDuration <= 1", main)
        self.assertIn("animateRows: !lessMotion", main)
        for ts, qml in (("travels: this.lone && !reducedMotion()", "travels: pet.lone && !root.lessMotion"),
                        ("instant: () => reducedMotion()", "instant: () => root.lessMotion"),
                        ("if (!reducedMotion() && this.talpy.tug(", "if (!root.lessMotion && talpy && talpy.tug(")):
            self.assertIn(ts, pet_ts)
            self.assertIn(qml, pet)
        dig_ts = pet_ts[pet_ts.index("private digTo("):pet_ts.index('this.talpy.react(quick ? "scoot" : "dig")')]
        dig = pet[pet.index("function digTo("):pet.index('react(quick ? "scoot" : "dig")')]
        self.assertIn("if (reducedMotion()) {", dig_ts)
        self.assertIn("if (root.lessMotion) {", dig)
        self.assertIn("night && !reducedMotion()", stage_ts)
        self.assertIn("!root.lessMotion ? strip.twinkle(", strip)
        # as the setting changes, not only when the view opens (Plasma's binding,
        # GNOME's notify::enable-animations); and less motion doesn't draw them
        # live (each picture costs): the film stays on, as Plasma's
        self.assertIn("onReducedMotionChange(() => {", stage_ts)
        self.assertIn("this.talpy.travels = this.lone && !reducedMotion();", pet_ts)
        film = pet_ts[pet_ts.index("f.on = "):][:200]
        self.assertNotIn("reducedMotion", film[:film.index(";")])

    def test_looping_animations_stop_under_a_window(self):
        # Every repeating timer and endless animation of the pets runs only
        # while it can be seen (playing), not just while the popup is open
        # (live): on the desktop the dashboard is always "open".
        for name in ("Pet.qml", "PetStrip.qml", "TalpyView.qml"):
            lines = (ROOT / "ui" / name).read_text().split("\n")
            for i, line in enumerate(lines):
                if not re.search(r"^\s*(loops: Animation\.Infinite|repeat: true)\s*$", line):
                    continue
                indent = len(line) - len(line.lstrip())
                start = i
                while start > 0 and not lines[start].rstrip().endswith("{"):
                    start -= 1
                end = i
                while end < len(lines) and not (lines[end].strip() == "}" and len(lines[end]) - len(lines[end].lstrip()) < indent):
                    end += 1
                running = [l for l in lines[start:end] if l.strip().startswith("running:")
                           and len(l) - len(l.lstrip()) == indent]
                self.assertTrue(running and "playing" in running[0] and ".live" not in running[0],
                                f"{name}:{i + 1}: a loop that should stop while covered")


class NewChatTests(unittest.TestCase):
    def test_only_a_new_chat_switches_vscode_on_a_host(self):
        # A new chat on an SSH host's other account opens in VS Code, which
        # switches there first (--account); a recent chat reopens on its own
        # account, so its switch never offers that
        switch = (ROOT / "ui/OpenInSwitch.qml").read_text()
        main = (ROOT / "ui/main.qml").read_text()
        self.assertIn("root.openInVscode(group, remoteHost, resuming)", switch)
        self.assertIn("readonly property bool switching: !resuming && root.vscodeSwitches(group, remoteHost)", switch)
        self.assertIn('const account = group && !group.vscodeHere ? " --account " + shellQuote(group.configDir || "-") : ""', main)
        self.assertIn("(group.vscodeHere || (!resuming && vscodeSwitches(group, host)))", main)

    def test_a_folder_row_never_closes_its_own_list(self):
        # Closing the list (newChatGroup = "") destroys its rows: the rest of
        # the row's click handler lost root ("ReferenceError: root is not
        # defined") and no terminal opened on the host (2026-10-20). Root's
        # functions close it, after the row handed them what they need.
        section = (ROOT / "ui/GroupSection.qml").read_text()
        box = (ROOT / "ui/NewChatBox.qml").read_text()
        main = (ROOT / "ui/main.qml").read_text()
        self.assertNotIn("newChatGroup = ", section)
        rows = box[box.index("delegate: PlasmaComponents3.ItemDelegate"):box.index("Kirigami.Separator")]
        self.assertNotIn("newChatGroup", rows)
        self.assertNotIn("planComposer", rows)
        self.assertIn("onClicked: root.startChat(box.group, box.remoteHost, folderRow.folder, box.inVscode, box.plan)", rows)
        start = main[main.index("function startChat("):]
        self.assertIn("remoteNewChat(host, folder.newChatCommand ? folder.newChatCommand + chatOptions : folder.newChatCommand)",
                      start[:start.index("\n    }\n")])
        self.assertIn('function remoteNewChat(host, command) {\n        newChatGroup = ""\n        remoteOpen(host, command)', main)


class SshUsageTests(unittest.TestCase):
    def test_every_host_view_shows_an_accounts_usage_once(self):
        # An account on this computer and on a host has one plan usage: the
        # host lists, the badge's and the tooltip's (allGroups) all go
        # through withUsage, and the setting is shared between copies
        main = (ROOT / "ui/main.qml").read_text()
        host = (ROOT / "ui/HostSection.qml").read_text()
        section = (ROOT / "ui/GroupSection.qml").read_text()
        self.assertIn('<entry name="sshUsage" type="String">', (ROOT / "config/main.xml").read_text())
        self.assertIn('"sshUsage"', main[main.index("readonly property var sharedKeys"):])
        self.assertIn('status.groups.map(g => withUsage(g, ""))', main)
        self.assertIn("out.push(Object.assign({}, withUsage(g, host), { host: host }))", main)
        self.assertIn("info.result.groups.map(g => root.withUsage(g, host))", host)
        self.assertIn("visible: !section.group.limitsHidden", section)


class DefaultAccountMenuTests(unittest.TestCase):
    def test_the_right_click_menus_accounts_are_radio_buttons_under_its_icons(self):
        # One choice (checkboxes said you could pick two), its mark in the
        # icon column as the other entries' icons: a checkable entry's mark
        # is drawn left of that column, so the entries are plain ones with
        # a radio button for an icon, following the status
        main = (ROOT / "ui/main.qml").read_text()
        choices = re.findall(r"readonly property var account: root\.defaultChoices\[\d\] \|\| null\n((?:\s+.*\n)*?)\s+\}", main)
        self.assertEqual(len(choices), 4)
        for body in choices:
            self.assertIn("icon.name: root.defaultIcon(account)", body)
            self.assertIn("onTriggered: root.makeDefault(account)", body)
            self.assertNotIn("checkable", body)
        icon = main[main.index("function defaultIcon("):]
        self.assertIn('account.defaultHere === true ? "radio-on.svg" : "radio-off.svg"', icon[:icon.index("\n    }\n")])
        for name in ("radio-on.svg", "radio-off.svg"):
            self.assertTrue((ROOT / "icons" / name).is_file(), name)


class SearchAndNewChatBoxTests(unittest.TestCase):
    def test_a_box_made_while_its_list_is_open_shows_the_task(self):
        # A plan's new-chat box is made again when the plans are folded and
        # unfolded with its composer open: it is visible from the start, so
        # onVisibleChanged never filled its field, which stayed empty while
        # root.taskText, still set, was what the chat started with
        box = (ROOT / "ui/NewChatBox.qml").read_text()
        self.assertIn("onVisibleChanged:", box)
        self.assertRegex(box, r"Component\.onCompleted:\s*taskField\.text = root\.taskText")

    def test_a_stale_hosts_error_is_a_sentence_before_what_it_said(self):
        # "Can't reach h: ssh: connect to host h port 22: Connection timed out"
        # has no full stop: the VS Code view adds one before "Showing what it
        # said", the dashboard ran the two together
        host = (ROOT / "ui/HostSection.qml").read_text()
        self.assertIn("[.!?]$", host)

    def test_a_found_chats_dot_is_red_like_its_row(self):
        # The search shows a chat that's listed above by its row's state: the
        # row's dot is red for a chat that failed or that a usage limit stopped
        row = (ROOT / "ui/SessionRow.qml").read_text()
        found = (ROOT / "ui/SearchResults.qml").read_text()
        self.assertIn('row.session.reason === "failed" || (row.stopped && !row.stopped.over) ? Kirigami.Theme.negativeTextColor', row)
        self.assertIn('hit.row.reason === "failed" || (!!hit.row.stopped && !hit.row.stopped.over) ? Kirigami.Theme.negativeTextColor', found)


class SettingsPageTests(unittest.TestCase):
    def test_the_check_intervals_default_alike_in_plasma_gnome_and_vs_code(self):
        # GNOME checked twice as often while nothing ran (10 s, the others 20 s)
        repo = ROOT.parent.parent
        plasma = dict(re.findall(r'<entry name="(\w+)" type="Int">\s*<label>[^<]*</label>\s*<default>(\d+)<',
                                 (ROOT / "config/main.xml").read_text()))
        gnome = dict(re.findall(r'<key name="([\w-]+)" type="i">\s*<default>(\d+)<',
                                (repo / "gnome/extension/schemas/org.gnome.shell.extensions.talpy-den.gschema.xml").read_text()))
        code = {k: v for c in json.loads((repo / "vscode/package.json").read_text())["contributes"]["configuration"]
                for k, v in c["properties"].items()}
        for key, gkey in (("pollInterval", "poll-interval"), ("idlePollInterval", "idle-poll-interval")):
            self.assertEqual({int(plasma[key]), int(gnome[gkey]), code["talpyDen." + key]["default"]}, {int(plasma[key])}, key)

    def test_a_closable_message_box_isnt_bound_to_visible(self):
        # Kirigami's close button sets the box's visible, which ends a binding
        # like `visible: page.message !== ""`: the next message never showed
        # again (the Accounts settings: after one was closed, no answer to a
        # click was seen). Such a box is shown and hidden from code.
        for path in sorted((ROOT / "ui").glob("*.qml")):
            lines = path.read_text().split("\n")
            for i, line in enumerate(lines):
                if not re.match(r"\s*Kirigami\.InlineMessage\s*\{\s*$", line):
                    continue
                indent = len(line) - len(line.lstrip())
                own = []
                for j in range(i + 1, len(lines)):
                    if lines[j].strip() == "}" and len(lines[j]) - len(lines[j].lstrip()) == indent:
                        break
                    if re.match(" {%d}\\S" % (indent + 4), lines[j]):
                        own.append(lines[j])
                if any(re.match(r"\s*showCloseButton:\s*true", l) for l in own):
                    self.assertFalse(any(re.match(r"\s*visible:", l) for l in own),
                                     f"{path.name}:{i + 1}: a closable message box bound to visible")

    def test_every_cfg_property_matches_a_setting_of_its_type(self):
        # Plasma writes every cfg_ property of the page shown back on Apply
        # (and passes every setting and its default to each page): one without
        # a setting of its type in main.xml, or a setting on no page, is lost
        # or mangled, and one on two pages is written back by both
        kinds = dict(re.findall(r'<entry name="(\w+)" type="(\w+)"', (ROOT / "config/main.xml").read_text()))
        of_control = {"QQC2.SpinBox": "Int", "QQC2.Slider": "Int", "QQC2.CheckBox": "Bool", "QQC2.TextField": "String",
                      "SoundChooser": "String"}
        of_type = {"string": "String", "bool": "Bool", "int": "Int"}
        found, defaults, where = {}, {}, {}
        for name in SETTINGS_PAGES:
            page = (ROOT / "ui" / name).read_text()
            controls = {m.group(2): m.group(1) for m in re.finditer(r"(\S+) \{\n\s+id: (\w+)\n", page)}
            own, own_defaults = {}, {}
            for m in re.finditer(r"property alias cfg_(\w+): (\w+)\.\w+", page):
                own[m.group(1)] = of_control[controls[m.group(2)]]
            for m in re.finditer(r"property (string|bool|int) cfg_(\w+)", page):
                (own_defaults if m.group(2).endswith("Default") and m.group(2)[:-7] in kinds else own)[m.group(2)] = of_type[m.group(1)]
            for key in own:
                self.assertNotIn(key, where, f"cfg_{key} on {where.get(key)} and {name}")
                where[key] = name
            # (each page declares the defaults of its own settings, no others)
            self.assertEqual({k + "Default": v for k, v in own.items() if k in kinds}, own_defaults, name)
            found.update(own)
            defaults.update(own_defaults)
        # (the ones set in the popup are ConfigPage's on every page: it puts them back as they are now on Apply)
        popup = {"focusView", "sshHosts", "newChatInVscode", "newChatModel", "newChatEffort", "newChatMode",
                 "diffSideBySide", "paneTextPercent"}
        self.assertEqual(found, {k: v for k, v in kinds.items() if k not in popup})
        self.assertEqual({k + "Default": v for k, v in kinds.items() if k not in popup}, defaults)

    def test_the_settings_pages_are_the_categories_in_their_order(self):
        # The same categories in the same order in Plasma, VS Code and GNOME;
        # Plasma's Accounts page after them
        config = (ROOT / "config/config.qml").read_text()
        names = re.findall(r'name: i18n\("([^"]+)"\)', config)
        self.assertEqual(names, CATEGORIES + ["Accounts"])
        sources = re.findall(r'source: "(\w+\.qml)"', config)
        self.assertEqual(sorted(sources), sorted(p.name for p in (ROOT / "ui").glob("config*.qml")))
        for icon in re.findall(r"icon: (.+)", config):
            # (from the icon table, as every icon; Talpy's page his own picture, a file of the package's icons/)
            self.assertRegex(icon, r'^(Icons\.plasma\.\w+|Qt\.resolvedUrl\("\.\./icons/" \+ Icons\.plasma\.\w+\)   // .*)$')
        self.assertIn('icon: Qt.resolvedUrl("../icons/" + Icons.plasma.pet)', config)
        # (a copy of his picture: the same file)
        self.assertEqual((ROOT / "icons/talpy.svg").read_bytes(), (ROOT / "pets/talpy.svg").read_bytes())

    def test_every_settings_page_takes_every_setting_without_a_warning(self):
        # Plasma hands every page cfg_<key> and cfg_<key>Default for every
        # setting: each page logged 70-80 "Setting initial properties failed"
        # for the other pages' ones (2026-11-01). ConfigPage declares them all
        # (and on Apply puts back the ones a page didn't change as they are now)
        keys = re.findall(r'<entry name="(\w+)" type="\w+"', (ROOT / "config/main.xml").read_text())
        base = (ROOT / "ui/ConfigPage.qml").read_text()
        self.assertIn("\nKCM.SimpleKCM {\n", base)
        self.assertEqual(re.findall(r"\n    property var cfg_(\w+)(?=\n)", base),
                         [k for key in keys for k in (key, key + "Default")])
        self.assertIn("configPage[name] = config[key]", base)
        for name in SETTINGS_PAGES + ["configAccounts.qml"]:
            page = (ROOT / "ui" / name).read_text()
            self.assertIn("\nConfigPage {\n", page, name)
            self.assertNotIn("KCM.SimpleKCM {", page, name)
            self.assertNotIn("function saveConfig()", page, name)   # (it would hide ConfigPage's)
        vscode = json.loads((ROOT.parent.parent / "vscode/package.json").read_text())["contributes"]["configuration"]
        self.assertEqual([c["title"] for c in sorted(vscode, key=lambda c: c["order"])], CATEGORIES)
        prefs = (ROOT.parent.parent / "gnome/extension/prefs.js").read_text()
        self.assertEqual(re.findall(r"category\('([^']+)'", prefs), CATEGORIES)
        self.assertIn("new Adw.PreferencesPage({title: 'Accounts'", prefs)
        self.assertLess(prefs.rindex("category('Advanced'"), prefs.index("window.add(this._accountsPage("))

    def test_the_settings_pages_call_the_helpers_with_flags_they_have(self):
        # A flag a helper doesn't know ends in its usage text, never an answer:
        # the page then says "the helper gave no answer"
        code = ROOT / "code"

        def main_of(name):
            text = (code / name).read_text()
            return text[text.index("def main("):]
        accounts = (ROOT / "ui/configAccounts.qml").read_text()
        flags = set(re.findall(r'"(--[a-z-]+)"', accounts))
        actions = {"--list", "--add", "--login", "--logout", "--remove", "--command", "--no-command", "--default"}
        self.assertLessEqual(actions | {"--check", "--share-from", "--config-dir", "--accounts"}, flags)
        for flag in sorted(flags - {"--accounts"}):
            self.assertIn(f'"{flag}"', main_of("accounts.py"), flag)
        self.assertIn('"--accounts"', main_of("remote.py"))
        host_actions = re.search(r"ACCOUNT_ACTIONS = \((.*?)\)", (code / "remote.py").read_text(), re.S).group(1)
        for flag in sorted(actions):
            self.assertIn(f'"{flag}"', host_actions, flag)
        general = "".join((ROOT / "ui" / name).read_text() for name in SETTINGS_PAGES)
        for flag in sorted(set(re.findall(r"--[a-z-]+", general))):
            self.assertTrue(any(f'"{flag}"' in main_of(name) for name in ("jump.py", "notify_sound.py", "week.py", "pane.py",
                                                                         "dictate.py")),
                            flag)

    def test_every_setting_the_ui_reads_exists(self):
        # A setting misspelled in the UI reads as undefined, without an error
        names = set(re.findall(r'<entry name="(\w+)"', (ROOT / "config/main.xml").read_text()))
        for path in sorted((ROOT / "ui").glob("**/*.qml")):
            for name in re.findall(r"Plasmoid\.configuration\.(\w+)", path.read_text()):
                self.assertIn(name, names, f"{path.name}: Plasmoid.configuration.{name}")
        main = (ROOT / "ui/main.qml").read_text()
        shared = main[main.index("readonly property var sharedKeys: ["):]
        for name in re.findall(r'"(\w+)"', shared[:shared.index("]")]):
            self.assertIn(name, names, f"sharedKeys: {name}")

    def test_the_copies_share_every_setting_but_the_focus_view_and_the_shortcut(self):
        # Only one copy notifies (the Monday recap too), and the chat pane is
        # any copy's: a setting left out was changed only where you changed it
        names = set(re.findall(r'<entry name="(\w+)"', (ROOT / "config/main.xml").read_text()))
        main = (ROOT / "ui/main.qml").read_text()
        shared = main[main.index("readonly property var sharedKeys: ["):]
        shared = set(re.findall(r'"(\w+)"', shared[:shared.index("]")]))
        self.assertEqual(names - shared, {"focusView", "shortcutGoesToChat"})


class PetLifeTests(unittest.TestCase):
    """What a pet shows of its chat, and what ends a drag: QML that can't be
    run here, so the rules are read off the source."""

    def test_a_pet_is_told_of_every_field_of_its_chat_that_it_shows(self):
        # A pet reads its chat (Pet.qml's mood, the tooltip's stateText) from the
        # row that PetStrip.sync() handed it, and sync() does nothing while the
        # signature of the shown chats is the same. A field missing from the
        # signature never reaches the pet: when a usage limit reset
        # (stopped.over), the chat's pet went on waiting for it, "battery-low"
        strip = (ROOT / "ui/PetStrip.qml").read_text()
        pet = (ROOT / "ui/Pet.qml").read_text()
        main = (ROOT / "ui/main.qml").read_text()
        signature = strip[strip.index("const seen = JSON.stringify("):]
        signature = signature[:signature.index("syncedAs = seen")]
        tooltip = main[main.index("function stateText(s) {"):]
        tooltip = tooltip[:tooltip.index("\n    }\n")]
        shown = set(re.findall(r"\bchat\.(\w+)", pet)) | set(re.findall(r"\bs\.(\w+)", tooltip))
        self.assertLessEqual({"state", "stopped", "reason", "since", "context", "agents"}, shown)
        for field in sorted(shown):
            self.assertIn(f"s.{field}", signature, f"PetStrip.sync() doesn't see changes of {field}")

    def test_a_drag_cut_short_puts_the_pet_down(self):
        # The popup closing (or the stage folding away) under a pressed mouse
        # button ends the press with canceled(), not released(): the pet stayed
        # held in the air with no life in him, and a chat's pet whose chat had
        # left never walked off (leaveTimer waits for a pet that is held)
        pet = (ROOT / "ui/Pet.qml").read_text()
        grab = pet[pet.index("id: grab"):]
        self.assertRegex(grab, r"onCanceled:\s*\{[^}]*pet\.drop\(\)")

    def test_a_pet_whose_chat_left_waves_and_digs_away(self):
        # "then it waves and digs away" (PetStrip.qml): leaving plays Talpy's
        # leave, which waves before it digs in, and only then is the pet gone
        pet = (ROOT / "ui/Pet.qml").read_text()
        self.assertRegex(pet, r"onLeavingChanged: \{\n\s+if \(leaving && !held && !tugging && !pushing\)\n\s+goAway\(\)")
        self.assertRegex(pet, r'react\("leave", ok => \{\n\s+if \(ok && pet\.leaving\) \{\n\s+pet\.departed = true\n\s+Qt\.callLater\(pet\.gone\)')
        actions = (TALPY / "actions.mjs").read_text()
        leave = actions[actions.index("    leave: {"):]
        leave = leave[:leave.index("}] }")]
        self.assertLess(leave.index("arms: 'wave'"), leave.index("depth: 'gone'"))

    @NEEDS_PLASMA_QML
    def test_a_pet_that_dug_away_is_removed_after_its_frame(self):
        # Its leave ends in Talpy's tick, inside its view's frame; removed
        # right there (PetStrip's removePet), the view was destroyed under the
        # rest of the frame: "attempted to evaluate a function in an invalid
        # context" and "TalpyView.qml:121: TypeError: Property 'showWanted'
        # … is not a function" in the journal for each chat that left
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            stage = Path(tmp) / "stage.qml"
            stage.write_text(f'import QtQuick\nimport "{(ROOT / "ui").as_uri()}"\n' + """Item {
    id: root
    width: 400; height: 200
    signal petFrame(real now)
    readonly property real petFrameMs: 16.7
    property string petMood: "idle"
    property int agentsRunning: 0
    property string waitingName: ""
    property string highUsageText: ""
    property string contextFullText: ""
    property int maxFiveHour: 0
    property int removed: 0
    function stateText(c) { return "" }
    function jumpTo() {}
    function remoteShow() {}
    function i18n(s) { return s }
    function i18nc(c, s) { return s }
    function i18np(a, b, n) { return n === 1 ? a : b }
    // as PetStrip's
    function removePet() { petModel.remove(0); removed++; done.start() }
    Timer { interval: 16; repeat: true; running: true; onTriggered: root.petFrame(Date.now()) }
    Timer { interval: 300; running: true; onTriggered: petModel.setProperty(0, "leaving", true) }
    Timer { id: done; interval: 300; onTriggered: Qt.quit() }
    Item {
        id: stage
        anchors.fill: parent
        property real gu: 8
        property real boxSize: 60
        property real bodyWidth: 40
        property real bodyHeight: 40
        property real loneGround: 150
        property real chatGround: 150
        property real tagWidth: 100
        property bool live: true
        property bool playing: true
        property real cursorX: -1
        property bool firstShown: true
        function say(pet, text) {}
        ListModel { id: petModel; ListElement { petKey: "a"; leaving: false } }
        Repeater {
            model: petModel
            delegate: Pet {
                required property var model
                strip: stage
                petKey: model.petKey
                leaving: model.leaving
                label: "a"
                chat: ({ state: "working" })
                homeX: 200
                onGone: root.removePet()
            }
        }
    }
}
""")
            script = (
                "import sys\n"
                "from PySide6.QtCore import QUrl, QTimer\n"
                "from PySide6.QtGui import QGuiApplication\n"
                "from PySide6.QtQuick import QQuickView\n"
                "app = QGuiApplication(sys.argv)\n"
                "view = QQuickView()\n"
                "view.engine().quit.connect(app.quit)\n"
                "view.setSource(QUrl.fromLocalFile(sys.argv[1]))\n"
                "view.show()\n"
                "QTimer.singleShot(15000, app.quit)\n"
                "app.exec()\n"
                "print(view.rootObject().property('removed'))\n")
            out = subprocess.run(["python3", "-c", script, str(stage)], capture_output=True, text=True, timeout=60,
                                 env=dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software",
                                          QT_FORCE_STDERR_LOGGING="1"))
        self.assertEqual(out.stdout.split()[-1:], ["1"], out.stderr[-2000:])
        self.assertNotIn("invalid context", out.stderr)
        self.assertNotRegex(out.stderr, r"TalpyView\.qml:\d+: TypeError")
