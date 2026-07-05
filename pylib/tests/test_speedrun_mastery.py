# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from datetime import date, timedelta

from anki import speedrun_pb2
from anki.speedrun import (
    POOL_BLOCKED,
    POOL_CROSS_UNIT,
    POOL_WITHIN_UNIT,
    TIER_CROSS_UNIT,
    TIER_WITHIN_UNIT,
    clear_exam_date,
    clear_tier_scope,
    exam_date_iso,
    exam_timestamp_for_iso,
    expected_subtopic_tags,
    set_exam_date,
    set_tier_scope,
    subtopic_prereqs,
    subtopic_tag,
    subtopic_weights,
    tier_for_deck_name,
    tier_scope_name,
    unit_prereqs,
    unit_weights,
)
from anki.speedrun.seed import ROOT_DECK, SEED_CARDS, build_deck
from tests.shared import getEmptyCol

# MasteryPool enum values (from proto): BLOCKED=0, WITHIN_UNIT=1, CROSS_UNIT=2
BLOCKED = 0


def test_tier_scope_name_labels_by_tier_scope():
    # The reviewer banner's scope after the tier name follows the TIER's scope,
    # not just the card's subtopic. "Common continuous distributions" is a
    # SUBTOPIC of the Univariate unit, so:
    tag = subtopic_tag("univariate", "continuous_dists")
    # Blocked practice drills the single subtopic -> the subtopic name.
    assert tier_scope_name(POOL_BLOCKED, tag) == "Common continuous distributions"
    # Within-unit interleaving is scoped to the whole UNIT -> the unit name,
    # NOT the subtopic (the reported bug: a subtopic shown as if it were a unit).
    assert tier_scope_name(POOL_WITHIN_UNIT, tag) == "Univariate Random Variables"
    # Cross-unit spacing spans everything.
    assert tier_scope_name(POOL_CROSS_UNIT, tag) == "All units"
    # A malformed tag degrades gracefully to the raw tag (the banner never breaks).
    assert tier_scope_name(POOL_WITHIN_UNIT, "subtopic::nope") == "subtopic::nope"


