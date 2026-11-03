// The status bar shows Talpy, held still in the panel icon's pose for the
// state, from the extension's own icon font. Its spinner ($(loading~spin))
// had VS Code redraw the window 60 times a second while a chat worked: about
// 8% of a core, under other windows too (measured 2026-11-02).

import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { test } from "node:test";
import { demoState } from "../src/shared/demo";
import type { Group, Overall, SessionState, ViewState } from "../src/shared/types";
import { StatusBar } from "../src/statusBar";
import { recorded } from "./vscode-stub";

const NOW = 1_800_000_000_000;
const STATES: Overall[] = ["waiting", "working", "idle", "none"];

test("every state has its Talpy in the extension's icon font", () => {
  const manifest = JSON.parse(fs.readFileSync("package.json", "utf8"));
  const icons = manifest.contributes.icons;
  const chars = new Set<string>();
  for (const s of STATES) {
    const icon = icons[`talpy-den-${s}`];
    assert.ok(icon, `an icon for ${s}`);
    assert.ok(fs.existsSync(path.resolve(icon.default.fontPath)), icon.default.fontPath);
    assert.match(icon.default.fontCharacter, /^\\E00[0-3]$/);
    chars.add(icon.default.fontCharacter);
  }
  assert.equal(chars.size, STATES.length, "a glyph each");
});

function withStates(state: ViewState, to: SessionState[]): ViewState {
  const copy: ViewState = JSON.parse(JSON.stringify(state));
  let i = 0;
  for (const g of copy.status?.groups ?? []) {
    const n = Math.max(0, Math.min(g.sessions.length, to.length - i));
    g.sessions = g.sessions.slice(0, n).map((s) => ({ ...s, state: to[i++] }));
  }
  copy.hosts = [];
  return copy;
}

test("the status bar shows Talpy still, never a spinner", () => {
  const bar = new StatusBar();
  const item = recorded.statusBarItems.at(-1)!;
  assert.equal(item.text, "$(talpy-den-none)");
  bar.update(withStates(demoState(NOW), ["working", "working", "idle"]));
  assert.match(item.text, /^\$\(talpy-den-working\) 2( · \d+%)?$/);
  bar.update(withStates(demoState(NOW), ["waiting", "working"]));
  assert.match(item.text, /^\$\(talpy-den-waiting\) 1( · \d+%)?$/);
  bar.update(withStates(demoState(NOW), []));
  assert.match(item.text, /^\$\(talpy-den-(idle|none)\)( \d+%)?$/);
  assert.doesNotMatch(fs.readFileSync("src/statusBar.ts", "utf8"), /~spin/);
  bar.dispose();
});

// One item, not two: with two or more accounts it names the one VS Code's
// Claude runs on, its 5-hour usage next to it; the hover links to switching
test("the status bar item names VS Code's Claude's account, with its usage, and links to switching it", () => {
  const bar = new StatusBar();
  const item = recorded.statusBarItems.at(-1)!;
  const state = withStates(demoState(NOW), ["waiting", "working"]);
  const own = state.status!.groups.find((g) => g.profileKeys.includes(".claude") && g.limits?.windows.length)!;
  assert.ok(own, "VS Code's Claude's account in the demo, with usage");
  const other: Group = { ...own, id: "work", name: "work", title: "work · Team", profileKeys: [".claude-work"], sessions: [], limits: null };
  state.status!.groups.push(other);
  const pct = `${Math.round(own.limits!.windows[0].pct)}%`;
  const shown = { name: own.name, group: own, tip: `VS Code's Claude runs on ${own.title}.`, link: "Change the default account…" };
  bar.update(state, shown);
  assert.equal(item.text, `$(talpy-den-waiting) 1 · ${own.name} ${pct}`);
  const tip = item.tooltip as { value: string; isTrusted: unknown };
  assert.ok(tip.value.includes(`VS Code's Claude runs on ${own.title}. [$(account) Change the default account…](command:talpyDen.switchAccount)`), tip.value);
  assert.deepEqual(tip.isTrusted, { enabledCommands: ["talpyDen.switchAccount"] });
  // nothing working: Talpy, the account and its usage
  bar.update({ ...state, status: { ...state.status!, groups: state.status!.groups.map((g) => ({ ...g, sessions: [] })) } }, shown);
  assert.match(item.text, new RegExp(`^\\$\\(talpy-den-(idle|none)\\) ${own.name} \\d+%$`));
  // the usage shown is another account's (VS Code's has no numbers): it says whose
  bar.update(state, { ...shown, name: other.name, group: other });
  assert.equal(item.text, `$(talpy-den-waiting) 1 · ${other.name} · ${own.name} ${pct}`);
  // one account: nothing to tell apart, no name, no link
  bar.update(state, null);
  assert.equal(item.text, `$(talpy-den-waiting) 1 · ${pct}`);
  assert.ok(!(item.tooltip as { value: string }).value.includes("command:"));
  bar.dispose();
});
