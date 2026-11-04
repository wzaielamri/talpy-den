// The webview's entry: draws the dashboard from what the extension sends.

import { gotRecentMore, setTab } from "./util/ui";
import { render } from "preact";
import type { HostMessage } from "../src/shared/types";
import { App } from "./components/App";
import { gotDeleteAsk } from "./components/DeleteAsk";
import { gotMoveAsk } from "./components/MoveAsk";
import { isDark, post } from "./env";
import { pets } from "./pets";
import { hostVisible, limitsAnswer, liveViews, pageVisible, permsAnswer, projectsAnswer, petColorsVersion, readAgain, viewState, weekAnswer, weekRevokeAnswer, weekRuleAnswer } from "./util/stores";

// Listen before saying "ready": the first state comes right after it
window.addEventListener("message", (event: MessageEvent) => {
  const msg = event.data as HostMessage | null;
  if (!msg || typeof msg !== "object") return;
  switch (msg.type) {
    case "state":
      liveViews.set(msg.state.live ?? {});
      viewState.set(msg.state);
      break;
    case "live":
      liveViews.set(msg.live ?? {});
      break;
    case "petEvent":
      pets.dispatchPetEvent(msg.kind, msg.text, msg.key);
      break;
    case "playWithTalpy":
      pets.play();
      break;
    case "visible":
      hostVisible.set(!!msg.visible);
      break;
    case "showTab":
      setTab(msg.tab);
      break;
    case "readAgain":
      readAgain.set(readAgain.get() + 1);
      break;
    case "week":
      weekAnswer.set(msg);
      break;
    case "limits":
      limitsAnswer.set(msg);
      break;
    case "weekRule":
      weekRuleAnswer.set(msg);
      break;
    case "weekRevoke":
      weekRevokeAnswer.set(msg);
      break;
    case "perms":
      permsAnswer.set(msg);
      break;
    case "recentMore":
      gotRecentMore(msg);
      break;
    case "projects":
      projectsAnswer.set(msg);
      break;
    case "deleteAsk":
      gotDeleteAsk(msg.key, msg.ok, msg.question, msg.message);
      break;
    case "moveAsk":
      gotMoveAsk(msg.key, msg.ok, msg.answer, msg.message);
      break;
  }
});

document.addEventListener("visibilitychange", () => pageVisible.set(document.visibilityState !== "hidden"));
pets.onColorsChanged(() => petColorsVersion.set(petColorsVersion.get() + 1));

function start(): void {
  // VS Code swaps the body's theme class when the theme changes, and its
  // colors (the html element's style) also from one dark theme to another
  pets.setDark(isDark());
  const themed = new MutationObserver(() => pets.setDark(isDark()));
  themed.observe(document.body, { attributes: true, attributeFilter: ["class"] });
  themed.observe(document.documentElement, { attributes: true, attributeFilter: ["style"] });

  const root = document.createElement("div");
  root.id = "root";
  document.body.appendChild(root);
  render(<App />, root);
  post({ type: "ready" });
}

if (document.body) start();
else document.addEventListener("DOMContentLoaded", start, { once: true });
