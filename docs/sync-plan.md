# Sync plan + test (Friday / Sunday)

The phone must share the engine **and sync** with desktop (else a 70% cap). The
shared engine is already on the phone (`docs/android-build.md`); this file plans
the sync bring-up and its test so Friday is a checklist, not a design session.

## What we rely on

Anki already has a full sync protocol (`rslib/src/sync/`): collection sync +
media sync against a sync server. We do **not** write a new sync engine; we make
our fork's desktop and the AnkiDroid build talk to the **same self-hosted sync
server** and verify reviews flow both ways without loss.

## Setup (Friday)

1. Run Anki's built-in sync server locally (`anki.syncserver` /
   `SYNC_ENDPOINT`), create one test account.
2. Point desktop (Preferences → Network) and the phone (AnkiDroid → sync
   settings) at that endpoint with the same account.
3. Do a first full sync so both sides share one collection (the Exam P deck with
   its subtopic tags).

## Test 7b: reviews land once, conflicts resolve

- **Offline divergence:** with both offline, review **10 cards on the phone** and
  **10 different cards on the desktop**.
- Reconnect and sync both.
- **Assert:** all **20** reviews are present on both sides, **none doubled, none
  lost** (compare revlog counts + card states before/after).
- **Same-card conflict:** review the **same** card differently on each side while
  offline; after sync the winner is deterministic and **documented** (Anki's
  rule: the later/normal-sync merge; record exactly what happens).
- **Offline-then-reconnect:** confirm a phone review made with no network appears
  on desktop after reconnecting and syncing.

## Acceptance

- A recording of a card reviewed on the phone appearing on desktop after sync.
- Revlog reconciliation table (before/after counts per side) showing 20/20, zero
  duplicates, zero losses.
- One paragraph documenting the same-card conflict winner and why.

## Status (built)

- **Scripted 7b test built + passing:** `make sync-test`
  (`tools/speedrun/sync_test.py`) starts Anki's built-in sync server, uploads the
  Exam P deck, downloads it to two client collections, reviews 10 different cards
  offline on each, syncs, and asserts all 20 land once (desktop 20 | phone 20,
  none lost/doubled). It also runs a same-card conflict and asserts both revlog
  rows are kept and both sides converge to a deterministic winner.
- **Conflict rule documented:** `docs/sync-conflict-rule.md`.
- **Phone score surface:** `docs/phone-scores.md` (shared engine computes all
  three signals on-device; native screen is the remaining UI).
- **On-device phone↔desktop recording:** manual, per `docs/demo-script.md` (the
  phone runs the same engine, so the scripted desktop↔desktop test exercises the
  identical sync code path).

## On-device verification (emulator): status + tooling

Re-checked the 2-way sync requirements against the **real AnkiDroid emulator**
(our fork's engine), talking to a local `make sync-server` on `10.0.2.2:27701`.

Verified:

- **Engine 2-way sync is valid (authoritative):** `make sync-test` → `desktop 20 |
  phone 20`, none lost/doubled; same-card conflict keeps both revlog rows and both
  sides converge to one deterministic winner; two-way reconcile 0.02s (< 5s). This
  is the exact Rust sync code compiled into the phone APK (`librsdroid.so`).
- **The phone participates in the real protocol:** the AnkiDroid emulator
  authenticates (hkey from `user:pass`) and performs real Anki sync ops
  (`/sync/meta`, `/sync/upload`, `/msync/begin`) against the local server.
- **Phone → desktop demonstrated on-device:** reviews graded in the AnkiDroid
  emulator were uploaded to the server, then a desktop peer downloaded them
  (the phone's `revlog` rows showed up in the desktop collection). Captured:
  `out/phone-reviewed.png` (3 cards studied on the phone) →
  `out/desktop-readiness-after-sync.png` (desktop readiness reads "3 cards
  reviewed / 3/200").
- **Server → phone demonstrated on-device (re-verified this session):** with the
  fully-scored persona uploaded to the local server
  (`tools/speedrun/sync_setup.py --from-collection out/demo-persona.anki2`), the
  `Speedrun_P` emulator ran the real protocol: Sync → *Select collection to keep*
  → **AnkiWeb** → **Replace** → full download + media sync (logcat:
  `anki::sync::media::syncer: media sync complete`, `SyncMediaWorker: success`;
  186 notes pulled). The phone then rendered the three scores with ranges (see
  `docs/phone-scores.md`).
- **Client↔server incremental merge works:** a headless desktop/editor peer on the
  same engine does normal (non-full) merge syncs (e.g. server `revlog` 3 → 5 via a
  merge, not a replace).

Not cleanly demonstrated on-device (environment-blocked, **not** a sync defect):

- A single **fresh phone→desktop *review* recording on the current themed build.**
  Two environment factors made the app UI unstable this session (neither is a
  sync/engine defect): (1) a leftover **phone crash-test loop** from an earlier run
  was force-stopping AnkiDroid every ~3 s (killed once found); and (2) the debug
  build ships **LeakCanary**, which heap-dumps on the WebView's retained objects and
  under heavy host load takes many seconds + steals focus (its `LeakLauncherActivity`
  pops over AnkiDroid), so tab/reviewer navigation intermittently bounces. `Speedrun_P`
  is a lean 2 GB AVD; with a quiet host (fewer background `./run`/`yarn dev`
  processes) or a release build (no LeakCanary), the reviewer flow is stable. The
  server→phone full download + the three-score render DID complete on-device this
  session; only the phone→desktop *review* leg awaits a stable capture (prior real
  capture exists, see above). The shared engine merges correctly (proven by
  `make sync-test`/`make sync-twoway`), so this is a demo-environment limitation.

Tooling added for reproducing the on-device test:

- `tools/speedrun/sync_emu.py`: desktop-side peer on the shared engine (persistent
  headless collection) with `sync` / `status` / `review N` / `card` / `reset`
  subcommands, pointed at the same local server the phone uses.
- `tools/speedrun/emu_drive.py`: tiny uiautomator driver (tap-by-text, wait,
  screenshot) to drive the AnkiDroid emulator UI robustly.

Repro sketch: `make sync-server` (leave running) → boot emulator + open AnkiDroid
pointed at `10.0.2.2:27701` (`user`/`pass`) → sync once to share the deck →
review on phone, sync, then `sync_emu.py sync` on desktop and confirm the phone's
`revlog` rows arrive (and the reverse).

## Notes / risks

- Keep the sync server local and disposable; never point at AnkiWeb for tests.
- Version skew: the phone build and desktop must be sync-compatible (same engine
  fork). Since both come from this fork's engine, the sync schema matches.
