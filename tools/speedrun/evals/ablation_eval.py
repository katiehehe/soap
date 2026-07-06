#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Study-feature ablation (rubric section 8): RUN the three builds.

Feature under test: the WITHIN-UNIT interleaving tier of the three-tier
mastery-gated scheduler. Builds: Full / Ablated (tier removed) / Plain Anki.
Pre-registered in docs/study-feature-ablation.md. Metric: accuracy on held-out
confusable exam-style questions, at EQUAL study time.

This is a seeded simulation on the labelled synthetic persona cohort, engineered
so it cannot smuggle in the answer:

- study time is held equal (identical reps per subtopic in every build), so only
  the interleaving ORDER differs;
- the sole build-dependent term is a discrimination boost with one explicit knob
  ``disc_gain``; we sweep it FROM ZERO, so the null is always reported;
- at disc_gain = 0 the three builds must coincide (fair-test sanity).

The real effect size for real students is unknown; this reports the experiment,
the null, and the sensitivity to the assumed mechanism, not a measured claim.

Usage:
    out/pyenv/bin/python tools/speedrun/evals/ablation_eval.py [--students 60] [--seed 0]
Or via `make ablation`.
"""

from __future__ import annotations

import argparse
import os
import sys

_REPO = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
for _p in (os.path.join(_REPO, "pylib"), os.path.join(_REPO, "out", "pylib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from anki.speedrun.ablation import (  # noqa: E402
    BUILDS,
    build_sequence,
    evaluate_all,
    rep_counts,
    within_unit_interleaving,
)
from anki.speedrun.evalsplit import find_leaks  # noqa: E402
from anki.speedrun.paraphrase import load_paraphrase_cards  # noqa: E402
from anki.speedrun.persona import synthetic_cohort  # noqa: E402
from anki.speedrun.soa_sample import load_corpus  # noqa: E402

# Effect sizes to sweep (logits). 0.0 is the null; the rest are an assumed
# mechanism's sensitivity, NOT a measured value.
DISC_GAINS = (0.0, 0.5, 1.0, 1.5, 2.0)
# Reference effect used to state whether the pre-registered direction held.
REFERENCE_GAIN = 1.0


def _equal_study_ok() -> bool:
    counts = {b: rep_counts(build_sequence(b)) for b in BUILDS}
    ref = counts["full"]
    return all(counts[b] == ref for b in BUILDS)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--students", type=int, default=60)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    corpus = load_corpus()
    items = corpus.items
    cohort = synthetic_cohort(args.students, seed=args.seed)
    provenance = "official SOA" if corpus.is_real_soa else "original fallback"

    print("=" * 76)
    print("STUDY-FEATURE ABLATION (section 8): within-unit interleaving tier")
    print("Builds: Full / Ablated (tier removed) / Plain. Metric: accuracy on")
    print(
        f"{len(items)} held-out exam-style questions ({corpus.source}, {provenance})."
    )
    print(
        f"SYNTHETIC cohort of {args.students} students (seed {args.seed}). Not real students."
    )
    print("=" * 76)

    # Equal study time is the invariant that keeps the test fair.
    if not _equal_study_ok():
        print("\nABORT: builds do not share an identical study budget (bug).")
        return 1
    print("\nEqual study time: CONFIRMED. Every build studies the same reps per")
    print("subtopic; only the interleaving order differs.")

    # Held-out / leakage: the exam questions must not be near-copies of the study
    # material (the committed study cards), or 'held-out' would be a fiction.
    study = [(c.id, f"{c.fact} {c.card_prompt}") for c in load_paraphrase_cards()]
    evalq = [(it.id, it.question) for it in items]
    leaks = find_leaks(study, evalq)
    print(
        f"Leakage scan (study cards vs eval questions): "
        f"{'CLEAN' if not leaks else f'{len(leaks)} LEAK(S), aborting'}"
    )
    if leaks:
        return 1

    # Interleaving exposure per build (the mechanism's input).
    print("\nWithin-unit interleaving exposure (fraction of adjacent sibling pairs):")
    for b in BUILDS:
        print(f"    {b:8s}: {within_unit_interleaving(build_sequence(b)):.3f}")

    # The sweep, including the null at disc_gain = 0.
    print("\nHeld-out accuracy by build across the assumed effect size (disc_gain):")
    print(f"    {'disc_gain':>9} | {'Full':>18} | {'Ablated':>18} | {'Plain':>18}")
    print("    " + "-" * 72)
    reference: dict[str, float] = {}
    for g in DISC_GAINS:
        res = evaluate_all(cohort, items, g)
        if g == REFERENCE_GAIN:
            reference = {b: res[b].accuracy_mean for b in BUILDS}

        def cell(b: str) -> str:
            r = res[b]
            return f"{r.accuracy_mean:.3f} [{r.accuracy_lo:.2f}-{r.accuracy_hi:.2f}]"

        tag = "  (NULL)" if g == 0.0 else ""
        print(
            f"    {g:9.1f} | {cell('full'):>18} | {cell('ablated'):>18} | "
            f"{cell('plain'):>18}{tag}"
        )

    # Verdicts.
    null_res = evaluate_all(cohort, items, 0.0)
    null_spread = max(null_res[b].accuracy_mean for b in BUILDS) - min(
        null_res[b].accuracy_mean for b in BUILDS
    )
    print("\n" + "-" * 76)
    print(
        f"NULL check (disc_gain = 0): build spread = {null_spread:.4f} "
        f"({'PASS, builds coincide with no assumed effect' if null_spread < 1e-9 else 'FAIL, bias in the harness'})"
    )

    if reference:
        full, ablated, plain = (
            reference["full"],
            reference["ablated"],
            reference["plain"],
        )
        direction = full >= ablated >= plain
        print(
            f"\nPre-registered direction (Full >= Ablated >= Plain) at disc_gain="
            f"{REFERENCE_GAIN}: {'HELD' if direction else 'NOT held (reportable null/reversal)'}"
        )
        print(
            f"    Full {full:.3f}  vs  Ablated {ablated:.3f}  "
            f"(within-unit tier = {full - ablated:+.3f})  vs  Plain {plain:.3f}"
        )
    print(
        "\nHonest reading: with NO assumed mechanism (disc_gain=0) the builds are\n"
        "identical, so this run does not, and cannot, prove the feature works. It shows\n"
        "a fair, reproducible experiment: equal study time, held-out leakage-clean\n"
        "questions, the ablation isolating the within-unit tier (Full vs Ablated), and\n"
        "the effect size that a real study-log run would need to measure."
    )
    print("Reproducible: deterministic given --students and --seed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
