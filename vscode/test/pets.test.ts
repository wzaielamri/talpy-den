// The pets (webview/pets) are DOM code. Their sources are bundled here and run
// in a fresh vm context (one per test) with just enough of a fake DOM: the
// observers are triggered by hand, timers and tweens are fired and stepped by
// hand, nothing waits.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import * as path from "node:path";
import { test } from "node:test";
import * as vm from "node:vm";

type Any = any; // (the pets' private parts are reached at run time)

const repo = path.resolve(__dirname, "..", "..");
let bundled = "";

function bundle(): string {
  if (!bundled) {
    const { buildSync } = createRequire(__filename)("esbuild") as Any; // (not bundled into this test)
    bundled = buildSync({
      stdin: {
        contents: 'export { Stage, setDarkAll, setPlayfulAll } from "./webview/pets/stage";\nexport { petFields, stageCallbacks } from "./webview/util/petStage";\n' +
          'export { ACTIONS, MOODS } from "./vendor/talpy/actions.mjs";\nexport { Spring } from "./webview/pets/motion";\n',
        resolveDir: repo,
        loader: "ts",
      },
      bundle: true,
      write: false,
      format: "cjs",
      platform: "browser",
      target: "es2022",
      logLevel: "silent",
    }).outputFiles[0].text;
  }
  return bundled;
}

class FakeEl {
  children: FakeEl[] = [];
  parent: FakeEl | null = null;
  style: Record<string, unknown> = { setProperty() {} };
  dataset: Record<string, string> = {};
  attrs: Record<string, string> = {};
  classes = new Set<string>();
  classList = {
    toggle: (c: string, on?: boolean) => void ((on ?? !this.classes.has(c)) ? this.classes.add(c) : this.classes.delete(c)),
    add: (c: string) => void this.classes.add(c),
    contains: (c: string) => this.classes.has(c),
  };
  adoptedStyleSheets: unknown[] = [];
  hidden = false;
  textContent = "";
  className = "";
  title = "";
  tabIndex = 0;
  offsetWidth = 40;
  offsetHeight = 16;
  constructor(readonly tag: string) {}
  get childElementCount(): number {
    return this.children.length;
  }
  append(...nodes: FakeEl[]): void {
    for (const n of nodes) {
      n.parent = this;
      this.children.push(n);
    }
  }
  remove(): void {
    if (this.parent) this.parent.children = this.parent.children.filter((c) => c !== this);
    this.parent = null;
  }
  after(...nodes: FakeEl[]): void {
    const parent = this.parent;
    if (!parent) return;
    const at = parent.children.indexOf(this) + 1;
    for (const n of nodes) n.parent = parent;
    parent.children.splice(at, 0, ...nodes);
  }
  replaceChildren(...nodes: FakeEl[]): void {
    this.children = [];
    this.append(...nodes);
  }
  setAttribute(k: string, v: string): void {
    this.attrs[k] = v;
  }
  removeAttribute(k: string): void {
    delete this.attrs[k];
  }
  listeners: Record<string, (() => void)[]> = {};
  addEventListener(kind: string, fn: () => void): void {
    (this.listeners[kind] ??= []).push(fn);
  }
  setPointerCapture(): void {}
  getBoundingClientRect() {
    return { left: 0, top: 0, width: 400, height: 80 };
  }
  width = 300;
  height = 150;
  drawn: string[] = []; // a canvas: what was drawn on it
  getContext() {
    const drawn = this.drawn;
    // A 2D context that takes every call (and a gradient's color stops)
    return new Proxy({} as Record<string | symbol, unknown>, {
      get: (target, k) => (k in target ? target[k] : (...args: unknown[]) => {
        drawn.push(String(k));
        void args;
        return { addColorStop() {} };
      }),
      set: (target, k, v) => ((target[k] = v), true),
    });
  }
}

// A page with the pets' code loaded; a stage made in it is the only one, so its
// observers are the first (and only) ones
function load() {
  const resize: ((entries: unknown[]) => void)[] = [];
  const intersect: ((entries: unknown[]) => void)[] = [];
  const frames = { asked: 0 };
  const posted: Any[] = [];
  const css = { color: "rgb(204, 204, 204)" }; // the theme's text color
  const micro = { queued: 0 }; // (more than 1000 in a row: endless, the page would hang)
  const sandbox: Record<string, unknown> = {
    document: {
      createElement: (tag: string) => new FakeEl(tag),
      addEventListener() {},
      removeEventListener() {},
      visibilityState: "visible",
      body: new FakeEl("body"),
    },
    window: { TALPY_DEN: { editorTab: false }, addEventListener() {} },
    acquireVsCodeApi: () => ({ postMessage: (m: unknown) => void posted.push(m), getState: () => undefined, setState() {} }),
    ResizeObserver: class {
      constructor(cb: (entries: unknown[]) => void) {
        resize.push(cb);
      }
      observe() {}
      disconnect() {}
    },
    IntersectionObserver: class {
      constructor(cb: (entries: unknown[]) => void) {
        intersect.push(cb);
      }
      observe() {}
      disconnect() {}
    },
    requestAnimationFrame: () => ++frames.asked,
    cancelAnimationFrame() {},
    getComputedStyle: () => ({ getPropertyValue: () => "", color: css.color }),
    devicePixelRatio: 2,
    queueMicrotask: (fn: () => void) => {
      if (++micro.queued <= 1000) queueMicrotask(fn);
    },
    performance,
    setTimeout: (fn: () => void, ms: number) => {
      const handle = setTimeout(fn, ms);
      handle.unref();
      return handle;
    },
    clearTimeout,
    module: { exports: {} },
  };
  vm.runInNewContext(bundle(), sandbox);
  const exports = (sandbox.module as { exports: Any }).exports;
  return {
    Stage: exports.Stage as Any, petFields: exports.petFields as Any, ACTIONS: exports.ACTIONS as Any,
    MOODS: exports.MOODS as Any, stageCallbacks: exports.stageCallbacks as Any, resize, intersect, frames, posted,
    setDarkAll: exports.setDarkAll as Any, setPlayfulAll: exports.setPlayfulAll as Any, css, Spring: exports.Spring as Any, micro,
  };
}

