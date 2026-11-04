#!/usr/bin/env bash
# Install or upgrade Talpy Den (the Plasma widget, or the GNOME Shell
# extension) and hook the Claude status line.
#   ./install.sh              install/upgrade; add the status-line snippet and
#                             (Plasma) the permission hook (asks first)
#   ./install.sh --yes        same, without asking
#   ./install.sh --uninstall  remove it, the snippet and the hook (and the
#                             chat pane's window rule)
#   --plasma / --gnome        which one (default: the desktop you're on)
# The snippet goes into every script a Claude profile's settings.json runs as
# its status line (~/.claude, ~/.claude-*; a script shared by several profiles
# is patched once). TALPY_DEN_STATUSLINE=/path/script.sh overrides that.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
id="org.wzaielamri.talpyden"
uuid="talpy-den@wzaielamri.github.io"
marker_start="# >>> talpy-den >>>"
gsettings_path="/org/gnome/shell/extensions/talpy-den"
# What earlier versions installed under their first name, replaced on upgrade
legacy_id="org.wzaielamri.claudestatus"
legacy_uuid="claude-status@wzaielamri.github.io"
legacy_gsettings_path="/org/gnome/shell/extensions/claude-status"
legacy_marker_start="# >>> claude-widget >>>"
legacy_pane_app="org.wzaielamri.claudestatus.chat"
legacy_pane_rule="claude-status-chat-pane"
yes=0
uninstall=0
target=""
for arg in "$@"; do
  case "$arg" in
    -y|--yes) yes=1 ;;
    --uninstall) uninstall=1 ;;
    --plasma) target=plasma ;;
    --gnome) target=gnome ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

# Plasma unless only GNOME is here, or both are and this is a GNOME session
if [ -z "$target" ]; then
  if command -v kpackagetool6 >/dev/null; then
    target=plasma
    if command -v gnome-extensions >/dev/null; then
      case ":${XDG_CURRENT_DESKTOP:-}:" in *:GNOME:*) target=gnome ;; esac
    fi
  elif command -v gnome-extensions >/dev/null; then
    target=gnome
  else
    target=plasma
  fi
fi

if [ "$target" = plasma ] && ! command -v kpackagetool6 >/dev/null; then
  echo "kpackagetool6 not found: Talpy Den needs KDE Plasma 6 (Plasma 5 isn't supported)," >&2
  echo "or GNOME Shell 43/44 or 49 or newer (./install.sh --gnome)." >&2
  exit 1
fi
if [ "$target" = gnome ] && ! command -v gnome-extensions >/dev/null; then
  echo "gnome-extensions not found: the GNOME version needs GNOME Shell 43/44 or 49 or newer." >&2
  exit 1
fi
command -v python3 >/dev/null || echo "warning: python3 not found; Talpy Den needs it to read Claude's files" >&2

confirm() {
  [ "$yes" = 1 ] && return 0
  if [ ! -t 0 ]; then
    echo "(no terminal to ask on; re-run with --yes to apply)"
    return 1
  fi
  read -r -p "$1 [y/N] " reply
  [[ "$reply" =~ ^[Yy] ]]
}

# Whether VS Code has the extension $1 (publisher.name): a folder of it that
# VS Code hasn't uninstalled (it keeps that one, named in .obsolete, until it
# starts again)
vscode_has() {
  local dir
  for dir in "$HOME"/.vscode*/extensions/"$1"-*; do
    [ -d "$dir" ] || continue
    grep -qF "\"${dir##*/}\"" "${dir%/*}/.obsolete" 2>/dev/null || return 0
  done
  return 1
}

