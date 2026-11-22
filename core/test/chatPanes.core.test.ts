// Talpy Chat on its host alone (no vscode): a chat's surface gets its first state once its page is ready,
// the + button's file dialog (pictures only for an SSH host's chat), the conversation's font following the
// editor's and the terminal's, and Open on a file Claude made. (The side questions panel's choices kept in
// the host's state: vscode/test/pane.test.ts, on VsCodeHost and VS Code's surfaces.)

import assert from "node:assert/strict";
import * as os from "node:os";
import { pathToFileURL } from "node:url";
import { test } from "node:test";
import type { Actions } from "../src/actions";
import type { Backend } from "../src/agents/claudeCode/backend";
import { ChatPanes } from "../src/chatPanes";
import type { Dashboard } from "../src/dashboard";
import { Emitter } from "../src/events";
import type { ChatPage, EditorPort, PaneSurface, PaneSurfaces, TerminalPort } from "../src/ports";
import { useSettingsHost } from "../src/settings";
import { demoState } from "../src/shared/demo";
import { chatRefOf } from "../src/shared/model";
import type { PaneHostMessage, PaneItem, PaneMessage } from "../src/shared/pane";
import type { ChatRef } from "../src/shared/types";
import { FakeHost } from "./fakeHost";

const NOW = 1_800_000_000_000;

// A chat's surface: what it was posted, and a way to say what its page says (say) or to close it
class FakeSurface implements PaneSurface {
  posts: PaneHostMessage[] = [];
  visible = true;
  active = false;
  disposed = false;
  private received = new Emitter<PaneMessage>();
  private changed = new Emitter<void>();
  private gone = new Emitter<void>();
  readonly onDidReceive = this.received.event;
  readonly onDidChangeView = this.changed.event;
  readonly onDidDispose = this.gone.event;

  constructor(readonly key: string, public title: string, readonly page: ChatPage) {}

  post(message: PaneHostMessage): void {
    if (!this.disposed) this.posts.push(message);
  }
  reveal(): void {}
  resourceUri(path: string): string {
    return `page-resource:${path}`;
  }
  say(message: unknown): void {
    this.received.fire(message as PaneMessage);
  }
  of<T extends PaneHostMessage["type"]>(type: T): Extract<PaneHostMessage, { type: T }>[] {
    return this.posts.filter((m): m is Extract<PaneHostMessage, { type: T }> => m.type === type);
  }
  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.gone.fire(undefined);
  }
}

class FakeSurfaces implements PaneSurfaces {
  opened: FakeSurface[] = [];
  open(key: string, title: string, page: ChatPage): PaneSurface {
    const surface = new FakeSurface(key, title, page);
    this.opened.push(surface);
    return surface;
  }
  openLater(): boolean {
    return false;
  }
}

const tick = () => new Promise((r) => setTimeout(r, 10));

// The core's ChatPanes over a FakeHost and FakeSurfaces; items: what a read of the conversation gives
const setup = (items: PaneItem[] = []) => {
  const fake = new FakeHost();
  useSettingsHost(fake);
  const surfaces = new FakeSurfaces();
  const backend = {
    pane: async (args: string[]) => (args.includes("--wait") ? { ok: true, unchanged: true } : { ok: true, items, more: false, stamp: "s1" }),
  } as unknown as Backend;
  const state = demoState(NOW);
  const dash = {
    opened() {}, state: () => state, refresh: async () => undefined, pollHost: async () => undefined, setActionError() {}, setActionInfo() {},
    onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), liveHook: false,
  } as unknown as Dashboard;
  const actions = { canMoveToClaudeCode: () => false } as unknown as Actions;
  const terminals = { find: async () => undefined } as unknown as TerminalPort;
  const panes = new ChatPanes(fake, backend, dash, surfaces, actions, terminals, {} as EditorPort);
  return { fake, surfaces, panes, state };
};

