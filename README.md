# Speedrun: a desktop + mobile study app for SOA Exam P, built on Anki

**The exam:** [SOA Exam P (Probability)](https://www.soa.org/education/exam-req/edu-exam-p-detail/).
Computer-based, 3 hours, 30 multiple-choice questions (A-E) plus 5 unscored
pilots. **Scored 0-10; 0-5 = fail, 6-10 = pass.** Section weights (May 2026
syllabus): General Probability 23-30% · Univariate Random Variables 44-50% ·
Multivariate Random Variables 23-30%. Historical pass rate ~43%.

This is a **fork of [Anki](https://apps.ankiweb.net)** that doesn't just help you
_remember_ Exam P: it measures three different things and is honest about
whether you'd _pass_:

1. **Memory**: can you recall the fact now? (Anki's FSRS.)
2. **Performance**: can you solve a new, exam-style question that uses it?
3. **Readiness**: what would you score today, and how sure are we?

**The honesty rule (enforced in code):** no readiness number is shown unless it
also shows the evidence, what data is missing, how accurate past guesses were, a
range (not a point), and the single best next thing to study. Below the data
threshold (≥ 200 graded reviews **and** ≥ 50% weighted, practiced coverage) the
app shows **no** score, only a Rust assertion (`ComputeReadiness` returns a
`oneof { NoScore, ReadinessScore }`), not a UI hint. Never a fabricated number.

## Submission map (project brief §12)

The four hand-in items, and exactly where each lives, so a grader can find
everything in one place:

1. **GitHub repo** (this public AGPL-3.0-or-later fork, credit to Anki): the
   [License](#license) section + [LICENSE](./LICENSE) name Ankitects Pty Ltd and
   the BSD-3-Clause parts; the **exam is stated up front** at the very top of this
   README; **build instructions for both apps** are under
   [Build & run](#build--run) (desktop `./run`; Android via
   [docs/android-build.md](./docs/android-build.md)); the **architecture
   overview** is under [Architecture](#architecture-both-apps-one-engine) with the
   diagram in [docs/architecture.mermaid](./docs/architecture.mermaid); the
   **Rust-change note** is [docs/rust-change.md](./docs/rust-change.md); the
   **files-touched list** is [docs/upstream-touched.md](./docs/upstream-touched.md).
2. **Demo video (3-5 min):** the timed six-shot script is
   [docs/demo-script.md](./docs/demo-script.md); manual-capture steps are in
   [docs/recording-steps.md](./docs/recording-steps.md).
3. **Model descriptions** (memory, performance, and readiness, each with the
   give-up rule): [docs/score-models.md](./docs/score-models.md).
4. **Brainlift:** [docs/brainlift.md](./docs/brainlift.md).

## License

**AGPL-3.0-or-later**, with credit to **Anki** (Ankitects Pty Ltd). This is a
derivative work of Anki; some upstream Anki components are BSD-3-Clause. See
[LICENSE](./LICENSE) and the upstream README below.

## What's proven (measured, reproducible)

Every number below comes from a one-command, seeded, leakage-checked run, not a
claim. Commands in [Makefile](./Makefile); details in [SPEC_CHECKLIST.md](./SPEC_CHECKLIST.md).

- **Rust engine change**: `SpeedrunService` (7 RPCs) + two opt-in live-queue
  reorders; 89 Rust tests + Python-calling tests; undo/no-corruption covered.
- **Study feature + ablation** (`make ablation`): the three-tier scheduler's
  **within-unit interleaving** tier, tested Full / Ablated / Plain at **equal
  study time**. Reports the pre-registered metric across an effect-size sweep
  **including the null** (disc_gain 0 → builds identical, no built-in bias);
  direction Full ≥ Ablated ≥ Plain holds for any assumed effect.
  [docs/study-feature-ablation.md](./docs/study-feature-ablation.md).
- **Paraphrase test** (`make paraphrase`, rubric 7d): 30 cards × 2 reworded
  questions: **card recall 73% vs reworded accuracy 32% → +41-pt gap**, so
  Performance is a genuinely separate signal from Memory (a copycat control
  collapses to ~0, confirming the test discriminates).
  [docs/paraphrase-test.md](./docs/paraphrase-test.md).
- **AI, checked vs a baseline** (`make ai-eval`, off by default): on the
  held-out official SOA corpus, leakage-clean: **classifier** AI top-1 38% vs
  keyword 13% (**+25 pts, PASS**); **generation** AI 92% correct / 0%
  bad-teaching vs 24% baseline (**PASS**), each against a pre-registered cutoff.
  [docs/ai-results.md](./docs/ai-results.md).
- **Speed** (`make bench`, 50k cards): next-card p95 ~0.05 ms, mastery query p95
  ~0.06 ms, readiness p95 ~4.7 ms. **Crash** (`make crash-test`): 20× mid-review
  SIGKILL, SQLite integrity clean every time. **Sync** (`make sync-test`): 20/20
  reviews land once, none lost/doubled, deterministic conflict winner.

## The engine change (why it's real)

The graded Rust change lives in Anki's shared engine (`rslib/`, the `anki`
crate), so it ships to both desktop and phone. `SpeedrunService`
(`rslib/src/speedrun/`, `proto/anki/speedrun.proto`) adds seven RPCs called from
Python: `SpeedrunPing`, `ComputeReadiness` (give-up rule), `GetMasteryState`
(three-tier mastery gate + importance-weighted rollups + "what to study next"),
`GetMasteryOrderedNewCards`, `GetPointsAtStakeOrder` (due cards by topic
weight × student weakness), `GetStudyPlan` (today's tiered deck plan), and
`GetStudyPace` (mastery pace vs the exam date). Two opt-in, default-off live-queue reorders hook
`build_queues` (`rslib/src/scheduler/queue/builder/mod.rs`): `speedrunMasteryScheduler`
(new-card tier order) and `speedrunPointsAtStake` (review order), both read-only,
so FSRS intervals stay valid and undo/integrity are untouched. Full rationale in
[docs/rust-change.md](./docs/rust-change.md); the exact upstream files touched and
their merge risk are in [docs/upstream-touched.md](./docs/upstream-touched.md).

## Architecture (both apps, one engine)

- **Shared engine (Rust):** the `anki` crate in `rslib/`, with FSRS (memory) + the
  SpeedrunService (mastery, coverage, readiness give-up rule, orderings). One
  compiled engine ships to desktop and phone.
- **Desktop:** the Rust engine + Python (`pylib`/`aqt`) + a TypeScript/Svelte
  frontend. The readiness dashboard (`ts/routes/readiness-dashboard`) and the
  importance-sized bubble study map (`ts/routes/study-map`) call the RPCs.
- **Mobile:** AnkiDroid consuming the **same** Rust engine via the
  `Anki-Android-Backend` JNI `.aar` (see [docs/android-build.md](./docs/android-build.md)).
- The one-screen engine/apps diagram:
  [docs/architecture.mermaid](./docs/architecture.mermaid). Full spec + diagrams:
  [PRD.md](./PRD.md); north-star design: [docs/vision.md](./docs/vision.md).

## Model descriptions & hand-in docs

- **Model descriptions** (one section each: memory / performance / readiness,
  with the give-up rule and calibration): [docs/score-models.md](./docs/score-models.md).
- **Rust-change rationale:** [docs/rust-change.md](./docs/rust-change.md) ·
  **upstream files touched + merge risk:** [docs/upstream-touched.md](./docs/upstream-touched.md).
- **AI features + results:** [docs/ai-results.md](./docs/ai-results.md) ·
  **paraphrase test:** [docs/paraphrase-test.md](./docs/paraphrase-test.md) ·
  **study-feature ablation:** [docs/study-feature-ablation.md](./docs/study-feature-ablation.md).
- **Demo video script:** [docs/demo-script.md](./docs/demo-script.md) ·
  **Brainlift:** [docs/brainlift.md](./docs/brainlift.md).
- **Latency evidence** (p50/p95/worst on 50k cards): [docs/latency.md](./docs/latency.md) ·
  **manual-capture steps** (clean install + phone sync recording):
  [docs/recording-steps.md](./docs/recording-steps.md).

## Build & run

Prereqs: Rustup (toolchain auto-pinned), N2 (`tools/install-n2`) or Ninja 1.10+,
Python 3, Node/Yarn. The repo path must contain **no spaces**.

- **Desktop:** `./run` (build + launch). Installer: `tools/build-installer`
  (output in `out/installer/dist`). Tests/checks: `./ninja check`.
- **Mobile (Android):** clone `Anki-Android` and `Anki-Android-Backend` as
  siblings, point the backend's `anki` submodule at this fork, rebuild the
  `.aar`, and run AnkiDroid, recipe in [docs/android-build.md](./docs/android-build.md).
- **Speedrun tooling:** `make bench` (50k-card speed report), `make crash-test`
  (20× mid-review SIGKILL, zero corruption), `make calibration` (FSRS held-out
  memory calibration). Compliance tracker: [SPEC_CHECKLIST.md](./SPEC_CHECKLIST.md).

## Files touched upstream

Every pre-existing Anki file this fork modifies is logged, with merge risk, in
[docs/upstream-touched.md](./docs/upstream-touched.md). Everything else under
`rslib/src/speedrun/`, `qt/aqt/speedrun.py`, `ts/routes/{readiness-dashboard,study-map}`,
`pylib/anki/speedrun/`, and `tools/speedrun/` is new and fork-owned.

---

# Anki (upstream project)

[![Build Status](https://github.com/ankitects/anki/actions/workflows/ci.yml/badge.svg)](https://github.com/ankitects/anki/actions/workflows/ci.yml)
[![Documentation](https://img.shields.io/badge/docs-dev--docs.ankiweb.net-blue)](https://dev-docs.ankiweb.net)

This repo contains the source code for the computer version of
[Anki](https://apps.ankiweb.net).

## About

Anki is a spaced repetition program. Please see the [website](https://apps.ankiweb.net) to learn more.

## Getting Started

### Contributing

Want to contribute to Anki? Check out the [Contribution Guidelines](./docs/contributing.md).

For more information on building and developing, please see [Development](./docs/development.md).

#### Contributors

The following people have contributed to Anki: [CONTRIBUTORS](./CONTRIBUTORS)

### Anki Betas

If you'd like to try development builds of Anki but don't feel comfortable
building the code, please see [Anki betas](https://betas.ankiweb.net/).

## License

Anki's license: [LICENSE](./LICENSE)
