// Plasma Talpy Chat's conversation moved by the wheel and the touchpad (package/contents/ui/wheel.mjs,
// WheelScroll.qml), frame by frame on a screen's clock (60.03 Hz, the owner's): a notch eases out, a spin
// keeps its pace, a touchpad's stream is followed evenly however its moves come, and its glide starts at
// the speed it had. Kirigami's WheelHandler (Plasma's scroll views; kirigami 6.32 wheelhandler.cpp,
// written out below as it does it) fails the same checks: that's the fault this fixes.
import test from "node:test";
import assert from "node:assert/strict";
import * as W from "../../package/contents/ui/wheel.mjs";

const F = 1000 / 60.03;   // (a frame, ms)
const STEP = 60;          // (a notch: 3 lines × 20 px, the desktop's default)
const LONG = 200;         // (Kirigami.Units.longDuration)

// An event as WheelScroll.qml hands it to wheel.mjs: its angle (120 a notch, up), its pixels, its phase
interface Ev { t: number; phase: "none" | "begin" | "update" | "end"; angle: number; pixel: number }

const notches = (n: number, gap: number, angle = 120): Ev[] =>
  Array.from({ length: n }, (_, i) => ({ t: i * gap, phase: "none" as const, angle, pixel: 0 }));
// (Wayland's touchpad: a move a report, its angle 12 eighths of a degree a pixel, its pixels the rest carried)
function touchpad(hz: number, speed: number, ms: number, late = 0, seed = 1): Ev[] {
  let r = seed;
  const rnd = () => { r = (r * 16807) % 2147483647; return r / 2147483647; };
  const out: Ev[] = [{ t: 5.3, phase: "begin", angle: 0, pixel: 0 }];
  let rest = 0;
  for (let t = 5.3; t <= 5.3 + ms + 1e-9; t += 1000 / hz) {
    const d = speed / hz, px = Math.round(d + rest);
    rest += d - px;
    out.push({ t: t + rnd() * late, phase: "update", angle: Math.round(12 * d), pixel: px });
  }
  for (let i = 1; i < out.length; i++) out[i].t = Math.max(out[i].t, out[i - 1].t);   // (late ones come bunched, in order)
  out.push({ t: out[out.length - 1].t + 1000 / hz, phase: "end", angle: 0, pixel: 0 });
  return out;
}
const moves = (events: Ev[]) => sum(events.map((e) => (e.phase === "none" || e.phase === "update" ? e.angle / 120 * STEP : 0)));

// The scroller as WheelScroll.qml runs it (wheel.mjs input() and tick(), the same code): a screen of `hz`
// frames a second (the system's rate given, rate(), unless `learn`: what it learns without); the events
// that came before a frame are taken, then, as the window is about to draw it (its afterAnimating), the
// step, drawn in that frame: tick() given the time as Date.now() gives it (whole ms, `jitter` ms early or
// late). A frame `miss` says is one the window didn't draw (busy): no step then. During a `stall` (from, to:
// ms) this thread is busy: no frame, no event taken; the events meanwhile are taken together after it. The
// list's place each frame, and its steps from the first that moved to the last
function play(events: Ev[], o: { hz?: number; lo?: number; hi?: number; y0?: number; jitter?: number; s?: W.Wheel; learn?: boolean;
                                 miss?: (k: number) => boolean; stall?: [number, number] } = {}) {
  const vs = 1000 / (o.hz || 60.03), lo = o.lo === undefined ? -1e9 : o.lo, hi = o.hi === undefined ? 1e9 : o.hi;
  const s = o.s || W.create(o.y0 || 0);
  if (!o.s && !o.learn) W.rate(s, o.hz || 60.03, []);
  let y = o.y0 || 0, i = 0, running = false, first = -1, r = 7;
  const rnd = () => { r = (r * 16807) % 2147483647; return r / 2147483647 - 0.5; };
  const ys = [y];
  for (let k = 1; k < 600; k++) {
    if (o.stall && k * vs > o.stall[0] && k * vs < o.stall[1]) { ys.push(y); continue; }
    while (i < events.length && events[i].t <= k * vs) {
      const e = events[i++];
      if (first < 0 && e.angle !== 0) first = k;
      const res = W.input(s, { angle: e.angle, pixel: e.pixel, phase: e.phase }, y, lo, hi, STEP, LONG);
      if (!Number.isNaN(res.put)) y = res.put;
      if (res.starting) running = W.moving(s);
    }
    if (running && !(o.miss && o.miss(k))) {
      const p = W.tick(s, Math.floor(k * vs + (o.jitter ? rnd() * o.jitter : 0)), y, lo, hi);
      if (!Number.isNaN(p)) y = p;
      running = W.moving(s);
    }
    ys.push(y);
  }
  const moved = ys.findIndex((v, k) => k > 0 && v !== ys[k - 1]);
  const steps = stepsOf(ys);
  return { steps, ys, still: !W.moving(s), late: moved - first, ms: steps.length * vs };   // (late: frames from the input to its first move)
}
function stepsOf(ys: number[]): number[] {
  const st = ys.slice(1).map((y, k) => ys[k] - y);
  const moving = st.map((x, k) => (x !== 0 ? k : -1)).filter((k) => k >= 0);
  return moving.length ? st.slice(moving[0], moving[moving.length - 1] + 1) : [];
}
// How often the steps go from growing to shrinking or back by more than whole-pixel rounding: an ease
// turns once at most (it speeds up, then slows down); every turn more is judder
function turns(steps: number[], tol = 1.5): number {
  let n = 0, trend = 0, extreme = steps[0];
  for (const s of steps.slice(1)) {
    if (trend >= 0 && s < extreme - tol) { n += trend > 0 ? 1 : 0; trend = -1; extreme = s; }
    else if (trend <= 0 && s > extreme + tol) { n += trend < 0 ? 1 : 0; trend = 1; extreme = s; }
    else if ((trend >= 0 && s > extreme) || (trend <= 0 && s < extreme)) extreme = s;
  }
  return n;
}
const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0);

