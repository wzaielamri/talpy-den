import assert from "node:assert/strict";
import { test } from "node:test";
import { demoProjects, demoState } from "../src/shared/demo";
import type { Group, HostState, Session, Status } from "../src/shared/types";
import {
  clockText,
  findProjectChat,
  movedText,
  findProjectMemory,
  findProjectPlan,
  folderIn,
  groupOfProfile,
  listedChats,
  moreText,
  moreTitle,
  pagedTitle,
  pageSizeOf,
  openChatsByProject,
  projectLists,
  recentPage,
  accountNameProblem,
  agentDetailKey,
  agentRunTitle,
  agentSummary,
  allGroups,
  claudeCodeGroup,
  countStates,
  findChatRef,
  focusLists,
  duration,
  formatTokens,
  handoverTarget,
  headlineText,
  heroMood,
  limitReset,
  machineStatus,
  overallState,
  panelWindow,
  petKeyOf,
  planUsageText,
  resetText,
  shareAccounts,
  shareUsage,
  shellQuote,
  toLocalClock,
  stateText,
  summaryText,
  tokensText,
} from "../src/shared/model";

const NOW = 1_800_000_000_000;

test("hosts' accounts come after this computer's, marked with their host", () => {
  const s = demoState(NOW);
  const groups = allGroups(s.status, s.hosts);
  assert.equal(groups.length, 2);
  assert.equal(groups[0].host, undefined);
  assert.equal(groups[1].host, "build-server");
});

test("counts, overall state, headline and mood follow the most urgent chat", () => {
  const s = demoState(NOW);
  const groups = allGroups(s.status, s.hosts);
  const counts = countStates(groups);
  assert.deepEqual(counts, { waiting: 1, working: 2, idle: 0, done: 1, limit: 1 }); // (the idle one waits for its usage limit)
  assert.equal(overallState(groups, counts), "waiting");
  assert.equal(headlineText(s, counts), "1 chat needs you");
  assert.equal(heroMood(s, "waiting", groups), "needs");
  assert.equal(heroMood(s, "working", groups), "agents"); // a demo chat runs subagents
  assert.equal(summaryText(counts), "1 needs input · 2 working · 1 at the usage limit · 1 done");
  assert.equal(heroMood({ status: null, errorText: "" }, "none", []), "loading");
  assert.equal(heroMood({ status: null, errorText: "broken" }, "none", []), "error");
});

test("the focus view lists what waits for you, what finished that you haven't opened and what works; the rest counted", () => {
  const s = demoState(NOW);
  const groups = allGroups(s.status, s.hosts);
  const lists = focusLists(groups);
  assert.deepEqual(lists.needs.map((i) => i.session.state), ["waiting"]);
  assert.equal(lists.working.length, 2);
  assert.ok(lists.working.every((i, k) => k === 0 || (lists.working[k - 1].session.since ?? 0) <= (i.session.since ?? 0)));
  assert.equal(lists.rest.limit, 1);
  assert.equal(lists.needs.length + lists.working.length + lists.finished.length + lists.rest.idle + lists.rest.done + lists.rest.limit,
    countStates(groups).waiting + countStates(groups).working + countStates(groups).idle + countStates(groups).done + countStates(groups).limit);
  assert.ok(lists.usage.length >= 1);
  // a chat that finished a turn you haven't opened is listed (a failed one
  // too, as in the widget), however long ago; once opened, it's only counted
  const g = groups.find((x) => x.sessions.some((y) => y.state === "done"))!;
  const done = g.sessions.find((x) => x.state === "done")!;
  const unopened = focusLists(groups, [petKeyOf(done, g.host)]);
  assert.deepEqual(unopened.finished.map((i) => i.session), [done]);
  assert.equal(unopened.rest.done, lists.rest.done - 1);
  assert.deepEqual(focusLists(groups, ["ssh:gone|.claude/nothing"]).finished, []);
  // a chat listed twice (a shared chat) counts once
  const twice = focusLists([...groups, groups[0]]);
  assert.equal(twice.needs.length + twice.working.length, lists.needs.length + lists.working.length);
});

