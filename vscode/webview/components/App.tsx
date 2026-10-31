import {
  agentsRunning,
  allGroups,
  countStates,
  firstWaiting,
  headlineText,
  heroMood,
  highUsageText,
  maxFiveHour,
  overallState,
  stateText,
} from "../../src/shared/model";
import { Component, type ComponentChildren } from "preact";
import { useEffect, useRef, useState } from "preact/hooks";
import { editorTab } from "../env";
import { pets } from "../pets";
import { FocusView } from "./FocusView";
import { ProjectsView } from "./ProjectsView";
import type { HeroInput } from "../pets/api";
import { chatRefOf, contextFullText, groupKeyOf } from "../util/chat";
import { useStore } from "../util/store";
import { petColorsVersion, viewState } from "../util/stores";
import { TAB_ORDER, uiState } from "../util/ui";
import { ViewContext } from "./context";
import { GroupSection } from "./GroupSection";
import { Header } from "./Header";
import { HeroStage } from "./HeroStage";
import { HostSection } from "./HostSection";
import { Messages } from "./Messages";
import { PermsView } from "./PermsView";
import { Reading } from "./Reading";
import { WeekView } from "./WeekView";

const appClass = "app" + (editorTab ? " tab" : "");

// A shadow under the sticky top once the list scrolls under it
function useScrolled(): boolean {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 0);
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  return scrolled;
}

// One account's (or host's) section: if drawing it fails, the others still
// show, and it says so instead of the view going blank
class Guarded extends Component<{ what: string; children: ComponentChildren }, { failed: string }> {
  state = { failed: "" };
  componentDidCatch(error: unknown): void {
    this.setState({ failed: error instanceof Error ? error.message : String(error) });
  }
  componentDidUpdate(previous: { children: ComponentChildren }): void {
    if (this.state.failed && previous.children !== this.props.children) this.setState({ failed: "" }); // new data: try again
  }
  render() {
    return this.state.failed ? (
      <div class="msg error" role="alert">
        Couldn't show {this.props.what}: {this.state.failed}
      </div>
    ) : (
      this.props.children
    );
  }
}

// The popup's layout: header and the big Talpy on top (they stay while the
// list scrolls), then this computer's accounts, then each SSH host's.
export function App() {
  const state = useStore(viewState);
  // pets changed color: repaint the bars next to their rows
  useStore(petColorsVersion);
  const scrolled = useScrolled();
  // Playful Talpy on or off: the pets' tricks, props, jokes, cookies and games
  const playful = state?.settings.playful !== false;
  useEffect(() => pets.setPlayful(playful), [playful]);
  const { tab, focus } = useStore(uiState);
  const week = tab === "week";
  const perms = tab === "perms";
  const projectsTab = tab === "projects";
  // A tab slides in from the side it's on (Talpy Den | Projects | Permissions | Recap)
  const lastTab = useRef(tab);
  const tabFrom = useRef(0);
  if (lastTab.current !== tab) {
    tabFrom.current = TAB_ORDER.indexOf(tab) > TAB_ORDER.indexOf(lastTab.current) ? 1 : -1;
    lastTab.current = tab;
  }
  const tabIn = tabFrom.current ? { class: "content tab-in", style: { "--tab-from": `${tabFrom.current * 24}px` } } : { class: "content" };

  if (!state)
    return (
      <div class={appClass}>
        <div class="content">
          <Reading text="Looking for your chats…" />
        </div>
      </div>
    );

  const groups = allGroups(state.status, state.hosts);
  const counts = countStates(groups);
  const overall = overallState(groups, counts);
  const waiting = firstWaiting(groups);
  const hero: HeroInput = {
    mood: heroMood(state, overall, groups),
    headline: headlineText(state, counts, groups.length > 0),
    counts,
    highUsageText: highUsageText(groups),
    contextFullText: contextFullText(groups, (key) => pets.petColor(key)),
    maxFiveHour: maxFiveHour(groups),
    agentsRunning: agentsRunning(groups),
    waiting: waiting ? chatRefOf(waiting.session, waiting.group.host) : null,
    waitingState: waiting ? stateText(waiting.session, Date.now()) : "",
  };
  const local = state.status ? state.status.groups : [];
  // the plan usage bars' label column: one width in every account (the widest
  // window label shown), so their bars line up
  const labelChars = Math.max(2, ...groups.flatMap((g) => (g.limits?.windows ?? []).map((w) => w.label.length)));

  return (
    <ViewContext.Provider value={state}>
      <div class={appClass} style={{ "--usage-label-w": `${labelChars + 0.5}ch` }}>
        <div class={"top" + (scrolled ? " scrolled" : "")}>
          <Header
            overall={overall}
            counts={counts}
            groups={groups}
            hosts={state.hosts}
            answered={!!state.status || groups.length > 0}
            unavailable={!state.status && !!state.errorText}
            heroShown={state.settings.showPet}
          />
          {state.settings.showPet && !week && !perms && !projectsTab ? <HeroStage input={hero} groups={groups} /> : null}
        </div>
        {week ? (
          <main key="week" {...tabIn}>
            <Guarded what="the week">
              <WeekView hosts={state.hosts.filter((h) => h.ok && !!h.result).map((h) => h.name)}
                currency={state.settings.recapCurrency ?? "USD"} />
            </Guarded>
          </main>
        ) : projectsTab ? (
          <main key="projects" {...tabIn}>
            <Guarded what="the projects">
              <ProjectsView />
            </Guarded>
          </main>
        ) : perms ? (
          <main key="perms" {...tabIn}>
            <Guarded what="the permissions">
              <PermsView rules={state.settings.recapRules !== false} />
            </Guarded>
          </main>
        ) : (
        <main key="chats" {...tabIn}>
          <Messages state={state} />
          {!state.status && !state.errorText ? <Reading text="Looking for your chats…" /> : null}
          {focus && state.status ? (
            <Guarded what="the focus view">
              <FocusView groups={groups} />
            </Guarded>
          ) : null}
          {(focus ? [] : local).map((g) => (
            <Guarded key={groupKeyOf(g)} what={g.name}>
              <GroupSection group={g} accounts={local.length} />
            </Guarded>
          ))}
          {/* No account here, but SSH hosts shown: one quiet line where this computer's accounts go */}
          {!focus && state.status && local.length === 0 && state.hosts.length > 0 ? (
            <div class="no-sessions muted">No Claude Code config on this computer</div>
          ) : null}
          {(focus ? [] : state.hosts).map((h) => (
            <Guarded key={h.name} what={h.name}>
              {/* its last answer, also when the last check failed (dimmed): allGroups leaves that one out */}
              <HostSection host={h} groups={(h.result?.groups ?? []).map((g) => ({ ...g, host: h.name }))} />
            </Guarded>
          ))}
          {state.status && groups.length === 0 && state.hosts.length === 0 ? (
            <div class="empty">
              <p class="empty-title">No Claude Code chats yet</p>
              <p>
                Your Claude Code chats show up here once you start <code>claude</code> in a terminal or open
                Claude in VS Code. Talpy Den looks in ~/.claude and ~/.claude-*; other folders go in its settings
                (Extra Config Dirs).
              </p>
              <p class="muted">
                {editorTab
                  ? "Chats on other machines: add SSH hosts with the SSH hosts button above."
                  : "Chats on other machines: add SSH hosts from the view's title bar."}
              </p>
            </div>
          ) : null}
        </main>
        )}
      </div>
    </ViewContext.Provider>
  );
}
