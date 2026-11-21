// Plasma Talpy Chat's rows a few at a time (package/contents/ui/fill.mjs, ChatPane.qml fillBuffer):
// where it starts, how each step grows, that it ends, and that each wait aims to leave half the time
import test from "node:test";
import assert from "node:assert/strict";
import { FILL_ALL, FILL_INTERVAL, FILL_QUICK, FILL_SLOW, FILL_STEP_MAX, fillNext, fillPace, fillStart, fillStepMin } from "../../package/contents/ui/fill.mjs";

const LINE = 20;   // (a line's height, px)

test("the fill starts at a screen around what you read, a step a screen or more, at the shortest wait", () => {
  assert.deepEqual(fillStart(700.4, LINE), { buffer: 700, step: 700.4, interval: FILL_INTERVAL });
  assert.equal(fillStart(100, LINE).step, LINE * 12);          // (a small list: a dozen lines at least)
  assert.equal(fillStart(50000, LINE).step, FILL_STEP_MAX);    // (never more than a step's most)
  assert.equal(fillStart(-5, LINE).buffer, 0);
});

test("each step grows by what the one before cost: half over FILL_SLOW, twice under FILL_QUICK, within its limits", () => {
  assert.equal(fillPace(800, FILL_SLOW + 1, LINE).step, 400);
  assert.equal(fillPace(800, FILL_QUICK - 1, LINE).step, 1600);
  assert.equal(fillPace(800, (FILL_SLOW + FILL_QUICK) / 2, LINE).step, 800);
  assert.equal(fillPace(fillStepMin(LINE), 500, LINE).step, fillStepMin(LINE));   // (never under a few lines)
  assert.equal(fillPace(FILL_STEP_MAX, 0, LINE).step, FILL_STEP_MAX);              // (nor over its most)
  assert.equal(fillPace(800, Number.NaN, LINE).step, 1600);                       // (no cost known: a quick one)
});

test("the wait after a step is at least twice what it cost: it aims at half of each period for the rows, at most", () => {
  for (const cost of [0, 3, 16, 17, 24, 40, 100, 333.3, 2000]) {
    const { interval } = fillPace(1000, cost, LINE);
    assert.ok(interval >= FILL_INTERVAL, `${cost}: ${interval}`);
    assert.ok(interval >= 2 * cost, `${cost}: ${interval}`);
    assert.ok(cost / interval <= 0.5, `${cost}: ${interval}`);
  }
  assert.equal(fillPace(1000, 5, LINE).interval, FILL_INTERVAL);   // (a cheap step: no longer than the shortest wait)
  assert.equal(fillPace(1000, 100, LINE).interval, 200);
});

test("it ends: the buffer only grows, and it's every row again (-1) in a bounded number of steps, however much a step costs", () => {
  let seed = 7;
  const random = () => ((seed = (seed * 1103515245 + 12345) % 2 ** 31) / 2 ** 31);
  const costs: Record<string, () => number> = { heavy: () => 300, light: () => 1, middle: () => 15,
                                                 alternating: (() => { let i = 0; return () => (i++ % 2 ? 200 : 0); })(),
                                                 random: () => random() * 120 };
  const most = Math.ceil(FILL_ALL / fillStepMin(LINE)) + 1;
  for (const [name, cost] of Object.entries(costs)) {
    const start = fillStart(900, LINE);
    let buffer = start.buffer, step = start.step, steps = 0;
    while (buffer !== -1) {
      const next = fillNext(buffer, step);
      assert.ok(next === -1 || next > buffer, `${name}: ${buffer} → ${next}`);
      assert.ok(next === -1 || next < FILL_ALL, name);
      buffer = next;
      const pace = fillPace(step, cost(), LINE);
      assert.ok(pace.step >= fillStepMin(LINE) && pace.step <= FILL_STEP_MAX, `${name}: ${pace.step}`);
      step = pace.step;
      assert.ok(++steps <= most, `${name}: ${steps} steps`);
    }
  }
  assert.equal(fillNext(FILL_ALL - 1, 1), -1);
  assert.equal(fillNext(FILL_ALL - 2, 1), FILL_ALL - 1);
});
