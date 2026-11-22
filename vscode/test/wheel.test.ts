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
// frames a second, its animation steps right after each frame (FrameAnimation, its frameTime `jitter` ms
// early or late); the events that came before a frame are taken, the frame shows where the list is, then
// the step. The list's place each frame, and its steps from the first that moved to the last
function play(events: Ev[], o: { hz?: number; lo?: number; hi?: number; y0?: number; jitter?: number; s?: W.Wheel } = {}) {
  const vs = 1000 / (o.hz || 60.03), lo = o.lo === undefined ? -1e9 : o.lo, hi = o.hi === undefined ? 1e9 : o.hi;
  const s = o.s || W.create(o.y0 || 0);
  let y = o.y0 || 0, i = 0, running = false, first = -1, startedAt = 0, lastStep = 0, r = 7;
  const rnd = () => { r = (r * 16807) % 2147483647; return r / 2147483647 - 0.5; };
  const ys = [y];
  for (let k = 1; k < 600; k++) {
    while (i < events.length && events[i].t <= k * vs) {
      const e = events[i++];
      if (first < 0 && e.angle !== 0) first = k;
      const res = W.input(s, { angle: e.angle, pixel: e.pixel, phase: e.phase }, y, lo, hi, STEP, LONG);
      if (!Number.isNaN(res.put)) y = res.put;
      if (res.starting) { running = W.moving(s); startedAt = e.t; }
    }
    ys.push(y);
    if (running) {   // (the step after this frame: frameTime since the last step, or since it started)
      const at = k * vs + (o.jitter ? rnd() * o.jitter : 0);
      const p = W.tick(s, at - Math.max(startedAt, lastStep), y, lo, hi);
      lastStep = at;
      startedAt = 0;
      if (!Number.isNaN(p)) y = p;
      running = W.moving(s);
    }
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
  assert.deepEqual(steps, kirigami(notches(1, 0)));   // (one notch alone: the same ease)
  assert.ok(still);
});

test("on a screen of 75, 120, 144 or 165 frames a second every frame of a notch moves, and it lasts its 200 ms", () => {
  for (const hz of [60.03, 75, 120, 144, 165]) {
    for (const jitter of [0, 1.5]) {
      // (its first motion in a window learns the screen's frame: 60 a second till its steps say otherwise)
      const first = play(notches(1, 0), { hz, jitter });
      assert.equal(sum(first.steps), STEP);
      assert.equal(first.steps.filter((x, k) => x === 0 && (first.steps[k - 1] + first.steps[k + 1]) / 2 >= 2).length, 0, `${hz} Hz: ${first.steps}`);
      // (while it learns, its steps go by their times: within 2 px of falling)
      for (let k = 1; k < first.steps.length; k++) assert.ok(first.steps[k] <= first.steps[k - 1] + 2, `${hz} Hz: ${first.steps}`);
      const s = W.create(0);
      play(notches(1, 0), { hz, jitter, s });
      const { steps, still, ms } = play(notches(1, 0), { hz, jitter, s, y0: s.y });
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
  assert.ok(up[up.length - 1] <= 4, `it stopped at ${up[up.length - 1]} px a frame: ${up}`);
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
  assert.ok(Number.isNaN(W.tick(s, F, 500, -1e9, 1e9)));   // (the list was put at 500 meanwhile)
  assert.equal(W.moving(s), false);
});
