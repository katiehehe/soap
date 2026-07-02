# SOA Exam P "Speedrun" convenience targets.
# Build the app first with `./run` or `./ninja pylib qt` so out/pyenv exists.

PYENV := out/pyenv/bin/python
PYPATH := pylib:out/pylib
ARGS ?=

.PHONY: bench crash-test calibration

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
