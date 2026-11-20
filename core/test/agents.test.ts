import { test } from "node:test";
import * as assert from "node:assert/strict";
import { CLAUDE_CODE } from "../src/agents";
import { agentOf, capabilitiesOf } from "../src/shared/model";
import type { Group, Session } from "../src/shared/types";

test("a chat without an agent is Claude Code's", () => {
  assert.equal(agentOf({} as Session), "claude-code");
  assert.equal(agentOf({ agent: "claude-code" } as Session), "claude-code");
});

test("a group without an agent has Claude Code's capabilities", () => {
  assert.deepEqual(capabilitiesOf({} as Group), CLAUDE_CODE.capabilities);
});

test("CLAUDE_CODE has every capability", () => {
  assert.equal(CLAUDE_CODE.id, "claude-code");
  assert.equal(CLAUDE_CODE.name, "Claude");
  assert.ok(Object.values(CLAUDE_CODE.capabilities).every((v) => v === true));
  assert.equal(Object.keys(CLAUDE_CODE.capabilities).length, 8);
});
