// The chat tab's page (src/chatPane.ts): a chat's conversation as it goes,
// drawn the way Claude's terminal draws it (a dot before each reply and tool
// call, a tool call's outcome under it, your prompts set off), a box to
// reply, what it asks while it waits for a permission, and its review. It
// shows what the extension sends and says what you clicked.

import { render } from "preact";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "preact/hooks";
import { attachedTag, whereTag, droppedPaths, fileMention, picturesIn, PICTURE_TYPES, routeHint, shownAsk, suggestFor, type Offers, type Suggestion, testsText, TEXT_SCALES, withoutPicture, type Conversation, type PaneChat, type PaneHostMessage, type PaneItem, type PaneMessage, type ReviewAnswer } from "../src/shared/pane";
import { AskBox, askKey } from "./components/AskBox";
import { Diff, Listing, ToolDetail } from "./components/CodeView";
import type { Answers, Decision, Session } from "../src/shared/types";
import { modeHint, modeText } from "../src/shared/model";
import { sharedTagTitle } from "./util/chat";
import { IconButton } from "./components/IconButton";
import { Tag, TestsTag } from "./components/Tag";
import { TalpyIcon } from "./components/TalpyIcon";
import { I, Icon, T } from "./util/icons";
import { Markdown } from "./util/markdown";

declare global {
  interface Window {
    CLAUDE_CHAT: { tab: "chat" | "review"; local: boolean; scale?: number; split?: boolean };
  }
}

const api = acquireVsCodeApi();
const post = (m: PaneMessage) => api.postMessage(m);
const copyCode = (code: string) => post({ type: "copy", text: code });
const config = window.CLAUDE_CHAT;

// Chat (your messages and Claude's replies), Steps (its tool calls too) and
// Review; its screen is in its window (Open its window)
type Tab = "chat" | "steps" | "review";

function plural(n: number, one: string, many = one + "s"): string {
  return `${n} ${n === 1 ? one : many}`;
}

// A tool call: ● Bash  npm test in green, red, or (still going) blinking,
// under it ⎿ what came of it, and an edit's change (its first lines; open,
// all of it); click for what it ran and got (CodeView.tsx)
function ToolLine({ item, open, onToggle, asking, going, gap, split, onSplit }: {
  item: PaneItem; open: boolean; onToggle: () => void; asking: boolean; going: boolean; gap: string; split: boolean; onSplit: (s: boolean) => void;
}) {
  const name = item.name ?? "";
  const line = item.line ?? "";
  const args = name && line.startsWith(name + ": ") ? line.slice(name.length + 2) : "";
  const tone = item.status === "ok" ? "ok" : item.status === "error" ? "error" : asking ? "asking" : going ? "going" : "open";
  const summary = item.summary || (asking ? "Waiting for your answer" : "");
  const diff = item.diff ?? [];
  return (
    <div class={`pane-item pane-tool ${tone} ${gap}`}>
      <button type="button" class="pane-tool-line" aria-expanded={open} title="Click for what it ran and what came back" onClick={onToggle}>
        <span class="pane-gutter" aria-hidden="true">
          <span class="pane-dot" />
        </span>
        <span class="pane-tool-body">
          <span class="pane-tool-call">
            <strong>{args ? name : line}</strong>
            {args ? <span class="pane-tool-args">{args}</span> : null}
          </span>
          {summary ? <span class="pane-tool-summary">⎿&nbsp;&nbsp;{summary}</span> : null}
        </span>
      </button>
      {diff.length ? (
        <div class="pane-tool-diff">
          <Diff lines={diff} path={args} max={open ? 0 : 6} split={split} onSplit={open ? onSplit : undefined} />
        </div>
      ) : null}
      {open && (item.input || item.output) && (!diff.length || item.status === "error") ? <ToolDetail item={item} path={args} /> : null}
    </div>
  );
}