# Status-line scripts in use, one per line (links resolved, duplicates dropped).
find_statuslines() {
  local given="${TALPY_DEN_STATUSLINE:-${CLAUDE_WIDGET_STATUSLINE:-}}"  # (its first name too)
  if [ -n "$given" ]; then
    printf '%s\n' "$given"
    return
  fi
  python3 -I - "$HOME" <<'EOF'
import json, os, shlex, sys
from pathlib import Path
home = Path(sys.argv[1])
os.environ["HOME"] = str(home)


def shell_script(path):
    """A script for sh, bash or zsh: a .sh file, or one whose #! line says so."""
    if path.suffix == ".sh":
        return True
    try:
        with open(path, "rb") as f:
            first = f.readline(200)
    except OSError:
        return False
    return first.startswith(b"#!") and any(sh in first for sh in (b"sh\n", b"bash", b"zsh", b"dash", b"ksh", b"sh "))


found = []
for cfg in [home / ".claude", *sorted(home.glob(".claude-*"))]:
    try:
        command = json.loads((cfg / "settings.json").read_text())["statusLine"]["command"]
        words = shlex.split(command)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        continue
    for word in words:
        path = Path(os.path.expanduser(os.path.expandvars(word)))  # ~/…, $HOME/… and ${HOME}/…
        if path.is_absolute() and path.is_file() and shell_script(path) and str(path.resolve()) not in found:
            found.append(str(path.resolve()))
        # (VS Code's wrapper, which has the snippet: the command after it is the
        # status line it wraps, one the snippet couldn't be added to)
        if path.name == "statusline.sh" and path.parent.name in ("talpy-den", "claude-status"):
            break
for path in found:
    print(path)
EOF
}

# Write the patched status line ($statusline) to stdout: add, or with "remove" strip, the snippet.
patched_statusline() {
  python3 -I - "$statusline" "$here/statusline-snippet.sh" "$1" <<'EOF'
import re, sys
path, snippet_path, mode = sys.argv[1:4]
text = open(path, encoding="utf-8").read()
block = re.compile(r"^# >>> (talpy-den|claude-widget) >>>\n.*?^# <<< \1 <<<\n", re.S | re.M)
text = block.sub("", text)
if mode == "add":
    snippet = open(snippet_path, encoding="utf-8").read()
    lines = text.splitlines(keepends=True)
    # input=$(cat), input="$(cat)", input=$(cat -): a line of its own (not
    # one that goes on with && or a \ at its end)
    reads = re.compile(r"""\s*input=("?)\$\(cat(\s+-)?\)\1\s*(;\s*)?(#.*)?$""")
    for i, line in enumerate(lines):
        if reads.match(line.rstrip("\n")):
            if not line.endswith("\n"):
                lines[i] = line + "\n"
            lines.insert(i + 1, snippet)
            break
    else:
        sys.exit(f"{path}: no 'input=$(cat)' line found; add statusline-snippet.sh by hand after it reads stdin")
    text = "".join(lines)
sys.stdout.write(text)
EOF
}

has_snippet() {  # the snippet is in the script $1 (under either of its names)
  grep -qF "$marker_start" "$1" || grep -qF "$legacy_marker_start" "$1"
}

apply_statusline() {
  local mode="$1" tmp
  tmp="$(mktemp)"
  if ! patched_statusline "$mode" > "$tmp"; then
    rm -f "$tmp"
    return 0
  fi
  if cmp -s "$tmp" "$statusline"; then
    rm -f "$tmp"
    echo "Status line already up to date: $statusline"
    return 0
  fi
  diff -u "$statusline" "$tmp" || true
  if confirm "Apply this change to $statusline?"; then
    # Written next to it, then moved over it in one step: Claude may run the
    # script at any moment, and must never find it half-written
    local target new
    target="$(realpath -e -- "$statusline")"
    if ! cp -p "$target" "$target.bak.$(date +%Y%m%d%H%M%S)" 2>/dev/null \
        || ! new="$(mktemp "$(dirname "$target")/.$(basename "$target").XXXXXX" 2>/dev/null)"; then
      echo "Can't write in $(dirname "$target"); add the snippet to $statusline by hand (statusline-snippet.sh)."
      rm -f "$tmp"
      return 0
    fi
    cat "$tmp" > "$new"
    chmod --reference="$target" "$new" 2>/dev/null || chmod 755 "$new"
    mv -f "$new" "$target"
    echo "Patched $statusline (backup next to it)."
  elif has_snippet "$statusline"; then
    echo "Skipped $statusline; its Talpy Den snippet stays as it was."
  else
    echo "Skipped $statusline; plan-usage bars stay empty until the snippet is added."
  fi
  rm -f "$tmp"
}

