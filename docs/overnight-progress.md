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
  and the study-map Playwright e2e (screenshot `out/study-map.png`).
