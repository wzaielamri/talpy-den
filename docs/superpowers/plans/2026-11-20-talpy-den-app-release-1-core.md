# Talpy Den app, release 1: the core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move Talpy Den's host logic out of the VS Code extension into a `core/` that imports nothing from VS Code and asks its host for UI and settings through one interface, with agent-neutral types, so the app (release 3) can run the same core; VS Code runs it in-process and its users see no change.

**Architecture:** `core/src` holds the logic and the shared types. It reaches its host only through `HostServices` (messages, pickers, inputs, dialogs, progress, settings, focus, clipboard, links, log) and through small ports for what only one host can do (terminals, VS Code's changes view, doc tab, plan review, Claude's own VS Code panel, chat panels). `vscode/src/vscodeHost.ts` implements `HostServices` with VS Code's API; the VS Code-only classes implement the ports; `vscode/src/extension.ts` wires them. The existing esbuild build bundles `core/src` into the extension through relative imports; `core/` gets its own `tsconfig.json` with Node types only, which proves it doesn't touch VS Code.

**Tech Stack:** TypeScript (strict, ES2022), esbuild, `node:test`, Preact webview (unchanged), Python backend (unchanged), CI on Node 22.

**Spec:** `docs/superpowers/specs/2026-11-20-talpy-den-app-design.md` (sections "The core", "Agent adapters", "Releases, in order" item 1). Releases 2–5 get plans of their own, written once this one has landed.

## Progress and handoff