// Kirigami 6.32's WheelHandler, as wheelhandler.cpp does it: each event stops its ease and starts one
// from where the list is to where it was going plus the event's distance (OutCubic, |Δ| × 200/60 ms,
// 50 ms at least), and as the fingers lift a glide from the pixels' speed × 2.5 (OutQuad, 10000 px/s²)
function kirigami(events: Ev[]): number[] {
  let y = 0, anim: { a: number; b: number; d: number; t: number; quad: boolean } | null = null;
  const queue: [number, number][] = [];
  const ys = [0];
  let i = 0;
  for (let k = 1; k < 400; k++) {
    if (anim) {
      anim.t += Math.floor(k * F) - Math.floor((k - 1) * F);
      const u = Math.min(1, anim.t / anim.d);
      y = anim.a + (anim.b - anim.a) * (anim.quad ? 1 - (1 - u) ** 2 : 1 - (1 - u) ** 3);
      if (u >= 1) anim = null;
    }
    while (i < events.length && events[i].t <= k * F) {
      const e = events[i++];
      const dist = -e.angle / 120 * STEP;
      if (e.phase === "end" && queue.length > 2) {
        const px = sum(queue.map((q) => q[1])), el = Math.max(1, queue[queue.length - 1][0] - queue[0][0]);
        const v = px / el * 2.5, time = Math.abs(v) / 0.01;   // (px/ms; 4000 × 2.5 px/s²: 0.01 px/ms²)
        queue.length = 0;
        anim = { a: y, b: y + time * v / 2, d: time, t: 0, quad: true };
        continue;
      }
      if (queue.length > 6) queue.shift();
      queue.push([Math.floor(e.t), -e.pixel]);
      if (e.angle === 0) continue;
      const target = Math.round((anim && !anim.quad ? anim.b : y) + dist);
      const d = Math.abs(target - y);
      anim = null;
      if (d > 2) anim = { a: y, b: target, d: Math.max(50, Math.min(Math.round(d * 200 / 60), 200)), t: 0, quad: false };
      else y = target;
    }
    ys.push(Math.round(y));
  }
  return stepsOf(ys);
}

test("a notch eases out over Kirigami's 200 ms: the desktop's lines × 20 px, its steps only fall, the first frame moves", () => {
  const { steps, still, late } = play(notches(1, 0));
  assert.equal(late, 0);   // (it moves in the frame that comes next: Kirigami's ease began a frame later)
  assert.equal(sum(steps), STEP);
  assert.ok(steps[0] >= 12, String(steps));   // (as Kirigami's first: 23% of the way)
  for (let k = 1; k < steps.length; k++) assert.ok(steps[k] <= steps[k - 1] + 1, String(steps));
  // (one notch alone: the same ease, but for a pixel's rounding: its frame is learned from frames whose times
  // are whole ms, Kirigami's is Qt's)
  const old = kirigami(notches(1, 0));
  assert.ok(steps.length === old.length && steps.every((x, k) => Math.abs(x - old[k]) <= 1), `${steps} / Kirigami's ${old}`);
  assert.ok(still);
});

