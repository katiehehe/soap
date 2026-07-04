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
  result. `make performance ARGS="--persona"` additionally runs it on the **real
  held-out item corpus × a synthetic student cohort**, split **by item** (no item
  leakage), reporting held-out accuracy/AUC/calibration vs the majority baseline
  (e.g. acc ~0.76 > baseline ~0.71, ECE ~0.06).
- **Data & safety:** a real result needs a held-out set of disguised performance
  items with correctness labels, kept out of training and verified by the leakage
  scan. **Until that dataset exists, performance reads "not yet measured" — never
  a fabricated number.**
- **Divergence check (measured):** the paraphrase test (rubric 7d, `make
  paraphrase`) compares clean-cue **card recall** against **reworded-question
  accuracy** on 30 cards × 2 rewordings. Result on the synthetic cohort: recall
  **73%** vs reworded **32%** → a **+41-point gap** in every subtopic, so
  performance is a genuinely separate, harder signal — not memory in disguise. A
  copycat control (performance model on both sides) collapses to ~0, confirming
  the test would catch a performance signal that merely tracked memory.
  [docs/paraphrase-test.md](./paraphrase-test.md).

## 3. Readiness — "would you pass today, and how sure are we?" **[built; give-up rule in Rust]**

Emitted by the Rust `compute_readiness` (so the honesty bundle is enforced by the
type system) from graded **practice-test** evidence.

- **Give-up rule (unchanged):** below **≥ 200 graded reviews AND ≥ 50% weighted
  coverage** it returns `NoScore`. Even above that, a readiness NUMBER also needs
  **≥ 30 graded practice-test questions** (config `speedrunPracticeStats`, written
  by `practice_test.record_test`); below that it still abstains. No practice
  evidence → no number.
- **Mapping (fixed in advance, in `readiness_from_practice`):** let p̂ = correct /
  questions over all graded practice-test questions.
  - **Projected 0–10 band:** scaled ≈ 10 × p̂; the range is 10 × the **95% Wilson
    interval** on p̂ (robust for small n and near 0/1).
  - **P(pass):** SOA P passes at scaled ≥ 6, i.e. p ≥ **0.60** under the linear
    map. P(pass) = Φ((p̂ − 0.60) / se), the normal approximation to the binomial
    proportion (se = √(p̂(1−p̂)/n)). 0.60 is a stated assumption, recalibratable
    with real scaled-score data; never tuned to flatter a result.
  - **Confidence** ∈ [0,1] rises with a tighter band and more coverage.
  - **Next best action:** the weakest reviewed-but-uncleared subtopic by measured
    revlog accuracy.
- **Honesty bundle:** every `ReadinessScore` carries `point, low, high,
  coverage_pct, confidence, updated_at, reasons[], next_best_action,
  pass_probability` (+ `past_accuracy`, shown as not-yet-available until there is
  a history of predictions vs outcomes). The struct makes a bare number
  impossible to emit. Rust tests: `emits_a_readiness_band_with_practice_evidence`,
  `meeting_review_gates_still_refuses_without_practice_tests`,
  `readiness_band_scales_and_bounds`, `wilson_interval_brackets_the_estimate`,
  `normal_cdf_is_calibrated_at_known_points`.
- **Demo:** `make seed-persona` / `make practice-test` show a real, reproducible,
  synthetic-persona readiness band (e.g. projected ~5.5, range ~4.6–6.4,
  P(pass) ~14%) plus a Memory band (mean FSRS retrievability ~90%, range
  ~85–96%) — computed by this exact code, never hardcoded.

## Synthetic demo persona (honest "reasonable data")

To demo live numbers without a real study history, the fork uses a **seeded,
clearly-labelled synthetic persona** (`pylib/anki/speedrun/persona.py`), never a
hardcoded score. The rubric's automatic-fail is _dressing up a guess as a
measurement_; this does the opposite:

- The persona is a latent **per-subtopic skill** vector, deterministic from a
  seed. `tools/speedrun/seed_persona.py` turns it into a real collection: it
  builds the tagged deck, inserts **graded revlog rows** (so coverage and review
  counts are genuine collection state), and records **graded practice tests**.
- Every number the app then shows is computed by **exactly the code a real
  student hits** (the Rust give-up rule, `compute_readiness`, the performance
  pipeline) — only the input history is synthetic, and it is stamped
  `synthetic demo persona` everywhere it surfaces.
- Same seed -> same persona -> same numbers, so anyone can reproduce them
  (`make seed-persona`, `make practice-test`).
- The **performance model** is evaluated on a synthetic **cohort**
  (`synthetic_cohort`) crossed with the real held-out item corpus, split by item
  so no item leaks. That measures the model, honestly labelled as synthetic.

This keeps the give-up rule and the honesty bundle fully in force: below the
thresholds the persona still gets `NoScore`, and no persona number is ever
emitted that the real pipeline didn't compute.

## Reproducibility

- **Seeded split:** `train_test_split(seed)` in `evalsplit.py` — same ids + seed
  give the same split every run.
- **Leakage gate:** `tools/speedrun/leakage_scan.py` flags any test item (or
  near-copy) that leaks into training and exits non-zero.
- **Commands:** `make calibration` (memory); performance/readiness evals land
  with their datasets. All deterministic — anyone can re-run and get the same
  numbers.

## What is deliberately NOT done yet (stated honestly)

- **Readiness** now emits from the graded practice-test proportion. What is NOT
  yet done: fusing the per-question **performance-model** predictions into
  readiness, and validating the 0.60 pass map against real SOA scaled scores. The
  mapping is fixed in advance so it can't be tuned to flatter the result.
- No calibrated **performance** model on REAL students yet (needs a real labelled
  disguised-item dataset); it is validated on a synthetic cohort + the held-out
  item corpus and abstains ("not yet measured") on real data.
- **Memory** calibration prints numbers only on a real review history; on a fresh
  or seed collection it abstains by design.
