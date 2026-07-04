#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Exam-style PROBLEM generation eval (Phase 2 of Feature 2 / challenge 7f).

    out/pyenv/bin/python tools/speedrun/evals/problem_eval.py [--per-subtopic 2] [--subtopics 0]

- Baseline: the deterministic TEMPLATED generator (``problem_gen.templated_problems``)
  — correct BY CONSTRUCTION, but narrow (covers only the subtopics with a formula
  template). This is the simpler method the AI must beat, and the offline fallback.
- AI: problems generated from the NAMED sources (``gen_sources.json``); each is
  kept only if an INDEPENDENT re-solve matches its stated answer
  (self-verification = the "gold-check before a student sees it").
- Reports the AI verification pass-rate, syllabus coverage, and a leakage scan of
  the generated questions vs the held-out corpus, against a PRE-REGISTERED cutoff.
- Offline-safe: the baseline always runs; the AI side runs only with a key.
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

from anki.speedrun import load_topics  # noqa: E402
from anki.speedrun.ai import OpenAiClient, available_provider  # noqa: E402
from anki.speedrun.evalsplit import jaccard  # noqa: E402
from anki.speedrun.problem_gen import (  # noqa: E402
    ai_candidates,
    templated_problems,
    verify_problem,
)
from anki.speedrun.soa_sample import load_sample_items  # noqa: E402

# --- pre-registered cutoff (set BEFORE looking at any AI output) ----------
MIN_VERIFIED_RATE = 0.70  # ship AI problems only if >= 70% self-verify...
LEAK_THRESHOLD = 0.6  # ...AND none is a near-copy (Jaccard) of a held-out item...
# ...AND the AI covers more of the syllabus than the templated baseline.


def all_subtopics() -> list[str]:
    return [
        f"subtopic::{u['id']}::{s['id']}"
        for u in load_topics()["units"]
        for s in u["subtopics"]
    ]


