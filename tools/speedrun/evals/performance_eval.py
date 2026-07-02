#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Performance model (score-model Step 2) eval on a SYNTHETIC fixture.

Generates a deterministic, clearly-labelled synthetic dataset of disguised
exam-style questions (correctness driven by mastery / difficulty / timing /
coverage plus seeded noise), runs the seeded held-out pipeline, scans for
train/test leakage, and reports held-out accuracy + AUC + calibration against a
majority-class baseline.

This validates the PIPELINE end to end. The numbers are on synthetic data and are
NOT a real student result. On real data (a labelled held-out set of disguised
questions) the same pipeline runs unchanged; until that data exists the app shows
"performance: not yet measured" and never fabricates a number.

Usage:
    out/pyenv/bin/python tools/speedrun/evals/performance_eval.py [--n 400] [--seed 0]
Or via `make performance`.
"""

from __future__ import annotations

import argparse
import math
import os
import random
import sys

_REPO = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
for _p in (os.path.join(_REPO, "pylib"), os.path.join(_REPO, "out", "pylib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from anki.speedrun.evalsplit import find_leaks, train_test_split  # noqa: E402
from anki.speedrun.performance import PerformanceExample, run_pipeline  # noqa: E402


def synthetic_dataset(n: int, seed: int) -> list[PerformanceExample]:
    """Deterministic synthetic questions. Correctness follows a known logistic
    relationship in the four features plus seeded Bernoulli noise, so a correct
    pipeline should recover a well-calibrated, better-than-baseline model."""
    rng = random.Random(seed)
    out: list[PerformanceExample] = []
    for i in range(n):
        mastery = rng.random()
        difficulty = rng.random()
        response_time = rng.random()
        coverage = rng.random()
        logit = -3.0 + 5.0 * mastery - 2.0 * difficulty + coverage - response_time
        p = 1.0 / (1.0 + math.exp(-logit))
        correct = 1 if rng.random() < p else 0
        out.append(
            PerformanceExample(
                id=f"syn-{i}",
                mastery=mastery,
                difficulty=difficulty,
                response_time=response_time,
                coverage=coverage,
                correct=correct,
                text=f"[synthetic fixture] disguised exam-style question #{i} (seed {seed})",
            )
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=400)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--test-frac", type=float, default=0.3)
    args = parser.parse_args()

    print("=" * 72)
    print("SYNTHETIC FIXTURE — validates the performance pipeline end to end.")
    print("These numbers are NOT a real student measurement. On real data the")
    print("same pipeline runs unchanged; until then the app abstains.")
    print("=" * 72)

    data = synthetic_dataset(args.n, args.seed)

    # Leakage scan on the exact seeded split the pipeline uses (challenge 7e).
    by_id = {e.id: e for e in data}
    train_ids, test_ids = train_test_split(
        list(by_id), test_frac=args.test_frac, seed=args.seed
    )
    leaks = find_leaks(
        [(i, by_id[i].text) for i in train_ids],
        [(i, by_id[i].text) for i in test_ids],
    )
    print(
        f"Leakage scan: {'CLEAN' if not leaks else f'{len(leaks)} LEAK(S) — aborting'}"
    )
    if leaks:
        return 1

    result = run_pipeline(data, seed=args.seed, test_frac=args.test_frac)
    if result.status != "ok":
        print(
            f"NOT ENOUGH DATA: held-out set too small ({result.n_test}); no metric "
            "shown (give-up rule)."
        )
        return 0

    cal = result.calibration
    print(f"\nHeld-out performance (train {result.n_train} / test {result.n_test}):")
    print(f"  accuracy       : {result.accuracy:.3f}")
    print(f"  AUC            : {result.auc:.3f}")
    print(
        f"  baseline (majority class): {result.baseline_accuracy:.3f}   "
        f"-> beats baseline: {result.beats_baseline}"
    )
    if cal is not None and cal.status == "ok":
        print(
            f"  calibration    : Brier {cal.brier:.3f}, log loss {cal.log_loss:.3f}, "
            f"ECE {cal.ece:.3f} (base rate {cal.base_rate:.3f})"
        )
    print("\nReproducible: deterministic given --n and --seed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
