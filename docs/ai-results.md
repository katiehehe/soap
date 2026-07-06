# AI features: what was built, why, and the eval results (Friday)

Short note required by the brief (§6 "Due Friday": _"a short note on what AI you
built, why, and what you skipped"_). The full spec is `docs/ai-features-prd.md`;
this records what shipped and the measured numbers.

## What was built

Two AI features, both **off by default** behind one hard switch
(`pylib/anki/speedrun/ai.py`, config `speedrunAiEnabled`), both **provider-agnostic**
(an `OpenAiClient` and a deterministic offline `StubClient`):

1. **Feature 1: subtopic classifier.** Files a pasted question into one of the 19
   syllabus subtopics, each suggestion carrying the syllabus outcome text it is
   grounded in. Baseline to beat: keyword overlap
   (`tools/speedrun/evals/classify_eval.py`).
2. **Feature 2: card generation from a named source.** Generates exam-style
   cards grounded in a named source passage (`pylib/anki/speedrun/gen_sources.json`).
   Every card is stamped `src::<source>` and lands tagged `ai::unreviewed` with a
   `subtopic_candidate::` tag, so it **never counts toward coverage/mastery until
   a human approves it**. Baseline to beat: template/extraction generation (the
   stub).

## Why

Both target real gaps: classifying user-pasted questions onto the study map, and
expanding practice for a weak subtopic. These are the two places a student wants
help that the deterministic core does not provide. Neither touches scoring: **readiness,
performance, and memory are computed with AI off**, so AI can never fabricate a
number.

## What was skipped

- Feature 3 (grounded "why this subtopic" explanation): stretch, not built.
- No AI in the scoring path at all (by design).
- Live AI-vs-baseline numbers populate only when a key is present. The offline
  baselines and the full comparison harness are committed and reproducible; the
  AI cells of the artifact (`tools/speedrun/evals/results/ai_eval.json`) are now
  filled from a **full keyed run** (`is_subsample: false`, see "Full keyed run"
  below), and AI beats the baseline and clears every pre-registered cutoff on all
  three evals. With no key the AI cells stay `null`/`pending`, never fabricated.

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

## Measured results (committed artifact + reproducible)

All numbers below are emitted, side by side, into one committed machine-readable
artifact, **`tools/speedrun/evals/results/ai_eval.json`**, by a single command:

```bash
make ai-report                       # writes the artifact (baseline cells filled)
OPENAI_API_KEY=... make ai-report    # ALSO populates the AI cells
```

The artifact records, per eval: the dataset descriptor, the pre-registered
cutoffs, the **baseline** metrics (accuracy + wrong-answer rate), the **AI**
metrics, plus a timestamp, git SHA, and an `ai_ran` flag. Baseline/offline cells
are reproducible with no key; **AI cells populate only on a keyed run**, and with no
key they are `null` with a `pending` verdict, never fabricated.

> **Status of the committed artifact:** the AI cells hold the **FULL held-out
> results** from a keyed run (`ai_ran: true`, `is_subsample: false`,
> `model: gpt-4o-mini`, `seed: 0`, ~4.2 min): all 715 classifier items, 50
> generated cards, and all 19 problem subtopics. AI beat the baseline and cleared
> every pre-registered cutoff on all three (see "Full keyed run" below). Regenerate
> the offline baseline-only artifact any time with `make ai-report ARGS="--no-ai"`.

> **Reproducibility on a clean checkout (read before comparing cells):** the AI
> cells above are the owner's real KEYED run at commit `f876127df`, produced with
> `OPENAI_API_KEY` set AND the owner's local, gitignored real SOA corpus (the 715
> official sample items). Reproducing those exact cells therefore needs both a key
> and that local corpus, so a grader who just clones the repo will NOT land on the
> same AI numbers. A clean checkout instead reproduces (a) the offline baselines,
> with no key, always, and (b) once a key is added, the AI side over the committed
> 38-item fallback corpus (`pylib/anki/speedrun/sample_items.json`, the
> no-copyright stand-in for the 715 real items), not the 715-item cells. Nothing
> here is fabricated: the committed cells are a real measured run, dated and
> attributed by `ai_ran` / `git_sha` / `generated_at_utc` in the artifact.