test("on a screen of 75, 120, 144 or 165 frames a second every frame of a notch moves, and it lasts its 200 ms", () => {
  for (const hz of [60.03, 75, 120, 144, 165]) {
    for (const jitter of [0, 1.5]) {
      // (the system's rate for its window's screen: its first motion steps the screen's frames)
      const { steps, still, ms } = play(notches(1, 0), { hz, jitter });
      assert.equal(sum(steps), STEP, `${hz} Hz: ${steps}`);
      // (a frame that didn't move while the list went a pixel or more a frame: one missed; at the tail,
      // moving less than a pixel a frame, a whole-pixel list stays put a frame now and then)
      const missed = steps.filter((x, k) => x === 0 && (steps[k - 1] + steps[k + 1]) / 2 >= 2);
      assert.equal(missed.length, 0, `${hz} Hz, ±${jitter} ms: a frame that didn't move ${steps}`);
      for (let k = 1; k < steps.length; k++) assert.ok(steps[k] <= steps[k - 1] + 1, `${hz} Hz: ${steps}`);
      assert.ok(ms > 150 && ms < 230, `${hz} Hz: ${Math.round(ms)} ms ${steps}`);
      assert.ok(still);
    }
    const spin = play(notches(6, 50), { hz }).steps;   // (and a spin as at 60, in a window's first motion too)
    assert.equal(sum(spin), 6 * STEP, `${hz} Hz: ${spin}`);
    assert.ok(spin.every((s) => s > 0) && turns(spin) <= 2, `${hz} Hz: ${spin}`);
  }
});

test("a touchpad's swipe on a screen of 120, 144 or 165 frames a second eases in without a frame standing still", () => {
  for (const hz of [120, 144, 165]) {
    const s = W.create(0), vs = 1000 / hz;
    W.rate(s, hz, []);   // (the system's rate for its window's screen)
    for (const rate of [60, 90, 125]) {
      for (const phase of [0.3, 2, 4, 5.3, 9]) {   // (its first move this long after a frame)
        const at = Math.ceil(1000 / vs) * vs + (phase % vs) - 5.3;
        const { steps } = play(touchpad(rate, 200, 400).map((e) => ({ ...e, t: e.t + at })), { hz, s, y0: s.written });
        // (its first frames speed up, by whole pixels: none still, none slower than the one before but for rounding)
        const start = steps.slice(0, 8);
        assert.ok(start.every((x, k) => x >= 1 && (k === 0 || x >= start[k - 1] - 1)), `${hz} Hz, ${rate}/s, ${phase} ms: ${start}`);
      }
    }
  }
});

// (a notch from rest at `e` on a `hz` screen, its frames from the vsync just after the event on, as rates.mjs
// gives them; review round 5: per notch, its steps)
function notchAt(s: W.Wheel, y: number, e: number, hz: number) {
  W.input(s, { angle: 120, pixel: 0, phase: "none" }, y, -1e9, 1e9, STEP, LONG);
  return ticks(s, Array.from({ length: 200 }, (_, k) => e + 0.3 + k * 1000 / hz), y);
}
const near = (a: number[], b: number[]) => a.length === b.length && a.every((x, k) => Math.abs(x - b[k]) <= 1);

test("a window moved to a screen of another rate: the system's rate steps its frames at once; without it, faster ones are learned in a motion, slower ones in two", () => {
  const pairs = [[60.03, 120], [60.03, 144], [60.03, 165], [60.03, 240], [120, 60.03], [144, 60.03], [165, 60.03], [240, 60.03], [75, 144], [144, 165], [165, 144]];
  for (const [h1, h2] of pairs) {
    const ref = (() => { const s = W.create(0); W.rate(s, h2, []); return notchAt(s, 0, 1000, h2); })();
    // (the system's: told the new screen's rate as the window moves there)
    const told = W.create(0);
    W.rate(told, h1, []);
    let y = 0;
    for (let i = 0; i < 3; i++) y += sum(notchAt(told, y, 1000 + i * 1000, h1)) * -1;
    W.rate(told, h2, []);
    const first = notchAt(told, y, 9000, h2);
    assert.ok(near(first, ref), `${h1} -> ${h2}, told: ${first} / ${ref}`);
    // (without it: from what the frames show, the steps of each notch on the new screen)
    const s = W.create(0);
    y = 0;
    for (let i = 0; i < 3; i++) y -= sum(notchAt(s, y, 1000 + i * 1000, h1));
    const on = [0, 1, 2, 3].map((i) => { const st = notchAt(s, y, 10000 + i * 1000, h2); y -= sum(st); return st; });
    const from = h2 > h1 ? 1 : 2;   // (a faster screen's frames: learned in the first motion there; a slower one's in two)
    for (let i = from; i < 4; i++)
      assert.ok(on[i].length === ref.length && on[i].every((x, k) => Math.abs(x - ref[k]) <= 1), `${h1} -> ${h2}, notch ${i + 1} there: ${on[i]} / ${ref}`);
    on.forEach((st) => assert.equal(sum(st), STEP, `${h1} -> ${h2}: ${on}`));
    assert.ok(Math.abs(W.period(s) - 1000 / h2) <= 0.002 * 1000 / h2, `${h1} -> ${h2}: learned ${W.period(s)} ms`);
  }
});

