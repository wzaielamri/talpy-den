"""Playful Talpy (a setting, on by default): off, Talpy only shows what the
chats do: his moods, his lamp and quiet moves (looking around, typing,
thinking, sleeping); no prop tricks (balloon, plane, selfie, music…), no joke
bubbles, no cookie, no games. Notifications and badges stay as they are."""
import json
import re
import unittest
from pathlib import Path

from test_pets import run_node

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "package/contents/ui"
PROPS = {"balloon", "plane", "selfie", "music", "coffee", "gum", "bubbles", "flower", "snack", "juggle", "telescope",
         "butterfly", "sneeze", "hiccups", "boogie", "bunnyhop", "blowkiss", "dream", "stargaze", "firefly", "phone", "letter"}


class CoreTests(unittest.TestCase):
    def test_off_it_picks_only_calm_moves_in_every_mood(self):
        picked = run_node("""
const out = {};
for (const mood of Object.keys(MOODS)) {
    const t = new Talpy({ playful: false, travels: true });
    t.onTravel = () => {};
    t.setMood(mood);
    const seen = new Set();
    for (let i = 0; i < 300; i++) {
        t.cancel();
        t.lastAuto = '';
        t.think();
        if (t.run) seen.add(t.run.name);
    }
    out[mood] = [...seen];
}
console.log(JSON.stringify(out));
""")
        for mood, names in picked.items():
            with self.subTest(mood):
                self.assertTrue(names)
                self.assertEqual(set(names) & PROPS, set())
        self.assertEqual(set(picked["idle"]) - {"lookaround", "duck", "nap", "dig"}, set())
        self.assertEqual(set(picked["working"]) - {"typing", "thinking", "read"}, set())
        self.assertEqual(set(picked["done"]) - {"sleep", "nap"}, set())

    def test_on_it_still_has_its_tricks(self):
        picked = run_node("""
const t = new Talpy({ travels: true });
t.onTravel = () => {};
const seen = new Set();
for (let i = 0; i < 400; i++) { t.cancel(); t.lastAuto = ''; t.think(); if (t.run) seen.add(t.run.name); }
console.log(JSON.stringify([...seen]));
""")
        self.assertTrue(set(picked) & PROPS)

    def test_turned_off_a_trick_under_way_stops_and_a_calm_one_goes_on(self):
        out = run_node("""
const t = new Talpy({});
t.tick(1000);
t.play('balloon', null, true);
const before = t.run && t.run.name;
t.setPlayful(false);
const trick = t.run ? t.run.name : null;
t.setPlayful(true);
t.play('lookaround', null, true);
t.setPlayful(false);
console.log(JSON.stringify([before, trick, t.run ? t.run.name : null, t.playful]));
""")
        self.assertEqual(out, ["balloon", None, "lookaround", False])


class HostTests(unittest.TestCase):
    def test_plasma_has_the_setting_shared_and_a_ticked_menu_item(self):
        xml = (ROOT / "package/contents/config/main.xml").read_text()
        self.assertRegex(xml, r'<entry name="playful" type="Bool">[\s\S]*?<default>true</default>')
        main = (UI / "main.qml").read_text()
        self.assertIn('"showPet", "playful"', main)                       # (every copy of the widget alike)
        action = main[main.index('text: i18n("Playful Talpy")') - 200:]
        self.assertIn("checkable: true", action[:600])
        self.assertIn("checked: Plasmoid.configuration.playful", action[:600])
        self.assertIn("cfg_playful: playful.checked", (UI / "configGeneral.qml").read_text())

    def test_plasma_pets_drop_jokes_greetings_and_the_cookie(self):
        pet = (UI / "Pet.qml").read_text()
        line = pet[pet.index("function petLine()"):pet.index("function event(")]
        self.assertLess(line.index("Busy coding"), line.index("if (!root.playful)"))   # (what the chats do stays)
        self.assertLess(line.index("if (!root.playful)"), line.index("Ship it!"))
        self.assertRegex(pet, r"function placeCookie\(x, y\) \{\n\s+if \(!root\.playful \|\|")      # no cookie
        self.assertRegex(pet, r"onLiveChanged: \{\n\s+if \([^{]*\|\| !root\.playful\)")   # no Hi! or holiday
        view = (UI / "TalpyView.qml").read_text()
        self.assertIn("playful: root.playful", view)
        self.assertIn("view.talpy.setPlayful(root.playful)", view)

    def test_vscode_has_the_setting_and_its_menu_says_what_a_click_does(self):
        pkg = json.loads((ROOT / "vscode/package.json").read_text())
        props = pkg["contributes"]["configuration"]
        props = props if isinstance(props, dict) else {k: v for c in props for k, v in c["properties"].items()}
        props = props.get("properties", props)
        self.assertEqual(props["talpyDen.playfulTalpy"]["default"], True)
        menus = {m["command"]: m["when"] for m in pkg["contributes"]["menus"]["view/title"]}
        self.assertIn("&& config.talpyDen.playfulTalpy", menus["talpyDen.playfulOff"])
        self.assertIn("&& !config.talpyDen.playfulTalpy", menus["talpyDen.playfulOn"])
        pet = (ROOT / "vscode/webview/pets/pet.ts").read_text()
        self.assertIn("playful: world.playful", pet)
        self.assertIn("if (!world.playful) return \"\"", pet)
        self.assertRegex(pet, r"placeCookie\(x: number, y: number\): boolean \{\n\s+if \(!world\.playful \|\|")

    def test_gnome_has_the_setting(self):
        schema = (ROOT / "gnome/extension/schemas/org.gnome.shell.extensions.talpy-den.gschema.xml").read_text()
        self.assertRegex(schema, r'<key name="playful-talpy" type="b">\s*<default>true</default>')
        self.assertIn("'playful-talpy'", (ROOT / "gnome/extension/prefs.js").read_text())
        pets = (ROOT / "gnome/extension/ui/pets.js").read_text()
        self.assertIn("playful: stage.pets.playful", pets)
        # no Hi! or holiday greeting when it's off (the setting is the director's: a stage has none of its own)
        greet = pets[pets.index("    _greet() {"):]
        self.assertIn("!this.pets.playful)", greet[:greet.index("\n    }\n")])
        self.assertIn("changed::playful-talpy", (ROOT / "gnome/extension/indicator.js").read_text())


if __name__ == "__main__":
    unittest.main()
