import QtQuick
import org.kde.taskmanager as TaskManager
import org.kde.kwindowsystem
import "cover.mjs" as Cover

// Whether windows cover the whole widget on the desktop, one or several
// together (main.qml: coveredByWindow): then nobody sees the pets, and they
// stop moving, as Plasma's animated wallpapers do under a maximized window.
// Showing the desktop, or moving the windows so a bit of the widget shows,
// starts them again. Where windows cover only a part of it, what's under
// them holds still too (hides(): a stage of pets, the spinner), since each
// picture of the smallest pet redraws the whole desktop. Loaded only on the
// desktop with the dashboard drawn there (and only where the taskmanager
// module is), so elsewhere the widget is never taken for covered: a popup
// (the panel's, or a small desktop widget's icon's) shows above windows.
Item {
    id: watch

    // Showing the desktop doesn't minimize the windows, it only hides them:
    // they stay in the list below, so it's checked on its own, at once
    readonly property bool covered: windowCovers && !KWindowSystem.showingDesktop
    property bool windowCovers: false
    // The windows over the widget, in its window's coordinates ({x, y, width, height})
    readonly property var over: KWindowSystem.showingDesktop ? [] : windowsOver
    property var windowsOver: []
    readonly property rect screenRect: Window.window ? Qt.rect(Window.window.x, Window.window.y, Window.window.width, Window.window.height)
                                                     : Qt.rect(0, 0, 0, 0)

    TaskManager.ActivityInfo {
        id: activityInfo
    }

    // The windows on this screen that you could see now
    TaskManager.TasksModel {
        id: windows
        filterByCurrentVirtualDesktop: true
        filterByActivity: true
        activity: activityInfo.currentActivity
        filterByRegion: TaskManager.RegionFilterMode.Intersect
        regionGeometry: watch.screenRect
        filterHidden: true
        filterMinimized: true
        groupMode: TaskManager.TasksModel.GroupDisabled
        onCountChanged: check.restart()
        // (not restart: a terminal's title changes several times a second
        // while Claude works, and the check waited for a pause that never came)
        onDataChanged: if (!check.running) check.start()
    }

    Connections {
        target: root
        function onWidthChanged() { check.restart() }
        function onHeightChanged() { check.restart() }
    }
    onScreenRectChanged: check.restart()

    // A moment's wait, as Plasma's panel does: a new dialog can show up in
    // the middle of the screen for a split second before it's placed
    Timer {
        id: check
        interval: 100
        onTriggered: watch.look(false)
    }
    // and now and then, for a widget moved on the desktop (or a part of it
    // moved in the widget: what's under the windows is looked at again)
    Timer {
        interval: 5000
        repeat: true
        running: true
        onTriggered: watch.look(true)
    }
    Component.onCompleted: check.restart()

    function look(again) {
        const now = windowsOverNow()
        const mine = widgetRect()
        windowCovers = mine.width > 0 && mine.height > 0 && Cover.covers(now, mine)
        if (again || JSON.stringify(now) !== JSON.stringify(windowsOver))
            windowsOver = now
    }

    function widgetRect() {
        if (!Window.window || root.width <= 0 || root.height <= 0)
            return { x: 0, y: 0, width: 0, height: 0 }
        const at = root.mapToItem(null, 0, 0)
        return { x: at.x, y: at.y, width: root.width, height: root.height }
    }

    function windowsOverNow() {
        const mine = widgetRect()
        const found = []
        for (let i = 0; i < windows.count; i++) {
            const g = windows.data(windows.makeModelIndex(i), TaskManager.AbstractTasksModel.Geometry)
            if (!g)
                continue
            const r = { x: g.x - screenRect.x, y: g.y - screenRect.y, width: g.width, height: g.height }
            if (Cover.meets(r, mine))
                found.push(r)
        }
        return found
    }

    // Whether the windows hide all of the item (what of it shows in clipTo,
    // when given: the list it scrolls in) from view
    function hides(item, clipTo) {
        if (over.length === 0 || !item || item.width <= 0 || item.height <= 0)
            return false
        const at = item.mapToItem(null, 0, 0)
        let r = Cover.clip({ x: at.x, y: at.y, width: item.width, height: item.height }, widgetRect())
        if (clipTo) {
            const c = clipTo.mapToItem(null, 0, 0)
            r = Cover.clip(r, { x: c.x, y: c.y, width: clipTo.width, height: clipTo.height })
        }
        return r.width > 0 && r.height > 0 && Cover.covers(over, r)
    }
}
