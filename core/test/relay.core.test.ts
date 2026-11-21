// Answer Permission Prompts… and Live Mode… on their host alone (no vscode): what the pick list offers (the
// one on now checked), what it runs here and on the SSH hosts shown, what it asks first and says after.

import assert from "node:assert/strict";
import { test } from "node:test";
import type { Backend } from "../src/agents/claudeCode/backend";
import type { Dashboard } from "../src/dashboard";
import { answerPermissionsHere, liveModeHere } from "../src/relay";
import { useSettingsHost } from "../src/settings";
import { FakeHost } from "./fakeHost";

// A host, and a backend whose pane.py answers as answer says, with the calls it got (without the --config-dir
// of the machine the tests run on)
const setup = (answer: (args: string[]) => Record<string, unknown>) => {
  const fake = new FakeHost();
  useSettingsHost(fake);
  const calls: string[][] = [];
  const backend = {
    pane: async (args: string[]) => {
      const mine = args.filter((a, i) => a !== "--config-dir" && args[i - 1] !== "--config-dir");
      calls.push(mine);
      return answer(mine);
    },
  } as unknown as Backend;
  return { fake, calls, backend };
};

test("Answer Permission Prompts… turns the hook on here and on each SSH host shown, and says where; a host that fails is said", async () => {
  let hostAnswer: Record<string, unknown> = { ok: true, message: "on" };
  const { fake, calls, backend } = setup((args) =>
    args[1] === "status" ? { ok: true, on: false, hooked: 0 } : args.includes("--host") ? hostAnswer : { ok: true, message: "Answers from Talpy Den: on" });
  const dash = { shownHosts: () => ["lab"] } as unknown as Dashboard;
  fake.answer.pick = (items) => items[0];
  await answerPermissionsHere(fake, backend, dash);
  const asked = fake.recorded.picks[0];
  assert.deepEqual(asked.options, { title: "Permission prompts", placeHolder: "Where can you answer them?" });
  assert.deepEqual(asked.items.map((i) => [i.label, i.description]), [["Answer them from Talpy Den too", ""], ["$(check) Only in the chats", "on now"]]);
  assert.match(asked.items[0].detail ?? "", /settings\.json \(and on lab\): /);
  assert.deepEqual(calls, [["--relay", "status"], ["--relay", "on"], ["--relay", "on", "--host", "lab"]]);
  assert.deepEqual(fake.recorded.messages.map((m) => [m.level, m.text]), [["info", "Talpy Den: Answers from Talpy Den: on (and on lab)."]]);

  hostAnswer = { ok: false, message: "unreachable" };
  await answerPermissionsHere(fake, backend, dash);
  assert.deepEqual(fake.recorded.messages.at(-1), { level: "error", text: "Talpy Den: lab: unreachable", options: undefined, actions: [] });
});

// Turned off while chats Talpy Chat started answer their prompts with the hook: asked whether it goes for them
// too (No keeps their copy: --keep-copy); Escape on that question changes nothing
test("Answer Permission Prompts… turned off asks about the chats Talpy Chat started; No keeps their hook, Escape changes nothing", async () => {
  const { fake, calls, backend } = setup((args) => (args[1] === "status" ? { ok: true, on: true, hooked: 2 } : { ok: true, message: "Answers from Talpy Den: off" }));
  const dash = { shownHosts: () => [] } as unknown as Dashboard;
  fake.answer.pick = (items) => items[1];
  fake.answer.message = (_text, actions) => (actions.length ? "No, Keep It for Them" : undefined);
  await answerPermissionsHere(fake, backend, dash);
  assert.deepEqual(fake.recorded.picks[0].items.map((i) => [i.label, i.description]), [["$(check) Answer them from Talpy Den too", "on now"], ["Only in the chats", ""]]);
  const question = fake.recorded.messages[0];
  assert.deepEqual([question.level, question.text, question.options?.modal, question.actions],
    ["warning", "2 chats started from Talpy Chat answer their prompts here with it. Turn it off for them too?", true, ["Yes, for Them Too", "No, Keep It for Them"]]);
  assert.deepEqual(calls, [["--relay", "status"], ["--relay", "off", "--keep-copy"]]);
  assert.deepEqual(fake.recorded.messages.at(-1)?.text, "Talpy Den: Answers from Talpy Den: off.");

  fake.answer.message = () => undefined;
  await answerPermissionsHere(fake, backend, dash);
  assert.deepEqual(calls.slice(2), [["--relay", "status"]], "Escape: nothing turned off");
  assert.equal(fake.recorded.messages.length, 3, "nothing said after");
});

test("Live Mode… sets the live hook as picked, says so and checks again; Escape changes nothing; a failure is said", async () => {
  let result: Record<string, unknown> = { ok: true, message: "Live mode: off" };
  const { fake, calls, backend } = setup((args) => (args[1] === "status" ? { ok: true, on: true } : result));
  let refreshed = 0;
  const dash = { refresh: async () => void refreshed++ } as unknown as Dashboard;
  fake.answer.pick = (items) => items[1];
  await liveModeHere(fake, backend, dash);
  const asked = fake.recorded.picks[0];
  assert.deepEqual(asked.options, { title: "Live mode", placeHolder: "When do chats' steps show?" });
  assert.deepEqual(asked.items.map((i) => [i.label, i.description]), [["$(check) Show each step as it happens", "on now"], ["At each check", ""]]);
  assert.deepEqual(calls, [["--live", "status"], ["--live", "off"]]);
  assert.deepEqual(fake.recorded.messages.map((m) => [m.level, m.text]), [["info", "Talpy Den: Live mode: off."]]);
  assert.equal(refreshed, 1);

  fake.answer.pick = () => undefined;
  await liveModeHere(fake, backend, dash);
  assert.deepEqual([calls.length, refreshed], [3, 1], "Escape: only the status asked");

  fake.answer.pick = (items) => items[0];
  result = { ok: false, message: "no settings.json to change" };
  await liveModeHere(fake, backend, dash);
  assert.deepEqual(calls.at(-1), ["--live", "on"]);
  assert.deepEqual(fake.recorded.messages.at(-1), { level: "error", text: "Talpy Den: no settings.json to change", options: undefined, actions: [] });
});
