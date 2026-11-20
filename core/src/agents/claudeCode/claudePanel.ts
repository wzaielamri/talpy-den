// Where the Claude Code extension's own chat panel keeps its chats (no VS Code
// in it: the config dir comes in as the setting's value).

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { expandHome } from "../../settings";

// The config dir the Claude Code extension starts claude with on this
// computer: CLAUDE_CONFIG_DIR from claudeCode.environmentVariables, else
// VS Code's own, else ~/.claude.
export function panelConfigDir(vars: unknown, env: NodeJS.ProcessEnv = process.env): string {
  const list: unknown[] = Array.isArray(vars) ? vars : [];
  const entry = list.find((v) => !!v && typeof v === "object" && (v as { name?: unknown }).name === "CLAUDE_CONFIG_DIR") as
    | { value?: unknown }
    | undefined;
  const set = typeof entry?.value === "string" ? entry.value.trim() : "";
  return expandHome(set || env.CLAUDE_CONFIG_DIR || path.join(os.homedir(), ".claude"));
}

// How the backend names a profile: its real folder's name (a link like
// ~/.claude names the profile it points to)
export function profileKey(dir: string): string {
  try {
    return path.basename(fs.realpathSync(dir));
  } catch {
    return path.basename(dir);
  }
}

// Claude Code files a chat under the folder it started in (projects/<the
// folder, mangled> in the config dir), wherever Claude's `cd`s took it
export function filedUnder(configDir: string, folder: string, chatId: string): boolean {
  return fs.existsSync(path.join(configDir, "projects", folder.replace(/[^A-Za-z0-9]/g, "-"), `${chatId}.jsonl`));
}
