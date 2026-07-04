# Brainlift — Speedrun (SOA Exam P), built on Anki

> A Brainlift is the thinking behind the build: the contrarian bets (Spiky POVs),
> why they're true, the evidence, and how they shaped the code. It's meant to be
> sentences only the owner (Katie He) can write; the sources, reasoning, and
> evidence around them are already filled in.

## 1. The mission, in one line

Most study apps optimise **remembering**. A big exam rewards **doing**: solving a
new question under time, and knowing whether you're actually ready. So this fork
of Anki measures **three separate things — Memory, Performance, Readiness — and
never blends them into one flattering number.**

## 2. Spiky POVs (the contrarian bets)

A Spiky POV is a belief that is _contrarian but defensibly true_. This project
has **two**; only SPOV 1 is built this week (SPOV 2 is a documented bonus).

### SPOV 1 — "Interleaving beats blocking, but only _inside a unit_, and only _after_ you've mastered the pieces."

- **What most tools do:** either pure blocking (drill one topic to death) or a
  single global shuffle. Anki's default is neither topic-aware.
- **The bet:** the failure mode on Exam P is **discrimination** — students mix up
  _confusable siblings_ (binomial vs. Poisson vs. geometric; MGF vs. raw moment;
  "does this need conditioning?"). Interleaving helps you tell those apart — but
  only once you can execute each in isolation, and only when the confusable items
  are interleaved **with each other** (within a unit), not drowned in a global
  pool. Hence a **three-tier, mastery-gated** order: Blocked → Within-unit
  interleave → Cross-unit interleave, with a gate at each level.
- **How it shows up in the build:** the real Rust change
  (`rslib/src/speedrun/mastery.rs`, the `build_queues` reorder), the study-map UI,
  and — critically — **it's the exact thing the ablation removes** so the claim is
  falsifiable (`make ablation`, `docs/study-feature-ablation.md`).
- **Why it's defensibly true:** interleaved math practice beats blocked at equal
  reps (Rohrer & Taylor 2007; Rohrer, Dedrick & Stershic 2015), and the _reason_
  is discrimination — interleaving trains you to tell confusable categories apart
  (Birnbaum et al. 2013; Kang & Pashler 2012). That is exactly the Exam P failure
  mode: not "I forgot the Poisson pmf" but "I used Poisson when it was geometric."
- A single
  global shuffle also mixes in general-probability and multivariate cards, which
  are easy to tell apart, so it wastes discrimination reps on non-confusable
  pairs; keeping the mix _within a unit_ puts binomial next to Poisson next to
  geometric — where students actually slip."

### SPOV 2 — "Familiarity is not transfer; a memory score that predicts exam performance is lying."

- **What most tools do:** show one "mastery %" that's really just recall, and
  imply it means readiness.
- **The bet:** recall of a cue and the ability to solve a _reworded_ problem are
  **different quantities**, and a serious tool must _measure the gap_ rather than
  hide it. If your Performance score just tracks Memory, you built nothing.
- **How it shows up in the build:** three separate signals with separate models;
  the **paraphrase test** (`make paraphrase`) that measures the recall-vs-reworded
  gap (**+41 pts** — they genuinely diverge) with a **copycat control** that
  proves the test can catch a Performance score that's secretly Memory.
- **Why it's defensibly true:** transfer is specific and hard (Barnett & Ceci
  2002), and fluency breeds an _illusion of competence_ — recognising a cue feels
  like knowing but doesn't predict solving a reworded problem (Koriat & Bjork
  2005); retrieval on _new_ questions is what tracks learning (Roediger & Karpicke
  2006). So Performance must be measured separately and allowed to diverge from
  Memory — which the paraphrase test shows it does (+41 pts).
- I could recite the CLT statement cold, then blanked
  when it was buried inside an insurance-payout problem. The chronotype/timing
  angle is the _bonus_ half of SPOV 2 and is intentionally **not** built this week.

## 3. Key insights / decisions (why the build looks like it does)

- **Honesty is a type, not a vibe.** The give-up rule is a Rust `oneof {NoScore,
  ReadinessScore}` — a bare readiness number _cannot_ be emitted below threshold
  (≥200 graded reviews AND ≥50% weighted coverage). Honesty enforced by the
  compiler beats honesty enforced by good intentions.
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
  grade and — more importantly — wouldn't ship the same behaviour to the phone.
  One compiled engine, two platforms. (`docs/rust-change.md`.)
- **AI is a helper, never a scorer.** AI is off by default; all three signals
  compute without it; every AI output is source-traced, quarantined until human
  approval, and gated by a pre-registered eval vs a simpler baseline.

