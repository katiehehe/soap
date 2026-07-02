# Rust engine change: the three-tier, mastery-gated scheduler

This fork's graded Rust change is a **three-tier, mastery-gated scheduler** for SOA
Exam P, implemented in the shared `anki` crate (`rslib/`). This document explains
why it belongs in Rust (not Python/Svelte), what exists today, and how the current
scaffold grows into the full feature.

For the concrete list of upstream files touched and their merge risk, see
[upstream-touched.md](upstream-touched.md) and `SPEC_CHECKLIST.md`. For the FSRS
algorithm the memory model is built on, see [fsrs-reference.md](fsrs-reference.md).

## Why this must be in Rust, not Python or JS

- **It is where scheduling actually happens.** The review queue is built in the
  Rust engine at `rslib/src/scheduler/queue/builder/` (`gathering.rs`,
  `sorting.rs`, `mod.rs`) and iterated in `rslib/src/scheduler/queue/mod.rs`.
  Topic-aware ordering has to change how that queue is gathered, sorted and
  merged. Reordering cards after the fact in Python/JS would be a reimplementation,
  not a change to the scheduler.
- **One engine ships to both apps.** Desktop (`pylib`/`aqt`) and AnkiDroid consume
  the _same_ compiled engine (AnkiDroid via the `Anki-Android-Backend` `.aar`). A
  Rust change ships to the phone for free; a JS/Swift/Python scheduler would not,
  and per the rubric caps the project at 50%.
- **The gate needs engine-only data.** The mastery gate is
  `blocked accuracy >= 80% AND FSRS retrievability >= 0.90 over >= 10 problems`.
  FSRS retrievability is computed in Rust (`rslib/src/scheduler/fsrs/`), and review
  accuracy comes from the `revlog` table via `rslib/src/storage`. Both are cheapest
  and most consistent at the source.
- **Speed on 50k cards.** The mastery/ordering query must power the dashboard on a
  50,000-card deck (see `PRD.md` 15). Doing it in Rust over SQLite keeps it within
  the p95 budgets; marshalling everything to Python first would not.
- **Integrity/undo.** Card and queue mutations must go through the Rust
  collection/undo layer (`rslib/src/undo`, `rslib/src/collection`) so undo keeps
  working and the collection is never corrupted.

## What exists today

A self-contained `SpeedrunService` (new file `proto/anki/speedrun.proto`,
implemented in `rslib/src/speedrun/`) so the diff against upstream Anki stays small:

- `SpeedrunPing` - a trivial, read-only RPC that proves the
  proto -> Rust -> Python plumbing end to end (3 Rust unit tests + 1
  Python-calling test; verified it makes no writes to the collection).
- `ComputeReadiness` - returns a protobuf `oneof { NoScore, ReadinessScore }`, so a
  bare readiness number literally cannot be emitted. The give-up rule is a
  pre-registered Rust assertion: below `>= 200 graded reviews AND >= 50% coverage`
  (coverage weighted by the SOA section weights) it returns `NoScore { reason, ... }`.
  Coverage is **practiced** coverage (PRD 9: "% of syllabus practiced") - the share
  of subtopics with `>= 1` graded review, not the share you merely own cards for - so
  a freshly imported full deck reads 0%, not 100% (regression test:
  `unstudied_cards_do_not_count_as_coverage`). This is the honesty/give-up rule as code.
- **The three-tier mastery model** (`rslib/src/speedrun/mastery.rs`): per subtopic,
  the gate is computed from real revlog accuracy + FSRS retrievability
  (`>= 80% accuracy AND >= 0.90 retrievability over >= 10 problems`); each subtopic
  is Blocked, WithinUnit, or CrossUnit, and a unit only opens the cross-unit pool
  once all its subtopics clear. Exposed via `GetMasteryState` (which also returns
  an importance-weighted mastery rollup and a "what to study next" ranking) and,
  for the topic-aware order, `GetMasteryOrderedNewCards` (block -> within-unit ->
  cross-unit).
- `GetPointsAtStakeOrder` - a points-at-stake review order: due cards sorted by
  topic importance weight x measured student weakness (1 - retention), highest
  value first. Read-only, so it never reschedules a card.
