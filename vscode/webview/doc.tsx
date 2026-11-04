// A plan, a subagent's run or a memory, as Talpy Den's own page (src/doc.ts):
// its Markdown rendered as the chat tab renders replies (util/markdown.tsx:
// made into elements, nothing in it runs or loads; no pictures from the web,
// the page's CSP lets none in), Open as text for its file in the editor
// (a plan's comments and Send Feedback to Claude are there), and Copy on
// its code blocks. Its text comes with the page, then again when the file
// changes.

import { render } from "preact";
import { useEffect, useState } from "preact/hooks";
import { Markdown } from "./util/markdown";

declare global {
  interface Window {
    TALPY_DOC: { text: string; file: string; scale?: number; font?: string };
  }
}

const api = acquireVsCodeApi();
const config = window.TALPY_DOC;
// (the chat tab's text size and font)
const look = { "--pane-scale": String(config.scale ?? 1.15), ...(config.font ? { "--pane-font": config.font } : {}) };

function Doc() {
  const [text, setText] = useState(config.text);
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    const listener = (e: MessageEvent) => {
      const m = e.data as { type?: string; text?: unknown };
      if (m?.type === "doc" && typeof m.text === "string") setText(m.text);
    };
    window.addEventListener("message", listener);
    return () => window.removeEventListener("message", listener);
  }, []);
  useEffect(() => {
    if (!copied) return;
    const t = setTimeout(() => setCopied(false), 1500);
    return () => clearTimeout(t);
  }, [copied]);
  return (
    <div class="pane doc-page" style={look}>
      <div class="pane-head">
        <span class="doc-file" title={config.file}>{config.file}</span>
        <span class="doc-note">{copied ? "Copied" : ""}</span>
        <button type="button" class="btn secondary small" title="Open its file in the editor, to read or change it as text"
          onClick={() => api.postMessage({ type: "openText" })}>
          Open as text
        </button>
      </div>
      <div class="pane-list doc-body">
        <Markdown text={text} onCopy={(code) => (api.postMessage({ type: "copy", text: code }), setCopied(true))} />
      </div>
    </div>
  );
}

render(<Doc />, document.body);
