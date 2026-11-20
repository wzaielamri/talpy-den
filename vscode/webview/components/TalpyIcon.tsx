import { useEffect, useRef } from "preact/hooks";
import { drawGlyph, glyphMoves } from "../../vendor/talpy/glyph.mjs";
import { cancelBeat, nextBeat } from "../pets/beat";

// Talpy peeking up out of the ground (the widget's panel icon,
// talpy/glyph.mjs), in the state's color. It pops up when a chat needs you,
// glances around while Claude works, smiles when it's your turn and sleeps
// when nothing runs (thinking: a chat's working line): ten pictures a second
// on the page's beat (pets/beat.ts: every third, in step with the pets, one
// frame for both), cheap for hours. Its size is the CSS's (.talpy-icon: 16 px).
export const GLYPH_BEATS = 3;

export function TalpyIcon({ state, moving }: { state: string; moving: boolean }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const draw = () => {
      const px = Math.round((canvas.clientWidth || 16) * (devicePixelRatio || 1));
      if (canvas.width !== px) canvas.width = canvas.height = px;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, px, px);
      ctx.setTransform(px / 24, 0, 0, px / 24, 0, 0);
      drawGlyph(ctx, state, getComputedStyle(canvas).color, Date.now());
    };
    draw();
    // (the theme changed: its colors too)
    const theme = new MutationObserver(draw);
    theme.observe(document.body, { attributes: true, attributeFilter: ["class"] });
    let wish = 0;
    let stopped = false;
    const step = (): void => {
      wish = nextBeat(() => {
        if (stopped) return;
        draw();
        step();
      }, false, GLYPH_BEATS);
    };
    if (moving && glyphMoves(state)) step();
    return () => {
      stopped = true;
      theme.disconnect();
      cancelBeat(wish);
    };
  }, [state, moving]);
  return <canvas class={`talpy-icon ov-${state}`} ref={ref} width={16} height={16} aria-hidden="true" />;
}
