// Chats a usage limit stopped, Claude's recaps, permission modes and plans:
// how the model reads the backend's new fields, and the notices when a limit
// resets.
import assert from "node:assert/strict";
import { test } from "node:test";
import { demoState } from "../../core/src/shared/demo";
import {
  countStates,
  findPlan,
  handoverTarget,
  hasPeek,
  headlineText,
  modeText,
  peekLine,
  stateText,
  stopText,
  summaryText,
  toLocalClock,
} from "../../core/src/shared/model";
import type { Group, Session, Status, Stop } from "../../core/src/shared/types";
import "./useHost";
import { mergeChanges, TransitionTracker } from "../src/transitions";

const NOW = 1_800_000_000_000;
const MIN = 60000;
const OPTS = { notifyWaiting: true, notifyDone: true, notifyDoneMinSeconds: 30 };

function limit(over = false, resetsAt: number | null = NOW + 41 * MIN): Stop {
  return { kind: "limit", window: "five_hour", text: "You've hit your session limit · resets 4:10pm", at: NOW - 10 * MIN, resetsAt, over };
}

function chat(partial: Partial<Session>): Session {
  const base = demoState(NOW).status!.groups[0].sessions[0];
  return { ...base, key: "c1", sessionId: "c1", chatId: "c1", state: "idle", agents: null, tasks: null, ...partial };
}

function account(id: string, shareProfile: string, pct: number | null, profileKeys = [shareProfile]): Group {
  const g = demoState(NOW).status!.groups[0];
  return {
    ...g,
    id,
    title: id,
    shareProfile,
    profileKeys,
    limits: pct === null ? null : { updatedAt: NOW, windows: [{ key: "five_hour", label: "5h", pct, resetsAt: NOW + 3600000, reset: false }] },
  };
}

test("a chat a usage limit stopped: its state, its line, when the limit resets", () => {
  const s = chat({ stopped: limit() });
  assert.equal(stateText(s, NOW), "Limit · resets in 41m");
  assert.deepEqual(peekLine(s), { kind: "stopped", text: "You've hit your session limit · resets 4:10pm" });
  assert.equal(stateText(chat({ stopped: limit(false, NOW + 30000) }), NOW), "Limit · resets in <1m");
  assert.equal(stateText(chat({ stopped: limit(false, null) }), NOW), "Hit a usage limit");
  const freed = chat({ stopped: limit(true, null) });
  assert.equal(stateText(freed, NOW), "Limit reset · go on");
  assert.match(peekLine(freed)!.text, /has reset/);
  assert.equal(stateText(chat({ stopped: { kind: "login", window: null, text: "Login expired · Please run /login", at: NOW } }), NOW), "Login expired");
  assert.match(stopText({ kind: "login", window: null, text: "", at: null }), /login expired/i);
});

test("a chat that waits for its limit doesn't count as your turn, nor as done", () => {
  const stopped = chat({ stopped: limit() });
  const g = { ...demoState(NOW).status!.groups[0], sessions: [stopped, chat({ key: "c2", chatId: "c2" }), { ...stopped, key: "c3", state: "done" as const }] };
  const counts = countStates([g]);
  assert.deepEqual(counts, { waiting: 0, working: 0, idle: 1, done: 0, limit: 2 });
  assert.equal(summaryText(counts), "1 idle · 2 at the usage limit");
  assert.equal(headlineText({ status: demoState(NOW).status, errorText: "" }, counts), "Your turn in 1 chat");
  assert.equal(headlineText({ status: demoState(NOW).status, errorText: "" }, { ...counts, idle: 0 }), "2 chats wait for their usage limit");
  // once the limit reset, it's your turn again
  assert.equal(countStates([{ ...g, sessions: [chat({ stopped: limit(true, null) })] }]).idle, 1);
});

test("Claude's recap is the line of an idle chat, after what stopped it and a job's result", () => {
  const recap = { text: "You asked me to fix it; it's fixed.\nNext step: say whether to open a pull request.", at: NOW };
  const peek = { activity: "", prompt: "fix it", reply: "Fixed.", replyLine: "Fixed.", at: NOW, recap };
  assert.deepEqual(peekLine(chat({ peek })), { kind: "recap", text: "Recap: You asked me to fix it; it's fixed." });
  assert.equal(peekLine(chat({ peek, stopped: limit() }))!.kind, "stopped");
  assert.equal(peekLine(chat({ peek, state: "done", detail: "All good" }))!.kind, "result");
  assert.equal(peekLine(chat({ peek: { ...peek, recap: null } }))!.kind, "reply");
  assert.ok(hasPeek({ peek: { ...peek, prompt: "", reply: "" }, tasks: null, changes: null }));
});

