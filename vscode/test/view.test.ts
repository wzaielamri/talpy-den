// The page is only a picture of the state: what it sends back is checked
// against the extension's own state (the chat, its commands, the host), and
// the page itself loads nothing but its own script and files.

import assert from "node:assert/strict";
import { test } from "node:test";
import * as vscode from "vscode";
import { demoProjects, demoState } from "../src/shared/demo";
import { badgeOf, chatRefOf, findProjectChat } from "../src/shared/model";
import type { ViewState } from "../src/shared/types";
import { ViewHost } from "../src/view";

const NOW = 1_800_000_000_000;

function setup(state: ViewState = demoState(NOW), projects = demoProjects(NOW)) {
  const calls: { name: string; args: unknown[] }[] = [];
  const record = (name: string) => (...args: unknown[]) => {
    calls.push({ name, args });
    return Promise.resolve();
  };
  const actions = new Proxy({}, { get: (_target, name: string) => record(name) });
  const dash = {
    onState: () => ({ dispose() {} }),
    onPetEvent: () => ({ dispose() {} }),
    onLive: () => ({ dispose() {} }),
    state: () => state,
    shownHosts: () => state.hosts.map((h) => h.name),
    setVisible() {},
    dismissDigest: record("dismissDigest"),
    pollHost: record("pollHost"),
    refreshAll: record("refreshAll"),
    startQueued: (t: { id: string }) => record("startQueued")(t.id),
    // (the Projects tab as it was last read; a bigger check's recent chats)
    projects: () => Promise.resolve({ data: projects }),
    projectsRead: () => projects,
    moreChat: (host: unknown, key: unknown) => (host ? null : findProjectChat(projects, key)),
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
  const dash = { onState: () => ({ dispose() {} }), onPetEvent: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), state: () => demoState(NOW), setVisible() {} };
  const host = new ViewHost(vscode.Uri.file("/ext") as never, dash as never, {} as never);
  const tree = (vscode as unknown as { recorded: { treeViews: Map<string, { badge: unknown }> } }).recorded.treeViews.get("talpyDen.badge")!;
  host.setBadge(0, 2);
  assert.deepEqual(tree.badge, { value: 2, tooltip: "2 chats finished" });
  let dispose = () => {};
  const view = {
    badge: undefined as unknown,
    webview: { options: {}, html: "", postMessage: async () => true, onDidReceiveMessage: () => ({ dispose() {} }), asWebviewUri: (u: unknown) => u, cspSource: "" },
    visible: false, onDidChangeVisibility: () => ({}), onDidDispose: (f: () => void) => ((dispose = f), {}),
  };
  host.resolveWebviewView(view as never);
  assert.deepEqual(view.badge, { value: 2, tooltip: "2 chats finished" });
  assert.equal(tree.badge, undefined);
  host.setBadge(1, 2);
  assert.deepEqual(view.badge, { value: 1, tooltip: "1 chat needs you" });
  assert.equal(tree.badge, undefined);
  dispose();
  assert.deepEqual(tree.badge, { value: 1, tooltip: "1 chat needs you" });
  host.setBadge(0, 0);
  assert.equal(tree.badge, undefined);
});

// "Open the Recap" (the Monday notification): the view's page shows it now
// if it's loaded, else once it is; a page that loads later starts on Chats
test("a tab shown goes to the view's page once, not to a page that loads hours later", () => {
  const dash = { onState: () => ({ dispose() {} }), onPetEvent: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), state: () => demoState(NOW), setVisible() {} };
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
  // (an SSH host's are never looked for there, nor what it doesn't list)
  receive({ type: "openPlan", groupId: g.id, host: state.hosts[0]?.name ?? "box", plan: "demo-plan-1" });
  receive({ type: "open", chat: { host: state.hosts[0]?.name ?? "box", key: ".claude/demo-6/project" } });
  receive({ type: "openMemory", groupId: g.id, memory: "nope" });
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
