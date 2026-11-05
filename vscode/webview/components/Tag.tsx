import type { Tone } from "../../vendor/icons.mjs";
import { I, Icon, T, type IconName } from "../util/icons";

// Whether tests ran after a chat's last edit and how they went: its icon
// green or red (icons.mjs TONES), the tag itself plain (model.testsText)
export function TestsTag({ tests }: { tests: { text: string; title: string; ok: boolean | null } }) {
  return tests.ok === null ? <Tag text={tests.text} title={tests.title} />
    : <Tag icon={tests.ok ? I.done : I.failed} tone={tests.ok ? T.done : T.failed} text={tests.text} title={tests.title} />;
}

// Small outlined label next to a chat's name: its profile, "VS Code", …
// (icon: one before its text, as big as the buttons')
export function Tag(props: {
  text: string;
  icon?: IconName;
  tone?: Tone; // its icon colored, not the tag (icons.mjs TONES)
  title?: string;
  active?: boolean; // outlined in the accent color
  warning?: boolean; // outlined and written in the error color
  caution?: boolean; // outlined and written in the warning color (it's close to something: the context to its compaction)
  pressed?: boolean;
  onClick?: () => void;
}) {
  const cls = "tag" + (props.icon ? " with-icon" : "") + (props.active ? " active" : "") + (props.warning ? " warning" : "") + (props.caution ? " caution" : "");
  if (props.onClick)
    return (
      <button type="button" class={cls + " clickable"} title={props.title} aria-pressed={props.pressed} onClick={props.onClick}>
        {props.icon ? <Icon name={props.icon} tone={props.tone} /> : null}
        {props.text}
      </button>
    );
  return (
    <span class={cls} title={props.title}>
      {props.icon ? <Icon name={props.icon} tone={props.tone} /> : null}
      {props.text}
    </span>
  );
}