test("opening a chat posts its first state to its surface", async () => {
  const { surfaces, panes, state } = setup();
  const row = state.status!.groups.flatMap((g) => g.sessions).find((s) => s.state !== "waiting")!;
  try {
    panes.open(chatRefOf(row));
    assert.equal(surfaces.opened.length, 1);
    const surface = surfaces.opened[0];
    assert.equal(surface.key, `|${row.chatId || row.sessionId}`);
    assert.equal(surface.title, row.name);
    assert.deepEqual(surface.page, { tab: "chat", local: true, scale: 1.15, split: true, font: "var(--vscode-editor-font-family, monospace)",
                                     suggest: true, side: { open: false, pick: "" }, fresh: false });
    assert.equal(surface.posts.length, 0, "nothing before its page is ready");
    surface.say({ type: "ready" });
    await tick();
    const first = surface.posts[0];
    assert.equal(first.type, "chat");
    if (first.type === "chat") assert.deepEqual([first.chat.chatId, first.chat.name, first.chat.host], [row.chatId || row.sessionId, row.name, ""]);
    assert.equal(surface.of("conversation").length, 1, "then its conversation");
    assert.deepEqual(surface.of("focusReply"), [{ type: "focusReply", asking: false }], "the cursor in its reply box");
  } finally {
    panes.dispose();
  }
});

test("pickFiles on an SSH host's chat offers pictures only and posts the picked paths", async () => {
  const { fake, surfaces, panes } = setup();
  fake.answer.choose = () => ["/home/me/shot.png", "/home/me/diagram.webp"];
  try {
    panes.open({ key: "h-1", chatId: "h-1", sessionId: "h-1", profileDir: ".claude", name: "on lab", host: "lab" } as ChatRef);
    const surface = surfaces.opened[0];
    assert.equal(surface.page.local, false);
    surface.say({ type: "pickFiles" });
    await tick();
    // (this computer's files, which go there, also in a window connected to it)
    assert.deepEqual(fake.recorded.choices, [{ kind: "file", many: true, openLabel: "Attach", title: "Attach to your reply", defaultPath: os.homedir(),
                                               filters: { Pictures: ["png", "jpg", "jpeg", "webp", "gif"] }, localOnly: true }]);
    assert.deepEqual(surface.of("picked"), [{ type: "picked", paths: ["/home/me/shot.png", "/home/me/diagram.webp"] }]);
  } finally {
    panes.dispose();
  }
});

test("pickFiles on this computer's chat offers any file of its folder; none picked, an empty list is posted", async () => {
  const { fake, surfaces, panes } = setup();
  try {
    panes.open({ key: "l-1", chatId: "l-1", sessionId: "l-1", profileDir: ".claude", name: "here", cwd: "/home/me/repo" } as ChatRef);
    surfaces.opened[0].say({ type: "pickFiles" });
    await tick();
    assert.deepEqual(fake.recorded.choices, [{ kind: "file", many: true, openLabel: "Attach", title: "Attach to your reply", defaultPath: "/home/me/repo",
                                               localOnly: true }]);
    assert.deepEqual(surfaces.opened[0].of("picked"), [{ type: "picked", paths: [] }], "(Escape: an empty list, as before)");
  } finally {
    panes.dispose();
  }
});

test("the conversation's font follows talpyDen.chatFont and the terminal's and the editor's fonts as they change", async () => {
  const { fake, surfaces, panes } = setup();
  try {
    panes.open({ key: "f-1", chatId: "f-1", sessionId: "f-1", profileDir: ".claude", name: "x" } as ChatRef);
    const surface = surfaces.opened[0];
    fake.setOther("terminal.integrated.fontFamily", "Iosevka Term");
    fake.setOther("editor.fontFamily", "Fira Code");
    fake.set("chatFont", "editor");
    fake.set("chatFont", "ui");
    fake.setOther("workbench.colorTheme", "Dark");   // (not a font: nothing)
    assert.deepEqual(surface.of("font").map((m) => m.family), ["Iosevka Term", "Iosevka Term", "Fira Code", ""]);
    panes.open({ key: "f-2", chatId: "f-2", sessionId: "f-2", profileDir: ".claude", name: "y" } as ChatRef);
    assert.equal(surfaces.opened[1].page.font, "", "the next chat's page starts with it");
  } finally {
    panes.dispose();
  }
});