## 4. What the evidence says (measured, reproducible)

- Study feature (ablation): equal study time, null at effect=0, direction holds
  otherwise; within-unit tier isolated. **[caveat]** synthetic cohort — real
  effect size needs real study logs.
- Paraphrase: recall 73% vs reworded 32%, +41-pt gap; copycat control ~0.
- AI vs baseline: classifier +25 pts; generation 92% vs 24% correct — both PASS.
- Speed: next-card p95 ~0.05 ms on 50k; crash test 0 corruptions; sync 20/20.

## 5. Sources & prior art

The real lineage of the ideas in the code, grouped by where each shows up.
**[Katie: skim these, keep the ones you actually engaged with — 4–5 you've read
beats 15 you haven't — and add anyone I missed: a talk, a tutor, an SOA/actuarial
forum thread, an Anki/FSRS dev discussion.]**

**Interleaving & discrimination-contrast (SPOV 1 — the within-unit tier)**

- Rohrer & Taylor (2007), _The shuffling of mathematics problems improves
  learning_ — interleaved (vs blocked) practice raised later math-test scores;
  the closest prior art, since Exam P is a math test.
- Rohrer, Dedrick & Stershic (2015), _Interleaved practice improves mathematics
  learning_ — replicated on a delayed test, large effect.
- Birnbaum, Kornell, E. Bjork & R. Bjork (2013), _Why interleaving enhances
  inductive learning: the roles of discrimination and retrieval_ — the mechanism
  I'm betting on: interleaving trains you to tell confusable categories apart.
- Kang & Pashler (2012), _…spacing is advantageous when it promotes discriminative
  contrast_ — the benefit is about discrimination, not spacing alone.

**Desirable difficulties & spacing (the mastery gate + the cross-unit tier)**

- R. Bjork & E. Bjork (2011), _Making things hard on yourself, but in a good way_
  — the "desirable difficulties" frame behind gating before you interleave.
- Cepeda, Pashler, Vul, Wixted & Rohrer (2006), _Distributed practice in verbal
  recall tasks: a review and quantitative synthesis_ — the spacing meta-analysis
  (cross-unit interleaving = spacing).

**Transfer & "familiarity ≠ competence" (SPOV 2)**

- Barnett & Ceci (2002), _When and where do we apply what we learn? A taxonomy for
  far transfer_ — transfer is specific and hard; recall ≠ application.
- Koriat & Bjork (2005), _Illusions of competence in monitoring one's knowledge_ —
  the fluency illusion: feeling you know it is not knowing it (what the paraphrase
  test catches).
- Roediger & Karpicke (2006), _Test-enhanced learning_ — retrieval on new
  questions beats restudy; justifies scoring Performance on unseen items.
- Dunlosky, Rawson, Marsh, Nathan & Willingham (2013), _Improving students'
  learning with effective learning techniques_ — ranks practice testing +
  distributed practice as highest-utility; a good umbrella citation.

**Spaced repetition / the memory model I build _on_, not reinvent**

- FSRS (Free Spaced Repetition Scheduler; open-source, now Anki's default), on the
  DSR (Difficulty–Stability–Retrievability) memory model — my Memory signal. I
  change the scheduler _order_, not FSRS itself.
- SuperMemo / Woźniak's SM-2 lineage — the origin of the spacing-algorithm family.

**Calibration & honest uncertainty (the scoring-honesty stance)**

- Brier (1950), _Verification of forecasts expressed in terms of probability_ —
  the Brier score in `calibration.py`.
- Gneiting & Raftery (2007), _Strictly proper scoring rules, prediction, and
  estimation_ — why a proper scoring rule forces an honest probability, not a
  flattering one.
- Wilson (1927), _Probable inference, the law of succession…_ — the Wilson score
  interval behind the readiness band's range.

**The exam itself**

- SOA Exam P syllabus (2026-05 learning outcomes) + official sample questions —
  the coverage map (`pylib/anki/speedrun/exam_p_topics.json`) and the held-out
  eval corpus.

## 6. Open questions / what's next

- Fuse the per-question **performance model** into readiness (today readiness uses
  the graded practice-test proportion).
- Validate the 0.60 pass-map and the interleaving effect against **real students**.
- The on-device phone↔desktop sync **recording** (code path already tested).
- SPOV 2's chronotype-timing feature (bonus, not this project).

## 7. Honesty stance (the line I won't cross)

No fabricated readiness number, no test item in training, no AI claim without a
named source. Where the data doesn't exist yet, the app says so — "we calibrated
memory but can't yet prove the projected score" is a better answer than a polished
number with nothing behind it.