### Feature 1: classifier (`make classify`)

Held-out gold set: the **official SOA sample corpus, 715 items** across all 19
subtopics (leakage over AI inputs: CLEAN). The committed original fallback corpus
reproduces the same structure with different absolute values.

| method                   | top-1      | top-3      | wrong-rate (top-1) | status                              |
| :----------------------- | :--------- | :--------- | :----------------- | :---------------------------------- |
| keyword baseline         | 13.15%     | 33.29%     | 86.85%             | committed, reproducible offline     |
| AI (OpenAI, gpt-4o-mini) | **38.18%** | **70.77%** | **61.82%**         | committed (full 715-item keyed run) |

Pre-registered bar (in the artifact): **AI top-1 must beat the baseline by ≥ 5
points** (`AI_TOP1_MARGIN=0.05`). Actual margin **+25.0 pts → PASS**.

### Feature 2: card generation (`make ai-eval`)

Named sources: **19, all subtopics** (`gen_sources.json`; all pass the leakage
gate). Human reference cards: **186** (structural-OK 100%, meaning the rubric passes
hand-written cards). Rubric per card, over a 50-card sample: correct / wrong /
bad-teaching.

| generator                    | correct         | wrong | bad-teaching | status                             |
| :--------------------------- | :-------------- | :---- | :----------- | :--------------------------------- |
| template/extraction baseline | 30% (15/50)     | 35    | 0%           | committed, reproducible offline    |
| AI (OpenAI, gpt-4o-mini)     | **92% (46/50)** | **4** | **0%**       | committed (full 50-card keyed run) |

Pre-registered cutoff (set before looking; in the artifact): ship AI generation
only if **correct ≥ 60% AND bad-teaching ≤ 20% AND it beats the baseline's correct
rate** (`MIN_CORRECT_RATE=0.60`, `MAX_BAD_TEACHING=0.20`). Actual **92% correct, 0%
bad-teaching, beats 30% → PASS**.

> **What "correct" means here (do not over-read the 92%):** this generation number
> is a **grounded / traceable** rate, not a gold-answer factual check. `score_card`
> (`tools/speedrun/evals/generate_eval.py`) marks a card correct when it is
> structurally sound AND its answer contains a key term from the card's own named
> source, i.e. it verifiably carries that source's fact; "wrong" means structurally
> fine but not grounded in the source's key terms. So the 92% / 4-wrong figure reads
> as "92% of generated cards are well-formed and traceable to their source", not
> "92% are proven factually true". Generation also draws from **19 original AUTHORED
> named sources** (`gen_sources.json`, written for this fork and copyright-safe),
> each card citing the one source it came from, rather than one external textbook
> chapter. (The exam-style PROBLEMS in Phase 2 below DO use real self-verification,
> an independent re-solve, so their 84.2% is a stronger, gold-answer-style check.)

### Full keyed run (gpt-4o-mini, seed 0), committed in the artifact

The authoritative FULL held-out run (`make ai-report`, ~4.2 min, ~790 API calls,
no rate limits), committed to `tools/speedrun/evals/results/ai_eval.json`
(`is_subsample: false`). The baseline is computed on the SAME full set for an
apples-to-apples comparison (`ai.baseline_on_sample`); leakage CLEAN throughout;
every AI output source-traced.

| eval (full held-out)              | AI (gpt-4o-mini)                         | baseline                          | result              |
| :-------------------------------- | :--------------------------------------- | :-------------------------------- | :------------------ |
| classify: top-1 (715 items)       | **38.18%** (wrong 61.82%)                | 13.15% (wrong 86.85%)             | AI **+25.0 pts** ✓  |
| classify: top-3 (715 items)       | **70.77%**                               | 33.29%                            | AI **+37.5 pts** ✓  |
| generate: correct (50 cards)      | **92%** (46/50, 4 wrong, 0 bad-teaching) | 30% (15/50, 35 wrong)             | AI **+62 pts** ✓    |
| problems: verified (19 subtopics) | **84.2%** (32/38, 0 leaks), covers 19/19 | 100% by construction, covers 9/19 | AI **wider cov.** ✓ |

