# Brainlift: Speedrun (SOA Exam P), built on Anki

> A Brainlift is the thinking behind the build: the contrarian bets (Spiky POVs), why they are true, the evidence, and how they shaped the code.

## 1. The mission, in one line

Most study apps optimise **remembering**. A big exam rewards **doing**: solving a
new question under time, and knowing whether you're actually ready. So this fork
of Anki measures **three separate things: Memory, Performance, and Readiness,
and never blends them into one flattering number.**

## 2. Spiky POVs (the contrarian bets)

A Spiky POV is a belief that is _contrarian but defensibly true_. This project
has **two Spiky POVs**. **SPOV 1** (built this week) is the mastery-gated
interleaving scheduler; **SPOV 2** (a documented bonus, not built) is
chronotype-aware timing. The three-score split described below is a spec
requirement, not a third spiky POV: SPOV 1 is what defines what Performance must
measure.

### The consensus I'm betting against

The dominant Exam P prep website, Coaching Actuaries, gives students a single confident readiness number
through its ADAPT and its "Earned Level" score. That number is a black box: no evidence behind it, no range,
no honest "I cannot tell yet." This whole fork is the counter-bet: readiness is
only worth showing with its evidence, its uncertainty as a range, and a hard rule
that refuses to show anything when the data is not there. The honesty IS the
product, not a footnote on it.

### SPOV 1: "Interleaving beats blocking, but only _inside a unit_, and only _after_ you've mastered the pieces."

- **What most tools do:** either pure blocking (drill one topic to death) or a
  single global shuffle. Anki's default is neither topic-aware.
- **The bet:** the failure mode on Exam P is **discrimination**: students mix up
  _confusable siblings_ (binomial vs. Poisson vs. geometric; MGF vs. raw moment;
  "does this need conditioning?"). Interleaving helps you tell those apart, but
  only once you can execute each in isolation, and only when the confusable items
  are interleaved **with each other** (within a unit), not drowned in a global
  pool. Hence a **three-tier, mastery-gated** order: Blocked → Within-unit
  interleave → Cross-unit interleave, with a gate at each level.
- **How it shows up in the build:** the real Rust change
  (`rslib/src/speedrun/mastery.rs`, the `build_queues` reorder), the study-map UI,
  and, critically, **it's the exact thing the ablation removes** so the claim is
  falsifiable (`make ablation`, `docs/study-feature-ablation.md`).
- **Why it's defensibly true:** interleaved math practice beats blocked at equal
  reps (Rohrer & Taylor 2007; Rohrer, Dedrick & Stershic 2015), and the _reason_
  is discrimination: interleaving trains you to tell confusable categories apart
  (Birnbaum et al. 2013; Kang & Pashler 2012). That is exactly the Exam P failure
  mode: not "I forgot the Poisson pmf" but "I used Poisson when it was geometric."
- A single
  global shuffle also mixes in general-probability and multivariate cards, which
  are easy to tell apart, so it wastes discrimination reps on non-confusable
  pairs; keeping the mix _within a unit_ puts binomial next to Poisson next to
  geometric, which is where students actually slip.

### Why Performance is its own score (the three-score rationale, not a spiky POV)

- **What most tools do:** show one "mastery %" that's really just recall, and
  imply it means readiness.
- **The bet:** recall of a cue and the ability to solve a _reworded_ problem are
  **different quantities**, and a serious tool must _measure the gap_ rather than
  hide it. If your Performance score just tracks Memory, you built nothing.
- **How it shows up in the build:** three separate signals with separate models;
  the **paraphrase test** (`make paraphrase`) that measures the recall-vs-reworded
  gap (**+41 pts**, showing they genuinely diverge) with a **copycat control** that
  proves the test can catch a Performance score that's secretly Memory.
- **Why it's defensibly true:** transfer is specific and hard (Barnett & Ceci
  2002), and fluency breeds an _illusion of competence_: recognising a cue feels
  like knowing but doesn't predict solving a reworded problem (Koriat & Bjork
  2005); retrieval on _new_ questions is what tracks learning (Roediger & Karpicke
  2006). So Performance must be measured separately and allowed to diverge from
  Memory, which the paraphrase test shows it does (+41 pts).
- I could recite the CLT statement cold, then blanked
  when it was buried inside an insurance-payout problem. The chronotype/timing
  angle is its own bet, **SPOV 2 (bonus, not built)**, covered in the next
  subsection.

### SPOV 2 (bonus, documented not built): timing should follow chronotype, not the clock

- **The bet:** the best time to do effortful, timed practice is a person's own
  peak-alertness window, which depends on chronotype and sleep, not a fixed hour;
  first-time encoding tends to favor the afternoon; transfer practice has its own
  best window that must be learned per user. A scheduler could choose not just
  _what_ to study but _when_.
- **Why it's parked:** the rubric wants exactly one ablated study feature
  (SPOV 1), so this stays in the spec's feature-ideas list and is deliberately
  not built this project. 

## 3. Key insights / decisions (why the build looks like it does)

- **Honesty is a type, not a vibe.** The give-up rule is a Rust `oneof {NoScore,
  ReadinessScore}`: a bare readiness number _cannot_ be emitted below threshold
  (≥200 graded reviews AND ≥50% weighted coverage AND ≥30 graded practice-test
  questions for the readiness band). Honesty enforced by the compiler beats
  honesty enforced by good intentions.
- **"Reasonable data" without lying = a labelled synthetic persona.** To demo live
  numbers with no real study history, a seeded, clearly-labelled persona feeds the
  _real_ pipeline; the app computes every number the way a real student would hit
  it. The automatic-fail is dressing a guess as a measurement; a labelled,
  reproducible fixture is the opposite.
