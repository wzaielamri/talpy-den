import { useEffect, useRef, useState } from "preact/hooks";
import { cancelBeat, nextBeat } from "../pets/beat";
import { reducedMotion } from "../pets/motion";
import { GLYPH_BEATS } from "./TalpyIcon";

// How a blinking dot fades: to a quarter and back in 1.2 s, easing in and out
// (the CSS animation it was: pane-blink, ease-in-out; the widget's Beat.fade)
export function blinkOpacity(ms: number): number {
  return 0.625 + 0.375 * Math.cos((2 * Math.PI * ms) / 1200);
}

// Less motion asked for, now: and again whenever the system's setting changes
export function useReducedMotion(): boolean {
  const [still, setStill] = useState(reducedMotion);
  useEffect(() => {
    if (typeof matchMedia !== "function") return undefined;
    const query = matchMedia("(prefers-reduced-motion: reduce)");
    const changed = (): void => setStill(query.matches);
    query.addEventListener?.("change", changed);
    return () => query.removeEventListener?.("change", changed);
  }, []);
  return still;
}

// The ● before a tool call still going (or waiting for your answer): blinking,
// on the page's beat in step with the working Talpy (pets/beat.ts, every third
// beat: one frame for both), not on the compositor's clock, which drew the
// whole page 60 times a second for it. Still with less motion asked for (also
// when that's asked for while it blinks), as the CSS animation's media query
// had it.
export function BlinkDot({ on }: { on: boolean }) {
  const ref = useRef<HTMLSpanElement>(null);
  const still = useReducedMotion();
  useEffect(() => {
    const dot = ref.current;
    if (!dot || !on || still) return undefined;
    const since = performance.now();
    let wish = 0;
    let stopped = false;
    const step = (): void => {
      wish = nextBeat((now) => {
        if (stopped) return;
        dot.style.opacity = blinkOpacity(now - since).toFixed(3);
        step();
      }, false, GLYPH_BEATS);
    };
    step();
    return () => {
      stopped = true;
      cancelBeat(wish);
      dot.style.opacity = "";
    };
  }, [on, still]);
  return <span class="pane-dot" ref={ref} />;
}
