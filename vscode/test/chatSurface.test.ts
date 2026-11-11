// Talpy Chat in the secondary side bar (talpyDen.chatPlace: sideBar): its
// view holds one chat at a time, the next one opened takes its place, and a
// chat's tab stays a tab where the setting says so or VS Code has no such bar.

import assert from "node:assert/strict";
import { test } from "node:test";
import * as vscode from "vscode";
import { ChatPanes } from "../src/chatPane";
import { emptyView, sideBarSupported, ViewSurface } from "../src/chatSurface";
import { demoState } from "../src/shared/demo";
import { chatRefOf } from "../src/shared/model";
import { changeSettings, overrides, recorded, setVersion } from "./vscode-stub";

const NOW = 1_800_000_000_000;

// A view as VS Code hands it to its provider: what was set on it, and a way to show, hide and close it
function fakeView() {
  const visibility = new Set<() => void>();
  const closed = new Set<() => void>();
  const sent: unknown[] = [];
  let receive: (m: unknown) => void = () => undefined;
  const view = {
    description: undefined as string | undefined,
    visible: true,
    shown: 0,
    webview: {
      options: {} as { enableScripts?: boolean },
      html: "",
      cspSource: "vscode-webview:",
      asWebviewUri: (u: unknown) => u,
      postMessage: async (m: unknown) => (sent.push(m), true),
      onDidReceiveMessage: (l: (m: unknown) => void) => ((receive = l), { dispose() {} }),
    },
    onDidChangeVisibility: (l: () => void) => (visibility.add(l), { dispose: () => void visibility.delete(l) }),
    onDidDispose: (l: () => void) => (closed.add(l), { dispose: () => void closed.delete(l) }),
    show: () => void view.shown++,
  };
  return {
    view,
    sent,
    page: (m: unknown) => receive(m),
    setVisible: (on: boolean) => ((view.visible = on), visibility.forEach((l) => l())),
    close: () => closed.forEach((l) => l()),
  };
}

test("VS Code 1.106 and later has a secondary side bar for a view", () => {
  assert.equal(sideBarSupported("1.105.3"), false);
  assert.equal(sideBarSupported("1.106.0"), true);
  assert.equal(sideBarSupported("1.145.2"), true);
  assert.equal(sideBarSupported("2.0.0"), true);
  assert.equal(sideBarSupported("0.9"), false);
});

test("the view is a chat's place until the chat closes: its name beside the view's, its keys while its page has the focus", () => {
  const { view, setVisible } = fakeView();
  const surface = new ViewSurface(view as never, { enableScripts: true });
  assert.equal(view.webview.options.enableScripts, true);
  surface.title = "fix the tests";
  assert.equal(view.description, "fix the tests");
  assert.equal(surface.visible, true);
  assert.equal(surface.active, false, "VS Code doesn't say which view has the focus: the page does");
  surface.focus(true);
  assert.equal(surface.active, true);
  setVisible(false);
  assert.deepEqual([surface.visible, surface.active], [false, false]);
  setVisible(true);
  let gone = 0;
  surface.onDidDispose(() => gone++);
  surface.reveal();
  assert.equal(view.shown, 1);
  surface.dispose();
  surface.dispose();
  assert.equal(gone, 1, "said once");
  surface.title = "another chat's";
  surface.reveal();
  assert.deepEqual([view.description, view.shown, surface.visible], ["fix the tests", 1, false], "given back: nothing of it changes the view any more");
  emptyView(view as never);
  assert.equal(view.description, undefined);
  assert.equal(view.webview.options.enableScripts, false);
  assert.match(view.webview.html, /No chat here yet/);
});

test("a chat opens in Talpy Chat's view in the side bar, one at a time; with Chat Place on tab, in a tab of its own", async () => {
  const state = demoState(NOW);
  const rows = state.status!.groups.flatMap((g) => g.sessions);
  const dash = {
    opened() {}, state: () => state, refresh: async () => undefined, pollHost: async () => undefined, setActionError() {}, setActionInfo() {},
    onState: () => ({ dispose() {} }), onLive: () => ({ dispose() {} }),
  };
  const panes = new ChatPanes(vscode.Uri.file("/ext") as never, { pane: async () => ({ ok: true, message: "" }) } as never, dash as never,
                              {} as never, { find: async () => undefined } as never, {} as never);
  const side = panes.sideBar();
  const provider = recorded.viewProviders.get("talpyDen.chatView") as { resolveWebviewView(view: unknown): void };
  assert.ok(provider, "its view has a provider");
  const tabs = () => recorded.panels.length;
  const before = tabs();

  try {
    // (a VS Code without that bar: a tab, whatever the setting says)
    panes.open(chatRefOf(rows[0]));
    assert.equal(tabs(), before + 1);
    recorded.panels.at(-1)!.dispose();
    setVersion("1.110.0");
    changeSettings("talpyDen.chatPlace");

    // (set to tab: an editor tab for each chat, as it was)
    overrides.set("chatPlace", "tab");
    changeSettings("talpyDen.chatPlace");
    panes.open(chatRefOf(rows[0]));
    assert.equal(tabs(), before + 2);

    // the setting's default: the side bar
    overrides.delete("chatPlace");
    changeSettings("talpyDen.chatPlace");
    // the view isn't made yet: VS Code makes it (its focus command), and the chat shows once it has
    panes.open(chatRefOf(rows[1]));
    assert.equal(tabs(), before + 2, "no tab for it");
    const made = fakeView();
    provider.resolveWebviewView(made.view);
    assert.equal(made.view.description, rows[1].name);
    assert.match(made.view.webview.html, /chat\.js/);
    assert.equal(made.view.webview.options.enableScripts, true);
    assert.equal(made.view.shown, 1);

    // its keys go to it only while its page has the focus (a tab can be the editor in front all the while)
    assert.equal(panes.key("allow"), false);
    made.page({ type: "focus", on: true });
    made.page({ type: "ready" });
    await new Promise((r) => setTimeout(r, 0));
    assert.equal(panes.key("allow"), true);
    assert.deepEqual(made.sent.filter((m) => (m as { type: string }).type === "key"), [{ type: "key", key: "allow" }]);
    made.page({ type: "focus", on: false });
    assert.equal(panes.key("allow"), false);

    // the next chat takes its place; the same one again only comes to the front
    panes.open(chatRefOf(rows[2]));
    assert.equal(made.view.description, rows[2].name);
    assert.equal(made.view.shown, 2);
    panes.open(chatRefOf(rows[2]));
    assert.deepEqual([made.view.description, made.view.shown, tabs()], [rows[2].name, 3, before + 2]);

    // back to tabs: the view's chat closes (its view goes), and the next one opens in a tab
    overrides.set("chatPlace", "tab");
    changeSettings("talpyDen.chatPlace");
    assert.match(made.view.webview.html, /No chat here yet/);
    panes.open(chatRefOf(rows[2]));
    assert.equal(tabs(), before + 3);
  } finally {
    overrides.delete("chatPlace");
    setVersion("1.90.0");
    side.dispose();
    panes.dispose();
  }
});