def test_get_mastery_state_reads_reviews_and_gates():
    col = getEmptyCol()
    build_deck(col)
    expected = expected_subtopic_tags()

    state = col._backend.get_mastery_state(
        expected_subtopics=expected,
        units=[],
        subtopic_weights=[],
        subtopic_prereqs=[],
        unit_prereqs=[],
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
        expected_subtopics=expected,
        units=[],
        subtopic_weights=[],
        subtopic_prereqs=[],
        unit_prereqs=[],
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
        subtopic_prereqs=[],
        unit_prereqs=[],
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

    # Tier-aware recommendation: a fresh deck (nothing cleared) -> blocked
    # practice on a specific subtopic (StudyMode.BLOCKED == 0).
    assert state.recommendation.mode == 0
    assert state.recommendation.subtopic_tag


def test_mastery_ordered_new_cards_returns_blocked_cards():
    col = getEmptyCol()
    build_deck(col)
    # Single-field response: the generated wrapper returns card_ids directly.
    card_ids = col._backend.get_mastery_ordered_new_cards(
        expected_subtopics=expected_subtopic_tags(),
        units=[],
        subtopic_weights=[],
        subtopic_prereqs=[],
        unit_prereqs=[],
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
        subtopic_prereqs=[],
        unit_prereqs=[],
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


def test_study_plan_blocked_on_fresh_deck():
    # Today's plan: on a fresh deck every subtopic is blocked practice, ordered by
    # exam importance, each pointing at a real subtopic deck with cards due today.
    col = getEmptyCol()
    build_deck(col)
    weights = subtopic_weights()
    # Single repeated field -> the generated wrapper returns the list directly.
    items = col._backend.get_study_plan(
        expected_subtopics=expected_subtopic_tags(),
        units=[],
        subtopic_weights=[
            speedrun_pb2.SubtopicWeight(tag=t, weight=w) for t, w in weights
        ],
        subtopic_prereqs=[],
        unit_prereqs=[],
    )
    assert len(items) >= 1
    # StudyMode.BLOCKED == 0: nothing is cleared, so every row is blocked practice.
    for it in items:
        assert it.tier == 0
        assert it.subtopic_tag
        assert it.new_count >= 1
        assert it.deck_id > 0
        assert it.deck_name.startswith("SOA Exam P::")
    # Highest exam-importance first: the top blocked deck is a univariate subtopic
    # (that unit carries the weight-9 distributions).
    assert items[0].subtopic_tag.startswith("subtopic::univariate::")


def test_study_plan_counts_match_seeded_cards():
    # The plan's counts are Anki's own deck-tree numbers, not fabricated: each
    # subtopic deck's "new" count equals how many cards the seed put in it,
    # capped by that deck's new-cards/day limit. Subtopics seeded with more cards
    # than the daily cap (the single-fact distribution decks) show the capped
    # count Anki will actually serve today.
    from collections import Counter

    col = getEmptyCol()
    build_deck(col)
    items = col._backend.get_study_plan(
        expected_subtopics=expected_subtopic_tags(),
        units=[],
        subtopic_weights=[
            speedrun_pb2.SubtopicWeight(tag=t, weight=w) for t, w in subtopic_weights()
        ],
        subtopic_prereqs=[],
        unit_prereqs=[],
    )
    want = Counter(subtopic_tag(c.unit_id, c.subtopic_id) for c in SEED_CARDS)
    got = {it.subtopic_tag: it.new_count for it in items}
    # Every seeded subtopic appears in the plan.
    assert set(got) == set(want)
    # Each plan count is the seeded count capped by the deck's new-cards/day
    # limit (still Anki's own deck-tree number, never fabricated).
    new_per_day = col.decks.config_dict_for_deck_id(col.decks.id(ROOT_DECK))["new"][
        "perDay"
    ]
    for tag, n in want.items():
        assert got[tag] == min(n, new_per_day), (tag, got[tag], n)


def test_study_plan_drops_decks_with_nothing_due():
    # Answer every card in one subtopic so it has nothing due today; its deck must
    # drop out of the plan (the actionable filter), while others remain.
    col = getEmptyCol()
    build_deck(col)
    target = subtopic_tag("general", "sets_axioms")
    deck_name = "SOA Exam P::General Probability::Sets, sample spaces, and axioms"
    col.decks.select(col.decks.id(deck_name))
    col.reset()
    while (card := col.sched.getCard()) is not None:
        col.sched.answerCard(card, 3)  # good -> leaves "new", not due again today

    items = col._backend.get_study_plan(
        expected_subtopics=expected_subtopic_tags(),
        units=[],
        subtopic_weights=[],
        subtopic_prereqs=[],
        unit_prereqs=[],
    )
    tags = {it.subtopic_tag for it in items}
    assert target not in tags, "a subtopic with nothing due today must be dropped"
    assert len(tags) >= 1, "other subtopics still have new cards due"


def _prereq_msgs() -> tuple[
    list[speedrun_pb2.SubtopicPrereqs], list[speedrun_pb2.UnitPrereqs]
]:
    sp = [speedrun_pb2.SubtopicPrereqs(tag=t, prereqs=p) for t, p in subtopic_prereqs()]
    up = [speedrun_pb2.UnitPrereqs(unit_id=u, prereqs=p) for u, p in unit_prereqs()]
    return sp, up


def test_guided_is_advisory_by_default_and_gate_still_works_when_enabled():
    # Performance-first app: a freshly built deck has the guided gate OFF, so
    # NOTHING is ever locked — the guided sequence is advice (recommended order +
    # arrows), not a gate. unmet_prereqs is still populated (the advice), and
    # performance is reported as its OWN signal, abstaining with no data.
    col = getEmptyCol()
    build_deck(col)
    sp, up = _prereq_msgs()

    def mastery():
        return col._backend.get_mastery_state(
            expected_subtopics=expected_subtopic_tags(),
            units=[],
            subtopic_weights=[],
            subtopic_prereqs=sp,
            unit_prereqs=up,
        )

    default = mastery()
    assert default.guided_mode is False  # advisory by default (no gate)
    assert all(not s.locked for s in default.subtopics)
    by_tag = {s.tag: s for s in default.subtopics}
    # The recommended order is still exposed (unmet prereqs), just never a lock.
    assert by_tag["subtopic::general::bayes"].unmet_prereqs
    # Performance stays a SEPARATE signal, abstaining with no practice yet.
    bayes = by_tag["subtopic::general::bayes"]
    assert bayes.perf_questions == 0
    assert bayes.performance_mastered is False

    # The gate MECHANISM still works when explicitly enabled (kept for the
    # study-feature ablation + this test): downstream + the next unit lock behind
    # their prerequisites, and the lock reason names an unmet prerequisite.
    col.set_config("speedrunGuidedMode", True)
    gated = mastery()
    assert gated.guided_mode is True
    by_tag = {s.tag: s for s in gated.subtopics}
    assert by_tag["subtopic::general::sets_axioms"].locked is False
    assert by_tag["subtopic::general::bayes"].locked is True
    assert by_tag["subtopic::multivariate::joint_distributions"].locked is True
    assert by_tag["subtopic::general::bayes"].unmet_prereqs


def test_performance_satisfies_a_prereq_without_flashcards():
    # An experienced user's practice-test PERFORMANCE (a separate signal) can
    # satisfy a prerequisite and unlock the next subtopic, with no flashcard reps
    # and without ever touching the memory gate.
    col = getEmptyCol()
    build_deck(col)
    sp, up = _prereq_msgs()
    # Enable the gate explicitly to exercise the unlock mechanism (the app runs
    # advisory/ungated; the Rust gate is kept for the ablation + this test).
    col.set_config("speedrunGuidedMode", True)
    col.set_config(
        "speedrunPerformanceBySubtopic",
        {"subtopic::general::sets_axioms": {"questions": 8, "correct": 8}},
    )
    state = col._backend.get_mastery_state(
        expected_subtopics=expected_subtopic_tags(),
        units=[],
        subtopic_weights=[],
        subtopic_prereqs=sp,
        unit_prereqs=up,
    )
    by_tag = {s.tag: s for s in state.subtopics}
    sa = by_tag["subtopic::general::sets_axioms"]
    assert sa.perf_questions == 8
    assert sa.performance_mastered is True
    # ...but the MEMORY gate is untouched (no reviews) — the two never blend.
    assert sa.gate_cleared is False
    assert sa.reviews == 0
    # combinatorics depends only on sets_axioms, so performance unlocks it...
    assert by_tag["subtopic::general::combinatorics"].locked is False
    # ...while bayes (its prereq chain unsatisfied) stays locked — proving the
    # gate is active and performance specifically cleared combinatorics.
    assert by_tag["subtopic::general::bayes"].locked is True


def test_exam_date_round_trips_through_config():
    col = getEmptyCol()
    assert exam_date_iso(col) is None
    assert exam_timestamp_for_iso("not-a-date") is None
    assert set_exam_date(col, "2026-08-15") is True
    assert exam_date_iso(col) == "2026-08-15"
    assert set_exam_date(col, "garbage") is False  # unchanged on bad input
    assert exam_date_iso(col) == "2026-08-15"
    clear_exam_date(col)
    assert exam_date_iso(col) is None


def test_study_pace_without_exam_date():
    # No deadline set: report the measured subtopic counts (none mastered yet on
    # a freshly built deck) but never claim on/off track without a deadline.
    col = getEmptyCol()
    build_deck(col)
    pace = col._backend.get_study_pace(
        expected_subtopics=expected_subtopic_tags(),
        units=[],
        subtopic_weights=[],
        subtopic_prereqs=[],
        unit_prereqs=[],
    )
    assert pace.has_exam_date is False
    assert pace.total_subtopics == len(expected_subtopic_tags())
    assert pace.mastered_subtopics == 0  # nothing reviewed -> nothing mastered
    assert pace.remaining_subtopics == pace.total_subtopics
    assert pace.on_track is False


def test_study_pace_gathers_before_projecting_without_mastery():
    # A mastery pace can't project until subtopics start clearing their gate. On
    # a freshly built deck nothing is mastered, so even with a deadline we show
    # the needed weekly rate but abstain from an on/off-track verdict (the
    # give-up rule applied to the pace).
    col = getEmptyCol()
    build_deck(col)

    far = (date.today() + timedelta(days=365)).isoformat()
    assert set_exam_date(col, far)
    pace = col._backend.get_study_pace(
        expected_subtopics=expected_subtopic_tags(),
        units=[],
        subtopic_weights=[],
        subtopic_prereqs=[],
        unit_prereqs=[],
    )
    assert pace.has_exam_date is True
    assert pace.days_left >= 360
    assert pace.mastered_subtopics == 0
    # Nothing mastered -> the observed rate is undefined, so no projection.
    assert pace.projected_days_to_finish == 0
    assert pace.on_track is False
    # The rate needed to master everything in time is still shown.
    assert pace.recommended_per_week > 0


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


def test_tier_for_deck_name_classifies_by_level():
    # Deck -> tier mapping (mirrors the Rust TierScope): the root deck is the
    # cross-unit tier, a unit deck is the within-unit tier, and a subtopic (leaf)
    # or any non-exam deck needs no scope (it is already a single subtopic).
    assert tier_for_deck_name(ROOT_DECK) == TIER_CROSS_UNIT
    assert tier_for_deck_name("SOA Exam P::General Probability") == TIER_WITHIN_UNIT
    assert (
        tier_for_deck_name("SOA Exam P::General Probability::Bayes' theorem") is None
    )
    assert tier_for_deck_name("Some Other Deck") is None
    assert tier_for_deck_name("") is None


def _rebuild_for(col, deck_id, other_id):
    # Force the v3 scheduler to rebuild its (cached) queue for `deck_id` after a
    # plain config change: a bare set_config does NOT invalidate the queue cache,
    # but re-selecting the deck (via a different deck) does.
    col.decks.select(other_id)
    col.decks.select(deck_id)


def test_tier_scope_keeps_blocked_out_of_cross_unit_live_queue():
    # Strict tiers, end to end through the LIVE Rust queue: on a freshly built
    # deck (mastery scheduler ON) every subtopic is still Blocked, so scoping the
    # root deck to the cross-unit tier must serve NOTHING — a still-blocked
    # subtopic must never leak into cross-unit study. Clearing the scope restores
    # normal study. This is the strict-tier fix exercised from Python.
    col = getEmptyCol()
    build_deck(col)
    root_id = col.decks.id(ROOT_DECK)
    default_id = col.decks.id("Default")

    # Baseline: with no tier scope the root deck serves its (blocked) cards.
    col.decks.select(root_id)
    assert col.sched.getCard() is not None

    # Scope the root to the cross-unit tier: nothing is cross-unit yet -> empty.
    set_tier_scope(col, root_id, TIER_CROSS_UNIT)
    _rebuild_for(col, root_id, default_id)
    assert col.sched.getCard() is None, "cross-unit must not serve blocked subtopics"

    # Remove the scope -> the root deck studies its whole subtree again.
    clear_tier_scope(col)
    _rebuild_for(col, root_id, default_id)
    assert col.sched.getCard() is not None


def test_tier_scope_is_deck_keyed_and_read_only():
    # The scope is keyed to the deck it was set for, so a root cross-unit scope
    # must NOT affect a different (subtopic) deck; studying that subtopic still
    # works. And scoping is read-only: no revlog rows are written by building the
    # scoped queue (undo/integrity are untouched).
    col = getEmptyCol()
    build_deck(col)
    root_id = col.decks.id(ROOT_DECK)
    set_tier_scope(col, root_id, TIER_CROSS_UNIT)

    sub_deck = "SOA Exam P::General Probability::Sets, sample spaces, and axioms"
    # Selecting the subtopic deck (a different deck) rebuilds its queue; the root-
    # keyed scope must not apply here.
    col.decks.select(col.decks.id(sub_deck))
    revlog_before = col.db.scalar("select count() from revlog")
    assert (
        col.sched.getCard() is not None
    ), "a root-keyed scope must not affect a subtopic deck"
    # Building the (scoped) queue never writes to the revlog.
    assert col.db.scalar("select count() from revlog") == revlog_before
