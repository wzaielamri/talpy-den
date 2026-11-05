import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { test } from "node:test";
import { cleanupSettingOf, cleanupStatusOf, cleanupText, keptText, oldChatsDetail, overridesNote, riskText, runsLines, sizeText, SETTING_OF } from "../src/oldChats";

const when = (ms: number) => `t${ms}`;

test("what a run deletes says each kind once, its size, and plans to the Trash", () => {
  assert.equal(cleanupText({}), "nothing");
  assert.equal(cleanupText({ chats: 3, backgroundChats: 1, files: 12, plans: 1, bytes: 432 * 1024 * 1024 }),
    "3 chats, 1 background chat, 12 other files (432.0 MB), 1 plan to the Trash");
  assert.equal(cleanupText({ plans: 2 }), "2 plans to the Trash");
  assert.equal(keptText({ keptChats: 1 }), "1 old starred, open or queued one stays");
  assert.equal(keptText({}), "");
  assert.deepEqual([sizeText(500), sizeText(3 * 1024 ** 3)], ["0 KB", "3.0 GB"]);
});

test("the choice alone, and what Claude's cleanup would delete of what Talpy Den keeps", () => {
  assert.deepEqual(cleanupSettingOf({ ok: true, mode: "talpy", days: 9, pending: false }), { mode: "talpy", days: 9 });
  assert.equal(cleanupSettingOf({ ok: true, mode: "x" }), null);
  assert.equal(riskText({ chats: 2, plans: 1 }), "2 chats you keep and 1 plan you keep");
  assert.equal(riskText({ chats: 0, plans: 3 }), "3 plans you keep");
  const st = cleanupStatusOf({ ok: true, mode: "talpy", days: 30, preview: {}, claudeRisk: { days: 45, chats: 1, plans: 0 } })!;
  assert.deepEqual(st.claudeRisk, { days: 45, chats: 1, plans: 0 });
  assert.equal(cleanupStatusOf({ ok: true, mode: "claude", days: 30, preview: {}, claudeRisk: null })!.claudeRisk, null);
});

test("settings that still have Claude Code clean up are told, a host's on its line", () => {
  const st = cleanupStatusOf({
    ok: true, mode: "talpy", days: 30, preview: {}, previewDays: 30, claudeDays: [],
    overrides: [{ path: "~/repo/.claude/settings.json", days: 7 }, { nope: 1 }],
    runs: { lab: { ok: true, at: 5, mode: "talpy", overrides: [{ path: "/etc/claude-code/managed-settings.json", days: 14 }] } },
  })!;
  assert.deepEqual(st.overrides, [{ path: "~/repo/.claude/settings.json", days: 7 }]);
  assert.match(overridesNote(st.overrides), /^These settings still have Claude Code delete old chats.*~\/repo\/\.claude\/settings\.json \(7 days\)/);
  assert.equal(overridesNote([]), "");
  assert.deepEqual(runsLines(st, when), ["lab, t5: nothing · Claude Code still cleans up by /etc/claude-code/managed-settings.json (14 days)"]);
  assert.match(oldChatsDetail(st, when), /These settings still have/);
});

test("cleanup.py's status is read only when it's one", () => {
  assert.equal(cleanupStatusOf(null), null);
  assert.equal(cleanupStatusOf({ ok: false, message: "x" }), null);
  assert.equal(cleanupStatusOf({ ok: true, mode: "other", preview: {} }), null);
  const st = cleanupStatusOf({ ok: true, mode: "talpy", days: 21, preview: { chats: 2 }, previewDays: 21, runs: {}, claudeDays: [{ account: "work", days: 30 }, null] })!;
  assert.deepEqual([st.mode, st.days, st.maxDays, st.claudeDays.length, SETTING_OF[st.mode]], ["talpy", 21, 3649, 1, "talpyDen"]);
});

test("each place's last run, this computer first, a host out of reach by why", () => {
  const st = cleanupStatusOf({
    ok: true, mode: "talpy", days: 30, preview: {}, previewDays: 30, claudeDays: [],
    runs: { "lab": { ok: false, at: 2, message: "lab didn't answer", chats: 4 }, "": { ok: true, at: 1, mode: "talpy", chats: 1, bytes: 2048, keptPlans: 1 },
      "docker:web": { ok: true, at: 3, mode: "claude", raised: false } },
  })!;
  assert.deepEqual(runsLines(st, when), [
    "This computer, t1: 1 chat (2 KB); 1 old starred, open or queued one stays",
    "docker:web, t3: Claude Code's cleanup is back",
    "lab, t2: lab didn't answer",
  ]);
  assert.match(oldChatsDetail(st, when), /^Talpy Den deletes the chats you haven't used for 30 days once a day;.*next run would delete nothing here\.\n\nThis computer/s);
  st.mode = "claude";
  st.claudeDays = [{ account: "work", days: 30 }, { account: "personal", days: 45 }];
  assert.match(oldChatsDetail(st, when), /cleanupPeriodDays \(work: 30 days, personal: 45 days\): starred or not, for good\./);
});

test("the settings, the command and the backend's script are declared", () => {
  const pkg = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "..", "package.json"), "utf8"));
  const props = Object.assign({}, ...pkg.contributes.configuration.map((c: any) => c.properties));
  assert.deepEqual(props["talpyDen.oldChats"].enum, ["claude", "talpyDen"]);
  assert.equal(props["talpyDen.oldChats"].default, "claude"); // (Claude Code's own, unless you choose)
  assert.deepEqual([props["talpyDen.oldChatsDays"].minimum, props["talpyDen.oldChatsDays"].maximum], [1, 3649]);
  assert.ok(pkg.contributes.commands.some((c: any) => c.command === "talpyDen.oldChats"));
});
