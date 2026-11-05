// The page is only a picture of the state: what it sends back is checked
// against the extension's own state (the chat, its commands, the host), and
// the page itself loads nothing but its own script and files.

import assert from "node:assert/strict";
import { test } from "node:test";
import * as vscode from "vscode";
import { demoProjects, demoState } from "../src/shared/demo";
import { badgeOf, chatRefOf, findProjectChat, recentRef } from "../src/shared/model";
import type { ProjectsData, RecentChat, ViewState } from "../src/shared/types";
import { ViewHost } from "../src/view";
import { recorded } from "./vscode-stub";

const NOW = 1_800_000_000_000;

function setup(state: ViewState = demoState(NOW), projects = demoProjects(NOW), more: { chat: RecentChat; groupId: string }[] = [],
               hostProjects: Record<string, Pick<ProjectsData, "projects">> = {}) {
  const calls: { name: string; args: unknown[] }[] = [];
  const record = (name: string) => (...args: unknown[]) => {
    calls.push({ name, args });
    return Promise.resolve();
  };
  const actions = new Proxy({}, { get: (_target, name: string) => record(name) });
  const dash = {
    onState: () => ({ dispose() {} }),
    onPetEvent: () => ({ dispose() {} }),
    onLive: () => ({ dispose() {} }), onUsageCameIn: () => ({ dispose() {} }),
    state: () => state,
    shownHosts: () => state.hosts.map((h) => h.name),
    setVisible() {},
    dismissDigest: record("dismissDigest"),
    pollHost: record("pollHost"),
    refreshAll: record("refreshAll"),
    startQueued: (t: { id: string }) => record("startQueued")(t.id),
    // (the Projects tab as it was last read, an SSH host's as read there; a bigger check's recent chats)
    projects: () => Promise.resolve({ data: projects }),
    projectsRead: () => projects,
    projectsOn: (host?: string) => (host ? hostProjects[host] ?? null : projects),
    answeringHosts: () => Object.keys(hostProjects),
    hostProjectsRead: () => Object.entries(hostProjects).map(([host, read]) => ({ host, ok: true, error: "", projects: read.projects })),
    readHostProjects: record("readHostProjects"),
    moreChat: (host: unknown, key: unknown) => {
      const m = host ? undefined : more.find((x) => x.chat.key === key);
      return m ? recentRef(m.chat) : findProjectChat(host ? hostProjects[host as string] : projects, key, (host as string) || undefined);
    },
    moreRecentChat: (host: unknown, key: unknown) => (host ? null : (more.find((x) => x.chat.key === key) ?? null)),
    setActionError: record("setActionError"),
    recentMore: (...args: unknown[]) => (calls.push({ name: "recentMore", args }), Promise.resolve({ recent: [], asked: args[2] })),
  };
  const host = new ViewHost(vscode.Uri.file("/ext") as never, dash as never, actions as never);
  const priv = host as unknown as { receive(webview: unknown, m: unknown): void; html(webview: unknown, editorTab: boolean): string };
  return {
    state,
    calls,
    receive: (m: unknown) => priv.receive({ postMessage: () => Promise.resolve(true) }, m),
    html: (webview: unknown, editorTab = false) => priv.html(webview, editorTab),
  };
}

// The Activity Bar badge: chats that need you, else chats that finished since
// you last looked, as the Plasma panel's; on a tree view nobody sees until
// the view is there (a webview's badge shows only once it was opened), then on
// the view itself, so it follows the view to another container (a container
// adds up its views' numbers: never both)
test("the badge counts what needs you, else what finished, and its tooltip says which", () => {
  assert.equal(badgeOf(0, 0), undefined);
  assert.deepEqual(badgeOf(2, 3), { value: 2, tooltip: "2 chats need you" });
  assert.deepEqual(badgeOf(1, 0), { value: 1, tooltip: "1 chat needs you" });
  assert.deepEqual(badgeOf(0, 3), { value: 3, tooltip: "3 chats finished" });
  assert.deepEqual(badgeOf(0, 1), { value: 1, tooltip: "1 chat finished" });
});

