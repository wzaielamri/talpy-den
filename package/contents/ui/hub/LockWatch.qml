import QtQuick
import org.kde.plasma.workspace.dbus as DBus

// Whether the screen is locked: asked once, then told as it locks and
// unlocks (org.freedesktop.ScreenSaver, KDE's screen locker). Loaded by
// Beat.qml only where Plasma's D-Bus module is.
QtObject {
    id: watch

    property bool locked: false
    property bool told: false          // a lock or unlock came: the first answer is old news then

    property var watcher: DBus.SignalWatcher {
        enabled: true
        busType: DBus.BusType.Session
        service: "org.freedesktop.ScreenSaver"
        path: "/ScreenSaver"
        iface: "org.freedesktop.ScreenSaver"
        function dbusActiveChanged(active) {
            watch.told = true
            watch.locked = active === true
        }
    }

    Component.onCompleted: DBus.SessionBus.asyncCall({ service: "org.freedesktop.ScreenSaver", path: "/ScreenSaver",
                                                      iface: "org.freedesktop.ScreenSaver", member: "GetActive" },
                                                    reply => {
                                                        if (!watch.told && !reply.isError)
                                                            watch.locked = reply.value === true
                                                    },
                                                    () => {})
}
