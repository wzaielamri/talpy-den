// What a chat waiting for a permission asks, with Allow once / Always allow /
// Deny (with a note), or Claude's questions to answer: in its row and in its
// chat tab (a change it asks for as CodeView.tsx draws it).

import { useEffect, useRef, useState } from "preact/hooks";
import type { Answers, Decision, PermissionAsk, Question } from "../../src/shared/types";
import { I, Icon, T } from "../util/icons";
import { Markdown } from "../util/markdown";
import { Diff } from "./CodeView";

// The prompt an AskBox is for: a Deny note begun for one prompt goes when
// the chat asks the next
export function askKey(ask: PermissionAsk): string {
  return ask.request ?? ask.line;
}

// Another prompt in the place of the one shown (a parallel subagent's, the
// next one): its buttons wait SETTLE_MS, so a click meant for the one before
// doesn't answer it, and it says it's new for FRESH_MS (not the hook's request
// coming for the prompt shown: the same thing asked)
const SETTLE_MS = 600;
const FRESH_MS = 3000;

// What it asks with when there's no command or change to show (an MCP
// tool's, a page's): in a row the first ARG_ROWS, one line each (the chat's
// tab: all of them)
const ARG_ROWS = 3;

// What a waiting chat asks, with Allow once / Always allow / Deny (a note);
// Claude's questions: each with its options, Send answers / Decline (a note)
export function AskBox({ ask, onAnswer, onWholePlan, onTerminal, busy = false, max = 12, compact = false }: {
  ask: PermissionAsk;
  onTerminal?: () => void; // (a background chat's, in its tab: where it can't be answered here, a terminal on it, claude attach)
  onWholePlan?: () => void; // (a row: the chat's tab shows all of it)
  onAnswer: (d: Decision, note: string, answers?: Answers) => void;
  busy?: boolean;
  max?: number;
  compact?: boolean; // (in a row: the options' descriptions in tooltips)
}) {
  const k = askKey(ask);
  const what = [ask.tool, ask.line, ask.command, ask.file].join("\n");
  const request = ask.request ?? "";
  const shown = useRef({ k, what, request, changed: 0 });
  if (shown.current.k !== k) {
    const other = what !== shown.current.what || (!!request && !!shown.current.request && request !== shown.current.request);
    shown.current = { k, what, request, changed: other ? Date.now() : 0 };
  }
  const since = shown.current.changed ? Date.now() - shown.current.changed : Infinity;
  const settling = since < SETTLE_MS;
  const fresh = since < FRESH_MS;
  const [, redraw] = useState(0);
  useEffect(() => {
    if (!fresh) return;
    const timers = [SETTLE_MS, FRESH_MS].filter((ms) => ms > since).map((ms) => setTimeout(() => redraw((n) => n + 1), ms - since));
    return () => timers.forEach(clearTimeout);
  }, [shown.current.changed]);
  const off = busy || settling;
  const [denyingFor, setDenyingFor] = useState(""); // (the prompt a Deny… was begun for)
  const denying = denyingFor === k;
  const setDenying = (on: boolean) => {
    if (on && !denying) setNote("");
    setDenyingFor(on ? k : "");
  };
  const [note, setNote] = useState("");
  const canAnswer = ask.answer === "hook" || ask.answer === "keys";
  const questions = ask.questions ?? [];
  const plan = ask.plan ?? null;
  const args = ask.args ?? [];
  const title = plan ? "Claude has a plan, ready to start:" : questions.length
    ? questions.length > 1 ? `Claude asks you ${questions.length} questions:` : "Claude asks you:"
    : ask.command ? "Claude asks to run:" : ask.file ? `Claude asks to change ${ask.file}:` : `Claude asks: ${ask.line}`;
  const deny = () => {
    if (off) return;
    onAnswer(plan ? "keep" : "deny", note);
    setDenying(false);
    setNote("");
  };
  return (
    <div class="ask-box">
      <div class="ask-title">{fresh ? "New prompt · " : ""}{title}</div>
      {ask.command ? <pre class="ask-command">{ask.command}</pre> : null}
      {args.length ? (
        <div class={"ask-command ask-args" + (compact ? " compact" : "")}>
          {(compact ? args.slice(0, ARG_ROWS) : args).map((a, i) => <div key={i}>{compact ? a.replace(/\s+/g, " ") : a}</div>)}
          {compact && args.length > ARG_ROWS ? <div class="ask-more">… {args.length - ARG_ROWS} more: Talpy Chat shows them all</div> : null}
        </div>
      ) : null}
      {plan ? (
        <div class={"ask-plan" + (compact ? " compact" : "")}>
          <Markdown text={plan.text} />
        </div>
      ) : null}
      {plan && (compact || plan.cut) && onWholePlan ? (
        <button type="button" class="link small" onClick={onWholePlan}>Read the whole plan</button>
      ) : null}
      {canAnswer && !denying && plan ? (
        <div class="ask-buttons">
          <button type="button" class="btn secondary" disabled={off} onClick={() => onAnswer("approve-edits", "")}
            title="It starts on the plan and changes files without asking for the rest of this chat (accept edits mode); commands still ask.">
            <Icon name={I.always} tone={T.always} /><strong>Approve, accept edits</strong>
          </button>
          <button type="button" class="btn secondary" disabled={off} onClick={() => onAnswer("approve", "")}
            title="It starts on the plan and asks before each change, as “Yes, manually approve edits” in its dialog.">
            <Icon name={I.allow} tone={T.allow} />Approve
          </button>
          <button type="button" class="btn secondary" disabled={off} onClick={() => setDenying(true)}><Icon name={I.edit} />Keep planning…</button>
        </div>
      ) : null}
      {ask.diff.length ? <Diff lines={ask.diff} max={max} path={ask.file} /> : null}
      {questions.length ? (
        <QuestionForm
          key={askKey(ask)}
          questions={questions}
          enabled={canAnswer && !off}
          buttons={canAnswer && !denying}
          compact={compact}
          onSend={(answers) => onAnswer("answer", "", answers)}
          onDecline={() => setDenying(true)}
        />
      ) : null}
      {canAnswer && !denying && !questions.length && !plan ? (
        <div class="ask-buttons">
          <button type="button" class="btn secondary" disabled={off} onClick={() => onAnswer("allow", "")}><Icon name={I.allow} tone={T.allow} />Allow once</button>
          {ask.answer === "keys" || ask.always ? (
            <button
              type="button"
              class="btn secondary"
              disabled={off}
              title={ask.answer === "keys" ? "Like “Yes, and don't ask again” in its dialog (for an edit, “Yes, allow all edits during this session”)."
                : `From now on, without asking: ${ask.always}.`}
              onClick={() => onAnswer("always", "")}
            >
              <Icon name={I.always} tone={T.always} />Always allow
            </button>
          ) : null}
          <button type="button" class="btn secondary" disabled={off} onClick={() => setDenying(true)}><Icon name={I.deny} tone={T.deny} />Deny…</button>
        </div>
      ) : null}
      {canAnswer && denying ? (
        <div class="ask-buttons">
          <input
            type="text"
            class="ask-note"
            placeholder={plan ? "What should change in the plan? (optional)" : "What should Claude do instead? (optional)"}
            value={note}
            onInput={(e) => setNote((e.target as HTMLInputElement).value)}
            onKeyDown={(e) => {
              // (not the Enter that picks a word in an input method's list)
              if (e.key === "Enter" && !e.isComposing && !off) {
                e.preventDefault();
                deny();
              }
            }}
          />
          <button type="button" class="btn secondary" disabled={off} onClick={deny}>{plan ? <Icon name={I.edit} /> : <Icon name={I.deny} tone={T.deny} />}{plan ? "Keep planning" : questions.length ? "Decline" : "Deny"}</button>
          <button type="button" class="btn secondary" onClick={() => setDenying(false)}>Cancel</button>
        </div>
      ) : null}
      {!canAnswer && onTerminal ? (
        <div class="ask-buttons">
          <button type="button" class="btn" onClick={onTerminal}><Icon name={I.terminal} />Answer it in a terminal</button>
        </div>
      ) : null}
      {!canAnswer && onTerminal ? (
        <div class="muted small">
          This background chat started without Talpy Den's hook, so what it asks can't be answered here: answer it in a terminal (claude attach shows Claude's own prompt), or run “Talpy Den: Answer Permission Prompts from Talpy Den…” for the next ones.
        </div>
      ) : !canAnswer ? (
        <div class="muted small">
          {plan
            ? "Approve it in the chat, or run “Talpy Den: Answer Permission Prompts from Talpy Den…” (it takes plans too) to approve it here."
            : questions.length
            ? "Answer it in the chat, or run “Talpy Den: Answer Permission Prompts from Talpy Den…” (it answers Claude's questions too) to answer it here."
            : "Answer it in the chat, or run “Talpy Den: Answer Permission Prompts from Talpy Den…” to answer it here."}
        </div>
      ) : null}
    </div>
  );
}

interface Chosen {
  labels: string[];
  text: string;
}

// Claude's questions (AskUserQuestion): each with its options, one to pick
// (or any, for a multiSelect one), and a field to answer in your own words
// instead (as "Type something." in Claude's dialog); then Send answers
function QuestionForm({ questions, enabled, buttons, compact, onSend, onDecline }: {
  questions: Question[];
  enabled: boolean;
  buttons: boolean;
  compact: boolean;
  onSend: (answers: Answers) => void;
  onDecline: () => void;
}) {
  const [chosen, setChosen] = useState<Record<number, Chosen>>({});
  const stateOf = (i: number): Chosen => chosen[i] ?? { labels: [], text: "" };
  // a click on an option: the one answer (instead of what you typed), or one more of several
  const choose = (i: number, label: string) => {
    const q = questions[i];
    const was = stateOf(i);
    const labels = q.multiSelect ? (was.labels.includes(label) ? was.labels.filter((l) => l !== label) : [...was.labels, label]) : [label];
    setChosen({ ...chosen, [i]: { labels, text: q.multiSelect ? was.text : "" } });
  };
  // what you typed: the answer instead of an option (or one more of several)
  const type = (i: number, text: string) => {
    const was = stateOf(i);
    setChosen({ ...chosen, [i]: { labels: questions[i].multiSelect || !text.trim() ? was.labels : [], text } });
  };
  const answers = (): Answers => {
    const out: Answers = {};
    questions.forEach((q, i) => {
      const s = stateOf(i);
      const values = q.options.map((o) => o.label).filter((l) => s.labels.includes(l));
      if (s.text.trim()) values.push(s.text.trim());
      if (values.length) out[q.question] = values;
    });
    return out;
  };
  const complete = questions.every((_, i) => stateOf(i).labels.length > 0 || stateOf(i).text.trim() !== "");
  return (
    <div class="ask-questions">
      {questions.map((q, i) => (
        <div key={i} class="ask-question">
          {q.header && questions.length > 1 ? <div class="ask-question-header muted">{q.header}</div> : null}
          <div class="ask-question-text">
            {q.question}
            {q.multiSelect ? <span class="muted"> (choose any)</span> : null}
          </div>
          {q.options.map((o) => (
            <label key={o.label} class="ask-option" title={compact && o.description ? o.description : undefined}>
              <input
                type={q.multiSelect ? "checkbox" : "radio"}
                disabled={!enabled}
                checked={stateOf(i).labels.includes(o.label)}
                onChange={() => choose(i, o.label)}
              />
              <span>
                {o.label}
                {!compact && o.description ? <span class="ask-option-desc muted">{o.description}</span> : null}
              </span>
            </label>
          ))}
          <input
            type="text"
            class="ask-note ask-own"
            placeholder="Or answer in your own words…"
            disabled={!enabled}
            value={stateOf(i).text}
            onInput={(e) => type(i, (e.target as HTMLInputElement).value)}
          />
        </div>
      ))}
      {buttons ? (
        <div class="ask-buttons">
          <button type="button" class="btn secondary" disabled={!enabled || !complete} onClick={() => onSend(answers())}><Icon name={I.send} />Send answers</button>
          <button type="button" class="btn secondary" disabled={!enabled} onClick={onDecline}><Icon name={I.deny} tone={T.deny} />Decline…</button>
        </div>
      ) : null}
    </div>
  );
}