test("the badge is on the hidden tree from startup, on the view once it's there, and back when it's gone", () => {
  const dash = { onState: () => ({ dispose() {} }), onPetEvent: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), onUsageCameIn: () => ({ dispose() {} }), state: () => demoState(NOW), setVisible() {} };
  const host = new ViewHost(vscode.Uri.file("/ext") as never, dash as never, {} as never);
  const tree = (vscode as unknown as { recorded: { treeViews: Map<string, { badge: unknown }> } }).recorded.treeViews.get("talpyDen.badge")!;
  host.setBadge(0, 2);
  assert.deepEqual(tree.badge, { value: 2, tooltip: "2 chats finished" });
  let dispose = () => {};
  let disposed = false;
  const page = { options: {}, html: "", postMessage: async () => true, onDidReceiveMessage: () => ({ dispose() {} }), asWebviewUri: (u: unknown) => u, cspSource: "" };
  const view = {
    badge: undefined as unknown,
    get webview() {
      if (disposed) throw new Error("Webview is disposed"); // (as VS Code's, from its onDidDispose on)
      return page;
    },
    visible: false, onDidChangeVisibility: () => ({}), onDidDispose: (f: () => void) => ((dispose = f), {}),
  };
  host.resolveWebviewView(view as never);
  assert.deepEqual(view.badge, { value: 2, tooltip: "2 chats finished" });
  assert.equal(tree.badge, undefined);
  host.setBadge(1, 2);
  assert.deepEqual(view.badge, { value: 1, tooltip: "1 chat needs you" });
  assert.equal(tree.badge, undefined);
  disposed = true;
  dispose();
  assert.deepEqual(tree.badge, { value: 1, tooltip: "1 chat needs you" });
  host.setBadge(0, 0);
  assert.equal(tree.badge, undefined);
});

// "Open the Recap" (the Monday notification): the view's page shows it now
// if it's loaded, else once it is; a page that loads later starts on Chats
test("a tab shown goes to the view's page once, not to a page that loads hours later", () => {
  const dash = { onState: () => ({ dispose() {} }), onPetEvent: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), onUsageCameIn: () => ({ dispose() {} }), state: () => demoState(NOW), setVisible() {} };
  const host = new ViewHost(vscode.Uri.file("/ext") as never, dash as never, {} as never);
  const priv = host as unknown as { receive(webview: unknown, m: unknown): void };
  const page = () => {
    const got: unknown[] = [];
    return { got, webview: { options: {}, html: "", postMessage: async (m: { type: string }) => (m.type === "showTab" && got.push(m), true), onDidReceiveMessage: () => ({ dispose() {} }), asWebviewUri: (u: unknown) => u, cspSource: "" } };
  };
  const view = page();
  host.resolveWebviewView({ webview: view.webview, visible: true, onDidChangeVisibility: () => ({}), onDidDispose: () => ({}) } as never);
  priv.receive(view.webview, { type: "ready" });
  host.showTab("week");
  assert.deepEqual(view.got, [{ type: "showTab", tab: "week" }], "the loaded page shows it now");
  const later = page();
  priv.receive(later.webview, { type: "ready" });
  assert.deepEqual(later.got, [], "a page loading later starts on Chats");
  // the view's page not loaded yet: it shows the tab once it is
  const fresh = new ViewHost(vscode.Uri.file("/ext") as never, dash as never, {} as never);
  fresh.showTab("week");
  const first = page();
  fresh.resolveWebviewView({ webview: first.webview, visible: true, onDidChangeVisibility: () => ({}), onDidDispose: () => ({}) } as never);
  (fresh as unknown as { receive(webview: unknown, m: unknown): void }).receive(first.webview, { type: "ready" });
  assert.deepEqual(first.got, [{ type: "showTab", tab: "week" }]);
});

