---
name: prose-cleanup
description: Strip em-dashes, en-dashes, and unnecessary explanation from any text. Invoke when asked to "clean up," "tighten," or "de-fluff" docs, comments, commit messages, UI copy, or generated card text, or when a file has been flagged for dash/verbosity issues before commit.
---

# Prose cleanup

Run this over the target file(s) or the current diff. Do not touch logic,
only text.

## Replace all dashes
- Em-dash and en-dash are banned. Replace by rewriting the sentence:
  - Aside or interruption: use a comma or parentheses.
  - Range (e.g. "6-10"): use a hyphen.
  - Clause break that was carrying a colon's job: use a colon.
- After editing, grep the file for the code points below and confirm zero
  hits: U+2013, U+2014, U+2015, U+2212.

## Cut unnecessary explanation
- Delete restatements of the request and after-the-fact summaries.
- Delete filler adjectives: comprehensive, robust, seamless, powerful,
  cutting-edge, elegant.
- A code comment survives only if it explains non-obvious intent, an
  invariant, or a gotcha. Delete comments that narrate what the code
  plainly does.
- Keep at most one or two sentences on a real trade-off. Drop the rest.

## What not to change
- Do not alter numbers, identifiers, quoted exam content, or the honesty
  score copy (evidence, missing data, calibration, range, give-up rule).
  Those are correctness-critical and get reviewed by diff, not cleaned.
- Do not reformat code or rename anything.

## Report
State how many dashes you removed and how many lines you cut, in one line.
