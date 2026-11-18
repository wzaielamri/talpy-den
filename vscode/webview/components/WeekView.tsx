import { drawCard } from "../util/card";
import { Fragment, type JSX } from "preact";
import { useEffect, useRef, useState } from "preact/hooks";
import { hostLabel, plural } from "../../src/shared/model";
import type { LimitAccount, LimitHistory, WeekChat, WeekDay, WeekPlanWindow, WeekRecap, WeekSpan, WeekTip, WeekTipChat } from "../../src/shared/types";
import {
  currencyOf,
  dayTip,
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
  planUseText,
  planUseTip,
  weekShareShort,
  weekShareTip,
  RECAP_SECTIONS,
  type RecapSection,
  rowDay,
  tipMeaning,
  tipSource,
  tipShareShown,
  tipShareText,
  tipShareTip,
  TIPS_TOO_LITTLE,
  dayLanes,
  laneNumbers,
  daysBack,
  laneHoverText,
  laneTicks,
  LANES_HINT,
  mixLabel,
  mixTip,
  mixValue,
  modelRowText,
  modelTip,
  tipChatAct,
  tipsShown,
  tipWas,
  weekTiles,
  workText,
  workBeforeText,
  doneText,
  doneTip,
  commitsShown,
  listedChatRef,
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
  limitValueText,
  limitStart,
  limitShareText,
  limitSizeTip,
  limitTokensText,
  limitWeekBars,
} from "../../src/shared/week";
import { reviewPending, testsText } from "../../src/shared/pane";
import { post } from "../env";
import { I, Icon } from "../util/icons";
import { useView } from "./context";
import { Tag, TestsTag } from "./Tag";
import { useViewVisible } from "../util/petStage";
import { useStore } from "../util/store";
import { limitsAnswer, limitsAsked, limitsRound, useReadAgain, weekAnswer } from "../util/stores";
import { setTab, showProject } from "../util/ui";
import { Reading } from "./Reading";

const REFRESH_MS = 10 * 60000; // while the tab is in sight

