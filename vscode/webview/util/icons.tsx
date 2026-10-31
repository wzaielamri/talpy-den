// Small line icons drawn here, after the codicons of the same meaning: the
// webview loads nothing from outside (no codicon font), and currentColor
// makes them follow every theme. Which one stands for what is the widget's
// icon table (icons.mjs, vendored), the same for Plasma and GNOME: the
// components ask for a meaning, I.cancel, never for a shape by its name.

import type { JSX } from "preact";
import { TONES, memoryMeaning, vscode, type Meaning, type Tone } from "../../vendor/icons.mjs";

export type IconName = "refresh" | "stop" | "close" | "share" | "chevron" | "server" | "eye" | "external" | "play" | "back" | "search" | "logout" | "edit" | "send" | "repeat" | "star" | "chat" | "move" | "filter" | "chart" | "shield" | "folder" | "mic" | "attach" | "camera" | "newChat" | "gear" | "task" | "user" | "bookmark" | "note" | "trash" | "more" | "eyeClosed" | "clock" | "starFull" | "warning" | "error" | "window" | "zoomIn" | "zoomOut" | "check" | "checkAll" | "deny" | "globe" | "terminal" | "folderLock" | "plug";

const shapes: Record<IconName, JSX.Element> = {
  repeat: (
    <>
      <path d="M2.75 7.5V6.25a2.5 2.5 0 0 1 2.5-2.5h7.5" />
      <path d="M10.75 1.75l2 2-2 2" />
      <path d="M13.25 8.5v1.25a2.5 2.5 0 0 1-2.5 2.5h-7.5" />
      <path d="M5.25 14.25l-2-2 2-2" />
    </>
  ),
  refresh: (
    <>
      <path d="M13.4 8.6A5.5 5.5 0 1 1 11.6 3.9" />
      <path d="M12.4 1.4v3.2H9.2" />
    </>
  ),
  stop: <rect x="3.75" y="3.75" width="8.5" height="8.5" rx="1.5" fill="currentColor" />,
  close: <path d="M4 4l8 8M12 4l-8 8" />,
  share: (
    <>
      <circle cx="11.75" cy="3.75" r="1.75" />
      <circle cx="4.25" cy="8" r="1.75" />
      <circle cx="11.75" cy="12.25" r="1.75" />
      <path d="M5.8 7.1l4.4-2.5M5.8 8.9l4.4 2.5" />
    </>
  ),
  chevron: <path d="M6 3.5L10.5 8 6 12.5" />,
  play: <path d="M5 3.25v9.5L12.5 8z" fill="currentColor" />,
  back: <path d="M7.5 3.5L3 8l4.5 4.5M3.25 8h9.75" />,
  filter: <path d="M2.5 3.5h11l-4.25 5v4l-2.5 1.25V8.5z" />,
  search: (
    <>
      <circle cx="7" cy="7" r="4.25" />
      <path d="M10.2 10.2l3.3 3.3" />
    </>
  ),
  logout: (
    <>
      <path d="M6.5 2.75H3.75c-.55 0-1 .45-1 1v8.5c0 .55.45 1 1 1H6.5" />
      <path d="M10 5l3 3-3 3M13 8H6.5" />
    </>
  ),
  server: (
    <>
      <rect x="2.25" y="2.25" width="11.5" height="5" rx="1.25" />
      <rect x="2.25" y="8.75" width="11.5" height="5" rx="1.25" />
      <path d="M4.75 4.75h.01M4.75 11.25h.01" stroke-width="1.8" />
    </>
  ),
  eye: (
    <>
      <path d="M1.5 8S3.9 3.5 8 3.5 14.5 8 14.5 8 12.1 12.5 8 12.5 1.5 8 1.5 8z" />
      <circle cx="8" cy="8" r="2" />
    </>
  ),
  edit: (
    <>
      <path d="M10.75 2.75l2.5 2.5-7.5 7.5-3.25 0.75 0.75-3.25z" />
      <path d="M9.25 4.25l2.5 2.5" />
    </>
  ),
  send: <path d="M2.5 8l11-5.5-3.5 11-2.5-4.5zM7.5 9l6-6.5" />,
  move: <path d="M2.5 8h8M7.75 5.25L10.5 8l-2.75 2.75M13.25 3v10" />,
  star: <path d="M8 1.9l1.85 3.8 4.15.6-3 2.93.7 4.13L8 11.4l-3.7 1.96.7-4.13-3-2.93 4.15-.6z" />,
  starFull: <path d="M8 1.9l1.85 3.8 4.15.6-3 2.93.7 4.13L8 11.4l-3.7 1.96.7-4.13-3-2.93 4.15-.6z" fill="currentColor" />,
  // (an eye, struck out: hidden, nothing deleted)
  eyeClosed: (
    <>
      <path d="M1.5 8S3.9 3.5 8 3.5 14.5 8 14.5 8 12.1 12.5 8 12.5 1.5 8 1.5 8z" />
      <circle cx="8" cy="8" r="2" />
      <path d="M2.75 13.25l10.5-10.5" />
    </>
  ),
  window: (
    <>
      <rect x="2.25" y="3" width="11.5" height="10" rx="1.25" />
      <path d="M2.25 5.75h11.5" />
    </>
  ),
  zoomIn: (
    <>
      <circle cx="7" cy="7" r="4.25" />
      <path d="M10.2 10.2l3.3 3.3M5 7h4M7 5v4" />
    </>
  ),
  zoomOut: (
    <>
      <circle cx="7" cy="7" r="4.25" />
      <path d="M10.2 10.2l3.3 3.3M5 7h4" />
    </>
  ),
  check: <path d="M3 8.5l3 3 7-7" />,
  checkAll: <path d="M1.75 8.75l2.75 2.75 6.25-6.5M7.5 11.25l.25.25 6.5-6.75" />,
  // (a circle struck through: no, as Breeze's dialog-cancel)
  deny: (
    <>
      <circle cx="8" cy="8" r="5.5" />
      <path d="M4.1 11.9l7.8-7.8" />
    </>
  ),
  globe: (
    <>
      <circle cx="8" cy="8" r="5.75" />
      <path d="M2.25 8h11.5M8 2.25c-2.1 2.2-2.1 9.3 0 11.5M8 2.25c2.1 2.2 2.1 9.3 0 11.5" />
    </>
  ),
  terminal: (
    <>
      <rect x="1.75" y="2.75" width="12.5" height="10.5" rx="1.25" />
      <path d="M4.5 6.25l2 1.75-2 1.75M8 10.25h3.5" />
    </>
  ),
  folderLock: (
    <>
      <path d="M8 13H3c-.55 0-1-.45-1-1V4c0-.55.45-1 1-1h3.5l1.5 1.75h5c.55 0 1 .45 1 1V8" />
      <rect x="9.5" y="10.25" width="4.5" height="3.5" rx="0.6" />
      <path d="M10.5 10.25v-1a1.25 1.25 0 0 1 2.5 0v1" />
    </>
  ),
  plug: <path d="M6 2.5v3M10 2.5v3M4.25 5.5h7.5v2.25a3.75 3.75 0 0 1-7.5 0zM8 11.5v2.5" />,
  clock: (
    <>
      <circle cx="8" cy="8" r="5.75" />
      <path d="M8 4.75V8l2.25 1.5" />
    </>
  ),
  // (the two that say something is wrong: colored by their class, see styles.css)
  warning: (
    <>
      <path d="M8 2.25l6 10.75H2z" />
      <path d="M8 6.5v3" />
      <path d="M8 11.4v.1" stroke-width="1.6" />
    </>
  ),
  error: (
    <>
      <circle cx="8" cy="8" r="5.75" />
      <path d="M8 4.9v3.6" />
      <path d="M8 10.9v.1" stroke-width="1.6" />
    </>
  ),
  chat: <path d="M2.5 3.75c0-.7.55-1.25 1.25-1.25h8.5c.7 0 1.25.55 1.25 1.25v5.5c0 .7-.55 1.25-1.25 1.25H7l-3 2.75V10.5h-.25c-.7 0-1.25-.55-1.25-1.25z" />,
  // (a bubble with a plus: a new chat, not a new account)
  newChat: (
    <>
      <path d="M2.5 3.75c0-.7.55-1.25 1.25-1.25h8.5c.7 0 1.25.55 1.25 1.25v5.5c0 .7-.55 1.25-1.25 1.25H7l-3 2.75V10.5h-.25c-.7 0-1.25-.55-1.25-1.25z" />
      <path d="M8 4.5v4M6 6.5h4" />
    </>
  ),
  gear: (
    <>
      <path d="M12.72 6.69l1.61.36v1.9l-1.61.36-.46 1.1.88 1.4-1.33 1.33-1.4-.88-1.1.46-.36 1.61h-1.9l-.36-1.61-1.1-.46-1.4.88-1.33-1.33.88-1.4-.46-1.1-1.61-.36v-1.9l1.61-.36.46-1.1-.88-1.4 1.33-1.33 1.4.88 1.1-.46.36-1.61h1.9l.36 1.61 1.1.46 1.4-.88 1.33 1.33-.88 1.4z" />
      <circle cx="8" cy="8" r="2" />
    </>
  ),
  chart: <path d="M2.5 13.5h11M4.5 11V8M8 11V3.5M11.5 11V6" />,
  shield: <path d="M8 1.75l5 2v4c0 3.1-2.15 5.35-5 6.5-2.85-1.15-5-3.4-5-6.5v-4z" />,
  folder: <path d="M2 4c0-.55.45-1 1-1h3.5l1.5 1.75h5c.55 0 1 .45 1 1V12c0 .55-.45 1-1 1H3c-.55 0-1-.45-1-1z" />,
  mic: (
    <>
      <rect x="6" y="1.75" width="4" height="7.5" rx="2" />
      <path d="M3.75 7.5a4.25 4.25 0 0 0 8.5 0M8 11.75v2.5M5.75 14.25h4.5" />
    </>
  ),
  attach: <path d="M11.25 5v5.75a3.25 3.25 0 0 1-6.5 0V4.5a2.25 2.25 0 0 1 4.5 0v5.75a1.125 1.125 0 0 1-2.25 0V6" transform="rotate(45 8 8.1)" />,
  camera: (
    <>
      <path d="M1.75 5.5c0-.7.55-1.25 1.25-1.25h2l1.25-1.75h3.5l1.25 1.75h2c.7 0 1.25.55 1.25 1.25v6.25c0 .7-.55 1.25-1.25 1.25H3c-.7 0-1.25-.55-1.25-1.25z" />
      <circle cx="8" cy="8.5" r="2.5" />
    </>
  ),
  external: (
    <>
      <path d="M9.5 2.5h4v4M13.5 2.5L8 8" />
      <path d="M12 9.5v2.75c0 .7-.55 1.25-1.25 1.25h-7c-.7 0-1.25-.55-1.25-1.25v-7C2.5 4.55 3.05 4 3.75 4H6.5" />
    </>
  ),
  // (a plan: a list with ticks, as Plasma's view-task)
  task: <path d="M2.5 4.25l1.25 1.25 2-2.25M2.5 10.25l1.25 1.25 2-2.25M8 4.5h5.5M8 10.5h5.5" />,
  user: (
    <>
      <circle cx="8" cy="5.25" r="2.75" />
      <path d="M2.75 13.75c0-2.75 2.35-4.5 5.25-4.5s5.25 1.75 5.25 4.5" />
    </>
  ),
  bookmark: <path d="M4.25 2.25h7.5v11.5L8 10.75l-3.75 3z" />,
  note: <path d="M3.25 2.25h6.5l3 3v8.5h-9.5zM9.75 2.25v3h3M5.5 8.25h5M5.5 11h5" />,
  more: <path d="M8 2.5v7M4.75 6.5L8 9.75l3.25-3.25M3 13.25h10" />,
  trash: <path d="M2.75 4.25h10.5M6.25 4.25v-1.5h3.5v1.5M4 4.25l.75 9.25h6.5l.75-9.25M6.75 6.75v4.5M9.25 6.75v4.5" />,
};

// The icon of each meaning (only those VS Code has a button or mark for are
// asked for: tests/test_icons.py)
export const I = vscode as Readonly<Record<Meaning, IconName>>;

// The icons colored where the color says something (icons.mjs TONES: cancel
// and delete red, done and allow green, a star yellow…); undefined: plain
export const T = TONES as Readonly<Partial<Record<Meaning, Tone>>>;

// A memory's icon by its kind, as Plasma's: a note about you, feedback, a
// project, a reference, the account's CLAUDE.md, else a note
export function memoryIcon(type: string): IconName {
  return I[memoryMeaning(type)];
}

export function Icon({ name, class: cls, tone }: { name: IconName; class?: string; tone?: Tone }) {
  const t = tone ?? (name === "warning" ? "neutral" : name === "error" ? "negative" : undefined);
  return (
    <svg
      class={"icon" + (t ? ` tone-${t}` : "") + (cls ? " " + cls : "")}
      viewBox="0 0 16 16"
      width="16"
      height="16"
      fill="none"
      stroke="currentColor"
      stroke-width="1.3"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {shapes[name]}
    </svg>
  );
}
