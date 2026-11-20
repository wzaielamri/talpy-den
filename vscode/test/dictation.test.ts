// Dictation Models…: set up when nothing writes it down; a model picked,
// then downloaded, used or deleted through dictate.py; removing
// faster-whisper asks first.

import assert from "node:assert/strict";
import { test } from "node:test";
import * as vscode from "vscode";
import "./useHost";
import { dictationModels } from "../src/dictation";
import { recorded } from "./vscode-stub";

const model = (name: string, more: Record<string, unknown> = {}) =>
  ({ name, mb: 142, note: "fast", installed: false, deletable: false, used: false, ...more });

function harness(status: Record<string, unknown>, picks: string[], warn = "") {
  const window = vscode.window as unknown as Record<string, unknown>;
  const calls: string[][] = [];
  const pickers: { title: string; items: string[] }[] = [];
  window.showQuickPick = async (items: { label: string }[], o: { title: string }) => {
    pickers.push({ title: o.title, items: items.map((i) => i.label) });
    const wanted = picks.shift();
    return items.find((i) => i.label === wanted);
  };
  window.showWarningMessage = async (m: string, ..._rest: unknown[]) => (recorded.messages.push(m), warn || undefined);
  const backend = {
    dictate: async (args: string[]) => (calls.push(args), args[0] === "--status" ? status : { ok: true, message: `done: ${args.join(" ")}` }),
  };
  return { calls, pickers, run: () => dictationModels(backend as never) };
}

test("nothing writes it down: setting up is offered and runs", async () => {
  recorded.messages.length = 0;
  const h = harness({ ok: false, engine: null, canSetup: true, setupMb: 612, recorder: "pw-record", missing: [], chosen: "auto",
                      models: [model("base")] }, ["$(cloud-download) Set up dictation"]);
  await h.run();
  assert.equal(h.pickers[0].title, "Dictation isn't set up");
  assert.deepEqual(h.calls, [["--status"], ["--setup"]]);
  assert.equal(recorded.messages.at(-1), "done: --setup");
});

test("a model is downloaded, used or deleted; whisper.cpp's own isn't deleted", async () => {
  const status = { ok: true, engine: "faster-whisper", modelName: "base", chosen: "base", setUp: true, recorder: "pw-record", missing: [],
                   models: [model("base", { installed: true, deletable: true, used: true }), model("small"), model("tiny", { installed: true, deletable: true })] };
  let h = harness(status, ["small", "$(cloud-download) Download and use it"]);
  await h.run();
  assert.equal(h.pickers[0].title, "Dictation: faster-whisper, the base model");
  assert.deepEqual(h.pickers[0].items, ["$(check) base", "small", "tiny", "Use the best one downloaded", "$(trash) Remove faster-whisper…"]);
  assert.deepEqual(h.calls.at(-1), ["--get-model", "small"]);
  h = harness(status, ["tiny", "$(check) Use it"]);
  await h.run();
  assert.deepEqual(h.pickers[1].items, ["$(check) Use it", "$(trash) Delete it"]);
  assert.deepEqual(h.calls.at(-1), ["--use-model", "tiny"]);
  h = harness(status, ["tiny", "$(trash) Delete it"]);
  await h.run();
  assert.deepEqual(h.calls.at(-1), ["--delete-model", "tiny"]);
  h = harness({ ...status, engine: "whisper.cpp", tool: "/usr/bin/whisper-cli", setUp: false,
                models: [model("base", { installed: true, used: true })] }, ["$(check) base"]);
  await h.run();
  assert.deepEqual(h.pickers[1].items, ["whisper.cpp's own model"]);
  assert.deepEqual(h.calls, [["--status"]]);
});

test("removing faster-whisper asks first", async () => {
  const status = { ok: true, engine: "faster-whisper", modelName: "base", chosen: "auto", setUp: true, recorder: "pw-record", missing: [],
                   models: [model("base", { installed: true, deletable: true, used: true })] };
  let h = harness(status, ["$(trash) Remove faster-whisper…"]);
  await h.run();
  assert.deepEqual(h.calls, [["--status"]]); // (not confirmed)
  h = harness(status, ["$(trash) Remove faster-whisper…"], "Delete");
  await h.run();
  assert.deepEqual(h.calls.at(-1), ["--remove-setup"]);
});
