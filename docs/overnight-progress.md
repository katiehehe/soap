# Overnight run — progress log

Autonomous Phase 2 & 3 build (SOA Exam P Speedrun). Newest entries at the bottom.
Scope C: importance-weighting + 3-level mastery transparency + polished concept map,
then live-queue tier wiring (flag off), then honesty-guarded score calibration.
Rules honored: real Rust changes, three scores never blended, honesty/give-up rules
are code, no fabricated numbers, no AI, no sync. Commit per green feature; never push.

## Conventions

- Per task: implement -> scoped tests (`cargo test -p anki`, `./ninja check:svelte`,
  `pytest`) -> fix -> commit (conventional message) -> log here.
- After `.proto` edits: rebuild so `@generated` regenerates for TS/Python.
- Anti-fabrication: a readiness/performance number appears ONLY from a reproducible,
  seeded, held-out eval with enough data; otherwise the `NoScore` path stays.
  Bubble SIZE = importance (real unit weight / labeled subtopic estimate);
  bubble FILL = measured mastery. Never let size imply mastery.

## Timeline

### Setup (2026-07-02 ~02:38 CT)

- Started `caffeinate -dimsu` so the machine won't idle-sleep.
- Git baseline: branch `main`, clean tree (only untracked `docs/project-brief.md`).
- Baseline `./ninja check` = GREEN in ~66s (rust_test, pytest pylib+aqt, ruff, mypy,
  clippy, minilints, format). Build is warm. Safe to start editing.

### Phase 2.1 — subtopic importance weights (done)

- Added editable per-subtopic `weight` to `exam_p_topics.json`; each unit's weights
  sum exactly to its published section midpoint (general 26.5, univariate 47,
  multivariate 26.5; total 100). Labeled as emphasis estimates, NOT official SOA
  figures; they never touch the give-up thresholds.
- New `subtopic_weights()` helper in `pylib/anki/speedrun/__init__.py`.
- Guard test `test_subtopic_weights_sum_to_unit_midpoints`: weights positive, count
  matches the syllabus, and per-unit sums equal the official midpoints.
- `./ninja check` green. Commit `bc31b4eef`.

### Phase 2.2 — importance-weighted mastery rollup in the engine (done)

- Proto: `MasteryRequest` gains optional `units` + `subtopic_weights` (new
  `SubtopicWeight`); `SubtopicMastery.weight`; `UnitMastery.weight` +
  `weighted_mastery_pct`; `MasteryOverall.weighted_mastery_pct`.
- Rust: `SubtopicStats.weight`; new pure `weighted_mastery()` = weighted share of
  gate-cleared subtopics, falling back to the plain count fraction when no weights
  are supplied (+2 unit tests). `get_mastery_state` wires request weights onto the
  stats, echoes each subtopic's weight, and reports per-unit + overall weighted %.
- Python-calling test: weights echo, each unit's weight equals its section
  midpoint, and weighted mastery is honestly 0 with nothing studied.
- Updated existing callers (mastery tests, `bench.py`) and the study-map RPC call
  for the now-required request fields.
- Formatting: rslib via pinned nightly rustfmt, proto via clang-format, py via ruff.
- `./ninja check` green (~60s). Commit `3c4ce45ef`.

### Phase 2.3 — weighted "what to study next" ranking (done)

- Proto: new `StudyPriority` message + `MasteryState.priorities`.
- Rust: `study_priorities()` ranks non-cleared subtopics by weight x opportunity
  (not-started = 1.0, gathering = 0.8, judgeable in-progress = distance to the
  gate, cleared dropped), with an equal-weight fallback and deterministic ties
  (+3 unit tests). Purely reorders measured state — never fabricates a score.
- `get_mastery_state` returns the ranked priorities.
- Python test: a fresh weighted deck yields 19 priorities, top = a univariate
  weight-9 subtopic, each with a human-readable reason.
- `./ninja check` green (~112s; proto change triggered a fuller rebuild). Commit
  `834aa2714`.

### Phase 2.4 — importance-sized bubble concept map + unit detail (done)

- The study map is now a bubble concept map: every topic is a circle whose SIZE =
  its exam-importance weight (units by section weight, subtopics by their emphasis)
  and whose FILL colour = measured mastery (grey/amber/green). A legend states
  "size = importance, colour = mastery" and keeps the honesty framing.
- `lib.ts` rewritten for circle geometry (radius from weight; circle border/edge
  math; generous radial spacing that provably avoids overlap). `lib.test.ts`
  updated to circle invariants (no-overlap by centre distance, inside-canvas by
  radius, edges touch circle borders) + a new "radius grows with weight" test.