Kept current after every task (the owner's rule: "always save and update the
plan so new chats can follow up"). A new chat resumes from here: read this
section, then the next open task.

- **Execution:** subagent-driven (owner, 2026-11-20). A fresh agent implements each task, a fresh reviewer checks it before the next one, and the whole branch is reviewed at the end.
- **Branch:** `worktree-app-core-r1`, in the worktree `.claude/worktrees/app-core-r1` (from `main` f90282e9; commit a140142c ignores `.superpowers/`).
- **Execution ledger:** `.superpowers/sdd/2026-11-20-talpy-den-app-release-1-core/progress.md` in that worktree (git-ignored scratch). It holds the pre-flight scan and its rulings: R1, `live.test.ts` moves in Task 8; R2, Task 4's `cacheDir` test names the rule `cacheDir()` follows today; R3, VS Code-side subscriptions adapt to the core's single-argument `Event`; R4, Task 12 Step 4 waits for the owner's go-ahead.
- **Before Task 1:** the VS Code webview animation fix (an agent's branch `worktree-agent-…` in `.claude/worktrees/agent-…`, started 2026-11-20) must be reviewed and merged into `main`, then `main` merged into `worktree-app-core-r1`. Status: the agent is still running. **If this chat ends first:** check `git worktree list` and the agent's branch for commits; review them (tests: `cd vscode && npm run check && npm test`, `python3 -m unittest discover -s tests`); merge when they're good; then start Task 1.
- **Also before Task 1:** Talpy Chat's task strip split (the owner's report, 2026-11-20). In both `ChatPane.qml` and `chat.tsx`, the strip's line opens only the tasks; without a task list, it opens the subagents. The header's Agents tag opens only the subagents. With both shown, a small "Subagents" heading sits over the subagent tree. With a task list, the heading shows whenever the subagents are shown, even with the tasks folded, so they never hang off the task line. Status: **done**, merged into `main` (c29b3b91, 32138761, 86bbc605) and into this branch. Checked with the full Python suite (1669 OK), VS Code check and tests (401 of 401), and screenshots of the VS Code harness.

| Task | Status | Commits | Review | Notes |
|---|---|---|---|---|
| 1 Core folder, build, tests | done | 3a532755, f7963eda | clean after 1 fix round | 401 → 406 tests. Core tests build to `vscode/out/test/core/`; the extension's stay in `out/test/` (R6). `Emitter.fire` isolates listener errors, as `vscode.EventEmitter` does. |
| 2 HostServices, FakeHost, VsCodeHost | done | 7031abf4, 6e9ad962 | clean after 1 fix round | 406 → 430 tests. The contract gained what today's code needs (the Task 2 block above shows it): `update(…, scope?)`, `updateOther`, `watchOther`, `ChooseOptions.localOnly`. `FakeHost` records `updates` and has `setOther`. |
| 3 Shared types, agent-neutral | done | 469194c1, cf7e0df1 | clean after 1 fix round | 430 → 433 tests; Python 1669 OK. The Python tests, `docs/claude-code-updates.md` and the comments that named `vscode/src/shared` now name `core/src/shared`. The row-key test needs the webview, so it stays in `vscode/test/rowKey.test.ts`. The tests build clears `out/test` first, so stale bundles don't run. Open for later: `core/src/shared/pane.ts` imports `vscode/vendor/*.mjs`. |
| 4 Settings through the host | done | 59ecc5f8, 55b50e25 | clean after 1 fix round | 433 → 439 tests; Python 1669 OK. `useSettingsHost` runs first in `activate`; reading a setting before it throws "no settings host". `setReopenIn` writes in the scope where the setting is set. `VsCodeHost(log, settingKeys)` gets its keys from `settingNames(context.extension.packageJSON)`, so no manifest is bundled. VS Code tests set the host through `vscode/test/useHost.ts`, except `activate.test`, which must not. |
| 5 VS Code-free modules | done | ea3e834d | clean | Still 439 tests; Python 1669 OK. 8 tests moved to `core/test` on `FakeHost`; `live.test` stays until Task 8. `remoteHost.ts` is split: `currentRemoteAuthority` and `windowHostFile` use VS Code, so they stay in `vscode/src/remoteHost.ts` for Task 6's ports. |
| 6 Ports | done | 669e20c7, 603f76ef | clean after 1 fix round | 439 → 446 tests. `TerminalPort` (`find`, `run`; handle `show`/`sendText`), `ChatPanesPort` (`open`, `openNew`, `answer`, `reply`, `draft`), and `EditorPort` (12 members, each traced to a call site, including `claudeCodeInstalled`). `HostServices.environment.remoteAuthority`. Plan and memory files of the window's host open through `EditorPort.showDoc`/`editFile` with `onWindowHost`. Then `main` (with the animation fix) merged in: 462 tests. |
| 7 Notify and away | done | 999624bf, 6158f542 | clean after 1 fix round | 462 → 468 tests; Python 1670 OK. `HostServices.focus` gained `inUse`/`onDidChangeUse` (away used the window's `active`, else `focused`). `host.message` takes strings or `{title}` items and returns the caller's own one, so same-titled buttons stay apart (a question option "Open" against the notification's Open). `Dashboard` takes `host` as a last parameter for `AwayWatch`. |
| 8 Dashboard | not started | | | |
| 9 Actions | not started | | | |
| 10 Accounts, relay, dictation, agent runs | not started | | | |
| 11 Talpy Chat's logic | not started | | | |
| 12 Wiring, VS Code check, docs | not started | | | |

Decisions taken during execution (details in the ledger):
- R5: Task 1 started before the animation fix merged. Task 1 touches nothing the fix touches; the fix must be in `main` and here before Task 3.
- R6: test bundles. The extension's tests stay in `vscode/out/test/<name>.test.js`, because six of them find files through `__dirname/../..`. Core's tests go to `out/test/core/`. A test that moves to `core/test` and reads files through `__dirname` switches to paths from `process.cwd()`; `npm test` runs in `vscode/`.
- R7: `node --test` prints `ℹ tests N / ℹ pass N / ℹ fail N`, not `# tests N`. The baseline was 401.
- Task 1: `Emitter.fire` reports a throwing listener with `console.error` and goes on to the others, as `vscode.EventEmitter` does. This keeps later swaps free of any behaviour change.
- R8, for Tasks 7–11: `HostServices` doesn't yet cover everything the modules still to move use. Each task adds the smallest member it needs, with `VsCodeHost`, `FakeHost` and a test, as Task 2's fix round did. Found so far:
  - Task 7: `notify` uses `MessageItem`s.
  - Task 8: `dashboard` uses `env.sessionId`.
  - Task 9: `actions` uses `createQuickPick` with buttons; its window folders need their scheme.
  - Task 10: `accountSwitch` uses `getExtension` (now `EditorPort.claudeCodeInstalled`), a reload and its own commands.
  - Task 11: `chatPanes` uses the chat font and a `Memento`.
- Task 12: pass `VsCodeEditor` its `planReview` when wiring, the same one `actions` gets. Left unset, plan feedback goes out without the comments.
- The animation fix and the task-strip split are in `main` and merged here.

**After Task 12 and the final review (owner, 2026-11-20): remove the tests that are no longer needed or useful.**
- Release 1's rule that the test count never drops covers the moves only. This cleanup comes after them, as its own reviewed step.
- Candidates:
  - tests that duplicate another test's coverage, e.g. a VS Code test and a core test of the same scenario;
  - text assertions that pin code shapes the moves made obsolete;
  - tests of code that no longer exists.
- Each removal gets a one-line reason, and the owner gets the list.

## Global Constraints

- Release 1 changes nothing VS Code users see: no setting, command, message, view or behaviour changes; every existing test keeps passing, with at least as many tests as before (Task 1 records the count).
- Nothing under `core/src` imports `vscode` (or `electron`): `tsc -p ../core` with Node types only, and `core/test/noVscode.test.ts`.
- Core code runs on Node 18 or newer (esbuild `target: "node18"`), TypeScript strict, ES2022, CommonJS output as today.
- The Python backend (`package/contents/code`) is not changed.
- Checks: `cd vscode && npm ci --ignore-scripts && npm run check && npm test`, and `python3 -m unittest discover -s tests` from the repository root.
- Start from `main` with the VS Code UI animation work merged (it touches `vscode/webview` and may touch `vscode/src/shared`).
- Commits: plain prose in the style of `git log`, no Co-Authored-By or any line crediting Claude; the pre-commit public check (`.githooks`, `tools/check_public.py`) must pass, never bypassed.
- Moves keep history: `git mv`, then edit.
- No `AgentAdapter` interface yet: Claude Code's modules are grouped under `core/src/agents/claudeCode/`, chats and accounts carry an agent id, and accounts have capabilities. The adapter interface is written together with the ACP adapter, when a second agent shows its real shape (spec, "Agent adapters": "Now: only the Claude Code adapter").

## Review Focus

1. **A setting changed in VS Code's Settings editor reaches the core at once** (turning `talpyDen.notifyWaiting` off stops the next notification): Task 2 test `settings onDidChange fires with the changed talpyDen keys`; Task 4 test `a setting changed through the host is read at once`.
2. **Several VS Code windows**: only the window that leads notifies, and focus changes hand over as before: Task 2 test `focus mirrors window state and fires on change`; Task 7 keeps `vscode/test/notify.test.ts` passing through `VsCodeHost`.
3. **Destructive confirmations stay modal, and Escape cancels** (deleting a chat, a plan, a memory): Task 2 tests `message passes modal and detail` and `a cancelled message returns undefined`; Task 9 test `delete with no answer deletes nothing`.
4. **Remote-SSH windows**: "same machine" decisions (`env.remoteName`) and the folder dialog on the remote keep working: Task 2 tests `environment mirrors remoteName and web` and `choose on the remote uses the remote scheme`.
5. **Quick picks with separators and icons** (accounts, hosts, new-chat folders) look and pick as before, and the picked item is the caller's own object (callers compare by identity): Task 2 test `pick maps separators and icons and returns the caller's item`.

---

## File Structure

```
core/
  tsconfig.json                     strict; types ["node"] from ../vscode/node_modules/@types
  src/
    events.ts                       Emitter<T>, Event<T>, Disposable (in place of vscode.EventEmitter / Disposable)
    host.ts                         HostServices and its option and item types
    ports.ts                        TerminalPort, TerminalHandle, Place, EditorPort, ChatPanesPort
    agents.ts                       AgentId, Capabilities, CLAUDE_CODE
    settings.ts                     from vscode/src/config.ts, read through the host
    comparisons.ts                  the pure part of vscode/src/changes.ts
    terminal.ts                     the pure helpers of vscode/src/terminals.ts
    shared/                         from vscode/src/shared: types, model, pane, week, demo
    agents/claudeCode/              backend, live, remoteHost, hostWatch, sshControl, found, oldChats,
                                    vscodeAccount, profiles (profileDirs from statusline.ts),
                                    claudePanel (its pure functions)
    platform/linux/desktop.ts       from vscode/src/desktop.ts
    transitions.ts, openRequests.ts
    notify.ts, away.ts, dashboard.ts, actions.ts, accounts.ts, accountSwitch.ts,
    relay.ts, dictation.ts, agentRun.ts, chatPanes.ts
  test/
    fakeHost.ts                     FakeHost implements HostServices
    noVscode.test.ts, events.test.ts, settings.test.ts, agents.test.ts
    the pure tests moved from vscode/test (backend, found, hostWatch, live, model, oldChats,
    openRequests, peek, remoteHost, stats, tasks, transitions)
vscode/
  src/vscodeHost.ts                 HostServices on VS Code's API
  src/vscodeEditor.ts               EditorPort on changes.ts, doc.ts, planReview.ts, claudePanel.ts
  src/terminals.ts                  implements TerminalPort (stays)
  src/chatPane.ts                   the webview panels and views only, around core/src/chatPanes.ts
  src/extension.ts                  builds VsCodeHost, the ports and the core, as today's activate does
  test/vscodeHost.test.ts
  test/vscode-stub.ts               grows the members VsCodeHost needs
  esbuild.mjs                       tests also from ../core/test; outbase ".."
  package.json                      check runs tsc -p ../core; test runs node --test on out/test/**
  webview/tsconfig.json             includes ../../core/src/shared instead of ../src/shared
docs/development.md                 the layout gains core/
```

Integration tests that use the VS Code stub stay in `vscode/test` and import the moved modules from `../../core/src/...`: they now test exactly what VS Code users run (the core through `VsCodeHost`).

---

### Task 1: The core folder, its build and tests

**Files:**
- Create: `core/tsconfig.json`, `core/src/events.ts`, `core/test/events.test.ts`, `core/test/noVscode.test.ts`
- Modify: `vscode/esbuild.mjs` (the `tests` build), `vscode/package.json` (`check`, `test`)

**Interfaces:**
- Produces:
  ```ts
  // core/src/events.ts (the same shape as vscode.EventEmitter, so replacements are mechanical)
  export interface Disposable { dispose(): void }
  export type Event<T> = (listener: (value: T) => void) => Disposable;
  export class Emitter<T> {
    readonly event: Event<T>;
    fire(value: T): void;
    dispose(): void;
  }
  ```

- [ ] **Step 1: Record the baseline.** Run `cd vscode && npm ci --ignore-scripts && npm run check && npm test 2>&1 | tail -8`. Note the `# tests N` and `# pass N` numbers in the task's commit message; every later task must keep `# fail 0` and at least N tests.
- [ ] **Step 2: Write the failing tests.**
  - `events.test.ts`: `listeners hear fire in the order they subscribed`; `a disposed listener hears nothing`; `dispose() drops every listener` (fire after dispose calls none).
  - `noVscode.test.ts`: `nothing under core/src imports vscode or electron`: walks `path.resolve(process.cwd(), "../core/src")` (`npm test` runs in `vscode/`) for `*.ts` files and asserts none matches `/from\s+["'](vscode|electron)["']|require\(["'](vscode|electron)["']\)/`; it also asserts it found at least one file (so a wrong path can't pass).
- [ ] **Step 3: Wire the build.** In `esbuild.mjs`'s `tests` build: entry points from both `test/` and `../core/test/` (`*.test.ts`), `outbase: ".."`, `outdir: "out/test"` (so files land in `out/test/vscode/test/` and `out/test/core/test/`). In `package.json`: `"check": "node esbuild.mjs --vendor && tsc -p . && tsc -p webview && tsc -p ../core"`, `"test": "node esbuild.mjs --tests && node --test \"out/test/**/*.test.js\""`. `core/tsconfig.json`: the options of `vscode/tsconfig.json` but `"types": ["node"]`, `"typeRoots": ["../vscode/node_modules/@types"]`, `"include": ["src/**/*.ts", "test/**/*.ts"]`.
- [ ] **Step 4: Run to see the new tests fail.** `cd vscode && npm test 2>&1 | grep -E "^# (tests|pass|fail)"`. Expected: fail, `Cannot find module '../src/events'`.
- [ ] **Step 5: Implement `Emitter<T>`** in `core/src/events.ts` (a `Set` of listeners; `event` returns a `Disposable` that removes its listener).
- [ ] **Step 6: Run everything.** `npm run check && npm test`. Expected: no type errors; `# fail 0`; tests = baseline + 4.
- [ ] **Step 7: Commit.** `git add core vscode/esbuild.mjs vscode/package.json && git commit` ("Core: a folder of its own…", with the baseline counts).

### Task 2: HostServices, FakeHost and VsCodeHost

**Files:**
- Create: `core/src/host.ts`, `core/test/fakeHost.ts`, `vscode/src/vscodeHost.ts`, `vscode/test/vscodeHost.test.ts`
- Modify: `vscode/test/vscode-stub.ts` (only members `VsCodeHost` uses that it lacks: e.g. `window.showOpenDialog`, `window.withProgress`, `window.setStatusBarMessage`, `env.uiKind`, `env.remoteName`, `UIKind`, `ProgressLocation`, `QuickPickItemKind`, `ConfigurationTarget`, recording what was called)

**Interfaces:**
- Consumes: `Emitter`, `Event`, `Disposable` (Task 1).
- Produces (the contract every later task uses):
  ```ts
  // core/src/host.ts
  export type MessageLevel = "info" | "warning" | "error";
  export interface MessageOptions { modal?: boolean; detail?: string }
  export interface PickItem { label: string; description?: string; detail?: string; picked?: boolean;
    alwaysShow?: boolean; separator?: boolean; icon?: string /* codicon id */ }
  export interface PickOptions { title?: string; placeHolder?: string; matchOnDescription?: boolean;
    matchOnDetail?: boolean; ignoreFocusOut?: boolean }
  export interface InputOptions { title?: string; prompt?: string; placeHolder?: string; value?: string;
    password?: boolean; ignoreFocusOut?: boolean; validateInput?: (value: string) => string | undefined | null }
  export interface ChooseOptions { kind: "folder" | "file"; many?: boolean; title?: string; openLabel?: string;
    defaultPath?: string; onRemote?: boolean /* the window's remote file system (Remote-SSH) */;
    filters?: Record<string, string[]>; localOnly?: boolean /* only this computer's files (file:) */ }
  export type SettingScope = "global" | "workspace" | "workspaceFolder";
  export interface HostSettings {
    get<T>(key: string, fallback: T): T;                 // talpyDen.<key>
    update(key: string, value: unknown, scope?: SettingScope): Promise<void>;  // global unless given (config.ts whereSet)
    inspect(key: string): { global?: unknown; workspace?: unknown; workspaceFolder?: unknown } | undefined;
    other<T>(section: string, key: string, fallback: T): T; // another extension's or VS Code's setting
    updateOther(section: string, key: string, value: unknown): Promise<void>; // global (accountSwitch: claudeCode.environmentVariables)
    watchOther(keys: readonly string[]): Event<string[]>; // which of these full keys a change touched (chatPane: the fonts)
    readonly onDidChange: Event<string[]>;              // the talpyDen keys that changed
  }
  export interface HostServices {
    message<A extends string>(level: MessageLevel, text: string, options?: MessageOptions, ...actions: A[]): Promise<A | undefined>;
    pick<T extends PickItem>(items: readonly T[], options?: PickOptions): Promise<T | undefined>;
    pickMany<T extends PickItem>(items: readonly T[], options?: PickOptions): Promise<T[] | undefined>;
    input(options?: InputOptions): Promise<string | undefined>;
    choose(options: ChooseOptions): Promise<string[] | undefined>;
    progress<R>(options: { where: "window" | "notification"; title: string }, task: () => Promise<R>): Promise<R>;
    statusMessage(text: string, ms: number): void;
    readonly settings: HostSettings;
    readonly focus: { readonly focused: boolean; readonly onDidChange: Event<boolean> };
    readonly clipboard: { read(): Promise<string>; write(text: string): Promise<void> };
    openExternal(url: string): Promise<boolean>;
    openFile(path: string): Promise<void>;      // VS Code: "vscode.open"
    revealFile(path: string): Promise<void>;    // VS Code: "revealFileInOS"
    openSettings(query: string): Promise<void>; // VS Code: "workbench.action.openSettings"
    showView(): Promise<void>;                  // VS Code: "talpyDen.view.focus"
    setContext(key: string, value: unknown): void; // VS Code: "setContext"
    workspaceFolders(): readonly { name: string; path: string }[];
    readonly onDidChangeWorkspaceFolders: Event<void>;
    readonly environment: { readonly remoteName?: string; readonly web: boolean };
    readonly log: { info(m: string): void; warn(m: string): void; error(m: string): void };
  }
  ```
  `FakeHost implements HostServices` (core/test/fakeHost.ts):
  `recorded = { messages: {level, text, options?, actions}[], picks: {items, options?}[], inputs: InputOptions[], choices: ChooseOptions[], external: string[], files: string[], revealed: string[], settingsOpened: string[], views: number, contexts: Map<string, unknown>, status: string[], logs: string[] }`;
  scripted answers `answer: { message?: (text: string, actions: string[]) => string | undefined; pick?: (items: readonly PickItem[]) => PickItem | undefined; pickMany?: (items: readonly PickItem[]) => PickItem[] | undefined; input?: (o: InputOptions) => string | undefined; choose?: (o: ChooseOptions) => string[] | undefined }` (default: undefined, as Escape);
  `values: Map<string, unknown>` behind `settings.get`, `set(key, value)` that updates it and fires `onDidChange([key])`; `others: Map<string, unknown>` keyed `section.key`; `setFocused(f: boolean)` firing `focus.onDidChange`; `clip: string`; `folders: {name, path}[]`; `environment` settable.

- [ ] **Step 1: Write the failing tests** in `vscode/test/vscodeHost.test.ts` (VsCodeHost over the stub; names as in Review Focus):
  `message passes level, text, modal and detail, and returns the chosen action`; `a cancelled message returns undefined`; `pick maps separators and icons and returns the caller's item` (`{separator: true}` → `kind: QuickPickItemKind.Separator`, `icon: "folder"` → `iconPath` a `ThemeIcon("folder")`, returns `===` the item passed in); `pickMany passes canPickMany and returns the caller's items`; `input passes its options, validateInput included`; `choose a folder: canSelectFolders, the default path and the open label`; `choose on the remote uses the remote scheme` (with `env.remoteName` set, `defaultUri` keeps the workspace folder's scheme and authority, as `actions.ts` does today, and `fsPath`s come back); `choose files with filters and many`; `progress uses the window or a notification`; `settings get reads talpyDen.<key>, update writes the global scope`; `settings onDidChange fires with the changed talpyDen keys` (and not for other sections); `settings other reads another section`; `focus mirrors window state and fires on change`; `environment mirrors remoteName and web`; `openFile, revealFile, openSettings, showView and setContext run their VS Code commands`; `clipboard reads and writes`; `openExternal parses the URL`; `statusMessage sets the status bar message`.
- [ ] **Step 2: Run them to see them fail.** `cd vscode && npm test 2>&1 | grep -E "^# (pass|fail)"`. Expected: failures, `Cannot find module '../src/vscodeHost'`.
- [ ] **Step 3: Write `core/src/host.ts`** (the interfaces above) **and `core/test/fakeHost.ts`** (the class above).
- [ ] **Step 4: Implement `class VsCodeHost implements HostServices`** in `vscode/src/vscodeHost.ts`, constructor `(log: vscode.LogOutputChannel)`; it is the only new file that translates between paths and `vscode.Uri`. Extend the stub where a test needs a member.
- [ ] **Step 5: Run everything.** `npm run check && npm test`. Expected: no type errors, `# fail 0`.
- [ ] **Step 6: Commit** ("Core: HostServices…").

### Task 3: The shared types in the core, agent-neutral

**Files:**
- Move: `vscode/src/shared/{types,model,pane,week,demo}.ts` → `core/src/shared/`
- Create: `core/src/agents.ts`, `core/test/agents.test.ts`
- Modify: every import of `./shared/…`, `../src/shared/…` in `vscode/src`, `vscode/test`, `vscode/webview`, `vscode/dev`; `vscode/webview/tsconfig.json` (`include` `../../core/src/shared/**/*.ts` in place of `../src/shared/**/*.ts`); `core/src/shared/types.ts`, `core/src/shared/model.ts`
- Move tests: `vscode/test/{model,peek,stats}.test.ts` → `core/test/`

**Interfaces:**
- Produces:
  ```ts
  // core/src/agents.ts
  export type AgentId = "claude-code";
  export interface Capabilities { accounts: boolean; planUsage: boolean; backgroundJobs: boolean;
    remoteControl: boolean; subagents: boolean; plans: boolean; permissionAnswers: boolean; sshHosts: boolean }
  export interface AgentInfo { id: AgentId; name: string; capabilities: Capabilities }
  export const CLAUDE_CODE: AgentInfo; // id "claude-code", name "Claude", every capability true
  ```
  In `shared/types.ts`: the chat (session) type and the account (group) type gain `agent?: AgentId` (absent means `"claude-code"`, so the Python backend's answers need no change); in `shared/model.ts`: `agentOf(chat): AgentId` and `capabilitiesOf(group): Capabilities` (the agent's capabilities; `CLAUDE_CODE.capabilities` when `agent` is absent).

- [ ] **Step 1: Write the failing tests** in `core/test/agents.test.ts`: `a chat without an agent is Claude Code's`; `a group without an agent has Claude Code's capabilities`; `CLAUDE_CODE has every capability`.
- [ ] **Step 2: Run** `npm test`. Expected: fail (no `agents` module).
- [ ] **Step 3: `git mv` the shared files and the three tests, fix every import** (relative paths into `core/src/shared`), add `agents.ts` and the two fields and helpers.
- [ ] **Step 4: Run** `npm run check && npm test`, and `npm run build && node esbuild.mjs --harness` (the webview and demo pages still build). Expected: no errors, `# fail 0`.
- [ ] **Step 5: Commit** ("Core: the shared types…, agent-neutral…").

### Task 4: Settings through the host

**Files:**
- Move: `vscode/src/config.ts` → `core/src/settings.ts`
- Create: `core/test/settings.test.ts`
- Modify: every importer of `./config` (`vscode/src/*.ts`, `vscode/test/*.ts`); `vscode/src/extension.ts` (calls `useSettingsHost` first thing in `activate`)

**Interfaces:**
- Consumes: `HostServices` (Task 2).
- Produces: `core/src/settings.ts` keeps today's exports with the same names and signatures (`expandHome`, `settings`, `chatOptionArgs`, `setChatOptions`, `viewSettings`, `extraConfigDirs`, `configDirArgs`, `statusArgs`, `setSshHosts`, `setReopenIn`, `cacheDir`), reading through `export function useSettingsHost(host: HostServices): void`, called once by whoever hosts the core (VS Code's `activate`, a test's setup). Today's `getConfiguration("talpyDen")` reads become `host.settings.get`; reads of other sections (`claudeCode`, `dev.containers`, `editor`, `terminal.integrated`) become `host.settings.other`; scope inspection becomes `host.settings.inspect`.

- [ ] **Step 1: Write the failing tests** (`settings.test.ts`, with `FakeHost`): `a setting changed through the host is read at once` (`fake.set("notifyWaiting", false)` → `settings.notifyWaiting === false`); `configDirArgs reads the extra config dirs`; `setSshHosts writes talpyDen.sshHosts`; `cacheDir follows XDG_CACHE_HOME`.
- [ ] **Step 2: Run** `npm test`. Expected: fail (no `settings` module).
- [ ] **Step 3: `git mv` and rewrite the VS Code reads** as above; fix the importers.
- [ ] **Step 4: Run** `npm run check && npm test`. Expected: `# fail 0` (the VS Code tests now read settings through `VsCodeHost` over the stub: their setup calls `useSettingsHost(new VsCodeHost(...))`, done once in a shared test helper if many need it).
- [ ] **Step 5: Commit.**

### Task 5: Pure helpers and VS Code-free modules into the core

**Files:**
- Create from today's files: `core/src/comparisons.ts` (`Comparison`, `isComparison`, `inside` out of `vscode/src/changes.ts`), `core/src/terminal.ts` (`asPaste`, `localAncestors`, `attachClients` and the `Place` type out of `vscode/src/terminals.ts`, if they use no VS Code API; one that does stays and goes behind `TerminalPort` in Task 6), `core/src/agents/claudeCode/profiles.ts` (`profileDirs` out of `vscode/src/statusline.ts`), `core/src/agents/claudeCode/claudePanel.ts` (the functions of `vscode/src/claudePanel.ts` that use no VS Code API)
- Move: `vscode/src/{backend,live,remoteHost,hostWatch,sshControl,found,oldChats,vscodeAccount}.ts` → `core/src/agents/claudeCode/`; `vscode/src/desktop.ts` → `core/src/platform/linux/desktop.ts`; `vscode/src/{transitions,openRequests}.ts` → `core/src/`
- Move tests: `vscode/test/{backend,found,hostWatch,live,oldChats,openRequests,remoteHost,tasks,transitions}.test.ts` → `core/test/` (only those that, after the moves, import nothing that stays in `vscode/src` and no stub; the rest stay and import from the core)
- Modify: the importers; `changes.ts`, `terminals.ts`, `statusline.ts`, `claudePanel.ts` import their moved parts back from the core

**Interfaces:**
- Produces: the same exported names as today, at the new paths. `Backend`'s constructor keeps `(extensionPath: string, python: string)` (its scripts stay in the extension's `vendor/code`).

- [ ] **Step 1:** `git mv` the modules and tests; split out the pure helpers into the files above; fix imports.
- [ ] **Step 2: Run** `npm run check && npm test`. Expected: no type errors (with `tsc -p ../core` proving the moved code uses no VS Code API), `# fail 0`, the moved tests now under `out/test/core/test/`.
- [ ] **Step 3: Run the Python suite** `python3 -m unittest discover -s tests` (it reads the vendored backend). Expected: `OK`.
- [ ] **Step 4: Commit.**

### Task 6: Ports for what only VS Code does

**Files:**
- Create: `core/src/ports.ts`, `vscode/src/vscodeEditor.ts`
- Modify: `vscode/src/terminals.ts` (`class Terminals implements TerminalPort`), `vscode/src/chatPane.ts` (`class ChatPanes implements ChatPanesPort`)

**Interfaces:**
- Produces:
  ```ts
  // core/src/ports.ts
  export type { Place } from "./terminal";
  export interface TerminalHandle { show(): void; sendText(text: string, addNewLine: boolean): void }
  export interface TerminalPort {
    find(ancestors: Set<number>, onWindowHost: boolean): Promise<TerminalHandle | undefined>;
    run(key: string, name: string, command: string, place: Place,
        opts?: { private?: boolean; chatOn?: string }): Promise<TerminalHandle>;
    // plus the other members of Terminals that core code calls, typed the same way
  }
  // What VS Code shows in its own UI and an app does its own way (or not at all)
  export interface EditorPort {
    openComparison(c: Comparison): Promise<void>;     // changes.ts openComparison
    showDoc(/* doc.ts showDoc's parameters, written out with core types: paths as strings */): Promise<void>;
    // planReview.ts and claudePanel.ts members that core code calls (openPanelChat, the PlanReview
    // methods actions.ts uses), typed with core types only
  }
  // The chat panes, as notify.ts and actions.ts use them today (the members of ChatPanes they call)
  export interface ChatPanesPort { /* those members, with core types */ }
  ```
  The rule for every port: exactly the members core code calls today (find them with `grep -n "this\.terminals\.\|this\.panes\.\|planReview\.\|openPanelChat\|showDoc\|openComparison" vscode/src/{notify,actions,accounts,agentRun,dashboard}.ts`), no more; only core types in the signatures (paths are strings; no `vscode.Uri`, `vscode.Terminal`).
  `vscode/src/vscodeEditor.ts`: `class VsCodeEditor implements EditorPort` over `changes.ts`, `doc.ts`, `planReview.ts`, `claudePanel.ts`.

- [ ] **Step 1: Write the failing test** `vscode/test/vscodeEditor.test.ts`: `openComparison opens VS Code's changes view` (the stub records the command `changes.ts` runs today); `showDoc opens Talpy Den's doc tab`.
- [ ] **Step 2: Run** `npm test`. Expected: fail.
- [ ] **Step 3: Write `ports.ts`, `VsCodeEditor`, and the two `implements` clauses** (the classes already have these members; only their parameter and return types change to the port types where they used `vscode.*` types).
- [ ] **Step 4: Run** `npm run check && npm test`. Expected: `# fail 0`.
- [ ] **Step 5: Commit.**

### Task 7: Notifications and "away" in the core

**Files:**
- Move: `vscode/src/{notify,away}.ts` → `core/src/`
- Create: `core/test/notify.core.test.ts`
- Modify: importers; `extension.ts` passes the host and the ports

**Interfaces:**
- Consumes: `HostServices`, `ChatPanesPort`, `settings`, `transitions`, `desktop`.
- Produces: `Notifier` and `Away` with the host as their first constructor parameter: `new Notifier(host: HostServices, backend: Backend, open: (chat: …) => void)` (today's parameters after it, unchanged), `new Away(host, …)`; every `vscode.window.show*Message` → `host.message`, `showInputBox` → `host.input`, `showQuickPick` (with `canPickMany`) → `host.pick` / `host.pickMany`, `window.state.focused` → `host.focus.focused`, `onDidChangeWindowState` → `host.focus.onDidChange`, `vscode.Disposable` → `Disposable`.

- [ ] **Step 1: Write the failing test** `core/test/notify.core.test.ts`: the first scenario of `vscode/test/notify.test.ts`, with `FakeHost` in place of the stub (same demo data, same expected message in `fake.recorded.messages`), plus `an unfocused window that leads notifies; a focused one claims the lead` (`fake.setFocused`).
- [ ] **Step 2: Run** `npm test`. Expected: fail.
- [ ] **Step 3: `git mv` and replace the VS Code calls** as listed; `vscode/test/notify.test.ts` and `away.test.ts` construct with `new VsCodeHost(...)` over the stub.
- [ ] **Step 4: Run** `npm run check && npm test`. Expected: `# fail 0`.
- [ ] **Step 5: Commit.**

### Task 8: The dashboard in the core

**Files:**
- Move: `vscode/src/dashboard.ts` → `core/src/dashboard.ts`
- Create: `core/test/dashboard.core.test.ts`
- Modify: importers (`view.ts`, `extension.ts`, tests)

**Interfaces:**
- Consumes: `HostServices`, `EditorPort` (Claude panel), `Notifier`, `settings`, `Backend`, `agents.ts`.
- Produces: `new Dashboard(host: HostServices, editor: EditorPort, backend: Backend, notifier: Notifier)` (today: `(backend, notifier, log)`; the log is `host.log`); its events are `Emitter`s; `vscode.commands.executeCommand("setContext", …)` → `host.setContext`, `"talpyDen.view.focus"` → `host.showView()`, `"workbench.action.openSettings"` → `host.openSettings`; `onDidChangeWorkspaceFolders` → `host.onDidChangeWorkspaceFolders`. The state it builds sets `agent` on each chat and group (`CLAUDE_CODE.id`; the UI reads nothing new).

- [ ] **Step 1: Write the failing test** `dashboard.core.test.ts`: `with FakeHost and the demo data, the state carries every chat with agent "claude-code"`; `an unfocused window polls at the working interval` (the behaviour behind `dashboard.ts`'s `!vscode.window.state.focused` check: assert the interval value used today).
- [ ] **Step 2: Run.** Expected: fail.
- [ ] **Step 3: `git mv` and replace**; the VS Code tests (`dashboard`, `live`, `keepGoing`, `terminals`, `openIn`, `attach`, `desktop`, `accountSwitch`) build the dashboard with `VsCodeHost` and `VsCodeEditor` over the stub.
- [ ] **Step 4: Run** `npm run check && npm test`. Expected: `# fail 0`.
- [ ] **Step 5: Commit.**

### Task 9: The actions in the core

**Files:**
- Move: `vscode/src/actions.ts` → `core/src/actions.ts`
- Create: `core/test/actions.core.test.ts`
- Modify: importers

**Interfaces:**
- Consumes: `HostServices`, `TerminalPort`, `EditorPort`, `ChatPanesPort`, `Dashboard`, `AccountSwitch` (until Task 10 moves it, a type-only interface in `ports.ts` with the members `actions.ts` calls), `settings`, `comparisons`, `terminal` helpers.
- Produces: `new Actions(host, terminals: TerminalPort, editor: EditorPort, backend, dash, account)` (today `(backend, dash, terminals, log, account)`); `showOpenDialog` → `host.choose({ kind: "folder", onRemote: … })`; `env.remoteName` → `host.environment.remoteName`; `workspace.workspaceFolders` → `host.workspaceFolders()`; `vscode.Uri.file(p)` → `p`; `executeCommand("vscode.open", uri)` → `host.openFile(path)`, `"revealFileInOS"` → `host.revealFile`; `executeCommand("talpyDen.addAccount")` / `("talpyDen.accounts")` → calls of the `Accounts` methods those commands run (passed in as `{ add(): Promise<void>; manage(): Promise<void> }`), not VS Code commands.

- [ ] **Step 1: Write the failing tests** (`actions.core.test.ts`, FakeHost and a fake `TerminalPort` recording `run` calls): `delete with no answer deletes nothing` (the delete confirmation is a modal `warning` message; answering undefined runs no backend call); `opening a terminal chat on this machine runs its open command in a terminal keyed host|chat` (the call at today's `actions.ts:219`); `a new chat's folder dialog on a Remote-SSH window asks the remote file system`.
- [ ] **Step 2: Run.** Expected: fail.
- [ ] **Step 3: `git mv` and replace.** `vscode/test/{openIn,attach,keepGoing,desktop,terminals}.test.ts` construct through `VsCodeHost`.
- [ ] **Step 4: Run** `npm run check && npm test`. Expected: `# fail 0`.
- [ ] **Step 5: Commit.**

### Task 10: Accounts, account switching, the relay, dictation and agent runs in the core

**Files:**
- Move: `vscode/src/{accounts,accountSwitch,relay,dictation,agentRun}.ts` → `core/src/`
- Create: `core/test/accounts.core.test.ts`
- Modify: importers; `ports.ts` (drop the temporary `AccountSwitch` interface from Task 9)

**Interfaces:**
- Consumes: `HostServices`, `EditorPort` (`showDoc`, the Claude panel), `TerminalPort`, `profiles`, `vscodeAccount`, `claudePanel` (core part).
- Produces: each class takes `host` first; `withProgress` → `host.progress`; `env.remoteName` → `host.environment.remoteName`; `env.uiKind === Web` → `host.environment.web`; `vscode.Uri.file` → paths; `showDoc` → `editor.showDoc`.

- [ ] **Step 1: Write the failing test** `accounts.core.test.ts`: `adding an account asks for its name and shows progress in the window` (FakeHost records an `input` and a `progress` with `where: "window"`); `dictation in a web UI says it isn't available` (`environment.web` true → a `warning` message, no backend call).
- [ ] **Step 2: Run.** Expected: fail.
- [ ] **Step 3: `git mv` and replace**; `vscode/test/{accountSwitch,agentRun,dictation,queue}.test.ts` construct through `VsCodeHost`/`VsCodeEditor`.
- [ ] **Step 4: Run** `npm run check && npm test`. Expected: `# fail 0`.
- [ ] **Step 5: Commit.**

### Task 11: Talpy Chat's logic in the core

**Files:**
- Create: `core/src/chatPanes.ts` (from the logic in `vscode/src/chatPane.ts`), `core/test/chatPanes.core.test.ts`
- Modify: `vscode/src/chatPane.ts` (keeps only what needs a `WebviewPanel`/`WebviewView`: creating and revealing panels and views, their HTML and resource URIs, the paste action), `ports.ts` (`ChatPanesPort` is now implemented by the core's `ChatPanes`), `notify.ts`, `actions.ts` (they take the core's `ChatPanes`)

**Interfaces:**
- Produces: `class ChatPanes implements ChatPanesPort` in the core with `new ChatPanes(host, backend, dash, surfaces: PaneSurfaces)`, where `PaneSurfaces` (in `ports.ts`) is what the core asks of the host's chat surfaces: `open(key: string, title: string): PaneSurface`, and `PaneSurface { post(message: HostMessage): void; reveal(): void; readonly visible: boolean; onDidReceive: Event<WebviewMessage>; onDidDispose: Event<void> }`. The `pickFiles` request → `host.choose({ kind: "file", many: true, openLabel: "Attach", title: "Attach to your reply", defaultPath, filters })` (filters only for an SSH host's chat, as today); `env.clipboard` → `host.clipboard`; `env.openExternal` → `host.openExternal`.

- [ ] **Step 1: Write the failing test** `chatPanes.core.test.ts`, with FakeHost and a fake `PaneSurfaces` recording posts: `opening a chat posts its first state to its surface`; `pickFiles on an SSH host's chat offers pictures only and posts the picked paths` (FakeHost `answer.choose` returns two paths → a `{ type: "picked", paths }` post).
- [ ] **Step 2: Run.** Expected: fail.
- [ ] **Step 3: Split `chatPane.ts`**: the logic into `core/src/chatPanes.ts`, the VS Code surfaces stay. `vscode/test/{pane,made,chatSurface}.test.ts` keep passing.
- [ ] **Step 4: Run** `npm run check && npm test`. Expected: `# fail 0`.
- [ ] **Step 5: Commit.**

### Task 12: Wiring, a check in VS Code, docs

**Files:**
- Modify: `vscode/src/extension.ts`, `docs/development.md` (the layout block: `core/` and what lives there; the check and test commands), `docs/vscode.md` (its Development section: the extension bundles `../core`)

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Wire `activate`**: `const host = new VsCodeHost(log); useSettingsHost(host);` then the ports (`new Terminals(…)`, `new VsCodeEditor(…)`), then the core classes in today's order with their new constructors. `vscode/test/activate.test.ts` keeps passing (it activates the extension over the stub).
- [ ] **Step 2: Run** `npm run check && npm test` and `python3 -m unittest discover -s tests`. Expected: no type errors, `# fail 0` with at least the baseline count plus the new tests, `OK`.
- [ ] **Step 3: Package** `npm run package`. Expected: a `talpy-den-<version>.vsix`, no errors.
- [ ] **Step 4: The owner's check in VS Code** (with the owner's go-ahead: it installs the vsix in their VS Code, `code --install-extension talpy-den-<version>.vsix`, then *Developer: Reload Window*): the view shows the chats and usage; a chat opens in Talpy Chat and a reply goes through; a chat that waits notifies (and Allow/Deny work); turning `talpyDen.notifyWaiting` off in Settings stops the next one; a new chat's folder picker opens; in a Remote-SSH window the host's chats show and "same machine" chats open in the right place. Anything different from before is a bug of this release.
- [ ] **Step 5: Docs** as listed. **Step 6: Commit** ("App release 1: the core…", with the final test counts).
