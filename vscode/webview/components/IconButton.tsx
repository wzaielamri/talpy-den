import type { ComponentChildren } from "preact";
import type { Tone } from "../../vendor/icons.mjs";
import { Icon, type IconName } from "../util/icons";

// A toolbar-style button: an icon, its label as tooltip and for screen readers
export function IconButton(props: {
  icon: IconName;
  tone?: Tone; // its icon colored (icons.mjs TONES): T.delete, T.cancel…
  label: string;
  title?: string; // a longer tooltip than the label
  onClick: () => void;
  class?: string;
  children?: ComponentChildren;
  disabled?: boolean; // (greyed out in its place, so every line's buttons stay in the same columns)
  pressed?: boolean; // a toggle that's on (drawn pressed)
}) {
  return (
    <button
      type="button"
      class={"icon-btn" + (props.class ? " " + props.class : "")}
      title={props.title ?? props.label}
      aria-label={props.label}
      disabled={props.disabled}
      aria-pressed={props.pressed}
      onClick={(e) => {
        e.stopPropagation();
        props.onClick();
      }}
    >
      <Icon name={props.icon} tone={props.tone} />
      {props.children}
    </button>
  );
}
