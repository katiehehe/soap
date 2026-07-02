# Sync plan + test (Friday / Sunday)

The phone must share the engine **and sync** with desktop (else a 70% cap). The
shared engine is already on the phone (`docs/android-build.md`); this file plans
the sync bring-up and its test so Friday is a checklist, not a design session.

## What we rely on

Anki already has a full sync protocol (`rslib/src/sync/`) — collection sync +
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

## Test 7b — reviews land once, conflicts resolve

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

## Notes / risks

- Keep the sync server local and disposable; never point at AnkiWeb for tests.
- Version skew: the phone build and desktop must be sync-compatible (same engine
  fork). Since both come from this fork's engine, the sync schema matches.