test("a chat moves between the accounts of its own machine: this computer's or its SSH host's", () => {
  const s = demoState(NOW);
  const host = s.hosts[0];
  assert.equal(machineStatus(s), s.status);
  assert.equal(machineStatus(s, host.name), host.result);
  assert.equal(machineStatus(s, "nowhere"), undefined);
  const two = (status: typeof s.status) => ({
    ...status!,
    canShare: true,
    groups: [{ ...status!.groups[0], shareProfile: ".claude" }, { ...status!.groups[0], id: "w", shareProfile: ".claude-work" }],
  });
  const shared = { ...s, hosts: [{ ...host, result: two(host.result) }] };
  assert.deepEqual(shareAccounts(machineStatus(shared, host.name)).map((g) => g.shareProfile), [".claude", ".claude-work"]);
  assert.deepEqual(shareAccounts(machineStatus(shared)), []); // the demo's own computer can't share
  assert.deepEqual(shareAccounts({ ...two(host.result), canShare: false }), []);
  assert.deepEqual(shareAccounts(null), []);
});

test("finished jobs without a process don't count as running", () => {
  const s = demoState(NOW);
  const g = { ...s.status!.groups[0], sessions: s.status!.groups[0].sessions.filter((x) => x.state === "done") };
  const counts = countStates([g]);
  assert.equal(overallState([g], counts), "none");
  assert.equal(headlineText(s, counts), "1 finished chat to look at");
});

test("the status bar shows the 5-hour usage of the account with an active chat", () => {
  const s = demoState(NOW);
  const best = panelWindow(allGroups(s.status, s.hosts));
  assert.equal(best?.window.key, "five_hour");
  assert.equal(best?.group.id, "demo-personal"); // active, and fresher than the host's
});

// An account with its 5-hour usage as of updatedAt (and an active chat)
function account(id: string, pct: number, updatedAt: number, extra: Partial<Group> = {}): Group {
  return { id, name: id, title: id, plan: null, profiles: [id], profileKeys: [`.claude-${id}`], sessions: [], tokens: null,
           limits: { updatedAt, windows: [{ key: "five_hour", label: "5h", pct, resetsAt: NOW + 3600_000, reset: false }] },
           chatProfile: `.claude-${id}`, shareProfile: null, projects: [], sharedHere: [], recent: [], ...extra } as Group;
}

function machine(groups: Group[]): Status {
  return { ok: true, generatedAt: NOW, overall: "none", counts: { waiting: 0, working: 0, idle: 0, done: 0, limit: 0 }, groups, dismissed: 0, canShare: false, errors: [] };
}

function host(name: string, groups: Group[], current = false): HostState {
  return { name, loading: false, ok: true, error: "", result: machine(groups), updatedAt: NOW, current };
}

test("an account on this computer and on hosts shows its plan usage once, the newest numbers", () => {
  const status = machine([account("work", 80, NOW - 60_000), account("personal", 40, NOW - 9 * 60_000)]);
  const hosts = [host("lab", [account("work", 70, NOW - 3600_000), account("personal", 55, NOW - 30_000)]),
                 host("gpu", [account("team", 10, NOW), account("work", 90, NOW - 120_000)])];
  const shown = shareUsage(status, hosts, "once");
  const [work, personal] = shown.status!.groups;
  assert.equal(work.limits!.windows[0].pct, 80); // its own, the newest
  assert.equal(work.limitsFrom, undefined);
  assert.equal(personal.limits!.windows[0].pct, 55); // lab's, newer than its own
  assert.equal(personal.limitsFrom, "lab");
  const [labWork, labPersonal] = shown.hosts[0].result!.groups;
  assert.ok(labWork.limitsHidden && labWork.limits === null);
  assert.ok(labPersonal.limitsHidden && labPersonal.limits === null);
  const [team, gpuWork] = shown.hosts[1].result!.groups;
  assert.equal(team.limits!.windows[0].pct, 10); // only on gpu: shown there
  assert.ok(!team.limitsHidden);
  assert.ok(gpuWork.limitsHidden);
  assert.equal(status.groups[1].limits!.windows[0].pct, 40); // (the answers themselves stay as they were)
});

test("an account on two hosts only shows its usage on the first, with the other's newer numbers", () => {
  const hosts = [host("lab", [account("team", 10, NOW - 600_000)]), host("gpu", [account("team", 30, NOW)])];
  const shown = shareUsage(null, hosts, "once");
  assert.equal(shown.hosts[0].result!.groups[0].limits!.windows[0].pct, 30);
  assert.equal(shown.hosts[0].result!.groups[0].limitsFrom, "gpu");
  assert.ok(shown.hosts[1].result!.groups[0].limitsHidden);
});