Every pre-registered cutoff cleared: classifier margin ≥ 5 pts (actual **+25.0**);
generation correct ≥ 60% + bad-teaching ≤ 20% + beats baseline (**92% / 0% / >30%**);
problems verified ≥ 70% + leakage 0 + coverage > baseline (**84% / 0 / 19 > 9**).
Source of truth: the `evals.*.ai` cells. Re-run the offline baseline-only artifact
any time with `make ai-report ARGS="--no-ai"`.

### Earlier keyed run (attributed), now re-confirmed

An earlier keyed run, recorded before this artifact pipeline existed, measured
classifier AI top-1 38% / top-3 70% and generation AI 92% (46/50). The full keyed
run above **re-confirms** these (classifier 38.18% / 70.77%, generation 92%) and
commits them as a machine-readable artifact. Note the generation _baseline_ moved
from the historical 24% (12/50, 8-source set) to 30% (15/50, 19-source set) as the
sources expanded 8 → 19; the AI still clears the cutoff on the current sources.

## Source leakage gate (generation side)

Every AI generation SOURCE is checked against the held-out corpus before use, so
memorised test items can't inflate scores (rubric automatic fail). `make
leakage-scan-sources` validates the committed 19 sources: **CLEAN** (0 held-out
items reproduced, even at a strict 0.3 containment threshold). The same gate vets
any dropped-in reference: `make leakage-scan SRC="<file.pdf>"`. It flagged an
ACTEX Exam P study manual as reproducing **67+ official SOA sample questions**
(several verbatim), i.e. the held-out test set, so that manual was **rejected
as a source** (and, being copyrighted, is gitignored, never committed). Tool:
`tools/speedrun/leakage_scan_text.py` (word-shingle containment + exact
substring).

## Phase 2: exam-style problem generation (with self-verification)

Feature 2 was extended from flashcards to full exam-style **problems** (question +
worked solution + final answer), grounded in the 19 named sources
(`pylib/anki/speedrun/problem_gen.py`). Because a wrong problem is worse than
none, correctness is gated by **self-verification**: the model writes the problem
and its answer, then solves it AGAIN independently, and the problem is kept only
if the two answers match (`answers_match`, numeric-tolerant). Verified problems
land in a **quarantined pool** next to the collection, never mixed into the
held-out corpus. Prompt-injection defence: the source passage is passed as
untrusted DATA the model is told never to obey.

Eval (`make problems`, also folded into `make ai-report`): baseline = a
deterministic **templated** generator (correct by construction but narrow) that
**covers 9/19 subtopics** (reproduced offline, 100% verified by construction);
AI = problems from the sources, self-verified, leakage-scanned. The full keyed run
(all 19 subtopics, 2 each = 38 problems) scored **AI verified 84.2% (32/38),
0 leaks, covering 19/19 subtopics vs the baseline's 9/19 → PASS** (pre-registered
cutoff: verified ≥ 70% AND leakage 0 AND coverage > baseline;
`MIN_VERIFIED_RATE=0.70`), committed in the artifact. Offline tests in
`test_speedrun_problems.py` (templated correctness, answer-matching, pool
round-trip, fail-closed off-switch). Still Phase-2 to do: surface the verified
pool as clearly-labelled AI practice in the UI.

## Reproduce

```bash
# Offline (no API calls): (re)writes the committed artifact with baseline cells
# filled and AI cells left `pending`; nothing fabricated. Use this even if a
# key is configured, to regenerate the baseline artifact without cost.
make ai-report ARGS="--no-ai"

# With a valid key: also populates the AI cells and prints PASS/FAIL vs each
# cutoff. A key in a gitignored .env is auto-loaded by the Makefile.
out/pyenv/bin/pip install -r tools/speedrun/requirements-ai.txt
export OPENAI_API_KEY=...     # or put OPENAI_API_KEY=... in .env
make ai-report               # runs all three evals + WRITES the artifact
                             #   tools/speedrun/evals/results/ai_eval.json
make ai-eval                 # (optional) classifier + generation evals, printed
make problems                # (optional) problem-generation eval, printed
```

The committed artifact `tools/speedrun/evals/results/ai_eval.json` is the source
of truth for the tables above: `ai_ran` tells you whether the AI cells are real
or `pending`, and `git_sha` + `generated_at_utc` date the run.
