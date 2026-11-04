import { drawCard } from "../util/card";
import { Fragment, type JSX } from "preact";
import { useEffect, useRef, useState } from "preact/hooks";
import { hostLabel, plural } from "../../src/shared/model";
import type { LimitAccount, LimitHistory, WeekChat, WeekDay, WeekPlanWindow, WeekRecap, WeekSpan } from "../../src/shared/types";
import {
  cacheText,
  coldText,
  currencyOf,
  dayTip,
  factsText,
  fillPaths,
  footText,
  hoursText,
  hoverText,
  moneyText,
  periodText,
  periodWaiting,
  stepText,
  weekRows,
  planText,
  RECAP_SECTIONS,
  type RecapSection,
  rowDay,
  shareText,
  tipMeaning,
  toolsText,
  weekTiles,
  workText,
  type Currency,
  dayMoment,
  dayPlace,
  LIMIT_EMPTY,
  limitChangeText,
  limitDay,
  limitDots,
  limitEventText,
  limitEventTip,
  limitFillText,
  limitFootText,
  limitKeys,
  limitLabel,
  limitMix,
  limitMoney,
  limitStart,
  limitShareText,
  limitSizeTip,
  limitTokensText,
  limitWeekBars,
} from "../../src/shared/week";
import { post } from "../env";
import { I, Icon } from "../util/icons";
import { useViewVisible } from "../util/petStage";
import { useStore } from "../util/store";
import { limitsAnswer, limitsOpen, useReadAgain, weekAnswer } from "../util/stores";
import { showProject } from "../util/ui";
import { Reading } from "./Reading";

const REFRESH_MS = 10 * 60000; // while the tab is in sight

