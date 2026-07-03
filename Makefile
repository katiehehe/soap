# SOA Exam P "Speedrun" convenience targets.
# Build the app first with `./run` or `./ninja pylib qt` so out/pyenv exists.

PYENV := out/pyenv/bin/python
PYPATH := pylib:out/pylib
ARGS ?=

# Load local secrets (e.g. OPENAI_API_KEY) from a gitignored .env if present, so
# the AI evals pick up the key without you ever typing it in the terminal.
# Format: one KEY=value per line, e.g.  OPENAI_API_KEY=sk-...
-include .env
export

.PHONY: bench crash-test calibration performance seed-persona practice-test classify ai-eval sync-test paraphrase ablation

# 7h: load a large deck and report p50/p95/worst per action.
bench:
	PYTHONPATH=$(PYPATH) $(PYENV) tools/speedrun/bench.py $(ARGS)

# 7g: kill the app mid-review repeatedly and verify zero corruption.
crash-test:
	PYTHONPATH=$(PYPATH) $(PYENV) tools/speedrun/crash_test.py $(ARGS)

# Score-model Step 1: memory (FSRS) calibration on held-out reviews. Abstains
# honestly when there is too little history. Point at a real collection with
# `make calibration ARGS="--col /path/to/collection.anki2"`.
calibration:
	PYTHONPATH=$(PYPATH) $(PYENV) tools/speedrun/evals/memory_calibration.py $(ARGS)

# Score-model Step 2: performance-model pipeline. Default = synthetic fixture;
# `ARGS="--persona"` runs it on the real held-out item corpus x a synthetic
# cohort (seeded held-out split, leakage scan, calibration vs a baseline).
# Validates the pipeline; persona/fixture numbers are synthetic, not a real
# student result.
performance:
	PYTHONPATH=$(PYPATH) $(PYENV) tools/speedrun/evals/performance_eval.py $(ARGS)

# Build a DEMO collection driven by the seeded synthetic persona (real engine,
# synthetic history). Writes out/demo-persona.anki2; open it in the app.
seed-persona:
	PYTHONPATH=$(PYPATH) $(PYENV) tools/speedrun/seed_persona.py $(ARGS)

# Assemble + grade a section-weighted practice test for the demo persona and
# print the readiness band it produces (honesty-gated).
practice-test:
	PYTHONPATH=$(PYPATH) $(PYENV) tools/speedrun/evals/practice_test_demo.py $(ARGS)

# Friday AI, Feature 1: subtopic-classifier eval (keyword baseline; AI side runs
# when OPENAI_API_KEY is set) on the held-out gold corpus.
classify:
	PYTHONPATH=$(PYPATH) $(PYENV) tools/speedrun/evals/classify_eval.py $(ARGS)

# Friday AI gate: run every AI eval (classify + generate) with baselines.
ai-eval:
	PYTHONPATH=$(PYPATH) $(PYENV) tools/speedrun/evals/classify_eval.py
	PYTHONPATH=$(PYPATH) $(PYENV) tools/speedrun/evals/generate_eval.py $(ARGS)

# Sync test (rubric 7b): 10 offline reviews on each of two collections through a
# local sync server; assert all 20 land once, none doubled/lost.
sync-test:
	PYTHONPATH=$(PYPATH) $(PYENV) tools/speedrun/sync_test.py $(ARGS)

# Paraphrase test (rubric 7d): 30 cards x 2 reworded exam-style questions each;
# compare card recall (memory) vs reworded accuracy (performance) and report the
# gap. Includes a copycat control that must read COPYING. Synthetic cohort.
paraphrase:
	PYTHONPATH=$(PYPATH) $(PYENV) tools/speedrun/evals/paraphrase_eval.py $(ARGS)

# Study-feature ablation (section 8): run the three builds (Full / Ablated /
# Plain) at equal study time and report held-out accuracy across an assumed
# effect-size sweep, including the null (disc_gain=0). Synthetic cohort.
ablation:
	PYTHONPATH=$(PYPATH) $(PYENV) tools/speedrun/evals/ablation_eval.py $(ARGS)