// More room before your prompt (a new turn) than between the steps of a turn
// Its tasks, when it has a task list: a progress bar and "3/7 · what it's on",
// folded; unfolded, the tasks (✓ done, ▸ the one it's on, ○ to do) and its
// subagents with what each does now, the running ones first (made only then)
function TaskStrip({ tasks, agents }: { tasks: NonNullable<PaneChat["tasks"]>; agents: PaneChat["agents"] }) {
  const [open, setOpen] = useState(false);
  const next = tasks.items.find((t) => t.status !== "completed")?.subject ?? "";
  const now = tasks.current || (tasks.done >= tasks.total ? "all done" : `next: ${next}`);
  const tree = open && agents ? [...agents.tree.filter((a) => a.status === "running"), ...agents.tree.filter((a) => a.status !== "running")] : [];
  return (
    <div class="pane-tasks">
      <button type="button" class="pane-tasks-line" aria-expanded={open} onClick={() => setOpen(!open)}
        title={open ? "Fold its tasks" : "Its tasks and subagents"}>
        <Icon name={I.folded} class={"chevron" + (open ? " open" : "")} />
        <span class="pane-tasks-bar" aria-hidden="true">
          <span style={{ width: `${Math.round((tasks.done / Math.max(1, tasks.total)) * 100)}%` }} />
        </span>
        <span class="pane-tasks-now">{tasks.done}/{tasks.total} · {now}</span>
      </button>
      {open ? (
        <ul class="pane-tasks-list">
          {tasks.items.map((t, i) => (
            <li key={i} class={"pane-task " + (t.status === "completed" ? "done" : t.status === "in_progress" ? "now" : "todo")}>
              {(t.status === "completed" ? "✓ " : t.status === "in_progress" ? "▸ " : "○ ") + t.subject}
            </li>
          ))}
          {tree.map((a) => (
            <li key={a.id} class={"pane-agent " + a.status}>
              <span class={`focus-dot st-${a.status === "running" ? "working" : a.status === "done" ? "done" : a.status === "failed" ? "failed" : "stopped"}`} aria-hidden="true" />
              {(a.description || a.type) + (a.status === "running" ? (a.activity ? `: ${a.activity}` : "") : ` · ${a.status}`)}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function gapOf(kind: PaneItem["kind"], prev: PaneItem["kind"] | undefined): string {
  if (!prev) return "first";
  if (kind === "you") return "turn";
  return kind === "tool" && prev === "tool" ? "close" : "";
}

function ChatApp() {
  const [chat, setChat] = useState<PaneChat | null>(null);
  const [items, setItems] = useState<PaneItem[]>([]);
  const [more, setMore] = useState(false);
  const [capped, setCapped] = useState(false); // (Show earlier went as far as a tab goes)
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [loadMissing, setLoadMissing] = useState(false); // (no transcript: it hasn't started yet, or it's gone: a note, not an error)
  const [tab, setTab] = useState<Tab>(config.tab);
  const conversation = tab === "chat" || tab === "steps";
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [text, setText] = useState("");
  const [askHow, setAskHow] = useState(false);
  const [info, setInfo] = useState<{ ok: boolean; message: string } | null>(null);
  const [answering, setAnswering] = useState(0);
  // A message on its way (until its result): no second one meanwhile, so a
  // second Enter doesn't send it twice (the ref: two keys before a redraw)
  const [sending, setSending] = useState(false);
  const sendingNow = useRef(false);
  const [review, setReview] = useState<ReviewAnswer | null>(null);
  const [reviewError, setReviewError] = useState("");
  const [reviewLoading, setReviewLoading] = useState(false);
  const [reviewAsked, setReviewAsked] = useState(0); // (the extension showed the Review tab)
  const [openFiles, setOpenFiles] = useState<Record<string, boolean>>({});
  const [undoAsk, setUndoAsk] = useState("");
  const [commitOpen, setCommitOpen] = useState(false);
  const [commitText, setCommitText] = useState("");
  const [commitEdited, setCommitEdited] = useState(false);
  const [scale, setScale] = useState(config.scale ?? 1.15);
  const [shown, setShown] = useState(true); // (the tab in front: its working Talpy moves only then)
  const list = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  const reply = useRef<HTMLTextAreaElement>(null);

  // Pictures pasted into the reply: saved by the extension (an SSH host's chat
  // gets a copy there once you say so), then named in it as [Image: path]
  const [thumbs, setThumbs] = useState<Record<string, string>>({}); // path -> the picture, to show
  const [offer, setOffer] = useState<{ id: string; mime: string; data: string; url: string; at: number } | null>(null);
  const [saving, setSaving] = useState(0);
  const pending = useRef<Record<string, { at: number; url: string }>>({});
  const pasted = (e: ClipboardEvent) => {
    const items = [...(e.clipboardData?.items ?? [])];
    const file = items.find((i) => i.kind === "file" && i.type.startsWith("image/"))?.getAsFile();
    if (!file || e.clipboardData?.getData("text/plain")) return; // (text pastes as text)
    e.preventDefault();
    if (!PICTURE_TYPES.includes(file.type)) {
      setInfo({ ok: false, message: "Claude takes PNG, JPEG, WebP and GIF pictures" });
      return;
    }
    const at = reply.current?.selectionStart ?? text.length;
    const reader = new FileReader();
    reader.onload = () => {
      const url = String(reader.result);
      const picture = { id: `${Date.now()}-${Math.random().toString(36).slice(2)}`, mime: file.type, data: url.slice(url.indexOf(",") + 1), url, at };
      if (chat?.host) setOffer(picture);
      else savePicture(picture);
    };
    reader.readAsDataURL(file);
  };
  // What the box offers as you type (/ commands and skills, @ files) and ↑ / ↓
  // through your past prompts there (pane.py --complete, asked again after a minute)
  const [offers, setOffers] = useState<Offers | null>(null);
  const offersAt = useRef(0);
  const [cursor, setCursor] = useState(0);
  const [dismissed, setDismissed] = useState("");
  const [offerAt, setOfferAt] = useState(0);
  const historyAt = useRef(-1);
  const historyDraft = useRef("");
  const askOffers = () => {
    if (Date.now() - offersAt.current < 60000) return;
    offersAt.current = Date.now();
    post({ type: "complete" });
  };
  const offered = suggestFor(text.slice(0, cursor), offers, dismissed);
  useEffect(() => {
    if (offered.token && Date.now() - offersAt.current >= 60000) askOffers();
  }, [offered.token]);
  useEffect(() => setOfferAt(0), [offered.token, offered.items.length]);
  const take = (sug: Suggestion) => {
    const next = text.slice(0, offered.start) + sug.insert + text.slice(cursor);
    const at = offered.start + sug.insert.length;
    setText(next);
    setCursor(at);
    requestAnimationFrame(() => reply.current?.setSelectionRange(at, at));
  };
  const historyStep = (step: number): boolean => {
    const list = offers?.history ?? [];
    if (!list.length) return false;
    if (historyAt.current < 0) historyDraft.current = text;
    const next = Math.max(-1, Math.min(list.length - 1, historyAt.current + step));
    if (next === historyAt.current) return true;
    historyAt.current = next;
    const value = next < 0 ? historyDraft.current : list[next];
    setText(value);
    setCursor(value.length);
    requestAnimationFrame(() => reply.current?.setSelectionRange(value.length, value.length));
    return true;
  };

  // The microphone: record, then whisper writes it down on this computer
  const [dictating, setDictating] = useState<"" | "starting" | "recording" | "writing" | "model" | "setup">("");
  const [recordedAt, setRecordedAt] = useState(0);
  const [offerModel, setOfferModel] = useState(""); // (the engine that needs one)
  const [offerSetup, setOfferSetup] = useState(0); // (MB it downloads)
  const [, tickRecording] = useState(0);
  useEffect(() => {
    if (dictating !== "recording") return undefined;
    const t = setInterval(() => tickRecording((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, [dictating]);

  // Dropped on the tab: files from VS Code's Explorer (held Shift) by their
  // paths (a picture goes in as one, a file is named), pictures from
  // elsewhere as pasted ones; the screenshot button: a region you pick
  const [dragging, setDragging] = useState(false);
  const pendingAt = (id: string) => {
    pending.current[id] = { at: reply.current?.selectionStart ?? text.length, url: "" };
    setSaving((n) => n + 1);
  };
  // files by their paths (dropped from the Explorer, or picked with +)
  const attachPaths = (paths: string[]) => {
    for (const path of paths) {
      const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
      pendingAt(id);
      post({ type: "attach", id, path });
    }
  };
  const dropped = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const dt = e.dataTransfer;
    if (!dt) return;
    const paths = droppedPaths(dt.getData("text/uri-list") || dt.getData("application/vnd.code.uri-list"));
    if (paths.length) {
      attachPaths(paths);
      return;
    }
    const files = Array.from(dt.files ?? []);
    const picture = files.find((f) => PICTURE_TYPES.includes(f.type));
    if (!picture) {
      if (files.length) setInfo({ ok: false, message: "Drop files from VS Code's Explorer (hold Shift) to name them; pictures can come from anywhere" });
      return;
    }
    const at = reply.current?.selectionStart ?? text.length;
    const reader = new FileReader();
    reader.onload = () => {
      const url = String(reader.result);
      const p = { id: `${Date.now()}-${Math.random().toString(36).slice(2)}`, mime: picture.type, data: url.slice(url.indexOf(",") + 1), url, at };
      if (chat?.host) setOffer(p);
      else savePicture(p);
    };
    reader.readAsDataURL(picture);
  };
  const screenshot = () => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    pendingAt(id);
    post({ type: "screenshot", id });
  };
  const micText = dictating === "recording" ? `Stop: write it down · ${Math.max(1, Math.round((Date.now() - recordedAt) / 1000))}s`
    : dictating === "starting" ? "Starting the microphone…"
    : dictating === "writing" ? "Writing it down…" : dictating === "model" ? "Downloading the speech model…"
    : dictating === "setup" ? "Setting up dictation (a few minutes)…" : "Dictate";
  const savePicture = (p: { id: string; mime: string; data: string; url: string; at: number }) => {
    pending.current[p.id] = { at: p.at, url: p.url };
    setSaving((n) => n + 1);
    post({ type: "picture", id: p.id, mime: p.mime, data: p.data });
  };

  // Changes side by side or one after the other: talpyDen.diffSideBySide
  const [split, setSplit] = useState(config.split !== false);
  const sideBySide = (next: boolean) => {
    setSplit(next);
    post({ type: "diffLayout", split: next });
  };

  // A− / A+ and Ctrl+wheel: the text size, kept in talpyDen.chatTextScale
  const zoom = (step: number) => {
    const i = TEXT_SCALES.findIndex((v) => v >= scale - 0.001);
    const at = i < 0 ? TEXT_SCALES.length - 1 : i;
    const next = TEXT_SCALES[Math.max(0, Math.min(TEXT_SCALES.length - 1, at + step))];
    setScale(next);
    post({ type: "textSize", scale: next });
  };

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      const m = event.data as PaneHostMessage | null;
      if (!m || typeof m !== "object") return;
      if (m.type === "chat") setChat(m.chat);
      else if (m.type === "textSize") setScale(m.scale);
      else if (m.type === "visible") setShown(m.visible);
      else if (m.type === "diffLayout") setSplit(m.split);
      else if (m.type === "picked") attachPaths(m.paths);
      else if (m.type === "picture") {
        const p = pending.current[m.id];
        delete pending.current[m.id];
        setSaving((n) => Math.max(0, n - 1));
        if (!m.path) {
          if (m.error) setInfo({ ok: false, message: m.error });
        } else if (p) {
          if (p.url) setThumbs((t) => ({ ...t, [m.path]: p.url }));
          setText((t) => {
            const at = Math.min(p.at, t.length);
            return t.slice(0, at) + (at > 0 && t.charAt(at - 1).trim() ? " " : "") + `[Image: ${m.path}] ` + t.slice(at);
          });
          reply.current?.focus();
        }
      }
      else if (m.type === "offers") setOffers(m.offers);
      else if (m.type === "dictation") {
        setDictating(m.state);
        if (m.state === "recording") setRecordedAt(Date.now());
        if (m.offerModel) setOfferModel(m.engine || "whisper");
        if (m.offerSetup) setOfferSetup(m.setupMb || 612);
        if (m.text) {
          const said = m.text;
          const box = reply.current;
          const at = box ? box.selectionStart : Number.MAX_SAFE_INTEGER;
          setText((t) => {
            const i = Math.min(at, t.length);
            return t.slice(0, i) + (i > 0 && t.charAt(i - 1).trim() ? " " : "") + said + " " + t.slice(i);
          });
          box?.focus();
        }
        if (m.message) setInfo({ ok: !!m.ok, message: m.message }); // (set up, downloaded: not an error)
      }
      else if (m.type === "file") {
        const p = pending.current[m.id];
        delete pending.current[m.id];
        setSaving((n) => Math.max(0, n - 1));
        const at = Math.min(p?.at ?? Infinity, Infinity);
        setText((t) => {
          const i = Math.min(at, t.length);
          return t.slice(0, i) + (i > 0 && t.charAt(i - 1).trim() ? " " : "") + `${fileMention(m.path)} ` + t.slice(i);
        });
        reply.current?.focus();
      }
      else if (m.type === "conversation") {
        const a: Conversation = m.answer;
        if (!a.ok) {
          setLoadError(a.message || "Can't read this chat");
          setLoadMissing(!!a.missing);
        }
        else if (!a.unchanged) {
          const el = list.current;
          if (el) follow.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40; // (on another tab: as when you left)
          setLoadError("");
          setItems(a.items ?? []);
          setMore(!!a.more);
          setCapped(!!a.capped);
          setLoaded(true);
        }
      } else if (m.type === "review") {
        setReviewLoading(false);
        setReview(m.answer);
        setReviewError(m.error);
      } else if (m.type === "result") {
        if (m.kind.startsWith("tab:")) {
          showTab(m.kind.slice(4) as Tab);
          if (m.kind === "tab:review") setReviewAsked((n) => n + 1); // (compared again, also when it showed already)
          return;
        }
        if (m.kind === "draft") {
          setText(m.message);
          setAskHow(true);
          return;
        }
        if (m.kind === "answer") setAnswering((n) => Math.max(0, n - 1));
        if (m.kind === "send" || m.kind === "later") {
          sendingNow.current = false;
          setSending(false);
        }
        if (m.kind === "send" && m.ask) {
          setAskHow(true);
          return;
        }
        if ((m.kind === "send" || m.kind === "later") && m.ok) {
          setText("");
          setAskHow(false);
        }
        if (m.kind === "commit" && m.ok) {
          setCommitOpen(false);
          setCommitEdited(false);
        }
        setInfo(m.message ? { ok: m.ok, message: m.message } : null);
      }
    };
    window.addEventListener("message", onMessage);
    post({ type: "ready" });
    return () => window.removeEventListener("message", onMessage);
  }, []);

  useEffect(() => {
    if (!info) return;
    const t = setTimeout(() => setInfo(null), 12000);
    return () => clearTimeout(t);
  }, [info]);

  useEffect(() => {
    if (review && !commitEdited) setCommitText(review.message || "");
  }, [review]);

  // The review: compared when its tab shows (once, however it was opened),
  // and again after a new edit while it shows. (The chat's first news says
  // when it was last edited: no news, the comparison asked for is on its way.)
  const askReview = () => {
    setReviewLoading(true);
    post({ type: "review" });
  };
  useEffect(() => {
    if (tab === "review") askReview();
  }, [tab, reviewAsked]);
  const editedAt = chat ? chat.review?.editedAt ?? 0 : null;
  const lastEdit = useRef(editedAt);
  useEffect(() => {
    const was = lastEdit.current;
    lastEdit.current = editedAt;
    if (tab === "review" && was !== null && editedAt !== was) askReview();
  }, [editedAt]);

  useLayoutEffect(() => {
    const el = list.current;
    if (el && follow.current) el.scrollTop = el.scrollHeight;
  }, [items, chat?.activity]);
  // The list made shorter (a prompt to answer under it, the queued reply,
  // what the reply box offers) or taller: still at its end if it was
  useEffect(() => {
    const el = list.current;
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    const watch = new ResizeObserver(() => {
      if (follow.current) el.scrollTop = el.scrollHeight;
    });
    watch.observe(el);
    return () => watch.disconnect();
  }, [conversation]);
  // Back on the Chat or Steps tab (its list is made again), or from one to
  // the other: at its end, following it, if it was when you left, else on the
  // message that was at its top (Steps has tool calls between them, so the
  // same place in pixels is another part of the chat), else where you were
  const listTop = useRef(0);
  const topItem = useRef<{ key: string; at: number } | null>(null);
  const showTab = (t: Tab) => {
    const el = list.current;
    topItem.current = null;
    if (el) {
      const top = el.getBoundingClientRect().top;
      const it = [...el.querySelectorAll<HTMLElement>("[data-key]")].find((m) => m.getBoundingClientRect().bottom > top);
      if (it) topItem.current = { key: it.dataset.key ?? "", at: it.getBoundingClientRect().top - top };
    }
    setTab(t);
  };
  useLayoutEffect(() => {
    const el = list.current;
    if (!conversation || !el) return;
    const was = topItem.current;
    const it = was && !follow.current ? [...el.querySelectorAll<HTMLElement>("[data-key]")].find((m) => m.dataset.key === was.key) : undefined;
    el.scrollTop = follow.current ? el.scrollHeight
      : it && was ? el.scrollTop + it.getBoundingClientRect().top - el.getBoundingClientRect().top - was.at
      : listTop.current;
  }, [tab]);

  const send = (how: "auto" | "background" | "copy" | "enter", afterTurn: boolean) => {
    if (!text.trim() || sendingNow.current) return;
    sendingNow.current = true;
    setSending(true);
    post({ type: "send", text, how, afterTurn });
  };
  // (to the prompt shown now: if the chat asks something else by then, it isn't answered)
  const answer = (decision: Decision, note: string, answers?: Answers) => {
    setAnswering((n) => n + 1);
    post({ type: "answer", decision, note, answers, shown: shownAsk(chat?.permission) });
  };

  const terminal = chat?.route === "terminal" || askHow;
  const lastIndex = items.length - 1;
  const last = items[lastIndex];
  const activity = (chat?.activity ?? "").replace(/[….\s]+$/, "");
  const sums = (review?.files ?? []).reduce((a, f) => [a[0] + (f.added ?? 0), a[1] + (f.removed ?? 0)], [0, 0]);
  const tests = testsText(chat?.review ?? (review ? { editedAt: review.editedAt, tests: review.tests } : null));
  const marked = !!chat && chat.reviewed && !!chat.review;

  // The conversation, drawn again only when it or how it shows changes: not
  // for each key typed in the reply, a dictation's second or a chat's poll
  // (the Chat tab leaves out its tool calls)
  const asking = !!chat?.permission;
  const going = !!chat?.busy;
  const steps = useMemo(() => items.map((it, i) => {
    const gap = gapOf(it.kind, items[i - 1]?.kind);
    return it.kind === "you" ? (
      <div key={it.key} data-key={it.key} class={`pane-item pane-you ${gap}`}>
        <span class="pane-gutter" aria-hidden="true">›</span>
        <div class="pane-you-text">{it.text}</div>
      </div>
    ) : it.kind === "claude" ? (
      <div key={it.key} data-key={it.key} class={`pane-item pane-claude ${gap}`}>
        <span class="pane-gutter" aria-hidden="true">
          <span class="pane-dot" />
        </span>
        <div class="pane-body">
          <Markdown text={it.text ?? ""} onCopy={copyCode} />
        </div>
      </div>
    ) : it.kind === "tool" ? (tab !== "steps" ? null :
      <ToolLine
        key={it.key}
        item={it}
        gap={gap}
        open={!!open[it.key]}
        asking={asking && i === items.length - 1 && it.status === "open"}
        going={going && it.status === "open"}
        onToggle={() => setOpen((was) => ({ ...was, [it.key]: !was[it.key] }))}
        split={split}
        onSplit={sideBySide}
      />
    ) : (
      <div key={it.key} data-key={it.key} class={`pane-item pane-note${it.error ? " bad" : ""} ${gap}`}>
        <span>{it.text}</span>
      </div>
    );
  }), [items, open, asking, going, split, tab]);

  return (
    <div class="pane pane-grow" style={{ "--pane-scale": String(scale) }}>
      <div class="pane-head">
        <span class={`state-dot st-${chat?.state ?? "done"}`} aria-hidden="true" />
        <h2 class="pane-name">{chat?.name ?? ""}</h2>
        {chat?.host ? <Tag text={chat.host} title={`This chat runs on the SSH host ${chat.host}.`} /> : null}
        <span class={`pane-state st-${chat?.state ?? "done"}`}>{chat?.stateText ?? ""}</span>
        <span class="pane-sizes">
          <IconButton icon={I.zoomOut} label="Smaller text" title="Smaller text (Ctrl+wheel)" disabled={scale <= TEXT_SCALES[0] + 0.001} onClick={() => zoom(-1)} />
          <IconButton icon={I.zoomIn} label="Larger text" title="Larger text (Ctrl+wheel)" disabled={scale >= TEXT_SCALES[TEXT_SCALES.length - 1] - 0.001} onClick={() => zoom(1)} />
        </span>
        {chat?.canMove ? (
          <button
            type="button"
            class="btn secondary small"
            title="Go on with it in a Claude Code panel: Claude quits in its terminal (the terminal stays open) and the chat reopens in a Claude Code panel. Asks first; a chat that's working or waiting for you is stopped only once you say so."
            onClick={() => post({ type: "moveToClaudeCode" })}
          >
            Move to Claude Code
          </button>
        ) : null}
        <IconButton
          icon={I.openWindow}
          label="Open its window"
          title="Open its window: the terminal or Claude Code panel the chat runs in; a chat that isn't open reopens, in a terminal or a Claude Code panel as the switch of Recent chats says."
          onClick={() => post({ type: "openWindow" })}
        />
      </div>
      <div class="pane-folder">
        {chat ? <Tag {...(({ tag, title }) => ({ text: tag, title }))(whereTag(chat.where, chat.terminalApp))} /> : null}
        {chat && chat.where === "background" && attachedTag(chat.attached) ? (
          <Tag {...(({ tag, title }) => ({ text: tag, title }))(attachedTag(chat.attached)!)} />
        ) : null}
        {/* what its row in the list says of it too: shared, its permission mode, its plan, its subagents */}
        {chat?.shared ? (
          <Tag icon={I.share} text={chat.shared.forkOf ? "Shared copy" : "Shared"}
            title={sharedTagTitle({ shared: chat.shared, profile: chat.profile } as Session)} />
        ) : null}
        {chat && modeText(chat.mode) ? (
          <Tag text={modeText(chat.mode)} warning={chat.mode === "bypassPermissions"}
            title={`Permission mode: ${modeText(chat.mode)}\n${modeHint(chat.mode)}`} />
        ) : null}
        {chat?.plan ? (
          <Tag icon={I.plan} text="Plan" title={`${chat.plan.title}\nThe plan this chat made. Click to read it.`} onClick={() => post({ type: "openPlan" })} />
        ) : null}
        {chat?.agents && chat.agents.total > 0 ? (
          <Tag text={`Agents ${chat.agents.done}/${chat.agents.total}`} active={chat.agents.running > 0}
            title={`Subagents\n${chat.agents.done} done, ${chat.agents.running} running, ${chat.agents.stopped} stopped` +
              (chat.agents.failed ? `, ${chat.agents.failed} failed` : "")} />
        ) : null}
        <span class="pane-path">{(chat?.host ? chat.host + ":" : "") + (chat?.cwd ?? "")}</span>
      </div>
      {chat?.tasks ? <TaskStrip key={chat.chatId} tasks={chat.tasks} agents={chat.agents} /> : null}
      <div class="pane-tabs" role="tablist">
        {(["chat", "steps"] as const).map((t) => (
          <button key={t} type="button" role="tab" aria-selected={tab === t} class={tab === t ? "on" : ""} onClick={() => showTab(t)}>
            {t === "chat" ? "Chat" : "Steps"}
          </button>
        ))}
        <button type="button" role="tab" aria-selected={tab === "review"} class={tab === "review" ? "on" : ""} onClick={() => showTab("review")}>
          {chat?.changes ? `Review ±${chat.changes}${chat.reviewPending ? " •" : ""}` : "Review"}
        </button>
      </div>
      {info ? <div class={info.ok ? "pane-info" : "pane-info bad"}>{info.message}</div> : null}

      {conversation ? (
        <>
          <div
            class="pane-list"
            ref={list}
            onScroll={(e) => {
              const el = e.currentTarget;
              listTop.current = el.scrollTop;
              follow.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
            }}
            onWheel={(e) => {
              if (!e.ctrlKey) return;
              e.preventDefault();
              zoom(e.deltaY < 0 ? 1 : -1);
            }}
          >
            {more ? (
              <button type="button" class="btn secondary small pane-more" onClick={() => post({ type: "more" })}>
                Show earlier
              </button>
            ) : capped ? (
              <div class="muted center small">Only its last 2000 steps are shown here.</div>
            ) : null}
            {!loaded || loadError ? <div class={`muted center${loadError && !loadMissing ? " bad" : ""}`}>{loadError || "Reading the chat…"}</div> : null}
            {steps}
            {chat?.state === "working" ? (
              <div class="pane-item pane-working">
                <span class="pane-gutter">
                  <TalpyIcon state="thinking" moving={shown} />
                </span>
                <span>{activity && !(tab === "steps" && last?.kind === "tool" && last.status === "open") ? activity : "Working"}…</span>
              </div>
            ) : null}
          </div>
          {chat?.permission ? <AskBox key={askKey(chat.permission)} ask={chat.permission} onAnswer={answer} busy={answering > 0} /> : null}
          {chat?.queued ? (
            <div class="pane-queued">
              <span>Sent when this turn ends: {chat.queued.prompt}{chat.queued.error ? ` (${chat.queued.error})` : ""}</span>
              <button type="button" class="btn secondary small" onClick={() => post({ type: "unqueue" })}>Cancel</button>
            </div>
          ) : null}
          {offered.items.length ? (
            <ul class="pane-offers" role="listbox">
              {offered.items.map((o, i) => (
                <li key={o.text} role="option" aria-selected={i === offerAt} class={i === offerAt ? "on" : ""}
                  onMouseDown={(e) => { e.preventDefault(); take(o); }}>
                  <code>{o.text}</code>
                  {o.about ? <span class="muted">{o.about}</span> : null}
                </li>
              ))}
            </ul>
          ) : null}
          <div class={"pane-replybox" + (dragging ? " dropping" : "")}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={dropped}>
          <span class="pane-prompt" aria-hidden="true">›</span>
          <textarea
            class="pane-reply"
            rows={3}
            ref={reply}
            placeholder={chat?.permission ? "It's asking you something: answer that first" : "Reply to Claude… (Enter sends, Shift+Enter: new line; Ctrl+V or drop with Shift: a picture or a file too)"}
            value={text}
            onInput={(e) => {
              const box = e.target as HTMLTextAreaElement;
              setText(box.value);
              setCursor(box.selectionStart);
              historyAt.current = -1;
            }}
            onSelect={(e) => setCursor((e.target as HTMLTextAreaElement).selectionStart)}
            onFocus={askOffers}
            onPaste={pasted}
            onKeyDown={(e) => {
              const box = e.target as HTMLTextAreaElement;
              if (offered.items.length) {
                if (e.key === "ArrowDown" || e.key === "ArrowUp") {
                  e.preventDefault();
                  const n = offered.items.length;
                  setOfferAt((i) => (i + (e.key === "ArrowDown" ? 1 : n - 1)) % n);
                  return;
                }
                if (e.key === "Tab" || (e.key === "Enter" && !e.shiftKey && !e.isComposing)) {
                  e.preventDefault();
                  take(offered.items[Math.min(offerAt, offered.items.length - 1)]);
                  return;
                }
                if (e.key === "Escape") {
                  e.preventDefault();
                  setDismissed(offered.token);
                  return;
                }
              }
              const firstLine = box.value.lastIndexOf("\n", box.selectionStart - 1) < 0;
              const lastLine = box.value.indexOf("\n", box.selectionStart) < 0;
              if (!e.shiftKey && !e.altKey && !e.ctrlKey && !e.metaKey
                  && ((e.key === "ArrowUp" && firstLine && (box.value === "" || historyAt.current >= 0))
                      || (e.key === "ArrowDown" && lastLine && historyAt.current >= 0))
                  && historyStep(e.key === "ArrowUp" ? 1 : -1)) {
                e.preventDefault();
                return;
              }
              // Enter sends, as in Claude's own prompt (Shift+Enter: a new line). For a
              // terminal that takes no text from outside, Enter copies it and opens its
              // terminal: Claude there never quits on an Enter.
              if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
                e.preventDefault();
                send("enter", false);
              }
            }}
          />
          </div>
          {picturesIn(text).length ? (
            <div class="pane-pictures">
              {picturesIn(text).map((path) => (
                <span key={path} class="pane-picture" title={`A picture for Claude\n${chat?.host ? `${path}, on ${chat.host}` : path}`}>
                  {thumbs[path] ? <img src={thumbs[path]} alt="" /> : <span class="pane-picture-name">{path.split("/").pop()}</span>}
                  <button type="button" class="pane-picture-x" title="Take it out of your reply" onClick={() => setText((t) => withoutPicture(t, path))}>
                    ×
                  </button>
                </span>
              ))}
            </div>
          ) : null}
          {offer ? (
            <div class="confirm pane-offer">
              <img src={offer.url} alt="" />
              <span>Copy this picture to {chat?.host}? Claude there can only open it there.</span>
              <button type="button" class="btn small" onClick={() => { savePicture(offer); setOffer(null); }}>Copy</button>
              <button type="button" class="btn secondary small" onClick={() => setOffer(null)}>Cancel</button>
            </div>
          ) : null}
          {saving ? <div class="pane-hint">{chat?.host ? `Copying the picture to ${chat.host}…` : "Adding it to your reply…"}</div> : null}
          {offerSetup ? (
            <div class="pane-hint ask-buttons">
              <span>Set up dictation? It installs faster-whisper, speech to text that runs on this computer, and its base speech model: about {offerSetup} MB from pypi.org and huggingface.co into ~/.local/share/talpy-den/whisper, no sudo needed; a few minutes. What you say never leaves the computer. Other models: Talpy Den: Dictation Models.</span>
              <button type="button" class="btn" onClick={() => { setOfferSetup(0); post({ type: "dictate", action: "setup" }); }}>Set up</button>
              <button type="button" class="btn secondary" onClick={() => setOfferSetup(0)}>Not now</button>
            </div>
          ) : null}
          {offerModel ? (
            <div class="pane-hint ask-buttons">
              <span>To dictate, {offerModel} needs a speech model: download its base model (142 MB) from huggingface.co? It's kept in ~/.local/share/talpy-den/whisper; what you say never leaves the computer. Other models: Talpy Den: Dictation Models.</span>
              <button type="button" class="btn" onClick={() => { setOfferModel(""); post({ type: "dictate", action: "getModel" }); }}>Download</button>
              <button type="button" class="btn secondary" onClick={() => setOfferModel("")}>Not now</button>
            </div>
          ) : null}
          <div class="pane-hint">{chat ? routeHint(chat.route, chat.state !== "done" || !!chat.busy, chat.where === "background" ? "bg" : "", chat.host) : ""}</div>
          <div class="pane-buttons">
            {/* (icons, as in the widget; what dictation is doing shows beside the microphone) */}
            <button type="button" class={"icon-btn pane-mic" + (dictating === "recording" ? " on" : "")}
              disabled={dictating === "starting" || dictating === "writing" || dictating === "model" || dictating === "setup"}
              title="Dictate: say your reply, click again to stop, and it's written down where you're typing. On this computer only (whisper): what you say doesn't leave it. The speech model: Talpy Den: Dictation Models."
              aria-label={micText}
              onClick={() => {
                if (dictating === "") setDictating("starting"); // (until it records, or says why not: no second recorder)
                post({ type: "dictate", action: "toggle" });
              }}>
              <Icon name={dictating === "recording" ? I.stop : I.dictate} />
              {dictating === "" || dictating === "starting" ? null : <span>{micText}</span>}
            </button>
            {dictating === "recording" ? (
              <IconButton icon={I.cancel} tone={T.cancel} label="Stop, don't write it down" onClick={() => post({ type: "dictate", action: "cancel" })} />
            ) : null}
            <IconButton icon={I.attach} class="pane-attach" label="Attach files…"
              title={chat?.host ? `Attach pictures (copied to ${chat.host})` : "Attach files: a picture goes in as one, another file is named for Claude to read. You can drop them on the tab too (hold Shift from the Explorer)."}
              onClick={() => post({ type: "pickFiles" })} />
            <IconButton icon={I.screenshot} class="pane-shot" label="Screenshot…" title="Screenshot: pick a region of the screen, its picture goes in your reply"
              onClick={screenshot} />
            {terminal ? (
              <button type="button" class="btn secondary" disabled={!text.trim() || sending} onClick={() => send("copy", false)}>
                Copy and open its terminal
              </button>
            ) : null}
            {chat?.busy ? (
              <button
                type="button"
                class="btn secondary"
                disabled={!text.trim() || sending}
                title="Kept, and sent once Claude's turn is over."
                onClick={() => send(terminal ? "background" : "auto", true)}
              >
                Send when this turn ends
              </button>
            ) : null}
            <button
              type="button"
              class="btn"
              disabled={!text.trim() || sending || (terminal && !!chat?.busy) || (!!chat?.permission && chat.route === "tmux")}
              onClick={() => send(terminal ? "background" : "auto", false)}
            >
              {sending ? "Sending…" : terminal ? "Send, go on in the background" : "Send"}
            </button>
          </div>
        </>
      ) : (
        <>
          <div class="pane-list">
            {!review ? (
              <div class={`muted${reviewError ? " bad" : ""}`}>
                {reviewLoading ? "Comparing its files with how they were before the chat…" : reviewError || "Nothing to review yet"}
              </div>
            ) : review.files.length === 0 ? (
              <div class="muted">No changed files: they're as they were before this chat.</div>
            ) : (
              <>
                <div class="review-head">
                  <strong>
                    {plural(review.files.length, "file")} changed since the chat started +{sums[0]} −{sums[1]}
                  </strong>
                  {tests ? <TestsTag tests={tests} /> : null}
                  <button type="button" class={`btn secondary small${split ? " on" : ""}`} aria-pressed={split}
                    title="Each change as before | after where the tab is wide enough; else removed and added lines one after the other"
                    onClick={() => sideBySide(!split)}>
                    Side by side
                  </button>
                </div>
                {review.files.map((f) => (
                  <div key={f.path} class="review-file">
                    <div class="review-line">
                      <button type="button" class="pane-tool-line" aria-expanded={!!openFiles[f.path]} onClick={() => setOpenFiles({ ...openFiles, [f.path]: !openFiles[f.path] })}>
                        <Icon name={I.folded} class={"pane-fold" + (openFiles[f.path] ? " open" : "")} />
                        <span class="pane-tool-text mono">
                          {f.label}
                          {f.created ? " (new)" : ""}
                          {f.deleted ? " (removed)" : ""}
                        </span>
                      </button>
                      {f.added !== null ? <span class="add mono">+{f.added}</span> : null}
                      {f.removed !== null ? <span class="del mono">−{f.removed}</span> : null}
                      {f.binary || f.unknown ? <span class="muted small">{f.binary ? "binary" : "no earlier version kept"}</span> : null}
                      {config.local ? (
                        <button type="button" class="btn secondary small" title="In VS Code's diff editor" onClick={() => post({ type: "diff", path: f.path })}>
                          Diff
                        </button>
                      ) : null}
                      {!f.unknown ? (
                        <button type="button" class="btn secondary small" title="Asks first. Puts it back as it was before this chat." onClick={() => setUndoAsk(f.path)}>
                          Undo
                        </button>
                      ) : null}
                    </div>
                    {undoAsk === f.path ? (
                      <div class="confirm">
                        <span>{f.created ? `Delete ${f.label} for good? The chat made it; what you changed in it since is lost too.` : `Put ${f.label} back as it was before this chat? Later changes to it are lost too.`}</span>
                        <button type="button" class="btn small" onClick={() => { setUndoAsk(""); post({ type: "undo", path: f.path }); }}>Undo</button>
                        <button type="button" class="btn secondary small" onClick={() => setUndoAsk("")}>Cancel</button>
                      </div>
                    ) : null}
                    {openFiles[f.path] && f.diff.length ? <Diff lines={f.diff} path={f.path} split={split} onSplit={sideBySide} /> : null}
                    {openFiles[f.path] && !f.diff.length && f.unknown && f.now?.length ? (
                      <>
                        <div class="muted small">No earlier version was kept, so this is how it is now:</div>
                        <Listing lines={f.now} path={f.path} />
                      </>
                    ) : null}
                  </div>
                ))}
              </>
            )}
          </div>
          {/* (above the buttons that open them, not at the end of a list that may scroll) */}
          {commitOpen && review ? (
            <div class="commit-box">
              <div>
                {review.repos.length
                  ? `Commit only these files in ${review.repos.join(", ")} (yours that aren't this chat's stay as they are):`
                  : "None of these files is in a git repository."}
              </div>
              <textarea
                class="pane-reply mono"
                rows={6}
                value={commitText}
                onInput={(e) => {
                  setCommitText((e.target as HTMLTextAreaElement).value);
                  setCommitEdited(true);
                }}
              />
              <div class="pane-buttons">
                <button type="button" class="btn secondary" onClick={() => setCommitOpen(false)}>Cancel</button>
                <button type="button" class="btn" disabled={!commitText.trim() || !review.repos.length} onClick={() => post({ type: "commit", message: commitText })}>
                  Commit
                </button>
              </div>
            </div>
          ) : null}
          {undoAsk === "*" ? (
            <div class="confirm">
              <span>Put all of them back as they were before this chat? Files it made are deleted for good; later changes to them are lost too.</span>
              <button type="button" class="btn small" onClick={() => { setUndoAsk(""); post({ type: "undo", path: "*" }); }}>Undo all</button>
              <button type="button" class="btn secondary small" onClick={() => setUndoAsk("")}>Cancel</button>
            </div>
          ) : null}
          <div class="pane-buttons">
            <button type="button" class="btn secondary" onClick={() => { setReviewLoading(true); post({ type: "review" }); }}>Compare again</button>
            <span class="spacer" />
            <button type="button" class="btn secondary" disabled={!review?.files.length} onClick={() => setUndoAsk("*")}>Undo all…</button>
            <button type="button" class="btn secondary" disabled={!review?.files.length || !review.repos.length} onClick={() => setCommitOpen(!commitOpen)}>
              Commit these files…
            </button>
            <button
              type="button"
              class="btn"
              title={marked ? "Click to mark it not reviewed." : "Its row stops saying “to review”, until it changes files again."}
              onClick={() => post({ type: "reviewed", on: !marked })}
            >
              {marked ? <Icon name={I.reviewed} tone={T.reviewed} /> : <Icon name={I.markReviewed} />}
              {marked ? "Reviewed" : "Mark reviewed"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function start(): void {
  const root = document.createElement("div");
  root.id = "root";
  document.body.appendChild(root);
  render(<ChatApp />, root);
}

if (document.body) start();
else document.addEventListener("DOMContentLoaded", start, { once: true });
