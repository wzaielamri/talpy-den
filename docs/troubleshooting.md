# Troubleshooting

- **"No plan usage yet":** plan usage comes from the status line, so it shows up after the next reply in a chat of that account (in VS Code's Claude Code panel, which runs no status line, Talpy Den asks Claude Code for it while the chat works). If it never does, check that `jq` is installed and that the snippet is in your status-line script (`./install.sh` adds it). Saved snapshots are in `~/.cache/talpy-den/statusline/`.
- **Talpy Den isn't in the widget list:** it needs Plasma 6. Check that it's installed: `kpackagetool6 -t Plasma/Applet --list | grep claude`.
- **The old version is still showing after an update:** `systemctl --user restart plasma-plasmashell`.
- **"Can't find the claude command":** Talpy Den looks on PATH, in the usual install folders and on your login shell's PATH. If Claude is somewhere else, add its folder to PATH in `~/.profile` (not only `~/.bashrc`) and log in again.
- **A chat didn't go on right after the usage limit reset:** a chat whose turn the limit ended still looks at work while commands it started in the background run (a server, say), and Claude can't take a message into it then. Its go-on waits for them to finish (its queued line says until when) and, if they still run 15 minutes after its time, ends them and goes on; its line's **Start it now** ends them at once and goes on. A notification says so when it starts waiting and when it ends them, and `~/.cache/talpy-den/go-on.log` keeps a dated line of each (its last 200 lines).
- **Clicking a chat doesn't switch to its tab:** tab switching works with Konsole and tmux. With other terminals the window is raised.
- **An SSH host refuses the login:** the checks log in without a terminal, so they need key-based login (load your key with `ssh-add`) or a connection you logged in with: click **Log in…** at the host (Plasma) and type your password where `ssh` asks for it. The host also needs `python3`.
- **Something else:** run the widget in its own window to see its messages: `plasmawindowed org.wzaielamri.talpyden`. You can also run the status script on its own: `python3 -I package/contents/code/talpy_den.py --pretty`.

Issues and ideas are welcome on the [issue tracker](https://github.com/wzaielamri/talpy-den/issues).

## Limitations

- `sessions/*.json` is an internal Claude Code format and may change in a future version. The backend fails soft: Talpy Den shows the error instead of breaking.
- Plan usage only refreshes when a chat of that account in a terminal gets a reply (that's when the status line runs), when Claude Code fetches it itself (`/usage`), or, while a chat of that account works with numbers more than 5 minutes old (VS Code's Claude Code panel), when Talpy Den has Claude Code fetch it (at most every 5 minutes, or what *Fetch plan usage older than* says). The popup shows how old the numbers are and treats windows whose reset time has passed as reset.
- Token totals cover each machine's own transcripts (an SSH host shows its own). Plan limits are account-wide.
- An SSH host's chats in a terminal can't be brought to your screen; Talpy Den shows them and opens background and finished chats in a new terminal.
- Jumping to the right tab is built for KDE Plasma (KWin) with Konsole. In other terminals the window is raised but the tab isn't selected.
