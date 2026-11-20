// Settings for a test that runs extension code outside VS Code: read through a VsCodeHost over the stub
// (so a test sets one with stub.overrides). Imported for its effect.

import type * as vscode from "vscode";
import { useSettingsHost } from "../../core/src/settings";
import { VsCodeHost } from "../src/vscodeHost";
import { settingNames } from "../src/legacySettings";
import * as fs from "node:fs";

const quiet = { info() {}, warn() {}, error() {} } as unknown as vscode.LogOutputChannel;

export const manifest = JSON.parse(fs.readFileSync("package.json", "utf8"));
export const host = new VsCodeHost(quiet, settingNames(manifest));
useSettingsHost(host);
