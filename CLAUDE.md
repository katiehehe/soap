# AGENTS.md — Speedrun (SOA Exam P)

> This file is the source of truth for every AI coding agent working in this repo
> (Cursor reads it natively; `.cursor/rules/*.mdc` add file-scoped detail).
> Read this file, then `PRD.md`, then `SPEC_CHECKLIST.md` **before writing any code.**
> When guidance conflicts, the grading rubric in `SPEC_CHECKLIST.md` wins.

## What this is

A desktop + mobile study app **forked from Anki**, built for **one exam: SOA Exam P (Probability)**.
It is NOT a new flashcard app. It answers three _different_ questions and never blends them:

1. **Memory** — can the student recall this fact right now? (Anki's FSRS already does this.)
2. **Performance** — can the student answer a _new, exam-style_ question that uses the fact?
3. **Readiness** — what would they score today, and how sure are we?

Owner: Katie He. License: **AGPL-3.0-or-later**, with credit to Anki (some Anki parts are BSD-3-Clause).

## The exam (state this in the README, up front)

SOA Exam P is NOT one of the rubric's four example exams (MCAT/LSAT/GMAT/USMLE), so be explicit about its real scale so nothing looks invented:

- Computer-based, 3 hours, multiple choice A–E. Includes 5 unscored pilot questions.
- **Scored 0–10. 0–5 = fail, 6–10 = pass.** (Unofficial instant pass/fail at the center; official scaled score ~8 weeks later.)
- Section weights (May 2026 syllabus): **General Probability 23–30% · Univariate Random Variables 44–50% · Multivariate Random Variables 23–30%.**
- Calculus (series, integration, differentiability) is assumed knowledge.
- Historical pass rate ~43%; Jan 2026: 49.2% pass / 57.2% effective pass. Typical prep 150–300 hours.
- **Readiness output for P** = P(pass) with a confidence band + a projected 0–10 band + % of syllabus covered. Never a single bare number.

## HARD RULES — do not break these

- **Change Anki's Rust engine, not just the Python/Svelte screens.** A JS/Swift reimplementation of the scheduler does NOT count.
- **Two apps, one shared engine** (desktop + phone). Reviews and progress sync between them. Mobile uses the same Rust backend (Android via AnkiDroid's `Anki-Android-Backend` JNI bridge; iOS via the Rust C FFI). Do not fork the engine per platform.
- **Three separate scores, each with a range** — never one blended number.
- **The honesty rule:** never show a readiness score unless it also shows (a) the evidence behind it, (b) what data is missing, (c) how accurate past guesses were, (d) a range not a point, (e) the single best next thing to study.
- **The give-up rule:** the app shows NO score when it lacks data. This is an assertion in code, not a UI suggestion. State the exact threshold (e.g. ≥200 graded reviews AND ≥50% topic coverage).
- **Held-out testing + reproducibility:** train/test split with a seed; anyone can re-run and get the same numbers.
- **One study feature, pre-registered hypothesis, tested by turning it off/on** against plain Anki (3 builds, equal study time).
- **Every AI output traces to a named source,** is checked against a gold test set before a student sees it, and beats a simpler baseline (keyword/vector search).
- **Both apps must run with AI switched OFF** and still give a score.

## AUTOMATIC FAIL — never do these

- Show a made-up or misleading readiness number, or dress up a guess as a measurement.
- Let any test item (or a near-copy) leak into training data. (Run the leakage scan; keep it clean.)
- Emit an AI claim/card with no traceable source.

## GRADE CAPS (why the hard rules matter)

No real Rust change → 50% max · No phone companion sharing the engine + sync → 70% max · No re-runnable test setup → 60% max · No held-out testing → 60% max · Either app fails on a clean device → 50% max · Leaked test data → that score is 0 · AI claims with no source → AI section is 0.

## The spine of this project

One feature satisfies three requirements at once and should be built first after the core:
**a three-tier, mastery-gated scheduler** (Spiky POV 1) — block subtopics, then interleave _within_ a unit, then interleave _across_ units, with a mastery gate at each level. It IS the required Rust change (topic-aware scheduling + a mastery query), it IS the study feature we ablate (the ablation removes the within-unit interleaving tier), and it is the owner's core thesis. There are **two** Spiky POVs, not three: SPOV 1 is this scheduler; SPOV 2 (chronotype-aware timing) is a bonus we do NOT build this project. See `PRD.md` §"Spiky POVs → Features".

## Build & run (Anki, current `main`)

Prereqs: Rustup (toolchain auto-pinned by `rust-toolchain.toml`), N2 (`tools/install-n2`) or Ninja 1.10+, Python 3, Node/Yarn. Repo path must contain **no spaces**.

- Build + launch desktop from source: `./run` (non-optimized/dev by default; `RELEASE=1` or `RELEASE=2` to optimize)
- Run all checks/tests: `./ninja check` (scoped example: `./ninja check:svelte`)
- Rust-only tests for your change: `cargo test -p <crate>` (e.g. the `anki` crate in `rslib/`)
- Build a desktop installer: `tools/build-installer` → output in `out/installer/dist`
- Mobile: clone `Anki-Android` and `Anki-Android-Backend` **into the same parent folder**; the backend builds an `.aar` (Rust engine compiled for Android) that AnkiDroid consumes. Match `BACKEND_VERSION`.

## Before you code (every session)

1. Re-read `SPEC_CHECKLIST.md` and state which deadline + which checklist item you are working on.
2. Also read `docs/project-brief.md` before coding — it's the official project brief and grading criteria; treat it like the rubric (it wins on conflicts alongside SPEC_CHECKLIST.md).
3. In Plan mode, propose the change and name the files you'll touch; wait for confirmation before editing.
4. No AI/model calls, generated cards, or chatbot until the Wednesday core is done.
5. After a change, confirm: relevant tests pass, undo still works, the collection isn't corrupted.
6. Update `SPEC_CHECKLIST.md` checkboxes and note any new "files touched (upstream)" for the merge-difficulty log.

## Layout of this kit

- `PRD.md` — full product spec, tech stack, Spiky-POV→feature map, milestones, today's plan.
- `SPEC_CHECKLIST.md` — the living grade/compliance tracker (update it as you go).
- `.cursor/rules/` — file-scoped rules: `core`, `rust-engine`, `scoring-honesty`, `ai-traceability`, `testing-evals`, `sync`.