// The Recap tab: your last 7 days with Claude, as a story. The big picture
// (how long you were at it, how long Claude worked, your prompts, its
// tokens, the API prices), when (a day per row on a timeline, chat by
// chat), what got done (by project, its chats with their commits and
// Claude's recaps, what Claude did in all), what it meant for your plan,
// where the usage went (by model at API prices, then as your plan's limits
// count it) and what would use less of your plan (the rules of Claude Code's
// own /usage, each with what acts on it); in Overall,
// last, your plan's limits over time. The extension runs the
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
  // at the view's Refresh; those two read your plan's limits over time
  // again too, once it's in sight (limitsRound), as does opening the tab
  // when they were read over 10 minutes ago
  const again = () => {
    ask();
    limitsRound.set(limitsRound.get() + 1);
  };
  useEffect(() => {
    if (!visible) return;
    ask();
    const timer = setInterval(again, REFRESH_MS);
    return () => clearInterval(timer);
  }, [visible, span, back, account, hostsKey, currency]);
  useEffect(() => {
    const read = limitsAnswer.get()?.data?.generatedAt;
    if (visible && read && Date.now() - read > REFRESH_MS) limitsRound.set(limitsRound.get() + 1);
  }, [visible]);
  useReadAgain(visible, again, true);

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

  // (in the order of RECAP_SECTIONS: when, what got done, your plan, then
  // the money; in Overall, your plan's limits over time last)
  const sections: Record<RecapSection, () => JSX.Element | null> = {
    days: () => (dayLanes(recap!) ? null : <Timeline recap={recap!} onDay={(day) => {
      setSpan("day");
      setBack(Math.max(0, daysBack(day, Date.now())));
    }} />),
    lanes: () => <Lanes recap={recap!} />,
    projects: () => <Done recap={recap!} />,
    plan: () => <Plan recap={recap!} />,
    usage: () => <Usage recap={recap!} />,
    tips: () => <Tips recap={recap!} copied={copied} onCopy={copy} />,
    limits: () => (recap!.span === "all" ? <Limits recap={recap!} account={account} /> : null),
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
          {RECAP_SECTIONS.map((k) => <Fragment key={k}>{sections[k]()}</Fragment>)}
          <div class="week-foot small muted">{footText(recap)}</div>
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
// (bare: its button alone, in a line of What got done's; tip: more for its tooltip)
function ChatLine({ c, cur, where, sub, bare, tip }: { c: WeekChat; cur: Currency; where?: string; sub?: boolean; bare?: boolean; tip?: string }) {
  const line = (
    <button type="button" class={"week-chat" + (sub ? " sub" : "")} disabled={!!c.host || !c.chatId}
      title={(c.host ? `${c.name} on ${hostLabel(c.host)}: its row under ${hostLabel(c.host)} opens it` : `Open “${c.name}”`) + (tip ? `\n${tip}` : "")}
      onClick={() => post({ type: "openWeekChat", chatId: c.chatId, profileDir: c.profileDir, name: c.name, cwd: c.cwd })}>
      <span class="week-chat-name">{c.name}</span>
      <span class="week-chat-folder small muted">{where ?? (c.host ? hostLabel(c.host) + ": " : "") + c.folder}</span>
      <span class="week-chat-value small muted">{hoursText(c.workedMs)} · {moneyText(c.cost, cur)}</span>
    </button>
  );
  return bare ? line : <li>{line}</li>;
}

// A day per row: when you were at it, when Claude worked (darker where
// several chats worked at once), when it waited for your answer, where a
// usage limit stopped a chat. Click a day for its chats.
function Timeline({ recap, onDay }: { recap: WeekRecap; onDay: (day: string) => void }) {
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
  const opensDay = recap.span === "week"; // (a day's name: that day alone, a Day; its row unfolds its chats)
  return (
    <section class={"week-section" + (weeks ? " week-weeks" : "")}>
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
              title={dayTip(d, cur, recap)} {...(d.chats?.length ? opens(shown, () => setOpen(shown ? "" : d.day)) : { onClick: () => setOpen("") })}>
              {opensDay ? (
                <button type="button" class="week-day small week-day-open" title={`${rowDay(d.day)}\nThis day alone`}
                  onClick={(e) => {
                    e.stopPropagation();
                    onDay(d.day);
                  }}
                  onKeyDown={(e) => e.stopPropagation()}>
                  {rowDay(d.day, weeks, d.to)}
                </button>
              ) : <span class="week-day small">{rowDay(d.day, weeks, d.to)}</span>}
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
          : hover ? hoverText(recap.days[hover.row], hover.ms, recap.generatedAt, hover.px)
            : opensDay ? "Point at a day to see what went on then; click it for its chats, or its name for that day alone."
              : "Point at a day to see what went on then; click it for its chats."}
      </div>
    </section>
  );
}

