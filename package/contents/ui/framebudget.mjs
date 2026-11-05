// One budget of time a frame for every list that makes its rows a few a
// frame (KeyedRows.qml: an account's chats, the Projects tab's cards…), in
// every copy of the widget (an engine has one of this module): the lists of
// a popup that fill at once share it, so a frame waits at most that long.
// ES2017, no `?.` or `??`.

let until = 0;
let lastEnd = 0;

// A go starts: when it should stop making rows. A go right after another
// (within a few ms: the same frame) gets what's left of that one's budget.
export function begin(ms) {
    const now = Date.now();
    if (now - lastEnd > 3)
        until = now + ms;
    return until;
}

export function end() {
    lastEnd = Date.now();
}
