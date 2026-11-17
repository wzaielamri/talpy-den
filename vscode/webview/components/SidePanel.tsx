// Talpy Chat's side questions (Claude's /btw, beside the chat; Plasma's SidePanel.qml: the same parts,
// words and clicks): questions about the chat that aren't added to it, answered by a copy of it with no
// tools while Claude goes on (pane.py --side-question), kept per chat to read again. Beside the chat where
// the view is wide enough (SIDE_WIDE), over the chat under its tabs where it isn't. Made only while it's
// open, outside the chat (fixed), so opening it lays out none of the conversation again; the list keeps
// to its newest while you're at its end.
//
// Each: your question (as your messages are), the answer (as Claude's replies are; a stand-in Claude
// wrote for one muted), when it was asked, on which model and what of the chat it saw (sideSaw); on hover
// Copy, Quote in reply, Ask with the whole chat (one asked about a part) and Remove (SIDE_ACTIONS' order).
// One on its way says so; one that got no answer says why, with Ask again.
// At the foot the box (Enter asks, Shift+Enter: a new line), the model a question goes to and what
// the next one costs, or, with a part of the chat picked (Ask from here), where it starts and what it
// costs, with × back to the whole chat.

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "preact/hooks";
import { foldedLine, SIDE_ACTIONS, SIDE_AGAIN, SIDE_FOLD_TIP, SIDE_FROM_SHOW, SIDE_UNFOLD_TIP, SIDE_ASK_WHOLE, SIDE_CLEAR, SIDE_CLEAR_ASK, SIDE_CLOSE, SIDE_COPY, SIDE_EMPTY, SIDE_PENDING, SIDE_PICK_TIP, SIDE_PICKS,
         SIDE_PLACEHOLDER, SIDE_QUOTE, SIDE_REMOVE, SIDE_TITLE, SIDE_WHOLE, SIDE_WHOLE_TIP, sideModelLabel, sidePickLabel, sideSaw, sideState, timeText,
         type ShownSide, type SidePick } from "../../src/shared/pane";
import { I, Icon, T } from "../util/icons";
import { Markdown } from "../util/markdown";
import { IconButton } from "./IconButton";
import { TalpyIcon } from "./TalpyIcon";

