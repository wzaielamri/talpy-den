// Mounts a pet stage (webview/pets) on an element and keeps it fed: new
// input when it changed, and animations only while someone can see them.

import { useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";
import type { ChatRef, Session } from "../../src/shared/types";
import { post } from "../env";
import type { AccountInput, HeroInput, PetStage, StageCallbacks } from "../pets/api";
import { useStore } from "./store";
import { hostVisible, pageVisible } from "./stores";

// A pet (its name tag, the hero's headline) goes to the chat's own window, its
// terminal or Claude Code panel; only a click on the chat's name opens its tab
// here (as on Plasma)
export const stageCallbacks: StageCallbacks = {
  open(chat: ChatRef) {
    post({ type: "openWindow", chat });
  },
  saveBest(game, meters) {
    post({ type: "gameBest", game, best: meters });
  },
};

export function useViewVisible(): boolean {
  const host = useStore(hostVisible);
  const page = useStore(pageVisible);
  return host && page;
}

export function petFields(key: string, value: unknown): unknown {
  if (key !== "session" || !value || typeof value !== "object") return value;
  const s = value as Session;
  const stopped = s.stopped ? [s.stopped.kind, s.stopped.over, s.stopped.resetsAt] : null; // (a limit that has reset)
  return [s.key, s.chatId, s.sessionId, s.state, s.reason, s.name, s.since, s.context, s.agents?.running ?? 0, s.openCommand ?? "", stopped];
}

// `active`: the stage is open (an account's stage folds away without chats);
// `made`: told of the stage once it's there (null once it's gone)
export function usePetStage(
  create: (el: HTMLElement) => PetStage,
  input: HeroInput | AccountInput,
  active: boolean,
  made?: (stage: PetStage | null) => void,
) {
  const ref = useRef<HTMLDivElement>(null);
  const stage = useRef<PetStage | null>(null);
  const lastInput = useRef("");
  // stages start live; the observer says soon enough if it's off screen
  const [onScreen, setOnScreen] = useState(true);
  const visible = useViewVisible();

  // Layout effects: the stage is there, with its pets, in the first paint
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    stage.current = create(el);
    made?.(stage.current);
    lastInput.current = "";
    const io = new IntersectionObserver((entries) => setOnScreen(entries[entries.length - 1].isIntersecting));
    io.observe(el);
    return () => {
      io.disconnect();
      stage.current?.destroy();
      stage.current = null;
      made?.(null);
    };
  }, []);

  // Every poll brings new objects: only pass on what really changed, and only
  // what the pets show of a chat (the rest of its row, its reply, its agents'
  // trees, its tasks, changes with every poll)
  const json = JSON.stringify(input, petFields);
  useLayoutEffect(() => {
    if (stage.current && json !== lastInput.current) {
      lastInput.current = json;
      stage.current.update(input);
    }
  }, [json]);

  const live = visible && onScreen && active;
  useEffect(() => {
    stage.current?.setLive(live);
  }, [live]);

  return ref;
}
