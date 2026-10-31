import { dayTitle, formatTokens, labeledBar, modelShares, plural, statsSummary, weekdayShort } from "../../src/shared/model";
import type { UsageStats } from "../../src/shared/types";

// An account's last days, unfolded from its token line: tokens per day as
// bars (today's in the accent color), the totals, the busiest folders and
// the models used
export function StatsPanel({ stats: s }: { stats: UsageStats }) {
  const peak = Math.max(1, ...s.days.map((d) => d.total));
  const projects = s.projects ?? [];
  const busiest = Math.max(1, ...projects.map((p) => p.total));
  const last = s.days.length - 1;
  return (
    <div class="stats small" aria-label={`Last ${s.days.length} days`}>
      <div class="stats-chart" role="img" aria-label={statsSummary(s)}>
        {s.days.map((d, i) => (
          <div key={d.day} class={"stats-day" + (i === last ? " today" : "")} title={dayTitle(d)}>
            <div class="stats-bar-area">
              {d.total ? <div class="stats-bar" style={{ height: `${Math.max(4, (100 * d.total) / peak)}%` }} /> : null}
            </div>
            {/* A no-break space: a plain one leaves the line empty, and that day's bar area grows into it */}
            <span class="stats-weekday muted">{labeledBar(i, s.days.length) ? (i === last ? "today" : weekdayShort(d.day)) : "\u00a0"}</span>
          </div>
        ))}
      </div>
      <div class="stats-sum">{statsSummary(s)}</div>
      {projects.length ? (
        <ul class="stats-projects" aria-label="Busiest folders">
          {projects.slice(0, 5).map((p) => (
            <li key={p.path} class="stats-project" title={`${p.path}\n${formatTokens(p.total)} tokens (${formatTokens(p.output)} out) · ${plural(p.prompts, "%1 prompt", "%1 prompts")}`}>
              <span class="stats-project-name">{p.name}</span>
              <span class="stats-project-meter">
                <span style={{ width: `${(100 * p.total) / busiest}%` }} />
              </span>
              <span class="stats-project-numbers muted">
                {formatTokens(p.total)}
                {p.prompts ? ` · ${plural(p.prompts, "%1 prompt", "%1 prompts")}` : ""}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      {s.models?.length ? <div class="stats-models muted">{modelShares(s.models)}</div> : null}
    </div>
  );
}
