    // tools/bench/bench.py's measuring, put in the widget's root item
    // (render_popup.sh EXTRA): it opens the made-up chats' Talpy Chat windows
    // (fake_chats.py) and says what it measured as "BENCH <what> <json>" lines.
    // Times are Date.now() ms; "frame" is the window's next frameSwapped.
    Item {
        id: bench
        readonly property string scenario: "__SCENARIO__"
        readonly property var ids: __IDS__
        readonly property int idleMs: __IDLE_MS__
        readonly property int repeats: 3
        readonly property int sends: 5
        readonly property int turns: 5

        function log(what, data) { console.warn("BENCH " + what + " " + JSON.stringify(data || {})) }
        function done() {
            log("done", {})
            Qt.quit()
        }
        function rowOf(id) {
            for (const g of (root.status && root.status.groups) || [])
                for (const r of (g.recent || []).concat(g.starred || []))
                    if (r.sessionId === id)
                        return r
            return null
        }
        function chatOf(id) { return rowOf(id) || { sessionId: id, profileDir: "", cwd: "", name: "" } }
        function windowOf(id) { return root.paneWindows.find(w => w.chat && w.chat.chatId === id) || null }
        function find(item, test) {
            if (!item)
                return null
            if (test(item))
                return item
            const kids = item.children || []
            for (let i = 0; i < kids.length; i++) {
                const f = find(kids[i], test)
                if (f)
                    return f
            }
            return null
        }
        function listOf(win) { return find(win.contentItem, o => o.cacheBuffer === 100000) }
        function boxOf(win) {
            return find(win.contentItem, o => typeof o.placeholderText === "string" && o.placeholderText.indexOf("Reply to Claude") === 0)
        }

        // cb() in ms (a one-off timer: nothing runs between)
        function after(ms, cb) {
            const t = Qt.createQmlObject("import QtQuick; Timer { }", bench)
            t.interval = Math.max(1, ms)
            t.triggered.connect(function() { t.destroy(); cb() })
            t.start()
        }
        // cb() once test() holds (looked at every 25 ms), or onTimeout() after ms
        property var waits: []
        function when(test, cb, ms, label) {
            waits = waits.concat([{ test: test, cb: cb, until: Date.now() + ms, label: label }])
        }
        Timer {
            interval: 25
            repeat: true
            running: bench.waits.length > 0
            onTriggered: {
                const now = bench.waits
                bench.waits = []
                const left = []
                for (const w of now) {
                    if (w.test())
                        w.cb()
                    else if (Date.now() > w.until) {
                        bench.log("timeout", { waiting: w.label })
                        w.cb()
                    } else
                        left.push(w)
                }
                bench.waits = left.concat(bench.waits)
            }
        }
        // cb(time) at win's next frame, -1 if none comes in 3 s
        // The frame the chips above the reply box are drawn in: the one before (seen) if they were
        // made by then, else the first after they are; -1 for none (in 2 s, or a package without them)
        function chipsFrame(win, cb, seen) {
            const made = () => win.chipsShown !== undefined && win.chipsShown.length > 0
                               && find(win.contentItem, o => o.objectName === "replyChips") !== null
            if (win.chipsShown === undefined)
                return cb(-1)
            if (made())
                return cb(seen)
            let over = false
            const f = function() {
                if (over || !made())
                    return
                over = true
                win.frameSwapped.disconnect(f)
                cb(Date.now())
            }
            win.frameSwapped.connect(f)
            after(2000, () => {
                if (!over) {
                    over = true
                    win.frameSwapped.disconnect(f)
                    cb(-1)
                }
            })
        }
        function nextFrame(win, cb) {
            let over = false
            const f = function() {
                if (over)
                    return
                over = true
                win.frameSwapped.disconnect(f)
                cb(Date.now())
            }
            win.frameSwapped.connect(f)
            after(3000, () => {
                if (!over) {
                    over = true
                    win.frameSwapped.disconnect(f)
                    cb(-1)
                }
            })
        }

        // Opening a chat's window: openPane → its conversation read and in the
        // list (loaded) → shown (visible) → its first frame, and the first frame
        // with the conversation in it (dataFrame), each in ms from the call
        function open(id, label, cb) {
            const t0 = Date.now()
            root.openPane(chatOf(id), "", "chat")
            const t1 = Date.now()
            const win = windowOf(id)
            if (!win) {
                log("open", { label: label, error: "no window" })
                cb(null)
                return
            }
            const r = { label: label, call: t1 - t0, loaded: win.loaded ? t1 - t0 : -1, visible: win.visible ? t1 - t0 : -1,
                        frame: -1, dataFrame: -1 }
            let over = false
            const onLoaded = function() { if (win.loaded && r.loaded < 0) r.loaded = Date.now() - t0 }
            const onVisible = function() { if (win.visible && r.visible < 0) r.visible = Date.now() - t0 }
            const finish = function(timeout) {
                if (over)
                    return
                over = true
                win.loadedChanged.disconnect(onLoaded)
                win.visibleChanged.disconnect(onVisible)
                win.frameSwapped.disconnect(onFrame)
                r.items = win.lastItems.length
                if (timeout)
                    r.timeout = true
                log("open", r)
                cb(win)
            }
            const onFrame = function() {
                if (!win.visible)
                    return
                const t = Date.now() - t0
                if (r.frame < 0)
                    r.frame = t
                if (win.loaded && r.dataFrame < 0) {
                    r.dataFrame = t
                    finish(false)
                }
            }
            win.loadedChanged.connect(onLoaded)
            win.visibleChanged.connect(onVisible)
            win.frameSwapped.connect(onFrame)
            after(10000, () => finish(true))
        }
        function close(win) {
            if (win)
                win.close()
        }
        // fns: [fn(next)], one after another
        function chain(fns) {
            if (fns.length)
                fns[0](() => chain(fns.slice(1)))
        }

        function runOpen() {
            let a = null, b = null
            const steps = [
                next => open(ids.short, "first window (short chat)", w => { a = w; after(1500, next) }),
                next => open(ids.long, "new window (long chat)", w => { b = w; after(1500, next) }),
                next => { close(a); close(b); after(1500, next) }]
            for (let k = 0; k < repeats; k++)
                steps.push(next => open(ids.short, "pooled window (short chat)", w => after(1500, () => { close(w); after(1000, next) })),
                           next => open(ids.long, "pooled window (long chat)", w => after(1500, () => { close(w); after(1000, next) })))
            steps.push(next => done())
            chain(steps)
        }

        // Enter → your message shown: the reply box's text sent as Enter sends it
        // (send("enter"): pane.py --send is stubbed, nothing goes anywhere); call:
        // till send() is back (the pending item is in the list then), frame: its frame
        function runSend() {
            open(ids.short, "chat to send to", win => after(2000, () => sendOne(win, 1)))
        }
        function sendOne(win, i) {
            if (i > sends) {
                done()
                return
            }
            const box = boxOf(win), list = listOf(win)
            box.text = "Bench message " + i
            const t0 = Date.now()
            win.send("enter", false)
            const t1 = Date.now()
            const last = list.count ? list.model.get(list.count - 1) : null
            nextFrame(win, t2 => {
                log("send", { i: i, call: t1 - t0, frame: t2 < 0 ? -1 : t2 - t0, last: last ? last.key : "",
                              route: win.route, boxAfter: box.text })
                after(2500, () => sendOne(win, i + 1))
            })
        }

        // Turn's end → shown: bench.py appends a turn to the chat's transcript, a
        // line at a time, on "BENCH feed n"; its last line (Claude's reply,
        // BENCH-END-n) is in lastItems at "in", and on screen at "frame"
        function runTurn() {
            open(ids.turn, "chat with turns", win => after(3000, () => turnOne(win, 1)))
        }
        function turnOne(win, n) {
            if (n > turns) {
                done()
                return
            }
            const marker = "BENCH-END-" + n
            let got = false
            const onItems = function() {
                if (got || JSON.stringify(win.lastItems.slice(-3)).indexOf(marker) < 0)
                    return
                got = true
                const tIn = Date.now()
                win.lastItemsChanged.disconnect(onItems)
                nextFrame(win, tFrame => {
                    log("turn", { n: n, in: tIn, frame: tFrame })
                    // (and the reply's chips, drawn: the frame they're in; a package without them: none)
                    chipsFrame(win, tChips => {
                        if (tChips > 0)
                            log("chips", { n: n, frame: tChips })
                        after(2000, () => turnOne(win, n + 1))
                    }, tFrame)
                })
            }
            win.lastItemsChanged.connect(onItems)
            after(20000, () => {
                if (!got) {
                    got = true
                    win.lastItemsChanged.disconnect(onItems)
                    log("turn", { n: n, timeout: true })
                    turnOne(win, n + 1)
                }
            })
            log("feed", { n: n })
        }

        // Scrolling a 500-item chat: its list moved 120 px a frame, from its end to
        // the top and back, on the Chat tab, then on the Steps tab; each frame's time
        function runScroll() {
            open(ids.long, "long chat", win => {
                win.limit = 500
                win.stamp = ""
                win.load()
                when(() => win.loaded && win.lastItems.length >= 500, () => after(3000, () =>
                    scrollTab(win, "chat", () => {
                        win.tab = "steps"
                        after(3000, () => scrollTab(win, "steps", done))
                    })), 30000, "500 items")
            })
        }
        function scrollTab(win, tab, cb) {
            const list = listOf(win), step = 120
            const bottom = () => Math.max(list.originY, list.originY + list.contentHeight - list.height)
            list.contentY = bottom()
            after(1500, () => {
                const frames = []
                let last = 0, dir = -1
                const f = function() {
                    const t = Date.now()
                    if (last)
                        frames.push(t - last)
                    last = t
                    if (dir < 0 && list.contentY <= list.originY + 0.5)
                        dir = 1
                    else if (dir > 0 && list.contentY >= bottom() - 0.5) {
                        win.frameSwapped.disconnect(f)
                        const s = frames.slice().sort((x, y) => x - y)
                        const ms = frames.reduce((x, y) => x + y, 0)
                        log("scroll", { tab: tab, items: win.lastItems.length, rows: list.count, height: Math.round(list.contentHeight),
                                        frames: frames.length, ms: ms, fps: Math.round(frames.length * 10000 / ms) / 10,
                                        p50: s[Math.floor(s.length * 0.5)], p95: s[Math.floor(s.length * 0.95)], max: s[s.length - 1],
                                        over16: frames.filter(x => x > 16.7).length, over33: frames.filter(x => x > 33.4).length })
                        cb()
                        return
                    }
                    list.contentY = dir < 0 ? Math.max(list.originY, list.contentY - step) : Math.min(bottom(), list.contentY + step)
                }
                win.frameSwapped.connect(f)
                list.contentY = Math.max(list.originY, list.contentY - step)
            })
        }

        // Idle CPU (bench.py reads it from /proc): no window yet, a window open
        // on the long chat, then that window closed (kept, hidden); idleMs each.
        // The frames each window draws meanwhile, too
        function runIdle() {
            const popup = root.fullRepresentationItem ? root.fullRepresentationItem.Window.window : null
            let popupFrames = 0, paneFrames = 0, at = 0
            if (popup)
                popup.frameSwapped.connect(() => popupFrames++)
            const mark = (name, win) => {
                const t = Date.now()
                log("mark", { name: name, t: t, popupFrames: popupFrames, paneFrames: paneFrames })
            }
            after(10000, () => {
                mark("none-start")
                after(idleMs, () => {
                    mark("none-end")
                    open(ids.long, "idle chat", win => {
                        win.frameSwapped.connect(() => paneFrames++)
                        after(5000, () => {
                            mark("open-start")
                            after(idleMs, () => {
                                mark("open-end")
                                close(win)
                                after(5000, () => {
                                    mark("closed-start")
                                    after(idleMs, () => {
                                        mark("closed-end")
                                        done()
                                    })
                                })
                            })
                        })
                    })
                })
            })
        }

        Component.onCompleted: {
            // the made-up chats listed first (at most a minute), then a moment for the
            // widget's first checks to settle
            when(() => rowOf(ids.short) !== null && rowOf(ids.long) !== null, () => {
                log("start", { scenario: scenario, listed: rowOf(ids.short) !== null })
                after(3000, () => ({ open: runOpen, send: runSend, turn: runTurn, scroll: runScroll, idle: runIdle })[scenario]())
            }, 60000, "the made-up chats listed")
        }
    }
