# Held-out SOA Exam P sample questions (local only)

This folder is where the **official public "SOA Exam P Sample Questions"** go so
the evals can run against real items. It exists to keep the fork honest:

- **Real items are NOT committed.** They are copyrighted by the Society of
  Actuaries. This repo is AGPL-3.0-or-later, so we do not redistribute them.
  `items.json` here is **gitignored** (see the repo `.gitignore`).
- **The pipeline still runs with nothing here.** With no `items.json`, the loader
  (`pylib/anki/speedrun/soa_sample.py`) falls back to the committed, original,
  no-copyright corpus (`pylib/anki/speedrun/sample_items.json`), so tests, CI,
  and `make ai-eval` work out of the box.
- **Held out of training.** Whatever you put here is an EVALUATION-ONLY set: it
  must never enter AI training, a retrieval index, or a few-shot prompt. The
  leakage scan (`tools/speedrun/leakage_scan.py`) runs over these against AI
  inputs and fails the build on any leak.

## How to add the real set

1. Download the official "Exam P Sample Questions" and "Sample Solutions" from
   soa.org (free, public).
2. Extract each question into an item and hand-label its syllabus subtopic tag
   (one of the 19 in `pylib/anki/speedrun/exam_p_topics.json`).
3. Write them to `data/soa_sample_p/items.json` in this shape:

```json
{
    "source": "soa-sample-2026",
    "items": [
        {
            "id": "soa-p-001",
            "question": "…the official question text…",
            "subtopic": "subtopic::general::bayes",
            "difficulty": "medium",
            "answer": "…"
        }
    ]
}
```

The loader will prefer this file automatically and label every downstream result
as the real SOA set (`is_real_soa = true`) instead of the original fallback.
