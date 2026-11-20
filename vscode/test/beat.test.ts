// The page's beat (webview/pets/beat.ts): one clock for what moves on a page,
// 30 beats a second in step with the screen, nothing while nobody sees it.
// Run in a vm context of its own with a made-up 60 Hz screen: time only goes
// on when the test says so, timers and frames come when they're due.

import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { createRequire } from "node:module";
import * as path from "node:path";
import { test } from "node:test";
import * as vm from "node:vm";

type Any = any; // (the module is reached at run time)

const repo = path.resolve(__dirname, "..", "..");
let bundled = "";

function bundle(): string {
  if (!bundled) {
    const { buildSync } = createRequire(__filename)("esbuild") as Any; // (not bundled into this test)
    bundled = buildSync({
      stdin: {
        contents: 'export * from "./webview/pets/beat";\nexport { blinkOpacity } from "./webview/components/BlinkDot";\n',
        resolveDir: repo,
        loader: "ts",
      },
      bundle: true,
      write: false,
      format: "cjs",
      platform: "browser",
      target: "es2022",
      jsx: "automatic",
      jsxImportSource: "preact",
      logLevel: "silent",
    }).outputFiles[0].text;
  }
  return bundled;
}

const VSYNC = 1000 / 60;

// A page on a 60 Hz screen. A frame asked for comes at the screen's next
// refresh; asked for after a while without frames, Chromium hands over the
// one of its last refresh at once (handsLast), as it did here.
function page(handsLast = true) {
  let now = 1000;
  let lastFrameAt = -Infinity; // (when the page last had a frame)
  let timers: { at: number; fn: () => void; id: number }[] = [];
  let frames: { fn: (t: number) => void; id: number; at: number }[] = [];
  let ids = 0;
  const seen = { frames: 0, wakes: 0 };
  const visibility = { state: "visible", listeners: [] as (() => void)[] };
  const sandbox: Record<string, unknown> = {
    performance: { now: () => now },
    setTimeout: (fn: () => void, ms: number) => {
      const id = ++ids;
      timers.push({ at: now + Math.max(0, ms), fn, id });
      return id;
    },
    clearTimeout: (id: number) => void (timers = timers.filter((t) => t.id !== id)),
    requestAnimationFrame: (fn: (t: number) => void) => {
      const id = ++ids;
      const next = Math.floor(now / VSYNC + 1e-9) * VSYNC + VSYNC;
      const idle = now - lastFrameAt > 1.5 * VSYNC;
      frames.push({ fn, id, at: handsLast && idle ? next - VSYNC : next });
      return id;
    },
    cancelAnimationFrame: (id: number) => void (frames = frames.filter((f) => f.id !== id)),
    document: {
      get visibilityState() {
        return visibility.state;
      },
      addEventListener: (_kind: string, fn: () => void) => visibility.listeners.push(fn),
    },
    matchMedia: () => ({ matches: false, addEventListener() {} }),
    module: { exports: {} },
  };
  vm.runInNewContext(bundle(), sandbox);
  const beat = (sandbox.module as { exports: Any }).exports;
  // Time goes on by ms: timers and frames come as they're due, in order
  const run = (ms: number): void => {
    const end = now + ms;
    for (;;) {
      const t = timers.reduce((a, b) => (b.at < a.at ? b : a), { at: Infinity } as { at: number; fn: () => void; id: number });
      const f = visibility.state === "hidden" ? { at: Infinity } as { at: number } : frames.reduce((a, b) => (b.at < a.at ? b : a), { at: Infinity } as { at: number; fn: (t: number) => void; id: number });
      const at = Math.min(t.at, f.at);
      if (at > end) break;
      now = Math.max(now, at);
      if (t.at <= f.at) {
        timers = timers.filter((x) => x !== t);
        seen.wakes++;
        t.fn();
      } else {
        const frame = f as { at: number; fn: (t: number) => void; id: number };
        frames = frames.filter((x) => x !== frame);
        lastFrameAt = now;
        seen.frames++;
        frame.fn(frame.at);
      }
    }
    now = end;
  };
  const hide = (hidden: boolean): void => {
    visibility.state = hidden ? "hidden" : "visible";
    for (const fn of visibility.listeners) fn();
  };
  return { beat, run, seen, hide, pending: () => ({ timers: timers.length, frames: frames.length }), time: () => now };
}

// Something that moves on every count-th beat as long as it lives: the times it moved
function mover(beat: Any, count = 1, quick = () => false) {
  const at: number[] = [];
  let wish = 0;
  const step = (): void => {
    wish = beat.nextBeat((t: number) => {
      at.push(t);
      step();
    }, quick(), count);
  };
  step();
  return { at, stop: () => beat.cancelBeat(wish) };
}

const gaps = (at: number[]) => at.slice(1).map((t, i) => Math.round(t - at[i]));

test("the beat comes every other frame of a 60 Hz screen, 30 a second, the same for all that moves", () => {
  for (const handsLast of [true, false]) {
    const p = page(handsLast);
    const pets = mover(p.beat);
    const stars = mover(p.beat);
    p.run(1000);
    const after = { frames: p.seen.frames, at: pets.at.length };
    p.run(1000);
    assert.ok(Math.abs(pets.at.length - after.at - 30) <= 1, `${pets.at.length - after.at} beats a second (handsLast ${handsLast})`);
    assert.deepEqual(new Set(gaps(pets.at.slice(-25))), new Set([33]), "beats not evenly apart");
    assert.deepEqual(stars.at, pets.at, "not one frame for both");
    // (at most a frame handed over before each beat, let go)
    assert.ok(p.seen.frames - after.frames <= 2 * (pets.at.length - after.at) + 1, `${p.seen.frames - after.frames} frames for ${pets.at.length - after.at} beats`);
    if (!handsLast) assert.equal(p.seen.frames - after.frames, pets.at.length - after.at, "frames for nothing");
    pets.stop();
    stars.stop();
  }
});

