// The question before a plan moves (as Plasma's MoveAsk.qml): under a plan's
// line once its Move to project… (or Move back) is clicked, or at the top of
// the project card a plan was dropped on. It says where the plan goes (the
// backend's --describe), lets you pick the project (Move to project…),
// offers "Keep this project's new plans there too" when the project names no
// plans folder (its settings.local.json then does, so Claude's chats there
// find the plan by its name), says when git would show it there, and asks
// keep both or replace when a plan of that name is there. Nothing moves
// until Move: Cancel, Esc or a click anywhere else lets it be, and Cancel
// has the keyboard, so Enter never moves it.

import { useEffect, useRef } from "preact/hooks";
import type { MoveAnswer, MoveTarget } from "../../src/shared/types";
import { post } from "../env";
import { I, Icon } from "../util/icons";
import { useStore } from "../util/store";
import { moveAsk } from "../util/stores";

// The line's Move… button (again: the question goes), a pick in its list of
// projects (folder), or a drop on a card: ask the extension where it would go
export function askMove(key: string, target: MoveTarget, pick: boolean): void {
  const was = moveAsk.get();
  if (was?.key === key && !target.folder) {
    moveAsk.set(null);
    return;
  }
  moveAsk.set({ key, target, pick, busy: true, answer: null, message: "", keepThere: was?.key === key ? was.keepThere : true });
  post({ type: "moveDescribe", key, ...target });
}

// (the extension's answer, for the question that asked it if it's still there)
export function gotMoveAsk(key: string, ok: boolean, answer: MoveAnswer | null, message: string): void {
  const a = moveAsk.get();
  if (!a || a.key !== key || !a.busy) return;
  moveAsk.set({ ...a, busy: false, answer: ok ? answer : null, message: ok ? "" : message || "It can't be moved." });
}

export function MoveAsk({ itemKey, li }: { itemKey: string; li?: boolean }) {
  const a = useStore(moveAsk);
  const box = useRef<HTMLDivElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  const open = !!a && a.key === itemKey;
  const ready = open && !a.busy && !!a.answer;
  // (Cancel has the keyboard once it shows; Esc and a click outside let it be)
  useEffect(() => {
    if (ready) cancel.current?.focus();
  }, [ready]);
  useEffect(() => {
    if (!open) return;
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") moveAsk.set(null);
    };
    const press = (e: PointerEvent) => {
      const t = e.target as Element | null;
      if (t?.closest?.(`[data-ask-for="${CSS.escape(itemKey)}"]`)) return; // (its own Move… button: that one toggles it)
      if (box.current && !box.current.contains(t)) moveAsk.set(null);
    };
    document.addEventListener("keydown", key, true);
    document.addEventListener("pointerdown", press, true);
    return () => {
      document.removeEventListener("keydown", key, true);
      document.removeEventListener("pointerdown", press, true);
    };
  }, [open]);
  if (!open) return null;
  const close = () => moveAsk.set(null);
  const r = a.answer;
  const move = (ifExists?: "keep" | "replace") => {
    if (!r) return;
    close();
    post({ type: "movePlan", ...a.target, folder: a.target.back ? undefined : r.project || a.target.folder, keepThere: a.keepThere, ...(ifExists ? { ifExists } : {}) });
  };
  const picked = !!r && (r.back || !!r.project);
  const body = a.busy ? (
    <div class="move-ask small muted" role="status" ref={box}>Looking at where it would go…</div>
  ) : !r ? (
    <div class="delete-ask-no move-ask" ref={box}>
      <span class="error">{a.message}</span>
      <button type="button" class="btn secondary small" onClick={close}>OK</button>
    </div>
  ) : (
    <div class="move-ask" ref={box}>
      <div class="confirm">
        <span>
          {r.back ? `Move “${r.title}” back to ${r.account}?`
            : a.pick ? (
              <>
                Move “{r.title}” to{" "}
                <select
                  class="move-pick"
                  aria-label="The project it goes to"
                  value={r.project}
                  onChange={(e) => {
                    const folder = (e.target as HTMLSelectElement).value;
                    if (folder && folder !== r.project) askMove(a.key, { ...a.target, folder }, true);
                  }}
                >
                  {r.project ? null : <option value="">Pick a project…</option>}
                  {r.choices.map((c) => <option value={c.path}>{c.short}</option>)}
                </select>
              </>
            ) : `Move “${r.title}” to ${r.projectShort}?`}
        </span>
      </div>
      {picked && r.targetShort ? <div class="small muted">It goes to {r.targetShort}.</div> : null}
      {picked && !r.back && !r.setting ? (
        <>
          <label class="move-keep small">
            <input type="checkbox" checked={a.keepThere} onChange={(e) => moveAsk.set({ ...a, keepThere: (e.target as HTMLInputElement).checked })} />
            Keep this project's new plans there too
          </label>
          <div class={"small move-note " + (a.keepThere ? "muted" : "move-warn")}>
            {a.keepThere ? `Adds plansDirectory to ${r.settingsFile}.` : "Without it, Claude's chats there won't find the plan by its name."}
          </div>
        </>
      ) : null}
      {picked && r.git === true ? <div class="small move-warn">It would show up in git there.</div> : null}
      {r.back && r.lost ? <div class="small move-warn">Claude's chats in {r.projectShort} look for plans in its own folder: they won't find it there.</div> : null}
      {r.exists ? (
        <div class="small move-warn">There's another plan called {r.slug} there: keep both (this one becomes {r.free}), or replace it (it goes to the Trash)?</div>
      ) : null}
      <div class="confirm move-buttons">
        {r.exists ? (
          <>
            <button type="button" class="btn secondary small" onClick={() => move("keep")}>
              <Icon name={r.back ? I.moveBack : I.moveToProject} />Keep both
            </button>
            <button type="button" class="btn secondary small" onClick={() => move("replace")}>Replace</button>
          </>
        ) : (
          <button type="button" class="btn secondary small" disabled={!picked} onClick={() => move()}>
            <Icon name={r.back ? I.moveBack : I.moveToProject} />Move
          </button>
        )}
        <button type="button" class="btn secondary small" ref={cancel} onClick={close}>Cancel</button>
      </div>
    </div>
  );
  return li ? <li class="delete-ask-item">{body}</li> : body;
}