// Refresh (the view's title bar, the Command Palette, an editor tab's
// header): the chats and the plan usage, and in every page the Recap,
// Permissions or Projects tab in sight reads again (the Recap's own Read
// again is gone: one Refresh); a host's Refresh checks that host only
test("Refresh checks the chats and the plan usage and has every page read its tab again; a host's checks that host", () => {
  const calls: string[] = [];
  const dash = {
    onState: () => ({ dispose() {} }), onPetEvent: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), onUsageCameIn: () => ({ dispose() {} }),
    state: () => demoState(NOW), shownHosts: () => ["lab"], setVisible() {},
    refreshAll: () => void calls.push("refreshAll"),
    fetchUsage: async () => void calls.push("fetchUsage"),
    pollHost: async (h: string) => void calls.push(`pollHost ${h}`),
  };
  const host = new ViewHost(vscode.Uri.file("/ext") as never, dash as never, {} as never);
  const sidebar: { type: string }[] = [];
  host.resolveWebviewView({
    webview: { options: {}, html: "", postMessage: async (m: { type: string }) => (sidebar.push(m), true), onDidReceiveMessage: () => ({ dispose() {} }), asWebviewUri: (u: unknown) => u, cspSource: "" },
    visible: true, onDidChangeVisibility: () => ({}), onDidDispose: () => ({}),
  } as never);
  host.openInEditor();
  const tab = recorded.panels.at(-1)!;
  const readAgain = () => [sidebar, tab.sent as { type: string }[]].map((sent) => sent.filter((m) => m.type === "readAgain").length);

  tab.receive({ type: "refresh", host: "lab" }); // (a host's own ↻)
  assert.deepEqual(calls, ["pollHost lab"]);
  assert.deepEqual(readAgain(), [0, 0], "a host's Refresh reads no tab again");

  calls.length = 0;
  tab.receive({ type: "refresh" }); // (the editor tab's header)
  assert.deepEqual(calls, ["refreshAll", "fetchUsage"]);
  assert.deepEqual(readAgain(), [1, 1], "each page reads the tab it shows again");

  calls.length = 0;
  host.refresh(); // (talpyDen.refresh: the view's title bar, the Command Palette)
  assert.deepEqual(calls, ["refreshAll", "fetchUsage"]);
  assert.deepEqual(readAgain(), [2, 2]);
});

// The Recap read at once, before the plan usage Refresh fetched came in:
// once it has, the Recap in sight reads again (not Permissions or Projects)
test("the plan usage Refresh fetched came in: every page's Recap reads again", () => {
  let cameIn = () => {};
  const dash = {
    onState: () => ({ dispose() {} }), onPetEvent: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }),
    onUsageCameIn: (f: () => void) => ((cameIn = f), { dispose() {} }),
    state: () => demoState(NOW), setVisible() {}, refreshAll() {}, fetchUsage: async () => undefined,
  };
  const host = new ViewHost(vscode.Uri.file("/ext") as never, dash as never, {} as never);
  host.openInEditor();
  const tab = recorded.panels.at(-1)!;
  cameIn();
  assert.deepEqual((tab.sent as { type: string }[]).filter((m) => m.type === "readAgain"), [{ type: "readAgain", recap: true }]);
});

// Closing the editor tab: VS Code refuses its panel's webview from then on
// (the stub's too), so the view forgets the tab without asking for it, and
// Open in Editor Tab opens a new one (it revealed the closed one, which
// throws)
test("a closed editor tab is forgotten, and Open in Editor Tab opens a new one", () => {
  const dash = {
    onState: () => ({ dispose() {} }), onPetEvent: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), onUsageCameIn: () => ({ dispose() {} }),
    state: () => demoState(NOW), setVisible() {}, refreshAll() {}, fetchUsage: async () => undefined,
  };
  const host = new ViewHost(vscode.Uri.file("/ext") as never, dash as never, {} as never);
  host.openInEditor();
  const first = recorded.panels.at(-1)!;
  first.dispose();
  host.openInEditor();
  const second = recorded.panels.at(-1)!;
  assert.notEqual(second, first, "a new tab");
  host.refresh();
  assert.deepEqual((second.sent as { type: string }[]).filter((m) => m.type === "readAgain"), [{ type: "readAgain" }]);
  second.dispose();
});

