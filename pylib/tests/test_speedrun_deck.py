# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from anki.speedrun import (
    apply_prereqs_config,
    deck_name_for_subtopic_tag,
    expected_subtopic_tags,
    load_topics,
    subtopic_prereqs,
    subtopic_tag,
    unit_deck_name,
    unit_prereqs,
)
from anki.speedrun.seed import (
    KIND_NUMERIC,
    SEED_CARDS,
    SEEDED_KEY,
    SHORT_ANSWER_NOTETYPE,
    build_deck,
    convert_seeded_short_answer_to_basic,
    ensure_short_answer_notetype,
    seed_if_missing,
)
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


def test_all_seeded_cards_are_basic_flashcards_with_worked_solutions():
    # Every seeded card is now a stock Basic flip card the student self-grades;
    # numeric ones show the concise answer + the worked solution on the Back. No
    # typed {{type:Answer}} short-answer notes are created for the seeded deck.
    col = getEmptyCol()
    build_deck(col)

    assert col.find_notes("tag:format::short_answer") == []
    flashcards = col.find_notes("tag:format::flashcard")
    assert len(flashcards) == len(SEED_CARDS)
    for nid in flashcards:
        assert col.get_note(nid).note_type()["name"] == "Basic"

    # A computational card renders the answer AND the worked solution (MathJax
    # preserved) on the Basic back.
    numeric = [c for c in SEED_CARDS if c.kind == KIND_NUMERIC]
    assert numeric, "expected some computational cards"
    target = next(c for c in numeric if c.answer == "120")

    def note_by_front(front: str):
        for nid in col.find_notes("tag:difficulty::*"):
            note = col.get_note(nid)
            if note["Front"] == front:
                return note
        return None

    note = note_by_front(target.front)
    assert note is not None
    assert note.note_type()["name"] == "Basic"
    assert "120" in note["Back"]  # the concise answer
    assert "\\binom" in note["Back"]  # the worked solution + MathJax, preserved


def test_convert_seeded_short_answer_to_basic_migrates_only_curriculum_cards():
    # A collection seeded BEFORE this change still holds typed "SOA Short Answer"
    # curriculum cards. The one-off migration rewrites them as Basic flip cards in
    # place (preserving each card's scheduling row) and leaves AI quarantine cards
    # (same notetype, no difficulty tag) untouched. It is idempotent.
    col = getEmptyCol()
    short_answer = ensure_short_answer_notetype(col)

    # Old-style seeded curriculum card (typed short-answer).
    deck_id = col.decks.id("SOA Exam P::General Probability::Combinatorics")
    note = col.new_note(short_answer)
    note["Front"] = "Choose 3 of 10 when order doesn't matter?"
    note["Answer"] = "120"
    note["Explanation"] = r"\[ \binom{10}{3} = 120 \]"
    note.add_tag("unit::general")
    note.add_tag("subtopic::general::combinatorics")
    note.add_tag("difficulty::easy")
    note.add_tag("format::short_answer")
    col.add_note(note, deck_id)
    original_card_id = note.cards()[0].id

    # AI quarantine card: SAME notetype, but no difficulty tag -> left as-is.
    ai_deck = col.decks.id("SOA Exam P::AI (unreviewed)")
    ai_note = col.new_note(short_answer)
    ai_note["Front"] = "AI generated?"
    ai_note["Answer"] = "maybe"
    ai_note.add_tag("ai::unreviewed")
    ai_note.add_tag("subtopic_candidate::general::bayes")
    ai_note.add_tag("format::short_answer")
    col.add_note(ai_note, ai_deck)

    converted = convert_seeded_short_answer_to_basic(col)
    assert converted == 1

    # The curriculum card is now Basic, its card (FSRS scheduling row) preserved,
    # and the Back carries the answer + the worked solution (MathJax intact).
    note.load()
    assert note.note_type()["name"] == "Basic"
    assert len(note.cards()) == 1
    assert note.cards()[0].id == original_card_id
    assert "120" in note["Back"]
    assert "\\binom" in note["Back"]
    assert "format::flashcard" in note.tags
    assert "format::short_answer" not in note.tags

    # The AI quarantine card is untouched (still typed short-answer).
    ai_note.load()
    assert ai_note.note_type()["name"] == SHORT_ANSWER_NOTETYPE
    assert "format::short_answer" in ai_note.tags

    # Idempotent: a second run finds nothing to convert.
    assert convert_seeded_short_answer_to_basic(col) == 0


def test_seed_if_missing_builds_once_then_is_a_noop():
    # The main deck is not optional: it auto-builds on first open, once.
    col = getEmptyCol()
    assert col.get_config(SEEDED_KEY, False) is False
    assert seed_if_missing(col) is True  # built it now
    n = len(col.find_notes("tag:subtopic::*"))
    assert n == len(SEED_CARDS)
    # Second call is a no-op (guarded by the flag) — no duplicate deck.
    assert seed_if_missing(col) is False
    assert len(col.find_notes("tag:subtopic::*")) == n


def test_prereqs_form_a_valid_dag():
    topics = load_topics()
    tags = set(expected_subtopic_tags(topics))
    sp = dict(subtopic_prereqs(topics))
    assert set(sp) == tags
    for tag, prereqs in sp.items():
        for p in prereqs:
            assert p in tags, f"{tag} -> unknown prereq {p}"
            assert p != tag
    # Acyclic: a DFS finds no back-edge (grey node).
    white, grey, black = 0, 1, 2
    color = dict.fromkeys(tags, white)

    def visit(t: str) -> None:
        color[t] = grey
        for p in sp.get(t, []):
            assert color[p] != grey, f"cycle at {t} -> {p}"
            if color[p] == white:
                visit(p)
        color[t] = black

    for t in tags:
        if color[t] == white:
            visit(t)

    up = dict(unit_prereqs(topics))
    assert up["general"] == []
    assert up["univariate"] == ["general"]
    assert up["multivariate"] == ["univariate"]


def test_apply_prereqs_config_writes_the_dag():
    col = getEmptyCol()
    apply_prereqs_config(col)
    sp = col.get_config("speedrunSubtopicPrereqs")
    assert sp["subtopic::general::bayes"] == ["subtopic::general::conditional"]
    assert sp["subtopic::general::sets_axioms"] == []
    up = col.get_config("speedrunUnitPrereqs")
    assert up["multivariate"] == ["univariate"]


def test_deck_has_multiple_difficulties_per_syllabus():
    # a mix of recall + applied cards means more than one card per unit
    from collections import Counter

    by_difficulty = Counter(card.difficulty for card in SEED_CARDS)
    assert set(by_difficulty) <= {"easy", "medium", "hard"}
    # graded difficulty is represented, not a single flat level
    assert len(by_difficulty) >= 2
