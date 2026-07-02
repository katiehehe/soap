# Demo script & feature reference — SOA Exam P Speedrun

Everything you need to demo the app correctly: what it is, what each feature
does, and a step-by-step walkthrough. Built for the **Wednesday core** (no AI
yet). Keep the demo to the reliable desktop flow; the phone is the "same engine
on mobile" beat.

## What the app is (say this first)

A desktop + mobile study app **forked from Anki** for **one exam: SOA Exam P
(Probability)**. It is not a generic flashcard app — it answers three _different_
questions and never blends them:

1. **Memory** — can you recall this fact right now? (Anki's FSRS.)
2. **Performance** — can you solve a _new, exam-style_ question that uses it?
3. **Readiness** — what would you score today, and how sure are we?

The engine change lives in **Anki's Rust core**, not a script on top — that's the
key requirement.

## The exam (state the real scale so nothing looks invented)

SOA Exam P: computer-based, 3 hours, 30 multiple-choice (A–E), 5 unscored pilot
questions. Scored 0–10 (0–5 fail, 6–10 pass). Section weights (May 2026):
**General Probability 23–30% · Univariate Random Variables 44–50% · Multivariate
Random Variables 23–30%.** Historical pass rate ~43%.

## Features (what each does · why it matters · where to see it)

1. **Real Rust engine change** — a new `SpeedrunService` in the `anki` crate
   (`compute_readiness`, `get_mastery_state`, `get_mastery_ordered_new_cards`),
   wired proto → Rust → Python → web. _Why:_ a JS/Swift reimplementation would
   cap the grade; this is the actual engine. _See:_ `rslib/src/speedrun/`,
   `./ninja check:rust_test`.

2. **Three separate scores, never blended** — Memory / Performance / Readiness
   are shown side by side, each with its own status. _See:_ Tools → Exam
   readiness (Speedrun).

3. **The honesty rule + give-up rule** — no readiness number is shown until
   there are **≥ 200 graded reviews AND ≥ 50% weighted syllabus coverage**. This
   is a **Rust assertion** (the return type is a `oneof`, so a bare number
   literally can't be emitted below threshold), with a matching test. The
   dashboard shows the evidence, what's missing, and the single best next action.
   _See:_ the "Not enough data yet" card + honesty bundle.

4. **Three-tier, mastery-gated scheduler** (the spine / Spiky POV 1) — each
   subtopic is scored from real review data (revlog accuracy + FSRS
   retrievability). A subtopic clears its **gate** (≥10 problems, ≥80% accuracy,
   ≥90% retrievability) → moves from **Blocked** (practise alone) to
   **Within-unit** (interleave in the unit) to **Cross-unit** (unit mastered,
   interleave across units). _See:_ `rslib/src/speedrun/mastery.rs`; the study
   map colors come from this.

5. **Study map (concept map)** — Exam P at the centre, the 3 units on an
   equilateral triangle, subtopics radiating out. **Each link fills along its
   length as you clear the gate** (grey → amber → green). Tap a subtopic for its
   mastery detail. _See:_ Tools → Study map (Speedrun).

6. **Readiness dashboard** — the three signals, the give-up card, and the full
   honesty bundle (point, range, coverage, confidence, reviews, reasons, next
   action). _See:_ Tools → Exam readiness (Speedrun).

7. **Syllabus-faithful taxonomy + tagged deck** — 3 units, 19 subtopics taken
   from the official 2026-05 learning outcomes; a 42-card starter deck (recall +
   applied) tagged by unit / subtopic / difficulty. _See:_
   `pylib/anki/speedrun/exam_p_topics.json`, `out/SOA-Exam-P.apkg`.

8. **Weighted coverage** — coverage is weighted by the official section weights,
   so skipping a high-weight unit can't read as "covered." _See:_ the coverage
   metric on the dashboard.

9. **Shared engine on the phone** — the AnkiDroid APK is built from _our_ Rust
   engine (`librsdroid.so`), installs and runs on the emulator. Desktop and phone
   run the same backend. _See:_ `docs/android-build.md`; the emulator.

10. **Reproducibility & reliability** — seeded train/test split, a leakage scan
    (verbatim + near-copy), a one-command benchmark (`make bench`, p50/p95/worst
    on a 50k deck), and a crash test (`make crash-test`, 20× SIGKILL, zero
    corruption). _See:_ `tools/speedrun/`, `pylib/anki/speedrun/evalsplit.py`.

## Demo walkthrough (≈ 4 minutes)

Do it in this order. The desktop is rock-solid; save the phone for last.

**0. Setup (before the demo)**

```bash
cd ~/dev/soap && ./run
```

In the app: **File → Import** → choose `out/SOA-Exam-P.apkg` (imports the tagged
"SOA Exam P" deck; safe, non-destructive).

**1. The real engine change + everything passes (~30s)**

```bash
./ninja check          # all green
./ninja check:rust_test  # the speedrun engine tests
```

Say: _"I changed Anki's Rust engine — a new SpeedrunService, not a wrapper."_

**2. Readiness dashboard: three signals + the give-up rule (~90s)**

Tools → **Exam readiness (Speedrun)**. Point out: three separate signals;
**Syllabus coverage jumps to 100%** after import (coverage metric working); but
**Graded reviews 0/200** keeps it honestly at "Not enough data yet." Say: _"It
refuses to show a score until it has the evidence — enforced in Rust."_

**3. Study map: the mastery concept map (~60s)**

Tools → **Study map (Speedrun)**. Show Exam P at the centre with the 3 units and
their subtopics. Say: _"As I clear each subtopic's mastery gate, its link fills
in — grey to amber to green. This is the three-tier scheduler made visible."_
Tap a subtopic to show its mastery detail (reviews, accuracy, retrievability,
gate).

**4. The review loop on the real engine (~30s)**

Open the "SOA Exam P" deck → study a few cards, grading Again/Hard/Good/Easy.
Reopen the dashboard/map to show the graded-review count climbing.

**5. Same engine on the phone (~40s)**

Point at the emulator running AnkiDroid, then prove the engine is ours:

```bash
unzip -l ~/dev/Anki-Android/AnkiDroid/build/outputs/apk/play/debug/AnkiDroid-play-arm64-v8a-debug.apk | grep librsdroid.so
```

Say: _"Desktop and phone run the same compiled Rust backend — here it is inside
the phone APK."_

## What's built vs planned (be honest in the demo)

- **Built:** real Rust engine change; three signals; give-up rule (Rust
  assertion + test); mastery model + ordering; study map with proportional
  fill; readiness dashboard; syllabus taxonomy + 42-card deck; weighted
  coverage; shared engine on the phone; seeded split + leakage scan + benchmark
  - crash test.
- **Planned (Friday/Sunday, documented in `docs/vision.md` + `docs/ai-features-prd.md`):**
  tap-a-node-opens-the-deck; wiring the three-pile order into the live queue;
  practice-test-driven readiness calibration; two-way phone↔desktop sync; the
  user-question area; and the AI features (all off by default).

## Key files (for Q&A)

- Engine: `rslib/src/speedrun/{service.rs,mastery.rs}`, `proto/anki/speedrun.proto`
- Give-up rule test: `pylib/tests/test_speedrun.py`
- Taxonomy + deck: `pylib/anki/speedrun/{exam_p_topics.json,seed.py}`
- UI: `ts/routes/{readiness-dashboard,study-map}/+page.svelte`
- Phone: `docs/android-build.md`
- Vision + AI plan: `docs/vision.md`, `docs/ai-features-prd.md`