test("a chat the page names is the extension's own row, not what the page says about it", () => {
  const { state, calls, receive } = setup();
  const local = state.status!.groups[0].sessions[0];
  receive({ type: "open", chat: { key: local.key, openCommand: "touch /tmp/pwned", stopCommand: "reboot", pid: 1, name: "forged" } });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].name, "open");
  assert.deepEqual(calls[0].args[0], chatRefOf(local, undefined));

  calls.length = 0;
  const hostName = state.hosts[0].name;
  const remote = state.hosts[0].result!.groups[0].sessions[0];
  receive({ type: "stop", chat: { host: hostName, key: remote.key, stopCommand: "reboot" } });
  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0].args[0], chatRefOf(remote, hostName));
});

test("a chat that isn't in the extension's state, and a message that isn't one, do nothing", () => {
  const { state, calls, receive } = setup();
  const local = state.status!.groups[0].sessions[0];
  receive({ type: "open", chat: { key: "nope" } });
  receive({ type: "open", chat: { host: "nope", key: local.key } }); // that host's rows only
  receive({ type: "open", chat: { host: 7, key: local.key } });
  receive({ type: "open", chat: "x" });
  receive({ type: "open" });
  receive({ type: 7 });
  receive({});
  receive("open");
  receive(null);
  assert.deepEqual(calls, []);
});

// Move to project… and a plan dropped on a project ask first (moveDescribe):
// nothing moves until the question is answered (movePlan), and only a plan
// the view lists goes, to a folder named in full
test("a plan's move asks first, and moves only a plan it lists to a folder in full", () => {
  const state = demoState(NOW);
  const g = state.status!.groups[0];
  g.plans = [];
  const { calls, receive } = setup(state);
  const named = () => calls.splice(0).map((c) => [c.name, ...c.args.map((a) => (a && typeof a === "object" && "slug" in a ? (a as { slug: string }).slug : a))]);
  receive({ type: "moveDescribe", key: "plan||g|demo-plan-1", groupId: g.id, id: "demo-plan-1" });
  receive({ type: "moveDescribe", key: "drop|/srv/app", groupId: g.id, id: "demo-plan-1", folder: "/srv/app" });
  receive({ type: "moveDescribe", key: "plan||g|demo-plan-1", groupId: g.id, id: "demo-plan-1", back: true });
  assert.deepEqual(named(), [["describeMove", "brave-green-otter", undefined, undefined, false],
    ["describeMove", "brave-green-otter", undefined, "/srv/app", false], ["describeMove", "brave-green-otter", undefined, undefined, true]]);
  // (a drop only asks: nothing moved)
  receive({ type: "moveDescribe", key: "x", groupId: g.id, id: "demo-plan-1", folder: "relative/folder" });
  receive({ type: "moveDescribe", groupId: g.id, id: "demo-plan-1" });
  receive({ type: "movePlan", groupId: g.id, id: "nope", keepThere: true });
  receive({ type: "movePlan", groupId: g.id, id: "demo-plan-1", folder: "relative", keepThere: true });
  assert.deepEqual(named(), []);
  receive({ type: "movePlan", groupId: g.id, id: "demo-plan-1", folder: "/srv/app", keepThere: false, ifExists: "keep" });
  receive({ type: "movePlan", groupId: g.id, id: "demo-plan-1", back: true, keepThere: true, ifExists: "everything" });
  assert.deepEqual(named(), [["movePlan", "brave-green-otter", undefined, "/srv/app", false, false, "keep"],
    ["movePlan", "brave-green-otter", undefined, undefined, true, true, undefined]]);
});