function chat(key: string, state = "working", extra: Record<string, unknown> = {}) {
  const [profileDir, chatId] = key.split("/");
  const session = {
    key, chatId, sessionId: `s-${chatId}`, profileDir, name: `chat ${chatId}`, state, reason: "", since: 1,
    context: null, agents: null, stopped: null, ...extra,
  };
  return { key, session };
}

// An account's stage with room for maxPets pets, still unseen until show()
function account(maxPets = 3) {
  const t = load();
  const counts: number[] = []; // what it told the UI of its pets
  const stage: Any = new t.Stage(new FakeEl("div"), false, "account:test", { open() {}, petsChanged: (n: number) => counts.push(n) });
  return {
    stage,
    counts,
    t,
    frames: t.frames,
    lay: (width = 400) => t.resize[0]([{ contentRect: { width, height: 80 } }]),
    show: (on = true) => t.intersect[0]([{ isIntersecting: on }]),
    // (in the order of the account's list)
    give: (chats: Any[]) => stage.update({ chats: chats.map((c, i) => ({ order: i, ...c })), maxPets, fiveHour: 0 }),
  };
}

// Talpy's time goes on by ms (it ticks every 50 ms, as on a stage in view)
function wait(pet: Any, ms: number) {
  const from = pet.talpy.now;
  for (let t = from + 50; t <= from + ms; t += 50) pet.talpy.tick(t);
}

// A chat's pet on a stage in view, up out of the ground, whose chat has just
// left the list
function leaving() {
  const s = account();
  s.give([chat("p/1")]);
  s.lay();
  s.show();
  const pet = s.stage.petFor("p/1");
  wait(pet, 3000);
  s.give([]);
  assert.equal(pet.leaving, true);
  return { ...s, pet };
}

test("the pets are told when a usage limit has reset", () => {
  // They get a chat's row only when what they show of it changed (petFields):
  // the limit's end changes nothing else, and the chat's pet went on waiting
  // for it (out of steam) with a tooltip that said "resets in <1m"
  const { petFields } = load();
  const rows = (over: boolean) =>
    JSON.stringify({ chats: [chat("p/1", "idle", { stopped: { kind: "limit", over, resetsAt: 5 } })] }, petFields);
  assert.notEqual(rows(false), rows(true));
  assert.notEqual(rows(false), JSON.stringify({ chats: [chat("p/1", "idle")] }, petFields));
});

test("a click on a pet goes to its chat's window; only the chat's name opens its tab", () => {
  // (as on Plasma: the pets jump to the terminal or Claude Code panel, whatever
  // talpyDen.clickOpensPane says about the name)
  const { stageCallbacks, posted } = load();
  const ref = { key: "p/1", sessionId: "s-1", profileDir: "p", name: "chat 1" };
  stageCallbacks.open(ref);
  assert.equal(posted.length, 1);
  assert.equal(posted[0].type, "openWindow");
  assert.equal(posted[0].chat, ref);
});

test("every mood and action a pet asks Talpy for is one it knows", () => {
  const { ACTIONS, MOODS } = load();
  for (const mood of ["error", "loading", "needs", "agents", "working", "idle", "done", "failed", "limit"])
    assert.ok(mood in MOODS, mood);
  // what the pets react with: react("…"), the events' actions and the usage limit's
  const source = readFileSync(path.join(repo, "webview", "pets", "pet.ts"), "utf8");
  const reacts = [...source.matchAll(/react\(([^;]*)\);/g)].map((m) => m[1]);
  const events = /\{ done: [^}]*\}/.exec(source)![0];
  const names = new Set([...reacts, events].flatMap((s) => [...s.matchAll(/"(\w+)"/g)].map((m) => m[1])));
  assert.ok(names.has("dig") && names.has("charged") && names.has("mindblown"), [...names].join(" "));
  for (const name of names) assert.ok(name in ACTIONS, `Talpy has no "${name}"`);
});

test("a pet on a stage in view draws itself, the canvas as sharp as the screen", () => {
  const { stage, lay, show, give } = account();
  give([chat("p/1")]);
  lay();
  show();
  stage.render();
  const pet = stage.petFor("p/1");
  const canvas = pet.view; // (the picture is drawn on a sheet off the page, then shown on it)
  assert.equal(canvas.width, Math.round(stage.canvasW * 2)); // devicePixelRatio 2
  assert.ok(pet.canvases.some((c: Any) => c.drawn.includes("fill")), "nothing drawn");
  assert.ok(canvas.drawn.includes("drawImage"), "not shown");
  assert.equal(pet.canvases.find(Boolean).width, canvas.width); // (sheets are made as they are needed)
  assert.equal(canvas.style.width, `${stage.canvasW}px`);
  stage.destroy();
});

