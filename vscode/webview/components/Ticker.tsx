import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { reducedMotion } from "../pets/motion";
import { chatRefOf, hostLabel, type TickerItem, tickerItems, TickerTurns } from "../../src/shared/model";
import type { Group } from "../../src/shared/types";
import { post } from "../env";
import { useStore } from "../util/store";
import { hostVisible, liveViews, pageVisible } from "../util/stores";

// In the big Talpy's box, under the counts: what the working chats do right now, e.g.
// "fix parser ▸ Edit: parser.py +12 −3". A chat's new step shows as it
// comes (at once with live mode, else at each check); with several chats at
// work, one that did something new goes first, and with nothing new they
// take turns. A click opens that chat's tab.
export function Ticker({ groups, shown: tabShown }: { groups: Group[]; shown: boolean }) {
  const live = useStore(liveViews);
  const viewShown = useStore(hostVisible);
  const pageShown = useStore(pageVisible);
  const shown = viewShown && pageShown && tabShown;
  const items = useMemo(() => tickerItems(groups, live), [groups, live]);
  const turns = useRef(new TickerTurns());
  const [item, setItem] = useState<TickerItem | null>(null);

  useEffect(() => setItem(turns.current.update(items, Date.now())), [items]);

  // (the turns only while there's someone to see them)
  useEffect(() => {
    if (!shown || items.length < 2) return undefined;
    const timer = setInterval(() => setItem(turns.current.tick(Date.now())), 500);
    return () => clearInterval(timer);
  }, [shown, items.length > 1]);

  // Another chat's turn fades in. The button itself stays (no key), so one
  // the keyboard is on keeps the focus as the chats take turns
  const box = useRef<HTMLButtonElement>(null);
  const key = item?.key;
  useEffect(() => {
    if (!key || !box.current || !shown || reducedMotion()) return;
    box.current.animate([{ opacity: 0.15, transform: "translateY(3px)" }, { opacity: 1, transform: "none" }], { duration: 220, easing: "ease-out" });
  }, [key]);

  if (!item) return null;
  const several = items.length > 1 || !!item.host;
  return (
    <button
      type="button"
      class="ticker"
      ref={box}
      title={`${item.host ? hostLabel(item.host) + ": " : ""}${item.name}\n${item.text}\n\nClick to open it in a tab.`}
      onClick={() => post({ type: "openPane", chat: chatRefOf(item.session, item.host) })}
    >
      {several ? <span class="ticker-name">{item.host ? `${hostLabel(item.host)}: ` : ""}{item.name}</span> : null}
      <span class="ticker-text">▸ {item.text}</span>
    </button>
  );
}