// The Recap tab: your last 7 days with Claude, as a story. The big picture
// (how long you were at it, how long Claude worked, your prompts, its
// tokens, the API prices), what Claude did, when (a day per row on a
// timeline, your plan's limits, chat by chat), where (by project, by chat),
// then the money: what the same work would cost at API prices and what would
// use less of your plan (the rules of Claude Code's own /usage). The extension runs the
// widget's week.py for it (only while this tab is open): read from the chats'
// transcripts, no tokens used.
export function WeekView({ hosts, currency }: { hosts: string[]; currency: string }) {
  const visible = useViewVisible();
  const answer = useStore(weekAnswer);
  const [span, setSpan] = useState<WeekSpan>(answer?.span ?? "week");
  const [back, setBack] = useState(answer?.back ?? 0);
  const [account, setAccount] = useState(answer?.account ?? "");
  const [busy, setBusy] = useState(true); // asked, and its answer hasn't come
  const [sharing, setSharing] = useState(false);
  const [copied, setCopied] = useState("");
  const hostsKey = hosts.join(",");

  function ask() {
    setBusy(true);
    post({ type: "week", back, account, span });
  }

  // Ask for these days when the tab is in sight, again every 10 minutes and
  // at the view's Refresh
  useEffect(() => {
    if (!visible) return;
    ask();
    const timer = setInterval(ask, REFRESH_MS);
    return () => clearInterval(timer);
  }, [visible, span, back, account, hostsKey, currency]);
  useReadAgain(visible, ask);

  const mine = answer && answer.span === span && answer.back === back && answer.account === account ? answer : null;
  useEffect(() => {
    if (mine) setBusy(false);
  }, [mine]);
  // (the days read before: dimmed while these come, under the error when a read fails)
  const kept = useRef<WeekRecap | null>(null);
  if (answer?.recap) kept.current = answer.recap;
  const recap: WeekRecap | null = mine?.recap ?? kept.current;
  const error = mine?.error ?? "";
  const s = recap?.sum;
  const hasData = !!s && (s.workedMs > 0 || s.prompts > 0 || s.cost > 0);

  // (in the order of RECAP_SECTIONS: what Claude did, when, where, then the money)
  const sections: Record<RecapSection, () => JSX.Element | null> = {
    work: () => <Work recap={recap!} />,
    days: () => <Timeline recap={recap!} />,
    plan: () => <Plan recap={recap!} />,
    lanes: () => <Lanes recap={recap!} />,
    projects: () => <Projects recap={recap!} />,
    chats: () => <Chats recap={recap!} />,
    models: () => <Models recap={recap!} />,
    tips: () => <Tips recap={recap!} copied={copied} onCopy={copy} />,
  };

  function copy(text: string) {
    post({ type: "copy", text });
    setCopied(text);
    setTimeout(() => setCopied((c) => (c === text ? "" : c)), 2000);
  }

  return (
    <div class={"week" + (busy && recap ? " busy" : "")}>
      {/* A day, 7 days, 30 days or everything kept */}
      <div class="week-spans" role="radiogroup" aria-label="What to show">
        {([["day", "Day"], ["week", "Week"], ["month", "Month"], ["all", "Overall"]] as const).map(([sp, text]) => (
          <button key={sp} type="button" role="radio" aria-checked={span === sp} class={"chip" + (span === sp ? " on" : "")}
            onClick={() => {
              setSpan(sp);
              setBack(0);
            }}>
            {text}
          </button>
        ))}
      </div>
      <div class="week-period">
        {span !== "all" ? (
          <button type="button" class="icon-btn flip" title={stepText(span, false)} aria-label={stepText(span, false)}
            disabled={!mine || back >= (recap?.backMax ?? 0)} onClick={() => setBack(back + 1)}>
            <Icon name={I.previous} />
          </button>
        ) : null}
        <span class="week-span">{mine && recap ? periodText({ ...recap, back }) : periodWaiting(span, back)}</span>
        {span !== "all" ? (
          <button type="button" class="icon-btn" title={stepText(span, true)} aria-label={stepText(span, true)} disabled={back <= 0}
            onClick={() => setBack(back - 1)}>
            <Icon name={I.next} />
          </button>
        ) : null}
        {/* (none to read these days again: the view's Refresh does) */}
        <button type="button" class="icon-btn" title={"Share as a picture\nThese days as a card with Talpy, to save or copy."}
          aria-label="Share as a picture" disabled={!(recap && hasData)} onClick={() => setSharing(true)}>
          <Icon name={I.share} />
        </button>
      </div>
      {sharing && recap ? <ShareCard recap={recap} onClose={() => setSharing(false)} /> : null}

      {recap && recap.accounts.length > 1 ? (
        <div class="week-accounts" role="radiogroup" aria-label="Whose chats">
          {[{ id: "", name: "All accounts", plan: null }, ...recap.accounts].map((a) => (
            <button key={a.id} type="button" role="radio" aria-checked={account === a.id} class={"chip" + (account === a.id ? " on" : "")}
              title={a.id ? "This account's chats (a chat shared with others counts on each account that has it)" : "All your chats"}
              onClick={() => setAccount(a.id)}>
              {a.name + (a.plan ? ` · ${a.plan}` : "")}
            </button>
          ))}
        </div>
      ) : null}

      {busy && !recap && !error ? (
        <Reading text="Reading your chats of these days. The first time takes a few seconds; after that only what's new is read." />
      ) : null}
      {error ? <div class="msg error" role="alert">Couldn't read your week: {error}</div> : null}
      {recap && !hasData ? (
        <div class="empty">
          <div class="empty-title">{recap.span === "day" ? "No Claude on this day" : recap.span === "all" ? "No Claude yet" : "No Claude in these days"}</div>
          <div class="muted">
            {recap.span === "day" ? "None of your chats here (or on the SSH hosts shown) has a prompt or a reply on this day."
              : recap.span === "all" ? "None of your chats here (or on the SSH hosts shown) has a prompt or a reply yet."
                : `None of your chats here (or on the SSH hosts shown) has a prompt or a reply in these ${recap.span === "month" ? "30" : "7"} days.`}
          </div>
        </div>
      ) : null}

      {recap && s && hasData ? (
        <>
          <div class="week-tiles">
            {weekTiles(recap).map((t) => (
              <div key={t.label} class="week-tile" title={`${t.label}\n${t.tip}`}>
                <span class="week-tile-label muted">{t.label}</span>
                <span class="week-tile-value">{t.value}</span>
                {t.delta ? <span class="week-tile-delta muted">{t.delta}</span> : null}
                <Trend values={t.trend} />
              </div>
            ))}
          </div>
          {factsText(s) ? <div class="week-facts small muted">{factsText(s)}</div> : null}
          {RECAP_SECTIONS.map((k) => <Fragment key={k}>{sections[k]()}</Fragment>)}
          <div class="week-foot small muted">{footText(recap)}</div>
          <Limits recap={recap} account={account} />
        </>
      ) : null}
    </div>
  );
}

// The card to share (util/card.ts): a preview, the projects named or not, Save or Copy
function ShareCard({ recap, onClose }: { recap: WeekRecap; onClose: () => void }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [names, setNames] = useState(false);
  useEffect(() => {
    if (canvas.current) drawCard(canvas.current, recap, names);
  }, [recap, names]);
  const send = (how: "save" | "copy") => {
    const url = canvas.current?.toDataURL("image/png") ?? "";
    post({ type: "shareCard", how, name: `claude-${recap.span ?? "week"}-${recap.to}.png`, png: url.slice(url.indexOf(",") + 1) });
  };
  return (
    <div class="week-share" role="dialog" aria-label="Share as a picture">
      <canvas ref={canvas} class="week-share-card" />
      <label class="small"><input type="checkbox" checked={names} onChange={(e) => setNames((e.target as HTMLInputElement).checked)} /> Name the projects on it</label>
      <div class="ask-buttons">
        <button type="button" class="btn" onClick={() => send("save")}>Save</button>
        <button type="button" class="btn secondary" onClick={() => send("copy")}>Copy</button>
        <button type="button" class="btn secondary" onClick={onClose}>Close</button>
      </div>
    </div>
  );
}

// The same number over the 5 weeks up to these days, these last (a week
// the widget no longer has: a dot)
function Trend({ values }: { values: (number | null)[] }) {
  if (values.length < 2) return null;
  const top = Math.max(1e-9, ...values.filter((v): v is number => v !== null));
  return (
    <span class="week-trend" aria-hidden="true">
      {values.map((v, i) => (
        <span key={i} class={(v === null ? "gone" : "") + (i === values.length - 1 ? " now" : "")}
          style={v === null ? undefined : { height: `max(1px, ${(100 * v) / top}%)` }} />
      ))}
    </span>
  );
}

// A day or a folder that unfolds its chats: a click, or Enter / Space when
// Tab got to it
function opens(shown: boolean, toggle: () => void) {
  return {
    role: "button" as const,
    tabIndex: 0,
    "aria-expanded": shown,
    onClick: toggle,
    onKeyDown: (e: KeyboardEvent) => {
      if (e.target !== e.currentTarget || (e.key !== "Enter" && e.key !== " ")) return;
      e.preventDefault();
      toggle();
    },
  };
}

// A chat in the tab's lists: click one of this computer's to bring it up
function ChatLine({ c, cur, where, sub }: { c: WeekChat; cur: Currency; where?: string; sub?: boolean }) {
  return (
    <li>
      <button type="button" class={"week-chat" + (sub ? " sub" : "")} disabled={!!c.host || !c.chatId}
        title={c.host ? `${c.name} on ${hostLabel(c.host)}: its row under ${hostLabel(c.host)} opens it` : `Open “${c.name}”`}
        onClick={() => post({ type: "openWeekChat", chatId: c.chatId, profileDir: c.profileDir, name: c.name, cwd: c.cwd })}>
        <span class="week-chat-name">{c.name}</span>
        <span class="week-chat-folder small muted">{where ?? (c.host ? hostLabel(c.host) + ": " : "") + c.folder}</span>
        <span class="week-chat-value small muted">{hoursText(c.workedMs)} · {moneyText(c.cost, cur)}</span>
      </button>
    </li>
  );
}

// A day per row: when you were at it, when Claude worked (darker where
// several chats worked at once), when it waited for your answer, where a
// usage limit stopped a chat. Click a day for its chats.
function Timeline({ recap }: { recap: WeekRecap }) {
  const [hover, setHover] = useState<{ row: number; x: number; ms: number; px: number } | null>(null);
  const [open, setOpen] = useState("");
  const cur = currencyOf(recap);
  const weeks = weekRows(recap.span); // (a row per 7 days, with their numbers)
  const last = weeks ? 0 : recap.days.length - 1;
  const most = Math.max(1, ...recap.days.map((d) => Math.max(d.youMs, d.workedMs)));
  // (by the day's own wall clock: dayPlace)
  const pct = (d: WeekDay, ms: number) => `${100 * dayPlace(d, ms)}%`;
  const width = (d: WeekDay, a: number, b: number) => `max(1px, ${Math.max(0, 100 * (dayPlace(d, b) - dayPlace(d, a)))}%)`;
  const limits = recap.days.some((d) => d.limits?.length);
  return (
    <section class="week-section">
      <div class="week-heading">
        <h2>{weeks ? "Week by week" : recap.span === "day" ? "Through the day" : "Day by day"}</h2>
        <span class="week-legend small muted">
          <span><span class="swatch you" /> You</span>
          <span><span class="swatch work" /> {weeks ? "Claude worked" : "Claude working"}</span>
          {weeks ? null : <span><span class="swatch wait" /> Waiting for you</span>}
          {limits && !weeks ? <span><span class="swatch limit" /> A usage limit stopped a chat</span> : null}
        </span>
      </div>
      <div class="week-row week-axis small muted" aria-hidden="true">
        <span class="week-day" />
        <span class="week-hours">
          {(weeks ? [] : [0, 6, 12, 18, 24]).map((h) => (
            <span key={h} style={{ left: `${(100 * h) / 24}%` }}>{h}</span>
          ))}
        </span>
        <span class="week-num">You</span>
        <span class="week-num">Claude</span>
      </div>
      {recap.days.map((d, i) => {
        const shown = open === d.day && !!d.chats?.length;
        return (
          <div key={d.day}>
            <div class={"week-row" + (i === last && recap.back === 0 ? " today" : "") + (d.chats?.length ? " opens" : "") + (shown ? " open" : "")}
              title={dayTip(d, cur)} {...(d.chats?.length ? opens(shown, () => setOpen(shown ? "" : d.day)) : { onClick: () => setOpen("") })}>
              <span class="week-day small">{rowDay(d.day, weeks)}</span>
              {weeks ? (
                <span class="week-track">
                  {d.youMs > 0 ? <span class="week-you" style={{ left: 0, width: `max(1px, ${(100 * d.youMs) / most}%)` }} /> : null}
                  {d.workedMs > 0 ? <span class="week-work many" style={{ left: 0, width: `max(1px, ${(100 * d.workedMs) / most}%)` }} /> : null}
                </span>
              ) : (
              <span
                class="week-track"
                onMouseMove={(e) => {
                  const box = (e.currentTarget as HTMLElement).getBoundingClientRect();
                  const x = Math.max(0, Math.min(box.width, e.clientX - box.left));
                  const span = d.end - d.start;
                  setHover({ row: i, x, ms: dayMoment(d, x / Math.max(1, box.width)), px: span / Math.max(1, box.width) });
                }}
                onMouseLeave={() => setHover((h) => (h && h.row === i ? null : h))}
              >
                {d.you.map(([a, b]) => <span key={"y" + a} class="week-you" style={{ left: pct(d, a), width: width(d, a, b) }} />)}
                {d.wait.map(([a, b]) => <span key={"w" + a} class="week-wait" style={{ left: pct(d, a), width: width(d, a, b) }} />)}
                {d.work.map(([a, b, n]) => (
                  <span key={"c" + a} class={"week-work" + (n >= 3 ? " many" : n === 2 ? " two" : "")} style={{ left: pct(d, a), width: width(d, a, b) }} />
                ))}
                {(d.limits ?? []).map((t) => <span key={"l" + t} class="week-limit" style={{ left: pct(d, t) }} />)}
                {i === last && recap.back === 0 ? <span class="week-now" style={{ left: pct(d, recap.generatedAt) }} /> : null}
                {hover && hover.row === i ? <span class="week-cross" style={{ left: `${hover.x}px` }} /> : null}
              </span>
              )}
              <span class="week-num small muted">{d.youMs >= 60000 ? hoursText(d.youMs) : "–"}</span>
              <span class="week-num small">{d.workedMs >= 60000 ? hoursText(d.workedMs) : "–"}</span>
            </div>
            {shown ? (
              <ul class="week-chats week-day-chats">
                {d.chats.map((c) => <ChatLine key={c.host + c.chatId} c={c} cur={cur} sub />)}
              </ul>
            ) : null}
          </div>
        );
      })}
      <div class={"week-readout small" + (hover ? "" : " muted")}>
        {weeks ? "Click a week for its chats."
          : hover ? hoverText(recap.days[hover.row], hover.ms, recap.generatedAt, hover.px) : "Point at a day to see what went on then; click it for its chats."}
      </div>
    </section>
  );
}

// How full your plan's windows are now, and how they filled up (this
// computer's accounts, from the widget's usage history)
function Plan({ recap }: { recap: WeekRecap }) {
  const plans = recap.plan ?? [];
  if (!plans.length) return null;
  return (
    <section class="week-section">
      <h2>Your plan's limits now</h2>
      <ul class="week-bars week-plan">
        {plans.flatMap((p) =>
          p.windows.map((w) => (
            <li key={p.account + w.key} title={`${w.label}: ${Math.round(w.pct)}% used\nHow this window of your plan filled up, from its start (on the left) to when it resets (on the right), as Talpy Den saw it.`}>
              <span class="week-bar-name">{(plans.length > 1 ? p.name + " · " : "") + w.label}</span>
              <FillChart w={w} now={recap.generatedAt} />
              <span class={"week-bar-value small" + (w.pct >= 90 ? " over" : " muted")}>
                {planText(w, recap.generatedAt)}
              </span>
            </li>
          )),
        )}
      </ul>
    </section>
  );
}

// Advanced analyses, for now how your limits changed (week.py --limits):
// folded until you open it (it
// stays open while the view lives), read then, and again with each read of
// the Recap while open; with today's days only, as the limits now
function Limits({ recap, account }: { recap: WeekRecap; account: string }) {
  const open = useStore(limitsOpen);
  const answer = useStore(limitsAnswer);
  useEffect(() => {
    if (open && recap.back === 0) post({ type: "limits", account });
  }, [open, account, recap.generatedAt, recap.back]);
  if (recap.back !== 0) return null;
  const mine = answer && answer.account === account ? answer : null;
  const data: LimitHistory | null = mine?.data ?? null;
  const cur = currencyOf(data ?? recap);
  const shown = (data?.accounts ?? []).filter((a) => a.periods.length);
  const plans = new Set(shown.map((a) => a.plan));
  return (
    <section class="week-section week-limits">
      <h2 class="limits-title" {...opens(open, () => limitsOpen.set(!open))}>
        <Icon name={I.folded} class={open ? "turn" : ""} />
        Advanced analyses <span class="limits-estimate muted">· your plan's limits over time · estimates</span>
      </h2>
      {!open ? null : !mine ? (
        <Reading text="Working out how much your plan's windows held, from your chats and the limit readings kept." />
      ) : mine.error ? (
        <div class="msg error" role="alert">Couldn't work it out: {mine.error}</div>
      ) : !shown.length ? (
        <div class="muted">{LIMIT_EMPTY}</div>
      ) : (
        <>
          {shown.length > 1 && plans.size > 1 ? (
            <table class="limits-compare">
              <thead><tr><th>Plan</th><th>5-hour</th><th>Week</th><th>5-hour share</th></tr></thead>
              <tbody>
                {shown.map((a) => (
                  <tr key={a.id}>
                    <td>{a.name} · {a.plan ?? "?"}</td>
                    <td>{a.now.fiveHour ? limitMoney(a.now.fiveHour.cost, cur) : "–"}</td>
                    <td>{a.now.weeks.seven_day ? limitMoney(a.now.weeks.seven_day.cost, cur) : "–"}</td>
                    <td>{a.now.share ? `${Math.round(a.now.share.pct)}%` : "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
          {shown.map((a) => <LimitsOf key={a.id} a={a} many={shown.length > 1} cur={cur} now={data!.generatedAt}
            start={limitStart(shown, data!.generatedAt)} />)}
          <div class="small muted">{limitFootText(data!)}</div>
        </>
      )}
    </section>
  );
}

function LimitsOf({ a, many, cur, now, start }: { a: LimitAccount; many: boolean; cur: Currency; now: number; start: number }) {
  // (every account's chart on one time line: a week is at the same place in each)
  const dots = limitDots(a, now, start);
  const bars = limitWeekBars(a, now, start);
  const weekTop = Math.max(0, ...bars.map((b) => b.cost));
  const mix = limitMix(a.now.tokens);
  const shares = a.periods.map((p) => p.share?.pct ?? null);
  return (
    <div class="limits-account">
      <div class="limits-plan">{many ? <b>{a.name} · </b> : null}{a.plan ?? ""}</div>
      {(a.events ?? []).map((e) => (
        <div key={e.at} class="limits-event small" title={limitEventTip(e)}>{limitEventText(e)}</div>
      ))}
      <h3>How your limits changed</h3>
      <ul class="week-bars limits-sizes">
        {limitKeys(a).map((k) => {
          const cost = k === "five_hour" ? a.now.fiveHour?.cost : a.now.weeks[k]?.cost;
          const change = a.changes[k === "five_hour" ? "fiveHour" : k];
          return (
            <li key={k} title={limitSizeTip(k, a, cur)}>
              <span class="week-bar-name">{limitLabel(k)}</span>
              <span class="limits-value">{(k === "five_hour" ? a.now.fiveHour?.scaled : a.now.weeks[k]?.scaled) ? "≈ " : ""}{limitMoney(cost ?? 0, cur)}</span>
              <span class={"week-bar-value small" + ((change?.kind === "change" && (change.pct ?? 0) < 0) || (change?.kind === "limits" && (change.factor ?? 1) < 0.9) ? " over" : " muted")}>
                {limitChangeText(change)}
              </span>
            </li>
          );
        })}
      </ul>
      {dots.dots.length || bars.length ? (
        <figure class="limits-chart">
          {dots.dots.length ? (
            <>
              <figcaption class="small muted">Each 5-hour window · {limitMoney(dots.lo, cur)} to {limitMoney(dots.top, cur)}</figcaption>
              <div class="limits-dots" role="img" aria-label="How much each 5-hour window held, week by week, with each week's middle">
                {dots.marks.map((x, i) => <span key={"c" + i} class="mark" style={{ left: `${x * 100}%` }} />)}
                {dots.medians.map((m, i) => (
                  <span key={"m" + i} class="med" style={{ left: `${m.x1 * 100}%`, width: `${(m.x2 - m.x1) * 100}%`, bottom: `${m.y * 100}%` }} />
                ))}
                {dots.dots.map((d, i) => (
                  <span key={i} class="dot" style={{ left: `${d.x * 100}%`, bottom: `${d.y * 100}%` }}
                    title={`${limitMoney(d.full, cur)} · ${d.tip}`} />
                ))}
              </div>
            </>
          ) : null}
          {bars.length ? (
            <>
              <figcaption class="small muted">Each week · up to {limitMoney(weekTop, cur)}</figcaption>
              <div class="limits-bars" role="img" aria-label="How much each week held, on the same days as the 5-hour windows">
                {dots.marks.map((x, i) => <span key={"c" + i} class="mark" style={{ left: `${x * 100}%` }} />)}
                {bars.map((b, i) => (
                  <span key={b.from} class={"bar" + (i === bars.length - 1 ? " now" : "") + (b.partial ? " partial" : "")}
                    style={{ left: `${b.x1 * 100}%`, width: `${(b.x2 - b.x1) * 100}%`, height: `max(2px, ${b.h * 100}%)` }}
                    title={`Week of ${limitDay(b.from)}: ${limitMoney(b.cost, cur)}` + (b.partial ? " (the limit began during it)" : "")} />
                ))}
              </div>
            </>
          ) : null}
          <div class="limits-axis small muted"><span>{limitDay(start)}</span><span>today</span></div>
        </figure>
      ) : null}
      {a.now.share ? (
        <>
          <h3>A 5-hour window in the week</h3>
          <div class="limits-line">
            <span>{limitShareText(a.now.share.pct)}</span>
            <span class="small muted">{limitChangeText(a.changes.share)}</span>
            <Trend values={shares} />
          </div>
        </>
      ) : null}
      {a.now.fill ? (
        <>
          <h3>How long a window lasts</h3>
          <div class="limits-line">{limitFillText(a.now.fill)}</div>
        </>
      ) : null}
      {a.equivalents || mix.parts.length ? (
        <>
          <h3>In tokens</h3>
          {a.equivalents ? <div class="limits-line">{limitTokensText(a)}</div> : null}
          {mix.parts.length ? (
            <div class="limits-mix-box">
              <span class="limits-mix" aria-hidden="true">
                {mix.parts.map((p) => <span key={p.kind} class={p.kind} style={{ flexGrow: p.share }} />)}
              </span>
              <div class="limits-legend small muted">
                {mix.parts.map((p) => <span key={p.kind}><i class={"key " + p.kind} />{p.label}</span>)}
                <span>{mix.text}</span>
              </div>
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

function FillChart({ w, now }: { w: WeekPlanWindow; now: number }) {
  const { line, area } = fillPaths(w, now, 100, 20);
  const level = w.pct >= 90 ? " high" : w.pct >= 70 ? " mid" : "";
  return (
    <svg class={"week-fill" + level} viewBox="0 0 100 20" preserveAspectRatio="none" aria-hidden="true">
      {area ? <path class="area" d={area} /> : null}
      {line ? <path class="line" d={line} vector-effect="non-scaling-stroke" /> : null}
    </svg>
  );
}

// The project folders Claude worked in most (a chat started in a subfolder
// of a repository counts for the repository): click one of this computer's
// to open it in the Projects tab, an SSH host's for its chats
function Projects({ recap }: { recap: WeekRecap }) {
  const [open, setOpen] = useState("");
  if (!recap.projects.length) return null;
  const cur = currencyOf(recap);
  const most = Math.max(1, ...recap.projects.map((p) => p.workedMs));
  return (
    <section class="week-section">
      <h2>Where Claude worked</h2>
      <ul class="week-bars">
        {recap.projects.map((p) => {
          const key = p.host + "|" + p.path;
          const shown = open === key;
          const chats = Array.isArray(p.chats) ? p.chats : [];
          return [
            <li key={key} class={"opens" + (shown ? " open" : "")} {...opens(shown, () => (p.host ? setOpen(shown ? "" : key) : showProject(p.folder || p.path)))}
              title={`${p.host ? hostLabel(p.host) + ": " : ""}${p.path}\nClaude worked ${hoursText(p.workedMs)} · ${moneyText(p.cost, cur)} at API prices\n` +
                `${plural(p.prompts, "%1 prompt", "%1 prompts")} · ${plural(p.chatCount ?? chats.length, "%1 chat", "%1 chats")}\n` +
                (p.host ? "Click for its chats." : "Click to open it in the Projects tab: its chats, plans and memories.")}>
              <span class="week-bar-name">
                <Icon name={I.folded} class={shown ? "turn" : ""} />
                {(p.host ? hostLabel(p.host) + ": " : "") + p.name}
              </span>
              <span class="week-bar-meter work"><span style={{ width: `${(100 * p.workedMs) / most}%` }} /></span>
              <span class="week-bar-value small muted">{hoursText(p.workedMs)} · {moneyText(p.cost, cur)}</span>
            </li>,
            shown ? (
              <li key={key + "/chats"} class="week-sub">
                <ul class="week-chats">
                  {chats.map((c) => <ChatLine key={c.host + c.chatId} c={c} cur={cur} where="" sub />)}
                </ul>
                {(p.chatCount ?? 0) > chats.length ? (
                  <span class="small muted week-more">and {(p.chatCount ?? 0) - chats.length} more {(p.chatCount ?? 0) - chats.length === 1 ? "chat" : "chats"}</span>
                ) : null}
              </li>
            ) : null,
          ];
        })}
      </ul>
    </section>
  );
}

// The Day view, chat by chat: when each chat worked, waited for you (a
// permission, a question) or was paused (asleep, a usage limit); between
// those it was your turn. A name brings the chat up.
function Lanes({ recap }: { recap: WeekRecap }) {
  const lanes = recap.lanes ?? [];
  if (!lanes.length) return null;
  const t0 = Math.min(...lanes.map((l) => l.parts[0][0]));
  const t1 = Math.max(...lanes.map((l) => l.parts[l.parts.length - 1][1]));
  const span = Math.max(60000, t1 - t0);
  const time = (ms: number) => new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const kinds = { w: "Claude worked", y: "Waited for you", p: "Paused (asleep, a limit)" };
  return (
    <section class="week-section">
      <h2>Chat by chat</h2>
      <div class="week-lanes-legend small muted">
        {(["w", "y", "p"] as const).map((k) => <span key={k}><i class={`lane-${k}`} aria-hidden="true" />{kinds[k]}</span>)}
      </div>
      <ul class="week-lanes">
        {lanes.map((l) => (
          <li key={l.key}>
            <button type="button" class="week-lane-name small" disabled={!!l.host || !l.id}
              title={l.host ? `${l.name} on ${hostLabel(l.host)}` : `Open “${l.name}”`}
              onClick={() => post({ type: "openWeekChat", chatId: l.id, profileDir: l.profileDir ?? "", name: l.name, cwd: "" })}>
              {(l.host ? hostLabel(l.host) + ": " : "") + l.name}
            </button>
            <span class="week-lane" title={`${l.name}\nClaude worked ${hoursText(l.workedMs)}, waited for you ${hoursText(l.waitedMs)}${l.project ? `\n${l.project}` : ""}`}>
              {l.parts.map(([a, b, k], i) => (
                <i key={i} class={`lane-${k}`} style={{ left: `${((a - t0) / span) * 100}%`, width: `max(1.5px, ${((b - a) / span) * 100}%)` }} />
              ))}
            </span>
          </li>
        ))}
      </ul>
      <div class="week-lanes-times small muted"><span>{time(t0)}</span><span>{time(t1)}</span></div>
    </section>
  );
}

// The chats Claude worked on most
function Chats({ recap }: { recap: WeekRecap }) {
  if (!recap.chats.length) return null;
  const cur = currencyOf(recap);
  return (
    <section class="week-section">
      <h2>Chats it worked on most</h2>
      <ul class="week-chats">
        {recap.chats.map((c) => <ChatLine key={c.host + c.chatId} c={c} cur={cur} />)}
      </ul>
    </section>
  );
}

// What Claude did: its tool calls, commands, edits, subagents
function Work({ recap }: { recap: WeekRecap }) {
  const text = workText(recap.work);
  if (!text) return null;
  return (
    <section class="week-section">
      <h2>What Claude did</h2>
      <div>{text}</div>
      {toolsText(recap.work) ? <div class="small muted">{toolsText(recap.work)}</div> : null}
    </section>
  );
}

// What it'd cost on the API, by model, and what the cache saved
function Models({ recap }: { recap: WeekRecap }) {
  if (!recap.models.length) return null;
  const cur = currencyOf(recap);
  return (
    <section class="week-section">
      <h2>At API prices</h2>
      <ul class="week-bars">
        {recap.models.map((m) => (
          <li key={m.model} title={`${m.model}: ${moneyText(m.cost, cur)} · ${plural(m.requests, "%1 request", "%1 requests")}`}>
            <span class="week-bar-name">{m.model}</span>
            <span class="week-bar-meter"><span style={{ width: `${100 * m.share}%` }} /></span>
            <span class="week-bar-value small muted">{moneyText(m.cost, cur)} · {shareText(m.share)}</span>
          </li>
        ))}
      </ul>
      {cacheText(recap) ? <div class="small muted">{cacheText(recap)}</div> : null}
    </section>
  );
}

// What would use less of your plan (Claude Code's /usage rules), and what
// coming back to chats after their cache expired cost
function Tips({ recap, copied, onCopy }: { recap: WeekRecap; copied: string; onCopy: (text: string) => void }) {
  const cold = coldText(recap);
  return (
    <section class="week-section">
      <h2>What could use less of your plan</h2>
      {!recap.tips.length && !cold ? <div class="muted">Nothing stands out: no habit takes a tenth of the usage shown.</div> : null}
      <ul class="week-tips">
        {recap.tips.map((t) => (
          <li key={t.key} class="week-tip">
            <Icon name={I[tipMeaning(t.key)]} class="week-tip-icon" />
            <span class="week-tip-text">
              <span class="week-tip-title">{t.title}</span>
              {t.detail ? <span class="small muted">{t.detail}</span> : null}
            </span>
            {t.pct !== null ? (
              <span class="week-tip-pct small"
                title={`${t.pct}% of the usage shown: of the usage of these days, as Claude Code's /usage weighs it toward your plan's limits. A request can count for several of these.`}>
                {t.pct}%
              </span>
            ) : null}
            {t.command ? (
              <button type="button" class="chip code" title={`Copy ${t.command}, to type it in a chat of yours`} onClick={() => onCopy(t.command)}>
                {copied === t.command ? "Copied" : t.command}
              </button>
            ) : null}
          </li>
        ))}
      </ul>
      {cold ? <div class="small muted">{cold}</div> : null}
    </section>
  );
}
