---
name: honesty-gate
description: Use this skill before displaying, returning, or committing ANY memory, performance, or readiness number in the Speedrun exam app — dashboard values, API responses, demo screens, or test output. It enforces the project's honesty rule and give-up rule: no score ships without evidence, a range, calibration, coverage, and a clear abstain condition. Trigger whenever code produces a user-facing score or a readiness estimate.
---

# Honesty gate

The rubric has an automatic-fail condition: a made-up or misleading readiness number
fails the whole project. This skill is the checklist that must pass before any score
reaches a user, a demo, or a screenshot. If a check fails, the app **abstains and shows
the gap** — it never shows a bare number.

## Rule 0 — three scores, never one blend

Memory, performance, and readiness are three different questions and must be shown as
three separate numbers, each with a range. Never collapse them into one "% ready".

- **Memory** — chance of recalling a taught fact (this is FSRS's R; see the FSRS reference).
- **Performance** — chance of getting a new, exam-style question right, including unseen ones.
- **Readiness** — projected result on the real SOA P scale (pass-mark framing), with a range.

## The display contract (readiness)

A readiness score may be shown ONLY if the same view also shows all of:

1. Point estimate.
2. Likely range (not a single number).
3. Percent of the exam covered so far (topic coverage).
4. A "how sure" indicator, tied to coverage and data volume.
5. Timestamp of last update.
6. The main reasons / evidence behind the number.
7. The single best next thing to study.

If any of the seven is missing, do not render the score. Render the missing-data state instead.

## The give-up rule (abstain condition)

The app shows NO score when it lacks data. Default line for SOA P — **pre-register the
final numbers before you look at any results, then record them here:**

> Abstain unless **>= 200 graded reviews AND >= 50% topic coverage**, where coverage is
> weighted by the official SOA P section weights: General probability (23–30%),
> Univariate random variables (44–50%), Multivariate random variables (23–30%).

A deck that skips a whole high-weight section must not show "ready" even with many cards.
If a high-weight SOA section has ~0 coverage, abstain regardless of total review count.

## Provenance rule (AI outputs)

Any number or card that came from a model output must trace to a named source and must
have passed the held-out eval (see the eval skill). No traceable source → do not display.
Violating this zeroes the AI section of the grade.

## What "abstain" looks like

Never show a fake or placeholder number. Show, for example:
`No score yet — need N more graded reviews and coverage in {uncovered high-weight topics}.`
Always name the single best next action.

## Self-check before returning any score (run this)

- [ ] Is this a memory, performance, or readiness number, shown separately from the other two?
- [ ] Is it a range, not a bare point?
- [ ] For readiness: are all seven display-contract items present in the same view?
- [ ] Does the give-up rule pass (reviews + weighted coverage)? If not, abstain.
- [ ] For any AI-derived value: named source AND passed the held-out eval?
- [ ] Is every displayed number computed from real data — never hardcoded or mocked?

If any box is unchecked, abstain and surface the gap. A smaller honest number beats a
confident guess.