# The GNOME extension: built from this repo (gnome/build.sh), then installed
# and turned on. A running GNOME Shell only loads new extension code at the
# next login. It's built first, before anything is replaced: a GNOME Shell
# it doesn't run on, or a build that fails, leaves the installed one as it was.
build_gnome() {
  local major
  # GNOME Shell 43/44 load extensions the older way: build a converted copy
  major="$(gnome-shell --version 2>/dev/null | sed -nE 's/^GNOME Shell ([0-9]+).*/\1/p')"
  if [ -n "$major" ] && [ "$major" -ge 45 ] && [ "$major" -le 48 ]; then
    echo "GNOME Shell $major isn't supported: Talpy Den runs on GNOME Shell 43/44 and 49 or newer." >&2
    exit 1
  fi
  if [ -n "$major" ] && [ "$major" -lt 45 ]; then
    if [ "$major" -lt 43 ]; then
      echo "GNOME Shell $major is too old: Talpy Den needs GNOME Shell 43 or newer." >&2
      exit 1
    fi
    "$here/gnome/build.sh" --gnome43 >/dev/null
  else
    "$here/gnome/build.sh" >/dev/null
  fi
}

install_gnome() {
  local zip="$here/gnome/build/$uuid.shell-extension.zip"
  if [ -d "$HOME/.local/share/gnome-shell/extensions/$uuid" ]; then upgraded=1; else upgraded=0; fi
  gnome-extensions install --force "$zip"
  if gnome-extensions enable "$uuid" 2>/dev/null; then
    enabled=1
  else
    # not loaded yet (first install): turn it on for the next login
    enabled=0
    local list
    list="$(gsettings get org.gnome.shell enabled-extensions 2>/dev/null || echo "@as []")"
    case "$list" in
      *"'$uuid'"*) ;;
      "@as []"|"[]") gsettings set org.gnome.shell enabled-extensions "['$uuid']" || true ;;
      *) gsettings set org.gnome.shell enabled-extensions "${list%]}, '$uuid']" || true ;;
    esac
  fi
}

uninstall_gnome() {
  gnome-extensions uninstall "$uuid" 2>/dev/null || rm -rf "$HOME/.local/share/gnome-shell/extensions/$uuid"
  local list
  list="$(gsettings get org.gnome.shell enabled-extensions 2>/dev/null || true)"
  case "$list" in
    *"'$uuid'"*)
      list="$(printf '%s' "$list" | sed -e "s/, '$uuid'//; s/'$uuid', //; s/'$uuid'//")"
      gsettings set org.gnome.shell enabled-extensions "$list" || true ;;
  esac
}

# The chat pane's icon (Plasma). The pane is a window of plasmashell, so the
# taskbar would show Plasma's icon for it; a KWin window rule gives windows
# titled "… — Talpy Chat" a desktop file of their own (hidden from menus)
# with Talpy as its icon. It shows in System Settings → Window Rules.
pane_app="org.wzaielamri.talpyden.chat"
pane_desktop="${XDG_DATA_HOME:-$HOME/.local/share}/applications/$pane_app.desktop"
pane_rule="talpy-den-chat-pane"
pane_rule_keys=(
  "Description=Talpy Den: Talpy as the chat pane's icon"
  "title=— Talpy Chat" "titlematch=2"         # 2: the title has it (ChatPane.qml's title)
  "wmclass=plasmashell" "wmclassmatch=2"       # (org.kde.plasmashell on Wayland)
  "types=1"                                    # normal windows
  "desktopfile=$pane_app" "desktopfilerule=2"  # 2: force
)

kwin_rules() {  # the rules in kwinrulesrc, one per line
  kreadconfig6 --file kwinrulesrc --group General --key rules 2>/dev/null | tr ',' '\n' | sed '/^$/d'
}

set_kwin_rules() {  # $@: the rules, in order
  local IFS=,
  kwriteconfig6 --file kwinrulesrc --group General --key rules "$*"
  kwriteconfig6 --file kwinrulesrc --group General --key count "$#"
  gdbus call --session --dest org.kde.KWin --object-path /KWin --method org.kde.KWin.reconfigure >/dev/null 2>&1 || true
}

