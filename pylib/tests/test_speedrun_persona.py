# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from anki.speedrun.persona import (
    SYNTHETIC_LABEL,
    answer_items,
    default_persona,
    experienced_persona,
    new_persona,
    p_correct,
    review_grades,
    synthetic_cohort,
)
from anki.speedrun.soa_sample import load_sample_items


def _mean_skill(persona) -> float:
    return sum(persona.skill.values()) / len(persona.skill)


def test_persona_is_labelled_synthetic():
    # Anti-fabrication: a persona must never look like a real measurement. Every
    # scenario persona carries the synthetic label so nothing looks like real data.
    for persona in (default_persona(), new_persona(), experienced_persona()):
        assert persona.label == SYNTHETIC_LABEL


def test_scenario_personas_are_deterministic_and_cover_every_subtopic():
    for factory in (new_persona, experienced_persona):
        a = factory(123)
        b = factory(123)
        assert a.skill == b.skill
        assert len(a.skill) == 19
        assert all(0.0 <= v <= 1.0 for v in a.skill.values())


def test_scenario_personas_are_ordered_new_intermediate_experienced():
    # The three mock users span the readiness range: barely-ready < borderline <
    # well-prepared. Ordering the mean latent skill keeps the demo scenarios
    # honestly distinct (new abstains, experienced clears every gate).
    assert (
        _mean_skill(new_persona())
        < _mean_skill(default_persona())
        < _mean_skill(experienced_persona())
    )


def test_default_persona_is_deterministic():
    a = default_persona(123)
    b = default_persona(123)
    assert a.skill == b.skill
    # Different seed -> different profile.
    assert default_persona(124).skill != a.skill


def test_skill_covers_every_subtopic_in_unit_range():
    p = default_persona()
    assert len(p.skill) == 19
    assert all(0.0 <= v <= 1.0 for v in p.skill.values())


def test_p_correct_increases_with_skill():
    # Two personas identical except skill on one subtopic: higher skill -> higher
    # P(correct) on a new question, holding difficulty fixed.
    tag = "subtopic::general::bayes"
    strong = default_persona()
    strong.skill[tag] = 0.95
    weak = default_persona()
    weak.skill[tag] = 0.15
    assert p_correct(strong, tag, "medium") > p_correct(weak, tag, "medium")


def test_answer_items_deterministic_and_binary():
    p = default_persona()
    items = load_sample_items()
    r1 = answer_items(p, items, seed_salt="x")
    r2 = answer_items(p, items, seed_salt="x")
    assert [r.correct for r in r1] == [r.correct for r in r2]
    assert all(r.correct in (0, 1) for r in r1)
    # A different salt (a different test sitting) can differ.
    assert len(r1) == len(items)


def test_review_grades_reflect_skill():
    p = default_persona()
    strong_tag = max(p.skill, key=lambda t: p.skill[t])
    weak_tag = min(p.skill, key=lambda t: p.skill[t])
    strong = review_grades(p, strong_tag, 40)
    weak = review_grades(p, weak_tag, 40)
    # Eases are Anki passes(3)/fails(1); the stronger subtopic passes more often.
    assert sum(1 for e in strong if e >= 2) > sum(1 for e in weak if e >= 2)
    # Deterministic.
    assert review_grades(p, strong_tag, 40) == strong


def test_cohort_is_sized_and_reproducible():
    a = synthetic_cohort(10, seed=1)
    b = synthetic_cohort(10, seed=1)
    assert len(a) == 10
    assert [p.skill for p in a] == [p.skill for p in b]
