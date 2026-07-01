# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Build a small, tagged SOA Exam P starter deck for the review loop (7c).

Cards are static for now; parameterized (regenerating) questions are a later step
for the performance model and the mastery gate. Every card is tagged with its
unit, subtopic, and difficulty so coverage and the scheduler can reason about it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from anki.speedrun import (
    difficulty_tag,
    load_topics,
    subtopic_name,
    subtopic_tag,
    unit_name,
    unit_tag,
)

if TYPE_CHECKING:
    from anki.collection import Collection

ROOT_DECK = "SOA Exam P"


class SeedCard(NamedTuple):
    unit_id: str
    subtopic_id: str
    difficulty: str
    front: str
    back: str


# A handful of cards spanning all three units.
SEED_CARDS: list[SeedCard] = [
    SeedCard(
        "general",
        "conditional",
        "easy",
        "State the definition of the conditional probability P(A | B).",
        "P(A | B) = P(A and B) / P(B), for P(B) > 0.",
    ),
    SeedCard(
        "general",
        "bayes",
        "medium",
        "State Bayes' theorem for events A and B.",
        "P(A | B) = P(B | A) P(A) / P(B).",
    ),
    SeedCard(
        "univariate",
        "discrete_common",
        "easy",
        "For X ~ Binomial(n, p), give E[X] and Var(X).",
        "E[X] = n p, Var(X) = n p (1 - p).",
    ),
    SeedCard(
        "univariate",
        "continuous_common",
        "medium",
        "For X ~ Exponential with rate lambda, give E[X] and Var(X).",
        "E[X] = 1 / lambda, Var(X) = 1 / lambda^2.",
    ),
    SeedCard(
        "multivariate",
        "covariance_correlation",
        "medium",
        "Define Cov(X, Y) in terms of expectations.",
        "Cov(X, Y) = E[XY] - E[X] E[Y].",
    ),
    SeedCard(
        "multivariate",
        "linear_combinations",
        "hard",
        "For independent X and Y, give Var(aX + bY).",
        "a^2 Var(X) + b^2 Var(Y).",
    ),
]


def build_deck(col: Collection, root: str = ROOT_DECK) -> int:
    """Create the tagged Exam P deck in ``col``. Returns the number of cards added."""
    topics = load_topics()
    notetype = col.models.by_name("Basic")
    if notetype is None:
        raise RuntimeError("Basic notetype not found in collection")

    added = 0
    for card in SEED_CARDS:
        deck_name = "::".join(
            [
                root,
                unit_name(card.unit_id, topics),
                subtopic_name(card.unit_id, card.subtopic_id, topics),
            ]
        )
        deck_id = col.decks.id(deck_name)
        assert deck_id is not None
        note = col.new_note(notetype)
        note["Front"] = card.front
        note["Back"] = card.back
        note.add_tag(unit_tag(card.unit_id))
        note.add_tag(subtopic_tag(card.unit_id, card.subtopic_id))
        note.add_tag(difficulty_tag(card.difficulty))
        col.add_note(note, deck_id)
        added += 1
    return added