test("a glyph on every third beat moves ten times a second, on beats of the pets'", () => {
  const p = page();
  const pets = mover(p.beat);
  const glyph = mover(p.beat, 3);
  p.run(2000);
  const last = glyph.at.slice(-10);
  assert.deepEqual(new Set(gaps(last)), new Set([100]));
  for (const t of last) assert.ok(pets.at.includes(t), "the glyph drew a frame of its own");
  // alone it's woken once a picture, not at every beat
  pets.stop();
  const wakes = p.seen.wakes;
  const frames = p.seen.frames;
  const from = glyph.at.length;
  p.run(1000);
  const pictures = glyph.at.length - from;
  assert.ok(Math.abs(pictures - 10) <= 1, `${pictures} pictures a second`);
  assert.ok(p.seen.wakes - wakes <= pictures + 1, `${p.seen.wakes - wakes} wake-ups for ${pictures} pictures`);
  assert.ok(p.seen.frames - frames <= pictures + 1, `${p.seen.frames - frames} frames for ${pictures} pictures`);
  assert.deepEqual(new Set(gaps(glyph.at.slice(-8))), new Set([100]));
  glyph.stop();
});

test("a change that can wait (the turn's clock) comes with the glyph's next picture, no frame of its own", () => {
  const p = page();
  const glyph = mover(p.beat, 3);
  p.run(1000);
  const came: number[] = [];
  for (let i = 0; i < 5; i++) {
    p.run(337); // (a second's tick, whenever its timer fires)
    p.beat.withNextBeat((t: number) => came.push(t));
  }
  p.run(200);
  assert.equal(came.length, 5);
  for (const t of came) assert.ok(glyph.at.includes(t), "a frame of its own");
  glyph.stop();
  // (nothing else moving: on a beat of its own, at once)
  p.run(500);
  p.beat.withNextBeat((t: number) => came.push(t));
  p.run(50);
  assert.equal(came.length, 6);
});

test("with nothing that moves, the beat asks for no timer and no frame", () => {
  const p = page();
  const pets = mover(p.beat);
  p.run(500);
  pets.stop();
  assert.deepEqual(p.pending(), { timers: 0, frames: 0 });
  const frames = p.seen.frames;
  p.run(1000);
  assert.equal(p.seen.frames, frames);
});

test("a hidden page, or one its host says nobody sees, gets no beat; seen again it goes on", () => {
  const p = page();
  const pets = mover(p.beat);
  p.run(500);
  for (const hide of [(on: boolean) => p.hide(on), (on: boolean) => p.beat.beatShown(!on)]) {
    hide(true);
    const n = pets.at.length;
    p.run(1000);
    assert.equal(pets.at.length, n, "it moved while hidden");
    assert.deepEqual(p.pending(), { timers: 0, frames: 0 });
    hide(false);
    p.run(1000);
    assert.ok(pets.at.length - n >= 29, "it didn't go on");
  }
  pets.stop();
});

test("a quick wish (a pet in your hand) comes true every frame; the rest keep their beat", () => {
  const p = page();
  let holding = true;
  const held = mover(p.beat, 1, () => holding);
  const other = mover(p.beat);
  p.run(1000);
  const n = held.at.length;
  p.run(1000);
  assert.ok(Math.abs(held.at.length - n - 60) <= 1, `${held.at.length - n} frames a second`);
  assert.deepEqual(new Set(gaps(other.at.slice(-20))), new Set([33]));
  holding = false; // (put down: from its next wish on, on the beat)
  p.run(100);
  const m = held.at.length;
  p.run(1000);
  assert.ok(Math.abs(held.at.length - m - 30) <= 1, `${held.at.length - m} beats a second`);
  held.stop();
  other.stop();
});

test("Talpy Chat's dot blinks as the CSS animation did: to a quarter and back in 1.2 s", () => {
  const { beat } = page();
  const blink = (beat as Any).blinkOpacity as (ms: number) => number;
  assert.equal(blink(0), 1);
  assert.equal(blink(600), 0.25);
  assert.equal(blink(1200), 1);
  assert.ok(Math.abs(blink(300) - 0.625) < 1e-9);
});

test("nothing on the pages animates forever on the compositor's clock", () => {
  // An animation that never ends draws the whole page at every frame of the
  // screen (14% of a core here for a fading dot): what keeps moving moves on
  // the beat. The spinner shows only while something loads.
  const css = ["webview/styles.css", "webview/pets/pets.css"].map((f) => readFileSync(path.join(repo, f), "utf8")).join("\n");
  const forever = [...css.matchAll(/animation:[^;]*infinite[^;]*;/g)].map((m) => m[0]);
  assert.deepEqual(forever, ["animation: td-spin 0.8s linear infinite;"]);
  for (const dir of ["webview", "webview/components", "webview/pets", "webview/util"])
    for (const f of readdirSync(path.join(repo, dir))) {
      if (!/\.tsx?$/.test(f)) continue;
      const source = readFileSync(path.join(repo, dir, f), "utf8");
      assert.ok(!/iterations:\s*Infinity/.test(source), `${dir}/${f} animates forever`);
      assert.ok(!/setInterval\([^)]*,\s*(\d{1,2}|1\d\d)\)/.test(source), `${dir}/${f} has a timer of its own for what moves`);
    }
});
