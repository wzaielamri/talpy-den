import { mock, test } from "node:test";
import * as assert from "node:assert/strict";
import { Emitter, type Disposable } from "../src/events";

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

test("a listener that throws doesn't stop the others", () => {
  const e = new Emitter<number>();
  const heard: string[] = [];
  e.event((v) => heard.push(`a${v}`));
  e.event(() => { throw new Error("boom"); });
  e.event((v) => heard.push(`c${v}`));
  const original = console.error;
  const reported: unknown[][] = [];
  console.error = (...args: unknown[]) => { reported.push(args); };
  try {
    assert.doesNotThrow(() => e.fire(1));
  } finally {
    console.error = original;
  }
  assert.deepEqual(heard, ["a1", "c1"]);
  assert.equal(reported.length, 1);
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

// As vscode.EventEmitter: a listener taken off during a fire, by one that heard it before, doesn't hear it;
// one added during a fire hears the next
test("a listener taken off during a fire isn't called; one added during it hears the next fire", () => {
  const e = new Emitter<number>();
  const heard: string[] = [];
  let b: Disposable | undefined;
  e.event((v) => {
    heard.push(`a${v}`);
    b?.dispose();
    if (v === 1) e.event((w) => heard.push(`c${w}`));
  });
  b = e.event((v) => heard.push(`b${v}`));
  e.fire(1);
  e.fire(2);
  assert.deepEqual(heard, ["a1", "a2", "c2"]);
});

// As vscode.EventEmitter: a fire from inside a listener first delivers the event being delivered to the rest
// of the listeners, then its own to every listener, before it returns; a listener that throws meanwhile
// doesn't stop the others
test("a fire from inside a listener comes after the event being delivered, for every listener", () => {
  const e = new Emitter<number>();
  const heard: string[] = [];
  e.event((v) => {
    heard.push(`a${v}`);
    if (v === 1) {
      e.fire(2);
      heard.push("a fired 2");
    }
  });
  e.event((v) => {
    if (v === 1) throw new Error("boom");
  });
  e.event((v) => heard.push(`c${v}`));
  const reported = mock.method(console, "error", () => undefined);
  try {
    e.fire(1);
  } finally {
    reported.mock.restore();
  }
  assert.deepEqual(heard, ["a1", "c1", "a2", "c2", "a fired 2"]);
  assert.equal(reported.mock.callCount(), 1);
  e.fire(3);
  assert.deepEqual(heard.slice(5), ["a3", "c3"], "and the next fire as usual");
});
