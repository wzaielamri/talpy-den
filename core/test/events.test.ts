import { test } from "node:test";
import * as assert from "node:assert/strict";
import { Emitter } from "../src/events";

test("listeners hear fire in the order they subscribed", () => {
  const e = new Emitter<number>();
  const heard: string[] = [];
  e.event((v) => heard.push(`a${v}`));
  e.event((v) => heard.push(`b${v}`));
  e.fire(1);
  e.fire(2);
  assert.deepEqual(heard, ["a1", "b1", "a2", "b2"]);
});

test("a disposed listener hears nothing", () => {
  const e = new Emitter<number>();
  const heard: number[] = [];
  const sub = e.event((v) => heard.push(v));
  e.fire(1);
  sub.dispose();
  e.fire(2);
  assert.deepEqual(heard, [1]);
});

test("dispose() drops every listener", () => {
  const e = new Emitter<number>();
  let calls = 0;
  e.event(() => calls++);
  e.event(() => calls++);
  e.dispose();
  e.fire(1);
  assert.equal(calls, 0);
});
