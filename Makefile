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

.PHONY: bench crash-test calibration performance seed-persona practice-test classify ai-eval ai-report sync-test paraphrase ablation demo leakage-scan leakage-scan-sources problems phone phone-install phone-rebuild phone-rebuild-dry

# Boot the phone emulator (Medium_Phone) and open AnkiDroid — our shared-engine
# fork. `make phone` just boots + opens; `make phone-install` also reinstalls the
# freshest built APK first (use after rebuilding it in the Anki-Android checkout).
# Then tap the ☰ menu → Exam readiness to see the three scores on the phone.
phone:
	tools/speedrun/phone.sh

phone-install:
	tools/speedrun/phone.sh --install

# One command to see a code change ON THE PHONE: overlays your working tree
# (incl. uncommitted changes) into the engine submodule, rebuilds the engine+UI
# .aar and the APK, then installs + opens. Slow (cross-compiles Rust) — for quick
# iteration use the desktop `./run`. `phone-rebuild-dry` just lists what would
# sync without building.
phone-rebuild:
	tools/speedrun/phone-rebuild.sh

phone-rebuild-dry:
	tools/speedrun/phone-rebuild.sh --dry-run

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

# Launch the desktop app straight into the populated demo persona (no manual
# studying, real collection untouched): every dashboard, the three signals with
# ranges, and the coloured concept map are live on open. Build first if needed
# with `./ninja pylib qt`.
demo:
	PYTHONPATH=$(PYPATH) $(PYENV) tools/speedrun/open_demo.py $(ARGS)

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

# Friday AI PROOF artifact: run all three AI evals (classifier / generation /
# problems) side by side and WRITE the committed machine-readable comparison to
# tools/speedrun/evals/results/ai_eval.json (dataset, pre-registered cutoffs,
# baseline accuracy + wrong-rate, git SHA, timestamp). Baseline/offline cells
# always fill; AI cells populate only when OPENAI_API_KEY is set (else null /
# "pending", never fabricated). This is the one command behind the doc's
# "AI beats a simpler baseline" table. NOTE: a key in .env is auto-loaded, so a
# plain `make ai-report` will make real API calls; use
# `make ai-report ARGS="--no-ai"` to (re)write the offline baseline artifact
# with the AI cells left pending (no key, no cost).
ai-report:
	PYTHONPATH=$(PYPATH) $(PYENV) tools/speedrun/evals/ai_eval_report.py $(ARGS)

# Phase 2: exam-style PROBLEM generation eval. Templated baseline (correct by
# construction) always runs; the AI side — problems generated from named sources,
# each self-verified by an INDEPENDENT re-solve, plus a leakage scan of the
# generated questions — runs when OPENAI_API_KEY is set, against a pre-registered
# cutoff. `--per-subtopic N` and `--subtopics N` (via ARGS) control cost.
problems:
	PYTHONPATH=$(PYPATH) $(PYENV) tools/speedrun/evals/problem_eval.py $(ARGS)

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

# Leakage gate (rubric 7e, generation side): assert no held-out item is
# reproduced in an AI generation SOURCE (verbatim or near-copy), or scores are
# inflated by memorisation. `leakage-scan-sources` validates the committed
# generation sources (the CI gate). `leakage-scan SRC=<file>` vets a dropped-in
# reference (PDF / notes) BEFORE it is ever used — this is what flagged the
# ACTEX manual as reproducing the official SOA sample questions.
leakage-scan-sources:
	PYTHONPATH=$(PYPATH) $(PYENV) tools/speedrun/leakage_scan_text.py --source pylib/anki/speedrun/gen_sources.json --threshold 0.3

leakage-scan:
	PYTHONPATH=$(PYPATH) $(PYENV) tools/speedrun/leakage_scan_text.py --source "$(SRC)" $(ARGS)
