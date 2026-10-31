import QtQuick
import org.kde.kirigami as Kirigami
import "icons.mjs" as Icons

// Whether tests ran after a chat's last edit and how they went (its row's
// review: talpy_den.py, TestsCache.review): its icon green or red, the tag
// itself plain, as in VS Code.
Tag {
    id: badge

    property var review: null
    readonly property var run: review ? review.tests || null : null

    visible: review !== null
    text: run === null ? i18nc("a chat ran no tests after its last edit", "Not tested") : i18nc("a chat's tests after its last edit", "Tests")
    icon: run === null ? "" : run.ok ? Icons.plasma.done : Icons.plasma.failed
    tone: run === null ? "" : run.ok ? "done" : "failed"
    tooltipTitle: run === null ? i18n("No tests since its last edit")
                : run.ok ? i18n("Tests passed after its last edit") : i18n("Tests failed after its last edit")
    tooltip: run === null ? i18n("Claude ran no test command (pytest, npm test, cargo test, …) after it last changed a file.")
           : i18n("The last test run: %1", run.command)
}
