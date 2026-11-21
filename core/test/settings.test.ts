import assert from "node:assert/strict";
import * as os from "node:os";
import * as path from "node:path";
import { test } from "node:test";
import { cacheDir, chatFont, chatOptionArgs, configDirArgs, setChatOptions, setReopenIn, setSshHosts, settings, useSettingsHost } from "../src/settings";
import { FakeHost } from "./fakeHost";

const make = () => {
  const fake = new FakeHost();
  useSettingsHost(fake);
  return fake;
};

test("a setting changed through the host is read at once", () => {
  const fake = make();
  assert.equal(settings.notifyWaiting(), true);
  fake.set("notifyWaiting", false);
  assert.equal(settings.notifyWaiting(), false);
});

test("chatFont: the terminal's font, else the editor's; editor: the editor's; ui: the host's own", () => {
  const fake = make();
  assert.equal(chatFont(), "var(--vscode-editor-font-family, monospace)", "none set: the editor's, as the page names it");
  fake.setOther("editor.fontFamily", "Fira Code");
  assert.equal(chatFont(), "Fira Code");
  fake.setOther("terminal.integrated.fontFamily", "Iosevka Term");
  assert.equal(chatFont(), "Iosevka Term");
  fake.set("chatFont", "editor");
  assert.equal(chatFont(), "Fira Code");
  fake.set("chatFont", "ui");
  assert.equal(chatFont(), "");
});

test("configDirArgs reads the extra config dirs", (t) => {
  const fake = make();
  const saved = process.env.CLAUDE_CONFIG_DIR;
  t.after(() => {
    if (saved === undefined) delete process.env.CLAUDE_CONFIG_DIR;
    else process.env.CLAUDE_CONFIG_DIR = saved;
  });
  delete process.env.CLAUDE_CONFIG_DIR;
  fake.set("extraConfigDirs", ["/data/a", " ~/b "]);
  assert.deepEqual(configDirArgs(), ["--config-dir", "/data/a", "--config-dir", path.join(os.homedir(), "b")]);
});

test("setSshHosts writes talpyDen.sshHosts", async () => {
  const fake = make();
  await setSshHosts(["h1", "h2"]);
  assert.deepEqual(fake.recorded.updates, [{ section: "talpyDen", key: "sshHosts", value: ["h1", "h2"], scope: "global" }]);
});

// (application settings: only your user settings hold them)
test("setChatOptions writes the model, effort and mode new chats start with in your user settings", async () => {
  const fake = make();
  await setChatOptions("sonnet", "high", "plan");
  assert.deepEqual(fake.recorded.updates, [
    { section: "talpyDen", key: "newChatModel", value: "sonnet", scope: "global" },
    { section: "talpyDen", key: "newChatEffort", value: "high", scope: "global" },
    { section: "talpyDen", key: "newChatMode", value: "plan", scope: "global" },
  ]);
  assert.deepEqual(chatOptionArgs(), ["--model", "sonnet", "--effort", "high", "--permission-mode", "plan"]);
});

test("setReopenIn writes where reopenIn is already set", async () => {
  const fake = make();
  await setReopenIn("claudeCode");
  fake.settings.inspect = () => ({ global: "terminal", workspace: "talpyChat" });
  await setReopenIn("terminal");
  fake.settings.inspect = () => ({ global: "terminal", workspace: "talpyChat", workspaceFolder: "claudeCode" });
  await setReopenIn("talpyChat");
  assert.deepEqual(fake.recorded.updates.map((u) => u.scope), ["global", "workspace", "workspaceFolder"]);
});

test("cacheDir follows XDG_CACHE_HOME", () => {
  make();
  const saved = process.env.XDG_CACHE_HOME;
  try {
    process.env.XDG_CACHE_HOME = "/x/cache";
    assert.equal(cacheDir(), path.join("/x/cache", "talpy-den"));
    delete process.env.XDG_CACHE_HOME;
    assert.equal(cacheDir(), path.join(os.homedir(), ".cache", "talpy-den"));
  } finally {
    if (saved === undefined) delete process.env.XDG_CACHE_HOME;
    else process.env.XDG_CACHE_HOME = saved;
  }
});

test("reading a setting before any host is set says so", () => {
  useSettingsHost(undefined as never);
  assert.throws(() => settings.notifyWaiting(), /no settings host: call useSettingsHost first/);
});
