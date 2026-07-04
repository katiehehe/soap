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

Prep (once):

```bash
export ANDROID_HOME="$HOME/Library/Android/sdk"
"$ANDROID_HOME/emulator/emulator" -avd Medium_Phone &
"$ANDROID_HOME/platform-tools/adb" wait-for-device
"$ANDROID_HOME/platform-tools/adb" install -r \
  ~/dev/Anki-Android/AnkiDroid/build/outputs/apk/play/debug/AnkiDroid-play-arm64-v8a-debug.apk
# Start a local sync server (or use AnkiWeb). Point BOTH desktop and phone at it.
```

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
adb install -r ~/dev/Anki-Android/.../AnkiDroid-play-arm64-v8a-debug.apk
# Real phone: transfer the APK, enable "install unknown apps", sideload, open it.
```

Record: install → open AnkiDroid → load the Exam P deck (import a `.colpkg` from
desktop or sync) → run a short review session on **our** engine → open the
navigation drawer → tap **"Exam readiness"** to show the three signals
(Memory/Performance/Readiness) with ranges + the give-up rule, computed on-device
by the shared engine (`ReadinessScoresActivity` → `computeReadiness`; see
`docs/phone-scores.md`). Prove the engine is ours on camera (any one is enough):

```bash
APK=~/dev/Anki-Android/AnkiDroid/build/outputs/apk/play/debug/AnkiDroid-play-arm64-v8a-debug.apk
unzip -p "$APK" lib/arm64-v8a/librsdroid.so | strings | grep -iE "speedrun|ComputeReadiness|Mastery" | head
# -> anki/rslib/src/speedrun/service.rs, .../out/anki.speedrun.rs, ComputeReadinessRequest ...
```

## Where these plug into the video

Beats 3 (sync) and the clean-install section of `docs/demo-script.md`. Everything
else in that script is recordable today from the desktop app + terminal.
