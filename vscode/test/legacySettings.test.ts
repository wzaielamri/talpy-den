import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { carryOverSettings, type Inspected, type SettingsScope, settingNames } from "../src/legacySettings";

const GLOBAL = 1;
const WORKSPACE = 2;

function scope(values: Record<string, Inspected>): SettingsScope & { writes: [string, unknown, number][] } {
  const writes: [string, unknown, number][] = [];
  return {
    writes,
    inspect: (key) => values[key],
    update: async (key, value, target) => {
      writes.push([key, value, target]);
    },
  };
}

test("the old settings carry over, user's and workspace's", async () => {
  const old = scope({ newChatModel: { globalValue: "opus" }, sshHosts: { globalValue: [], workspaceValue: ["lab"] } });
  const now = scope({});
  const n = await carryOverSettings(old, now, ["newChatModel", "sshHosts", "reopenIn"], { global: GLOBAL, workspace: WORKSPACE });
  assert.equal(n, 3);
  assert.deepEqual(now.writes, [
    ["newChatModel", "opus", GLOBAL],
    ["sshHosts", [], GLOBAL],
    ["sshHosts", ["lab"], WORKSPACE],
  ]);
});

test("a value the new setting has already is kept", async () => {
  const old = scope({ newChatModel: { globalValue: "opus", workspaceValue: "haiku" } });
  const now = scope({ newChatModel: { globalValue: "sonnet" } });
  await carryOverSettings(old, now, ["newChatModel"], { global: GLOBAL, workspace: WORKSPACE });
  assert.deepEqual(now.writes, [["newChatModel", "haiku", WORKSPACE]]);
});

test("setting names come from the manifest", () => {
  const manifest = { contributes: { configuration: { properties: { "talpyDen.a": {}, "talpyDen.b": {}, "other.c": {} } } } };
  assert.deepEqual(settingNames(manifest), ["a", "b"]);
  assert.deepEqual(settingNames({}), []);
});

test("setting names come from every category of the manifest", () => {
  const manifest = {
    contributes: {
      configuration: [
        { title: "General", properties: { "talpyDen.a": {} } },
        { title: "Chats", properties: { "talpyDen.b": {}, "other.c": {} } },
        { title: "Empty" },
      ],
    },
  };
  assert.deepEqual(settingNames(manifest), ["a", "b"]);
});

test("the extension's own manifest names every setting it has", () => {
  const manifest = JSON.parse(readFileSync(join(__dirname, "..", "..", "package.json"), "utf8"));
  const names = settingNames(manifest);
  assert.ok(names.length >= 40, String(names.length));
  for (const name of ["pollInterval", "openIn", "sshHosts", "playfulTalpy", "pythonPath"]) assert.ok(names.includes(name), name);
});

// A repo's .vscode/settings.json, or the Machine settings of the SSH host or
// container a window is connected to, named the program run as Python here,
// started your new chats with bypassPermissions, or a usage cap of 1%
test("what runs or is read on this computer comes only from your user settings", () => {
  const manifest = JSON.parse(readFileSync(join(__dirname, "..", "..", "package.json"), "utf8"));
  const properties = Object.assign({}, ...manifest.contributes.configuration.map((s: { properties: object }) => s.properties));
  for (const name of ["pythonPath", "extraConfigDirs", "sshHosts", "recapHistory"]) {
    assert.equal(properties[`talpyDen.${name}`].scope, "application", name);
    assert.equal(properties[`talpyDen.${name}`].ignoreSync, true, name);
  }
  for (const name of ["newChatModel", "newChatEffort", "newChatMode", "usageCap"])
    assert.equal(properties[`talpyDen.${name}`].scope, "application", name);
});
