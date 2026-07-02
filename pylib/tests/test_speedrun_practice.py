# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from anki.speedrun.practice_test import (
    _unit_allocation,
    assemble_test,
    grade,
    practice_stats,
    record_test,
    reset_practice_stats,
)
from anki.speedrun.soa_sample import load_sample_items
from tests.shared import getEmptyCol


def test_allocation_is_section_weighted_and_sums_to_n():
    # 30 questions split by the official section midpoints (26.5 / 47 / 26.5):
    # univariate (the heaviest unit) gets the most, and the split sums to n.
    alloc = _unit_allocation(30)
    assert sum(alloc.values()) == 30
    assert alloc["univariate"] > alloc["general"]
    assert alloc["univariate"] > alloc["multivariate"]


def test_assemble_test_is_sized_and_deterministic():
    a = assemble_test(n=30, seed=7)
    b = assemble_test(n=30, seed=7)
    assert len(a) == 30
    assert [it.id for it in a] == [it.id for it in b]
    # No duplicate items in a single test.
    assert len({it.id for it in a}) == 30


def test_grade_counts_correct_and_per_unit():
    items = load_sample_items()[:10]
    responses = {it.id: (1 if i % 2 == 0 else 0) for i, it in enumerate(items)}
    result = grade(items, responses)
    assert result.questions == 10
    assert result.correct == sum(responses.values())
    # per-unit totals sum back to the whole test.
    assert sum(t for _c, t in result.per_unit.values()) == 10


def test_missing_response_counts_wrong():
    items = load_sample_items()[:5]
    result = grade(items, {})  # answered nothing
    assert result.correct == 0


def test_record_test_accumulates_in_config():
    col = getEmptyCol()
    assert practice_stats(col) == {"questions": 0, "correct": 0, "tests": 0}
    items = load_sample_items()[:10]
    r1 = grade(items, {it.id: 1 for it in items})  # all correct
    record_test(col, r1)
    stats = practice_stats(col)
    assert stats == {"questions": 10, "correct": 10, "tests": 1}
    # A second test accumulates.
    r2 = grade(items, {})  # all wrong
    record_test(col, r2)
    assert practice_stats(col) == {"questions": 20, "correct": 10, "tests": 2}
    # Reset clears the evidence (readiness returns to abstaining).
    reset_practice_stats(col)
    assert practice_stats(col) == {"questions": 0, "correct": 0, "tests": 0}