test("a chat's pet draws a picture only when what it shows changes", async () => {
  const { stage, lay, show, give } = account();
  give([chat("p/1", "done")]); // asleep: its picture changes now and then
  lay();
  show();
  const pet = stage.petFor("p/1");
  // up out of the ground (drawn live: a big move), 3 s on the stage's own
  // clock, which Talpy's must follow
  const clock = stage.clock as Any;
  for (let i = 0; i < 60; i++) {
    clock.base += 50;
    pet.talpy.tick(clock.now());
  }
  const drawn = () => pet.canvases.reduce((n: number, c: Any) => n + c.drawn.length, 0);
  const fadeOver = () => new Promise((done) => setTimeout(done, 260)); // (the stage's clock is real time)
  stage.render(); // its first picture, fading in
  await fadeOver();
  stage.render();
  const before = drawn();
  stage.render(); // nothing new to show
  assert.equal(drawn(), before, "drawn again without a change");
  const key = pet.talpy.stillKey();
  pet.talpy.react("pet"); // a new pose
  assert.notEqual(pet.talpy.stillKey(), key);
  stage.render();
  assert.ok(drawn() > before, "the new pose isn't drawn");
  stage.destroy();
});

test("a stage in view with pets keeps drawing them; a hidden one asks for no frames", () => {
  const { stage, frames, lay, show, give } = account();
  give([chat("p/1")]);
  lay();
  assert.equal(frames.asked, 0, "frames for a stage nobody sees");
  show();
  assert.equal(frames.asked, 1);
  stage.loop(); // a frame: nothing walks, but Talpy is always up to something
  assert.equal(frames.asked, 2);
  show(false);
  stage.loop();
  assert.equal(frames.asked, 2);
  stage.destroy();
});

test("a stage hidden while Talpy goes after a cookie draws him once and lets the page go on", async () => {
  const t = load();
  const stage: Any = new t.Stage(new FakeEl("div"), true, "hero", { open() {} });
  t.resize[0]([{ contentRect: { width: 400, height: 96 } }]);
  t.intersect[0]([{ isIntersecting: true }]);
  stage.update({
    mood: "idle", headline: "", counts: { waiting: 0, working: 0, idle: 1, limit: 0, done: 0 }, highUsageText: "",
    contextFullText: "", maxFiveHour: 0, agentsRunning: 0, waiting: null,
  });
  assert.ok(stage.pets[0].placeCookie(40, 30));
  stage.loop();
  await new Promise((done) => setTimeout(done, 0));
  t.micro.queued = 0;
  t.intersect[0]([{ isIntersecting: false }]); // the sidebar switched to Explorer
  await new Promise((done) => setTimeout(done, 20));
  assert.equal(t.micro.queued, 1, "it keeps drawing itself while hidden");
  stage.destroy();
});

// A drag that starts downward (within 45°) while he's in his burrow pushes him
// in, drawn live meanwhile: he hangs on and sinks a little, and says so; let
// go, he's on his way back; back up past where you began, or sideways, is the
// tug, up from where he was pushed to
test("a drag that starts downward pushes the hero into his burrow; up or sideways pulls him", () => {
  const t = load();
  const stage: Any = new t.Stage(new FakeEl("div"), true, "hero", { open() {} });
  t.resize[0]([{ contentRect: { width: 400, height: 96 } }]);
  t.intersect[0]([{ isIntersecting: true }]);
  stage.update({
    mood: "idle", headline: "", counts: { waiting: 0, working: 0, idle: 1, limit: 0, done: 0 }, highUsageText: "",
    contextFullText: "", maxFiveHour: 0, agentsRunning: 0, waiting: null,
  });
  const hero = stage.pets[0];
  hero.talpy.brainOn = false; // (no trick of his own between the drags)
  const g = hero.grab;
  const said: string[] = [];
  hero.say = (text: string) => void said.push(text);
  const at = (x: number, y: number) => ({ button: 0, pointerId: 1, clientX: x, clientY: y, preventDefault() {} });
  const settle = () => {
    for (let i = 0; i < 30; i++) hero.talpy.tick(hero.talpy.now + 16);
  };
  const from = hero.talpy.v.depth;
  g.listeners.pointerdown[0](at(100, 40));
  g.listeners.pointermove[0](at(106, 60)); // down, a little to the right
  assert.equal(hero.pushing, true);
  assert.equal(hero.held, false);
  assert.ok(["Hey!", "Nooo!", "No pushing!"].includes(said[0]), "he says so");
  settle();
  assert.ok(hero.talpy.v.depth > from, "it sinks as your hand goes");
  stage.loop();
  assert.equal(hero.film.on, false); // (drawn live while pushed)
  g.listeners.pointermove[0](at(106, 90));
  settle();
  const deeper = hero.talpy.v.depth;
  assert.ok(deeper > from + 2 && deeper < from + 50 / (stage.box / 64), "it hangs on: less than your hand went");
  g.listeners.pointerup[0](at(106, 90));
  assert.equal(hero.pushing, false);
  assert.equal(hero.talpy.pushing, false);
  assert.ok(hero.talpy.run, "it's on its way back up");
  assert.equal(said[said.length - 1], "Hmpf!"); // (it sprang back: it hadn't given in)
  hero.talpy.cancel();
  hero.talpy.apply({});
  settle();
  // pushed on far enough, it gives in
  g.listeners.pointerdown[0](at(100, 20));
  g.listeners.pointermove[0](at(100, 30));
  g.listeners.pointermove[0](at(100, 20 + 70 * (stage.box / 64)));
  assert.equal(hero.talpy.gaveIn, true);
  assert.equal(said[said.length - 1], "Okay, okay!");
  // then back up past where you began: pulled out after all, from down there
  g.listeners.pointermove[0](at(100, 10));
  assert.equal(hero.pushing, false);
  assert.equal(hero.talpy.pushing, false);
  assert.ok(hero.tugging, "the tug, up from where it was");
  g.listeners.pointerup[0](at(100, 10));
  hero.talpy.cancel();
  hero.talpy.apply({});
  settle();
  g.listeners.pointerdown[0](at(100, 40));
  g.listeners.pointermove[0](at(130, 45)); // sideways: the tug, as before
  assert.equal(hero.pushing, false);
  assert.ok(hero.tugging || hero.held);
  g.listeners.pointerup[0](at(130, 45));
  stage.destroy();
});

