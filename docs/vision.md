# Product vision — SOA Exam P study app (owner: Katie He)

This is the north star for the app. Not everything here is built yet; this file
records the intended design so we can build toward it deliberately. Where a piece
exists today, it is marked **[built]**; planned pieces are **[planned]**.

## The core idea: a mastery tree you climb

The home screen is a **three-layer topic tree** of the official SOA Exam P
syllabus, now rendered as an **importance-sized bubble concept map** (bubble size
= a topic's exam weight, colour = measured mastery):

```
                Exam P (root)
       /            |             \
  General       Univariate     Multivariate      <- the 3 units
  /  |  \         / | \            / | \
subtopics      subtopics        subtopics        <- syllabus outcomes
```

- The **root** branches into the **3 units** (General Probability, Univariate
  Random Variables, Multivariate Random Variables).
- Each unit branches into its **subtopics**, taken from the official
  2026-05 Exam P learning outcomes
  (https://www.soa.org/globalassets/assets/files/edu/2026/spring/syllabi/2026-05-exam-p-syllabus.pdf).
- The user **taps a node to open that deck** and study it.
- **Edges fill in with color as mastery grows.** An edge from a unit to a
  subtopic fills toward "done" as that subtopic clears its mastery gate; an edge
  from the root to a unit fills as the unit's subtopics clear. The tree is the
  progress bar. **[tree page: built as a first slice; deck-open on tap: planned]**

## The three-tier, mastery-gated flow (the spine)

Cards move up three piles as the student improves. This is Spiky POV 1 and the
required Rust engine change. **[mastery model + ordering: built in Rust; live
queue integration: built behind a default-off `speedrunMasteryScheduler` flag —
`build_queues` reorders new cards by tier when it is on]**

1. **Subtopic pile (Blocked)** — a small deck per subtopic, practised in
   isolation until its **mastery gate** clears (enough graded problems, high
   accuracy, strong FSRS retrievability).
2. **Unit pile (Within-unit)** — once a subtopic clears, its cards join a larger
   per-unit pile that **interleaves** the confusable sub-types within that unit.
3. **Overall pile (Cross-unit)** — once the whole unit is mastered (and, later,
   once _performance_ on exam-style questions is good enough), its cards join the
   overall deck that interleaves **across units** for spacing.

The gate thresholds live in `rslib/src/speedrun/mastery.rs` (a subtopic clears at

> = 10 graded problems, >= 80% accuracy, >= 90% mean retrievability). The
> `GetMasteryState` RPC already reports each subtopic's pool and each unit's
> mastery, which is what colors the tree.

## The three signals (never blended)

1. **Memory** — can the student recall the fact right now? (FSRS.) **[built]**
2. **Performance** — can they solve a _new, exam-style_ question that uses the
   fact? **[planned]**
3. **Readiness** — what would they score today, with a range and confidence?
   **[readiness give-up rule: built; calibrated number: planned]**

## Readiness from practice tests **[planned]**

Readiness should be driven primarily by **full practice tests**, not just review
counts:

- The student takes timed, exam-shaped practice tests (30 questions, mixed across
  units by the official section weights: General 23-30%, Univariate 44-50%,
  Multivariate 23-30%).
- Readiness = P(pass) estimated from practice-test scores over time, shown as a
  **range + confidence + projected 0-10 band**, with the honesty bundle.
- The give-up rule still holds: no readiness number until there is enough
  evidence (e.g. a minimum number of graded practice-test questions AND enough
  syllabus coverage). Practice-test items are **held out** from training so the
  estimate isn't contaminated (the leakage scan already exists).

## User-authored questions **[planned]**

- The student can add **their own questions**. By default these live in a
  **separate area**, not attached to the tree, so hand-entered cards never
  silently distort the syllabus coverage or the mastery gates.
- **Later:** an opt-in AI step parses a user's question and suggests which
  subtopic node it belongs to (with the source shown), so it can be filed into
  the tree. Every AI suggestion must trace to a named source and beat a simple
  keyword/vector baseline before it is shown (per the AI-traceability rules). AI
  is off by default and the app must still work with AI switched off.

## What exists today (so we build on it, not around it)

- Rust engine: `SpeedrunService` — `speedrun_ping`, `compute_readiness` (give-up
  rule as a Rust assertion), `get_mastery_state` (mastery gate + importance-
  weighted rollups + "what to study next"), `get_mastery_ordered_new_cards`, and
  `get_points_at_stake_order` (due cards by topic weight × student weakness).
  Two opt-in live-queue flags: `speedrunMasteryScheduler`, `speedrunPointsAtStake`.
- Topic map: `pylib/anki/speedrun/exam_p_topics.json` (3 units + subtopics,
  official section weights). Cards are tagged `unit::<u>`, `subtopic::<u>::<s>`,
  `difficulty::<d>`.
- Desktop pages: `readiness-dashboard` (three signals + honesty bundle) and
  `study-map` (the tree). Both call the Rust RPCs over the mediasrv bridge.
- Deck: `pylib/anki/speedrun/seed.py` builds a tagged starter deck spanning the
  whole syllabus; `tools/speedrun/build_exam_p_deck.py` exports an importable
  `.apkg`.

## Build order (suggested next steps)

1. ~~Tap a tree node -> open that subtopic's deck in the reviewer (pycmd bridge).~~
   **[done]** - a "Study this subtopic (blocked practice)" button on the study map
   opens that subtopic's deck via a webview->Python bridge, and a review-time
   banner shows the current card's tier (Blocked / Within-unit / Cross-unit).
2. ~~Live queue: use the tier order in the actual scheduler~~ **[done]** — the
   `speedrunMasteryScheduler` flag makes `build_queues` serve new cards in tier
   order (Blocked -> WithinUnit -> CrossUnit); default off.
3. Practice-test mode + readiness calibration from held-out practice scores.
   Memory (FSRS) calibration harness is built (`make calibration`,
   `docs/score-models.md`); the performance model + practice tests are next.
4. User-question area (separate), then the opt-in AI subtopic classifier.

Recent additions (built): per-topic **importance weights** (`exam_p_topics.json`),
an **importance-weighted mastery rollup** and a **"what to study next"** ranking
in `GetMasteryState`, an **importance-sized bubble concept map** with unit-level
detail, and the honest **calibration** layer above.