test("without the system's rate a window starts at 60 a second: a session's first motion moves from its first frame, and its first gaps (the pipeline's) teach it nothing", () => {
  // (lock.mjs, review round 5: a session's first motion from rest, Wayland's frames, then ten notches long after,
  // each 14, 11, 10 … in its 10 moving frames; round 4 learned a frame from the first gaps in 24 of 96)
  let bad = 0, n = 0;
  for (let phase = 1.5; phase <= 17; phase += 0.5) {
    for (const frac of [0.1, 0.4, 0.7]) {
      const s = W.create(0);
      const e = 5000 + frac;
      W.input(s, { angle: 120, pixel: 0, phase: "none" }, 0, -1e9, 1e9, STEP, LONG);
      const first = ticks(s, [e + 0.3, e + 1.3, ...Array.from({ length: 60 }, (_, k) => e + phase + k * F)], 0);
      let y = -sum(first), last: number[] = [];
      for (let i = 0; i < 10; i++) {
        W.input(s, { angle: 120, pixel: 0, phase: "none" }, y, -1e9, 1e9, STEP, LONG);
        last = ticks(s, Array.from({ length: 60 }, (_, k) => 7000 + i * 1000 + frac + 0.3 + k * F), y);
        y -= sum(last);
      }
      n++;
      if (last.filter((x) => x).length !== 10 || last[0] !== 14 || first.slice(0, 3).join() !== "14,11,10") bad++;
      assert.ok(Math.abs(W.period(s) - 1000 / 60) < 0.01, `phase ${phase}: learned ${W.period(s)}`);
    }
  }
  assert.equal(bad, 0, `${bad} of ${n}`);
  // (and a first motion with nothing given starts at once at 60 a second)
  const { steps, late } = play(notches(1, 0), { learn: true });
  assert.equal(late, 0);
  assert.ok(near(steps, play(notches(1, 0)).steps), String(steps));
});

test("a step each frame of its window, as long as the frames since the last: when in its vsync a frame comes changes nothing, a missed one keeps the speed", () => {
  const ref = play(notches(1, 0));   // (the screen's frame learned before: the first test)
  const near = (a: number[], b: number[]) => a.length === b.length && a.every((x, k) => Math.abs(x - b[k]) <= 1);
  for (const jitter of [1.5, 4, 8]) {
    // (a frame's afterAnimating a few ms early or late, its time in whole ms: the same steps, but for a
    // pixel's rounding as the frame it learns moves by a hundredth of a ms)
    const { steps } = play(notches(1, 0), { jitter });
    assert.ok(near(steps, ref.steps) && sum(steps) === STEP, `±${jitter / 2} ms: ${steps} / ${ref.steps}`);
  }
  for (const missed of [2, 3, 5]) {
    // (a frame the window didn't draw: the next is where the list would have been by then)
    const { ys } = play(notches(1, 0), { miss: (k) => k === missed });
    assert.equal(ys[missed], ys[missed - 1], `frame ${missed}`);
    assert.ok(near(ys.slice(missed + 1, 30), ref.ys.slice(missed + 1, 30)), `frame ${missed} missed: ${stepsOf(ys)} / ${ref.steps}`);
  }
});

// (ticks at the given times, as an afterAnimating each: the list's steps)
function ticks(s: W.Wheel, times: number[], y0: number) {
  const ys = [y0];
  let y = y0;
  for (const t of times) {
    const p = W.tick(s, Math.floor(t), y, -1e9, 1e9);
    if (!Number.isNaN(p)) y = p;
    ys.push(y);
    if (!W.moving(s)) break;
  }
  return stepsOf(ys);
}

// (a motion from rest at `e` as Qt Wayland draws it (qwaylandwindow.cpp requestUpdate and handleUpdate,
// qwaylandglcontext.cpp swapBuffers, qsgthreadedrenderloop.cpp polishAndSync): its first frame at once, its second
// as soon as the first is handed on, a millisecond later (its update asked for before the first's swap, with no
// frame callback pending yet), its third at the first's frame callback `callback` ms after the event, then one
// each vsync; the events taken before the frame after them. Its steps)
function fromRest(events: Ev[], callback: number) {
  const s = W.create(0), e = 5000.2;
  W.rate(s, 60.03, []);
  const times = [e + 0.5, e + 1.6, ...Array.from({ length: 60 }, (_, n) => e + Math.max(callback, 1.7) + n * F)];
  let y = 0, i = 0, running = false;
  const ys = [0];
  for (const ft of times) {
    while (i < events.length && e + events[i].t <= ft) {
      const ev = events[i++];
      W.input(s, { angle: ev.angle, pixel: ev.pixel, phase: ev.phase }, y, -1e9, 1e9, STEP, LONG);
      running = W.moving(s);
    }
    if (running) {
      const p = W.tick(s, Math.floor(ft), y, -1e9, 1e9);
      if (!Number.isNaN(p)) y = p;
      running = W.moving(s);
    }
    ys.push(y);
  }
  return stepsOf(ys);
}