- `+page.svelte`: bubbles with labels beneath; tappable UNIT bubbles open a new
  unit detail (mastered count, exam importance, mastery-by-weight, interleaving
  tier); subtopic detail gains its weight; overall panel shows "% by exam weight"
  and a "Study next" suggestion from the engine's priorities; calm hover/selection
  transitions that honour `prefers-reduced-motion`. Passes real unit + subtopic
  weights to `getMasteryState`.
- Green: svelte-check, eslint, prettier, vitest geometry, full `./ninja check`,
  and the study-map Playwright e2e (screenshot `out/study-map.png`). Commit
  `ba5860e7b`.

## Phase 3 — live queue + honest calibration

### Phase 3.1 — opt-in three-tier mastery ordering in the live queue (done)

- The real scheduler change: when the config flag `speedrunMasteryScheduler` is
  on, `Collection::build_queues` reorders the gathered new cards by mastery tier
  (Blocked -> WithinUnit -> CrossUnit, blocked grouped by subtopic). OFF by
  default, so upstream Anki's queue is unchanged unless a user opts in (this flag
  is also the ablation's Full-vs-plain switch).
- Implemented in `rslib/src/speedrun/mastery.rs` (`speedrun_reorder_new_cards` +
  `speedrun_note_subtopic_map` + the flag helper), reusing the already-tested
  `compute_pools`/`order_new_cards`/`speedrun_subtopic_stats`. Read-only (no DB
  writes), so undo and integrity are untouched. The flag is a plain string config
  key, so upstream's `BoolKey` enum is not modified. Upstream hook is 3 lines in
  `scheduler/queue/builder/mod.rs` (logged in `docs/upstream-touched.md`).
- Tests (4 new, 23 speedrun rust tests total): flag defaults off + settable;
  reorder groups blocked subtopics and puts untagged cards last; no-op without
  syllabus cards; `build_queues` builds a valid 2-card queue with the flag on.
- Safety gates all passed: full `./ninja check` green (no scheduler regression),
  and `make crash-test` survived 20 mid-review SIGKILLs with zero corruption.
  Commit `368530302`.

### Phase 3.2 — honest score calibration (memory calibrated; perf/readiness gated) (done)

- `pylib/anki/speedrun/calibration.py`: pure, deterministic calibration metrics
  (Brier, log loss, expected calibration error, reliability bins) + a
  `calibration_report` with an insufficient-data gate — the honesty/give-up rule
  applied to calibration. 8 known-value unit tests
  (`test_speedrun_calibration.py`).
- `tools/speedrun/evals/memory_calibration.py` + `make calibration`: the memory
  signal IS FSRS; this reports the engine's held-out (time-series split) log loss
  and RMSE on a real review history, and abstains honestly ("not enough data yet")
  on a thin/seed collection (verified: seed deck -> give-up, no number).
- `docs/score-models.md`: the method written down for all three signals + the
  shared give-up rule + reproducibility (seed, leakage scan, commands) + an
  explicit "what is NOT done yet" (no calibrated performance model, so readiness
  stays `NoScore`; nothing fabricated).
- `compute_readiness` left unchanged: still returns `NoScore` — no number is
  invented before the performance model exists.
- `./ninja check` green. Commit `5a8880aaf`.

### Specs synced (PRD, vision, checklist)

- `SPEC_CHECKLIST.md`: 7a now `[x]` (live-queue wiring done behind the flag +
  weighted rollups + priorities); Step 1 / Sunday memory-calibration + score-
  mapping marked `[~]` with the new harness/doc; ablation switch noted; new files
  - the queue-builder hook added to the merge log.
- `docs/vision.md`: live-queue integration marked built; recent additions
  (weights, weighted rollup, priorities, sized bubbles, calibration) listed.
- `PRD.md`: §8 status note (live queue + weighting) and §9 pointer to
  `docs/score-models.md` + the calibration library.
- `./ninja check` (dprint) green.

## Final validation (2026-07-02)

- Full `./ninja check` green (rust_test, pytest pylib+aqt, ruff, mypy, clippy,
  eslint, svelte, prettier, dprint, minilints, vitest).
- `make bench` on 50k cards: next-card p95 0.05ms, mastery query p95 0.12ms
  (weighted rollup + priorities added, still negligible), mastery-ordered new
  cards p95 148ms, readiness p95 3.78ms — all within the speed targets.
- `make crash-test`: 20/20 mid-review SIGKILLs, zero corruption.
- Playwright e2e: 4/4 pass (readiness dashboard, study map, sanity x2).

## Summary of the night

Phase 2 (all committed, all green):

