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
- `./ninja check` green.