install_pane_icon() {
  command -v kwriteconfig6 >/dev/null && command -v kreadconfig6 >/dev/null || return 0
  mkdir -p "$(dirname "$pane_desktop")"
  # (Exec does nothing: the pane opens from the widget)
  cat > "$pane_desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Talpy Chat
Comment=The chat pane of the Talpy Den widget
Icon=$HOME/.local/share/plasma/plasmoids/$id/contents/pets/window.svg
Exec=true
NoDisplay=true
StartupNotify=false
EOF
  local kv rules
  for kv in "${pane_rule_keys[@]}"; do
    kwriteconfig6 --file kwinrulesrc --group "$pane_rule" --key "${kv%%=*}" "${kv#*=}"
  done
  mapfile -t rules < <(kwin_rules)
  if printf '%s\n' "${rules[@]}" | grep -qxF "$pane_rule"; then
    set_kwin_rules "${rules[@]}"  # (KWin reads the rule again)
  else
    set_kwin_rules "${rules[@]}" "$pane_rule"
    echo "The chat pane shows Talpy in the taskbar (a window rule: System Settings → Window Rules)."
  fi
}

uninstall_pane_icon() {
  rm -f "$pane_desktop"
  command -v kwriteconfig6 >/dev/null && command -v kreadconfig6 >/dev/null || return 0
  local kv rules=() rule found=0
  for kv in "${pane_rule_keys[@]}"; do
    kwriteconfig6 --file kwinrulesrc --group "$pane_rule" --key "${kv%%=*}" --delete
  done
  while IFS= read -r rule; do
    if [ "$rule" = "$pane_rule" ]; then
      found=1
    else
      rules+=("$rule")
    fi
  done < <(kwin_rules)
  if [ "$found" = 1 ]; then
    set_kwin_rules "${rules[@]}"
  fi
}

# The copies of the widget of the first name (in the panel, on the desktop,
# in the system tray) become Talpy Den where they are, with their settings:
# Plasma's layout file names the widget each copy is, so the old id changes
# to the new one there. plasmashell writes that file as it quits, so it's
# changed while plasmashell is stopped (the panel and desktop restart).
moved=0
move_legacy_applets() {
  local rc="${XDG_CONFIG_HOME:-$HOME/.config}/plasma-org.kde.plasma.desktop-appletsrc" n how="" backup
  [ -f "$rc" ] || return 0
  n="$(grep -cxF "plugin=$legacy_id" "$rc" || true)"
  [ "${n:-0}" -gt 0 ] || return 0
  confirm "Turn your $n Claude Status widget(s) into Talpy Den where they are, with their settings? (Plasma's panel and desktop restart for it)" || return 0
  if systemctl --user is-active --quiet plasma-plasmashell.service 2>/dev/null; then
    how=systemd
    systemctl --user stop plasma-plasmashell.service
  elif pgrep -xu "$UID" plasmashell >/dev/null 2>&1; then
    how=plain
    kquitapp6 plasmashell >/dev/null 2>&1 || true
    local tries=0
    while pgrep -xu "$UID" plasmashell >/dev/null 2>&1 && [ "$tries" -lt 50 ]; do
      sleep 0.2
      tries=$((tries + 1))
    done
  fi
  backup="$rc.bak.$(date +%Y%m%d%H%M%S)"
  cp -p "$rc" "$backup"
  python3 -I - "$rc" "$legacy_id" "$id" <<'EOF'
import sys
path, old, new = sys.argv[1:4]
lines = open(path, encoding="utf-8").read().split("\n")
for n, line in enumerate(lines):
    key, eq, value = line.partition("=")
    if eq and key == "plugin" and value == old:
        lines[n] = "plugin=" + new
    elif eq and key in ("extraItems", "knownItems", "hiddenItems", "shownItems"):  # (the system tray's lists)
        items = [new if item == old else item for item in value.split(",")]
        lines[n] = key + "=" + ",".join(item for k, item in enumerate(items) if item not in items[:k])
open(path, "w", encoding="utf-8").write("\n".join(lines))
EOF
  case "$how" in
    systemd) systemctl --user start plasma-plasmashell.service ;;
    plain) (command -v kstart >/dev/null && kstart plasmashell || setsid -f plasmashell) >/dev/null 2>&1 || true ;;
  esac
  moved="$n"
  echo "Your $n Claude Status widget(s) are now Talpy Den, where they were and with their settings (Plasma's layout before: $backup)."
}

