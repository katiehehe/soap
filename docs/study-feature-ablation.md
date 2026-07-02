# Study-feature ablation — pre-registration (Sunday)

The rubric requires our one study feature to be tested by turning it **off/on**
against plain Anki, with a **pre-registered hypothesis** and equal study time.
This file registers the plan **before** any numbers are collected, so the result
is honest. (Written Wednesday; the run happens Sunday.)

## The feature under test

The **within-unit interleaving tier** of the three-tier mastery-gated scheduler
(Spiky POV 1). Full scheduler: Blocked (practise a subtopic alone) → Within-unit
(interleave confusable sub-types in a unit) → Cross-unit (interleave across
units). The ablation **removes the middle tier**: a cleared subtopic goes
straight into a single global mixed pool.

## Three builds (identical except the scheduler)

1. **Full** — the complete three-tier scheduler (`order_new_cards` with all three
   pools).
2. **Ablated** — within-unit interleaving removed: Blocked → (global mixed). This
   is the same engine with the middle tier collapsed.
3. **Plain Anki** — stock new-card order (no topic-aware ordering).

Implementation note: builds 1 and 2 differ only by a flag on the ordering
function; keep the flag out of the demo path (default = Full). Build 3 = upstream
ordering.

## Pre-registered hypothesis

> Interleaving confusable sub-types _within a unit_ (Full) produces higher
> performance on **new, exam-style** questions than either the ablated build or
> plain Anki, at equal study time — because discrimination between similar
> distributions/rules is the main failure mode on Exam P.

Direction: Full > Ablated ≥ Plain on the primary metric. We report the result
**even if null or reversed.**

## Protocol

- **Participants/sim:** equal study time per build (fixed minutes or fixed number
  of reviews — decide once, apply to all three).
- **Primary metric:** accuracy on a **held-out** set of exam-style (performance)
  questions not seen during study. Train/test split uses the existing seeded
  splitter (`pylib/anki/speedrun/evalsplit.py`); the leakage scan must be clean.
- **Secondary:** time-to-first-mastery per unit; retention at a fixed delay.
- **Seed:** fixed and recorded so anyone can re-run and get the same numbers.
- **Analysis:** report per-build metric with a simple interval; state whether the
  pre-registered direction held. No metric changes after seeing data.

## What "setup today" covers

- This pre-registration (done).
- The ordering function already exists and is unit-tested; the ablation is a
  one-flag variant to add Sunday (kept off the demo path).
- The held-out splitter + leakage scan already exist and are re-runnable.
