# FSRS reference (Speedrun exam-readiness app)

Purpose: ground-truth notes on the algorithm this project's **memory model** is built
on, so the agent does not reconstruct stale FSRS-4 formulas from training data. Read
this before touching scheduling code, the memory model, or the calibration eval.

Related: [rust-change.md](rust-change.md) (the scheduler change), `PRD.md` section 9
(the three models), `SPEC_CHECKLIST.md` section 7 (score-model steps).

> Verify the version against your actual fork (see "Versions" below). If Anki's bundled
> FSRS version differs from what's here, update this file, because formulas change between versions.

## One-paragraph version

FSRS ("Free Spaced Repetition Scheduler") is Anki's default scheduler. It models each
card with three numbers (the DSR model): Difficulty, Stability, Retrievability.
Retrievability is the probability of recalling the card right now; it decays along a
forgetting curve whose speed is set by Stability. FSRS schedules the next review for
whenever Retrievability is predicted to fall to a target (default 90%). On each review,
Stability and Difficulty update based on the grade and the card's state at review time.

## The three variables

- **Retrievability (R)**: probability of correct recall right now, in [0, 1]. Changes
  every day. This is the number the memory model outputs and the number the calibration
  eval checks.
- **Stability (S)**: memory strength in days. Defined precisely as the number of days
  for R to fall from 100% to 90%. So `S = 30` means R hits 90% exactly 30 days after the
  last review. Changes only when the card is reviewed.
- **Difficulty (D)**: how hard the card is, roughly 1-10. A heuristic with no clean
  definition; mean-reverts over time so an early fumble does not poison the card forever.
  Changes only on review.

Each card carries its own D, S, R.

## Forgetting curve and interval

R as a function of days-since-review `t` and stability `S` (FSRS-5 form):

    R(t) = (1 + (19/81) * (t / S)) ^ (-0.5)

At `t = 0`, R = 1. At `t = S`, R = 0.9 (forced by the definition of S). FSRS-6 keeps this
power-curve shape but adds a trainable decay parameter (`w20`, range 0.1-0.8, usually
< 0.2) so the tail can be personalized per user.

Scheduling: pick a desired retention `DR` (default 0.90); the next interval is the `t`
where predicted R = DR. When `DR = 0.90`, the interval ≈ S (before Anki's fuzz).

## Grades and how state updates

- **Again (1)** = lapse. Card → relearning, S drops sharply, D rises.
- **Hard (2)** = pass. S barely moves (can stay flat), D rises slightly.
- **Good (3)** = pass. S rises, D roughly flat.
- **Easy (4)** = pass. S rises a lot, D falls.

Only **Again** is a failure; Hard/Good/Easy all count as success, so on a successful
review stability never decreases.

Key mechanism (what SM-2 missed): how much S grows on a successful review depends on
_when_ you review. Reviewing while R is still high barely strengthens the memory;
reviewing when R has dropped low strengthens it much more. That is the spacing effect,
and it is why interval length matters, not just pass/fail.

## Versions (verified against this fork)

- **This fork: v25.09.99.** The bundled `fsrs` Rust crate is **5.2.0** (the crate's
  semver in `Cargo.lock`, which is _not_ the algorithm generation).
- **Algorithm: FSRS-6** (in Anki since **v25.07**; our version is newer). FSRS-6 adds a
  per-card trainable **decay** parameter (`w20`); this fork carries it as `card.decay`
  with `fsrs::FSRS5_DEFAULT_n` as the fallback (see `rslib/src/stats/card.rs`,
  `rslib/src/browser_table.rs`, `rslib/src/stats/graphs/retrievability.rs`).
  **21 trainable parameters** (`w0`-`w20`).
- FSRS-5 had 19 parameters and no personalizable decay.
- FSRS-4 / 4.5 / v3 used different forgetting curves. If an online source's formula does
  not match, check which version it describes before copying.
- Trained by Jarrett Ye on ~700M reviews from ~20k users; ~20-30% fewer reviews than SM-2
  at equal retention.
- Anki fits the 21 weights to a user's own review history via the optimizer (needs
  ~1,000+ reviews to personalize).

## What this means for THIS project (important)

- **FSRS _is_ the memory model.** Step 1 of the score bridge ("show the memory model is
  calibrated") is mostly inherited, so the job is to _prove_ it, not rebuild it. Bin
  held-out reviews by predicted R, plot predicted vs. actual, report a Brier score.
- **R is not performance.** FSRS's R is the recall probability for _this card with its
  familiar cue_. It says nothing about whether the student can recognize the topic in a
  disguised SOA problem or set up the procedure. That gap is exactly what the paraphrase
  test measures and what the performance model must capture. Do not let R stand in for
  performance.
- **Same-day memory is weak.** FSRS has only a crude heuristic for same-day / short-term
  memory, with no real short-term model. Trust its predictions least for cramming behavior
  inside a single session.
- **R is already a probability**, so it drops straight into calibration and give-up-rule
  logic without transformation. (The give-up rule itself lives in Rust: see
  `rslib/src/speedrun/service.rs` and [rust-change.md](rust-change.md).)

## Sources

- Anki FAQ (scheduler / FSRS): https://faqs.ankiweb.net/what-spaced-repetition-algorithm
- Expertium, "A technical explanation of FSRS" (FSRS-6): https://expertium.github.io/Algorithm.html
- open-spaced-repetition / fsrs4anki fundamentals: https://github.com/open-spaced-repetition/fsrs4anki
- py-fsrs (parameter count and defaults): https://pypi.org/project/fsrs/