test("a motion from rest on Wayland: each frame goes a frame, its second (drawn a ms after its first) and third (at the first's callback) too", () => {
  // (start2.mjs, review round 5: with the callback 0 to 16 ms after the event round 4 went 14, 11, 1 … 5, 9, 8; a
  // frame's way each: 14, 11, 10)
  const ref = play(notches(1, 0)).steps;
  for (let callback = 0; callback <= 16; callback += 0.5) {
    const steps = fromRest(notches(1, 0), callback);
    assert.ok(near(steps, ref), `a notch, callback ${callback} ms after: ${steps} / ${ref}`);
    const spin = fromRest(notches(6, 50), callback);
    assert.ok(Math.abs(spin[0] - 14) <= 1 && Math.abs(spin[1] - 11) <= 1 && Math.abs(spin[2] - 10) <= 1, `a spin, callback ${callback} ms after: ${spin}`);
    assert.ok(spin.every((x) => x > 0) && turns(spin) <= 2 && sum(spin) === 6 * STEP, `a spin, callback ${callback} ms after: ${spin}`);
  }
});

test("frames missed for a while (a busy window) don't teach it a longer frame: back on every frame, back to its pace", () => {
  // (a spin; for ten frames the window draws every other vsync, then every vsync again: each frame's step
  // goes the vsyncs it stands for, and none after alternates single and double)
  const s = W.create(0);
  let y = 0;
  const t0 = 5000, notch = Array.from({ length: 40 }, (_, i) => t0 + i * 25);
  const frames: number[] = [];
  let t = t0 + F;
  while (t < t0 + 300) { frames.push(t); t += F; }
  for (let i = 0; i < 10; i++) { t += F; frames.push(t); t += F; }
  for (let i = 0; i < 20; i++) { frames.push(t); t += F; }
  let i = 0;
  const steps: number[] = [];
  for (const ft of frames) {
    while (i < notch.length && notch[i] <= ft) { W.input(s, { angle: 120, pixel: 0, phase: "none" }, y, -1e9, 1e9, STEP, LONG); i++; }
    const p = W.tick(s, Math.floor(ft), y, -1e9, 1e9);
    const prev = y;
    if (!Number.isNaN(p)) y = p;
    steps.push(prev - y);
  }
  const after = steps.slice(-20, -2);   // (every vsync again)
  const pace = after.slice().sort((a, b) => a - b)[after.length >> 1];
  assert.ok(after.every((x) => Math.abs(x - pace) <= 0.15 * pace + 1), `after the busy frames: ${after} (busy: ${steps.slice(-30, -20)})`);
  const busy = steps.slice(-30, -20);   // (every other vsync: two frames' way each)
  assert.ok(busy.every((x) => x <= 2.6 * pace), `the busy frames: ${busy} (pace after: ${pace})`);
  assert.equal(W.period(s), 1000 / 60);   // (busy.mjs, review round 5: its frame never changed)
});

test("a window that draws one vsync in four keeps its speed: each frame goes four (the first, as after a stall, three)", () => {
  // (a touchpad's steady swipe, 125 moves a second; the window draws every 4th vsync for a while: the first of those
  // frames goes three frames' way, as after a stall, each after it four, so the list keeps its speed; back on every
  // vsync, its pace; round 4's cap of three went three of four the whole while)
  const s = W.create(0);
  W.rate(s, 60.03, []);
  const events = touchpad(125, 400, 1300);
  const frames: number[] = [];
  let t = F;
  while (t < 400) { frames.push(t); t += F; }
  const busyFrom = frames.length;
  for (let i = 0; i < 8; i++) { t += 3 * F; frames.push(t); t += F; }
  const busyTo = frames.length;
  while (t < 1200) { frames.push(t); t += F; }
  let y = 0, i = 0;
  const steps: number[] = [];
  for (const ft of frames) {
    while (i < events.length && events[i].t <= ft) {
      const e = events[i++];
      W.input(s, { angle: e.angle, pixel: e.pixel, phase: e.phase }, y, -1e9, 1e9, STEP, LONG);
    }
    const p = W.tick(s, Math.floor(ft), y, -1e9, 1e9);
    const prev = y;
    if (!Number.isNaN(p)) y = p;
    steps.push(prev - y);
  }
  const before = steps.slice(busyFrom - 6, busyFrom);
  const pace = before.slice().sort((a, b) => a - b)[3];
  const busy = steps.slice(busyFrom, busyTo);
  assert.ok(Math.abs(busy[0] - 3 * pace) <= 0.1 * 3 * pace + 1, `the first busy frame: ${busy} (pace ${pace})`);
  assert.ok(busy.slice(1).every((x) => Math.abs(x - 4 * pace) <= 0.1 * 4 * pace + 1), `the busy frames: ${busy} (pace ${pace})`);
  const back = steps.slice(busyTo + 1, busyTo + 10);
  assert.ok(back.every((x) => Math.abs(x - pace) <= 0.15 * pace + 1), `back on every vsync: ${back} (pace ${pace})`);
  assert.ok(Math.abs(W.period(s) - F) < 1e-9);
});