- `GetStudyPlan` - today's tiered study plan: the decks to study now, grouped by
  tier (blocked -> within-unit -> cross-unit), each carrying Anki's own
  deck-tree counts for today (daily-limit capped, i.e. the same numbers the deck
  list shows). It reads the measured gate state to assign a tier and attributes
  the real counts to the matching subtopic/unit/root deck via the deck tree's
  own structure (no display-name duplication). Read-only: it only reads
  `deck_tree`, so it never reschedules or fabricates a score. The tiering itself
  is a pure, unit-tested function (`build_study_plan`). This makes the scheduler
  tiers visible as a _daily plan_ rather than an invisible reorder.
- `GetStudyPace` - coverage pace vs the user's exam date: counts the new
  (unstudied) syllabus cards, reads the exam deck's new-cards/day limit, and
  works out the pace needed to introduce them all before the exam
  (recommended/day, projected finish, on-track/behind). Pure arithmetic over
  measured counts + the stored exam date (`compute_pace`, unit-tested); it is a
  _coverage_ pace, never the readiness score. Read-only.

All seven RPCs are called from Python and covered by tests (~53 Rust unit tests
across `service.rs` + `mastery.rs`, plus a Python-calling test for every RPC).

The tier order and the points-at-stake order are now wired into the **live**
queue builder behind two opt-in, default-off config flags:
`speedrunMasteryScheduler` and `speedrunPointsAtStake`. The mastery scheduler
tier-orders **both** the new-card queue AND the due-review queue (blocked
practice carries through reviews: a not-yet-mastered subtopic's due cards are
grouped/served first, then within-unit, then cross-unit, and only interleave
once the subtopic clears its gate). `speedrunPointsAtStake` reorders due reviews
by points at stake; when both are on the tier is primary and stakes break ties
within a tier. All reorders are read-only (presentation only), so FSRS intervals
stay valid and undo/integrity are untouched; with the flags off the queue is
built exactly as upstream. The orders are also exposed as RPCs so the
dashboard/study map can use them.

## How the scheduler is built

(Items 1-3 are implemented. The live-queue integration ships as a post-gather,
read-only reorder of the gathered new/review cards in `build_queues` behind the
two flags above, rather than editing `gathering.rs`/`sorting.rs` in place, which
keeps the upstream diff tiny and undo/integrity trivially safe. The
`gathering.rs`/`sorting.rs` hook points below remain the route for any future
deeper integration.)

1. **Mastery model (new, in `rslib/src/speedrun/`).** Per subtopic tag
   (`subtopic::...`), compute gate state from recent parameterized reviews:
   blocked accuracy and FSRS retrievability over the last N attempts. A subtopic is
   `Blocked`, in its unit's `WithinUnitMix`, or in the `CrossUnitMix` pool.
2. **`GetMasteryState` RPC.** Expose per-subtopic tier + pool membership (a new
   message on `SpeedrunService`), called from Python for the dashboard and reused
   by the scheduler. Follows the same pattern as `SpeedrunPing`.
3. **Ordering hooks in the queue builder** (the actual scheduling change):
   - `rslib/src/scheduler/queue/builder/gathering.rs` - skip/hold cards whose
     subtopic has not cleared the gate for the tier currently being served.
   - `rslib/src/scheduler/queue/builder/sorting.rs` - order within a tier (blocked
     single-subtopic practice first).
   - `merge_new` / `merge_day_learning` in
     `rslib/src/scheduler/queue/builder/mod.rs` - control interleaving: mix
     confusable sub-types **within a unit** (tier 2, the ablated tier) before mixing
     **across units** (tier 3).
   - `rslib/src/scheduler/queue/mod.rs` (`CardQueues::iter`) - final presentation
     order safeguard.
4. **Tiers, each with its own gate (not one global switch):**
   1. Block subtopics -> build procedure in isolation.
   2. Interleave within a unit -> train recognition of confusable sub-types.
      **This tier is what the ablation removes.**
   3. Interleave across units -> spacing (low confusability).

## Tests / guarantees for the full change

- = 3 Rust unit tests: tier transition, gate condition, pool ordering.
- 1 Python-calling test through `col._backend`.
- FSRS intervals stay valid; undo works; no collection corruption.
- Fast enough to power the dashboard on a 50k-card deck.

## Ablation (study feature under test)

The **within-unit interleaving tier** is the pre-registered ablation target:
build 1 = full three tiers; build 2 = within-unit interleaving removed (mastered
subtopic drops straight into a global mixed pool); build 3 = plain Anki. See
`PRD.md` 10 and `SPEC_CHECKLIST.md` 5.
