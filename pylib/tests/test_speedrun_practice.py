# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from anki.speedrun.practice_test import (
    PRACTICE_STATS_KEY,
    _unit_allocation,
    assemblable,
    assemble_test,
    grade,
    is_mcq,
    is_well_formatted,
    performance_by_subtopic,
    practice_stats,
    readiness_weight,
    record_test,
    reset_practice_stats,
)
from anki.speedrun.soa_sample import SampleItem, load_fallback_items, load_sample_items
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


def test_performance_by_subtopic_accumulates_separately():
    # Practice tests build a SEPARATE per-subtopic performance signal (used for
    # prerequisites + the map), distinct from the memory gate.
    col = getEmptyCol()
    assert performance_by_subtopic(col) == {}
    items = load_sample_items()[:8]
    responses = {it.id: (1 if i % 2 == 0 else 0) for i, it in enumerate(items)}
    record_test(col, grade(items, responses))
    perf = performance_by_subtopic(col)
    assert sum(c["questions"] for c in perf.values()) == len(items)
    assert sum(c["correct"] for c in perf.values()) == sum(responses.values())
    # per-subtopic totals line up with the graded items
    for it in items:
        assert it.subtopic in perf
    # accumulates across tests
    record_test(col, grade(items, responses))
    perf2 = performance_by_subtopic(col)
    assert sum(c["questions"] for c in perf2.values()) == 2 * len(items)


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


def test_readiness_weight_factors():
    # A full, whole-exam OFFICIAL test is the reference: weight 1.0. Narrower
    # scope or a generated source counts for proportionally less.
    assert readiness_weight("all", "official") == 1.0
    assert readiness_weight("unit", "official") == 0.6
    assert readiness_weight("subtopic", "official") == 0.4
    assert readiness_weight("all", "generated") == 0.7
    assert readiness_weight("subtopic", "generated") == 0.4 * 0.7
    # Unknown values fall back to the most conservative factor, never over 1.0.
    assert readiness_weight("bogus", "bogus") == 0.4 * 0.7


def test_record_test_stores_weighted_evidence_alongside_raw():
    # record_test keeps float weighted_questions/weighted_correct next to the raw
    # integer counts, so the readiness band can use the weighted proportion while
    # the give-up gate uses the raw count.
    col = getEmptyCol()
    items = load_sample_items()[:10]
    # A full official test (weight 1.0): 8/10.
    record_test(
        col,
        grade(items, {it.id: (1 if i < 8 else 0) for i, it in enumerate(items)}),
        scope="all",
        source="official",
    )
    raw = col.get_config(PRACTICE_STATS_KEY)
    assert raw["questions"] == 10 and raw["correct"] == 8
    assert raw["weighted_questions"] == 10.0 and raw["weighted_correct"] == 8.0
    # A subtopic generated quiz (weight 0.4*0.7 = 0.28): 5/10 correct.
    record_test(
        col,
        grade(items, {it.id: (1 if i < 5 else 0) for i, it in enumerate(items)}),
        scope="subtopic",
        source="generated",
    )
    raw = col.get_config(PRACTICE_STATS_KEY)
    # Raw counts add the full questions; weighted counts add the discounted ones.
    assert raw["questions"] == 20 and raw["correct"] == 13
    assert raw["weighted_questions"] == 10.0 + 0.28 * 10
    assert raw["weighted_correct"] == 8.0 + 0.28 * 5
    # The public int-triple view is unchanged (backward compatible).
    assert practice_stats(col) == {"questions": 20, "correct": 13, "tests": 2}


def test_assembled_pool_is_all_multiple_choice():
    # A test is 100% multiple choice: filtering the pool to is_mcq items and
    # assembling yields only items that render as real A-E choices.
    pool = [it for it in load_sample_items() if is_mcq(it)]
    chosen = assemble_test(n=30, seed=11, items=pool)
    assert len(chosen) == 30
    assert all(is_mcq(it) for it in chosen)


# --- Formatting-quality gate (a badly-formatted question is never shown) ------


