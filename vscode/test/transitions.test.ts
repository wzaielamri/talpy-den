import assert from "node:assert/strict";
import { test } from "node:test";
import { demoState } from "../src/shared/demo";
import type { Group, SessionState } from "../src/shared/types";
import { askText, askTitle, TransitionTracker } from "../src/transitions";

const NOW = 1_800_000_000_000;
const OPTS = { notifyWaiting: true, notifyDone: true, notifyDoneMinSeconds: 30 };

function oneChat(state: SessionState, since: number, reason = ""): Group[] {
  const g = demoState(NOW).status!.groups[0];
  const s = { ...g.sessions[0], key: "chat-1", name: "Fix the parser", state, since, reason };
  return [{ ...g, sessions: [s] }];
}

test("the first poll only learns; later changes notify", () => {
  const t = new TransitionTracker();
  assert.deepEqual(t.track("", oneChat("working", NOW - 60000), NOW, undefined, OPTS).notices, []);
  const done = t.track("", oneChat("idle", NOW + 120000), NOW + 120000, undefined, OPTS);
  assert.equal(done.notices.length, 1);
  assert.equal(done.notices[0].kind, "done");
  assert.match(done.notices[0].title, /finished/);
  assert.match(done.notices[0].body, /Took 3m/);
  assert.equal(done.sound, "done");
  assert.deepEqual(done.petEvents.map((e) => e.kind), ["done"]);
});

test("a short turn makes the pet happy but sends no notification", () => {
  const t = new TransitionTracker();
  t.track("", oneChat("working", NOW), NOW, undefined, OPTS);
  const r = t.track("", oneChat("idle", NOW + 5000), NOW + 5000, undefined, OPTS);
  assert.equal(r.notices.length, 0);
  assert.equal(r.sound, "");
  assert.equal(r.petEvents.length, 1);
});

test("waiting notifies at most once a minute per chat, and failures sound different", () => {
  const t = new TransitionTracker();
  t.track("", oneChat("working", NOW), NOW, undefined, OPTS);
  const w = t.track("", oneChat("waiting", NOW + 1000), NOW + 1000, undefined, OPTS);
  assert.equal(w.notices[0].kind, "waiting");
  assert.equal(w.sound, "waiting");
  t.track("", oneChat("working", NOW + 2000), NOW + 2000, undefined, OPTS);
  assert.equal(t.track("", oneChat("waiting", NOW + 3000), NOW + 3000, undefined, OPTS).notices.length, 0);
  t.track("", oneChat("working", NOW + 4000), NOW + 4000, undefined, OPTS);
  const failed = t.track("", oneChat("done", NOW + 90000, "failed"), NOW + 90000, undefined, OPTS);
  assert.equal(failed.sound, "failed");
  assert.match(failed.notices[0].title, /failed/);
});

test("the next permission prompt within a minute is told, the same one isn't told again", () => {
  const t = new TransitionTracker();
  const asks = (state: SessionState, at: number, request: string | null, line = "Bash: ls") => {
    const groups = oneChat(state, at);
    groups[0].sessions[0] = { ...groups[0].sessions[0], permission: state !== "waiting" ? null
      : { tool: "Bash", line, command: line.slice(6), file: "", diff: [], always: "", request, toolUse: null, answer: request ? "hook" : "" } };
    return t.track("", groups, at, undefined, OPTS);
  };
  asks("working", NOW, null);
  assert.equal(asks("waiting", NOW + 1000, "r1").notices.length, 1);
  asks("working", NOW + 2000, null);
  // you allowed it; 20 s later it asks for the next command
  const next = asks("waiting", NOW + 20000, "r2", "Bash: npm test");
  assert.deepEqual([next.notices.length, next.sound, next.petEvents.length], [1, "waiting", 1]);
  assert.equal(asks("waiting", NOW + 22000, "r2", "Bash: npm test").notices.length, 0);
  // it flaps: the same prompt isn't told again within the minute, then or a poll later
  asks("working", NOW + 24000, null);
  assert.equal(asks("waiting", NOW + 26000, "r2", "Bash: npm test").notices.length, 0);
  assert.equal(asks("waiting", NOW + 28000, "r2", "Bash: npm test").notices.length, 0);
});

test("an SSH host's chats are tracked apart and name the host", () => {
  const t = new TransitionTracker();
  t.track("ssh:build-server", oneChat("working", NOW), NOW, "build-server", OPTS);
  const r = t.track("ssh:build-server", oneChat("waiting", NOW + 1000), NOW + 1000, "build-server", OPTS);
  assert.match(r.notices[0].body, /build-server/);
  const s = oneChat("waiting", 0)[0].sessions[0];
  assert.equal(r.petEvents[0].key, `ssh:build-server|${s.profileDir}/${s.chatId}`);
});

test("a plan limit that drops a lot is celebrated as a reset", () => {
  const t = new TransitionTracker();
  const groups = demoState(NOW).status!.groups;
  assert.deepEqual(t.resets("", groups), []);
  const reset = groups.map((g) => ({ ...g, limits: { ...g.limits!, windows: g.limits!.windows.map((w) => ({ ...w, pct: 2 })) } }));
  assert.deepEqual(t.resets("", reset).map((e) => e.text), ["5h limit reset!", "7d limit reset!"]);
});

