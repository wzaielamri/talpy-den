// What the extension last sent, and whether anyone can see the view.

import type { DeleteTarget, HostMessage, LiveView, ViewState } from "../../src/shared/types";
import { useEffect, useState } from "preact/hooks";
import { createStore } from "./store";

export const viewState = createStore<ViewState | null>(null);

// What this computer's running chats do now (live mode), by session id: with
// each state, and between states as each step comes (its own message, so a
// step doesn't send the whole state)
export const liveViews = createStore<Record<string, LiveView>>({});

// The extension says when the view is hidden (another view in front, the
// sidebar closed); the page's own visibility covers a minimized window.
export const hostVisible = createStore(true);
export const pageVisible = createStore(document.visibilityState !== "hidden");

// Bumped when a pet's color changes, so the rows repaint their bars
export const petColorsVersion = createStore(0);

// The Recap tab's last answer (the extension runs week.py when the tab asks)
export const weekAnswer = createStore<Extract<HostMessage, { type: "week" }> | null>(null);

// What allowing (or taking back) a rule of the Recap tab's did
export const weekRuleAnswer = createStore<Extract<HostMessage, { type: "weekRule" }> | null>(null);
export const weekRevokeAnswer = createStore<Extract<HostMessage, { type: "weekRevoke" }> | null>(null);
export const permsAnswer = createStore<Extract<HostMessage, { type: "perms" }> | null>(null);
export const projectsAnswer = createStore<Extract<HostMessage, { type: "projects" }> | null>(null);

// One chat's live view: a row re-renders when its own view changes, not at
// every other chat's step
export function useLiveView(sessionId: string, on: boolean): LiveView | undefined {
  const pick = () => (on ? liveViews.get()[sessionId] : undefined);
  const [, bump] = useState(0);
  const current = pick();
  useEffect(() => {
    if (!on) return undefined;
    let last = pick();
    const check = () => {
      const v = pick();
      if (v !== last) {
        last = v;
        bump((n) => n + 1);
      }
    };
    check(); // (it may have changed between this render and subscribing)
    return liveViews.subscribe(check);
  }, [sessionId, on]);
  return current;
}

// The question under a line once its Delete… is clicked, one at a time (as
// Plasma's): busy while the extension looks at what it would delete, then the
// question, or why it can't be deleted (message)
export interface DeleteAsk {
  key: string; // the line's
  what: DeleteTarget;
  busy: boolean;
  question: string;
  message: string;
}
export const deleteAsk = createStore<DeleteAsk | null>(null);