- 2.1 per-subtopic importance weights (`bc31b4eef`)
- 2.2 importance-weighted mastery rollup in the engine (`3c4ce45ef`)
- 2.3 weighted "what to study next" ranking (`834aa2714`)
- 2.4 importance-sized bubble concept map + unit detail (`ba5860e7b`)

Phase 3 (all committed, all green):

- 3.1 opt-in three-tier mastery ordering in the live queue, default off,
  self-contained + read-only (`368530302`)
- 3.2 honest calibration: memory (FSRS held-out) + tested metrics library +
  `docs/score-models.md`; readiness stays `NoScore` (no fabricated number)
  (`5a8880aaf`)
- specs synced (`ad3b0dd43`)

Honesty guarantees kept: three scores never blended; give-up rule untouched (no
threshold weakened); no readiness/performance number invented; bubble size =
importance, colour = measured mastery; no AI; no sync. Undo/integrity verified.

Not done (by design / out of scope for the unattended run): calibrated
performance model (needs a disguised-item dataset), the ablation _run_ itself,
AI features, and two-way sync.

## Follow-up: two more 7a Rust changes (requested)

### Feature A — Points-at-stake review order (new RPC) (done)

- New protobuf message (`PointsAtStakeCard` / `PointsAtStakeOrder`) + RPC
  `GetPointsAtStakeOrder`, called from Python. Orders due review-pipeline cards
  by **topic importance weight x measured student weakness** (weakness = 1 - mean
  FSRS retrievability; a neutral 0.5 when there is no retention evidence),
  highest stakes first, ties broken by the more-urgent card. Read-only, so it
  never reschedules a card and FSRS intervals stay valid.
- Rust: `points_at_stake_order` + `subtopic_weakness` +
  `speedrun_due_cards_with_subtopic` (+4 unit tests). Python-calling test answers
  a card and checks it comes back with `stakes == weight * weakness`, sorted
  descending.
- `./ninja check` green (27 speedrun Rust tests + Python).

### Feature B — Topic-aware live review scheduling (done)

- Brings weak-topic due cards back **sooner** in the live review queue: behind an
  opt-in `speedrunPointsAtStake` flag (default off), `build_queues` reorders the
  gathered review cards by points at stake (topic weight x weakness). Order-only,
  so **FSRS intervals stay valid and undo/integrity are untouched**; with the
  flag off the queue is exactly upstream's.
- Weights reach the engine via a `speedrunSubtopicWeights` config key that Python
  writes from the topic map (`apply_subtopic_weights_config`, called by
  `build_deck`); absent -> equal weighting (weakest-topic-first). Flag + weights
  are plain config keys, so upstream's `BoolKey` enum is untouched.
- Rust: `speedrun_reorder_review_cards` + flag/weights helpers (+4 tests: flag
  default off, reorders by weight, no-op without weights, `build_queues` builds
  with the flag on). Python test: `build_deck` writes the weights and the live
  flag still builds a valid queue.
- Safety gates: full `./ninja check` green (31 speedrun Rust tests + Python; no
  scheduler regression) and `make crash-test` 20/20 with zero corruption.

### Audit vs docs/project-brief.md + fixes (done)

Ran three parallel read-only subagents auditing (1) the honesty/give-up/no-
fabrication rules, (2) the Rust change + tests + undo + merge log, (3) doc/spec
consistency. Verdict: code is compliant on the hard rules (readiness never a bare
number; three scores separate; bubble size = importance vs colour = mastery;
coverage abstains; weakness measured). Fixed the concrete findings:

- **Honesty copy:** the readiness dashboard now distinguishes "not enough data"
  from "data threshold met, model not yet calibrated" (was misreported).
- **Honesty bundle:** added `ReadinessScore.past_accuracy` + a dashboard row for
  "how accurate past guesses were" (brief 1 requires it); shows not-yet-available
  until scores are emitted. (`f14021de8`)
- **Undo:** added a Python undo test with both live-queue flags on.
- **README (brief 12 blocker):** replaced the stock-Anki README top with a
  Speedrun section — exam stated up front, AGPL + Anki credit, build steps for
  both apps, architecture, the Rust-change note, and the files-touched pointer.
- **Stale docs reconciled** with the built code (5 RPCs, live-queue flags,
  bubble map, calibration, 42-card deck): `docs/rust-change.md`,
  `docs/upstream-touched.md`, `docs/demo-script.md`, `SPEC_CHECKLIST.md`,
  `docs/vision.md`, `PRD.md` (also softened two PRD overclaims: ablation
  "harness" -> pre-registered plan; leakage scan "wired to CI" -> run in
  `./ninja check`).
- `./ninja check` green throughout.
