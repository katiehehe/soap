#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Performance model (score-model Step 2) eval.

Two modes, both deterministic and leakage-checked, both clearly SYNTHETIC (never
a real student result):

- default: a fully synthetic fixture (correctness driven by a known logistic
  relationship in mastery / difficulty / timing / coverage plus seeded noise).
  Validates the PIPELINE end to end on tabular data.
- ``--persona``: the REAL held-out exam-style item corpus (``soa_sample``)
  crossed with a synthetic student **cohort** (``persona.synthetic_cohort``).
  Correctness comes from each student's latent skill vs each item's difficulty.
  The held-out split is BY ITEM (never by example), so no item's text appears in
  both train and test — the leakage scan enforces this.

On a real labelled held-out set of disguised questions the same pipeline runs
unchanged; until that data exists the app shows "performance: not yet measured"
and never fabricates a number.

Usage:
    out/pyenv/bin/python tools/speedrun/evals/performance_eval.py [--n 400] [--seed 0]
    out/pyenv/bin/python tools/speedrun/evals/performance_eval.py --persona [--students 40]
Or via `make performance` / `make performance ARGS="--persona"`.
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
from anki.speedrun.performance import (  # noqa: E402
    PerformanceExample,
    evaluate,
    run_pipeline,
    train_logistic,
)
from anki.speedrun.persona import (  # noqa: E402
    difficulty_num,
    p_correct,
    response_time_for,
    synthetic_cohort,
)
from anki.speedrun.soa_sample import load_corpus  # noqa: E402


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


def _mean_skill(persona) -> float:
    return sum(persona.skill.values()) / len(persona.skill)


def persona_examples(item_ids, cohort, items_by_id) -> list[PerformanceExample]:
    """Cohort x items -> one graded PerformanceExample per (student, item).
    Deterministic. ``coverage`` proxies each student's breadth via mean skill."""
    out: list[PerformanceExample] = []
    for persona in cohort:
        cov = min(1.0, max(0.4, _mean_skill(persona)))
        for iid in item_ids:
            it = items_by_id[iid]
            rt = response_time_for(persona, it.subtopic, it.difficulty)
            p = p_correct(persona, it.subtopic, it.difficulty, cov, rt)
            rng = random.Random(f"perf|{persona.seed}|{iid}")
            out.append(
                PerformanceExample(
                    id=f"{persona.name}|{iid}",
                    mastery=persona.skill_for(it.subtopic),
                    difficulty=difficulty_num(it.difficulty),
                    response_time=rt,
                    coverage=cov,
                    correct=1 if rng.random() < p else 0,
                    text=it.question,
                )
            )
    return out


def _report(result) -> None:
    if result.status != "ok":
        print(
            f"NOT ENOUGH DATA: held-out set too small ({result.n_test}); no metric "
            "shown (give-up rule)."
        )
        return
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


def run_persona(students: int, seed: int, test_frac: float) -> int:
    corpus = load_corpus()
    items_by_id = {it.id: it for it in corpus.items}
    provenance = "official SOA" if corpus.is_real_soa else "original fallback"
    print("=" * 72)
    print("PERSONA MODE — real held-out item corpus x a SYNTHETIC student cohort.")
    print(f"corpus: {corpus.source} ({provenance}); split BY ITEM (no item leakage).")
    print("These numbers measure the model on synthetic responses; NOT a real student.")
    print("=" * 72)

    # Held-out split BY ITEM (not by example), so an item's text can never sit in
    # both train and test.
    train_ids, test_ids = train_test_split(
        list(items_by_id), test_frac=test_frac, seed=seed
    )
    # Leakage scan over the unique item texts (rubric 7e).
    leaks = find_leaks(
        [(i, items_by_id[i].question) for i in train_ids],
        [(i, items_by_id[i].question) for i in test_ids],
    )
    print(
        f"Leakage scan (by item): {'CLEAN' if not leaks else f'{len(leaks)} LEAK(S) — aborting'}"
    )
    if leaks:
        return 1

    cohort = synthetic_cohort(students, seed=seed)
    train = persona_examples(train_ids, cohort, items_by_id)
    test = persona_examples(test_ids, cohort, items_by_id)
    model = train_logistic(train, seed=seed)
    result = evaluate(model, test, n_train=len(train), min_test=30, min_samples=30)
    print(
        f"\ncohort: {students} synthetic students x "
        f"{len(train_ids)} train / {len(test_ids)} held-out items"
    )
    _report(result)
    print("\nReproducible: deterministic given --students and --seed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=400)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--test-frac", type=float, default=0.3)
    parser.add_argument(
        "--persona", action="store_true", help="corpus x synthetic cohort"
    )
    parser.add_argument("--students", type=int, default=40)
    args = parser.parse_args()

    if args.persona:
        return run_persona(args.students, args.seed, args.test_frac)

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
    _report(result)
    print("\nReproducible: deterministic given --n and --seed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
