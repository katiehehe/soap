# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from anki.speedrun import expected_subtopic_tags, subtopic_tag
from anki.speedrun.seed import SEED_CARDS, build_deck
from tests.shared import getEmptyCol

# MasteryPool enum values (from proto): BLOCKED=0, WITHIN_UNIT=1, CROSS_UNIT=2
BLOCKED = 0


def test_get_mastery_state_reads_reviews_and_gates():
    col = getEmptyCol()
    build_deck(col)
    expected = expected_subtopic_tags()

    state = col._backend.get_mastery_state(expected_subtopics=expected)

    # Every syllabus unit is rolled up, none mastered on a fresh deck.
    assert len(state.units) == 3
    assert all(not u.mastered for u in state.units)

    # Covered subtopics are present; on a fresh deck everything is Blocked with
    # no reviews and the gate uncleared.
    tags = {s.tag for s in state.subtopics}
    covered = {subtopic_tag(c.unit_id, c.subtopic_id) for c in SEED_CARDS}
    assert covered.issubset(tags)
    for s in state.subtopics:
        assert s.reviews == 0
        assert s.gate_cleared is False
        assert s.pool == BLOCKED

    # Answering a card is picked up from the revlog by the mastery query.
    col.decks.select(col.decks.id("SOA Exam P"))
    card = col.sched.getCard()
    assert card is not None
    col.sched.answerCard(card, 3)

    state2 = col._backend.get_mastery_state(expected_subtopics=expected)
    assert sum(s.reviews for s in state2.subtopics) >= 1


def test_mastery_ordered_new_cards_returns_blocked_cards():
    col = getEmptyCol()
    build_deck(col)
    # Single-field response: the generated wrapper returns card_ids directly.
    card_ids = col._backend.get_mastery_ordered_new_cards(
        expected_subtopics=expected_subtopic_tags()
    )
    # All seeded cards are new + tagged, so they all come back in the order.
    assert len(card_ids) == len(SEED_CARDS)
