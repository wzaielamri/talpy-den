// Tasks waiting for the usage limit, chats changing the same files, and the
// widgets' link to a plan or a subagent's run in the Markdown preview.
import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { test } from "node:test";
import { markdownLinkFile } from "../src/agentRun";
import { demoState } from "../src/shared/demo";
import { findMemory, goOnAt, laterAt, laterDays, limitReset, overlapText, queuedChat, queuedFor, queuedWhat, startText } from "../src/shared/model";
import type { Group, QueuedTask, Session } from "../src/shared/types";
import { TransitionTracker } from "../src/transitions";
import { planPath } from "../src/planReview";

const NOW = 1_800_000_000_000;
const OPTS = { notifyWaiting: true, notifyDone: true, notifyDoneMinSeconds: 30 };

function group(pct: number, resetsAt: number, sessions: Session[] = []): Group {
  const g = demoState(NOW).status!.groups[0];
  return { ...g, sessions, limits: { updatedAt: NOW, windows: [{ key: "five_hour", label: "5h", pct, resetsAt, reset: false }] } };
}

test("a task can wait for the limit of an account that's at it", () => {
  assert.deepEqual(limitReset(group(100, NOW + 3600000), NOW), { at: NOW + 3600000, label: "5h" });
  assert.equal(limitReset(group(60, NOW + 3600000), NOW), null);
  assert.equal(limitReset(group(100, NOW - 1000), NOW), null); // reset already
  // no numbers, but a chat the limit stopped says when
  const s = { ...demoState(NOW).status!.groups[0].sessions[0], stopped: { kind: "limit" as const, window: "five_hour", text: "", at: NOW, resetsAt: NOW + 60000, over: false } };
  assert.equal(limitReset({ ...group(0, NOW + 1), limits: null, sessions: [s] }, NOW)!.at, NOW + 60000);
});

test("a chat a usage limit stopped can go on by itself after the reset", () => {
  const stopped = { kind: "limit" as const, window: "five_hour", text: "", at: NOW, resetsAt: NOW + 3600000, over: false };
  const row = { ...demoState(NOW).status!.groups[0].sessions[0], sessionId: "c1", chatId: "c1", pid: 42, state: "idle" as const, entrypoint: "cli", stopped };
  assert.equal(goOnAt(row), NOW + 3660000); // a minute after the reset
  assert.equal(goOnAt({ sessionId: "c1", stopped }), NOW + 3660000); // a recent chat
  assert.equal(goOnAt({ ...row, entrypoint: "claude-vscode" }), 0); // its tab can't be ended
  assert.equal(goOnAt({ ...row, state: "working" }), 0); // at work again
  assert.equal(goOnAt({ ...row, stopped: { ...stopped, over: true } }), 0); // it can go on now
  assert.equal(goOnAt({ ...row, stopped: { ...stopped, resetsAt: null } }), 0); // when isn't known
  const t: QueuedTask = {
    id: "q", host: "lab", profile: ".claude", account: "", folder: "/srv", folderShort: "/srv", prompt: "", plan: null,
    planProfile: null, planTitle: "", startAt: NOW, createdAt: NOW, error: "", due: false, chat: "c1", name: "Fix it",
  };
  assert.equal(queuedWhat(t), "Go on with “Fix it”");
  // named as the chat is called now: its row's name, else as queued
  const g = demoState(NOW).status!.groups[0];
  const renamed = { ...g.sessions[0], chatId: "c1", sessionId: "c1-own", name: "Shared creature code tug" };
  assert.equal(queuedWhat(t, { groups: [{ ...g, sessions: [renamed] }] }), "Go on with “Shared creature code tug”");
  assert.equal(queuedWhat(t, { groups: [{ ...g, sessions: [] }] }), "Go on with “Fix it”");
  assert.equal(queuedChat({ queue: [t] } as never, "c1", "lab"), t);
  assert.equal(queuedChat({ queue: [t] } as never, "c1"), null); // (that's the host's chat)
  assert.equal(queuedChat({ queue: [{ ...t, chat: null }] } as never, "c1", "lab"), null);
});

test("an account's memories are found by their key", () => {
  const s = demoState(NOW);
  const g = s.status!.groups[0];
  assert.equal(findMemory(s.status, s.hosts, undefined, g.id, "demo-mem-1")?.memory.name, "test-command");
  assert.equal(findMemory(s.status, s.hosts, undefined, g.id, "nope"), null);
  assert.equal(findMemory(s.status, s.hosts, 42, g.id, "demo-mem-1"), null);
});

test("feedback goes with the plan files of Claude's config folders", () => {
  const file = "/home/alice/.claude-work/plans/calm-red-owl.md";
  assert.deepEqual(planPath(file, [], "/home/alice"), { slug: "calm-red-owl", file });
  assert.equal(planPath("/home/alice/.claude/plans/calm-red-owl.md", [], "/home/alice")?.slug, "calm-red-owl");
  assert.equal(planPath("/home/alice/notes/plans/calm-red-owl.md", [], "/home/alice"), null); // not Claude's
  assert.equal(planPath("/srv/claude/plans/a.md", ["/srv/claude"], "/home/alice")?.slug, "a"); // a config folder of the settings
  assert.equal(planPath("/home/alice/.claude-work/plans/notes.txt", [], "/home/alice"), null);
});