test("continuing a stopped chat on another account with room left", () => {
  const here = account("work", ".claude-work", 100);
  const full = account("full", ".claude-full", 97);
  const roomy = account("personal", ".claude-personal", 40);
  const roomier = account("spare", ".claude-spare", 10);
  const unknown = account("new", ".claude-new", null);
  const s = chat({ profileDir: ".claude-work", stopped: limit(), pid: 4242 });
  assert.equal(handoverTarget(s, [here, full, roomy, roomier, unknown])!.shareProfile, ".claude-spare");
  assert.deepEqual(handoverTarget(s, [here, unknown]), { title: "new", shareProfile: ".claude-new", pct: null, label: "" });
  assert.equal(handoverTarget(s, [here, full]), null); // no room anywhere
  // not when it's over, when the chat isn't idle, nor for a Claude Code panel or a session continuing another chat
  assert.equal(handoverTarget({ ...s, stopped: limit(true, null) }, [here, roomy]), null);
  assert.equal(handoverTarget({ ...s, state: "working" }, [here, roomy]), null);
  assert.equal(handoverTarget({ ...s, entrypoint: "claude-vscode" }, [here, roomy]), null);
  assert.equal(handoverTarget({ ...s, sessionId: "other" }, [here, roomy]), null);
  // a finished one (no process) can go, whatever its rows say
  assert.equal(handoverTarget({ ...s, pid: null, state: "done", sessionId: "other" }, [here, roomy])!.title, "personal");
});

test("permission modes as their tags say them", () => {
  assert.equal(modeText("plan"), "Plan mode");
  assert.equal(modeText("bypassPermissions"), "Bypass permissions");
  assert.equal(modeText("default"), "Manual mode");
  assert.equal(modeText(undefined), "");
  assert.equal(modeText("somethingNew"), "somethingNew");
});

test("a plan the page names is the extension's own, found by account and key", () => {
  const state = demoState(NOW);
  const found = findPlan(state.status, state.hosts, undefined, "demo-personal", "demo-plan-1");
  assert.equal(found?.plan.title, "Release 2.0");
  assert.equal(found?.group.id, "demo-personal");
  assert.equal(findPlan(state.status, state.hosts, undefined, "demo-personal", "nope"), null);
  assert.equal(findPlan(state.status, state.hosts, "build-server", "demo-personal", "demo-plan-1"), null);
  assert.equal(findPlan(state.status, state.hosts, 7, "demo-personal", "demo-plan-1"), null);
});

test("a host's stops, recaps and plans come onto this computer's clock", () => {
  const g = demoState(NOW).status!.groups[0];
  const status: Status = {
    ...demoState(NOW).status!,
    groups: [
      {
        ...g,
        sessions: [chat({ stopped: limit(), peek: { activity: "", prompt: "", reply: "", replyLine: "", at: NOW, recap: { text: "r", at: NOW } } })],
        recent: [{ ...g.recent[0], stopped: limit(), recap: { text: "r", at: NOW } }],
      },
    ],
  };
  const shifted = toLocalClock(status, 60000).groups[0];
  assert.equal(shifted.sessions[0].stopped!.resetsAt, NOW + 41 * MIN + 60000);
  assert.equal(shifted.sessions[0].peek!.recap!.at, NOW + 60000);
  assert.equal(shifted.recent[0].stopped!.at, NOW - 10 * MIN + 60000);
  assert.equal(shifted.plans![0].updatedAt, g.plans![0].updatedAt + 60000);
});

test("a notice when the limit that stopped chats resets: once, per account", () => {
  const t = new TransitionTracker();
  const g = (over: boolean) => [{ ...demoState(NOW).status!.groups[0], sessions: [chat({ name: "Parser", stopped: limit(over, over ? null : NOW + MIN) })] }];
  assert.deepEqual(t.limitResets("", g(false), undefined, OPTS).notices, []); // the first poll only learns
  assert.deepEqual(t.limitResets("", g(false), undefined, OPTS).notices, []);
  const freed = t.limitResets("", g(true), undefined, OPTS);
  assert.equal(freed.notices.length, 1);
  assert.equal(freed.notices[0].title, "personal: the usage limit reset");
  assert.equal(freed.notices[0].body, "Parser can go on");
  assert.equal(freed.notices[0].kind, "reset"); // (its own kind: no Reply… to the first chat only)
  assert.equal(freed.sound, "done");
  assert.deepEqual(freed.petEvents.map((e) => e.kind), ["reset"]);
  assert.deepEqual(t.limitResets("", g(true), undefined, OPTS).notices, []); // once
  // with "finished" notifications off: the pet cheers, no notice
  const quiet = new TransitionTracker();
  quiet.limitResets("ssh:lab", g(false), "lab", OPTS);
  const r = quiet.limitResets("ssh:lab", g(true), "lab", { ...OPTS, notifyDone: false });
  assert.deepEqual([r.notices.length, r.petEvents.length], [0, 1]);
  // merged with the other changes of a poll: the more urgent sound wins
  assert.equal(mergeChanges({ notices: [], petEvents: [], sound: "waiting", finished: [] }, freed).sound, "waiting");
});
