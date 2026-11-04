// Motion in the list and the numbers (the widget does the same in Plasma):
// a chat's row that moves (it needs you, it finished, a row above it grew)
// slides from where it was to where it is, a new one fades in, and a number
// glides to its new value. Only transform and opacity animate: the
// compositor's work, no layout. Less motion asked for: nothing moves.

import type { RefObject } from "preact";
import { useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";
import { reducedMotion } from "../pets/motion";

const SLIDE: KeyframeAnimationOptions = { duration: 320, easing: "cubic-bezier(0.22, 1, 0.36, 1)" };
const APPEAR: KeyframeAnimationOptions = { duration: 380, easing: "cubic-bezier(0.5, 1, 0.89, 1)" };

// The rows: the container's children with data-flip="their key"; the
// container is their offsetParent (position: relative), so where a row is
// doesn't count what it's sliding by
export function useFlip(ref: RefObject<HTMLElement>): void {
  const spots = useRef<Map<string, number> | null>(null);
  useLayoutEffect(() => {
    const box = ref.current;
    if (!box || !box.offsetParent) return; // (hidden, another tab showing: where they were stays)
    const was = spots.current;
    const now = new Map<string, number>();
    const still = !was || reducedMotion() || document.hidden;
    for (const row of Array.from(box.children) as HTMLElement[]) {
      const key = row.dataset.flip;
      if (!key) continue;
      const y = row.offsetTop;
      now.set(key, y);
      if (still) continue;
      const from = was.get(key);
      if (from === undefined) row.animate([{ opacity: 0, transform: "translateX(-10px)" }, { opacity: 1, transform: "none" }], APPEAR);
      else if (Math.abs(from - y) >= 1) row.animate([{ transform: `translateY(${from - y}px)` }, { transform: "none" }], SLIDE);
    }
    spots.current = now;
  });
}

// A number shown gliding to its new value over ms
export function useGlide(value: number, ms = 600): number {
  const [shown, setShown] = useState(value);
  const at = useRef(value);
  useEffect(() => {
    const from = at.current;
    if (reducedMotion() || document.hidden || Math.abs(value - from) < 0.5) {
      at.current = value;
      setShown(value);
      return;
    }
    const start = performance.now();
    let frame = 0;
    const step = (): void => {
      const t = Math.min(1, (performance.now() - start) / ms);
      at.current = from + (value - from) * (1 - (1 - t) ** 3);
      setShown(at.current);
      if (t < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [value]);
  return shown;
}
