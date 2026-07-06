# Study-feature ablation: pre-registration (Sunday)

The rubric requires our one study feature to be tested by turning it **off/on**
against plain Anki, with a **pre-registered hypothesis** and equal study time.
This file registers the plan **before** any numbers are collected, so the result
is honest. (Written Wednesday; the run happens Sunday.)

## The feature under test

The **within-unit interleaving tier** of the three-tier mastery-gated scheduler
(Spiky POV 1). Full scheduler: Blocked (practice a subtopic alone) → Within-unit
(interleave confusable sub-types in a unit) → Cross-unit (interleave across
units). The ablation **removes the middle tier**: a cleared subtopic goes
straight into a single global mixed pool.

## Three builds (identical except the scheduler)

1. **Full**: the complete three-tier scheduler (`order_new_cards` with all three
   pools).
2. **Ablated** removes within-unit interleaving: Blocked → (global mixed). This
   is the same engine with the middle tier collapsed.
3. **Plain Anki**: stock new-card order (no topic-aware ordering).

Implementation note: builds 1 and 2 differ only by a single flag, now
implemented. All three builds run on the same engine, selected by two config
keys (both default off, so the demo path is Full-off = plain Anki):

- **Build 1 (Full):** `speedrunMasteryScheduler = true`, `speedrunAblateWithinUnit = false`.
- **Build 2 (Ablated):** `speedrunMasteryScheduler = true`, `speedrunAblateWithinUnit = true`,
  where `order_new_cards(..., ablate_within_unit=true)` collapses every cleared
  subtopic into one global mixed pool, removing the within-unit tier.
- **Build 3 (Plain Anki):** `speedrunMasteryScheduler = false` (upstream ordering).

## Pre-registered hypothesis

> Interleaving confusable sub-types _within a unit_ (Full) produces higher
> performance on **new, exam-style** questions than either the ablated build or
> plain Anki, at equal study time, because discrimination between similar
> distributions/rules is the main failure mode on Exam P.

Direction: Full > Ablated ≥ Plain on the primary metric. We report the result
**even if null or reversed.**

## Protocol

- **Participants/sim:** equal study time per build (fixed minutes or fixed number
  of reviews; decide once, apply to all three).
- **Primary metric:** accuracy on a **held-out** set of exam-style (performance)
  questions not seen during study. Train/test split uses the existing seeded
  splitter (`pylib/anki/speedrun/evalsplit.py`); the leakage scan must be clean.
- **Secondary:** time-to-first-mastery per unit; retention at a fixed delay.
- **Seed:** fixed and recorded so anyone can re-run and get the same numbers.
- **Analysis:** report per-build metric with a simple interval; state whether the
  pre-registered direction held. No metric changes after seeing data.

## What "setup today" covers

- This pre-registration (done).
- The ordering function exists and is unit-tested, and the ablation is now
  implemented: `order_new_cards` takes an `ablate_within_unit` flag, driven by the
  `speedrunAblateWithinUnit` config key (default off, kept off the demo path). The
  Full-vs-Ablated ordering difference is covered by Rust tests
  (`full_scheduler_groups_within_unit_cleared_cards_by_unit`,
  `ablated_collapses_within_and_cross_into_one_mixed_pool`).
- The held-out splitter + leakage scan already exist and are re-runnable.

## The run (`make ablation`)

Harness: `pylib/anki/speedrun/ablation.py`; runner
`tools/speedrun/evals/ablation_eval.py`; tests
`pylib/tests/test_speedrun_ablation.py`.

Because there is no real cohort in a week, this is a **seeded simulation on the
labelled synthetic persona cohort**, engineered so it cannot smuggle in the
conclusion:

- **Equal study time**: every build studies the identical multiset of reps
  (asserted), so each subtopic's proficiency is the same in all three; only the
  interleaving ORDER differs.
- The **only** build-dependent term is a discrimination boost on confusable
  within-unit questions, with one explicit knob `disc_gain` (in logits), swept
  **from zero**. At `disc_gain = 0` the builds must coincide (the null).
- Held-out, leakage-clean metric: accuracy on the held-out exam-style corpus
  (`soa_sample`); a leakage scan confirms the eval questions are not near-copies
  of the study cards.

### Results (synthetic cohort, 60 students, seed 0; official SOA corpus locally)

Within-unit interleaving exposure (the mechanism's input): Full 0.715 ·
Ablated 0.636 · **Plain 0.106**.

| disc_gain      | Full  | Ablated | Plain |
| -------------- | ----- | ------- | ----- |
| **0.0 (null)** | 0.486 | 0.486   | 0.486 |
| 0.5            | 0.568 | 0.559   | 0.499 |
| 1.0            | 0.647 | 0.630   | 0.511 |
| 1.5            | 0.719 | 0.696   | 0.523 |
| 2.0            | 0.782 | 0.755   | 0.535 |

- **Null check passes**: at `disc_gain = 0` the three builds are identical
  (spread 0.0000), so the harness has no built-in bias.
- For any assumed positive effect the **pre-registered direction holds**:
  Full ≥ Ablated ≥ Plain. The **within-unit tier** (Full - Ablated) contributes
  +0.017 at `disc_gain = 1.0`, growing with the assumed effect; the bulk of the
  gap over Plain comes from mastery-gated interleaving generally.

### Honest reading

This run does **not** prove the feature works, and it cannot: with no assumed
mechanism the builds are identical. What it delivers is a **fair, reproducible
experiment**: equal study time, held-out leakage-clean questions, the ablation
isolating the within-unit tier (Full vs Ablated), a null that passes, and the
effect size a real study-log run would need to detect. The real per-student
effect requires real study logs; the machine to measure it is done and seeded.
Numbers above use the owner's local official SOA corpus (gitignored); the
committed fallback corpus reproduces the same structure (null at 0, ordering
preserved) with slightly different absolute values.