// The Projects tab's lines are this computer's chats, plans and memories as
// week.py --projects last listed them: the status lists only the starred
// plans and the CLAUDE.md, so a click on one is found there
test("a project's chat, plan and memory are found in what the Projects tab last read", () => {
  const state = demoState(NOW);
  const g = state.status!.groups[0];
  g.plans = [];
  g.memories = [];
  const { calls, receive } = setup(state);
  const names = () => calls.splice(0).map((c) => [c.name, ...c.args.map((a) => (a && typeof a === "object" && "sessionId" in a ? a.sessionId : a))]);
  receive({ type: "open", chat: { key: ".claude/demo-6/project" } });
  receive({ type: "star", chat: { key: ".claude/demo-6/project" }, on: true });
  assert.deepEqual(names(), [["open", "demo-6"], ["star", "chats", "demo-6", undefined, true]]);
  receive({ type: "openPlan", groupId: g.id, plan: "demo-plan-1" });
  receive({ type: "hide", kind: "plans", groupId: g.id, id: "demo-plan-2" });
  receive({ type: "openMemory", groupId: g.id, memory: "demo-mem-1", edit: true });
  receive({ type: "delete", kind: "memory", groupId: g.id, id: "demo-mem-2" });
  const got = calls.splice(0);
  assert.deepEqual(got.map((c) => c.name), ["openPlan", "hide", "openMemory", "delete"]);
  assert.equal((got[0].args[0] as { slug: string }).slug, "brave-green-otter");
  assert.deepEqual(got[1].args, ["plans", "quiet-amber-heron", undefined]);
  assert.deepEqual([(got[2].args[0] as { key: string }).key, got[2].args[2]], ["demo-mem-1", true]);
  assert.deepEqual(got[3].args, ["memory", "demo-mem-2", "", undefined]);
  // (Delete?'s question on the line: what it would delete, asked the same way)
  receive({ type: "deleteDescribe", key: "memory||g|demo-mem-2", kind: "memory", groupId: g.id, id: "demo-mem-2" });
  receive({ type: "deleteDescribe", kind: "memory", groupId: g.id, id: "demo-mem-2" }); // (no line to answer: nothing)
  const asked = calls.splice(0);
  assert.deepEqual(asked.map((c) => [c.name, ...c.args]), [["describeDelete", "memory", "demo-mem-2", "", undefined]]);
  // (this computer's are never looked for in an SSH host's, nor what it doesn't list)
  receive({ type: "openPlan", groupId: g.id, host: state.hosts[0]?.name ?? "box", plan: "demo-plan-1" });
  receive({ type: "open", chat: { host: state.hosts[0]?.name ?? "box", key: ".claude/demo-6/project" } });
  receive({ type: "openMemory", groupId: g.id, memory: "nope" });
  assert.deepEqual(calls, []);
});

