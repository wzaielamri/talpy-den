import assert from "node:assert/strict";
import { test } from "node:test";
import { rowKeyOf } from "../webview/util/chat";

test("a row's open details stay open when its chat changes kind (a background session ends: live → job)", () => {
  const live = { key: ".claude-work/s1/live", profileDir: ".claude-work", sessionId: "s1", chatId: "c1" };
  assert.equal(rowKeyOf(live, "lab"), rowKeyOf({ ...live, key: ".claude-work/s1/job" }, "lab"));
  assert.equal(rowKeyOf(live, "lab"), "lab|.claude-work/c1");
  assert.equal(rowKeyOf({ ...live, chatId: "" }), ".claude-work/s1");
});