// Pulled at (back up past where you began), then back down past it before he
// came out: pushed in again, from where he is, as one move (the tug's end
// takes nothing); held down a second, as long as a tug takes, he gives in
test("a drag down, up, then down again before he comes out pushes the hero again", () => {
  const t = load();
  const stage: Any = new t.Stage(new FakeEl("div"), true, "hero", { open() {} });
  t.resize[0]([{ contentRect: { width: 400, height: 96 } }]);
  t.intersect[0]([{ isIntersecting: true }]);
  stage.update({
    mood: "idle", headline: "", counts: { waiting: 0, working: 0, idle: 1, limit: 0, done: 0 }, highUsageText: "",
    contextFullText: "", maxFiveHour: 0, agentsRunning: 0, waiting: null,
  });
  const hero = stage.pets[0];
  hero.talpy.brainOn = false;
  const g = hero.grab;
  const said: string[] = [];
  hero.say = (text: string) => void said.push(text);
  const at = (x: number, y: number) => ({ button: 0, pointerId: 1, clientX: x, clientY: y, preventDefault() {} });
  const tick = (ms: number) => {
    for (let i = 0; i < ms / 16; i++) hero.talpy.tick(hero.talpy.now + 16);
  };
  tick(500);
  g.listeners.pointerdown[0](at(100, 40));
  g.listeners.pointermove[0](at(102, 60)); // down: pushed
  assert.equal(hero.pushing, true);
  tick(200);
  g.listeners.pointermove[0](at(100, 20)); // back up past where you began: the tug
  assert.equal(hero.pushing, false);
  assert.equal(hero.tugging, true);
  assert.equal(said[said.length - 1], "Hnngh!");
  tick(300);
  g.listeners.pointermove[0](at(101, 40 + stage.gu * 0.3)); // (down, but not past where you began by much: still the tug)
  assert.equal(hero.tugging, true);
  const depth = hero.talpy.v.depth;
  g.listeners.pointermove[0](at(101, 60)); // down again: pushed, from where he is
  assert.equal(hero.tugging, false);
  assert.equal(hero.pushing, true);
  assert.equal(hero.talpy.tugging, false);
  assert.equal(hero.talpy.pushing, true);
  assert.ok(Math.abs(hero.talpy.pushFrom - depth) < 0.01, "from where he was pulled up to");
  assert.ok(["Hey!", "Nooo!", "No pushing!"].includes(said[said.length - 1]), "he says so");
  tick(1100); // the tug's second is long gone: no popping out into your hand
  assert.equal(hero.held, false);
  assert.equal(hero.talpy.gaveIn, true, "held down a second, he gives in");
  assert.equal(said[said.length - 1], "Okay, okay!");
  g.listeners.pointerup[0](at(101, 60));
  assert.equal(hero.pushing, false);
  assert.ok(hero.talpy.run, "down a moment, then he peeks out");
  stage.destroy();
});