test("plan usage on every host, or on none", () => {
  const status = machine([account("work", 80, NOW - 3600_000)]);
  const hosts = [host("lab", [account("work", 70, NOW), account("team", 10, NOW)])];
  const all = shareUsage(status, hosts, "all");
  assert.equal(all.status, status);
  assert.equal(all.hosts, hosts);
  const none = shareUsage(status, hosts, "none");
  assert.ok(none.hosts[0].result!.groups.every((g) => g.limitsHidden && g.limits === null));
  assert.equal(none.status!.groups[0].limits!.windows[0].pct, 70); // still the account's newest numbers
  assert.equal(none.status!.groups[0].limitsFrom, "lab");
});

test("where an account's usage is hidden, what weighs it still uses the account's numbers", () => {
  const status = machine([account("work", 100, NOW - 60_000), account("personal", 97, NOW)]);
  const lab = { ...machine([account("work", 100, NOW - 600_000, { shareProfile: ".claude-work" }),
                            account("personal", 96, NOW - 600_000, { shareProfile: ".claude-personal" })]), canShare: true };
  const hosts = [{ ...host("lab", []), result: lab }];
  const stopped = { stopped: { kind: "limit", window: "five_hour", text: "", at: NOW, resetsAt: NOW + 3600_000 },
                    chatId: "c1", sessionId: "c1", pid: null, state: "done", profileDir: ".claude-work" } as Session;
  for (const mode of ["once", "none"] as const) {
    const shown = shareUsage(status, hosts, mode);
    const [labWork, labPersonal] = shown.hosts[0].result!.groups;
    assert.ok(labWork.limitsHidden && labWork.limits === null && labPersonal.limitsHidden); // (not shown on lab)
    // personal is full: no "Continue on personal" for a chat on lab, as on this computer
    assert.equal(handoverTarget(stopped, shareAccounts(machineStatus({ ...shown }, "lab"))), null);
    // and a task on lab's work can wait for its limit
    assert.equal(limitReset(labWork, NOW)?.at, NOW + 3600_000);
  }
});

test("the status bar shows the usage of the account VS Code's Claude runs on, before an active one", () => {
  const busy = { state: "working" } as Session;
  const status = machine([account("work", 99, NOW - 600_000), account("personal", 79, NOW, { sessions: [busy] })]);
  const info = { available: true, profileKey: ".claude-work" };
  const groups = allGroups(status, []);
  assert.equal(panelWindow(groups, claudeCodeGroup(groups, [], info)?.id)?.group.id, "work");
  assert.equal(panelWindow(groups)?.group.id, "personal"); // (without one: the active account)
  assert.equal(panelWindow(groups, claudeCodeGroup(groups, [], { available: false, profileKey: null })?.id)?.group.id, "personal");
  // A Remote-SSH window: the host's account, its numbers wherever they show (shareUsage)
  const hosts = [host("lab", [account("personal", 60, NOW - 3600_000), account("work", 98, NOW - 900_000, { vscodeHere: true })], true)];
  const shown = shareUsage(status, hosts, "once");
  const all = allGroups(shown.status, shown.hosts);
  const mine = claudeCodeGroup(all, shown.hosts, info);
  assert.equal(mine?.host, "lab");
  assert.equal(panelWindow(all, mine?.id)?.window.pct, 99); // this computer's copy of work, the newer numbers
});

test("shellQuote quotes like Python's shlex.quote", () => {
  assert.equal(shellQuote(""), "''");
  assert.equal(shellQuote("/home/alice/projects"), "/home/alice/projects");
  assert.equal(shellQuote("a b"), "'a b'");
  assert.equal(shellQuote("it's"), "'it'\"'\"'s'");
});

