# Recording steps — the manual captures for hand-in

Three clips need a real screen recording (they can't be scripted): the
**phone→desktop sync**, the **clean-machine desktop install**, and the **phone
install/review**. Everything is already built and tested; this is just the
capture checklist. **Do not stage or fake any of it** — a faked sync/AI clip is
an automatic fail. Use QuickTime (desktop) and the emulator's built-in recorder
or `adb screenrecord` (phone).

## A. Phone → desktop two-way sync (the money shot)

Proves reviews flow phone→desktop with none lost/doubled. The code path is
already verified green by `make sync-test` (20/20, conflict rule); this records
it on-device.

Prep (once) — all reproducible via the Makefile:

```bash
make sync-server         # local sync server (Anki's own), binds 0.0.0.0:27701
make sync-seed           # seed the server with the Exam P deck + mint an hkey
#   ...or seed the FULLY-SCORED persona so the phone shows all three scores:
make seed-persona && PYTHONPATH=pylib:out/pylib out/pyenv/bin/python \
    tools/speedrun/sync_setup.py --from-collection out/demo-persona.anki2
make phone               # boot the Speedrun_P emulator + open AnkiDroid
make phone-install       # (re)install the freshest APK first, if rebuilt
make sync-phone-config   # point AnkiDroid at the local server (no UI login)
make sync-desktop        # point the desktop profile at the same server (app CLOSED)
```

On-device sync verified this session (server→phone): tapping **Sync** in the home
shell → **Select collection to keep → AnkiWeb → Replace** ran a real full download
+ media sync from the local server (logcat: `anki::sync::media::syncer: media sync
complete`, `SyncMediaWorker: success`). The phone runs the exact `librsdroid.so`
engine, so the two-way + conflict + offline path is the same one `make sync-test`
(20/20) and `make sync-twoway` (live server) assert green.

Record (one take):

1. Desktop: open the SOA Exam P deck, show a specific card's due count / a subtopic's review count on the readiness dashboard. Sync (toolbar → Sync).
2. Phone (bring emulator forward, screen-record from here): review **N** cards
   on that subtopic, grading them. Then Sync on the phone.
3. Desktop: Sync again → show the **same N reviews now on desktop** (review count
   climbed by N; the dashboard updates). Say the numbers out loud.
4. Optional conflict beat: review the _same_ card offline on both, sync, and show
   both reviews kept with the deterministic winner (`docs/sync-conflict-rule.md`).

Keep `adb logcat | grep -i backend` in a corner to show AnkiDroid loading **our**
engine (`makeBackendUsable` succeeds).

## B. Clean-machine desktop install (covers the "clean device" hard limit)

"Clean" = no dev toolchain (no Rust/Node/Python) and no repo checkout. The DMG is
self-contained (bundles its own Python).

```bash
ls -lh out/installer/dist/anki-25.09.99-mac-apple.dmg      # the drag-install DMG
otool -L /Applications/Anki.app/Contents/MacOS/Anki        # system + bundled Python only
```

Fastest clean context (no second Mac): **new Standard user account.** System
Settings → Users & Groups → add a Standard user → log in there → mount the DMG →
drag **Anki.app** to Applications → right-click **Open** (unsigned). Record:

1. Launch on the clean account → it opens a collection (no toolchain present).
2. Open the custom Home shell → **Concept map / Progress / Readiness** tabs work.
3. Say on camera: **"AI is off by default and it still produces all three
   scores"** (this is the hard requirement; `test_three_signals_compute_with_ai_off`).

Airtight alternative: a throwaway macOS VM (`tart`) or a rented cloud Mac.
Apple Silicon only (arm64 binary).

## C. Phone install + review (clean device)

```bash
# Same-machine emulator:
adb install -r ~/dev/projects/speedrun/Anki-Android/.../AnkiDroid-play-arm64-v8a-debug.apk
# Real phone: transfer the APK, enable "install unknown apps", sideload, open it.
```

Record: install → open AnkiDroid (it launches straight into the Svelte **home
shell**) → load the Exam P deck (import a `.colpkg` from desktop or sync) → run a
short review session on **our** engine → tap the **Readiness** tab in the home
shell to show the three signals (Memory / Performance / Readiness) with ranges +
the give-up rule, computed on-device by the shared engine (the Svelte
`readiness-dashboard` route → `computeReadiness` over AnkiDroid's post-bridge;
the old native `ReadinessScoresActivity` was removed so scores stay
engine-sourced — see `docs/phone-scores.md`). A captured example of this
populated three-score screen (synthetic-persona data) is in
`out/phone-3scores-memory.png` / `-performance.png` / `-readiness.png`. Prove the
engine is ours on camera (any one is enough):

```bash
APK=~/dev/projects/speedrun/Anki-Android/AnkiDroid/build/outputs/apk/play/debug/AnkiDroid-play-arm64-v8a-debug.apk
unzip -p "$APK" lib/arm64-v8a/librsdroid.so | strings | grep -iE "speedrun|ComputeReadiness|Mastery" | head
# -> anki/rslib/src/speedrun/service.rs, .../out/anki.speedrun.rs, ComputeReadinessRequest ...
```

## Where these plug into the video

Beats 3 (sync) and the clean-install section of `docs/demo-script.md`. Everything
else in that script is recordable today from the desktop app + terminal.