// Your plan: what these days meant for each account's plan (week.py
// plan_use: how much of its week they used, its full 5-hour windows, how
// often it ran out and how long that held chats), its line's tooltip how
// each is worked out; on today's Day its windows now under it, how they
// filled up (this computer's accounts, from the widget's usage history)
function Plan({ recap }: { recap: WeekRecap }) {
  const uses = recap.planUse ?? [];
  const now = recap.plan ?? [];
  const ids = [...uses.map((u) => u.account), ...now.map((p) => p.account).filter((id) => !uses.some((u) => u.account === id))];
  if (!ids.length) return null;
  return (
    <section class="week-section">
      <h2>Your plan</h2>
      {ids.map((id) => {
        const u = uses.find((x) => x.account === id);
        const p = now.find((x) => x.account === id);
        const plan = u?.plan ?? recap.accounts.find((a) => a.id === id)?.plan;
        return (
          <div key={id} class="week-plan-account">
            {ids.length > 1 ? <div class="week-plan-name">{(u?.name ?? p?.name ?? "") + (plan ? ` · ${plan}` : "")}</div> : null}
            {u ? <div class="week-plan-line" title={planUseTip(u, recap)}>{planUseText(u, recap)}</div> : null}
            {p?.windows.length ? (
              <ul class="week-bars week-plan">
                {p.windows.map((w) => (
                  <li key={w.key} title={`${w.label}: ${Math.round(w.pct)}% used\nHow this window of your plan filled up, from its start (on the left) to when it resets (on the right), as Talpy Den saw it.`}>
                    <span class="week-bar-name">{w.label}</span>
                    <FillChart w={w} now={recap.generatedAt} />
                    <span class={"week-bar-value small" + (w.pct >= 90 ? " over" : " muted")}>
                      {planText(w, recap.generatedAt)}
                    </span>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        );
      })}
    </section>
  );
}

// Your plan's limits over time (week.py --limits), Overall's last section:
// asked for only once it scrolls into view, not when the tab opens nor
// again on a change of span; again on a change of account, at the view's
// Refresh and the tab's 10-minute read (limitsRound). While its numbers
// come, a dim line in its place (what was read before stays, dimmed).
function Limits({ recap, account }: { recap: WeekRecap; account: string }) {
  const answer = useStore(limitsAnswer);
  const round = useStore(limitsRound);
  const box = useRef<HTMLElement>(null);
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const el = box.current;
    if (!el || typeof IntersectionObserver === "undefined") return undefined;
    const seen = new IntersectionObserver((entries) => setInView(entries.some((e) => e.isIntersecting)));
    seen.observe(el);
    return () => seen.disconnect();
  }, []);
  const want = `${account}|${round}`;
  useEffect(() => {
    if (!inView || limitsAsked.get() === want) return;
    limitsAsked.set(want);
    post({ type: "limits", account });
  }, [inView, want]);
  const mine = answer && answer.account === account ? answer : null;
  const data: LimitHistory | null = answer?.data ?? null;
  const cur = currencyOf(data ?? recap);
  const shown = (data?.accounts ?? []).filter((a) => a.periods.length);
  const plans = new Set(shown.map((a) => a.plan));
  return (
    <section ref={box} class={"week-section week-limits" + (data && !mine ? " busy" : "")}>
      <h2>
        Your plan's limits over time <span class="limits-estimate muted">· estimates</span>
      </h2>
      {mine?.error ? (
        <div class="msg error" role="alert">Couldn't work it out: {mine.error}</div>
      ) : !data ? (
        <div class="limits-waiting"><Reading text="Working out how much your plan's windows held, from your chats and the limit readings kept." /></div>
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
                    <td>{a.now.fiveHour ? limitValueText("", a.now.fiveHour, cur).text : "–"}</td>
                    <td>{a.now.weeks.seven_day ? limitValueText("", a.now.weeks.seven_day, cur).text : "–"}</td>
                    <td>{a.now.share ? `${Math.round(a.now.share.pct)}%` : "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
          {shown.map((a) => <LimitsOf key={a.id} a={a} many={shown.length > 1} cur={cur} now={data.generatedAt}
            start={limitStart(shown, data.generatedAt)} />)}
          <div class="small muted">{limitFootText(data)}</div>
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
  const mix = limitMix(a.now.costs, a.now.tokens);
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
          const value = limitValueText(k, k === "five_hour" ? a.now.fiveHour : a.now.weeks[k], cur);
          const change = a.changes[k === "five_hour" ? "fiveHour" : k];
          return (
            <li key={k} title={limitSizeTip(k, a, cur)}>
              <span class="week-bar-name">{limitLabel(k)}</span>
              <span class={"limits-value" + (value.rough ? " rough" : "")}>{value.text}</span>
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
            <span>{limitShareText(a.now.share.pct, a.now.share.rough)}</span>
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

// What got done, by project (a chat started in a subfolder of a repository
// counts for the repository): its commits and the files Claude's edits
// changed, its time and amount. A click unfolds its chats in place (here and
// on an SSH host alike), each with Claude's recap of it and its commits; the
// button at the row's end opens one of this computer's in the Projects tab.
// Under the list, what Claude did in all, dim.
function Done({ recap }: { recap: WeekRecap }) {
  const [open, setOpen] = useState("");
  const work = workText(recap.work);
  if (!recap.projects.length && !work) return null;
  const cur = currencyOf(recap);
  const most = Math.max(1, ...recap.projects.map((p) => p.workedMs));
  return (
    <section class="week-section">
      <h2>What got done</h2>
      <ul class="week-bars week-projects week-done">
        {recap.projects.map((p) => {
          const key = p.host + "|" + p.path;
          const shown = open === key;
          const chats = Array.isArray(p.chats) ? p.chats : [];
          const done = doneText(p);
          const tip = doneTip(p);
          const share = weekShareShort(p);
          const shareTip = weekShareTip(p, recap);
          return [
            <li key={key} class={"opens" + (shown ? " open" : "")} {...opens(shown, () => setOpen(shown ? "" : key))}
              title={`${p.host ? hostLabel(p.host) + ": " : ""}${p.path}\nClaude worked ${hoursText(p.workedMs)} · ${moneyText(p.cost, cur)} at API prices\n` +
                `${plural(p.prompts, "%1 prompt", "%1 prompts")} · ${plural(p.chatCount ?? chats.length, "%1 chat", "%1 chats")}` +
                (tip ? `\n${tip}` : "") + (shareTip ? `\n${shareTip}` : "") +
                `\n\n${shown ? "Click to fold its chats." : "Click for its chats: what each got done."}`}>
              <span class="week-bar-name">
                <Icon name={I.folded} class={shown ? "turn" : ""} />
                {(p.host ? hostLabel(p.host) + ": " : "") + p.name}
              </span>
              <span class="week-done-text small muted">{done}</span>
              <span class="week-bar-meter work"><span style={{ width: `${(100 * p.workedMs) / most}%` }} /></span>
              <span class="week-bar-value small muted">{hoursText(p.workedMs)} · {moneyText(p.cost, cur)}{share ? ` · ${share}` : ""}</span>
              {/* (this computer's: to the Projects tab; an SSH host's keeps its room, so the numbers line up) */}
              {p.host ? <span class="week-done-go" aria-hidden="true" /> : (
                <button type="button" class="icon-btn week-done-go" title={"Open in the Projects tab\nAll its chats, plans and memories."}
                  aria-label="Open in the Projects tab"
                  onClick={(e) => {
                    e.stopPropagation();
                    showProject(p.folder || p.path);
                  }}
                  onKeyDown={(e) => e.stopPropagation()}>
                  <Icon name={I.project} />
                </button>
              )}
            </li>,
            shown ? (
              <li key={key + "/chats"} class="week-sub">
                <ul class="week-chats week-done-chats">
                  {chats.map((c) => <DoneChat key={c.host + c.chatId} c={c} cur={cur} recap={recap} />)}
                </ul>
                {(p.chatCount ?? 0) > chats.length ? (
                  <span class="small muted week-more">and {(p.chatCount ?? 0) - chats.length} more {(p.chatCount ?? 0) - chats.length === 1 ? "chat" : "chats"}</span>
                ) : null}
              </li>
            ) : null,
          ];
        })}
      </ul>
      {work ? <div class="week-done-work small muted" title={["What Claude did", workBeforeText(recap)].filter(Boolean).join("\n")}>{work}</div> : null}
    </section>
  );
}

// A chat in What got done, under its project: its line (its name, what it
// got done, its time and amount; a click brings it up), a chat whose changes
// you haven't reviewed says so with its tests (as its row in the chat
// list), then Claude's recap of what it did then (one line, the whole in
// its tooltip) and its commits' subjects, the newest three and how many more
// (with its share of your week in its tooltip)
function DoneChat({ c, cur, recap }: { c: WeekChat; cur: Currency; recap: WeekRecap }) {
  const view = useView();
  const listed = c.review ? listedChatRef(view.status, view.hosts, c.chatId, c.host) : null;
  const toReview = !!c.review && reviewPending({ review: c.review, chatId: c.chatId, sessionId: c.chatId, state: listed?.state ?? "done" },
    view.status, c.host || undefined);
  const tests = toReview ? testsText(c.review) : null;
  const { shown, more } = commitsShown(c);
  return (
    <li class="week-done-chat">
      <div class="week-done-line">
        <ChatLine c={c} cur={cur} where={doneText(c)} sub bare tip={weekShareTip(c, recap)} />
        <span class="week-done-tags">
          {toReview ? (
            <Tag text="To review" active
              title="It changed files. Click to see what it changed, against how the files were before the chat: undo it, commit only its files, or mark it reviewed."
              onClick={listed ? () => post({ type: "openPane", chat: listed, tab: "review" }) : undefined} />
          ) : null}
          {tests ? <TestsTag tests={tests} /> : null}
        </span>
      </div>
      {c.recap?.text ? <div class="week-done-recap small muted" title={`Claude's recap\n${c.recap.text}`}>{c.recap.text}</div> : null}
      {shown.map(([hash, subject], i) => (
        <div key={hash + i} class="week-done-commit small" title={hash ? `${subject}\nCommit ${hash}` : subject}>
          <Icon name={I.commit} />
          <span class="week-done-subject">{subject}</span>
          {i === shown.length - 1 && more ? <span class="muted nowrap">and {more} more</span> : null}
        </div>
      ))}
    </li>
  );
}

// The Day view, chat by chat: when each chat worked, waited for you (a
// permission, a question) or was paused (asleep, a usage limit); between
// those it was your turn. A name brings the chat up. On top, the day's own
// row (when you were at it, when Claude worked, waited, a usage limit), on
// the same hours; at each lane's end its chat's time and cost.
function Lanes({ recap }: { recap: WeekRecap }) {
  const [hover, setHover] = useState<{ x: number; ms: number; px: number } | null>(null);
  const lanes = recap.lanes ?? [];
  if (!lanes.length) return null;
  const cur = currencyOf(recap);
  const day = recap.span === "day" ? recap.days[0] : undefined;
  const dayParts: [number, number][] = day ? [...day.you, ...day.work, ...day.wait].map(([a, b]) => [a, b]) : [];
  const t0 = Math.min(...lanes.map((l) => l.parts[0][0]), ...dayParts.map((p) => p[0]));
  const t1 = Math.max(...lanes.map((l) => l.parts[l.parts.length - 1][1]), ...dayParts.map((p) => p[1]));
  const span = Math.max(60000, t1 - t0);
  const at = (ms: number) => `${((ms - t0) / span) * 100}%`;
  const ticks = laneTicks(t0, t1);
  // (the mouse over a lane, the day's row too: its moment, a line across them all)
  const point = {
    onMouseMove: (e: MouseEvent) => {
      const box = (e.currentTarget as HTMLElement).getBoundingClientRect();
      const x = Math.max(0, Math.min(box.width, e.clientX - box.left));
      setHover({ x: x / Math.max(1, box.width), ms: t0 + (x / Math.max(1, box.width)) * span, px: span / Math.max(1, box.width) });
    },
    onMouseLeave: () => setHover(null),
  };
  const marks = (
    <>
      {ticks.map((t) => <i key={"h" + t} class="lane-hour" style={{ left: at(t) }} />)}
      {hover ? <i class="lane-cross" style={{ left: `${hover.x * 100}%` }} /> : null}
    </>
  );
  const along = (a: number, b: number) => `max(1.5px, ${((b - a) / span) * 100}%)`;
  const time = (ms: number) => new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const paused = lanes.some((l) => l.parts.some((p) => p[2] === "p"));
  const limits = day?.limits ?? [];
  // (only what's drawn: you and the limits on the day's row, a pause on a chat's)
  const kinds: [string, string][] = [
    ...(dayParts.length ? [["u", "You"] as [string, string]] : []),
    ["w", "Claude worked"], ["y", "Waited for you"],
    ...(paused ? [["p", "Paused (asleep, a limit)"] as [string, string]] : []),
    ...(limits.length ? [["l", "A usage limit stopped a chat"] as [string, string]] : []),
  ];
  return (
    <section class="week-section">
      <h2>Chat by chat</h2>
      <div class="week-lanes-legend small muted">
        {kinds.map(([k, text]) => <span key={k}><i class={`lane-${k}`} aria-hidden="true" />{text}</span>)}
      </div>
      <ul class="week-lanes">
        {day && dayParts.length ? (
          <li key="day">
            <span class="week-lane-name small strong">All chats</span>
            <span class="week-lane week-lane-day" title={`All chats\n${dayTip(day, cur)}`} {...point}>
              {marks}
              {day.wait.map(([a, b]) => <i key={"y" + a} class="lane-y" style={{ left: at(a), width: along(a, b) }} />)}
              {day.work.map(([a, b, n]) => <i key={"w" + a} class={"lane-w" + (n >= 3 ? " many" : n === 2 ? " two" : "")} style={{ left: at(a), width: along(a, b) }} />)}
              {day.you.map(([a, b]) => <i key={"u" + a} class="lane-u" style={{ left: at(a), width: along(a, b) }} />)}
              {limits.map((t) => <i key={"l" + t} class="lane-l" style={{ left: at(t) }} />)}
            </span>
            <span />
          </li>
        ) : null}
        {lanes.map((l) => (
          <li key={l.key}>
            <button type="button" class="week-lane-name small" disabled={!!l.host || !l.id}
              title={l.host ? `${l.name} on ${hostLabel(l.host)}` : `Open “${l.name}”`}
              onClick={() => post({ type: "openWeekChat", chatId: l.id, profileDir: l.profileDir ?? "", name: l.name, cwd: "" })}>
              {(l.host ? hostLabel(l.host) + ": " : "") + l.name}
            </button>
            <span class="week-lane" title={`${l.name}\nClaude worked ${hoursText(l.workedMs)}, waited for you ${hoursText(l.waitedMs)}${l.project ? `\n${l.project}` : ""}`} {...point}>
              {marks}
              {l.parts.map(([a, b, k], i) => <i key={i} class={`lane-${k}`} style={{ left: at(a), width: along(a, b) }} />)}
            </span>
            <span class="week-lane-num small muted">{laneNumbers(l, cur)}</span>
          </li>
        ))}
        <li class="week-lanes-times small muted" aria-hidden="true">
          <span />
          {/* (its whole hours; none in between: its first and last times) */}
          {ticks.length ? (
            <span class="week-lanes-hours">{ticks.map((t) => <span key={t} style={{ left: at(t) }}>{time(t)}</span>)}</span>
          ) : <span><span>{time(t0)}</span><span>{time(t1)}</span></span>}
          <span />
        </li>
      </ul>
      <div class={"week-readout small" + (hover ? "" : " muted")}>{hover ? laneHoverText(lanes, day, hover.ms, hover.px) : LANES_HINT}</div>
    </section>
  );
}

// Where the usage went: by model (its amount at API prices), then weighed as
// Claude Code's /usage weighs it toward your plan's limits (subagents, over
// 150k of context, effort levels: week.py usage_mix), each with its share
// the period before
function Usage({ recap }: { recap: WeekRecap }) {
  const mix = recap.usageMix ?? [];
  if (!recap.models.length && !mix.length) return null;
  const cur = currencyOf(recap);
  return (
    <section class="week-section">
      <h2>Where the usage went</h2>
      <ul class="week-bars week-usage">
        {recap.models.map((m) => (
          <li key={m.model} title={`${m.model}\n${modelTip(m, recap)}`}>
            <span class="week-bar-name">{m.model}</span>
            <span class="week-bar-meter"><span style={{ width: `${100 * m.share}%` }} /></span>
            <span class="week-bar-value small muted">{modelRowText(m, cur)}</span>
          </li>
        ))}
      </ul>
      {mix.length ? (
        <>
          <div class="small muted week-usage-how">As your plan's limits count it (Claude Code's /usage):</div>
          <ul class="week-bars week-usage">
            {mix.map((p) => (
              <li key={p.key} title={`${mixLabel(p.key)}\n${mixTip(p, recap)}`}>
                <span class="week-bar-name">{mixLabel(p.key)}</span>
                <span class="week-bar-meter"><span style={{ width: `${Math.min(100, p.pct)}%` }} /></span>
                <span class="week-bar-value small muted">{mixValue(p)}</span>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </section>
  );
}

// What would use less of your plan (Claude Code's /usage rules, coming back
// to chats after their cache expired, waits, limits); too little in the
// period: a dim line instead
function Tips({ recap, copied, onCopy }: { recap: WeekRecap; copied: string; onCopy: (text: string) => void }) {
  const view = useView();
  const tips = tipsShown(recap.tips, view.status);
  return (
    <section class="week-section">
      <h2>What could use less of your plan</h2>
      {recap.tooLittle ? <div class="muted">{TIPS_TOO_LITTLE}</div>
        : !tips.length ? <div class="muted">Nothing stands out: no habit takes a tenth of the usage shown.</div> : null}
      <ul class="week-tips">
        {tips.map((t) => (
          <li key={t.key} class="week-tip">
            <span class="week-tip-icon" title={tipSource(t.key)}><Icon name={I[tipMeaning(t.key)]} /></span>
            <span class="week-tip-text">
              <span class="week-tip-title">{t.title}</span>
              {t.detail ? <span class="small muted">{t.detail}</span> : null}
              {t.chats?.length ? (
                <ul class="week-tip-chats">
                  {t.chats.map((c) => <TipChat key={c.host + c.chatId} tip={t} c={c} />)}
                </ul>
              ) : null}
              {t.more ? <span class="small muted">and {t.more} more {t.more === 1 ? "chat" : "chats"}</span> : null}
            </span>
            {tipShareShown(t, recap.usageMix) ? (
              <span class="week-tip-pct small" title={tipShareTip(t, recap)}>
                {tipShareText(t)}
                {tipWas(t) ? <span class="muted">{tipWas(t)}</span> : null}
              </span>
            ) : null}
            {t.key === "waits" ? (
              // (Claude waited for your answers: the Permissions tab)
              <button type="button" class="chip" title={"Open the Permissions tab\nThe permission prompts you answered, and the rules that would let the same go without asking."}
                onClick={() => setTab("perms")}>
                <Icon name={I.permissions} /> Permissions
              </button>
            ) : t.command ? (
              <button type="button" class="chip code" title={`Copy ${t.command}, to type it in a chat of yours`} onClick={() => onCopy(t.command)}>
                {copied === t.command ? "Copied" : t.command}
              </button>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

// A chat a tip names: its name brings it up (this computer's), what the tip
// says of it, and Stop or Keep going where the chat list offers it now (the
// extension asks before it stops one, and finds the chat itself)
function TipChat({ tip, c }: { tip: WeekTip; c: WeekTipChat }) {
  const view = useView();
  const { act, ref } = tipChatAct(tip.key, c, view.status, view.hosts);
  return (
    <li class="week-tip-chat">
      <button type="button" class="week-chat" disabled={!!c.host || !c.chatId}
        title={c.host ? `${c.name} on ${hostLabel(c.host)}: its row under ${hostLabel(c.host)} opens it` : `Open “${c.name}”`}
        onClick={() => post({ type: "openWeekChat", chatId: c.chatId, profileDir: c.profileDir, name: c.name, cwd: c.cwd })}>
        <span class="week-chat-name">{c.name}</span>
        <span class="week-chat-value small muted">{c.note}</span>
      </button>
      {act === "stop" && ref ? (
        <button type="button" class="chip" title={"Stop this chat\nAsks first. It's idle: Claude quits, and the chat is kept."}
          onClick={() => post({ type: "stop", chat: ref })}>
          <Icon name={I.stop} /> Stop
        </button>
      ) : (act === "keep" || act === "keepAtReset") && ref ? (
        <button type="button" class="chip"
          title={act === "keepAtReset"
            ? "Keep going until it's done\nIt goes on by itself a minute after the limit resets, in the background, and again after each later limit, until a turn of it ends by itself."
            : "Keep going until it's done\nWhen a usage limit stops this chat, it goes on by itself in the background a minute after the limit resets, and again after each later one, until a turn of it ends by itself."}
          onClick={() => post(act === "keepAtReset" ? { type: "queueContinue", chat: ref, keep: true } : { type: "keepGoing", chat: ref, on: true })}>
          <Icon name={I.keepGoing} /> Keep going
        </button>
      ) : act === "kept" ? <span class="small muted">Keeps going</span> : null}
    </li>
  );
}
