// Under a chat's, a plan's or a memory's line once its Delete… button is
// clicked (askDelete): what goes to the Trash and on which accounts (the
// backend's --describe), with Delete and Cancel; or why it can't be deleted
// (open in a chat, gone, the account's CLAUDE.md). As Plasma's DeleteAsk.qml
// and every other question: the question in orange, its buttons beside it.

import type { DeleteTarget } from "../../src/shared/types";
import { post } from "../env";
import { I, Icon, T } from "../util/icons";
import { deleteAsk } from "../util/stores";
import { useStore } from "../util/store";

// The line's Delete… button: the question under it (again: the question goes)
export function askDelete(key: string, what: DeleteTarget): void {
  if (deleteAsk.get()?.key === key) {
    deleteAsk.set(null);
    return;
  }
  deleteAsk.set({ key, what, busy: true, question: "", message: "" });
  post({ type: "deleteDescribe", key, ...what });
}

// (the extension's answer, for the line that asked it if it still does)
export function gotDeleteAsk(key: string, ok: boolean, question: string, message: string): void {
  const a = deleteAsk.get();
  if (!a || a.key !== key || !a.busy) return; // (cancelled, or another one asked meanwhile)
  deleteAsk.set({ ...a, busy: false, question: ok ? question : "", message: ok ? "" : message || "It can't be deleted." });
}

// li: in a list of lines (a recent chat's, a plan's, a memory's), a line of its own under it
export function DeleteAsk({ itemKey, li }: { itemKey: string; li?: boolean }) {
  const a = useStore(deleteAsk);
  if (!a || a.key !== itemKey) return null;
  const close = () => deleteAsk.set(null);
  const body = a.busy ? (
    <div class="delete-ask small muted" role="status">Looking at what it would delete…</div>
  ) : a.question ? (
    <div class="confirm delete-ask">
      <span>{a.question}</span>
      <button type="button" class="btn secondary small" onClick={() => { close(); post({ type: "delete", ...a.what }); }}>
        <Icon name={I.delete} tone={T.delete} />Delete
      </button>
      <button type="button" class="btn secondary small" onClick={close}>Cancel</button>
    </div>
  ) : (
    <div class="delete-ask delete-ask-no">
      <span class="error">{a.message}</span>
      <button type="button" class="btn secondary small" onClick={close}>OK</button>
    </div>
  );
  return li ? <li class="delete-ask-item">{body}</li> : body;
}
