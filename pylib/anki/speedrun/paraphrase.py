# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""The paraphrase test (challenge 7d): does Performance measure more than Memory?

The trap the brief warns about: a "performance" score that just tracks the
memory model. If a student can recall a flashcard but can't answer a *reworded*
exam-style question about the same idea, the bridge from memory to performance
was never built.

The test (per the brief): take 30 cards; for each, write 2 exam-style questions
that test the same idea in NEW words. Compare the student's **recall on the card**
(the memory signal) with their **accuracy on the reworded questions** (the
performance signal). Report the GAP. If the two numbers are basically the same,
performance is copying memory.

Two layers, kept separate so real data flows through the same code:

- ``grade`` is pure aggregation over 0/1 outcomes (what a real student's graded
  answers produce);
- the runner (``tools/speedrun/evals/paraphrase_eval.py``) feeds it either the
  clearly-labelled synthetic persona/cohort or, when it exists, real graded data.

Honesty: the committed dataset is ORIGINAL, held-out, no-copyright; the reworded
questions must be genuinely reworded (checked by ``reworded_distinctness``, a
near-copy of the card prompt would make "performance" trivially equal memory at
the DATA level). Nothing here fabricates a real student result.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Committed, original, held-out paraphrase dataset (ships with the repo).
_DATA_PATH = Path(__file__).parent / "paraphrase_items.json"

# The gap (recall_rate - reworded_rate) below which we conclude performance is
# just tracking memory. Pre-registered here, not tuned after seeing results.
COPYING_GAP = 0.05

# Reworded questions whose word-overlap (Jaccard) with the card prompt is at or
# above this are too close to count as "reworded": they'd make the performance
# side a re-read of the memory side.
MAX_REWORD_OVERLAP = 0.5


@dataclass(frozen=True)
class ParaphraseCard:
    """One memorised fact (the card) plus exam-style questions that reword it.

    ``card_prompt`` is the memory side (recall the fact). ``reworded`` are the
    performance side: the same idea asked in new words. ``source`` traces the
    item (all committed items are original, held-out).
    """

    id: str
    subtopic: str
    difficulty: str
    fact: str
    card_prompt: str
    reworded: list[str] = field(default_factory=list)
    source: str = ""

    @property
    def unit_id(self) -> str:
        parts = self.subtopic.split("::")
        return parts[1] if len(parts) == 3 else ""


@dataclass(frozen=True)
class ParaphraseResult:
    """Aggregate outcome of the paraphrase test.

    ``recall_rate`` is the memory signal; ``reworded_rate`` the performance
    signal; ``gap`` = recall_rate - reworded_rate. ``copying`` is True when the
    gap is below ``COPYING_GAP`` (performance is tracking memory).
    """

    n_cards: int
    n_reworded: int
    recall_correct: int
    reworded_correct: int
    per_subtopic: dict[str, tuple[float, float]]  # tag -> (recall_rate, reworded_rate)

    @property
    def recall_rate(self) -> float:
        return self.recall_correct / self.n_cards if self.n_cards else 0.0

    @property
    def reworded_rate(self) -> float:
        return self.reworded_correct / self.n_reworded if self.n_reworded else 0.0

    @property
    def gap(self) -> float:
        return self.recall_rate - self.reworded_rate

    @property
    def copying(self) -> bool:
        # abs(): a gap near zero in EITHER direction means the two signals are
        # not separated.
        return abs(self.gap) < COPYING_GAP

    @property
    def verdict(self) -> str:
        if self.copying:
            return (
                "COPYING: reworded accuracy tracks card recall (gap "
                f"{self.gap:+.1%}); the performance signal is not separated from "
                "memory."
            )
        if self.gap > 0:
            return (
                f"BRIDGE: recall exceeds reworded accuracy by {self.gap:.1%}, so "
                "performance is a distinct, harder signal than memory."
            )
        return (
            f"reworded accuracy exceeds recall by {-self.gap:.1%}, unusually; "
            "performance is still separated from memory."
        )


def load_paraphrase_cards(path: str | None = None) -> list[ParaphraseCard]:
    """Load the paraphrase dataset. Validates that every card carries exactly two
    reworded questions (the brief's "2 exam-style questions" per card)."""
    p = Path(path) if path is not None else _DATA_PATH
    with open(p, encoding="utf8") as f:
        data: dict[str, Any] = json.load(f)
    default_src = str(data.get("source", "original-speedrun-paraphrase"))
    out: list[ParaphraseCard] = []
    for raw in data.get("cards", []):
        reworded = [str(q) for q in raw.get("reworded", [])]
        if len(reworded) != 2:
            raise ValueError(
                f"card {raw.get('id')!r} must have exactly 2 reworded questions, "
                f"got {len(reworded)}"
            )
        out.append(
            ParaphraseCard(
                id=str(raw["id"]),
                subtopic=str(raw["subtopic"]),
                difficulty=str(raw.get("difficulty", "medium")),
                fact=str(raw["fact"]),
                card_prompt=str(raw["card_prompt"]),
                reworded=reworded,
                source=str(raw.get("source", default_src)),
            )
        )
    if not out:
        raise ValueError(f"no cards found in {p}")
    return out


def grade(
    cards: list[ParaphraseCard],
    recalls: dict[str, int],
    reworded: dict[str, list[int]],
) -> ParaphraseResult:
    """Aggregate graded outcomes into the memory-vs-performance comparison.

    ``recalls`` maps card id -> 1/0 (recalled the card). ``reworded`` maps card
    id -> list of 1/0 for its reworded questions. Missing entries count as wrong.
    This is pure: real graded answers and simulated ones flow through it the same.
    """
    recall_correct = 0
    reworded_correct = 0
    reworded_total = 0
    per_sub: dict[str, list[int]] = {}  # tag -> [rc, rn, wc, wn]
    for card in cards:
        rc = 1 if recalls.get(card.id, 0) == 1 else 0
        recall_correct += rc
        answers = reworded.get(card.id, [])
        wc = sum(1 for a in answers if a == 1)
        wn = len(card.reworded)
        reworded_correct += wc
        reworded_total += wn
        cell = per_sub.setdefault(card.subtopic, [0, 0, 0, 0])
        cell[0] += rc
        cell[1] += 1
        cell[2] += wc
        cell[3] += wn
    per_subtopic = {
        tag: (
            rc / rn if rn else 0.0,
            wc / wn if wn else 0.0,
        )
        for tag, (rc, rn, wc, wn) in per_sub.items()
    }
    return ParaphraseResult(
        n_cards=len(cards),
        n_reworded=reworded_total,
        recall_correct=recall_correct,
        reworded_correct=reworded_correct,
        per_subtopic=per_subtopic,
    )


def _tokens(text: str) -> set[str]:
    return {t for t in "".join(c.lower() if c.isalnum() else " " for c in text).split()}


def reworded_distinctness(cards: list[ParaphraseCard]) -> list[tuple[str, float]]:
    """Word-overlap (Jaccard) of each reworded question with its card prompt.

    Returns ``(card_id#index, overlap)`` for any reworded question at or above
    ``MAX_REWORD_OVERLAP``, i.e. too close to the memory prompt to count as a
    genuine rewording. An empty list means every rewording is distinct.
    """
    flagged: list[tuple[str, float]] = []
    for card in cards:
        prompt = _tokens(card.card_prompt)
        for i, q in enumerate(card.reworded):
            other = _tokens(q)
            union = prompt | other
            overlap = len(prompt & other) / len(union) if union else 0.0
            if overlap >= MAX_REWORD_OVERLAP:
                flagged.append((f"{card.id}#{i}", round(overlap, 3)))
    return flagged
