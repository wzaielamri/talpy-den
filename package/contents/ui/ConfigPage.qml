import QtQuick
import org.kde.kcmutils as KCM
import org.kde.plasma.plasmoid

// Every settings page is one of these. Plasma hands each page every setting
// and its default (cfg_<key>, cfg_<key>Default) and warns for each one the
// page doesn't have, so this declares them all; a page declares its own
// again, typed or as an alias of its control.
//
// On Apply Plasma writes back every cfg_ property the page has: one left to
// this declaration that the page didn't change takes the setting as it is
// now (the popup may have changed it meanwhile: the Focus button, the
// new-chat box…), not as it was when the page opened. So a setting set in
// the popup is left to these on every page: here a page's own declaration
// of it isn't reached. (A page's own saveConfig() would hide this one.)
KCM.SimpleKCM {
    id: configPage

    property var cfgOpened: ({})   // key -> its value as the page opened

    function saveConfig() {
        const config = Plasmoid.configuration
        for (const key of config.keys()) {
            const name = "cfg_" + key
            if (key.endsWith("Default") || !(name in configPage) || !(key in configPage.cfgOpened))
                continue
            if (String(configPage[name]) === String(configPage.cfgOpened[key]))
                configPage[name] = config[key]
        }
    }

    Component.onCompleted: {
        const config = Plasmoid.configuration
        const opened = {}
        for (const key of config.keys())
            if (!key.endsWith("Default") && ("cfg_" + key) in configPage)
                opened[key] = configPage["cfg_" + key]
        cfgOpened = opened
    }

    // ---- every setting in main.xml and its default (tests/test_pets.py
    // checks this list against main.xml)
    property var cfg_pollInterval
    property var cfg_pollIntervalDefault
    property var cfg_idlePollInterval
    property var cfg_idlePollIntervalDefault
    property var cfg_extraConfigDirs
    property var cfg_extraConfigDirsDefault
    property var cfg_notifyWaiting
    property var cfg_notifyWaitingDefault
    property var cfg_notifyDone
    property var cfg_notifyDoneDefault
    property var cfg_notifyDoneMinSeconds
    property var cfg_notifyDoneMinSecondsDefault
    property var cfg_notifySound
    property var cfg_notifySoundDefault
    property var cfg_soundVolume
    property var cfg_soundVolumeDefault
    property var cfg_soundWaiting
    property var cfg_soundWaitingDefault
    property var cfg_soundDone
    property var cfg_soundDoneDefault
    property var cfg_soundFailed
    property var cfg_soundFailedDefault
    property var cfg_recentChats
    property var cfg_recentChatsDefault
    property var cfg_sshHosts
    property var cfg_sshHostsDefault
    property var cfg_remotePollSeconds
    property var cfg_remotePollSecondsDefault
    property var cfg_showContainers
    property var cfg_showContainersDefault
    property var cfg_containerDays
    property var cfg_containerDaysDefault
    property var cfg_markdownApp
    property var cfg_markdownAppDefault
    property var cfg_sshUsage
    property var cfg_sshUsageDefault
    property var cfg_keepDoneHours
    property var cfg_keepDoneHoursDefault
    property var cfg_showUsageInPanel
    property var cfg_showUsageInPanelDefault
    property var cfg_iconBlink
    property var cfg_iconBlinkDefault
    property var cfg_mondayRecap
    property var cfg_mondayRecapDefault
    property var cfg_dictateLanguage
    property var cfg_dictateLanguageDefault
    property var cfg_focusView
    property var cfg_focusViewDefault
    property var cfg_showPet
    property var cfg_showPetDefault
    property var cfg_playful
    property var cfg_playfulDefault
    property var cfg_chatPets
    property var cfg_chatPetsDefault
    property var cfg_showTokens
    property var cfg_showTokensDefault
    property var cfg_awayDigest
    property var cfg_awayDigestDefault
    property var cfg_awayMinutes
    property var cfg_awayMinutesDefault
    property var cfg_phoneWhileAway
    property var cfg_phoneWhileAwayDefault
    property var cfg_phoneFinished
    property var cfg_phoneFinishedDefault
    property var cfg_phoneDevice
    property var cfg_phoneDeviceDefault
    property var cfg_shortcutGoesToChat
    property var cfg_shortcutGoesToChatDefault
    property var cfg_clickOpensPane
    property var cfg_clickOpensPaneDefault
    property var cfg_diffSideBySide
    property var cfg_diffSideBySideDefault
    property var cfg_paneTextPercent
    property var cfg_paneTextPercentDefault
    property var cfg_newChatInVscode
    property var cfg_newChatInVscodeDefault
    property var cfg_newChatModel
    property var cfg_newChatModelDefault
    property var cfg_newChatEffort
    property var cfg_newChatEffortDefault
    property var cfg_recapRules
    property var cfg_recapRulesDefault
    property var cfg_recapCurrency
    property var cfg_recapCurrencyDefault
    property var cfg_newChatMode
    property var cfg_newChatModeDefault
    property var cfg_usageCap
    property var cfg_usageCapDefault
    property var cfg_usageRefreshMinutes
    property var cfg_usageRefreshMinutesDefault
}