def collect_results(
    per_subtopic: int = 2, subtopics: int = 0, run_ai: bool = True, seed: int = 0
) -> dict:
    """Machine-readable record for the committed AI-eval artifact (ai_eval.json).

    The templated baseline (correct by construction) coverage is always computed
    offline over ALL 19 subtopics; the AI cell — verified-rate, wrong-rate,
    coverage, leakage — is populated only when a provider/key is configured AND
    ``run_ai`` is True, else ``None`` with a ``pending`` verdict. No AI number is
    ever fabricated here. Pass ``run_ai=False`` to force the offline record.

    ``subtopics`` caps the AI side to the first N subtopics (cost control for a
    keyed smoke run); when it does, the AI cell is flagged ``is_subsample`` and
    carries an apples-to-apples ``baseline_on_sample`` (templated coverage over
    the same N subtopics).
    """
    all_subs = all_subtopics()
    subs = all_subs[:subtopics] if subtopics else all_subs
    base_cov_full = sum(1 for t in all_subs if templated_problems(t, 1))

    ai_cell: dict | None = None
    ai_ran = False
    verdict = "pending: run `make ai-report` with OPENAI_API_KEY to populate"
    provider = available_provider() if run_ai else None
    if provider is not None:
        from anki.speedrun.ai import DEFAULT_OPENAI_MODEL

        is_sub = bool(subtopics) and len(subs) < len(all_subs)
        client = OpenAiClient()
        held_out = load_sample_items()
        total = verified = ai_cov = leaks = 0
        for tag in subs:
            cands = ai_candidates(client, tag, per_subtopic)
            if cands:
                ai_cov += 1
            for c in cands:
                total += 1
                if verify_problem(client, c["question"], c["answer"]):
                    verified += 1
                worst = max(
                    (jaccard(c["question"], it.question) for it in held_out),
                    default=0.0,
                )
                if worst >= LEAK_THRESHOLD:
                    leaks += 1
        rate = verified / total if total else 0.0
        base_cov_sample = sum(1 for t in subs if templated_problems(t, 1))
        ai_ran = True
        ai_cell = {
            "provider": client.name,
            "model": DEFAULT_OPENAI_MODEL,
            "is_subsample": is_sub,
            "sample_size_subtopics": len(subs),
            "per_subtopic": per_subtopic,
            "seed": seed,
            "problems": total,
            "verified": verified,
            "verified_rate": round(rate, 4),
            "wrong_rate": round(1.0 - rate, 4),
            "coverage_subtopics": ai_cov,
            "leaks": leaks,
            "baseline_on_sample": {
                "subtopics": len(subs),
                "coverage_subtopics": base_cov_sample,
                "verified_rate": 1.0,
                "wrong_rate": 0.0,
            },
        }
        passed = rate >= MIN_VERIFIED_RATE and leaks == 0 and ai_cov > base_cov_sample
        scope = f"sample of {len(subs)} subtopics" if is_sub else "all 19 subtopics"
        verdict = (
            f"{'PASS' if passed else 'BELOW bar'} on {scope}: AI verified "
            f"{rate:.0%}, leaks {leaks}, coverage {ai_cov} vs baseline "
            f"{base_cov_sample}"
        )

    return {
        "name": "Feature 2 (Phase 2) — exam-style problem generation",
        "make_target": "make problems",
        "baseline_vs": "templated (correct by construction)",
        "dataset": {
            "subtopics_evaluated_ai": len(subs),
            "num_subtopics_total": 19,
            "per_subtopic": per_subtopic,
        },
        "cutoff": {
            "min_verified_rate": MIN_VERIFIED_RATE,
            "leak_threshold_jaccard": LEAK_THRESHOLD,
        },
        "baseline": {
            "method": "templated (correct by construction)",
            "coverage_subtopics": base_cov_full,
            "verified_rate": 1.0,
            "wrong_rate": 0.0,
        },
        "ai": ai_cell,
        "ai_ran": ai_ran,
        "verdict": verdict,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-subtopic", type=int, default=2)
    parser.add_argument(
        "--subtopics", type=int, default=0, help="limit # subtopics (0 = all 19)"
    )
    args = parser.parse_args()

    subs = all_subtopics()
    if args.subtopics:
        subs = subs[: args.subtopics]
    print(
        f"pre-registered cutoff: ship AI problems only if verified >= "
        f"{MIN_VERIFIED_RATE:.0%} AND leakage = 0 AND coverage > baseline.\n"
    )

    base_cov = sum(1 for t in subs if templated_problems(t, 1))
    print(
        f"baseline (templated): covers {base_cov}/{len(subs)} subtopics, "
        f"correct by construction (100% verified)."
    )

    provider = available_provider()
    if provider is None:
        print(
            "\nAI generator: not run (no provider/key). Set OPENAI_API_KEY to run "
            "it and apply the cutoff. The app still practices from the held-out "
            "corpus with AI off."
        )
        return 0

    client = OpenAiClient()
    held_out = load_sample_items()
    total = verified = ai_cov = leaks = 0
    for tag in subs:
        cands = ai_candidates(client, tag, args.per_subtopic)
        if cands:
            ai_cov += 1
        for c in cands:
            total += 1
            if verify_problem(client, c["question"], c["answer"]):
                verified += 1
            worst = max(
                (jaccard(c["question"], it.question) for it in held_out), default=0.0
            )
            if worst >= LEAK_THRESHOLD:
                leaks += 1

    rate = verified / total if total else 0.0
    print(
        f"AI ({provider}): {total} problems  verified {verified}/{total} "
        f"({rate:.0%})  covers {ai_cov}/{len(subs)} subtopics  leakage {leaks}"
    )
    passed = rate >= MIN_VERIFIED_RATE and leaks == 0 and ai_cov > base_cov
    print(
        f"\nverdict: {'PASS -> ship AI problems' if passed else 'FAIL -> ship the templated baseline'} "
        f"(verified {rate:.0%}, leakage {leaks}, coverage {ai_cov} vs baseline {base_cov})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
