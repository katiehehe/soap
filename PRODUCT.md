# Product

## Register

product

## Users

Candidates preparing for the SOA Exam P (Probability) actuarial exam — self-studying
adults putting in 150–300 hours, mostly on a desktop (this Anki fork) with a phone
companion that shares the same engine. On any given screen the user is in one of three
tasks: studying the cards due now, deciding what to study next (concept map / plan), or
checking how ready they are (readiness).

## Product Purpose

A focused study app forked from Anki, built for ONE exam. It answers three separate
questions and never blends them: **Memory** (can you recall the fact right now?),
**Performance** (can you solve a new, exam-style question?), and **Readiness** (what
would you score today, and how sure are we?). Success = the learner trusts the numbers
and always knows the single best next action.

## Brand Personality

Calm, scholarly, and trustworthy — an academic study tool, not an arcade. Three words:
**scholarly, honest, focused**. A restrained "dark-academia" palette (ink + warm ivory,
muted indigo / teal / gold accents) with a serif/sans pairing (Fraunces + DM Sans);
personality comes through craft and typography, not noise. Easy on the eyes for long
study sessions.

## Anti-references

- A guess dressed up as a measurement: a glowing/celebratory readiness score, or hype
  words behind a "no score yet" state. (This is an auto-fail for the project.)
- Blending the three scores into a single "% ready".
- Overstimulating chrome — neon clashes, gradient text, glows, floating emoji — that is
  jarring and fatiguing across 150–300 hours of study.
- Looking like stock Anki.

## Design Principles

- **Calm, academic chrome; honest core.** Restrained color and quiet motion so the tool
  disappears into the task, while every measured number stays high-contrast, calm, and
  always shown with a range and a named source.
- **Three scores, never one blend**, each shown with a range.
- **Show the give-up state honestly.** No score below the data threshold; style it as
  withholding (amber/neutral), never as a win.
- **Semantic colors carry fixed meaning** (not-started / in-progress / mastered) and are
  never rotated through the decorative accent palette.
- **Offline-first and accessible.** Self-hosted fonts, WCAG-AA contrast on all text,
  visible focus, reduced-motion honored, ≥44px touch targets.

## Accessibility & Inclusion

WCAG AA minimum for all text (warm ivory on the ink background reaches AAA). Accent
colors are never used for body text or critical numbers. Focus is a high-visibility
dashed ring with offset. Full `prefers-reduced-motion` support. Touch targets ≥ 44px.
