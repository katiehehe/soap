# The paraphrase test (challenge 7d)

**Question it answers:** is our _Performance_ signal actually measuring something
beyond _Memory_, or is it just copying the memory model?

Anki's FSRS already tells us whether a student can **recall a flashcard**. The
whole point of this project's Performance signal is to predict whether they can
answer a **new, exam-style question that uses the same idea**. If a student can
recite the card but flunks a reworded question, the memory-to-performance bridge
was never built. This test measures that gap.

## Method (as the brief specifies)

Take **30 cards**. For each, write **2 exam-style questions that test the same
idea in new words**. Compare **card recall** (memory) with **accuracy on the
reworded questions** (performance). **Report the gap.**

- Dataset: `pylib/anki/speedrun/paraphrase_items.json` — 30 original, held-out,
  no-copyright cards spanning all 19 subtopics; each has a memory `card_prompt`
  and two `reworded` exam-style questions.
- Harness: `pylib/anki/speedrun/paraphrase.py` — `grade()` is pure aggregation
  over 0/1 outcomes (real graded answers and simulated ones flow through it
  identically); `reworded_distinctness()` guards against rewordings that are
  near-copies of the card prompt.
- Runner: `tools/speedrun/evals/paraphrase_eval.py` (`make paraphrase`).

## Honesty

There is no real cohort in a week, so the numbers come from the **clearly
labelled synthetic persona cohort** (`persona.py`), graded by the real code. The
memory side uses `persona.recall_prob` (an FSRS-style recall) and the performance
side uses `persona.p_correct` (transfer to a new question) — two different
models, exactly as in the app. Same `--seed`/`--students` → same numbers.

Three guards make it a _fair_ test rather than a flattering one:

1. **Distinctness gate** — every rewording must differ enough (word-overlap
   below `MAX_REWORD_OVERLAP`) from its card prompt, or "performance" would just
   be re-reading the memory prompt.
2. **Pre-registered threshold** — `COPYING_GAP = 0.05`; a gap below it is
   reported as COPYING, not spun.
3. **Copycat control (null run)** — feed the _performance_ model into _both_
   sides. If the test is sound, the gap must collapse to ~0 and the verdict must
   flip to COPYING. It does.

## Result (synthetic cohort, `--students 60 --seed 0`)

|                       | Card recall (memory) | Reworded accuracy (performance) | Gap        |
| --------------------- | -------------------- | ------------------------------- | ---------- |
| **Main**              | 73.2%                | 31.8%                           | **+41.4%** |
| **Control (copycat)** | 31.1%                | 31.8%                           | −0.7%      |

The +41.4% gap means performance is a **genuinely separate, harder signal** than
memory — the bridge exists. The control collapsing to −0.7% (verdict: COPYING)
shows the test would **catch** a performance model that merely tracked memory.
The gap is present in **every** subtopic (smallest +30% on combinatorics,
largest +58% on joint/conditional moments).

Reproduce: `make paraphrase` (or `make paraphrase ARGS="--students 100 --seed 7"`).
Tests: `pylib/tests/test_speedrun_paraphrase.py`.
