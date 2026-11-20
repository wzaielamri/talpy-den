import { forecastTitle, forecastWarning, resetAtText, resetText, usageLevel } from "../../../core/src/shared/model";
import type { LimitWindow } from "../../../core/src/shared/types";
import { useGlide } from "../util/motion";

// One plan limit: label, bar, percent, when it resets. Its four cells sit in
// the account's usage grid, so the bars of all windows line up. The bar also
// shows where your pace leads by the reset (lighter) and where an even pace
// would be by now (a tick); a line under it warns when it runs out first.
export function UsageBar({ window: w, now }: { window: LimitWindow; now: number }) {
  const pct = Math.min(100, Math.max(0, w.pct));
  const reset = resetText(w, now);
  const resetAt = !w.reset && w.resetsAt && w.resetsAt > now ? resetAtText(w.resetsAt, now) : "";
  const f = w.reset ? null : (w.forecast ?? null);
  const ahead = f ? Math.min(100, Math.max(pct, f.atReset)) : pct;
  const warning = forecastWarning(w, now);
  const shownPct = useGlide(w.pct); // (the bar glides with it: a CSS transition)
  const title = [`${w.label}: ${Math.round(w.pct)}% used` + (reset ? ` · ${reset}` : ""), resetAt ? resetAt + "." : "", forecastTitle(w, now)]
    .filter(Boolean)
    .join("\n");
  return (
    <>
      <span class="usage-label" title={title}>
        {w.label}
      </span>
      <span
        class={`meter usage-meter lvl-${usageLevel(w.pct)}`}
        role="meter"
        aria-label={`${w.label} plan usage`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(pct)}
        title={title}
      >
        <span style={{ width: `${pct}%` }} />
        {f && ahead > pct ? (
          <span class={`meter-ahead lvl-${usageLevel(f.atReset)}`} style={{ left: `${pct}%`, width: `${ahead - pct}%` }} />
        ) : null}
        {f ? <span class="meter-even" style={{ left: `${Math.min(100, Math.max(0, f.evenPct))}%` }} /> : null}
      </span>
      <span class="usage-pct">{Math.round(shownPct)}%</span>
      <span class="usage-reset" title={resetAt || reset}>
        {reset}
      </span>
      {warning ? (
        <span class="usage-warning" title={forecastTitle(w, now)}>
          {warning}
        </span>
      ) : null}
    </>
  );
}
