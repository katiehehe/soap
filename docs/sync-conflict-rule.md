# Sync conflict rule (rubric 7b)

We do **not** rewrite sync. Desktop and the AnkiDroid phone build run the **same
Rust engine** (`rslib/src/sync/`) and talk to the **same sync server**, so both
platforms use one protocol. This documents how reviews merge and how same-card
conflicts resolve, and the test that proves it.

## Reviews never get lost or double-counted

Each graded review is a `revlog` row keyed by its **millisecond id**. Sync merges
the revlog by id (a union), so offline reviews from both devices all land exactly
once:

- Review 10 different cards offline on the phone and 10 on the desktop → after
  sync **all 20** are present on both sides, none dropped, none duplicated.
- Verified: `make sync-test` (`tools/speedrun/sync_test.py`) reports
  `desktop 20 | phone 20`.

(Two reviews created in the _same millisecond_ on two offline devices would share
a revlog id and collide — astronomically rare for real reviews, which are seconds
apart. The test spaces reviews so each gets a distinct id, as real use does.)

## Same-card conflict → deterministic winner, no history lost

If the **same card** is reviewed offline on both devices before syncing:

1. **Both graded reviews are preserved** in the revlog — the full study history is
   kept; nothing is dropped. (`sync_test.py`: the conflict card has **2** revlog
   rows after sync.)
2. The card's **scheduling state** (queue / due / interval) converges to a single
   winner: **the review with the newer card modification time wins** (Anki's
   per-object _newer-mtime-wins_ merge). Both devices end in the _same_ state
   after syncing — the winner is deterministic, not device-dependent.

Card `mtime` is in **whole seconds**. The later review (a second or more after the
other, as real cross-device reviews are) wins cleanly. A genuine same-second tie
has no natural winner; in that rare case the merge is order-dependent, and we
accept the documented "later review wins" rule with that caveat. We never resolve
a conflict by silently dropping or duplicating a review.

## Offline, then reconnect

Full review works offline; syncing resumes when the connection returns and the
above merge applies. `sync_test.py` reviews entirely offline on two collections,
then syncs, exercising exactly this path.

## Reproduce

```bash
make sync-test          # 10+10 offline reviews + a same-card conflict, asserted
```

Output shows the revlog reconciliation (20/20, none lost/doubled) and the
conflict result (both reviews kept; both sides converge to the later review). The
on-device phone↔desktop version is a manual recording (`docs/demo-script.md`);
because the phone runs this same engine, the desktop↔desktop test above exercises
the identical sync code path.