// A game with the hero (vendor/talpy/games.mjs): its three holes drawn under
// him only while it's on; over at once when the stage hides or a chat needs you
test("a game's holes show while it's on; the stage hidden or a chat that needs you ends it", () => {
  const t = load();
  const stage: Any = new t.Stage(new FakeEl("div"), true, "hero", { open() {} });
  t.resize[0]([{ contentRect: { width: 400, height: 96 } }]);
  t.intersect[0]([{ isIntersecting: true }]);
  const input = (mood: string) => ({
    mood, headline: "", counts: { waiting: mood === "needs" ? 1 : 0, working: 0, idle: 1, limit: 0, done: 0 }, highUsageText: "",
    contextFullText: "", maxFiveHour: 0, agentsRunning: 0, waiting: null,
  });
  stage.update(input("idle"));
  const hero = stage.pets[0];
  hero.startGame();
  assert.equal(hero.play.on, true);
  stage.loop();
  assert.equal(hero.playHoles.length, 3);
  assert.ok(hero.playHoles.every((c: Any) => !c.hidden));
  assert.equal(hero.talpy.brainOn, false); // (nothing of his own meanwhile)
  t.intersect[0]([{ isIntersecting: false }]); // out of sight: over
  assert.equal(hero.play.on, false);
  assert.equal(hero.talpy.brainOn, true);
  t.intersect[0]([{ isIntersecting: true }]);
  stage.loop(); // (seen again: no holes left over)
  assert.ok(hero.playHoles.every((c: Any) => c.hidden));
  hero.startGame();
  assert.equal(hero.play.on, true);
  stage.update(input("needs")); // a chat needs you: over, and he shows his sign
  assert.equal(hero.play.on, false);
  assert.equal(hero.talpy.run?.name, "sign");
  hero.startGame(); // (not while a chat needs you)
  assert.equal(hero.play.on, false);
  stage.destroy();
});

// Playful Talpy off: no cookie, no joke bubbles; the pets' Talpys pick calm moves
test("with Playful Talpy off the hero takes no cookie and tells no jokes", () => {
  const t = load();
  const stage: Any = new t.Stage(new FakeEl("div"), true, "hero", { open() {} });
  t.resize[0]([{ contentRect: { width: 400, height: 96 } }]);
  t.intersect[0]([{ isIntersecting: true }]);
  stage.update({
    mood: "idle", headline: "", counts: { waiting: 0, working: 0, idle: 1, limit: 0, done: 0 }, highUsageText: "",
    contextFullText: "", maxFiveHour: 0, agentsRunning: 0, waiting: null,
  });
  t.setPlayfulAll(false);
  const hero = stage.pets[0];
  assert.equal(hero.talpy.playful, false);
  assert.equal(hero.placeCookie(40, 30), false);
  assert.equal(hero.petLine(), "");
  t.setPlayfulAll(true);
  assert.equal(hero.talpy.playful, true);
  assert.ok(hero.placeCookie(40, 30));
  stage.loop();
  assert.equal(hero.cookie.hidden, false);
  // turned off with a cookie out: it vanishes in a puff where it was, and the
  // game ends once the puff has gone
  const { x, y } = hero.game.cookie;
  t.setPlayfulAll(false);
  assert.equal(hero.game.cookie, null);
  assert.ok(hero.game.puff, "a puff where it was");
  assert.deepEqual([hero.game.puff.x, hero.game.puff.y], [x, y]);
  assert.equal(hero.game.state, "");
  stage.loop();
  assert.equal(hero.cookie.hidden, true);
  assert.equal(hero.puff.hidden, false);
  for (let i = 0; i < 40; i++) hero.game.tick(hero.game.now + 16);
  assert.equal(hero.game.puff, null);
  assert.equal(hero.game.on, false);
  stage.loop();
  assert.equal(hero.puff.hidden, true);
  stage.destroy();
});

test("a pet whose chat left waves, digs away and is gone", () => {
  const { stage, pet } = leaving();
  assert.equal(pet.talpy.run.name, "leave");
  wait(pet, 6000);
  assert.ok(!stage.pets.includes(pet), "it stayed");
  stage.destroy();
});

test("news of a chat that left doesn't keep its pet on the stage", () => {
  const { stage, pet } = leaving();
  stage.petEvent("done", "Done!", "p/1"); // (a reaction would stop it digging away)
  wait(pet, 6000);
  assert.ok(!stage.pets.includes(pet), "it stayed");
  stage.destroy();
});

test("a pet you grab on its way off the stage is held, not removed", () => {
  const { stage, pet } = leaving();
  wait(pet, 300); // waving
  pet.pickUp();
  wait(pet, 6000);
  assert.ok(stage.pets.includes(pet), "the pet vanished under the pointer");
  assert.equal(pet.held, true);
  assert.equal(pet.talpy.held, true);
  stage.destroy();
});

test("a held pet whose chat left stays in your hand and goes once it is put down", () => {
  const s = account();
  s.give([chat("p/1")]);
  s.lay();
  s.show();
  const pet = s.stage.petFor("p/1");
  wait(pet, 3000);
  pet.pickUp();
  s.give([]); // its chat left
  wait(pet, 6000);
  assert.ok(s.stage.pets.includes(pet), "it left your hand");
  pet.lift = s.stage.gu * 2;
  pet.drop();
  pet.faller.step(1e15); // the fall is over: landed
  assert.equal(pet.held, false);
  assert.ok(s.stage.pets.includes(pet), "gone before it got its bearings");
  wait(pet, 10000); // it lands, then digs away
  assert.ok(!s.stage.pets.includes(pet), "nothing sends it off once it is put down");
  s.stage.destroy();
});

test("a pet grabbed again while it gets its bearings stays in your hand, whose chat left meanwhile too", () => {
  const s = account();
  s.give([chat("p/1")]);
  s.lay();
  s.show();
  const pet = s.stage.petFor("p/1");
  wait(pet, 3000);
  pet.pickUp();
  s.give([]); // its chat left
  pet.lift = s.stage.gu * 6;
  pet.drop();
  pet.faller.step(1e15); // landed, dizzy
  wait(pet, 400);
  pet.pickUp(); // grabbed again before it was done
  assert.equal(pet.landing, true);
  wait(pet, 6000);
  assert.ok(s.stage.pets.includes(pet), "it waved and sank out of your hand");
  assert.equal(pet.talpy.held, true);
  s.stage.destroy();
});

