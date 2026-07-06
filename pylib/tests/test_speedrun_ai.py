# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import pytest

from anki import speedrun_pb2
from anki.speedrun import expected_subtopic_tags, unit_weights
from anki.speedrun.ai import (
    AI_PROVIDER_KEY,
    AI_UNREVIEWED_TAG,
    AiDisabledError,
    add_generated_cards,
    ai_enabled,
    approve_generated_note,
    available_provider,
    candidate_tag,
    classify_subtopic,
    generate_cards,
    openai_key_present,
    openai_package_available,
    require_ai,
    set_ai_enabled,
)
from tests.shared import getEmptyCol


def _enable_stub(col):
    # Turn AI on but pin the offline stub provider, so tests never hit a network
    # provider even if OPENAI_API_KEY happens to be set in the environment.
    set_ai_enabled(col, True)
    col.set_config(AI_PROVIDER_KEY, "stub")


def test_ai_disabled_by_default():
    col = getEmptyCol()
    assert ai_enabled(col) is False


def test_toggle_ai_flag():
    col = getEmptyCol()
    set_ai_enabled(col, True)
    assert ai_enabled(col) is True
    set_ai_enabled(col, False)
    assert ai_enabled(col) is False


def test_require_ai_raises_when_off():
    col = getEmptyCol()
    with pytest.raises(AiDisabledError):
        require_ai(col)


def test_scores_with_ai_off():
    # The scoring path must not depend on AI. With AI off (the default), the
    # readiness RPC still returns a result (NoScore on an empty collection).
    col = getEmptyCol()
    assert ai_enabled(col) is False
    units = [
        speedrun_pb2.UnitWeight(unit_id=uid, weight=w) for uid, w in unit_weights()
    ]
    result = col._backend.compute_readiness(
        expected_subtopics=expected_subtopic_tags(),
        units=units,
    )
    assert result.WhichOneof("value") == "no_score"


def test_three_signals_compute_with_ai_off():
    # Rubric AUTOMATIC-FAIL guard: with AI off (the default) all three signals
    # still compute with no AI import or dependency.
    from anki.speedrun.calibration import calibration_report
    from anki.speedrun.performance import PerformanceExample, run_pipeline

    col = getEmptyCol()
    assert ai_enabled(col) is False
    units = [speedrun_pb2.UnitWeight(unit_id=u, weight=w) for u, w in unit_weights()]

    # Readiness (honest NoScore on an empty deck) computes with AI off.
    r = col._backend.compute_readiness(
        expected_subtopics=expected_subtopic_tags(), units=units
    )
    assert r.WhichOneof("value") in ("no_score", "score")

    # The measured mastery signal behind the dashboard computes with AI off.
    ms = col._backend.get_mastery_state(
        expected_subtopics=expected_subtopic_tags(),
        units=units,
        subtopic_weights=[],
        subtopic_prereqs=[],
        unit_prereqs=[],
    )
    assert len(ms.subtopics) == 19

    # Performance model + memory-calibration metrics are pure Python, no AI.
    data = [
        PerformanceExample(
            f"q{i}", 0.9 if i % 2 else 0.1, 0.5, 0.5, 0.5, i % 2, f"q{i}"
        )
        for i in range(80)
    ]
    assert run_pipeline(data, seed=0, min_test=10, min_samples=10).status == "ok"
    assert (
        calibration_report([0.2, 0.8] * 60, [0, 1] * 60, min_samples=10).status == "ok"
    )


def test_generate_requires_ai_on():
    col = getEmptyCol()
    with pytest.raises(AiDisabledError):
        generate_cards(
            col, "subtopic::general::bayes", "src", "P(A|B)=P(B|A)P(A)/P(B).", 3
        )


def test_generate_with_stub_is_sourced():
    col = getEmptyCol()
    _enable_stub(col)
    cards = generate_cards(
        col,
        "subtopic::general::bayes",
        "Bayes note",
        "Bayes theorem relates conditional probabilities. The posterior is proportional to the likelihood times the prior.",
        n=4,
    )
    assert len(cards) == 4
    # Every AI output must trace to a named source (AUTOMATIC-FAIL rule).
    assert all(c.source_name == "Bayes note" for c in cards)
    assert all(c.front and c.back for c in cards)


def test_generated_cards_are_quarantined_from_coverage():
    col = getEmptyCol()
    _enable_stub(col)
    cards = generate_cards(
        col,
        "subtopic::general::bayes",
        "Bayes note",
        "The posterior combines prior and likelihood.",
        n=3,
    )
    note_ids = add_generated_cards(col, cards)
    assert len(note_ids) == 3
    # They carry the quarantine + source + CANDIDATE tags, never the real
    # subtopic tag, so coverage/mastery are untouched until approval.
    assert col.find_notes("tag:subtopic::*") == []
    assert col.find_notes(f"tag:{AI_UNREVIEWED_TAG}")
    assert col.find_notes("tag:src::*")
    assert col.find_notes("tag:subtopic_candidate::*")


def test_approve_promotes_candidate_to_real_subtopic():
    col = getEmptyCol()
    _enable_stub(col)
    cards = generate_cards(
        col,
        "subtopic::general::bayes",
        "Bayes note",
        "The posterior combines prior and likelihood.",
        n=1,
    )
    [nid] = add_generated_cards(col, cards)
    assert col.find_notes("tag:subtopic::*") == []  # not counted yet
    approve_generated_note(col, nid)
    # Now it is a real syllabus card and the quarantine tag is gone.
    assert col.find_notes("tag:subtopic::general::bayes")
    assert col.find_notes(f"tag:{AI_UNREVIEWED_TAG}") == []


def test_classify_requires_ai_on():
    col = getEmptyCol()
    with pytest.raises(AiDisabledError):
        classify_subtopic(col, "Find P(A given B).")


def test_classify_with_stub_returns_sourced_suggestions():
    col = getEmptyCol()
    _enable_stub(col)
    out = classify_subtopic(
        col, "Use Bayes theorem and total probability to find the posterior."
    )
    assert out and "subtopic" in out[0] and out[0]["source"]


def test_candidate_tag_roundtrip():
    assert (
        candidate_tag("subtopic::general::bayes")
        == "subtopic_candidate::general::bayes"
    )


def test_available_provider_is_none_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert available_provider() is None


def test_provider_preconditions_are_distinguishable(monkeypatch):
    # Regression: a missing ``openai`` package must NOT masquerade as a missing
    # key. The two preconditions are reported independently so the UI can name the
    # real cause; ``available_provider`` is exactly their conjunction.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-not-a-real-key")
    assert openai_key_present() is True
    both = openai_key_present() and openai_package_available()
    assert (available_provider() == "openai") is both

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert openai_key_present() is False
    # No key => no provider, regardless of whether the package is importable.
    assert available_provider() is None
