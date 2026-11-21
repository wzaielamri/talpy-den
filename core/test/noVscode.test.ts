import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

// core/ runs outside VS Code (in the desktop app), so no file in it may import
// vscode or electron. `tsc -p ../core` (npm run check) fails on any import of
// them tsc reads (core/tsconfig.json); this also catches a plain require(…).
// `npm test` runs in vscode/, so core/src is ../core/src.
function tsFiles(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory() ? tsFiles(path.join(dir, e.name)) : e.name.endsWith(".ts") ? [path.join(dir, e.name)] : []);
}

// `… from "vscode"`, `import "vscode"`, `import("vscode")` (typeof import(…) too), `require("vscode")`; electron's
const IMPORTS_HOST = /(?:from\s+|import\s*\(\s*|import\s+|require\s*\(\s*)["'](vscode|electron)["']/;

test("each way of importing vscode or electron is caught", () => {
  const caught = [
    'import * as vscode from "vscode";',
    "import type { Uri } from 'vscode';",
    'export { window } from "vscode";',
    'import "vscode";',
    'const v = await import("vscode");',
    'type V = typeof import( "vscode" );',
    'const v = require("vscode");',
    'import v = require ( "vscode" );',
    'import { app } from "electron";',
    "const { app } = require('electron');",
  ];
  for (const line of caught) assert.ok(IMPORTS_HOST.test(line), line);
  const not = [
    'import * as fs from "node:fs";',
    'import { x } from "./vscodeHost";',
    'import { y } from "vscode-uri";',
    "// what VS Code's window does",
    'const label = "vscode";',
  ];
  for (const line of not) assert.ok(!IMPORTS_HOST.test(line), line);
});

test("nothing under core/src imports vscode or electron", () => {
  const files = tsFiles(path.resolve(process.cwd(), "../core/src"));
  assert.ok(files.length > 0, "found no files under core/src");
  for (const f of files) assert.ok(!IMPORTS_HOST.test(fs.readFileSync(f, "utf8")), `${f} imports vscode or electron`);
});
