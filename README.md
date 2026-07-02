# Speedrun — a desktop + mobile study app for SOA Exam P, built on Anki

**The exam:** [SOA Exam P (Probability)](https://www.soa.org/education/exam-req/edu-exam-p-detail/).
Computer-based, 3 hours, 30 multiple-choice questions (A–E) plus 5 unscored
pilots. **Scored 0–10; 0–5 = fail, 6–10 = pass.** Section weights (May 2026
syllabus): General Probability 23–30% · Univariate Random Variables 44–50% ·
Multivariate Random Variables 23–30%. Historical pass rate ~43%.

This is a **fork of [Anki](https://apps.ankiweb.net)** that doesn't just help you
_remember_ Exam P — it measures three different things and is honest about
whether you'd _pass_:

1. **Memory** — can you recall the fact now? (Anki's FSRS.)
2. **Performance** — can you solve a new, exam-style question that uses it?
3. **Readiness** — what would you score today, and how sure are we?

**The honesty rule (enforced in code):** no readiness number is shown unless it
also shows the evidence, what data is missing, how accurate past guesses were, a
range (not a point), and the single best next thing to study. Below the data
threshold (≥ 200 graded reviews **and** ≥ 50% weighted, practiced coverage) the
app shows **no** score — a Rust assertion (`ComputeReadiness` returns a
`oneof { NoScore, ReadinessScore }`), not a UI hint. Never a fabricated number.

## License

**AGPL-3.0-or-later**, with credit to **Anki** (Ankitects Pty Ltd). This is a
derivative work of Anki; some upstream Anki components are BSD-3-Clause. See
[LICENSE](./LICENSE) and the upstream README below.

## The engine change (why it's real)

The graded Rust change lives in Anki's shared engine (`rslib/`, the `anki`
crate), so it ships to both desktop and phone. `SpeedrunService`
(`rslib/src/speedrun/`, `proto/anki/speedrun.proto`) adds five RPCs called from
Python: `SpeedrunPing`, `ComputeReadiness` (give-up rule), `GetMasteryState`
(three-tier mastery gate + importance-weighted rollups + "what to study next"),
`GetMasteryOrderedNewCards`, and `GetPointsAtStakeOrder` (due cards by topic
weight × student weakness). Two opt-in, default-off live-queue reorders hook
`build_queues` (`rslib/src/scheduler/queue/builder/mod.rs`): `speedrunMasteryScheduler`
(new-card tier order) and `speedrunPointsAtStake` (review order) — both read-only,
so FSRS intervals stay valid and undo/integrity are untouched. Full rationale in
[docs/rust-change.md](./docs/rust-change.md); the exact upstream files touched and
their merge risk are in [docs/upstream-touched.md](./docs/upstream-touched.md).

## Architecture (both apps, one engine)

- **Shared engine (Rust):** the `anki` crate in `rslib/` — FSRS (memory) + the
  SpeedrunService (mastery, coverage, readiness give-up rule, orderings). One
  compiled engine ships to desktop and phone.
- **Desktop:** the Rust engine + Python (`pylib`/`aqt`) + a TypeScript/Svelte
  frontend. The readiness dashboard (`ts/routes/readiness-dashboard`) and the
  importance-sized bubble study map (`ts/routes/study-map`) call the RPCs.
- **Mobile:** AnkiDroid consuming the **same** Rust engine via the
  `Anki-Android-Backend` JNI `.aar` (see [docs/android-build.md](./docs/android-build.md)).
- Full spec + diagrams: [PRD.md](./PRD.md); north-star design:
  [docs/vision.md](./docs/vision.md); score models:
  [docs/score-models.md](./docs/score-models.md).

## Build & run

Prereqs: Rustup (toolchain auto-pinned), N2 (`tools/install-n2`) or Ninja 1.10+,
Python 3, Node/Yarn. The repo path must contain **no spaces**.

- **Desktop:** `./run` (build + launch). Installer: `tools/build-installer`
  (output in `out/installer/dist`). Tests/checks: `./ninja check`.
- **Mobile (Android):** clone `Anki-Android` and `Anki-Android-Backend` as
  siblings, point the backend's `anki` submodule at this fork, rebuild the
  `.aar`, and run AnkiDroid — recipe in [docs/android-build.md](./docs/android-build.md).
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