test("the hole stays where a pet was pulled out of it, and is filled in once the pet has landed", () => {
  // The hole shrank within 350 ms while it followed the pet you pulled out of
  // it, as if carried along (2026-10-26)
  const s = account();
  s.give([chat("p/1")]);
  s.lay();
  s.show();
  const pet = s.stage.petFor("p/1");
  wait(pet, 4000); // up out of the ground, its hole open
  assert.ok(pet.talpy.v.hole > 0.9, "no hole to leave");
  assert.equal(pet.leftHole.hidden, true);
  const home = pet.px;
  pet.pickUp();
  assert.equal(pet.leftHole.hidden, false, "its hole didn't stay");
  assert.equal(pet.talpy.v.hole, 0, "its hole came along");
  s.stage.render();
  const placed = pet.leftHole.style.transform;
  assert.ok(placed.startsWith(`translate(${Math.round(home * 10) / 10 - s.stage.canvasW / 2}px,`), `${placed}, it was at ${home}`);
  assert.ok(pet.leftHole.drawn.length > 0, "the hole isn't drawn");
  pet.px = home + s.stage.gu * 6; // carried off
  pet.lift = s.stage.gu * 2;
  wait(pet, 400);
  s.stage.render();
  assert.equal(pet.leftHole.style.transform, placed, "the hole went along");
  assert.equal(pet.leftHole.hidden, false);
  pet.drop();
  pet.faller.step(1e15); // landed
  assert.equal(pet.fill.active, true, "the old hole isn't filled in");
  pet.fill.step(1e15);
  assert.equal(pet.leftHole.hidden, true);
  s.stage.destroy();
});

test("a pet that wasn't over a hole leaves none behind", () => {
  const s = account();
  s.give([chat("p/1")]);
  s.lay();
  s.show();
  const pet = s.stage.petFor("p/1");
  wait(pet, 4000);
  pet.talpy.react("dig"); // tunnelling: no hole under it
  wait(pet, 1200);
  pet.pickUp();
  assert.equal(pet.leftHole.hidden, true, "a hole from nowhere");
  s.stage.destroy();
});

test("while you hold a pet nothing moves it", () => {
  const { stage, pet, give } = leaving();
  pet.pickUp();
  pet.px = 200; // dragged away from its spot
  give([chat("p/1")]); // its chat came back: it would pop up again
  assert.equal(pet.leaving, false);
  const spot = pet.homeX;
  give([chat("p/1"), chat("p/2"), chat("p/3")]); // the row is spaced anew
  assert.notEqual(pet.homeX, spot);
  stage.petEvent("done", "Done!", "p/1");
  wait(pet, 6000);
  assert.equal(pet.stride.active, false, "it digs home while you hold it");
  assert.equal(pet.px, 200);
  assert.equal(pet.talpy.held, true);
  assert.equal(pet.talpy.run, null, "it acts while you hold it");
  stage.destroy();
});

test("a spring steps as Qt's SpringAnimation does, as the widget's swing (values from Qt 6.11)", () => {
  const { Spring } = load();
  const swing = new Spring(3, 0.16, 0.3);
  swing.aim(30, 1000);
  swing.step(1015);
  assert.equal(swing.value, 0, "a step before 16 ms");
  const seen: number[] = [];
  for (let t = 1016; swing.moving; t += 16) {
    swing.step(t);
    seen.push(swing.value);
  }
  const near = (a: number, b: number) => Math.abs(a - b) < 1e-9;
  assert.ok(near(seen[0], 1.44) && near(seen[1], 4.02048) && near(seen[3], 11.38649628672), String(seen.slice(0, 4)));
  assert.ok(near(Math.max(...seen), 38.27449633860427), "its overshoot");
  assert.ok(near(seen[57], 29.83079908030854));
  assert.equal(seen.length, 59, "at rest after 944 ms");
  assert.equal(swing.value, 30, "exactly there");
  // (the time left over is kept for the next step; a new target keeps its speed)
  const shown = new Spring(5, 0.32, 0.2);
  shown.aim(10, 0);
  shown.step(40);
  const twice = shown.value;
  shown.step(48);
  assert.ok(shown.value > twice, "the 8 ms left over and 8 more make a step");
  shown.aim(-10, 50);
  shown.step(64);
  assert.ok(shown.value > twice, "a new target stopped it");
});

// A chat's pet on a stage in view, up out of the ground, and a frame every 16 ms
function framed() {
  const s = account();
  s.give([chat("p/1")]);
  s.lay();
  s.show();
  const pet = s.stage.petFor("p/1");
  wait(pet, 3000);
  const clock = s.stage.clock as Any;
  const frame = () => {
    clock.base += 16;
    pet.faller.step(clock.base);
    pet.render();
  };
  const angle = () => Number(/rotate\((-?[\d.]+)deg\)/.exec(String(pet.sheets.style.transform))?.[1] ?? 0);
  frame();
  return { ...s, pet, frame, angle };
}

