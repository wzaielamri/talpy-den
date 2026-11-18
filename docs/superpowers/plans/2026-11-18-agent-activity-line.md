# Agent Activity Line Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agent rows (and the main chat's line) say what they do in readable words, show their current context size, and, when unfolded, list the exact tool calls still running and for how long.

**Architecture:** All data comes from what Talpy Den already reads: the transcript tail that `agent_end` reads, the job `state.json` that `session_row` reads, and the live hook's events. `talpy_den.py` gains `tool_intent()` (readable line) and per-agent `running` and `context`. The live hook gets the same readable line for `doing`. The Plasma (`AgentTree.qml`, `main.qml`) and VS Code (`AgentTree.tsx`, `model.ts`) trees render the new fields.

**Tech Stack:** Python 3 stdlib (unittest), QML (Plasma 6), TypeScript/Preact (VS Code webview, node test runner).

**Spec:** `docs/superpowers/specs/2026-11-18-agent-activity-line-design.md`

## Global Constraints

- No new file reads, processes or model calls; all from the transcript tail `agent_end` reads, the job state `session_row` reads, and the live hook's events.
- Exact calls stay exact: Talpy Chat's transcript tool lines (`pane.py`), the agents' "last steps", the live steps list, permission prompts (`permission_view`, the hook's PermissionRequest) keep `describe_tool` / `describe`.
- Claude's tool words: Reading, Editing, Writing, Editing notebook, Finding, Searching for, Fetching, Searching the web for, Running.
- Bump `AGENT_CACHE_VERSION` to 4.
- GNOME isn't changed (it keeps working: fields are only added).
- Python stays 3.7-compatible (CI runs py3.7/3.9).
- Speed: no UI-thread blocking; "for 2m 10s" ticks from the existing `now` clock.

## Review Focus

- Parallel tool calls, one result back and one still running: the activity names the running one (no "(thinking about the result)"), and `running` lists only the unfinished call (Task 2 test).
- A description that isn't a plain verb ("npm test", "Git status", "Running tests") is shown as written, never "Gitting status" (Task 1 test).
- An agent that is stopped/failed/done (also when its session ended while a tool ran) has `running == []` (Task 2 test).
- A background job whose own state isn't "working", or whose `updatedAt` is older than 3 minutes, gives no `workingOn`, e.g. this very job showed "blocked · yes go for it" while at work (Task 3 test).
- An agent whose newest reply has no usage (`<synthetic>`, test fixtures) gets `context: None`, and the UI shows no "0 tokens" (Tasks 2, 5, 6).

---

### Task 1: `tool_intent()`: the readable line; chats and agents use it

**Files:**
- Modify: `package/contents/code/talpy_den.py` (next to `describe_tool`, ~1208; `agent_end` ~1284; `step_text` ~1963)
- Test: `tests/test_talpy_den.py` (`AgentTests`, ~757)

**Interfaces:**
- Produces: `ing_form(text: str) -> str`, `tool_intent(block: dict) -> str`, `INTENT_CHARS = 90`, and `describe_tool(block, limit=60)` (gains a `limit` for the command/description length).

- [ ] **Step 1: Write the failing tests**

```python
def test_tool_intent(self):
    t = lambda name, **inp: td.tool_intent({"name": name, "input": inp})
    self.assertEqual(t("Bash", command="sed -n 1,25p CHANGELOG.md", description="Read the top of both CHANGELOG.md files"),
                     "Reading the top of both CHANGELOG.md files")
    self.assertEqual(t("Bash", command="npm test", description="Run the tests"), "Running the tests")
    self.assertEqual(t("Bash", command="git status", description="Git status"), "Git status")
    self.assertEqual(t("Bash", command="x", description="Running tests"), "Running tests")
    self.assertEqual(t("Bash", command="pytest -x tests/\necho"), "Running pytest -x tests/ echo")
    self.assertEqual(t("Read", file_path="/a/b/week.py"), "Reading week.py")
    self.assertEqual(t("Edit", file_path="/a/CHANGELOG.md"), "Editing CHANGELOG.md")
    self.assertEqual(t("Write", file_path="/a/new.ts"), "Writing new.ts")
    self.assertEqual(t("NotebookEdit", notebook_path="/a/n.ipynb"), "Editing notebook n.ipynb")
    self.assertEqual(t("Glob", pattern="**/*.qml"), "Finding **/*.qml")
    self.assertEqual(t("Grep", pattern="tipChatAct"), "Searching for tipChatAct")
    self.assertEqual(t("WebFetch", url="https://x.org/a"), "Fetching https://x.org/a")
    self.assertEqual(t("WebSearch", query="qt listview"), "Searching the web for qt listview")
    self.assertEqual(t("Agent", description="Explore the auth code"), "Exploring the auth code")
    self.assertEqual(t("Monitor", description="Wait for the build"), "Waiting for the build")
    self.assertEqual(t("mcp__github__create_issue"), "github: create_issue")
    self.assertEqual(t("TodoWrite", todos=[]), "TodoWrite")
    self.assertEqual(td.ing_form("Stop the server"), "Stopping the server")
    self.assertEqual(td.ing_form("Make a copy"), "Making a copy")
```

Update `test_counts_tree_and_activity`'s expectations: `("a2", 0, "running", "Running pytest -x tests/ echo")`, `("a3", 1, "running", "Reading test_io.py (thinking about the result)")`. `test_describe_tool` stays as it is.

- [ ] **Step 2: Run them to see them fail**

Run: `python3 -m unittest tests.test_talpy_den.AgentTests -v 2>&1 | tail -5`
Expected: FAIL (`tool_intent` not defined; activity strings differ)

- [ ] **Step 3: Implement**

`ing_form(text)`: when the first word, lowercased, is in a `VERBS` set, replace it with its -ing form (capitalized as the word was); otherwise return the text unchanged. Use a small set: read, run, list, find, check, show, count, search, print, get, set, make, write, create, remove, delete, install, build, test, compile, copy, move, look, open, start, stop, kill, fetch, commit, push, pull, merge, rebase, render, inspect, compare, extract, wait, explore, review, fix, update, add, verify, confirm, measure, trace, capture, take, save, load, clean, restart, reload, apply, check, launch, watch, diff, grab, scan, compute, convert, generate, record, replay, export, import, publish, upload, download, tag, try, see, use. -ing rules: `DOUBLE = {"run","stop","get","set","put","cut","grab","scan","tag","commit","diff","drop","skip","plan","ship","log","wrap"}` adds the last letter again; a word ending in "ie" → "ying"; one ending in "e" but not "ee"/"ye"/"oe" drops the "e"; otherwise add "ing". ("diff" is already doubled, so it gets plain "ing".)
`tool_intent(block)`: as in the spec. Description-carrying tools (Bash, Agent, Task, Monitor) → `ing_form(description)` when it's non-empty; Bash with no description → `"Running " + short_text(command, 60)`; file tools → verb + basename; Glob/Grep pattern; WebFetch url; WebSearch query; anything else → `describe_tool(block)`. Cut to `INTENT_CHARS` with `short_text`.
`agent_end`: both `describe_tool(uses[-1])` calls become `tool_intent(uses[-1])` (the "(thinking about the result)" suffix stays). `step_text`: both `describe_tool` calls become `tool_intent`. `agent_steps`, `permission_view` and `pane.py` keep `describe_tool`.

- [ ] **Step 4: Run them to see them pass, plus the whole Python suite**

Run: `python3 -m unittest tests.test_talpy_den.AgentTests -v 2>&1 | tail -3; python3 -m unittest discover -s tests 2>&1 | tail -3`
Expected: OK (fix any other test that asserted the old `peek.activity` text to the new words)

- [ ] **Step 5: Commit**

---

### Task 2: An agent's `running` calls and `context` size

**Files:**
- Modify: `package/contents/code/talpy_den.py` (`AGENT_CACHE_VERSION`, `agent_end`/`agent_status`/`agent_progress`, `AgentCache.progress`, `session_agents`)
- Test: `tests/test_talpy_den.py` (`AgentTests`)

**Interfaces:**
- Consumes: `tool_intent`, `describe_tool(block, limit)` (Task 1).
- Produces: agent dicts in `row["agents"]["tree"]` gain `"running": [{"line": str, "since": int|None}]` (oldest first; `[]` unless status is "running") and `"context": int|None` (the newest assistant entry's `input_tokens + cache_read_input_tokens + cache_creation_input_tokens + output_tokens`; None when the usage is missing or the sum is 0). `agent_progress`'s detail dict gains the same two keys. `RUNNING_LINE_CHARS = 160`.

- [ ] **Step 1: Write the failing tests**

```python
def test_running_calls_and_context(self):
    tool = lambda i, name, inp: {"type": "tool_use", "id": i, "name": name, "input": inp}
    a = self.line("assistant", [tool("t1", "Read", {"file_path": "/w/a.py"})], "tool_use")
    b = self.line("assistant", [tool("t2", "Bash", {"command": "make test", "description": "Run the tests"})], "tool_use")
    for e in (a, b):
        e["message"]["id"] = "msg_1"
        e["message"]["usage"] = {"input_tokens": 3, "cache_read_input_tokens": 200_000,
                                 "cache_creation_input_tokens": 22_000, "output_tokens": 700}
    b["timestamp"] = iso(self.now - 130)  # (iso takes seconds like the other fixtures; check its unit)
    result = self.line("user", [{"type": "tool_result", "tool_use_id": "t1", "content": "..."}])
    self.agent("busy", "p1", [self.line("user", "go"), a, b, result], description="Parallel")
    agent = next(t for t in self.agents_of_busy()[0]["tree"] if t["id"] == "p1")
    self.assertEqual(agent["activity"], "Running the tests")
    self.assertEqual([r["line"] for r in agent["running"]], ["Bash: make test"])
    self.assertEqual(agent["running"][0]["since"], td.to_ms(b["timestamp"]))
    self.assertEqual(agent["context"], 222_703)

def test_no_running_calls_once_it_ended(self):
    # a1 is done, and a2's session ending while its Bash ran makes it stopped
    a, _ = self.agents_of_busy()
    self.assertEqual(next(t for t in a["tree"] if t["id"] == "a1")["running"], [])
    self.assertIsNone(next(t for t in a["tree"] if t["id"] == "a1")["context"])
```

Extend `test_agents_of_an_ended_session_are_stopped` with `running == []` for its stopped agent.

- [ ] **Step 2: Run them to see them fail**

Run: `python3 -m unittest tests.test_talpy_den.AgentTests -v 2>&1 | tail -5`
Expected: FAIL (KeyError 'running')

- [ ] **Step 3: Implement**

`running_calls(recent)`: walk `recent` (newest first), collecting the `tool_use_id`s of `tool_result` blocks from user entries. At the first assistant entry, take its message id. Collect the `tool_use` blocks of that entry and of the following assistant entries with the same non-empty message id; an entry without an id counts as a message of its own. Stop at the first other entry. Return the ones whose id has no result, excluding SubagentHandback, oldest first, as `{"line": describe_tool(c, RUNNING_LINE_CHARS), "since": to_ms(entry timestamp)}`, plus the newest such block. In `agent_end`'s "running" branches: when that list is non-empty, the activity is `tool_intent(newest unfinished block)` with no suffix. `context_of(recent)`: the usage sum of the newest assistant entry that has a `usage` dict. `agent_progress` puts `running` (only when status is "running") and `context` into `detail`. In `session_agents`, add `"running": detail.get("running") or [] if status == "running" else []` and `"context": detail.get("context")`; read them with `.get`, because old detail records lack them. Bump `AGENT_CACHE_VERSION = 4  # 4: running calls and context`.

- [ ] **Step 4: Run the agent tests and the whole suite**

Run: `python3 -m unittest tests.test_talpy_den.AgentTests 2>&1 | tail -3; python3 -m unittest discover -s tests 2>&1 | tail -3`
Expected: OK

- [ ] **Step 5: Commit**

---

### Task 3: `workingOn`, Claude's own line for a working background chat

**Files:**
- Modify: `package/contents/code/talpy_den.py` (`make_session` ~864, `session_row` ~1003)
- Test: `tests/test_talpy_den.py` (next to the existing background-job row tests; find them with `grep -n "jobs/" tests/test_talpy_den.py`)

**Interfaces:**
- Produces: `row["workingOn"]: str` ("" when none). `WORKING_ON_FRESH_MS = 180_000`.

- [ ] **Step 1: Write the failing test**

A live bg session row (status busy) whose job `state.json` is `{"state": "working", "detail": "tracing how talpy shows agents", "updatedAt": <iso now - 30 s>}` → `row["workingOn"] == "tracing how talpy shows agents"`. The same row with job state "blocked" → `""`; with `updatedAt` 4 minutes old → `""`; an interactive (non-bg) row → `""`.

- [ ] **Step 2: Run it to see it fail** (KeyError 'workingOn')

- [ ] **Step 3: Implement**

`make_session` gets `"workingOn": ""` with a comment. In `session_row`, after the state is known: when `state == "working"`, the job's own `state == "working"`, its `detail` is non-empty after `clean_text`, and `now - to_ms(job["updatedAt"]) <= WORKING_ON_FRESH_MS` → `row["workingOn"] = clean_text(detail, 120)`. Use the entry's own fields merged into `job` (as `own` does) only for state and detail. A row parked without a process never gets it.

- [ ] **Step 4: Run it, then the whole suite** (OK)

- [ ] **Step 5: Commit**

---

### Task 4: The live hook's `doing` in the same words

**Files:**
- Modify: `package/contents/code/live_hook.py` (`describe` ~80, PreToolUse ~168)
- Test: `tests/test_live.py`

**Interfaces:**
- Produces: a live step gains `"intent": str` and the view's `doing` = that intent for main-chat steps; PermissionRequest's `doing` stays `describe(...)`; an agent's `doing` in `view["agents"]` stays `s["text"]`.

- [ ] **Step 1: Write the failing test**: a PreToolUse Bash event with `description: "Run the tests"` gives `view["doing"] == "Running the tests"` and the step's `text == "Bash: npm test"`, `intent == "Running the tests"`. A PreToolUse Read gives `doing == "Reading week.py"`. Also assert that `live_hook.intent` matches `talpy_den.tool_intent` on the Task 1 cases, so the two copies can't drift (loop over a shared list of `(name, input)`).
- [ ] **Step 2: Run it to see it fail**
- [ ] **Step 3: Implement** `intent(name, inp)` in `live_hook.py` as a copy of `tool_intent` and `ing_form` (the hook is installed as a standalone copy and imports nothing from the package; note that in its docstring, as `describe` does). Store `s["intent"]` when a step is made, and set the view's `doing` from it.
- [ ] **Step 4: Run `tests/test_live.py` and the whole suite** (OK)
- [ ] **Step 5: Commit**

---

### Task 5: VS Code: rows, Running now, `workingOn`

**Files:**
- Modify: `vscode/src/shared/types.ts` (`Agent`: `running?: { line: string; since: number | null }[]`, `context?: number | null`; `Session`: `workingOn?: string`; live step: `intent?: string`)
- Modify: `vscode/src/shared/model.ts` (`agentSummary` ~1521, `doingText` ~814, new `agentStatusText`)
- Modify: `vscode/webview/components/AgentTree.tsx` (status text, Running now)
- Modify: `vscode/webview/styles.css` (`.agent-running` list, same look as `.agent-steps`)
- Test: `vscode/test/model.test.ts`

**Interfaces:**
- Produces: `agentStatusText(a: Pick<Agent, "status" | "started" | "context">, now: number): string` (moved from AgentTree's `statusText`), and `doingText(s: Pick<Session, "peek" | "workingOn">, live)`.

- [ ] **Step 1: Write the failing tests**

```ts
assert.equal(agentSummary({ toolCalls: 12, tokens: 45_200 }), "12 tool calls · 45.2k tokens processed");
assert.equal(agentSummary({ toolCalls: null, tokens: 1_300_000 }), "1.3M tokens processed");
assert.equal(agentStatusText({ status: "running", started: 0, context: 222_703 }, 17 * 60_000), "running · 17m · 223k tokens");
assert.equal(agentStatusText({ status: "done", started: 0, context: 222_703 }, 1), "done · 223k tokens");
assert.equal(agentStatusText({ status: "running", started: 0, context: null }, 60_000), "running · 1m");
assert.equal(doingText({ peek: { activity: "Reading a.py" } as any, workingOn: "tracing the agents" }, null), "tracing the agents");
// an edit's counts with a live step that has intent
assert.equal(doingText({ peek: null, workingOn: "" } as any,
  { doing: "Editing a.py", at: 2, steps: [{ text: "Edit: a.py", intent: "Editing a.py", add: 3, del: 1 }] } as any), "Editing a.py +3 −1");
```

Fix the token rounding to whatever `formatTokens` gives (`223k` or `222.7k`), and use that in the expectations.

- [ ] **Step 2: Run to see them fail**: `cd vscode && npm test 2>&1 | tail -15`
- [ ] **Step 3: Implement**: `doingText` returns `s.workingOn` first when it's non-empty; the counts match when `(last.intent || last.text) === live.doing`. In `AgentTree.tsx`, the status uses `agentStatusText`. `AgentDetail` shows, above the steps when `a.status === "running" && a.running?.length`, a `<ul class="agent-running" aria-label="Running now">`. Each item is `▸ {line}` with `for {duration(now - since)}` muted at its end, and the full line in its `title`. Pass `now` into `AgentDetail`.
- [ ] **Step 4: Run** `npm run check && npm test` (both pass)
- [ ] **Step 5: Commit**

---

### Task 6: Plasma: rows, Running now, `workingOn`

**Files:**
- Modify: `package/contents/ui/AgentTree.qml` (status label ~84, unfolded column ~150)
- Modify: `package/contents/ui/main.qml` (`emptyAgent` ~59: `running: [], context: null`; `agentNumbers` ~2016: "%1 tokens processed"; `doingText` ~1532: `workingOn` first, counts by `(last.intent || last.text)`)
- Test: `tests/test_task_strip.py` (its QML text checks, if they list the label strings), plus a render

- [ ] **Step 1: Implement**: the status label text gets `+ (modelData.context ? " · " + i18n("%1 tokens", root.formatTokens(modelData.context)) : "")`. A TipArea on that label says "Its context now: what its last request sent and got back". In the unfolded column, before the steps Repeater, add a "Running now" Repeater over `modelData.status === "running" ? (modelData.running || []) : []`. Each item is a RowLayout: an eliding Label `"▸ " + line` (bold, opacity 0.9) with a TipArea showing the full line when truncated, then a Label `i18nc("how long a tool call has run", "for %1", root.duration(root.now - since))` (opacity 0.6), shown only when `since` is set.
- [ ] **Step 2: Check**: `python3 -m unittest discover -s tests 2>&1 | tail -3` (OK). Then a Plasma render of a row with a running agent (`tools/render_popup.sh`, see docs/development.md) showing the row's tokens and the unfolded Running now. Look at the PNG.
- [ ] **Step 3: Commit**

---

### Task 7: Changelogs

**Files:** `CHANGELOG.md`, `vscode/CHANGELOG.md` (Unreleased, the project's voice: what you see, then what was wrong before)

- [ ] **Step 1:** One entry each: agent rows say what they do in words and show their context size, Running now when unfolded, and background chats' own line while working.
- [ ] **Step 2:** `python3 -m unittest discover -s tests 2>&1 | tail -3; cd vscode && npm run check && npm test 2>&1 | tail -3` (all pass)
- [ ] **Step 3: Commit**
