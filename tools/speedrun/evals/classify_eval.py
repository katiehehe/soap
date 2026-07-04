#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Subtopic-classifier eval harness + keyword baseline (Friday AI, Feature 1).

    out/pyenv/bin/python tools/speedrun/evals/classify_eval.py [gold.json]

The held-out gold set is the sample-item corpus (``anki.speedrun.soa_sample`` —
the official SOA sample questions when present, else the committed original
fallback). The keyword baseline ranks the 19 official subtopics by word overlap
between a question and each subtopic's curated terms; it has NO dependencies, so
it always runs and gives the bar the AI classifier must beat.

When ``OPENAI_API_KEY`` is set (or another provider is configured), the AI
classifier (``anki.speedrun.ai.classify_subtopic_core``) is run on the SAME gold
set and reported side by side, with a pre-registered pass bar. Everything is
deterministic given the gold set, and the leakage scan runs over the AI inputs
(rubric 7e) so no gold item leaks into the classifier's index.
"""

from __future__ import annotations

import json
import os
import random
import re
import sys

_REPO = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
for _p in (os.path.join(_REPO, "pylib"), os.path.join(_REPO, "out", "pylib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from anki.speedrun.evalsplit import find_leaks  # noqa: E402
from anki.speedrun.soa_sample import gold_items, load_corpus  # noqa: E402

# Pre-registered pass bar (set BEFORE looking at AI results): the AI classifier
# must beat the keyword baseline's top-1 accuracy by at least this margin, or we
# ship the baseline and say so (AI-traceability rule: beat a simpler method).
AI_TOP1_MARGIN = 0.05

# Curated keyword hints per subtopic tag, drawn from the official 2026-05
# learning outcomes. This is the baseline's index AND (with the outcome text) the
# only "training" input the AI classifier is allowed — gold items never leak in.
SUBTOPIC_KEYWORDS: dict[str, list[str]] = {
    "subtopic::general::sets_axioms": ["set", "sample space", "event", "axiom", "venn"],
    "subtopic::general::combinatorics": [
        "combination",
        "permutation",
        "choose",
        "arrange",
        "count",
        "committee",
    ],
    "subtopic::general::independence": [
        "independent",
        "mutually exclusive",
        "disjoint",
        "series",
    ],
    "subtopic::general::add_mult_rules": [
        "addition rule",
        "multiplication rule",
        "union",
        "without replacement",
    ],
    "subtopic::general::conditional": ["conditional", "given"],
    "subtopic::general::bayes": ["bayes", "total probability", "posterior", "prior"],
    "subtopic::univariate::rv_basics": [
        "pdf",
        "cdf",
        "density",
        "cumulative",
        "random variable",
        "constant",
    ],
    "subtopic::univariate::expectation": [
        "expected value",
        "expectation",
        "moment",
        "mean",
        "median",
    ],
    "subtopic::univariate::variance": [
        "variance",
        "standard deviation",
        "coefficient of variation",
    ],
    "subtopic::univariate::discrete_dists": [
        "binomial",
        "poisson",
        "geometric",
        "hypergeometric",
        "negative binomial",
        "trials",
        "successes",
    ],
    "subtopic::univariate::continuous_dists": [
        "exponential",
        "normal",
        "gamma",
        "beta",
        "uniform",
        "lifetime",
    ],
    "subtopic::univariate::insurance_apps": [
        "deductible",
        "coinsurance",
        "policy limit",
        "claim",
        "inflation",
        "loss",
        "payment",
    ],
    "subtopic::multivariate::joint_distributions": [
        "joint",
        "bivariate",
        "unit square",
    ],
    "subtopic::multivariate::marginal_conditional": [
        "marginal",
        "conditional distribution",
    ],
    "subtopic::multivariate::joint_moments": [
        "double expectation",
        "tower",
        "conditional expectation",
    ],
    "subtopic::multivariate::covariance_correlation": [
        "covariance",
        "correlation",
        "rho",
    ],
    "subtopic::multivariate::order_statistics": [
        "order statistic",
        "minimum",
        "maximum",
    ],
    "subtopic::multivariate::linear_combinations": [
        "linear combination",
        "sum of",
        "aggregate",
    ],
    "subtopic::multivariate::clt": [
        "central limit",
        "sample mean",
        "approximate",
        "normal approximation",
    ],
}


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.lower()))


def rank(
    question: str, keywords: dict[str, list[str]] | None = None
) -> list[tuple[str, float]]:
    """Rank subtopics for a question by normalized keyword overlap (desc)."""
    table = keywords or SUBTOPIC_KEYWORDS
    q = _tokens(question)
    scored: list[tuple[str, float]] = []
    for tag, words in table.items():
        terms: set[str] = set()
        for w in words:
            terms |= _tokens(w)
        overlap = len(q & terms)
        scored.append((tag, overlap / (len(terms) or 1)))
    scored.sort(key=lambda item: (-item[1], item[0]))
    return scored


def evaluate(items: list[dict[str, str]], ranker=None) -> dict[str, float]:
    """Top-1 and top-3 accuracy of a ranker over gold items. ``ranker`` maps a
    question to a ranked list of subtopic tags; defaults to the keyword baseline."""
    ranker = ranker or (lambda q: [tag for tag, _ in rank(q)])
    top1 = 0
    top3 = 0
    for item in items:
        ranked = ranker(item["question"])
        gold = item["subtopic"]
        if ranked and ranked[0] == gold:
            top1 += 1
        if gold in ranked[:3]:
            top3 += 1
    n = len(items) or 1
    return {"n": len(items), "top1": top1 / n, "top3": top3 / n}


def leakage_over_ai_inputs(items: list[dict[str, str]]) -> int:
    """Rubric 7e over AI inputs: no gold item may be a near-copy of the
    classifier's index (the per-subtopic keyword terms + outcome text). Returns
    the number of leaks (0 = clean)."""
    index = [(tag, " ".join(words)) for tag, words in SUBTOPIC_KEYWORDS.items()]
    test = [(str(i), it["question"]) for i, it in enumerate(items)]
    return len(find_leaks(index, test))


def _ai_ranker():
    """Return an AI ranker (question -> ranked tags) if a provider is configured,
    else None. The AI classifier is off in the app by default; this dev harness
    runs it explicitly to MEASURE it, so it bypasses the collection off-switch
    and calls the provider-backed core directly."""
    try:
        from anki.speedrun.ai import available_provider, classify_subtopic_core
    except Exception:  # noqa: BLE001 - AI module optional / not built yet
        return None
    provider = available_provider()
    if provider is None:
        return None

    def ranker(question: str) -> list[str]:
        return [tag for tag, _score, _src in classify_subtopic_core(question, provider)]

    return ranker, provider


def collect_results(run_ai: bool = True, limit: int = 0, seed: int = 0) -> dict:
    """Machine-readable record for the committed AI-eval artifact (ai_eval.json).

    The keyword baseline is always computed on the FULL held-out set; the AI cell
    is populated only when a provider/key is configured AND ``run_ai`` is True,
    else left ``None`` with a ``pending`` verdict — no AI number is ever
    fabricated here. Pass ``run_ai=False`` to force the offline/baseline-only
    record.

    ``limit`` caps the AI side to a seeded random SUBSAMPLE of the held-out items
    (cost control for a keyed smoke run). Sampling only chooses which held-out
    items to *evaluate* — it never touches the classifier's index / training, so
    there is no leakage. When it samples, the AI cell carries ``is_subsample``,
    ``sample_size``, ``seed`` and an apples-to-apples ``baseline_on_sample``.
    """
    corpus = load_corpus()
    items = gold_items()
    leaks = leakage_over_ai_inputs(items)
    base = evaluate(items)  # FULL keyword baseline (no API)

    ai_cell: dict | None = None
    ai_ran = False
    verdict = "pending: run `make ai-report` with OPENAI_API_KEY to populate"
    ai = _ai_ranker() if run_ai else None
    if ai is not None:
        from concurrent.futures import ThreadPoolExecutor

        from anki.speedrun.ai import DEFAULT_OPENAI_MODEL

        ranker, provider = ai
        is_sub = bool(limit) and limit < len(items)
        sample = random.Random(seed).sample(items, limit) if is_sub else items
        base_sample = evaluate(sample)  # same-sample keyword baseline (no API)

        # The AI ranker makes one API call per item; run them concurrently (they
        # are I/O-bound) so the full 715-item held-out set completes in minutes,
        # not ~15 min sequentially. A failed call returns [] (counts as wrong —
        # this can only ever LOWER the AI score, never inflate it).
        def _safe_rank(question: str) -> list[str]:
            try:
                return ranker(question)
            except Exception:  # noqa: BLE001 — a failed classify counts as wrong
                return []

        questions = [it["question"] for it in sample]
        with ThreadPoolExecutor(max_workers=8) as pool:
            ranked = list(pool.map(_safe_rank, questions))
        ranked_by_q = dict(zip(questions, ranked))
        ai_res = evaluate(sample, ranker=lambda q: ranked_by_q.get(q, []))
        margin = ai_res["top1"] - base_sample["top1"]
        ai_ran = True
        ai_cell = {
            "provider": provider,
            "model": DEFAULT_OPENAI_MODEL,
            "is_subsample": is_sub,
            "sample_size": len(sample),
            "seed": seed,
            "top1": round(ai_res["top1"], 4),
            "top3": round(ai_res["top3"], 4),
            "wrong_rate_top1": round(1.0 - ai_res["top1"], 4),
            "baseline_on_sample": {
                "top1": round(base_sample["top1"], 4),
                "top3": round(base_sample["top3"], 4),
                "wrong_rate_top1": round(1.0 - base_sample["top1"], 4),
            },
            "margin_top1_vs_baseline_on_sample": round(margin, 4),
        }
        scope = f"sample n={len(sample)}" if is_sub else "full set"
        beat = margin >= AI_TOP1_MARGIN
        verdict = (
            f"{'PASS' if beat else 'BELOW bar'} on {scope}: AI top-1 "
            f"{ai_res['top1']:.0%} vs baseline {base_sample['top1']:.0%} "
            f"(margin {margin:+.0%})"
        )

    return {
        "name": "Feature 1 — subtopic classifier",
        "make_target": "make classify",
        "baseline_vs": "keyword overlap",
        "dataset": {
            "gold_set": corpus.source,
            "is_real_soa": corpus.is_real_soa,
            "held_out_items": len(items),
            "num_subtopics": 19,
        },
        "cutoff": {"ai_top1_margin": AI_TOP1_MARGIN},
        "leakage_over_ai_inputs": {"leaks": leaks, "clean": leaks == 0},
        "baseline": {
            "method": "keyword overlap",
            "top1": round(base["top1"], 4),
            "top3": round(base["top3"], 4),
            "wrong_rate_top1": round(1.0 - base["top1"], 4),
        },
        "ai": ai_cell,
        "ai_ran": ai_ran,
        "verdict": verdict,
    }


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if path:
        with open(path, encoding="utf-8") as f:
            items = json.load(f).get("items", [])
        provenance = path
    else:
        corpus = load_corpus()
        items = gold_items()
        provenance = f"{corpus.source} ({'official SOA' if corpus.is_real_soa else 'original fallback'})"

    print(f"gold set: {provenance}")
    print(f"items: {len(items)}")

    leaks = leakage_over_ai_inputs(items)
    print(
        f"leakage over AI inputs (7e): {'CLEAN' if leaks == 0 else f'{leaks} LEAK(S)'}"
    )
    if leaks:
        print(
            "ABORT: gold items leak into the classifier index; fix before evaluating."
        )
        sys.exit(1)

    base = evaluate(items)
    print(f"keyword baseline   top-1: {base['top1']:.0%}   top-3: {base['top3']:.0%}")

    ai = _ai_ranker()
    if ai is None:
        print(
            "AI classifier: not run (no provider/key configured). Set OPENAI_API_KEY "
            "to run the AI side and compare. The app still classifies with the "
            "baseline, and still scores with AI off."
        )
        return
    ranker, provider = ai
    ai_result = evaluate(items, ranker=ranker)
    print(
        f"AI classifier ({provider})  top-1: {ai_result['top1']:.0%}   top-3: {ai_result['top3']:.0%}"
    )
    margin = ai_result["top1"] - base["top1"]
    beat = margin >= AI_TOP1_MARGIN
    print(
        f"pre-registered bar: AI top-1 must beat baseline by >= {AI_TOP1_MARGIN:.0%} "
        f"(actual margin {margin:+.0%}) -> {'PASS, ship AI' if beat else 'FAIL, ship baseline'}"
    )


if __name__ == "__main__":
    main()