# The widget/extension an earlier version installed under its first name:
# taken out, with the chat pane's window rule and desktop file. (A widget's
# places and settings carry over with move_legacy_applets, an extension's
# settings here.)
remove_legacy() {
  if [ "$target" = gnome ]; then
    [ -d "$HOME/.local/share/gnome-shell/extensions/$legacy_uuid" ] || return 0
    # (its settings, unless the new one has some already)
    if command -v dconf >/dev/null && [ -z "$(dconf dump "$gsettings_path/" 2>/dev/null)" ]; then
      dconf dump "$legacy_gsettings_path/" 2>/dev/null | dconf load "$gsettings_path/" 2>/dev/null || true
    fi
    gnome-extensions disable "$legacy_uuid" 2>/dev/null || true
    gnome-extensions uninstall "$legacy_uuid" 2>/dev/null || rm -rf "$HOME/.local/share/gnome-shell/extensions/$legacy_uuid"
    local list
    list="$(gsettings get org.gnome.shell enabled-extensions 2>/dev/null || true)"
    case "$list" in
      *"'$legacy_uuid'"*)
        list="$(printf '%s' "$list" | sed -e "s/, '$legacy_uuid'//; s/'$legacy_uuid', //; s/'$legacy_uuid'//")"
        gsettings set org.gnome.shell enabled-extensions "$list" || true ;;
    esac
    echo "Replaced the old Claude Status extension."
    return 0
  fi
  rm -f "${XDG_DATA_HOME:-$HOME/.local/share}/applications/$legacy_pane_app.desktop"
  if command -v kreadconfig6 >/dev/null && command -v kwriteconfig6 >/dev/null; then
    local key rules=() rule found=0
    while IFS= read -r rule; do
      if [ "$rule" = "$legacy_pane_rule" ]; then found=1; else rules+=("$rule"); fi
    done < <(kwin_rules)
    if [ "$found" = 1 ]; then
      for key in Description title titlematch wmclass wmclassmatch types desktopfile desktopfilerule; do
        kwriteconfig6 --file kwinrulesrc --group "$legacy_pane_rule" --key "$key" --delete
      done
      set_kwin_rules "${rules[@]}"
    fi
  fi
  [ -d "$HOME/.local/share/plasma/plasmoids/$legacy_id" ] || return 0
  kpackagetool6 -t Plasma/Applet -r "$legacy_id" || true
  if [ "$moved" = 0 ] && [ "$uninstall" = 0 ]; then
    echo "Replaced the old Claude Status widget: add Talpy Den to your panel (right-click the panel → Add Widgets…)."
  fi
}

mapfile -t statuslines < <(find_statuslines)

# The permission hook (pane.py --relay status|on|off): with it, the widget's
# rows, chat pane and notifications can answer Claude's permission prompts.
# The live hook (pane.py --live status|on|off): live mode, each step of each
# chat as it happens. Prints what happened; "status" prints True or False.
hook() {
  python3 -I "$here/package/contents/code/pane.py" "--$1" "$2" 2>/dev/null \
    | python3 -I -c 'import json, sys
a = json.load(sys.stdin)
print(a["on"] if "on" in a else a.get("message") or "")' 2>/dev/null || true
}
relay() { hook relay "$1"; }
live() { hook live "$1"; }

if [ "$uninstall" = 1 ]; then
  if [ "$target" = gnome ]; then
    uninstall_gnome
  else
    kpackagetool6 -t Plasma/Applet -r "$id" || true
    uninstall_pane_icon
  fi
  remove_legacy
  # The snippet stays while something else still reads what it saves
  others=()
  [ "$target" != plasma ] && [ -d "$HOME/.local/share/plasma/plasmoids/$id" ] && others+=("the Plasma widget")
  [ "$target" != gnome ] && [ -d "$HOME/.local/share/gnome-shell/extensions/$uuid" ] && others+=("the GNOME extension")
  vscode_has wzaielamri.talpy-den && others+=("the VS Code extension")
  if [ "${#others[@]}" -gt 0 ]; then
    echo "Kept the status-line snippet: ${others[*]} still uses it."
  else
    for statusline in "${statuslines[@]}"; do
      [ -f "$statusline" ] && has_snippet "$statusline" && apply_statusline remove
    done
    # (the permission hook too: nothing would answer what it hands on; and
    # the live hook: nothing would read what it notes)
    relay off
    live off
  fi
  echo "Uninstalled. Cached data is in ${XDG_CACHE_HOME:-$HOME/.cache}/talpy-den (safe to delete)."
  # (left as the cache is: the hooks' scripts, and dictation's speech engine
  # and models if it was set up, hundreds of MB)
  data="${XDG_DATA_HOME:-$HOME/.local/share}/talpy-den"
  if [ -d "$data" ] && [ "${#others[@]}" -eq 0 ]; then
    echo "The hooks and dictation's speech engine and models (if you set it up) are in $data (safe to delete)."
  fi
  exit 0
