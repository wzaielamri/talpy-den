# When Claude Code updates

Talpy Den reads Claude Code's files, talks to its background service, runs its commands and matches its
wording. Most of this is not a documented interface, so a new Claude Code version can change any of it without
notice. This page lists each of these reliances. Go through it before or after a Claude Code update to check
that Talpy Den still works.

Sections: [Sessions](#sessions) · [Jobs](#jobs) · [Service socket](#service-socket) · [CLI](#cli) ·
[Transcripts](#transcripts) · [Hooks](#hooks) · [Settings](#settings) · [Status line](#status-line) · [VS Code
extension](#vs-code-extension) · [Wording](#wording) · [SSH hosts and containers](#ssh-hosts-and-containers) ·
[Other](#other)

## How to use it

- Each item names what Talpy Den relies on, then: **Used in** (the files, and the functions or constants in
  them), **Check** (how to see it on a new version), **Breaks** (what goes wrong if it changes) and **Test**
  (the tests that cover it, or "no test").
- Some tests write their own fixtures. They check how Talpy Den reads a format, not what Claude Code writes,
  so they can't tell you that Claude Code changed. The items say where this is the case.
- Start with the quick reads. They grep Claude Code's binary for a word, read a file with `jq`, or read
  `claude --help`. A count of 0 means the word is gone or renamed: read the code around it before you change
  anything.
- Next, do the items that need a throwaway chat. Start with the ones that touch what the release notes
  mention.
- `python3 -I $TD/talpy_den.py | jq .errors` names every status, kind or job state Claude Code writes that
  Talpy Den doesn't know yet.
- Background Stop only runs on the versions it was checked on (`BG_STOP_FROM` up to `BG_STOP_BEFORE` in
  talpy_den.py). Raise `BG_STOP_BEFORE` only after the attach item passes.
- When something changed: fix the code, the item and the test fixture, then the "Last checked" line at the
  end.
- Python files are in `package/contents/code/`, QML and `.mjs` files in `package/contents/ui/`. The tests are
  in `tests/` (`python3 -m unittest discover -s tests`), `vscode/test/` (`npm test` in `vscode/`) and
  `gnome/tests/`.

### Set up the quick reads

Run these from the repository's root:

```bash
TD=$PWD/package/contents/code        # Talpy Den's Python code
B=$(readlink -f "$(type -P claude)") # Claude Code itself (native: ~/.local/share/claude/versions/<version>)
C=~/.claude                          # the profile you check (~/.claude-NAME for another one)
A=$C/.claude.json                    # its account file (a plain, unlinked ~/.claude uses ~/.claude.json)
SNAP=~/.cache/talpy-den/statusline/$(basename "$(readlink -f "$C")")   # its status-line snapshots
has() { for s in "$@"; do printf '%6s  %s\n' "$(LC_ALL=C grep -a -c -F -- "$s" "$B")" "$s"; done; }  # 0: gone
td() {  # td 'EXPR' ARGS: a talpy_den call on that profile (p), with ARGS in a
  python3 -I -c 'import sys; sys.path.insert(0, sys.argv[1]); import talpy_den as t
p = [x for x in t.discover_profiles(t.Path.home()) if x.key == sys.argv[2]][0]; a = sys.argv[4:]
print(eval(sys.argv[3]))' "$TD" "$(basename "$(readlink -f "$C")")" "$@"
}
```

- `type -P` looks only at PATH. Don't use `command -v`: if a shell function or alias is named `claude`, it
  makes `$B` wrong and every count comes out empty. If claude isn't on PATH, use
  `B=$(readlink -f ~/.local/bin/claude)`.
- With an npm install, `$B` is its `cli.js`. The greps work the same on it.
- For long patterns, put `LC_ALL=C` in front of `grep -a -o`, or the match may fail on the binary.

### Throwaway chats

Some checks need Claude Code to actually do something. Follow these rules for those chats:

- Work in a scratch folder, never a real project. Keep one folder for the whole check: `--bg` only works in a
  trusted folder and never asks, so trust it once.
- Use Haiku (`--model haiku`) unless the item is about a model or an effort.
- Start chats with `--setting-sources project,local`, so your own settings (hooks, status line) stay out.
  Items about the status line, the relay or the live hook need your settings: start those chats without this
  flag, as the item says.
- **Never run `/model` or `/effort` in any chat, a throwaway one included.** They save the pick as your
  default for every new chat, in your global settings, whatever the chat was started with (`--setting-sources`
  doesn't stop it). Use `--model` or `--effort` on the command line, or Talpy Chat's own picker. Treat
  `/config` the same way: use it only where an item asks, and put the option back afterwards.
- Options given to `--bg --resume` can make a copy of the chat, and some items check exactly that. Stop and
  remove every chat and copy you make.

```bash
S=$(mktemp -d /tmp/talpy-check.XXXX)               # the scratch folder
M=$(printf %s "$S" | sed 's/[^A-Za-z0-9]/-/g')    # its folder's name in $C/projects
export CLAUDE_CONFIG_DIR=$C          # only for a profile other than a plain ~/.claude
# a throwaway chat; the first time, answer Yes to the trust question
(cd "$S" && CLAUDE_CODE_DISABLE_AGENT_VIEW=1 claude --model haiku --setting-sources project,local)
# a throwaway background chat: prints its short id
(cd "$S" && claude --bg --model haiku --setting-sources project,local 'say hi')
SHORT=<that id>; ID=$(jq -r .sessionId $C/jobs/$SHORT/state.json); T=$C/projects/$M/$ID.jsonl
# a terminal chat's id: jq -r .sessionId $C/sessions/<its pid>.json
# the newest transcript: T=$(ls -t $C/projects/$M/*.jsonl | head -1)
```

Clean up afterwards:

```bash
claude stop $SHORT; claude rm $SHORT   # each background chat and copy you started
rm -rf "$S" "$C/projects/$M"           # the scratch folder and its chats' transcripts
```

Then revoke the scratch folder's trust in the Permissions tab. Claude's own cleanup removes the rest it made
(plans, file history, task lists).

## Sessions

- [ ] **Session registry.** Claude writes one file per process, `$C/sessions/<pid>.json`. Fields read: `pid`,
  `procStart`, `sessionId`, `cwd`, `name`, `kind`, `entrypoint`, `status`, `waitingFor`, `statusUpdatedAt`,
  `updatedAt`, `startedAt` (epoch ms), `version`, `tmux`, `jobId`, `spare`, `parkedJobId`. A folder with
  `sessions/` or `projects/` counts as a profile.
  - Used in: talpy_den.py live_entries_all, live_row, make_session, own_session, wake_settle, find_chat_live,
    is_profile_dir.
  - Check: right after you start a throwaway chat:

    ```bash
    P=$(pgrep -n -x claude)
    jq '{pid,procStart,sessionId,cwd,name,kind,entrypoint,status,waitingFor,statusUpdatedAt,updatedAt,startedAt,version}' $C/sessions/$P.json
    ```

    Every key should be there, the file named after the pid, and the times in ms.
  - Breaks: chats vanish from every list, or rows lose their name, folder and times. Stop, Interrupt and Reply
    say "That chat isn't running any more".
  - Test: SessionTests.test_session_states_and_filtering (test_talpy_den.py), LiveAttributionTests
    (test_chats.py).
- [ ] **procStart guards against PID reuse.** `procStart` equals field 22 (starttime, in clock ticks) of
  `/proc/<pid>/stat`, compared as a string. The same guard reads `supervisorProcStart` and each worker's
  `procStart` in `daemon.status.json`.
  - Used in: talpy_den.py proc_start_time, is_alive, process_gone, end_leftovers, service_config_dir,
    parked_row.
  - Check: `jq .procStart $C/sessions/$P.json; awk '{print $22}' /proc/$P/stat`. The two should be equal.
  - Breaks: if the unit or field changes, every chat counts as dead: no rows, no Stop or Interrupt. If the
    field goes, the guard is lost silently (a missing `procStart` counts as alive).
  - Test: SessionTests.test_liveness (test_talpy_den.py), ChatStopTests.test_profile_and_pid_reuse
    (test_jump.py).
- [ ] **status values.** `busy`, `shell` (the turn is over but a background shell still runs), `idle` and
  `waiting`, read from the 2.1.304 binary into KNOWN_VALUES. An unknown value counts as idle and is reported
  in `errors`.
  - Used in: talpy_den.py session_state, KNOWN_VALUES, note_unknown, unknown_values_text, interrupt_chat,
    interrupt_background, chat_at_work.
  - Check: `python3 -I $TD/talpy_den.py | jq .errors` should not say Claude Code "writes something Talpy Den
    doesn't know yet". In a throwaway chat, `watch -n1 "jq -c '{status,waitingFor}' $C/sessions/*.json"`:
    `busy` during a prompt, `shell` after a turn that left a `run_in_background` `sleep 60` running, `idle` at
    the end.
  - Breaks: chats show as idle while working, or the reverse. Interrupt sends Ctrl+C at an idle prompt, which
    quits Claude.
  - Test: StateMappingTests.test_interactive, NewClaudeValuesTests (test_talpy_den.py).
- [ ] **waitingFor reasons.** `permission prompt`, `goal proposal`, `sandbox request`, `worker request`,
  `input needed` (a question, MCP elicitation too) and `dialog open` (a dialog you opened yourself,
  deliberately not counted as waiting).
  - Used in: talpy_den.py WAITING_REASONS, session_state, live_row, QUESTION_WAIT, PERMISSION_WAITS.
  - Check:

    ```bash
    has 'permission prompt' 'goal proposal' 'sandbox request' 'worker request' 'input needed' 'dialog open'
    ```

    To spot new reasons, watch `jq .waitingFor` during a permission prompt and during an AskUserQuestion.
  - Breaks: a renamed reason shows raw. If `dialog open` is renamed, chats with `/config` open show as needing
    you. If `input needed` is renamed, questions can't be answered from rows or Talpy Chat.
  - Test: StateMappingTests.test_interactive, test_own_dialog_is_not_waiting (test_talpy_den.py).
- [ ] **Waiting while a dialog shows.** While Claude's dialog shows, the session file has `status` `waiting`
  and `waitingFor` `permission prompt` (or `input needed` for AskUserQuestion), and leaves `waiting` once you
  answer. The permission hook finds that file by Claude's pid, under `$CLAUDE_CONFIG_DIR`, `~/.claude` or
  `~/.claude*`. Rows match a relayed request to a session by `sessionId` (the newest request per session), and
  only to a row that waits.
  - Used in: permission_hook.py session_file, session_status, main; talpy_den.py note_permissions,
    permission_requests.
  - Check: while a throwaway chat shows a permission dialog, and again during an AskUserQuestion,
    `jq -c '{pid,status,waitingFor}' $C/sessions/*.json`. Look once more after you answer.
  - Breaks: if the status word changes, the hook leaves after 5 s (nothing is relayed) or stays for hours
    after the chat was answered. If `waitingFor` is renamed, rows skip the relayed prompt, and a question
    shows as a permission or not at all.
  - Test: HookTests.test_answered_in_the_chat, PermissionViewTests.test_rows_waiting_for_a_permission,
    test_rows_with_a_question (test_pane.py).
- [ ] **kind values.** `interactive`, `bg`, `daemon` and `daemon-worker`; only `interactive` and `bg` are
  chats. `spare: true` marks a pre-warmed process and `parkedJobId` a terminal parked on a job; neither is a
  chat (`claude agents` hides both). The front ends rely on `bg` for the Background tag, attach, Stop as
  `claude stop`, a reply that answers what the chat asks, and Talpy Chat as the chat's window; on
  `interactive` for ending a chat.
  - Used in: talpy_den.py SESSION_KINDS, live_row, find_chat_live, live_background, end_for_handover,
    background_work, wake_settle; chatpick.py set_now; vscode/src/shared/model.ts canEndChat, shared/pane.ts
    chatWhere, replyAnswers, chatPane.ts windowTerminal, actions.ts stop; SessionRow.qml, ChatPane.qml,
    main.qml; gnome/extension/ui/sessionRow.js, logic.js openHint.
  - Check: with a throwaway background chat running and `claude attach $SHORT` open,
    `jq -c '{kind,spare,parkedJobId,jobId}' $C/sessions/*.json; has parkedJobId`.
  - Breaks: a renamed kind drops those chats from every list. The service's workers get listed as chats, an
    attached terminal shows as a second copy, or background chats are handled as terminal chats (Stop kills
    them, no attach).
  - Test: SessionTests.test_parked_and_finished_jobs_listed, test_session_states_and_filtering,
    StateMappingTests.test_interactive (test_talpy_den.py); vscode/test/pane.test.ts "the tag under a chat's
    name says where it runs"; vscode/test/openIn.test.ts "a chat with a process can be stopped, whatever it's
    doing; a working one interrupted"; gnome/tests/test_logic.js 'stopping: background sessions, and chats
    with a process; interrupting in tmux'.
- [ ] **entrypoint `claude-vscode`.** It marks a chat in the Claude Code panel. Talpy Den assumes such a chat
  runs in print mode and that the panel starts it again with your next message. So the chat has no terminal to
  find or type into, opens through the extension's link, can be stopped (its tab survives), can't be moved to
  the panel, isn't ended by a go-on or hand-over, and is tagged "Claude Code panel".
  - Used in: talpy_den.py reply_route, stop_chat, end_for_handover, background_work, kept_step, live_row,
    add_remote_commands; vscode/src/actions.ts open, openSystem, stop, sendPlanFeedback; chatPane.ts
    windowTerminal; shared/pane.ts chatWhere; shared/model.ts canMoveToClaudeCode, handoverTarget, goOnAt;
    accountSwitch.ts switchTo; main.qml, SessionRow.qml, ChatPane.qml; gnome/extension/logic.js openHint,
    stopTip, stopQuestion, indicator.js remoteShow.
  - Check: with a throwaway chat in VS Code's Claude panel and one in a terminal,
    `jq -r .entrypoint $C/sessions/*.json | sort | uniq -c`. Only the panel chat should say `claude-vscode`.
  - Breaks: panel chats get handled as terminal chats: SIGTERM (an error in the tab), replies that go nowhere,
    and Keep going or a hand-over ending a tab still in use. Tags are wrong, and Default account no longer
    protects working panel chats from the reload.
  - Test: ChatStopTests.test_vscode_chat_gets_sigint (test_jump.py),
    HandoverTests.test_vscode_and_busy_sessions_stay (test_tasks.py); vscode/test/pane.test.ts "the tag under
    a chat's name says where it runs"; vscode/test/openIn.test.ts "a chat running in a terminal can move to a
    Claude Code panel, when Claude Code is on its account".
- [ ] **Fields that pick a chat's route.** `tmux` (`session:@window.%pane`, the pane id after the last `.`;
  the tmux server's socket comes from the process's `TMUX` variable), `jobId`, `parkedJobId`, `spare`, `name`,
  `cwd`, and `status` `shell` (the row's reason is "background shell", and Plasma doesn't hold back a new
  message then).
  - Used in: jump.py jump, find_session, jump_job, jump_terminal, tmux_client_pids, tmux_pane_of; pane.py
    send_now, type_in, tmux_base; talpy_den.py live_row, reply_route, interrupt_chat, tmux_socket,
    interrupt_background, find_chat_live; vscode/src/shared/pane.ts chatWhere, stopOf, chatPane.ts
    windowTerminal; ChatPane.qml where, canStop; SessionRow.qml bgInterrupt.
  - Check: in a throwaway chat inside tmux, compare `jq .tmux $C/sessions/<pid>.json` with
    `tmux display -p '#{session_name}:#{window_id}.#{pane_id}'`. Then read
    `jq -c '{kind,entrypoint,tmux,jobId,parkedJobId,spare,status,name}' $C/sessions/*.json` with chats in
    tmux, the panel, the background and an attached terminal.
  - Breaks: replies go to the clipboard instead of being typed, Interrupt is missing or presses Ctrl+C in the
    wrong pane, Stop refuses ("doesn't run in tmux"), and messages are held at the wrong time.
  - Test: TmuxFlagTests.test_rows_say_whether_a_chat_runs_in_tmux (test_talpy_den.py);
    FindSessionTests.test_live_and_parked, test_routing, SmallJumpTests.test_tmux_on_the_chats_own_server,
    ChatStopTests.test_interrupt_presses_ctrl_c_in_its_tmux_pane (test_jump.py); SendTests.test_tmux,
    test_vscode (test_pane.py); vscode/test/pane.test.ts "Stop on the working line: …".
- [ ] **Claude Code's version.** Talpy Den never parses `claude --version`. It reads `X.Y.Z` from the
  session's `version`, the job's `cliVersion` and the attach answer's `workerCliVersion`, and compares it as a
  tuple. The version gates background Stop (`BG_STOP_FROM` 2.1.318 up to `BG_STOP_BEFORE` 2.2) and is named in
  the unknown-values message.
  - Used in: talpy_den.py bg_stop_known, version_key, interrupt_background, esc_through_attach, live_row,
    note_unknown.
  - Check:

    ```bash
    claude --version
    jq -r .version $C/sessions/*.json | sort -u
    jq -r .cliVersion $C/jobs/*/state.json | sort -u
    ```

    They should agree, with no suffix.
  - Breaks: a suffix (`2.2.0-beta`) or a renamed field hides Stop for background chats, which is safe. A new
    2.1.x with a changed attach protocol still passes the version check, which is not (see the attach item).
  - Test: BackgroundStopTests.test_the_claude_code_versions_it_was_checked_on,
    test_rows_say_whether_stop_can_interrupt_a_background_chat,
    NewClaudeValuesTests.test_new_values_are_named_with_the_version (test_talpy_den.py).
- [ ] **A process's profile.** A process belongs to the profile its `CLAUDE_CONFIG_DIR` names in
  `/proc/<pid>/environ` (else `$HOME/.claude`). A process started through a link follows the link when it is
  switched: its next status write lands in the other profile's `sessions/`, and the old file stays until it
  exits. The entry with the newer `statusUpdatedAt`/`updatedAt` wins.
  - Used in: talpy_den.py process_config_dir, live_entries_all, own_session, shown_row.
  - Check: start a throwaway chat with `CLAUDE_CONFIG_DIR=~/.claude` while `~/.claude` links to profile A.
    Switch the link to B and send a prompt. Then `ls -l ~/.claude-*/sessions/<pid>.json` and compare
    `jq .statusUpdatedAt` in both files.
  - Breaks: one chat shows under two accounts or under the wrong one, and snapshots and limits go to the wrong
    account.
  - Test: LiveAttributionTests.test_same_process_in_two_profiles_listed_once_where_it_runs,
    test_unknown_config_dir_keeps_the_file_profile, test_default_config_dir_from_the_process_home
    (test_chats.py).
- [ ] **A session's own state fields.** Some sessions write `state`, `tempo`, `needs` and `detail` into their
  own entry. Talpy Den lays these over the job's `state.json`.
  - Used in: talpy_den.py live_row.
  - Check: while a background chat runs,
    `jq 'with_entries(select(.key|test("^(state|tempo|needs|detail)$")))' $C/sessions/*.json`.
  - Breaks: nothing if Claude stops writing them (the job record is used). If they get another meaning, the
    row's state is wrong.
  - Test: no test.
- [ ] **Session files are written at every change.** Claude rewrites `sessions/<pid>.json` (close-write or
  rename) when a chat starts or ends, starts working, waits or ends its turn, and after you answer or
  interrupt it in its terminal. live.py, its host watcher and the VS Code extension wake on those writes.
  - Used in: live.py session_dirs, Watch (WATCH_MASK), wait; vscode/src/live.ts sessionDirs, LiveWatch.
  - Check: `inotifywait -m -e close_write,moved_to,delete $C/sessions` (from inotify-tools) while a throwaway
    chat starts, works, asks a permission, ends its turn and quits: one event at each step. Without
    inotify-tools, run `python3 -I $TD/live.py --wait --timeout 60` in a loop.
  - Breaks: nothing visible here: rows and notifications fall back to the poll pace, and nothing warns (VS
    Code's `healthy` stays true). A host's prompts reach Talpy Chat only at the host's next check (every 30
    s).
  - Test: WaitTests.test_a_session_file_wakes_it_at_once, test_first_answer_then_only_changes (test_live.py);
    vscode/test/live.test.ts "the sessions folders to watch: each profile's, once", "the watcher: a session
    file asks for a check at once, a live file is handed on".

## Jobs

- [ ] **Job records.** A background job's record is `$C/jobs/<short>/state.json`, the short id 8 hex
  characters. For a chat started or woken with `--bg`/`--resume`, it is the first 8 characters of the session
  id, so Talpy Den opens `jobs/<id[:8]>/state.json` directly.
  - Used in: talpy_den.py read_job, job_dirs, newest_job_records, go_on_with, note_moved, live_row;
    chatpick.py job_record; sharing.py chat_jobs.
  - Check: after a throwaway background chat, `ls $C/jobs/` and
    `jq -r .sessionId $C/jobs/$SHORT/state.json | cut -c1-8` should print the folder's name. Do the same after
    `claude --bg --resume $ID 'hi'`.
  - Breaks: a go-on can't find `respawnFlags` and passes options, so Claude starts a copy with a new id and
    loses the mode and effort. Talpy Chat treats the chat as having no job, and `movedFrom.at` goes missing.
  - Test: ContinueAfterResetTests.test_it_goes_on_in_its_own_permission_mode,
    MovedChatTests.test_its_row_says_it_moved_and_a_hide_follows_it (test_tasks.py).
- [ ] **Job lifecycle.** `state` is one of `working`, `running`, `blocked`, `done`, `failed`, `stopped`;
  `tempo` one of `active`, `blocked`, `idle`. The tempo is written at every turn's end; the state only for a
  turn that ended by itself, so a stopped turn keeps `working`. `blocked` stays after you answer, with tempo
  `active` again. A worker that dies mid-turn keeps tempo `active`, and the idle service retires workers, so a
  blocked job can have no process. `needs` and `detail` are one-line texts. These rules mirror
  `claude agents --all`. The front ends key colour, pose, sound and notification text on `failed` and
  `stopped`.
  - Used in: talpy_den.py session_state, parked_job_state, job_finished, FINISHED_JOB_STATES, KNOWN_VALUES,
    live_row, parked_row, finish_row; vscode/src/away.ts; FocusLine.qml, Pet.qml, SessionRow.qml,
    SearchResults.qml, main.qml; gnome/extension/logic.js, notifier.js, ui/pets.js, ui/sessionRow.js.
  - Check: start a throwaway background chat with 'run sleep 5, then say done'. Run
    `watch -n0.5 "jq -c '{state,tempo,needs,detail,updatedAt}' $C/jobs/$SHORT/state.json"` and compare with
    `claude agents --all` at each step. After `claude stop $SHORT` the state should be `stopped`; one started
    with `--model no-such-model` should end `failed`. Then `python3 -I $TD/talpy_den.py | jq .errors`.
  - Breaks: background chats show as working forever, done while waiting for you, failed when settled, or
    hidden. Failed and stopped ones show as plain Done: no red dot, sad pose, sound or notification.
  - Test: StateMappingTests, ParkedJobTests, NewClaudeValuesTests (test_talpy_den.py);
    vscode/test/away.test.ts "coming back after a while sums up what happened".
- [ ] **needs `send a prompt to start`.** This exact text marks a background session dispatched or woken
  without a prompt (`idle — send a prompt to start`). It counts as idle and isn't listed when parked.
  - Used in: talpy_den.py NOT_STARTED, session_state, parked_job_state, start_background.
  - Check: `has 'send a prompt to start'`. Live: stop a throwaway background chat, run
    `claude --bg --resume $ID` with no prompt, then `jq .needs $C/jobs/$SHORT/state.json`.
  - Breaks: woken idle chats show as waiting for you with that text, and parked ones get listed.
  - Test: StateMappingTests.test_background_job_not_started, ParkedJobTests.test_not_started_hidden
    (test_talpy_den.py).
- [ ] **Recurring jobs.** A job is recurring when `routine` isn't null, `selfWake` is true, `inFlight.kinds`
  contains `session_cron`, or `intent`/`initialPrompt` starts with `/loop`. `inFlight.tasks > 0` means a
  background task's notification is about to wake the job (idle for only 15–100 ms). Read from 2.1.300.
  - Used in: talpy_den.py is_recurring, session_state, parked_job_state.
  - Check: `has session_cron selfWake`. Live: a throwaway background chat with '/loop 1m say hi', then
    `jq '{routine,selfWake,inFlight,intent,initialPrompt}' $C/jobs/$SHORT/state.json` between runs. Stop it
    afterwards.
  - Breaks: `/loop` and routine jobs show as done between runs and drop off after 24 h, or a settled chat
    shows as working.
  - Test: RecurringTests.test_loop_jobs, test_parked_recurring_job_between_runs (test_chats.py),
    StateMappingTests.test_background_still_at_work_with_an_idle_tempo_or_status (test_talpy_den.py).
- [ ] **Other job fields.** `createdAt` and `updatedAt` (ISO or epoch), `name`, `displayIntent`, `intent` (the
  row's name), `cwd`, `sessionId`, and `linkScanPath` (there when the job had a transcript, so a finished job
  whose transcript is gone is hidden). `updatedAt` also picks the newest copy of a record written through a
  switched link.
  - Used in: talpy_den.py parked_row, parked_job_state, newest_job_records, read_job, note_moved,
    add_remote_commands, attach_command.
  - Check:

    ```bash
    jq '{createdAt,updatedAt,name,displayIntent,intent,cwd,sessionId,linkScanPath}' $C/jobs/*/state.json | head -40
    ```
  - Breaks: finished jobs are never listed or never dropped, rows lose their names, and a stale copy of a
    record wins.
  - Test: SessionTests.test_parked_and_finished_jobs_listed (test_talpy_den.py),
    LiveAttributionTests.test_job_in_two_profiles_listed_once (test_chats.py).
- [ ] **One-shot exec jobs.** `template` `exec` with no `respawnFlags` marks a one-shot job. Once its process
  is gone, it is never "waiting" or "settled".
  - Used in: talpy_den.py parked_job_state.
  - Check:

    ```bash
    jq -r .template $C/jobs/*/state.json | sort | uniq -c
    jq -c 'select(.template=="exec") | .respawnFlags' $C/jobs/*/state.json
    ```

    (should be null).
  - Breaks: exec jobs show as waiting or done wrongly after their process ends.
  - Test: no test.
- [ ] **daemon.status.json.** `$C/daemon.status.json` holds `supervisorPid`, `supervisorProcStart` and
  `workers {<short>: {pid, procStart}}`. A job with a live worker counts as present, even without a session
  entry.
  - Used in: talpy_den.py service_config_dir, parked_rows, parked_row, daemon_socket.
  - Check: while a background chat runs,
    `jq '{supervisorPid,supervisorProcStart,workers}' $C/daemon.status.json; has daemon.status.json`.
  - Breaks: Talpy Den can't work out the socket path, so `reply`, `has` and `attach` fail: Stop goes off, and
    go-ons fall back to stop then `--resume`. Parked jobs with a worker show as failed.
  - Test: AttachCommandTests.test_reuses_the_running_service_name (test_jump.py). The workers roster: no test.
- [ ] **daemon/roster.json.** `$C/daemon/roster.json` is the service's roster:
  `{proto, supervisorPid, updatedAt, workers: {<short>: {pid, procStart, sessionId, cwd, cliVersion, …}}}`.
  Talpy Den's cleanup counts a job as running while its worker's pid is alive (no `procStart` check).
  - Used in: cleanup.py running (keeps sweep_jobs and sweep_chats off running background chats).
  - Check:

    ```bash
    jq -c '{k:keys, w:(.workers|map_values({pid,procStart,sessionId}))}' $C/daemon/roster.json
    has roster.json
    ```
  - Breaks: Talpy Den's cleanup (when chosen) sees running workers only through `sessions/`, and a reused pid
    keeps a finished job's folder forever.
  - Test: no test.
- [ ] **respawnFlags.** The command-line words Claude wakes the worker with. Claude rewrites them itself after
  a mode change, `/model` or `/effort` in the chat; a copy saves only the model your settings name. Talpy Den
  parses `--permission-mode`, `--model`/`-m`, `--effort` and `--settings` (a JSON naming permission-hook.py),
  in both the `=` and next-word forms. It also writes Claude's `state.json` while the job is settled (no
  process, the service has let go): an atomic replace that adds the missing flags, or swaps
  `--model`/`--effort`. It expects the next wake to use them.
  - Used in: talpy_den.py saved_flags, SAVED_OPTIONS, replace_options, hook_settings, has_settings_flag,
    saved_options, go_on_with; chatpick.py job_record, write_flags, set_now, options_now.
  - Check: `jq .respawnFlags $C/jobs/$SHORT/state.json`. Open `claude attach $SHORT`, change the mode with
    Shift+Tab (never `/model` or `/effort`), detach, and read it again: `--permission-mode` should be updated.
    To check that an edit is honoured: `claude stop $SHORT`, add `"--model","sonnet"` to `respawnFlags` with
    jq (through a temp file), run `claude --bg --resume $ID 'hi'`. `tr '\0' ' ' < /proc/<worker pid>/cmdline`
    should show it, the next reply's `message.model` should match, and no new job folder should appear.
  - Breaks: go-ons come back in the default mode, effort or model; Talpy Den's edits are ignored or
    overwritten; Talpy Chat's `/model` and `/effort` say "from your next message" while the chat wakes on the
    old ones.
  - Test: ContinueAfterResetTests.test_a_copy_that_saved_only_its_model_wakes_in_the_chats_mode_and_effort,
    test_a_background_chat_of_it_wakes_with_its_own_options_and_what_they_lack (test_tasks.py);
    TalpyChatHookTests.test_a_stopped_background_job_gets_it_in_its_saved_options,
    test_a_copy_of_a_hooked_chat_keeps_its_hook,
    ChatPickTests.test_a_settled_background_job_wakes_with_them_next (test_pane.py).
- [ ] **Talpy Chat's own model and effort (`pane.py --set-options`).** Talpy Chat's `/model` and `/effort`
  never send Claude's commands. For an idle background chat that is open, chatpick.py runs `claude stop`,
  waits until no session entry has the chat and `has` is false, rewrites the job's `respawnFlags` (`--model`,
  `--effort`; `ultracode` for "xhigh with ultracode"), then `claude --bg --resume FULL-ID` with no prompt and
  no options: the same job wakes idle with them in about half a second, with no "Switch model?" (live-checked
  on 2.1.318). A settled job gets them from its next message. A chat with no job record keeps them for its
  next wake from Talpy Den. A chat at work, asking, running background commands, or open in a terminal or the
  panel is refused. The lists' check marks come from `options_now`: the job's flags, else your pick, else the
  last reply's model and the status line's effort.
  - Used in: chatpick.py set_options, set_now, let_go, write_flags, options_now, pick_value, label;
    talpy_den.py replace_options, keep_picked, picked_options, wake_lock, stop_background, start_background;
    pane.py --set-options, --conversation ("options").
  - Check: with a throwaway background chat idle (Talpy Chat open on it), pick Sonnet in its `/model` list.
    `jq .respawnFlags $C/jobs/$SHORT/state.json` should name it, `ls $C/jobs | wc -l` should be unchanged,
    `jq .needs` should say `send a prompt to start`, and the next reply's `message.model` should be Sonnet's.
  - Breaks: the pick makes a copy (a new id, the old chat left behind), is ignored, or the chat doesn't wake
    ("it stopped and didn't wake again"); the check marks are wrong.
  - Test: ChatPickTests.test_an_idle_background_chat_is_woken_again_with_them_at_once,
    test_the_answer_of_a_wake, test_not_now_and_not_from_here, test_ultracode_on_and_off_for_this_chat,
    test_what_it_uses_now, test_a_chat_with_no_job_of_its_own_wakes_with_them_from_here (test_pane.py; a
    stand-in claude).
- [ ] **daemonShort.** `daemonShort` in `state.json` is the short id the service knows the session by. It can
  differ from the folder name and from `id[:8]`.
  - Used in: talpy_den.py go_on_with (the ids passed to daemon_holds).
  - Check: `jq -r .daemonShort $C/jobs/*/state.json; has daemonShort`.
  - Breaks: the hold check misses a session the service still holds, so `--resume` starts a copy.
  - Test: no test.
- [ ] **A session that took a chat over.** A background session that resumed or forked a chat has its own
  session id, and its own transcript holds no user or assistant messages. Its job names the chat in
  `resumeSessionId` (resumed) or `forkParentSessionId` (forked); the job's `sessionId` is the session's own
  id.
  - Used in: talpy_den.py chat_link, has_own_messages, finish_row (jobSessionId), continued_from; sharing.py
    chat_jobs.
  - Check: `claude --bg --resume <id of a throwaway chat> 'hi'`, then
    `jq '{sessionId,resumeSessionId,forkParentSessionId}'` on the new job, and look at both ids' transcripts.
  - Breaks: rows show an empty session instead of the chat, and copies of shared chats are mislabelled.
  - Test: SharedCopiesTests.test_background_session_continuing_the_chat_is_that_chat (test_talpy_den.py),
    ChatLinkTests.test_copy_named_by_its_job (test_chats.py).
- [ ] **A job's background commands.** They come from `state.json` `fan[]` entries
  `{kind:'shell', label, doneAt}`. Otherwise Talpy Den finds the shells Claude started below its process by
  their command line, `bash -c … source <…/shell-snapshots/…> … && eval '<command>' …`.
  - Used in: talpy_den.py background_commands, claude_shell_command, background_work; chatpick.py set_now
    (refuses while they run).
  - Check: ask a throwaway background chat to run `sleep 300` in the background, then
    `jq .fan $C/jobs/$SHORT/state.json`. For a terminal chat, `tr '\0' ' ' < /proc/<child pid>/cmdline` should
    show `shell-snapshots` and `eval`. Also `has shell-snapshots`.
  - Breaks: a go-on that waits on background commands names none or never sees them, and a pick in Talpy Chat
    ends them without warning.
  - Test: GoOnWaitsTests.test_its_commands_named_and_ended (test_tasks.py).
- [ ] **A background chat stopped by a usage limit.** Its job gets tempo `blocked`, `needs`
  `rate limited — wait and retry`, and no `waitingFor`. Talpy Den shows it as idle and limit-stopped, not as
  needing you.
  - Used in: talpy_den.py finish_row, row_over.
  - Check: `has 'rate limited'`. After a real limit hit in a background chat, `jq '{state,tempo,needs}'` on
    its job.
  - Breaks: limit-stopped background chats show "needs you" (Keep going still works off the transcript).
  - Test: RowTests.test_a_background_session_the_limit_blocked_waits_for_the_limit (test_tasks.py).
- [ ] **The job record names the new chat at once.** `claude --bg` writes `jobs/<short>/state.json`, whose
  `sessionId` starts with the short id, before it answers. Talpy Chat's `--start` waits 2 s at most.
  - Used in: pane.py job_chat, start_chat.
  - Check: start a throwaway background chat, then at once
    `jq -r .sessionId $C/jobs/<printed short>/state.json`.
  - Breaks: "It started (<id>), but its chat isn't there to show", and Talpy Chat can't open the new chat.
  - Test: TalpyChatHookTests.test_a_job_record_that_never_names_its_chat (test_pane.py).
- [ ] **Claude's predicted reply.** `CLAUDE_CODE_ENABLE_PROMPT_SUGGESTION=true` (PREDICT_ENV) in a chat's own
  `--settings` `env` makes a background chat write `suggestedReply` into its job record once a turn ends
  asking you something. Talpy Chat takes it only while the record has tempo `blocked` and no `block` (a
  permission prompt has one), and only when the turn ended asking: `pane.py --conversation --suggest` answers
  it as `"predicted"`, the first reply chip. It comes a few seconds after the turn ends, and never near a
  usage limit (live-checked on 2.1.318). On 2.1.322 a background chat makes one only when its job is already
  `blocked` (and has no `block`) as the turn ends; the job's tempo comes from Claude's own summary about 2 s
  later, so most turns get none (two live tries on 2.1.322: none, the job `blocked` 2.4 s after the turn).
  Talpy Chat then simply shows no such chip.
  - Used in: pane.py PREDICT_ENV, chat_hook_of, predicted_reply, PREDICTED_CHARS, chat_conversation;
    chatpick.py job_record.
  - Check: `has CLAUDE_CODE_ENABLE_PROMPT_SUGGESTION suggestedReply`.

    ```bash
    (cd "$S" && claude --bg --model haiku --setting-sources project,local --settings '{"env":{"CLAUDE_CODE_ENABLE_PROMPT_SUGGESTION":"true"}}' 'Ask me whether to go on, then stop')
    ```

    After the turn, `jq '{tempo,block,suggestedReply}' $C/jobs/<short>/state.json`.
  - Breaks: the first reply chip disappears without a word.
  - Test: TalpyChatHookTests.test_claudes_predicted_reply_on_with_suggest_replies,
    test_claudes_predicted_reply_is_in_the_conversation (test_pane.py).
- [ ] **Chats that carry the hook.** A background chat is "hooked" (Talpy Den answers its prompts) when its
  job's `respawnFlags` carry a `--settings` naming permission-hook.py, or its account's settings have the
  relay. The relay's status counts those jobs; turning the relay off with `--keep-copy` keeps the hook file
  for them. Without the file, the guard in the hook's command makes it exit 0, and Claude is left to ask by
  itself (a background chat has nowhere to ask).
  - Used in: talpy_den.py finish_row (hooked), hook_settings; pane.py relay, hooked_chats, relay_status,
    install_hook, forget_hook; configChats.qml; vscode/src/relay.ts.
  - Check: compare `python3 -I $TD/pane.py --relay status | jq .hooked` with
    `grep -l permission-hook.py ~/.claude*/jobs/*/state.json | wc -l`.
  - Breaks: if Claude stores the settings elsewhere, the count is 0 and the question isn't asked, so turning
    the relay off (or taking a host off the list) strands the background chats Talpy Chat started.
  - Test: RelayTests.test_off_asks_about_the_chats_talpy_chat_started,
    test_a_hook_whose_copy_is_gone_leaves_the_prompt_to_claude (test_pane.py);
    HostHookTests.test_its_row_says_whether_its_prompts_are_answered_here (test_pane.py).

## Service socket

- [ ] **The service is keyed by the config folder's name as written.** Its socket is
  `/tmp/cc-daemon-<uid>/<sha256(CLAUDE_CONFIG_DIR string)[:8]>/control.sock`, with `$HOME/.claude` when the
  variable is unset, and the path is not resolved. A client using another name for the same folder (the
  `~/.claude` link or its real folder) starts a second service and waits forever at "Starting background
  service…". So Talpy Den reads the supervisor's `CLAUDE_CONFIG_DIR` from `/proc/<supervisorPid>/environ`,
  else the job's `providerEnv.CLAUDE_CONFIG_DIR`, and runs attach, stop and `--bg` under that name. It also
  hands VS Code the link's name for the profile `~/.claude` points to.
  - Used in: talpy_den.py service_config_dir, job_config_dir, config_dir_value, config_env, daemon_socket,
    start_background, stop_background, usage_refresh_command; accounts.py through_link, vscode_value;
    vscode/src/vscodeAccount.ts configDirFor.
  - Check: `ls /tmp/cc-daemon-$(id -u)/`. `printf %s "$C" | sha256sum | cut -c1-8` should name a folder there
    with `control.sock` in it. Also
    `tr '\0' '\n' < /proc/$(jq .supervisorPid $C/daemon.status.json)/environ | grep CLAUDE_CONFIG_DIR` and
    `jq .providerEnv.CLAUDE_CONFIG_DIR $C/jobs/$SHORT/state.json`.
  - Breaks: attach, stop and `--bg` from Talpy Den hang at "Starting background service", and service ops find
    no socket. Panel and terminal chats of one account run under two services and don't see each other's
    background chats.
  - Test: AttachCommandTests.test_reuses_the_running_service_name, test_a_service_named_after_a_switched_link,
    test_uses_the_name_the_job_was_started_with (test_jump.py);
    BackgroundServiceTests.test_no_service_no_key_or_no_answer_is_as_before (test_tasks.py);
    RemoveTests/AddTests test_command_uses_the_link_name_where_claude_does (test_accounts.py);
    vscode/test/vscodeAccount.test.ts "the folder VS Code's Claude gets for an account".
- [ ] **Protocol framing.** Read from 2.1.316's own client: a Unix stream socket, one JSON request line
  carrying `proto: 1`, one JSON answer line. Talpy Den only asks a socket owned by your uid (SO_PEERCRED, else
  lstat).
  - Used in: talpy_den.py DAEMON_PROTO, daemon_ask, peer_uid, esc_through_attach.
  - Check: `has cc-daemon- control.sock`. Live, with a running throwaway background chat:
    `td 't.daemon_ask(p, {"op": "has", "short": a[0]})' $SHORT` should print a dict with `ok` true.
  - Breaks: every service op returns None. Go-ons then stop the session and resume it (an attached terminal
    says the session exited), and background Stop fails.
  - Test: BackgroundServiceTests (test_tasks.py), BackgroundStopTests (test_talpy_den.py): fakes only, never
    the real service.
- [ ] **op `has`.** `{op:'has', short}` answers `{ok:true, op:'has', present, alive}`. Talpy Den asks because
  `claude --bg --resume` starts a copy while the service still holds the session, which it can for a moment
  after `claude stop`. It waits up to 10 s for `present` and `alive` to go false. The ids asked are `id[:8]`,
  the job's `daemonShort` and the live entry's `jobId`.
  - Used in: talpy_den.py daemon_holds, go_on_with; chatpick.py let_go.
  - Check: the `td` line above with a running throwaway background chat should show `present` and `alive`
    true; after `claude stop $SHORT` both should be false within a few seconds.
  - Breaks: go-ons and picks race the service and Claude starts a copy (new id, saved options lost). If the
    fields are renamed, Talpy Den never sees a hold, which gives copies too.
  - Test: BackgroundServiceTests.test_one_it_wont_take_stops_and_goes_on_once_the_service_let_go,
    ContinueAfterResetTests.test_a_job_its_service_still_holds_goes_on_as_a_copy_with_the_jobs_own_options
    (test_tasks.py).
- [ ] **op `reply`.** `{op:'reply', short, text, auth:<control.key>}` types a message into a live background
  session, the way `claude agents` answers one (queued while the chat works). The answer is
  `{ok:true, op:'reply'}` or `{ok:false, code, error}`. `ESTARTING`, `ENOREPLY` and `ERESPAWNING` are retried
  10 times, 0.2 s apart.
  - Used in: talpy_den.py reply_to_background, DAEMON_RETRY_CODES, go_on_with; pane.py send.
  - Check: `has ESTARTING ENOREPLY ERESPAWNING`. Live, with a throwaway background chat open in
    `claude attach $SHORT`: `td 't.reply_to_background(p, a[0], "say hi")' $SHORT`. The prompt should show up
    in the attached terminal.
  - Breaks: replies and go-ons to background chats fall back to `claude stop` plus `--bg --resume`: the
    attached terminal ends ("Session … has exited"), and the chat may be copied.
  - Test: BackgroundServiceTests.test_its_session_takes_the_go_on_in_and_isnt_stopped,
    test_a_reply_starting_or_restarting_is_tried_again_as_claude_does (test_tasks.py),
    SendTests.test_a_background_session_takes_it_in_where_it_is (test_pane.py).
- [ ] **control.key.** `$C/daemon/control.key` is the service's auth key: plain text, at most 4096 bytes,
  stripped. It is sent as `auth` in `reply` and `attach`.
  - Used in: talpy_den.py daemon_key, DAEMON_KEY_MAX, reply_to_background, interrupt_background.
  - Check: `ls -l $C/daemon/control.key; wc -c < $C/daemon/control.key` (don't print it). Also
    `has control.key`.
  - Breaks: replies and Stop say "can't be asked" or "has a key Talpy Den doesn't know", and fall back to stop
    plus resume.
  - Test: BackgroundServiceTests.test_no_service_no_key_or_no_answer_is_as_before (test_tasks.py),
    BackgroundStopTests.test_no_service_no_key_or_another_users_socket (test_talpy_den.py).
- [ ] **op `attach`: the handshake background Stop uses.** The request is
  `{proto:1, op:'attach', short, auth, cols, rows, attachId:<uuid4>, caps:{imark:false, terminal:null, mux:null, ssh:false, colorLevel:3}}`
  (BG_STOP_CAPS). The answer is `{ok:true, op:'attach', workerCliVersion, booting, …}`, and after it every
  byte sent is typed into the session. Talpy Den refuses when `booting` is true or `workerCliVersion` is
  outside the version range, waits for the first frame (BG_STOP_FRAME_WAIT), sends one ESC and lingers 0.2 s
  (BG_STOP_LINGER) before letting go. One ESC interrupts the turn (`[Request interrupted by user]`); two
  within 2 s (BG_STOP_GAP) open the rewind menu. On detach, the service gives an attached terminal back its
  own size. `BROWSER` is dropped while attached. Live-checked on 2.1.318 only; allowed from 2.1.318 up to 2.2.
  - Used in: talpy_den.py esc_through_attach, interrupt_background, stop_turn, bg_stop_known, BG_STOP_FROM,
    BG_STOP_BEFORE, BG_STOP_CAPS; jump.py interrupt; pane.py interrupt.
  - Check: on a new version Stop stays off until `BG_STOP_BEFORE` is raised, so check first.
    `has attachId workerCliVersion colorLevel`, then read the attach code:
    `LC_ALL=C grep -a -o '.\{80\}workerCliVersion.\{200\}' "$B" | head`. Start a throwaway background chat
    with 'count slowly to 300', open `claude attach $SHORT` in a terminal, widen the version range in your working
    copy, and run `python3 -I $TD/pane.py --interrupt $ID`. The transcript should get
    `[Request interrupted by user]`, the attached terminal should keep its size, and no rewind menu should
    open.
  - Breaks: Stop types into the wrong place or nothing, resizes an attached terminal, or opens the rewind menu
    where nobody sees it.
  - Test: BackgroundStopTests (test_talpy_den.py), e.g. test_esc_goes_in_at_the_size_its_terminal_has_now,
    test_nothing_is_typed_unless_it_works_on_a_version_it_knows,
    test_interrupt_by_id_types_esc_into_a_background_chat_and_ctrl_c_into_tmux.
- [ ] **A background worker's terminal size.** A worker's stdin (`/proc/<pid>/fd/0`) is a pty whose window
  size is the session's terminal size. Stop attaches at that size.
  - Used in: talpy_den.py tty_size, interrupt_background.
  - Check:

    ```bash
    python3 -c 'import os,sys,fcntl,termios,struct;fd=os.open(f"/proc/{sys.argv[1]}/fd/0",os.O_RDONLY|os.O_NONBLOCK);print(os.isatty(fd),struct.unpack("HHHH",fcntl.ioctl(fd,termios.TIOCGWINSZ,b"\0"*8)))' <worker pid>
    ```
  - Breaks: Stop refuses ("can't read the size of its terminal"), or an attached terminal gets resized.
  - Test: TtySizeTests.test_the_size_of_a_process_terminal (test_talpy_den.py; a generic pty only).
- [ ] **Esc before Claude's first words.** An Esc sent before Claude starts writing cancels the turn as Esc
  does in a terminal: your prompt goes back into the session's input box, and the transcript gets your prompt
  with no reply and no `[Request interrupted by user]`. An Esc mid-reply does write the note. Live-checked on
  2.1.318.
  - Used in: talpy_den.py interrupt_background, esc_through_attach, last_turn, kept_step; pane.py
    conversation_items; turns.py TurnSoFar; replies.py TurnEnd.
  - Check: start a throwaway background chat with 'write a 1500-word story' and at once run
    `python3 -I $TD/pane.py --interrupt $ID`. `tail -3 "$T" | jq -c '{type,c:.message.content}'` should show
    your prompt with no reply and no note, and `claude attach $SHORT` should show the prompt back in its input
    box.
  - Breaks: Talpy Chat shows your prompt unanswered with no "Interrupted" note, and Keep going may read the
    turn as broken off and retry it. The text left in the input box can go out later, together with a message
    typed into the session.
  - Test: no test.
- [ ] **The service's lifetime.** The first `claude --bg` (or attach) that finds no service starts one
  ("Starting background service…"). It runs detached, stays in the starting process's cgroup, and exits a few
  seconds after its last worker and client go (2.1.318 logs `idle ${n}s with no clients — exiting`, seen after
  5 s). So Talpy Den starts `claude --bg` in a systemd scope of its own: otherwise a restart of the desktop
  shell would end the service, and every background chat with it. On SSH hosts and in containers there is no
  scope (see that section).
  - Used in: jump.py scope_prefix, start_app, new_chat_background; pane.py go_on_in_background, start_chat,
    send, --set-options; talpy_den.py start_background.
  - Check: `has 'with no clients'`. With no service running (`ls /tmp/cc-daemon-$(id -u)/` empty), run:

    ```bash
    (cd "$S" && systemd-run --user --scope --collect -- claude --bg --model haiku --setting-sources project,local 'say hi')
    ```

    `cat /proc/$(jq .supervisorPid $C/daemon.status.json)/cgroup` should name that scope, not your shell's.
    After `claude stop <short>`, the folder should be empty again within about 10 s.
  - Breaks: if the service gets a systemd unit of its own, the scope is needless. If it detaches differently,
    a restart of the desktop shell can end every background chat the widget started.
  - Test: no test for Claude's side (scope_prefix is mocked).

## CLI

- [ ] **What `claude --bg` prints.** For `claude [--bg [--resume ID]] [options] PROMPT`, the job's short id is
  the last `\b[0-9a-f]{8}\b` on stdout (2.1.306 printed `backgrounded · 1a2b3c4d`, plus attach and stop
  hints). On a non-zero exit, the last line of stderr and stdout is the reason (`Workspace not trusted.`).
  stderr lines starting with `note:` are kept; one containing `started a copy` means `--resume` made a copy.
  - Used in: talpy_den.py start_background (SHORT_ID, notes), go_on_with, run_task; pane.py start_chat.
  - Check: start a throwaway background chat, `echo $?`, read stdout.
    `has 'started a copy' 'is already running in the background'`. For the copy note:
    `claude --bg --resume <id of a running background chat> 'hi' 2>&1 | grep '^note:'` (this makes a copy:
    stop and remove it).
  - Breaks: started chats get no id or a wrong one (any 8-hex word, say a hash in a path), so their rows can't
    be opened, and copies go unreported.
  - Test: TaskTests.test_background, test_background_reports_claudes_refusal,
    ContinueAfterResetTests.test_the_answer_says_when_claude_started_a_copy_after_all (test_tasks.py; fake
    output).
- [ ] **Refusals of the background commands.** `--bg` refuses in a folder whose trust question wasn't answered
  Yes (`Workspace not trusted`; always in the home folder). attach, stop, logs, rm and `--bg` refuse while
  `CLAUDE_CODE_DISABLE_AGENT_VIEW` is set (`'attach' is disabled by CLAUDE_CODE_DISABLE_AGENT_VIEW`), so Talpy
  Den runs them with `env -u`. `--bg` refuses auto and bypass modes until you turned them on in a terminal.
  - Used in: talpy_den.py start_background, config_env, NO_AGENT_VIEW, GO_ON_MODES, stop_background; jump.py
    new_chat, jump_job.
  - Check: `has 'Workspace not trusted' 'is disabled by CLAUDE_CODE_DISABLE_AGENT_VIEW'`.
    `CLAUDE_CODE_DISABLE_AGENT_VIEW=1 claude stop 00000000; echo $?` should print the refusal.
  - Breaks: background tasks and go-ons are refused, and attach and stop fail in terminals that export the
    variable.
  - Test: TaskTests.test_background_needs_a_trusted_folder, test_background (test_tasks.py);
    RemoteModeTests.test_rows_carry_their_commands (test_chats.py);
    AttachCommandTests.test_plain_default_profile_unsets_config_dir (test_jump.py).
- [ ] **Plain `claude` and one-word prompts.** While background sessions exist, plain `claude` opens the agent
  view, so new chats are started with `CLAUDE_CODE_DISABLE_AGENT_VIEW=1`. A one-word prompt (update, doctor,
  agents…) is taken as a subcommand, so Talpy Den gives it a leading space.
  - Used in: talpy_den.py new_chat_command, task_command, prompt_arg; jump.py new_chat.
  - Check: with a background session running, `claude` in the scratch folder should open the agent view, and
    `CLAUDE_CODE_DISABLE_AGENT_VIEW=1 claude` a plain prompt (`/exit` both). `claude --help` lists the
    subcommands a one-word task could hit.
  - Breaks: New chat opens the agent view, and a one-word task runs `claude update` or similar.
  - Test: TaskTests.test_a_one_word_task_isnt_one_of_claudes_commands (test_tasks.py), RemoteModeTests
    (test_chats.py).
- [ ] **`claude --resume`.** `claude --resume <id>`, run in the chat's last folder, reopens a finished chat.
  In an untrusted folder, Claude first asks with "No, exit" preselected and "Yes, I trust this folder", and
  Talpy Den's note quotes both.
  - Used in: jump.py resume_chat, resume, resume_command_of, jump; talpy_den.py resume_command,
    claude_command.
  - Check: `cd <a finished throwaway chat's folder> && claude --resume <id>` should reopen it with its
    history. In an untrusted copy of the folder, read the trust question's two choices.
  - Breaks: Reopen fails if `--resume` needs another folder or another form of id, and the note misleads.
  - Test: ResumeChatTests.test_resumes_in_the_chats_last_folder, test_explains_trust_question,
    AttachCommandTests.test_explains_the_trust_question_for_untrusted_folders (test_jump.py).
- [ ] **`claude --bg --resume ID` wakes or copies.** It wakes the same chat (same id and job) only when no
  process has the chat open, the service no longer holds it, the full id is given, and (for a chat with a job
  record) no options are given. Any option on a chat with a job record, or a holder, makes a copy under a new
  id that saves only the options given (or the model your settings name), with a stderr
  `note: … started a copy`. A chat with no job record (it last ran in a terminal) takes options with no copy
  (seen on 2.1.310, not rechecked since). Without a prompt and options, it wakes the same job idle
  (`idle — send a prompt to start`) in about half a second, with no "Switch model?", and prints the same short
  id. Claude lists the woken chat a moment after `--bg` answers; Talpy Den waits up to 8 s.
  - Used in: talpy_den.py go_on_with, go_on_options, saved_options, wake_lock, wake_settle, continue_chat,
    start_background; chatpick.py set_now.
  - Check: stop a throwaway background chat and wait until `has` says false. `claude --bg --resume $ID 'hi'`
    should add no job folder and keep the `sessionId`. Again with no prompt: the same short id is printed, and
    the chat is idle. Then repeat with `--permission-mode plan`: you should get `note: … started a copy` and a
    new job folder (remove it). For the no-record rule: a throwaway terminal chat, `/exit`, then
    `claude --bg --resume <its id> --model haiku 'hi'`: no note, and the new job's `sessionId` is the chat's
    id.
  - Breaks: every go-on or reply to a stopped chat becomes a copy (duplicate chats, lost mode, effort and
    hook), or a wake never shows in the list. If a wake without a prompt is refused, Talpy Den says the chat
    "stopped and didn't wake again".
  - Test: ContinueAfterResetTests.test_a_background_chat_of_it_wakes_with_its_own_options_and_what_they_lack,
    test_a_job_its_service_still_holds_goes_on_as_a_copy_with_the_jobs_own_options (test_tasks.py);
    TalpyChatHookTests.test_two_front_ends_waking_one_chat_make_no_copy, test_one_wake_of_a_chat_at_a_time,
    ChatPickTests.test_an_idle_background_chat_is_woken_again_with_them_at_once (test_pane.py).
- [ ] **`--resume` needs the full session id.** The lowercase uuid. Given the 8-character short id, Claude
  starts a copy with none of the saved options
  (`note: started a copy … pass its full session id (lowercase, as claude agents --json prints it) to --resume`).
  The front ends pass a host's `chatId` in full too.
  - Used in: talpy_den.py start_background, go_on_with, continue_chat; chatpick.py set_now; pane.py
    go_on_in_background, send_now, start_chat; jump.py resume; remote.py chats_with_ids.
  - Check: `has 'pass its full session id'` (2 on 2.1.318 and 2.1.322). Live: stop a throwaway background
    chat, then `claude --bg --resume $ID 'hi' 2>&1 | grep '^note:'` should say `woke session`.
  - Breaks: if Claude wants another form (mixed case, or the short id), every wake and go-on becomes a copy
    without its options.
  - Test: no test (the fakes take any id).
- [ ] **`claude stop`.** `claude stop <short>` ends a background session and keeps its conversation, exit code
  0, its last output line shown as the message. It also ends the session's background commands, and the
  service may hold the session for a moment afterwards. So Talpy Chat refuses to stop a chat while its
  background commands run, and after a stop waits until no session entry has the chat and `has` is false.
  - Used in: talpy_den.py stop_background, stop_command, end_for_handover, end_background_work, stop_all;
    chatpick.py set_now, let_go.
  - Check: `claude stop $SHORT; echo $?`. Within a few seconds no `sessions/*.json` should have its `jobId`,
    `jq .state $C/jobs/$SHORT/state.json` should be `stopped`, and the job folder should stay.
  - Breaks: Stop, the usage-cap stop, hand-overs and Talpy Chat's per-chat picks fail, show garbled messages,
    or end in a copy.
  - Test: StopTests.test_stops_background_session_under_its_profile, test_reports_claude_errors
    (test_jump.py), ChatPickTests.test_not_now_and_not_from_here (test_pane.py).
- [ ] **`claude attach` wakes a stopped job.** On a job with no worker (stopped, or retired by the idle
  service), `claude attach <short>` wakes the same job with its saved options ("Waking session <short>…"),
  then shows it. Open on a parked or finished background chat runs this command (over `ssh -t` for a host's).
  - Used in: jump.py jump_job, attach_command; talpy_den.py attach_command, add_remote_commands.
  - Check: `claude stop $SHORT; claude attach $SHORT` should print "Waking session …" and show the chat.
    `ls $C/jobs | wc -l` and the job's `sessionId` should be unchanged.
  - Breaks: Open on a stopped background chat fails or starts a copy.
  - Test: AttachCommandTests (test_jump.py; the command line only).
- [ ] **How a terminal shows a background session.** The process's comm is `claude`. `claude attach <id|name>`
  has argv[1] `attach` and argv[2] the id or name, and runs on as the agent view. `claude agents`, or a plain
  `claude`/`--continue` with no `sessions/<pid>.json` of its own, is the agent view, and its
  `CLAUDE_AGENTS_SELECT` names the session it was opened for. This holds for the native binary; an npm install
  shows comm `node` and the `cli.js` path in argv[1].
  - Used in: talpy_den.py attach_clients, own_session, process_environ_value, shown_row, attached_in,
    note_attached, attach_command; jump.py find_attached_tab, attach_clients, claude_pids, jump_job;
    vscode/src/terminals.ts attachClients, actions.ts open.
  - Check: open `claude attach $SHORT` in a terminal, then:

    ```bash
    for p in $(pgrep -x claude)
    do echo "$p $(cat /proc/$p/comm) | $(tr '\0' ' ' </proc/$p/cmdline) | $(tr '\0' '\n' </proc/$p/environ | grep CLAUDE_AGENTS_SELECT)"
    done
    ```

    Also `has CLAUDE_AGENTS_SELECT`.
  - Breaks: rows lose their "attached in Konsole/tmux/VS Code" tag, Open starts a second attached terminal
    instead of raising the one that shows the chat, and Talpy Chat thinks no terminal shows it.
  - Test: AttachedTabTests.test_claude_attach_on_command_line, test_attach_under_a_wrapper_shell,
    AttachedElsewhereTests.test_attach_clients_by_id_or_by_name_on_this_profile,
    ProcessNameTests.test_a_name_cut_inside_a_character (test_jump.py);
    TerminalTests.test_a_background_session_shown_in_a_terminal (test_talpy_den.py);
    vscode/test/attach.test.ts "attach clients are told by their command line", "a background job a terminal
    shows already comes up there, not attached twice".
- [ ] **Option values.** `--effort` takes `low`, `medium`, `high`, `xhigh`, `max` or `ultracode` (2.1.312+:
  xhigh with ultracode on; `xhigh` turns it off). `--permission-mode` takes `default` (shown as "Manual";
  older Claude, say on a host, knows only `default`), `acceptEdits`, `plan`, `auto`, `dontAsk` and
  `bypassPermissions`. The model aliases are `opus`, `sonnet`, `fable` and `haiku`, and a full model id maps
  to its alias by substring (`claude-opus-5-5[1m]` → opus). `--add-dir` takes several values, so it must be
  one word, `--add-dir=DIR`: a separate DIR would swallow the prompt.
  - Used in: talpy_den.py chat_options, EFFORT_LEVELS, ULTRACODE, PERMISSION_MODES, GO_ON_MODES,
    go_on_options, picture_options, go_on_with; chatpick.py pick_value, label, MODEL_ALIASES; pane.py
    start_chat; vscode/src/shared/pane.ts CHAT_MODELS, CHAT_EFFORTS, CHAT_MODES, ULTRACODE, modelKey,
    withPick, pickerItems, nowText; vscode/src/actions.ts MODELS, EFFORTS, MODES; ChatPane.qml,
    NewChatOptions.qml, NewChatBox.qml.
  - Check: `claude --help | grep -A4 -E -- '--(model|effort|permission-mode|add-dir)'`; `has ultracode`;
    `jq -r 'select(.type=="assistant").message.model' $C/projects/*/*.jsonl 2>/dev/null | sort -u | tail`
    (each id should still contain its family name).
  - Breaks: new chats, go-ons and wakes fail to start ("invalid option"), or the prompt is taken as a folder.
    Ultracode isn't carried, and the "now" check mark and "Now: …" line are wrong.
  - Test: TaskTests.test_a_new_chat_with_the_model_and_effort_you_picked,
    PictureTests.test_a_chat_whose_task_names_a_picture_can_open_it (test_tasks.py);
    HostTaskTests.test_a_picture_goes_there_for_a_task_that_opens_it (test_remote.py);
    ChatPickTests.test_ultracode_on_and_off_for_this_chat (test_pane.py); vscode/test/pane.test.ts "a command
    runs as its kind says on the chat's route (Plasma's commandRun: the same rule and words)".
- [ ] **Variables Claude gives its children.** Talpy Den strips `CLAUDECODE`, `CLAUDE_CODE_CHILD_SESSION`,
  `CLAUDE_CODE_ENTRYPOINT`, `CLAUDE_CODE_EXECPATH`, `CLAUDE_CODE_MESSAGING_SOCKET`,
  `CLAUDE_CODE_MESSAGING_TOKEN`, `CLAUDE_CODE_SESSION_ATTENDED`, `CLAUDE_CODE_SESSION_ID`, `CLAUDE_EFFORT`,
  `CLAUDE_PID` and `CLAUDE_JOB_DIR`. A claude started with them counts as part of that session.
  - Used in: talpy_den.py SESSION_ENV, start_background, usage_refresh_command.
  - Check: ask a throwaway chat to run `env | grep -E '^CLAUDE' | cut -d= -f1 | sort` and compare with
    SESSION_ENV. Add any new name that ties a child to the session.
  - Breaks: a `--bg` started from Talpy Den inside a Claude session, or a usage fetch, is tied to that session
    (wrong hooks or parent).
  - Test: TaskTests.test_background (test_tasks.py),
    UsageRefreshTests.test_old_usage_fetched_while_a_chat_works (test_talpy_den.py).
- [ ] **SIGTERM ends a terminal chat.** On SIGTERM a terminal chat shuts down: the step is cut, the chat is
  kept and `--resume` works. Since 2.1.316, closing a chat's terminal moves the chat to the background under a
  new id; in 2.1.318's code SIGTERM goes to shutdown(143) and SIGHUP to shutdown(129) (where the move is
  decided wasn't traced). Talpy Den relies on SIGTERM not moving the chat.
  - Used in: talpy_den.py stop_chat, end_leftovers, process_tree, end_for_handover.
  - Check: in a throwaway terminal chat that finished a turn, note its `sessionId` and `kill -TERM <pid>`.
    `ls -t $C/jobs | head -2` should show no new folder, no `kind` `bg` session should appear for it, no new
    transcript should carry `session_id` = the old id, and `claude --resume <old id>` should reopen it.
    Compare with `kill -HUP`, which moves it.
  - Breaks: if SIGTERM also moves a chat, Stop sends the chat on under a new id, and a hand-over (stop, then
    `--bg --resume <old id>`) leaves two copies at work.
  - Test: ChatStopTests.test_idle_chat_quits_on_sigterm, test_commands_it_leaves_behind_are_ended
    (test_jump.py; fake processes, not Claude's reaction).
- [ ] **Ctrl+C in a chat's terminal.** Claude's terminal UI runs raw, so a typed Ctrl+C byte is a key. The
  first Ctrl+C while Claude works stops the turn and its subagents (background ones too), and the chat stays
  open with your draft. At an idle prompt Ctrl+C starts quitting (a second one quits), so Talpy Den sends it
  only while the chat works. The transcript notes `[Request interrupted`. VS Code terminals run the chat as
  `trap : INT; <command>; exec $SHELL`, so the shell stays after Claude exits.
  - Used in: talpy_den.py interrupt_chat, interrupt_chat_by_id; jump.py interrupt; pane.py interrupt;
    vscode/src/actions.ts stop, chatPane.ts interrupt, terminals.ts run.
  - Check: in a throwaway chat in tmux, ask 'run: for i in $(seq 100); do sleep 1; done'. Then
    `tmux send-keys -t <pane> C-c`, `grep -c '\[Request interrupted' "$T"`, and
    `tmux display -pt <pane> '#{pane_current_command}'` should still say claude.
  - Breaks: Interrupt and Talpy Chat's Stop quit Claude or do nothing.
  - Test: ChatStopTests.test_interrupt_presses_ctrl_c_in_its_tmux_pane,
    test_interrupt_only_in_tmux_and_while_working (test_jump.py); vscode/test/openIn.test.ts "a chat with a
    process can be stopped, whatever it's doing; a working one interrupted" (routing only).
- [ ] **Typing into a chat's terminal.** In tmux, Talpy Den types with `tmux load-buffer`, then
  `paste-buffer -p` (bracketed paste), then `send-keys Enter` after 0.3 s. In VS Code terminals it sends
  `ESC[200~ … ESC[201~`, then `\r` about 300 ms later. Control characters are stripped and newlines kept.
  Claude's prompt takes the paste as one message and runs no keys; type-in leaves out the Enter. While a
  dialog shows, typed text would answer the dialog, so Talpy Den refuses then.
  - Used in: pane.py tmux_type, as_typed, send_now, type_in, answer_with_keys; jump.py tmux_paste;
    vscode/src/terminals.ts asPaste, chatPane.ts sendNow, typeIn, actions.ts sendPlanFeedback.
  - Check: in a throwaway chat in tmux,
    `tmux send-keys -t <pane> -l $'\e[200~line 1\nline 2\e[201~'; sleep 0.3; tmux send-keys -t <pane> Enter`.
    The transcript's last prompt should hold both lines as one message.
  - Breaks: multi-line replies and plan feedback go in as several prompts, stay unsent, or run their lines as
    keys.
  - Test: SendTests.test_tmux, KeysTests.test_each_paste_has_its_own_buffer,
    TypeInTests.test_tmux_types_it_without_enter (test_pane.py); vscode/test/terminals.test.ts "text typed
    into a chat's terminal is one paste, whatever it holds".
- [ ] **`!` shell mode.** In a running chat's prompt, `!cmd` runs in the shell. `claude --resume` and a new
  `--bg` chat read it as a plain message. A `!cmd` queued while Claude works sits in Claude's queue without
  its `!`.
  - Used in: vscode/src/shared/pane.ts commandRun, pendingTaken, clipboardCode; ChatPane.qml commandRun;
    markdown.mjs (copy).
  - Check: send `!echo hi` from Talpy Chat to a working throwaway background chat.
    `grep '"queue-operation"' "$T" | tail -2 | jq -c .` should show content `echo hi`.
  - Breaks: a shell command you sent shows "sending" for 30 s, then twice, or is routed wrong.
  - Test: vscode/test/pane.test.ts "a shell command you sent is found in Claude's queue without its !", "a
    command runs as its kind says on the chat's route …";
    PaneMarkdownTests.test_copy_leaves_out_the_bang_of_a_command_for_claudes_prompt (test_pane.py).
- [ ] **Built-in slash commands (BUILTIN_COMMANDS, 2.1.318).** Talpy Den keeps a table of how each built-in
  command behaves, checked live on tmux, running background and `--bg --resume` chats. "here" commands print
  into the chat: code-review, compact, context, debug, doctor, fork, init, insights, plan, recap, rename,
  security-review, simplify, subtask, and `/export FILE` and `/goal COND` with an argument. "picker" commands
  (`/model`, `/effort`) go to Talpy Chat's own picker, "page" (`/permissions`) to Talpy Den's Permissions tab,
  and "terminal" ones open a panel or dialog. RUNS marks the prompt commands that start a turn. Aliases are in
  TYPED (cost → usage, review → code-review, checkup → doctor), panel-only commands in PANELS (agents among
  them), and AUTO holds what Claude runs on its own (`/rate-limit-options`). A / command sent into a
  background chat's queue runs as a command; given as the prompt of `claude --bg --resume ID` it runs too, but
  a `!` line there is read as a message. /context run that way leaves the job at running/active while the
  session is idle.
  - Used in: commands.py BUILTIN_COMMANDS, TYPED, PANELS, AUTO, RUNS, builtin_offers, typed_kinds; pane.py
    --complete, --type-in; vscode/src/shared/pane.ts commandRun; ChatPane.qml commandRun.
  - Check: in a throwaway chat in tmux, type `/` and compare the list with BUILTIN_COMMANDS, TYPED and PANELS.
    Send each "here" command to a throwaway background chat from Talpy Chat: it should print into the
    transcript (`grep -c local-command-stdout "$T"`), not leave the chat waiting in a panel nobody sees. Never
    `/model` or `/effort`.
  - Breaks: a "here" command that now opens a dialog leaves a background chat stuck where nobody sees it.
    Renamed or removed commands are still offered, new ones are missing, and a prompt command's turn isn't
    followed.
  - Test: CommandKindsTests.test_each_builtin_commands_kind, test_typed_names_not_listed (test_pane.py; they
    pin the table, not Claude's behaviour).
- [ ] **Plan usage fetch.** Talpy Den runs
  `claude -p /usage --no-session-persistence --setting-sources user --strict-mcp-config --settings '{"disableAllHooks":true}' --output-format json`
  in `~/.cache/talpy-den/usage-check`. It refreshes `cachedUsageUtilization`, uses no tokens and saves no
  chat. It leaves an empty `projects/<mangled cwd>/memory/`, which Talpy Den removes. Its own session entry
  has that cwd and is left out of the list. An account counts as logged in when `.credentials.json` exists.
  - Used in: talpy_den.py usage_refresh_command, USAGE_CHECK_SCRIPT, refresh_usage, claim_usage_refresh,
    usage_refresh_profile, usage_now_profile, fetch_usage_now, is_usage_check, mangle.
  - Check: `(cd /tmp && claude -p /usage --no-session-persistence --output-format json >/dev/null)`, then
    `jq .cachedUsageUtilization.fetchedAtMs "$A"` should have changed, and `ls $C/projects | grep -- '-tmp$'`
    shows the leftover folder (remove it).
  - Breaks: Refresh and the automatic fetch do nothing, stray project folders pile up, and the fetch shows as
    a chat.
  - Test: UsageRefreshTests.test_old_usage_fetched_while_a_chat_works, test_its_own_session_isnt_a_chat,
    UsageRefreshCommandTests.test_it_runs_and_leaves_no_folder_behind, FetchUsageTests (test_talpy_den.py).
- [ ] **`claude auth status --json`.** It prints `{loggedIn, authMethod ('claude.ai'|'none'|…), email}` for
  the profile `CLAUDE_CONFIG_DIR` names.
  - Used in: accounts.py auth_status, list_accounts (--check).
  - Check: `claude auth status --json | jq 'keys'` (read-only).
  - Breaks: the Accounts check shows everyone logged out, or no method.
  - Test: LoginTests.test_check_asks_claude (test_accounts.py; a stand-in claude).
- [ ] **`claude auth login` and `logout`.** Login keeps the login in the profile's folder:
  `.credentials.json`, and `oauthAccount` in the account file. Logout revokes the login, removes
  `oauthAccount` and keeps a device id in `.credentials.json`; on failure it exits non-zero with the reason on
  the last output line. Login opens a browser, or over SSH shows an address and takes a pasted code.
  - Used in: accounts.py login, logout, remove_account; talpy_den.py login_command, needs_login.
  - Check: on a spare profile, `CLAUDE_CONFIG_DIR=~/.claude-NAME claude auth logout; echo $?`, then
    `jq 'has("oauthAccount")' ~/.claude-NAME/.claude.json; ls -la ~/.claude-NAME/.credentials.json`.
  - Breaks: logged-out detection is wrong. A removed account's folder goes to the Trash still holding a login,
    or Remove reports a failed logout.
  - Test: LoginTests.test_logout, test_logout_failure_is_reported, test_add_opens_claudes_login_in_a_terminal,
    test_plain_default_logs_in_without_the_variable, RemoveTests.test_logs_out_then_moves_to_the_trash,
    test_login_never_reaches_the_trash (test_accounts.py).
- [ ] **Stopping a profile's background service.** Before Remove, Talpy Den runs
  `CLAUDE_CONFIG_DIR=<the service's own name> claude daemon stop --any`, finding the service through
  `daemon.status.json` and the supervisor's environment.
  - Used in: accounts.py stop_service, command_script; talpy_den.py service_config_dir.
  - Check: `claude daemon --help 2>&1 | grep -E 'stop|--any'`.
  - Breaks: Remove refuses ("its background service is still running"), or moves a folder to the Trash while a
    service still writes there.
  - Test: no test for stop_service.
- [ ] **Plan feedback reopens a chat in plan mode.** For a chat with no process, Talpy Den runs
  `claude --resume <id> --permission-mode plan '<feedback>'` in a terminal, relying on this reopening the same
  chat (no copy) in plan mode with the feedback sent at once. For a chat that has a job record, the flag is
  left out, since it would start a copy.
  - Used in: jump.py send_plan_feedback, was_background; talpy_den.py claude_command, prompt_arg.
  - Check: in a throwaway terminal chat, send one prompt and `/exit`.
    `claude --resume <id> --permission-mode plan 'revise step 2'`: the same `<id>.jsonl` should grow, the
    footer should show plan mode, and the message should go at once. Repeat without the flag for a stopped
    background chat.
  - Breaks: feedback opens a copy, starts in the wrong mode, or sits unsent.
  - Test: PlanFeedbackTests.test_a_chat_without_a_process_reopens_in_plan_mode_with_it,
    test_a_former_background_session_reopens_without_options (test_tasks.py; the command line only).
- [ ] **Where claude is installed.** Talpy Den looks on PATH first, then `~/.local/bin` (the native
  installer's link into `~/.local/share/claude/versions/<version>`), `~/.claude/local`, `~/.npm-global/bin`,
  `~/.bun/bin`, `~/bin`, `~/.volta/bin`, `~/.local/share/pnpm`, mise and asdf shims,
  `~/.nvm/versions/node/*/bin` (newest first), `/usr/local/bin` and Homebrew. For a click, it then tries the
  login shell's PATH (`$SHELL -l -i -c env`). An npm install needs the node next to it on PATH.
  - Used in: talpy_den.py CLAUDE_PLACES, SYSTEM_PLACES, claude_places, find_claude, login_shell_path,
    cached_find_claude, claude_words; jump.py claude_path, claude_in_terminal; accounts.py claude_path.
  - Check: after an update `readlink -f "$(type -P claude)"` should be the new version. Then:

    ```bash
    env -i HOME=$HOME PATH=/usr/bin:/bin python3 -I -c 'import sys,pathlib;sys.path.insert(0,sys.argv[1]);import talpy_den as t;print(t.find_claude(pathlib.Path.home()))' "$TD"
    ```
  - Breaks: "Can't find the claude command" for Open, Send, Stop, accounts, background starts and usage
    refresh from the desktop.
  - Test: FindClaudeTests.test_install_places_and_the_newest_nvm_node,
    test_the_login_shells_path_only_when_asked, test_status_checks_ask_the_login_shell_once_an_hour,
    test_node_next_to_claude_goes_on_path, test_reopening_runs_it_by_its_full_path_or_says_what_to_do
    (test_jump.py).

## Transcripts

- [ ] **Where transcripts live.** A chat's transcript is
  `$C/projects/<mangled start folder>/<session uuid>.jsonl`, found with the glob `projects/*/<id>.jsonl`.
  Subagents are in `<project>/<id>/subagents/agent-*.jsonl`, workflow agents in
  `<project>/<id>/subagents/workflows/<run>/agent-*.jsonl`. Only uuid-named `.jsonl` files count as chats.
  - Used in: talpy_den.py transcript_path, subagent_transcripts, transcript_files, project_folders,
    find_agent_transcript; pane.py find_transcript; week.py transcript_kind, found_transcripts; replies.py
    reply_history; cleanup.py sweep_chats (CHAT_ID).
  - Check: have a throwaway chat run one subagent ('use a subagent to list this folder'), `/exit`, then
    `ls $C/projects/$M/ $C/projects/$M/*/subagents/`.
  - Breaks: Talpy Chat says "This chat hasn't started yet" for every chat. Rows lose name, peek and stats,
    Recap and suggested replies miss chats, subagents' tool calls and tokens aren't counted, and cleanup never
    matches a chat.
  - Test: TranscriptFileTests.test_follows_linked_folders_and_marks_them_shared (test_chats.py),
    UsageTests.test_a_forked_subagent_starts_with_a_copy_of_the_call (test_week.py).
- [ ] **How Claude names a project folder.** The start folder with every non-alphanumeric character turned
  into `-`. A chat stays filed under its start folder, wherever its `cd`s take it later. start_folder trusts a
  transcript's first `cwd` only if its mangled form is the folder's name. Claude's own shortening of very long
  paths is not modelled.
  - Used in: talpy_den.py mangle, start_folder, memory_folder, project_folder_of, usage_refresh_command;
    vscode/src/claudePanel.ts filedUnder, actions.ts windowHasChat.
  - Check: after a throwaway chat, `ls $C/projects | grep -Fx -- "$M"`. For long paths, start a throwaway chat
    in a folder whose path is over 200 characters and compare the folder name with the sed output.
  - Breaks: a chat's start folder becomes unknown, chats are filed under the wrong project and reopen in the
    wrong folder, and Open in Claude Code opens another window.
  - Test: TranscriptFileTests (test_chats.py),
    UsageRefreshCommandTests.test_it_runs_and_leaves_no_folder_behind (test_talpy_den.py),
    vscode/test/openIn.test.ts "a recent chat reopens in this window when it has the chat's project open". The
    Python tests build paths with mangle itself, so they would follow a wrong rule.
- [ ] **Compact JSON, one entry per line.** Each entry is one line of compact JSON with no spaces
  (`"type":"assistant"`) and non-ASCII characters written as they are (not `\u` escapes). Byte matches rely on
  it: week.py matches `"type":"assistant"`, `"type":"user"`, `"subtype":"turn_duration"`, `compact_boundary`,
  title lines (`"type":"ai-title"`), lines starting `{"type":"api-request`, and `"attachment":{"type":"file"`,
  and measures a tool result from `"type":"tool_result"` up to `"toolUseResult":` (key order). LinkCache.holds
  looks for `"uuid":"<id>"`, LinkCache.transcript for `"stop_reason":"`, replies.py REPLY_WORDS for
  `"thinkingDisplay":"updates"`, made.py for a file's JSON-escaped name.
  - Used in: week.py take_line, take_user (RESULT_FIELD); talpy_den.py LinkCache.holds, LinkCache.transcript,
    the PLAN_FILE and WRITE_CALL byte patterns, ULTRA_LINE; pane.py PANE_LINE, tool_originals; replies.py
    REPLY_WORDS; made.py named_in, lines_with.
  - Check: `head -c 3000 "$T" | grep -c '": "'` (expect 0). Also `grep -c '^{"type":"api-request' "$T"` and
    `grep -o '"type":"tool_result".\{0,4000\}"toolUseResult":' "$T" | head -c 200`.
  - Breaks: with spaces or another key order, Recap and the Week view go empty without a word, large-result
    tips go wrong, and copy and moved-chat detection stop. With `\u` escapes, a made file with a non-ASCII
    name can't be opened.
  - Test: UsageTests.test_a_reply_in_blocks_over_two_scans and the rest of test_week.py (their fixtures write
    compact JSON, so they pin the format but can't detect a change).
- [ ] **One assistant message, several entries.** Claude splits an assistant message into one entry per
  content block (text, thinking, tool_use). The entries share `message.id` and repeat the message's usage; the
  last one may carry the final output count.
  - Used in: pane.py conversation_items; replies.py whole_text, TurnEnd.assistant; talpy_den.py peek_from,
    final_answer, fold_stats, scan_transcripts; week.py take_reply.
  - Check: `grep -o '"id":"msg_[A-Za-z0-9]*"' "$T" | sort | uniq -c | sort -rn | head` (some counts above 1).
  - Breaks: replies are split or merged wrongly, Copy returns part of a reply, and token totals and costs are
    doubled or undercounted.
  - Test: ConversationTests.test_items, WholeReplyTests.test_a_long_reply_whole_as_the_conversation_joins_it
    (test_pane.py); PeekTests.test_finished_reply_in_several_blocks,
    TokenTests.test_dedupe_partial_line_and_rescan, ChatRecapTests.test_recap (test_talpy_den.py).
- [ ] **Stable ids.** Talpy Chat keys items by `message.id` (Claude), the entry's `uuid` (your prompt), the
  tool_use `id`, `<message id>/thinking`, `<tool id>/answer` and `queued-<ms>`. Copy finds a reply again by
  grepping its JSON-escaped key. Copies of a chat (a fork, a resumed copy, one moved to the background) keep
  the original `uuid` and `message.id`, and a fork starts with a copy of the call that started it.
  - Used in: pane.py conversation_items, THOUGHT; replies.py whole_text, reply_history; week.py reply_id,
    first_seen, scan; talpy_den.py LinkCache.copied, holds, fold_stats.
  - Check: after a fork or a `--resume` copy of a throwaway chat,
    `grep -o '"uuid":"[^"]*"' OLD.jsonl | head -3 | while read u; do grep -c -F "$u" NEW.jsonl; done`.
  - Breaks: Copy answers that no entry has that key, items get new keys between reads (bookmarks are lost),
    forks are counted twice in Recap, and moved or copied chats aren't recognised.
  - Test: WholeReplyTests.test_none_with_that_key (test_pane.py);
    HistoryTests.test_a_chat_claude_moved_to_another_folder_counts_once,
    PromptTests.test_a_forked_chat_counts_its_prompts_and_compactions_once (test_week.py);
    AgentTests.test_a_forks_copy_of_the_call_isnt_its_work (test_talpy_den.py).
- [ ] **Bookmarks and their reach.** Bookmarks are Talpy Den's own files
  (`~/.cache/talpy-den/bookmarks/<chat>.json`), but each keeps a message's item key: your prompt's `uuid` or
  Claude's `message.id`. They rely on those ids being the same at every read and in a moved chat's copy
  (bookmarks_moved merges the old id's file into the new one), and on fitting BOOKMARK_KEY
  (`[A-Za-z0-9_.:@-]`, at most 200; uuids and `msg_…` ids do). `pane.py --conversation --reach KEY` reads the
  transcript further back (×4, up to PANE_TAIL_MAX) until an item has that key, then grows the limit to show
  it ("here"), or says "far" (over PANE_ITEMS_MAX items back) or "gone" (read whole, not there). That relies
  on the transcript being append-only and in order.
  - Used in: talpy_den.py change_bookmark, load_bookmarks, bookmarks_answer, bookmarks_moved,
    forget_bookmarks, BOOKMARK_KEY; pane.py conversation, reach_limit, REACH_ABOVE, chat_conversation,
    --bookmark; bookmarks.mjs.
  - Check: `grep -o '"uuid":"[^"]*"\|"id":"msg_[^"]*"' "$T" | grep -v -E '"[A-Za-z0-9_.:@-]{1,200}"$' | head`
    (should print nothing). Bookmark a message in a throwaway chat, close its terminal so Claude moves it to
    the background (see the moved-chat item), and the bookmark should still reach that message in Talpy Chat.
  - Breaks: bookmarks can't be made ("Which message?"), point at nothing after a move or a new read, or a jump
    to one says "gone" for a message that's there.
  - Test: BookmarkStoreTests.test_a_moved_chats_bookmarks_follow_it,
    test_a_check_takes_moved_chats_bookmarks_along_only_when_a_chat_moved (test_talpy_den.py);
    ReachTests.test_a_key_300_items_back, test_a_key_not_in_the_chat_is_gone,
    test_a_queued_prompt_is_found_once_the_read_grows,
    BookmarkTests.test_the_conversation_carries_them_once_there_are_some (test_pane.py). Fixtures only.
- [ ] **Append-only.** Transcripts are never rewritten in place: compaction appends a `compact_boundary`, and
  earlier entries stay. Incremental readers go on from saved byte offsets, checked by inode and size.
  - Used in: week.py scan, read_transcript; replies.py reply_history; turns.py turn_before; talpy_den.py
    scan_edits, ChatCache, LinkCache.transcript, LinkCache.moved_from, TestsCache; pane.py conversation
    (--reach).
  - Check: in a throwaway chat, `stat -c '%i %s' "$T"` before and after `/compact` and after a rewind (Esc
    Esc). The inode should stay the same and the size only grow.
  - Breaks: Recap counts entries twice or misses them, suggested replies and peeks go stale, and turns start
    in the wrong place.
  - Test: TokenTests.test_truncated_file_rescanned, ChangedFilesTests.test_appended_records_are_read_once
    (test_talpy_den.py), SuggestedRepliesTests.test_a_transcript_is_read_once (test_pane.py).
- [ ] **Rewinds and parentUuid.** Entries chain by `parentUuid`, but Talpy Den reads the file in order and
  never follows that chain. It relies on the file holding only the live conversation.
  - Used in: pane.py conversation_items, conversation; talpy_den.py tail_entries, peek_from, last_turn,
    open_tools; replies.py reply_records; turns.py turn_before; week.py take_line.
  - Check: in a throwaway chat, send two prompts, rewind to the first with Esc Esc, and send another.
    `jq -c '{type,u:.uuid,p:.parentUuid}' "$T" | tail -12`: if the new prompt's `parentUuid` skips back over
    entries still in the file, those are a dropped branch.
  - Breaks: Talpy Chat, the peek, chips and Recap show replies Claude no longer has in its context, and a Copy
    or bookmark on one points into a branch the chat left.
  - Test: no test.
- [ ] **What counts as your prompt.** A `user` entry that isn't `isMeta`, `isCompactSummary` or `isSidechain`,
  has no tool_result block, and whose joined text, once the Claude Code panel's notes are taken off its front,
  doesn't start with `<` or `[Request interrupted`. The panel (VS Code, JetBrains) puts each note in a text
  block of its own before what you typed: `<ide_opened_file>…</ide_opened_file>`,
  `<ide_selection>…</ide_selection>` (any `<ide_…>` tag, IDE_NOTE).
  - Used in: talpy_den.py human_prompt, typed_part, IDE_NOTE, read_chat_info (through pane.py
    conversation_items, typed_text, peek_from, step_text, fold_stats, last_turn, open_tools, recap_of);
    turns.py turn_prompt_at; replies.py reply_records; week.py take_user.
  - Check: `has ide_opened_file ide_selection`.
    `grep -h -o '"text":"<ide_[a-z_]*>' ~/.claude*/projects/*/*.jsonl | sort | uniq -c` (look for a new tag),
    and in those entries `"isMeta":true` should be absent.
  - Breaks: your prompts from the panel drop out of Talpy Chat, the peek, prompt counts, busy time, the turn
    timer, suggested replies and chat names; or a new note shows as part of your prompt.
  - Test: ConversationTests.test_a_prompt_from_the_claude_code_panel_shows (test_pane.py);
    PeekTests.test_own_notes_are_not_prompts (test_talpy_den.py).
- [ ] **Entry flags.** `isMeta` (expanded skills, caveats, Claude's own notes), `isCompactSummary` (the
  compaction summary written as a user entry) and `isSidechain` (a subagent's entry in the main transcript)
  are never shown as yours.
  - Used in: pane.py conversation_items; talpy_den.py human_prompt, names_mode, open_tools, peek_from;
    turns.py tool_calls, turn_prompt_at; replies.py reply_records, asks_of.
  - Check: in a throwaway chat with `/compact` and a skill,
    `grep -o '"isCompactSummary":true\|"isMeta":true\|"isSidechain":true' "$T" | sort | uniq -c`.
  - Breaks: the compaction summary or a skill's text shows as your prompt, and subagent steps get mixed into
    the chat.
  - Test: CommandsInChatTests.test_compact_keeps_its_note, test_prompt_commands_skills_and_claudes_own,
    ConversationTests.test_items (test_pane.py).
- [ ] **Thinking shown as updates.** When thinking is shown as updates (background chats), assistant entries
  carry top-level `"thinkingDisplay":"updates"`, and a thinking block's `thinking` text is Claude Code's
  one-line narration of the thinking, not the reply. Talpy Chat shows it as an item of its own (`thinking`,
  key `<message id>/thinking`), dimmed in italics after `∴`; replies.py leaves it out of chips. Otherwise
  thinking blocks have no text.
  - Used in: pane.py conversation_items, THOUGHT; replies.py TurnEnd.assistant, whole_text, REPLY_WORDS;
    vscode/src/shared/pane.ts THINKING_TIP; vscode/webview/chat.tsx; ChatPane.qml.
  - Check: `has thinkingDisplay`. On a background chat's transcript,
    `grep -c '"thinkingDisplay":"updates"' "$T"` and:

    ```bash
    jq -r 'select(.thinkingDisplay=="updates")|.message.content[]?|select(.type=="thinking")|.thinking' "$T" | head -3
    ```

    (short lines, not the reply).
  - Breaks: thinking lines show as Claude's reply again (they can claim work as done before it ran) or vanish,
    Copy on one returns nothing, and chips are judged on thinking text.
  - Test: ConversationTests.test_thinking_shown_as_updates_is_a_line_of_its_own,
    WholeReplyTests.test_yours_and_thinking_shown_as_updates (test_pane.py).
- [ ] **Queue operations.** Messages sent while Claude works become `queue-operation` entries. `enqueue`
  carries your text in `content`. `remove` carries `content`, `commandUuid` and `reason` `absorbed_mid_turn`.
  `popAll` puts the queue back in the input box, and `dequeue` (content null) makes the head of the queue the
  next prompt.
  - Used in: pane.py conversation_items; commands.py Commands.take.
  - Check: `has popAll absorbed_mid_turn`. In a throwaway chat, send a message while a `sleep 30` runs, then
    `grep '"type":"queue-operation"' "$T" | grep -o '"operation":"[a-zA-Z]*"' | sort | uniq -c`.
  - Breaks: messages sent mid-turn show twice, never, or stay "queued". Commands lose their key, and the 5 s
    undo or queued rows go wrong.
  - Test: ConversationTests.test_a_message_sent_while_claude_works_shows_when_it_is_sent,
    test_a_queued_message_taken_back_or_run_as_a_turn_shows_once,
    CommandsInChatTests.test_a_command_through_claudes_queue_keeps_its_key (test_pane.py).
- [ ] **Messages taken in mid-turn.** Such a message is an attachment
  `{type:'queued_command', prompt (string or blocks), source_uuid (= the remove's commandUuid), commandMode:'prompt' (else e.g. 'task-notification'), origin:{kind:'human'} (else 'peer')}`.
  PANE_LINE lets attachment lines through only for `"type":"queued_command"` (and ULTRA_LINE the ultracode
  ones).
  - Used in: pane.py conversation_items, PANE_LINE, typed_text.
  - Check: with the same recipe,
    `grep -o '"attachment":{"type":"queued_command"[^}]*' "$T" | head -2; has source_uuid commandMode`.
  - Breaks: a message Claude took in mid-turn never shows, or task notifications and subagent reports show as
    yours.
  - Test: ConversationTests.test_a_message_sent_while_claude_works_shows_when_it_is_sent (test_pane.py).
- [ ] **Claude's own wake-ups.** A wake-up from ScheduleWakeup or `/loop` is written as an enqueue, then a
  system entry with subtype `scheduled_task_fire` carrying `prompt` ("Claude resuming /loop wakeup (…)"), then
  a dequeue, then a user entry with `isMeta: true` and `promptSource: 'system'` holding that prompt.
  - Used in: pane.py conversation_items.
  - Check: `has scheduled_task_fire promptSource`. In a throwaway chat, run '/loop 1m say hi', stop it after
    one fire, then `grep -o '"subtype":"scheduled_task_fire"\|"promptSource":"[a-z]*"' "$T" | sort | uniq -c`.
  - Breaks: Claude's own wake-up prompts show as yours, at the end of the chat, for good.
  - Test: ConversationTests.test_a_wake_up_claude_scheduled_isnt_yours (test_pane.py).
- [ ] **Compaction.** A system entry with subtype `compact_boundary` plus a user entry with
  `isCompactSummary`; earlier entries stay. The next assistant message's usage is the new, smaller context.
  - Used in: pane.py conversation_items; turns.py TurnSoFar.compacted; week.py take_line, track_context.
  - Check: after `/compact` in a throwaway chat,
    `grep -c '"subtype":"compact_boundary"' "$T"; grep -c '"isCompactSummary":true' "$T"`.
  - Breaks: no "The conversation was compacted" note, the summary shows as your prompt, the context meter
    stays at the old fill, and Recap stops counting compactions.
  - Test: ConversationTests.test_items, CommandsInChatTests.test_compact_keeps_its_note (test_pane.py),
    PromptTests.test_a_forked_chat_counts_its_prompts_and_compactions_once (test_week.py).
- [ ] **Commands you ran.** A command is a user entry (or a system entry with subtype `local_command`) holding
  `<command-name>/x</command-name><command-message>x</command-message><command-args>…</command-args>`. Its
  output comes next as `<local-command-stdout>`/`<local-command-stderr>`, with ANSI kept and `(no content)`
  when empty. A shell `!` line is `<bash-input>`, then `<bash-stdout>`/`<bash-stderr>`. A skill Claude loaded
  itself has a command-name without `/`, and a prompt command (a skill) starts with `<command-message>`.
  `/compact` writes a plain `/compact` prompt, then the compaction, then its command entry. Claude runs
  `/rate-limit-options` by itself at a limit.
  - Used in: commands.py Commands.entry, ran, printed, take (COMMAND_PART, OUTPUT_PART, BASH_INPUT, AUTO,
    SAID_ELSEWHERE, NO_OUTPUT); pane.py conversation_items (COMMAND_TAGS); turns.py turn_prompt_at.
  - Check:

    ```bash
    has command-name command-message local-command-stdout local-command-stderr bash-input bash-stdout
    has '(no content)' rate-limit-options
    ```

    In a throwaway chat, run `/context` and `!ls`, then
    `grep -o '<command-name>[^<]*\|<bash-input>[^<]*\|"subtype":"local_command"' "$T"`.
  - Breaks: commands show as raw tags or vanish, and their output is lost. A skill's turn start is missed
    (wrong working line and timer), and limit options show as your command.
  - Test: CommandsInChatTests.test_a_command_with_and_without_arguments_and_what_it_printed,
    test_a_shell_command, test_compact_keeps_its_note, test_prompt_commands_skills_and_claudes_own,
    test_long_output_is_cut (test_pane.py).
- [ ] **API errors and stand-in replies.** An API error is an assistant entry with `isApiErrorMessage: true`,
  model `<synthetic>`, and the error as its text. Without limit wording, it is an error to retry. A chat
  Claude stopped gets a `<synthetic>` reply "No response requested." with stop_reason `stop_sequence`.
  - Used in: pane.py conversation_items; replies.py TurnEnd.assistant, REPLY_WORDS; turns.py
    TurnSoFar.assistant; talpy_den.py stopped_by, last_turn, kept_step, model_label, transcript_model,
    last_model, agent_end, finished_reply; week.py take_reply.
  - Check: `has isApiErrorMessage`.
    `LC_ALL=C grep -a -o '.\{40\}No response requested\..\{40\}' "$B" | head -1` should show it next to
    `<synthetic>`.
  - Breaks: errors show as Claude's reply, the model tag reads `<synthetic>`, the context meter drops to 0, a
    turn never ends, and Keep going gives up on a turn that broke off.
  - Test: ConversationTests.test_items, SuggestedRepliesTests.test_how_the_turn_ended,
    ContextAndTurnTests.test_context_is_claudes_last_message_of_its_own (test_pane.py);
    AgentTests.test_how_an_agent_can_end (test_talpy_den.py); LinkCacheTests.test_finished_reply_rules
    (test_chats.py); KeepGoingTests.test_a_turn_that_broke_off_on_an_api_error_goes_on_again (test_tasks.py).
- [ ] **quotaLimits on a limit error.** A limit error entry carries `quotaLimits`
  `{status, rateLimitType, resetsAt}`. `rateLimitType` is one of `five_hour`, `seven_day`, `seven_day_opus`,
  `seven_day_sonnet`, `seven_day_overage_included`; `resetsAt` is in epoch seconds.
  - Used in: talpy_den.py stopped_by, limit_stop, note_limit_hits.
  - Check: `has quotaLimits seven_day_overage_included`. After a real limit stop,
    `grep -h -o '"quotaLimits":{[^}]*}' ~/.claude*/projects/*/*.jsonl | tail -3`.
  - Breaks: the reset falls back to parsing the text (a local-time guess), and a shared chat stopped on
    another account fills the wrong account's window.
  - Test: PeekTests.test_what_stopped_it (test_tasks.py).
- [ ] **Stop reasons.** `message.stop_reason` `end_turn`, `stop_sequence` or `max_tokens` ends a turn;
  `tool_use` and `pause_turn` don't, and null means still streaming. A message with a tool_use block never
  ends a turn. replies.py reads the stop reason from the raw line with `"stop_reason":\s*(?:null|"(\w+)")`.
  - Used in: turns.py TurnSoFar.over; replies.py TurnEnd.assistant, reply_records (REPLY_STOP); talpy_den.py
    TURN_ENDS, last_turn, step_text, finished_reply, agent_end, LinkCache.transcript, queued_tasks.
  - Check: `grep -o '"stop_reason":[a-z"_]*' "$T" | sort | uniq -c; has pause_turn`.
  - Breaks: the working line never ends or ends mid-turn, and Keep going thinks a turn broke off. Chips show
    mid-turn, the peek sticks on "writing…", and moved-chat detection breaks.
  - Test: ContextAndTurnTests.test_the_turn_so_far, SuggestedRepliesTests.test_how_the_turn_ended
    (test_pane.py); PeekTests.test_working_on_a_tool (test_talpy_den.py);
    LinkCacheTests.test_finished_reply_rules (test_chats.py).
- [ ] **A closed terminal moves its chat to the background under a new id (2.1.316+).** The new transcript
  starts with copies of the history that keep the old id in snake_case `session_id`, while `sessionId` is the
  new id. `/clear` and `/resume` also leave the old id in `session_id`, but those entries are new (their
  `uuid` isn't in the old transcript). Talpy Den reports the move as `status.moved {old: new}`. The front ends
  follow it, and treat a session whose `sessionId` differs from its `chatId` as one that continues another
  chat, which must not be ended (pane.py gets `--session <id>`). Stars, hides, Keep going and bookmarks follow
  the chat.
  - Used in: talpy_den.py LinkCache.moved_from, LinkCache.copied, chat_moves, moved_chat, continuation,
    follow_moved, note_moved, go_on_with, list_kept, look_after_kept, bookmarks_moved; vscode/src/chatPane.ts
    findPaneRow, ChatPanes.open, sendNow, typeIn; shared/model.ts handoverTarget, goOnAt; main.qml,
    ChatPane.qml.
  - Check: in a throwaway terminal chat, send one prompt and close the terminal window.
    `ls -t $C/projects/$M/ | head -2`, `head -3 <newest>.jsonl | jq -c '{sessionId,session_id,uuid}'`, and
    `jq -c 'select(.kind=="bg")|{sessionId,jobId}' $C/sessions/*.json`.
  - Breaks: the chat is listed twice, and go-ons resume the old id (a second copy at work). Stars, hides,
    bookmarks and Keep going lose the chat, Talpy Chat's window goes stale, and queued messages go to the old
    id.
  - Test: MovedChatTests.test_a_moved_transcript_names_the_chat_it_continues_read_once,
    test_the_go_on_goes_on_with_the_new_id_never_the_old,
    test_its_row_star_bookmarks_keep_and_queued_go_on_follow_it (test_tasks.py);
    BookmarkStoreTests.test_a_moved_chats_bookmarks_follow_it (test_talpy_den.py); vscode/test/pane.test.ts "a
    chat's tab follows the chat Claude moved to the background under a new id", "a message waiting its turn
    goes to the chat's new id when Claude moved it meanwhile"; vscode/test/model.test.ts "a chat Claude moved
    to the background says so where it runs".
- [ ] **The continued-in record.** A shared (hard-linked) transcript gets
  `{type:'continued-in', continuedInSessionId}` when its chat moves on. A chat has moved on when its last
  continued-in comes after its last finished reply (assistant, stop_reason a string, not `isApiErrorMessage`).
  - Used in: talpy_den.py LinkCache.transcript, finished_reply, moved_to, continued_from, place_chats.
  - Check: `has continuedInSessionId`. After a `--bg --resume` of a throwaway shared chat,
    `grep -c '"continued-in"' "$T"`.
  - Breaks: shared chats that moved on are listed twice, or not as their copy.
  - Test: ChatLinkTests.test_continuation_named_by_continued_in_record,
    MovedOnTests.test_chat_that_moved_to_a_copy_is_listed_as_the_copy,
    LinkCacheTests.test_finished_reply_rules, test_first_uuid_skips_entries_without_one (test_chats.py).
- [ ] **How copies are recognised.** A copy Claude makes of a chat starts with the chat's history, so its
  first entry's `uuid` also appears in the original. Talpy Den searches for `"uuid":"<uuid>"` verbatim, with
  no spaces.
  - Used in: talpy_den.py LinkCache.first_uuid, LinkCache.holds, copied_from, chat_link.
  - Check: make a copy (`claude --bg --resume <id held by a running session> 'hi'`), then
    `U=$(jq -r 'select(.uuid).uuid' COPY.jsonl | head -1); grep -c "\"uuid\":\"$U\"" ORIGINAL.jsonl` should be
    1 or more.
  - Breaks: copies of shared chats aren't recognised, and the chat is listed twice.
  - Test: ChatLinkTests.test_copy_found_by_its_history, test_new_conversation_is_not_a_copy (test_chats.py).
- [ ] **The transcript moves when the chat enters a worktree.** Claude then moves the chat's `.jsonl` to
  another `projects/<folder>`. Talpy Chat's watcher catches IN_MOVE_SELF or IN_DELETE_SELF and finds the file
  again.
  - Used in: pane.py WAIT_MASK, wait_for_change, chat_conversation; talpy_den.py LinkCache.copied.
  - Check: in a throwaway chat in a scratch git repository, ask it to enter a worktree, and
    `ls $C/projects/*/<id>.jsonl` before and after.
  - Breaks: Talpy Chat stops updating or says "This chat hasn't started yet".
  - Test: QuickChatTests.test_wait_answers_when_the_transcript_changes (test_pane.py; the move itself isn't
    tested).
- [ ] **cwd on entries.** An entry's `cwd` follows Claude's `cd`: the last one is where the chat runs now, the
  first where it started.
  - Used in: talpy_den.py chat_folder, start_folder, read_chat_info, scan_transcripts; week.py take_line;
    replies.py reply_records; made.py Collector.step, Collector.reply (pictures named by relative path).
  - Check: ask a throwaway chat to `cd /tmp` and run `pwd`, then `grep -o '"cwd":"[^"]*"' "$T" | uniq`.
  - Breaks: Resume, New chat and go-ons open in the wrong folder, Projects and Recap file chats under the
    wrong project, and pictures a reply names by a relative path aren't found.
  - Test: ResumeChatTests.test_resumes_in_the_chats_last_folder (test_jump.py),
    RecapTests.test_a_days_chats_and_a_projects (test_week.py).
- [ ] **timestamp.** Every entry, queue-operation and system entries included, carries `timestamp` as ISO 8601
  UTC (`2026-11-04T21:33:44.123Z`).
  - Used in: pane.py conversation_items; talpy_den.py to_ms, fold_tests, peek_from, scan_transcripts,
    find_chats; week.py take_line, close_turn; replies.py; made.py (a picture newer than the turn); turns.py
    Away (Since you last looked: how far a window showed a chat is the newest of its items' times, and what
    came after is what it did since; the times must grow along the file, on the clock of the computer the
    chat runs on).
  - Check: `jq -r '[.type,.timestamp]|@tsv' "$T" | sort -u -k1,1 | head`.
  - Breaks: times under messages vanish, Recap's work and wait times and timelines go wrong, newest-first
    orders break, a command's new picture isn't told from an old one, and *Since you last looked* counts
    what you saw, or misses what you didn't.
  - Test: ConversationTests.test_items (test_pane.py), TurnTests (test_week.py) (their fixtures write ISO
    times).
- [ ] **The last-prompt record and the peek's tail.** Claude appends `{"type":"last-prompt","lastPrompt":…}`,
  so the end of the file holds your last prompt. The peek reads the last 256 KB (up to 4 MB) and stops once it
  has your prompt, or Claude's reply plus that record. Lines are prefiltered on
  `"type":\s*"(user|assistant|last-prompt|system|permission-mode)"`.
  - Used in: talpy_den.py tail_entries, peek_from, chat_peek, step_text (PEEK_LINE, PEEK_MORE_LINE),
    ChatCache.
  - Check: after a prompt, `grep -c '^{"type":"last-prompt","lastPrompt"' "$T"` should be above 0.
  - Breaks: rows show no prompt or an old one when big tool results fill the end, and each check reads up to 4
    MB.
  - Test: PeekTests.test_last_prompt_record_saves_reading_everything, test_reads_further_back_past_big_lines,
    test_no_old_reply_after_a_new_prompt (test_talpy_den.py).
- [ ] **Entry types Talpy Den ignores.** Seen in 2.1.318 and ignored: `api-request` (about 5 KB each),
  `api-request-blob`, `api-request-shape`, `mode`, `session-owner`, `atis-latch`, `isolation-latch`,
  `tools-used`, `cost-state`; on 2.1.322 also `file-history-delta`, `relocated`, `worktree-state`,
  `permission-mode`, `last-prompt`, `ai-title` and `agent-name` again and again. A new chat's first turn
  writes about 400 KB of `api-request-blob` (its system prompt and tools); in a 6.8 MB chat the
  `api-request` lines were 17% of it, and Talpy Chat's read took the same time with or without them
  (73 / 76 ms, the same items). They still use up the fixed tail windows: peek 256 KB, Talpy Chat 512 KB
  (PANE_TAIL_BYTES), open_tools 256 KB with no growth. week.py skips only lines starting
  `{"type":"api-request`.
  - Used in: talpy_den.py tail_entries, open_tools; pane.py conversation (PANE_TAIL_BYTES); week.py take_line.
  - Check: `grep -o '^{"type":"[a-z-]*"' "$T" | sort | uniq -c` (look for new types). Compare
    `grep '^{"type":"api-request' "$T" | wc -c` with `stat -c %s "$T"`.
  - Breaks: Talpy Chat shows fewer items per read and peeks read further back. A new type that holds
    conversation goes unseen.
  - Test: no test.
- [ ] **Chat names.** In order: a `custom-title` record `{customTitle}` (/rename), `agent-name` `{agentName}`,
  `ai-title` `{aiTitle}`, `summary` `{summary}`, else the first prompt that isn't meta and doesn't start with
  `<` (the panel's notes taken off). Only the first and last 64 KB are read, which relies on Claude writing
  these records again near the end. `cwd` comes from the last user or assistant entry read.
  - Used in: talpy_den.py read_chat_info (TITLE_KINDS), LinkCache.chat_info; week.py take_line (TITLE_LINES),
    chat_label.
  - Check: on a long chat,
    `grep -o '^{"type":"\(custom-title\|agent-name\|ai-title\|summary\)"' "$T" | sort | uniq -c`. After
    `/rename` in a throwaway chat, `tail -c 65536 "$T" | grep -c '"type":"custom-title"'`.
  - Breaks: rows and Talpy Chat are titled with the first prompt or an old name, and a /rename in a long chat
    doesn't show.
  - Test: RecentChatTests.test_name_precedence, test_names_cached_until_the_file_grows (test_chats.py).
- [ ] **Permission mode records.** Each mode change writes `{"type":"permission-mode","permissionMode":…}`,
  and your user entries carry `permissionMode` too (VS Code's panel only on its first prompt). The newest
  wins. A separate `{"type":"mode","mode":"normal"}` record exists in 2.1.318 and isn't read.
  - Used in: talpy_den.py names_mode, mode_of, fold_mode, scan_mode, scan_named, peek_from, go_on_with.
  - Check: in a throwaway chat, Shift+Tab into plan mode and back, then:

    ```bash
    grep -o '"permissionMode":"[a-zA-Z]*"' "$T" | uniq -c
    grep -o '^{"type":"mode","mode":"[a-z]*"' "$T" | sort | uniq -c
    ```
  - Breaks: the mode tag is wrong, and a go-on wakes a plan-mode chat in default mode, or the reverse.
  - Test: ModeTests.test_named_once_then_kept (test_talpy_den.py); PeekTests.test_permission_mode_and_slug,
    ContinueAfterResetTests.test_it_goes_on_in_its_own_permission_mode,
    test_a_panel_chat_goes_on_in_the_mode_its_first_prompt_named (test_tasks.py).
- [ ] **Ultracode shows only as attachments.** Ultracode is visible only as
  `{"type":"attachment","attachment":{"type":"ultra_effort_enter"|"ultra_effort_exit"}}`. One is written with
  the first prompt after a change, then only every few prompts, and ultracode isn't in the status line.
  `--effort ultracode` turns it on and `--effort xhigh` off, also in `respawnFlags` when a background chat is
  woken (live-checked on 2.1.318). Talpy Den takes the newest of the two as the chat's state.
  - Used in: talpy_den.py ULTRA_LINE, ULTRACODE, ultracode_of, fold_ultra, scan_named, tail_entries;
    chatpick.py options_now, pick_value, label; pane.py chat_conversation.
  - Check: `has ultra_effort_enter ultra_effort_exit`. Start a throwaway chat with `--effort ultracode` on a
    model that takes it, send one prompt, then `grep -o '"type":"ultra_effort_[a-z]*"' "$T"`.
  - Breaks: the "· ultracode" tag and the /effort list's check mark are wrong, a go-on loses ultracode, and
    "Turn ultracode on" fails.
  - Test: PeekTests.test_ultracode_as_claude_last_noted_it, RowTests.test_ultracode_stays_on_after_a_big_turn
    (test_tasks.py), ChatPickTests.test_ultracode_on_and_off_for_this_chat (test_pane.py).
- [ ] **Plans and slug.** While a chat has a plan, its entries carry `slug`, and the plan is
  `$C/plans/<slug>.md` (or in the folder a project's `plansDirectory` names). A slug matches
  `^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$` (random words like calm-red-owl). VS Code's Send Feedback is enabled by
  the `when` regex `\.claude[^/]*\/plans\/[^/]+\.md$`.
  - Used in: talpy_den.py peek_from, transcript_slug (SLUG_LINE), SlugCache, PLAN_SLUG;
    vscode/src/planReview.ts SLUG, planPath, planFileOf, agentRun.ts markdownLinkFile, extension.ts
    planFolders, sendFeedback; vscode/package.json (when clause).
  - Check: let a throwaway plan-mode chat (`--permission-mode plan`) write a plan, then
    `grep -o '"slug":"[^"]*"' "$T" | sort -u` and find its file in `$C/plans/`.
    `ls ~/.claude*/plans/*.md | xargs -n1 basename | grep -vE '^[A-Za-z0-9][A-Za-z0-9_-]{0,127}\.md$'` should
    print nothing.
  - Breaks: plans aren't linked to their chat (Projects tab, open plan, Move to project, cleanup keeping a
    plan while its chat stays). Send Feedback and plan comments aren't offered, and Markdown links to plans
    are refused.
  - Test: PeekTests.test_permission_mode_and_slug (test_tasks.py); vscode/test/queue.test.ts "feedback goes
    with the plan files of Claude's config folders", "the widgets' Markdown link opens only their runs and
    Claude's plans"; vscode/test/agentRun.test.ts "only files in the cache's agent-runs folder are opened".
- [ ] **A chat's model.** `message.model` on assistant entries (`claude-opus-5-5`, never `<synthetic>`),
  parsed as `claude-<family>-<major>-<minor>[-date][[1m]]`. A provider id (`us.anthropic.claude-…`) gives None
  in model_label, although model_key handles it. chatpick.py options_now passes chat_model no transcript path,
  so only the status-line snapshot counts there.
  - Used in: talpy_den.py model_label, transcript_model, last_model, chat_model; chatpick.py options_now;
    turns.py TurnSoFar.model; week.py price_model.
  - Check: `grep -o '"model":"[^"]*"' "$T" | sort | uniq -c`.
  - Breaks: the model tag is missing or wrong, the context window is unknown (no meter), a go-on wakes on the
    wrong model, and Recap prices the model as a guess.
  - Test: AgentTests.test_model_label, test_each_agents_model (test_talpy_den.py);
    ChatPickTests.test_what_it_uses_now (test_pane.py; chat_model mocked);
    PriceTests.test_a_model_the_list_doesnt_know (test_week.py).
- [ ] **Where a long turn starts.** A turn starts at your prompt, or at a prompt command whose text begins
  with `<command-message>`. Tool-result lines contain `"tool_use_id"` and are skipped. Steps are tool_use
  blocks in assistant lines that aren't sidechain.
  - Used in: turns.py turn_prompt_at, tool_calls, turn_backward, turn_forward, turn_before, TurnSoFar.now.
  - Check: in a throwaway chat that runs a skill,
    `grep -o '"content":"<command-message>' "$T" | head -1; grep -c '"tool_use_id"' "$T"`.
  - Breaks: "working for Xm · N steps" is wrong or missing for turns longer than what Talpy Chat reads.
  - Test: ContextAndTurnTests.test_the_turn_so_far,
    test_a_long_turn_counts_from_its_prompt_before_what_is_read (test_pane.py).
- [ ] **Tool results.** A result is a user entry with tool_result blocks
  `{tool_use_id, content (a string, or text, image or document blocks), is_error}`. There is one result per
  entry, so the entry's `toolUseResult` belongs to it. Errors are wrapped in `<tool_use_error>`. Read output
  has numbered lines matching `^\s*\d+[\t→]`, which the front ends draw as a numbered, coloured listing.
  - Used in: pane.py result_text, tool_summary (READ_LINE, TOOL_ERROR), conversation_items; talpy_den.py
    tool_result_md; week.py take_user; replies.py reply_records (REPLY_FAILED); made.py results_of;
    codeview.mjs READ_LINE, readLines; codehtml.mjs; vscode/webview/components/CodeView.tsx.
  - Check: `grep -c '<tool_use_error>' "$T"`. Compare `grep -o '"content":\[{"tool_use_id"' "$T" | wc -l` with
    `grep -c '"type":"tool_result"' "$T"`. After a Read:

    ```bash
    jq -r 'select(.type=="user")|.message.content[]?|select(.type=="tool_result")|.content|if type=="array" then (.[0].text // "") else . end' "$T" | grep -m3 -P '^\s*\d+(\t|→)'
    ```
  - Breaks: tool lines summarize wrongly ("0 lines" for a Read, error text with its tags), edit diffs are
    lost, tool statuses stay open, and Read steps show as plain text.
  - Test: ConversationTests.test_what_came_of_each_tool_call, test_items,
    CodeViewTests.test_rows_side_by_side_and_what_changed (test_pane.py).
- [ ] **is_error on Bash results.** A Bash tool_result has `is_error: true` when the command exits non-zero,
  and false or no `is_error` when it succeeds.
  - Used in: talpy_den.py fold_tests, scan_tests, TestsCache, is_test_run (Review tab: tests since the last
    edit); replies.py REPLY_FAILED, TurnEnd; pane.py conversation_items; turns.py Away.done (Since you last
    looked: *tests passed* or *tests failed*, and the files an edit that went through changed).
  - Check: tell a throwaway chat 'With the Bash tool run exactly: false, then exactly: true.' Then:

    ```bash
    jq -c 'select(.type=="user")|.message.content[]?|select(.type=="tool_result")|{is_error}' "$T" | tail -2
    ```

    It should give true, then false or null.
  - Breaks: the Review tab says tests passed when they failed, or the reverse, and chips and step statuses
    misjudge a failed command.
  - Test: TestsAfterEditTests.test_tests_since_the_last_edit, test_what_counts_as_a_test_run,
    AwayTests.test_since_your_last_message (test_pane.py; is_error from fixtures).
- [ ] **Edit results.** Edit and MultiEdit results carry `toolUseResult`
  `{filePath, originalFile, structuredPatch:[{oldStart, oldLines, newStart, newLines, lines}]}`. A Write that
  creates a file gives `{type:'create', content}`. The Review tab takes a file's content before the chat from
  the first such result when Claude kept no backup (a file outside the chat's folder).
  - Used in: pane.py edit_lines, conversation_items, tool_originals, originals.
  - Check: `has structuredPatch originalFile`. In a throwaway chat that edits one file and creates one,
    `grep -o '"toolUseResult":{"[a-zA-Z]*"' "$T" | sort | uniq -c` and
    `jq -c 'select(.toolUseResult.filePath)|.toolUseResult|{type,f:.filePath,o:(.originalFile|type)}' "$T"`.
  - Breaks: diffs fall back to the call's own diff (no file line numbers), a new file shows no content, and
    the Review tab's "before" falls back to git or is unknown.
  - Test: ConversationTests.test_an_edits_diff_shows_under_it, test_older_edits_keep_a_glimpse_of_their_diff
    (test_pane.py).
- [ ] **Tool names and their input fields.** Talpy Den reads Bash `{command, description}`,
  Read/Edit/Write/MultiEdit/NotebookEdit `{file_path or notebook_path}`, Edit
  `{old_string, new_string, replace_all}`, MultiEdit `{edits[]}`, Write `{content}`, Grep/Glob
  `{pattern, path}`, WebFetch `{url}`, WebSearch `{query}` and Skill `{skill}`. It also reads Agent (Task in
  older Claude) `{subagent_type, description, prompt}`, AskUserQuestion, ExitPlanMode, and MCP tools named
  `mcp__<server>__<tool>`. The tool names are documented, the input fields aren't.
  - Used in: talpy_den.py describe_tool, tool_call_md, EDIT_TOOLS, EDIT_LINE, SUBAGENT_TOOLS, fold_tests,
    WRITE_CALL, BASH_CALL, FILE_PATH_VALUE, COMMAND_VALUE; pane.py EDITS, tool_summary, tool_input_text,
    edit_lines; made.py STEP_TOOLS, TOOLS, Collector.step; week.py USER_TOOLS, EDIT_TOOLS, FILE_TOOLS,
    SUBAGENT_TOOLS, COUNTED_TOOLS; live_hook.py describe, lines_changed.
  - Check: ask a throwaway chat for one Bash, Read, Grep, Edit, Write and WebFetch call and one subagent,
    then:

    ```bash
    jq -c 'select(.type=="assistant")|.message.content[]?|select(.type=="tool_use")|{name,k:(.input|keys)}' "$T" | sort -u
    ```
  - Breaks: tool lines show only the tool's name, edit diffs, +/− counts and made files vanish. Recap's counts
    per tool and its edited files go wrong, test runs and plan writes go unseen, and a renamed subagent tool
    isn't taken for one.
  - Test: ConversationTests.test_what_came_of_each_tool_call, test_an_edits_diff_shows_under_it
    (test_pane.py), LiveHookTests.test_a_turn_step_by_step (test_live.py), MadeItemsTests (test_made.py)
    (their fixtures write the names).
- [ ] **What Claude made (made.py).** Talpy Chat shows a picture (png, jpg, gif, webp, svg), a page (html) or
  a plan (Markdown in a `plans` folder: `$C/plans`, a project's `.claude/plans`) under the step that made it,
  all from the transcript. It reads: Write, Edit, MultiEdit and NotebookEdit calls'
  `file_path`/`notebook_path` (an absolute path) and Write's `content`; a Read result's image blocks
  `{type:'image', source:{media_type, data}}` (what Claude saw, kept in the transcript), its `document` blocks
  (a PDF) and `toolUseResult.file.originalSize`; a Bash result's text naming a picture file newer than the
  turn; picture paths a reply names. Unfolding one (`pane.py --made`) finds the file's name in the transcript
  as JSON writes it, and a Read's picture by its `tool_use_id`.
  - Used in: made.py Collector.step, Collector.reply, Collector.place, results_of, type_of, in_plans,
    named_paths, named_in, seen_in, lines_with, show, keep_copy; pane.py conversation, conversation_items,
    --made.
  - Check: in a throwaway chat, ask it to write `a.svg`, Read a png, and run `ls *.png`. Then:

    ```bash
    jq -c 'select(.type=="user")|.message.content[]?|select(.type=="tool_result")|.content|arrays|.[]|select(.type=="image" or .type=="document")|{type,m:.source.media_type}' "$T"
    ```

    And `jq -c 'select(.toolUseResult.file)|.toolUseResult.file|{originalSize}' "$T"`. Talpy Chat should show
    a line under each of those steps.
  - Breaks: made lines vanish (if a Read's image moves out of the transcript, say to `image-cache/`), sizes
    show as unknown, or unfolding says the chat didn't make that file.
  - Test: MadeItemsTests.test_a_written_picture_page_and_plan_under_their_steps,
    test_read_results_that_carry_an_image, test_a_command_that_names_a_new_picture,
    test_pictures_a_reply_names_that_are_there, ShowMadeTests.test_what_claude_saw_comes_from_the_transcript,
    test_only_a_file_the_chat_made_of_those_types (test_made.py; fixtures); vscode/test/made.test.ts.
- [ ] **AskUserQuestion and ExitPlanMode as written.** AskUserQuestion's input is
  `{questions:[{question, header, multiSelect, options:[{label, description}]}]}`. Its result's
  `toolUseResult` is `{questions, answers:{question: text}, annotations:{question:{notes}}}`. Multi-select
  answers are joined with `, ` (JSON-quoted where needed), and no answer gives "The user did not answer the
  questions.". ExitPlanMode's input is `{plan, planFilePath}`, and an approved plan's `toolUseResult` is
  `{plan}`.
  - Used in: pane.py asked_of, your_answer, split_answer, picked_labels; talpy_den.py question_view,
    plan_view, permission_view.
  - Check: `has 'The user did not answer the questions.'`. Ask a throwaway chat for 'a multiple-choice
    question with AskUserQuestion', answer it in the terminal, then
    `grep -o '"toolUseResult":{"questions".\{0,300\}' "$T" | head -1`.
  - Breaks: question and plan cards stay open or show no picked answers, your typed notes are lost, and plans
    lose their text.
  - Test: AnswersInChatTests.test_one_question, test_several_questions_multi_select_typed_and_notes,
    test_plan, test_split_answer, HookTests.test_a_plans_view (test_pane.py).
- [ ] **Which call a permission prompt is about.** Claude's tool queue (canExecuteTool and processQueue, read
  in 2.1.314) runs a reply's calls in order. A call that can change something runs alone, after every call
  before it, while reads can run together. So the oldest tool_use without a result in the last turn is the one
  asking. It is "sure" only when one call is open and it isn't Agent or Task. open_tools reads only the last
  256 KB and never further.
  - Used in: talpy_den.py open_tools, pending_tool, pending_permission, chat_tool_use; pane.py main (--keys
    --expect).
  - Check: `has canExecuteTool` (2 on 2.1.318 and 2.1.322; 0 means re-read the queue code). In a throwaway
    chat in default mode, ask for two file writes in one reply and see which prompt shows first. While a tmux
    dialog shows, run:

    ```bash
    tail -n 20 "$T" | jq -c 'select(.type=="assistant") | .message.content[]? | select(.type=="tool_use") | {id,name}'
    ```
  - Breaks: Allow or Deny from a row, a notification or Talpy Chat goes to the wrong call. Keys refuse ("It
    asks something else now"), or are pressed for another prompt.
  - Test: PermissionViewTests.test_the_oldest_call_without_a_result,
    ToolUseTests.test_no_keys_for_a_call_that_may_not_be_the_one_asked_about,
    test_keys_for_the_call_it_asks_about (test_pane.py).
- [ ] **Permission prompts you answered.** The tool result's `permissionDecision.source` starting with `user`
  means you answered, and `decision` `accept` means you allowed. `reasonCode` `safetyCheck` means the call is
  never suggested as a rule. The wait is measured from the tool_use's time to the result's.
  - Used in: week.py take_user, permission_prompts, rule_for.
  - Check: `has reasonCode safetyCheck`. After answering one prompt in a throwaway default-mode chat,
    `grep -o '"permissionDecision":{[^}]*}' "$T"`.
  - Breaks: the Permissions tab shows 0 prompts or wrong rules, and Recap's waiting-for-you time is wrong.
  - Test: PromptTests.test_rules_for_the_prompts_you_answered,
    TurnTests.test_waiting_for_your_permission_isnt_work (test_week.py).
- [ ] **turn_duration.** A system entry with subtype `turn_duration` and `durationMs` is written when a turn
  ends: Claude's own work time, without waits. Without it, a turn ends at the next prompt.
  - Used in: week.py take_line, close_turn.
  - Check: `has turn_duration; grep -c '"subtype":"turn_duration"' "$T"`.
  - Breaks: Recap's "Claude worked" time includes your waits and long pauses.
  - Test: TurnTests.test_without_turn_records_a_turn_ends_at_the_next_prompt,
    test_waiting_for_your_permission_isnt_work, test_a_prompt_sent_while_claude_works_is_the_same_turn
    (test_week.py).
- [ ] **Usage fields and /usage's scheme.**
  `usage.{input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens}`,
  `cache_creation.ephemeral_1h_input_tokens`, `server_tool_use.web_search_requests`, `usage.speed` `fast`,
  `usage.inference_geo` `us`, `effort` `max` on the entry, and `attributionPlugin`, `attributionMcpServer`,
  `attributionAgent`, `attributionSkill`. The weights mirror /usage: cache read 1, input 10, cache write 12.5,
  output 50, times a model tier (fable 10, opus 5, sonnet 3, haiku 1). /usage's thresholds: 100k uncached,
  150k context, 40k always-on, a large result as bytes/2.5 over 10k, 4 chats per 5 minutes, 8 hours. The first
  prompt's size comes from `"attachment":{"type":"file"` lines.
  - Used in: week.py usage_values, take_reply, track_context, usage_weight, model_tier, price_key, take_user,
    the USAGE_ constants; talpy_den.py scan_transcripts, fold_stats.
  - Check:

    ```bash
    has inference_geo ephemeral_1h_input_tokens web_search_requests attributionSkill attributionAgent
    has attributionPlugin attributionMcpServer
    ```

    In a throwaway chat in tmux, compare /usage's "contributing to your limits" list with the Recap tips.
  - Breaks: Recap costs, plan weights and tips drift from Claude's /usage, and fast mode or US-only prices are
    missed.
  - Test: PriceTests.test_the_same_cost_as_claude_code, test_weights_as_claude_codes_usage,
    TipTests.test_tips_from_transcripts, test_a_behavior_from_a_tenth_of_the_usage (test_week.py).
- [ ] **File-history records.** `file-history-snapshot`
  `{messageId, snapshot:{trackedFileBackups:{path:{backupFileName, version, realParentDir}}}, isSnapshotUpdate}`
  and `file-history-delta` `{trackingPath, backup, snapshotMessageId}`. Backups are kept per session id
  (`sessionId` on the lines) as `$C/file-history/<session id>/<backupFileName>`.
  - Used in: talpy_den.py fold_edits, backup_target, backup_name, note_backup, scan_edits (SESSION_ID_FIELD),
    chat_edits; pane.py backup_content, originals.
  - Check:

    ```bash
    has file-history-delta realParentDir
    grep -o '"type":"file-history-[a-z]*"' "$T" | sort | uniq -c
    ls $C/file-history/$ID/ | head
    ```
  - Breaks: the Review tab, changed-file lists, overlap warnings and Undo lose the "before" versions.
  - Test: ChangedFilesTests.test_backed_up_created_and_edited_files, test_first_backup_and_last_turn,
    test_older_snapshot_updates (test_talpy_den.py).
- [ ] **Subagents.** A subagent's report is its SubagentHandback tool call's `input.message`. `origin.kind`
  `coordinator` on a user entry means its chat sent it more. A fork's first prompt is Claude's rules, then
  `</fork-boilerplate>` and `Your directive:`. `projects/*/<id>/subagents/agent-<agentId>.meta.json` gives
  `finished`, `spawnDepth`, `toolUseId`, `agentType`, `description` and `requestShape` (`background` for
  background agents). A nested agent's parent is the agent transcript that holds its `toolUseId`.
  - Used in: talpy_den.py AgentCache.session_agents, AgentCache.progress, AgentCache.parent, agent_progress,
    agent_end, agent_status, agent_steps, agent_task, agent_run_markdown, find_agent_transcript, fold_stats.
  - Check: `has SubagentHandback fork-boilerplate 'Your directive:' spawnDepth requestShape agentType`. After
    a throwaway chat ran a subagent (and one in the background):

    ```bash
    jq -c '{finished,spawnDepth,toolUseId,agentType,description,requestShape}' $C/projects/$M/*/subagents/agent-*.meta.json
    ```
  - Breaks: agent rows stay "running" and reports go missing. The boilerplate shows as the task, nested agents
    lose their parent, and background agents aren't marked.
  - Test: AgentTests.test_how_an_agent_can_end, test_a_forks_task_is_its_directive,
    test_a_message_from_its_chat_wakes_a_finished_agent, test_a_forks_copy_of_the_call_isnt_its_work
    (test_talpy_den.py; meta.json from fixtures).
- [ ] **Rebuilding a plan for plan feedback.** Talpy Den rebuilds the plan as Claude last wrote it by
  replaying the chat's calls on `plans/<slug>.md`. A Write's content replaces the plan. An Edit replaces the
  first occurrence of `old_string` (every one with `replace_all`), and a MultiEdit applies its edits in order.
  An empty `new_string` also takes the line's newline, and a refused call (`is_error`) changes nothing.
  ExitPlanMode's `input.plan`, with `planFilePath` ending in `/<slug>.md`, is the plan.
  - Used in: talpy_den.py claude_plan, apply_plan_tool, PLAN_TOOLS, plan_feedback; jump.py send_plan_feedback.
  - Check: have a throwaway plan-mode chat write a plan and then change one line of it.

    ```bash
    python3 -I -c 'import sys,pathlib;sys.path.insert(0,sys.argv[1]);import talpy_den as t;print(t.claude_plan(pathlib.Path(sys.argv[2]),sys.argv[3]),end="")' "$TD" "$T" <slug> | diff - $C/plans/<slug>.md
    ```

    It should print nothing.
  - Breaks: plan feedback reports Claude's own edits as yours, or says nothing changed.
  - Test: PlanFeedbackTests.test_claudes_version_is_rebuilt_from_its_transcript,
    test_a_line_claude_took_out_goes_with_its_line_break (test_tasks.py).
- [ ] **Pictures pasted into Claude.** A picture pasted into Claude's terminal or panel is stored inline as an
  image block of your user entry:
  `{type:'image', source:{type:'base64', media_type:'image/png'|'image/jpeg'|'image/webp'|'image/gif', data}}`.
  - Used in: pane.py prompt_pictures, PICTURE_TYPES, PICTURE_MAX, conversation_items.
  - Check: paste a small picture into a throwaway chat, then:

    ```bash
    jq -c 'select(.type=="user")|.message.content[]?|select(.type=="image")|{t:.source.type,m:.source.media_type,n:(.source.data|length)}' "$T"
    ```
  - Breaks: such pictures get no thumbnails in Talpy Chat (if Claude moves them to `image-cache/`, say).
  - Test: QuickChatTests.test_your_pictures (test_pane.py).
- [ ] **Colours in command output.** The output of local commands (`/context`, `!cmd`) keeps its ANSI colour
  codes. The front ends draw only SGR colour codes and drop every other escape (cursor moves, titles, links).
  - Used in: ansi.mjs runs, html; CommandOutput.qml; vscode/webview/chat.tsx CommandOutput.
  - Check: in a throwaway chat, run `!ls --color=always /` and `/context`, then:

    ```bash
    grep -hE 'local-command-stdout|bash-stdout' "$T" | tail -2 | cat -v | grep -o '\^\[[^a-zA-Z]*[a-zA-Z]' | sort | uniq -c
    ```
  - Breaks: little: colours are lost or links stripped, and the text stays readable.
  - Test: AnsiTests.test_colours_and_the_rest_left_out (test_pane.py).
- [ ] **Sharing a chat between accounts.** Talpy Den hard-links the transcript into each profile's
  `projects/<key>/`, and symlinks `projects/<key>/<id>/` and `file-history/<id>/` to a store. It relies on
  Claude appending to the transcript in place (never writing a new file and renaming it over the link),
  writing plans in place, and following the symlinked folders for subagents, tool results and checkpoints; on
  its cleanup removing only the link; on `claude --resume` on the other account finding the linked transcript;
  and on only one session having a chat open at a time.
  - Used in: sharing.py share, keep_only, link_into, share_plan, share_chat_plan, give_to, continue_command,
    chat_to_delete, chat_jobs; talpy_den.py LinkCache, discover_profiles; cleanup.py.
  - Check: share a throwaway chat (`python3 -I $TD/jump.py --share <id>`), continue it on the other account
    (`python3 -I $TD/jump.py --continue <id> --profile <other>`) and send one prompt there.
    `stat -c '%i %h %s %n' ~/.claude*/projects/<key>/<id>.jsonl` should show one inode with 2 or more links,
    and `ls -l ~/.claude*/projects/<key>/<id> ~/.claude*/file-history/<id>` should still be links.
  - Breaks: after one turn each account holds its own copy (the chat forks without a word), checkpoints or
    subagents vanish on one account, or one account's cleanup deletes what the other still uses.
  - Test: SharedChatActionTests (test_jump.py),
    ChatTests.test_a_chat_shared_between_accounts_goes_whole_once_every_copy_is_old,
    test_a_shared_chat_an_account_still_has_keeps_its_store (test_cleanup.py),
    SharingTests.test_the_hosts_accounts_can_share (test_remote.py). These check the file layout only, never
    Claude writing.

## Hooks

- [ ] **PermissionRequest input.** The hook reads `session_id`, `transcript_path`, `cwd`, `permission_mode`,
  `tool_name`, `tool_input` and `permission_suggestions`. Undocumented: `tool_use_id` is absent (2.1.311; used
  only if a string shows up), and the suggestions' shapes are
  `{type: setMode|addRules|addDirectories, mode, behavior:'allow', rules:[{toolName, ruleContent}], directories:[…], destination: session|cliArg|localSettings|projectSettings|userSettings}`.
  Always allow sends these back unchanged as `updatedPermissions`. For a file edit Claude suggests only
  `setMode` `acceptEdits`, so the button reads "Allow all edits" (ALWAYS_LABELS).
  - Used in: permission_hook.py main; talpy_den.py always_allow, always_label, ALWAYS_LABELS, ALWAYS_MODES,
    ALWAYS_WHERE, request_view, permission_view; pane.py decision_of.
  - Check:

    ```bash
    (cd "$S" && claude --model haiku --setting-sources project,local --settings '{"hooks":{"PermissionRequest":[{"matcher":"*","hooks":[{"type":"command","command":"cat >> /tmp/pr.jsonl; echo >> /tmp/pr.jsonl"}]}]}}')
    ```

    Ask it to 'run touch x', then 'edit a.txt', and answer No in its dialog. Then
    `jq -c '{k:keys, s:.permission_suggestions}' /tmp/pr.jsonl`.
  - Breaks: if `session_id` is renamed, requests are dropped, so no Allow or Deny shows anywhere. A new
    suggestion type or destination is dropped, so Always allow has no words and becomes a one-time Allow.
  - Test: HookTests.test_the_widget_answers, test_the_tool_call_it_asks_about, PermissionViewTests,
    PermissionViewTests.test_always_allow_says_all_it_does (test_pane.py).
- [ ] **The hook runs beside Claude's dialog.** Whichever answers first counts. A decision printed on stdout
  minutes or hours later (`{"hookSpecificOutput":{"hookEventName":"PermissionRequest","decision":{…}}}`) is
  still taken. A hook that exits 0 with no output leaves the dialog to decide. Claude doesn't wait for the
  hook before it shows its dialog, and the hook gives up after 5 s (NO_DIALOG_S) if the chat never shows
  "waiting". install.sh turns the relay and live hooks on through `pane.py --relay`/`--live`.
  - Used in: permission_hook.py main (NO_DIALOG_S, LONGEST_S); pane.py answer_request; vscode/src/relay.ts;
    install.sh hook, relay, live, uninstall.
  - Check: with the relay on (`python3 -I $TD/pane.py --relay status`), ask a throwaway chat in tmux, started
    without `--setting-sources`, to 'run touch x'. While the dialog shows,
    `ls ~/.local/state/talpy-den/permissions/`, then `python3 -I $TD/pane.py --answer <id> --decision allow`:
    the dialog should close and touch should run. Repeat and answer in the terminal instead: the request file
    should go within about 1 s, and `pgrep -af permission-hook.py` should be empty.
  - Breaks: if Claude waits for the hook before its dialog, nothing is relayed and terminal users see nothing
    until the timeout. If Claude ignores a late decision, or kills the hook when its dialog is answered, Allow
    and Deny from Talpy Den do nothing ("The chat didn't take the answer: answer it there").
  - Test: HookTests.test_the_widget_answers, test_answered_in_the_chat,
    test_run_through_a_shell_it_finds_its_claude (test_pane.py; a stand-in Claude),
    InstallTests.test_the_permission_hook_with_plasma (test_install.py).
- [ ] **A hook is Claude's own child.** Claude runs a hook's command with `sh -c` as its own child process
  (dash can stay in between unless the command starts with `exec`). Walking `/proc` parents and skipping
  shells therefore reaches Claude's pid, the `<pid>` in `sessions/<pid>.json`. The live hook stores that pid,
  and a row shows a live file only when it equals the session's pid.
  - Used in: permission_hook.py claude_pid, parent_of, SHELLS; live_hook.py claude_pid, main; talpy_den.py
    live_view; pane.py hook_command (exec).
  - Check:

    ```bash
    (cd "$S" && claude --model haiku --setting-sources project,local --settings '{"hooks":{"UserPromptSubmit":[{"hooks":[{"type":"command","command":"ps -o pid=,comm= -p $PPID >> /tmp/hookparent"}]}]}}')
    ```

    Send 'hi', then `cat /tmp/hookparent`. It should be claude, or sh with a claude parent, and the pid should
    be in `ls $C/sessions`.
  - Breaks: if hooks run from a helper (the service, a worker, a hook runner), the permission hook watches the
    wrong session file and leaves at once or after 5 s, and live rows lose their live view.
  - Test: HookTests.test_claudes_process_through_shells (test_pane.py),
    ThroughAShellTests.test_old_and_new_commands (test_live.py).
- [ ] **AskUserQuestion is answered through PermissionRequest.** An answer is an allow whose `updatedInput` is
  the call's input plus `answers: {question text: answer}`. A question has at most 4 options. Several picks
  are joined with `, `, and an option containing `, ` or a quote is JSON-quoted, as Claude's own dialog writes
  it. A typed answer replaces the options. Declining is a deny with a message and `interrupt: true`.
  - Used in: pane.py answer_text, question_answers, decision_of, answer_request; talpy_den.py question_view,
    ASK_TOOL; vscode/src/shared/pane.ts oneChoice, joinAnswer, answerText, answerKind, answersOf, chipsOf;
    QuestionForm.qml, PermissionAsk.qml; vscode/webview/chat.tsx.
  - Check: with the relay on, tell a throwaway chat 'Use AskUserQuestion to ask me two questions, one
    multiSelect'. Answer with
    `python3 -I $TD/pane.py --answer <id> --decision answer --answers '{"<q1>":["A","B, c"],"<q2>":["X"]}'`.
    `grep -o '"answers":{[^}]*}' "$T"` should show `A, "B, c"`. Compare with one answered in the terminal.
  - Breaks: Claude asks again or gets no answers. The question card shows the wrong picks, and your shown
    answer never matches the transcript (it drops after 30 s).
  - Test: HookTests.test_a_question, test_answers_as_claudes_dialog_sends_them,
    AnswersInChatTests.test_several_questions_multi_select_typed_and_notes (test_pane.py);
    vscode/test/pane.test.ts "a question's answers go to the hook's request as JSON; none chosen, nothing
    goes", "answers a page sends: {question: [strings]}, not too many", "your answer as the conversation will
    have it: …".
- [ ] **ExitPlanMode is answered through PermissionRequest (checked on 2.1.311).** An allow must carry the
  call's input as `updatedInput`.
  `updatedPermissions [{type:'setMode', mode:'acceptEdits', destination:'session'}]` switches the chat to
  accepting edits. A deny's message becomes plan feedback, and Claude keeps planning.
  - Used in: pane.py plan_decision, answer_request, answer_oldest; talpy_den.py PLAN_TOOL, plan_view.
  - Check: with the relay on, start a throwaway chat with `--permission-mode plan` and ask it to 'plan
    creating a.txt'. `python3 -I $TD/pane.py --answer <id> --decision approve-edits`: it should start with no
    edit prompts. In a second throwaway chat, `--decision keep --note 'use b.txt'`: it should plan again.
  - Breaks: an approve that drops the input leaves Claude with an empty plan. If setMode is ignored, edits
    still prompt. If a keep-planning deny ends the turn, the feedback is lost.
  - Test: HookTests.test_a_plan_is_approved_or_planned_on, test_a_plans_view,
    test_keyboard_answers_take_the_oldest_prompt (test_pane.py).
- [ ] **Hook denies are written back verbatim.** Talpy Den sends
  `{behavior:'deny', message:'The user denied this and said: <note>'}` (or "The user didn't answer…", "…wants
  to keep planning…", or with no note "…denied this." plus `interrupt: true`). Claude writes that message as
  the tool_result text, sometimes followed by `\n\nNote: The user's next message may contain`, and stamps
  `permissionDecision {decision:'reject', source:'hook'}`.
  - Used in: pane.py decision_of, plan_decision, OUR_NO, NEXT_NOTE, rejection, your_answer.
  - Check: deny with a note (`python3 -I $TD/pane.py --answer <id> --decision deny --note 'use make test'`),
    then `grep -n 'The user denied this' "$T"` and
    `jq -c 'select(.permissionDecision) | .permissionDecision' "$T"`.
  - Breaks: if Claude rewords or prefixes the message, or drops `source` `hook`, your note doesn't show as
    yours (it shows as an error). If `interrupt` is ignored, Claude carries on after a bare Deny.
  - Test: AnswersInChatTests.test_deny_with_a_note, test_declined, test_plan, HookTests.test_decisions
    (test_pane.py).
- [ ] **A chat's own hook through `--settings`.** Chats Talpy Chat starts or wakes in the background (here, on
  an SSH host or in a container) get the permission hook, and the env for predictions, through
  `claude --settings '<JSON>'`. Talpy Den relies on four things: these hooks add to yours rather than replace
  them; they run in a background session; Claude saves the `--settings` value verbatim in `respawnFlags` and
  applies it again at every wake and after a mode change; and a copy Claude makes doesn't carry it, so Talpy
  Den adds it. No hook of its own is given where the account's settings already have the relay, or where
  managed settings allow only their own hooks.
  - Used in: pane.py chat_hook_of, chat_hook, place_hook, start_chat, send_now, go_on_in_background;
    talpy_den.py continue_chat, go_on_with, hook_settings, saved_options, has_settings_flag,
    managed_hooks_only.
  - Check:

    ```bash
    (cd "$S" && claude --bg --model haiku --setting-sources project,local --settings '{"env":{"TALPY_T":"1"}}' 'say hi')
    ```

    `jq .respawnFlags $C/jobs/<short>/state.json` should hold `--settings` and the JSON.
    `claude stop <short>; claude --bg --resume <id> 'hi again'`, then
    `tr '\0' '\n' < /proc/<worker pid>/environ | grep TALPY_T`. Also open `claude attach <short>`, change the
    mode with Shift+Tab and detach: `respawnFlags` should still hold `--settings`.
  - Breaks: if `--settings` isn't kept, at a wake or after a mode change, a woken background chat asks
    permission prompts nobody can answer and stalls. If these hooks replace yours, your other hooks stop
    running in those chats.
  - Test: TalpyChatHookTests.test_a_new_chat_starts_in_the_background_with_its_own_hook,
    test_a_stopped_background_job_gets_it_in_its_saved_options, test_a_copy_of_a_hooked_chat_keeps_its_hook,
    test_no_hook_of_its_own_where_the_hook_runs_anyway_or_cant, test_the_command_line (test_pane.py). The
    mode-change rewrite: no test.
- [ ] **Live hook events and fields.** All events carry `session_id`, `cwd`, `transcript_path` and
  `hook_event_name`. SessionStart has `source` `startup`/`clear`. Tool events carry `tool_name`, `tool_input`,
  `tool_use_id`, and `agent_id` on a subagent's calls. PostToolUseFailure has `error`. PermissionRequest has
  no `tool_use_id` (it is matched by tool and description) and has `agent_id` for a subagent's. Notification's
  `notification_type` is `permission_prompt`, `elicitation_dialog` or `idle_prompt`. Stop has
  `last_assistant_message`, StopFailure `error` and `error_details`, and SubagentStart/Stop `agent_id` and
  `agent_type`. Undocumented: `agent_id` on tool events, the PostToolUseFailure and StopFailure fields,
  `last_assistant_message`, and the missing `tool_use_id` on PermissionRequest.
  - Used in: live_hook.py fold, describe, first_line, main; pane.py LIVE_EVENTS, TOOL_EVENTS; live.py
    URGENT_EVENTS.
  - Check:

    ```bash
    (cd "$S" && claude --model haiku --setting-sources project,local --settings "$(jq -nc '{hooks:(["PreToolUse","PostToolUse","PostToolUseFailure","PermissionRequest","Notification","Stop","StopFailure","SubagentStart","SubagentStop"]|map({key:.,value:[{matcher:"*",hooks:[{type:"command",command:"cat >> /tmp/ev.jsonl
    echo >> /tmp/ev.jsonl"}]}]})|from_entries)}')")
    ```

    Run a failing Bash, an Edit and an Agent call, then
    `jq -c '{e:.hook_event_name,k:keys}' /tmp/ev.jsonl | sort -u`.
  - Breaks: if an event is renamed, Claude may reject the settings and live mode stops. If fields go missing,
    rows lose "doing", steps, the failure text and subagent lists, and urgent wake-ups are missed.
  - Test: LiveHookTests.test_a_turn_step_by_step, test_failures_new_files_and_questions, test_subagents,
    test_what_it_ignores (test_live.py).
- [ ] **PostToolUse structuredPatch.** For Edit, Write, MultiEdit and NotebookEdit,
  `tool_response.structuredPatch` is a list of hunks whose `lines` start with `+` or `-`. A new file's Write
  gives `type` `create` with an empty patch, so its lines are counted from `tool_input.content`.
  - Used in: live_hook.py lines_changed.
  - Check: with the `/tmp/ev.jsonl` recipe above, ask for one edit and one new file, then:

    ```bash
    jq -c 'select(.hook_event_name=="PostToolUse") | .tool_response | {type, n:(.structuredPatch|length)}' /tmp/ev.jsonl
    ```
  - Breaks: the +N/−N counts on live steps disappear. Nothing crashes.
  - Test: LiveHookTests.test_a_turn_step_by_step, test_failures_new_files_and_questions (test_live.py).

## Settings

- [ ] **Hook entries in settings.json.** The relay is
  `hooks.PermissionRequest = [{matcher:'*', hooks:[{type:'command', command:"[ -f '<copy>' ] || exit 0; exec python3 -I '<copy>'", timeout:86400}]}]`.
  Live mode is 13 events (LIVE_EVENTS) with `async: true` and `timeout: 10`, and matcher `*` on tool events
  only. Undocumented details Talpy Den relies on: a 24 h timeout is honoured (a prompt can wait for hours);
  the command runs under sh, so `[` and `exec` work; exit 0 with no output means no decision (python3 on a
  missing file, exit 2, would refuse); async hooks don't block and can overlap, so the live hook takes a
  flock; chats started after the edit use hooks written from outside, with no /hooks review.
  - Used in: pane.py HOOKS, HOOK_TIMEOUT_S, hook_command, set_hook, install_hook, upgrade_hooks, relay, live;
    talpy_den.py HOOK_GUARD, refresh_hooks, upgrade_hook_settings; live_hook.py main (flock).
  - Check: with the relay and live mode on (`python3 -I $TD/pane.py --relay on`, `--live on`),
    `jq '.hooks | keys' $C/settings.json`. A new throwaway chat started without `--setting-sources` should
    show no settings warning. Ask it for a permission and leave it for 11 minutes or more:
    `pgrep -af permission-hook.py` should still list the hook, and `pane.py --answer` should still work.
  - Breaks: if Claude caps hook timeouts, relayed prompts die after the cap. If async is dropped, the live
    hook blocks each tool call for up to 10 s. If validation rejects the entry, the whole settings.json is
    flagged. If outside edits need a /hooks review, turning the relay on does nothing for new chats.
  - Test: RelayTests.test_on_and_off, test_an_entry_written_before_is_replaced_not_added_to,
    test_a_hook_whose_copy_is_gone_leaves_the_prompt_to_claude, test_a_folder_name_with_a_space
    (test_pane.py); LiveSwitchTests.test_on_and_off, HookRefreshTests (test_live.py).
- [ ] **Talpy Den rewrites settings.json.** It reads an account's settings.json, changes it and replaces the
  real file atomically (links followed), for hook entries and `cleanupPeriodDays`, locking only against its
  own helpers. It relies on Claude keeping no in-memory copy that it later saves over the whole file (Claude's
  own writes, such as a model pick, an Always allow saved to userSettings or a /config change, read the file
  again and change one key), and on Claude writing through a linked settings.json rather than replacing the
  link.
  - Used in: talpy_den.py write_claude_settings, claude_settings_lock, claude_settings_files; pane.py
    set_hook, install_hook, upgrade_hooks; cleanup.py keep_claude_from_cleaning, let_claude_clean; accounts.py
    SHARED_FILES, share_into.
  - Check: on a profile whose settings.json is a link, with a throwaway chat open that was started without
    `--setting-sources`, turn the relay on. In that chat, change a /config option that Claude saves to
    settings.json, then put it back (never `/model` or `/effort`). `ls -l $C/settings.json` should still be a
    link, and `jq '.hooks|keys'` should still list PermissionRequest.
  - Breaks: a hook entry or `cleanupPeriodDays` Talpy Den wrote is lost without a word (relay or live mode
    off, Claude cleaning starred chats again), or the shared settings link becomes a plain file and accounts
    stop sharing settings.
  - Test: no test for Claude's side (RelayTests and ClaudeSettingTests cover Talpy Den's own writes).
- [ ] **Managed settings.** Talpy Den reads `allowManagedHooksOnly` and `disableAllHooks` from
  `/etc/claude-code/managed-settings.json`, each `.json` in `/etc/claude-code/managed-settings.d`, or
  `/Library/Application Support/ClaudeCode`. Undocumented: the drop-in folder's name, and that a `--settings`
  hook counts as unmanaged and is therefore blocked. No other managed source is read (MDM plist,
  server-managed settings).
  - Used in: talpy_den.py managed_hooks_only, MANAGED_SETTINGS_DIRS; pane.py chat_hook_of.
  - Check:

    ```bash
    ls /etc/claude-code /etc/claude-code/managed-settings.d 2>/dev/null
    jq '{allowManagedHooksOnly,disableAllHooks}' /etc/claude-code/managed-settings.json
    ```

    In a container with `allowManagedHooksOnly: true` there, run
    `claude --settings '<a hook that writes /tmp/x>'` and see whether `/tmp/x` appears.
  - Breaks: if managed settings live elsewhere, Talpy Den starts background chats with a hook that never runs,
    and their prompts stall. If `--settings` hooks are allowed after all, Talpy Chat loses relaying that would
    have worked.
  - Test: ManagedHooksTests.test_managed_settings_that_allow_only_their_own_hooks (test_pane.py).
- [ ] **/model and /effort save your default: never run them in a throwaway chat.** `/model` and `/effort`
  save the pick as your default for new sessions, in your global settings, whatever the chat was started with.
  So Talpy Chat never sends them: it uses its own picker (the job's `respawnFlags`, `pane.py --set-options`).
  Before the command list has loaded, the front ends send `/model` and `/effort` to that picker, and `/config`
  to the terminal.
  - Used in: commands.py BUILTIN_COMMANDS ("picker"); chatpick.py; pane.py --set-options;
    vscode/src/shared/pane.ts commandRun, commandHint; ChatPane.qml commandRun, send.
  - Check (a read, never in a chat):
    `has 'and saved as your default for new sessions' '(saved as your default for new sessions)'` (2 and 2 on
    2.1.322; 4 for the first on 2.1.318). 2.1.322 also has a "(this session only)" wording next to them: if
    either count changed, read the code before trusting that a pick stays in the chat:
    `LC_ALL=C grep -a -o '.\{80\}saved as your default.\{120\}' "$B" | sort -u | head`, and the release notes.
    Talpy Chat's `/` list should still show /model and /effort as "this chat" pickers, and /config tagged
    Terminal.
  - Breaks: if Claude stops saving a default (or saves it only for the session), the warnings are wrong and
    the detour is needless. If the names change, a /model typed early is sent to Claude and changes your
    default.
  - Test: CommandKindsTests.test_each_builtin_commands_kind (test_pane.py); vscode/test/pane.test.ts "a
    command runs as its kind says on the chat's route …".
- [ ] **Context windows and when Claude compacts (2.1.318).** Read from Claude's code into CONTEXT_WINDOWS:
  Opus 4.7 and later, Sonnet 5.x, Haiku 5.5 and Fable 5.x have 1M; the 4.x models have 200k, or 1M with `[1m]`
  or once a chat is past 200k. Claude compacts at the window minus min(max output, 20k) minus 13k
  (COMPACT_ROOM, 33k), and "near" starts 20k before that (COMPACT_CLOSE). Model ids are parsed as
  family-version-minor (date, provider prefix, `@` and `[1m]` stripped). Context used is input + cache
  creation + cache read tokens of Claude's last message of its own. A status line's `context_window_size` wins
  over the table.
  - Used in: talpy_den.py CONTEXT_WINDOWS, CONTEXT_1M, COMPACT_ROOM, COMPACT_CLOSE, USAGE_READ, model_key,
    context_window, context_left; turns.py context_left, status_window.
  - Check: `has 'Autocompact buffer'`. In a throwaway chat on each new model, run `/context` (read-only) and
    compare its total and autocompact buffer (33k) with Talpy Chat's header. For a new model id, compare the
    status line's `context_window.context_window_size` and add it to CONTEXT_WINDOWS.
  - Breaks: the "% left before compacting" header and "near" are wrong, and new models show no meter.
  - Test: ContextAndTurnTests.test_context_left_till_claude_compacts_the_chat, test_the_window_by_model,
    test_context_is_claudes_last_message_of_its_own, test_the_status_line_says_which_window (test_pane.py).
- [ ] **The auto-compact window you set.** Read from code (2.1.318), likely undocumented.
  `CLAUDE_CODE_AUTO_COMPACT_WINDOW` (COMPACT_WINDOW_ENV) in settings.json's `env` comes first (`200k`, `1M`, a
  number, or a bare 100–1000 meaning thousands). Then `autoCompactWindow`, with
  `modelSettings.<model>.autoCompactWindow` before the top-level one (`auto` means the model's own). Values
  are kept between 100k and 1M and apply only below the model's window. Talpy Den reads only
  `$C/settings.json`.
  - Used in: talpy_den.py COMPACT_WINDOW_ENV, COMPACT_WINDOW_MIN, COMPACT_WINDOW_MAX, compact_tokens,
    compact_window, attach_snapshot; pane.py chat_conversation.
  - Check: `has CLAUDE_CODE_AUTO_COMPACT_WINDOW autoCompactWindow modelSettings`. With
    `{"autoCompactWindow": 300000}` in the scratch folder's `.claude/settings.local.json`, a throwaway chat's
    `/context` should show a 300k window.
  - Breaks: the "% left" header ignores your setting or misreads a new format.
  - Test: ContextAndTurnTests.test_the_auto_compact_window_you_set (test_pane.py).
- [ ] **The account file follows CLAUDE_CONFIG_DIR.** Claude reads `~/.claude.json` only when
  `CLAUDE_CONFIG_DIR` is unset; when it is set, `$CLAUDE_CONFIG_DIR/.claude.json`. So a plain (unlinked)
  `~/.claude` runs with the variable unset (`env -u`), and any other profile with it named. VS Code started
  with the variable keeps its panel on that folder. Claude creates `<dir>/.claude.json` once you start logging
  in, which marks a new profile.
  - Used in: talpy_den.py config_dir_value, config_env, Profile.__init__, trusted_folders, account_file,
    usage_refresh_command, start_background, stop_background; vscode/src/vscodeAccount.ts configDirFor,
    accountSwitch.ts switchTo, statusline.ts profileDirs.
  - Check: `ls -l ~/.claude.json ~/.claude/.claude.json ~/.claude-*/.claude.json 2>&1`.
    `CLAUDE_CONFIG_DIR=$(mktemp -d) claude auth status --json` should say not logged in, because it doesn't
    read `~/.claude.json` (remove the folder after).
  - Breaks: chats, attaches and usage fetches start on the wrong account or logged out. Make Default on the
    `~/.claude` account logs VS Code's panel out, and a new profile isn't offered the status-line setup.
  - Test: AttachCommandTests.test_plain_default_profile_unsets_config_dir (test_jump.py);
    UsageRefreshTests.test_a_plain_claude_folder_runs_without_claude_config_dir (test_talpy_den.py);
    vscode/test/vscodeAccount.test.ts "the folder VS Code's Claude gets for an account";
    vscode/test/statusline.test.ts "set up and remove on a machine with three kinds of profiles".
- [ ] **Profile layout and what accounts share.** An account is a config folder `~/.claude-NAME`, recognised
  by `sessions/`, `projects/` or `.claude.json`. Sharing links `settings.json`, `CLAUDE.md` and
  `keybindings.json`, and each entry of `skills`, `agents`, `commands` and `output-styles`, and Claude follows
  those links. Each account keeps its own login and MCP servers (in `.claude.json`) and `plugins/`.
  `skills/synced` (claude.ai's synced skills) and `.trash` are Claude's own and never shared.
  - Used in: accounts.py SHARED_FILES, SHARED_FOLDERS, NOT_SHARED, share_into, add_account; talpy_den.py
    is_profile_dir, discover_profiles; the texts in vscode/src/accounts.ts, gnome/extension/prefs.js,
    configAccounts.qml.
  - Check: `ls -A $C/skills` (is `synced` still the name, anything new of Claude's?).
    `jq 'has("mcpServers"), has("oauthAccount")' "$A"`. In a profile with linked skills, start claude and
    check that a linked skill is in the `/` menu. Read the release notes for config files that moved (MCP
    servers into settings.json, say).
  - Breaks: shared settings or skills don't apply, one account's synced skills are shared into another, or
    shared settings carry or drop MCP servers or the login. The texts are wrong.
  - Test: AddTests.test_shares_settings_from_the_real_files, test_own_skills_one_by_one_without_claude_ais,
    RemoveTests.test_hands_over_what_other_accounts_link_into_it (test_accounts.py).
- [ ] **Trust entries.** A folder is trusted when
  `<account file>.projects[<absolute folder>].hasTrustDialogAccepted` is true. Like Claude, Talpy Den also
  counts a trusted folder above (inside its git repository) and a worktree's main repository. Claude never
  saves trust for the home folder. A background chat can't ask, so Talpy Den refuses untrusted folders before
  it runs `claude --bg`.
  - Used in: talpy_den.py trusted_folders, folder_trusted, main_repository, git_root, start_background,
    claude_command; pane.py start_chat; jump.py pick_folder.
  - Check:

    ```bash
    jq -r '.projects|to_entries[]|select(.value.hasTrustDialogAccepted==true)|.key' ~/.claude.json ~/.claude-*/.claude.json
    ```

    Start claude in a subfolder of a trusted repository and in a new worktree of it: no trust question should
    come up (`/exit`).
  - Breaks: Talpy Den refuses background chats in trusted folders ("Claude doesn't trust … yet"), or starts
    one where `--bg` can't go on.
  - Test: RowTests.test_trusted_folders, test_a_worktree_is_trusted_when_its_repository_is,
    TaskTests.test_background_needs_a_trusted_folder (test_tasks.py);
    TalpyChatHookTests.test_a_folder_claude_doesnt_trust_isnt_started (test_pane.py);
    ChooseFolderTests.test_a_folder_for_talpy_chat_says_whether_claude_trusts_it (test_jump.py).
- [ ] **Trusting a folder from Talpy Chat.** When you choose an untrusted folder for a new chat and say yes to
  Talpy Den's question (in the words of Claude's own), Talpy Den writes the trust where Claude keeps it:
  `hasTrustDialogAccepted: true` in the folder's entry of the account file, keyed by the git repository's main
  folder (a worktree's main repository) or the folder itself. A new entry is made as Claude starts one
  (NEW_PROJECT, copied from 2.1.322: `allowedTools`, `mcpContextUris`, `mcpServers`, `enabledMcpjsonServers`,
  `disabledMcpjsonServers`, `hasTrustDialogAccepted`, `hasClaudeMdExternalIncludesApproved`,
  `hasClaudeMdExternalIncludesWarningShown`). The question names the folder's own Claude settings
  (TRUST_SETTINGS: `.claude/settings.json`, `.claude/settings.local.json`, `.mcp.json`). The file is read
  again if Claude wrote it meanwhile. Never for the home folder.
  - Used in: talpy_den.py trust_folder, trust_place, NEW_PROJECT, TRUST_SETTINGS, account_file,
    write_claude_settings; jump.py trust_folder, pick_folder (--trust-folder).
  - Check: `has hasClaudeMdExternalIncludesWarningShown mcpContextUris`. In a terminal, trust a new scratch
    folder once and compare its entry, `jq --arg f "$S" '.projects[$f]' "$A"`, with NEW_PROJECT. Then trust
    another scratch folder from Talpy Chat's Choose folder… and start `claude --bg` there: no "Workspace not
    trusted".
  - Breaks: a folder trusted from Talpy Chat still gets "Workspace not trusted", or Claude rewrites the entry
    and drops keys, or a running Claude saves its older copy over the write.
  - Test: ChooseFolderTests.test_a_new_folder_for_talpy_chat_is_trusted_once_you_say_so (test_jump.py;
    fixtures).
- [ ] **plansDirectory.** An undocumented detail of a documented setting. Plans go to `$C/plans/<slug>.md`
  unless `plansDirectory` names a folder inside the project, relative to the chat's start folder. The value
  comes from the project's `.claude/settings.local.json` (a worktree's from its main repository), else
  `.claude/settings.json`, else the account's settings.json. An empty value, one with a backslash, or one that
  leads out of the project (also through a link, judged by its nearest existing part) counts as none.
  - Used in: talpy_den.py PLANS_SETTING, plans_dir_in, stat_inside, canonical_git_root, the project plan
    folders; sharing.py add_plans_setting.
  - Check: in a throwaway git repository with `.claude/settings.local.json` `{"plansDirectory":"docs/plans"}`,
    start a chat with `--permission-mode plan`, ask it to 'plan creating a.txt', then `ls docs/plans`. Repeat
    with `../out` and with a link that leads out: the plan should land in `$C/plans`.
  - Breaks: project plans go missing from the Plans list, or Move to project puts a plan where Claude won't
    find it.
  - Test: PlansDirectoryTests, MoveTests.test_without_the_setting_it_says_claude_wont_find_it,
    test_never_through_a_link_out_of_the_project (test_project_plans.py).
- [ ] **Permissions tab sources.** The tab reads `/etc/claude-code/managed-settings.json` and
  `managed-settings.d/*.json`, each account's settings.json, and a folder's `.claude/settings.json` and
  `settings.local.json`: `permissions.allow`, `permissions.additionalDirectories`, `permissions.defaultMode`
  (acceptEdits, auto, bypassPermissions), `enabledMcpjsonServers`, and the flags
  `skipDangerousModePermissionPrompt`, `skipAutoPermissionPrompt`, `useAutoModeDuringPlan`,
  `enableAllProjectMcpServers`, `skipWebFetchPreflight`, `channelsEnabled`, `autoUploadSessions`,
  `remoteControlAtStartup`, `remoteTools.allowUnattendedServing` and `sandbox.autoAllowBashIfSandboxed`. From
  each account file it reads `bypassPermissionsModeAccepted`, and per folder `hasTrustDialogAccepted`,
  `allowedTools`, `enabledMcpjsonServers` and `enableAllProjectMcpServers`. Allow writes `Bash(<cmd> *)` and
  `WebFetch(domain:<host>)` rules into a folder's settings.local.json. Revoke edits these files,
  `.claude.json` included: it sets `hasTrustDialogAccepted` false and keeps `allowedTools: []` as Claude does.
  Undocumented: most flag names, the per-folder `.claude.json` keys, and that a running Claude (which rewrites
  `.claude.json` all the time) reads an outside edit instead of saving its older copy over it.
  - Used in: week.py GRANTING_MODES, FLAGS, MANAGED_DIR, BASH_RULE, FETCH_RULE, rule_for, granted_rules,
    claude_jsons, rule_folders, allow_rule, undo_rule, revoke_rule, write_settings; PermsView.qml,
    vscode/webview, gnome/extension/ui/permsView.js.
  - Check:

    ```bash
    has skipDangerousModePermissionPrompt skipAutoPermissionPrompt useAutoModeDuringPlan
    has enableAllProjectMcpServers skipWebFetchPreflight channelsEnabled autoUploadSessions
    has remoteControlAtStartup allowUnattendedServing autoAllowBashIfSandboxed bypassPermissionsModeAccepted
    has enabledMcpjsonServers allowedTools
    ```

    (all above 0 on 2.1.318). Live: with a throwaway chat open in the trusted scratch folder, revoke that
    folder's trust in the Permissions tab, send the chat one prompt and `/exit`.
    `jq --arg f "$S" '.projects[$f].hasTrustDialogAccepted' "$A"` should still be false.
  - Breaks: the tab lists settings that no longer let anything through, or misses a new one. Revoke changes a
    key Claude no longer reads, or a running Claude saves its copy over the revoke and the folder is trusted
    again.
  - Test: GrantedTests.test_every_rule_that_lets_chats_go_without_asking,
    test_revoke_takes_it_out_of_its_file, test_what_it_never_revokes,
    test_a_folders_settings_outside_a_repository_arent_shared,
    test_revoking_a_rule_the_recap_allowed_puts_back_what_was_before, PromptTests.test_allow_and_undo
    (test_week.py; fixtures only).
- [ ] **statusLine setting.** Documented as `{type:"command", command}`. Undocumented details: Claude reads
  settings.json again while chats run, so a rewritten statusLine works after the next reply, with no restart;
  Claude runs the command through a shell, so the wrapper's `'wrapper' 'previous command'` quoting works;
  other statusLine keys (padding) are kept. Talpy Den replaces files atomically because Claude may read or run
  them at any moment.
  - Used in: vscode/src/statusline.ts plan, withStatusLine, wrapperScript, unwrapCommand, scriptOf, apply;
    install.sh find_statuslines, patched_statusline, apply_statusline.
  - Check: with a throwaway chat open (started without `--setting-sources`), run "Set up plan usage bars" or
    `./install.sh`. After the chat's next reply, `ls -t $SNAP/ | head -1` should be a fresh
    `<sessionId>.json`, and the status line should look as before.
  - Breaks: usage bars stay empty until every chat restarts, or the wrapped status line breaks.
  - Test: vscode/test/statusline.test.ts (all of it); InstallTests.test_home_variable_and_no_last_newline,
    test_the_script_vs_codes_wrapper_runs_is_left_alone (test_install.py).
- [ ] **cleanupPeriodDays details.** Undocumented details of a documented setting: 3650 stops Claude's sweep
  in practice (its own hint is "3650 for ~10 years"), and values under 1 are refused. Project
  `.claude/settings(.local).json` and managed settings still make Claude clean, wherever it runs. Recap keeps
  its history after Claude deletes a transcript.
  - Used in: cleanup.py CLAUDE_KEEPS, keep_claude_from_cleaning, let_claude_clean, claude_overrides,
    claude_days; week.py scan ("gone" records).
  - Check: `LC_ALL=C grep -a -o '.\{60\}cleanupPeriodDays must be at least 1.\{120\}' "$B" | head -1`, then
    read the code around `cleanupPeriodDays` for which settings file wins.
  - Breaks: with Talpy Den's cleanup chosen, Claude still deletes old chats, starred ones included.
  - Test: ClaudeSettingTests.test_kept_from_cleaning_through_the_link_and_put_back,
    ChatTests.test_a_projects_or_managed_setting_that_still_cleans_is_told (test_cleanup.py),
    HistoryTests.test_a_deleted_transcript_stays_in_the_history (test_week.py).

## Status line

- [ ] **Status-line input.** statusline-snippet.sh saves Claude's status-line JSON as a snapshot. Fields read:
  `session_id`, `transcript_path`, `model.id` (it may end in `[1m]`), `model.display_name`, `effort.level`,
  `context_window.used_percentage`, `context_window.context_window_size`,
  `context_window.current_usage.{input_tokens, cache_creation_input_tokens, cache_read_input_tokens}` and
  `cost.total_cost_usd`. Undocumented details: `effort.level`, the `[1m]` suffix and `context_window_size`. VS
  Code's panel and background sessions draw no status line, so only snapshots newer than the run's `startedAt`
  count.
  - Used in: talpy_den.py attach_snapshot, chat_model, snapshot_paths, snapshot_of, context_left; turns.py
    status_window.
  - Check: with the snippet installed, after one prompt in a throwaway terminal chat started without
    `--setting-sources`:

    ```bash
    jq '{session_id,transcript_path,m:.model,e:.effort,c:.context_window,cost:.cost.total_cost_usd}' $SNAP/<id>.json
    ```
  - Breaks: rows lose their model, effort, context %, % left and cost. Go-ons guess the wrong model or effort,
    and a 1M window isn't known.
  - Test: LimitTests.test_limits_and_context, test_a_run_with_no_status_line_shows_no_earlier_runs_snapshot,
    SnippetTests (test_talpy_den.py); ContinueAfterResetTests.test_it_goes_on_with_its_own_model_and_effort
    (test_tasks.py); ContextAndTurnTests.test_the_status_line_says_which_window (test_pane.py).
- [ ] **Which profile a snapshot belongs to.** The snippet takes the profile folder from `transcript_path`'s
  layout `<cfg>/projects/<project>/<session>.jsonl`, else from `$CLAUDE_CONFIG_DIR` in the status line's
  environment, else `~/.claude`. It saves a snapshot only when `session_id` matches `[A-Za-z0-9_-]+`.
  - Used in: statusline-snippet.sh (added by install.sh apply_statusline and vscode/src/statusline.ts
    patchScript, wrapperScript).
  - Check:

    ```bash
    for f in $(ls -t ~/.cache/talpy-den/statusline/*/*.json | head -3)
    do jq -r '[.session_id, .transcript_path, .talpyDenConfigDir] | @tsv' "$f"
    done
    ```

    Each transcript should sit under `talpyDenConfigDir/projects/`, and the ids should be plain uuids.
  - Breaks: plan usage and context are filed under the wrong account, or no snapshot is written (empty usage
    bars).
  - Test: SnippetTests.test_profile_from_transcript_path, test_rejects_unsafe_session_id,
    test_link_filed_under_the_real_folder, test_plain_posix_sh (test_talpy_den.py).
- [ ] **rate_limits and prompt_cache.** The window keys are `five_hour`, `seven_day`, `seven_day_opus`,
  `seven_day_sonnet`, or others with a model family in them (fable, mythos, opus, sonnet, haiku). Each is
  `{used_percentage, resets_at}` in epoch seconds. A weekly window is left out until the new week has usage.
  An idle chat's status line is drawn again later, when its prompt cache goes cold, with the old numbers.
  `prompt_cache {ttl:'5m'|'1h', expires_at}` says when its last request went. `prompt_cache` and the extra
  keys are undocumented. The front ends key on the names: `five_hour` for the status bar and the 90% warnings,
  and spans and labels like "Week · Opus" in Recap.
  - Used in: talpy_den.py plan_limits, limit_window, with_ended_windows, limits_read_at, cache_ttl_ms,
    WINDOW_LABELS, WINDOW_ORDER, WINDOW_HOURS; vscode/src/shared/model.ts, shared/week.ts (WINDOW_MS,
    limitLabel, FAMILIES), webview/components/WeekView.tsx; main.qml, WeekView.qml, limits.mjs;
    gnome/extension/logic.js.
  - Check:

    ```bash
    jq -c '{r:.rate_limits,p:.prompt_cache}' ~/.cache/talpy-den/statusline/*/*.json | tail
    has prompt_cache seven_day_sonnet
    ```
  - Breaks: plan % and resets are wrong, and an old reading wins (32% shown after 100%). Forecasts are off,
    weekly windows vanish after a reset, the status bar % and 5-hour warnings vanish, and Keep going waits on
    the wrong window.
  - Test: LimitTests.test_limits_and_context, test_a_weekly_window_missing_after_its_reset_shows_as_reset,
    test_an_idle_chats_status_line_drawn_again_is_an_old_reading, test_when_a_snapshots_numbers_were_read
    (test_talpy_den.py); vscode/test/model.test.ts "the status bar shows the 5-hour usage of the account with
    an active chat"; vscode/test/week.test.ts "a plan window's fill, from its start to its reset", "advanced
    analyses: how a plan's limits changed, in words"; gnome/tests/test_logic.js 'plan usage shows once per
    account, with the newest numbers'.
- [ ] **What a chat runs on now.** For the check marks in Talpy Chat's /model and /effort lists, Talpy Den
  takes the job's `respawnFlags` first (chatpick.py options_now), else the newest snapshot's `model.id` and
  `effort.level`, else the last main-chat assistant entry's `message.model` (not `<synthetic>`).
  - Used in: talpy_den.py chat_model, last_model; chatpick.py options_now.
  - Check: for a chat that just replied, `jq -c '{m:.model.id, e:.effort}' $SNAP/<id>.json`.
  - Breaks: no check mark or the wrong one, and no "Now: …" line.
  - Test: ChatPickTests.test_what_it_uses_now (test_pane.py).
- [ ] **VS Code's panel runs no status line.** So its chats don't refresh plan usage, and Talpy Den has Claude
  fetch it instead (`--usage-refresh`, "as /usage does: no tokens, no chat saved").
  - Used in: vscode/src/config.ts statusArgs; vscode/package.json; configUsage.qml;
    package/contents/config/main.xml; gnome/extension/prefs.js; talpy_den.py (--fetch-usage).
  - Check: on a profile with the snippet, send a message in a panel chat. `$SNAP/` should get no file named
    after that chat's `sessionId`.
  - Breaks: if the panel starts running the status line, the fetches are needless and the setting's text is
    wrong. If /usage-style fetches start costing tokens or saving chats, the claim is false.
  - Test: no test.

## VS Code extension

Set these first (the Claude Code extension's folder and its main script):

```bash
ext=$(ls -d ~/.vscode/extensions/anthropic.claude-code-*/ | sort -V | tail -1)
main="$ext/$(jq -r .main "$ext/package.json")"
```

- [ ] **The extension's link.** `vscode://anthropic.claude-code/open` opens a new conversation.
  `?session=<id>` brings up an open chat, or resumes it in a new tab of the window focused last.
  `?prompt=<text>` types the text in without sending it, and session plus prompt puts the text in that chat's
  input. The query is encoded twice (`%` → `%25`), because VS Code decodes it once before the extension's
  URLSearchParams. The link must fit in about 128 KB as one argument. The front ends accept a link only with
  this prefix.
  - Used in: jump.py CLAUDE_CODE_LINK, VSCODE_NEW_CHAT, link_query, vscode_chat_link, vscode_task_link,
    jump_vscode, open_in_vscode, open_vscode_link, VSCODE_LINK_MAX; pane.py vscode_prompt_link,
    host_vscode_link; vscode/src/actions.ts CHAT_LINK, chatPane.ts sendNow, typeIn; main.qml openVscodeLink.
  - Check: `grep -c registerUriHandler "$main"; grep -oE 'get\("(session|prompt)"\)' "$main" | sort -u`. Then
    `code --open-url 'vscode://anthropic.claude-code/open?prompt=a%2526b%252Bc'`: the input should read
    `a&b+c` and not be sent. With `session=<id of a throwaway panel chat>`, its tab should come up, and a
    closed chat's id should resume it in a new tab.
  - Breaks: Reply to a panel chat, New chat in VS Code with a task, Reopen and Open in Claude Code open
    nothing or an empty chat, or cut prompts at `&` and turn `+` into a space.
  - Test: SendTests.test_vscode, test_a_hosts_vscode_link_is_made_here,
    TypeInTests.test_vscode_and_the_clipboard (test_pane.py); TaskTests.test_vscode_link_types_the_task_in,
    test_a_long_plans_vscode_link_fits_in_one_argument (test_tasks.py);
    RemoteShowTests.test_a_reply_link_opens_in_the_window_that_runs_the_chat (test_jump.py);
    ResumeTests.test_opens_the_chats_folder_then_the_chat,
    NewChatTests.test_opens_the_folder_then_asks_for_a_new_chat (test_vscode.py); vscode/test/openIn.test.ts
    "a recent chat reopens in this window when it has the chat's project open"; vscode/test/pane.test.ts "a
    reply goes to pane.py --send; copy goes to the clipboard and opens the chat; a Claude Code panel gets its
    link".
- [ ] **The command `claude-vscode.editor.open`.** "Claude Code: Open in New Tab". Talpy Den treats the panel
  as available when this command is in `getCommands(true)`: the extension registers it once activate has run
  (onStartupFinished), and not in an untrusted folder. Talpy Den calls it with the positional arguments
  (sessionId = undefined, prompt) to open a new tab with the prompt typed in but not sent. It also checks the
  extension id `anthropic.claude-code` with getExtension.
  - Used in: vscode/src/claudePanel.ts NEW_CHAT_TAB, claudePanelAvailable, openPanelChat; actions.ts
    panelChoice, panelChat; dashboard.ts checkClaudeCode, claudeCodeInfo; accountSwitch.ts switch.
  - Check:

    ```bash
    jq -r '.contributes.commands[].command' "$ext/package.json" | grep -x claude-vscode.editor.open
    jq .activationEvents "$ext/package.json"
    grep -o 'claude-vscode.editor.open",[^{]*' "$main" | head -3
    ```

    (the handler should still take sessionId, prompt). Live: New Chat… → "Claude Code chat tab" with a task
    should open a tab with the task in its input, not sent, and an untrusted folder should hide the choice.
  - Breaks: if the command is renamed, the Claude Code panel choice disappears everywhere. If the arguments
    change, the tab opens empty, sends the task at once, or reads the prompt as a session id.
  - Test: vscode/test/dashboard.test.ts "the Claude Code extension starting after this one is found without a
    reload" (the command id only, not the arguments).
- [ ] **`claudeCode.environmentVariables`.** An array of `{name, value}`; a `CLAUDE_CONFIG_DIR` entry chooses
  the account the panel's claude runs on. On the desktop it is read from
  `~/.config/<Code>/User/settings.json`, and a new value applies only after a window reload. On a Remote-SSH
  host it is a machine-scoped setting (`~/.vscode-server/data/Machine/settings.json`): a user-setting write
  from a remote window lands there, and new chats use it within about a second, with no reload (Talpy Den
  waits 1.5 s). The status bar's usage follows the panel's account.
  - Used in: vscode/src/claudePanel.ts panelConfigDir, localPanelConfigDir, localPanelProfileKey;
    vscodeAccount.ts withConfigDir; accountSwitch.ts switchTo, switchHost, panelDir; actions.ts panelChat;
    statusBar.ts; accounts.py make_default, set_vscode, vscode_value, vscode_setting; talpy_den.py
    config_dir_in_settings, vscode_server_settings, set_vscode_user_config_dir, set_vscode_server_config_dir,
    vscode_running_config_dir, VSCODE_SERVERS.
  - Check:

    ```bash
    jq '.contributes.configuration | (if type=="array" then .[] else . end) | .properties["claudeCode.environmentVariables"] | {type, items, scope}' "$ext/package.json"
    ```

    An array of `{name,value}` objects with scope machine or machine-overridable. Live: set
    `CLAUDE_CONFIG_DIR=~/.claude-NAME`, reload, open a panel chat, and
    `jq -r 'select(.entrypoint=="claude-vscode").pid' ~/.claude-NAME/sessions/*.json` should list it. In a
    Remote-SSH window, change it without a reload, open a new tab, and check the host's sessions folder.
  - Breaks: Default Claude Account… switches nothing or reloads for nothing. The status bar shows another
    account's usage, and Open in Claude Code is refused or opens on the wrong account. On hosts the value goes
    to the wrong scope, or 1.5 s is too short.
  - Test: DefaultTests.test_make_default_points_both_there, test_the_default_is_vscodes_and_comes_first
    (test_accounts.py); AccountTests.test_default_on_a_host_with_vscode (test_remote.py);
    SettingsTests.test_config_dir_from_the_extension_setting,
    ProfileTests.test_switching_an_ssh_hosts_vscode_to_another_account (test_vscode.py);
    vscode/test/vscodeAccount.test.ts "only CLAUDE_CONFIG_DIR changes in the settings list";
    vscode/test/claudePanel.test.ts "the panel's config dir: its own setting, else VS Code's, else ~/.claude";
    vscode/test/accountSwitch.test.ts "a Remote-SSH window shows the host's account and switches it in the
    host's settings".
- [ ] **Stopping a panel chat.** Talpy Den sends SIGINT. The panel's print-mode claude cancels the turn and
  exits 0, as with the panel's own stop button. The tab says the chat was interrupted, keeps it, and starts
  claude again with your next message (SIGTERM would show an error there). Claude leaves child commands
  behind, and Talpy Den ends them. A go-on or hand-over must never end a panel chat that has a pid, and a
  window reload stops a working panel chat.
  - Used in: talpy_den.py stop_chat, end_leftovers, end_for_handover; jump.py stop, jump; accounts.py
    vscode_chats; vscode/src/shared/model.ts canEndChat, handoverTarget, goOnAt; actions.ts stop;
    accountSwitch.ts switchTo (refuses while a panel chat works or waits); main.qml; gnome/extension/logic.js
    stopTip, stopQuestion.
  - Check: in an idle throwaway panel chat,
    `kill -INT $(jq -r 'select(.entrypoint=="claude-vscode").pid' $C/sessions/*.json | head -1)`. The tab
    should say interrupted and stay. Type a message there: a new `sessions/<pid>.json` with the same
    `sessionId` should appear.
  - Breaks: Stop leaves an error or a dead tab. A go-on or hand-over runs while the tab restarts the same chat
    (two processes on one transcript), and the tooltips are wrong.
  - Test: ChatStopTests.test_vscode_chat_gets_sigint, test_commands_it_leaves_behind_are_ended (test_jump.py);
    gnome/tests/test_logic.js 'stopping: background sessions, and chats with a process; interrupting in tmux';
    vscode/test/keepGoing.test.ts; vscode/test/openIn.test.ts "a chat with a process can be stopped, whatever
    it's doing; a working one interrupted" (rules only; nothing checks Claude's reaction).

## Wording

- [ ] **Limit and login messages.** Assistant entries with `isApiErrorMessage: true` whose text starts with
  "You've hit your " or "You've reached your ", then the window: `session limit`, `5-hour limit` (2.1.312+),
  `weekly limit`, `Opus limit`, `Sonnet limit` or `Fable limit` (five_hour, five_hour, seven_day,
  seven_day_opus, seven_day_sonnet, seven_day_overage_included). Other limit forms: "You're out of usage
  credits" and "Your org is out of usage". Login problems: "Login expired", "OAuth token revoked", "Anthropic
  profile login expired". The reset is in the text: ` · resets 7:10pm (<time zone>)` or `resets Oct 30, 7pm`.
  - Used in: talpy_den.py LIMIT_NAMES, LIMIT_STARTS, OUT_OF_USAGE, LOGIN_ENDED, stopped_by, RESET_IN_TEXT,
    reset_from_text, limit_stop, note_limit_hits, last_turn, kept_step, go_on_with; replies.py TurnEnd.state;
    week.py take_reply.
  - Check:

    ```bash
    has "You've hit your" "You've reached your" "You're out of usage credits" 'Your org is out of usage'
    has 'Login expired' 'OAuth token revoked' 'Anthropic profile login expired' 'session limit' '5-hour limit'
    has 'weekly limit' 'Opus limit' 'Sonnet limit' 'Fable limit'
    ```

    Look for new "<name> limit" words near "You've hit your", and read the reset format with
    `LC_ALL=C grep -a -o '.\{60\}resets .\{60\}' "$B" | head`.
  - Breaks: limit-stopped chats aren't marked. Queued and Keep going go-ons never fire, fire at the wrong
    time, or retry an error as a limit. Rows show no reset, the window isn't shown full, Recap misses limit
    hits, and an expired login is retried as an error.
  - Test: PeekTests.test_what_stopped_it, LimitStopTests.test_time_in_the_message,
    test_resets_with_its_window, test_login_and_unknown_limits_dont_reset,
    KeepGoingTests.test_it_goes_on_after_each_limit_until_its_done (test_tasks.py);
    RecapTests.test_limits_hit_by_several_chats_are_one_time (test_week.py).
- [ ] **The interruption note.** A user entry whose text starts with `[Request interrupted` (`… by user]`,
  `… by user for tool use]`).
  - Used in: pane.py INTERRUPTED; replies.py INTERRUPTED; talpy_den.py human_prompt, interrupted_note,
    last_turn, agent_end, kept_step; week.py take_user.
  - Check: `has '[Request interrupted by user'` (10 on 2.1.318). Press Esc mid-reply in a throwaway chat, then
    `tail -2 "$T" | jq -c '{type,c:.message.content}'`.
  - Breaks: an interruption shows as your prompt. Keep going reads your Esc as a turn that broke off and goes
    on by itself, and chips, subagents' "stopped" state and Recap's turn ends go wrong.
  - Test: ConversationTests.test_items, SuggestedRepliesTests.test_how_the_turn_ended (test_pane.py);
    TurnTests.test_a_stopped_turn_ends_where_you_stopped_it (test_week.py);
    KeepGoingTests.test_a_chat_you_interrupted_is_let_go (test_tasks.py).
- [ ] **Unknown commands.** An unknown command becomes a system entry with subtype `informational` and content
  `Unknown command: /x` (plus `. Did you mean /y?` when there's a guess). Talpy Chat also matches
  `Unknown skill: /`, which isn't a literal in 2.1.318 or 2.1.322 (it is built as `Unknown skill: ${name}`),
  so it may never match.
  - Used in: pane.py UNKNOWN_COMMAND; commands.py Commands.unknown.
  - Check: `LC_ALL=C grep -a -o '.\{40\}Unknown command: /.\{80\}' "$B" | head -2; has 'Unknown skill: /'`.
  - Breaks: a mistyped command sent from Talpy Chat shows no error and stays as a plain or queued message.
  - Test: CommandsInChatTests.test_a_command_claude_doesnt_know (test_pane.py).
- [ ] **How your No is written.** A No is stamped
  `permissionDecision {decision:'reject', source:'user_reject'|'hook'|'config'}` (`reasonType` `classifier`).
  The text is "The user doesn't want to proceed with this tool use." or "Permission for this tool use was
  denied.", with your note after `the user said:` (the older "…reason for the rejection:" form is gone since
  2.1.318), then "\n\nNote: The user's next message may contain…". `toolUseResult` is "User rejected tool
  use", and "The user wants to clarify these questions." means Chat about this.
  - Used in: pane.py rejection (REFUSALS, SAID, NEXT_NOTE, REJECTED_USE, CLARIFY, OUR_NO), your_answer.
  - Check:

    ```bash
    has "The user doesn't want to proceed with this tool use." 'Permission for this tool use was denied.'
    has 'the user said:' 'User rejected tool use' 'The user wants to clarify these questions.'
    has "Note: The user's next message may contain" user_reject
    ```
  - Breaks: your No and its note don't show as yours, a No looks like a tool error, and Chat about this shows
    as Declined.
  - Test: AnswersInChatTests.test_declined, test_deny_with_a_note (test_pane.py).
- [ ] **Claude's recap.** A system entry with subtype `away_summary` whose content ends with
  ` (disable recaps in /config)`. It counts as stale once a prompt or reply follows it.
  - Used in: talpy_den.py recap_of (RECAP_NOTE), peek_from; week.py project_recaps.
  - Check: `has away_summary 'disable recaps in /config'`.
  - Breaks: rows and the Projects tab lose Claude's recap, or show it with the note.
  - Test: PeekTests.test_recap_while_nothing_was_said_after_it, RowTests.test_recent_chats_carry_their_recap
    (test_tasks.py).
- [ ] **Input placeholders.** `[Pasted text #N …]` and `[Image #N]` in a prompt mark it as not one of your
  usual replies.
  - Used in: replies.py usual_reply.
  - Check: `has 'Pasted text #' '[Image #'`.
  - Breaks: pasted text could count as a usual reply (low impact: usual replies must also be one line of 40
    characters or fewer).
  - Test: SuggestedRepliesTests.test_your_usual_replies (test_pane.py).
- [ ] **Permission dialog wording for keys.** For tmux chats without the hook, Talpy Den answers by keys. The
  screen contains "Do you want to", with numbered options like `❯ 1. Yes`, "2. Yes, and don't ask again for …"
  or "Yes, allow all edits during this session", and "3. No" / "No, and tell Claude…". A digit answers at
  once. After No, Claude asks what to do instead, and the next typed text is the note.
  - Used in: pane.py DIALOG_OPTION, dialog_options, answer_with_keys.
  - Check: with a throwaway chat in tmux asking to 'run touch x',
    `tmux capture-pane -p -t <pane> | grep -nE 'Do you want to|^[[:space:]]*(❯[[:space:]]*)?[0-9]\.'`.
  - Breaks: Allow and Deny for tmux chats say "Its screen shows no permission question now" or "That answer
    isn't one of the choices it shows".
  - Test: KeysTests.test_options, test_keys (test_pane.py).
- [ ] **Dialog labels copied into the UI.** The plan dialog's options and their order: Approve and accept
  edits, Approve, Keep planning (the decisions approve-edits, approve, keep). The permission dialog's "Yes,
  and don't ask again" and "Yes, allow all edits during this session" (and Always allow's "Allow all edits"),
  the question dialog's "Type something.", and the Deny note's "What should Claude do instead?".
  - Used in: PermissionAsk.qml (pressKey, tooltips), QuestionForm.qml; vscode/src/shared/pane.ts answerText;
    vscode/src/notify.ts; talpy_den.py ALWAYS_LABELS.
  - Check: `has 'Type something.' 'What should Claude do instead?'`. In the scratch folder, run a chat with
    `--permission-mode plan`, ask for a small plan, and read the dialog's options and order. Ask for a Bash
    command and an AskUserQuestion too.
  - Breaks: labels and order differ from Claude's, and keys in tmux press the wrong option.
  - Test: vscode/test/pane.test.ts "your answer as the conversation will have it: …" (texts only).
- [ ] **Terminal look and behaviour Talpy Den copies or describes.** `∴` before Claude's thinking lines,
  "Manual" as the name of the default mode (2.1.312), ↑ taking back a queued message, Esc stopping a
  background chat, and Shift+Tab changing the mode. A background chat can start in auto or bypass mode only
  once you turned it on in a terminal, and `--bg` only works in folders Claude already trusts.
  - Used in: vscode/src/shared/pane.ts THINKING_TIP, HOLD_MS, stopOf; actions.ts MODES;
    vscode/webview/chat.tsx; ChatPane.qml; NewChatBox.qml, NewChatOptions.qml, keys.mjs.
  - Check: in a throwaway chat, Shift+Tab cycles the modes and shows "Manual" for the default. Type during a
    turn and press ↑ to pull it back, and look for `∴` with thinking shown as updates. Run
    `claude --bg --permission-mode auto 'hi'` on a fresh profile and in an untrusted folder, and read the
    messages.
  - Breaks: tooltips and labels are wrong. Nothing functional breaks.
  - Test: no test.
- [ ] **Command names in tooltips.** Tooltips name claude attach, claude stop, claude --resume, claude --bg,
  `--model`/`--effort`/`--permission-mode`, claude auth login/logout, /login, /compact and /usage, plus where
  claude is looked for.
  - Used in: vscode/src/shared/model.ts stopText, shared/pane.ts whereTag, attachedTag, contextHint,
    accounts.ts; SessionRow.qml, ChatPane.qml, PermissionAsk.qml, main.qml; gnome/extension/logic.js openHint,
    stopTip, prefs.js.
  - Check: `claude --help` and `claude attach --help`, `claude stop --help`, `claude auth --help`. /login,
    /compact and /usage should still be in a chat's `/` list.
  - Breaks: tooltips name commands that don't exist. The real calls are built in Python.
  - Test: no test.
- [ ] **What the texts say about Claude's cleanup.** That `cleanupPeriodDays` defaults to 30 days, that at
  startup Claude deletes every chat and every plan older than that, starred or not, and that 3650 turns the
  cleanup off in practice.
  - Used in: vscode/package.json, vscode/src/oldChats.ts, configChats.qml, configRecap.qml,
    gnome/extension/prefs.js (the logic is in cleanup.py).
  - Check: `LC_ALL=C grep -a -o '.\{80\}cleanupPeriodDays.\{80\}' "$B" | head -5`, and the settings docs for
    the default.
  - Breaks: the texts and the first-run warning are wrong, and "keep what you starred" may no longer hold.
  - Test: test_cleanup.py (the backend).

## SSH hosts and containers

Talpy Den runs the same Python there, on the host's or the container's own Claude version and files, so every
item above holds there too. Run the quick reads against that Claude (`ssh HOST`, or
`docker exec NAME sh -c …`) when a host updates on its own. The items here are what is different there.

- [ ] **Talpy Den's code runs there on stdin.** `python3 -I - --remote …` gets talpy_den.py on stdin (for
  Talpy Chat's actions pane.py, with the modules its action needs, ACTION_MODULES: reply_words.py, replies.py,
  commands.py, turns.py, chatpick.py, made.py; for sharing sharing.py with accounts.py), after PYTHON_CHECK
  (Python 3.7 or newer). Each module goes as one line of ASCII (`exec(compile({text!a}, …))`): Python 3.7
  reads a program on stdin in pieces of a few KB and refuses one that ends inside a multi-byte character. Long
  texts and the hook's code (TEXT_ARGS: `--text`, `--prompt`, `--note`, `--answers`, `--message`,
  `--hook-source`) go on stdin too, never on the command line. claude is found there without a login shell
  (the install places), and commands run through `sh -c`. A container is reached through
  `ENGINE exec -i [-u USER] NAME sh -c …` (over `ssh HOST` for a host's), as the container's own user (Dev
  Containers' `remoteUser`, or you in a Toolbox or Distrobox), never root from a label.
  - Used in: remote.py host_script, host_answer, PYTHON_CHECK, TEXT_ARGS, with_texts, run_on, exec_line,
    exec_user, status, task, continue_chat; pane.py forward, ACTION_MODULES, main; talpy_den.py find_claude,
    add_remote_commands, chat_options, container_user.
  - Check:

    ```bash
    ssh HOST 'command -v claude || ls ~/.local/bin/claude; claude --version; python3 --version; ls -d ~/.claude*/sessions'
    ```

    Then `python3 -I $TD/remote.py --status HOST | jq '.result.cli'` (`installed` and `hooks` should be true).
    For a container: `docker exec NAME sh -c 'command -v claude; claude --version'`.
  - Breaks: host rows say claude is missing, or a host on Python 3.7 answers nothing; Open, Stop and new chats
    fail there.
  - Test: HostListTests.test_a_python3_too_old_there_says_so, test_the_modules_sent_along_are_ascii_lines,
    LoginShellTests.test_your_text_goes_on_stdin, StatusTests.test_status_of_a_host,
    ActionTests.test_host_says_whether_claude_is_there (test_remote.py);
    ContainerStatusTests.test_run_text_and_start (test_containers.py).
- [ ] **The host's own Claude version.** A host or container may run an older or newer Claude than this
  computer. What depends on it: "Manual" is only a name (an older Claude knows `default`, which Talpy Den
  sends); background Stop checks the version range on the host's `version` and `workerCliVersion`; `ultracode` needs
  2.1.312+; and the prompt rules below (a background chat's session file says `waiting` with
  `permission prompt` while the hook waits) were checked on this computer's 2.1.31x only.
  - Used in: talpy_den.py chat_options, bg_stop_known, note_permissions; remote.py status.
  - Check: `ssh HOST claude --version`, then the Sessions items' `jq` reads on the host's files
    (`ssh HOST 'jq -c "{status,waitingFor,version}" ~/.claude*/sessions/*.json'`) while a throwaway chat there
    asks a permission.
  - Breaks: options refused there ("invalid option"), Stop greyed out or typing into an unknown protocol, and
    prompts of host chats never reaching Talpy Chat.
  - Test: ActionTests.test_stop_a_working_chat_or_interrupt_it_on_the_host (test_remote.py; fake host).
- [ ] **A chat's own hook on a host or in a container.** Talpy Chat starts (`--start`) and reopens (`--send`)
  chats there as here: `claude --bg --settings '<hook JSON>'` (or the hook added to the job's `respawnFlags`),
  with the full id. The hook's code comes from this computer as `--hook-source` on stdin; place_hook copies it
  to the host's `~/.local/share/talpy-den/permission-hook.py` (0600, in a folder only you may write:
  safe_folder), and replaces a copy only with a newer HOOK_REVISION, so front ends of other versions never
  make it older. It relies on the host's Claude taking a `--settings` PermissionRequest hook in a background
  chat, on the hook running in the worker's environment with `python3` on its PATH and the same
  `XDG_STATE_HOME` the status run reads (its requests land in `~/.local/state/talpy-den/permissions/` there),
  and on the session file saying `waiting` while the hook waits. "Answer it in a terminal"
  (`claude attach JOB` over `ssh -t`) is the way out when the hook didn't start. A host taken off the list
  loses the copy unless a chat there still names it in its `respawnFlags` or the hook is on for every chat
  there.
  - Used in: pane.py place_hook, hook_copy, chat_hook_of, start_chat, send, go_on_in_background, forget_hook,
    main (--hook-source); talpy_den.py safe_folder, own_file, hook_revision, hooks_dir, note_permissions,
    permission_requests, request_dirs, continue_chat, saved_options; permission_hook.py HOOK_REVISION,
    cache_root; remote.py TEXT_ARGS.
  - Check: on a host, start a throwaway chat from Talpy Chat in a trusted scratch folder and ask it to 'run
    touch x'.

    ```bash
    ssh HOST 'ls -l ~/.local/share/talpy-den/permission-hook.py ~/.local/state/talpy-den/permissions/; jq .respawnFlags ~/.claude/jobs/<short>/state.json'
    ```

    The copy is 0600, a request file is there, and `--settings` names the copy. The prompt should show in
    Talpy Chat within about a second; Allow should run the command. No settings.json there should have
    changed. Stop and remove the chat after.
  - Breaks: chats started there ask prompts nobody sees and stall ("Answer it in a terminal" only), requests
    land where the status run doesn't look, or an older front end's copy wins.
  - Test: HostHookTests.test_its_copy_comes_from_the_code_sent_and_only_ever_newer,
    test_a_folder_others_may_write_in, test_hooked_says_whether_talpy_chat_answers_what_it_asks,
    test_started_there_with_no_scope, test_a_stopped_job_there_wakes_with_it,
    test_a_host_taken_off_the_list_forgets_the_hook_unless_a_chat_still_uses_it,
    test_two_windows_answering_one_prompt (test_pane.py);
    TalpyChatThereTests.test_a_chat_started_there_asks_here_and_takes_the_answer,
    test_a_folder_claude_doesnt_trust_there (test_remote.py); RelayTests.test_on_a_host_it_gets_the_hook
    (test_pane.py). A stand-in ssh and claude: nothing checks a real host.
- [ ] **The host watcher.** While a host chat's Talpy Chat window shows, or a chat Talpy Chat hooked there
  works or waits, `remote.py --watch HOST --as NAME` runs live.py there
  (`python3 -I - --wait --requests --remote`, on stdin through the shared ssh connection, at most 50 s a run).
  It wakes on the host's `sessions/<pid>.json` writes and on the hook's request files (inotify), so it relies
  on the host's Claude rewriting session files at every change (see Sessions) and on inotify working there (a
  container's overlay or bind-mounted home). It ends when its connection goes (fd 1 hangs up).
  - Used in: remote.py watch, WATCH_S, WATCH_NAME; live.py session_dirs, Watch, wait (--requests, --remote);
    vscode/src/hostWatch.ts; main.qml.
  - Check: `python3 -I $TD/remote.py --watch HOST --as check --timeout 30` and, meanwhile, start or answer a
    throwaway chat there: it should answer at once with `"sessions": true` (or `"requests": true`), not at its
    timeout. In a container, the same with `--watch docker:NAME`.
  - Breaks: a host's prompts show only at its next status check (every 30 s), not within a second.
  - Test: HostWatchTests.test_it_answers_when_something_changes_there, test_a_host_it_cant_reach,
    test_in_a_container (test_remote.py); HostWatchTests.test_a_request_wakes_it_at_once,
    test_gone_with_the_connection_that_asked (test_live.py); vscode/test/hostWatch.test.ts "a watcher runs
    again at once, hands on what changed, and stops when it's no longer wanted".
- [ ] **The background service there.** There is no systemd scope on hosts or in containers: the service a
  chat's `claude --bg` starts there must outlive the ssh channel (ControlPersist's end, `ssh -O exit`,
  logind's KillUserProcesses) and the `docker exec` that started it. Its socket is the host's or container's
  `/tmp/cc-daemon-<uid>/…`, so Stop and reply work only as the user that started it: a chat someone started as
  root in a container belongs to root's service, and the peer-uid check makes Talpy Den say it can't.
  - Used in: pane.py start_chat (scoped only here), send; talpy_den.py start_background, daemon_ask, peer_uid,
    interrupt_background; remote.py run_on, exec_line.
  - Check: start a throwaway background chat on a host from Talpy Chat, close every ssh connection to it
    (`ssh -O exit HOST`), wait a minute, then `ssh HOST 'claude agents --all'` (or the host's row): the chat
    should still be there. In a container, the same after the exec ends; `loginctl show-user $USER -p Linger`
    on the host if it died.
  - Breaks: host and container background chats die when the connection drops or the exec ends; reply and Stop
    say they can't reach the chat.
  - Test: HostHookTests.test_started_there_with_no_scope (test_pane.py; the command line only).
- [ ] **Containers that share your home.** A Toolbox, a Distrobox or a container with your home bind-mounted
  writes its Claude files into this computer's `~/.claude*`, and its hook's copy and requests would be this
  computer's too. Talpy Den tells such a container by `homeId` (the boot id plus the home folder's device and
  inode, home_id), and Talpy Chat doesn't open its chats ("home"): they show among this computer's.
  - Used in: talpy_den.py home_id (status `homeId`); vscode/src/shared/model.ts talpyPlace, dashboard.ts;
    main.qml.
  - Check:

    ```bash
    toolbox run python3 -I -c 'import sys;sys.path.insert(0,sys.argv[1]);import talpy_den as t;print(t.home_id(t.Path.home()))' "$TD"
    ```

    And the same here should print the same id.
  - Breaks: a shared-home container's chats show twice, or Talpy Chat opens one whose prompts this computer's
    rows also answer.
  - Test: HostHookTests.test_which_home_it_is (test_pane.py).

## Other

- [ ] **cachedUsageUtilization.** The account file holds
  `{fetchedAtMs, accountUuid, utilization:{five_hour:{utilization, resets_at ISO}, seven_day…, null entries, extra_usage}}`.
  `/usage` and VS Code's panel write it.
  - Used in: talpy_den.py Profile.__init__, cached_usage_limits, plan_limits, usage_forecast.
  - Check:

    ```bash
    jq '.cachedUsageUtilization|{fetchedAtMs,accountUuid,keys:(.utilization|keys)}' "$A"
    has cachedUsageUtilization fetchedAtMs
    ```
  - Breaks: accounts used only in VS Code's panel show no plan usage or old usage, and Refresh does nothing
    visible.
  - Test: LimitTests.test_claude_codes_own_usage_when_its_newer,
    test_a_usage_cache_of_another_account_is_left_out (test_talpy_den.py).
- [ ] **Account fields.** `oauthAccount.accountUuid` (profiles of one account share limits), `displayName`,
  `organizationType` (claude_free, claude_pro, claude_max, claude_team, claude_enterprise),
  `organizationRateLimitTier` and `userRateLimitTier` (`…_max_20x`), and `seatTier` (`…premium`/`…standard`).
  A logout removes `oauthAccount`.
  - Used in: talpy_den.py Profile.__init__, plan_detail, PLAN_NAMES, TIER_TIMES, needs_login, group_profiles;
    accounts.py list_accounts, default_link.
  - Check:

    ```bash
    jq '.oauthAccount | keys' "$A"
    jq -r '.oauthAccount | .organizationType, .seatTier, .organizationRateLimitTier' "$A"
    ```
  - Breaks: the plan and tier labels go missing, profiles of one account aren't grouped (limits shown twice),
    and logged in or out is misjudged.
  - Test: SessionTests.test_groups_by_account, UsageHistoryTests.test_the_plan_with_its_tier
    (test_talpy_den.py), AddTests.test_new_folder_is_an_account_not_logged_in (test_accounts.py).
- [ ] **history.jsonl.** `$C/history.jsonl` has one JSON object per line,
  `{display, project, sessionId, timestamp (epoch ms), pastedContents}`, newest last. Its last 64 KB feed ↑ in
  the reply box, its last 16 MB feed Find, and Recap reads it for when an account took up a shared chat.
  - Used in: talpy_den.py history_tail, history_all, find_chats, scan_prompts; commands.py past_prompts,
    completions; week.py chat_signs.
  - Check: `tail -n 2 $C/history.jsonl | jq -c 'keys'`.
  - Breaks: ↑ shows nothing or prompts from other folders, and Find matches only names and folders.
  - Test: CompleteTests.test_commands_skills_files_and_past_prompts (test_pane.py),
    FindTests.test_every_word_in_name_folder_or_prompts (test_tasks.py).
- [ ] **Your commands and skills in the `/` list.** From `$C/commands/**/*.md` (a file in a subfolder is named
  `dir:name`) and `$C/skills/<dir>/SKILL.md` (front matter `name`, else the folder's name, and `description`).
  The same is read under the chat folder's `.claude/commands` and `.claude/skills` (that folder only, not its
  parents). Plugins' commands and skills, and claude.ai-synced skills, aren't listed.
  - Used in: commands.py completions, command_files, skill_dirs, front_matter; pane.py --complete.
  - Check: in a throwaway chat, type `/` and compare its own commands and skills with `pane.py --complete`'s
    answer for that chat (`jq -r '.commands[]|select(.kind!="Claude")|.name'`).
  - Breaks: your skills and commands are missing from Talpy Chat's list, or are named differently, so one sent
    comes back "Unknown command".
  - Test: CompleteTests.test_commands_skills_files_and_past_prompts (test_pane.py).
- [ ] **Claude's task lists.** TaskCreate and TaskUpdate keep `$C/tasks/<session id>/<n>.json`, one file per
  task (beside Claude's own `.highwatermark` and `.lock`). Fields: `id` (a number as a string), `subject`,
  `status` (pending, in_progress, completed; deleted ones are skipped), `activeForm` and `blocks`/`blockedBy`.
  Talpy Den looks the folder up by the row's `sessionId`, `chatId` and the job's `sessionId`.
  - Used in: talpy_den.py task_progress, task_number, TASKS_LISTED, finish_row; the front ends' task strip.
  - Check: tell a throwaway chat 'Make a 3-step task list with your task tools and start the first step, then
    stop.' Then `ls -A $C/tasks/<id>/` and `jq -c '{id,subject,status,activeForm}' $C/tasks/<id>/*.json`. Also
    `has activeForm` (28 on 2.1.318).
  - Breaks: the task strip disappears for every chat, or shows deleted tasks. If the folder is named by a
    task-list or team id, no chat finds its list.
  - Test: TaskProgressTests.test_progress_and_current_task, test_no_tasks (test_talpy_den.py);
    test_task_strip.py (fixture data).
- [ ] **Claude's scratch folders.** Under `/tmp/claude-<uid>`: the scratchpad at
  `/tmp/claude-<uid>/<mangled project>/<session id>/scratchpad`, and background-command output under
  `…/tasks/`. Files a chat writes there aren't the project's changes.
  - Used in: talpy_den.py own_folders (with each profile's folder), through changed_files and changes in
    finish_row, the recent rows and the project plan folders; pane.py originals; jump.py.
  - Check: `has /tmp/claude-`. Ask a throwaway chat to save a note in its scratchpad: its path should start
    with `/tmp/claude-$(id -u)/`.
  - Breaks: scratch files show up as the chat's changes (Review tab, the row's changes, overlap warnings
    between chats).
  - Test: no test for `/tmp/claude-<uid>` (test_project_plans.py test_never_claudes_own_folders covers profile
    folders only).
- [ ] **Claude's memories.** Each memory is one Markdown file in `$C/projects/<key>/memory/`, starting with
  front matter (`name`, `description`, `type`: user, feedback, project or reference). `MEMORY.md` in the same
  folder indexes them as Markdown links, and Claude reads it into every new chat. The key is the folder's
  name, mangled, so Talpy Den finds the folder by walking the disk, else from a transcript's first `cwd`. VS
  Code opens a memory only if its path matches `/projects/<key>/memory/<name>.md` or ends in `/CLAUDE.md`.
  - Used in: talpy_den.py memory_head, MEMORY_FIELD, account_memories, project_folder_of, memory_folder,
    memory_key, memory_file, find_more; sharing.py memory_to_delete, unindex_memory, delete; week.py projects;
    vscode/src/actions.ts openMemory.
  - Check: after a throwaway chat saved a memory ('remember that I like tabs'),
    `head -6 $C/projects/$M/memory/*.md; cat $C/projects/$M/memory/MEMORY.md; has MEMORY.md`.
  - Breaks: memories show without name, description or type, or under the wrong folder. Delete leaves the
    memory's line in `MEMORY.md` (a dead link Claude keeps reading) or takes out the wrong one, and VS Code
    says "That isn't one of Claude's memories."
  - Test: MemoryTests.test_an_accounts_memories_newest_first_with_their_folder,
    test_memories_linked_from_a_renamed_folder_are_the_folders_there,
    DeleteTests.test_a_memory_and_only_its_line_in_memory_md (test_tasks.py).
- [ ] **Claude's own cleanup, mirrored file for file.** Read from Claude's code. Claude runs its cleanup at
  startup, at most once a day. It deletes by mtime anything older than `cleanupPeriodDays` (default 30):
  `projects/<p>/<uuid>.jsonl` with `<id>.ccr-tip.json`, `<id>.precompact.json` and its `<id>/` folder, and
  empty project folders. It also deletes the folders in `file-history`, `session-env`, `image-cache`, `tasks`
  and `uploads`, and the files in `todos`, `debug` (except `latest`), `shell-snapshots` and `paste-cache`.
  Finished, non-recurring `jobs/<id>`, `plans/*.md` and `.md.tmp.` leftovers go too. It never deletes chats
  Claude Desktop keeps (entrypoint `claude-desktop*` or `local-agent` near the start of the file). 2.1.318
  also has `desktopSessionCleanupPeriodDays`, which Talpy Den doesn't model.
  - Used in: cleanup.py AGED, COMPANIONS, DESKTOP, CHAT_ID, sweep, sweep_chats, sweep_aged, sweep_jobs,
    sweep_plans, from_desktop, running.
  - Check: compare `ls $C` with AGED (look for new cache folders).
    `has .ccr-tip.json .precompact.json desktopSessionCleanupPeriodDays`, and read the code with
    `LC_ALL=C grep -a -o '.\{100\}cleanupPeriodDays.\{100\}' "$B" | head`.
  - Breaks: with Talpy Den's cleanup chosen, disk use grows where Claude would delete, or something Claude
    keeps gets deleted.
  - Test: ChatTests.test_an_old_chat_goes_with_its_files_what_stays_stays,
    test_claudes_memories_and_what_isnt_a_chat_stay_however_old,
    test_a_routine_or_loop_between_its_runs_stays, test_background_chats_that_finished_go_the_others_stay,
    PlanTests.test_old_plans_go_to_the_trash_once_starred_queued_and_living_ones_stay (test_cleanup.py).
- [ ] **Terminal titles.** The agent view titles its terminal tab with the shown session's name, after a
  spinner or state mark that TITLE_MARKS strips. Talpy Den matches that title (Konsole's Session.title over
  D-Bus, tmux `#{pane_title}`) to a session name, to tell which background session an agent view shows, and it
  raises Konsole tabs by their title. `CLAUDE_CODE_DISABLE_TERMINAL_TITLE` stops Claude writing a title at
  all.
  - Used in: jump.py find_attached_tab, konsole_tabs, show_konsole_tab; talpy_den.py tab_title, TITLE_MARKS,
    shown_row.
  - Check: in Konsole, run plain `claude` while a background session exists and switch to it.
    `busctl --user call $KONSOLE_DBUS_SERVICE $KONSOLE_DBUS_SESSION org.kde.konsole.Session title i 1` (or
    `tmux display -p '#{pane_title}'`) should show `<mark> <session name>`. Also
    `env | grep CLAUDE_CODE_DISABLE_TERMINAL_TITLE`, and check your settings' `env`.
  - Breaks: the "attached" tag is wrong or missing, and Open starts another terminal for a session an agent
    view already shows. Nothing warns when titles are turned off.
  - Test: AttachedTabTests.test_agent_view_matched_by_title_and_profile (test_jump.py),
    TerminalTests.test_the_row_of_a_session_attached_in_konsole_says_so, test_the_title_without_its_marks
    (test_talpy_den.py).
- [ ] **Pictures named in prompts.** Talpy Den names a pasted picture as `[Image: /abs/path]` in the text, and
  Claude opens it from that path (its Read tool takes images), with the pictures folder added by `--add-dir`.
  Talpy Chat shows such names as `[Image #1]`, `[Image #2]`…, as Claude's terminal does. The types are png,
  jpeg, webp and gif.
  - Used in: vscode/src/shared/pane.ts picturesIn, withoutPicture, numberedPictures, PICTURE_TYPES;
    vscode/webview/chat.tsx; ChatPane.qml, NewChatBox.qml, PictureStrip.qml; talpy_den.py picture_options.
  - Check:

    ```bash
    d=$(mktemp -d)
    cp "$(ls /usr/share/pixmaps/*.png | head -1)" "$d/p.png"
    (cd "$d" && claude -p --model haiku "[Image: $d/p.png] describe this picture in five words")
    ```

    It should describe the picture.
  - Breaks: Claude gets only a path, and pasted pictures go unseen.
  - Test: vscode/test/pane.test.ts "the pictures a reply names, each once, and taking one out", "your pictures
    read as Claude's terminal writes them: [Image #1], [Image #2], one picture named twice the same number".
- [ ] **File mentions.** `@path`, or `@"path with spaces"` quoted, attaches a file. Dropped and completed
  files are put in that way.
  - Used in: vscode/src/shared/pane.ts fileMention, suggestFor; vscode/webview/chat.tsx;
    vscode/src/chatPane.ts.
  - Check: `d=$(mktemp -d); echo 'the word is plum' > "$d/a b.txt"`. In a throwaway chat in `$d`, send
    `What word is in @"a b.txt"?`. It should answer plum without searching.
  - Breaks: dropped files with spaces aren't attached, and Claude sees the raw text.
  - Test: vscode/test/pane.test.ts "a file dropped on a reply is named as Claude's prompt names it; a drop's
    links are its paths", "the reply box offers commands at the start and files after @, best first".
- [ ] **The usage page.** "Open Usage Page" opens `https://claude.ai/settings/usage`.
  - Used in: vscode/src/extension.ts; main.qml.
  - Check: `curl -sI https://claude.ai/settings/usage | head -3`. A redirect to the login is fine, a 404
    isn't.
  - Breaks: the menu item opens a dead page.
  - Test: no test.

Last checked: Claude Code 2.1.322 (checklist written for Talpy Den 1.19)