test("finished turns are reported with how long they took", () => {
  const t = new TransitionTracker();
  t.track("ssh:lab", oneChat("working", NOW - 60000), NOW, "lab", OPTS);
  const r = t.track("ssh:lab", oneChat("done", NOW + 60000, "failed"), NOW + 60000, "lab", OPTS);
  assert.equal(r.finished.length, 1);
  const s = oneChat("done", 0)[0].sessions[0];
  assert.deepEqual([r.finished[0].id, r.finished[0].host, r.finished[0].took], [`ssh:lab|${s.profileDir}/${s.chatId}`, "lab", 120000]);
});

test("a turn a usage limit or the login broke off isn't finished", () => {
  const limit = { kind: "limit" as const, window: "five_hour", text: "You've hit your session limit · resets 4am (Europe/Berlin)", at: NOW };
  const login = { ...limit, kind: "login" as const, window: null, text: "Login expired · Please run /login" };
  const t = new TransitionTracker();
  const g = demoState(NOW).status!.groups[0];
  const at = (since: number, rows: [string, SessionState, object?][]) => [{
    ...g, sessions: rows.map(([id, state, extra]) => ({ ...g.sessions[0], key: id, chatId: id, sessionId: id, name: id, state, since, reason: "", stopped: null, permission: null, ...extra })),
  }];
  const kept = { ...OPTS, kept: (chat: string) => chat === "a" };
  t.track("", at(NOW, [["a", "working"], ["b", "working"], ["c", "working"], ["d", "working"], ["e", "working"]]), NOW, undefined, kept);
  // a: its limit shows at once; b: the transcript isn't written yet; c (in the
  // background) says it waits; d: finished; e: the login expired
  let r = t.track("", at(NOW + 60000, [["a", "idle", { stopped: limit }], ["b", "idle"], ["c", "waiting"], ["d", "idle"],
    ["e", "idle", { stopped: login }]]), NOW + 60000, undefined, kept);
  assert.deepEqual(r.notices.map((n) => [n.session.name, n.kind, n.title]), [["a", "stopped", "a hit the usage limit"],
    ["b", "done", "b finished"], ["c", "waiting", "c needs your input"], ["d", "done", "d finished"],
    ["e", "stopped", "e stopped: the login expired"]]);
  assert.match(r.notices[0].body, /^You've hit your session limit · resets 4am \(Europe\/Berlin\) · It goes on by itself after the reset · Took 1m/);
  assert.deepEqual(r.petEvents.map((e) => e.kind), ["limit", "done", "waiting", "done", "stopped"]);
  assert.deepEqual(r.finished.map((f) => [f.session.name, f.stop]), [["a", "limit"], ["b", ""], ["d", ""], ["e", "login"]]);
  // a poll later b's and c's limits show: they're said so instead
  const stoppedAll = (d: object | undefined): [string, SessionState, object?][] =>
    [["a", "idle", { stopped: limit }], ["b", "idle", { stopped: limit }], ["c", "idle", { stopped: limit }], ["d", "idle", d], ["e", "idle", { stopped: login }]];
  r = t.track("", at(NOW + 60000, stoppedAll(undefined)), NOW + 62000, undefined, kept);
  assert.deepEqual(r.notices.map((n) => [n.session.name, n.kind]), [["b", "stopped"], ["c", "stopped"]]);
  assert.deepEqual(r.finished.map((f) => [f.session.name, f.stop]), [["b", "limit"], ["c", "limit"]]);
  assert.equal(r.sound, "failed");
  // only one poll later: a limit that shows up after that is another turn's
  assert.deepEqual(t.track("", at(NOW + 60000, stoppedAll({ stopped: limit })), NOW + 64000, undefined, kept).notices, []);
});

test("a chat keeps its notifications while its row changes, and a chat listed twice counts once", () => {
  const t = new TransitionTracker();
  const row = (state: SessionState, suffix: string, since: number) => {
    const g = demoState(NOW).status!.groups[0];
    return { ...g.sessions[0], key: `${g.sessions[0].profileDir}/job-1/${suffix}`, chatId: "job-1", sessionId: "job-1", state, since };
  };
  const g = demoState(NOW).status!.groups[0];
  t.track("", [{ ...g, sessions: [row("working", "live", NOW - 120000)] }], NOW, undefined, OPTS);
  // its process ended as it finished: the row is the job's record now (…/job)
  const done = t.track("", [{ ...g, sessions: [row("done", "job", NOW)] }], NOW + 2000, undefined, OPTS);
  assert.deepEqual(done.notices.map((n) => n.kind), ["done"]);
  const twice = [{ ...g, sessions: [row("waiting", "live", NOW), row("idle", "job", NOW)] }];
  t.track("", twice, NOW + 4000, undefined, OPTS);
  assert.deepEqual(t.track("", twice, NOW + 70000, undefined, OPTS).notices, [], "not an alert every minute");
});

test("a chat waiting on its plan says so, as Plasma's notification", () => {
  const g = demoState(NOW).status!.groups[0];
  const s = { ...g.sessions[0], name: "Fix the parser", permission: { answer: "", line: "ExitPlanMode", command: "", plan: { title: "Speed up", text: "", file: "", cut: false } } };
  assert.equal(askTitle(s as never), "Fix the parser has a plan ready");
  assert.equal(askText(s as never), "Speed up");
  const untitled = { ...s, permission: { ...s.permission, plan: { ...s.permission.plan, title: "" } } };
  assert.equal(askText(untitled as never), "Approve it to start, or keep planning.");
  // (an MCP tool's: what it sends where, not only its name)
  const mcp = { ...s, permission: { answer: "hook", line: "slack: send_message", command: "", file: "", args: ["channel: #x", "text: a\nb"] } };
  assert.equal(askText(mcp as never), "slack: send_message · channel: #x · text: a b");
});