// The widget's pet in Qt 6.11, pulled right 4 units a frame for 37 frames, then
// held still: drawn 0.32 and swung 0.35° after the first frame, 1.15 and 1.28°
// after the second; swung to 37.7°, waited at 28.2° until it was drawn where
// the hand is, back to −7.7°, then 2.1°, and at rest 1.49 s after the hand stopped
test("a pet you hold trails your hand on a spring and swings, then wobbles back as in the widget", () => {
  const { stage, pet, frame, angle } = framed();
  const unit = stage.box / 64;
  pet.pickUp();
  const from = pet.px;
  let most = 0;
  for (let i = 1; i <= 37; i++) {
    pet.px = from + 4 * unit * i;
    frame();
    if (i <= 2) {
      assert.ok(Math.abs((pet.shown.value - from) / unit - [0.32, 1.15][i - 1]) < 0.01, `drawn at ${(pet.shown.value - from) / unit}`);
      assert.equal(angle(), [0.3, 1.3][i - 1]); // (to 0.1°)
    }
    most = Math.max(most, angle());
  }
  let back = 0,
    wait = 0,
    ms = 0;
  for (; ms < 3000 && (pet.shown.moving || pet.tilt.moving); ms += 16) {
    const was = angle();
    frame();
    if (angle() === was && pet.shown.moving) wait = was;
    most = Math.max(most, angle());
    back = Math.min(back, angle());
  }
  assert.equal(pet.shown.value, pet.px, "it never catches up");
  assert.equal(angle(), 0, "it keeps swinging");
  assert.ok(most > 37 && most < 38.3, `it swung to ${most}°`);
  assert.ok(wait > 27 && wait < 29, `it waited at ${wait}°`);
  assert.ok(back > -8.3 && back < -7, `it swung back to ${back}°`);
  assert.ok(ms > 1300 && ms < 1650, `at rest ${ms} ms after the hand stopped`);
  pet.drop();
  for (let i = 0; i < 20; i++) frame();
  assert.equal(pet.held, false);
  assert.equal(angle(), 0);
  assert.equal(pet.shown.value, pet.px);
  stage.destroy();
});

test("a pet put down swinging wobbles back upright on the ground, and its burrow never swings", () => {
  const { stage, pet, frame, angle } = framed();
  pet.pickUp();
  for (let i = 0; i < 12; i++) {
    pet.px += stage.gu * 2; // a fast pull to the right
    frame();
  }
  assert.ok(angle() > 20, `it swings ${angle()}°`);
  pet.drop(); // let go at once: it falls, still swinging
  frame();
  assert.ok(angle() !== 0, "it stopped swinging as it fell");
  let ms = 16;
  for (; pet.held; ms += 16) frame();
  assert.ok(ms <= 500, `it landed after ${ms} ms`);
  // On the ground it swings on, as in the widget, back past upright; land()'s
  // first step (700 ms or more) keeps the burrow shut, and from when it opens
  // the pet stands upright (only a trace of the swing was left)
  let sides = 0, last = Math.sign(angle()), opened = -1;
  for (ms = 0; ms < 1500; ms += 16) {
    const before = angle();
    frame();
    const side = Math.sign(angle());
    if (side && side !== last) {
      sides++;
      last = side;
    }
    if (pet.talpy.holeOpen) {
      if (opened < 0) {
        opened = ms;
        assert.ok(Math.abs(before) < 1, `still ${before}° as the burrow opens`);
      }
      assert.equal(angle(), 0, "its burrow swings");
    }
  }
  assert.ok(opened >= 650, `its burrow opened ${opened} ms after it landed`);
  assert.ok(sides >= 1, "it didn't wobble back on the ground");
  stage.destroy();
});

test("the open hole is drawn once and copied into each picture", () => {
  const { stage, lay, show, give } = account();
  give([chat("p/1")]);
  lay();
  show();
  const pet = stage.petFor("p/1");
  stage.render();
  assert.equal(pet.holes.length, 4); // back and front, turned right and left
  const drawnOnce = pet.holes.map((c: Any) => c.drawn.length);
  assert.ok(drawnOnce.every((n: number) => n > 10));
  assert.equal(pet.talpy.holeImage("front", true), pet.holes[3]);
  const clock = stage.clock as Any;
  for (let i = 0; i < 100; i++) {
    clock.base += 33;
    stage.render();
  }
  assert.deepEqual(pet.holes.map((c: Any) => c.drawn.length), drawnOnce, "the hole was drawn again");
  stage.destroy();
});

test("the open hole is drawn again when the graphics lost its pictures", () => {
  const { stage, lay, show, give } = account();
  give([chat("p/1")]);
  lay();
  show();
  const pet = stage.petFor("p/1");
  stage.render();
  for (const c of pet.holes) c.drawn = []; // (given back blank)
  pet.holes[2].listeners.contextrestored[0]();
  stage.render();
  assert.ok(pet.holes.every((c: Any) => c.drawn.length > 10), "a hole's sheet stays blank");
  assert.equal(pet.talpy.holeImage("front", true), pet.holes[3]);
  stage.destroy();
});