fi

# 1. Widget (without Python bytecode caches a test run may have left in it)
find "$here/package" -name __pycache__ -type d -prune -exec rm -rf {} +
# (and the compiled copies an older Talpy Den kept in the cache: now in its data folder)
rm -rf "${XDG_CACHE_HOME:-$HOME/.cache}/talpy-den/pycache"
if [ "$target" = gnome ]; then
  build_gnome
  remove_legacy
  install_gnome
else
  if [ -d "$HOME/.local/share/plasma/plasmoids/$id" ]; then
    kpackagetool6 -t Plasma/Applet -u "$here/package"
    upgraded=1
  else
    kpackagetool6 -t Plasma/Applet -i "$here/package"
    upgraded=0
  fi
  move_legacy_applets  # (with the new widget installed, so plasmashell finds it as it starts)
  remove_legacy
  install_pane_icon
fi

# 2. Status-line snippet (feeds plan limits and per-session context)
command -v jq >/dev/null || echo "warning: jq not found; the snippet needs it" >&2
if [ "${#statuslines[@]}" -eq 0 ]; then
  echo "No Claude profile runs a status-line script (statusLine in settings.json)."
  echo "Add the contents of statusline-snippet.sh to your status-line command, after it reads stdin into \$input."
fi
for statusline in "${statuslines[@]}"; do
  if [ -f "$statusline" ]; then
    apply_statusline add
  else
    echo "Status-line script not found: $statusline"
  fi
done

# 3. Permission hook (opt-in; the Plasma widget answers what it hands on)
if [ "$target" = plasma ]; then
  if [ "$(relay status)" = True ]; then
    relay on >/dev/null  # (its copy brought up to date)
    echo "Permission prompts can be answered from Talpy Den (the hook is up to date)."
  elif confirm "Answer Claude's permission prompts from Talpy Den too? (adds a hook to each Claude profile's settings.json; Talpy Den's settings turn it off)"; then
    relay on
  else
    echo "Skipped the permission hook: Talpy Den's settings can turn it on (Answer permission prompts from Talpy Den)."
  fi
fi

# 4. Live mode (opt-in): each step of each chat as it happens
if [ "$target" = plasma ]; then
  if [ "$(live status)" = True ]; then
    live on >/dev/null  # (its copy brought up to date)
    echo "Live mode is on: chats show each step as it happens (the hook is up to date)."
  elif confirm "Show each step of your chats as it happens (live mode)? (adds a hook to each Claude profile's settings.json that Claude doesn't wait for; Talpy Den's settings turn it off)"; then
    live on
  else
    echo "Skipped live mode: Talpy Den's settings can turn it on (Live mode: show each step as it happens)."
  fi
fi

vscode_has wzaielamri.claude-status &&
  echo "The VS Code extension is now Talpy Den too: install the new one and remove \"Claude Status\" from VS Code's extensions."
echo
if [ "$target" = gnome ]; then
  if [ "$upgraded" = 1 ]; then
    echo "Extension upgraded. GNOME Shell loads the new version when you log out and back in."
  elif [ "$enabled" = 1 ]; then
    echo "Extension installed and turned on: look for Talpy in the top bar."
  else
    echo "Extension installed. Log out and back in: Talpy then shows in the top bar."
  fi
elif [ "$moved" != 0 ]; then
  echo "Widget installed in place of Claude Status."
elif [ "$upgraded" = 1 ]; then
  echo "Widget upgraded. If the panel still shows the old version: systemctl --user restart plasma-plasmashell"
else
  echo "Widget installed. Right-click the panel → Add Widgets… → search \"Talpy Den\"."
fi
