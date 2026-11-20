import assert from "node:assert/strict";
import { test } from "node:test";
import { useSettingsHost } from "../src/settings";
import { FakeHost } from "./fakeHost";
import type { FindAnswer } from "../src/agents/claudeCode/backend";
import { allShown, foundLines, showAll, type FoundLine } from "../src/agents/claudeCode/found";

useSettingsHost(new FakeHost());

// only how many of each kind matters here
function answer(chats: number, rest: { projects?: number; plans?: number; memories?: number; more?: boolean; error?: string } = {}): FindAnswer {
  const some = (n = 0) => Array.from({ length: n }, (_, i) => ({ i }));
  return {
    ok: !rest.error,
    message: rest.error ?? "",
    more: !!rest.more,
    results: some(chats),
    projects: some(rest.projects),
    plans: some(rest.plans),
    memories: some(rest.memories),
  } as unknown as FindAnswer;
}

// a line as text: "▾ Chats (2)", "chats 0", "note: …"
function text(line: FoundLine): string {
  if ("fold" in line) return `${line.open ? "▾" : "▸"} ${line.title}`;
  if ("note" in line) return `${line.warning ? "warning" : "note"}: ${line.note}`;
  return `${line.kind} ${line.source ? `@${line.source} ` : ""}${line.index}`;
}

test("the chats show at first; folders, plans and memories fold under their headings", () => {
  const lines = foundLines([answer(2, { plans: 3, memories: 1 })], [], new Map()).map(text);
  assert.deepEqual(lines, ["▸ Plans (3)", "▸ Memories (1)", "▾ Chats (2)", "chats 0", "chats 1"]);
});

test("with no chat found, everything shows", () => {
  const lines = foundLines([answer(0, { projects: 1, memories: 2 })], [], new Map()).map(text);
  assert.deepEqual(lines, ["▾ Folders (1)", "projects 0", "▾ Memories (2)", "memories 0", "memories 1"]);
});

test("a heading you picked stays as you left it", () => {
  const folds = new Map([["/memories", true], ["/chats", false]]);
  const lines = foundLines([answer(1, { memories: 1 })], [], folds).map(text);
  assert.deepEqual(lines, ["▾ Memories (1)", "memories 0", "▸ Chats (1)"]);
});

test("more chats than listed: the heading and a note say so", () => {
  const lines = foundLines([answer(1, { more: true })], [], new Map()).map(text);
  assert.deepEqual(lines, ["▾ Chats (1+)", "chats 0", "note: More chats have these words: add a word to narrow it down"]);
  const folded = foundLines([answer(1, { more: true })], [], new Map([["/chats", false]])).map(text);
  assert.deepEqual(folded, ["▸ Chats (1+)"]);
});

test("with SSH hosts shown, each source folds under its own heading", () => {
  const answers = [answer(1, { plans: 1 }), answer(0, { error: "Couldn't reach lab" }), answer(2)];
  const hosts = ["lab", "gpu"];
  assert.deepEqual(foundLines(answers, hosts, new Map()).map(text), [
    "▾ This computer · 1 chat, 1 plan",
    "▸ Plans (1)",
    "▾ Chats (1)",
    "chats 0",
    "▾ lab",
    "warning: Couldn't reach lab",
    "▾ gpu · 2 chats",
    "▾ Chats (2)",
    "chats @2 0",
    "chats @2 1",
  ]);
  const folded = foundLines(answers, hosts, new Map([["/source", false], ["gpu/chats", false]])).map(text);
  assert.deepEqual(folded, ["▸ This computer · 1 chat, 1 plan", "▾ lab", "warning: Couldn't reach lab", "▾ gpu · 2 chats", "▸ Chats (2)"]);
});

test("nothing found anywhere says so; no answers yet, no lines", () => {
  const lines = foundLines([answer(0)], [], new Map()).map(text);
  assert.deepEqual(lines, ["note: Nothing with all of these words: no chat (its name, folder or your prompts), project folder, plan or memory"]);
  assert.deepEqual(foundLines([], [], new Map()), []);
});

test("unfold all shows every source and kind; fold all folds the kinds and leaves the sources open", () => {
  const answers = [answer(1, { plans: 1, memories: 1 }), answer(1)];
  const hosts = ["lab"];
  const start = new Map([["lab/source", false]]);
  assert.equal(allShown(answers, hosts, start), false);
  const open = showAll(answers, hosts, start, true);
  assert.equal(allShown(answers, hosts, open), true);
  assert.equal(foundLines(answers, hosts, open).filter((l) => "fold" in l && !l.open).length, 0);
  const folded = showAll(answers, hosts, open, false);
  assert.deepEqual(foundLines(answers, hosts, folded).map(text), [
    "▾ This computer · 1 chat, 1 plan, 1 memory",
    "▸ Plans (1)",
    "▸ Memories (1)",
    "▸ Chats (1)",
    "▾ lab · 1 chat",
    "▸ Chats (1)",
  ]);
  assert.equal(allShown(answers, hosts, folded), false);
  assert.equal(start.get("lab/source"), false, "the folds it was given stay as they were");
});