test("Open on a file Claude made: a picture or a plan in the host's viewer, another file in its own app", async () => {
  const made = (key: string, path: string, type: string): PaneItem =>
    ({ kind: "made", key, of: key.split("/made/")[0], at: NOW, text: path, made: { type, name: path, size: null, path } }) as PaneItem;
  const { fake, surfaces, panes } = setup([made("w1/made/0", "/a/icon.svg", "picture"), made("w2/made/0", "/a/my report #2.pdf", "file"),
                                           made("p1/made/0", "/p/plans/x.md", "plan")]);
  try {
    panes.open({ key: "m-1", chatId: "m-1", sessionId: "m-1", profileDir: ".claude", name: "x" } as ChatRef);
    const surface = surfaces.opened[0];
    surface.say({ type: "ready" });
    await tick();
    for (const path of ["/a/icon.svg", "/a/my report #2.pdf", "/p/plans/x.md", "/etc/passwd"]) surface.say({ type: "openMade", path });
    await tick();
    assert.deepEqual(fake.recorded.files, ["/a/icon.svg", "/p/plans/x.md"]);
    assert.deepEqual(fake.recorded.external, [pathToFileURL("/a/my report #2.pdf").href], "(as a file: URL, its # and spaces kept)");
  } finally {
    panes.dispose();
  }
});

// (2026-11-22) A tab of a chat on an SSH host read it every 5 s while Claude worked or waited (every second after a
// send), each read sending ~270 KB of code over a slow link: its host's watcher is told its chat, the tab reads it
// when the watcher says it was written there, and otherwise looks only every minute, no chase, while that watcher
// answers for it
test("a host's tab: its watcher is told its chat, and it reads it when that was written there", async () => {
  const fake = new FakeHost();
  useSettingsHost(fake);
  const surfaces = new FakeSurfaces();
  const reads: string[][] = [];
  const backend = {
    pane: async (args: string[]) => (reads.push(args), { ok: true, items: [], more: false, stamp: `s${reads.length}` }),
  } as unknown as Backend;
  const changed = new Emitter<{ host: string; changed: string[]; requests: boolean; wrote: string[] }>();
  const told: [string[], [string, string[]][]][] = [];
  let polls = 0;
  let watched = true;
  const state = demoState(NOW);
  const dash = {
    opened() {}, state: () => state, refresh: async () => undefined, pollHost: async () => undefined, pollHostSoon: () => void polls++,
    setActionError() {}, setActionInfo() {}, onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }), liveHook: false,
    onHostChanged: changed.event, hostWatched: (_h: string, chat?: string) => watched && chat === "h-1",
    setPaneHosts: (hosts: Iterable<string>, chats: Map<string, string[]>) => void told.push([[...hosts], [...chats]]),
  } as unknown as Dashboard;
  const actions = { canMoveToClaudeCode: () => false } as unknown as Actions;
  const terminals = { find: async () => undefined } as unknown as TerminalPort;
  const panes = new ChatPanes(fake, backend, dash, surfaces, actions, terminals, {} as EditorPort);
  try {
    panes.open({ key: "h-1", chatId: "h-1", sessionId: "h-1", profileDir: ".claude", name: "on lab", host: "lab" } as ChatRef);
    assert.deepEqual(told.at(-1), [["lab"], [["lab", ["h-1"]]]], "its host's watcher watches its chat");
    const surface = surfaces.opened[0];
    surface.say({ type: "ready" });
    await tick();
    const first = reads.length;
    assert.ok(first >= 1);
    changed.fire({ host: "lab", changed: [], requests: false, wrote: ["h-1"] });
    await tick();
    assert.equal(reads.length, first + 1, "written there: read now");
    assert.equal(polls, 0, "and that's no reason to check the host");
    changed.fire({ host: "lab", changed: [], requests: false, wrote: ["another"] });
    changed.fire({ host: "box", changed: [], requests: false, wrote: ["h-1"] });
    await tick();
    assert.equal(reads.length, first + 1, "another chat's, another host's: nothing");
    // (its looks: every minute while the watcher answers for it, even just after a send; else 5 s, a second after a send)
    const pane = [...(panes as unknown as { panes: Map<string, { lookEvery(): number; chaseUntil: number }> }).panes.values()][0];
    pane.chaseUntil = Date.now() + 30000;
    assert.equal(pane.lookEvery(), 60000);
    watched = false;
    assert.equal(pane.lookEvery(), 1000);
    pane.chaseUntil = 0;
    assert.equal(pane.lookEvery(), 5000);
  } finally {
    panes.dispose();
  }
});