test("a pet dropped away from its spot digs back to it", () => {
  const s = account();
  s.give([chat("p/1")]);
  s.lay();
  s.show();
  const pet = s.stage.petFor("p/1");
  wait(pet, 3000);
  pet.pickUp();
  pet.px = pet.homeX + s.stage.gu * 6;
  pet.drop();
  pet.faller.step(1e15);
  let dug = false;
  for (let i = 0; i < 200 && !dug; i++) {
    wait(pet, 50);
    dug = pet.stride.active;
  }
  assert.ok(dug, "it stays where it was dropped");
  assert.equal(pet.stride.to, pet.homeX);
  s.stage.destroy();
});

test("the pets stand in the order of the list", () => {
  const { stage, lay, show, give } = account();
  lay();
  show();
  // (the chats come with the ones that need you first; the list has them in its own order)
  give([chat("p/2", "waiting", { }), chat("p/1"), chat("p/3", "idle")].map((c, i) => ({ ...c, order: [1, 0, 2][i] })));
  const x = (k: string) => stage.petFor(k).homeX;
  assert.ok(x("p/1") < x("p/2") && x("p/2") < x("p/3"), "not in the list's order");
  stage.destroy();
});

test("a pet whose spot moves hurries over to it", () => {
  const { stage, lay, show, give } = account();
  lay();
  show();
  stage.firstShownTimer.fire();
  give([chat("p/1")]);
  const pet = stage.petFor("p/1");
  wait(pet, 3000); // up out of the ground
  give([chat("p/0"), chat("p/1")]); // a new chat comes first in the list: p/1's spot moves right
  assert.equal(pet.talpy.run?.name, "scoot");
  stage.destroy();
});

test("the other pets wait for a pet that leaves to be gone, then move up", () => {
  // (they tunnelled over it while it still waved and dug away; a chat that
  // was one too many dug up where they stood)
  const { stage, lay, show, give } = account(2);
  lay();
  show();
  stage.firstShownTimer.fire();
  give([chat("p/1"), chat("p/2"), chat("p/3")]);
  const [one, two] = [stage.petFor("p/1"), stage.petFor("p/2")];
  wait(one, 3000);
  wait(two, 3000); // up out of the ground
  const first = one.homeX;
  give([chat("p/2"), chat("p/3")]); // p/1 left: p/3 has a pet's place now
  assert.equal(one.leaving, true);
  assert.notEqual(two.talpy.run?.name, "scoot", "moved over the pet that leaves");
  assert.equal(stage.petFor("p/3"), null, "dug up while the other one left");
  wait(one, 6000); // waved and dug away
  assert.ok(!stage.pets.includes(one));
  assert.equal(two.homeX, first, "p/2 stands first now");
  assert.equal(two.talpy.run?.name, "scoot");
  assert.ok(stage.petFor("p/3"), "p/3's pet came");
  stage.destroy();
});

test("a pet still popping up goes to where its spot is now", () => {
  const { stage, lay, show, give } = account();
  lay(240);
  show();
  stage.firstShownTimer.fire();
  give([chat("p/1")]);
  const first = stage.petFor("p/1");
  assert.equal(first.arriving, true);
  const spot = first.homeX;
  give([chat("p/1"), chat("p/2")]); // the row is spaced anew
  assert.notEqual(first.homeX, spot);
  assert.equal(first.px, first.homeX, "pops up where its spot was");
  stage.destroy();
});

test("news from while the pets were hidden is acted out when they show, if it's from the last minute", () => {
  const { stage, lay, show, give } = account();
  give([chat("p/1", "idle")]);
  lay();
  show();
  const pet = stage.petFor("p/1");
  wait(pet, 3000); // up out of the ground
  show(false);
  stage.petEvent("done", "chat 1 is done!", "p/1");
  assert.equal(stage.bubbleEl.hidden, true, "words nobody sees");
  show();
  assert.equal(stage.bubbleEl.textContent, "chat 1 is done!");
  assert.ok(["yay", "finished"].includes(pet.talpy.run?.name), pet.talpy.run?.name);
  show(false);
  stage.petEvent("failed", "chat 1 failed…", "p/1");
  pet.missed.at -= 61000; // an hour ago, say
  show();
  assert.notEqual(stage.bubbleEl.textContent, "chat 1 failed…", "old news");
  assert.equal(pet.missed, null);
  stage.destroy();
});

test("an account's stage stays open while its last pet waves goodbye", () => {
  // (the UI folds it away once the stage has no pet left, AccountStage)
  const { stage, counts } = leaving();
  assert.deepEqual(counts, [1], "the pet still waves");
  wait(stage.petFor("p/1"), 6000);
  assert.deepEqual(counts, [1, 0]);
  stage.destroy();
});

test("the pets take the theme's text color, also from one dark theme to another", () => {
  const { stage, lay, show, give, t } = account();
  give([chat("p/1")]);
  lay();
  show();
  const pet = stage.petFor("p/1");
  const film = pet.film;
  let resets = 0;
  const reset = film.reset.bind(film);
  film.reset = () => (resets++, reset());
  t.setDarkAll(true);
  t.css.color = "rgb(102, 136, 204)"; // Abyss after Dark+
  t.setDarkAll(true);
  assert.equal(pet.talpy.theme.text, "rgb(102, 136, 204)");
  const before = resets;
  t.setDarkAll(true); // (nothing changed: its pictures stay)
  assert.equal(resets, before);
  stage.destroy();
});
