import { createContext } from "preact";
import { useContext } from "preact/hooks";
import type { ViewState } from "../../../core/src/shared/types";

// The latest state from the extension, for the components deep in the list
export const ViewContext = createContext<ViewState | null>(null);

export function useView(): ViewState {
  const view = useContext(ViewContext);
  if (!view) throw new Error("useView outside of the view");
  return view;
}
