// Dictation on its host alone (no vscode): in a browser it isn't there, and nothing is asked of the backend.

import assert from "node:assert/strict";
import { test } from "node:test";
import type { Backend } from "../src/agents/claudeCode/backend";
import { dictationModels } from "../src/dictation";
import { FakeHost } from "./fakeHost";

// Dictation Models… in VS Code in a browser: said in an information message (as it always was), dictate.py
// isn't asked
test("dictation in a web UI says it isn't available", async () => {
  const fake = new FakeHost();
  fake.environment.web = true;
  const calls: string[][] = [];
  const backend = { dictate: async (args: string[]) => (calls.push(args), { ok: true, models: [] }) } as unknown as Backend;
  await dictationModels(fake, backend);
  assert.deepEqual(fake.recorded.messages.map((m) => [m.level, m.text]), [["info", "Dictating works in VS Code on your computer, not in a browser"]]);
  assert.deepEqual(calls, [], "no backend call");
  assert.equal(fake.recorded.picks.length, 0);
});
