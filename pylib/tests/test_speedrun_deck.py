# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from anki.speedrun import (
    deck_name_for_subtopic_tag,
    expected_subtopic_tags,
    load_topics,
    subtopic_tag,
    unit_deck_name,
)
from anki.speedrun.seed import SEED_CARDS, build_deck
from tests.shared import getEmptyCol


def test_deck_name_for_subtopic_tag_matches_built_decks():
    # The study map opens a subtopic's deck for blocked practice by name, so the
    # helper must resolve to a deck that build_deck actually created.
    col = getEmptyCol()
    build_deck(col)
    for tag in expected_subtopic_tags():
        name = deck_name_for_subtopic_tag(tag)
        assert name is not None and name.startswith("SOA Exam P::")
        assert col.decks.by_name(name) is not None, name
    # malformed / unknown tags resolve to None (never a wrong deck)
    assert deck_name_for_subtopic_tag("not-a-tag") is None
    assert deck_name_for_subtopic_tag("subtopic::nope::nope") is None


def test_unit_deck_name_matches_built_decks():
    # Within-unit interleaving opens a unit's deck by name.
    col = getEmptyCol()
    build_deck(col)
    for unit in load_topics()["units"]:
        name = unit_deck_name(unit["id"])
        assert name is not None and name.startswith("SOA Exam P::")
        assert col.decks.by_name(name) is not None, name
    assert unit_deck_name("nope") is None


def test_build_deck_covers_all_three_units():
    col = getEmptyCol()
    added = build_deck(col)
    assert added == len(SEED_CARDS)

    # every syllabus unit is represented in the starter deck
    units = {card.unit_id for card in SEED_CARDS}
    assert units == {"general", "univariate", "multivariate"}

    # each seeded card is findable by its subtopic tag
    for card in SEED_CARDS:
        tag = subtopic_tag(card.unit_id, card.subtopic_id)
        assert len(col.find_notes(f"tag:{tag}")) >= 1


def test_starter_deck_covers_full_syllabus():
    col = getEmptyCol()
    build_deck(col)
    expected = set(expected_subtopic_tags())
    covered = {subtopic_tag(c.unit_id, c.subtopic_id) for c in SEED_CARDS}
    # every covered subtopic is a real entry in the official outline
    assert covered.issubset(expected)
    # the starter deck now spans the entire syllabus (full weighted coverage)
    assert covered == expected
    assert len(covered) / len(expected) == 1.0


def test_deck_has_multiple_difficulties_per_syllabus():
    # a mix of recall + applied cards means more than one card per unit
    from collections import Counter

    by_difficulty = Counter(card.difficulty for card in SEED_CARDS)
    assert set(by_difficulty) <= {"easy", "medium", "hard"}
    # graded difficulty is represented, not a single flat level
    assert len(by_difficulty) >= 2
