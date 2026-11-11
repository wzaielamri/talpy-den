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
            const made = () => win.chipsOn === true && find(win.contentItem, o => o.objectName === "replyChips") !== null
            if (win.chipsOn === undefined)
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

        // Search on a 500-item chat, on the Steps tab (what each step ran and got searched too): a
        // query typed (Talpy Chat's FindBar.qml: none in a package without it), till all is searched,
        // and how late a 5 ms timer ticks meanwhile (the longest the window can't draw); then 20
        // steps to matches, each till its frame; then Ctrl+O on a chat of long texts, and back
        function lateness(cb) {   // cb() → {max, p95, over16}: the timer's late ticks till then
            const t = Qt.createQmlObject("import QtQuick; Timer { interval: 5; repeat: true }", bench)
            const gaps = []
            let last = Date.now()
            t.triggered.connect(() => { const n = Date.now(); gaps.push(n - last); last = n })
            t.start()
            return () => {
                t.stop()
                t.destroy()
                const s = gaps.slice().sort((x, y) => x - y)
                return { max: s.length ? s[s.length - 1] : -1, p95: s.length ? s[Math.floor(s.length * 0.95)] : -1,
                         over16: gaps.filter(x => x > 16).length, ticks: gaps.length }
            }
        }
        function barOf(win) { return find(win.contentItem, o => o.hits !== undefined && o.step !== undefined && o.searched !== undefined) }
        function runFind() {
            open(ids.long, "long chat", win => {
                win.limit = 500
                win.stamp = ""
                win.load()
                when(() => win.loaded && win.lastItems.length >= 500, () => after(3000, () => {
                    win.tab = "steps"
                    after(3000, () => {
                        if (win.findOn === undefined) {
                            log("search", { error: "no search in this package" })
                            return done()
                        }
                        win.findOn = true
                        after(1000, () => chain(["parser", "nowhere at all", "a"].map(q => next => searchOnce(win, q, next)).concat([
                            next => stepsOnce(win, next), next => foldsChat(next), next => done()])))
                    })
                }), 30000, "500 items")
            })
        }
        function searchOnce(win, q, cb) {
            const late = lateness()
            const t0 = Date.now()
            win.findQuery = q
            const bar = barOf(win)
            when(() => bar.next === -1 && bar.searched, () => {
                const t1 = Date.now()
                const l = late()
                log("search", { query: q, items: win.shownList.length, hits: bar.hits.length, ms: t1 - t0, lateMax: l.max, lateP95: l.p95, over16: l.over16 })
                after(1500, cb)
            }, 20000, "search " + q)
        }
        function stepsOnce(win, cb) {
            win.findQuery = "parser"
            const bar = barOf(win)
            when(() => bar.next === -1, () => {
                const times = [], calls = []
                const one = k => {
                    if (k >= 20) {
                        const s = times.slice().sort((x, y) => x - y), c = calls.slice().sort((x, y) => x - y)
                        log("steps", { steps: times.length, frameMedian: s[Math.floor(s.length / 2)], frameMax: s[s.length - 1],
                                       callMedian: c[Math.floor(c.length / 2)], callMax: c[c.length - 1] })
                        return after(1000, cb)
                    }
                    const t0 = Date.now()
                    bar.step(false)
                    bar.goTo()   // (what its timer does a moment later: at once here)
                    calls.push(Date.now() - t0)
                    nextFrame(win, t => { times.push(t < 0 ? -1 : t - t0); after(150, () => one(k + 1)) })
                }
                one(0)
            }, 20000, "steps")
        }
        // (Ctrl+O unfolds long texts: on a chat of long replies and messages, its 500 items, Chat tab)
        function foldsChat(cb) {
            open(ids.folds, "folds chat", win => {
                win.limit = 500
                win.stamp = ""
                win.load()
                when(() => win.loaded && win.lastItems.length >= 200, () => after(3000, () => foldOnce(win, cb)), 30000, "the folds chat")
            })
        }
        function foldOnce(win, cb) {
            win.findOn = false
            const list = listOf(win)
            const late = lateness()
            const t0 = Date.now()
            win.foldAll()
            const t1 = Date.now()
            let h = list.contentHeight, still = Date.now()
            const watch = () => {
                if (list.contentHeight !== h) {
                    h = list.contentHeight
                    still = Date.now()
                }
                if (Date.now() - still > 1000) {
                    const l = late()
                    log("foldAll", { items: win.lastItems.length, long: win.shownList.filter(it => it.kind === "claude" || it.kind === "you").length,
                                     call: t1 - t0, settled: still - t0, height: Math.round(h), lateMax: l.max, lateP95: l.p95, over16: l.over16 })
                    const t2 = Date.now()
                    win.foldAll()
                    log("foldAll", { back: Date.now() - t2 })
                    return after(1500, cb)
                }
                after(50, watch)
            }
            watch()
        }

        // Talpy Chat's bookmarks on the long chat (100 of them, fake_chats.py): once its window opens,
        // the frame its ribbons show in; on its 500 items, what each read costs them (Bookmarks.qml
        // place(): the rows unchanged, nothing made), a bookmark taken away and given back (the frame its
        // ribbon goes or comes in), the list opened (its first frame, then again: warm), Alt+↓ (its frame),
        // and a reach: from the 120 items a window reads first, to the oldest bookmark (till it's gone to)
        function logicOf(win) { return find(win.contentItem, o => o.objectName === "bookmarkLogic") }
        function flagsOf(win, under) {
            let n = 0
            const walk = item => {
                if (item.objectName === "bookmarkFlag" && item.visible)
                    n++
                for (const k of item.children || [])
                    walk(k)
            }
            walk(under || win.contentItem)
            return n
        }
        function runBookmarks() {
            const t0 = Date.now()
            root.openPane(chatOf(ids.long), "", "chat")
            const win = windowOf(ids.long)
            if (!win || win.bookmarksNow === undefined) {
                log("bookmarks", { error: "no bookmarks in this package" })
                return done()
            }
            const r = { dataFrame: -1, flagsFrame: -1, flags: 0 }
            const onFrame = function() {
                const t = Date.now() - t0
                if (win.loaded && win.visible && r.dataFrame < 0)
                    r.dataFrame = t
                if (r.dataFrame >= 0 && r.flagsFrame < 0 && flagsOf(win) > 0) {
                    r.flagsFrame = t
                    r.flags = flagsOf(win)
                    win.frameSwapped.disconnect(onFrame)
                }
            }
            win.frameSwapped.connect(onFrame)
            when(() => r.flagsFrame >= 0, () => {
                log("bookmarksOpen", r)
                after(1500, () => {
                    win.limit = 500
                    win.stamp = ""
                    win.load()
                    when(() => win.loaded && win.lastItems.length >= 500 && flagsOf(win) >= 90, () => after(2000, () => marksOn500(win)), 30000, "500 items")
                })
            }, 15000, "ribbons")
        }
        function marksOn500(win) {
            const lg = logicOf(win), n = 100
            let t = Date.now()
            for (let i = 0; i < n; i++)
                lg.place()
            log("place", { ms: (Date.now() - t) / n, flags: flagsOf(win), items: win.shownList.length, marks: win.bookmarks.length })
            // (and every ribbon made again: as a window shows a chat's 100 at once)
            lg.clear()
            t = Date.now()
            lg.place()
            log("placeMade", { ms: Date.now() - t, flags: flagsOf(win), missing: lg.missing })
            // (those out of sight a few a frame: each frame's time till all are made)
            const made = { frames: 0, worst: 0, last: Date.now() }
            const onMade = function() {
                const now = Date.now()
                made.frames++
                made.worst = Math.max(made.worst, now - made.last)
                made.last = now
                if (lg.missing === 0) {
                    win.frameSwapped.disconnect(onMade)
                    log("placeAll", { ms: now - t, frames: made.frames, worstFrameMs: made.worst, flags: flagsOf(win) })
                }
            }
            win.frameSwapped.connect(onMade)
            // the Chat tab scrolled with its 100 ribbons, then without them (the same window)
            after(1500, () => scrollTab(win, "chat, 100 ribbons", () => {
                const saved = win.bookmarked
                win.bookmarked = {}
                lg.place()
                after(1500, () => scrollTab(win, "chat, no ribbons", () => {
                    win.bookmarked = saved
                    lg.place()
                    after(1500, () => scrollTab(win, "chat, 100 ribbons again", () => after(1500, () => toggleTwice(win, lg))))
                }))
            }))
        }
        function toggleTwice(win, lg) {
            let t = 0
            const list = listOf(win)
            let at = -1
            for (let i = win.shownList.length - 1; i >= 0 && at < 0; i--)
                if (win.bookmarked[String(win.shownList[i].key)] === true && list.itemAtIndex(i))
                    at = i
            const row = list.itemAtIndex(at), key = String(win.shownList[at].key)
            list.contentY = Math.max(list.originY, row.y - 40)
            after(800, () => {
                t = Date.now()
                lg.toggle(row)
                const off = Date.now() - t
                nextFrame(win, f1 => {
                    const offFrame = f1 - t
                    const gone = flagsOf(win, row) === 0
                    after(1500, () => {
                        t = Date.now()
                        lg.toggle(row)
                        const on = Date.now() - t
                        nextFrame(win, f2 => {
                            log("toggle", { offMs: off, offFrameMs: offFrame, goneThatFrame: gone, onMs: on, onFrameMs: f2 - t,
                                            shownThatFrame: flagsOf(win, row) === 1, key: key })
                            after(1500, () => listTwice(win, lg))
                        })
                    })
                })
            })
        }
        function listTwice(win, lg) {
            const once = (label, cb) => {
                const t = Date.now()
                win.bookmarksOn = true
                const call = Date.now() - t
                nextFrame(win, f => {
                    log("list", { label: label, callMs: call, frameMs: f - t, open: find(win.contentItem, o => o.capped !== undefined && o.go !== undefined) !== null })
                    after(1000, () => {
                        win.bookmarksOn = false
                        after(1000, cb)
                    })
                })
            }
            once("first", () => once("warm", () => once("warm", () => pillOnce(win, () => {
                const list = listOf(win)
                list.contentY = list.originY
                after(1000, () => {
                    const t = Date.now()
                    lg.step(false)
                    const call = Date.now() - t
                    nextFrame(win, f => {
                        log("step", { callMs: call, frameMs: f - t, current: lg.current })
                        after(1500, () => reachOnce(win, lg))
                    })
                })
            }))))
        }
        // (the tab row's count made, as a window shows a chat with bookmarks: what it costs then)
        function pillOnce(win, cb) {
            const saved = win.bookmarks
            win.bookmarks = []
            after(1000, () => {
                const t = Date.now()
                win.bookmarks = saved
                const call = Date.now() - t
                log("pill", { callMs: call })
                after(1500, cb)
            })
        }
        function reachOnce(win, lg) {
            win.limit = 120
            win.stamp = ""
            win.load()
            when(() => win.lastItems.length === 120, () => after(2000, () => {
                const key = win.bookmarks[0].key
                const t = Date.now()
                let answered = -1
                const onLimit = () => { if (answered < 0) answered = Date.now() - t }
                win.limitChanged.connect(onLimit)
                lg.reach(key, false)
                when(() => lg.going === "" && lg.current === key, () => {
                    win.limitChanged.disconnect(onLimit)
                    const all = Date.now() - t, limit = win.limit
                    nextFrame(win, f => {
                        log("reach", { answerMs: answered, ms: all, frameMs: f - t, limit: limit, items: win.lastItems.length, current: lg.current === key })
                        // (Show earlier to that length, from the same 120: the same rows put in)
                        after(1500, () => earlierOnce(win, limit))
                    })
                }, 20000, "reach")
            }), 20000, "120 items")
        }
        function earlierOnce(win, limit) {
            win.limit = 120
            win.stamp = ""
            win.load()
            when(() => win.lastItems.length === 120, () => after(2000, () => {
                const t = Date.now()
                win.limit = limit
                win.stamp = ""
                win.load()
                when(() => win.lastItems.length > 120, () => {
                    const all = Date.now() - t
                    nextFrame(win, f => {
                        log("earlier", { ms: all, frameMs: f - t, limit: limit, items: win.lastItems.length })
                        after(1000, done)
                    })
                }, 20000, "show earlier")
            }), 20000, "120 items again")
        }

        Component.onCompleted: {
            // the made-up chats listed first (at most a minute), then a moment for the
            // widget's first checks to settle
            when(() => rowOf(ids.short) !== null && rowOf(ids.long) !== null, () => {
                log("start", { scenario: scenario, listed: rowOf(ids.short) !== null })
                after(3000, () => ({ open: runOpen, send: runSend, turn: runTurn, scroll: runScroll, idle: runIdle, find: runFind, bookmarks: runBookmarks,
                                     first: () => open(ids.short, "first window (short chat)", w => after(1500, done)) })[scenario]())
            }, 60000, "the made-up chats listed")
        }
    }
