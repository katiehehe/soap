# Score models — memory, performance, readiness

Three **separate** signals, never blended into one number, each shown with a
range and honest uncertainty. This is the method written down (rubric §9): what
each model is, how it is calibrated, and where it deliberately abstains. Where a
piece exists today it is marked **[built]**; the rest is **[planned]** with its
method fixed in advance so no number is ever invented after the fact.

> The overriding rule: **a number appears only when it is backed by real,
> reproducible, held-out evidence.** Otherwise the app shows the reason it is
> withheld, never a guess in a nice font.

## Shared give-up rule

- **Readiness** returns nothing below **≥ 200 graded reviews AND ≥ 50% weighted
  practiced coverage**. This is a Rust assertion, not a UI hint:
  `compute_readiness` returns `oneof { NoScore, ReadinessScore }`
  (`rslib/src/speedrun/service.rs`), so a bare readiness number literally cannot
  be emitted below threshold.
- **Calibration** (any model) reports no number below a minimum sample count
  (`pylib/anki/speedrun/calibration.py`, default 100 graded predictions;
  `tools/speedrun/evals/memory_calibration.py`, default 100 reviews). A
  reliability curve over a handful of points is noise, not evidence.

## 1. Memory — "can you recall this fact right now?" **[built]**

- **Model:** Anki's **FSRS**, in the shared Rust engine. It predicts the
  probability of recall for a fact given its review history.
- **Calibration (held-out):** the engine's time-series–split evaluation
  (`evaluate_params`, the same replay FSRS uses to grade parameter fits) reports
  **log loss** and **RMSE over reliability bins** on reviews the fit did not see.
  Run it with `make calibration` (or `--col PATH` for a real collection);
  `tools/speedrun/evals/memory_calibration.py` prints the numbers, or an explicit
  "not enough data yet" on a thin history.
- **Reliability library:** `pylib/anki/speedrun/calibration.py` provides pure,
  unit-tested Brier score, log loss, expected calibration error, and the
  reliability curve (mean predicted vs mean observed per bin). These are the
  reusable metrics behind the give-up rule and the performance model below
  (`pylib/tests/test_speedrun_calibration.py` checks them against known values).
- **Honest state today:** the seed deck has no reviews, so calibration abstains;
  on a real study history it produces real numbers.

## 2. Performance — "can you solve a NEW exam-style question?" **[pipeline built; abstains on real data]**

Per SPOV 1 this measures **procedure** (recognition + recall + setup), the
application component FSRS cannot see — so it must be allowed to diverge from
memory where transfer is weak.

- **Target:** P(correct) on a **disguised, parameterized** exam-style question
  (numbers regenerate each time), not a clean cue.
- **Features:** subtopic mastery (from the gate: accuracy + FSRS retrievability),
  difficulty tag, response time, and coverage.
- **Model (built):** a small **calibrated** logistic-regression classifier in
  `pylib/anki/speedrun/performance.py` — deterministic seeded SGD, no external ML
  deps — trained on a **seeded held-out split** (`evalsplit.py`) and scored with
  `calibration.py` (Brier / log loss / ECE) plus accuracy and AUC, against a
  majority-class baseline. Unit-tested in `test_speedrun_performance.py`.
- **Validation:** `make performance` runs the full pipeline on a **clearly
  labelled synthetic fixture** (`tools/speedrun/evals/performance_eval.py`):
  seeded split, leakage scan (clean), calibrated, beats the baseline. This proves
  the pipeline end to end; the numbers are synthetic, **not** a real student
  result.
- **Data & safety:** a real result needs a held-out set of disguised performance
  items with correctness labels, kept out of training and verified by the leakage
  scan. **Until that dataset exists, performance reads "not yet measured" — never
  a fabricated number.**
- **Divergence check:** the paraphrase test (rubric 7d) compares clean-cue recall
  against reworded-question accuracy and reports the gap, confirming performance
  is not just memory in disguise.

## 3. Readiness — "would you pass today, and how sure are we?" **[planned; give-up rule built]**

- **Mapping (written down, applied once the performance model is calibrated):**
  performance + coverage → **P(pass ≥ 6)** with a confidence band, a projected
  **0–10 band**, and a **bootstrap range**. Coverage gates it: below the coverage
  line the app abstains.
- **Today:** `compute_readiness` meets the data threshold path but returns
  `NoScore { reason: "…model is not yet calibrated…" }` — we refuse to invent a
  number before the performance model exists. This is enforced and tested
  (`meeting_thresholds_still_refuses_a_number_without_models`).
- **Honesty bundle:** every real `ReadinessScore` carries `point, low, high,
  coverage_pct, confidence, updated_at, reasons[], next_best_action` — the struct
  makes a bare number impossible to emit.

## Reproducibility

- **Seeded split:** `train_test_split(seed)` in `evalsplit.py` — same ids + seed
  give the same split every run.
- **Leakage gate:** `tools/speedrun/leakage_scan.py` flags any test item (or
  near-copy) that leaks into training and exits non-zero.
- **Commands:** `make calibration` (memory); performance/readiness evals land
  with their datasets. All deterministic — anyone can re-run and get the same
  numbers.

## What is deliberately NOT done yet (stated honestly)

- No calibrated **performance** model yet (needs the disguised-item dataset), so
  **readiness stays `NoScore`**. The mapping above is fixed in advance so it
  can't be tuned to flatter the result later.
- **Memory** calibration prints numbers only on a real review history; on a fresh
  or seed collection it abstains by design.