export function SidePanel({ items, wide, anchor, shown, loaded, asked, draft, pick, pickOpen, setPickOpen, line, part, note, style,
                            onAsk, onPick, onRemove, onRemoveAll, onAgain, onAskWhole, onCopy, onQuote, onCopyCode, onWhole, onShowPart, onFold, onClose }: {
  items: readonly ShownSide[];
  wide: boolean; // beside the chat, else over it under its tabs (anchor)
  anchor: { current: HTMLElement | null };
  shown: boolean; // the view in front (Talpy moves only then)
  loaded: boolean; // the chat was read: none listed means none
  asked: number; // questions asked here: each one goes to the list's end
  draft: { current: string }; // the box's words, kept while it's closed
  pick: SidePick;
  pickOpen: boolean;
  setPickOpen: (open: boolean) => void;
  line: { text: string; tip: string }; // sideLine's: what the next one costs, or the part picked ("": none)
  part: boolean; // a part of the chat picked (Ask from here): × back to all of it
  note: { text: string; ok: boolean } | null; // what went wrong removing one; Ask from here's word on a part it can't be
  style: Record<string, string>;
  onAsk: (text: string) => void;
  onPick: (pick: SidePick) => void;
  onRemove: (s: ShownSide) => void;
  onRemoveAll: () => void;
  onAgain: (s: ShownSide) => void;
  onAskWhole: (s: ShownSide) => void;
  onCopy: (s: ShownSide) => void;
  onQuote: (s: ShownSide) => void;
  onCopyCode: (code: string) => void;
  onWhole: () => void;
  onShowPart: () => void;
  onFold: (s: ShownSide, on: boolean) => void;   // (a click on a question's ›: just its question, or all of it again)   // (the part line clicked: to where it starts in the chat)
  onClose: () => void;
}) {
  const card = useRef<HTMLDivElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const box = useRef<HTMLTextAreaElement>(null);
  const atEnd = useRef(true);
  const [text, setText] = useState(draft.current);
  const [clearAsk, setClearAsk] = useState(false);
  const [copied, setCopied] = useState("");
  // (the rows are made again only when they change, not with each key typed in the chat: their clicks call
  // this render's handlers, which see the pick and the reply box as they are now)
  const on = useRef({ onRemove, onAgain, onAskWhole, onCopy, onQuote, onFold });
  on.current = { onRemove, onAgain, onAskWhole, onCopy, onQuote, onFold };
  useEffect(() => {
    if (!copied) return undefined;
    const t = setTimeout(() => setCopied(""), 1500);
    return () => clearTimeout(t);
  }, [copied]);
  // (over the chat: from under its tabs, which a header that wraps or a task strip moves; placed before it's drawn)
  useLayoutEffect(() => {
    const c = card.current;
    if (!c) return undefined;
    const place = () => {
      c.style.top = wide ? "" : `${Math.round(anchor.current?.getBoundingClientRect().bottom ?? 0)}px`;
    };
    place();
    if (wide) return undefined;
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  });
  // (the box has the focus once it's open)
  useEffect(() => {
    box.current?.focus();
  }, []);
  // At the newest: when it opens, when you ask, and as answers come in while you're at the end
  useLayoutEffect(() => {
    const el = list.current;
    if (el && atEnd.current) el.scrollTop = el.scrollHeight;
  }, [items]);
  useLayoutEffect(() => {
    const el = list.current;
    atEnd.current = true;
    if (el) el.scrollTop = el.scrollHeight;
  }, [asked]);
  useEffect(() => {
    const el = list.current;
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    const watch = new ResizeObserver(() => {
      if (atEnd.current) el.scrollTop = el.scrollHeight;
    });
    watch.observe(el);
    return () => watch.disconnect();
  }, []);
  // (the model's menu: a press outside it, the view losing the focus or a scroll closes it; Esc: ChatApp)
  useEffect(() => {
    if (!pickOpen) return undefined;
    const close = () => setPickOpen(false);
    window.addEventListener("mousedown", close);
    window.addEventListener("blur", close);
    return () => {
      window.removeEventListener("mousedown", close);
      window.removeEventListener("blur", close);
    };
  }, [pickOpen]);

  const ask = () => {
    const q = text.trim();
    if (!q) return;
    onAsk(q);
    setText("");
    draft.current = "";
  };
  const rows = useMemo(() => {
    const now = Date.now();
    return items.map((s) => {
      const state = sideState(s);
      const model = sideModelLabel(s);
      const saw = sideSaw(s);
      return (
        <div key={s.id} class="pane-side-item">
          {/* (on hover, over the question's top right, so nothing moves; held at the list's top while a long one
              goes on below it; Copy and Quote once there's an answer, Ask with the whole chat on one about a part) */}
          <div class="pane-side-acts-at">
            <div class="pane-side-acts">
              {SIDE_ACTIONS.map((a) => a === "copy" ? (state === "answered" ? (
                <button key={a} type="button" class={copied === s.id ? "md-copy copied" : "md-copy"} title={SIDE_COPY}
                  onClick={() => { on.current.onCopy(s); setCopied(s.id); }}>
                  <span class="pane-swap"><span class={copied === s.id ? "off" : ""}>Copy</span><span class={copied === s.id ? "" : "off"} aria-hidden={copied !== s.id}>Copied</span></span>
                </button>
              ) : null) : a === "quote" ? (state === "answered" ? (
                <IconButton key={a} icon={I.quote} label={SIDE_QUOTE} onClick={() => on.current.onQuote(s)} />
              ) : null) : a === "whole" ? (state === "answered" && s.from ? (
                <IconButton key={a} icon={I.refresh} label={SIDE_ASK_WHOLE} onClick={() => on.current.onAskWhole(s)} />
              ) : null) : (
                <IconButton key={a} icon={I.cancel} tone={T.cancel} label={SIDE_REMOVE} onClick={() => on.current.onRemove(s)} />
              ))}
            </div>
          </div>
          <div class="pane-item pane-you first">
            {/* (its ›: a click folds it to its question, or unfolds it; pointing down while it's open) */}
            <button type="button" class="pane-gutter pane-side-fold" aria-expanded={!s.folded} title={s.folded ? SIDE_UNFOLD_TIP : SIDE_FOLD_TIP}
              onClick={() => on.current.onFold(s, !s.folded)}>›</button>
            {s.folded
              ? <div class="pane-body pane-side-folded">{foldedLine(s.q)}</div>
              : <div class="pane-body"><Markdown text={s.q} onCopy={onCopyCode} /></div>}
          </div>
          {s.folded ? null : state === "answered" ? (
            <div class={`pane-item pane-claude close${s.synthetic ? " pane-side-synthetic" : ""}`}>
              <span class="pane-gutter" aria-hidden="true"><span class="pane-dot" /></span>
              <div class="pane-body"><Markdown text={s.a ?? ""} onCopy={onCopyCode} /></div>
            </div>
          ) : state === "pending" ? (
            <div class="pane-item pane-working close" role="status">
              <span class="pane-gutter"><TalpyIcon state="thinking" moving={shown} /></span>
              <span class="grow">{SIDE_PENDING}</span>
            </div>
          ) : (
            <div class="pane-item close pane-side-error">
              <span class="pane-gutter" aria-hidden="true"><Icon name={I.error} /></span>
              <span class="grow">{s.error}</span>
              <button type="button" class="btn secondary small" onClick={() => on.current.onAgain(s)}><Icon name={I.refresh} />{SIDE_AGAIN}</button>
            </div>
          )}
          {s.folded ? null : <div class="pane-side-meta">{timeText(s.at, now)}{model ? ` · ${model}` : ""}{saw ? ` · ${saw}` : ""}</div>}
        </div>
      );
    });
  }, [items, copied, shown]);

  return (
    <div ref={card} class={`pane-side ${wide ? "beside" : "over"}`} style={style} role="complementary" aria-label={SIDE_TITLE}>
      <div class="pane-side-head">
        <Icon name={I.sideQuestions} />
        <strong class="grow">{SIDE_TITLE}</strong>
        {items.length ? (
          <button type="button" class="btn secondary small" aria-expanded={clearAsk} onClick={() => setClearAsk(!clearAsk)}>{SIDE_CLEAR}</button>
        ) : null}
        <IconButton icon={I.close} label={SIDE_CLOSE} title={`${SIDE_CLOSE} (Esc)`} onClick={onClose} />
      </div>
      {clearAsk && items.length ? (
        <div class="confirm">
          <span>{SIDE_CLEAR_ASK}</span>
          <button type="button" class="btn secondary small" onClick={() => { setClearAsk(false); onRemoveAll(); }}>
            <Icon name={I.cancel} tone={T.cancel} />{SIDE_CLEAR}
          </button>
          <button type="button" class="btn secondary small" onClick={() => setClearAsk(false)}>Cancel</button>
        </div>
      ) : null}
      {note ? <div class={note.ok ? "pane-info" : "pane-info bad"}>{note.text}</div> : null}
      <div class="pane-side-list" ref={list}
        onScroll={(e) => { const el = e.currentTarget; atEnd.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40; }}>
        {items.length ? rows : loaded ? <div class="pane-side-empty">{SIDE_EMPTY}</div> : null}
      </div>
      <div class="pane-replybox pane-side-box">
        <span class="pane-prompt" aria-hidden="true">›</span>
        <div class="pane-reply-wrap">
          <textarea class="pane-reply" rows={2} ref={box} placeholder={SIDE_PLACEHOLDER} aria-label={SIDE_PLACEHOLDER} value={text}
            onInput={(e) => {
              const v = (e.target as HTMLTextAreaElement).value;
              setText(v);
              draft.current = v;
            }}
            onKeyDown={(e) => {
              // (Enter asks, as the reply box sends; Shift+Enter: a new line; Esc closes the panel: ChatApp)
              if (e.key === "Enter" && !e.shiftKey && !e.ctrlKey && !e.altKey && !e.metaKey && !e.isComposing) {
                e.preventDefault();
                ask();
              }
            }} />
        </div>
      </div>
      <div class="pane-side-foot">
        <span class="pane-side-pick-at">
          <button type="button" class="pane-side-pick" aria-haspopup="menu" aria-expanded={pickOpen}
            title={SIDE_PICK_TIP}
            onMouseDown={(e) => e.stopPropagation()} onClick={() => setPickOpen(!pickOpen)}>
            {sidePickLabel(pick)}<Icon name={I.unfolded} />
          </button>
          {pickOpen ? (
            <div class="pane-chip-menu pane-side-picks" role="menu" onMouseDown={(e) => e.stopPropagation()}>
              {SIDE_PICKS.map((p) => (
                <button key={p.value} type="button" role="menuitemradio" aria-checked={p.value === pick}
                  onClick={() => { setPickOpen(false); onPick(p.value); box.current?.focus(); }}>
                  <span class="pane-side-check">{p.value === pick ? <Icon name={I.picked} /> : null}</span>{p.label}
                </button>
              ))}
            </div>
          ) : null}
        </span>
        <span class="grow" />
        {line.text && part ? (
          <button type="button" class="pane-side-cost pane-side-from" title={`${line.tip}\n${SIDE_FROM_SHOW}`} onClick={onShowPart}>{line.text}</button>
        ) : line.text ? <span class="pane-side-cost" title={line.tip}>{line.text}</span> : null}
        {part ? <IconButton class="pane-side-whole" icon={I.cancel} tone={T.cancel} label={SIDE_WHOLE} title={SIDE_WHOLE_TIP} onClick={onWhole} /> : null}
      </div>
    </div>
  );
}