test("a motion its window stops drawing ends where it was going: finish() is where its frames would have taken it", () => {
  for (const [what, events] of [["notch", notches(1, 0)], ["spin", notches(6, 50)], ["glide", touchpad(125, 200, 300)]] as [string, Ev[]][]) {
    const whole = play(events);
    const end = whole.ys[whole.ys.length - 1];
    for (const at of [3, 8, 20]) {   // (its window hidden after this many frames; the events till then came)
      const s = W.create(0);
      const { ys } = play(events.filter((e) => e.t <= at * F), { s, miss: (k) => k > at });
      const was = ys[at];
      const y = W.finish(s, -1e9, 1e9);
      assert.equal(W.moving(s), false, `${what} at ${at}`);
      if (events.every((e) => e.t <= at * F))
        assert.ok(Math.abs(y - end) <= 1, `${what}, hidden at frame ${at} (at ${was}): ended at ${y}, its frames took it to ${end}`);
      assert.equal(y, Math.round(y));
    }
  }
});

test("a spin keeps its pace: the steps go up once and down once, every notch's distance kept (Kirigami's go up and down)", () => {
  for (const [n, gap] of [[6, 50], [8, 25], [10, 40], [4, 80]]) {
    const { steps, still } = play(notches(n, gap));
    assert.equal(sum(steps), n * STEP, `${n}×${gap}: ${steps}`);
    // (the first notch's ease slows till the next ones speed it up, then it slows to a stop: twice at most)
    assert.ok(turns(steps) <= 2, `${n}×${gap}: ${turns(steps)} turns ${steps}`);
    assert.ok(steps.every((s) => s > 0), `${n}×${gap}: a frame that didn't move ${steps}`);
    assert.ok(still);
  }
  const old = kirigami(notches(6, 50));
  assert.ok(turns(old) >= 6, `Kirigami's: ${turns(old)} turns ${old}`);   // (each notch threw it forward again)
});

test("a spin into an end eases into it: no frame stops it dead (Kirigami kept its ease inside the list)", () => {
  for (const [n, room] of [[4, 150], [6, 200], [3, 100], [8, 300]]) {
    const { steps, ys } = play(notches(n, 50, -120), { lo: 0, hi: room });   // (down, toward the end `room` px away)
    assert.equal(ys[ys.length - 1], room, `${n} notches, ${room} px: ${steps}`);
    const down = steps.map((x) => -x);
    const tail = down.slice(-6);   // (its last frames slow down to the end, a pixel or two a frame at last)
    for (let k = 1; k < tail.length; k++)
      assert.ok(tail[k] <= tail[k - 1] + 1, `${n} notches, ${room} px: ${down}`);
    assert.ok(down[down.length - 1] <= 3, `${n} notches into ${room} px: it stopped at ${down[down.length - 1]} px a frame: ${down}`);
  }
});

test("a notch the other way turns it back to where it began, and a notch on a moving list adds to where it goes", () => {
  assert.equal(sum(play([{ t: 0, phase: "none", angle: 120, pixel: 0 }, { t: 30, phase: "none", angle: -120, pixel: 0 }]).steps), 0);
  assert.equal(sum(play([...notches(3, 30), { t: 100, phase: "none", angle: -60, pixel: 0 }]).steps), 2.5 * STEP);
});

test("the desktop's animations off: a notch is there at once", () => {
  const s = W.create(100);
  const r = W.input(s, { angle: 120, pixel: 0, phase: "none" }, 100, -1e9, 1e9, STEP, 0);
  assert.equal(r.put, 40);
  assert.equal(r.starting, false);
  assert.equal(W.moving(s), false);
});

