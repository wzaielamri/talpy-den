// The Claude Code config folders (profiles) on this computer.

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { extraConfigDirs } from "../../settings";

export function profileDirs(): string[] {
  const home = os.homedir();
  const dirs = [path.join(home, ".claude")];
  try {
    for (const name of fs.readdirSync(home).sort()) if (name.startsWith(".claude-")) dirs.push(path.join(home, name));
  } catch {
    // no home listing
  }
  dirs.push(...extraConfigDirs());
  const seen = new Set<string>();
  return dirs.filter((d) => {
    try {
      const st = fs.statSync(d);
      const real = fs.realpathSync(d);
      // (a new one: .profile-name, or Claude's .claude.json once you've started to log in)
      const isProfile =
        st.isDirectory() && ["sessions", "projects", "settings.json", ".profile-name", ".claude.json"].some((f) => fs.existsSync(path.join(d, f)));
      if (!isProfile || seen.has(real)) return false;
      seen.add(real);
      return true;
    } catch {
      return false;
    }
  });
}
