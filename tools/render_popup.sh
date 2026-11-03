#!/usr/bin/env bash
# Render the widget's popup offscreen to a PNG, from this repo's package (not
# the installed widget), with your real Claude data. For checking QML changes.
#
#   tools/render_popup.sh OUT.png [seconds]
#
# Environment:
#   WIN_W, WIN_H     window size (default 520x560)
#   ONLY_GROUP=work  show only that account section
#   SSH_HOSTS=a,b    pick SSH hosts (polled every 10 s)
#   EXTRA='QML'      extra QML put inside the widget's root item (e.g. a Timer
#                    that calls root.petEvent("done", "…") to see a reaction)
# Colors and fonts are your KDE theme's (QT_QPA_PLATFORMTHEME=kde).
# QML warnings go to OUT.log. The widget runs under a test id with its own
# config, data, state and cache folders, so nothing of your desktop is touched.
set -euo pipefail
umask 077  # the PNG and log show your real chats: keep them private
out=$(realpath -m "$1"); secs=${2:-7}
rm -f -- "$out" "${out%.png}.log"  # new files, so an old render's wider mode doesn't stay
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cp -a "$repo/package" "$work/pkg"
python3 -I - "$work/pkg" "$out" "$secs" <<'PY'
import json, os, sys
pkg, out, secs = sys.argv[1:4]
meta = json.load(open(f"{pkg}/metadata.json"))
meta["KPlugin"]["Id"] = "org.wzaielamri.talpyden.rendertest"
json.dump(meta, open(f"{pkg}/metadata.json", "w"), indent=2)
full = f"{pkg}/contents/ui/FullRepresentation.qml"
s = open(full).read()
# plasmawindowed shows the popup inline, without the panel popup's frame; and
# without a frame to reach into, the content's negative padding (out to the
# frame's inner edge, collapseMarginsHint) cut 6 px off its left and right
s = s.replace("    collapseMarginsHint: true\n",
              "    collapseMarginsHint: true\n    background: Rectangle { color: Kirigami.Theme.backgroundColor }\n"
              "    leftPadding: 0\n    rightPadding: 0\n", 1)
only = os.environ.get("ONLY_GROUP")
if only:
    s = s.replace("model: root.groups.length", f"model: root.groups.filter(g => g.name === {only!r}).length")
    s = s.replace("group: root.groups[index] || root.emptyGroup",
                  f"group: root.groups.filter(g => g.name === {only!r})[index] || root.emptyGroup")
open(full, "w").write(s)
main = f"{pkg}/contents/ui/main.qml"
s = open(main).read()
grab = """
    Timer {
        interval: %d * 1000; running: true
        onTriggered: {
            const item = root.fullRepresentationItem
            if (!item) { console.warn("RENDER: no popup"); Qt.quit(); return }
            item.grabToImage(function(result) {
                result.saveToFile("%s"); console.warn("RENDER: saved " + item.width + "x" + item.height); Qt.quit()
            })
        }
    }
    Item { Component.onCompleted: root.expanded = true }
%s
""" % (int(secs), out, os.environ.get("EXTRA", ""))
s = s.replace("PlasmoidItem {\n    id: root\n", "PlasmoidItem {\n    id: root\n" + grab, 1)
# The render is the only copy in its own cache, so it would be the one that
# notifies: it would pop up your desktop's notifications and start the queued
# tasks and go-ons it copied (queue.json, keep.json) for real. It never does.
notifier = "readonly property bool notifier: "
assert s.count(notifier) == 1, "main.qml's notifier property moved: update render_popup.sh"
s = s.replace(notifier, notifier + "false && ", 1)
open(main, "w").write(s)
PY
mkdir -p "$work/data" "$work/config" "$work/state" "$work/cache/talpy-den"
for f in kdeglobals plasmarc; do [ -f "$HOME/.config/$f" ] && cp "$HOME/.config/$f" "$work/config/"; done
# A copy of the widget's cache (the status-line snapshots for plan usage, and
# the token and transcript caches so the first check is quick), not the
# cache itself: the render mustn't sign up as another copy of the widget
# (instances.json) or hand its settings to the real ones (settings.json)
real_cache="${XDG_CACHE_HOME:-$HOME/.cache}/talpy-den"
if [ -d "$real_cache" ]; then
  [ -d "$real_cache/statusline" ] && cp -a "$real_cache/statusline" "$work/cache/talpy-den/"
  [ -d "$real_cache/live" ] && cp -a "$real_cache/live" "$work/cache/talpy-den/"  # (live mode's steps)
  find "$real_cache" -maxdepth 1 -name '*.json' ! -name instances.json ! -name settings.json \
    -exec cp -p {} "$work/cache/talpy-den/" \;
fi
{
  printf '[Applets][1]\nimmutability=1\nplugin=org.wzaielamri.talpyden.rendertest\n\n'
  printf '[Applets][1][Configuration]\ngeometry=0,0,%s,%s\n' "${WIN_W:-520}" "${WIN_H:-560}"
  [ -n "${SSH_HOSTS:-}" ] && printf '\n[Applets][1][Configuration][General]\nsshHosts=%s\nremotePollSeconds=10\n' "$SSH_HOSTS"
} > "$work/config/plasmawindowedrc"
export XDG_CONFIG_HOME="$work/config" XDG_STATE_HOME="$work/state" XDG_DATA_HOME="$work/data" XDG_CACHE_HOME="$work/cache"
kpackagetool6 -t Plasma/Applet -i "$work/pkg" >/dev/null
QT_FORCE_STDERR_LOGGING=1 QT_QPA_PLATFORMTHEME=kde QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software \
  timeout $((secs + 20)) plasmawindowed org.wzaielamri.talpyden.rendertest > "${out%.png}.log" 2>&1 || true
grep -E "RENDER|TypeError|ReferenceError|Error:" "${out%.png}.log" || echo "no RENDER line: see ${out%.png}.log"
