// Which account VS Code's Claude (the Claude Code extension's panel) runs on.
// The panel takes CLAUDE_CONFIG_DIR from VS Code's claudeCode.environmentVariables
// setting: changing that and reloading the window switches it, in any setup,
// and nothing else (plain `claude` in a terminal, other sessions) is touched.
// Kept free of the VS Code API, for tests.

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

function realOr(p: string): string {
  try {
    return fs.realpathSync(p);
  } catch {
    return path.resolve(p);
  }
}

// The CLAUDE_CONFIG_DIR value for a profile folder, or null for none: a plain
// ~/.claude only reads its account (~/.claude.json) without the variable. The
// profile ~/.claude links to is named by the link, as terminals name it (two
// names for one folder start two background services that wait on each other).
export function configDirFor(profileDir: string, home = os.homedir()): string | null {
  const real = realOr(profileDir);
  const link = path.join(home, ".claude");
  let st: fs.Stats | null = null;
  try {
    st = fs.lstatSync(link);
  } catch {
    // no ~/.claude
  }
  if (st && realOr(link) === real) return st.isSymbolicLink() ? link : null;
  return real;
}

// claudeCode.environmentVariables with CLAUDE_CONFIG_DIR set to value, or
// left out for null; the other variables stay as they are
export function withConfigDir(vars: unknown, value: string | null): unknown[] {
  const keep = (Array.isArray(vars) ? vars : []).filter(
    (v) => !(v && typeof v === "object" && (v as { name?: unknown }).name === "CLAUDE_CONFIG_DIR"),
  );
  return value === null ? keep : [...keep, { name: "CLAUDE_CONFIG_DIR", value }];
}