// An SSH host's projects (week.py --projects --on HOST, read there): a click
// on one of their lines is found in what was read on that host, and acts
// there, on that host's account; New chat here starts there with the command
// its read sent, never one from the page
test("an SSH host's project lines are found in what was read there, and act there", () => {
  const state = demoState(NOW);
  const host = state.hosts[0].name;   // (build-server: answered its check)
  const g = state.hosts[0].result!.groups[0];
  const path = "/srv/api";
  const chat = { key: ".claude/h-1/project", sessionId: "h-1", name: "Tune it", cwd: path, cwdShort: path, lastActive: NOW,
                 profile: "team", profileDir: ".claude", account: "team", shared: false, starred: false, openCommand: "cd /srv/api; claude --resume h-1" };
  const plan = { ...demoProjects(NOW).projects.flatMap((p) => p.plans)[0], key: "h-plan", slug: "host-plan", account: "team" };
  const memory = { ...(demoProjects(NOW).projects.flatMap((p) => p.memories)[0] ?? state.status!.groups[0].memories![0]),
                   key: "h-mem", type: "project", account: "team" };
  const row = { name: "api", path, short: path, lastAt: NOW, accounts: ["team"], chatCount: 1, chats: [chat], plans: [plan],
                memories: [memory], recap: null, newChatCommand: "cd /srv/api 2>/dev/null; claude" } as ProjectsData["projects"][number];
  const { calls, receive } = setup(state, demoProjects(NOW), [], { [host]: { projects: [row] } });
  receive({ type: "open", chat: { host, key: chat.key } });
  receive({ type: "openPlan", groupId: g.id, host, plan: "h-plan" });
  receive({ type: "openMemory", groupId: g.id, host, memory: "h-mem" });
  receive({ type: "hide", kind: "projects", host, id: path });
  receive({ type: "newChatIn", host, path, short: path, profileDir: ".claude" });
  const got = calls.splice(0);
  assert.deepEqual(got.map((c) => c.name), ["open", "openPlan", "openMemory", "hide", "newChat"]);
  assert.deepEqual([(got[0].args[0] as { sessionId: string; host: string; openCommand: string }).sessionId, (got[0].args[0] as { host: string }).host,
                    (got[0].args[0] as { openCommand: string }).openCommand], ["h-1", host, chat.openCommand]);
  assert.deepEqual([(got[1].args[0] as { slug: string }).slug, got[1].args[1]], ["host-plan", host]);
  assert.deepEqual([(got[2].args[0] as { key: string }).key, got[2].args[1]], ["h-mem", host]);
  assert.deepEqual(got[3].args, ["projects", path, host]);
  assert.deepEqual(got[4].args, [g.id, host, undefined, undefined, { path, short: path, newChatCommand: row.newChatCommand }]);
  // (a host that isn't shown, a folder its read doesn't list, a project's folder that isn't one: nothing)
  receive({ type: "hide", kind: "projects", host: "elsewhere", id: path });
  receive({ type: "newChatIn", host: "elsewhere", path, profileDir: ".claude" });
  receive({ type: "newChatIn", host, path: "/srv/other", profileDir: ".claude" });
  receive({ type: "hide", kind: "projects", id: "relative/path" });
  receive({ type: "openPlan", groupId: g.id, plan: "h-plan" });   // (this computer's: not the host's)
  receive({ type: "open", chat: { host: "elsewhere", key: chat.key } });
  assert.deepEqual(calls, []);
});

// "Show N more" past what the status lists: the extension runs a bigger
// check for the account, of a few pages, here or on a host shown
test("more recent chats are asked only for an account here or on a host shown, a few pages of it", () => {
  const { state, calls, receive } = setup();
  const g = state.status!.groups[0];
  receive({ type: "recentMore", groupId: g.id, count: 10 });
  receive({ type: "recentMore", groupId: g.id, host: state.hosts[0].name, count: 15 });
  for (const count of [0, -5, 2.5, "10", 5000]) receive({ type: "recentMore", groupId: g.id, count });
  receive({ type: "recentMore", groupId: g.id, host: "elsewhere", count: 10 });
  receive({ type: "recentMore", groupId: "", count: 10 });
  assert.deepEqual(calls.map((c) => c.args), [[g.id, undefined, 10], [g.id, state.hosts[0].name, 15]]);
});