- **Fair tests must be able to fail.** Both the ablation and the paraphrase test
  ship with a **null/control** (effect=0 → builds identical; copycat → gap→0), so
  a positive result means something. "It made no difference" is a real, reportable
  result.
- **The engine change had to be in Rust.** A JS/Swift reimplementation caps the
  grade and, more importantly, wouldn't ship the same behaviour to the phone.
  One compiled engine, two platforms. (`docs/rust-change.md`.)
- **AI is a helper, never a scorer.** AI is off by default; all three signals
  compute without it; every AI output is source-traced, quarantined until human
  approval, and gated by a pre-registered eval vs a simpler baseline.

## 4. What the evidence says (measured, reproducible)

- Study feature (ablation): equal study time, null at effect=0, direction holds
  otherwise; within-unit tier isolated. **[caveat]** synthetic cohort: real
  effect size needs real study logs.
- Paraphrase: recall 73% vs reworded 32%, +41-pt gap; copycat control ~0.
- AI vs baseline: classifier +25 pts; generation 92% vs 24% correct, both PASS.
- Speed: next-card p95 ~0.05 ms on 50k; crash test 0 corruptions; sync 20/20.

## 5. Sources & prior art

The real lineage of the ideas in the code, grouped by where each shows up.

**Actuarial prep and domain (people and tools I follow, from the BrainLift)**

- Coaching Actuaries / Dave Kester: the market-leading Exam P prep (ADAPT plus
  the "Earned Level" readiness number). The product inspiration and the black-box
  readiness critique this build sets out to beat.
- The Infinite Actuary: the shape of an Exam P curriculum and study path.
- Mancinelli Math Lab: explanation style for working probability problems.
- Sheldon Ross (_A First Course in Probability_) and Hassett, Stewart and
  Milovanovic (_Probability for Risk Management_): the standard texts. I ground
  my own concept explanations in these rather than copying any prep company's
  wording.

**Interleaving & discrimination-contrast (SPOV 1, the within-unit tier)**

- Rohrer & Taylor (2007), _The shuffling of mathematics problems improves
  learning_: interleaved (vs blocked) practice raised later math-test scores;
  the closest prior art, since Exam P is a math test.
- Rohrer, Dedrick & Stershic (2015), _Interleaved practice improves mathematics
  learning_: replicated on a delayed test, large effect.
- Birnbaum, Kornell, E. Bjork & R. Bjork (2013), _Why interleaving enhances
  inductive learning: the roles of discrimination and retrieval_. This is the
  mechanism I'm betting on: interleaving trains you to tell confusable
  categories apart.
- Kang & Pashler (2012), _…spacing is advantageous when it promotes discriminative
  contrast_: the benefit is about discrimination, not spacing alone.

**Desirable difficulties & spacing (the mastery gate + the cross-unit tier)**

- R. Bjork & E. Bjork (2011), _Making things hard on yourself, but in a good way_:
  the "desirable difficulties" frame behind gating before you interleave.
- Cepeda, Pashler, Vul, Wixted & Rohrer (2006), _Distributed practice in verbal
  recall tasks: a review and quantitative synthesis_ (the spacing meta-analysis;
  cross-unit interleaving = spacing).

**Transfer & "familiarity ≠ competence" (the three-score rationale)**

- Barnett & Ceci (2002), _When and where do we apply what we learn? A taxonomy for
  far transfer_: transfer is specific and hard; recall ≠ application.
- Koriat & Bjork (2005), _Illusions of competence in monitoring one's knowledge_
  describes the fluency illusion: feeling you know it is not knowing it (what the
  paraphrase test catches).
- Roediger & Karpicke (2006), _Test-enhanced learning_: retrieval on new
  questions beats restudy; justifies scoring Performance on unseen items.
- Dunlosky, Rawson, Marsh, Nathan & Willingham (2013), _Improving students'
  learning with effective learning techniques_: ranks practice testing +
  distributed practice as highest-utility; a good umbrella citation.

**Timing & chronotype (the bonus SPOV 2, documented not built)**

- Wieth and Zacks, and chronotype/circadian-rhythm researchers (SPOV 2, the
  bonus timing feature).

**Spaced repetition / the memory model I build _on_, not reinvent**

- FSRS (Free Spaced Repetition Scheduler; open-source, now Anki's default), on the
  DSR (Difficulty-Stability-Retrievability) memory model, my Memory signal. I
  change the scheduler _order_, not FSRS itself.
- SuperMemo / Woźniak's SM-2 lineage: the origin of the spacing-algorithm family.

**Calibration & honest uncertainty (the scoring-honesty stance)**

- Brier (1950), _Verification of forecasts expressed in terms of probability_:
  the Brier score in `calibration.py`.
- Gneiting & Raftery (2007), _Strictly proper scoring rules, prediction, and
  estimation_: why a proper scoring rule forces an honest probability, not a
  flattering one.
- Wilson (1927), _Probable inference, the law of succession…_: the Wilson score
  interval behind the readiness band's range.

**The exam itself**

- SOA Exam P syllabus (2026-05 learning outcomes) + official sample questions
  provide the coverage map (`pylib/anki/speedrun/exam_p_topics.json`) and the
  held-out eval corpus.

## 6. Open questions / what's next

- Fuse the per-question **performance model** into readiness (today readiness uses
  the graded practice-test proportion).
- Validate the 0.60 pass-map and the interleaving effect against **real students**.
- The on-device phone↔desktop sync **recording** (code path already tested).
- SPOV 2's chronotype-timing feature (bonus, not this project).

## 7. Honesty stance (the line I won't cross)

No fabricated readiness number, no test item in training, no AI claim without a
named source. Where the data doesn't exist yet, the app says so: "we calibrated
memory but can't yet prove the projected score" is a better answer than a polished
number with nothing behind it.