test("formatting", () => {
  assert.equal(duration(59 * 60000), "59m");
  assert.equal(duration(61 * 60000), "1h 1m");
  assert.equal(duration(25 * 3600000), "1d 1h");
  assert.equal(formatTokens(1500), "1.5k");
  assert.equal(formatTokens(2_500_000), "2.5M");
  // the unit by what it rounds to
  assert.equal(formatTokens(999_949), "999.9k");
  assert.equal(formatTokens(999_960), "1.0M");
  assert.equal(formatTokens(999_960_000), "1.0B");
  assert.equal(stateText({ state: "done", reason: "failed", since: NOW - 120000 }, NOW), "Failed · 2m");
  const window = { key: "five_hour", label: "5h", pct: 99, reset: false };
  assert.equal(resetText({ ...window, resetsAt: NOW + 30000 }, NOW), "resets in <1m", "the last minute doesn't read 0m");
  assert.equal(resetText({ ...window, resetsAt: NOW + 90 * 60000 }, NOW), "resets in 1h 30m");
  assert.equal(resetText({ ...window, resetsAt: null }, NOW), "");
  assert.equal(resetText({ ...window, resetsAt: NOW - 1000, reset: true }, NOW), "reset");
  assert.equal(petKeyOf({ chatId: "c", sessionId: "s", key: "k" }, "build-server"), "ssh:build-server|/c");
  assert.equal(petKeyOf({ chatId: "c", sessionId: "s", key: "k", profileDir: ".claude-work" }), ".claude-work/c");
});

