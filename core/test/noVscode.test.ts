import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

// core/ runs outside VS Code (in the desktop app), so no file in it may import
// vscode or electron. `npm test` runs in vscode/, so core/src is ../core/src.
function tsFiles(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory() ? tsFiles(path.join(dir, e.name)) : e.name.endsWith(".ts") ? [path.join(dir, e.name)] : []);
}

test("nothing under core/src imports vscode or electron", () => {
  const files = tsFiles(path.resolve(process.cwd(), "../core/src"));
  assert.ok(files.length > 0, "found no files under core/src");
  const bad = /from\s+["'](vscode|electron)["']|require\(["'](vscode|electron)["']\)/;
  for (const f of files) assert.ok(!bad.test(fs.readFileSync(f, "utf8")), `${f} imports vscode or electron`);
});