test("a task can start later, at a day and time you pick", () => {
  const noon = new Date(2026, 9, 21, 12, 0); // a Wednesday
  assert.deepEqual(laterDays(noon).slice(0, 2), ["Today", "Tomorrow"]);
  assert.equal(laterDays(noon).length, 7);
  assert.equal(laterAt(0, "14:30", noon), new Date(2026, 9, 21, 14, 30).getTime());
  assert.equal(laterAt(0, "1430", noon), new Date(2026, 9, 21, 14, 30).getTime());
  assert.equal(laterAt(1, "9", noon), new Date(2026, 9, 22, 9, 0).getTime());
  assert.equal(laterAt(1, "930", noon), new Date(2026, 9, 22, 9, 30).getTime());
  assert.equal(laterAt(0, "9:30", noon), 0); // passed
  assert.equal(laterAt(0, "25:00", noon), 0);
  assert.equal(laterAt(0, "soon", noon), 0);
  assert.match(startText(new Date(2026, 9, 21, 14, 30).getTime(), noon.getTime()), /^\d\d:\d\d|^\d{1,2}:\d\d/);
  assert.match(startText(new Date(2026, 9, 22, 9, 0).getTime(), noon.getTime()), /^tomorrow /);
  assert.ok(!startText(new Date(2026, 9, 24, 9, 0).getTime(), noon.getTime()).startsWith("tomorrow"));
});

test("an account's queued tasks: on its machine, by its profiles", () => {
  const task = (id: string, host: string, profile: string): QueuedTask => ({
    id, host, profile, account: "", folder: "/srv", folderShort: "/srv", prompt: "go", plan: null, planProfile: null,
    planTitle: "", startAt: NOW, createdAt: NOW, error: "", due: false,
  });
  const status = { queue: [task("a", "", ".claude"), task("b", "lab", ".claude"), task("c", "", ".claude-work")] };
  assert.deepEqual(queuedFor(status, { profileKeys: [".claude"] }).map((t) => t.id), ["a"]);
  assert.deepEqual(queuedFor(status, { host: "lab", profileKeys: [".claude"] }).map((t) => t.id), ["b"]);
  assert.deepEqual(queuedFor(null, { profileKeys: [".claude"] }), []);
});

test("two chats changing the same files: a notice once per pair", () => {
  const base = demoState(NOW).status!.groups[0];
  const row = (key: string, name: string, other: string): Session => ({
    ...base.sessions[0], key, name, chatId: key, sessionId: key,
    overlaps: [{ key: other, name: other.toUpperCase(), sessionId: other, profileDir: ".claude", count: 1, files: ["src/x.py"] }],
  });
  const groups = (overlap: boolean): Group[] => [{ ...base, sessions: overlap ? [row("a", "A", "b"), row("b", "B", "a")] : [] }];
  const t = new TransitionTracker();
  assert.deepEqual(t.overlaps("", groups(false), undefined, OPTS).notices, []);
  const r = t.overlaps("", groups(true), undefined, OPTS);
  assert.equal(r.notices.length, 1);
  assert.equal(r.notices[0].title, "Two chats change the same files");
  assert.equal(r.notices[0].body, "A and B: src/x.py");
  assert.equal(r.notices[0].kind, "overlap"); // (its own kind: no prompt's buttons)
  assert.deepEqual(t.overlaps("", groups(true), undefined, OPTS).notices, []);
  assert.equal(overlapText(groups(true)[0].sessions[0].overlaps!), "Also changed by “B”: src/x.py");
  // a chat listed twice (open on two accounts) is one chat: still one notice
  const twice = new TransitionTracker();
  const both = (on: boolean): Group[] => [{ ...base, sessions: on ? [row("a", "A", "b"), { ...row("a2", "A", "b"), chatId: "a" }, row("b", "B", "a")] : [] }];
  twice.overlaps("", both(false), undefined, OPTS);
  assert.equal(twice.overlaps("", both(true), undefined, OPTS).notices.length, 1);
});

test("the widgets' Markdown link opens only their runs and Claude's plans", () => {
  const link = (file: string) => ({ path: "/markdown", query: new URLSearchParams({ path: file }).toString() });
  const home = "/home/me";
  // (a run must be there: its real path is checked, links included)
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "runs-"));
  fs.writeFileSync(path.join(root, "run (ab12).md"), "# Run\n");
  assert.equal(markdownLinkFile(link(`${root}/run (ab12).md`), home, [], root), `${root}/run (ab12).md`);
  assert.equal(markdownLinkFile(link(`${root}/gone.md`), home, [], root), null);
  fs.rmSync(root, { recursive: true });
  assert.equal(markdownLinkFile(link("/home/me/.claude-work/plans/calm-red-owl.md"), home, [], root), "/home/me/.claude-work/plans/calm-red-owl.md");
  assert.equal(markdownLinkFile(link("/home/me/.claude/plans/x.md"), home, [], root), "/home/me/.claude/plans/x.md");
  assert.equal(markdownLinkFile(link("/srv/cfg/plans/x.md"), home, ["/srv/cfg"], root), "/srv/cfg/plans/x.md");
  for (const bad of ["/home/me/notes/x.md", "/home/me/.claude-work/plans/x.txt", "/home/me/.claude-work/plans/../secrets.md",
                     "relative/plans/x.md", "/etc/plans/x.md", "/home/me/.claude-work/x/plans/y.md"])
    assert.equal(markdownLinkFile(link(bad), home, [], root), null, bad);
  assert.equal(markdownLinkFile({ path: "/changes", query: "" }, home, [], root), null);
});
