# Phone ↔ desktop sync on the emulator (local server, no AnkiWeb)

This is the on-device sync path for the demo (rubric shot 3: "a card synced
phone→desktop"). Desktop and the AnkiDroid emulator sync through **Anki's own
local sync server** running the **same Rust sync protocol** — no AnkiWeb account.
It has been run end to end and **verified** (see "What was verified" below).

## The desktop Sync-button crash (fixed)

Clicking **Sync** on macOS crashed the whole app with a `Trace/BPT trap: 5`
(arm64 pointer-authentication SIGTRAP). Root cause, from the crash report: sync
starts → Anki shows a busy/hover cursor → `QGuiApplication::setOverrideCursor()`
→ `QImage::toCGImage()` → `CGImageCreate` traps. It is a Qt/macOS bug, not the
engine (that is why `make sync-test` always passed — only the GUI cursor died).

There are two `setOverrideCursor(QCursor(...))` sites; both are now guarded on
macOS:

- `qt/aqt/progress.py` `_set_busy_cursor` — the busy/wait cursor (committed).
- `qt/aqt/__init__.py` eventFilter — the hover **pointing-hand** cursor over
  buttons (the one that fires when you hover/click Sync).

After the guards, the desktop syncs (auto-sync on startup **and** the Sync
button) without crashing.

## Start the stack (three terminals)

```bash
# 1. the local sync server (leave running) — binds 0.0.0.0:27701
make sync-server
#    from the host  : http://127.0.0.1:27701/
#    from the phone : http://10.0.2.2:27701/   (Android emulator host alias)
#    login          : user / pass   (local account, NOT AnkiWeb)

# 2. the emulator + AnkiDroid
make phone

# 3. the desktop app
./run
```

## One-time config (already applied; here for reproducibility)

Both clients are pointed at the local server and pre-authenticated, so no login
UI is needed.

- **Server seeded** with the Exam P deck and an hkey minted:
  `PYTHONPATH=pylib:out/pylib out/pyenv/bin/python tools/speedrun/sync_setup.py`
  → prints `HKEY=...`.
- **Phone** (AnkiDroid SharedPreferences, set via `adb ... run-as`): keys
  `syncBaseUrl=http://10.0.2.2:27701/`, `syncBaseUrl_switch=true`,
  `username=user`, `hkey=<hkey>`.
- **Desktop** (profile, set with the app closed):
  `PYTHONPATH=pylib:out/pylib out/pyenv/bin/python tools/speedrun/desktop_sync_setup.py`
  sets `customSyncUrl`/`syncUser`/`syncKey` and full-downloads the shared deck.
  (The desktop collection is backed up first to `out/sync-backup/`.)

## Demo it (review on phone → appears on desktop)

1. On the **phone**: open **SOA Exam P**, grade a few cards, then tap the
   **sync** icon (top-right). First time it asks which collection to keep — pick
   the server copy ("AnkiWeb" → Replace) so both sides share one deck; after that
   it is a normal one-tap sync.
2. On the **desktop**: click **Sync** (crash-free now). It downloads the reviews.
3. Open **Readiness** on the desktop — **Graded reviews** goes up by exactly the
   number you did on the phone.

## What was verified (real, not staged)

- Server round-trip: seed full-upload (186 cards) → fresh client full-download
  186 → `RESULT=OK`.
- Phone: authenticated to `10.0.2.2:27701`, full-download of the 186-card deck
  (`SyncKt: Full Download Completed`).
- Two-way: graded **3** cards on the phone → phone sync → server `REVLOG=3` with
  an `…,android` client in the server log → desktop sync (`…,macos`, full
  protocol, no crash) → desktop **Readiness** shows **"3 cards reviewed / 3 / 200
  graded reviews"**. Screenshots in `out/phone-synced.png`,
  `out/phone-reviewed.png`, `out/desktop-readiness-after-sync.png`.

## Restore (if you want the desktop's pre-sync collection back)

A backup was taken before the desktop adopted the shared deck:

```bash
ls out/sync-backup/            # collection-<stamp>.anki2, prefs21-<stamp>.db
# with the desktop app closed, copy the backup back over
#   ~/Library/Application Support/Anki2/User 1/collection.anki2
```

## Tools

- `tools/speedrun/sync_server.sh` — start the local server (`make sync-server`).
- `tools/speedrun/sync_setup.py` — seed the server + print the hkey.
- `tools/speedrun/desktop_sync_setup.py` — point the desktop at the server + pull.
- `tools/speedrun/sync_probe.py` — download to a throwaway client and print
  note/card/revlog counts (used to prove the phone's reviews reached the server).