test("an unfolded subagent: its numbers, its open state's key, the run's tooltip", () => {
  assert.equal(agentSummary({ toolCalls: 12, tokens: 45_200 }), "12 tool calls · 45.2k tokens");
  assert.equal(agentSummary({ toolCalls: 1, tokens: 0 }), "1 tool call");
  assert.equal(agentSummary({ toolCalls: null, tokens: 1_300_000 }), "1.3M tokens");
  assert.equal(agentSummary({}), "");
  assert.equal(agentDetailKey("lab|.claude/s1/live", "a1"), "lab|.claude/s1/live|a1");
  assert.match(agentRunTitle(), /as Markdown\. Claude Code itself can't open a subagent from outside\.$/);
  assert.match(agentRunTitle("lab"), /from outside\. Fetched from lab over ssh\.$/);
});

test("a chat the page names is looked up: its commands are the extension's own", () => {
  const state = demoState(NOW);
  const host = state.hosts[0];
  const s = host.result!.groups[0].sessions[0];
  const ref = findChatRef(state.status, state.hosts, host.name, s.key);
  assert.equal(ref?.openCommand ?? null, s.openCommand ?? null);
  assert.equal(findChatRef(state.status, state.hosts, host.name, "made-up"), null, "a chat it doesn't know");
  assert.equal(findChatRef(state.status, state.hosts, "elsewhere", s.key), null, "on a host it doesn't show");
  assert.equal(findChatRef(state.status, state.hosts, { evil: 1 }, s.key), null);
  const local = state.status!.groups[0].sessions[0];
  assert.equal(findChatRef(state.status, state.hosts, undefined, local.key)?.sessionId, local.sessionId);
});

test("a shared chat's pointer is the chat's own row (its tab, its window), else the pointer", () => {
  const state = demoState(NOW);
  const groups = state.status!.groups;
  const row = groups[0].sessions[0];
  row.chatId = "the-transcript"; // (continued with --resume: not its session id)
  const pointer = { key: `${row.key}/shared`, sessionId: row.sessionId, name: row.name, profileDir: row.profileDir, openCommand: "x" };
  groups[groups.length - 1].sharedHere = [pointer as never];
  const ref = findChatRef(state.status, state.hosts, undefined, pointer.key);
  assert.equal(ref?.key, row.key);
  assert.equal(ref?.chatId, "the-transcript");
  groups[0].sessions = groups[0].sessions.slice(1); // (gone from the list: the pointer still opens)
  assert.equal(findChatRef(state.status, state.hosts, undefined, pointer.key)?.key, pointer.key);
});

test("a host that didn't answer this time doesn't count; its clock is put right", () => {
  const state = demoState(NOW);
  const counted = allGroups(state.status, state.hosts).length;
  const stale = state.hosts.map((h) => ({ ...h, error: "timed out" }));
  assert.equal(allGroups(state.status, stale).length, counted - state.hosts.reduce((n, h) => n + (h.result?.groups.length ?? 0), 0));
  const result = state.hosts[0].result!;
  const shifted = toLocalClock(result, 60000);
  assert.equal(shifted.generatedAt, result.generatedAt + 60000);
  assert.equal(shifted.groups[0].sessions[0].since, (result.groups[0].sessions[0].since ?? 0) + 60000);
  assert.equal(toLocalClock(result, 2000), result, "a few seconds: just the network");
  const moved: Status = { ...result, groups: [{ ...result.groups[0], sessions: [{ ...result.groups[0].sessions[0], movedFrom: { id: "b", at: 700 } }] }] };
  assert.deepEqual(toLocalClock(moved, 60000).groups[0].sessions[0].movedFrom, { id: "b", at: 60700 });
});

test("a chat Claude moved to the background says so where it runs", () => {
  const at = new Date(2026, 10, 1, 16, 1).getTime();
  assert.equal(movedText({ movedFrom: { id: "b", at } }),
    `Moved to the background at ${clockText(at)}: Claude goes on with it under a new id.\n\n`);
  assert.equal(movedText({ movedFrom: { id: "b", at: null } }), "Moved to the background: Claude goes on with it under a new id.\n\n");
  assert.equal(movedText({}), "");
});

test("a host's memories come onto this computer's clock too, like its plans", () => {
  const memory = { key: "m", name: "m", description: "", type: "", path: "/m.md", folder: "", folderShort: "", folderGone: false, profileDir: ".claude", profile: "main", updatedAt: NOW - 60_000 };
  const result = machine([account("work", 10, NOW, { memories: [memory] })]);
  const local = toLocalClock(result, 2 * 3600_000); // the host's clock is 2 hours behind
  assert.equal(local.groups[0].memories![0].updatedAt, NOW - 60_000 + 2 * 3600_000);
  assert.equal(result.groups[0].memories![0].updatedAt, NOW - 60_000); // (the answer itself stays as it was)
});

test("a new account's name: the backend's rule, and not one there already", () => {
  const folders = ["~/.claude", "~/.claude-work"];
  assert.equal(accountNameProblem("side", folders), "");
  assert.equal(accountNameProblem("my_Work-2", folders), "");
  assert.match(accountNameProblem("work", folders), /already/);
  assert.match(accountNameProblem("default", folders), /taken/);
  assert.match(accountNameProblem("main", folders), /~\/\.claude/);
  for (const bad of ["", "1st", "a b", "../x", "x".repeat(33)]) assert.notEqual(accountNameProblem(bad, folders), "", bad);
});

test("a row's open details stay open when its chat changes kind (a background session ends: live → job)", async () => {
  const { rowKeyOf } = await import("../webview/util/chat");
  const live = { key: ".claude-work/s1/live", profileDir: ".claude-work", sessionId: "s1", chatId: "c1" };
  assert.equal(rowKeyOf(live, "lab"), rowKeyOf({ ...live, key: ".claude-work/s1/job" }, "lab"));
  assert.equal(rowKeyOf(live, "lab"), "lab|.claude-work/c1");
  assert.equal(rowKeyOf({ ...live, chatId: "" }), ".claude-work/s1");
});

test("an account's plan usage line and token line read as in the widget", () => {
  const limits = (ago: number) => ({ updatedAt: NOW - ago, windows: [] }) as unknown as Parameters<typeof planUsageText>[0];
  assert.equal(planUsageText(limits(20_000), "", NOW), "Plan usage updated just now");
  assert.equal(planUsageText(limits(5 * 60_000), "", NOW), "Plan usage as of 5m ago");
  assert.equal(planUsageText(limits(20_000), "lab", NOW), "Plan usage updated just now, on lab");
  assert.equal(planUsageText(limits(5 * 60_000), "lab", NOW), "Plan usage as of 5m ago, on lab");
  const totals = (total: number, output: number) => ({ total, output, input: 0, cacheRead: 0, cacheWrite: 0, messages: 0, shared: 0 });
  const t = { today: totals(378_300, 12_000), week: totals(502_900, 15_000), models: [{ model: "claude-opus-5", total: 400_000 }] };
  assert.equal(tokensText(t as unknown as Parameters<typeof tokensText>[0]), "Tokens today 378.3k (12.0k out) · 7 days 502.9k (15.0k out)");
});

// ---------------------------------------------------------------- lists a page at a time

const recentChat = (i: number) => ({ key: `p/c${i}/recent`, sessionId: `c${i}`, name: `chat ${i}`, cwd: "/w", cwdShort: "/w", lastActive: 1000 - i,
                                     profile: "p", profileDir: "p", shared: false });

test("Recent chats: a page at a time, the next one asked for before it's wanted, a check with fewer than asked is the end", () => {
  assert.equal(pageSizeOf(0), 5);
  assert.equal(pageSizeOf(3), 3);
  // (the status lists a page more than shows, and counts them all)
  const group = { recent: Array.from({ length: 10 }, (_, i) => recentChat(i)), recentCount: 23 };
  let page = recentPage(group, null, 1, 5);
  assert.deepEqual([page.shown, page.count, page.fetch], [5, 23, 0]);
  assert.equal(pagedTitle("Recent chats", page.shown, page.count), "Recent chats (5 of 23)");
  assert.equal(moreText(page.shown, page.count, 5), "Show 5 more");
  assert.equal(moreTitle(page.shown, page.count), "5 of 23 show. Folded again, the list shows its first ones again.");
  // two pages show: the third is asked for (a check that lists 15)
  page = recentPage(group, null, 2, 5);
  assert.deepEqual([page.shown, page.fetch], [10, 15]);
  // its answer: the first 15 again, each once
  const more = { recent: Array.from({ length: 15 }, (_, i) => recentChat(i)), asked: 15 };
  page = recentPage(group, more, 2, 5);
  assert.deepEqual([page.all.length, page.shown, page.fetch], [15, 10, 0]);
  page = recentPage(group, more, 3, 5);
  assert.deepEqual([page.shown, page.fetch], [15, 20]);
  // fewer than asked: that's all of them, whatever the count said
  page = recentPage(group, { recent: more.recent.slice(0, 13), asked: 20 }, 4, 5);
  assert.deepEqual([page.shown, page.count, page.fetch], [13, 13, 0]);
  assert.equal(pagedTitle("Recent chats", page.shown, page.count), "Recent chats (13)");
  assert.equal(moreText(18, 20, 5), "Show 2 more");
  // a page the status hasn't got yet isn't shown as empty lines
  page = recentPage({ recent: [recentChat(0)], recentCount: 9 }, null, 2, 5);
  assert.deepEqual([page.shown, page.count, page.fetch], [1, 9, 9]);
  // an older backend: no count, what it lists
  assert.equal(recentPage({ recent: [recentChat(0), recentChat(1)] }, null, 1, 5).count, 2);
});

test("an opened project: its chats but the running ones, plans and memories a page at a time, tagged when it's on several accounts", () => {
  const project = demoProjects(1_800_000_000_000).projects[0];
  const opened = projectLists(project, new Set(["demo-1"]), {}, 2);
  assert.deepEqual(opened.chats.map((c) => c.sessionId), ["demo-r1", "demo-6"]);
  assert.deepEqual([opened.chatsShown, opened.plansShown, opened.memoriesShown, opened.tagged], [2, 0, 1, false]);
  const big = { ...project, accounts: ["personal", "work"], chats: Array.from({ length: 7 }, (_, i) => ({ ...recentChat(i), account: "work" })) };
  const more = projectLists(big, new Set(), { chats: 2 }, 3);
  assert.deepEqual([more.chats.length, more.chatsShown, more.tagged], [7, 6, true]);
  assert.equal(pagedTitle("Chats", more.chatsShown, more.chats.length), "Chats (6 of 7)");
  // the chats listed now, under their account: not again in the project
  const groups = demoState(1_800_000_000_000).status!.groups;
  assert.ok(listedChats(groups).has(groups[0].sessions[0].sessionId));
});

test("an open chat shows in its closest project only, not also in the folders above it", () => {
  const chat = (key: string, cwd: string) => ({ key, cwd }) as Session;
  const projects = [{ path: "/h" }, { path: "/h/repos" }, { path: "/h/repos/app" }, { path: "/h/repos/app2" }];
  const open = openChatsByProject(projects, [chat("a", "/h/repos/app"), chat("b", "/h/repos/app/src"), chat("c", "/h/repos"),
    chat("d", "/h/notes"), chat("e", "/elsewhere"), chat("f", "/h/repos/app2")]);
  assert.deepEqual(Object.fromEntries([...open].map(([path, s]) => [path, s.map((x) => x.key)])),
    { "/h/repos/app": ["a", "b"], "/h/repos": ["c"], "/h": ["d"], "/h/repos/app2": ["f"] });
  // in a project you hid: in no other
  const hid = openChatsByProject([{ path: "/h" }, { path: "/h/secret" }], [chat("g", "/h/secret/x")]);
  assert.deepEqual([...hid.keys()], ["/h/secret"]);
});

test("a line's folder in a project: only the part below the project's, nothing for the project's own", () => {
  assert.equal(folderIn("/srv/repos/api/server", "/srv/repos/api", "~/repos/api/server"), "server");
  assert.equal(folderIn("/srv/repos/api", "/srv/repos/api", "~/repos/api"), "");
  assert.equal(folderIn("/srv/repos/api-v2", "/srv/repos/api", "~/repos/api-v2"), "~/repos/api-v2");
  assert.equal(folderIn("/srv/x", "", "~/x"), "~/x"); // (the plans whose chat is gone: no project folder)
  assert.equal(folderIn("", "/srv/repos/api", ""), "");
});

test("the Projects tab's chats, plans and memories are found by key, on the account of their folder", () => {
  const state = demoState(1_800_000_000_000);
  const data = demoProjects(1_800_000_000_000);
  assert.equal(findProjectChat(data, ".claude/demo-6/project")?.sessionId, "demo-6");
  assert.equal(findProjectChat(data, "nope"), null);
  assert.equal(findProjectChat(null, ".claude/demo-6/project"), null);
  assert.equal(findProjectPlan(data, state.status, "demo-plan-2")?.group.id, state.status!.groups[0].id);
  assert.equal(findProjectMemory(data, state.status, "demo-mem-1")?.memory.name, "test-command");
  assert.equal(findProjectMemory(data, state.status, 5), null);
  assert.equal(groupOfProfile(state.status, ".claude")?.id, state.status!.groups[0].id);
});

test("containers: ids, labels, the picker's lines and sections", async () => {
  const { containerOf, containerDescription, containerDetail, containerPlaces, hostLabel, hostWhere } = await import("../src/shared/model");
  assert.deepEqual(containerOf("podman:web"), { engine: "podman", name: "web", host: "" });
  assert.deepEqual(containerOf("docker:api@user@lab"), { engine: "docker", name: "api", host: "user@lab" });
  assert.deepEqual([containerOf("lab"), containerOf("podman:-x"), containerOf("lxc:x")], [null, null, null]);
  assert.deepEqual([hostLabel("podman:web"), hostLabel("docker:api@lab"), hostLabel("lab")], ["web", "api on lab", "lab"]);
  assert.deepEqual([hostWhere("podman:web"), hostWhere("lab")], ["in web", "on lab"]);
  const now = 10 * 86400000;
  const base = { state: "", folder: "", folderShort: "", devcontainer: false, sharesHome: false };
  const web = { ...base, id: "podman:web", engine: "podman", name: "web", image: "ubuntu:22.04", running: true, activeAt: now - 5000 };
  const old = { ...base, id: "podman:old", engine: "podman", name: "old", image: "node:20", running: false, activeAt: now - 3 * 86400000, sharesHome: true };
  const dev = { ...base, id: "docker:shop@lab", engine: "docker", name: "shop", image: "vsc-shop", running: false, activeAt: now - 3600000, folderShort: "~/shop" };
  assert.equal(containerDescription(web, now), "podman · ubuntu:22.04");
  assert.equal(containerDescription(old, now), "podman · node:20 · stopped 3 days ago · shares your home folder");
  assert.equal(containerDetail("docker:shop@lab", dev), "~/shop · on lab");
  assert.equal(containerDetail("podman:gone", null), "podman");
  const places = containerPlaces([web, old], [{ engine: "docker", message: "Docker isn't running." }],
    { lab: { containers: [dev] }, far: { containers: [] } }, ["lab"], ["podman:web", "podman:gone", "docker:x@far"], 30, now);
  assert.deepEqual(places.map((p) => p.title), ["Containers on this computer", "Containers on lab", "Containers on far"]);
  assert.deepEqual(places[0].items.map((i) => [i.id, i.picked]), [["podman:web", true], ["podman:old", false], ["podman:gone", true]]);
  assert.deepEqual(places[0].notes, ["Docker isn't running."]);
  assert.deepEqual(places[2].items.map((i) => i.label), ["x"]); // (not connected: only the one you picked, to unpick it)
  assert.equal(containerPlaces([], [], {}, [], [], 30, now)[0].empty, "No containers active in the last 30 days");
  assert.equal(containerPlaces([], [], {}, [], [], 0, now)[0].empty, "No running containers");
});
