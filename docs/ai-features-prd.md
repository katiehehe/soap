# PRD: AI features (Friday), SOA Exam P Speedrun

Draft spec for the AI layer. **Do not start until the Wednesday core is done.**
AI is an _addition_ to a system that already works without it.

## Non-negotiable principles (from the grading rubric)

1. **Every AI output traces to a named source.** No card, hint, or classification
   is shown without a citation the student can check. AI claims with no source
   = that section scores 0.
2. **Gold-set gate.** Every AI output type is checked against a hand-built gold
   test set _before_ a student sees it. Ship only if it clears the bar.
3. **Beat a baseline.** Each AI feature must beat a simpler method
   (keyword/BM25 or vector search) on its gold set. If it doesn't, we ship the
   baseline.
4. **Off by default; app works with AI off.** A single setting disables all model
   calls; readiness, the map, and the deck still function. This is tested.
5. **No test-data leakage.** Practice-test / held-out items never enter any AI
   prompt, retrieval index, or few-shot set. The existing leakage scan
   (`tools/speedrun/leakage_scan.py`) runs over AI inputs too.
6. **Provider-agnostic + logged.** Model, prompt, source, and output are logged
   for every call so results are reproducible and auditable.

## Feature 1: Subtopic classifier (files a user question into the tree)

**Problem.** A student pastes their own question; we suggest which of the 19
subtopics it belongs to so it can join the study map.

- **Input:** question text. **Output:** ranked subtopic(s) + confidence + the
  syllabus source (the learning-outcome text the match is based on).
- **Baseline to beat:** TF-IDF / embedding similarity between the question and
  each subtopic's official outcome description.
- **Gold set:** ~100 questions hand-labelled with their true subtopic (drawn
  from public sample questions, kept out of any training/index).
- **Metric:** top-1 and top-3 accuracy vs the baseline; pre-registered pass bar
  (e.g. beat baseline top-1 by ≥ 5 points).
- **Safety:** user questions stay in a **separate area** until the user accepts a
  suggestion; a low-confidence result files nothing and says so.

## Feature 2: Card generation from a named source

**Problem.** Generate extra practice cards for a weak subtopic.

- **Input:** a subtopic + a named source passage (a specific text section).
  **Output:** Q/A cards, each stamped with that source.
- **Gold set:** 50 human-written cards for the same subtopics; generate 50 from
  the source; a rubric scores each generated card **correct / wrong /
  bad-teaching**, with the cutoff set _before_ looking.
- **Baseline to beat:** template/cloze cards built by simple extraction from the
  source.
- **Safety:** generated cards land in a review queue tagged `ai::unreviewed`;
  they never count toward mastery/coverage until a human approves them, and they
  carry `src::<source>`.

## Feature 3: Grounded "why this subtopic" explanation (stretch)

Short, cited explanation of _why_ a question maps to a subtopic, pulled from the
syllabus outcome text. Same gate: cited, gold-checked, off-switchable.

## Readiness with AI vs without

Readiness stays driven by held-out **practice-test** performance (see
`docs/vision.md`). AI may _summarise_ the evidence, but the number itself is
computed from graded results, never generated. With AI off, readiness is
unchanged.

## Architecture

- Model calls live behind one Python module (e.g. `pylib/anki/speedrun/ai.py`)
  with a hard `ai_enabled` flag read from config; default **off**.
- A gold-set harness under `tools/speedrun/evals/` runs each feature's eval and
  prints feature-vs-baseline numbers with a fixed seed (re-runnable).
- Every call logs `{feature, model, prompt_hash, source, output}` to a local
  JSONL for audit.
- The Rust engine is **not** involved in AI; it stays the deterministic,
  offline core.

## Milestones (Friday)

1. `ai_enabled` config flag + off-by-default wiring + "AI off still scores" test.
2. Baselines (BM25 + embeddings) for classify & generate, with gold sets.
3. Feature 1 (classifier) behind the flag; eval beats baseline; UI suggestion in
   the user-question area.
4. Feature 2 (generation) behind the flag; eval + `ai::unreviewed` review queue.
5. Leakage scan over all AI inputs; audit log; documentation of results
   (including anything that did **not** beat the baseline).

## Definition of done

- Every AI output on screen shows a source.
- Each feature's eval, with seed, beats its baseline on its gold set (or we ship
  the baseline and say so).
- Toggling AI off leaves a working app that still produces the three scores.
- Leakage scan is clean over training/retrieval/few-shot inputs.
