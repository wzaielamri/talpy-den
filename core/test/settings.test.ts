import assert from "node:assert/strict";
import * as os from "node:os";
import * as path from "node:path";
import { test } from "node:test";
import { cacheDir, configDirArgs, setReopenIn, setSshHosts, settings, useSettingsHost } from "../src/settings";
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

test("configDirArgs reads the extra config dirs", () => {
  const fake = make();
  delete process.env.CLAUDE_CONFIG_DIR;
  fake.set("extraConfigDirs", ["/data/a", " ~/b "]);
  assert.deepEqual(configDirArgs(), ["--config-dir", "/data/a", "--config-dir", path.join(os.homedir(), "b")]);
});

test("setSshHosts writes talpyDen.sshHosts", async () => {
  const fake = make();
  await setSshHosts(["h1", "h2"]);
  assert.deepEqual(fake.recorded.updates, [{ section: "talpyDen", key: "sshHosts", value: ["h1", "h2"], scope: "global" }]);
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
