// What Claude made, under the step that made it or the reply that names it (pane.py made.py,
// Plasma's MadeLine.qml: the same words and rules): "icon.svg · 2 KB", folded, on both tabs.
// Unfolded: a picture at the tab's width; a plan rendered; a page never drawn here, Open in
// browser and Show source; another file, Open. What it shows is read only then (the
// extension: pane.py --made, a picture as a data: URL), again at each unfold (the file as it
// is now; a picture Claude read: what it saw, from the transcript)
import { useEffect, useRef, useState } from "preact/hooks";
import { madeAsk, madeLine, type PaneHostMessage, type PaneItem, type PaneMessage } from "../../src/shared/pane";
import { I, Icon } from "../util/icons";
import { Markdown } from "../util/markdown";

type Shown = Extract<PaneHostMessage, { type: "made" }>;

// The answers the extension sends ("made", by id), to the line that asked
const waiting = new Map<number, (m: Shown) => void>();
let lastId = 0;
let listening = false;
function ask(post: (m: PaneMessage) => void, path: string, step: string | undefined, done: (m: Shown) => void): number {
  if (!listening) {
    listening = true;
    window.addEventListener("message", (e: MessageEvent) => {
      const m = e.data as PaneHostMessage | null;
      if (!m || m.type !== "made") return;
      const cb = waiting.get(m.id);
      waiting.delete(m.id);
      cb?.(m);
    });
  }
  const id = ++lastId;
  waiting.set(id, done);
  post({ type: "made", id, path, ...(step ? { step } : {}) });
  return id;
}

const ICONS = { picture: I.madePicture, plan: I.plan, page: I.madePage, file: I.madeFile } as const;

export function MadeLine({ item, open, onToggle, gap, local, post }: {
  item: PaneItem; open: boolean; onToggle: () => void; gap: string; local: boolean; post: (m: PaneMessage) => void;
}) {
  const m = item.made!;
  const what = madeAsk(m);
  const [shown, setShown] = useState<Shown | null>(null);
  const [source, setSource] = useState(false);   // (a page: its source shown)
  const asked = useRef(0);
  // (unfolded: read now, and again at each unfold; a page's source only once asked for)
  const wanted = open && !!what && (m.type !== "page" || source);
  useEffect(() => {
    if (!wanted || !what) return undefined;
    const id = ask(post, what.path, what.step, (r) => {
      if (asked.current === id) setShown(r);
    });
    asked.current = id;
    return () => {
      waiting.delete(id);
      asked.current = 0;
    };
  }, [wanted, m.path, m.step]);
  const openIt = () => post({ type: "openMade", path: m.path });
  const canOpen = local && !m.gone;
  const opens = m.type === "picture" ? "In VS Code's image viewer" : m.type === "plan" ? "In VS Code's editor" : "In the app for it";
  return (
    <div data-key={item.key} class={`pane-item pane-made ${gap}`}>
      <span class="pane-gutter" aria-hidden="true" />
      <div class="pane-body">
        <button type="button" class="pane-made-line" aria-expanded={open} onClick={onToggle}
          title={m.gone ? `${m.path}\nIt isn't there any more` : `${m.path}\n${open ? "Fold it" : "Click to see it"}`}>
          <Icon name={I.folded} class={"chevron" + (open ? " open" : "")} />
          <Icon name={ICONS[m.type] ?? I.madeFile} />
          <span class="pane-made-name">{madeLine(item)}</span>
        </button>
        {open ? (
          <div class="pane-made-shown">
            {m.type === "picture" && shown?.ok && shown.src ? (
              <img class="pane-made-pic" src={shown.src} alt={m.name} decoding="async" onClick={canOpen ? openIt : undefined} />
            ) : null}
            {m.type === "plan" && shown?.ok && typeof shown.text === "string" ? (
              <div class="pane-made-text">
                <Markdown text={shown.text} onCopy={(code) => post({ type: "copy", text: code })} />
                {shown.cut ? <div class="pane-made-cut">…</div> : null}
              </div>
            ) : null}
            {m.type === "page" && source && shown?.ok && typeof shown.text === "string" ? (
              <pre class="pane-made-text pane-made-source">{shown.text + (shown.cut ? "\n…" : "")}</pre>
            ) : null}
            {wanted && !shown ? <div class="pane-made-note">Reading it…</div> : null}
            {shown && !shown.ok ? <div class="pane-made-note">{shown.message}</div> : null}
            {m.gone ? <div class="pane-made-note">It isn't there any more</div> : null}
            {!local && (m.type === "page" || m.type === "file") ? <div class="pane-made-note">On the SSH host: {m.path}</div> : null}
            <div class="pane-made-tools">
              {m.type === "page" && canOpen ? (
                <button type="button" class="btn secondary small" title="Pages aren't drawn in Talpy Chat: in your browser" onClick={openIt}>
                  <Icon name={I.web} />Open in browser
                </button>
              ) : null}
              {m.type === "page" && !m.gone ? (
                <button type="button" class="btn secondary small" aria-pressed={source} onClick={() => setSource((s) => !s)}
                  title={source ? "Hide its HTML" : "Its HTML, as text (its first lines)"}>
                  <Icon name={I.showSource} />{source ? "Hide source" : "Show source"}
                </button>
              ) : null}
              {m.type !== "page" && canOpen ? (
                <button type="button" class="btn secondary small" title={opens} onClick={openIt}>
                  <Icon name={I.openRun} />Open
                </button>
              ) : null}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
