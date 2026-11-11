"""A chat's tasks and subagents in its chat window (Plasma's ChatPane.qml) and
its tab (VS Code's chat.tsx): a strip under the header, a progress bar and
"3/7 · what it's on" (without a task list: "Agents 1/3 · what the running
one does"), folded; unfolded, the tasks and the subagents as under the
chat's row in the popup or the view (AgentTree.qml, AgentTree.tsx: what each
does now, the running ones first, click one for its task, steps and report).
The header's Agents tag unfolds only the subagents. Hidden without either;
what's unfolded is made only then, so the window opens as quickly."""
import claude_guard  # noqa: F401  (first: no test runs the real claude)
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "package/contents/ui"
PANE = (UI / "ChatPane.qml").read_text()
CHAT = (ROOT / "vscode/webview/chat.tsx").read_text()


class PlasmaStripTests(unittest.TestCase):
    def strip(self):
        start = PANE.index("// Its tasks, when it has a task list")
        return PANE[start:PANE.index("// Chat | Steps | Review", start)]

    def test_it_shows_with_a_task_list_or_subagents_and_folds_shut_for_each_chat(self):
        self.assertIn("readonly property var tasks: row && row.tasks && row.tasks.total > 0 ? row.tasks : null", PANE)
        self.assertIn("readonly property var agents: row && row.agents && row.agents.total > 0 ? row.agents : null", PANE)
        self.assertIn("visible: pane.tasks !== null || pane.agents !== null", self.strip())
        reset = PANE[PANE.index("function reset() {"):PANE.index("}", PANE.index("function reset() {"))]
        self.assertIn("tasksOpen = false", reset)
        self.assertIn("agentsOpen = false", reset)

    def test_its_list_is_made_only_when_unfolded(self):
        strip = self.strip()
        loader = strip[strip.index("Loader {"):]
        self.assertIn("active: (pane.tasksOpen && pane.tasks !== null) || (pane.agentsOpen && pane.agents !== null)", loader)
        self.assertIn("pane.tasks.items", loader)          # the tasks
        self.assertIn("AgentTree {", loader)               # and the subagents, as under the row
        self.assertIn("agents: pane.stripAgents", loader)
        self.assertIn("Layout.maximumHeight", loader)      # (a long list scrolls)
        self.assertNotIn("Repeater", strip[:strip.index("Loader {")])
        self.assertNotIn("AgentTree {", strip[:strip.index("Loader {")])
        # (the subagents are sorted only while unfolded)
        self.assertRegex(PANE, r"stripAgents: \{\s+if \(!agentsOpen \|\| !agents\)\s+return \[\]")

    def test_the_running_subagents_come_first_each_with_the_ones_it_started(self):
        block = PANE[PANE.index("readonly property var stripAgents"):PANE.index("readonly property string agentsNow")]
        self.assertIn("a.depth === 0", block)
        self.assertIn("started.filter(busy)", block)

    def test_its_line_says_how_far_and_what_its_on(self):
        strip = self.strip()
        self.assertIn('"%1/%2 · %3", pane.tasks.done, pane.tasks.total', strip)
        self.assertIn("pane.tasks.current", strip)
        self.assertIn('"Agents %1/%2 · %3", pane.agents.done, pane.agents.total, pane.agentsNow', strip)
        self.assertIn("Icons.plasma.unfolded : Icons.plasma.folded", strip)   # (the folds' arrows, A1)
        self.assertIn("activeFocusOnTab: true", strip)                        # (and the keyboard's)
        self.assertIn("onClicked: pane.toggleStrip()", strip)
        toggle = PANE[PANE.index("function toggleStrip() {"):]
        toggle = toggle[:toggle.index("\n    }")]
        self.assertIn("tasksOpen = open && tasks !== null", toggle)
        self.assertIn("agentsOpen = open && agents !== null", toggle)

    def test_the_headers_agents_tag_unfolds_its_subagents(self):
        header = PANE[PANE.index("// mode, its plan, its subagents (SessionRow.qml's tags)"):PANE.index("// Its tasks, when it has a task list")]
        tag = header[header.index("readonly property var agents: pane.agents"):]
        tag = tag[:tag.index("\n                }")]
        self.assertIn("clickable: true", tag)
        self.assertIn("onClicked: pane.agentsOpen = !pane.agentsOpen", tag)
        self.assertIn("what each one is doing", tag)

    def test_the_pane_and_the_row_draw_the_same_tree(self):
        tree = (UI / "AgentTree.qml").read_text()
        row = (UI / "SessionRow.qml").read_text()
        self.assertIn("sourceComponent: AgentTree {", row)
        self.assertRegex(row, r"Loader \{[^}]*active: row\.showAgents && row\.agents !== null")   # (made only while shown)
        self.assertNotIn("expandedAgentRuns", row)
        for what in ("root.toggleAgentRun(agentRow.runKey)", "root.openAgentRun(tree.session", "agentRow.modelData.activity",
                     "root.agentNumbers(agentRow.modelData)", "TipArea {"):
            self.assertIn(what, tree)
        self.assertNotIn("PlasmaCore.ToolTipArea", tree)   # (its tooltips show in the chat window too)
        self.assertIn('rowKey: "pane|" + pane.host + "|" + pane.chatId', self.strip())


class VsCodeStripTests(unittest.TestCase):
    def strip(self):
        return CHAT[CHAT.index("function TaskStrip("):CHAT.index("function gapOf(")]

    def test_the_tab_gets_the_rows_tasks(self):
        pane_ts = (ROOT / "vscode/src/chatPane.ts").read_text()
        self.assertIn("tasks: session?.tasks && session.tasks.total > 0 ? session.tasks : null", pane_ts)
        self.assertIn('tasks: Session["tasks"];', (ROOT / "vscode/src/shared/pane.ts").read_text())

    def test_it_shows_with_a_task_list_or_subagents_and_lists_only_when_unfolded(self):
        self.assertIn("{chat?.tasks || (chat?.agents && chat.agents.total > 0) ? (", CHAT)
        self.assertIn("<TaskStrip key={chat.chatId}", CHAT)   # (a new chat: its subagents' details folded again)
        self.assertIn("stripOf.chatId === chat.chatId ? stripOf", CHAT)   # (and the strip itself)
        strip = self.strip()
        self.assertRegex(strip, re.compile(r"\{unfolded \? \(\s*<div class=\"pane-tasks-list\">", re.S))
        self.assertIn("{open.agents && agents ? (", strip)
        self.assertIn("<AgentTree tree={agentsRunningFirst(agents.tree)}", strip)
        self.assertIn("agentsNow(agents)", strip)
        self.assertIn("I.folded", strip)

    def test_the_headers_agents_tag_unfolds_its_subagents(self):
        tag = CHAT[CHAT.index("<Tag text={`Agents ${chat.agents.done}/${chat.agents.total}`}"):]
        tag = tag[:tag.index("/>")]
        self.assertIn("onClick={() => setStrip({ ...strip, agents: !strip.agents })}", tag)
        self.assertIn("pressed={strip.agents}", tag)

    def test_the_tab_and_the_row_draw_the_same_tree(self):
        tree = (ROOT / "vscode/webview/components/AgentTree.tsx").read_text()
        self.assertNotIn('from "../env"', tree)          # (the chat tab has its own way back)
        self.assertNotIn("uiState", tree)
        self.assertIn("onOpenRun", tree)
        pane_ts = (ROOT / "vscode/src/chatPane.ts").read_text()
        self.assertIn('case "openAgentRun":', pane_ts)
        self.assertIn("AGENT_ID.test(m.agentId)", pane_ts)


if __name__ == "__main__":
    unittest.main()
