# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from anki import speedrun_pb2
from anki.speedrun import (
    expected_subtopic_tags,
    subtopic_tag,
    subtopic_weights,
    unit_weights,
)
from anki.speedrun.seed import SEED_CARDS, build_deck
from tests.shared import getEmptyCol

# MasteryPool enum values (from proto): BLOCKED=0, WITHIN_UNIT=1, CROSS_UNIT=2
BLOCKED = 0


def test_get_mastery_state_reads_reviews_and_gates():
    col = getEmptyCol()
    build_deck(col)
    expected = expected_subtopic_tags()

    state = col._backend.get_mastery_state(
        expected_subtopics=expected, units=[], subtopic_weights=[]
    )

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

    state2 = col._backend.get_mastery_state(
        expected_subtopics=expected, units=[], subtopic_weights=[]
    )
    assert sum(s.reviews for s in state2.subtopics) >= 1


def test_get_mastery_state_echoes_weights_and_weighted_rollup():
    # Importance weights flow proto -> Rust -> Python: each subtopic echoes its
    # weight, each unit's weight is the sum of its subtopic weights (the official
    # section midpoint), and with nothing studied the weighted mastery rollup is
    # honestly 0 (never fabricated).
    col = getEmptyCol()
    build_deck(col)
    sw = subtopic_weights()
    state = col._backend.get_mastery_state(
        expected_subtopics=expected_subtopic_tags(),
        units=[speedrun_pb2.UnitWeight(unit_id=u, weight=w) for u, w in unit_weights()],
        subtopic_weights=[speedrun_pb2.SubtopicWeight(tag=t, weight=w) for t, w in sw],
    )

    weight_by_tag = dict(sw)
    for s in state.subtopics:
        assert abs(s.weight - weight_by_tag[s.tag]) < 1e-9

    midpoints = dict(unit_weights())
    for u in state.units:
        assert abs(u.weight - midpoints[u.unit_id]) < 1e-6
        assert u.weighted_mastery_pct == 0.0
    assert state.overall.weighted_mastery_pct == 0.0

    # "What to study next": nothing is cleared yet, so every subtopic is a
    # priority, ranked highest-weight first (univariate distributions, weight 9).
    assert len(state.priorities) == len(sw)
    top = state.priorities[0]
    assert top.unit_id == "univariate"
    assert abs(top.weight - 9.0) < 1e-9
    assert top.priority_score > 0
    assert top.reason


def test_mastery_ordered_new_cards_returns_blocked_cards():
    col = getEmptyCol()
    build_deck(col)
    # Single-field response: the generated wrapper returns card_ids directly.
    card_ids = col._backend.get_mastery_ordered_new_cards(
        expected_subtopics=expected_subtopic_tags(), units=[], subtopic_weights=[]
    )
    # All seeded cards are new + tagged, so they all come back in the order.
    assert len(card_ids) == len(SEED_CARDS)


def test_points_at_stake_order_reads_due_cards():
    # New protobuf message called from Python: once a card is answered it enters
    # the review pipeline and comes back in points-at-stake order, with
    # stakes = weight x measured weakness. Nothing is fabricated.
    col = getEmptyCol()
    build_deck(col)
    col.decks.select(col.decks.id("SOA Exam P"))
    card = col.sched.getCard()
    assert card is not None
    col.sched.answerCard(card, 3)

    # Single repeated field -> the generated wrapper returns the list directly.
    cards = col._backend.get_points_at_stake_order(
        expected_subtopics=expected_subtopic_tags(),
        units=[],
        subtopic_weights=[
            speedrun_pb2.SubtopicWeight(tag=t, weight=w) for t, w in subtopic_weights()
        ],
    )
    assert len(cards) >= 1
    for c in cards:
        assert abs(c.stakes - c.weight * c.weakness) < 1e-9
        assert 0.0 <= c.weakness <= 1.0
    # Highest stakes first.
    for a, b in zip(cards, cards[1:]):
        assert a.stakes >= b.stakes - 1e-9


def test_build_deck_writes_weights_and_points_at_stake_flag_builds():
    # Topic-aware live scheduling: build_deck writes the per-subtopic weights to
    # config, and with the points-at-stake flag on the live queue still builds
    # cleanly (the reorder is order-only, so it can't corrupt anything).
    col = getEmptyCol()
    build_deck(col)
    weights = col.get_config("speedrunSubtopicWeights")
    assert weights and len(weights) == len(expected_subtopic_tags())

    col.set_config("speedrunPointsAtStake", True)
    col.decks.select(col.decks.id("SOA Exam P"))
    assert col.sched.getCard() is not None


def test_undo_works_with_speedrun_scheduler_flags_on():
    # 7a requires undo keeps working with the Rust change. The live-queue reorders
    # are read-only, so answering a card with both flags on must still undo
    # cleanly (the revlog row is removed).
    col = getEmptyCol()
    build_deck(col)
    col.set_config("speedrunMasteryScheduler", True)
    col.set_config("speedrunPointsAtStake", True)
    col.decks.select(col.decks.id("SOA Exam P"))
    card = col.sched.getCard()
    assert card is not None
    before = col.db.scalar("select count() from revlog")
    col.sched.answerCard(card, 3)
    assert col.db.scalar("select count() from revlog") == before + 1
    col.undo()
    assert col.db.scalar("select count() from revlog") == before


def test_ablation_build_configs_build_a_valid_queue():
    # The study-feature ablation runs three builds off two config flags. Build 1
    # (Full) and Build 2 (Ablated) differ only by speedrunAblateWithinUnit; both
    # must build a valid queue. The ordering *difference* is covered by Rust unit
    # tests (a fresh deck is all-Blocked, so orders coincide here).
    col = getEmptyCol()
    build_deck(col)
    col.set_config("speedrunMasteryScheduler", True)
    col.decks.select(col.decks.id("SOA Exam P"))

    col.set_config("speedrunAblateWithinUnit", False)  # Build 1: Full
    col.reset()
    assert col.sched.getCard() is not None

    col.set_config("speedrunAblateWithinUnit", True)  # Build 2: Ablated
    col.reset()
    assert col.sched.getCard() is not None
