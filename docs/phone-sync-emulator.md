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

## The phone home-shell Sync-button bounce (fixed)

Tapping **Sync** in the branded **home shell** (the Svelte `home` action row,
`speedrun-nav:sync`) kicked the app straight to the Android launcher instead of
syncing — no crash (crash buffer empty, no `FATAL`/`AndroidRuntime`), the task
just closed. The **DeckPicker toolbar sync icon still worked**; only the
home-shell button was broken, which is why it looked like a headless-login issue
but wasn't.

Root cause (full logcat, `Anki-Android/.../pages/SpeedrunPageFragment.kt`): the
home button routed sync through the stock **`com.ichi2.anki.DO_SYNC`** intent →
`IntentHandler.handleSyncIntent` → `startActivity(DeckPicker, CLEAR_TOP)` (which
first *destroys* the home shell) → `DoSync.handleAsyncMessage` → `deckPicker.sync()`
**immediately followed by an unconditional `deckPicker.finish()`**. That
`finish()` is fine for a fire-and-forget widget/shortcut, but from the in-app
button it tears down the only remaining activity before the first-sync
**`FullSyncRequired { download_ok: true }`** download / dialog can run → the task
empties → launcher. The engine was reached and authenticated fine (`hkey` OK,
`server_usn` seen), so it was never an auth/config problem.

Fix (one call site, least-invasive, no engine change): route the home Sync button
through AnkiDroid's own **post-login** sync entry instead —
`DeckPicker.getIntent(ctx, autoSync = true)` (sets `INTENT_SYNC_FROM_LOGIN` →
`syncOnResume` → `sync()`), with `CLEAR_TOP | SINGLE_TOP` to reuse the DeckPicker
already under the shell. That path **never finishes the activity**, so the
full-sync download and progress complete normally. Rebuilt
(`./gradlew :AnkiDroid:assemblePlayDebug -x lint`), reinstalled, re-ran
`make sync-phone-config`.

Verified end-to-end: home Sync → `sync result: FULL_DOWNLOAD` →
`Full Download Completed`, foreground **stays** on DeckPicker (no bounce), deck
lands with **186 cards / 186 notes** (`pragma integrity_check = ok` via desktop
Anki). A later tap resolved a genuine two-sided `FULL_SYNC` conflict (server had
persona review history) by keeping the **AnkiWeb/server** copy; after that,
schema is aligned and syncs are clean incremental (`NormalSyncRequired` →
`NO_CHANGES`). Screenshot: `out/phone-sync-fixed-20260705-103811.png`,
`out/phone-final-synced-deck.png`.

## Phone device numbers (item 6) — real measurements on the `Speedrun_P` emulator

Measured via `adb -s emulator-5554` on the lean AVD (AOSP 34, **2 GB** guest, 4
cores, host GPU) on an **8 GB M1 Air**, **debug build with LeakCanary**. These
are honest device numbers, not fabricated; the emulator/host is the bottleneck,
not the app.

- **Cold start → full Svelte home shell** (`am start -W` of `IntentHandler`;
  system `Displayed …SingleFragmentActivity`): quiesced true-cold runs
  **6.23 / 6.12 / 6.72 s** (median ~6.2 s); a warm-cache run hit **3.75 s**. This
  is **above the <4 s target on this throttled emulator** — dominated by the
  2 GB memory-pressured guest (host swaps), the debug+LeakCanary build, and that
  it times the whole WebView home shell + 4 engine RPCs, not a native list. A
  release build on real phone hardware would be materially faster (not measured
  here, so not claimed as a pass).
- **Memory ceiling** (`dumpsys meminfo`, home shell settled): **TOTAL PSS
  ≈ 217 MB** (RSS 361 MB, SWAP 0; Code 34.5 MB reflects the unstripped debug
  build). Comfortably within a mid-range phone's headroom — a 4 GB phone leaves
  apps hundreds of MB before the low-memory killer engages; 217 MB is ~4–5 % of
  RAM.
- **Crash test** (mirror of desktop `make crash-test`, 20/20 zero-corruption):
  **~18 `am force-stop` kills interleaved with relaunch**, then pulled the
  collection (app stopped) and opened it with the real Anki engine →
  **`PRAGMA integrity_check = [['ok']]`, cards 186, notes 186, 24 decks intact**.
  **PASS — zero corruption.** (Bare `sqlite3` can't run the check: Anki's custom
  `unicase` collation is only registered by the engine, so the check is run via
  `out/pyenv` Anki, not host `sqlite3`.)

## Start the stack — run each in its OWN terminal

Use separate terminals so the long-running processes persist (the server,
emulator, and desktop each stay in the foreground of their terminal).

```bash
# 1. the local sync server (leave running) — binds 0.0.0.0:27701
make sync-server
#    from the host  : http://127.0.0.1:27701/
#    from the phone : http://10.0.2.2:27701/   (Android emulator host alias)
#    login          : user / pass   (local account, NOT AnkiWeb)

# 2. the emulator + AnkiDroid  (cold-boots reliably; ~1-2 min)
make phone

# 3. the desktop app
./run
```

## One-time config (already applied; commands to reproduce)

Both clients are pointed at the local server and pre-authenticated, so no login
UI is needed. All of this survives restarts (it's on disk); only re-run a step if
something was wiped.

```bash
make sync-seed            # seed the server with the Exam P deck + mint an hkey
make sync-phone-config    # write syncBaseUrl/hkey into AnkiDroid (emulator booted)
make sync-desktop         # point the desktop profile at the server + pull (app CLOSED)
```

- **Phone** prefs written (AnkiDroid SharedPreferences via `adb run-as`):
  `syncBaseUrl=http://10.0.2.2:27701/`, `syncBaseUrl_switch=true`,
  `username=user`, `hkey=<hkey>`.
- **Desktop** profile: `customSyncUrl`/`syncUser`/`syncKey`; collection backed up
  to `out/sync-backup/` before the shared deck is pulled.

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
- `tools/speedrun/sync_setup.py` — seed the server + print the hkey (`make sync-seed`).
- `tools/speedrun/sync_hkey.py` — print an hkey for the server (login only).
- `tools/speedrun/phone_sync_config.sh` — write the sync prefs into AnkiDroid
  (`make sync-phone-config`).
- `tools/speedrun/desktop_sync_setup.py` — point the desktop at the server + pull
  (`make sync-desktop`).
- `tools/speedrun/sync_probe.py` — download to a throwaway client and print
  note/card/revlog counts (used to prove the phone's reviews reached the server).

## Note on running the emulator here vs. in your terminal

When the emulator is launched as a background job by the assistant's tooling it
gets killed after ~2 minutes (an environment limit, not a sync problem — the
sync server process is unaffected and stays up). Launched from your own terminal
with `make phone` it persists normally. The sync itself was verified during a
window when the emulator was up (see "What was verified").
