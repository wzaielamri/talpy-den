// Builds the extension (Node, for VS Code's local extension host) and the
// webview (browser). --production minifies and leaves out source maps;
// --tests bundles test/*.test.ts into out/test for `node --test`; --harness
// bundles the dev pages' scripts (dev/*.tsx) into dev/out, to look at the
// webview with demo data in a browser.
//
// Every run first copies into vendor/ the parts of the widget (the rest of
// this repository) that the extension ships or bundles: the Python backend,
// Talpy (the pet), codeview.mjs, ansi.mjs (a command's colours), the icon table (icons.mjs), Talpy Chat's keys (keys.mjs), its search and folding (find.mjs) and the status-line snippet. They are changed
// where they are, never in vendor/, which isn't committed. --vendor only
// copies; --watch copies again when one of them changes.
import * as esbuild from "esbuild";
import { existsSync, mkdirSync, readFileSync, readdirSync, rmSync, watch as watchFolder, writeFileSync } from "node:fs";
import * as path from "node:path";

const production = process.argv.includes("--production");
const watch = process.argv.includes("--watch");
const tests = process.argv.includes("--tests");
const harness = process.argv.includes("--harness");
const onlyVendor = process.argv.includes("--vendor");

// [folder in the repository, folder in vendor/, which of its files]
const VENDOR = [
  ["../package/contents/code", "code", (name) => name.endsWith(".py")],
  ["../package/contents/ui/talpy", "talpy", (name) => name.endsWith(".mjs") || name.endsWith(".d.mts")],
  ["../package/contents/ui", ".", (name) => /^(codeview|icons|ansi|keys|find|bookmarks|quote)\.(mjs|d\.mts)$/.test(name)],
  ["..", ".", (name) => name === "statusline-snippet.sh"],
];

function vendor() {
  const keep = new Set();
  for (const [from, to, take] of VENDOR) {
    const folder = path.join("vendor", to);
    mkdirSync(folder, { recursive: true });
    keep.add(folder);
    for (const name of readdirSync(from).filter(take)) {
      const file = path.join(folder, name);
      keep.add(file);
      const data = readFileSync(path.join(from, name));
      // (an unchanged file isn't written: --watch would rebuild for nothing)
      if (!existsSync(file) || !readFileSync(file).equals(data)) writeFileSync(file, data);
    }
  }
  // What the widget no longer has, and a test run's __pycache__
  for (const [, to] of VENDOR) {
    const folder = path.join("vendor", to);
    for (const name of readdirSync(folder)) {
      if (!keep.has(path.join(folder, name))) rmSync(path.join(folder, name), { recursive: true, force: true });
    }
  }
}

const common = {
  bundle: true,
  loader: { ".svg": "dataurl" },   // (an icon the webview imports: media/talpy-chat.svg)
  minify: production,
  sourcemap: production ? false : "linked",
  logLevel: "info",
  legalComments: "none",
};

const builds = harness
  ? [{
      ...common,
      entryPoints: readdirSync("dev").filter((f) => f.endsWith(".tsx")).map((f) => `dev/${f}`),
      outdir: "dev/out",
      platform: "browser",
      format: "iife",
      target: "chrome114",
      jsx: "automatic",
      jsxImportSource: "preact",
    }]
  : tests
  ? [{
      ...common,
      sourcemap: false,
      entryPoints: readdirSync("test").filter((f) => f.endsWith(".test.ts")).map((f) => `test/${f}`),
      outdir: "out/test",
      platform: "node",
      format: "cjs",
      target: "node18",
      jsx: "automatic",
      jsxImportSource: "preact",
      alias: { vscode: "./test/vscode-stub.ts" },
    }]
  : [
      {
        ...common,
        entryPoints: ["src/extension.ts"],
        outfile: "dist/extension.js",
        platform: "node",
        format: "cjs",
        target: "node18",
        external: ["vscode"],
      },
      {
        ...common,
        entryPoints: { webview: "webview/main.tsx", chat: "webview/chat.tsx", doc: "webview/doc.tsx", "webview-style": "webview/styles.css" },
        outdir: "dist",
        platform: "browser",
        format: "iife",
        target: "chrome114",
        jsx: "automatic",
        jsxImportSource: "preact",
      },
    ];

vendor();
if (onlyVendor) {
  // copied, nothing to build
} else if (watch) {
  let again;
  for (const [from] of VENDOR) watchFolder(from, () => { clearTimeout(again); again = setTimeout(vendor, 100); });
  for (const options of builds) await (await esbuild.context(options)).watch();
} else {
  await Promise.all(builds.map((options) => esbuild.build(options)));
}
