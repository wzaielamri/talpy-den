import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { test } from "node:test";
import { AwayWatch } from "../src/away";
import { Notifier } from "../src/notify";
import { useSettingsHost } from "../src/settings";
import { demoState } from "../src/shared/demo";
import type { PermissionAsk, Session } from "../src/shared/types";
import { FakeHost } from "./fakeHost";

// The notifier talks to its host alone (no vscode): a permission prompt's buttons and text, and which
// window leads
const setup = () => {
  process.env.XDG_CACHE_HOME = fs.mkdtempSync(path.join(os.tmpdir(), "talpy-den-notify-core-"));
  const fake = new FakeHost();
  useSettingsHost(fake);
  const notifier = new Notifier(fake, { sound() {} } as never, () => undefined);
  const ask = (p: Partial<PermissionAsk>): Session => ({
    ...demoState(Date.now()).status!.groups[0].sessions[0], state: "waiting", name: "deploy",
    permission: { tool: "Bash", line: "Bash: npm publish", command: "npm publish", file: "", diff: [], always: "", request: "r1", answer: "hook", ...p },
  }) as Session;
  const notify = async (n: Notifier, s: Session) => {
    n.handle({ notices: [{ key: s.key, kind: "waiting", title: "deploy asks", body: "", session: s }], petEvents: [], sound: "", finished: [] });
    await new Promise((r) => setTimeout(r, 10));
  };
  return { fake, notifier, ask, notify };
};

test("a permission prompt's notification lists Allow once, Always allow, Deny, Deny with a note…", async () => {
  const { fake, notifier, ask, notify } = setup();
  const answers: [string, string][] = [];
  notifier.panes = { answer: async (_c: unknown, d: string, _s: unknown, n = "") => (answers.push([d, n]), { ok: true, message: "" }) } as never;
  await notify(notifier, ask({}));
  await notify(notifier, ask({ always: "Bash(npm publish:*) in this project (.claude/settings.local.json)" }));
  assert.deepEqual(fake.recorded.messages.map((m) => [m.level, m.text, m.actions]), [
    ["warning", "deploy asks — ", ["Allow once", "Deny", "Deny with a note…", "Open"]],
    ["warning", "deploy asks —  · Always allow: Bash(npm publish:*) in this project (.claude/settings.local.json)",
      ["Allow once", "Always allow", "Deny", "Deny with a note…", "Open"]],
  ]);
  fake.answer.message = () => "Deny";
  await notify(notifier, ask({}));
  assert.deepEqual(answers, [["deny", ""]]);
  notifier.dispose();
});

test("an unfocused window that leads notifies; a focused one claims the lead", () => {
  const { fake, notifier } = setup();
  assert.equal(fake.focus.focused, false);
  assert.equal(notifier.isLeader(), true, "no one leads yet: this window takes it");
  // another window leads (a live process that isn't this one): this one doesn't speak until it is focused
  const other = fs.readFileSync(path.join(process.env.XDG_CACHE_HOME!, "talpy-den", "vscode-notify.json"), "utf8");
  assert.equal(JSON.parse(other).pid, process.pid);
  fs.writeFileSync(path.join(process.env.XDG_CACHE_HOME!, "talpy-den", "vscode-notify.json"), JSON.stringify({ pid: process.ppid, at: Date.now() }));
  assert.equal(notifier.isLeader(), false);
  fake.setFocused(true);
  assert.equal(notifier.isLeader(), true);
  notifier.dispose();
});

test("the host's use state drives the away watch: used at start marks it; a window in use again tells it came back", () => {
  const { fake } = setup();
  const backs: number[] = [];
  const watch = new AwayWatch(fake, (now) => backs.push(now));
  fake.setActive(true); // (the first use of a window that started in the background: nothing to sum up)
  assert.deepEqual(backs, []);
  fake.setActive(false);
  assert.notEqual(watch.tracker.since, null, "left");
  fake.setActive(true);
  assert.equal(backs.length, 1, "back");
  watch.dispose();
});
