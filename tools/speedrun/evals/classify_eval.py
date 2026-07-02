#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Subtopic-classifier eval harness + keyword baseline (Friday AI setup).

    out/pyenv/bin/python tools/speedrun/evals/classify_eval.py [gold.json]

The keyword baseline ranks the 19 official subtopics by word overlap between a
question and each subtopic's curated terms. It has NO dependencies, so it always
runs and gives the bar that Friday's AI classifier must beat (see
``docs/ai-features-prd.md``). Deterministic: same gold set -> same numbers.

Gold-set format (JSON): {"items": [{"question": "...", "subtopic": "subtopic::u::s"}, ...]}.
Keep held-out gold items OUT of any AI training/index (run the leakage scan).
"""

from __future__ import annotations

import json
import os
import re
import sys

# Curated keyword hints per subtopic tag, drawn from the official 2026-05
# learning outcomes. Extend these as the gold set grows.
SUBTOPIC_KEYWORDS: dict[str, list[str]] = {
    "subtopic::general::sets_axioms": ["set", "sample space", "event", "axiom", "venn"],
    "subtopic::general::combinatorics": [
        "combination",
        "permutation",
        "choose",
        "arrange",
        "count",
    ],
    "subtopic::general::independence": [
        "independent",
        "mutually exclusive",
        "disjoint",
    ],
    "subtopic::general::add_mult_rules": [
        "addition rule",
        "multiplication rule",
        "union",
    ],
    "subtopic::general::conditional": ["conditional", "given"],
    "subtopic::general::bayes": ["bayes", "total probability", "posterior", "prior"],
    "subtopic::univariate::rv_basics": [
        "pdf",
        "cdf",
        "density",
        "cumulative",
        "random variable",
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
    ],
    "subtopic::univariate::continuous_dists": [
        "exponential",
        "normal",
        "gamma",
        "beta",
        "uniform",
    ],
    "subtopic::univariate::insurance_apps": [
        "deductible",
        "coinsurance",
        "policy limit",
        "claim",
        "inflation",
    ],
    "subtopic::multivariate::joint_distributions": ["joint", "bivariate"],
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


def evaluate(items: list[dict[str, str]]) -> dict[str, float]:
    """Top-1 and top-3 accuracy of the keyword baseline over gold items."""
    top1 = 0
    top3 = 0
    for item in items:
        ranked = [tag for tag, _ in rank(item["question"])]
        gold = item["subtopic"]
        if ranked and ranked[0] == gold:
            top1 += 1
        if gold in ranked[:3]:
            top3 += 1
    n = len(items) or 1
    return {"n": len(items), "top1": top1 / n, "top3": top3 / n}


def main() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    default_gold = os.path.join(here, "gold", "classify_gold.example.json")
    path = sys.argv[1] if len(sys.argv) > 1 else default_gold
    with open(path, encoding="utf-8") as f:
        gold = json.load(f)
    items = gold.get("items", [])
    result = evaluate(items)
    print(f"gold set: {path}")
    print(f"items: {result['n']}")
    print(f"keyword baseline  top-1: {result['top1']:.0%}  top-3: {result['top3']:.0%}")
    print("Friday: add the AI classifier here and require it to beat these numbers.")


if __name__ == "__main__":
    main()
