import { agentDetailKey, agentRunTitle, agentSummary, duration } from "../../src/shared/model";
import type { Agent } from "../../src/shared/types";
import { I, Icon } from "../util/icons";

function statusText(a: Agent, now: number): string {
  switch (a.status) {
    case "running":
      return `running · ${duration(now - (a.started ?? now))}`;
    case "done":
      return "done";
    case "failed":
      return "failed";
    default:
      return "stopped";
  }
}

// Unfolded under a subagent (click it): what it was asked, its numbers, its
// last steps, its report, and its whole run to open in the Markdown preview
function AgentDetail({ agent: a, host, onOpenRun }: { agent: Agent; host?: string; onOpenRun: (agentId: string) => void }) {
  const summary = agentSummary(a);
  const steps = a.steps ?? [];
  return (
    <div class="agent-detail">
      {a.task ? (
        <div class="agent-task muted" title={a.task}>
          <span class="agent-label">Task:</span> {a.task}
        </div>
      ) : null}
      {summary ? <div class="muted">{summary}</div> : null}
      {steps.length ? (
        <ul class="agent-steps" aria-label="Its last steps">
          {steps.map((step, i) => (
            <li key={i} class={a.status === "running" && i === steps.length - 1 ? "current" : ""} title={step}>
              ▸ {step}
            </li>
          ))}
        </ul>
      ) : null}
      {a.status === "done" && a.report ? (
        <div class="agent-report" title={a.report}>
          <span class="agent-label">Report:</span> {a.report}
        </div>
      ) : null}
      <div class="peek-actions">
        <button type="button" class="link" title={agentRunTitle(host)} onClick={() => onOpenRun(a.id)}>
          Open the whole run
        </button>
      </div>
    </div>
  );
}

// A chat's subagents as a tree: what each one is doing; click one for more.
// Under a chat's row (SessionRow.tsx: its Agents tag) and in its chat tab's
// strip (chat.tsx: the header's Agents tag), which keep what's unfolded
// (opened: by agentDetailKey) and open an agent's whole run (onOpenRun).
export function AgentTree({ tree, now, rowKey, host, opened, onToggle, onOpenRun }: {
  tree: Agent[]; now: number; rowKey: string; host?: string;
  opened: Readonly<Record<string, boolean>>; onToggle: (key: string) => void; onOpenRun: (agentId: string) => void;
}) {
  return (
    <ul class="agents" aria-label="Subagents">
      {tree.map((a) => {
        const title = a.description || a.type;
        const key = agentDetailKey(rowKey, a.id);
        const open = !!opened[key];
        return (
          <li key={a.id} class={`agent ag-${a.status}`} style={{ paddingLeft: `calc(var(--cs-gu) * 0.9 * ${a.depth})` }}>
            <span class="agent-branch" aria-hidden="true">
              └
            </span>
            <span class="agent-dot" aria-hidden="true" />
            <div class="agent-main">
              <button
                type="button"
                class="agent-head"
                aria-expanded={open}
                title={`${title}${a.activity ? "\n" + a.activity : ""}\n\nClick to ${open ? "fold it up again" : "see what it was asked, its last steps and its report"}.`}
                onClick={() => onToggle(key)}
              >
                <span class="agent-line">
                  <span class="agent-desc">{title}</span>
                  {a.description && a.type ? <span class="agent-type">{a.model ? `${a.type} · ${a.model}` : a.type}</span> : null}
                  <span class={"agent-status" + (a.status === "failed" ? " failed" : "")}>{statusText(a, now)}</span>
                  <Icon name={I.folded} class={open ? "open" : ""} />
                </span>
                {a.activity ? <span class="agent-activity">{a.activity}</span> : null}
              </button>
              {open ? <AgentDetail agent={a} host={host} onOpenRun={onOpenRun} /> : null}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
