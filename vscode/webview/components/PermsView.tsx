import { useEffect, useRef, useState } from "preact/hooks";
import type { PermsData, WeekGrant, WeekRule } from "../../src/shared/types";
import { GRANTED_FEW, grantedIntro, grantMeaning, grantMeta, promptsText, ruleMeaning, ruleMeta } from "../../src/shared/week";
import { I, Icon, T } from "../util/icons";
import { post } from "../env";
import { useViewVisible } from "../util/petStage";
import { useStore } from "../util/store";
import { permsAnswer, weekRevokeAnswer, weekRuleAnswer } from "../util/stores";

const REFRESH_MS = 10 * 60000; // while the tab is in sight

// The Permissions tab: the permissions you gave, every rule and mode that
// lets chats on this computer go without asking (each to revoke), and the
// permission prompts you answered in the last 7 days with the rules that
// would have let the most of them through (talpyDen.recapRules can leave
// those out). The extension runs the widget's week.py --permissions for it
// (only while this tab is open): read from your settings and the chats'
// transcripts, no tokens used.
export function PermsView({ rules }: { rules: boolean }) {
  const visible = useViewVisible();
  const answer = useStore(permsAnswer);
  const [busy, setBusy] = useState(true); // asked, and its answer hasn't come
  // the change being written (host|id): one settings write at a time, every
  // section's buttons wait for it (as Plasma's)
  const [change, setChange] = useState("");
  // which kind of change was the last: only its message shows (as Plasma's one message)
  const [last, setLast] = useState<"rule" | "revoke" | "">("");

  function ask() {
    setBusy(true);
    post({ type: "perms" });
  }

  // Ask when the tab is in sight, again every 10 minutes
  useEffect(() => {
    if (!visible) return;
    ask();
    const timer = setInterval(ask, REFRESH_MS);
    return () => clearInterval(timer);
  }, [visible]);
  useEffect(() => {
    if (answer) setBusy(false);
  }, [answer]);

  // (a read that failed says why above what was read before, as Plasma's)
  const lastData = useRef<PermsData | null>(null);
  if (answer?.data) lastData.current = answer.data;
  const data = answer?.data ?? lastData.current;
  return (
    <div class={"week" + (busy && data ? " busy" : "")}>
      {busy && !data && !answer?.error ? <div class="muted">Reading your settings and the chats of the last 7 days.</div> : null}
      {answer?.error ? <div class="error">Couldn't read your permissions: {answer.error}</div> : null}
      {data ? (
        <>
          {/* this computer's, then each SSH host's shown (as listed there) */}
          {[{ host: "", ok: true, error: "", prompts: data.prompts, granted: data.granted }, ...(data.hosts ?? [])].map((src) =>
            src.ok ? (
              <div key={src.host} class="week">
                <Granted granted={src.granted ?? []} host={src.host} reload={ask} change={change}
                  setChange={(key) => { setChange(key); if (key) setLast("revoke"); }} said={last === "revoke"} />
                <Prompts prompts={src.prompts ?? null} host={src.host} rules={rules} reload={ask} change={change}
                  setChange={(key) => { setChange(key); if (key) setLast("rule"); }} said={last === "rule"} />
              </div>
            ) : (
              <div key={src.host} class="msg error" role="alert">Couldn't read the permissions on {src.host}: {src.error || "no answer"}</div>
            ))}
          <div class="week-foot small muted">
            Read from your settings and the chats on this computer{data.hosts?.length ? " and on the SSH hosts shown" : ""}, without using any tokens.
          </div>
        </>
      ) : null}
    </div>
  );
}

// The permission prompts you answered, and the rules that would have let
// the most of them through (written only when you allow one; the settings
// can leave them out)
function Prompts({ prompts: p, host, rules: suggest, reload, change: busyKey, setChange, said }: {
  prompts: PermsData["prompts"] | null; host: string; rules: boolean; reload: () => void;
  change: string; setChange: (key: string) => void; said: boolean;
}) {
  const ruleAnswer = useStore(weekRuleAnswer);
  const [asking, setAsking] = useState("");
  const seen = useRef(ruleAnswer); // (one from before the tab showed is old news)
  useEffect(() => {
    if (!ruleAnswer || ruleAnswer === seen.current) return;
    seen.current = ruleAnswer;
    if (ruleAnswer.host !== host) return; // (the section it's for reads them all again, once)
    setChange("");
    reload();
  }, [ruleAnswer]);
  if (!p) return null;
  const rules = suggest ? p.rules : [];
  const busy = !!busyKey;

  function change(rule: WeekRule, allow: boolean) {
    setAsking("");
    setChange(`${host}|${rule.id}`);
    post(allow
      ? { type: "weekRule", allow: true, kind: rule.kind, value: rule.value, project: rule.project, id: "", host }
      : { type: "weekRule", allow: false, kind: "", value: "", project: "", id: rule.id, host });
  }

  return (
    <section class="week-section">
      <h2>{host ? `Permission prompts on ${host}, last 7 days` : "Permission prompts, last 7 days"}</h2>
      <div>{p.answered ? promptsText(p) : `You answered no permission prompts on ${host || "this computer"} in the last 7 days.`}</div>
      {p.byTool.length ? <div class="small muted">For: {p.byTool.map(([tool, n]) => `${tool} ${n}`).join(" · ")}</div> : null}
      {rules.length ? (
        <div class="small muted">
          These rules would have let the most of them through. One you allow goes into the .claude/settings.local.json of the
          folder the chats started in (not shared through git), and only chats started there follow it.
        </div>
      ) : null}
      <ul class="week-rules">
        {rules.map((r) => (
          <li key={r.id} class="week-rule">
            <Icon name={I[ruleMeaning(r)]} class="week-rule-icon" />
            <span class="week-rule-text">
              <span>{r.title}</span>
              <span class="small muted">{ruleMeta(r)}</span>
              {asking === r.id ? (
                <span class="week-rule-ask">
                  <span class="small">This {r.change}.</span>
                  <span class="week-rule-buttons">
                    <button type="button" class="chip" disabled={busy} onClick={() => change(r, true)}><Icon name={I.allow} tone={T.allow} />Allow</button>
                    <button type="button" class="chip" onClick={() => setAsking("")}>Cancel</button>
                  </span>
                </span>
              ) : null}
            </span>
            {busyKey === `${host}|${r.id}` ? <span class="spinner" role="status" aria-label="Writing it…" />
              : r.state === "allowed" ? <span class="small muted">Allowed now</span>
              : r.state === "added" ? (
                <button type="button" class="chip" disabled={busy} onClick={() => change(r, false)}
                  title={"Take this rule back\nYou allowed it here: Undo removes it from the file it went into, as it was before."}>Undo</button>
              ) : asking !== r.id ? (
                <button type="button" class="chip" disabled={busy} onClick={() => setAsking(r.id)}>Allow…</button>
              ) : null}
          </li>
        ))}
      </ul>
      {said && ruleAnswer?.message && ruleAnswer.host === host ? (
        <div class={"small" + (ruleAnswer.ok ? "" : " error")} role="status">{ruleAnswer.ok ? ruleAnswer.message : `Nothing changed: ${ruleAnswer.message}`}</div>
      ) : null}
    </section>
  );
}

// The permissions you gave: every rule and mode that lets chats on this
// computer go without asking, each to revoke (it asks first)
function Granted({ granted, host, reload, change: busyKey, setChange, said }: {
  granted: WeekGrant[]; host: string; reload: () => void; change: string; setChange: (key: string) => void; said: boolean;
}) {
  const answer = useStore(weekRevokeAnswer);
  const [asking, setAsking] = useState("");
  const [all, setAll] = useState(false);
  const seen = useRef(answer); // (as in Prompts)
  useEffect(() => {
    if (!answer || answer === seen.current) return;
    seen.current = answer;
    if (answer.host !== host) return;
    setChange("");
    reload();
  }, [answer]);
  const busy = !!busyKey;

  function revoke(g: WeekGrant) {
    setAsking("");
    setChange(`${host}|${g.id}`);
    post({ type: "weekRevoke", id: g.id, host });
  }

  const shown = all ? granted : granted.slice(0, GRANTED_FEW);
  return (
    <section class="week-section">
      <h2>{host ? `Permissions you gave on ${host}` : "Permissions you gave"}</h2>
      <div class="small muted">{grantedIntro(granted, host)}</div>
      <ul class="week-rules">
        {shown.map((g) => (
          <li key={g.id} class="week-rule">
            <Icon name={I[grantMeaning(g)]} tone={T[grantMeaning(g)]} class="week-rule-icon" />
            <span class="week-rule-text">
              <span>{g.title}</span>
              <span class="small muted">{grantMeta(g)}</span>
              {asking === g.id ? (
                <span class="week-rule-ask">
                  <span class="small">This {g.change}.</span>
                  <span class="week-rule-buttons">
                    <button type="button" class="chip" disabled={busy} onClick={() => revoke(g)}><Icon name={I.cancel} tone={T.cancel} />Revoke</button>
                    <button type="button" class="chip" onClick={() => setAsking("")}>Cancel</button>
                  </span>
                </span>
              ) : null}
            </span>
            {busyKey === `${host}|${g.id}` ? <span class="spinner" role="status" aria-label="Writing it…" />
              : g.shared ? (
                g.managed ? <span class="small muted" title={"Set by your administrator\nIt's in /etc/claude-code: it can't be changed here."}>Administrator's</span>
                : <span class="small muted" title={"Shared through git\nThis folder's .claude/settings.json is shared with whoever uses its repository: change it there."}>In git</span>
              ) : asking !== g.id ? (
                <button type="button" class="chip" disabled={busy} onClick={() => setAsking(g.id)}>Revoke…</button>
              ) : null}
          </li>
        ))}
      </ul>
      {!all && granted.length > GRANTED_FEW ? (
        <button type="button" class="chip" onClick={() => setAll(true)}>Show {granted.length - GRANTED_FEW} more</button>
      ) : null}
      {said && answer?.message && answer.host === host ? (
        <div class={"small" + (answer.ok ? "" : " error")} role="status">{answer.ok ? answer.message : `Nothing changed: ${answer.message}`}</div>
      ) : null}
    </section>
  );
}
