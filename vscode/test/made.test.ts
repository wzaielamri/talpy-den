// What Claude made, in Talpy Chat (pane.py made.py, webview/components/MadeLine.tsx): the folded
// line's words, what unfolding asks for, and the extension asking pane.py only for a file or a
// Read the conversation shows as made, a picture coming back as a data: URL.

import assert from "node:assert/strict";
import { mock, test } from "node:test";
import * as vscode from "vscode";
import { ChatPanes } from "../src/chatPane";
import { demoState } from "../src/shared/demo";
import { findParts, madeAsk, madeLine, madeOf, madeSize, newBelow, showsOn, type PaneItem } from "../src/shared/pane";
import { recorded } from "./vscode-stub";

const NOW = 1_800_000_000_000;

const made = (key: string, m: Partial<NonNullable<PaneItem["made"]>> & { path: string }, text?: string): PaneItem => ({
  kind: "made", key, of: key.split("/made/")[0], at: NOW, text: text ?? m.path.split("/").pop(),
  made: { type: "picture", name: m.path.split("/").pop()!, size: null, ...m },
});

test("a made file's folded line: its name and size, or that it isn't there any more", () => {
  assert.deepEqual([0, 512, 1023, 1024, 1600, 2047, 300 * 1024, 1024 * 1024 - 1, 1024 * 1024, 5.25 * 1024 * 1024].map(madeSize),
                   ["0 B", "512 B", "1023 B", "1 KB", "2 KB", "2 KB", "300 KB", "1024 KB", "1.0 MB", "5.3 MB"]);
  assert.equal(madeSize(null), "");
  assert.equal(madeLine(made("t1/made/0", { path: "/a/icon.svg", size: 2048 })), "icon.svg · 2 KB");
  assert.equal(madeLine(made("t1/made/0", { path: "/p/plans/x.md", type: "plan", size: 3000 }, "Plan: Ship it")), "Plan: Ship it · 3 KB");
  assert.equal(madeLine(made("t1/made/0", { path: "/a/page.html", type: "page" })), "page.html");
  assert.equal(madeLine(made("t1/made/0", { path: "/tmp/shot.png", size: 90, gone: true })), "shot.png · not there any more");
});

test("unfolding asks for the file as it is now, or what Claude saw; nothing for a file gone or another file", () => {
  assert.deepEqual(madeAsk(made("a", { path: "/a/icon.svg" }).made!), { path: "/a/icon.svg" });
  assert.deepEqual(madeAsk(made("a", { path: "/tmp/shot.png", step: "toolu_1" }).made!), { path: "/tmp/shot.png", step: "toolu_1" });
  assert.equal(madeAsk(made("a", { path: "/a/icon.svg", gone: true }).made!), null);
  assert.equal(madeAsk(made("a", { path: "/a/paper.pdf", type: "file" }).made!), null);
  const items: PaneItem[] = [{ kind: "tool", key: "r1", at: NOW, name: "Read" }, made("r1/made/0", { path: "/tmp/shot.png", step: "r1" }),
                             { kind: "claude", key: "c1", at: NOW, text: "see /a/b.png" }, made("c1/made/0", { path: "/a/b.png" })];
  const of = madeOf(items);
  assert.deepEqual([[...of.paths], [...of.steps]], [["/tmp/shot.png", "/a/b.png"], ["r1"]]);
  assert.deepEqual([...madeOf(undefined).paths], []);
});

test("a made file shows on both tabs, is found by its name, and counts as new below", () => {
  const it = made("w1/made/0", { path: "/a/icon.svg" }, "icon.svg");
  assert.equal(showsOn(it, false), true);
  assert.equal(showsOn(it, true), true);
  assert.deepEqual(findParts(it, false), ["icon.svg", ""]);
  assert.equal(newBelow(new Set(["x"]), [{ kind: "note", key: "x", at: NOW, text: "" }, it], false), 1);
});

