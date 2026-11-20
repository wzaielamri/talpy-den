// What a comparison (a chat's changed files, before and now) is, and whether a
// file is inside a folder; no VS Code in it.

import * as fs from "node:fs";
import * as path from "node:path";

export interface ComparisonItem {
  label: string;
  path: string; // the file now
  original: string; // a copy of it from before
  created: boolean; // it didn't exist before
  deleted: boolean; // it's gone now
}

export interface Comparison {
  title: string;
  folder: string;
  items: ComparisonItem[];
}

export function isComparison(x: unknown): x is Comparison {
  const c = x as Comparison;
  return (
    !!c &&
    typeof c.title === "string" &&
    Array.isArray(c.items) &&
    c.items.every(
      (i) => !!i && typeof i.path === "string" && i.path.startsWith("/") && typeof i.original === "string" && typeof i.label === "string",
    )
  );
}

// Is file (followed through links) inside folder?
export function inside(file: string, folder: string): boolean {
  try {
    const real = fs.realpathSync(file);
    const base = fs.realpathSync(folder);
    return real.startsWith(base + path.sep);
  } catch {
    return false;
  }
}
