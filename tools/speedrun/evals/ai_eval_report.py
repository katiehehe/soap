#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Friday AI PROOF artifact: run all three AI evals and WRITE one committed,
machine-readable comparison file.

This is the single command behind the "AI beats a simpler baseline" claim. It
runs the classifier, card-generation, and problem-generation evals side by side
and writes ``tools/speedrun/evals/results/ai_eval.json`` capturing, for each:
dataset descriptor, the pre-registered cutoffs, the offline BASELINE metrics
(accuracy + wrong-answer rate), and the AI metrics, plus a timestamp, git SHA,
and an ``ai_ran`` flag.

Honesty: the baseline/offline cells are reproducible with no key and always
fill; the AI cells populate ONLY when ``OPENAI_API_KEY`` is set. With no key the
AI cells are ``null`` with a ``pending`` verdict: never fabricated.

Usage:
    # Offline: writes baseline + offline cells; AI cells stay pending.
    out/pyenv/bin/python tools/speedrun/evals/ai_eval_report.py
    # With a key: also populates the AI cells.
    OPENAI_API_KEY=... out/pyenv/bin/python tools/speedrun/evals/ai_eval_report.py
Or `make ai-report` (add OPENAI_API_KEY to populate the AI cells).
"""

from __future__ import annotations

import argparse
import os
import sys
import time

_REPO = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
for _p in (os.path.join(_REPO, "pylib"), os.path.join(_REPO, "out", "pylib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
# The sibling eval scripts live next to this file.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from anki.speedrun.ai import DEFAULT_OPENAI_MODEL, available_provider  # noqa: E402
from anki.speedrun.ai_eval import (  # noqa: E402
    DEFAULT_ARTIFACT_PATH,
    build_report,
    read_git_sha,
    write_report,
)
from classify_eval import collect_results as classify_results  # noqa: E402
from generate_eval import collect_results as generate_results  # noqa: E402
from problem_eval import collect_results as problem_results  # noqa: E402


def _fmt_pct(x: float | None) -> str:
    return "  n/a" if x is None else f"{x:>5.0%}"


def _print_eval(key: str, rec: dict) -> None:
    base = rec.get("baseline", {})
    print(f"\n[{key}] {rec['name']}  (baseline: {rec['baseline_vs']})")
    leak = rec.get("leakage_over_ai_inputs")
    if leak is not None:
        print(f"    leakage over AI inputs: {'CLEAN' if leak['clean'] else 'LEAK'}")
    # accuracy-ish metric differs per eval; print whatever the baseline exposes.
    for metric in ("top1", "correct_rate", "verified_rate"):
        if metric in base:
            wrong = base.get("wrong_rate", base.get("wrong_rate_top1"))
            print(
                f"    baseline {metric}={_fmt_pct(base[metric])}"
                f"  wrong_rate={_fmt_pct(wrong)}"
            )
            break
    if rec.get("ai_ran"):
        print(f"    AI: {rec['ai']}")
    print(f"    verdict: {rec['verdict']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=50, help="AI cards to generate/score")
    parser.add_argument("--per-subtopic", type=int, default=2)
    parser.add_argument(
        "--subtopics",
        type=int,
        default=0,
        help="cap the AI problem side to the first N subtopics (0 = all 19)",
    )
    parser.add_argument(
        "--classify-limit",
        type=int,
        default=0,
        help="cap the AI classifier side to a seeded N-item subsample (0 = full)",
    )
    parser.add_argument(
        "--seed", type=int, default=0, help="seed for the classifier subsample"
    )
    parser.add_argument(
        "--out", default=None, help=f"artifact path (default {DEFAULT_ARTIFACT_PATH})"
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="force the offline/baseline-only artifact (AI cells stay pending) "
        "even if a key is configured, so no API calls happen. Handy to regenerate "
        "the committed baseline artifact without cost.",
    )
    args = parser.parse_args()

    run_ai = not args.no_ai
    provider = available_provider() if run_ai else None
    subsample = run_ai and (args.classify_limit or args.subtopics or args.n < 50)
    print(
        "Running the three AI evals for the committed artifact.\n"
        f"AI provider: {provider or 'NONE (offline): AI cells will be pending'}"
        + (
            f"\nSUBSAMPLE smoke run: classify n={args.classify_limit or 'full'}, "
            f"generate n={args.n}, problems subtopics={args.subtopics or 'all'}, "
            f"seed={args.seed}"
            if subsample
            else ""
        )
    )

    # Run + print each eval incrementally (with elapsed time) so a long keyed
    # run is observable in the log rather than silent until the end.
    order = (
        ("classify", lambda: classify_results(
            run_ai=run_ai, limit=args.classify_limit, seed=args.seed
        )),
        ("generate", lambda: generate_results(args.n, run_ai=run_ai, seed=args.seed)),
        ("problems", lambda: problem_results(
            args.per_subtopic, args.subtopics, run_ai=run_ai, seed=args.seed
        )),
    )
    evals: dict = {}
    for key, fn in order:
        print(f"\n... running [{key}] ...", flush=True)
        t0 = time.time()
        evals[key] = fn()
        _print_eval(key, evals[key])
        print(f"    ({key} done in {time.time() - t0:.0f}s)", flush=True)

    report = build_report(
        evals,
        ai_provider=provider,
        ai_model=DEFAULT_OPENAI_MODEL if run_ai else None,
        git_sha=read_git_sha(_REPO),
        seed=args.seed,
    )
    path = write_report(report, args.out)

    print(
        f"\nartifact written: {path}"
        f"\n  ai_ran={report['ai_ran']}  is_subsample={report['is_subsample']}  "
        f"git_sha={report['git_sha']}  at={report['generated_at_utc']}",
        flush=True,
    )
    if not report["ai_ran"]:
        print(
            "  AI cells are PENDING (no key). Re-run with OPENAI_API_KEY set to "
            "populate them; no AI number was fabricated.",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
