// FakeHost, the host the core's tests run on, answers as VS Code's host does where the core relies on it: the
// order of the focus events, inspect for a setting set nowhere, and watchers of other sections that go when
// they're disposed.

import assert from "node:assert/strict";
import { test } from "node:test";
import { FakeHost } from "./fakeHost";

test("FakeHost tells the focus before the use, for one change of the window's state", () => {
  const fake = new FakeHost();
  const heard: string[] = [];
  fake.focus.onDidChangeUse((u) => heard.push(`use ${u}`));
  fake.focus.onDidChange((f) => heard.push(`focus ${f}`));
  fake.setFocused(true);
  fake.setActive(false); // (the use alone)
  assert.deepEqual(heard, ["focus true", "use true", "use false"]);
});

test("FakeHost's settings.inspect answers for a setting set nowhere, as VS Code does: no value anywhere", () => {
  const fake = new FakeHost();
  assert.deepEqual(fake.settings.inspect("reopenIn"), { global: undefined });
  fake.set("reopenIn", "talpyChat");
  assert.deepEqual(fake.settings.inspect("reopenIn"), { global: "talpyChat" });
});

test("FakeHost's watchOther tells each watcher the keys it watches that changed, until it's disposed: then it's gone", () => {
  const fake = new FakeHost();
  const heard: string[][] = [];
  const fonts = fake.settings.watchOther(["editor.fontFamily", "terminal.integrated.fontFamily"])((keys) => heard.push(keys));
  const docker = fake.settings.watchOther(["dev.containers.dockerPath"])((keys) => heard.push(keys));
  assert.equal(fake.watching, 2);
  fake.setOther("editor.fontFamily", "Fira Code");
  fake.setOther("workbench.colorTheme", "Dark");
  assert.deepEqual(heard, [["editor.fontFamily"]]);
  fonts.dispose();
  assert.equal(fake.watching, 1, "the disposed watcher is gone");
  fake.setOther("editor.fontFamily", "Iosevka");
  fake.setOther("dev.containers.dockerPath", "podman");
  assert.deepEqual(heard, [["editor.fontFamily"], ["dev.containers.dockerPath"]]);
  docker.dispose();
  assert.equal(fake.watching, 0);
});
