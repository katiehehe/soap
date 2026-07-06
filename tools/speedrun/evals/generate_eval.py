#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""AI card-generation eval (Friday AI Feature 2 / challenge 7f).

    out/pyenv/bin/python tools/speedrun/evals/generate_eval.py [--n 50]

- Human gold set: the hand-written seed-deck cards (the quality reference).
- Generated set: ``--n`` cards generated from NAMED sources
  (``anki.speedrun.gen_sources``), each grounded in and citing one source.
- Rubric (deterministic, cutoff pre-registered BELOW, before looking): each
  generated card is scored correct / wrong / bad-teaching.
- Baseline: the template/extraction generator (the offline stub). The real AI
  generator (OpenAI, when ``OPENAI_API_KEY`` is set) must beat it.
- Leakage (7e): the source passages (AI inputs) are scanned against the held-out
  item corpus, so no held-out item leaks into generation.

Everything is deterministic offline; the AI side runs only when a key is present.
"""

from __future__ import annotations

import argparse
import math
import os
import sys

_REPO = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
for _p in (os.path.join(_REPO, "pylib"), os.path.join(_REPO, "out", "pylib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import json  # noqa: E402
from pathlib import Path  # noqa: E402

from anki.speedrun import subtopic_name  # noqa: E402
from anki.speedrun.ai import available_provider, make_client  # noqa: E402
from anki.speedrun.evalsplit import find_leaks  # noqa: E402
from anki.speedrun.seed import SEED_CARDS  # noqa: E402
from anki.speedrun.soa_sample import load_sample_items  # noqa: E402

# --- pre-registered cutoff (set BEFORE looking at any AI output) ----------
MIN_CORRECT_RATE = 0.60  # ship AI generation only if >= 60% of cards are correct
MAX_BAD_TEACHING = 0.20  # ... AND <= 20% are bad-teaching
# ... AND the AI's correct rate must beat the extraction baseline's.

_SOURCES_PATH = Path(_REPO) / "pylib" / "anki" / "speedrun" / "gen_sources.json"


def load_sources() -> list[dict]:
    with open(_SOURCES_PATH, encoding="utf-8") as f:
        return json.load(f)["sources"]


def structural_ok(front: str, back: str) -> bool:
    f, b = front.strip(), back.strip()
    if len(f) < 15 or len(b) < 3:
        return False
    if b.lower() == f.lower() or b.lower() in f.lower():
        return False
    return True


def score_card(front: str, back: str, key_terms: list[str]) -> str:
    """correct / wrong / bad_teaching for a generated card grounded in a source.

    - bad_teaching: structurally poor (trivial, empty, or answer restates the
      prompt), so it would mis-teach regardless of content.
    - correct: structurally sound AND grounded (the answer contains a source key
      term, i.e. it actually conveys the source fact).
    - wrong: structurally sound but not grounded in the source's key facts.
    """
    if not structural_ok(front, back):
        return "bad_teaching"
    bl = back.lower()
    if any(k.lower() in bl for k in key_terms):
        return "correct"
    return "wrong"


def generate_set(
    provider: str, sources: list[dict], n: int
) -> list[tuple[str, str, list[str]]]:
    """Generate ~n cards across the sources with the given provider. Returns
    (front, back, key_terms) so the rubric can score each against its source."""
    client = make_client(provider)
    per_source = max(1, math.ceil(n / len(sources)))
    out: list[tuple[str, str, list[str]]] = []
    for src in sources:
        parts = src["subtopic"].split("::")
        name = subtopic_name(parts[1], parts[2]) if len(parts) == 3 else src["subtopic"]
        for front, back in client.generate(
            name, src["name"], src["passage"], per_source
        ):
            out.append((front, back, src["key_terms"]))
    return out[:n]


def tally(cards: list[tuple[str, str, list[str]]]) -> dict[str, int]:
    counts = {"correct": 0, "wrong": 0, "bad_teaching": 0}
    for front, back, keys in cards:
        counts[score_card(front, back, keys)] += 1
    return counts


def _rates(counts: dict[str, int]) -> tuple[float, float]:
    n = sum(counts.values()) or 1
    return counts["correct"] / n, counts["bad_teaching"] / n


def _print_counts(label: str, counts: dict[str, int]) -> None:
    n = sum(counts.values()) or 1
    cr, br = _rates(counts)
    print(
        f"{label:<22} correct {counts['correct']:>2}/{n} ({cr:.0%})  "
        f"wrong {counts['wrong']:>2}  bad-teaching {counts['bad_teaching']:>2} ({br:.0%})"
    )


_FULL_N = 50  # the rubric-7f reference sample size (generate 50 from the sources)


def collect_results(n: int = _FULL_N, run_ai: bool = True, seed: int = 0) -> dict:
    """Machine-readable record for the committed AI-eval artifact (ai_eval.json).

    The extraction baseline is always computed offline at the FULL rubric size
    (50 cards); the AI cell is populated only when a provider/key is configured
    AND ``run_ai`` is True, else ``None`` with a ``pending`` verdict. No AI
    number is ever fabricated here. Pass ``run_ai=False`` to force the
    offline/baseline-only record.

    ``n`` caps how many cards the AI generates/scores (cost control for a keyed
    smoke run). When ``n`` is below the full size the AI cell is flagged
    ``is_subsample`` and carries an apples-to-apples ``baseline_on_sample``
    (the extraction baseline at the same ``n``).
    """
    sources = load_sources()
    corpus = load_sample_items()
    leaks = find_leaks(
        [(s["id"], s["passage"]) for s in sources],
        [(it.id, it.question) for it in corpus],
    )
    human_ok = sum(1 for c in SEED_CARDS if structural_ok(c.front, c.back))

    baseline = tally(generate_set("stub", sources, _FULL_N))  # FULL baseline
    base_total = sum(baseline.values()) or 1
    base_correct, base_bad = _rates(baseline)

    ai_cell: dict | None = None
    ai_ran = False
    verdict = "pending: run `make ai-report` with OPENAI_API_KEY to populate"
    provider = available_provider() if run_ai else None
    if provider is not None:
        from anki.speedrun.ai import DEFAULT_OPENAI_MODEL

        is_sub = n < _FULL_N
        ai = tally(generate_set(provider, sources, n))
        base_s = tally(generate_set("stub", sources, n))  # same-n baseline (no API)
        ai_total = sum(ai.values()) or 1
        base_s_total = sum(base_s.values()) or 1
        ai_correct, ai_bad = _rates(ai)
        bs_correct, bs_bad = _rates(base_s)
        ai_ran = True
        ai_cell = {
            "provider": provider,
            "model": DEFAULT_OPENAI_MODEL,
            "is_subsample": is_sub,
            "sample_size": sum(ai.values()),
            "seed": seed,
            "correct": ai["correct"],
            "wrong": ai["wrong"],
            "bad_teaching": ai["bad_teaching"],
            "correct_rate": round(ai_correct, 4),
            "wrong_rate": round(ai["wrong"] / ai_total, 4),
            "bad_teaching_rate": round(ai_bad, 4),
            "baseline_on_sample": {
                "n": sum(base_s.values()),
                "correct": base_s["correct"],
                "wrong": base_s["wrong"],
                "bad_teaching": base_s["bad_teaching"],
                "correct_rate": round(bs_correct, 4),
                "wrong_rate": round(base_s["wrong"] / base_s_total, 4),
                "bad_teaching_rate": round(bs_bad, 4),
            },
        }
        passed = (
            ai_correct >= MIN_CORRECT_RATE
            and ai_bad <= MAX_BAD_TEACHING
            and ai_correct > bs_correct
        )
        scope = f"sample n={sum(ai.values())}" if is_sub else "full set"
        verdict = (
            f"{'PASS' if passed else 'BELOW bar'} on {scope}: AI correct "
            f"{ai_correct:.0%} vs baseline {bs_correct:.0%}, bad-teaching "
            f"{ai_bad:.0%}"
        )

    return {
        "name": "Feature 2: card generation from a named source",
        "make_target": "make ai-eval",
        "baseline_vs": "template/extraction (stub)",
        "dataset": {
            "named_sources": len(sources),
            "human_gold_cards": len(SEED_CARDS),
            "human_gold_structural_ok": human_ok,
            "full_sample_size": sum(baseline.values()),
            "held_out_items_for_leakage": len(corpus),
        },
        "cutoff": {
            "min_correct_rate": MIN_CORRECT_RATE,
            "max_bad_teaching": MAX_BAD_TEACHING,
        },
        "leakage_over_ai_inputs": {"leaks": len(leaks), "clean": not leaks},
        "baseline": {
            "method": "template/extraction (stub)",
            "n": sum(baseline.values()),
            "correct": baseline["correct"],
            "wrong": baseline["wrong"],
            "bad_teaching": baseline["bad_teaching"],
            "correct_rate": round(base_correct, 4),
            "wrong_rate": round(baseline["wrong"] / base_total, 4),
            "bad_teaching_rate": round(base_bad, 4),
        },
        "ai": ai_cell,
        "ai_ran": ai_ran,
        "verdict": verdict,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=50)
    args = parser.parse_args()

    sources = load_sources()
    print(f"named sources: {len(sources)}  |  human gold cards: {len(SEED_CARDS)}")
    print(
        f"pre-registered cutoff: ship AI only if correct >= {MIN_CORRECT_RATE:.0%} "
        f"AND bad-teaching <= {MAX_BAD_TEACHING:.0%} AND it beats the baseline.\n"
    )

    # Leakage (7e): source passages (AI inputs) vs the held-out item corpus.
    corpus = load_sample_items()
    leaks = find_leaks(
        [(s["id"], s["passage"]) for s in sources],
        [(it.id, it.question) for it in corpus],
    )
    print(
        f"leakage over AI inputs (sources vs held-out corpus): {'CLEAN' if not leaks else f'{len(leaks)} LEAK(S)'}"
    )
    if leaks:
        return 1

    # Human reference: structural quality of the hand-written cards (sanity that
    # the rubric passes good cards).
    human_ok = sum(1 for c in SEED_CARDS if structural_ok(c.front, c.back))
    print(
        f"human reference structural-OK: {human_ok}/{len(SEED_CARDS)} ({human_ok / len(SEED_CARDS):.0%})\n"
    )

    baseline = tally(generate_set("stub", sources, args.n))
    _print_counts("baseline (extraction)", baseline)
    base_correct, _ = _rates(baseline)

    provider = available_provider()
    if provider is None:
        print(
            "\nAI generator: not run (no provider/key). Set OPENAI_API_KEY to run it "
            "and apply the cutoff. The app never shows AI cards below the cutoff, and "
            "still works with AI off."
        )
        return 0

    ai = tally(generate_set(provider, sources, args.n))
    _print_counts(f"AI ({provider})", ai)
    ai_correct, ai_bad = _rates(ai)
    passed = (
        ai_correct >= MIN_CORRECT_RATE
        and ai_bad <= MAX_BAD_TEACHING
        and ai_correct > base_correct
    )
    print(
        f"\nverdict: {'PASS -> ship AI generation' if passed else 'FAIL -> ship the baseline'} "
        f"(AI correct {ai_correct:.0%} vs baseline {base_correct:.0%})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