def _item(question: str, answer: str = "0.5", id: str = "t") -> SampleItem:
    return SampleItem(
        id=id,
        question=question,
        subtopic="subtopic::general::sets_axioms",
        difficulty="easy",
        answer=answer,
    )


def test_gate_passes_clean_latex_and_word_problems():
    # Math wrapped in balanced inline \( \) LaTeX renders cleanly.
    assert is_well_formatted(
        _item(r"Find \(P(A \cup B)\) when \(P(A) = 0.3\).", r"\(0.5\)")
    )
    # Balanced display \[ \] LaTeX, including a piecewise \begin{cases}.
    assert is_well_formatted(
        _item(
            r"Density \[ f(x) = \begin{cases} 2x, & 0 < x < 1 \\ 0 \end{cases} \]",
            "0.5",
        )
    )
    # A pure word problem (prose + plain numbers, no real math) renders as text.
    assert is_well_formatted(
        _item(
            "A committee of 4 is chosen from 12 people. Find the probability.", "0.42"
        )
    )


def test_gate_excludes_mangled_math():
    # Bare lost superscript "X2" (was X^2) sitting in raw text.
    assert not is_well_formatted(_item("Let Y = X2. Find E[Y].", "3"))
    # Stray caret from an e^(-x/2) that lost its LaTeX.
    assert not is_well_formatted(_item("The density is e^(-x/2) for x > 0.", "0.5"))
    # Lost exponent on a parenthesised base "(1+x)-4".
    assert not is_well_formatted(
        _item("f is proportional to (1+x)-4 on the interval.", "0.5")
    )
    # Unicode math (integral, less-than-or-equal) sitting in raw text.
    assert not is_well_formatted(_item("Evaluate ∫ f(x) dx where x ≤ 2.", "0.5"))
    # Unbalanced \( with no closing \).
    assert not is_well_formatted(_item(r"Compute \(P(A) for the event.", "0.5"))
    # A mangled ANSWER fails too (the superscript was lost in the answer).
    assert not is_well_formatted(_item("Find the second moment.", "E[X2] = 27"))


def test_gate_keeps_option_markers_and_ranges():
    # Genuine (A)-(E) option markers and roman-numeral lists are SPACED, so they
    # must not be mistaken for a lost exponent ")digit".
    assert is_well_formatted(
        _item("Calculate. (A) 24% (B) 36% (C) 41% (D) 52% (E) 60%", "D) 52%")
    )
    assert is_well_formatted(
        _item("(i) 28% watch A (ii) 29% watch B. Find the probability.", "0.5")
    )


def test_assemblable_requires_both_well_formatted_and_mcq():
    # Clean numeric word problem: well-formatted AND MCQ-able.
    assert assemblable(_item("Committee of 4 from 12. Find P.", "0.42"))
    # A non-numeric (letter-only) answer can't become A-E choices -> excluded.
    assert not assemblable(_item("Name the distribution.", "Exponential"))
    # A mangled question is excluded even with a numeric answer.
    assert not assemblable(_item("Find E[X2].", "27"))


def test_committed_fallback_corpus_all_passes_gate():
    # The committed, no-copyright fallback corpus is already clean LaTeX; the
    # heuristic must never drop a clean item (else it would eat good questions).
    fb = load_fallback_items()
    assert fb
    assert all(is_well_formatted(it) for it in fb)
    assert all(assemblable(it) for it in fb)


def test_assemble_test_never_yields_badly_formatted_items():
    # Whatever pool is passed, a badly-formatted item can NEVER be assembled.
    mangled = [
        _item("The density is e^(-x/2) for x > 0.", "0.5", id=f"bad-{i}")
        for i in range(40)
    ]
    # No fallback: the entire junk pool is excluded, so we get an (empty) test
    # rather than a badly-formatted one.
    assert assemble_test(n=30, seed=1, items=mangled) == []
    # With the committed clean fallback, a valid test is still assembled (every
    # item well-formatted) instead of showing junk.
    rescued = assemble_test(n=30, seed=1, items=mangled, fallback=load_fallback_items())
    assert len(rescued) == 30
    assert all(is_well_formatted(it) and is_mcq(it) for it in rescued)