for (const hz of [60, 90, 125]) {
  test(`a touchpad's stream at ${hz} a second is followed evenly, its moves on time or late and bunched`, () => {
    for (const late of [0, 4, 8, 12]) {
      for (const seed of [1, 2, 3]) {
        const { steps, still, late: wait } = play(touchpad(hz, 200, 600, late, seed));
        assert.equal(wait, 0, `${hz} Hz: the first frame moves`);
        // (after its start, till the fingers lift: each frame's step within a tenth and rounding of the pace)
        const mid = steps.slice(12, 34);
        const pace = mid.slice().sort((a, b) => a - b)[mid.length >> 1];
        const off = mid.filter((s) => Math.abs(s - pace) > 0.1 * pace + 1);
        assert.ok(off.length <= (late ? 2 : 0), `${hz} Hz, ${late} ms late: ${off.length} uneven of ${mid} (pace ${pace})`);
        assert.ok(steps.every((s) => s > 0), `${hz} Hz, ${late} ms late: a frame that didn't move ${steps}`);
        assert.ok(still);
      }
    }
  });
}

// (steps of a run around a stall: the frame before it, the frames from the first after it on)
function aroundStall(r: { ys: number[] }, stall: [number, number]) {
  const k0 = Math.ceil(stall[1] / F - 1e-9);   // (the first frame after it)
  const kb = Math.floor(stall[0] / F + 1e-9);   // (the last before it)
  return { before: r.ys[kb - 1] - r.ys[kb], after: r.ys.slice(k0 - 1).map((v, k, a) => (k ? a[k - 1] - v : NaN)).slice(1) };
}

test("a stall mid-swipe (this thread busy 200 to 300 ms, the moves meanwhile taken together after it) doesn't speed the touch up: it ends where it would have, at the fingers' pace again at once", () => {
  // (stream3.py, review round 5: the moves that came together after a stall, counted against its frames' time,
  // made a pace twice the fingers' and its glide went 180-720 px further; now its pace isn't counted from them)
  const events = touchpad(125, 400, 600);
  const total = sum(play(events).steps);
  for (const ms of [200, 250, 300]) {
    const stall: [number, number] = [200, 200 + ms];
    const r = play(events, { stall });
    assert.ok(Math.abs(sum(r.steps) - total) <= 0.05 * total, `${ms} ms: went ${sum(r.steps)}, ${total} without`);
    const { before, after } = aroundStall(r, stall);
    // (its first frame after: three frames' way at most; then the fingers' pace (a tenth more while it catches up))
    assert.ok(after[0] <= 3 * before + 2 && after[0] >= 1.5 * before, `${ms} ms: ${before} before, then ${after.slice(0, 10)}`);
    assert.ok(after.slice(1, 12).every((x) => Math.abs(x - before) <= 0.15 * before + 1), `${ms} ms: ${before} before, then ${after.slice(0, 12)}`);
  }
});

test("a stall mid-glide goes on after it: three frames' way at most, then its glide, no frame standing still", () => {
  // (freeze2.py, review round 5: stalls of 90 to 250 ms mid-glide)
  const events = touchpad(125, 400, 300);
  const whole = play(events);
  for (const ms of [90, 110, 120, 130, 140, 150, 200, 250]) {
    const stall: [number, number] = [360, 360 + ms];
    const r = play(events, { stall });
    const { before, after } = aroundStall(r, stall);
    const moving = after.filter((x, k) => k < after.findIndex((y, j) => j > 0 && after.slice(j).every((z) => z === 0)) || after.every((z) => z !== 0));
    assert.ok(after[0] <= 3 * before + 2, `${ms} ms: ${before} before, then ${after.slice(0, 10)}`);
    assert.ok(after[1] >= 0.5 * before - 2 || after[1] >= after[0] / 6, `${ms} ms: a frame near still after it: ${before}, then ${after.slice(0, 10)}`);
    assert.ok(moving.length >= 3, `${ms} ms: ${after.slice(0, 10)}`);
    assert.ok(r.still && Math.abs(r.ys[r.ys.length - 1] - whole.ys[whole.ys.length - 1]) <= 2, `${ms} ms: ended ${r.ys[r.ys.length - 1]}, ${whole.ys[whole.ys.length - 1]} without`);
  }
});

test("a touchpad on a screen of 144 frames a second is followed evenly too", () => {
  for (const hz of [90, 125]) {
    const { steps } = play(touchpad(hz, 200, 600), { hz: 144 });
    const mid = steps.slice(25, 75);
    const pace = mid.slice().sort((a, b) => a - b)[mid.length >> 1];
    assert.ok(steps.every((s) => s > 0), `${hz}/s on 144 Hz: ${steps}`);
    assert.ok(mid.filter((s) => Math.abs(s - pace) > 0.15 * pace + 1).length <= 2, `${hz}/s on 144 Hz: ${mid}`);
  }
});

