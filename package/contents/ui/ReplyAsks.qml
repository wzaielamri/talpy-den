import QtQuick
import QtQuick.Layouts
import QtQuick.Window
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami

// What Talpy Chat asks under its reply box before it does something for you: copy a pasted picture
// to an SSH host (and that it's copying), set dictation up, download a speech model. ChatPane.qml's
// Loader: read and made only while one of them is asked
ColumnLayout {
    spacing: Kirigami.Units.smallSpacing

    // A picture for an SSH host's chat: copied there once you say so
    RowLayout {
        Layout.fillWidth: true
        visible: !!pane.host && !!root.pictureOffer && root.pictureOffer.host === pane.host
                 && root.pictureOffer.target === pane.pasteTarget
        spacing: Kirigami.Units.smallSpacing

        Image {
            source: root.pictureOffer ? "file://" + encodeURI(root.pictureOffer.path) : ""
            Layout.preferredHeight: Kirigami.Units.gridUnit * 2
            Layout.preferredWidth: Kirigami.Units.gridUnit * 3
            sourceSize.height: Kirigami.Units.gridUnit * 2 * Screen.devicePixelRatio
            fillMode: Image.PreserveAspectFit
            asynchronous: true
        }
        ConfirmLine {
            Layout.fillWidth: true
            text: i18n("Copy this picture to %1? Claude there can only open it there.", root.hostLabel(pane.host))
            confirmText: i18n("Copy")
            onConfirmed: root.copyPicture()
            onCancelled: root.pictureOffer = null
        }
    }
    PlasmaComponents3.Label {
        visible: !!pane.host && root.pictureCopyingTo === pane.host && root.pictureCopyTarget === pane.pasteTarget
        textFormat: Text.PlainText
        text: i18n("Copying the picture to %1…", root.hostLabel(pane.host))
        color: pane.mutedColor
    }
    // Nothing to write it down with: dictation is set up once you say so
    ConfirmLine {
        Layout.fillWidth: true
        visible: pane.offerSetup
        text: i18n("Set up dictation? It installs faster-whisper, speech to text that runs on this computer, and its base speech model: about %1 MB from pypi.org and huggingface.co into ~/.local/share/talpy-den/whisper, no sudo needed; a few minutes. What you say never leaves the computer. Other models: in the settings.",
                   pane.dictateState ? pane.dictateState.setupMb : 612)
        confirmText: i18n("Set up")
        onConfirmed: {
            pane.offerSetup = false
            pane.dictating = "setup"
            pane.dictateRun("--setup")
        }
        onCancelled: pane.offerSetup = false
    }
    // whisper is there but no speech model: one is downloaded once you say so
    ConfirmLine {
        Layout.fillWidth: true
        visible: pane.offerModel
        text: i18n("To dictate, %1 needs a speech model: download its base model (142 MB) from huggingface.co? It's kept in ~/.local/share/talpy-den/whisper; what you say never leaves the computer. Other models: in the settings.",
                   pane.dictateState && pane.dictateState.engine ? pane.dictateState.engine : "whisper")
        confirmText: i18n("Download")
        onConfirmed: {
            pane.offerModel = false
            pane.dictating = "model"
            pane.dictateRun("--get-model base")
        }
        onCancelled: pane.offerModel = false
    }
}
