#!/usr/bin/env python3
# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""The paraphrase test (challenge 7d): is Performance more than Memory?

Take 30 cards, each with 2 exam-style questions that reword the same idea, then
compare CARD RECALL (memory) against REWORDED ACCURACY (performance) and report
the GAP. If the two numbers match, the performance signal is just copying memory.

Everything here is deterministic and clearly SYNTHETIC (a labelled persona
cohort, never a real student). Three parts print:

1. Distinctness gate: every reworded question must differ enough from its card
   prompt (else "performance" would be a re-read of the memory side). Data-level
   leakage guard for 7d.
2. Main run: memory recall vs reworded performance across the cohort -> the gap
   + a verdict.
3. Control (null) run: feed the PERFORMANCE model into BOTH sides. The gap
   collapses to ~0 and the verdict flips to COPYING, proving the test actually
   discriminates (a fair test that can fail).

On real data (real card recall from the revlog + real graded reworded answers)
the same ``paraphrase.grade`` aggregates the outcomes unchanged.

Usage:
    out/pyenv/bin/python tools/speedrun/evals/paraphrase_eval.py [--students 60] [--seed 0]
Or via `make paraphrase`.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from dataclasses import replace

_REPO = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
for _p in (os.path.join(_REPO, "pylib"), os.path.join(_REPO, "out", "pylib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from anki.speedrun.paraphrase import (  # noqa: E402
    ParaphraseCard,
    ParaphraseResult,
    grade,
    load_paraphrase_cards,
    reworded_distinctness,
)
from anki.speedrun.persona import (  # noqa: E402
    Persona,
    p_correct,
    recall_prob,
    response_time_for,
    synthetic_cohort,
)


def _sub_label(tag: str) -> str:
    """Human-readable subtopic name (falls back to the raw tag)."""
    parts = tag.split("::")
    if len(parts) == 3:
        try:
            from anki.speedrun import subtopic_name

            return subtopic_name(parts[1], parts[2])
        except Exception:
            pass
    return tag


def _mean_skill(persona: Persona) -> float:
    return sum(persona.skill.values()) / len(persona.skill)


def _memory_recall(persona: Persona, card: ParaphraseCard, cov: float) -> float:
    """Memory side: probability of recalling the card (FSRS-style)."""
    return recall_prob(persona, card.subtopic)


def _transfer_perf(persona: Persona, card: ParaphraseCard, cov: float) -> float:
    """Performance side: probability of answering a NEW reworded question."""
    rt = response_time_for(persona, card.subtopic, card.difficulty)
    return p_correct(persona, card.subtopic, card.difficulty, cov, rt)


def simulate(
    cards: list[ParaphraseCard],
    cohort: list[Persona],
    recall_fn,
    perf_fn,
    seed: int,
) -> ParaphraseResult:
    """Grade the cohort against the cards and aggregate via ``paraphrase.grade``.

    ``recall_fn``/``perf_fn`` map (persona, card, coverage) -> probability, so the
    control run can point BOTH at the performance model. Deterministic."""
    pseudo: list[ParaphraseCard] = []
    recalls: dict[str, int] = {}
    reworded: dict[str, list[int]] = {}
    for persona in cohort:
        cov = min(1.0, max(0.4, _mean_skill(persona)))
        for card in cards:
            cid = f"{persona.name}|{card.id}"
            pseudo.append(replace(card, id=cid))
            rp = recall_fn(persona, card, cov)
            rng = random.Random(f"recall|{persona.seed}|{card.id}|{seed}")
            recalls[cid] = 1 if rng.random() < rp else 0
            outs: list[int] = []
            for i in range(len(card.reworded)):
                pp = perf_fn(persona, card, cov)
                rng2 = random.Random(f"reword|{persona.seed}|{card.id}|{i}|{seed}")
                outs.append(1 if rng2.random() < pp else 0)
            reworded[cid] = outs
    return grade(pseudo, recalls, reworded)


def _print_result(title: str, result: ParaphraseResult) -> None:
    print(f"\n{title}")
    print(
        f"  card recall (memory)     : {result.recall_rate:.1%} "
        f"({result.recall_correct}/{result.n_cards})"
    )
    print(
        f"  reworded accuracy (perf) : {result.reworded_rate:.1%} "
        f"({result.reworded_correct}/{result.n_reworded})"
    )
    print(f"  GAP (recall - reworded)  : {result.gap:+.1%}")
    print(f"  verdict                  : {result.verdict}")


def _print_per_subtopic(result: ParaphraseResult) -> None:
    print("\n  Per-subtopic (recall -> reworded, biggest gap first):")
    rows = sorted(
        result.per_subtopic.items(),
        key=lambda kv: kv[1][0] - kv[1][1],
        reverse=True,
    )
    for tag, (rec, rew) in rows:
        print(f"    {_sub_label(tag):32s} {rec:5.0%} -> {rew:5.0%}  ({rec - rew:+.0%})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--students", type=int, default=60)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    cards = load_paraphrase_cards()
    cohort = synthetic_cohort(args.students, seed=args.seed)

    print("=" * 74)
    print("PARAPHRASE TEST (7d) — does Performance measure more than Memory?")
    print(f"{len(cards)} cards x 2 reworded questions each; graded by a SYNTHETIC")
    print(f"cohort of {args.students} students (seed {args.seed}). Not a real student.")
    print("=" * 74)

    # 1) Distinctness gate: rewordings must not be near-copies of the card prompt.
    flagged = reworded_distinctness(cards)
    if flagged:
        print("\nDISTINCTNESS: FAILED — these rewordings are too close to the card")
        print("prompt (performance would just be a re-read of memory):")
        for cid, overlap in flagged:
            print(f"    {cid}: word-overlap {overlap:.0%}")
        return 1
    print(
        f"\nDistinctness gate: CLEAN — all {2 * len(cards)} rewordings differ enough "
        "from their card prompt."
    )

    # 2) Main run: memory recall vs reworded performance.
    main_result = simulate(cards, cohort, _memory_recall, _transfer_perf, args.seed)
    _print_result("MAIN — memory model vs performance model:", main_result)
    _print_per_subtopic(main_result)

    # 3) Control: reuse the PERFORMANCE model for the recall side too. A copycat
    #    performance model shows ~0 gap; the verdict must flip to COPYING.
    control = simulate(cards, cohort, _transfer_perf, _transfer_perf, args.seed)
    _print_result(
        "CONTROL (null) — performance model on BOTH sides (should read COPYING):",
        control,
    )

    print("\n" + "-" * 74)
    if main_result.copying:
        print(
            "RESULT: no meaningful gap — performance is tracking memory. The bridge "
            "is NOT demonstrated on this data."
        )
    elif control.copying:
        print(
            "RESULT: the real gap is "
            f"{main_result.gap:+.1%} while the copycat control is {control.gap:+.1%}. "
            "Performance is a genuinely separate, harder signal than memory, and the "
            "test correctly flags a copycat."
        )
    else:
        print(
            "RESULT: main gap present but the control did not collapse — inspect the "
            "fixture."
        )
    print("Reproducible: deterministic given --students and --seed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