test("each move applied as it comes, the moves of a frame at once (what the follower smooths), beats with the frames", () => {
  // (90 moves a second on 60 frames: one, two, one, two… a frame; what the follower above smooths)
  const raw: number[] = [];
  const ev = touchpad(90, 200, 600);
  let y = 0, i = 0;
  for (let k = 1; k < 40; k++) {
    while (i < ev.length && ev[i].t <= k * F) y += ev[i++].angle / 120 * STEP;
    raw.push(y);
  }
  const st = raw.slice(1).map((v, k) => v - raw[k]).slice(5, 30);
  assert.ok(Math.max(...st) >= 1.8 * Math.min(...st), String(st));
});

test("as the fingers lift it glides on at the speed it had, slowing evenly (Kirigami's glide began at less than half)", () => {
  // (from the pace it had down to rest, no frame slows by more than a sixth of it)
  const slows = (steps: number[]) => Math.max(...steps.slice(30).map((s, k) => s - steps[30 + k + 1]).filter((d) => !Number.isNaN(d)));
  for (const hz of [60, 90, 125]) {
    for (const liftLate of [0, 0.5, 1]) {   // (the lift a move after the last, or a little later)
      const ev = touchpad(hz, 200, 600);
      ev[ev.length - 1].t += liftLate * 1000 / hz;
      const { steps } = play(ev);
      const pace = steps.slice(12, 34).sort((a, b) => a - b)[11];
      assert.ok(slows(steps) <= pace / 6 + 1, `${hz} Hz, lift ${liftLate} late: ${steps.slice(30)}`);
    }
  }
  const old = kirigami(touchpad(60, 200, 600));
  assert.ok(slows(old) >= 0.4 * 20, `Kirigami's: ${old.slice(30)}`);
});

test("fingers that stopped before they lifted don't glide; no lift seen (X11), it ends where they took it", () => {
  const stopped = touchpad(125, 200, 300);
  stopped[stopped.length - 1].t += 200;   // (the lift 200 ms after the last move)
  const a = play(stopped);
  assert.equal(sum(a.steps), moves(stopped));
  assert.ok(a.still);
  const b = play(touchpad(125, 200, 300).filter((e) => e.phase === "update").map((e) => ({ ...e, phase: "none" as const })));
  assert.ok(b.still);
  const x11 = touchpad(125, 200, 300).filter((e) => e.phase === "update").map((e) => ({ ...e, phase: "none" as const, pixel: e.pixel || 1 }));
  assert.equal(sum(play(x11).steps), sum(x11.map((e) => e.angle / 120 * STEP)));   // (pixels, no phase: a touchpad still)
});

test("a glide into an end slows to a stop at it", () => {
  const { steps, ys } = play(touchpad(125, 200, 300), { lo: -380, hi: 1e9 });   // (360 px of moves, then the glide)
  assert.equal(Math.min(...ys), -380);
  const up = steps.filter((s) => s > 0);
  // (its last frame, into the end, a third of its pace at most: 20 px from the end at 20 px a frame, it can't
  // stop in less than two frames)
  const pace = up.slice(8, 16).sort((a, b) => a - b)[4];
  assert.ok(up[up.length - 1] <= pace / 3, `it stopped at ${up[up.length - 1]} px a frame: ${up}`);
});

test("it stops at an end; a touch held there goes back the other way at once", () => {
  const { ys } = play(notches(8, 25), { lo: -100 });
  assert.equal(Math.min(...ys), -100);   // (up from 0, its top 100 px up: no further)
  const back = play([...touchpad(125, 400, 200), ...touchpad(125, -200, 200).map((e) => ({ ...e, t: e.t + 300 }))], { lo: -150 });
  const turn = back.ys.findIndex((v, k) => k > 0 && v > back.ys[k - 1]);
  const atEnd = back.ys.findIndex((v) => v === -150);
  assert.ok(atEnd > 0 && turn > atEnd, String(back.ys.slice(0, 40)));
  assert.ok(turn - back.ys.findIndex((v, k) => k > 0 && k * F > 305) <= 4, "back the other way within a few frames");
});

test("moved by anything else, it stops there", () => {
  const s = W.create(0);
  W.input(s, { angle: 120, pixel: 0, phase: "none" }, 0, -1e9, 1e9, STEP, LONG);
  assert.equal(W.moving(s), true);
  assert.ok(Number.isNaN(W.tick(s, 1000, 500, -1e9, 1e9)));   // (the list was put at 500 meanwhile)
  assert.equal(W.moving(s), false);
});
