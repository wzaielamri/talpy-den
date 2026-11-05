// Talpy Chat's keys, in Plasma (ChatPane.qml) and VS Code (its chat tab): one
// table for the ? list (KeysHelp.qml, chat.tsx KeysHelp) and the tooltips that
// name a key. Where Claude's terminal has a key for the same thing, it's that
// one. plasma / vscode: the key there ("": none; VS Code: the default of its
// talpyDen.chat.* command, which anyone can change in Keyboard Shortcuts; on a
// Mac, Cmd for Ctrl); commands: [command, its default keybinding] (package.json
// has them, a test checks it). No translations: Plasma reads the words through
// its own i18n, by id (KeysHelp.qml).

export const KEY_GROUPS = ["Sending", "Answering", "Reading", "Moving around", "Help"];

const VS = "talpyDen.chat.";

export const KEYS = [
    { id: "send", group: "Sending", plasma: "Enter", vscode: "Enter", what: "Send (Shift+Enter: a new line)" },
    { id: "sendNow", group: "Sending", plasma: "Ctrl+Enter", vscode: "Ctrl+Enter", commands: [[VS + "sendNow", "ctrl+enter"]],
      what: "Send now: while Claude works, it goes without the 5 s wait (in an empty box: the message waiting)" },
    { id: "sendLater", group: "Sending", plasma: "Alt+Enter", vscode: "Alt+Enter", commands: [[VS + "sendWhenTurnEnds", "alt+enter"]],
      what: "Send when this turn ends" },
    { id: "sendBackground", group: "Sending", plasma: "Ctrl+Shift+Enter", vscode: "Ctrl+Shift+Enter",
      commands: [[VS + "sendInBackground", "ctrl+shift+enter"]],
      what: "Send, go on in the background (a terminal that takes no text)" },
    { id: "clear", group: "Sending", plasma: "Ctrl+L", vscode: "Ctrl+L", commands: [[VS + "clear", "ctrl+l"]],
      what: "Clear the box (Ctrl+Z brings it back)" },
    { id: "history", group: "Sending", plasma: "↑ / ↓", vscode: "↑ / ↓",
      what: "Your earlier messages (↑ in an empty box: a waiting one back first)" },
    { id: "complete", group: "Sending", plasma: "Tab or →", vscode: "Tab or →", what: "The grey rest of your usual reply" },
    { id: "offers", group: "Sending", plasma: "↑ ↓ Tab Enter", vscode: "↑ ↓ Tab Enter", what: "In the / and @ list: move, take one" },
    { id: "paste", group: "Sending", plasma: "Ctrl+V", vscode: "Ctrl+V", what: "A picture from the clipboard" },

    { id: "chips", group: "Answering", plasma: "Alt+1 … Alt+4", vscode: "Alt+1 … Alt+4",
      commands: [1, 2, 3, 4].map((n) => [VS + "reply" + n, "alt+" + n]),
      what: "A suggested reply (with Shift: in the box first)" },
    { id: "allow", group: "Answering", plasma: "Alt+Y", vscode: "Alt+Y", commands: [[VS + "allow", "alt+y"]],
      what: "Allow once (a plan: Approve)" },
    { id: "always", group: "Answering", plasma: "Alt+A", vscode: "Alt+A", commands: [[VS + "alwaysAllow", "alt+a"]],
      what: "Always allow (a plan: Approve, accept edits)" },
    { id: "deny", group: "Answering", plasma: "Alt+N", vscode: "Alt+N", commands: [[VS + "deny", "alt+n"]],
      what: "Deny…, with a note (a plan: Keep planning…; questions: Decline…)" },

    { id: "page", group: "Reading", plasma: "PageUp / PageDown", vscode: "PageUp / PageDown", what: "Scroll a page, from the box too" },
    { id: "prompts", group: "Reading", plasma: "Ctrl+↑ / Ctrl+↓", vscode: "Ctrl+↑ / Ctrl+↓",
      commands: [[VS + "previousPrompt", "ctrl+up"], [VS + "nextPrompt", "ctrl+down"]],
      what: "Your previous / next message (past the last: the end)" },
    { id: "tabs", group: "Reading", plasma: "Ctrl+1 / Ctrl+2 / Ctrl+3", vscode: "Ctrl+1 / Ctrl+2 / Ctrl+3",
      commands: [[VS + "showChat", "ctrl+1"], [VS + "showSteps", "ctrl+2"], [VS + "showReview", "ctrl+3"]],
      what: "The Chat, Steps and Review tabs" },
    { id: "tasks", group: "Reading", plasma: "Ctrl+T", vscode: "Ctrl+T", commands: [[VS + "toggleTasks", "ctrl+t"]],
      what: "Show or hide the chat's tasks" },
    { id: "copyLast", group: "Reading", plasma: "Ctrl+Shift+C", vscode: "Ctrl+Shift+C", commands: [[VS + "copyLastReply", "ctrl+shift+c"]],
      what: "Copy Claude's last reply, as Markdown" },
    { id: "copy", group: "Reading", plasma: "Ctrl+C", vscode: "Ctrl+C", what: "Copy what you selected" },
    { id: "zoom", group: "Reading", plasma: "Ctrl+= / Ctrl+- / Ctrl+0", vscode: "Ctrl+wheel", what: "Text size" },

    { id: "chats", group: "Moving around", plasma: "Ctrl+Tab / Ctrl+Shift+Tab", vscode: "",
      what: "Your other Talpy Chat windows, the last one first" },
    { id: "openWindow", group: "Moving around", plasma: "Ctrl+Shift+O", vscode: "Ctrl+Shift+O", commands: [[VS + "openWindow", "ctrl+shift+o"]],
      what: "Open its window (a background chat: in a terminal)" },
    { id: "close", group: "Moving around", plasma: "Ctrl+W", vscode: "Ctrl+W", what: "Close it" },
    { id: "needsYou", group: "Moving around", plasma: "", vscode: "Ctrl+Alt+Shift+Q",
      commands: [["talpyDen.talpyChatNeedsYou", "ctrl+alt+shift+q"]],
      what: "Talpy Chat with the chat that needs you, from anywhere (again: the next one)" },

    { id: "help", group: "Help", plasma: "?", vscode: "?", what: "These keys (in an empty box)" },
    { id: "escape", group: "Help", plasma: "Esc", vscode: "Esc",
      what: "Closes what's open first: a menu, the big picture, the / and @ list, these keys, the grey completion; then, in an empty box while Claude works, Stop" },
];

export function keyOf(id) {
    return KEYS.find((k) => k.id === id) || null;
}

// The key of id in where ("plasma" | "vscode"); a Mac's VS Code: Cmd for Ctrl
export function keyText(id, where, mac = false) {
    const k = keyOf(id);
    const text = k ? k[where] || "" : "";
    return mac && where === "vscode" ? text.replace(/Ctrl\+/g, "Cmd+") : text;
}

// A tooltip that names its key: "Send now (Ctrl+Enter)"
export function withKey(title, id, where, mac = false) {
    const key = keyText(id, where, mac);
    return key ? `${title} (${key})` : title;
}

// Esc does the nearest thing first, one thing a press: what's open closes, in
// this order; only then, in an empty box while Stop shows (and isn't already
// on its way), it stops Claude. open: {menu, big, list, find, help, ghost,
// stop}, each true when there's that to close (stop: Stop can be pressed now)
export const ESC_ORDER = ["menu", "big", "list", "find", "help", "ghost", "stop"];
export function escTarget(open) {
    return ESC_ORDER.find((what) => !!(open && open[what])) || "";
}