test("the tab gets a made file only if the conversation shows it: a picture as a data: URL, a plan's text, else why not", async () => {
  const asked: string[][] = [];
  const answers: Record<string, Record<string, unknown>> = {
    "/a/icon.svg": { ok: true, type: "picture", mime: "image/svg+xml", data: "PHN2Zy8+", size: 6 },
    "/tmp/shot.png": { ok: true, type: "picture", mime: "image/png", data: "iVBORw0K", size: 6, seen: true },
    "/p/plans/x.md": { ok: true, type: "plan", text: "# Ship it", cut: false, size: 9 },
    "/a/evil.png": { ok: true, type: "picture", mime: "text/html", data: "PGI+", size: 3 },
    "/a/gone.png": { ok: false, gone: true, message: "It isn't there any more" },
  };
  const items: PaneItem[] = [made("w1/made/0", { path: "/a/icon.svg" }), made("r1/made/0", { path: "/tmp/shot.png", step: "r1" }),
                             made("p1/made/0", { path: "/p/plans/x.md", type: "plan" }, "Plan: Ship it"),
                             made("w2/made/0", { path: "/a/evil.png" }), made("w3/made/0", { path: "/a/gone.png" })];
  const backend = {
    pane: async (args: string[]) => {
      if (args[0] === "--conversation") return args.includes("--wait") ? { ok: true, unchanged: true } : { ok: true, items, more: false, stamp: "s1" };
      asked.push(args);
      return answers[args[args.indexOf("--path") + 1]] ?? { ok: false, message: "?" };
    },
  };
  const dash = { opened() {}, state: () => demoState(NOW), refresh: async () => undefined, pollHost: async () => undefined, onState: () => ({ dispose() {} }),
                 onLive: () => ({ dispose() {} }), onUsageCameIn: () => ({ dispose() {} }), liveHook: false };
  const p = new ChatPanes(vscode.Uri.file("/ext") as never, backend as never, dash as never, {} as never, { find: async () => undefined } as never, {} as never);
  const tick = () => new Promise((r) => setTimeout(r, 10));
  p.open({ chatId: "c-made", sessionId: "c-made", profileDir: ".claude", name: "x" } as never);
  const panel = recorded.panels.at(-1)!;
  panel.show(true);
  panel.receive({ type: "ready" });
  await tick();
  const ask = async (m: Record<string, unknown>) => {
    panel.receive({ type: "made", ...m });
    await tick();
    return panel.sent.filter((x) => (x as { type: string }).type === "made").at(-1);
  };
  assert.deepEqual(await ask({ id: 1, path: "/a/icon.svg" }), { type: "made", id: 1, ok: true, src: "data:image/svg+xml;base64,PHN2Zy8+" });
  assert.deepEqual(await ask({ id: 2, path: "/tmp/shot.png", step: "r1" }), { type: "made", id: 2, ok: true, src: "data:image/png;base64,iVBORw0K" });
  assert.deepEqual(await ask({ id: 3, path: "/p/plans/x.md" }), { type: "made", id: 3, ok: true, text: "# Ship it", cut: false });
  assert.deepEqual(await ask({ id: 4, path: "/a/evil.png" }), { type: "made", id: 4, ok: true });   // (only a picture's type makes a data: URL)
  assert.deepEqual(await ask({ id: 5, path: "/a/gone.png" }), { type: "made", id: 5, ok: false, message: "It isn't there any more", gone: true });
  const before = asked.length;
  assert.deepEqual(await ask({ id: 6, path: "/home/me/.ssh/id_ed25519" }), { type: "made", id: 6, ok: false, message: "Not a file this chat made" });
  assert.deepEqual(await ask({ id: 7, path: "/tmp/shot.png", step: "toolu_other" }), { type: "made", id: 7, ok: false, message: "Not a file this chat made" });
  assert.equal(asked.length, before);   // (pane.py never asked for those)
  assert.deepEqual(asked[1].slice(0, 6), ["--made", "c-made", "--path", "/tmp/shot.png", "--step", "r1"]);
  // Open: this computer's, only what the conversation shows
  const opened: string[] = [];
  const cmd = mock.method(vscode.commands, "executeCommand", async (id: string, uri?: { fsPath?: string }) => void opened.push(`${id} ${uri?.fsPath}`));
  const ext = mock.method(vscode.env, "openExternal", async (uri: { fsPath?: string }) => (opened.push(`external ${uri.fsPath}`), true));
  try {
    panel.receive({ type: "openMade", path: "/a/icon.svg" });
    panel.receive({ type: "openMade", path: "/p/plans/x.md" });
    panel.receive({ type: "openMade", path: "/etc/passwd" });
    await tick();
  } finally {
    cmd.mock.restore();
    ext.mock.restore();
  }
  assert.deepEqual(opened, ["vscode.open /a/icon.svg", "vscode.open /p/plans/x.md"]);
  panel.dispose();
});