test("agent ids, hosts and accounts in a message are checked", () => {
  const state = demoState(NOW);
  const mine = state.status!;
  mine.canShare = true;
  mine.groups[0].shareProfile ??= ".claude";
  mine.groups.push({ ...structuredClone(mine.groups[0]), id: "work", profileKeys: [".claude-work"], shareProfile: ".claude-work", sessions: [] });
  const { calls, receive } = setup(state);
  const local = mine.groups[0].sessions[0];
  const names = () => calls.splice(0).map((c) => c.name);

  receive({ type: "openAgentRun", chat: { key: local.key }, agentId: "../../etc/passwd" });
  receive({ type: "openAgentRun", chat: { key: local.key }, agentId: 5 });
  assert.deepEqual(names(), []);
  receive({ type: "openAgentRun", chat: { key: local.key }, agentId: "a1b2_c-3" });
  assert.deepEqual(names(), ["openAgentRun"]);

  receive({ type: "loginHost", host: "evil" });
  receive({ type: "disconnectHost", host: "evil" });
  assert.deepEqual(names(), []);
  receive({ type: "loginHost", host: state.hosts[0].name });
  receive({ type: "disconnectHost", host: state.hosts[0].name });
  assert.deepEqual(names(), ["loginHost", "disconnectHost"]);

  // handed over only to an account of the chat's own machine, as the extension knows it
  receive({ type: "handOver", chat: { key: local.key }, profile: "../../evil" });
  assert.deepEqual(names(), []);
  receive({ type: "handOver", chat: { key: local.key }, profile: ".claude-work" });
  assert.deepEqual(names(), ["handOver"]);

  // a task the queue doesn't have can't be cancelled or started
  receive({ type: "unqueue", id: "nope" });
  receive({ type: "startQueued", id: "nope" });
  assert.deepEqual(names(), []);
});

test("the page only runs its own script", () => {
  const { html } = setup();
  const webview = {
    cspSource: "https://example.vscode-cdn.net",
    asWebviewUri: (uri: vscode.Uri) => ({ toString: () => "https://example.vscode-cdn.net" + uri.path }),
  };
  const page = html(webview, true);
  const csp = /http-equiv="Content-Security-Policy" content="([^"]+)"/.exec(page)![1];
  assert.match(csp, /^default-src 'none'; base-uri 'none'; form-action 'none'; /);
  const scriptSrc = /script-src ([^;]+)/.exec(csp)![1];
  const nonce = /^'nonce-([A-Za-z0-9+/=]+)'$/.exec(scriptSrc)![1];
  assert.doesNotMatch(csp, /unsafe-eval/);
  assert.doesNotMatch(csp, /(^|; )(script-src|default-src) [^;]*unsafe-inline/);
  assert.doesNotMatch(csp, /https?:\/\/(?!example\.vscode-cdn\.net)/); // nothing from outside the extension
  const scripts = page.match(/<script\b[^>]*>/g)!;
  assert.equal(scripts.length, 2);
  for (const tag of scripts) assert.ok(tag.includes(`nonce="${nonce}"`), tag);
  assert.equal(page.match(/<\/script>/g)!.length, 2);
  assert.match(page, /window\.TALPY_DEN = \{"editorTab":true\};/);
  // a nonce for each page
  assert.notEqual(/'nonce-([^']+)'/.exec(html(webview))![1], nonce);
});

// Show N more: a chat a usage limit stopped, past the recent chats the status
// lists, goes on by itself as one of those does; a click on a chat nothing
// lists any more is answered
test("a bigger check's recent chat a limit stopped is queued to go on, and one not listed says so", () => {
  const state = demoState(NOW);
  const g = state.status!.groups[0];
  const old: RecentChat = { ...g.recent![0], key: "dir/0ld/chat", sessionId: "0ld", stopped: { kind: "limit", window: "five_hour", text: "limit", at: NOW, resetsAt: NOW + 3_600_000 } };
  const { calls, receive } = setup(state, demoProjects(NOW), [{ chat: old, groupId: g.id }]);
  receive({ type: "queueContinue", chat: { key: old.key }, keep: true });
  assert.deepEqual(calls.map((c) => c.name), ["queueContinue"]);
  assert.deepEqual(calls[0].args.slice(1), [NOW + 3_660_000, g.title, true]);
  receive({ type: "queueContinue", chat: { key: "dir/gone/chat" } });
  assert.deepEqual(calls.map((c) => c.name), ["queueContinue", "setActionError"]);
});
