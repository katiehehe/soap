# AI features — what was built, why, and the eval results (Friday)

Short note required by the brief (§6 "Due Friday": _"a short note on what AI you
built, why, and what you skipped"_). The full spec is `docs/ai-features-prd.md`;
this records what shipped and the measured numbers.

## What was built

Two AI features, both **off by default** behind one hard switch
(`pylib/anki/speedrun/ai.py`, config `speedrunAiEnabled`), both **provider-agnostic**
(an `OpenAiClient` and a deterministic offline `StubClient`):

1. **Feature 1 — subtopic classifier.** Files a pasted question into one of the 19
   syllabus subtopics, each suggestion carrying the syllabus outcome text it is
   grounded in. Baseline to beat: keyword overlap
   (`tools/speedrun/evals/classify_eval.py`).
2. **Feature 2 — card generation from a named source.** Generates exam-style
   cards grounded in a named source passage (`pylib/anki/speedrun/gen_sources.json`).
   Every card is stamped `src::<source>` and lands tagged `ai::unreviewed` with a
   `subtopic_candidate::` tag, so it **never counts toward coverage/mastery until
   a human approves it**. Baseline to beat: template/extraction generation (the
   stub).

## Why

Both target real gaps: classifying user-pasted questions onto the study map, and
expanding practice for a weak subtopic — the two places a student wants help that
the deterministic core does not provide. Neither touches scoring: **readiness,
performance, and memory are computed with AI off**, so AI can never fabricate a
number.

## What was skipped

- Feature 3 (grounded "why this subtopic" explanation) — stretch, not built.
- No AI in the scoring path at all (by design).
- Live AI-vs-baseline numbers are produced only when a key is present; this
  environment had none, so the AI rows below read "not run" (the harness prints
  them the moment `OPENAI_API_KEY` is set).

## Honesty / safety rules enforced

- **Source-traced:** every AI output carries a named source; generation also
  writes an audit record (`{feature, model, prompt_hash, source, output}`) to
  `speedrun_ai_audit.jsonl` next to the collection.
- **Gold-set gate + baseline:** each feature is scored on a held-out gold set
  against a simpler baseline with a **pre-registered cutoff** (below). If it does
  not clear the bar, we ship the baseline and say so.
- **Off by default; app scores with AI off** (tested: `test_speedrun_ai.py`).
- **No leakage:** the leakage scan runs over AI inputs (classifier index and
  generation sources) against the held-out corpus; clean.

## Measured results (reproducible)

Run: `make ai-eval` (baselines always; AI side when a key is set). Gold corpus is
the held-out sample-item set (official SOA sample when present, else the committed
original fallback — 38 items).

### Feature 1 — classifier (`make classify`)

| method           | top-1          | top-3          |
| :--------------- | :------------- | :------------- |
| keyword baseline | 45%            | 76%            |
| AI (OpenAI)      | run with a key | run with a key |

Pre-registered bar: **AI top-1 must beat the baseline by ≥ 5 points**, else ship
the baseline.

### Feature 2 — generation (`make ai-eval`)

Named sources: 8. Human reference cards: 42 (structural-OK 100% — the rubric
passes hand-written cards). Rubric: correct / wrong / bad-teaching.

| generator                    | correct        | bad-teaching   |
| :--------------------------- | :------------- | :------------- |
| template/extraction baseline | 24% (12/50)    | 0%             |
| AI (OpenAI)                  | run with a key | run with a key |

Pre-registered cutoff (set before looking): ship AI generation only if **correct
≥ 60% AND bad-teaching ≤ 20% AND it beats the baseline's correct rate**.

## Reproduce with a key

```bash
out/pyenv/bin/pip install -r tools/speedrun/requirements-ai.txt
export OPENAI_API_KEY=...    # your key
make ai-eval                 # now prints the AI rows + PASS/FAIL vs the cutoff
```
