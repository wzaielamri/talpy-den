// Talpy Chat's bookmarks (Ctrl+Shift+B, or the ribbon in the tab row; Plasma's BookmarkList.qml: the
// same parts, words and clicks): this chat's, in its order, each as its first words, who wrote it and
// when. Over the list's top right, as the find bar (below it while that's open), or beside the chat
// where the tab is wide enough for both (it covers nothing there, and stays open after a jump). Made
// only while it's open, and outside the list (fixed, placed from the list's box before it's drawn), so
// opening it lays out none of the conversation again. A click goes to one: here, it's in the chat as
// shown; earlier, the chat is read further back first ("Going there…"); too far back for a tab, it's
// copied; × takes the bookmark away.

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "preact/hooks";
import { stateOf, staysOpen, timeText, type Bookmark, type BookmarkState } from "../../src/shared/pane";
import { keyText } from "../../vendor/keys.mjs";
import { I, Icon, T } from "../util/icons";
import { IconButton } from "./IconButton";

// (beside the chat: its column is 860 px wide at most, centred; a gap, then the card's 260 px)
export const BESIDE_MIN = 1428;
const FIRST = 24;   // (made at once: more than the card shows)

export function BookmarkList({ marks, loaded, more, capped, settled, going, current, findOpen, list, mac, onGo, onRemove, onClose }: {
  marks: readonly Bookmark[];
  loaded: ReadonlySet<string>; // the keys the tab shows now
  more: boolean; // Show earlier can read more
  capped: boolean; // the tab shows the most it shows
  settled: Readonly<Record<string, "far" | "gone">>; // what a read for one found
  going: string; // the one read further back for, now
  current: string; // the one gone to last
  findOpen: boolean;
  list: { current: HTMLDivElement | null };
  mac: boolean;
  onGo: (m: Bookmark, state: BookmarkState, stays: boolean) => void;
  onRemove: (m: Bookmark) => void;
  onClose: () => void;
}) {
  const card = useRef<HTMLDivElement>(null);
  const beside = useRef(false);
  const go = useRef(onGo);   // (the entries are made again only when they change, not with each new message)
  go.current = onGo;
  const remove = useRef(onRemove);
  remove.current = onRemove;
  // (placed once it's there, before it's drawn, and again while it's open as the tab or the list
  // changes size: its style set here, so nothing is drawn twice; nothing runs while it's closed)
  useLayoutEffect(() => {
    const el = list.current, c = card.current;
    if (!el || !c) return undefined;
    const place = () => {
      const r = el.getBoundingClientRect();
      const side = window.innerWidth >= BESIDE_MIN;
      const bar = !side && findOpen ? el.querySelector<HTMLElement>(".pane-find") : null;
      const top = bar ? bar.getBoundingClientRect().bottom + 4 : r.top + 2;
      beside.current = side;
      c.classList.toggle("beside", side);
      // (as the find bar: 2 px in from the right of the list's text, clear of its scroll bar)
      const textRight = r.left + el.clientLeft + el.clientWidth - (parseFloat(getComputedStyle(el).paddingRight) || 0);
      c.style.right = side ? "" : `${Math.round(document.documentElement.clientWidth - textRight + 2)}px`;
      c.style.top = `${Math.round(top)}px`;
      c.style.maxHeight = `${Math.max(80, Math.round(r.bottom - top - (side ? 0 : 8)))}px`;
    };
    place();
    const watch = typeof ResizeObserver !== "undefined" ? new ResizeObserver(place) : null;
    watch?.observe(el);
    window.addEventListener("resize", place);
    return () => {
      watch?.disconnect();
      window.removeEventListener("resize", place);
    };
  }, [findOpen]);
  // (a long list: the first ones, as many as the card shows, at once; the rest a frame later)
  const [all, setAll] = useState(marks.length <= FIRST);
  useEffect(() => {
    if (all) return undefined;
    const id = requestAnimationFrame(() => setAll(true));
    return () => cancelAnimationFrame(id);
  }, []);
  const states = marks.map((m) => stateOf(m, loaded, more, capped, settled));
  const entries = useMemo(() => {
    const steps = keyText("bookmarkSteps", "vscode", mac);
    return (all ? marks : marks.slice(0, FIRST)).map((m, i) => {
      const state = states[i];
      const reading = state === "earlier" && going === m.key;
      const tip = state === "here" ? `${m.text}
Go to it (${steps}: the one before / after)`
        : state === "earlier" ? "Further back than what's shown: a click reads more of the chat and goes there"
        : state === "far" ? "Further back than the last 2000 steps Talpy Chat shows: a click copies it"
        : "Not in this chat any more: × removes the bookmark";
      return (
        <div key={m.key} data-mark={m.key} class={`pane-bm ${state}${current === m.key ? " current" : ""}`}>
          <button type="button" class="pane-bm-go" title={tip}
            onClick={() => go.current(m, state, staysOpen(list.current?.clientWidth ?? 0, card.current?.offsetWidth ?? 0, beside.current))}>
            <span class={`pane-bm-who ${m.kind}`} aria-hidden="true" />
            <span class="pane-bm-text">{m.text}</span>
            <span class="pane-bm-when">
              {reading ? "Going there…"
                : state === "far" ? "Too far back"
                : state === "gone" ? "Not in the chat any more"
                : <>{state === "earlier" ? <Icon name={I.earlier} class="pane-bm-up" /> : null}{m.at ? timeText(m.at, Date.now()) : ""}</>}
            </span>
          </button>
          <button type="button" class="pane-bm-x" title="Remove this bookmark" aria-label="Remove this bookmark" onClick={() => remove.current(m)}>
            <Icon name={I.cancel} tone={T.cancel} />
          </button>
        </div>
      );
    });
  }, [marks, states.join(), going, current, mac, all]);
  return (
    <div ref={card} class="pane-bookmarks" role="dialog" aria-label="Bookmarks">
      <div class="pane-bookmarks-head">
        <Icon name={I.bookmarked} />
        <strong>Bookmarks</strong>
        <span class="pane-bookmarks-count">{marks.length}</span>
        <span class="grow" />
        <IconButton icon={I.close} label="Close" title={`Close (${keyText("bookmarks", "vscode", mac)}, Esc)`} onClick={onClose} />
      </div>
      {marks.length ? (
        <div class="pane-bookmarks-list">{entries}</div>
      ) : (
        <div class="pane-bookmarks-empty">
          No bookmarks in this chat yet. Hover a message and click its bookmark, or press {keyText("bookmark", "vscode", mac)}.
        </div>
      )}
    </div>
  );
}
